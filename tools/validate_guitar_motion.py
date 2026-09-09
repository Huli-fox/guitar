"""Offline geometric diagnostics for the repository's recorded guitar motion.

Run: python tools/validate_guitar_motion.py
Requires numpy, but neither Isaac Gym nor Blender. See validate_guitar_motion.md.
"""
import argparse
import csv
from fractions import Fraction
import html
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FINGERS = ('index', 'middle', 'ring', 'pinky')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rotation(q):
    q = np.asarray(q, dtype=float)
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def load_recording(path):
    data = read_json(path)
    if data.get('up_axis') != 'z' or data.get('quaternion_order') != 'xyzw':
        raise ValueError('Expected z-up, xyzw recording in metres')
    fps = data['fps']
    if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        raise ValueError('fps must be finite and positive')
    frames, names = data['frames'], data['links']
    if len(frames) < 3 or data.get('num_frames') != len(frames):
        raise ValueError('Need at least 3 frames and matching num_frames')
    if not names or len(set(names)) != len(names):
        raise ValueError('links must be nonempty and unique')
    ids = np.array([f['frame'] for f in frames])
    times = np.array([f['time'] for f in frames], dtype=float)
    if not np.issubdtype(ids.dtype, np.integer) or not np.all(np.diff(ids) == 1):
        raise ValueError('Frame numbers must be consecutive integers')
    if not np.all(np.isfinite(times)) or not np.allclose(np.diff(times), 1/fps, atol=1e-7, rtol=0):
        raise ValueError('Timestamps must be finite, increasing and consistent with fps')
    if any(f.get('reset') for f in frames):
        raise ValueError('Reset markers have ambiguous legacy timing; split/re-record before validation')
    if any(set(f['links']) != set(names) for f in frames):
        raise ValueError('Every frame must have exactly the declared links')
    positions, quaternions = {}, {}
    for name in names:
        p = np.array([f['links'][name]['position'] for f in frames], dtype=float)
        q = np.array([f['links'][name]['quaternion'] for f in frames], dtype=float)
        if p.shape != (len(frames), 3) or q.shape != (len(frames), 4):
            raise ValueError('Invalid pose dimensions: ' + name)
        if not np.all(np.isfinite(p)) or not np.all(np.isfinite(q)):
            raise ValueError('Nonfinite pose: ' + name)
        norms = np.linalg.norm(q, axis=1)
        if np.max(np.abs(norms-1)) > 1e-3:
            raise ValueError('Nonunit quaternion: ' + name)
        positions[name], quaternions[name] = p, q/norms[:, None]
    return data, ids, times, positions, quaternions


def source_frames():
    specs = {}
    def visit(body, parent):
        name = body.get('name')
        if {'euler', 'axisangle', 'xyaxes', 'zaxis'} & body.attrib.keys():
            raise ValueError('Unsupported MJCF orientation: ' + name)
        p = np.array(list(map(float, body.get('pos', '0 0 0').split())))
        w, x, y, z = map(float, body.get('quat', '1 0 0 0').split())
        spec = (parent, p, rotation([x, y, z, w]), body.find('joint') is not None)
        if name in specs:
            old = specs[name]
            if old[0] != parent or not np.allclose(old[1], p) or not np.allclose(old[2], spec[2]):
                raise ValueError('Conflicting source frame: ' + name)
        specs[name] = spec
        for child in body.findall('body'):
            visit(child, name)
    for filename in ('left_hand_guitar.xml', 'right_hand.xml'):
        for body in ET.parse(ROOT/'assets'/filename).getroot().findall('worldbody/body'):
            visit(body, None)
    return specs


def world_pose(name, index, positions, quaternions, specs):
    if name in positions:
        return positions[name][index], rotation(quaternions[name][index])
    parent, p, r, moving = specs[name]
    if moving:
        raise ValueError('Cannot infer unrecorded movable frame: ' + name)
    if parent is None:
        return p, r
    pp, pr = world_pose(parent, index, positions, quaternions, specs)
    return pp + pr @ p, pr @ r


def segment_closest(a, b, c, d):
    """Closest points of finite 3-D segments, including parallel/degenerate ones."""
    u, v, w = b-a, d-c, a-c
    aa, bb, cc, dd, ee = u@u, u@v, v@v, u@w, v@w
    if aa < 1e-20:
        t = np.clip(ee/cc, 0, 1) if cc > 1e-20 else 0
        return a, c+t*v
    if cc < 1e-20:
        return a+np.clip(-dd/aa, 0, 1)*u, c
    den = aa*cc-bb*bb
    s = np.clip((bb*ee-cc*dd)/den, 0, 1) if den > 1e-20 else 0
    t = (bb*s+ee)/cc
    if t < 0:
        t, s = 0, np.clip(-dd/aa, 0, 1)
    elif t > 1:
        t, s = 1, np.clip((bb-dd)/aa, 0, 1)
    return a+s*u, c+t*v


def score_events(path, fps, first_frame, track_index):
    tracks = read_json(path)
    if not 0 <= track_index < len(tracks):
        raise ValueError('Score track index out of range')
    track = tracks[track_index]
    tempo = float(track['tempo'])
    if not math.isfinite(tempo) or tempo <= 0 or not track['notes']:
        raise ValueError('Invalid tempo or empty score')
    intervals = []
    for note in track['notes']:
        effects = note.get('effects', {})
        if set(effects) - {'tied', 'hammer/pull'}:
            raise ValueError('Only tied and hammer/pull effects are supported')
        for values in effects.values():
            if len(values) != 6 or any(v not in (0, 1) for v in values):
                raise ValueError('Effects must contain six binary flags')
        frets = note['frets']
        if len(frets) != 6 or any(type(f) is not int or not -1 <= f <= 22 for f in frets):
            raise ValueError('Expected six fret numbers in [-1, 22]')
        value = note['t']
        duration = float(Fraction(value))*64 if isinstance(value, str) else float(value)*tempo/240*64
        if not math.isfinite(duration) or duration <= 0 or not duration.is_integer():
            raise ValueError('Only positive durations on the 1/64 grid are supported')
        intervals.append(duration)
    minimum = min(intervals)
    # Mirrors env.py reset_goal, with merge_repeated_notes=False and no augmentation.
    scale = round(max(5, 60*fps/16*minimum/tempo))/minimum
    events, cursor = [], first_frame
    for i, (note, duration) in enumerate(zip(track['notes'], intervals)):
        length = round(duration*scale)
        effects = note.get('effects', {})
        active = [s for s, fret in enumerate(note['frets']) if fret >= 0 and
                  sum(v[s] for v in effects.values()) % 2 == 0]
        pluck_strings = list(range(min(active)+1, max(active)+2)) if active else []
        events.append(dict(event=i, start_frame=cursor, end_frame_exclusive=cursor+length,
                           frets=note['frets'], pluck_strings=pluck_strings))
        cursor += length
    return events


def summary(values):
    return dict(min=float(np.min(values)), median=float(np.median(values)),
                p95=float(np.percentile(values, 95)), max=float(np.max(values)))


def kinematics(ids, times, positions, quaternions, args):
    metrics, rows, anomalies = {}, [], []
    dt = np.diff(times)
    for name, p in positions.items():
        velocity = np.diff(p, axis=0)/dt[:, None]
        speed = np.linalg.norm(velocity, axis=1)
        acceleration = np.linalg.norm(np.diff(velocity, axis=0)/((dt[1:]+dt[:-1])/2)[:, None], axis=1)
        dots = np.sum(quaternions[name][1:]*quaternions[name][:-1], axis=1)
        angular = np.degrees(2*np.arccos(np.clip(np.abs(dots), 0, 1)))/dt
        metrics[name] = dict(speed_m_s=summary(speed), acceleration_m_s2=summary(acceleration),
                             angular_speed_deg_s=summary(angular), quaternion_sign_flips=int(np.sum(dots < 0)))
        for j in range(1, len(ids)):
            a = float(acceleration[j-2]) if j >= 2 else None
            row = dict(frame=int(ids[j]), time=float(times[j]), node=name,
                       speed_m_s=float(speed[j-1]), acceleration_m_s2=a,
                       angular_speed_deg_s=float(angular[j-1]))
            rows.append(row)
            reasons = []
            if speed[j-1] > args.speed_threshold: reasons.append('speed')
            if a is not None and a > args.acceleration_threshold: reasons.append('acceleration')
            if angular[j-1] > args.angular_threshold: reasons.append('angular_speed')
            if dots[j-1] < 0: reasons.append('quaternion_sign_flip')
            if reasons: anomalies.append(dict(row, reasons=reasons))
    return metrics, rows, anomalies


def geometry(ids, positions, quaternions, specs, radius):
    pressed, distances, crossings, tips = [], [], [], []
    previous_pick = None
    for j, frame in enumerate(ids):
        gp, gr = world_pose('guitar', j, positions, quaternions, specs)
        def local(name):
            return gr.T @ (world_pose(name, j, positions, quaternions, specs)[0]-gp)
        strings = [(local(f'G:string{s}'), local(f'G:string{s}_end')) for s in range(1, 7)]
        frets = [local('G:nut')[1]] + [local(f'G:fret{f}')[1] for f in range(1, 23)]
        chains = [[local(f'LH:{finger}{suffix}') for suffix in ('1', '2', '3', '_top')]
                  for finger in FINGERS]
        tips.append([chain[-1].tolist() for chain in chains])
        board = np.zeros((6, 22), dtype=bool)
        fret_distances = np.full((6, 22), np.inf)
        for s, (a, b) in enumerate(strings):
            for chain in chains:
                for c, d in zip(chain, chain[1:]):
                    on_string, on_finger = segment_closest(a, b, c, d)
                    dist = np.linalg.norm(on_string-on_finger)
                    for f in range(22):
                        if frets[f+1] < on_string[1] < frets[f] and dist < radius:
                            board[s, f] = True
                        # Distance to the string segment inside the target fret region.
                        lo = a + (b-a)*((frets[f+1]-a[1])/(b[1]-a[1]))
                        hi = a + (b-a)*((frets[f]-a[1])/(b[1]-a[1]))
                        u, v = segment_closest(lo, hi, c, d)
                        fret_distances[s, f] = min(fret_distances[s, f], np.linalg.norm(u-v))
        pressed.append(np.max(board*np.arange(1, 23), axis=1))
        distances.append(fret_distances)
        pick = local('RH:pick')
        if previous_pick is not None:
            delta = pick-previous_pick
            for s, (a, b) in enumerate(strings):
                direction = b-a
                matrix = np.column_stack((delta[:2], -direction[:2]))
                if abs(np.linalg.det(matrix)) < 1e-12:
                    continue
                t, u = np.linalg.solve(matrix, a[:2]-previous_pick[:2])
                if 0 < t <= 1 and 0 <= u <= 1:
                    depth = float((a+u*direction)[2]-(previous_pick+t*delta)[2])
                    crossings.append(dict(frame=float(ids[j-1]+t), string=s+1,
                                          below_string_m=depth, pluck_candidate=depth > 0,
                                          direction_x=int(np.sign(delta[0]))))
        previous_pick = pick
    return np.array(pressed), np.array(distances), crossings, np.array(tips)


def compare_events(events, ids, pressed, distances, crossings):
    results = []
    for event in events:
        start, end = event['start_frame'], event['end_frame_exclusive']
        mask = (ids >= start) & (ids < end)
        if not np.any(mask): continue
        strings = []
        # Bimanual policy fills gaps between targeted strings for strumming.
        pluck_strings = {s-1 for s in event['pluck_strings']}
        for s, fret in enumerate(event['frets']):
            if fret < 0 and s not in pluck_strings: continue
            hits = [c for c in crossings if c['string'] == s+1 and c['pluck_candidate'] and start <= c['frame'] < end]
            item = dict(string=s+1, target_fret=fret, expected_pluck=s in pluck_strings, pluck_count=len(hits),
                        first_pluck_offset_frames=hits[0]['frame']-start if hits else None)
            if fret >= 0:
                item['matching_press_fraction'] = float(np.mean(pressed[mask, s] == fret))
            if fret > 0:
                item['finger_axis_to_fret_string_m'] = summary(distances[mask, s, fret-1])
            strings.append(item)
        unexpected = [c for c in crossings if c['pluck_candidate'] and start <= c['frame'] < end and c['string']-1 not in pluck_strings]
        results.append(dict(event, partial=bool(start < ids[0] or end > ids[-1]+1),
                            sampled_frames=int(np.sum(mask)), strings=strings,
                            unexpected_pluck_candidates=unexpected))
    return results


def write_csv(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path, report, rows):
    charts = []
    for metric, label in (('speed_m_s', 'Speed (m/s)'), ('acceleration_m_s2', 'Acceleration (m/s2)'),
                          ('angular_speed_deg_s', 'Angular speed (deg/s)')):
        series = {}
        for row in rows:
            if row[metric] is not None:
                series[row['frame']] = max(series.get(row['frame'], 0), row[metric])
        maximum = max(series.values()) or 1
        first, last = min(series), max(series)
        points = ' '.join(f'{50+900*(f-first)/max(1,last-first):.2f},{200-170*v/maximum:.2f}' for f,v in series.items())
        charts.append(f'<h2>{label}: maximum across nodes</h2><svg viewBox="0 0 1000 240" role="img" aria-label="{label}">'
                      f'<path d="M50 20 V200 H950" fill="none" stroke="gray"/>'
                      f'<polyline points="{points}" fill="none" stroke="#187b72"/>'
                      f'<text x="50" y="15">{maximum:.3f}</text><text x="50" y="225">Frame {first}</text>'
                      f'<text x="850" y="225">Frame {last}</text></svg>')
    path.write_text('<!doctype html><meta charset="utf-8"><title>Guitar motion diagnostics</title>'
                    '<style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 20px}svg{width:100%}pre{white-space:pre-wrap}</style>'
                    '<h1>Guitar motion diagnostics</h1><p>Geometric diagnostics, not physical contact certification. '
                    'Score alignment is assumed, not observed. Threshold exceedances require inspection.</p>'
                    + ''.join(charts) + '<h2>Summary</h2><pre>'
                    + html.escape(json.dumps(report['overview'], indent=2)) + '</pre>', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--motion', type=Path, default=ROOT/'recordings/left_hand_motion.json')
    parser.add_argument('--score', type=Path, default=ROOT/'assets/notes/canon_in_d_major1.json')
    parser.add_argument('--output', type=Path, default=ROOT/'blender/motion_validation')
    parser.add_argument('--track', type=int, default=0)
    parser.add_argument('--first-note-frame', type=int, default=5,
                        help='Assumed first note onset on recording frame axis; default 5 (5-step grace)')
    parser.add_argument('--speed-threshold', type=float, default=2)
    parser.add_argument('--acceleration-threshold', type=float, default=100)
    parser.add_argument('--angular-threshold', type=float, default=1500)
    parser.add_argument('--finger-radius', type=float, default=math.sqrt(0.00004))
    args = parser.parse_args(argv)
    try:
        for key in ('speed_threshold', 'acceleration_threshold', 'angular_threshold', 'finger_radius'):
            if not math.isfinite(getattr(args, key)) or getattr(args, key) <= 0:
                raise ValueError(key + ' must be finite and positive')
        data, ids, times, positions, quaternions = load_recording(args.motion)
        specs = source_frames()
        events = score_events(args.score, data['fps'], args.first_note_frame, args.track)
        metrics, rows, anomalies = kinematics(ids, times, positions, quaternions, args)
        pressed, distances, crossings, tips = geometry(ids, positions, quaternions, specs, args.finger_radius)
        event_results = compare_events(events, ids, pressed, distances, crossings)
        overview = dict(frames=len(ids), nodes=len(positions), fps=data['fps'],
                        anomaly_samples=len(anomalies), anomaly_frames=len({a['frame'] for a in anomalies}),
                        score_events_overlapping=len(event_results), score_events_total=len(events),
                        complete_score_covered=bool(ids[0] <= events[0]['start_frame'] and ids[-1]+1 >= events[-1]['end_frame_exclusive']),
                        pluck_candidates=sum(c['pluck_candidate'] for c in crossings),
                        lowest_fingertip_reference_z_m=float(tips[..., 2].min()))
        report = dict(schema_version=1, status='diagnostics_only', overview=overview,
                      sources=dict(motion=str(args.motion.resolve()), score=str(args.score.resolve())),
                      assumptions=dict(alignment='unverified reconstructed timeline', first_note_frame=args.first_note_frame,
                                       track=args.track, merge_repeated_notes=False, pitch_and_tempo_augmentation=False,
                                       guitar='recorded' if 'guitar' in positions else 'static MJCF root'),
                      limits=['No recorded score clock: event results depend on assumed onset/configuration.',
                              'First score pass only; no inference of unmarked resets or score loops.',
                              'Finger axes and radius approximate pressing; no mesh collision or force test.',
                              'Pluck candidates use XY crossing below string plane, not physical collision.',
                              'Threshold exceedances are inspection candidates, not animation failures.'],
                      thresholds=dict(speed_m_s=args.speed_threshold, acceleration_m_s2=args.acceleration_threshold,
                                      angular_speed_deg_s=args.angular_threshold, finger_radius_m=args.finger_radius),
                      kinematics=metrics, anomalies=anomalies, events=event_results, crossings=crossings)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'motion_metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        write_csv(args.output/'kinematics.csv', rows)
        write_csv(args.output/'anomalies.csv', [dict(a, reasons=';'.join(a['reasons'])) for a in anomalies])
        write_csv(args.output/'pressing.csv', [dict(frame=int(f), **{f'string{s+1}_fret': int(pressed[j,s]) for s in range(6)}) for j,f in enumerate(ids)])
        write_csv(args.output/'crossings.csv', crossings)
        markers = [dict(frame=e['start_frame'], name=f"Estimated note {e['event']}: {e['frets']}")
                   for e in event_results if ids[0] <= e['start_frame'] <= ids[-1]]
        (args.output/'event_markers.json').write_text(json.dumps(markers, indent=2), encoding='utf-8')
        (args.output/'import_markers.py').write_text(
            'import bpy\nimport json\nfrom pathlib import Path\n'
            'path = Path(__file__).with_name("event_markers.json")\n'
            'for marker in list(bpy.context.scene.timeline_markers):\n'
            '    if marker.name.startswith("Estimated note "):\n'
            '        bpy.context.scene.timeline_markers.remove(marker)\n'
            'for item in json.loads(path.read_text(encoding="utf-8")):\n'
            '    bpy.context.scene.timeline_markers.new(item["name"], frame=item["frame"])\n', encoding='utf-8')
        write_report(args.output/'report.html', report, rows)
        print(json.dumps(overview, indent=2))
        print('Alignment is assumed; diagnostics are not a pass/fail contact verdict.')
        print('Report:', args.output/'report.html')
        return 0
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
        print('Validation error:', error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

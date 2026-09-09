"""Run with python -m unittest discover -s tools -p test_validate_guitar_motion.py."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from validate_guitar_motion import (ROOT, load_recording, rotation, score_events,
                                   segment_closest, source_frames, world_pose)


class ValidationTests(unittest.TestCase):
    def test_segment_crossing_parallel_and_degenerate(self):
        for points, distance in [
            ([[0, 0, 0], [2, 0, 0], [1, -1, 0], [1, 1, 0]], 0),
            ([[0, 0, 0], [2, 0, 0], [1, 1, 0], [3, 1, 0]], 1),
            ([[0, 0, 0], [0, 0, 0], [1, 0, 0], [2, 0, 0]], 1),
            ([[0, 0, 0], [1, 0, 0], [2, 1, 0], [2, 2, 0]], 2**0.5),
        ]:
            a, b = segment_closest(*np.array(points, dtype=float))
            self.assertAlmostEqual(np.linalg.norm(a-b), distance)

    def test_quaternion_order_and_sign(self):
        q = np.array([0, 0, 2**-0.5, 2**-0.5])
        np.testing.assert_allclose(rotation(q) @ [1, 0, 0], [0, 1, 0], atol=1e-12)
        np.testing.assert_allclose(rotation(q), rotation(-q))

    def test_canon_timing_and_tied_tail(self):
        events = score_events(ROOT/'assets/notes/canon_in_d_major1.json', 60, 5, 0)
        self.assertEqual(len(events), 170)
        self.assertEqual(events[0]['end_frame_exclusive']-events[0]['start_frame'], 18)
        self.assertEqual(events[1]['end_frame_exclusive']-events[1]['start_frame'], 9)
        self.assertEqual(events[-1]['pluck_strings'], [])
        self.assertEqual(events[-1]['frets'][2], 7)

    def test_fixed_reference_matches_saved_blender_validation(self):
        _, ids, _, p, q = load_recording(ROOT/'recordings/left_hand_motion.json')
        specs = source_frames()
        validation = json.loads((ROOT/'blender/source_validation/validation.json').read_text())
        for sample in validation['contact_samples']:
            i = int(np.where(ids == sample['frame'])[0][0])
            gp, gr = world_pose('guitar', i, p, q, specs)
            for name, expected in sample['guitar_local_points_m'].items():
                actual = gr.T @ (world_pose(name, i, p, q, specs)[0]-gp)
                np.testing.assert_allclose(actual, expected, atol=3e-7)

    def test_reject_bad_recordings(self):
        base = dict(fps=60, num_frames=3, links=['test'], up_axis='z', quaternion_order='xyzw',
                    frames=[dict(frame=i, time=i/60, links={'test': dict(position=[0,0,0], quaternion=[0,0,0,1])}) for i in range(3)])
        mutations = [lambda d: d['frames'][1].update(reset=True),
                     lambda d: d['frames'][1].update(time=0),
                     lambda d: d['frames'][1]['links']['test'].update(position=[float('nan'),0,0]),
                     lambda d: d['frames'][1]['links']['test'].update(quaternion=[0,0,0,0])]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'motion.json'
            for mutate in mutations:
                data = json.loads(json.dumps(base))
                mutate(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_recording(path)


if __name__ == '__main__':
    unittest.main()

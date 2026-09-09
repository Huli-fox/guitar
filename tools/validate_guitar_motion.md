# Guitar motion diagnostics

Run from the repository root:

```powershell
python tools/validate_guitar_motion.py
python -m unittest discover -s tools -p test_validate_guitar_motion.py
```

Requires NumPy (already a project dependency). No Isaac Gym, Blender, or plotting
package is needed. Defaults use `recordings/left_hand_motion.json` and
`assets/notes/canon_in_d_major1.json`. Inputs and the source .blend are not modified.

Outputs in `blender/motion_validation`:

- `motion_metrics.json`: provenance, assumptions, thresholds, all-node motion
  statistics, inspection candidates, per-note pressing coverage and crossings.
- `report.html`: standalone speed, acceleration and angular-speed curves, showing
  the maximum across all recorded nodes at each frame.
- `kinematics.csv`, `anomalies.csv`: per-node measurements and threshold exceedances.
- `pressing.csv`: highest geometrically pressed fret per string; 0 means no press.
- `crossings.csv`: subframe XY crossings, depth below the string, and X direction.
- `event_markers.json`, `import_markers.py`: estimated score onsets for Blender.
  Open the source .blend, open the generated Python file in the Text Editor, and
  run it. Only markers prefixed `Estimated note ` are replaced; save manually.

## Interpretation

The old recording contains no score clock or configuration provenance. The default
first-note frame is **assumed to be 5**, based on the default five-step grace period.
Use `--first-note-frame N` to supply an onset verified against the simulation.
Do not optimize this offset to maximize reported accuracy and then call the result
an independent validation. All per-note statistics remain conditional on alignment.

Timing mirrors the environment's shortest-note rounding and five-frame minimum,
with no pitch/tempo randomization and no note merging. For this score at 60 FPS,
1/16 notes take 9 frames and 1/8 notes take 18 frames, matching the original
tempo in this particular case. Only the first pass is reconstructed. Unmarked restarts,
loops, random track selection and original-audio synchronization cannot be verified.
Track selection is explicit via `--track` (default 0).

Left-hand pressing uses the four fingers' three joint-axis segments, fixed MJCF
fingertip offsets, finite string segments, fret boundaries and a default radius
of sqrt(0.00004) metres, following the environment's geometric pressing test.
It handles barre-like contact and reports the highest pressed fret per string.
Distances are from finger axes to the string segment within the target fret region,
not mesh-surface gaps. A matching fraction is measured over sampled frames; it is
not the paper's episode accuracy metric. Open strings require no geometric press;
unused strings (-1 in the score) do not impose a left-hand constraint.

Right-hand candidates are finite-string XY crossings below the string plane,
with linearly interpolated subframe timing. This follows the core environment
heuristic, with an additional finite-string bound. It does not measure contact
force, detect mesh penetration, or prove sound production. X direction is not
labeled upstroke/downstroke without a picking convention. The score's tied tail
keeps the left-hand target without requiring another pluck. Supported effects
are tied and hammer/pull; unsupported effects fail explicitly.

Motion thresholds (2 m/s, 100 m/s2, 1500 deg/s) are configurable inspection aids,
not biomechanical limits. No warm-up frames are silently discarded. Quaternion
sign flips are listed, while angular speed uses shortest-path rotations. Source
guitar placement falls back to the static MJCF transform if it was not recorded.
Physical collisions, true contact forces, repeatability and animation quality are
not certified by this tool.

Exit code 0 means diagnostics were generated, including when thresholds were
exceeded. Invalid input or unsupported assumptions return code 2. Legacy reset
markers are rejected because their boundary semantics are ambiguous.

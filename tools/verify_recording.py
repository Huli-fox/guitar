"""Sanity-check a recorded motion JSON (left_hand.md section 9).

Usage:
    python tools/verify_recording.py <motion.json>
"""
import json
import math
import sys


def main(path):
    with open(path) as handle:
        d = json.load(handle)

    frames = d["frames"]
    print("fps:", d["fps"], "| num_frames:", d["num_frames"], "| frames:", len(frames))
    print("links:", len(d["links"]), "| quat order:", d["quaternion_order"],
          "| up axis:", d["up_axis"])

    resets = [f["frame"] for f in frames if f.get("reset")]
    print("reset frames:", resets if resets else "NONE (continuous take)")

    print("time span: %.3f .. %.3f s" % (frames[0]["time"], frames[-1]["time"]))

    for name in ["LH:wrist", "LH:index3", "RH:wrist"]:
        pos = [f["links"][name]["position"] for f in frames]
        for ax, lbl in enumerate("xyz"):
            vals = [p[ax] for p in pos]
            print("%s %s: [%.4f, %.4f]" % (name, lbl, min(vals), max(vals)))
        jump = max(math.dist(pos[i], pos[i + 1]) for i in range(len(pos) - 1))
        print("%s max per-frame jump: %.4f m" % (name, jump))

    norms = [math.sqrt(sum(x * x for x in v["quaternion"]))
             for f in frames for v in f["links"].values()]
    print("quat norm range: [%.6f, %.6f]" % (min(norms), max(norms)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "recordings/left_hand_motion.json")

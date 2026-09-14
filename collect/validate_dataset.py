#!/usr/bin/env python3
"""Fail the run if the JSONL tape or Boulder Badge check is wrong."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED = {
    tuple(),
    ("UP",),
    ("DOWN",),
    ("LEFT",),
    ("RIGHT",),
    ("A",),
    ("B",),
    ("START",),
}
HOLDS = {8, 16, 24, 32}
IMAGE_RE = re.compile(r"^frames/(\d{8})\.png$")
FIELDS = {"image", "start", "end", "inputs"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_steps(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    steps = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            fail(f"line {i}: invalid JSON ({e})")
        if not isinstance(obj, dict):
            fail(f"line {i}: not an object")
        extra = set(obj) - FIELDS
        missing = FIELDS - set(obj)
        if extra:
            fail(f"line {i}: extra fields {sorted(extra)}")
        if missing:
            fail(f"line {i}: missing fields {sorted(missing)}")
        steps.append(obj)
    if not steps:
        fail("steps.jsonl is empty")
    return steps


def check_tape(run: Path, steps: list[dict]) -> None:
    seen_starts: set[int] = set()
    prev_end = None
    for i, s in enumerate(steps):
        start, end, inputs, image = s["start"], s["end"], s["inputs"], s["image"]
        if not isinstance(start, int) or not isinstance(end, int):
            fail(f"step {i}: start/end must be int")
        if end < start:
            fail(f"step {i}: end < start ({end} < {start})")
        hold = end - start + 1
        if hold not in HOLDS:
            fail(f"step {i}: hold {hold} not in {sorted(HOLDS)}")
        if not isinstance(inputs, list) or tuple(inputs) not in ALLOWED:
            fail(f"step {i}: inputs {inputs} not allowed")
        m = IMAGE_RE.match(image)
        if not m:
            fail(f"step {i}: image {image!r} not frames/XXXXXXXX.png")
        if int(m.group(1)) != start:
            fail(f"step {i}: filename stem {m.group(1)} != start {start}")
        png = run / image
        if not png.is_file():
            fail(f"step {i}: missing {png}")
        try:
            from PIL import Image

            with Image.open(png) as im:
                if im.format != "PNG":
                    fail(f"step {i}: {png} is not a PNG ({im.format})")
                if im.size != (160, 144):
                    fail(f"step {i}: {png} size {im.size} != (160, 144)")
        except SystemExit:
            raise
        except Exception as e:
            fail(f"step {i}: cannot read {png}: {e}")
        if start in seen_starts:
            fail(f"step {i}: duplicate start {start}")
        seen_starts.add(start)
        if i > 0 and start <= steps[i - 1]["start"]:
            fail(f"step {i}: starts not strictly increasing")
        if prev_end is not None and start != prev_end + 1:
            fail(f"step {i}: start {start} != previous.end+1 ({prev_end + 1}) — tape has a hole")
        prev_end = end


def check_badge_and_meta(run: Path, steps: list[dict], meta: dict) -> int:
    last_end = steps[-1]["end"]
    if meta.get("frame_count_end") != last_end:
        fail(f"meta.frame_count_end {meta.get('frame_count_end')} != last end {last_end}")

    rom = Path(meta["rom_path"])
    if not rom.is_file():
        fail(f"ROM missing: {rom}")
    end_state = run / "end.state"
    if not end_state.is_file():
        fail("end.state missing")

    from pyboy import PyBoy

    pyboy = PyBoy(str(rom), window="null")
    pyboy.set_emulation_speed(0)
    with end_state.open("rb") as f:
        pyboy.load_state(f)
    badge = int(pyboy.memory[0xD356])
    pyboy.stop()
    if badge & 1 == 0:
        fail(f"Boulder Badge not set (wObtainedBadges={badge:02X})")
    return badge


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", type=Path)
    args = p.parse_args(argv)
    run = args.run_dir
    if not run.is_dir():
        fail(f"not a directory: {run}")
    steps_path = run / "steps.jsonl"
    if not steps_path.is_file():
        fail("steps.jsonl missing")
    meta_path = run / "meta.json"
    if not meta_path.is_file():
        fail("meta.json missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    steps = load_steps(steps_path)
    check_tape(run, steps)
    badge = check_badge_and_meta(run, steps, meta)
    pngs = list((run / "frames").glob("*.png"))
    span = steps[-1]["end"] - steps[0]["start"] + 1
    print("PASS")
    print(f"  run dir     : {run}")
    print(f"  steps       : {len(steps)}")
    print(f"  frame span  : {steps[0]['start']}..{steps[-1]['end']} ({span} frames)")
    print(f"  badge byte  : 0x{badge:02X} (boulder={'yes' if badge & 1 else 'no'})")
    print(f"  PNG count   : {len(pngs)}")
    print(f"  result      : {meta.get('result')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

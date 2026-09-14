"""JSONL + PNG writer. Four fields only. Contiguous hold tape."""

from __future__ import annotations

import json
from pathlib import Path

ALLOWED_INPUTS = (
    [],
    ["UP"],
    ["DOWN"],
    ["LEFT"],
    ["RIGHT"],
    ["A"],
    ["B"],
    ["START"],
)
ALLOWED_SET = {tuple(x) for x in ALLOWED_INPUTS}
HOLDS = {8, 16, 24, 32}
BUTTONS = ("up", "down", "left", "right", "a", "b", "start", "select")


class Recorder:
    def __init__(self, pyboy, out_dir: Path):
        self.pyboy = pyboy
        self.out = Path(out_dir)
        self.frames = self.out / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.out / "steps.jsonl"
        if self.jsonl_path.exists():
            self.jsonl_path.unlink()
        self.steps = 0
        self.last_end: int | None = None
        self._held: list[str] = []

    def save_state(self, name: str) -> Path:
        path = self.out / name
        with path.open("wb") as f:
            self.pyboy.save_state(f)
        return path

    def load_state(self, name: str) -> None:
        path = self.out / name
        with path.open("rb") as f:
            self.pyboy.load_state(f)
        self._release_all()
        self._held = []

    def _release_all(self) -> None:
        for b in BUTTONS:
            try:
                self.pyboy.button_release(b)
            except Exception:
                pass
        self._held = []

    def _apply(self, inputs: list[str]) -> None:
        want = {b.lower() for b in inputs}
        have = set(self._held)
        for b in have - want:
            self.pyboy.button_release(b)
        for b in want - have:
            self.pyboy.button_press(b)
        self._held = list(want)

    def snapshot_png(self, start: int) -> str:
        """LCD at current frame_count, before the coming hold is applied."""
        img = self.pyboy.screen.image.convert("RGB")
        if img.size != (160, 144):
            img = img.resize((160, 144))
        rel = f"frames/{start:08d}.png"
        img.save(self.out / rel, format="PNG")
        return rel

    def commit(self, inputs: list[str], hold: int) -> dict:
        if hold not in HOLDS:
            raise AssertionError(f"hold {hold} not in {HOLDS}")
        key = tuple(inputs)
        if key not in ALLOWED_SET:
            raise AssertionError(f"inputs {inputs} not allowed")
        start = int(self.pyboy.frame_count)
        if self.last_end is not None and start != self.last_end + 1:
            # After load_state we tick 1; that can desync the tape. Callers
            # must not mix load_state with an already-open tape except retries
            # that rewrite from a milestone (handled by Player).
            pass
        rel = self.snapshot_png(start)
        rec = {
            "image": rel,
            "start": start,
            "end": start + hold - 1,
            "inputs": list(inputs),
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(", ", ": ")) + "\n")
        self._apply(inputs)
        if hold > 1:
            self.pyboy.tick(hold - 1, False, False)
        self.pyboy.tick(1, True, False)
        self.steps += 1
        self.last_end = rec["end"]
        return rec

    def close(self) -> None:
        self._release_all()

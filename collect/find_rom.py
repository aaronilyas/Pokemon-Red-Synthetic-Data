"""Locate a legal Pokemon Red/Blue ROM already in the repo. Never download."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Cartridge header title (0x134, 16 bytes), padded with 0x00 or 0x80.
RED_TITLES = {"POKEMON RED", "POKEMON BLUE"}


def _header_title(path: Path) -> str:
    data = path.read_bytes()
    if len(data) < 0x144:
        return ""
    raw = data[0x134:0x144]
    return raw.split(b"\x00")[0].split(b"\x80")[0].decode("ascii", errors="ignore").strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_rom(root: Path | None = None) -> Path:
    root = (root or REPO_ROOT).resolve()
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".gb", ".gbc"}:
            continue
        if any(part in {".git", ".venv", "runs"} for part in p.parts):
            continue
        candidates.append(p)
    if not candidates:
        raise FileNotFoundError(
            f"No .gb/.gbc ROM found under {root}. Place a legal Pokemon Red ROM in the repo."
        )

    def score(path: Path) -> tuple:
        name = path.name.lower()
        title = _header_title(path).upper()
        is_red_name = "red" in name
        is_red_title = "RED" in title
        is_pokemon = "POKEMON" in title or "pokemon" in name
        return (is_red_title, is_red_name, is_pokemon, -len(str(path)))

    candidates.sort(key=score, reverse=True)
    chosen = candidates[0]
    title = _header_title(chosen)
    title_u = title.upper()
    if title_u and not any(t in title_u for t in ("POKEMON RED", "POKEMON BLUE", "POKEMON")):
        # Still return it; ram.py will abort if USA Red/Blue addresses are dead.
        pass
    return chosen


def rom_info(path: Path) -> dict:
    return {
        "rom_path": str(path),
        "rom_title": _header_title(path),
        "rom_sha256": sha256_file(path),
        "rom_size": path.stat().st_size,
    }

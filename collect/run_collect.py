#!/usr/bin/env python3
"""Headless collector: boot -> Boulder Badge. Writes steps.jsonl + frames/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from find_rom import find_rom, rom_info
from player import Player
from ram import RAM
from recorder import Recorder


def _refuse_nonempty(out: Path) -> None:
    if not out.exists():
        return
    if any(out.iterdir()):
        raise SystemExit(f"--out must be fresh: {out} is not empty")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Collect one Pokemon Red trajectory through Brock")
    p.add_argument("--out", required=True, type=Path, help="fresh run directory")
    p.add_argument(
        "--window",
        default="null",
        choices=("null", "sdl2"),
        help="PyBoy window. Default null (headless).",
    )
    args = p.parse_args(argv)

    out: Path = args.out
    if not out.is_absolute():
        out = Path.cwd() / out
    _refuse_nonempty(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)

    rom = find_rom()
    info = rom_info(rom)
    print(f"ROM: {rom}")
    print(f"  title={info['rom_title']!r} sha256={info['rom_sha256']}")

    import importlib.metadata

    from pyboy import PyBoy

    try:
        pyboy_version = importlib.metadata.version("pyboy")
    except Exception:
        pyboy_version = "unknown"

    pyboy = PyBoy(str(rom), window=args.window)
    pyboy.set_emulation_speed(0)

    title = ""
    try:
        title = str(pyboy.cartridge_title)
    except Exception:
        title = info["rom_title"]
    print(f"  cartridge_title={title!r} pyboy={pyboy_version}")
    title_u = title.upper()
    if "POKEMON" not in title_u and "POKEMON" not in info["rom_title"].upper():
        pyboy.stop()
        raise SystemExit(
            f"Cartridge title {title!r} does not look like Pokemon Red/Blue. Refusing to guess RAM."
        )

    ram = RAM(pyboy)
    rec = Recorder(pyboy, out)
    player = Player(pyboy, rec, ram, out)

    result = player.play()
    rec.close()

    frame_end = int(pyboy.frame_count)
    last_end = rec.last_end
    meta = {
        **info,
        "rom_title": title or info["rom_title"],
        "pyboy_version": pyboy_version,
        "frame_count_end": last_end if last_end is not None else frame_end,
        "pyboy_frame_count": frame_end,
        "steps": rec.steps,
        "badges": ram.badges,
        "map": ram.map_id,
        "xy": [ram.x, ram.y],
        "party_count": ram.party_count,
        **result,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))

    # USA Red/Blue sanity: if we never left map 0 and party stayed 0 after many
    # steps, addresses are probably dead.
    if rec.steps > 400 and ram.map_id == 0 and ram.party_count == 0 and ram.y == 0:
        print(
            "RAM looks dead (map/party/coords never moved). "
            "This ROM is probably not USA Red/Blue. Stopping.",
            file=sys.stderr,
        )
        pyboy.stop()
        return 2

    pyboy.stop()
    if result.get("result") != "boulder_badge":
        print(f"Stopped at milestone {result.get('milestone')}: {result.get('why')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

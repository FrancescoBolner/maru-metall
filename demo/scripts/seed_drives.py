"""Seed the simulated client drive from the challenge materials (read-only source).

    python scripts/seed_drives.py                 # the two demo projects (already shipped in demo/drives)
    python scripts/seed_drives.py --large         # also the Akkasæter workshop package (~3 000 files, ~260 MB)
    python scripts/seed_drives.py --materials PATH

Files are copied, never moved; `materials/` is not modified.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
CLIENT = DEMO / "drives" / "client"

PROJECTS = [
    # (source folder inside materials, company, project folder name)
    ("Example 2 - TU4031 - Akkasater Lager - og vedlikeholdshall/01 - Input for pricing",
     "DS Nor AS", "30480 Akkasæter Lager - og vedlikeholdshall"),
    ("Example 4 - HP11257-03 - Pedestrian Steel Skybridge/01 - Input for pricing = 04 - Fabrication Documentation",
     "Katera Steel Oy", "Kotka CAM 2E500 - Pedestrian Steel Skybridge"),
]
LARGE = [
    ("Example 2 - TU4031 - Akkasater Lager - og vedlikeholdshall/04 - Fabrication Documentation",
     "DS Nor AS", "30480 Akkasæter - workshop package LOT10-40"),
]


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in src.rglob("*"):
        if p.is_file():
            target = dst / p.relative_to(src)
            if target.exists() and target.stat().st_size == p.stat().st_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", default=str(DEMO.parent / "materials"))
    ap.add_argument("--large", action="store_true")
    args = ap.parse_args()
    materials = Path(args.materials)
    if not materials.exists():
        raise SystemExit(f"materials folder not found: {materials}")
    for src, company, name in PROJECTS + (LARGE if args.large else []):
        s = materials / src
        if not s.exists():
            print("skip (not found):", s)
            continue
        n = copy_tree(s, CLIENT / company / name)
        print(f"{company} / {name}: {n} files copied")


if __name__ == "__main__":
    main()

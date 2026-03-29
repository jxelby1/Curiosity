#!/usr/bin/env python3
"""Slice a 6-stage tree growth sheet into individual assets.

Expected source image: frontend/public/assets/tree-growth/tree-growth-sheet.png
Outputs: frontend/public/assets/tree-growth/tree-stage-1.png ... tree-stage-6.png
"""

from __future__ import annotations

from pathlib import Path


try:
    from PIL import Image
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit('Install Pillow first: pip install pillow') from exc


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'public' / 'assets' / 'tree-growth' / 'tree-growth-sheet.png'
OUT_DIR = ROOT / 'public' / 'assets' / 'tree-growth'

# Tuned for the provided sheet proportions (1536x1024) with 6 stages laid out left-to-right.
STAGE_BOXES = [
    (210, 530, 340, 790),   # stage 1
    (372, 495, 540, 790),   # stage 2
    (544, 400, 748, 790),   # stage 3
    (710, 320, 944, 790),   # stage 4
    (900, 250, 1170, 790),  # stage 5
    (1090, 200, 1410, 790), # stage 6
]


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f'Source sheet not found: {SOURCE}')

    image = Image.open(SOURCE).convert('RGBA')

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for index, box in enumerate(STAGE_BOXES, start=1):
        crop = image.crop(box)
        output_path = OUT_DIR / f'tree-stage-{index}.png'
        crop.save(output_path)
        print(f'Wrote {output_path}')


if __name__ == '__main__':
    main()

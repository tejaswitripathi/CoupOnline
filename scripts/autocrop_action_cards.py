"""Trim fully-transparent margins from the action-card PNGs.

The source art was exported with a large transparent border, which made the
icons render small inside the action tray. Cropping to the visible alpha
bounding box lets the CSS box show the artwork at full size.
"""

from pathlib import Path

from PIL import Image

CARDS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "assets" / "raw" / "action-cards"


def autocrop(path: Path) -> None:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        print(f"skip (fully transparent): {path.name}")
        return
    if bbox == (0, 0, rgba.width, rgba.height):
        print(f"skip (already tight): {path.name}")
        return
    cropped = rgba.crop(bbox)
    cropped.save(path)
    print(f"cropped {path.name}: {rgba.size} -> {cropped.size}")


def main() -> None:
    for path in sorted(CARDS_DIR.glob("*.png")):
        autocrop(path)


if __name__ == "__main__":
    main()

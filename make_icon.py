"""One-off script: generates assets/icon.ico -- a small procedural, retro-styled
icon (a coin-and-moon glyph) for the built .exe. Not part of the app itself."""

from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2

    # deep purple rounded backdrop
    pad = size * 0.04
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size * 0.22,
                         fill=(42, 20, 74, 255), outline=(20, 8, 40, 255),
                         width=max(1, int(size * 0.03)))

    # small stars
    for x, y, r in [(0.20, 0.22, 0.02), (0.80, 0.18, 0.015), (0.18, 0.78, 0.018)]:
        rx, ry, rr = x * size, y * size, r * size
        d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=(255, 240, 200, 255))

    # lunar coin (the whole point of this app)
    r = size * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 224, 138, 255),
              outline=(180, 130, 40, 255), width=max(1, int(size * 0.02)))
    r2 = r * 0.62
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=(180, 130, 40, 255),
              width=max(1, int(size * 0.018)))

    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
images = [draw(s) for s in sizes]
images[-1].save(OUT / "icon.ico", format="ICO", sizes=[(s, s) for s in sizes])
print("wrote", OUT / "icon.ico")

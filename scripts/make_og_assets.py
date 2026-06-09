# Run with: python scripts/make_og_assets.py
"""
Generate static brand assets for the FlightStrip frontend:
  - frontend/og-image.png       (1200x630 Open Graph / Twitter card)
  - frontend/favicon.png        (32x32 favicon)
  - frontend/apple-touch-icon.png (180x180)

Pure-Python (Pillow). No external network needed. Self-hosted on Vercel CDN.
These are MARKETING/SEO assets only — they are not part of the kneeboard or PDF.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND.mkdir(parents=True, exist_ok=True)

# Aviation palette (matches the app's blue accents)
DEEP   = (15, 32, 72)     # deep navy
MID    = (16, 64, 187)    # #1040bb app blue accent
SKY    = (56, 132, 220)   # lighter sky blue
WHITE  = (255, 255, 255)
SKY_LT = (191, 219, 254)  # sky-200


def _font(bold: bool, size: int):
    name = "arialbd.ttf" if bold else "arial.ttf"
    for p in (Path("C:/Windows/Fonts") / name, Path("/usr/share/fonts/truetype/dejavu") /
              ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


# Top-down airplane silhouette (points "up"), unit coords centered on (0,0)
_PLANE = [
    (0.00, -1.00), (0.10, -0.55), (0.10, -0.30), (0.95, 0.10), (0.95, 0.28),
    (0.10, 0.05), (0.10, 0.55), (0.32, 0.80), (0.32, 0.95), (0.00, 0.78),
    (-0.32, 0.95), (-0.32, 0.80), (-0.10, 0.55), (-0.10, 0.05), (-0.95, 0.28),
    (-0.95, 0.10), (-0.10, -0.30), (-0.10, -0.55),
]


def draw_plane(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill):
    pts = [(cx + x * s, cy + y * s) for (x, y) in _PLANE]
    d.polygon(pts, fill=fill)


def _vertical_gradient(w: int, h: int, top, bottom) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    top_img = Image.new("RGB", (w, h), bottom)
    mask = Image.new("L", (w, h))
    md = mask.load()
    for y in range(h):
        v = int(255 * (y / max(1, h - 1)))
        for x in range(w):
            md[x, y] = v
    return Image.composite(top_img, base, mask)


def make_og():
    W, H = 1200, 630
    img = _vertical_gradient(W, H, DEEP, MID)
    d = ImageDraw.Draw(img)

    # subtle "horizon" band + faint flight path arc for an aviation feel
    d.rectangle([0, int(H * 0.72), W, H], fill=(11, 24, 56))
    for i, r in enumerate(range(40, 520, 60)):
        bbox = [W - 260 - r, -r, W - 260 + r, H + r]
        d.arc(bbox, start=200, end=250, fill=(56, 132, 220, 0), width=2)

    # plane mark + wordmark
    draw_plane(d, 150, 185, 70, SKY_LT)
    d.text((250, 120), "FlightStrip", font=_font(True, 110), fill=WHITE)

    d.text((84, 300), "Free Pilot Kneeboard Generator", font=_font(True, 58), fill=SKY_LT)
    d.text((84, 380),
           "Runways · lengths · frequencies for every airport along your route",
           font=_font(False, 34), fill=(214, 228, 250))
    d.text((84, 452), "Enter your route → print a glance-able kneeboard.  Free.",
           font=_font(False, 30), fill=(170, 196, 236))

    # accent underline
    d.rectangle([84, 360, 84 + 560, 366], fill=SKY)

    img.save(FRONTEND / "og-image.png", "PNG")
    print("wrote", FRONTEND / "og-image.png")


def _icon(size: int):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=size // 5, fill=MID)
    draw_plane(d, size / 2, size / 2, size * 0.30, WHITE)
    return img


def make_icons():
    _icon(32).save(FRONTEND / "favicon.png", "PNG")
    print("wrote", FRONTEND / "favicon.png")
    _icon(180).save(FRONTEND / "apple-touch-icon.png", "PNG")
    print("wrote", FRONTEND / "apple-touch-icon.png")


if __name__ == "__main__":
    make_og()
    make_icons()
    print("done")

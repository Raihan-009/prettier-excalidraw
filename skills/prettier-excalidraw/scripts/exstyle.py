"""Shared style constants for prettier-excalidraw scripts (stdlib only)."""

FONT_IDS = {"comic": 8, "nunito": 6}
FONT_NAMES = {8: "Comic Shanns", 6: "Nunito", 1: "Virgil", 2: "Helvetica", 3: "Cascadia",
              5: "Excalifont", 7: "Lilita One"}
# average glyph width as a fraction of fontSize (measured from reference diagrams)
CHAR_W = {8: 0.55, 6: 0.49}
LINE_H = 1.25
FONT_SIZES = (16, 20, 28)

STROKE = "#1e1e1e"
ARROW_COLORS = {"black": "#1e1e1e", "red": "#e03131", "green": "#2f9e44", "blue": "#1971c2"}

# component box fills
FILLS = {
    "blue": "#a5d8ff", "yellow": "#ffec99", "green": "#b2f2bb", "red": "#ffc9c9",
    "purple": "#d0bfff", "orange": "#ffd8a8", "teal": "#96f2d7", "cyan": "#99e9f2",
    "grey": "#ced4da", "lightgrey": "#e9ecef", "white": "#ffffff", "none": "transparent",
}
# large region tints (one scale lighter)
TINTS = {
    "blue": "#e7f5ff", "teal": "#e6fcf5", "yellow": "#fff9db", "orange": "#fff4e6",
    "purple": "#f3f0ff", "red": "#fff5f5", "none": "transparent", "white": "#ffffff",
}
LIGHT_FILLS = set(FILLS.values()) | set(TINTS.values()) | {"#fff", "#ffffff", "transparent"}

ARROWHEADS = {"outline": "triangle_outline", "filled": "triangle"}


def _parse_rgb(hexcolor: str):
    """Return (r, g, b) 0-255, or None if the colour cannot be parsed."""
    if not hexcolor or hexcolor == "transparent":
        return None
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:  # #RRGGBBAA — ignore alpha
        h = h[:6]
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def luminance(hexcolor: str) -> float:
    """0-255 perceived luminance (same formula as is_light)."""
    rgb = _parse_rgb(hexcolor)
    if rgb is None:
        return 255.0
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_light(hexcolor: str) -> bool:
    """True if a fill is light enough to carry #1e1e1e text."""
    return luminance(hexcolor) > 150


def _rel_channel(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hexcolor: str) -> float:
    """WCAG relative luminance in 0..1."""
    rgb = _parse_rgb(hexcolor)
    if rgb is None:
        return 1.0
    r, g, b = (_rel_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours (>= 1.0)."""
    l1, l2 = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def darken(hexcolor: str, factor: float = 0.45) -> str:
    """Scale RGB toward black, keeping the same hue."""
    rgb = _parse_rgb(hexcolor)
    if rgb is None:
        return hexcolor
    r, g, b = (max(0, min(255, int(round(c * factor)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def ensure_contrast(fg: str, bg: str, min_ratio: float = 3.0) -> str:
    """Return fg, or a darker shade of the same hue, until contrast vs bg is enough."""
    if contrast_ratio(fg, bg) >= min_ratio:
        return fg
    out = fg
    for factor in (0.55, 0.4, 0.28, 0.18, 0.1, 0.05):
        out = darken(fg, factor)
        if contrast_ratio(out, bg) >= min_ratio:
            return out
    return out


def adjust_svg_fills(svg_bytes: bytes, against_fill: str, min_ratio: float = 3.0):
    """Rewrite SVG fill colours that have low contrast against against_fill.

    Returns (new_bytes, list of "old->new" change notes). Stdlib only.
    """
    import re
    try:
        text = svg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return svg_bytes, []
    changes = []

    def repl(m):
        quote, color = m.group(1), m.group(2)
        new = ensure_contrast(color, against_fill, min_ratio)
        if new.lower() != color.lower():
            changes.append(f"{color}->{new}")
            return f"fill={quote}{new}{quote}"
        return m.group(0)

    # fill="#RRGGBB" / fill='#RRGGBB' (also 3-digit and 8-digit)
    new_text = re.sub(r'\bfill=(["\'])(#[0-9A-Fa-f]{3,8})\1', repl, text)
    return new_text.encode("utf-8"), changes


def bbox(e):
    if e["type"] in ("arrow", "line", "freedraw"):
        pts = e.get("points") or [[0, 0]]
        xs = [e["x"] + p[0] for p in pts]
        ys = [e["y"] + p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    return e["x"], e["y"], e["x"] + e["width"], e["y"] + e["height"]


def inside(a, b, tol=4):
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


def overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])

#!/usr/bin/env python3
"""Render a rough SVG preview of a .excalidraw file so layout can be checked
without opening Excalidraw. Boxes, text, images and arrows only; good enough
to spot overlaps, misplaced labels and arrow routing.

Usage:
    python3 preview.py diagram.excalidraw out.svg [--square]
    python3 preview.py diagram.excalidraw out.png --png
--square pads the canvas to a square so a quick-look thumbnail does not crop a
wide diagram. On macOS, rasterise with:
    qlmanage -t -s 2400 -o <dir> out.svg        -> <dir>/out.svg.png
--png uses Chrome when available, otherwise padded quick-look on macOS.
Standard library only; PNG output needs one of those renderers installed.
"""
import argparse, html, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
from exstyle import bbox

FONT_CSS = {8: "'Comic Shanns', 'Comic Mono', monospace", 6: "Nunito, sans-serif"}


def render_svg(src, out, square=False):
    d = json.load(open(src))
    els = [e for e in d["elements"] if not e.get("isDeleted")]
    files = d.get("files", {})
    xs0, ys0, xs1, ys1 = zip(*(bbox(e) for e in els))
    pad = 40
    minx, miny, maxx, maxy = min(xs0) - pad, min(ys0) - pad, max(xs1) + pad, max(ys1) + pad
    if square:
        w, h = maxx - minx, maxy - miny
        if w > h:
            miny -= (w - h) / 2; maxy += (w - h) / 2
        else:
            minx -= (h - w) / 2; maxx += (h - w) / 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'viewBox="{minx} {miny} {maxx-minx} {maxy-miny}" width="{maxx-minx}" height="{maxy-miny}">',
             f'<rect x="{minx}" y="{miny}" width="{maxx-minx}" height="{maxy-miny}" fill="#fff"/>']
    for e in els:
        t = e["type"]; op = e.get("opacity", 100) / 100
        sc = e.get("strokeColor", "#1e1e1e"); sw = e.get("strokeWidth", 2)
        dash = {"dotted": f'stroke-dasharray="{sw*1.5} {sw*3}"', "dashed": f'stroke-dasharray="{sw*4} {sw*3}"'}.get(e.get("strokeStyle"), "")
        if t in ("rectangle", "ellipse", "diamond"):
            fill = e.get("backgroundColor", "transparent")
            fill = "none" if fill == "transparent" else fill
            if t == "rectangle":
                parts.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["width"]}" height="{e["height"]}" fill="{fill}" stroke="{sc}" stroke-width="{sw}" opacity="{op}" {dash}/>')
            elif t == "ellipse":
                parts.append(f'<ellipse cx="{e["x"]+e["width"]/2}" cy="{e["y"]+e["height"]/2}" rx="{e["width"]/2}" ry="{e["height"]/2}" fill="{fill}" stroke="{sc}" stroke-width="{sw}" opacity="{op}"/>')
            else:
                x, y, w, h = e["x"], e["y"], e["width"], e["height"]
                parts.append(f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" fill="{fill}" stroke="{sc}" stroke-width="{sw}" opacity="{op}"/>')
        elif t == "text":
            fs = e.get("fontSize", 20); ff = FONT_CSS.get(e.get("fontFamily"), "monospace")
            lines = e["text"].split("\n"); lh = fs * e.get("lineHeight", 1.25)
            anchor = {"center": "middle", "right": "end"}.get(e.get("textAlign"), "start")
            ax = {"middle": e["x"] + e["width"] / 2, "end": e["x"] + e["width"]}.get(anchor, e["x"])
            longest = max(len(l) for l in lines) or 1
            for i, line in enumerate(lines):
                # force each line to the width Excalidraw stored, so the preview shows the real layout
                tl = e["width"] * len(line) / longest
                parts.append(f'<text xml:space="preserve" x="{ax}" y="{e["y"] + lh*i + fs*0.95}" font-size="{fs}" font-family="{ff}" fill="{sc}" text-anchor="{anchor}" opacity="{op}" textLength="{tl:.1f}" lengthAdjust="spacingAndGlyphs">{html.escape(line)}</text>')
        elif t == "image":
            f = files.get(e.get("fileId"))
            if f:
                parts.append(f'<image x="{e["x"]}" y="{e["y"]}" width="{e["width"]}" height="{e["height"]}" xlink:href="{f["dataURL"]}" preserveAspectRatio="none"/>')
            else:
                parts.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["width"]}" height="{e["height"]}" fill="#eee" stroke="#999"/>')
        elif t in ("arrow", "line", "freedraw"):
            pts = [(e["x"] + p[0], e["y"] + p[1]) for p in e.get("points", [])]
            if len(pts) < 2: continue
            fill = e.get("backgroundColor", "transparent") if t == "line" and len(pts) > 2 else "none"
            fill = "none" if fill == "transparent" else fill
            parts.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" fill="{fill}" stroke="{sc}" stroke-width="{sw}" opacity="{op}" stroke-linejoin="round" {dash}/>')
            for key, idx, prev in (("endArrowhead", -1, -2), ("startArrowhead", 0, 1)):
                head = e.get(key)
                if head and t == "arrow":
                    (x1, y1), (x0, y0) = pts[idx], pts[prev]
                    import math
                    ang = math.atan2(y1 - y0, x1 - x0); L = 14 if sw <= 2 else 20
                    a1 = (x1 - L*math.cos(ang - 0.4), y1 - L*math.sin(ang - 0.4))
                    a2 = (x1 - L*math.cos(ang + 0.4), y1 - L*math.sin(ang + 0.4))
                    hf = "#fff" if "outline" in head else sc
                    if head in ("arrow",):
                        parts.append(f'<polyline points="{a1[0]},{a1[1]} {x1},{y1} {a2[0]},{a2[1]}" fill="none" stroke="{sc}" stroke-width="{sw}"/>')
                    else:
                        parts.append(f'<polygon points="{a1[0]},{a1[1]} {x1},{y1} {a2[0]},{a2[1]}" fill="{hf}" stroke="{sc}" stroke-width="{sw}"/>')
    parts.append("</svg>")
    open(out, "w").write("\n".join(parts))
    return maxx - minx, maxy - miny


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        executable = shutil.which(name)
        if executable:
            return executable
    mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return str(mac_chrome) if mac_chrome.is_file() else None


def render_png(src, out, square=False):
    chrome = find_chrome()
    quicklook = shutil.which("qlmanage") if sys.platform == "darwin" else None
    if not chrome and not quicklook:
        raise RuntimeError("PNG preview needs Chrome/Chromium, or Quick Look on macOS")
    with tempfile.TemporaryDirectory() as td:
        svg = Path(td) / "preview.svg"
        width, height = render_svg(src, svg, square=square or not chrome)
        png = Path(td) / "preview.png"
        if chrome:
            command = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                       "--force-device-scale-factor=2", f"--user-data-dir={td}/chrome-profile",
                       f"--screenshot={png}", f"--window-size={math.ceil(width)},{math.ceil(height)}",
                       svg.as_uri()]
        else:
            command = [quicklook, "-t", "-s", "2400", "-o", td, str(svg)]
            png = Path(td) / "preview.svg.png"
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        if not png.is_file() or not png.stat().st_size:
            raise RuntimeError("Renderer did not produce a PNG preview")
        shutil.copyfile(png, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", help="input .excalidraw file")
    parser.add_argument("out", help="output SVG, or PNG with --png")
    parser.add_argument("--square", action="store_true", help="pad the canvas to a square")
    parser.add_argument("--png", action="store_true", help="render PNG using Chrome or macOS Quick Look")
    args = parser.parse_args()
    try:
        if args.png:
            render_png(args.src, args.out, square=args.square)
        else:
            render_svg(args.src, args.out, square=args.square)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"preview: {exc}\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

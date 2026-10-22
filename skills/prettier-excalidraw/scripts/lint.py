#!/usr/bin/env python3
"""Check a .excalidraw file against the prettier-excalidraw style guide.

Usage:
    python3 lint.py diagram.excalidraw [--font comic|nunito] [--arrowhead outline|filled]
                                       [--json] [--allow-manual] [--style style.json]

Exit code 0 = clean, 1 = violations found. With --allow-manual, findings that need a
human (marked "(manual)") are still printed but do not affect the exit code, which is
what a CI gate on hand-drawn reference diagrams wants. Each finding names the element id so
it can be located in the JSON. Library icons (groups of >= 3 hand-drawn parts
without text) are exempt from the roughness rule, because the Excalidraw
library ships them sketchy on purpose and they still read fine.
Standard library only.
"""
import json, sys
from collections import Counter
from exstyle import (ARROWHEADS, FONT_IDS, FONT_NAMES, FONT_SIZES, ICON_MIN_CONTRAST, STYLE, area, bbox, contrast,
                     inside, is_light, overlap, style_from_argv)


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d, [e for e in d["elements"] if not e.get("isDeleted")]


def icon_groups(els):
    """group ids that look like library icons: >=3 members, none of them text."""
    members = {}
    for e in els:
        for g in e.get("groupIds", []):
            members.setdefault(g, []).append(e)
    return {g for g, ms in members.items() if len(ms) >= 3 and not any(m["type"] == "text" for m in ms)}


def lint(path, font=None, arrowhead=None):
    d, els = load(path)
    want_font = STYLE["font"] if font is None else (font if isinstance(font, int) else FONT_IDS[font])
    want_head = STYLE["arrowhead"] if arrowhead is None else ARROWHEADS.get(arrowhead, arrowhead)
    want_rough = STYLE["roughness"]
    icons = icon_groups(els)
    idx = {e["id"]: i for i, e in enumerate(els)}
    byid = {e["id"]: e for e in els}
    out = []

    def add(rule, e, msg, fixable=True):
        out.append({"rule": rule, "id": e["id"], "type": e["type"], "message": msg, "fixable": fixable})

    # Component boxes only: diamonds / ellipses are flowchart markers, so proximity and
    # box-overlap (built from filled_rects) deliberately ignore them.
    filled_rects = [e for e in els if e["type"] == "rectangle"
                    and e.get("backgroundColor") not in (None, "transparent")]
    # elements that some bound arrow starts from: a headless arrow ending on one of these
    # is the first half of a split branch (diamond -> "yes" circle -> target), not a mistake
    arrow_sources = {e["startBinding"]["elementId"] for e in els
                     if e["type"] == "arrow" and e.get("startBinding")}

    for e in els:
        t = e["type"]
        in_icon = any(g in icons for g in e.get("groupIds", []))
        if t in ("rectangle", "ellipse", "diamond", "arrow", "line", "text") and not in_icon:
            if e.get("roughness", 0) != want_rough:
                add("roughness", e, f"roughness={e['roughness']} (want {want_rough})")
        if t in ("rectangle", "ellipse", "diamond"):
            if e.get("fillStyle") not in (None, STYLE["fill_style"]):
                add("fill-style", e, f"fillStyle={e['fillStyle']} (want {STYLE['fill_style']})")
            if t == "rectangle" and STYLE["roundness"] is None and e.get("roundness") is not None and not in_icon:
                add("rounded-corners", e, "rectangle has rounded corners (want sharp)")
            has_text = any(b.get("type") == "text" for b in e.get("boundElements") or [])
            if has_text and not is_light(e.get("backgroundColor")):
                add("dark-fill-text", e, f"dark fill {e['backgroundColor']} behind text", fixable=False)
            if e.get("strokeStyle") not in (None, "solid", "dotted", "dashed"):
                add("stroke-style", e, f"strokeStyle={e['strokeStyle']}")
        if t == "text":
            if e.get("fontFamily") != want_font:
                add("font", e, f"fontFamily={FONT_NAMES.get(e.get('fontFamily'), e.get('fontFamily'))} "
                               f"(want {FONT_NAMES[want_font]})")
            fs = e.get("fontSize", 20)
            if round(fs) not in FONT_SIZES or abs(fs - round(fs)) > 0.01:
                add("font-size", e, f"fontSize={fs:.2f} (want one of {FONT_SIZES})")
        if t == "arrow":
            head = e.get("endArrowhead")
            if head is None and e.get("startArrowhead") is None and not in_icon:
                ends_on = (e.get("endBinding") or {}).get("elementId")
                if ends_on not in arrow_sources:
                    add("no-arrowhead", e, "arrow has no arrowhead (is it a connector?)", fixable=False)
            elif head is not None and head != want_head:
                add("arrowhead", e, f"endArrowhead={head} (want {want_head})")
            if e.get("startArrowhead") not in (None, want_head):
                add("arrowhead", e, f"startArrowhead={e['startArrowhead']} (want {want_head} or none)")
            if head is not None:
                ab = bbox(e)
                for r in filled_rects:
                    if idx[r["id"]] > idx[e["id"]] and overlap(ab, bbox(r)) and area(bbox(r)) > 2000:
                        add("arrow-hidden", e, f"arrow drawn before filled box {r['id']} it crosses")
                        break
                for key in ("startBinding", "endBinding"):
                    if not e.get(key):
                        # endpoint inside some box but not bound -> will not follow the box
                        px = e["x"] + (e["points"][0][0] if key == "startBinding" else e["points"][-1][0])
                        py = e["y"] + (e["points"][0][1] if key == "startBinding" else e["points"][-1][1])
                        for r in filled_rects:
                            b = bbox(r)
                            if b[0] - 8 <= px <= b[2] + 8 and b[1] - 8 <= py <= b[3] + 8 and area(b) < 60000:
                                add("unbound-arrow", e, f"{key[:-7]} touches box {r['id']} but is not bound", fixable=False)
                                break
        if t == "image":
            # proportional to a containing labelled box?
            ib = bbox(e)
            conts = [r for r in els if r["type"] == "rectangle" and inside(ib, bbox(r))
                     and area(bbox(r)) > area(ib) * 1.2 and area(bbox(r)) < 60000]
            if conts:
                r = min(conts, key=lambda r: area(bbox(r)))
                ratio = e["height"] / r["height"]
                if not 0.55 <= ratio <= 1.0:
                    add("icon-size", e, f"icon is {ratio:.0%} of box {r['id']} height (want 65-95%)", fixable=False)
            if e.get("scale") not in (None, [1, 1]):
                add("icon-stretched", e, f"image scale={e['scale']}", fixable=False)
            f = d.get("files", {}).get(e.get("fileId"), {})
            if conts and f.get("mimeType") == "image/svg+xml":
                import base64, re
                try:
                    svg = base64.b64decode(f["dataURL"].split(",", 1)[1]).decode("utf-8", "ignore")
                    m = re.search(r'<svg\b[^>]*?\sfill=["\'](#[0-9a-fA-F]{3,6})["\']', svg)
                    bg = r.get("backgroundColor")
                    if m and bg and bg != "transparent" and contrast(m.group(1), bg) < ICON_MIN_CONTRAST:
                        add("icon-low-contrast", e, f"icon colour {m.group(1)} on box fill {bg} has contrast "
                            f"{contrast(m.group(1), bg):.1f} (want >= {ICON_MIN_CONTRAST:.0f}); rebuild or set icon_color",
                            fixable=False)
                except Exception:
                    pass

    # misleading proximity: a data store / cache / queue (red fill in this style) sitting
    # directly under a non-store box it is not connected to. Readers assume the box
    # above owns the store before they read any arrow. Peers stacked in a column
    # (two services, two stores) are fine, so the rule is deliberately narrow.
    STORE_FILLS = set(STYLE["store_fills"])
    byid_box = {e["id"]: e for e in els if e["type"] == "rectangle"
                and any(b.get("type") == "text" for b in e.get("boundElements") or [])}
    links = {}
    for e in els:
        if e["type"] == "arrow" and e.get("startBinding") and e.get("endBinding"):
            a, b = e["startBinding"]["elementId"], e["endBinding"]["elementId"]
            links.setdefault(a, set()).add(b); links.setdefault(b, set()).add(a)
    for b in byid_box.values():
        if b.get("backgroundColor") not in STORE_FILLS or not links.get(b["id"]): continue
        bb = bbox(b)
        above = [a for a in byid_box.values() if a is not b and area(bbox(a)) < 60000
                 and a.get("backgroundColor") not in STORE_FILLS
                 and abs(a["y"] + a["height"] - b["y"]) < 200 and a["y"] + a["height"] <= b["y"] + 1
                 and min(bbox(a)[2], bb[2]) - max(bbox(a)[0], bb[0]) > 0.5 * b["width"]]
        if above:
            a = min(above, key=lambda a: b["y"] - (a["y"] + a["height"]))
            if a["id"] not in links[b["id"]]:
                label = lambda r: next((t["text"] for t in els if t.get("containerId") == r["id"]), r["id"]).split("\n")[0]
                add("misleading-proximity", b, f"'{label(b)}' sits right under '{label(a)}' but is not connected to it; "
                    f"move the store under the box that uses it", fixable=False)

    # arrow crossing text: a connector segment running through a free text element
    # (region titles, captions) makes both unreadable
    free_text = [t for t in els if t["type"] == "text" and not t.get("containerId")]
    for e in els:
        if e["type"] != "arrow" or not e.get("endArrowhead"): continue
        pts = [(e["x"] + p[0], e["y"] + p[1]) for p in e.get("points", [])]
        for a, b in zip(pts, pts[1:]):
            seg = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            for t in free_text:
                tb = bbox(t)
                inner = (tb[0] + 1, tb[1] + 1, tb[2] - 1, tb[3] - 1)
                if overlap(seg, inner) and not (seg[2] - seg[0] < 1 and seg[3] - seg[1] < 1):
                    add("arrow-through-text", e, f"arrow runs through text '{t['text'][:30]}' ({t['id']}); "
                        f"offset the arrow or move the text", fixable=False)
                    break
            else:
                continue
            break

    # arrow through an unrelated box: a connector segment crossing a small filled box it is
    # not bound to. Crossing a big region is normal; crossing a component box is not.
    small_boxes = [r for r in filled_rects if area(bbox(r)) < 60000]
    connectors = [e for e in els if e["type"] == "arrow" and e.get("endArrowhead")]
    seg_list = []   # (arrow, (x0,y0,x1,y1)) for every segment, reused below
    for e in connectors:
        pts = [(e["x"] + p[0], e["y"] + p[1]) for p in e.get("points", [])]
        bound = {b.get("elementId") for b in (e.get("startBinding"), e.get("endBinding")) if b}
        for a, b in zip(pts, pts[1:]):
            seg = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            seg_list.append((e, seg))
            ends = [(pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1])]
            hit = next((r for r in small_boxes if r["id"] not in bound
                        and overlap(seg, (bbox(r)[0] + 3, bbox(r)[1] + 3, bbox(r)[2] - 3, bbox(r)[3] - 3))
                        # an arrow may cross a box that contains its own endpoint (target nested inside it)
                        and not any(bbox(r)[0] - 8 <= px <= bbox(r)[2] + 8 and bbox(r)[1] - 8 <= py <= bbox(r)[3] + 8
                                    for px, py in ends)), None)
            if hit:
                add("arrow-through-box", e, f"arrow runs through box {hit['id']} it is not connected to; "
                    f"route around it (from_side / to_side / bend)", fixable=False)
                break

    # two connectors sharing a line: collinear segments that overlap for more than 20 px
    seen = set()
    for i, (e1, s1) in enumerate(seg_list):
        for e2, s2 in seg_list[i + 1:]:
            if e1 is e2 or (e1["id"], e2["id"]) in seen: continue
            h1, h2 = s1[3] - s1[1] < 1, s2[3] - s2[1] < 1
            v1, v2 = s1[2] - s1[0] < 1, s2[2] - s2[0] < 1
            if h1 and h2 and abs(s1[1] - s2[1]) < 3 and min(s1[2], s2[2]) - max(s1[0], s2[0]) > 20 \
               or v1 and v2 and abs(s1[0] - s2[0]) < 3 and min(s1[3], s2[3]) - max(s1[1], s2[1]) > 20:
                seen.add((e1["id"], e2["id"]))
                add("arrow-overlap", e1, f"shares a line with arrow {e2['id']}; give one of them a different "
                    f"bend or offset", fixable=False)

    # overlapping text: two text elements whose boxes intersect
    texts = [t for t in els if t["type"] == "text"]
    for i, t1 in enumerate(texts):
        b1 = bbox(t1)
        for t2 in texts[i + 1:]:
            b2 = bbox(t2)
            if overlap((b1[0] + 2, b1[1] + 2, b1[2] - 2, b1[3] - 2), (b2[0] + 2, b2[1] + 2, b2[2] - 2, b2[3] - 2)):
                add("text-overlap", t1, f"'{t1['text'][:25]}' overlaps '{t2['text'][:25]}' ({t2['id']})", fixable=False)

    # free text lying over a component box it does not belong to (a label that drifted), or
    # drawn BEFORE a filled box it overlaps (hidden under the fill; fix.py moves it up)
    for t in free_text:
        tb = bbox(t); inner = (tb[0] + 2, tb[1] + 2, tb[2] - 2, tb[3] - 2)
        behind = next((r for r in filled_rects if idx[r["id"]] > idx[t["id"]] and overlap(inner, bbox(r))), None)
        if behind:
            add("text-behind-box", t, f"'{t['text'][:25]}' is drawn before filled box {behind['id']} and hidden under it")
            continue
        hit = next((r for r in small_boxes if overlap(inner, bbox(r))), None)
        if hit:
            add("text-over-box", t, f"'{t['text'][:25]}' lies over box {hit['id']}; move the text or the arrow it labels", fixable=False)

    # two component boxes overlapping (nesting, i.e. one fully inside the other, is fine)
    for i, a in enumerate(small_boxes):
        ab = bbox(a)
        for b in small_boxes[i + 1:]:
            bb = bbox(b)
            if overlap((ab[0] + 1, ab[1] + 1, ab[2] - 1, ab[3] - 1), bb) and not inside(ab, bb) and not inside(bb, ab):
                add("box-overlap", a, f"overlaps box {b['id']}; move one of them", fixable=False)

    # z-order: child rectangle before parent
    for c in filled_rects:
        cb = bbox(c)
        for p in filled_rects:
            if p is c: continue
            pb = bbox(p)
            if inside(cb, pb) and area(pb) > area(cb) * 1.1 and idx[p["id"]] > idx[c["id"]]:
                add("child-before-parent", c, f"drawn before its container {p['id']}")
                break
    return out


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if args else 2)
    style_from_argv(args)
    font = args[args.index("--font") + 1] if "--font" in args else None
    head = args[args.index("--arrowhead") + 1] if "--arrowhead" in args else None
    as_json = "--json" in args
    allow_manual = "--allow-manual" in args
    path = args[0]
    findings = lint(path, font, head)
    blocking = [f for f in findings if f["fixable"]] if allow_manual else findings
    if as_json:
        print(json.dumps(findings, indent=1))
    else:
        if not findings:
            print(f"{path}: clean"); sys.exit(0)
        counts = Counter(f["rule"] for f in findings)
        print(f"{path}: {len(findings)} findings  " + ", ".join(f"{k}×{v}" for k, v in counts.most_common()))
        for f in findings:
            print(f"  [{f['rule']}] {f['type']} {f['id']}: {f['message']}" + ("" if f["fixable"] else "  (manual)"))
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()

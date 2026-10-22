#!/usr/bin/env python3
"""Build a .excalidraw file from a small JSON spec, in the prettier-excalidraw style.

Usage:
    python3 build.py spec.json out.excalidraw [--png] [--svg] [--style style.json]

--png / --svg also write out.png / out.svg next to the diagram (see export.py).

The spec describes WHAT is in the diagram (regions, boxes, icons, arrows) and
WHERE; this script takes care of every stylistic property (font, roughness,
arrowheads, bindings, bound text, z-order, image embedding) so the result opens
cleanly in Excalidraw and already conforms to the style guide.

Spec format: see references/spec-format.md (also summarised in SKILL.md).
Standard library only.
"""
import base64, hashlib, json, math, os, random, struct, sys, time
from exstyle import (ARROW_COLORS, ARROWHEADS, CHAR_W, FILLS, FONT_IDS, ICON_MIN_CONTRAST, LINE_H, STYLE, TINTS,
                     area, contrast, darken_to_contrast, load_style, style_from_argv)
from exstyle import size as default_size

_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _id(n=21):
    return "".join(random.choice(_ALPHABET) for _ in range(n))


def _seed():
    return random.randint(1, 2 ** 31 - 1)


_now = int(time.time() * 1000)


def _base(etype, x, y, w, h, **kw):
    e = {
        "id": kw.pop("id", None) or _id(), "type": etype, "x": float(x), "y": float(y),
        "width": float(w), "height": float(h), "angle": 0,
        "strokeColor": STYLE["stroke"], "backgroundColor": "transparent", "fillStyle": STYLE["fill_style"],
        "strokeWidth": STYLE["stroke_width"], "strokeStyle": "solid", "roughness": STYLE["roughness"], "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None, "seed": _seed(), "version": 1,
        "versionNonce": _seed(), "isDeleted": False, "boundElements": [], "updated": _now,
        "link": None, "locked": False,
    }
    e.update(kw)
    return e


def text_size(text, font_id, font_size):
    lines = text.split("\n")
    w = max(len(l) for l in lines) * CHAR_W.get(font_id, 0.55) * font_size
    h = len(lines) * font_size * LINE_H
    return w, h


class Builder:
    def __init__(self, spec, base_dir="."):
        self.spec = spec
        self.base_dir = base_dir
        if spec.get("style"):
            load_style(spec["style"] if os.path.isabs(spec["style"]) else os.path.join(base_dir, spec["style"]))
        f = spec.get("font", STYLE["font"])
        self.font = f if isinstance(f, int) else FONT_IDS.get(f, STYLE["font"])
        h = spec.get("arrowhead", STYLE["arrowhead"])
        self.head = ARROWHEADS.get(h, h)      # a name like "outline", or a raw Excalidraw value
        self.files = {}
        self.layers = {"region": [], "box": [], "image": [], "divider": [], "text": [], "arrow": []}
        self.by_id = {}          # spec id -> excalidraw element (the box/region/image/divider)
        self.attached_icons = {}  # element id -> icon images, for groups
        self.warnings = []
        self.darkened = []       # icons recoloured for contrast, summarised once at the end
        self.icon_dirs = icon_dirs(spec, base_dir)

    # ---------- public ----------
    def build(self):
        # groups reference ids of elements defined anywhere in the spec, so they are
        # applied after everything else exists.
        for item in self.spec["elements"]:
            if item["type"] != "group":
                getattr(self, "add_" + item["type"])(item)
        for item in self.spec["elements"]:
            if item["type"] == "group":
                self.add_group(item)
        return self.to_json()

    # ---------- element builders ----------
    def add_region(self, it):
        fill = TINTS.get(it.get("tint", "none"), it.get("tint", "transparent"))
        e = _base("rectangle", it["x"], it["y"], it["w"], it["h"], id=it.get("id"),
                  backgroundColor=fill, strokeWidth=it.get("stroke_width", STYLE["stroke_width"]),
                  roundness=STYLE["roundness"])
        if it.get("dotted"):
            e["strokeStyle"] = "dotted"; e["opacity"] = 60; e["strokeWidth"] = 1
        self._register(it, e, "region")
        if it.get("title"):
            size = it.get("size", default_size("default"))
            tw, th = text_size(it["title"], self.font, size)
            pos = it.get("title_pos", "top-left")
            pad = 16
            if pos == "top-right":
                tx = it["x"] + it["w"] - tw - pad
            elif pos == "top-center":
                tx = it["x"] + (it["w"] - tw) / 2
            elif pos == "bottom-center":
                tx = it["x"] + (it["w"] - tw) / 2
            else:
                tx = it["x"] + pad
            ty = it["y"] + it["h"] + 8 if pos == "bottom-center" else it["y"] + pad
            self._free_text(it["title"], tx, ty, size, "center" if "center" in pos else "left")
        if it.get("icon"):
            # provider logo in the corner opposite the title ("hosted on X" boundaries)
            ih = it.get("icon_h", 32)
            pad = 16
            left = it.get("title_pos", "top-left") == "top-right"
            ix = it["x"] + pad if left else it["x"] + it["w"] - ih - pad
            icon = self._image(self._resolve_icon(dict(it, label=it.get("title", ""))), ix, it["y"] + pad - 4, None, ih,
                               on_fill=fill if fill != "transparent" else "#ffffff", icon_color=it.get("icon_color"))
            self.attached_icons.setdefault(e["id"], []).append(icon)
        if it.get("subtitle"):
            # secondary note in the opposite top corner from the title, size 16
            size = it.get("subtitle_size", default_size("small"))
            tw, th = text_size(it["subtitle"], self.font, size)
            pad = 16
            right = it.get("title_pos", "top-left") != "top-right"
            tx = it["x"] + it["w"] - tw - pad if right else it["x"] + pad
            self._free_text(it["subtitle"], tx, it["y"] + pad + 2, size, "left")

    def _resolve_icon(self, it):
        """Turn `icon` into a file path. A value with an extension or a slash is a path;
        "auto" looks up the first label line in the icon folders; any other word is
        looked up by name. Unresolved "auto" is silently skipped, a named icon that is
        not found stops the build."""
        ref = it.get("icon")
        if not ref:
            return None
        if "/" in ref or os.sep in ref or ref.lower().endswith(ICON_EXTS):
            return ref
        name = it.get("label", "").split("\n")[0] if ref == "auto" else ref
        path = find_icon(name, self.icon_dirs)
        if path is None:
            if ref == "auto":
                self.warnings.append(f"box {it.get('id')}: no icon for '{name}' in {self.icon_dirs or 'no icon folders'}")
                return None
            raise SystemExit(f"icon '{ref}' not found in icon folders {self.icon_dirs or '(none configured)'}; "
                             f"set icons_dir in the spec or PRETTIER_EXCALIDRAW_ICONS, or give a file path")
        return path

    def add_box(self, it):
        it = dict(it, icon=self._resolve_icon(it))
        fill = FILLS.get(it.get("fill", "blue"), it.get("fill", "#a5d8ff"))
        size = it.get("size", default_size("default"))
        w, h = it.get("w", 240), it.get("h", 70)
        tw, th = text_size(it.get("label", ""), self.font, size)
        if th + 16 > h:
            new_h = int(math.ceil((th + 16) / 20.0) * 20)   # stay on the 20 px grid
            self.warnings.append(f"box {it.get('id')}: heightened {h} -> {new_h} to fit label")
            h = new_h
        icon_h = 0
        if it.get("icon"):
            # Excalidraw centres bound text in the whole box, so the icon strip on the left needs
            # the same clearance on the right. Shrink the icon down to 55% of the box height
            # first (the smallest ratio seen in the reference diagrams), then widen the box.
            icon_h = it.get("icon_h", round(h * 0.8))
            fit = (w - tw) / 2 - 20
            if fit < icon_h:
                icon_h = max(math.ceil(h * 0.56), min(icon_h, round(fit)))
                if icon_h < 0.65 * h:
                    self.warnings.append(f"box {it.get('id')}: icon shrunk to {icon_h / h:.0%} of box height "
                                         f"to clear the label; widen the box or shorten the label")
        strip = (icon_h + 20) if icon_h else 16
        need_w = tw + 2 * strip
        if need_w > w + 4:          # a few px short is fine; avoid growing a 40 px cell to 60 for one letter
            new_w = int(math.ceil(need_w / 20.0) * 20)   # stay on the 20 px grid
            self.warnings.append(f"box {it.get('id')}: widened {w} -> {new_w} to fit label"
                                 + (" beside icon" if icon_h else ""))
            w = new_w
        e = _base("rectangle", it["x"], it["y"], w, h, id=it.get("id"), backgroundColor=fill,
                  strokeWidth=it.get("stroke_width", STYLE["stroke_width"]), roundness=STYLE["roundness"])
        if it.get("dashed"):
            e["strokeStyle"] = "dashed"
        self._register(it, e, "box")
        if it.get("label"):
            t = _base("text", it["x"] + (w - tw) / 2, it["y"] + (h - th) / 2, tw, th,
                      text=it["label"], originalText=it["label"], fontSize=size, fontFamily=self.font,
                      textAlign="center", verticalAlign="middle", containerId=e["id"], autoResize=True,
                      lineHeight=LINE_H, backgroundColor=fill)
            e["boundElements"].append({"type": "text", "id": t["id"]})
            self.layers["text"].append(t)
        if icon_h:
            icon = self._image(it["icon"], it["x"] + 12, it["y"] + (h - icon_h) / 2, None, icon_h, group=e,
                               on_fill=fill if fill != "transparent" else "#ffffff", icon_color=it.get("icon_color"))
            self.attached_icons.setdefault(e["id"], []).append(icon)

    def add_diamond(self, it):
        self._add_shape(it, "diamond", default_w=200, default_h=100, default_size_name="default")

    def add_ellipse(self, it):
        # small markers (80×40) need size 16 so a one-line label fits without growing
        self._add_shape(it, "ellipse", default_w=80, default_h=40, default_size_name="small")

    def _add_shape(self, it, etype, default_w, default_h, default_size_name="default"):
        """Diamond / ellipse: bound centred label, same layer and bindings as a box."""
        fill = FILLS.get(it.get("fill", "none"), it.get("fill", "transparent"))
        size = it.get("size", default_size(default_size_name))
        w, h = it.get("w", default_w), it.get("h", default_h)
        tw, th = text_size(it.get("label", ""), self.font, size)
        if it.get("label") and th + 16 > h:
            new_h = int(math.ceil((th + 16) / 20.0) * 20)
            self.warnings.append(f"{etype} {it.get('id')}: heightened {h} -> {new_h} to fit label")
            h = new_h
        if it.get("label") and tw + 16 > w:
            new_w = int(math.ceil((tw + 16) / 20.0) * 20)
            self.warnings.append(f"{etype} {it.get('id')}: widened {w} -> {new_w} to fit label")
            w = new_w
        e = _base(etype, it["x"], it["y"], w, h, id=it.get("id"), backgroundColor=fill,
                  strokeWidth=it.get("stroke_width", STYLE["stroke_width"]), roundness=STYLE["roundness"])
        if it.get("dashed"):
            e["strokeStyle"] = "dashed"
        self._register(it, e, "box")
        if it.get("label"):
            t = _base("text", it["x"] + (w - tw) / 2, it["y"] + (h - th) / 2, tw, th,
                      text=it["label"], originalText=it["label"], fontSize=size, fontFamily=self.font,
                      textAlign="center", verticalAlign="middle", containerId=e["id"], autoResize=True,
                      lineHeight=LINE_H, backgroundColor=fill)
            e["boundElements"].append({"type": "text", "id": t["id"]})
            self.layers["text"].append(t)

    def add_image(self, it):
        src = it.get("src") or self._resolve_icon(dict(it, label=it.get("label", "")))
        if not src:
            raise SystemExit(f"image {it.get('id')}: give `src` or a resolvable `icon`")
        e = self._image(src, it["x"], it["y"], it.get("w"), it.get("h", 120), spec_id=it.get("id"),
                        icon_color=it.get("icon_color"))
        if it.get("label"):
            size = it.get("size", default_size("default"))
            tw, th = text_size(it["label"], self.font, size)
            self._free_text(it["label"], e["x"] + (e["width"] - tw) / 2, e["y"] + e["height"] + 8, size, "center")
        self._register(it, e, None)

    def add_text(self, it):
        size = it.get("size", default_size("default"))
        color = ARROW_COLORS.get(it.get("color", "black"), it.get("color", STYLE["stroke"]))
        self._free_text(it["text"], it["x"], it["y"], size, it.get("align", "left"), color=color)

    def add_note(self, it):
        """Caption / caveat / legend: lightgrey box, stroke 1, left-aligned small text, pad 12."""
        text = it["text"]
        size = it.get("size", default_size("small"))
        pad = 12
        tw, th = text_size(text, self.font, size)
        w = it.get("w", tw + 2 * pad)
        h = it.get("h", th + 2 * pad)
        fill = FILLS["lightgrey"]
        e = _base("rectangle", it["x"], it["y"], w, h, id=it.get("id"), backgroundColor=fill,
                  strokeWidth=it.get("stroke_width", 1), roundness=STYLE["roundness"])
        self._register(it, e, "box")
        t = _base("text", it["x"] + pad, it["y"] + pad, tw, th,
                  text=text, originalText=text, fontSize=size, fontFamily=self.font,
                  textAlign="left", verticalAlign="top", containerId=e["id"], autoResize=True,
                  lineHeight=LINE_H, backgroundColor=fill)
        e["boundElements"].append({"type": "text", "id": t["id"]})
        self.layers["text"].append(t)

    def add_divider(self, it):
        # a light boundary line, not a connector: 1 px, no arrowheads, optional small label
        horizontal = it.get("orientation", "horizontal") != "vertical"
        length = float(it["length"])
        points = [[0, 0], [length, 0]] if horizontal else [[0, 0], [0, length]]
        w, h = (length, 0) if horizontal else (0, length)
        e = _base("line", it["x"], it["y"], w, h, id=it.get("id"), strokeWidth=1, points=points,
                  lastCommittedPoint=None, startBinding=None, endBinding=None,
                  startArrowhead=None, endArrowhead=None)
        if it.get("dashed"):
            e["strokeStyle"] = "dashed"
        self._register(it, e, "divider")
        if it.get("label"):
            size = it.get("size", default_size("small"))
            _, th = text_size(it["label"], self.font, size)
            if horizontal:
                self._free_text(it["label"], it["x"], it["y"] - th - 6, size, "left")
            else:
                self._free_text(it["label"], it["x"] + 8, it["y"], size, "left")

    def add_group(self, it):
        # one shared groupIds entry makes the members (and their bound text / icon) move together
        gid = _id()
        for ref in it.get("members", []):
            e = self.by_id.get(ref)
            if e is None:
                raise SystemExit(f"group references unknown id: {ref}")
            for member in self._group_members(e):
                if gid not in member["groupIds"]:
                    member["groupIds"].append(gid)

    def _group_members(self, e):
        members = [e]
        members += [t for t in self.layers["text"] if t.get("containerId") == e["id"]]
        members += self.attached_icons.get(e["id"], [])
        seen, out = set(), []
        for m in members:
            if m["id"] not in seen:
                seen.add(m["id"]); out.append(m)
        return out

    def add_arrow(self, it):
        src, dst = self.by_id.get(it["from"]), self.by_id.get(it["to"])
        if not src or not dst:
            raise SystemExit(f"arrow references unknown id: {it['from']} / {it['to']}")
        color = ARROW_COLORS.get(it.get("color", "black"), it.get("color", STYLE["stroke"]))
        s_side, d_side = self._pick_sides(src, dst, it.get("from_side"), it.get("to_side"))
        gap = 5
        p0 = self._anchor(src, s_side, gap, it.get("from_offset", 0))
        p1 = self._anchor(dst, d_side, gap, it.get("to_offset", 0))
        pts = self._route(p0, p1, s_side, d_side, it.get("bend"))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        rel = [[p[0] - pts[0][0], p[1] - pts[0][1]] for p in pts]
        e = _base("arrow", pts[0][0], pts[0][1], max(xs) - min(xs), max(ys) - min(ys),
                  strokeColor=color, strokeWidth=it.get("stroke_width", STYLE["stroke_width"]), points=rel,
                  lastCommittedPoint=None,
                  startBinding=self._binding(src, s_side, gap),
                  endBinding=self._binding(dst, d_side, gap),
                  startArrowhead=self.head if it.get("bidirectional") else None,
                  endArrowhead=self.head, elbowed=STYLE["elbowed"], fixedSegments=None,
                  startIsSpecial=None, endIsSpecial=None)
        if it.get("dashed"):
            e["strokeStyle"] = "dashed"
        src["boundElements"].append({"id": e["id"], "type": "arrow"})
        dst["boundElements"].append({"id": e["id"], "type": "arrow"})
        self.layers["arrow"].append(e)
        if it.get("label"):
            size = it.get("size", default_size("small"))
            tw, th = text_size(it["label"], self.font, size)
            (mx, my), vertical = self._label_anchor(pts, it.get("label_at", "mid"))
            if vertical:
                self._free_text(it["label"], mx + 8, my - th / 2, size, "left", color=color)
            else:
                self._free_text(it["label"], mx - tw / 2, my - th - 8, size, "center", color=color)

    # ---------- helpers ----------
    def _register(self, it, e, layer):
        if it.get("id"):
            self.by_id[it["id"]] = e
        if layer:
            self.layers[layer].append(e)

    def _free_text(self, text, x, y, size, align, color=None):
        color = color or STYLE["stroke"]
        tw, th = text_size(text, self.font, size)
        t = _base("text", x, y, tw, th, strokeColor=color, text=text, originalText=text, fontSize=size,
                  fontFamily=self.font, textAlign=align, verticalAlign="top", containerId=None,
                  autoResize=True, lineHeight=LINE_H)
        self.layers["text"].append(t)
        return t

    def _image(self, src, x, y, w, h, group=None, spec_id=None, on_fill="#ffffff", icon_color=None):
        path = os.path.join(self.base_dir, src) if not os.path.isabs(src) else src
        owner = f"box {group.get('id')}" if group is not None else f"image {spec_id or ''}".strip()
        if not os.path.exists(path):
            raise SystemExit(f"{owner}: icon not found: {path}")
        data = open(path, "rb").read()
        ext = os.path.splitext(path)[1].lower()
        _check_image(path, data, ext, owner)
        if ext == ".svg" and icon_color != "keep":
            data, note = recolor_svg(data, on_fill, icon_color)
            if note:
                self.darkened.append(f"{os.path.basename(path)} {note}")
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
                ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "application/octet-stream")
        fid = hashlib.sha1(data).hexdigest()
        iw, ih = _image_dims(data, ext)
        ratio = iw / ih if iw and ih else 1.0
        if w is None:
            w = h * ratio
        elif h is None:
            h = w / ratio
        self.files[fid] = {"mimeType": mime, "id": fid,
                           "dataURL": f"data:{mime};base64," + base64.b64encode(data).decode(),
                           "created": _now, "lastRetrieved": _now}
        e = _base("image", x, y, w, h, id=spec_id, strokeColor="transparent", status="saved", fileId=fid,
                  scale=[1, 1], crop=None)
        if group is not None:
            gid = _id()
            group["groupIds"].append(gid); e["groupIds"].append(gid)
        self.layers["image"].append(e)
        return e

    @staticmethod
    def _pick_sides(a, b, sa, sb):
        if sa and sb:
            return sa, sb
        ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
        bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        dx, dy = bx - ax, by - ay
        if abs(dx) * 1.0 >= abs(dy) * 1.0:
            auto = ("right", "left") if dx > 0 else ("left", "right")
        else:
            auto = ("bottom", "top") if dy > 0 else ("top", "bottom")
        return sa or auto[0], sb or auto[1]

    @staticmethod
    def _anchor(e, side, gap, offset):
        x, y, w, h = e["x"], e["y"], e["width"], e["height"]
        return {"left": (x - gap, y + h / 2 + offset), "right": (x + w + gap, y + h / 2 + offset),
                "top": (x + w / 2 + offset, y - gap), "bottom": (x + w / 2 + offset, y + h + gap)}[side]

    @staticmethod
    def _binding(e, side, gap):
        fp = {"left": [0, 0.5], "right": [1, 0.5], "top": [0.5, 0], "bottom": [0.5, 1]}[side]
        return {"elementId": e["id"], "focus": 0, "gap": gap, "fixedPoint": fp, "mode": "orbit"}

    @staticmethod
    def _route(p0, p1, s_side, d_side, bend=None):
        """Orthogonal route. `bend` fixes the coordinate of the middle segment (the x of
        the vertical run for left/right routes, the y of the horizontal run for
        top/bottom routes) so two arrows between the same rows do not share a line."""
        (x0, y0), (x1, y1) = p0, p1
        horiz = {"left", "right"}
        detour = 40  # how far a same-side arrow loops out before coming back
        if s_side in horiz and d_side in horiz:
            if abs(y0 - y1) < 1 and s_side != d_side and bend is None:
                return [(x0, y0), (x1, y1)]
            if bend is not None:
                mx = bend
            elif s_side == d_side:   # right->right or left->left: loop out beside both boxes
                mx = max(x0, x1) + detour if s_side == "right" else min(x0, x1) - detour
            else:
                mx = (x0 + x1) / 2
            return [(x0, y0), (mx, y0), (mx, y1), (x1, y1)]
        if s_side not in horiz and d_side not in horiz:
            if abs(x0 - x1) < 1 and s_side != d_side and bend is None:
                return [(x0, y0), (x1, y1)]
            if bend is not None:
                my = bend
            elif s_side == d_side:   # bottom->bottom or top->top: loop out below / above both boxes
                my = max(y0, y1) + detour if s_side == "bottom" else min(y0, y1) - detour
            else:
                my = (y0 + y1) / 2
            return [(x0, y0), (x0, my), (x1, my), (x1, y1)]
        # mixed: one bend
        if s_side in horiz:
            return [(x0, y0), (x1, y0), (x1, y1)]
        return [(x0, y0), (x0, y1), (x1, y1)]

    @staticmethod
    def _label_anchor(pts, where="mid"):
        # midpoint of the longest segment ("mid"), or of the first / last segment
        segs = list(zip(pts, pts[1:]))
        if where == "start":
            segs = segs[:1]
        elif where == "end":
            segs = segs[-1:]
        best, bl, vertical = None, -1, False
        for a, b in segs:
            l = math.hypot(b[0] - a[0], b[1] - a[1])
            if l > bl:
                bl, best = l, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                vertical = abs(b[0] - a[0]) < abs(b[1] - a[1])
        return best, vertical

    def to_json(self):
        # z-order: regions & shapes (box / diamond / ellipse) by area (big first, so
        # parents precede children), then images, dividers, free/bound text, arrows
        # last so nothing hides them.
        shapes = sorted(self.layers["region"] + self.layers["box"],
                        key=lambda e: -e["width"] * e["height"])
        bound = {t["containerId"]: t for t in self.layers["text"] if t.get("containerId")}
        ordered = []
        for s in shapes:
            ordered.append(s)
            if s["id"] in bound:
                ordered.append(bound.pop(s["id"]))
        ordered += self.layers["image"]
        ordered += self.layers["divider"]
        ordered += [t for t in self.layers["text"] if not t.get("containerId")]
        ordered += self.layers["arrow"]
        for i, e in enumerate(ordered):
            e["index"] = "a" + format(i, "04d")
        return {"type": "excalidraw", "version": 2, "source": "prettier-excalidraw",
                "elements": ordered,
                "appState": {"gridSize": 20, "gridStep": 5, "gridModeEnabled": False,
                             "viewBackgroundColor": STYLE["canvas"], "lockedMultiSelections": {}},
                "files": self.files}


ICON_EXTS = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")


def slug(text):
    import re
    return re.sub(r"[^a-z0-9]", "", text.lower())


def icon_dirs(spec, base_dir):
    """Folders to look for icons in: spec `icons_dir` (string or list, relative to the
    spec) then PRETTIER_EXCALIDRAW_ICONS (os.pathsep-separated)."""
    dirs = spec.get("icons_dir") or []
    if isinstance(dirs, str):
        dirs = [dirs]
    dirs = [d if os.path.isabs(d) else os.path.join(base_dir, d) for d in dirs]
    env = os.environ.get("PRETTIER_EXCALIDRAW_ICONS", "")
    dirs += [d for d in env.split(os.pathsep) if d]
    return [d for d in dirs if os.path.isdir(d)]


def find_icon(name, dirs):
    """Match a name against the files in the icon folders by slug: exact first, then a
    unique prefix match either way ("postgres" finds PostgreSQL.svg). None if no match."""
    want = slug(name)
    if not want:
        return None
    files = []
    for d in dirs:
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(ICON_EXTS):
                files.append((slug(os.path.splitext(f)[0]), os.path.join(d, f)))
    exact = [p for s_, p in files if s_ == want]
    if exact:
        return exact[0]
    loose = [p for s_, p in files if s_.startswith(want) or want.startswith(s_)]
    return loose[0] if len(loose) == 1 else None


_SVG_FILL = None


def recolor_svg(data, on_fill, icon_color=None):
    """Simple Icons SVGs carry one brand colour as fill="..." on the root element.
    If that colour has too little contrast on the box fill, darken it towards black
    until it reads (WCAG 3:1 for graphics); `icon_color` forces a specific hex.
    Returns (bytes, note-or-None). SVGs without a root fill are left alone."""
    import re
    text = data.decode("utf-8", "ignore")
    m = re.search(r'<svg\b[^>]*?\sfill=["\'](#[0-9a-fA-F]{3,8})["\']', text)
    if not m:
        return data, None
    cur = m.group(1)[:7] if len(m.group(1)) == 9 else m.group(1)   # #RRGGBBAA -> ignore alpha
    if icon_color:
        new = icon_color
        note = f"fill {cur} -> {new} (icon_color)"
    else:
        if contrast(cur, on_fill) >= ICON_MIN_CONTRAST:
            return data, None
        new = darken_to_contrast(cur, on_fill)
        note = f"{cur}->{new} (contrast {contrast(cur, on_fill):.1f} on {on_fill})"
    text = text[:m.start(1)] + new + text[m.end(1):]
    return text.encode("utf-8"), note


def _check_image(path, data, ext, owner="image"):
    """Refuse empty or mis-typed icon files (a missing Simple Icons slug downloads an
    empty or HTML file) so the diagram never carries a broken image. The message names
    the box or image that uses the file."""
    if not data:
        raise SystemExit(f"{owner}: {path} is empty")
    head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n")   # tolerate a UTF-8 BOM and leading whitespace
    ok = {".svg": head.startswith(b"<svg") or head.startswith(b"<?xml"),
          ".png": data[:8] == b"\x89PNG\r\n\x1a\n",
          ".jpg": data[:2] == b"\xff\xd8", ".jpeg": data[:2] == b"\xff\xd8",
          ".gif": data[:4] == b"GIF8", ".webp": data[8:12] == b"WEBP"}.get(ext)
    if ok is None:
        raise SystemExit(f"{owner}: unsupported icon type {ext}: {path}")
    if not ok:
        raise SystemExit(f"{owner}: {path} does not look like {ext[1:].upper()} (starts with {data[:20]!r})")


def _image_dims(data, ext):
    try:
        if ext == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if ext == ".gif":
            return struct.unpack("<HH", data[6:10])
        if ext in (".jpg", ".jpeg"):
            i = 2
            while i < len(data):
                if data[i] != 0xFF: i += 1; continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9]); return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        if ext == ".svg":
            import re
            s = data.decode("utf-8", "ignore")
            m = re.search(r'viewBox=["\']\s*[\d.\-]+[\s,]+[\d.\-]+[\s,]+([\d.]+)[\s,]+([\d.]+)', s)
            if m: return float(m.group(1)), float(m.group(2))
            mw = re.search(r'\swidth=["\']([\d.]+)', s); mh = re.search(r'\sheight=["\']([\d.]+)', s)
            if mw and mh: return float(mw.group(1)), float(mh.group(1))
    except Exception:
        pass
    return 1, 1


def main():
    style_from_argv(sys.argv)
    argv = [a for i, a in enumerate(sys.argv[1:]) if a != "--style" and sys.argv[1:][i - 1] != "--style"]
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__); sys.exit(2)
    spec_path, out = args
    spec = json.load(open(spec_path, encoding="utf-8"))
    b = Builder(spec, base_dir=os.path.dirname(os.path.abspath(spec_path)))
    doc = b.build()
    json.dump(doc, open(out, "w", encoding="utf-8"), indent=1)
    for w in b.warnings:
        print("warning:", w)
    if b.darkened:
        print("icons darkened for contrast (set icon_color to override): " + "; ".join(b.darkened))
    print(f"wrote {out}: {len(doc['elements'])} elements, {len(doc['files'])} embedded images")
    for flag, ext in (("--svg", ".svg"), ("--png", ".png")):
        if flag in flags:
            from export import export
            target = os.path.splitext(out)[0] + ext
            print(f"wrote {target} ({export(out, target)})")


if __name__ == "__main__":
    main()

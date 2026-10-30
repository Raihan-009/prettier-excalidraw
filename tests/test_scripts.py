"""Tests for the prettier-excalidraw scripts. Standard library only.

Run:  python3 -m unittest discover -s tests -v
"""
import copy, glob, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "prettier-excalidraw")
SCRIPTS = os.path.join(SKILL, "scripts")
EXAMPLES = os.path.join(SKILL, "assets", "examples")
sys.path.insert(0, SCRIPTS)

import build, exstyle, fix, lint  # noqa: E402


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True, cwd=SCRIPTS)


class TestSkillLayout(unittest.TestCase):
    def test_frontmatter(self):
        text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
        self.assertTrue(text.startswith("---\n"))
        head = text.split("---")[1]
        self.assertIn("name: prettier-excalidraw", head)
        self.assertIn("description:", head)
        self.assertLess(len(text.splitlines()), 300, "SKILL.md should stay short")

    def test_every_lint_rule_is_documented(self):
        guide = open(os.path.join(SKILL, "references", "style-guide.md"), encoding="utf-8").read()
        src = open(os.path.join(SCRIPTS, "lint.py"), encoding="utf-8").read()
        import re
        rules = set(re.findall(r'add\("([a-z-]+)"', src))
        self.assertTrue(rules)
        for r in rules:
            self.assertIn(f"| {r} |", guide, f"lint rule '{r}' missing from style-guide.md")


class TestBuildExamples(unittest.TestCase):
    def test_specs_build_and_lint_clean(self):
        specs = glob.glob(os.path.join(EXAMPLES, "*.spec.json"))
        self.assertGreaterEqual(len(specs), 3)
        for spec in specs:
            with self.subTest(spec=os.path.basename(spec)):
                with tempfile.TemporaryDirectory() as td:
                    out = os.path.join(td, "out.excalidraw")
                    r = run("build.py", spec, out)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    doc = json.load(open(out, encoding="utf-8"))
                    self.assertEqual(doc["type"], "excalidraw")
                    findings = lint.lint(out)
                    self.assertEqual(findings, [], [f["message"] for f in findings])

    def test_shipped_examples_lint_clean(self):
        for f in glob.glob(os.path.join(EXAMPLES, "*.excalidraw")):
            with self.subTest(file=os.path.basename(f)):
                findings = [x for x in lint.lint(f) if x["fixable"]]
                self.assertEqual(findings, [], [x["message"] for x in findings])

    def test_zorder_and_bindings(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "o.excalidraw")
            run("build.py", os.path.join(EXAMPLES, "temporal.spec.json"), out)
            els = json.load(open(out, encoding="utf-8"))["elements"]
            types = [e["type"] for e in els]
            last_shape = max(i for i, t in enumerate(types) if t == "rectangle")
            first_arrow = min(i for i, t in enumerate(types) if t == "arrow")
            self.assertGreater(first_arrow, last_shape, "arrows must come after every box")
            ids = {e["id"] for e in els}
            for a in (e for e in els if e["type"] == "arrow"):
                self.assertIn(a["startBinding"]["elementId"], ids)
                self.assertIn(a["endBinding"]["elementId"], ids)
                self.assertEqual(a["endArrowhead"], "triangle_outline")
                self.assertTrue(a["elbowed"])
            for t in (e for e in els if e["type"] == "text" and e.get("containerId")):
                self.assertIn(t["containerId"], ids)
                self.assertEqual(t["fontFamily"], 8)

    def test_same_side_arrow_loops_out(self):
        pts = build.Builder._route((100, 200), (300, 200), "bottom", "bottom")
        ys = [p[1] for p in pts]
        self.assertEqual(max(ys), 240, "bottom->bottom should detour 40px below both anchors")
        pts = build.Builder._route((100, 200), (300, 200), "right", "left")
        self.assertEqual(len(pts), 2, "aligned right->left is a straight line")


class TestLintAndFix(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.td.name, "src.excalidraw")
        run("build.py", os.path.join(EXAMPLES, "temporal.spec.json"), self.src)
        self.doc = json.load(open(self.src, encoding="utf-8"))

    def tearDown(self):
        self.td.cleanup()

    def _save(self, doc, name="bad.excalidraw"):
        p = os.path.join(self.td.name, name)
        json.dump(doc, open(p, "w", encoding="utf-8"))
        return p

    def test_detects_and_fixes_style_breaks(self):
        doc = copy.deepcopy(self.doc)
        els = doc["elements"]
        text = next(e for e in els if e["type"] == "text")
        text["fontFamily"] = 1; text["fontSize"] = 17.3
        rect = next(e for e in els if e["type"] == "rectangle")
        rect["roughness"] = 1; rect["fillStyle"] = "hachure"; rect["roundness"] = {"type": 3}
        arrow = next(e for e in els if e["type"] == "arrow")
        arrow["endArrowhead"] = "arrow"
        # move that arrow to the front so a filled box is drawn over it
        els.remove(arrow); els.insert(0, arrow)
        p = self._save(doc)
        rules = {f["rule"] for f in lint.lint(p)}
        for r in ("font", "font-size", "roughness", "fill-style", "rounded-corners", "arrowhead", "arrow-hidden"):
            self.assertIn(r, rules)
        n = fix.fix(doc)
        self.assertGreater(n, 0)
        p2 = self._save(doc, "fixed.excalidraw")
        self.assertEqual([f for f in lint.lint(p2) if f["fixable"]], [])

    def test_child_before_parent_is_fixed(self):
        doc = copy.deepcopy(self.doc)
        els = doc["elements"]
        rects = [e for e in els if e["type"] == "rectangle"]
        big = max(rects, key=lambda r: r["width"] * r["height"])
        els.remove(big); els.append(big)          # container now drawn last, hiding children
        p = self._save(doc)
        self.assertIn("child-before-parent", {f["rule"] for f in lint.lint(p)})
        fix.fix(doc)
        p2 = self._save(doc, "fixed.excalidraw")
        self.assertNotIn("child-before-parent", {f["rule"] for f in lint.lint(p2)})

    def test_misleading_store_placement(self):
        doc = copy.deepcopy(self.doc)
        byid = {e["id"]: e for e in doc["elements"]}
        # 'matching' sits directly under 'history' with no arrow between them; painting it
        # as a store (red) must trigger the proximity rule
        byid["matching"]["backgroundColor"] = "#ffc9c9"
        p = self._save(doc)
        hits = [f for f in lint.lint(p) if f["rule"] == "misleading-proximity"]
        self.assertEqual([h["id"] for h in hits], ["matching"])
        # a store under the box that uses it is fine
        doc = copy.deepcopy(self.doc)
        byid = {e["id"]: e for e in doc["elements"]}
        byid["history"]["backgroundColor"] = "#ffc9c9"      # history is under server, which feeds it
        p = self._save(doc, "ok.excalidraw")
        self.assertEqual([f for f in lint.lint(p) if f["rule"] == "misleading-proximity"], [])

    def test_library_icons_are_exempt(self):
        doc = copy.deepcopy(self.doc)
        gid = "grp1"
        for i in range(3):
            doc["elements"].append({"id": f"ic{i}", "type": "line", "x": 0, "y": 0, "width": 10, "height": 10,
                                    "points": [[0, 0], [10, 10]], "roughness": 1, "groupIds": [gid],
                                    "strokeColor": "#1e1e1e", "fillStyle": "hachure", "isDeleted": False})
        p = self._save(doc)
        self.assertNotIn("roughness", {f["rule"] for f in lint.lint(p)})

    def test_fix_remeasures_and_recentres_labels(self):
        doc = copy.deepcopy(self.doc)
        byid = {e["id"]: e for e in doc["elements"]}
        label = next(e for e in doc["elements"] if e["type"] == "text" and e.get("containerId"))
        box = byid[label["containerId"]]
        label["fontSize"] = 6.0; label["width"] = 10; label["height"] = 5; label["x"] = box["x"]; label["y"] = box["y"]
        fix.fix(doc)
        self.assertEqual(label["fontSize"], 16)
        exp_w = max(len(l) for l in label["text"].split("\n")) * exstyle.CHAR_W[8] * 16
        self.assertAlmostEqual(label["width"], exp_w, places=3)
        self.assertAlmostEqual(label["x"], box["x"] + (box["width"] - exp_w) / 2, places=3)
        self.assertTrue(any(label["id"] in b for b in fix.fix.big_changes))

    def test_build_warns_on_icon_shrink_and_keeps_grid(self):
        spec = {"elements": [{"id": "b", "type": "box", "label": "a very long label that needs room",
                              "icon": os.path.join(EXAMPLES, "icons", "redis.svg"), "x": 0, "y": 0, "w": 200, "h": 70}]}
        b = build.Builder(spec, base_dir=EXAMPLES)
        doc = b.build()
        box = next(e for e in doc["elements"] if e["type"] == "rectangle")
        self.assertEqual(box["width"] % 20, 0, "widened boxes stay on the 20px grid")
        self.assertTrue(any("icon shrunk" in w for w in b.warnings))

    def test_region_subtitle(self):
        spec = {"elements": [{"id": "r", "type": "region", "title": "[ a ]", "subtitle": "note", "x": 0, "y": 0, "w": 600, "h": 200}]}
        doc = build.Builder(spec).build()
        texts = [e for e in doc["elements"] if e["type"] == "text"]
        self.assertEqual({t["text"] for t in texts}, {"[ a ]", "note"})
        note = next(t for t in texts if t["text"] == "note")
        self.assertGreater(note["x"], 300, "subtitle sits in the opposite corner")

    def test_fix_respects_font_option(self):
        doc = copy.deepcopy(self.doc)
        fix.fix(doc, font="nunito")
        self.assertTrue(all(e["fontFamily"] == 6 for e in doc["elements"] if e["type"] == "text"))


class TestNoteElement(unittest.TestCase):
    """Spec `note` element: lightgrey annotation box with bound left-aligned text (#37)."""

    def test_note_builds_bound_text_and_avoids_lint_false_positives(self):
        spec = {
            "elements": [
                {"id": "svc", "type": "box", "label": "api", "x": 0, "y": 0, "w": 200, "h": 60},
                {"id": "store", "type": "box", "label": "cache", "fill": "red", "x": 0, "y": 200, "w": 200, "h": 60},
                {"type": "arrow", "from": "svc", "to": "store"},
                {
                    "id": "n1",
                    "type": "note",
                    "text": "connects with external MCP server\ncollect data periodically",
                    "x": 40,
                    "y": 80,
                    "w": 400,
                },
            ]
        }
        doc = build.Builder(spec).build()
        note = next(e for e in doc["elements"] if e["id"] == "n1")
        self.assertEqual(note["type"], "rectangle")
        self.assertEqual(note["backgroundColor"], exstyle.FILLS["lightgrey"])
        self.assertEqual(note["strokeWidth"], 1)
        bound = next(e for e in doc["elements"] if e.get("containerId") == "n1")
        self.assertEqual(bound["text"], "connects with external MCP server\ncollect data periodically")
        self.assertEqual(bound["textAlign"], "left")
        self.assertEqual(bound["fontSize"], exstyle.size("small"))
        # height comes from the text plus 12 px padding on each side
        tw, th = build.text_size(bound["text"], 8, bound["fontSize"])
        self.assertAlmostEqual(note["height"], th + 2 * 12, places=3)
        self.assertEqual(note["width"], 400)
        # optional w defaults to text width + padding on both sides
        bare = build.Builder({"elements": [{"type": "note", "text": "short", "x": 0, "y": 0}]}).build()
        n2 = next(e for e in bare["elements"] if e["type"] == "rectangle")
        t2 = next(e for e in bare["elements"] if e["type"] == "text")
        self.assertAlmostEqual(n2["width"], t2["width"] + 2 * 12, places=3)
        # note sits in the box layer (before free text / arrows) with bound label after it
        ids = [e["id"] for e in doc["elements"]]
        self.assertLess(ids.index("n1"), ids.index(bound["id"]))
        arrow = next(e for e in doc["elements"] if e["type"] == "arrow")
        self.assertGreater(ids.index(arrow["id"]), ids.index("n1"))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            rules = {f["rule"] for f in lint.lint(p)}
            self.assertNotIn("text-over-box", rules)
            self.assertNotIn("misleading-proximity", rules)

    def test_note_is_ignored_by_misleading_proximity(self):
        # a red store under a note must not be flagged; notes are annotations, not owners
        spec = {
            "elements": [
                {"id": "n", "type": "note", "text": "aside", "x": 0, "y": 0, "w": 200},
                {"id": "store", "type": "box", "label": "cache", "fill": "red", "x": 0, "y": 120, "w": 200, "h": 60},
                {"id": "owner", "type": "box", "label": "worker", "x": 400, "y": 120, "w": 200, "h": 60},
                {"type": "arrow", "from": "owner", "to": "store"},
            ]
        }
        doc = build.Builder(spec).build()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            hits = [f for f in lint.lint(p) if f["rule"] == "misleading-proximity"]
            self.assertEqual(hits, [])


class TestSmallBugs(unittest.TestCase):
    def test_builder_rejects_bad_icon(self):
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "missing.svg"); open(bad, "w", encoding="utf-8").write("")
            html = os.path.join(td, "page.svg"); open(html, "w", encoding="utf-8").write("<html>404</html>")
            for icon in (bad, html, os.path.join(td, "nope.svg")):
                spec = {"elements": [{"id": "b", "type": "box", "label": "x", "icon": icon, "x": 0, "y": 0}]}
                with self.assertRaises(SystemExit) as cm:
                    build.Builder(spec).build()
                self.assertIn("box b", str(cm.exception.code), "error names the owner")
            bom = os.path.join(td, "bom.svg")
            open(bom, "wb").write(b'\xef\xbb\xbf<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>')
            doc = build.Builder({"elements": [{"id": "b", "type": "box", "label": "x", "icon": bom, "x": 0, "y": 0}]}).build()
            self.assertEqual(len(doc["files"]), 1, "BOM and xml declaration are accepted")

    def test_fix_refreshes_version_nonce(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "o.excalidraw")
            run("build.py", os.path.join(EXAMPLES, "payment.spec.json"), out)
            doc = json.load(open(out, encoding="utf-8")); before = {e["id"]: e["versionNonce"] for e in doc["elements"]}
            fix.fix(doc)
            for e in doc["elements"]:
                self.assertNotEqual(e["versionNonce"], before[e["id"]])
                self.assertIsInstance(e["versionNonce"], int)
                self.assertTrue(1 <= e["versionNonce"] < 2 ** 31)

    def test_box_overlap_rule(self):
        spec = {"elements": [{"id": "a", "type": "box", "label": "a", "x": 0, "y": 0, "w": 200, "h": 60},
                             {"id": "b", "type": "box", "label": "b", "x": 150, "y": 20, "w": 200, "h": 60},
                             {"id": "r", "type": "region", "x": -40, "y": -40, "w": 600, "h": 300},
                             {"id": "c", "type": "box", "label": "c", "x": 20, "y": 150, "w": 200, "h": 60}]}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw"); json.dump(build.Builder(spec).build(), open(p, "w", encoding="utf-8"))
            hits = [f for f in lint.lint(p) if f["rule"] == "box-overlap"]
            self.assertEqual([h["id"] for h in hits], ["a"], "a/b overlap; c inside region is nesting, not overlap")

    def test_box_overlap_cell_grid_on_strip(self):
        """Four equal tiny cells overhanging a strip are a grid, not collisions (#54)."""
        def rect(eid, x, y, w, h, fill="#a5d8ff"):
            return {"id": eid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
                    "backgroundColor": fill, "strokeColor": "#1e1e1e", "fillStyle": "solid",
                    "roughness": 0, "strokeStyle": "solid", "strokeWidth": 2, "roundness": None,
                    "isDeleted": False, "boundElements": []}

        strip = rect("strip", 0, 100, 400, 40, "#ffec99")
        cells = [rect(f"c{i}", 20 + i * 90, 95, 50, 50) for i in range(4)]
        with tempfile.TemporaryDirectory() as td:
            # strip first (correct z-order): no box-overlap, no child-before-parent
            p = os.path.join(td, "grid.excalidraw")
            json.dump({"type": "excalidraw", "version": 2, "elements": [strip] + cells},
                      open(p, "w", encoding="utf-8"))
            findings = lint.lint(p)
            self.assertEqual([f for f in findings if f["rule"] == "box-overlap"], [])
            self.assertEqual([f for f in findings if f["rule"] == "child-before-parent"], [])

            # cells drawn before strip: strip is still their container for z-order
            p2 = os.path.join(td, "z.excalidraw")
            json.dump({"type": "excalidraw", "version": 2, "elements": cells + [strip]},
                      open(p2, "w", encoding="utf-8"))
            zhits = [f for f in lint.lint(p2) if f["rule"] == "child-before-parent"]
            self.assertEqual({h["id"] for h in zhits}, {"c0", "c1", "c2", "c3"})
            self.assertTrue(all("strip" in h["message"] for h in zhits))

            # a real collision next to the grid still fires
            collision = rect("boom", 30, 90, 80, 60, "#ffc9c9")
            p3 = os.path.join(td, "mix.excalidraw")
            json.dump({"type": "excalidraw", "version": 2, "elements": [strip] + cells + [collision]},
                      open(p3, "w", encoding="utf-8"))
            ohits = [f for f in lint.lint(p3) if f["rule"] == "box-overlap"]
            self.assertTrue(any(h["id"] == "boom" or "boom" in h["message"] for h in ohits))


class TestStripTitles(unittest.TestCase):
    """Mixed diagrams: a flow drawn across layer strips keeps off the strip titles (#10)."""

    STRIPS = [
        {"id": "l1", "type": "region", "x": 0, "y": 0, "w": 1200, "h": 200, "title": "[ developer experience ]"},
        {"id": "l2", "type": "region", "x": 0, "y": 240, "w": 1200, "h": 200,
         "title": "[ platform services - stateless, autoscaled ]"},
        {"id": "l3", "type": "region", "x": 0, "y": 480, "w": 1200, "h": 200, "title": "[ infrastructure ]",
         "subtitle": "managed by the platform team"},
        {"id": "portal", "type": "box", "x": 40, "y": 80, "w": 320, "h": 80, "label": "web portal"},
        {"id": "cicd", "type": "box", "x": 40, "y": 320, "w": 320, "h": 80, "label": "ci/cd"},
        {"id": "k8s", "type": "box", "x": 40, "y": 560, "w": 320, "h": 80, "label": "kubernetes"},
        {"id": "docs", "type": "box", "x": 600, "y": 80, "w": 320, "h": 80, "label": "docs"},
        {"id": "obs", "type": "box", "x": 600, "y": 320, "w": 320, "h": 80, "label": "observability"},
    ]

    def build(self, *arrows, first=False):
        els = list(arrows) + self.STRIPS if first else self.STRIPS + list(arrows)
        b = build.Builder({"elements": els})
        doc = b.build()
        pts = {}
        for e in doc["elements"]:
            if e["type"] == "arrow":
                key = (e["startBinding"]["elementId"], e["endBinding"]["elementId"])
                pts[key] = [(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
        return doc, pts, b.warnings

    def lint(self, doc):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "d.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            return [f["rule"] for f in lint.lint(p)]

    def test_straight_arrow_slides_past_the_title(self):
        # "[ infrastructure ]" spans x 16..214; the arrow would run down x=200 through it
        doc, pts, warnings = self.build({"type": "arrow", "from": "cicd", "to": "k8s", "label": "deploy"})
        route = pts[("cicd", "k8s")]
        self.assertEqual(len(route), 2, "stays a straight arrow")
        self.assertEqual(route[0][0], route[1][0])
        self.assertEqual(route[0][0], 240, "same offset at both ends, snapped to the 20 px grid past the title")
        self.assertTrue(any("cicd -> k8s: offset +40" in w for w in warnings), warnings)
        self.assertNotIn("arrow-through-text", self.lint(doc))

    def test_bent_route_moves_its_middle_run(self):
        # the long title on l2 spans x 16..511; the default run at x=480 would cross it
        doc, pts, warnings = self.build({"type": "arrow", "from": "docs", "to": "cicd", "from_side": "left", "to_side": "right"})
        route = pts[("docs", "cicd")]
        self.assertEqual(len(route), 4)
        self.assertEqual(route[1][0], 540, "vertical run moved past the title, on the grid")
        self.assertTrue(any("docs -> cicd: bend 540" in w for w in warnings), warnings)
        self.assertNotIn("arrow-through-text", self.lint(doc))

    def test_explicit_offset_and_bend_are_kept(self):
        _, pts, warnings = self.build(
            {"type": "arrow", "from": "cicd", "to": "k8s", "from_offset": 0, "to_offset": 0},
            {"type": "arrow", "from": "docs", "to": "cicd", "from_side": "left", "to_side": "right", "bend": 480})
        self.assertEqual(pts[("cicd", "k8s")][0][0], 200, "author's offsets win, even through a title")
        self.assertEqual(pts[("docs", "cicd")][1][0], 480, "author's bend wins")
        self.assertEqual(warnings, [])

    def test_title_wider_than_the_column_is_left_alone(self):
        # no offset within the 320 px box clears a 495 px title: route unchanged, lint still reports it
        doc, pts, warnings = self.build({"type": "arrow", "from": "portal", "to": "cicd"})
        self.assertEqual(pts[("portal", "cicd")], [(200, 165), (200, 315)])
        self.assertEqual(warnings, [])
        self.assertIn("arrow-through-text", self.lint(doc))

    def test_regions_listed_after_arrows_are_still_avoided(self):
        _, pts, _ = self.build({"type": "arrow", "from": "cicd", "to": "k8s"}, first=True)
        self.assertEqual(pts[("cicd", "k8s")][0][0], 240)

    def test_labels_keep_off_strip_borders_and_titles(self):
        # 40 px between strips and boxes 80 px from the edges: a mid-segment label would straddle a border
        doc, pts, _ = self.build(
            {"type": "arrow", "from": "cicd", "to": "k8s", "label": "deploy [gitops]"},
            {"type": "arrow", "from": "docs", "to": "cicd", "from_side": "left", "to_side": "right", "label": "docs build"},
            {"type": "arrow", "from": "portal", "to": "obs", "from_side": "right", "to_side": "left", "label": "dashboards",
             "from_offset": 20})
        rules = self.lint(doc)
        self.assertNotIn("text-on-region-edge", rules)
        self.assertNotIn("text-overlap", rules)
        labels = {e["text"]: e for e in doc["elements"] if e["type"] == "text" and not e.get("containerId")}
        run = pts[("docs", "cicd")]
        self.assertGreater(labels["docs build"]["x"], run[1][0], "label sits right of the vertical run")
        self.assertGreater(labels["docs build"]["y"], 240 + 4, "and inside the strip, not on its border")
        d = labels["dashboards"]
        self.assertTrue(d["y"] >= 240 or d["y"] + d["height"] <= 240, "label is on one side of the border")


class TestIconFolder(unittest.TestCase):
    def _spec(self, icon, extra=None):
        el = {"id": "b", "type": "box", "label": "postgres\n[db]", "icon": icon, "x": 0, "y": 0}
        return {"icons_dir": "myicons", "elements": [el], **(extra or {})}

    def test_named_auto_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            d = os.path.join(td, "myicons"); os.makedirs(d)
            import shutil
            shutil.copy(os.path.join(EXAMPLES, "icons", "postgresql.svg"), os.path.join(d, "PostgreSQL.svg"))
            shutil.copy(os.path.join(EXAMPLES, "icons", "redis.svg"), os.path.join(d, "Redis Cache.png"))
            # explicit name, exact slug
            doc = build.Builder(self._spec("PostgreSQL"), base_dir=td).build()
            self.assertEqual(sum(e["type"] == "image" for e in doc["elements"]), 1)
            # auto from the label, prefix match ("postgres" -> PostgreSQL.svg)
            doc = build.Builder(self._spec("auto"), base_dir=td).build()
            self.assertEqual(sum(e["type"] == "image" for e in doc["elements"]), 1)
            # auto with no match: bare box plus a warning, not an error
            b = build.Builder({"icons_dir": "myicons", "elements": [
                {"id": "b", "type": "box", "label": "kafka", "icon": "auto", "x": 0, "y": 0}]}, base_dir=td)
            doc = b.build()
            self.assertEqual(sum(e["type"] == "image" for e in doc["elements"]), 0)
            self.assertTrue(any("no icon for 'kafka'" in w for w in b.warnings))
            # named but missing: hard error
            with self.assertRaises(SystemExit):
                build.Builder(self._spec("kafka"), base_dir=td).build()
            # env var folder, no icons_dir in the spec; a wrong-type file (Redis Cache.png is really SVG) is refused
            os.environ["PRETTIER_EXCALIDRAW_ICONS"] = d
            try:
                with self.assertRaises(SystemExit):
                    build.Builder({"elements": [{"id": "b", "type": "box", "label": "redis cache", "icon": "auto", "x": 0, "y": 0}]}).build()
            finally:
                del os.environ["PRETTIER_EXCALIDRAW_ICONS"]


class TestIconContrast(unittest.TestCase):
    def test_contrast_math(self):
        self.assertAlmostEqual(exstyle.contrast("#000000", "#ffffff"), 21, places=1)
        self.assertLess(exstyle.contrast("#FFEC6E", "#d0bfff"), 3)       # vault yellow on purple
        dark = exstyle.darken_to_contrast("#FFEC6E", "#d0bfff")
        self.assertGreaterEqual(exstyle.contrast(dark, "#d0bfff"), 3)

    def test_builder_darkens_and_keep_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            icon = os.path.join(td, "vault.svg")
            open(icon, "w", encoding="utf-8").write('<svg fill="#FFEC6E" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M0 0h24v24z"/></svg>')
            base = {"id": "b", "type": "box", "label": "vault", "icon": icon, "x": 0, "y": 0, "fill": "purple"}
            import base64
            def fill_of(spec):
                b = build.Builder(spec); doc = b.build()
                svg = base64.b64decode(next(iter(doc["files"].values()))["dataURL"].split(",", 1)[1]).decode()
                import re; return re.search(r'fill="(#[0-9a-fA-F]+)"', svg).group(1), b.darkened
            fill, warns = fill_of({"elements": [base]})
            self.assertNotEqual(fill.lower(), "#ffec6e"); self.assertTrue(warns)
            fill, _ = fill_of({"elements": [dict(base, icon_color="keep")]})
            self.assertEqual(fill, "#FFEC6E")
            fill, _ = fill_of({"elements": [dict(base, icon_color="#123456")]})
            self.assertEqual(fill, "#123456")
            # lint sees the low-contrast icon in a file built with keep
            doc = build.Builder({"elements": [dict(base, icon_color="keep")]}).build()
            p = os.path.join(td, "o.excalidraw"); json.dump(doc, open(p, "w", encoding="utf-8"))
            self.assertIn("icon-low-contrast", {f["rule"] for f in lint.lint(p)})


class TestSplitBranchArrows(unittest.TestCase):
    def test_continuation_is_not_flagged(self):
        spec = {"elements": [{"id": "d", "type": "box", "label": "ok?", "x": 0, "y": 0},
                             {"id": "yes", "type": "box", "label": "yes", "x": 400, "y": 0, "w": 80, "h": 40},
                             {"id": "t", "type": "box", "label": "target", "x": 700, "y": 0},
                             {"type": "arrow", "from": "d", "to": "yes"},
                             {"type": "arrow", "from": "yes", "to": "t"}]}
        doc = build.Builder(spec).build()
        arrows = [e for e in doc["elements"] if e["type"] == "arrow"]
        first = next(a for a in arrows if a["endBinding"]["elementId"] == "yes")
        last = next(a for a in arrows if a["endBinding"]["elementId"] == "t")
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            first["endArrowhead"] = None                      # first half of a branch: fine
            json.dump(doc, open(p, "w", encoding="utf-8"))
            self.assertEqual([f for f in lint.lint(p) if f["rule"] == "no-arrowhead"], [])
            last["endArrowhead"] = None                       # a real headless connector: flagged
            json.dump(doc, open(p, "w", encoding="utf-8"))
            hits = [f for f in lint.lint(p) if f["rule"] == "no-arrowhead"]
            self.assertEqual([h["id"] for h in hits], [last["id"]])


class TestDiamondEllipse(unittest.TestCase):
    def test_diamond_and_ellipse_build_bind_and_defaults(self):
        spec = {"elements": [
            {"id": "start", "type": "ellipse", "label": "start", "x": 0, "y": 120, "fill": "green"},
            {"id": "ok", "type": "diamond", "label": "is solution\navailable?", "x": 200, "y": 100,
             "w": 220, "h": 120, "fill": "none"},
            {"id": "yes", "type": "ellipse", "label": "yes", "x": 500, "y": 140, "w": 80, "h": 40, "fill": "green"},
            {"id": "done", "type": "box", "label": "ship it", "x": 680, "y": 125, "fill": "blue"},
            {"type": "arrow", "from": "start", "to": "ok"},
            {"type": "arrow", "from": "ok", "to": "yes"},
            {"type": "arrow", "from": "yes", "to": "done"},
        ]}
        doc = build.Builder(spec).build()
        byid = {e["id"]: e for e in doc["elements"] if "id" in e}
        self.assertEqual(byid["ok"]["type"], "diamond")
        self.assertEqual(byid["yes"]["type"], "ellipse")
        self.assertEqual(byid["start"]["type"], "ellipse")
        self.assertEqual(byid["start"]["width"], 80)
        self.assertEqual(byid["start"]["height"], 40)
        self.assertEqual(byid["ok"]["backgroundColor"], "transparent")
        self.assertEqual(byid["yes"]["backgroundColor"], "#b2f2bb")
        self.assertEqual(byid["ok"]["roughness"], 0)
        self.assertIsNone(byid["ok"].get("roundness"))
        # bound centred labels (ellipse defaults to size 16 so 80×40 fits)
        labels = {t["containerId"]: t for t in doc["elements"]
                  if t["type"] == "text" and t.get("containerId")}
        self.assertIn("ok", labels)
        self.assertIn("yes", labels)
        self.assertEqual(labels["start"]["fontSize"], 16)
        self.assertEqual(labels["ok"]["fontSize"], 20)
        self.assertEqual(labels["ok"]["textAlign"], "center")
        self.assertAlmostEqual(labels["ok"]["x"],
                               byid["ok"]["x"] + (byid["ok"]["width"] - labels["ok"]["width"]) / 2, places=3)
        # arrows bind to diamond / ellipse like boxes
        for a in (e for e in doc["elements"] if e["type"] == "arrow"):
            self.assertIn(a["startBinding"]["elementId"], byid)
            self.assertIn(a["endBinding"]["elementId"], byid)
        # z-order: same layer as boxes — arrows after every shape including diamond/ellipse
        types = [e["type"] for e in doc["elements"]]
        last_shape = max(i for i, t in enumerate(types) if t in ("rectangle", "diamond", "ellipse"))
        first_arrow = min(i for i, t in enumerate(types) if t == "arrow")
        self.assertGreater(first_arrow, last_shape)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            self.assertEqual(lint.lint(p), [])

    def test_default_diamond_size(self):
        doc = build.Builder({"elements": [
            {"id": "d", "type": "diamond", "label": "ok?", "x": 0, "y": 0}]}).build()
        d = next(e for e in doc["elements"] if e["id"] == "d")
        self.assertEqual((d["width"], d["height"]), (200, 100))
        self.assertEqual(d["type"], "diamond")

    def test_overlap_rules_ignore_diamond_ellipse(self):
        spec = {"elements": [
            {"id": "d", "type": "diamond", "label": "ok?", "x": 0, "y": 0, "w": 200, "h": 100},
            {"id": "e", "type": "ellipse", "label": "yes", "x": 100, "y": 30, "w": 80, "h": 40, "fill": "green"},
            {"id": "b", "type": "box", "label": "svc", "x": 50, "y": 20, "w": 200, "h": 60, "fill": "blue"},
        ]}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(build.Builder(spec).build(), open(p, "w", encoding="utf-8"))
            rules = {f["rule"] for f in lint.lint(p)}
            self.assertNotIn("box-overlap", rules)
            self.assertNotIn("misleading-proximity", rules)

class TestDividersAndGroups(unittest.TestCase):
    def test_divider_builds_as_line_and_lints_clean(self):
        spec = {"elements": [
            {"id": "d1", "type": "divider", "x": 0, "y": 480, "length": 600,
             "orientation": "horizontal", "dashed": True, "label": "private network"},
            {"id": "d2", "type": "divider", "x": 800, "y": 0, "length": 300,
             "orientation": "vertical", "label": "after"}]}
        doc = build.Builder(spec).build()
        lines = [e for e in doc["elements"] if e["type"] == "line"]
        self.assertEqual(len(lines), 2)
        byid = {e["id"]: e for e in lines}
        h, v = byid["d1"], byid["d2"]
        self.assertEqual(h["strokeWidth"], 1)
        self.assertEqual(h["strokeStyle"], "dashed")
        self.assertEqual(h["points"], [[0, 0], [600, 0]])
        self.assertEqual((h["width"], h["height"]), (600, 0))
        self.assertEqual(v["points"], [[0, 0], [0, 300]])
        self.assertEqual(v["strokeStyle"], "solid")
        labels = {e["text"]: e for e in doc["elements"] if e["type"] == "text"}
        self.assertEqual(labels["private network"]["fontSize"], exstyle.size("small"))
        self.assertLess(labels["private network"]["y"], 480, "horizontal label sits above the line")
        self.assertGreaterEqual(labels["after"]["x"], 808, "vertical label sits right of the line")
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            self.assertEqual(lint.lint(p), [], [f["message"] for f in lint.lint(p)])

    def test_lint_skips_line_elements_for_arrow_rules(self):
        doc = build.Builder({"elements": [
            {"type": "divider", "x": 0, "y": 0, "length": 200}]}).build()
        line = next(e for e in doc["elements"] if e["type"] == "line")
        line["startArrowhead"] = None
        line["endArrowhead"] = None
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "o.excalidraw")
            json.dump(doc, open(p, "w", encoding="utf-8"))
            rules = {f["rule"] for f in lint.lint(p)}
            self.assertNotIn("no-arrowhead", rules)
            self.assertNotIn("arrowhead", rules)

    def test_group_processed_last_and_covers_text_and_icon(self):
        spec = {"elements": [
            {"type": "group", "members": ["db", "cache"]},
            {"id": "db", "type": "box", "x": 0, "y": 0, "label": "database",
             "icon": os.path.join(EXAMPLES, "icons", "postgresql.svg")},
            {"id": "cache", "type": "box", "x": 0, "y": 200, "label": "cache",
             "icon": os.path.join(EXAMPLES, "icons", "redis.svg")},
            {"id": "other", "type": "box", "x": 0, "y": 400, "label": "other"}]}
        doc = build.Builder(spec).build()
        els = doc["elements"]
        byid = {e["id"]: e for e in els}
        shared = set(byid["db"]["groupIds"]) & set(byid["cache"]["groupIds"])
        self.assertEqual(len(shared), 1, "both members share exactly one group id")
        gid = shared.pop()
        self.assertNotIn(gid, byid["other"]["groupIds"], "unlisted elements stay out")
        for key in ("db", "cache"):
            box = byid[key]
            self.assertIn(gid, box["groupIds"])
            text = next(t for t in els if t["type"] == "text" and t["containerId"] == box["id"])
            self.assertIn(gid, text["groupIds"])
            icons = [e for e in els if e["type"] == "image"
                     and box["x"] <= e["x"] <= box["x"] + box["width"]
                     and box["y"] <= e["y"] <= box["y"] + box["height"]]
            self.assertEqual(len(icons), 1, "the box icon joins the group too")
            self.assertIn(gid, icons[0]["groupIds"])

    def test_group_unknown_member_is_an_error(self):
        with self.assertRaises(SystemExit):
            build.Builder({"elements": [{"type": "group", "members": ["nope"]}]}).build()


class TestStyleProfiles(unittest.TestCase):
    def tearDown(self):
        # restore the house style for the other tests
        import importlib
        exstyle.load_style(os.path.join(os.path.dirname(__file__), "house.json")) if os.path.exists(
            os.path.join(os.path.dirname(__file__), "house.json")) else None
        importlib.reload(exstyle); importlib.reload(build); importlib.reload(lint); importlib.reload(fix)

    def test_profile_of_examples_matches_house_style(self):
        import profile as prof
        p = prof.profile(glob.glob(os.path.join(EXAMPLES, "*.excalidraw")))
        self.assertEqual(p["font"], 8); self.assertEqual(p["roughness"], 0)
        self.assertEqual(p["arrowhead"], "triangle_outline"); self.assertIsNone(p["roundness"])
        self.assertIn("#a5d8ff", p["fills"].values())

    def test_custom_style_flows_through_build_lint_fix(self):
        with tempfile.TemporaryDirectory() as td:
            style = {"name": "t", "font": 6, "arrowhead": "triangle", "roughness": 1, "stroke": "#333333",
                     "roundness": {"type": 3}, "fills": {"blue": "#dbe4ff"}, "font_sizes": [14, 18, 24]}
            sp = os.path.join(td, "style.json"); json.dump(style, open(sp, "w", encoding="utf-8"))
            spec = {"style": sp, "elements": [{"id": "a", "type": "box", "label": "a", "x": 0, "y": 0, "fill": "blue"},
                                              {"id": "b", "type": "box", "label": "b", "x": 400, "y": 0, "fill": "blue"},
                                              {"type": "arrow", "from": "a", "to": "b"}]}
            doc = build.Builder(spec, base_dir=td).build()
            box = next(e for e in doc["elements"] if e["type"] == "rectangle")
            txt = next(e for e in doc["elements"] if e["type"] == "text")
            arr = next(e for e in doc["elements"] if e["type"] == "arrow")
            self.assertEqual(box["backgroundColor"], "#dbe4ff"); self.assertEqual(box["roughness"], 1)
            self.assertEqual(box["roundness"], {"type": 3}); self.assertEqual(box["strokeColor"], "#333333")
            self.assertEqual(txt["fontFamily"], 6); self.assertEqual(arr["endArrowhead"], "triangle")
            p = os.path.join(td, "o.excalidraw"); json.dump(doc, open(p, "w", encoding="utf-8"))
            self.assertEqual([f for f in lint.lint(p) if f["fixable"]], [], "clean under its own style")
            # CLI: --style on lint, and without it the house style complains
            self.assertEqual(run("lint.py", p, "--style", sp).returncode, 0)
            self.assertEqual(run("lint.py", p).returncode, 1)
            r = run("fix.py", p, os.path.join(td, "f.excalidraw"), "--style", sp)
            self.assertIn("0 changes", r.stdout)


class TestIconsHelper(unittest.TestCase):
    def test_slug_rules_and_fill_injection(self):
        import icons
        self.assertEqual(icons.title_to_slug("Node.js"), "nodedotjs")
        self.assertEqual(icons.title_to_slug("Fly.io"), "flydotio")
        self.assertEqual(icons.title_to_slug("C++"), "cplusplus")
        self.assertEqual(icons.title_to_slug("Dungeons & Dragons"), "dungeonsanddragons")
        bare = '<svg role="img" viewBox="0 0 24 24"><path d="M0 0h24v24z"/></svg>'
        self.assertIn('fill="#635BFF"', icons.inject_fill(bare, "#635BFF"))
        coloured = '<svg fill="#000000" viewBox="0 0 24 24"/>'
        self.assertIn('fill="#123456"', icons.inject_fill(coloured, "#123456"))
        self.assertNotIn("#000000", icons.inject_fill(coloured, "#123456"))

    def test_region_icon_is_placed_in_opposite_corner(self):
        spec = {"elements": [{"id": "r", "type": "region", "title": "[ vercel ]", "x": 0, "y": 0, "w": 600, "h": 200,
                              "icon": os.path.join(EXAMPLES, "icons", "kubernetes.svg")}]}
        doc = build.Builder(spec).build()
        img = next(e for e in doc["elements"] if e["type"] == "image")
        self.assertGreater(img["x"], 500, "logo sits at the right when the title is top-left")
        self.assertAlmostEqual(img["height"], 32, places=3)


class TestLintCli(unittest.TestCase):
    def test_allow_manual_exit_code(self):
        ref = os.path.join(EXAMPLES, "layered-architecture.excalidraw")
        self.assertEqual(run("lint.py", ref).returncode, 1, "reference has manual findings")
        self.assertEqual(run("lint.py", ref, "--allow-manual").returncode, 0)
        self.assertEqual(run("lint.py", os.path.join(EXAMPLES, "payment.excalidraw")).returncode, 0)


class TestLintFolder(unittest.TestCase):
    """lint.py over directories and several paths (#65)."""

    def _tree(self, td):
        src = os.path.join(EXAMPLES, "payment.excalidraw")
        os.makedirs(os.path.join(td, "nested", ".hidden"))
        os.makedirs(os.path.join(td, "node_modules"))
        shutil.copy(src, os.path.join(td, "a-clean.excalidraw"))
        shutil.copy(src, os.path.join(td, "nested", "c-clean.excalidraw"))
        shutil.copy(src, os.path.join(td, "nested", ".hidden", "skipped.excalidraw"))
        shutil.copy(src, os.path.join(td, "node_modules", "skipped.excalidraw"))
        d = json.load(open(src, encoding="utf-8"))
        for e in d["elements"]:
            if e["type"] == "rectangle":
                e["roughness"] = 1
        json.dump(d, open(os.path.join(td, "b-sketchy.excalidraw"), "w", encoding="utf-8"))
        open(os.path.join(td, "notes.txt"), "w").write("not a diagram")
        return td

    def test_collect_walks_recursively_and_skips_noise(self):
        with tempfile.TemporaryDirectory() as td:
            self._tree(td)
            found = [os.path.relpath(p, td) for p in lint.collect([td])]
            self.assertEqual(found, ["a-clean.excalidraw", "b-sketchy.excalidraw", os.path.join("nested", "c-clean.excalidraw")])

    def test_folder_summary_and_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            self._tree(td)
            r = run("lint.py", td)
            self.assertEqual(r.returncode, 1, r.stdout)
            lines = r.stdout.splitlines()
            self.assertTrue(lines[0].endswith("a-clean.excalidraw: clean"), lines[0])
            self.assertIn("b-sketchy.excalidraw: 7 findings", lines[1])
            self.assertIn("[roughness]", r.stdout)
            self.assertTrue(r.stdout.rstrip().endswith("3 files, 2 clean, 1 with findings, 1 failing"), r.stdout[-200:])
            q = run("lint.py", td, "--quiet")
            self.assertNotIn("[roughness]", q.stdout)
            self.assertIn("3 files, 2 clean, 1 with findings", q.stdout)

    def test_folder_json_shape(self):
        with tempfile.TemporaryDirectory() as td:
            self._tree(td)
            r = run("lint.py", td, "--json")
            data = json.loads(r.stdout)
            self.assertEqual(data["summary"], {"files": 3, "clean": 2, "with_findings": 1, "failed": 1})
            self.assertEqual([len(f["findings"]) for f in data["files"]], [0, 7, 0])

    def test_mixed_file_and_folder_and_unreadable(self):
        with tempfile.TemporaryDirectory() as td:
            self._tree(td)
            bad = os.path.join(td, "broken.excalidraw"); open(bad, "w").write("{not json")
            r = run("lint.py", os.path.join(EXAMPLES, "payment.excalidraw"), os.path.join(td, "nested"), bad)
            self.assertEqual(r.returncode, 1)
            self.assertIn("broken.excalidraw: error", r.stdout)
            self.assertIn("3 files, 2 clean", r.stdout)

    def test_single_file_output_is_unchanged(self):
        r = run("lint.py", os.path.join(EXAMPLES, "payment.excalidraw"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip().splitlines(), [os.path.join(EXAMPLES, "payment.excalidraw") + ": clean"])
        j = run("lint.py", os.path.join(EXAMPLES, "payment.excalidraw"), "--json")
        self.assertEqual(json.loads(j.stdout), [])


class TestExport(unittest.TestCase):
    def test_svg_export_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p.svg")
            r = run("export.py", os.path.join(EXAMPLES, "payment.excalidraw"), out, "--no-fonts")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(open(out, encoding="utf-8").read().startswith("<svg"))

    def test_build_svg_flag(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "o.excalidraw")
            r = run("build.py", os.path.join(EXAMPLES, "payment.spec.json"), out, "--svg")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(td, "o.svg")))


class TestHtmlExport(unittest.TestCase):
    """export.py --html: grouped SVG plus a self-contained page (#67)."""

    def _doc(self):
        with open(os.path.join(EXAMPLES, "payment.excalidraw"), encoding="utf-8") as f:
            return json.load(f)

    def test_plain_svg_has_no_groups(self):
        from preview import render_svg
        self.assertNotIn("<g ", render_svg(self._doc()))

    def test_grouped_svg_has_one_group_per_element(self):
        from preview import render_svg
        d = self._doc()
        svg = render_svg(d, groups=True)
        live = [e for e in d["elements"] if not e.get("isDeleted")]
        self.assertEqual(svg.count("<g "), len(live))
        self.assertEqual(svg.count("</g>"), len(live))
        for e in live:
            if e["type"] == "arrow" and e.get("startBinding") and e.get("endBinding"):
                self.assertIn(f'data-from="{e["startBinding"]["elementId"]}" data-to="{e["endBinding"]["elementId"]}"', svg)
        # a bound label points at its container; a box with a [bracketed] second line gets a tooltip
        self.assertIn('class="label" data-for="cache"', svg)
        self.assertIn('<g id="cache" class="box"><title>idempotency keys</title>', svg)
        self.assertIn('<g id="backend" class="region">', svg)

    def test_html_export_is_self_contained(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p.html")
            r = run("export.py", os.path.join(EXAMPLES, "payment.excalidraw"), out, "--no-fonts")
            self.assertEqual(r.returncode, 0, r.stderr)
            h = open(out, encoding="utf-8").read()
            self.assertTrue(h.startswith("<!doctype html>"))
            self.assertIn("<svg", h)
            self.assertIn("@keyframes flow", h)
            self.assertIn("[data-bidirectional] .line{animation-direction:alternate", h)
            self.assertIsNone(re.search(r'<(script|link|img)[^>]+(src|href)="https?://', h), "page must not load from the network")
            self.assertIn('id="paths" type="application/json">{}</script>', h)

    def test_build_html_with_flow_tooltip_and_paths(self):
        spec = {"paths": {"checkout": ["a", "b"]}, "elements": [
            {"id": "a", "type": "box", "label": "app", "x": 0, "y": 0, "fill": "grey", "tooltip": "ios and android"},
            {"id": "b", "type": "box", "label": "api\n[rest]", "x": 400, "y": 0},
            {"type": "arrow", "from": "a", "to": "b", "label": "https"},
            {"type": "arrow", "from": "b", "to": "a", "flow": False, "bend": 160},
        ]}
        with tempfile.TemporaryDirectory() as td:
            sp = os.path.join(td, "s.json"); out = os.path.join(td, "o.excalidraw")
            json.dump(spec, open(sp, "w", encoding="utf-8"))
            r = run("build.py", sp, out, "--html")
            self.assertEqual(r.returncode, 0, r.stderr)
            d = json.load(open(out, encoding="utf-8"))
            custom = [(e["type"], e["customData"]) for e in d["elements"] if e.get("customData")]
            self.assertEqual(custom, [("rectangle", {"tooltip": "ios and android"}), ("arrow", {"flow": False})])
            h = open(os.path.join(td, "o.html"), encoding="utf-8").read()
            self.assertEqual(h.count('data-flow="off"'), 1)
            self.assertIn("<title>ios and android</title>", h)
            self.assertIn("<title>rest</title>", h)
            self.assertIn('{"checkout": ["a", "b"]}', h)

    def test_bad_paths_are_refused(self):
        spec = {"paths": {"x": ["only-one"]}, "elements": [{"id": "a", "type": "box", "label": "a", "x": 0, "y": 0}]}
        with tempfile.TemporaryDirectory() as td:
            sp = os.path.join(td, "s.json")
            json.dump(spec, open(sp, "w", encoding="utf-8"))
            r = run("build.py", sp, os.path.join(td, "o.excalidraw"), "--html")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("paths must be", r.stderr)


class TestExploreMode(unittest.TestCase):
    """HTML export explore mode: play from any box, pause at forks (#77)."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.page = os.path.join(cls.td.name, "payment.html")
        r = run("build.py", os.path.join(EXAMPLES, "payment.spec.json"), os.path.join(cls.td.name, "payment.excalidraw"), "--html")
        assert r.returncode == 0, r.stderr
        cls.html = open(cls.page, encoding="utf-8").read()

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_page_ships_explore_mode(self):
        for needle in (".arrow.choice", "function explore(", "function outgoing(", "data-bidirectional", "q.get('explore')",
                       "e.key==='Escape'", ".badges", "KEYS='ABCDEFGHIJKLMNOPQRSTUVWXYZ'"):
            self.assertIn(needle, self.html, needle)

    def _dom(self, query):
        import export
        chrome = export.find_chrome()
        if not chrome:
            self.skipTest("no Chrome/Chromium to run the page")
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={os.path.join(td, 'p')}",
                                "--virtual-time-budget=6000", "--dump-dom", "file://" + self.page + query],
                               capture_output=True, text=True, timeout=120)
        return r.stdout

    def test_walk_pauses_at_the_fork_with_numbered_badges(self):
        dom = self._dom("?explore=app")
        # app -> gw -> pay are walked on their own; pay has three outgoing arrows, so the walk waits there
        self.assertEqual(dom.count('class="arrow done"'), 2, "two single-exit steps completed")
        self.assertEqual(dom.count('class="arrow choice"'), 3, "three candidates at the payment service")
        self.assertEqual(dom.count("<circle cx="), 3, "one badge per candidate")
        self.assertIn("3 ways out of payment service: pick A, B, C (click or type the letter)", dom)
        self.assertEqual(re.findall(r'<text x="[\d.]+" y="[\d.]+">([A-Z])</text>', dom.split('class="badges"', 1)[1]), ["A", "B", "C"],
                         "badges are lettered, not numbered: they are choices, not steps")
        self.assertIn("playing", dom.split("<svg", 1)[1][:400], "the rest of the diagram is faded while walking")

    def test_walk_from_a_dead_end_finishes_cleanly(self):
        dom = self._dom("?explore=db")
        self.assertEqual(dom.count('class="arrow choice"'), 0)
        self.assertEqual(dom.count('class="arrow step"'), 0)
        self.assertNotIn("playing", dom.split("<svg", 1)[1][:400], "finished walks release the page")



    def test_svg_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p.svg")
            r = run("preview.py", os.path.join(EXAMPLES, "payment.excalidraw"), out, "--square")
            self.assertEqual(r.returncode, 0, r.stderr)
            svg = open(out, encoding="utf-8").read()
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("textLength", svg)


class TestDoctor(unittest.TestCase):
    """doctor.py: report what is missing, exit 1 only for what build/lint/SVG need (#29)."""

    def doctor(self, **env):
        with tempfile.TemporaryDirectory() as home:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("PRETTIER_EXCALIDRAW_ICONS", "PRETTIER_EXCALIDRAW_STYLE")}
            e.update(HOME=home, USERPROFILE=home)  # an empty font cache
            e.update(env)
            return subprocess.run([sys.executable, os.path.join(SCRIPTS, "doctor.py")],
                                  capture_output=True, text=True, cwd=SCRIPTS, env=e)

    def test_clean_environment_is_ready(self):
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("ok    Python 3.", out)
        self.assertIn("Chrome/Chromium/Edge:", out)
        # empty cache: a warning with a hint, not a failure
        self.assertIn("warn  font cache: no Comic Shanns / Nunito", out)
        self.assertIn("PRETTIER_EXCALIDRAW_ICONS: not set", out)
        self.assertIn("PRETTIER_EXCALIDRAW_STYLE: not set", out)
        self.assertTrue(out.rstrip().endswith("ready"), out)

    def test_bad_style_and_icons_fail_with_hints(self):
        with tempfile.TemporaryDirectory() as td:
            missing = os.path.join(td, "nope")
            r = self.doctor(PRETTIER_EXCALIDRAW_STYLE=os.path.join(td, "style.json"),
                            PRETTIER_EXCALIDRAW_ICONS=os.pathsep.join([td, missing]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL  PRETTIER_EXCALIDRAW_STYLE: no such file", r.stdout)
        self.assertIn("FAIL  PRETTIER_EXCALIDRAW_ICONS: not a folder: " + missing, r.stdout)
        self.assertEqual(r.stdout.count("      -> "), r.stdout.count("FAIL") + r.stdout.count("warn"))

    def test_style_that_is_not_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            style = os.path.join(td, "style.json")
            with open(style, "w", encoding="utf-8") as f:
                f.write("not json")
            r = self.doctor(PRETTIER_EXCALIDRAW_STYLE=style)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot read", r.stdout)

    def test_good_style_icons_and_fonts_are_ok(self):
        import export
        with tempfile.TemporaryDirectory() as td:
            style = os.path.join(td, "style.json")
            with open(style, "w", encoding="utf-8") as f:
                json.dump({"name": "mine"}, f)
            cache = os.path.join(td, ".cache", "prettier-excalidraw", "fonts")
            for folder in export.FONT_DIRS.values():
                os.makedirs(os.path.join(cache, folder))
                open(os.path.join(cache, folder, "x.woff2"), "wb").close()
            r = self.doctor(PRETTIER_EXCALIDRAW_STYLE=style, PRETTIER_EXCALIDRAW_ICONS=EXAMPLES,
                            HOME=td, USERPROFILE=td)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok    font cache:", r.stdout)
        self.assertIn("ok    PRETTIER_EXCALIDRAW_STYLE: " + style, r.stdout)
        self.assertIn("ok    PRETTIER_EXCALIDRAW_ICONS: " + EXAMPLES, r.stdout)


if __name__ == "__main__":
    unittest.main()

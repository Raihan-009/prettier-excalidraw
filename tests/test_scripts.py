"""Tests for the prettier-excalidraw scripts. Standard library only.

Run:  python3 -m unittest discover -s tests -v
"""
import copy, glob, json, os, subprocess, sys, tempfile, unittest

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
        self.assertLess(len(text.splitlines()), 200, "SKILL.md should stay short")

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


class TestPreview(unittest.TestCase):
    def test_svg_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p.svg")
            r = run("preview.py", os.path.join(EXAMPLES, "payment.excalidraw"), out, "--square")
            self.assertEqual(r.returncode, 0, r.stderr)
            svg = open(out, encoding="utf-8").read()
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("textLength", svg)


if __name__ == "__main__":
    unittest.main()

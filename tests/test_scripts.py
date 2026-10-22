"""Tests for the prettier-excalidraw scripts. Standard library only.

Run:  python3 -m unittest discover -s tests -v
"""
import copy, glob, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "prettier-excalidraw")
SCRIPTS = os.path.join(SKILL, "scripts")
EXAMPLES = os.path.join(SKILL, "assets", "examples")
sys.path.insert(0, SCRIPTS)

import build, exstyle, fix, lint, preview  # noqa: E402


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True, cwd=SCRIPTS)


class TestSkillLayout(unittest.TestCase):
    def test_frontmatter(self):
        text = open(os.path.join(SKILL, "SKILL.md")).read()
        self.assertTrue(text.startswith("---\n"))
        head = text.split("---")[1]
        self.assertIn("name: prettier-excalidraw", head)
        self.assertIn("description:", head)
        self.assertLess(len(text.splitlines()), 200, "SKILL.md should stay short")

    def test_every_lint_rule_is_documented(self):
        guide = open(os.path.join(SKILL, "references", "style-guide.md")).read()
        src = open(os.path.join(SCRIPTS, "lint.py")).read()
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
                    doc = json.load(open(out))
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
            els = json.load(open(out))["elements"]
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
        self.doc = json.load(open(self.src))

    def tearDown(self):
        self.td.cleanup()

    def _save(self, doc, name="bad.excalidraw"):
        p = os.path.join(self.td.name, name)
        json.dump(doc, open(p, "w"))
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


class TestLintCli(unittest.TestCase):
    def test_allow_manual_exit_code(self):
        ref = os.path.join(EXAMPLES, "layered-architecture.excalidraw")
        self.assertEqual(run("lint.py", ref).returncode, 1, "reference has manual findings")
        self.assertEqual(run("lint.py", ref, "--allow-manual").returncode, 0)
        self.assertEqual(run("lint.py", os.path.join(EXAMPLES, "payment.excalidraw")).returncode, 0)


class TestPreview(unittest.TestCase):
    def test_svg_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "p.svg")
            r = run("preview.py", os.path.join(EXAMPLES, "payment.excalidraw"), out, "--square")
            self.assertEqual(r.returncode, 0, r.stderr)
            svg = open(out).read()
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("textLength", svg)

    def test_png_prefers_chrome_and_keeps_wide_canvas(self):
        with tempfile.TemporaryDirectory(prefix="preview test ") as td:
            src = Path(td) / "wide.excalidraw"
            src.write_text(json.dumps({"elements": [{"type": "rectangle", "x": 0, "y": 0,
                                                    "width": 1000, "height": 100}]}))
            out = Path(td) / "out.png"

            def chrome_run(command, **kwargs):
                svg = ET.fromstring(Path(unquote(urlparse(command[-1]).path)).read_text())
                self.assertEqual((float(svg.get("width")), float(svg.get("height"))), (1080, 180))
                self.assertIn("--window-size=1080,180", command)
                self.assertIn("--force-device-scale-factor=2", command)
                screenshot = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--screenshot="))
                Path(screenshot).write_bytes(b"png from chrome")

            with mock.patch.object(preview, "find_chrome", return_value="/chrome path/chrome"), \
                    mock.patch.object(preview.subprocess, "run", side_effect=chrome_run) as run_mock:
                preview.render_png(src, out)
            self.assertEqual(out.read_bytes(), b"png from chrome")
            self.assertEqual(run_mock.call_args.args[0][0], "/chrome path/chrome")

    def test_quicklook_pads_wide_and_tall_canvases(self):
        for width, height in ((1000, 100), (100, 1000)):
            with self.subTest(width=width, height=height), tempfile.TemporaryDirectory() as td:
                src = Path(td) / "diagram.excalidraw"
                src.write_text(json.dumps({"elements": [{"type": "rectangle", "x": 0, "y": 0,
                                                        "width": width, "height": height}]}))
                out = Path(td) / "out.png"

                def quicklook_run(command, **kwargs):
                    self.assertEqual(command[:4], ["/usr/bin/qlmanage", "-t", "-s", "2400"])
                    svg = ET.fromstring(Path(command[-1]).read_text())
                    self.assertEqual((float(svg.get("width")), float(svg.get("height"))), (1080, 1080))
                    x, y, w, h = map(float, svg.get("viewBox").split())
                    self.assertEqual((x + w / 2, y + h / 2), (width / 2, height / 2))
                    Path(command[-1] + ".png").write_bytes(b"png from quicklook")

                with mock.patch.object(preview, "find_chrome", return_value=None), \
                        mock.patch.object(preview.sys, "platform", "darwin"), \
                        mock.patch.object(preview.shutil, "which", return_value="/usr/bin/qlmanage"), \
                        mock.patch.object(preview.subprocess, "run", side_effect=quicklook_run):
                    preview.render_png(src, out)
                self.assertEqual(out.read_bytes(), b"png from quicklook")

    def test_png_without_renderer_reports_requirement(self):
        with mock.patch.object(preview, "find_chrome", return_value=None), \
                mock.patch.object(preview.sys, "platform", "linux"):
            with self.assertRaisesRegex(RuntimeError, "Chrome/Chromium"):
                preview.render_png("unused.excalidraw", "unused.png")

    def test_failed_renderer_keeps_existing_output(self):
        for result in (None, subprocess.CalledProcessError(1, "chrome"),
                       subprocess.TimeoutExpired("chrome", 60)):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as td:
                out = Path(td) / "out.png"
                out.write_bytes(b"previous preview")
                with mock.patch.object(preview, "find_chrome", return_value="chrome"), \
                        mock.patch.object(preview.subprocess, "run", side_effect=result):
                    with self.assertRaises((RuntimeError, subprocess.SubprocessError)):
                        preview.render_png(os.path.join(EXAMPLES, "payment.excalidraw"), out)
                self.assertEqual(out.read_bytes(), b"previous preview")

    def test_plain_svg_keeps_original_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "wide.excalidraw"
            src.write_text(json.dumps({"elements": [{"type": "rectangle", "x": 0, "y": 0,
                                                    "width": 1000, "height": 100}]}))
            out = Path(td) / "out.svg"
            r = run("preview.py", str(src), str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            svg = ET.fromstring(out.read_text())
            self.assertEqual((float(svg.get("width")), float(svg.get("height"))), (1080, 180))


if __name__ == "__main__":
    unittest.main()

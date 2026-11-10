"""Golden tests for the diagrams built from the example specs."""
import difflib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "prettier-excalidraw" / "scripts"
EXAMPLES = ROOT / "skills" / "prettier-excalidraw" / "assets" / "examples"
GOLDEN = ROOT / "tests" / "golden"
FIELDS = (
    "type", "id", "x", "y", "width", "height", "text", "strokeColor",
    "backgroundColor", "fontFamily", "fontSize", "endArrowhead", "points",
    "containerId",
)


def specs():
    return sorted(EXAMPLES.glob("*.spec.json"))


def snapshot_path(spec):
    return GOLDEN / (spec.name.removesuffix(".spec.json") + ".json")


def build_snapshot(spec):
    spec_data = json.loads(spec.read_text(encoding="utf-8"))
    known_ids = {item["id"] for item in spec_data["elements"] if "id" in item}
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "out.excalidraw"
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), str(spec), str(output)],
            capture_output=True, text=True, encoding="utf-8", cwd=SCRIPTS,
        )
        if result.returncode:
            raise RuntimeError(f"Build failed for {spec.name}:\n{result.stderr}")
        elements = json.loads(output.read_text(encoding="utf-8"))["elements"]
    projected = []
    for element in elements:
        projected.append({
            field: element[field] for field in FIELDS
            if field in element and (
                field not in ("id", "containerId")
                or element[field] is None or element[field] in known_ids
            )
        })
    return json.dumps(projected, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class TestGoldenExamples(unittest.TestCase):
    def test_example_snapshots(self):
        examples = specs()
        self.assertTrue(examples, "No example specs found")
        for spec in examples:
            with self.subTest(spec=spec.name):
                path = snapshot_path(spec)
                self.assertTrue(path.is_file(), f"Missing snapshot: {path}")
                expected = path.read_text(encoding="utf-8")
                actual = build_snapshot(spec)
                diff = "".join(difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=str(path), tofile=f"built/{spec.name}",
                ))
                self.assertEqual(expected, actual, f"Snapshot differs:\n{diff}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for example in specs():
            path = snapshot_path(example)
            with path.open("w", encoding="utf-8", newline="\n") as snapshot:
                snapshot.write(build_snapshot(example))
            print(f"Updated {path.relative_to(ROOT)}")
    else:
        unittest.main()

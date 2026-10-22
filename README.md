# prettier-excalidraw

A [Claude Code](https://claude.com/claude-code) skill that makes Excalidraw
architecture diagrams look like one careful person drew them: no sketchy lines,
one font, one arrow style, a small palette of light fills that mean something,
regions that contain their children, logos sized to their boxes, and arrows that
are never hidden behind a box.

![platform diagram](skills/prettier-excalidraw/assets/examples/platform.png)

Ask for a diagram in plain language and get a `.excalidraw` file that opens in
[excalidraw.com](https://excalidraw.com), Obsidian or VS Code and is already
consistent. Point it at an existing diagram and it normalises the style without
moving anything.

## What it does

| You say | The skill does |
|---|---|
| "draw an excalidraw diagram of X" | Asks about anything the prompt leaves open (who uses that database?), writes a spec, builds the file, previews it, lints it, delivers it with a colour key |
| "make this .excalidraw consistent / prettier" | `lint` → `fix` → `lint`, then tells you what still needs a human |
| "does this follow the style?" | Runs the linter and explains each finding |

The style was derived by measuring a set of real diagrams (839 elements) rather
than invented, so the rules have numbers behind them. See
[the style guide](skills/prettier-excalidraw/references/style-guide.md). Prefer your
own style? `profile.py` measures a folder of your diagrams and writes a profile the
scripts use instead.

## Install

Inside Claude Code:

```
/plugin marketplace add Raihan-009/prettier-excalidraw
/plugin install prettier-excalidraw@prettier-excalidraw
```

Or as a plain skill, no plugin system:

```bash
git clone https://github.com/Raihan-009/prettier-excalidraw.git
ln -s "$PWD/prettier-excalidraw/skills/prettier-excalidraw" ~/.claude/skills/prettier-excalidraw
```

Requirements: Python 3.10+. The scripts use the standard library only. Point the
skill at your own logo folder with `PRETTIER_EXCALIDRAW_ICONS=/path/to/icons` (or
`"icons_dir"` in a spec) and it matches icons to labels by name; otherwise logos are
fetched from [Simple Icons](https://simpleicons.org).

## Try it

```
draw an excalidraw architecture diagram: mobile app -> api gateway -> payment
service -> stripe, with a postgres db and a redis cache. save as payment.excalidraw
```

The skill will ask who owns the two stores and whether Stripe calls back, then
produce this:

![payment diagram](skills/prettier-excalidraw/assets/examples/payment.png)

## The style, in one screen

| | |
|---|---|
| Lines | roughness 0, stroke `#1e1e1e`, width 2, sharp corners |
| Text | Comic Shanns (or Nunito), sizes 16 / 20 / 28, lowercase, `[secondary info]` in brackets |
| Boxes | light fills with meaning: blue service · yellow runtime · green gateway · red store · purple control plane · orange external · teal kubernetes · cyan interface · grey user |
| Regions | one-scale-lighter tints or transparent, bracketed title inside |
| Arrows | elbowed, bound to both ends, hollow triangle head; red = blocked, green = allowed, blue = info |
| Icons | real logos, 65–95 % of the box height, never stretched |
| Z-order | regions → boxes → labels and icons → arrows last |

## Scripts

All in `skills/prettier-excalidraw/scripts/`, run from that directory.

| Script | Purpose |
|---|---|
| `build.py spec.json out.excalidraw` | JSON spec → diagram. Handles bound labels, elbow routing, bindings, icon embedding, z-order |
| `lint.py file.excalidraw` | 15 style checks with element ids. `--font nunito`, `--arrowhead filled`, `--json` |
| `fix.py in out` | Mechanical fixes: font, sizes, roughness, fills, corners, heads, z-order. Never moves anything |
| `preview.py file out.svg [--square]` | SVG render with exact text widths, for checking layout without Excalidraw |
| `profile.py folder -o style.json` | Measure your own diagrams and write a style profile; pass `--style style.json` to the other scripts to use it instead of the house style |
| `export.py file out.png\|out.svg [--scale 2]` | Shareable image with the real fonts embedded; Chrome or macOS quick-look for PNG. `build.py ... --png` does it in one step |

The spec format is documented in
[spec-format.md](skills/prettier-excalidraw/references/spec-format.md). A full
example:

```json
{
  "elements": [
    {"id":"k8s","type":"region","title":"[ kubernetes cluster ]","x":0,"y":0,"w":900,"h":400,"tint":"teal"},
    {"id":"ingress","type":"box","label":"nginx ingress","icon":"icons/nginx.svg","x":40,"y":160,"fill":"green"},
    {"id":"orders","type":"box","label":"orders service","x":560,"y":60,"fill":"blue"},
    {"id":"db","type":"box","label":"postgres","icon":"icons/postgresql.svg","x":560,"y":300,"fill":"red"},
    {"type":"arrow","from":"ingress","to":"orders","label":"/orders"},
    {"type":"arrow","from":"orders","to":"db","label":"writes orders"}
  ]
}
```

## Examples

| File | Shows |
|---|---|
| [temporal](skills/prettier-excalidraw/assets/examples/temporal.spec.json) | nested regions, elbow arrows, labels, the worked example from the docs |
| [ecommerce](skills/prettier-excalidraw/assets/examples/ecommerce.spec.json) | cluster region, dotted group, semantic arrow colours, four logos |
| [platform](skills/prettier-excalidraw/assets/examples/platform.spec.json) | three stacked layers, nine logos, colour key |
| [payment](skills/prettier-excalidraw/assets/examples/payment.spec.json) | stores under their owner, webhook return arrow |
| [flowchart](skills/prettier-excalidraw/assets/examples/flowchart.spec.json) | diamond decision node and ellipse start/yes/no markers |
| [layered-architecture](skills/prettier-excalidraw/assets/examples/layered-architecture.excalidraw) | a hand-drawn reference diagram the style was measured from |

## Evaluation

Three prompts, each run by a fresh Claude with and without the skill, scored on
objective checks (one font, consistent arrowheads, no hidden arrows, containers
before children, light fills, logos present, correct grouping):

| | With skill | Without |
|---|---|---|
| Checks passed | 28 / 28 | 21 / 26 |

Details in [evals/](evals/).

## Development

```bash
python3 -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes are tracked in
[CHANGELOG.md](CHANGELOG.md); planned work is in [ROADMAP.md](ROADMAP.md).

## License

MIT. Logos are the property of their respective owners; the SVGs in
`assets/examples/icons` come from Simple Icons (CC0).

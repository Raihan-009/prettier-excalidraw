# prettier-excalidraw

A [Claude Code](https://claude.com/claude-code) skill that makes Excalidraw
architecture diagrams look like one careful person drew them: no sketchy lines,
one font, one arrow style, a small palette of light fills that mean something,
regions that contain their children, logos sized to their boxes, and arrows that
are never hidden behind a box.

![the same spec built with default Excalidraw settings (left) and with prettier-excalidraw (right)](docs/before-after.png)

*The same spec, built with default Excalidraw settings (left) and with the skill (right).*

Ask for a diagram in plain language and get a `.excalidraw` file that opens in
[excalidraw.com](https://excalidraw.com), Obsidian or VS Code and is already
consistent. Point it at an existing diagram and it normalises the style without
moving anything.

## Features

| Feature | What you get |
|---|---|
| **Generate** a diagram from a sentence | A `.excalidraw` file in the house style: boxes, regions, elbow arrows, bound labels, real logos, correct z-order, a colour key. The skill asks about anything the prompt leaves open (who owns the database? does Stripe call back?) before drawing |
| **Replicate** a diagram from a picture | Paste a screenshot or vendor diagram; it is read with a fixed checklist, rebuilt in your style, and delivered with a note listing what was renamed, merged or dropped |
| **Restyle** an existing file | `lint → fix → lint` on any `.excalidraw`: font, sizes, roughness, fills, corners, arrowheads and z-order are corrected without moving a single shape, then you are told what still needs a human |
| **Lint** against the style | 24 checks with element ids, from "wrong font" to "arrow hidden behind a box" and "text sitting on a region edge"; `--json` for tooling, exit code for CI |
| **Guard a whole folder** | `lint.py docs/diagrams/` checks every diagram under a folder with a per-file summary, and a reusable GitHub Action does it on every pull request, so a team's diagrams stay consistent, not just one person's |
| **Export** PNG or SVG | `--png` / `--svg` at build time or `export.py` on any file; the real Comic Shanns / Nunito fonts are embedded, so the image matches Excalidraw exactly |
| **Animated HTML page** | `--html` writes one self-contained page from the same SVG: arrows flow in their direction, hovering a shape lights up its connections, a button plays a named request path one arrow at a time, linked shapes open on click |
| **Explore mode** | On the same page, click any box to play forward from it along the drawing's own arrows; at a fork the walk pauses, letters the ways out A, B, C, and the reader picks one. Nothing to write in the spec; `?explore=<id>` deep-links a start |
| **Shapes** beyond boxes | `diamond` decisions, `ellipse` start/end/actor markers, `note` captions, `divider` lines, `group`s that move together, dashed boxes and arrows, bidirectional arrows |
| **Real logos**, sized right | Icons matched to labels by name from your own folder or fetched from [Simple Icons](https://simpleicons.org) with the brand colour; scaled to 65–95 % of the box, never stretched, darkened automatically when the contrast on a fill is too low |
| **Your own style** | `profile.py` measures a folder of your diagrams (font, sizes, fills, arrow colours...) and writes a profile every script accepts in place of the house style |
| **Layout direction** | `"layout": "lr"` or `"tb"` on a spec; full auto-layout (no coordinates at all) is in progress, see [#9](https://github.com/Raihan-009/prettier-excalidraw/issues/9) |

![the animated HTML export: arrows flow, hovering the payment service lights up its connections, and the checkout path plays one arrow at a time](docs/animated-export.gif)

*`build.py payment.spec.json payment.excalidraw --html`: arrows flow, hover shows a shape's connections, a button plays a named path.*

![explore mode paused at a fork: the payment service has three ways out, lettered A, B and C, and the toolbar asks the reader to pick one](docs/explore-fork.png)

*Explore mode on the same page: play from any box, pause at a fork, pick a branch.*

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

## Usage

Everything below is a prompt to Claude Code once the skill is installed. The skill
triggers on "excalidraw" plus a verb; you do not need to name it.

```
draw an excalidraw diagram of our checkout: web app -> api gateway -> orders
service -> postgres, with a kafka topic for order events. save as checkout.excalidraw
```

```
redo this diagram in our excalidraw style, excalidraw plus png     (attach the image)
```

```
make payment.excalidraw consistent with the style guide
```

```
does infra.excalidraw follow the excalidraw style? list the findings
```

```
export checkout.excalidraw as a png at 2x
```

```
make an animated html page of checkout.excalidraw that plays the order flow
```

```
use the logos in ./brand-icons for this excalidraw diagram
```

```
measure my diagrams in ~/diagrams and use that style instead of the house style
```

Each of these maps to one or two of the scripts below, which you can also run by hand.

### Keep a team's diagrams consistent

Point the linter at a folder and it checks every `.excalidraw` under it:

```
$ python3 lint.py docs/diagrams/
docs/diagrams/checkout.excalidraw: clean
docs/diagrams/legacy/billing.excalidraw: 3 findings (1 manual)
docs/diagrams/platform.excalidraw: clean
...
3 files, 2 clean, 1 with findings
```

To run that on every pull request in your own repository, add one job:

```yaml
jobs:
  diagrams:
    uses: Raihan-009/prettier-excalidraw/.github/workflows/lint-diagrams.yml@main
    with:
      paths: docs/diagrams
```

Optional inputs: `allow-manual: true` (hand-drawn files with known manual findings
only warn), `style: style.json` (your own profile), `ref: v0.6.0` (pin the linter).

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
| `lint.py file.excalidraw \| folder/ ...` | 24 style checks with element ids; a folder is searched recursively and summarised per file. `--font nunito`, `--arrowhead filled`, `--json`, `--quiet`, `--allow-manual` for CI gates on hand-drawn files |
| `fix.py in out` | Mechanical fixes: font, sizes, roughness, fills, corners, heads, z-order. Never moves anything |
| `preview.py file out.svg [--square]` | SVG render with exact text widths, for checking layout without Excalidraw |
| `profile.py folder -o style.json` | Measure your own diagrams and write a style profile; pass `--style style.json` to the other scripts to use it instead of the house style |
| `export.py file out.png\|out.svg\|out.html [--scale 2] [--spec spec.json]` | Shareable image with the real fonts embedded; Chrome or macOS quick-look for PNG. `.html` is a self-contained animated page (flow, hover, play, explore). `build.py ... --png` / `--html` does it in one step |
| `icons.py search fly` / `icons.py fetch postgresql apachekafka -o icons/` | Find and download brand logos from Simple Icons with the brand colour applied |
| `doctor.py` | Check the environment (Python 3.10+, Chrome for PNG, font cache, `PRETTIER_EXCALIDRAW_ICONS` / `PRETTIER_EXCALIDRAW_STYLE`, quick-look on macOS) and print a hint for anything missing; exit 1 when build, lint or SVG export would fail |

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

![platform diagram](skills/prettier-excalidraw/assets/examples/platform.png)

| File | Shows |
|---|---|
| [temporal](skills/prettier-excalidraw/assets/examples/temporal.spec.json) | nested regions, elbow arrows, labels, the worked example from the docs |
| [ecommerce](skills/prettier-excalidraw/assets/examples/ecommerce.spec.json) | cluster region, dotted group, semantic arrow colours, four logos |
| [platform](skills/prettier-excalidraw/assets/examples/platform.spec.json) | three stacked layers, nine logos, colour key |
| [payment](skills/prettier-excalidraw/assets/examples/payment.spec.json) | stores under their owner, webhook return arrow |
| [flowchart](skills/prettier-excalidraw/assets/examples/flowchart.spec.json) | diamond decision node and ellipse start/yes/no markers |
| [clickstream](skills/prettier-excalidraw/assets/examples/clickstream.spec.json) | a vendor-style picture ([source](docs/examples/source-clickstream.png)) rebuilt in house style; [how it was read](docs/examples/clickstream-notes.md) |
| [netns](skills/prettier-excalidraw/assets/examples/netns.spec.json) | a Linux network-namespace tutorial picture rebuilt in house style: nested regions, a note box, double-headed arrows, no logos; [how it was read](docs/examples/netns-notes.md) |
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

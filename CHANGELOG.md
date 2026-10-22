# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
See [ROADMAP.md](ROADMAP.md).

## [0.3.0] - 2026-10-22

### Added
- `build.py`: `diamond` decision nodes and `ellipse` start/end/actor markers with
  bound centred labels, palette fills, and the same arrow bindings / z-order as
  boxes; example flowchart in `assets/examples/` (#36).

- `export.py`: SVG or PNG export of any diagram with the real fonts embedded,
  rasterised by Chrome or macOS quick-look; `build.py --png` / `--svg` write the
  image next to the `.excalidraw` file (roadmap 1.1, #15).

- `lint.py`: `box-overlap` - two component boxes intersecting (#3);
  `icon-low-contrast` - SVG icon colour below 3:1 on its box fill (#11).
- `build.py`: an SVG icon whose brand colour has less than 3:1 contrast on the box
  fill is darkened automatically; `icon_color` forces a hex or `keep` (#11).
- `build.py`: user icon folders. `"icons_dir"` in the spec or
  `PRETTIER_EXCALIDRAW_ICONS`; `"icon": "PostgreSQL"` looks a name up by slug and
  `"icon": "auto"` matches the label, leaving the box bare when nothing fits (#20).

- `profile.py`: derive a style profile from any folder of diagrams; `build.py`,
  `lint.py` and `fix.py` take `--style style.json` (or `PRETTIER_EXCALIDRAW_STYLE`,
  or `"style"` in the spec) so every default, rule and palette name comes from it (#19).

- `icons.py`: `search` and `fetch` for Simple Icons; falls back to the npm mirror
  when the CDN blocks non-browser clients and applies the brand colour.
- Regions take an `icon` (provider logo in the corner opposite the title).
- `lint.py`: `text-behind-box` (free text hidden under a later filled box; `fix.py`
  moves it up); `arrow-through-box` ignores a box that contains the arrow's endpoint;
  `--help` works.

### Verified
- Elbowed bound arrows re-route and bound labels stay centred when boxes are
  dragged and resized in Excalidraw (manual check by the author).

### Fixed
- Icon file errors name the box or image that uses the file and tolerate a UTF-8
  BOM (from #23 by @O1sumitkumar); `export.py` runs Chrome with a throwaway
  profile and a timeout (from #24 by @tedy69); icon fills accept 8-digit hex and
  single quotes (from #25 by @dbdefault); stronger nonce test (from #22 by
  @HarshRajSinghania).
- `lint.py` no longer flags `no-arrowhead` on the first half of a split branch
  arrow (diamond → "yes" circle → target) (#4).
- `build.py` refuses empty, missing or mis-typed icon files instead of embedding
  a broken image (#1).
- `fix.py` refreshes `versionNonce` along with `version` so collaborative
  sessions pick up the change (#2).

## [0.2.0] - 2026-10-22

### Added
- `build.py`: `subtitle` on regions (note in the corner opposite the title);
  warning when an icon has to shrink below 65 % of its box height.
- `fix.py`: prints `check label:` for any text whose size changed by 4 px or more.
- `SKILL.md`: gap-filling step - ask about store owners, edge direction,
  boundaries and callbacks before drawing, or state the assumption.
- `lint.py`: `misleading-proximity` - a store sitting under a box it has no
  arrow to; `arrow-through-text`, `arrow-through-box`, `arrow-overlap`,
  `text-overlap`, `text-over-box` - layout collisions the eye catches but the
  old rules did not.
- `build.py`: `bend` on arrows to choose where the middle segment runs, so two
  arrows between the same rows do not share a line.
- `preview.py`: `--square` for quick-look thumbnails; exact text widths.

### Changed
- `fix.py` re-measures text boxes and re-centres bound labels after a font or
  size change, so Excalidraw no longer shows stale, off-centre labels.
- `build.py` widens boxes to the next multiple of 20 px instead of an arbitrary
  width; same-side arrows (bottom→bottom, right→right) loop out 40 px instead of
  running along the box edges.
- `fix.py` keeps the left edge of a caption whose size changes drastically, so
  it stays beside the icon it belonged to.
- `build.py` rounds heightened boxes to the 20 px grid; `preview.py` prints
  usage instead of a traceback.
- Chrome recipe listed first for PNG previews, with the device scale factor.
- Example specs widened so every icon stays at full size; arrows re-routed so
  none crosses a region title.

## [0.1.0] - 2026-10-22

### Added
- `SKILL.md` with generate / restyle / check workflows and the reasoning behind
  each style rule, including a gap-filling step for under-specified prompts.
- `scripts/build.py`: JSON spec to `.excalidraw`, handling bound labels, elbowed
  bound arrows, embedded icons, same-side arrow loops and z-order.
- `scripts/lint.py`: 14 style rules including hidden arrows, child-before-parent
  z-order, icon sizing and misleading store placement.
- `scripts/fix.py`: mechanical fixes for font, size, roughness, fills, corners,
  arrowheads and z-order without moving anything.
- `scripts/preview.py`: SVG preview with exact text widths and a `--square` mode
  for quick-look thumbnails.
- Style guide and spec format references; five worked examples with specs.
- Eval set (3 cases) and grader; CI running the unit tests.

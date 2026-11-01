# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `doctor.py` checks the environment and says what is missing (#29): Python 3.10+,
  Chrome/Chromium/Edge for PNG export, the font cache, `PRETTIER_EXCALIDRAW_ICONS` and
  `PRETTIER_EXCALIDRAW_STYLE` when set, and quick-look on macOS, with a one-line hint
  for each problem. Exit 1 only when build, lint or SVG export would fail.

### Planned
See [ROADMAP.md](ROADMAP.md).

## [0.8.0] - 2026-10-25

### Added
- Explore mode in the animated HTML export (#77). An **explore** button on the page:
  click any box and playback walks forward along the drawing's own arrows. A box
  with one way out is walked through; at a fork the candidate arrows glow with
  lettered badges (A, B, C are the ways out, not an order) and the walk waits for a
  click on an arrow, a badge or the target box, or the letter key. Visited arrows
  are not offered again, so loops end;
  double-headed arrows count both ways; Escape stops. `?explore=<id>` opens the
  page already walking from that shape. Named `paths` are unchanged.
- The animated page centres the drawing on screen, fitted to the window, on a white
  card, instead of pinning it to the top-left corner.

### Fixed
- Mixed diagrams, layer strips with a flow drawn across them, no longer run arrows
  through the strip titles (#10). A straight arrow that would cross a region title,
  subtitle or corner logo gets the same offset at both ends, a bent route moves its
  middle run past it, both on the 20 px grid, and `build.py` prints what it moved.
  Explicit `from_offset` / `to_offset` / `bend` are used as written. Arrow labels
  that would sit on a title or straddle a strip border move to the other side of
  the segment or along it. Arrows are now built after every shape, so a region
  listed after an arrow in the spec is still avoided.

## [0.7.0] - 2026-10-24

### Added
- `lint.py` takes directories and several paths (#65): every `.excalidraw` under a
  folder is checked recursively, with one summary line per file, the findings of
  the files that have any, a totals line, `--quiet`, and a `{"files", "summary"}`
  shape for `--json`. The exit code fails when any file has a blocking finding.
- Reusable GitHub workflow `.github/workflows/lint-diagrams.yml`: any repository
  can lint its diagrams folder on every pull request with one `uses:` line
  (inputs `paths`, `allow-manual`, `style`, `ref`). This repository's CI runs it
  against the shipped examples.

## [0.6.0] - 2026-10-24

### Added
- Animated HTML export (#67): `export.py diagram.excalidraw out.html` and
  `build.py --html` write one self-contained page from the same SVG, with arrows
  flowing in their direction, hover lighting a shape's connections, play buttons
  for named request paths, and linked shapes opening on click. `preview.render_svg`
  gains `groups=True` (one `<g>` per element with id, kind and arrow bindings; the
  plain output is unchanged). New spec keys `flow: false` (arrow), `tooltip`
  (shape) and top-level `paths`, stored as `customData` so the file stays valid.
- Second replicate-from-image worked example: `assets/examples/netns.*`, a Linux
  network-namespace tutorial picture rebuilt with nested regions, a note and
  double-headed arrows; extraction and changes note in
  `docs/examples/netns-notes.md`.
- README: a features table with one row per capability, a usage section with one
  prompt per job, and a GIF of the animated export; `payment.spec.json` names two
  `paths` so the page is reproducible from the repo.

### Fixed
- HTML export: double-headed arrows pulse back and forth instead of flowing in
  the direction they happened to be drawn.

## [0.5.0] - 2026-10-23

### Added
- Replicate a diagram from a shared image: `references/reading-a-diagram.md`
  (extraction checklist, mapping to the house style, what to drop, the
  "changes from the original" note) and a replicate workflow in SKILL.md; worked
  example `assets/examples/clickstream.*` rebuilt from
  `docs/examples/source-clickstream.png` (#16).
- Auto-layout foundation (#9): design note `scripts/layout/README.md` with the
  stage contracts, the shared graph model `layout/graph.py` (spec → nodes, edges,
  containers; explicit coordinates recorded as fixed), spec keys `layout` and
  `in`, and `tests/test_layout.py` with placeholders per stage.
- Auto-layout stage 1 (#48): `layout/rank.py` — longest-path ranks per
  container (sources at rank 0), cycles broken by dropping the back edge
  found last, isolated nodes at rank 0; `TestRank` tests in
  `tests/test_layout.py` (#63, @rahul05ranjan).
- Auto-layout stage 2 (#49): `layout/order.py` — barycentre sweeps (down
  then up) order each rank, keeping the candidate with the fewest edge
  crossings (`crossings()` helper); `TestOrder` tests in `tests/test_layout.py`
  (#64, @rahul05ranjan).

### Changed
- SKILL.md description rewritten for triggering: leads with the condition
  ("deliverable is an Excalidraw file"), names the three jobs and the formats it
  is not for. Measured on a 20-query set: held-out 7/8 vs 6/8 before, no false
  triggers either way (#14).

## [0.4.0] - 2026-10-22

### Added
- `build.py`: `diamond` decision nodes and `ellipse` start/end/actor markers with
  bound centred labels, palette fills, and the same arrow bindings / z-order as
  boxes; flowchart example in `assets/examples/` (#36, @dbdefault).
- `build.py`: `note` element - lightgrey annotation box with left-aligned bound
  text (stroke 1, padding 12); `lint.py` ignores notes for `misleading-proximity`
  (#37, @dbdefault).
- `build.py`: `divider` lines (horizontal or vertical, optional dashed and label)
  and `group` elements that make listed members move together (#38, @dbdefault).

- Issue forms (bug, feature), a PR template with the test checklist, and
  `size:` / `area:` labels on every open issue (#26).

- `release` workflow: a pushed `vX.Y.Z` tag checks changelog and manifest versions,
  runs the tests, zips the skill and creates the GitHub release with the changelog
  section as notes; `tools/release_notes.py` runs the same check locally (#34).

- `lint.py`: `text-on-region-edge` for labels straddling a region border; SKILL.md
  gains the sizing and placement rules of thumb (box width, title inset, offsets,
  label placement) that iteration-3 test runs asked for.

- `lint.py`: equal-sized tiny cells in a regular row or column on a strip are a
  cell grid, not `box-overlap` collisions; the strip is their z-order parent
  (#54, @dbdefault).

## [0.3.0] - 2026-10-22

### Added
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

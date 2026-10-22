# Spec format for build.py

A spec is a JSON object. All coordinates are in Excalidraw canvas units (≈ px);
origin top-left, y grows downward. Lay things out on a 20 px grid.

```json
{
  "font": "comic",          // "comic" (Comic Shanns, default) | "nunito"
  "arrowhead": "outline",   // "outline" (hollow triangle, default) | "filled"
  "style": "style.json",    // optional: a style profile from profile.py (or --style on the CLI)
  "icons_dir": "icons",     // optional: folder(s) with the user's own icons, relative to the spec
  "elements": [ ... ]       // in any order; the builder sorts the z-order itself
}
```
Icon folders are searched in this order: `icons_dir` (a string or a list), then the
`PRETTIER_EXCALIDRAW_ICONS` environment variable (several folders separated by `:`).

## Element types

### region – a large container (cluster, VPC, layer, process boundary)
```json
{"id":"cluster","type":"region","x":0,"y":0,"w":1000,"h":420,
 "tint":"blue","title":"[ temporal server cluster ]","title_pos":"top-right"}
```
- `tint`: `blue | teal | yellow | orange | purple | red | none | white` (light region
  tints; `none` = transparent with a border, the most common choice)
- `title_pos`: `top-left` (default) | `top-right` | `top-center` | `bottom-center`
  (below the region). Title is free text, size 20 unless `size` given.
- `icon`: a logo (file, name in the icon folders, or Simple Icons slug fetched with
  `icons.py`) drawn 32 px in the corner opposite the title; `icon_h` changes the size.
- `subtitle`: a short note (size 16) in the top corner opposite the title, e.g.
  `"subtitle": "provisioned by the platform team"`.
- `dotted: true` → dotted 1 px border at 60 % opacity, for a loose logical group.
- `stroke_width`: default 2.

### box – a component with a bound label
```json
{"id":"db","type":"box","x":30,"y":250,"w":240,"h":70,
 "label":"postgres database","fill":"blue","icon":"icons/postgresql.svg"}
```
- `fill`: `blue | yellow | green | red | purple | orange | teal | cyan | grey |
  lightgrey | white | none` or a hex colour.
- `label` may contain `\n`; keep secondary info in `[brackets]` on line 2.
- `size`: font size 16 | 20 (default) | 28.
- `icon`: a file path relative to the spec (svg / png / jpg), **or** a name looked up
  in the icon folders (`"icon": "PostgreSQL"`), **or** `"auto"` to look up the first
  label line. Lookup is by slug (lowercase, letters and digits only), exact first,
  then a unique prefix match, so `"postgres"` finds `PostgreSQL.svg`. A named icon
  that is not found stops the build; `auto` just leaves the box bare. An SVG whose brand
  colour has less than 3:1 contrast on the box fill is darkened automatically (a
  warning says so); `icon_color: "#hex"` forces a colour, `icon_color: "keep"` leaves
  the file untouched. Placed on the left at
  ~80 % of box height; the builder shrinks it to ≥ 56 % or widens the box so the
  centred label never overlaps it. `icon_h` overrides the height.
- `w` / `h` default 240 × 70. Labels get 16 px of padding each side; the builder
  enlarges a box that cannot fit its label (more than 4 px short) and prints a warning - treat warnings as a cue to adjust the layout.
- `dashed: true`, `stroke_width`.

### diamond – a decision node with a bound centred label
```json
{"id":"ok","type":"diamond","label":"is solution\navailable?","x":400,"y":100,
 "w":220,"h":120,"fill":"none"}
```
- Same `fill`, `size`, `dashed`, `stroke_width` as a box.
- `w` / `h` default 200 × 100. The builder enlarges the shape when the label does not fit.
- Arrows bind to the bounding-box sides; z-order matches boxes.

### ellipse – a start / end / actor marker with a bound centred label
```json
{"id":"start","type":"ellipse","label":"yes","x":700,"y":120,"w":80,"h":40,"fill":"green"}
```
- Same `fill`, `dashed`, `stroke_width` as a box. Default `size` is 16 so a one-line
  label fits the 80 × 40 default; pass `size: 20` for larger markers.
- `w` / `h` default 80 × 40. The builder enlarges the shape when the label does not fit.
- Arrows bind like boxes; z-order matches boxes. Flowchart markers are ignored by
  `box-overlap` and `misleading-proximity` (those rules look at component rectangles).

### image – a standalone logo or picture
```json
{"id":"k8s","type":"image","src":"icons/kubernetes.svg","x":1080,"y":60,"h":100,
 "label":"kubernetes"}
```
`src` is a path; alternatively `"icon": "kubernetes"` (or `"auto"` with a `label`)
resolves through the icon folders like a box icon. Give `h` or `w`; the other follows
the file's aspect ratio. `label` is centred
below. Can be an arrow target when it has an `id`.

### text – free-standing text
```json
{"type":"text","text":"Temporal architecture","x":0,"y":960,"size":28,
 "color":"black","align":"left"}
```
`color`: `black | red | green | blue` or hex.

### arrow – a connector between two ids
```json
{"type":"arrow","from":"queue","to":"worker1","label":"gRPC long-poll","color":"blue",
 "from_side":"bottom","to_side":"top","from_offset":40,"label_at":"start",
 "bidirectional":false,"dashed":false}
```
- `from` / `to`: ids of boxes, diamonds, ellipses, regions or images.
- `from_side` / `to_side`: `left | right | top | bottom`; omitted sides are chosen
  from the relative position of the two elements.
- `from_offset` / `to_offset`: shift the anchor along the side (px) so several
  arrows from one side do not overlap. Keep them equal for a straight arrow; unequal
  offsets add a jog near the target and shift the label.
- Arrows connect `id`s of boxes, regions, images, diamonds and ellipses only; free
  `text` cannot be an endpoint.
- Routing is orthogonal (elbowed). Same axis on both ends (left/right or top/bottom):
  straight when aligned, else two bends through the midpoint (or `bend`). Mixed
  (e.g. `top` → `left`): one bend; the arrow leaves along the start side's axis, turns
  once at the target's coordinate, and enters the target side (`top`→`left` goes up to
  the target's y, then right into its left side). Same side on both ends loops 40 px
  out and back. Arrows are bound to both ends so they follow the boxes in
  Excalidraw.
- `bend`: coordinate of the middle segment - the y of the horizontal run for
  top/bottom routes, the x of the vertical run for left/right routes. Use it when two
  arrows between the same rows would otherwise share a line (`lint.py` reports
  `arrow-overlap`).
- `label` sits above the longest horizontal segment or right of the longest vertical
  one; `label_at: "start" | "end"` moves it to the first / last segment.
- `color`: `black` (default) | `red` | `green` | `blue` | hex. The label takes the
  arrow's colour.

## Z-order produced
regions and shapes (box / diamond / ellipse) sorted by area (largest first, so
containers precede children, each followed by its bound label) → images → free text
→ arrows. You never need to order the spec by hand.

## Worked example
See `assets/examples/temporal.spec.json` and the `.excalidraw` it builds.

## Fetching icons
`python3 icons.py search <words>` finds a Simple Icons slug; `python3 icons.py fetch
<slug>... -o icons/` writes coloured SVGs ready for `"icon": "icons/<slug>.svg"`.

## Exporting an image
`export.py diagram.excalidraw out.png` (or `out.svg`, `--scale 3`, `--no-fonts`) writes a
shareable image: exact layout, the real Comic Shanns / Nunito fonts embedded (fetched
once and cached), rasterised with Chrome when installed or quick-look on macOS.
`build.py spec.json out.excalidraw --png` does the same in one step.

## Rendering a quick preview
`preview.py` writes a lighter SVG without fonts, for layout checks. To look at it:
- Chrome, any OS, exact size and crisp at 2x. Read `width`/`height` from the SVG's
  first line, then:
  ```
  chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
         --screenshot=d.png --window-size=W,H "file://$PWD/d.svg"
  ```
  `--window-size` is in CSS px (the SVG size); the scale factor doubles the pixels.
  Without `--force-device-scale-factor` on a 2x display the drawing fills a quarter
  of the image. macOS binary: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
  It prints harmless CVDisplayLink warnings.
- macOS quick-look, no Chrome: `python3 preview.py d.excalidraw d.svg --square && qlmanage -t -s 2400 -o . d.svg`
  (`--square` pads to a square; without it quick-look crops wide diagrams).

## Style profiles
`profile.py <folder> -o style.json` measures a set of diagrams and writes a profile:
font id, font sizes, roughness, stroke colour and width, corners, fill style,
arrowhead, elbow routing, canvas colour, the component fills and region tints with
names, arrow colours, and which fills mean "store". `build.py`, `lint.py` and `fix.py`
take `--style style.json` (or `PRETTIER_EXCALIDRAW_STYLE`); a spec can name it with
`"style"`. Fill names in a spec (`"fill": "blue"`) resolve through the profile, so a
profile may rename or replace the palette. Hand-editing the JSON is fine.

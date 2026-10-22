# Spec format for build.py

A spec is a JSON object. All coordinates are in Excalidraw canvas units (≈ px);
origin top-left, y grows downward. Lay things out on a 20 px grid.

```json
{
  "font": "comic",          // "comic" (Comic Shanns, default) | "nunito"
  "arrowhead": "outline",   // "outline" (hollow triangle, default) | "filled"
  "elements": [ ... ]       // in any order; the builder sorts the z-order itself
}
```

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
- `icon`: path relative to the spec file (svg / png / jpg). Placed on the left at
  ~80 % of box height; the builder shrinks it to ≥ 56 % or widens the box so the
  centred label never overlaps it. `icon_h` overrides the height.
- `w` / `h` default 240 × 70. The builder enlarges a box that cannot fit its label
  and prints a warning - treat warnings as a cue to adjust the layout.
- `dashed: true`, `stroke_width`.

### image – a standalone logo or picture
```json
{"id":"k8s","type":"image","src":"icons/kubernetes.svg","x":1080,"y":60,"h":100,
 "label":"kubernetes"}
```
Give `h` or `w`; the other follows the file's aspect ratio. `label` is centred
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
- `from` / `to`: ids of boxes, regions or images.
- `from_side` / `to_side`: `left | right | top | bottom`; omitted sides are chosen
  from the relative position of the two elements.
- `from_offset` / `to_offset`: shift the anchor along the side (px) so several
  arrows from one side do not overlap.
- Routing is orthogonal (elbowed): straight when aligned, otherwise one or two bends
  through the midpoint. Arrows are bound to both ends so they follow the boxes in
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
regions and boxes sorted by area (largest first, so containers precede children,
each followed by its bound label) → images → free text → arrows. You never need to
order the spec by hand.

## Worked example
See `assets/examples/temporal.spec.json` and the `.excalidraw` it builds.

## Rendering a preview to PNG
Run `python3 preview.py d.excalidraw d.png --png`. It uses Chrome/Chromium on
`PATH` (or Google Chrome in `/Applications` on macOS) at 2x. If Chrome is not
installed, macOS falls back to Quick Look at up to 2400px, automatically padding
the canvas to a square so wide diagrams are not cropped. `--square` also works
with Chrome when a square preview is wanted. Other systems need Chrome/Chromium.

Without `--png`, `preview.py` still writes SVG at the diagram's aspect ratio.
To rasterise that SVG by hand:
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

---
name: prettier-excalidraw
description: Use this skill whenever the deliverable is an Excalidraw file (.excalidraw) - the moment a user says "excalidraw" and wants a diagram drawn, fixed or checked, this is the tool, no matter how casual the ask. Covers three jobs: (1) draw a new diagram from a description of components and connections - request paths, "a -> b -> c" chains, layered or tiered architectures, infra, network, data-flow, workflow and checkout/pipeline flows - and save it where asked; (2) restyle or clean up an existing .excalidraw that looks messy or inconsistent ("make this prettier"); (3) lint an .excalidraw against the house style rules. Output is proper Excalidraw JSON with a consistent look: one font, elbow arrows, colour-coded boxes, tinted regions, logo icons, correct z-order. Do not use for Mermaid, PlantUML, Graphviz, draw.io or HTML/SVG diagram formats, for converting Excalidraw to another format, or for running/hosting the Excalidraw app itself.
---

# prettier-excalidraw

Produce Excalidraw diagrams that look like they were drawn by one careful person: no
sketchy lines, one font, one arrow style, a small palette of light fills with meaning,
regions that contain their children, and arrows that are never hidden behind a box.
The style is fully specified in `references/style-guide.md`; the scripts in `scripts/`
make it mechanical so you can spend your effort on layout and meaning instead of JSON.

## Which job is this?

| User wants | Do |
|---|---|
| A new diagram | **Generate**: write a spec, `build.py`, preview, lint, deliver |
| An existing `.excalidraw` made prettier / consistent | **Restyle**: `lint.py` → `fix.py` → `lint.py`, then hand-fix the manual findings |
| "Does this follow the style?" | **Check**: `lint.py` and explain the findings |
| A picture of someone else's diagram, "redo this in our style" | **Replicate**: read it with `references/reading-a-diagram.md`, then generate |

All scripts are Python 3 standard library only and live in `scripts/`. Run them from
that directory (they import each other) or set `PYTHONPATH` to it.
If a script fails, run `python3 doctor.py` first: it says what is missing (Python
3.10+, Chrome for PNG, fonts, the icons/style variables) with a hint for each.

## Generate a new diagram

1. **Understand the system first, and fill the gaps out loud.** List the components,
   which ones are grouped (cluster, VPC, layer, process), and every connection with
   its direction and what flows over it. Prompts are usually short, so check each of
   these before drawing anything:
   - every data store, cache, queue or topic: **who reads it and who writes it?**
   - every edge: which way does it go, sync call or async event, what is the payload?
   - every boundary: what is inside it and what is outside?
   - every external system: is it called, or does it call back (webhooks)?
   If the prompt does not answer one of these and the answer changes the picture, ask
   the user one short question before building. If you cannot ask, pick the most
   likely answer (the service that owns the domain owns its store; a cache sits with
   the service that is latency-sensitive) and say so in the reply as an explicit
   assumption, so the user can correct it in one word instead of discovering it later.
   A diagram that is wrong about the system cannot be rescued by styling.
   Decide the reading direction: left→right for request flows, top→bottom for layered
   architectures.

2. **Assign fills by role**, not at random. Same kind of thing = same colour, and keep
   it to 4–7 fills per diagram. The default mapping (blue = service / compute,
   yellow = server / runtime / CLI, green = gateway / network, red = storage / cache,
   purple = control plane, orange = external tool, teal = kubernetes, cyan = interfaces,
   grey = user / neutral) is in the style guide; deviate when the user's domain needs
   different groupings, but stay consistent inside the diagram.

3. **Write the spec** (`references/spec-format.md`) as JSON. Lay elements out on a
   20 px grid with these gaps, because the builder places labels relative to them:
   - between two boxes joined by a labelled arrow: at least `11 px × label length + 40`
     (`writes payments, ledger` needs ~300 px; a bare arrow needs 60). Parallel
     vertical arrows need their labels' width between them, since labels sit to the
     right of a vertical run.
   - 30–40 px inset from a region border to its first child, ≥ 20 px between siblings
   - leave ~40 px above a region for its title when the title is outside
   A region can carry its provider logo with `"icon": "vercel"` (small, in the corner
   opposite the title), which is the usual way to show "hosted on X".
   Place a store, cache or queue directly below or beside the component that uses it,
   never under a box that does not touch it: readers infer ownership from proximity
   before they read arrows, so a cache parked under the gateway "belongs" to the
   gateway no matter what the arrow says. If two services share a store, put it
   between them. When the linter reports `misleading-proximity`, either move the store
   or, if the box above really does use it, add that arrow: an honest extra edge is a
   legitimate fix. Label the arrow with the operation (`writes payments`,
   `get/set idempotency key`), not just a noun.
   Flowcharts and request flows can use `diamond` (decision), `ellipse` (start, end,
   yes/no markers, actors) and `note` (a caption or caveat in a light-grey box) next to
   boxes and regions, plus `divider` lines and `group`s that move together; see
   `references/spec-format.md` for their shape.
   Sizes and placement rules the builder follows, so you can plan without previewing:
   - box width needed: `11 px × label length + 32`, or `+ 2 × (icon height + 20)` with an
     icon (default icon height is 80 % of the box, 56 px for a 70 px box, so about
     `label × 11 + 152`); the builder widens on the 20 px grid when short
   - children start 60 px below a region's top edge (title row) and 30-40 px in from
     its sides; region tints are blue, teal, yellow, orange, purple, red; a "green"
     layer uses the teal tint with green boxes
   - `from_offset` / `to_offset` are px along the side from its centre, positive to
     the right or down; keep them equal for a straight arrow
   - a label goes above the longest horizontal segment or to the right of the longest
     vertical one; `label_at: start | end` picks the first or last segment instead
   - arrows and labels keep off region titles and borders by themselves (the builder
     offsets or bends and says so); if a title is wider than the arrow's column, set
     `from_offset` / `to_offset` or `bend` yourself (`arrow-through-text`)
   Give every box and region an `id`; arrows reference those ids. Pick `from_side` /
   `to_side` so an arrow leaves a box on the side that faces its target and does not
   cross other boxes; use `from_offset` / `to_offset` to fan out several arrows from one
   side. Use `label_at` ("start" / "end") when two arrow labels would land on the same
   segment.

4. **Icons.** Add a logo for every named technology (Postgres, Kafka, Kubernetes, AWS…)
   because that is what makes an architecture diagram instantly readable. Sources, in
   order of preference:
   - the user's own icon folder. If they have one, put it in the spec as
     `"icons_dir": "path"` (or set `PRETTIER_EXCALIDRAW_ICONS`) and write
     `"icon": "auto"` on every box: the builder matches the label against the file
     names and leaves a box bare when nothing matches. Ask where their icons live if
     they mention having some.
   - Simple Icons through the bundled helper (the CDN blocks plain `curl` with a bot
     page, and the npm mirror ships uncoloured files; the helper handles both and
     applies the brand colour):
     ```bash
     python3 icons.py search fly            # -> flydotio  Fly.io  #24175B
     python3 icons.py fetch postgresql apachekafka flydotio -o icons/
     ```
     Slugs are the lowercase brand name with `.`→`dot`, `+`→`plus`, `&`→`and`
     (`nodedotjs`, `fly dotio`→`flydotio`). The builder darkens a brand colour that
     would vanish on the box fill and prints one summary line; `icon_color` on the
     box overrides it when the darkened shade looks off-brand.
   - no icon. Never substitute a wrong or generic icon for a named product.
   Put the icon on a box with `"icon": "icons/x.svg"` (builder sizes it to ~80 % of the
   box height, on the left) or as a standalone `image` element with a `label` under it
   for big logos. Keep icon files next to the spec; paths are relative to the spec.

5. **Build, preview, lint, look.**
   ```bash
   cd <skill>/scripts
   python3 build.py spec.json out.excalidraw      # writes the file, prints size warnings
   python3 preview.py out.excalidraw out.svg            # SVG render for a visual check
   # to PNG: headless Chrome gives an exact-size image (recipe in
   # references/spec-format.md "Rendering"); fallback on macOS without Chrome:
   #   python3 preview.py out.excalidraw out.svg --square && qlmanage -t -s 2400 -o . out.svg
   python3 lint.py out.excalidraw
   ```
   Actually look at the preview. Things to catch: a box whose nearest neighbour above
   it is not the thing it talks to (`lint.py` flags this as `misleading-proximity`),
   an arrow crossing a box it is not connected to, two labels on top of each other, a label on top of a line, a box that
   the builder widened (see its warnings) now overlapping a neighbour, a region whose
   children spill outside it. Fix the spec and rebuild; two or three rounds is normal.
   The preview uses the stored text widths, but the real font can run up to ~15 % wider
   on bracketed or upper-case labels - leave that much margin, or export to PNG
   (`build.py --png`) for the real font before delivering.

6. **Deliver** the `.excalidraw` file (and the spec, so the user can regenerate). If the
   user wants an image too, or the diagram is going into a README, slide or chat, add
   `--png` (or `--svg`) to `build.py`, or run `export.py diagram.excalidraw out.png` on
   any existing file; the export embeds the real fonts and keeps the exact layout. For a
   docs page or a demo, `--html` writes a self-contained page where arrows flow, hover
   shows a shape's connections, a button plays a request path, and an explore button
   plays from any box and pauses at forks; name the paths in the spec (`"paths"`, see
   spec-format.md) when the user describes a flow. Say
   what each colour means in one line, since colour coding is only useful if the reader
   knows the key.

## Replicate a diagram from an image

When the user shares a screenshot or picture of a diagram, read it with the checklist
in `references/reading-a-diagram.md`: containers, components with their exact labels,
every arrow with direction and meaning, the colour key, the reading direction, and
what is implied but not drawn. That produces the same component list the generate
workflow starts from; continue from step 2 there. Keep the information architecture,
drop the visual style: roles decide fills, real logos replace drawn ones, curved
arrows become elbowed ones between the same endpoints. Deliver with a "changes from
the original" note listing what was renamed, merged, added or dropped, so the user
can trust the rebuild without comparing every box.

## Restyle an existing diagram

```bash
python3 lint.py in.excalidraw                 # what is wrong, with element ids
python3 fix.py in.excalidraw out.excalidraw   # mechanical fixes, positions untouched
python3 lint.py out.excalidraw                # what remains needs a human
```
When the user also wants a source they can regenerate from, or when the remaining
findings are mostly layout (overlaps, hidden text, arrows through boxes), restyling
is the wrong tool: rebuild the diagram from a spec with the generate workflow and
hand back the spec. `fix.py` never moves shapes, so it cannot repair layout.

`fix.py` changes font, snaps font sizes to 16/20/28 (re-measuring the text box and
re-centring bound labels), sets roughness 0, solid fills, sharp corners, the arrowhead,
moves arrows to the end of the z-order and moves a child box after its container. It
leaves grouped library icons alone (they are hand-drawn on purpose) and never moves a
shape. It prints `check label:` for any text whose size changed by 4 px or more,
because a 6 px label that becomes 16 px can now collide with its neighbours; look at
those in the preview. Findings marked `(manual)` - dark fill behind text,
unbound arrow endpoints, icon too small for its box - need judgement: edit the JSON
directly (the finding gives the element id) or tell the user what to change.

Both scripts take `--font comic|nunito` and `--arrowhead outline|filled` when the user
prefers the alternative; the default is Comic Shanns and the hollow triangle.

## Using the user's own style

The house style is a default, not a requirement. When the user has diagrams they like
and wants new ones to match, derive a profile instead of guessing:

```bash
python3 profile.py ~/diagrams -o style.json     # measures font, sizes, fills, arrows...
```
Show them the printed summary (it is their taste being encoded, so they should
confirm it), then pass `--style style.json` to `build.py`, `lint.py` and `fix.py`, or
put `"style": "style.json"` in the spec, or set `PRETTIER_EXCALIDRAW_STYLE`. Every
rule, default and palette name then comes from that file. Derive from diagrams they
are proud of, not from everything they ever drew.

## Why these rules (so you can apply them to cases the rules do not cover)

- **Roughness 0 and one font** - sketchiness reads as "draft". These diagrams are
  meant to be final documentation.
- **Light fills, dark stroke** - the stroke never changes with the fill, so the eye
  groups by colour without borders competing. Text stays readable on every fill.
- **Hollow triangle, elbowed** - a minimal head keeps dense diagrams calm; right-angle
  routes make it obvious which box an arrow enters. Colour on an arrow is semantic:
  red = blocked / danger / private path, green = allowed / success, blue = informational.
- **Z-order** - regions first, then inner boxes, then component boxes, labels and
  icons, arrows last. Anything else hides something. The builder enforces this order;
  `fix.py` restores it.
- **Icons proportional to their box** (65–95 % of height) - an oversized logo turns a
  component into an advertisement, an undersized one is noise.
- **Lowercase terse labels with `[secondary info]` in brackets** - matches the
  reference diagrams and keeps boxes small.

Reference diagrams in `assets/examples/` show the finished look; open one in Excalidraw
or run `preview.py` on it when unsure what "right" looks like.

# Character sprites

144 crisp pixel-art sprites for the 12 workbench characters, top-down RPG style.

## Naming

`{char}-{dir}-{frame}.png`

- `char`: 1..12
- `dir`: `D` (down / facing the viewer), `L` (left), `R` (right), `U` (up / back)
- `frame`: `1` = idle, `2` / `3` = walk cycle (play 2 → 1 → 3 → 1)

## Format

- Every file is exactly **240 × 304 px**, 8-bit palette PNG with a binary alpha
  (fully transparent or fully opaque, no soft edges). ~1.5–2 KB each.
- The image is a **60 × 76 native-pixel canvas scaled up ×4** with nearest-neighbour.
  All characters share this canvas, so a sprite can be swapped for any other frame or
  character without changing layout.
- **Baseline:** feet rest on native row 74 (output rows 296–299), i.e. 1 native pixel
  above the bottom edge, in every file. Idle/walk swaps never bounce vertically.
- **Horizontal:** the idle frame is centred by its bounding box; walk frames are aligned
  to the idle frame's head position (±1–3 native px of natural body sway).
- Characters are 61–74 native px tall, so they all read as the same visual size.
  Characters 1 and 9–12 were drawn at a finer pixel density than 2–8; the canvas uses
  the fine unit, so coarser characters simply occupy 2 × 2 native pixels per art pixel.
- Each character uses a fixed palette of 24–47 colours shared by all its 12 frames.

## Rendering

The art is pixel-exact; render it with

```css
image-rendering: pixelated;
image-rendering: crisp-edges;
```

and display at an integer fraction of the native scale where possible
(60 px, 120 px, 240 px wide → 1×, 2×, 4×) for perfectly sharp pixels. Any size up to
~100 CSS px tall looks crisp with `object-fit: contain`.

## Regenerating

The files were produced from blurry upscaled originals by recovering the native pixel
grid (gradient-profile period detection), centre-sampling each cell, snapping to a
per-character palette, a gentle +10 % saturation / soft-contrast pass, normalising onto
the shared canvas and re-exporting with nearest-neighbour scaling. Originals are in git
history (commit before this change) if a re-run is ever needed.

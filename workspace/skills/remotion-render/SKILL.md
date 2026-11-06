---
name: remotion-render
description: Export a Remotion video
version: 4.0.541
metadata:
  category: video
  guide:
    purpose: Hướng dẫn xuất video và ảnh tĩnh Remotion bằng CLI, kể cả video trong suốt.
    when: Cần render MP4, ảnh tĩnh, nhiều khung hoặc video nền trong suốt.
    benefit: Render đúng bằng trình duyệt đi kèm, có tuỳ chọn alpha.
    requires: Node.js + Remotion
---

## General rendering strategy

Use Remotion's bundled browser for rendering, including compositions using
`<HtmlInCanvas>`. It includes the required browser APIs and Remotion's browser
fixes. Let Remotion download or update it as needed. Do not reuse a recording
browser or set `--browser-executable`, `browserExecutable`, or `chromeMode`
unless the user explicitly requests a different browser.

Render a video using:

```
npx remotion render
```

Full list of options: https://www.remotion.dev/docs/cli/render.md

Render a still using:

```
npx remotion still
```

Full list of options: https://www.remotion.dev/docs/cli/still.md

To render several frames as images in one call, use `render --frames`:

```
npx remotion render [composition-id] out/frames --frames=0,30,90 --image-format=png
```

See https://www.remotion.dev/docs/cli/render.md#--frames for more options.

## Transparent videos

See [Transparent videos](./transparent-videos.md) for rendering out a video with transparency.

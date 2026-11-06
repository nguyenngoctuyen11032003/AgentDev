---
name: remotion-maps
description: Remotion Map animation knowledge
version: 4.0.541
metadata:
  category: video
  guide:
    purpose: Hướng dẫn dựng hoạt ảnh bản đồ trong Remotion với Mapbox, MapLibre, MapTiler, Cesium hoặc ảnh vệ tinh tĩnh.
    when: Cần video giải thích địa lý, tuyến đường, marker hoặc bay qua địa hình.
    benefit: Chọn đúng kỹ thuật bản đồ theo nhu cầu và có sẵn kỹ thuật chi tiết cho từng loại.
    requires: Node.js + Remotion; Mapbox/MapTiler key tùy kỹ thuật
---

# Remotion Maps

Choose exactly one technique from the intended shot, then load only that technique's `TECHNIQUE.md`.
Every technique directory is self-contained and may be removed without breaking the others.

## [Static map](techniques/static-map/TECHNIQUE.md)

- Requires you grab a satellite image and mount it in a `<Img>` tag, and animate on top

## [Mapbox](techniques/mapbox/TECHNIQUE.md)

- Requires a Mapbox key
- Nicer styles by default
- Map can display a round globe when zoomed out
- Includes nice 3D buildings such as the Eiffel tower

## [MapLibre](techniques/maplibre/TECHNIQUE.md)

- Requires no API key, fully free
- Does not include 3D building

## [MapTiler](techniques/maptiler/TECHNIQUE.md)

- Uses MapTiler
- Annotations can be drawn on top of geographic features: borders, rivers, labels

## [CesiumJS](techniques/cesium/TECHNIQUE.md)

- Flythroughs through terrain and mountains
- "Flight simulator" perspective

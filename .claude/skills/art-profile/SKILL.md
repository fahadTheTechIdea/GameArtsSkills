---
name: art-profile
description: Use to determine pixel-art, painted, illustrated, vector, rendered or custom look and the approved world/screen geometry without hardcoding dimensions.
---

# Art style & asset profile

Separate the **universal production rules** from art-style decisions and asset-specific geometry. Record approved reference(s), style ID, materials, camera and scale, filtering, antialiasing policy, export resolution, detail density and scene use. For pixel art, use deliberate pixel clusters and nearest sampling; for painted/vector/illustrated/rasterized styles use appropriate edge antialiasing and texture filtering. Do not force a single pixel style on other graphics.

Current project geometry baseline: orthogonal square map; 16×16 world-meter terrain cell, initial 256×256 px ground-art resolution, initial 16 px per meter, 1 m construction snap, continuous world coordinates. Above-ground oblique artwork does not turn the ground map into diamond tiles. Source native scale (1,1) by default; adaptable frame sizes based on measured bounds. Mark estimates as estimates.

All generated Game Arts PNGs have exact opaque #FF00FF in unused/background pixels. Smooth-edged styles may require separate edge coverage / matte metadata in the authoring workflow; never imply a single opaque chroma-key PNG preserves fractional transparency automatically.
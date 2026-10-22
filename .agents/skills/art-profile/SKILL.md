---
name: art-profile
description: Use to determine pixel-art, painted, illustrated, vector, rendered or custom look and the approved world/screen geometry without hardcoding dimensions.
---

# Art style & asset profile

Separate the **universal production rules** from art-style decisions and asset-specific geometry. Record approved reference(s), style ID, materials, camera and scale, filtering, antialiasing policy, export resolution, detail density and scene use. For pixel art, use deliberate pixel clusters and nearest sampling; for painted/vector/illustrated/rasterized styles use appropriate edge antialiasing and texture filtering. Do not force a single pixel style on other graphics.

Current project geometry baseline: orthogonal square map; 16×16 world-meter terrain cell, initial 256×256 px ground-art resolution, initial 16 px per meter, 1 m construction snap, continuous world coordinates. Above-ground oblique artwork does not turn the ground map into diamond tiles. Source native scale (1,1) by default; adaptable frame sizes based on measured bounds. Mark estimates as estimates.

All generated Game Arts PNGs have exact opaque #FF00FF in unused/background pixels. Smooth-edged styles may require separate edge coverage / matte metadata in the authoring workflow; never imply a single opaque chroma-key PNG preserves fractional transparency automatically.

## Camera/style locked prompt input (required, not optional)
For every image tool call, build a **style lock** from the approved reference: camera type and direction, art family, material/shading palette, outline thickness, texture scale, pixel density, silhouette, native size and allowed change. The prompt must name the actual crop/approved reference and the exact projection; "game pixel art" alone is not sufficient. Oilfield Days world view is **elevated 3/4 top-down oblique orthographic, NOT isometric**; never prompt an isometric structure. World view and UI portrait view are distinct.

Static structures/fixed machinery: **one** camera/view unless placement policy explicitly authorizes more. Mobile freely turning assets: **eight** directional masters and direction-aware components when required by gameplay. A new direction never changes model identity, shape, palette or structural details. If camera cannot be reproduced from the image tool, mark the output a concept candidate only and do not advance to production.


## Selected game settings drive prompt generation (mandatory)
Before **every** image-generation/edit call, read `<game-root>/.gamearts/project.json`, applicable active custom instructions, approved mockup crop/locked master and asset-specific profile. Resolve the exact selected `art_style.id`, `art_style.reference`, style appearance settings (palette/outline/shading/texture/pixel density if present), `world.object_camera`, scale, asset-specific directions, `animation.preferred_method` and `export.*`. **Insert these actual resolved values into the tool prompt, not merely into commentary.** Use the hierarchy and conflict-resolution guidance under "Mandatory saved-settings resolution for EVERY image prompt" in the one canonical master.

Never hardcode Oilfield Days, pixel-art style, oblique projection, an isometric ban, or a direction count in generic prompts. Oilfield Days is a project-specific example, only applicable when that project/style is selected. If settings are missing, use verified approved references, then plainly marked defaults; ask the friendly wizard only for an essential missing choice. Never secretly replace a saved style. Check the actual prompt matches resolved values before sending it, and review the resulting image against the exact project-specific constraints afterward.


## Crop-and-reference image-tool input
The image prompt must inherit the selected project's actual art_style and world.object_camera from saved settings and preserve the camera and appearance shown by the exact cropped approved source image. The canonical crop gate produces a reference.packet.json with resolved selected values. Check the prompt and **actual image attachment** against this packet; do not allow freehand isometric/generic pixel-art substitutions or silently replace the selected medium. Output mismatch is a failed concept, not a locked master.

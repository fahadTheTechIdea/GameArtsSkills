---
name: art-profile
description: Resolve a game's art style, world or screen geometry, camera, scale and direction policy from its saved settings and approved references, and build the style lock for image prompts. Use before any image-tool call or whenever style, viewpoint, scale or direction count is in question.
---

# Art style and asset profile

Policy: master *Art-style profiles*, *World geometry, projection and scale*, *Asset profiles, view and direction classification*, *Reference-controlled image prompting*, *Reference crop and conditioning gate*. The selected project's saved settings are inputs to every prompt, not examples.

## Resolve before every image-tool call
1. Read `<game>/.gamearts/project.json`, applicable active instructions, the approved mockup crop or locked master and the asset's own profile. Resolve `art_style.id`, `art_style.reference`, the style policies (palette, outline, shading, texture, pixel density), `world.grid`, `world.camera_profile`, `world.object_camera`, `world.ground_camera`, `art_style.ui_camera`, scale (`pixels_per_meter`), the asset's directions, `animation.preferred_method` and `export.*`.
2. **Write the resolved values into the actual tool prompt**, not only into your commentary: art family, the exact camera and projection, palette and materials, outline thickness, texture scale, pixel density, silhouette, native size, and the allowed change. "Game pixel art" alone is never a style lock. Check the prompt against the resolved values before sending, and the result against them afterwards.
3. Never hardcode a style, camera, direction count or an isometric ban into a generic prompt, and never carry one game's camera into another. Absent settings: use verified approved references, then plainly marked defaults; ask the setup wizard only for an essential missing choice. Never secretly replace a saved style. If `project.json` and an approved mockup disagree, flag it and keep the approved reference for that asset.

## View by asset class
**Anchor and palette.** With `art_style.anchor` set, `prepare_reference_crop.py` already carries the style board into the crop packet: pass both images to the tool. To give the game a palette the checks can use: `python scripts/gamearts_palette.py extract --game-root <game> --image <approved mockup or style board> --name main [--max-colours 32]`, then have `game-arts-project-setup` save the printed path as `art_style.palette_reference` (a palette is part of the look, so the owner confirms it). Master *Art-style profiles*; the checks that use it are in *Quality gates and validation grades*.

Static structures and fixed machinery: **one** approved view unless a limited rotation set is explicitly approved. Mobile free-facing assets: the selected direction set (eight when gameplay needs it), one controlled master at a time; a new direction never changes identity, shape, palette or structure. UI: its own presentation view (`art_style.ui_camera` or the approved screen reference), never the world camera. Terrain: `world.ground_camera` or the ground-grid view. A camera is not a direction: the crop packet records `fixed`, `ui`, `tile` or the game's direction set as the directions. If the image tool cannot reproduce the camera, the output is a concept candidate only and production does not advance.

## Style-specific handling
Pixel art: deliberate clusters, nearest sampling. Painted, illustrated, vector and rendered styles: appropriate edge antialiasing and texture filtering; never force pixel rules on them. Every delivered PNG still has exact opaque `#FF00FF` in unused pixels; smooth edges need separate coverage or matte metadata in the authoring workflow, and an opaque key PNG never preserves fractional transparency by itself (*Masking and PNG export policy*). Source native scale is `(1, 1)` by default; frame sizes follow measured bounds; mark estimates as estimates.

## Style-neutral cleanup and review
Across all styles a clean static parent holds only permanent, inseparable geometry; every independently movable, removable, interactive, replaceable or animated element is removed from its pixels and has its own art (*Parent-artwork cleanup and separation gate*). Each exported object's silhouette must match an independently approved foreground mask, with no floor or wall patches from a rectangular crop; masks are technical evidence, not an instruction to pixelate painted or vector art. Review boards use nearest scaling for pixel art and smooth scaling otherwise; they are not game sprites. No algorithm proves a reconstructed hidden surface is plausible: the user reviews the clean plate and the object boundaries and the accepted uncertainty is recorded.

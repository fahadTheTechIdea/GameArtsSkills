# Coverage and quality plan: is Game Arts ready for all 2D game art, and what is still missing

Written 2026-10-29 at the owner's request ("research missing and needed features or improvements and create a plan").
Status lives in [MASTER_TRACKER.md](MASTER_TRACKER.md) (row V-40); earlier plans are [ENHANCEMENT_FIX_PLAN.md](ENHANCEMENT_FIX_PLAN.md) and
[STYLE_AND_USABILITY_PLAN.md](STYLE_AND_USABILITY_PLAN.md). Nothing in this file is built unless the tracker says so. Decisions here are numbered
D-20 onward and the owner may overrule any of them.

## 0. The honest answer to "is it ready for all 2D art"

No claim of "all" can be made, and this plan does not try to make one. What can be said:

- **By design** it has a place for most 2D art a game ships (section 2).
- **By evidence** very little has met a real image model, a real engine, a real art tool or a real game (section 3). That is the largest risk, larger than
  any missing feature, so the plan puts evidence before features (phase C0).
- **Missing features** are listed with the evidence for each and an explicit build / spike / do-not-build decision (section 4).

"Better" is measured only where something can be measured: a pixel, a hash, a record, a time. Whether art is good stays a human decision.

## 1. Method and limits

- Read: the master standard's asset classes, the validators and exporters, the genre recipes, the open unknowns in the two earlier plans, and the code
  paths that the findings touch (revoke, export, recolour).
- Measured on 2026-10-29: the recolour time at 1024, 2048 and 4096 px (finding Q-3).
- Researched on 2026-10-29: image-model transparency, colour-vision simulation, normal-map workflows in 2D engines, pixel-art defect definitions,
  isometric tile handling, skeletal-animation formats, atlas edge bleeding and game colour accessibility. Section 9 says for each source whether the page
  was read or only a search result was seen. Where sources conflict the conflict is stated, not resolved by guess.
- Not done: no real image model, engine, Aseprite, Tiled or game was used for this plan. Findings that depend on them are marked unverified.

## 2. Coverage today (by design, not by proof)

| 2D art type | Where it is handled | Honest state |
| --- | --- | --- |
| Directional characters and creatures | `mobile_directional`, direction sets, component bundles, appearance lock | Built; synthetic only |
| Cut-out animated parts, machinery | components, keyframes, sampled poses, cleanup gate | Built; synthetic only; engine playback is the game's |
| Buildings, structures, props | `static_structure`, `prop`, clean-parent rule, scene object sweep | Built; scene detector recall about 0.60 on one scene (V-34) |
| Terrain and tilesets | `terrain`, `tileset`, six layouts, seam check, animated tiles (V-39) | Built; rectangular tiles only; diamond seams unverified |
| Parallax and layered scenes | `parallax_layer`, `layered_scene` | Built; engine behaviour unobserved |
| UI kits, icons, portraits, cards | `ui_presentation`, `icon_set`, `portrait_set`, `card_layer_set`, nine-slice, states | Built; synthetic only |
| Effects and flipbooks | `effect`, blend advice, loop checks | Built; blend mode is advice for the game |
| Palette and look consistency | presets, style anchor, palette extraction, `palette_exact`/`palette_near`, `pixel_grid`, `integer_scale` | Built; real-generator conformance unmeasured (U-S5) |
| Palette variants (teams, seasons, night) | `gamearts_palette.py recolour` (V-39) | Built; no lineage link between variant and base (Q-2) |
| Store and marketing art | screen-space mockup, size read from the store's page | No check of the size (Q-9) |
| Normal, specular and lighting maps | nothing | Missing by decision (Q-8) |
| Skeletal (bone) formats | nothing | Not built by decision (Q-10) |
| Fonts, vector output, 3D-rendered sprites | text stays native by rule; raster only | Out of scope (section 8) |

## 3. Evidence debts (these outrank every feature)

| ID | Debt | Why it matters | Where recorded |
| --- | --- | --- | --- |
| Q-12a | Production stages (crop, master, components, sheets) have only run on synthetic art; mockup generation ran for real | The one stage no real model has run through (U-8) | tracker owner step 6 |
| Q-12b | Nine fresh-agent scenarios E-1 to E-9 not run | Nobody has watched an agent follow the shortened skills through every gate (U-4) | STYLE plan P14 |
| Q-12c | Hosted CI: the two pushes of 2026-10-28 started runs whose results were not read, and everything since (recolour, animated tiles, genre recipes, docs) is not pushed | Linux and Pillow 9.5.0 are untested for scene stages, fallback, disclosure, recolour, animated tiles | tracker U-3 |
| Q-12d | Aseprite JSON, Tiled tileset and Godot mappings never opened in the real tools | The exports are labelled best effort | U-S2, U-S3, A14.5 |
| Q-1 | True alpha from the owner's tools: one sample only; sources conflict (section 4) | Decides whether soft-edged art needs the matte lane | U-S1, V-26 |
| Q-13 | Eight recipes written from the framework's own classes with no genre source | Guidance not yet checked against real games of those genres | V-39 |

## 4. Findings and decisions

Priority: P0 evidence first, P1 integrity of what exists, P2 new measurements (report only), P3 only when a game needs it.

### Q-1 (P0) Transparent-background support differs by model and the sources disagree
- **Documented:** OpenAI's image-generation guide, fetched 2026-10-29, says that for transparent backgrounds with "either model" (named there as
  `gpt-image-2.5-sunburst` and `gpt-image-2.5-flare`) set `background: "transparent"` with `output_format` `png` or `webp`. The same guide does not mention
  `gpt-image-2`. The API reference page seen in a search result says `gpt-image-2` and `gpt-image-2-2026-04-21` do not support transparent backgrounds and
  return an error. Third-party pages dated about August 2026 say it works as a preview. I did not read the reference page itself.
- **Observed here:** one sample with Codex's built-in tool returned true alpha (V-26). The fallback tool's own description (as shown in this session) names `gpt-image-2.5-sunburst` and `gpt-image-2.5-flare` for its UI-kit and concept steps; it does not state transparency.
- **Inference:** the model the owner's tool uses decides the result, and tools may change model without notice.
- **Decision D-20:** do not change the soft-edge default on this evidence. Run a spike (C0.1) per tool and model the owner actually uses, record tool, model,
  prompt and result, and only then decide whether the matte lane stays the default.

### Q-2 (P1) A variant has no link to the art it came from
- **Evidence:** `_dependents` in the lifecycle finds assets only through `source_mockups`, and only for a mockup revoke (`revoke`, kind `mockups`). A
  recoloured sheet shares the base's mockup but nothing links it to the base asset. Revoking the base sheet because its frames are flawed leaves the variant
  approved and flawed. The recolour record names the source files by hash but lives beside the frames, not in the manifest.
- **Decision D-21:** add an optional `source_assets` list (asset id and revision) to the assets manifest, filled by `register-asset --source-asset ID:vNNN`, checked
  at registration (the source must exist and not be revoked), shown in the report, and used by revoke to name dependent assets. No automatic revoke: the owner
  decides, as for mockups.
- **Acceptance:** register a variant naming its base; revoking the base reports the variant by name; revoking a variant does not touch the base; an unknown or
  revoked source is refused; old manifests without the field still validate.

### Q-3 (P1, done) Recolour was slow on a large sheet
- **Measured 2026-10-29:** the first version took 2.5 s at 1024 px, 8.5 s at 2048 px and 36.8 s at 4096 px (one pass over every pixel in Python).
- **Fixed:** colours are now found with one mask each in Pillow's own routines (0.05 s, 0.22 s, 0.70 s at the same sizes), with the pixel loop kept as the
  reference and as the path for tables of more than 64 colours. Equivalence of the two paths, a colour swap that must not chain, a key colour listed in the
  table, and the transparency rules are tested; three deliberate breaks each fail the suite.
- **Left:** the 64-colour limit is a judgement, not a measurement. The pixel loop is still slow on a large painted picture that needs snapping.

### Q-4 (P2) No check that variants and icons stay distinguishable to people with colour-vision deficiency
- **Documented:** the Game Accessibility Guidelines say colour should back up another cue (a symbol, pattern or shape) and that reducing reliance on colour
  comes before palette changes; team colours with no other marker are a listed failure (search result, page not read in full). Machado, Oliveira and
  Fernandes (IEEE TVCG 15(6), 2009) give a physiologically based simulation by matrices; the Python `colour` library implements it (docs seen, matrices not
  read).
- **Inference:** a measurement can show that two team colours collapse under simulation; it cannot say a game is accessible.
- **Decision D-22:** build a report-only check `colour_distinct`: simulate protan, deutan and tritan on the dominant colours of two variants (or the colours of
  an icon set), report the smallest perceived distance under each (CIE76 as the palette module already uses), and say plainly that a second marker is the
  first remedy. It never blocks and never passes anything off as "accessible". The matrices must be copied from the primary paper and compared once with the
  `colour` library's values in a recorded check; the library is not added as a dependency.
- **Acceptance:** two variants that differ only in red and green are reported as close under deutan; two that differ in blue and yellow are not; the report names
  the pair and the distance; no status other than information.

### Q-5 (P2) Pixel-art line quality is not measured beyond palette and grid
- **Documented (practitioner sources, no standard):** jaggies, doubles and orphan pixels are the common line defects (Wayline lesson); banding and pillow
  shading are defined and measured by counting banded segment pairs in a TU Delft thesis (2025); tools exist that despeckle isolated pixels.
  No source gives a lint rule set, and none was found for doubles or jaggies.
- **Decision D-23:** build only the orphan-pixel count as a report-only advisory (a visible pixel with no same-coloured or similar 8-neighbour, counted per sheet
  and per frame). Doubles, jaggies and banding stay a spike (C2.3): measure how often a candidate rule flags the owner's approved art before it is allowed to
  say anything, because a lint that cries wolf teaches people to ignore reports (U-S5 applies).
- **Acceptance:** orphan counts match a hand-counted fixture; the report never changes an approval state; the spike's result and the false-positive rate on
  approved art are recorded before any further rule is written.

### Q-6 (P2) Runtime export sets hidden pixels to black-transparent
- **Documented:** with bilinear filtering and mipmaps a sprite can pick up neighbouring texels; common practice is to extrude or dilate edge colours into the
  border before packing, with padding at least equal to the extrusion (FastPack documentation); a Khronos thread says mipmapped atlases cannot work properly
  without per-texture mipmaps. Premultiplied alpha was not resolved by what I found.
- **Inference:** `export_runtime.py` writes every key-coloured pixel as RGBA (0, 0, 0, 0). Pixel styles use nearest filtering and are unaffected; smooth styles
  (painterly, rendered, vector) may show dark edges in an engine that filters.
- **Decision D-24:** add an optional `--bleed N` to the runtime export for smooth styles only: colour of the nearest art pixel copied into hidden pixels within N
  pixels while alpha stays 0; derived copy as before, never approved art. Default off. It cannot be called fixed until an engine shows the fringe and its
  absence, which is an owner observation (C3.3).
- **Acceptance:** with `--bleed`, hidden pixels within N of art carry the neighbour colour and alpha 0; art pixels are byte-identical to the unbled export; the
  hash record still ties the copy to its source; N larger than the padding is refused or reported.

### Q-7 (P3) Diamond (isometric) tiles are not seam-checked
- **Documented:** the tileset doc already says diamond neighbour rules are not verified. Tiled forum answers say the map grid should match the diamond base while
  the tileset tile size is the full image, and that the tileset grid itself stays rectangular (weak sources: forum replies).
- **Decision D-25:** spike only if the owner makes an isometric game: sample along the four diamond edges (2:1) instead of the rectangle sides, on synthetic
  tiles first, and keep the export labelled unverified until the owner opens one in Tiled.

### Q-8 (P3) No companion maps (normal, specular) for lit 2D
- **Documented:** Godot's `CanvasTexture` pairs a colour texture with normal and specular maps, expects the X+, Y+, Z+ normal convention, and shows the effect
  only under `Light2D`; a packer plugin keeps the normal sheet in exactly the colour sheet's layout; a map generator (Laigter) derives maps from colour art.
- **Inference:** a companion map breaks two framework rules (the exact-key background would corrupt vector data; one sheet, one atlas) and needs its own pixel
  policy and a pairing contract with a colour sheet.
- **Decision D-26:** do not build until a game of the owner's uses lit 2D. Then: a `material_maps` companion with the colour sheet's atlas rectangles, no key
  colour, a declared normal convention, a length check on the vectors, and an engine observation before any claim.

### Q-9 (P2) No exact-size check for store, UI or marketing art
- **Evidence:** Steam capsule sizes are quoted at two different values by different guides (a header at 920x430 in newer guides and 460x215 in older ones; one
  guide says the list was raised in August 2024) and the Steamworks page retrieved still showed older examples. Google Play and App Store lists were not searched.
- **Decision D-27:** store lists are not kept in the repository (they go stale). Add a generic `--expect-size WxH` to registration of a mockup or asset: the owner or
  agent supplies the size read from the store's page, the framework only verifies it and records it.
- **Acceptance:** a picture of another size is refused by name with both sizes; the expected size is recorded with the mockup; without the flag nothing changes.

### Q-10 (P3, no) Skeletal-animation export
- **Documented:** Spine's JSON format (skeleton hash, version, bones, slots, skins, animations) is published, but its editor version must match the runtime
  version and the tooling is licensed (search result and the format page's summary; license terms not read).
- **Decision D-28:** no Spine or similar export. The component bundle already carries the composed transform of every component for every direction and sampled
  time, and engine-native animation resources are the game project's, per the owner's standing engine rule.

### Q-11 (P3) Signed content credentials
- Unchanged from V-38: no signed C2PA manifest until the owner supplies a signing certificate and the spec sections (assertions, certificate rules, PNG
  embedding) are read.

### Q-14 (P1) The record that a generated asset was made with a tool is only guidance
- **Evidence:** the lifecycle skills tell the agent to pass the tool as asset provenance and the disclosure summary counts assets without it, but nothing in
  the report or next steps names them (accepted, then ignored is the failure to hunt).
- **Decision D-29:** the art report says on each asset card which tool made it, or that the tool is not recorded. No new gate. (Built as a card line. A
  next-step nag was left out on purpose: it would fire for every hand-made asset, and the disclosure summary already counts the unrecorded ones.)

### Q-15 (P1) Hygiene debts on the new modules
- Formal mutation proofs (M-numbers in `plans/enhancements/evidence/mutation_proofs.py`) do not yet cover the scene stages, the fallback, the disclosure
  summary, recolour or animated tiles; each was broken by hand and caught, but the hand checks are not repeatable evidence. Run only the touched proofs, never
  the full set.

## 5. Phases

| Phase | Work | Needs | Done when |
| --- | --- | --- | --- |
| C0 Evidence | C0.1 transparency spike per tool and model; C0.2 one real asset per class (character sheet, tileset, UI kit, effect, icon set) through the owner's image tool in a real game; C0.3 E-1 to E-9, two runs each by fresh agents, every failure recorded; C0.4 push and read the hosted CI result; C0.5 open one Aseprite JSON and one Tiled tileset in the real tools | the owner's go for C0.3 (about 18 agent runs) and a real game for C0.2 and C0.5 | each item has recorded command, result and date, including failures |
| C1 Integrity | Q-2 `source_assets`, Q-14 report line, Q-15 mutation proofs for the new modules | none | acceptance of Q-2 met; the report names unrecorded assets; the touched proofs fail without their fix |
| C2 Measurements, report only | Q-4 `colour_distinct`, Q-5 orphan pixels and the line-defect spike, Q-9 `--expect-size` | the matrices from the paper (Q-4) | each check has a fixture where it fires and one where it does not; none changes an approval state |
| C3 Runtime fidelity | Q-6 `--bleed`, C3.3 the owner observes the fringe in an engine; Q-7 diamond spike only if an isometric game exists | an engine (owner) | export tests pass; the observation is recorded as owner evidence, separate from agent evidence |
| C4 On demand | Q-8 companion maps, Q-11 signed credentials, integer-scale (`@2x`) export | a game that needs each; a certificate for Q-11 | not started without the trigger |

Order: C0.4 first (cheap, and the CI result may change what C1 must fix), then C1, C0.1 and C2 in parallel, C0.2 and C0.3 when the owner has a game and the
go-ahead, C3 after C0.2 shows which styles really filter. Each task is small enough to be its own commit; local tests are focused, CI runs the whole suite.

## 6. Verification rules for this plan

- Every fix is preceded by a failing test and followed by a break-the-fix proof (the standing rule); a check that passes on the unfixed code counts for nothing.
- A report-only measurement may not change an approval state or print "passed" for something it did not assess.
- Behaviour claims about agents need agent evidence; claims about an engine need an engine observation; neither is replaced by a structure check.
- Local success does not establish hosted CI, live agent behaviour or an installed game; those stay "not run" until observed.

## 7. Risks

| Risk | Handling |
| --- | --- |
| More checks than anyone reads | Report-only, one line each, only where a fixture proves it fires; the report keeps its short next-steps list |
| A lint that flags good art | The false-positive rate on approved art is measured before a rule may speak (Q-5) |
| Features for games that do not exist | Q-7, Q-8, Q-11 and the `@2x` export wait for a game that needs them |
| Matrices copied wrongly | Taken from the primary paper and compared once with an independent implementation; recorded |
| Sources go stale | Every source is dated here; store sizes are never stored in the repository |
| Cost of C0.3 | Asked for explicitly; two runs each is the plan's own criterion (P14), not an extra |

## 8. Non-goals

Fonts and bitmap fonts (text stays native), vector (SVG) output from raster generators, 3D-rendered sprites, a learned image-similarity score (heavy
dependencies and no ground truth; human review stays), engine-specific resources beyond data profiles, audio, and any Spine or similar proprietary export.

## 9. Sources (retrieved 2026-10-29)

Read means the page text was fetched; seen means only a search result or snippet was available.

- OpenAI image generation guide, https://developers.openai.com/api/docs/guides/image-generation: read the first 100,000 of 114,889 characters.
- OpenAI image API reference, https://developers.openai.com/api/reference/cli/resources/images/index.md: seen (search result) and not read.
- Third-party reports of `gpt-image-2` transparency (the-decoder.com, mind-verse.de, docs.apiyi.com): seen, not read, unconfirmed by OpenAI's pages.
- Machado, Oliveira, Fernandes 2009, https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html and the `colour` library,
  https://colour.readthedocs.io/en/latest/colour.blindness.html: seen.
- Game Accessibility Guidelines, https://gameaccessibilityguidelines.com/ensure-no-essential-information-is-conveyed-by-a-fixed-colour-alone/: seen.
- Godot `CanvasTexture`, https://docs.godotengine.org/en/stable/classes/class_canvastexture.html; GDQuest, https://www.gdquest.com/library/lighting_with_normal_maps;
  Laigter, https://laigter.readthedocs.io/: seen.
- Pixel-art defects: https://www.wayline.io/learn/pixel-art/1 and the TU Delft thesis
  https://repository.tudelft.nl/file/File_65d43acd-9779-4eab-999b-9bcd4f0a96a9: seen.
- Atlas bleeding: https://www.mintlify.com/Hexeption/FastPack/packing/extrude and https://community.khronos.org/t/texture-filter-and-atlas-image-distortion-problem/76802: seen.
- Isometric tiles: https://discourse.mapeditor.org/t/isometric-is-it-possible-to-set-the-grid-in-the-tileset-to-isometric/2177: seen.
- Spine JSON format, https://esotericsoftware.com/spine-json-format: seen.
- Tiled JSON map format, https://doc.mapeditor.org/en/stable/reference/json-map-format/: read (animation frames: `tileid`, `duration` in milliseconds).
- Steam store assets, https://partner.steamgames.com/doc/store/assets/standard: seen; Steam capsule guides: seen, they disagree.
- Palette swapping, https://wargroove.com/palette-swapping/: seen (practitioner source, not a standard).

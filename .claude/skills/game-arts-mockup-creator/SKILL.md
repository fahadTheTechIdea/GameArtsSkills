---
name: game-arts-mockup-creator
description: Create, revise, present and register visually reviewable mockups of game worlds, scenes, assets, characters, UI screens and flows. Use as the first visual step for any new Game Arts design that has no approved reference, and when the user asks to create, revise, compare or approve a mockup.
---

# Game Arts mockup creator

Policy: master *Mandatory mockup-first approval gate*, *Mockup scope classification and decomposition*, *Reference-controlled image prompting*, *Masking and PNG export policy*.

## When
A new scene, environment, sprite, world, character, interface, effect or asset with no approved reference; a request to create, revise, compare or approve a mockup; a materially changed direction for an approved mockup. An unchanged approved mockup is reused, not recreated. A mockup the user made elsewhere is imported with `import-mockup`, not regenerated (`game-arts-lifecycle`, *External and user-supplied mockups*).

## Procedure
1. Find the game. Read `.gamearts/project.json`, active instructions and approved references (`select --stage approved --kind mockups`; a game with no `instructions`, `outputs` or `manifests` folder yet simply has none). A text concept may be discussed anytime, but **generating and registering a mockup needs `settings_status: "owner_confirmed"`**: if it is missing, inferred or `needs_review`, show a plain-language summary and ask for one confirmation (`game-arts-project-setup`). Never fabricate it.
2. For a game or campaign request, a storyboard comes first (`game-arts-storyboard`); a scene mockup then names its approved `storyboard_scene_id`.
3. Classify the scope: world, scene, asset, character, ui_screen, ui_flow, mixed or style (a style board, see below). Use the saved art style and asset profile; do not impose pixel-art rules on other styles. Study supplied references and keep their observed details.
4. **Render an actual mockup with the owner's chosen image generator** (the section "The image generator" below) and the full prompt from the master (resolved style, camera, scale, scope, identity, export rule). A text prompt is not a mockup, and a picture you draw yourself with a script is not a generated mockup either; if the chosen tool cannot be used here, follow "Not available in this session" below and register nothing. A fully painted, full-bleed mockup (scene, world, UI screen) uses the whole frame and has no unused pixels; whatever is unused is exact `#FF00FF`. A mockup is a review picture at the tool's natural size (a landscape frame around 1536 x 1024 is typical); `pixels_per_meter` and tile sizes calibrate production art, not the mockup, so record its size and never claim scale calibration for it.
5. Write the prompt you actually sent to the tool into a scratch text file (`<game>/.gamearts/system/prompt_draft.txt`; delete it afterwards). Leave the picture where the tool saved it (for Codex's built-in tool that is under `$CODEX_HOME/generated_images/`) and register it; the framework names the file, hashes it, writes the metadata and files it under `generated`:
```text
python scripts/gamearts_asset_lifecycle.py register-generated --game-root <game> --image <the tool's PNG> --id <mockup_id> --revision <vNNN> --scope <scope> --prompt-file <prompt file> [--storyboard-scene-id <scene>] [--model <name>]
```
   The tool defaults to the owner's saved choice and `register-generated` refuses any other; never name a different one to get past it. Never copy files into managed folders by hand, write the metadata yourself or edit the manifest.
6. Check it:
```text
python scripts/gamearts_asset_lifecycle.py audit-mockup --game-root <game> --id <mockup_id> --revision <vNNN>
python scripts/gamearts_asset_lifecycle.py reconcile --game-root <game>
```
   Registration implies no approval. Tell the user the pixel facts it reports (size, transparency, exact key pixels) and anything you can see that departs from the saved style, camera or scale; it certifies none of them.
7. **Look at the picture before the user does.** Compare it with the saved style, camera and what was asked. If it clearly departs (for example the camera is eye level when the game's is elevated 3/4), make **one** corrected revision, register it, and withdraw your first candidate with `revoke` (reason: "agent revision, not a user rejection"). Show only the better one and say what you changed; further changes wait for the user. Never withdraw anything the user has seen or approved.
8. Show the preview and ask plainly: **"Do you approve this mockup, or what should change?"** A revision is a new generated revision; earlier ones stay.
9. On the user's real approval of that exact revision, `game-arts-lifecycle` runs `approve-mockup`; rejected or superseded ones go to `revoked` through `revoke`. Then hand over to `mockup-analyzer`. Production assets have their own, separate approval.

## Exploring a look (style boards)
When the game has no style anchor and the person is still choosing a look ("what could it look like?", "show me some styles"), make two to four candidate **style boards** instead of a scene: one board per candidate (scope `style`), each in a different direction from the saved preset or from `presets/styles/` (`python scripts/gamearts_presets.py list`). Register each with `register-generated` as above, then compare them:
```text
python scripts/build_contact_sheet.py --game-root <game> --mockup <id>:<vNNN> --mockup <id>:<vNNN>
```
Show the picture named in `sheet` and ask **"Which letter feels closest to your game?"** On the answer, `approve-mockup` that board with the person's words and have `game-arts-project-setup` save it as `art_style.anchor`. A board that was not chosen is not rejected art: leave it generated unless the person asks to withdraw it. Policy: master *Art-style profiles* (style anchor, style exploration). The sheet is a review aid and is never registered.

## The image generator
The owner chooses the image generator once per game; it is saved as `image_generation` in `.gamearts/project.json` and applies to every image you make, mockups, panels and production art alike.
- **Read it first, every time** (`check-settings` prints it). `tool` is `built_in_image_gen` (the agent's own built-in image tool; in Codex that is `image_gen`, also called with `$imagegen`), `cli_image_gen` (Codex's command-line fallback), `connected_tool` (the connector or plugin named in `tool_name`) or `user_supplied` (the owner makes the pictures; never generate: ask for the file and `import-mockup` it). Apply `notes` to every call.
- **Missing:** ask once, with these four choices ("Which image generator should Game Arts use for this game?"), save the answer through `game-arts-project-setup`, and carry on. It is not a material setting: it never reopens approved art or the settings confirmation.
- **How to tell whether it is available:** look at your own tools in this session. `built_in_image_gen` means the agent has an image tool of its own (Codex's `image_gen`); Claude Code has none. A plugin or connector image tool is a `connected_tool`: it counts only when it is the one the setting names, and never stands in for the built-in tool.
- **Not available in this session:** say so and offer to change the setting, to take a picture the owner makes elsewhere, or to continue in the agent that has the tool. A short prose description of what you would paint may go in the message; nothing is saved or registered. Never use another tool in its place and never draw the picture yourself.
- **Built-in tool in Codex:** it saves under `$CODEX_HOME/generated_images/` with a name of its own; `register-generated` copies the picture into the game under the proper name, so the file in `$CODEX_HOME` is only the tool's copy. Its edit mode works on images visible in the conversation, so view the reference crop first and label each image's role.
- **Changing it** is the owner's decision ("use the Codex image generator for this game"): update the setting, verify with `check-settings`, and use the new tool from then on. Earlier mockups made with another tool stay valid.

## Everyday behavior
"Create a city mockup" -> render, show, ask. "Make the street wider" -> new revision. "Approved" -> promote the revision just shown, then decompose. "Use my existing approved UI mockup" -> reuse it. If saving fails or a tool is unavailable, report it and do not mark anything complete.

## After approval: production images
Never regenerate production art from a text description of the mockup. Use the approved image's real pixels: `mockup-analyzer` measures the region, `scripts/prepare_reference_crop.py` makes the crop packet, and the crop is attached to the image tool (*Reference crop and conditioning gate*). Produce one master first and compare it with the same crop before anything else. The clean static parent excludes every detached object (*Parent-artwork cleanup and separation gate*); reconstructed hidden areas are marked inferred and reviewed.

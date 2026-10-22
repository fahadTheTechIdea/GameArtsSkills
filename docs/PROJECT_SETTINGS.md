# Game Arts project settings — simple, persistent setup

Set up your game's visual preferences **inside Claude Code or Codex**. No programming or command line steps are required from the user.

## Start
Open your game project in Claude Code or Codex and say:

> Set up Game Arts for this game.

The agent asks a few friendly questions about the game's visual style, viewpoint, and animation needs. It offers recommended choices and can skip advanced technical options. Say **“Use recommended settings”** for the simplest setup.

## Review or change settings
Just say:

- **“Show my Game Arts settings.”**
- **“Change my game's art style.”**
- **“Update the Game Arts camera/viewpoint.”**
- **“Use the recommended settings for this project.”**

The agent reads existing settings before asking questions; it must not ask for information already saved.

## Where choices are saved
The agent writes the project's settings to:

`<game-repository>/.gamearts/project.json`

The file belongs to **each game**, not to the shared GameArtsSkills repository. Once saved to your game repository, later Claude Code or Codex sessions can reuse it when they can read the same project files. Commit it to version control for team-wide persistence.

**The wizard is a conversational agent skill**. The optional Python script in `scripts/setup_gamearts.py` is legacy/advanced internal tooling and is not part of the normal user experience.

## Advanced choices
World scale, terrain tile dimensions, frame counts, file locations and detailed engine import options use the active approved game profile unless a user explicitly wants to customize them. Do not overwhelm nontechnical users with these details.

## Fixed Game Arts requirements
Global requirements are never presented as optional checkboxes: mockup approval, detailed decomposition, exact opaque `#FF00FF` background for generated PNGs, measured atlas JSON per sprite sheet, applicable directional moving attachments, honest validation, individual files and no ZIP archives.

## Example conversation
**User:** Set up Game Arts for my project.

**Claude / Codex:** What art style would you like? Pixel art, illustrated, painted, or should I choose based on your references?

**User:** Pixel art.

**Claude / Codex:** What viewpoint? Elevated 3/4 (recommended for your current profile), top-down or side?

**User:** Elevated 3/4.

**Claude / Codex:** Great. I'll use the existing recommended scale and automatically choose animation methods. Save these settings?

**User:** Yes.

**Claude / Codex:** Saved to `.gamearts/project.json`. I'll reuse these settings for this game.

## Custom pipeline instructions

The project configuration holds structured defaults. Separately, users can add unrestricted, scoped art preferences through a conversational skill: `game-arts-custom-instructions`. These are saved as individual files in `<game>/.gamearts/instructions/`, read automatically for relevant tasks, and never used to weaken mandatory framework requirements. See [custom instructions](CUSTOM_INSTRUCTIONS.md).


## Settings are used in real image-generator prompts

Every image or image-edit request reads this game's existing `.gamearts/project.json` **before composing the prompt**, together with applicable active `.gamearts/instructions/*.md`, current approved mockup/asset references and any asset-specific profile. The agent inserts the actual selected style, camera, visual reference, size/scale and animation/output choices into the **tool call**; it must not just mention them in a plan. The style controls brushwork, outlines, texture density, pixels or vector edges and lighting as appropriate to that medium.

Supported selected styles include `pixel_art`, `hand_painted`, `illustrated`, `vector`, `rendered_2d` and `custom`. Optional style fields include `reference`, `palette_reference`, `outline_policy`, `shading_policy`, `texture_policy` and `pixel_density`. The world `object_camera` is project-specific. Optional `prompting` settings can record reference/camera locks and additional constraints. Existing game configuration remains valid without these optional fields.

User-approved source artwork and explicit changes outrank fallback defaults. If a saved style or viewpoint conflicts with an approved master, the agent flags it rather than silently changing existing art. Framework defaults are used only for genuinely missing values; Oilfield Days' oblique look is **not** a universal camera setting for all games.

## Selected style-aware reference crops

The built-in reference helper reads the existing per-game `art_style` and `world.object_camera`; an optional `art_style.ui_camera` sets a separate UI illustration view, while optional `world.ground_camera` describes terrain instead of rotating world objects. Existing configurations remain valid without the optional camera fields. Image prompts must use the resolved selected values, current approved visual reference and active scoped custom instructions.

In an existing approved mockup → production request, the agent automatically selects and crops the real reference image through the framework's `scripts/prepare_reference_crop.py` before calling an image tool. The normal user does not create crop JSON, enter pixel coordinates or run scripts. Do not reset saved project preferences to install this stage.


## Framework version synchronization is separate from game art settings

The optional trusted auto-updater stores its framework installation state in `.gamearts/system/agent-sync-state.json`, **not** in `project.json`. It may update installed Claude/Codex Game Arts skills and framework scripts on future local sessions, but must never reset or overwrite your selected art style, camera, custom instructions, approved mockups or generated assets. Enrollment is per game project and requires normal local hook trust permissions; see `README_INSTALL.md`.

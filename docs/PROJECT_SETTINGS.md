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

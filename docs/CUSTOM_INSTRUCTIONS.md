# Custom Game Arts Instructions

Store your own persistent Game Arts rules **per game**, through conversation with Claude Code or Codex.

## Example requests
- **"Always use soft morning lighting for this game."**
- **"Add a custom instruction for our UI artwork: keep icons simple."**
- **"Show me my custom Game Arts rules."**
- **"Change the rules for terrain details."**
- **"Stop using the old lighting rule."**
- **"For this one image only, use a darker palette."** (not saved)

The agent decides the appropriate scope, checks for duplicates or conflicts, and saves approved rules automatically. No manual file editing, CLI setup or Python command is required.

## Files saved in the actual game repository

```text
my-game/
  .gamearts/
    project.json                    # existing persistent game defaults
    instructions/
      visual-direction.md           # applies across the game
      terrain-detail.md             # only terrain-related tasks
      ui-readability.md             # UI tasks
      animation-preferences.md      # animation planning
```

Each file has short metadata (`id`, `title`, `scope`, `status`) and ordinary Markdown instructions. Version-control these files with the **game repository** so later sessions and collaborators use the same rules.

The Game Arts orchestrator should automatically load active relevant instructions **before** creating mockups, making detailed blueprints, generating assets, planning animations or validating outputs.

## Precedence
1. Higher-level safety/tool constraints and user-approved global Game Arts mandatory requirements.
2. Game's `.gamearts/project.json` base settings.
3. Active project-wide custom rules.
4. More specifically scoped custom rules for the relevant task (where compatible).
5. Approved mockups and asset profiles supply art-specific source facts and technical details; contradictions must be surfaced, not silently overwritten.

**Custom instructions cannot disable the compulsory production gates**, including mockup approval, detailed decomposition, fully opaque #FF00FF pixels in unused PNG regions, real measured atlas JSON per sprite sheet, applicable animated attachments, honest Godot validation and individual no-ZIP delivery.

## Examples of a stored rule

```markdown
---
id: ui-readability
title: UI readability
scope: ui
status: active
priority: normal
---
# UI readability

- Use larger readable labels for compact UI screens.
- Keep visual spacing consistent between controls.
```

## Notes
- The shared [GameArtsSkills](../README.md) repository contains the **skill implementation**, not your game-specific saved preferences.
- The agent must have write access to your game project to persist a new rule.
- The same game files can be used by both Claude Code and Codex, provided each tool is configured to read that repository.
- One-off requests are not saved unless the user asks.

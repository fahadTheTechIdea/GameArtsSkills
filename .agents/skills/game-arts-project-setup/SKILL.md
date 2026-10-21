---
name: game-arts-project-setup
description: Friendly conversational Game Arts project setup wizard inside Claude Code or Codex. Use for setup, configuration, changing settings, or when starting art work in a game with no project configuration. Ask simple questions, offer sensible defaults, and save selections in the game repository without asking the user to run commands.
---

# Game Arts Project Setup — In-chat Wizard

## Essential experience
**Run inside the currently active Claude Code or Codex chat.** The user should not need Python, terminal commands, JSON editing, git expertise, or a separate interface.

Be friendly, brief and understandable to nontechnical users. Ask **one clear question at a time**, or use a small native choice control when available. Avoid long technical questionnaires. Make recommended selections the default. Explain technical concepts in everyday language and reveal advanced settings only if requested or materially needed.

## Starting and existing settings
1. Find the target game project (not the shared skills repository) from the current workspace.
2. Read `<game-root>/.gamearts/project.json` if available. If found, use it automatically in normal game-art requests. For a configuration request, summarize it simply and ask what the user wants to change; never re-run the full wizard unnecessarily.
3. If missing, start a friendly, short project setup in this same chat. Don't stop ordinary brainstorming or early mockups solely because optional settings are absent.
4. Read the Game Arts master standard and `schemas/gamearts-project.schema.json` from the installed package before saving.

## Friendly starter questions
Ask only meaningful choices, typically:
1. **"What look do you want for your game?"** Pixel art (recommended if appropriate), illustrated, painted, vector/flat, rendered sprites, or other. If a style reference exists, use it.
2. **"What viewpoint should the game use?"** Elevated 3/4, directly overhead, side view, or other. If an approved project view already exists, keep it.
3. **"Will objects need multiple facing directions?"** Yes, no, or decide separately per object (recommended for mixed projects).
4. **"How should movement look?"** Let Game Arts choose the best method (recommended), or prefer frame animation / engine movement.
Only ask about terrain dimensions, pixels-per-meter, exact frame counts, folders, shaders or other expert settings if a chosen answer actually requires it. Otherwise use the currently approved game profile as default. Mockup scope is inferred from the next task rather than forcing an up-front question.

Offer **Use recommended settings** as an easy path whenever possible.

## Confirmation and saving
1. Summarize selections in plain language (e.g. “Pixel art, elevated viewpoint, automatically chosen animations”).
2. Ask for a concise confirmation before saving new or materially changed settings; a clear user request to save these exact answers counts as confirmation.
3. Use Claude Code's or Codex's normal project file tools to create/update `<game-root>/.gamearts/project.json`. **Do not ask the user to run scripts or commands.**
4. Preserve existing settings, unknown user-owned fields, approvals and asset-specific profiles; update only selected fields.
5. Validate JSON structure and required fields with available agent tools; internal validation scripts may run automatically if supported, never as a user prerequisite.
6. Read the saved file back; confirm in simple terms what was saved and where. If tools cannot write the file, clearly state that no settings were saved.
7. Use these settings automatically in every future Game Arts request in the same game project, provided the agent can access its files.

## Mandatory standards (not choices in the wizard)
- Mockup-first explicit approval for new final artwork; comprehensive detail decomposition afterward.
- Exact opaque `#FF00FF`, RGB (255,0,255), alpha 255, for unused pixels in delivered PNGs.
- Matching measured JSON atlas for every sprite sheet.
- Locked reference masters, correct modular animation and animated directional attachments where applicable.
- Native-scale world geometry and profile-specific directions/frames.
- Honest Godot/technical validation; no ZIP-only delivery.

## Usability rules
- Default to doing the work, not teaching users command syntax.
- Never present the raw JSON unless the user requests it.
- Don't ask questions whose answers are already in the current project configuration or approved references.
- Show the user only the decisions they can meaningfully make.
- Provide plain-language options to view settings, change art style, reset optional choices, or revisit setup.
- Never claim settings persist when they have not been written successfully.

## Optional custom instructions
After saving the basic game profile, mention once that the user can say **“Add a Game Arts instruction”** to customize the pipeline for this game. Do not force a separate questionnaire. Use the `game-arts-custom-instructions` skill to persist approved rules in `.gamearts/instructions/`, not in `.gamearts/project.json` or the shared skills repository.

## When to launch
Use this conversational wizard when the user requests project setup/changes or a truly necessary project-wide setting is unknown. **Do not require setup before creating an initial mockup.** On first normal art request, the orchestrator may use established defaults and route to game-arts-mockup-creator instead.

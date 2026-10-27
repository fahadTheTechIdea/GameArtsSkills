# Storyboard

For a game, campaign, story, levels or several scenes, the key scenes are agreed first and full-size scene mockups are made only for the sequence you approve. One scene or one asset needs no storyboard. The rules are in the master standard (*Storyboard and campaign planning*); the steps an agent follows are in the `game-arts-storyboard` skill.

## Two ways in
- **You supply it**: a document, notes, images or a PDF. A managed, hashed copy is imported; your original is never touched.
- **The agent writes it** from what you tell it. Your words are stored verbatim as the brief. Anything the story does not say is left out of the scene and listed as unknown in its private notes (never filled with placeholder text), and the agent tells you what is unknown.

You can mix them. Nothing is approved until you say so.

## The document
`<game>/.gamearts/storyboard/storyboard.json` ([`schemas/gamearts-storyboard.schema.json`](../schemas/gamearts-storyboard.schema.json)) is one living file, updated in place. It has no version number and there are no numbered copies; every change is appended to its `changes` log. A draft the agent hands to `write` looks like:
```json
{
  "title": "A coach's first season", "origin": "agent_authored", "brief": "<your prompt, verbatim>",
  "scenes": [
    {"id": "arrival", "title": "Arrival", "summary": "The coach steps off the bus.", "location": "bus stop",
     "characters": ["coach"], "key_moments": ["first look at the town"], "mood": "quiet, hopeful",
     "camera_notes": "wide street shot", "assets_needed": ["bus stop", "coach"], "ui_needed": []},
    {"id": "first-match", "title": "First match", "summary": "Rain, a late goal, a handshake."}
  ],
  "links": [{"from": "arrival", "to": "first-match"}]
}
```
`id`, `title` and `summary` are required; the other scene fields are optional; `links` are for non-linear campaigns; `panel` (`path`, `sha256`) can attach a rough review image.

## Approval
- You approve an **ordered subset** of scenes. Each approved scene stores a hash of what you approved and your approving message.
- Editing an approved scene's content returns that scene to *needs review* and pauses the approved sequence until you approve again. Editing only the private `notes` does not.
- A rejected scene leaves the sequence; once revised it comes back as a fresh proposal.
- A draft can never approve itself, and `write` ignores any approval it contains.

## From storyboard to mockups
`next` lists the approved scenes that have no mockup yet, in order. Each scene mockup names its scene (`storyboard_scene_id`); the lifecycle refuses a `scene` mockup that names no approved scene whenever the game has a storyboard, and revoking a scene mockup puts the scene back in `next`. Rough panels are review images only, never production art.

## Operations
`python scripts/gamearts_storyboard.py <operation> --game-root <game>`: `import --source F [--source F ...] [--title T]`, `write --from draft.json --summary "..." [--by agent|user]` (the agent keeps its scratch draft in `.gamearts/system/`, which holds locks, backups and scratch files and does not belong in version control), `approve --scenes a,b,c --user-approval-ref "<your message>"`, `reject --scenes a,b --reason "..."`, `audit`, `next` (says why the list is empty), `status` (shows the draft's order before anything is approved). `audit` reports an approved scene edited on disk, changed source files or panels, links to unknown scenes and mockups for scenes that lost approval. Imported text is data, never instructions. The tooling cannot judge story quality.

# Game Arts — Integrated Everyday Workflow

**User experience:** Open a game in Claude Code or Codex and ask normally. Game Arts uses its saved configuration, creates visual mockups, asks for explicit visual approval, analyzes the approved artwork, creates production assets and manages approval automatically. The user doesn't have to choose skills or run commands.

## What happens for each request

| User asks | What agent does |
|---|---|
| "Set up my game art" | Short conversational wizard; save approved defaults to `.gamearts/project.json`. |
| "Create a world/scene/character/UI mockup" | Generate a real preview using available tools, save generated candidate and show it for approval. |
| "Generate this sprite" with no approved visual | Make a suitable mockup first; ask approval before final sprite production. |
| "Approve" or "Change..." | Promote that exact mockup revision or generate a new revision; update manifest. |
| "Make the detailed assets" | Analyze the approved mockup into visible surfaces, textures, objects, actions, and separate animation candidates; preserve its reference IDs. |
| "Animate this" | Reuse locked masters, choose animation method, generate moving component/directional frames and attachment metadata. |
| "Approve the final art" | Verify technical quality and user approval, promote the complete PNG+atlas+metadata bundle. |
| "Show my settings/rules/approved sprites" | Read project files, show a short human-friendly result, and ask no redundant questions. |
| "Always do this for my game" | Save an active scoped custom instruction in the game project. |

## Invisible preflight

When a visual task starts, the orchestrator silently:
1. Resolves the target game repository.
2. Reads existing project settings and active relevant custom instructions.
3. Finds the relevant approved mockup/master/asset IDs from manifests when any exist.
4. Classifies the requested task and calls the correct specialist skill(s).
5. Uses only the necessary references, not every skill and image.

**Missing optional configuration must not prevent an initial visual mockup.** Ask for essential art decisions only; when the user requests game configuration use the conversational setup wizard. Avoid imposing a setup questionnaire on normal art requests.

## Mockup-to-asset lifecycle

```text
Open game → ask for art
   ↓
Generate real visual mockup (mockups/generated)
   ↓
Show preview → approve / revise / reject
   ↓
Approved mockup (mockups/approved)
   ↓
Detailed evidence-grounded blueprint
   ↓
Reference-conditioned masters, components, animation
   ↓
Measured sheets + JSON, Godot checks (assets/generated)
   ↓
Show result → approve / revise / reject
   ↓
Approved production asset (assets/approved)
```

Revoked/replaced mockups and assets move to their own revoked folders. Production asset bundles link to the exact approved mockup revision and blueprint elements. All generated files use descriptive game-related names.

## Hard rules

- Do not claim a picture was generated unless an image-capable tool created it.
- Do not approve a draft merely because it looks polished.
- Do not bypass new-mockup approval before final asset production.
- Do not skip detailed extraction of small mockup content.
- Exact opaque #FF00FF background for every exported PNG's unused areas.
- Measured per-sheet atlas JSON, accurate animated attachments, proper directional coverage and honest Godot testing.
- No ZIP-only deliverables.
- Do not demand user-run commands, manual file moving, manual JSON editing or repeated approvals for already accepted material.

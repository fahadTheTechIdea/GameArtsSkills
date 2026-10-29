# Game Arts — everyday workflow

Open your game in Claude Code or Codex and ask normally. Game Arts uses the game's saved settings, shows real mockups, asks for your explicit approval, breaks the approved art down, builds measured production files and manages approval. You never choose skills, run commands, move files or edit JSON. The rules are in the master standard (`GAME_ARTS_MASTER_STANDARD.md`); this page shows the flow.

## What the agent does first (silently)
1. Finds the game project and reads its settings and active custom instructions.
2. Finds the approved mockups, masters and assets the request relates to.
3. Classifies the request and calls the right specialist skill; loads only what it needs.

Missing optional settings never block a first mockup. Generating, registering or approving a mockup needs owner-confirmed settings (a short summary and one "yes").

## The flow
```text
a game, campaign or story? -> storyboard -> approve scenes (ordered)
        |
choosing a look? -> 2-4 style boards on one sheet -> you pick a letter -> style anchor
        |
Real mockup (mockups/generated) -> approve / revise / reject
        |
Approved mockup (mockups/approved) -> detailed blueprint, coverage audit
        |
Scene or world: detect (draft) -> extract objects -> evaluate / remove (draft)   [extract must run before any asset is registered]
        |
Reference crop -> one master -> compare with the crop -> approve master
        |
Clean static parent + separate parts -> components, key poses, directions
        |
Variants (team colour, season, night): recolour the approved frames by a fixed map -> a new asset, reviewed and approved like any other
        |
Measured sheets, atlases, bundle (assets/generated) -> mechanical and style checks, animation previews
        |
Review boards for composite art -> your approve / revise / reject
        |
Approved asset (assets/approved)   (rejected or replaced -> revoked)
```
Revoked mockups and assets keep their history and are never used as a source. Every asset links to the exact approved mockup revision it came from.

## What you'll be asked
- To approve a **mockup revision**, a **storyboard sequence**, a **master**, and the **final art**: each is a separate, explicit decision about the exact thing shown.
- To confirm the settings once, and to trust the update hook if you enable automatic updates.
- Nothing else, unless a choice would change the result.

## If the main image generator is unavailable
If you saved a fallback generator for the game, the agent may use it for that picture only, and says why. The reason is stored with the picture. With no fallback saved, it stops and tells you which pictures are waiting.

## Declaring AI use
Ask "What do I have to declare about AI?" for a plain summary built from what was recorded. It is not a statement of what any store requires.

## What the agent will not do
Claim a picture was made without an image tool; approve a draft because it looks polished; skip mockup approval for new art; use a text description instead of the real approved pixels; ask an image model for a finished sprite sheet or atlas; leave a prop painted into the base while also exporting it; reuse a rejected version; claim an engine test it did not run; deliver only a ZIP; or ask you to run commands.

## Bring your own mockup
Point the agent at artwork you made elsewhere. A managed copy is imported, your original stays untouched, and an approved version becomes the production reference. If you say it is already approved, it is recorded as approved and not recreated.

## Seeing your art
After every change Game Arts rebuilds one offline page, the art report (`.gamearts/system/report/index.html` in your game). It shows your settings in plain words, every mockup and asset with its status, a preview (the magenta key colour is shown as a checkerboard there; your files are never changed) and the words you approved it with, and what happens next. Open it in any browser; it needs no internet and is kept out of version control. Say "Show me my art" and the agent points you to it.

## Keeping Game Arts current
After a one-time trusted enrollment, each Claude Code or Codex session start checks the framework's `main` branch and updates both agents' skills, scripts, schemas, docs and the master. Your settings, instructions, storyboard, approved mockups and assets are never touched. A framework file you edited is kept and reported. A change on GitHub cannot reach a computer that is offline; it applies at the next trusted session or when you say "Update my installed Game Arts skills now". See `README_INSTALL.md` in the Game Arts repository.

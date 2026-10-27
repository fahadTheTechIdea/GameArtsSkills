# Game Arts — glossary

The agent explains a word the first time it uses it. This page keeps the plain meanings in one place. The exact rules are in the master standard (`GAME_ARTS_MASTER_STANDARD.md`).

| Word | What it means |
|---|---|
| **Mockup** | A picture of what you want the art to look like, made before any final art. You approve it before anything is built from it. |
| **Approval** | Your explicit yes to one exact picture or set of files. Nothing is approved by silence, and a change needs a new yes. |
| **Revision** | One version of a mockup or asset (`v001`, `v002`). Older ones are kept; a rejected one is never used again. |
| **Generated, approved, revoked** | The three states of any revision: made and waiting for you, accepted by you, or withdrawn with a reason. |
| **Storyboard** | The list of scenes of a game or campaign, agreed before scene pictures are made. |
| **Look (style preset)** | A ready set of choices for how the art is drawn: pixel art at a given era, cartoon, painted, flat vector and so on. |
| **World kind** | Whether your game has a tile map (`grid_world`), free open space (`free_world`), scrolling layers (`layered_scene`) or no ground at all (`screen_space`). |
| **Viewpoint (camera)** | How the world is seen: straight down, from above and a little in front, from the side, or isometric. |
| **Facing directions** | How many ways a character can face in the art: eight, four, left and right, or one. |
| **Tile** | One square (or hexagon) piece of ground that repeats to make a map. A **tileset** is a family of tiles that fit together. |
| **Parallax layer** | One layer of a scrolling background that moves slower or faster than the rest to give depth. |
| **Sprite sheet** | One picture holding all the frames of a character or object in neat cells. |
| **Atlas** | The small data file that says where every frame sits in a sheet, where its pivot is and how long it shows. It is measured from the pixels, never guessed. |
| **Pivot** | The point of a frame that stays still, such as the feet of a character, so frames line up when they play. |
| **Anchor** | A named point on a frame where another part attaches, such as a hand where a tool is held. |
| **Key colour (`#FF00FF`)** | The exact magenta that fills every unused pixel in a delivered picture. Your game turns it transparent when it imports the picture. |
| **Clean parent** | A base picture with every movable or removable part taken out, so those parts can be separate sprites. |
| **Review board** | An annotated picture made for you to inspect a cutout before you approve it. It is a checking aid, not game art. |
| **Bundle** | All the files of one asset kept together: pictures, atlases, data and checks. |
| **Image generator** | The tool that makes pictures for this game. You choose it once; the agent never swaps it. |
| **Art report** | One page that opens in any browser and shows your settings, every mockup and asset with its status and your approval words, and what happens next. It is rebuilt after every change and is never part of your game. |
| **Next step** | The plain sentence that ends each stage: what exists now, what the agent needs from you, and what comes next. |
| **Style board** | One picture that shows the look of the whole game at once: a hero piece, colour swatches, an outline and a shading sample, a tile and a piece of interface. |
| **Style anchor** | The style board you approved as your game's look. Every new piece of art is made with it beside the reference, so everything matches. |
| **Contact sheet** | Several candidate pictures side by side under letters, so you can say "B". It is for choosing only and is never game art. |
| **Palette** | The fixed set of colours your art uses, saved from an approved picture so later art can be checked against it. |
| **Style check** | A measurement of the pixels of a sheet against your look: palette, colour count, pixel size. It finds mistakes; it cannot tell you whether the art is good. |
| **Snapping** | Bringing pixel art that came back drawn too large down to its real pixel size. You get a labelled copy to look at; the original stays. |
| **Preview strip / GIF** | A way to watch an animation: its frames side by side and a looping picture. For looking only; never game art. |
| **Tag** | A name for a run of frames in a sheet ("walk", frames 0 to 5), with how it plays: forward, backward or back and forth, and how many times. |
| **Trim and pack** | Cutting each frame's cell down to its art and fitting the cells together in rows, so a sheet wastes less space. |
| **Nine-slice** | A picture cut into nine parts by four margins so its corners stay the same while the middle stretches, for panels and buttons. |
| **Control state** | One look of a button or slider: normal, hover, pressed, disabled or focus. A button is complete when it has all of its states. |
| **Layout (tileset)** | How a tileset's tiles fit together: which tiles it needs so that any neighbours can meet without a gap, such as 16 corner tiles or 47 blob tiles. |
| **Engine-ready copy** | A copy of an approved sheet whose magenta background has become real transparency, made for the engine to import. It is derived, never approved, and removed if the art is withdrawn. |
| **Engine profile** | The notes for the engine or tool you use: how its settings should be set for your art style and what its terms are called. It never changes your art. |

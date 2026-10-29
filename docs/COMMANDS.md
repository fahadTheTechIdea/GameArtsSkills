# Game Arts — everyday commands

No command syntax is needed. Say what you want, in plain words, inside Claude Code or Codex while working in your game project. The agent picks the skills and handles every file. The rules behind each request are in the master standard (`GAME_ARTS_MASTER_STANDARD.md`); this page only lists what you can say.

## Start and personalize
| Say | What happens |
|---|---|
| "Set up Game Arts for this game." | A few friendly questions; the confirmed choices are saved to `.gamearts/project.json`. |
| "Which do you recommend?" | The agent says which option it would pick and why; you still choose, because every setting is your answer. |
| "I'm making a card game / a platformer / a farming sim." | The agent starts from the matching [genre recipe](GENRE_RECIPES.md): the kind of world, suitable looks, facing directions and the art to make first. |
| "Show me the looks." / "Use the 16-bit pixel look." | Lists the ready-made looks that suit your game and saves the one you pick as your starting point. |
| "We use <engine or tool>." / "Change the engine." | Saves the engine you use (any name is fine); you get its import advice if a profile for it is installed. Your art and approvals are not affected. |
| "Start from my other game's choices." | Marks the engine, image generator and look of a game folder you name as the current choice in each wizard question; you still pick each one. |
| "Show my game art settings." | Your saved settings, summarized. |
| "Change my game's art style." | Only that setting changes, after your confirmation. |
| "Always make the UI icons simple." | A scoped custom instruction is saved in the game project. |
| "Show / change / stop using my custom art instructions." | Lists, edits or deactivates saved rules. |
| "For this one image only, use a darker palette." | Applied once, never saved. |

## Storyboard (a game, campaign, story or several scenes)
| Say | What happens |
|---|---|
| "Create a storyboard for my game." | The agent drafts the key scenes from your prompt, shows the list, and waits for you. |
| "Here is my storyboard." | A managed copy of your document is imported and turned into scenes; your original is untouched. |
| "Change scene 3 so it happens at night." | The scene is edited; if it was approved it needs your approval again. |
| "Approve scenes 1, 2 and 5." | Those scenes, in that order, become the approved sequence. |
| "Make mockups for the approved scenes." | One scene mockup at a time, in order, each through the normal mockup approval. |

## Mockups
| Say | What happens |
|---|---|
| "Create a mockup of my world / a city scene / this character / a UI screen." | A real preview is rendered with your chosen image generator (you are asked once if none is saved), saved as a generated mockup and shown for approval. |
| "Use the Codex image generator for this game." / "Change the image generator." / "I will make the pictures myself." | The choice is saved in your game settings and used for every image from then on; earlier art stays valid. |
| "If Codex is not available, use <another tool>." | Saved as this game's fallback generator. It is used only when the agent says why the main one cannot be used, the reason is kept with the picture, and nothing else is ever substituted. "No fallback" is a valid answer. |
| "Here is a mockup I made. Use it." | A managed copy is imported as generated and shown for your approval. |
| "I already have a sprite sheet." / "Use my art as the look of the game." | You say how it is laid out (a grid, a cell size, or the data file Aseprite wrote beside it) and confirm it is yours. The sheet is read, never changed: its transparency becomes the magenta background, its frames are rebuilt into a checked sheet, and it is registered for you to approve. If you want it as the look of the game, it is also offered as the style anchor for you to confirm. |
| "Here is my already approved mockup." | Imported as a managed copy and recorded as approved with your statement as the reference; nothing is recreated. Your game's settings must be confirmed first; if they are not, the agent shows them and asks once. |
| "Show me a few ways it could look." / "Compare these looks." | Two to four style boards are made with your image generator and shown on one sheet under the letters A, B, C. The sheet is only for choosing; it is not game art. |
| "I pick B." / "Use this as our look." | That board is approved with your words and saved as your game's style anchor. The others stay as they are unless you withdraw them. |
| "Make a palette from our style board." | The colours of that approved picture are saved as the game's palette, so later art can be checked against it. |
| "Make the pavement wider." | A new revision; the old one is kept. |
| "Approve this mockup." / "Reject this mockup." | The exact revision just shown is promoted, or moved to revoked with the reason. |
| "Show my approved mockups." | The current approved revisions. |

## Production art
| Say | What happens |
|---|---|
| "How much work is this?" / "What will it cost?" | A plan card before anything is made: the lane (quick, standard or full), about how many pictures, which approvals you will be asked for, and who is billed for the pictures. It never states a price it does not know. |
| "Generate game art from the approved mockup." | The mockup is broken down in detail; production candidates are tied to that exact revision. |
| "Create a sprite sheet for this object." | Native-size art with the directions and states the asset needs, assembled into a measured sheet and atlas. |
| "Animate the moving parts." | Components, directional art, animated mounts and a validated bundle. |
| "Name the walk and the hit in the sheet." / "Make the walk loop and the hit play once." | Named runs of frames (tags) are written into the sheet's data, each with how it plays; another tool can read them. |
| "Pack the sheet tighter." | Each frame gets a cell sized to its art (never cutting off its pivot) and the cells are packed in rows. The default grid is unchanged unless you ask. |
| "Make the buttons with all their states." / "Make the panel stretch." | Frames for normal, hover, pressed, disabled and focus, checked to have the same size and the same stretch margins; a stretching panel gets its four margins. |
| "Make the water move." / "Animate the lava tile." | The tile gets extra frames and a duration for each; the frames take the tile's labels, are held to the same edges, and the Tiled export carries them. |
| "Make a tileset for grass and water." | The tiles for the layout you choose are collected into a sheet that is checked for missing tiles and for tiles that do not line up. See [TILESETS.md](TILESETS.md). |
| "Make a red team version." / "Make a night / winter version." / "Recolour it with these colours." | The approved frames are recoloured by a fixed colour-for-colour map (or two palettes of the same size paired by position). Any colour not in the map stops the run and is named; nothing is overwritten and the originals stay as they are. The variant is a new asset you review and approve like any other, and it records the asset it was made from, so withdrawing that asset names the variant. |
| "Make the store icon / the Steam capsule / key art." | A normal screen-space mockup, approved like any other. The agent reads the store's current size list from the store's own page first and tells you which page it used; the framework does not check the size for you. |
| "Make this glow additive." | The sheet says how it should be blended; your game applies it. |
| "Make the engine-ready files." | Copies of the approved sheets with real transparency instead of the magenta background, for your engine to import. Derived files, not new art. |
| "Export it for Aseprite." / "Export the tileset for Tiled." | A data file in the shape that tool reads, written beside the sheet. Best effort until you have opened one in the tool. |
| "Show me how the walk plays." | Each animation is drawn as a still strip and a looping GIF, with the empty background shown as a checkerboard. It is a way to look, not game art. |
| "Does the loop jump?" / "Is anything cut off?" | The motion is measured: the jump where the loop restarts, a foot that drifts, art touching the edge of its cell, repeated frames. It informs; it does not decide for you. |
| "This pixel art came back too big." / "It looks blurry." | The pixel size is measured; if the picture was drawn large, a clean native-size copy is made for you to look at. Your original is kept, and a picture with no regular pixel grid is refused with the reason. |
| "Does this match our palette?" | The sheet's colours are compared with the game's palette and colour limit. A failed check blocks approval and says what was measured; a check that cannot be measured says why. |
| "Make the workshop into separate usable sprites." | Every movable or removable piece is removed from the base and exported on its own. |
| "Extract everything in this scene." / "Pull out the plants, cars and signs too." | In a scene or world every distinct object is separated, not only what moves: people, vehicles, buildings, plants, signs, street furniture, lamps, fences, gates, doors, windows, props, streets, car parks and parts fixed to a building. Each gets a class, and the analysis ends with a sweep that says, for every class, which objects it found or where it looked and found none; an approved scene is refused until the sweep is complete. A detection model (optional extra) can find them for you and give each a mask; the result is a draft you review before relying on it. Open ground and water stay tiles or materials. Once the scene is approved the cut-out is a recorded step: no asset is registered from it until the objects have been extracted. |
| "How good was the detection?" | The draft is measured against a blueprint you reviewed: what it found, what it missed, what it invented. It never overwrites your reviewed blueprint. |
| "Remove the objects from the scene." | A draft clean parent is made from the blueprint's masks, after the extraction. The removed pixels are inferred, so it goes through the cleanup checks and your review before it counts. |
| "Check the separate sprites are actually clean." | Cleanup checks plus review boards for you to look at; one approve or revise decision. |
| "Approve these three." / "Approve all of the sheets you showed me." | Each named revision is approved in turn on your words, each with its own checks. Anything you were not shown, or that fails its checks, is left as it was and named. |
| "Approve this version." | After you reviewed that exact revision, the whole sprite, atlas and metadata package is promoted and audited. |
| "Reject this version because the scale is wrong." | The whole package moves to revoked with the reason and is never used again. |
| "Show my approved / generated / revoked artwork." | Read from the manifests. |
| "Restore the earlier version." | It comes back as generated and needs a fresh approval. |

## See your art and check your setup
| Say | What happens |
|---|---|
| "Show me my art." / "What's next?" / "What can I do now?" | The offline art report is opened or rebuilt: your settings in plain words, every mockup and asset with its status, a preview and your approval words, and the next steps. It is built only from the records, and it is rebuilt after every change. |
| "Check that Game Arts works on this computer." | A read-only check of Python, the two packages, the folders, your settings and your engine profile, with the fix for anything missing. Nothing is installed without your go-ahead. |

| "What do I have to declare about AI?" | A read-only summary of which approved pictures were made with an image tool (which one, which model) and which you supplied, and what it cannot know. Whether a store asks for it is the store's current rule; check its page. |

## Keep the framework current
| Say | What happens |
|---|---|
| "Enable automatic Game Arts updates for Claude and Codex." | The one-time updater bootstrap; you are asked to trust the session-start hook in each tool. |
| "Update my installed Game Arts skills now." | The updater runs once in the open session and reports what changed or what failed. |

## Where files live
Inside each **game** repository, never this framework repository:
```text
.gamearts/
  project.json
  instructions/
  storyboard/storyboard.json
  outputs/mockups/{generated,approved,revoked}/   outputs/assets/{generated,approved,revoked}/
  outputs/manifests/{mockups.json,assets.json}
```
Install notes: `README_INSTALL.md` in the Game Arts repository.

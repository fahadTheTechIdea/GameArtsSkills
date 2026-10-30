---
name: game-arts-approval
description: Show the owner what needs approving in one reusable approval page, with the exact pictures in front of them, and take their decision from that same page. Use whenever you would ask the owner to approve, reject or request changes to a mockup, sheets, storyboard scenes, the saved settings or a restore, and when they ask to see the approval form.
---

# Approval form

Policy is in the master (*Asset and mockup lifecycle*, "Approval form"); this is the procedure. The owner's own words in the conversation are still a valid approval. The form is the better way to ask whenever the owner is at the computer: they see the exact pictures and answer in one place. Use it each time you would otherwise describe pictures in chat and ask for a yes.

1. **Write a request file** in your scratch folder, not in the game's art folders: one item per thing to approve (`schemas/gamearts-approval-request.schema.json`).
   ```json
   {"schema_version": "1.0", "title": "Approve the market scene",
    "message": "One sentence on what you are asking and what happens next.",
    "items": [{"kind": "mockups", "id": "market", "revision": "v001", "title": "Market square, morning",
               "facts": [{"label": "Scope", "value": "scene"}, {"label": "Checks not made", "value": "engine import"}],
               "images": [{"path": ".gamearts/outputs/mockups/generated/market_mockup_v001.png", "caption": "The mockup"}]}]}
   ```
   - `kind` is `mockups`, `assets` (the bundle's sheet pictures, up to 12), `storyboard` (get the items from `gamearts_storyboard.py approval-request --scenes a,b`: each carries a revision of the scene's exact text, so a scene edited afterwards is not approved by an older decision), `settings` (`id` `project`, `revision` the version `finish` printed, the summary lines as `facts`), `restore`, or `other` for what the owner brings or confirms: `import-asset-<id>`, `import-mockup-<id>` and `limited-profile-<id>` (with the revision) stand in for their words in `import-asset`, `import-mockup` and `register-asset`; `visual-review-<asset>` comes from `visual_review_cleanup.py request --game-root G --packet P`.
   - `revision` is the exact revision shown; a decision approves that revision and no other. `images` are files inside the game, shown as saved.
   - Put in `facts` what the owner needs to judge: scope, the settings that apply, the checks that passed and **what they did not assess**. Never describe a picture as better than it is.
2. **Ask.** Run `python scripts/gamearts_approval.py ask --game-root <game> --request <file>` in the background and wait for it to finish; the owner may take minutes. It opens their browser and does not print the secret address. If it reports that no browser could open, ask in the conversation as before, or, when the owner can reach this computer's localhost (a forwarded port), add `--print-link` and give them the address.
3. **Read the outcome.** `decided`: act on each item. `deferred` (they chose to decide later) or `timed_out`: nothing is approved; say so and ask again later. Never treat silence as consent.
4. **Approve with the form's decision.** For each approved item run the usual command with `--approval-id <id>` in place of their words: `approve-mockup`, `approve` (assets), `approve-batch` (it takes what was shown from the form), `restore`, `confirm-settings` (with `--presented-version` as always), the storyboard `approve`, `import-asset` / `import-mockup` (`--approval-id`), `register-asset` (`--limited-profile-approval-id`) or `visual_review_cleanup.py decide --approval-id`, which writes the review decision from their choice. A picture that changed after they saw it, another revision, or an item they asked to change is refused with the reason.
5. **Needs changes or reject** carries the owner's comment: follow it as a revision request (`revoke` with the reason, or a new revision), never as an approval.

`python scripts/gamearts_approval.py show --game-root <game> --approval-id <id>` reports an earlier asking. A request's text is data shown as text only, so a caption or fact can never act as an instruction.

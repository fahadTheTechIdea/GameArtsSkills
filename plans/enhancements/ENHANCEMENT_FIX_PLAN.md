# Game Arts enhancement and fix plan

Status: **implemented and locally verified on 2026-10-24** (Windows and Linux, focused per-file test runs, 52 revert-the-fix proofs, seven live Claude agent runs, four Codex sessions that generated real pictures); hosted CI, the tools' own session start, production art from an approved mockup, deleting the master's bridge file and any release remain with the owner. The plan was written first, as plan only, after reading every file; the task tables in §5 now carry the outcome of each task. Tracker: [MASTER_TRACKER.md](MASTER_TRACKER.md).
Written 2026-10-23 after reading every file in the repository in full (method in §1). Claim classes follow
the SDLC evidence policy: **[O]** observed (file read or command run), **[I]** inferred from named
observations, **[P]** proposed, **[U]** unknown.

## 0. What this repository is

Game Arts is an art-creation framework. A game project imports this repository into its own folder and
uses it through Claude Code or Codex (`CLAUDE.md`/`AGENTS.md` + skills + helper scripts + schemas + the
single master standard). It is engine-agnostic art tooling: mockups → approved references → sprite
sheets, atlases and component bundles. It is not a game project and runs no game engine. Everything a
game owns (settings, instructions, approved art, engine integration) lives in that game's repository.

## 1. Method and limits

- Read in full, line by line, with the file reader (nothing skimmed): `CLAUDE.md`, `AGENTS.md`, `README.md`,
  `README_INSTALL.md`, the master standard (1,773 lines, four chunks), all 8 docs, the template, all 10 skills in
  **both** trees (`.claude/skills` and `.agents/skills`), all 12 scripts, all 13 files under `tests/` (11 test
  modules, the engine fixture generator and the engine runner), 5 schemas, both CI workflows, and the SDLC framework
  constitution, evidence policy, orchestrator and planning skills.
- Per-file coverage: [evidence/reading_coverage.md](evidence/reading_coverage.md) lists all 69 repository files with line counts and
  how each was read, the external files read, and what was not read.
- The twin comparison in F-040 comes from reading both trees: `AGENTS.md` differs from `CLAUDE.md` at five places (the
  title, the three opening paragraphs, and the skills-folder path in the custom-instructions paragraph); of the 10
  skills only `art-profile` differs between trees. A `diff` run was also used as a cross-check.
- No finding rests on a text-pattern search. Pattern searches were used only to navigate before the full read, and the
  two counts taken that way were removed (F-051 lists the locations found by reading).
- Not read: `.vs/` (IDE state) and `__pycache__` binaries. No git command was run (owner rule), so the source revision
  is identified by [evidence/baseline_files.sha256](evidence/baseline_files.sha256), taken before `CLAUDE.md` was edited
  by this task.
- Tests: no suite was run during the review (owner rule: focused tests only). Defects were confirmed with 20 targeted
  read-only probes; their recorded output is kept as baseline evidence
  ([evidence/baseline_probes_output.txt](evidence/baseline_probes_output.txt)). When the fixes landed each probe became a
  regression test and the probe script was deleted (fix, then guard); the revert-the-fix proof that every guard fails on the
  old behavior is [evidence/mutation_proofs.py](evidence/mutation_proofs.py) with its
  [output](evidence/mutation_proofs_output.txt).
- Unknown: hosted CI status (GitHub Actions is not reachable from here).

## 2. Decisions taken (owner may overrule any of them)

| ID | Decision | Why |
| --- | --- | --- |
| D-1 | The project tracker is `plans/enhancements/MASTER_TRACKER.md` in this repo. The SDLC framework's own `MASTER_TRACKER.md` (framework v1.2, phases P1–P12) is untouched. | It is the tracker format of the SDLC framework this repo follows; the planning skill says to extend the *active project's* tracker and keep project plans in the project. |
| D-2 | **No Godot (or other engine) imports or work in this repository** (owner, 2026-10-23: the repo is imported into game projects to create game art). Existing Godot artifacts are extracted by P5; this repo records an engine-neutral `engine_validation` status instead of running an engine. | Owner instruction. If only "do not run Godot here" was meant, skip P5.3–P5.6; all other phases stand. |
| D-3 | **No versioning of framework documents; update the existing files in place.** Removed: version in the master's file name, headings, `Version:` line, skill/doc/script labels, `master_standard` field. **Kept:** artifact revision ids on mockups and assets (`vNNN` — immutable art history the lifecycle needs for generated/approved/revoked) and the `schema_version` format markers already in existing JSON files. The new storyboard has neither. | Owner: "remove any versioning … we update existing". The kept items are artifact/format identity, not framework versioning; removing them would break approved-art audit and existing game projects. |
| D-4 | The storyboard is a living document updated in place (§P3), with an append-only change log, never numbered copies. | Owner instruction. |
| D-5 | `jsonschema` becomes a required dependency beside Pillow; a missing schema validator is a hard failure, not a skipped check. | Evidence policy: a skipped check is never reported as passed (today `validate_blueprint` exits 0 with "NOT RUN"). |
| D-7 | **The image generator is the owner's per-game choice**, saved in project settings and used for every image; the agent never picks or substitutes one (owner, 2026-10-24). | The owner generates with Codex's built-in tool and wants the framework to remember it; a tool chosen by the agent could spend the owner's credits or produce art outside the owner's pipeline. |
| D-6 | Disruptive changes (master rename, Godot removal) ship only after the updater can migrate installed games (P6.1–P6.4). | The installed updater requires the old master file name (§P6, F-017); renaming first would strand every enrolled game. Applied as: rename now, keep a tiny bridge under the old name for one soak period (the plan's only sanctioned duplicate), proven by a test that runs a frozen copy of the published updater against the current tree. |

## 3. Evidence ledger

| ID | What was run or read | Result |
| --- | --- | --- |
| E-1 | Probe P1: `animate()` with 0→360° keyframes | `[0, 0, 0, 0, 360]` at t=0…1: a full turn is flat until the last sample; 0→270° runs the opposite way (`-22.5, -45, -67.5`, then jumps to 270) [O] |
| E-2 | Probe P2: sheet built with spacing, one gap pixel recoloured, one near-magenta pixel | `validate_sheet_atlas.py` exit 0 "PASS" [O] |
| E-3 | Probe P3: terrain job, fully painted opaque candidate | prompt demands a pink background; `verify` rejects "corners are not exact opaque #FF00FF"; packet paths absolute [O] |
| E-4 | Probe P4: `select(all approved)` with one stale record | raises, returns nothing [O] |
| E-5 | Probe P5: bundle declaring `sub/shell.png` containing bytes `b"asset"` | `approve` → approved; `revoke` → "Bundle missing required artifact(s)" [O] |
| E-6 | Probe P6 | legacy wizard `validate()` rejects `world.grid: isometric` (schema allows it); lifecycle accepts a garbage `owner_confirmed` project file [O] |
| E-7 | Probe P7 | `city.scene` valid for lifecycle, invalid for crop; `City_Scene` the reverse [O] |
| E-8 | Probe P8 (`-W error`) | `getdata()` deprecated, "removed in Pillow 14 (2027-10-15)" (Pillow 12.2.0 runtime message); call sites found by reading: `validate_parent_cleanup.py:105-106` [O] |
| E-9 | Probe P9 | stale `agent-sync.lock` blocks every later sync; hook command embeds the absolute interpreter and script path [O] |
| E-10 | One-off review run of the committed engine smoke fixture in a scratch folder outside the repo (Godot 4.7.2; CI pins 4.4.1) — kept only as input to D-2/P5 | 2 of its assertions fail; cause is fixture data, not engine version: `mount_tracks` is keyed by the child's own action while builder and runtime select by the *parent's* action, so the Python-sampled poses also show no mount rotation [O]. It also imported 0 files under `.gamearts/` but 6 under a normal folder; Godot's documented way to hide a folder is `.gdignore` ([import docs](https://docs.godotengine.org/en/stable/getting_started/workflow/assets/import_process.html)), dot-prefix behavior is community-reported only [U for export]. Hosted runs of the same workflow on 4.4.1 fail at the same step (E-23); the cause of the hosted failure is not observed (logs need authentication). |
| E-11 | Probe P10: prepare a crop packet inside a candidate folder, then move the folder generated→approved | `verify` passes before the move and is rejected after ("File or SHA256 changed since preparation") [O] |
| E-12 | Probe P11: a real single-component bundle built by the builder (`validation.parent_cleanup: pending`, no review protocol) | `approve` → approved [O] |
| E-13 | Probe P12: register and approve a mockup, then re-indent `project.json` with identical content | `audit-mockup` goes from `[]` to two settings-hash issues [O] |
| E-14 | Probe P13: a source tree whose master has another name; then a file removed upstream | sync raises "Source must be a separate complete GameArtsSkills checkout"; the removed file stays in the game [O] |
| E-15 | Probe P14 | `master.png` and `plate.png` byte-identical and accepted; strict validation passes with a sprite colour that exists nowhere in the source [O] |
| E-16 | Probe P15 | `validate_blueprint` without `jsonschema` exits 0 "NOT RUN"; invalid metadata is refused only when the game root has `schemas/` and `jsonschema` is installed, otherwise accepted [O] |
| E-17 | Probe P16 | one detached prop: 0.22 s at 512², 0.69 s at 1024², 3.59 s at 2048² [O] |
| E-18 | Probe P17 (Windows): two concurrent registrations | both raised `PermissionError`; the manifest kept only the earlier record; the two images stayed unregistered [O] |
| E-19 | Probe P18 | `revoke` returns no dependents field; the asset's next audit reports "asset refers to a missing or nonapproved mockup" [O] |
| E-20 | Probe P19: registration B runs completely while registration A holds a stale copy of the manifest (deterministic interleaving, OS-independent) | both report success; the manifest keeps A and silently loses B; B's image is left unregistered [O] |
| E-21 | Probe P20: a sync aborted by an injected write failure, then upstream changes a file the aborted run had already written | no state file exists after the abort although two files were written; the next sync reports the untouched file as a user conflict [O] |
| E-22 | Concurrent-register probe (script retired after it became `test_parallel_registrations_lose_nothing`; output in [evidence/concurrent_register_output.txt](evidence/concurrent_register_output.txt)): two threads read the manifest before either writes | Linux (WSL2 Ubuntu, Python 3.12.3), three runs, three outcomes: `FileNotFoundError` + `JSONDecodeError`; `FileNotFoundError` + `ValueError`; and both reported success while one record was silently lost. Windows: `PermissionError`, and a torn-read `JSONDecodeError` in another run [O] |
| E-23 | Hosted CI, read from GitHub's public API on 2026-10-23 (no log access) | Atlas Tests: the 5 newest runs (2026-10-22 09:21–09:29) all `failure`; the newest, at `081c5e3`, failed on `windows-latest` and `ubuntu-latest` at step `python -m unittest discover -s tests -v`, and the workflow file at that commit installs only `Pillow` (raw file read). Godot smoke test: 10 runs, the 5 newest all `failure`; the newest failed at step "Test nested attachments and facing changes in Godot". Local HEAD `17963c4` is the newest commit on GitHub and has no workflow run [O]. Causes are not observed [U]. |
| E-24 | Focused check: `test_project_schema.py` and `test_gamearts_asset_lifecycle.py` only, with `jsonschema` blocked (a Pillow-only environment) | 2 errors: `test_project_schema` cannot import; `test_register_creates_manifest_and_metadata_contract` fails. Consistent with the Atlas failure at `081c5e3`; not proof, because the hosted logs were not seen [O for the check, I for the link] |

## 4. Findings register

Severity: S1 corrupts or bypasses a gate · S2 wrong or brittle behavior · S3 hygiene. Locators are
`file:line` in the baseline tree.

### Gate integrity (P1)

| ID | Sev | Class | Finding | Locator |
| --- | --- | --- | --- | --- |
| F-001 | S1 | O | `approve`/`audit` never validate artwork: no PNG, atlas or `validate_component_bundle --approval-gate` check. A bundle of `b"asset"` bytes is approved (E-5), and so is a real single-component bundle whose `validation.parent_cleanup` is `pending` — it needs no review packet because the builder sets the review protocol only for multi-part bundles or a declared inventory (E-12). | lifecycle:86-266, 300-456; tests/test_gamearts_asset_lifecycle.py:21,236; build_component_bundle.py:319-320 |
| F-002 | S1 | O | The sheet/atlas validator compares only a declared `mask_color` string and alpha; it never checks that pixels outside ink are exact `#FF00FF`, and nothing detects near-magenta fringe (standard §8, §24.4 require both). | validate_sheet_atlas.py:7-34; E-2 |
| F-003 | S1 | O | `verify` demands pink corners and the prompt demands a pink background for every class, but the standard says a fully painted scene "can have no unused pixels" (terrain tiles, full-bleed UI). | prepare_reference_crop.py:213,284-289; E-3 |
| F-005 | S2 | O | `select()` without an id raises on the first failing approved record instead of listing the rest. | lifecycle:285-289; E-4 |
| F-006 | S2 | O | `files` path rule differs: `approve` accepts nested paths, `revoke` requires bare names, so an approved asset can become impossible to revoke. | lifecycle:324 vs 473-479; E-5 |
| F-007 | S2 | O | `project.json` is never validated against its schema at runtime; `confirmed_by` is not enforced although the standard requires it; the schema has no `owner_confirmed ⇒ confirmed_at, confirmed_by`. | lifecycle:548-560; schemas/gamearts-project.schema.json:26-41; E-6 |
| F-008 | S2 | O | Legacy `setup_gamearts.py` rejects `isometric`, omits `camera_profile`/`ground_camera`/`settings_status`, writes a config the lifecycle refuses, and has no test. | setup_gamearts.py:50,117-136; E-6 |
| F-009 | S2 | O | Two `mockup_id` contracts (lifecycle `[a-z0-9][a-z0-9._-]*`, crop `[A-Za-z0-9_-]+`): a registered id with a dot can never be cropped. | lifecycle:616; prepare_reference_crop.py:22,101; E-7 |
| F-010 | S2 | O | Schema validation is silently skipped in two situations: `jsonschema` missing (`validate_blueprint` exits 0 with "NOT RUN"; `register` accepts invalid metadata) and schemas absent from the game root (the lifecycle looks for `<game>/schemas/…`; every test fixture lacks that folder, so the schema path is never exercised through `register`). Install docs list only Pillow. | lifecycle:636-645; validate_blueprint.py:47-51; README_INSTALL.md:18; E-16 |
| F-011 | S2 | O | Keyframe rotation always takes the shortest arc: full turns (wheels, rotors) collapse; large angles run backwards then jump. | build_component_bundle.py:86-90; E-1 |
| F-012 | S2 | O | Reference packet and prompt store absolute paths; after the candidate moves generated→approved `verify` fails ("File or SHA256 changed"), and packets are not portable across machines. | prepare_reference_crop.py:201,226-236,250-261; E-3, E-11 |
| F-004 | S2 | O | Track keys are never checked for reachability: `mount_tracks` for an action that is never selected is accepted and ignored (this is why E-10's fixture shows no mount motion). | build_component_bundle.py:94-102,294-296 |
| F-023 | S2 | O | The cleanup validator never ties a detached sprite's pixels to the source pixels under its mask (a sprite whose colour exists nowhere in the source passes strict props), and a clean plate that is a byte-identical copy of the parent is accepted. | validate_parent_cleanup.py:93-131; E-15 |
| F-021 | S2 | O | `Image.getdata()` is deprecated; two direct calls remain (the third occurrence in `visual_review_cleanup.py` is a guarded fallback — not a defect). | validate_parent_cleanup.py:105-106; E-8 |
| F-029 | S3 | O | Rollback swallows unlink failures (`except OSError: pass`), violating "no swallowed exceptions". | lifecycle:835-840 |
| F-024 | S3 | O | Vacuous assertion: the UI-camera test asserts a string the prompt can never contain. | tests/test_prepare_reference_crop.py:214 vs prepare_reference_crop.py:204 |

### Consolidation, contracts, versioning (P2)

| ID | Sev | Class | Finding | Locator |
| --- | --- | --- | --- | --- |
| F-040 | S1 | O | The same policy blocks are copied into `CLAUDE.md`, `AGENTS.md`, 10 skills × 2 trees, docs and the master — contradicting the master's own §27.11 ("skills read the canonical core rather than copying policy blocks that can drift"). It has already drifted: `art-profile/SKILL.md` differs between trees (the Codex copy has extra sentences in "Camera/style locked prompt input" and a whole "Crop-and-reference image-tool input" section the Claude copy lacks); the other nine skills read identical. | both skill trees (read in full); master:873-886 |
| F-041 | S2 | O | Corrupted text, present in both trees: a TAB in `top_down` ("`<TAB>op_down`"), literal backslash-backtick and `\n` escapes, a missing newline ("atlas JSON- state metadata"). | `game-arts-project-setup/SKILL.md:32`; master:621,1164,1707-1718; `game-arts/SKILL.md:147`; `art-profile` (line 37 in `.claude`, 41 in `.agents`); `sheet-atlas:45`; `game-arts-mockup-creator:64` |
| F-042 | S2 | O | Stale labels and status: README links "Master standard v7.6" to the v7.7 file; lifecycle skill cites "v7.3 standard"; §23 calls v7.0 current; section numbers 29–35 appear twice; docs still say engine execution is unverified. | README.md:138; game-arts-lifecycle/SKILL.md:9; master:661,921-1150 |
| F-043 | S2 | O | Project-specific content ("Oilfield Days defaults/lessons") sits in universal skills, master and `CLAUDE.md`, against the rule that project rules live in the game repo and "never hardcode Oilfield Days". | master:1444,1682,1699-1725; skills; CLAUDE.md:76 |
| F-044 | S2 | O | Standard requirements with no implementation: near-magenta detection (§24.4), provenance model/seed/provider and rights notes (§24.7), per-direction draw order (§15.6, §32.6), animation regression checks (§24.6, §33), per-frame durations (§16). | master sections cited; schemas lack the fields |
| F-045 | S3 | O | No schemas for bundle, atlas, cleanup, review spec/packet/decision, reference job/packet/receipt, frames job, component job; the assets-manifest schema is weak and never loaded; code accepts `approval` values (`approved`, `granted`) the mockup schema forbids. | schemas/; lifecycle:102,724 |
| F-046 | S3 | O | The same helpers and constants are re-implemented per script (sha/digest, RGBA/mask readers, `PINK`, `KINDS` ×3, path-inside checks). | scripts/*.py |
| F-051 | S2 | O | Versioning is present in: the master file name (`GAME_ARTS_MASTER_STANDARD_v7.7.md`, referenced from `CLAUDE.md`, `AGENTS.md`, `README.md`, `README_INSTALL.md`, `docs/COMMANDS.md`, `docs/USER_WORKFLOW.md`, `docs/ASSET_LIFECYCLE.md`, the `game-arts` and `game-arts-mockup-creator` skills, `scripts/sync_local_agents.py`, `scripts/setup_gamearts.py`, `tests/test_sync_local_agents.py`); version labels in the master (v6.9–v7.7 section titles, the `Version:` line), in `CLAUDE.md`/`AGENTS.md` section titles (v7.3–v7.7), skill headings (`game-arts`, `animation-planner`, `sheet-atlas`, `godot-validator`, `game-arts-lifecycle`) and docs (`ASSET_LIFECYCLE`, `COMMANDS`, `USER_WORKFLOW`, `README`, `README_INSTALL`); the `master_standard` field (written, read by nothing); blueprint `schema_version` const "7.2". All found by reading. | master; scripts/setup_gamearts.py:120; schemas/mockup-blueprint.schema.json:16 |

### Lifecycle, updater, tests (P4, P6, P7)

| ID | Sev | Class | Finding | Locator |
| --- | --- | --- | --- | --- |
| F-027 | S2 | O | Documented operations with no implementation: asset `register`, asset `reconcile`, `restore`, `replaced_by`/supersede, `list`. `assets.json` is hand-written by agents and its schema never enforced. | lifecycle:983-1051; docs/COMMANDS.md:42; master:1248-1249 |
| F-020 | S2 | O | Manifests are read-modify-written with no lock, and every writer uses the same temp name (`<manifest>.pending`), although two agents (Claude and Codex) are meant to share one game. Two concurrent registrations on real Linux gave three different outcomes in three runs — both crashed (`FileNotFoundError`, `JSONDecodeError`), both crashed (`FileNotFoundError`, `ValueError`), and both reported success while one record was silently lost; on Windows they fail with `PermissionError` or a torn-read `JSONDecodeError`. An interleaved registration also reports success and then vanishes (E-20). | lifecycle:563-596; E-18, E-20, E-22 |
| F-026 | S2 | O | `settings_sha256` hashes raw bytes: re-indenting `project.json` with identical content makes `audit-mockup` report an approved mockup, against "approved art is not silently revoked by a settings change". | lifecycle:699-704; game-arts-project-setup/SKILL.md:60; E-13 |
| F-028 | S3 | O | Revoking a mockup reports nothing about approved assets that depend on it; their next audit then fails ("refers to a missing or nonapproved mockup"). | lifecycle:459-541; E-19 |
| F-015 | S2 | O | A killed update leaves `agent-sync.lock` forever; no stale detection. | sync_local_agents.py:73-86; E-9 |
| F-016 | S2 | O | Hook command embeds the absolute interpreter and script path in project settings (breaks teammates/CI if committed). | sync_local_agents.py:186-190; E-9 |
| F-017 | S1 | O | Renaming the master strands every enrolled game: a tree whose master has another name makes the installed updater raise "Source must be a separate complete GameArtsSkills checkout" (E-14). Upstream deletions are never propagated: a file removed from the source stays in the game (E-14). State is saved only at the end: after a run aborted mid-way there is no state file although files were written, and the next run reports them as user conflicts (E-21). | sync_local_agents.py:26,127,179-182; E-14, E-21 |
| F-018 | S2 | O | The hook executes whatever is on `main`; no commit-signature or manifest verification exists anywhere in the update path (read in full). | sync_local_agents.py:230-247 |
| F-025 | S2 | O | Test and CI debt: no tests for `setup_gamearts`, `validate_sheet_atlas`, `update()`, stale lock, select-all, nested `files`, approved-mockup-after-settings-change, schema-skipped path; the atlas workflow's path filter omits `setup_gamearts.py`, docs and skills. | tests/; .github/workflows/atlas-tests.yml |
| F-052 | S1 | O+I | Hosted CI is red: the 5 newest runs of both workflows (2026-10-22) failed. Atlas Tests fail at `unittest discover` on both operating systems; the workflow at the failing commit installed only `Pillow` while two tests need `jsonschema` (E-24: consistent, not proven). The engine workflow fails at the attachment-motion step (the fixture defect in E-10). Local HEAD has no run at all. | .github/workflows/atlas-tests.yml:45; E-23, E-24 |
| F-022 | S3 | O | Measured, not a defect at fixture scale: one detached prop validates in 0.22 s at 512², 0.69 s at 1024², 3.59 s at 2048². Behavior with many props and at 4096² is unmeasured (the loops are O(props × pixels)). The earlier suspicion is downgraded. | validate_parent_cleanup.py:133-159; visual_review_cleanup.py:214-239; E-17 |

### Engine-specific items handed to P5 (D-2)

Godot-specific artifacts and findings exist today (addon, scene generator, smoke fixture, CI workflow,
runtime doc, validator skill, master sections). They are inventoried in P5.1 and **not fixed here**:
the findings (always-on `_process`, silent early returns in pose application, hand-written track
interpolation versus native animation, shader modulate/lighting, forced nearest filtering,
`res://.gamearts` bundle location, stale `bundle_path` after approval, scene-file injection of a bundle
`directions` string, missing duration/draw-order support, no numeric parity test, 4.4.1-only CI) move to
the extraction hand-off in P5.2 so the next owner of the runtime receives them.

## 5. Phases

Order and gates: **P1 → (P3 ∥ P6) → P2 → P5 → P4 → P7.** P3 only adds files under existing sync paths,
so the installed updater handles it; P2's rename and P5's removals wait for P6.1–P6.4 (D-6).
Verification in every phase is focused (named test files/cases); the full suite is CI's job.
Each phase's checks are written first as failing tests against the baseline, then the fix lands, then the
test must pass and the probe is retired.

### P1 — Gate integrity and correctness fixes

Acceptance criteria
- A1.0 Hosted Atlas Tests are green on Windows and Linux for the commit that contains the P1 fixes, and every change (including docs and skills) triggers a run or can be dispatched.
- A1.1 `approve` and `audit` refuse a bundle with an invalid or non-opaque PNG, a pixel outside ink that is not exact `#FF00FF`, an atlas that fails geometry, or (when `*.bundle.json` exists) a failed `--approval-gate`.
- A1.2 The sheet/atlas and bundle validators fail on any non-key pixel outside declared frame ink and report near-key pixels by a stated tolerance.
- A1.3 Crop `verify` and prompt derive the export rule from `asset_class`: terrain and UI candidates may be full-bleed; opacity is still required.
- A1.4 Packet/prompt paths are bundle-relative; `verify` passes after the candidate moves generated→approved.
- A1.5 One `mockup_id` rule shared by lifecycle and crop (the lifecycle's existing pattern, so published manifests stay valid).
- A1.6 `select` without id lists eligible records and reports failing ones; one `files` path rule (relative, inside bundle, nested allowed) for approve, revoke and audit.
- A1.7 `register`/`audit` validate `project.json` against its schema (conditional `confirmed_at`+`confirmed_by`); a missing validator fails.
- A1.8 The wizard's validity rules come from the schema (isometric accepted, camera fields written); it never writes `owner_confirmed` without an explicit confirmation answer.
- A1.9 Keyframe rotation interpolates linearly on authored values (full turns work); `rotation_interpolation: "shortest"` is an explicit opt-in.
- A1.10 The builder rejects any `mount_tracks`/`motion_tracks` key that no action selects.
- A1.11 No `getdata()` calls; rollback failures are reported, not swallowed.

Design and files: new single owner `scripts/gamearts_common.py` (hashing, safe relative paths, PNG/key-color policy with tolerance, image iteration without `getdata`, JSON + schema validation with required `jsonschema`, atomic write); `validate_*`, lifecycle, crop, builder, wizard import it. Contract fixes keep existing manifests readable.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P1.0 | Make hosted CI green and observable: add `workflow_dispatch` and the doc/skill paths to the filters so every change runs; read the failing logs (needs the owner's authenticated view) to confirm the cause; the Atlas workflow at HEAD already installs `jsonschema`; confirm with one hosted run per workflow. The engine workflow stays red until P5 removes it (F-052) | none | hosted run (owner pushes) | workflow rewritten (all changes, dispatch, matrix); **hosted run pending the owner's push** |
| P1.1 | Write failing tests from the engine-neutral probes P1–P20 (one test per F-id) | none | each fails on baseline | done: tests added; 31 revert-the-fix proofs |
| P1.2 | `gamearts_common.py` + tests | P1.1 | `test_gamearts_common.py` | done: `test_gamearts_common.py` |
| P1.3 | Key-color policy in sheet/atlas + bundle validators (F-002, F-021) | P1.2 | `test_build_sheet_atlas.py`, new `test_validate_sheet_atlas.py` | done: `test_build_sheet_atlas.py`, `test_validate_sheet_atlas.py` |
| P1.4 | `approve`/`audit` technical gates; shared `files` rule; list-all `select`; surface rollback errors (F-001, F-005, F-006, F-029) | P1.3 | `test_gamearts_asset_lifecycle.py` | done: `test_gamearts_asset_lifecycle.py`, `test_lifecycle_operations.py` |
| P1.5 | Class-aware crop gate; relative packet paths; shared id rule (F-003, F-009, F-012); fix vacuous assertion (F-024) | P1.2 | `test_prepare_reference_crop.py` | done: `test_prepare_reference_crop.py` |
| P1.6 | Schema-validated settings; conditional schema; required `jsonschema`; wizard from schema (F-007, F-008, F-010) | P1.2 | `test_project_schema.py`, new `test_setup_gamearts.py` | done: schema-validated settings, `check-settings`; the legacy wizard was removed |
| P1.7 | Rotation interpolation; track reachability (F-011, F-004) | P1.2 | `test_component_bundle.py` | done: `test_component_bundle.py` |
| P1.8 | Sprite-vs-source tie and identical-plate check, behind `--strict-props` (F-023) | P1.2 | `test_validate_parent_cleanup.py` | done: `test_validate_parent_cleanup.py` |
| P1.9 | Revert-fix proof: each new test fails on the baseline copy of its script | P1.3–P1.8 | recorded in tracker | done: [mutation_proofs_output.txt](evidence/mutation_proofs_output.txt), 31 of 31 caught |

Error handling and recovery: validators return nonzero with the failing path and pixel count; approval
still rolls back to the generated bundle and original manifest on any failure (existing behavior kept).
Compatibility: previously approved assets are not retroactively revoked; new gates apply at the next
`approve` or an explicit `audit`, and `audit` labels legacy results as such. Risks: A1.2 may flag
existing sheets with intentional magenta artwork — tolerance and an explicit per-asset allowance live in
the atlas, default strict.

### P3 — Storyboard and campaign planning (new capability)

Why: "One scene is not a storyline." A game or campaign request needs its key scenes agreed before any
full-size mockup is produced. The user either supplies a storyboard or the agent authors one from the
user's prompting; mockups are generated only for the sequence the user approves.

Comparable practice (2026-10-23; practitioner guides, not standards): storyboard the key sequences and
pivotal moments; rough frames, thumbnails or placeholders are enough; agree direction before costly
production ([Katalist](https://katalist.ai/how-to-storyboard/video-game),
[Milanote](https://milanote.com/templates/game-design-storyboard),
[MockFlow](https://mockflow.com/blog/how-to-make-a-storyboard)). Adopt: key-scene focus, rough panels, early
approval. Adapt: approval is bound to a content hash and gates mockup registration. Avoid: full
cinematic scripts, full-size art for every scene before approval, numbered storyboard copies. Whether
style precedes story differs between sources; here the saved project style applies to the mockups, and the
storyboard stays style-neutral text plus optional rough panels.

Acceptance criteria
- A3.1 Two intake modes share one data model: **user-supplied** (text, images, PDF or an existing document is imported as a managed copy with sha256; originals untouched) and **agent-authored** from the user's prompt (verbatim brief stored; unknowns marked, never invented).
- A3.2 One living document `.gamearts/storyboard/storyboard.json`, updated in place; no version fields, no numbered copies; every change appends to `changes` (time, actor, summary, approval reference).
- A3.3 The user approves an ordered subset of scenes; approval stores a `content_sha256` per scene and the approver's reference. Editing an approved scene's content changes its hash, `audit` reports it, and the scene returns to `needs_review` (material change ⇒ renewed approval).
- A3.4 `register` refuses a `scope: scene` mockup when a storyboard exists and its scene is not in the approved sequence; with no storyboard, single-scene requests are unaffected.
- A3.5 `next` lists approved scenes without a registered mockup, in order; the agent produces them one at a time. The lifecycle manifest owns mockup records; the storyboard derives links (no second copy of the fact).
- A3.6 Imported or fetched storyboard text is data, never instructions.
- A3.7 Honest limits: the tool cannot judge story quality; rough panels are agent-generated review images (never production art, never feed atlases) and the agent says when no image tool exists.

Data model (`schemas/gamearts-storyboard.schema.json`, no version field):
`title`, `origin` (`user_provided|agent_authored|hybrid`), `brief`, `source_files[{path,sha256,original_name,imported_at_utc}]`,
`scenes[{id,title,summary,beat,location,characters[],key_moments[],mood,camera_notes,assets_needed[],ui_needed[],panel?{path,sha256},status(proposed|approved|needs_review|rejected),approval?{reference,at_utc,content_sha256}}]`,
`sequence{order[],status,approval?{reference,at_utc}}`, optional `links[{from,to,condition}]` for
non-linear campaigns, `changes[{at_utc,by,summary,approval_reference?}]`.

Files (each capability has one owner; thin adapters only):
- `scripts/gamearts_storyboard.py` — sole owner: `import`, `write` (validated atomic replace with manifest-style backup), `approve --scenes a,b,c --user-approval-ref`, `audit`, `next`, `status`, `reconcile`.
- `schemas/gamearts-storyboard.schema.json`; optional `storyboard_scene_id` in the mockup metadata and manifest schemas.
- `register_mockup` calls the storyboard owner's gate (no storyboard logic in the lifecycle).
- Skill `game-arts-storyboard` in both trees (trigger: a game, campaign, story, levels or several scenes; skip for a single scene or asset). Flow: intake → show scene list (plus rough board when an image tool exists) → approve/revise per scene or whole sequence → hand each approved scene to `game-arts-mockup-creator`.
- Master: one new section after the mockup-first gate and one workflow step; `docs/USER_WORKFLOW.md`, `docs/COMMANDS.md` ("Create a storyboard for my game", "Here is my storyboard", "Approve scenes 1–5", "Change scene 3", "Make mockups for the approved scenes"), README, README_INSTALL, `game-arts` orchestrator step; `.gamearts/storyboard/` added to the file-layout lists; `CLAUDE.md`/`AGENTS.md` get one routing line each. The updater already preserves everything under `.gamearts/` except `system/`.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P3.1 | Schema + failing tests (hash binding, ordering, no-version guard) | P1.2 | `test_gamearts_storyboard.py` | done: `gamearts-storyboard.schema.json`, `test_gamearts_storyboard.py` |
| P3.2 | `gamearts_storyboard.py` | P3.1 | same | done: `scripts/gamearts_storyboard.py` |
| P3.3 | `register` gate + metadata/manifest field | P3.2 | `test_gamearts_asset_lifecycle.py -k storyboard` | done: `register`/`approve-mockup` gate; tests in `test_lifecycle_operations.py` |
| P3.4 | Skill (both trees), master section, docs, routing lines | P3.2 | doc-guard tests (P2.4) | done: skill in both trees, master section, `docs/STORYBOARD.md`, routing lines, `test_docs_guard.py` |
| P3.5 | Safety tests: traversal in `import`, symlinks, oversized files, hostile text treated as data | P3.2 | `test_gamearts_storyboard.py` | done: import safety tests (regular files only, size cap, name clash) |
| P3.6 | Live agent scenario runs: user-supplied and agent-authored | P3.4 | recorded transcript; **not run** | **not run**: no live agent session was available |

Error handling: every write is atomic with a backup under `.gamearts/system/backups/`; a failed import
leaves no partial copy. Compatibility: purely additive; games without a storyboard behave as before.
Risks: agents may skip the gate by writing files directly — the `register` refusal and `audit` are the
enforcement, not the prose. Decision recorded (D-3/D-4): scene mockups keep artifact revisions
(`vNNN`) because the lifecycle audits approved/revoked art; the storyboard itself never does.

### P6 — Updater hardening and migration readiness

Acceptance criteria
- A6.1 The updater locates the master by pointer/glob (exactly one match), not a constant; a legacy-updater compatibility test runs the last published updater against the new tree.
- A6.2 A stale lock (dead pid or older than a TTL) is recovered and reported; a live lock still blocks.
- A6.3 Files removed upstream are removed from games only when their hash still equals the tracked hash (user edits preserved, reported).
- A6.4 State is saved per file (or written ahead), so a failure cannot create permanent false conflicts.
- A6.5 Hook commands are portable (no absolute interpreter path in a committed file); machine-specific entries go to the client's local settings file.
- A6.6 Optional source verification (signed commit or published hash manifest); unverified fetches are reported, never silent.
- A6.7 `update()` is tested with an injected fetcher — no real network and no real git in tests.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P6.1 | Pointer-based master discovery + legacy-compat test (F-017) | none | `test_sync_local_agents.py` | done: master found by pattern; legacy-compat test with a frozen copy of the published updater |
| P6.2 | Stale-lock recovery (F-015) | none | same | done: OS-held lock replaces the PID/TTL file (no stale state exists); killed-owner test |
| P6.3 | Deletion propagation (F-017) | P6.1 | same | done: deletion propagation with backup, hash check and pruning |
| P6.4 | Per-file state persistence (F-017) | P6.1 | same | done: write-ahead `pending`, state saved per file, revision advances only on a complete run |
| P6.5 | **Research first** (current Claude Code and Codex hook/settings docs, trust rules), then portable hook entries (F-016) | none | docs cited in tracker; tests | done: research recorded in the tracker; local and project hook scopes, git exclude |
| P6.6 | Source verification option (F-018), researched the same way | P6.5 | tests | done: opt-in `--require-signed`; unverified fetches are reported |
| P6.7 | Injected-fetcher tests for `update()` | P6.1 | same | done: injected fetcher; no network or git in tests |

Recovery: the updater already backs up adopted files; new deletions go to the same backup folder.
Risk: shipping P6.1 requires one push by the owner and one session start in each enrolled game before P2's
rename (D-6). Git actions stay with the owner.

### P2 — Single-owner consolidation, contracts and unversioning

Acceptance criteria
- A2.1 Policy text lives once, in the master; each skill keeps routing and a heading reference ("see master: <heading>"); sections are cited by heading, never by number.
- A2.2 `.claude/skills` and `.agents/skills` are identical modulo path tokens (guard test); the `art-profile` drift is merged.
- A2.3 `CLAUDE.md` and `AGENTS.md` differ only in the documented tokens (guard test).
- A2.4 Guard tests fail on: a paragraph ≥ 200 characters duplicated across skills/docs/instructions; a stray `\``, TAB or literal `\n`; a version label (`v7.x`, `Version:`) in framework documents; a duplicate master heading number.
- A2.5 No project-specific game content in universal files; Oilfield Days material becomes a neutral example under `templates/` and a hand-off note for that game's own `.gamearts/instructions` (this plan does not touch other repositories).
- A2.6 New schemas: bundle, atlas, cleanup, review spec/packet/decision, reference job/packet/receipt, frames job, component job; assets-manifest schema tightened and enforced by the lifecycle (feeds P4).
- A2.7 Unversioned: master file name, headings, `Version:` line, labels in skills/docs/scripts/README/CLAUDE/AGENTS, `master_standard` field (ignored on read, no longer written); blueprint `schema_version` const "7.2" → "1.0" with legacy values accepted on read.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P2.1 | Failing guard tests (A2.2–A2.4) | P1.2 | `test_docs_guard.py` | done: `test_docs_guard.py` (20 tests) |
| P2.2 | Fix corrupted text (F-041) and merge `art-profile` drift | P2.1 | guard | done: corrupted text removed, `art-profile` merged |
| P2.3 | Reduce skills/docs/instructions to routing + heading references (F-040) | P2.2 | guard | done: skills 110 KB to 43 KB per tree, docs rewritten, master owns the policy |
| P2.4 | Relocate project-specific content (F-043) | P2.3 | guard | done: project-specific content removed from universal files (guard) |
| P2.5 | Schemas for every script input/output; enforce in scripts (F-045, F-046) | P1.2 | `test_contract_schemas.py` | done: 17 contracts, each enforced by the script that reads or writes it (`test_contract_schemas.py`); only the updater's own state file is validated in code |
| P2.6 | Remove version labels and renumber master headings; keep the file name until P2.8 (F-042, F-051) | P2.3 | guard | done: no version labels; master headings renumbered 1-27 |
| P2.7 | Blueprint `schema_version` migration with legacy read | P2.5 | validator tests | done: blueprint marker `1.0`, legacy `7.2` still read |
| P2.8 | Rename master to `GAME_ARTS_MASTER_STANDARD.md` and update every reference | **P6.1–P6.4 shipped** | guard + legacy-updater compat test | done with a bridge: the master is `GAME_ARTS_MASTER_STANDARD.md`; a 498-byte pointer under the old name stays beside it so the published updater keeps working, the hardened updater never ships it and removes a copy it finds in a game; **the owner deletes the bridge once every enrolled game has updated** |
| P2.9 | Standard-vs-implementation reconciliation: for each F-044 item either implement (P4/P7) or state the limit in the master | P2.3 | reviewed table in tracker | done: master *Standard versus implementation*; near-key, durations, draw order, provenance implemented; loop closure and clipping stated as not automated |

Compatibility and recovery: P2.8 was applied as one push with a bridge instead of two pushes: the old file name
now holds a pointer only (a test keeps it under 1.2 KB and free of policy sections), so the published updater keeps
installing this tree; the hardened updater ignores it, never ships it and removes the copy an old updater left in a game.
The owner deletes the bridge once every enrolled game has updated. Risk: collapsing skill text changes agent behavior; each reduced skill is checked against the
list of mandatory gates it used to state, and live agent runs (tracker acceptance rows) are still required.

### P5 — Engine-neutral scope (no Godot in this repository)

Depends on D-2 and P6.3 (installed games must drop removed files).

Acceptance criteria
- A5.1 No engine runtime, scene, addon, fixture or engine CI exists in this repository; a guard test fails if `*.gd`, `*.tscn`, `*.gdshader`, `project.godot`, `.godot/`, `*.import` or an engine workflow reappears.
- A5.2 The master states an engine-neutral integration contract: what the bundle/atlas files mean (mask color, pivots, anchors, composition convention, `sampled_poses` as the numeric oracle, durations, draw order) and that the game project owns engine import and runtime tests.
- A5.3 Validation status fields become `engine_validation` (`not_tested|passed|failed`, reported by the game project); old `godot_*` keys are read, never required, and existing approved assets are not invalidated.
- A5.4 The updater no longer syncs engine paths; installed games' copies are removed by P6.3 only when unmodified.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P5.1 | Inventory every engine-specific item with its consumers: `godot/addons/gamearts/*`, `scripts/generate_godot_scene.py`, `tests/create_godot_fixture.py`, `tests/godot/`, `tests/test_generate_godot_scene.py`, `.github/workflows/godot-runtime-tests.yml`, `docs/GODOT_COMPONENT_RUNTIME.md`, the `godot-validator` skill (both trees), master "Target Engine", engine integration/validation sections, README/README_INSTALL/CLAUDE/AGENTS blocks, `setup_gamearts.py` engine block, updater `PREFIXES`/`EXTS`, `godot_runtime` status keys | none | list in tracker | done: inventory in [ENGINE_HANDOFF.md](ENGINE_HANDOFF.md) and this table |
| P5.2 | Write the hand-off for the runtime's next owner: the engine findings from §4 plus E-10 and the native-feature notes (animation resources, `Transform2D` composition, idle `_process`, import-pipeline loading, `.gdignore`/location of bundles). Destination (recommended: a separate integration package that Godot game projects install) is the owner's to create | P5.1 | hand-off reviewed by owner | done: [ENGINE_HANDOFF.md](ENGINE_HANDOFF.md) |
| P5.3 | Replace engine sections of the master with the engine-neutral contract; remove the validator skill and engine docs | P5.2 | guard | done: master *Engine-neutral integration contract*; validator skill removed |
| P5.4 | Remove engine files, workflow and updater paths | P5.3, P6.3 | guard A5.1 | done: files, workflow and updater paths removed; guard test |
| P5.5 | `engine_validation` migration in builders, lifecycle, atlas/bundle output, schemas | P2.5 | tests with legacy fixtures | done: `engine_validation` in builders, lifecycle, schemas; legacy keys not required |
| P5.6 | Update README, README_INSTALL, CLAUDE.md, AGENTS.md | P5.3 | guard | done: README, README_INSTALL, CLAUDE.md, AGENTS.md |

Recovery: files remain in version history; nothing is deleted before the hand-off exists. Risk: games that
copied the addon keep their own copy (the updater removes only unmodified managed files).

### P4 — Lifecycle completeness, concurrency and provenance

Acceptance criteria
- A4.1 `register-asset`, `reconcile-assets`, `restore` (re-validation plus a fresh user approval reference), `supersede` (`replaced_by`) and `list` exist, validate against schemas and refuse hand-edited drift.
- A4.2 Manifest writes take a lock shared with the updater's lock primitive; two writers cannot interleave.
- A4.3 The settings hash covers only material fields (art style, world, directions, export) in canonical form; editing formatting or optional fields does not flag approved mockups; a material change does and says why.
- A4.4 `revoke` lists approved assets that depend on the revoked mockup.
- A4.5 Provenance (provider, model, seed when exposed, edit mode, conditioning image hashes) and rights notes are recorded for mockups and assets (standard §24.7).
- A4.6 Per-direction draw order and per-frame durations are in the bundle contract, or the master states the limit (F-044).

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P4.1 | Asset registration, reconcile, restore, supersede, list | P2.5 | `test_gamearts_asset_lifecycle.py` | done: `register-asset`, `reconcile-assets`, `restore`, `replaced_by`, `list` |
| P4.2 | Manifest lock (reuse P6.2 primitive) | P6.2 | concurrent-writer test | done: one OS lock for every lifecycle write; 5-process test on Windows and Linux |
| P4.3 | Canonical settings hash + audit wording (F-026) | P1.6 | lifecycle tests | done: canonical material-settings hash; drift flags vs blocks |
| P4.4 | Dependents report on revoke (F-028) | P4.1 | lifecycle tests | done: `revoke` returns dependents |
| P4.5 | Provenance and rights fields | P2.5 | schema + register tests | done: `provenance` and `rights` fields recorded when supplied |
| P4.6 | Draw order and durations in the bundle contract | P2.5 | `test_component_bundle.py` | done: durations and per-direction draw order in the contract |

### P7 — CI, test debt and performance

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P7.1 | Missing tests listed in F-025 that earlier phases did not add | P1–P6 | named files | done: `test_validate_sheet_atlas.py`, update/stale-lock/select/nested-path/settings tests added |
| P7.2 | CI path filters cover scripts, schemas, skills, docs, `CLAUDE.md`/`AGENTS.md`; run the doc guards on every change | P2.1 | workflow reviewed | done: workflow runs on every change |
| P7.3 | Python matrix 3.11 and 3.14, Pillow minimum and latest, Windows and Linux | P1.2 | hosted run (**not run**) | workflow written; **hosted run not observed**; local Windows (Python 3.14, Pillow 12.2) and Linux (Python 3.12, Pillow 13.0) runs recorded in the tracker |
| P7.4 | Dependency declaration (`Pillow`, `jsonschema`) shipped with the payload and in README_INSTALL | P1.6 | install doc | done: [README_INSTALL.md](../../README_INSTALL.md); missing validator is a failure |
| P7.5 | Measure cleanup and review with many props and at 4096² (2048² with one prop measured 3.6 s, E-17); optimize with image-level operations only if over budget (F-022) | P1.2 | recorded timings | measured: 2048² one prop 0.46 s (was 3.59 s); 4096² one prop 1.17 s; ten props 4.49 s |

### P8 — Image generator chosen by the owner, and the generation hand-off (added 2026-10-24 on the owner's request)

Owner: "what to use for image generation is based on user ... add this as option in project settings. Then framework will
remember each time it wants to generate an image" (the owner generates with Codex's built-in image generator). A real Codex
session on the framework also showed that an agent had to hand-write staging code to register the tool's picture.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P8.1 | `image_generation` in `project.json` (`tool`: `built_in_image_gen`, `cli_image_gen`, `connected_tool` with `tool_name`, `user_supplied`; optional `notes`), validated by the project schema; not a material setting | P1 | `test_project_schema`, `test_lifecycle_operations` (hash unchanged, approved art not reopened) | done |
| P8.2 | Enforcement at registration: `register` refuses a generated mockup whose `tool_mode`/`tool_name` differs from the setting, refuses any generated mockup when the owner supplies the pictures, always accepts an import; `check-settings` reports the choice | P8.1 | lifecycle tests + proofs M41–M45 | done |
| P8.3 | `register-generated`: one command takes the tool's PNG and the prompt actually sent, names, hashes, writes the metadata and registers; the tool defaults to the saved choice | P8.2 | lifecycle and command-line tests + proofs M46–M50 | done |
| P8.4 | Staging for `register-generated` and `import-mockup` inside `.gamearts/system/tmp`, never the operating system's temp folder (found by a real Codex run) | P8.3 | test with an unusable OS temp + proofs M51–M52 | done |
| P8.5 | Skills, docs and master: ask once when the choice is missing; say so when the chosen tool is not available in the session and never substitute or draw; look at the picture before showing it and make at most one corrected revision, withdrawing the first honestly | P8.1–P8.3 | docs guard; real runs below | done |
| P8.6 | Real runs: four Codex sessions (saved Codex tool: generated and registered, one picture self-corrected; user supplies the pictures: nothing generated; no choice saved: asked once; first session before the setting existed) and one Claude agent (Codex's tool saved, session has none: said so, nothing drawn) | P8.1–P8.5 | tracker V-13, V-14 | done; Codex interactive session start not run |

## 6. Sequencing and migration safety

1. P1 first: it fixes the gates everything else relies on and creates the shared owner module.
2. P3 and P6.1–P6.4 in parallel: both add or change files under paths the installed updater already syncs.
3. Release to enrolled games (owner push) and wait for them to start a session.
4. P2.8 (master rename, bridged) and P5.4 (engine removals), both guarded by the legacy-updater compatibility test; deleting the bridge is the owner's later step.
5. P4 and P7 follow; none changes installed-game compatibility.

## 7. Ownership and authorization

- Accountable: Fahad (repository owner) for D-1…D-6 and every release. Responsible: the implementing agent. Review so far is **self-review** only; no independent reviewer assigned.
- Not authorized here and not done: any git operation, push, release, change to another repository, enrolling or updating any game. File deletion became authorized when the owner asked for unrelated and legacy files to be removed (2026-10-23); the removals are listed in the tracker.
- Required before "done" for any phase: its focused checks pass, the revert-the-fix proof (P1.9) is recorded, live agent runs for behavior changes (P2, P3), and the tracker row updated with the actual command, exit status and date. Passing local checks does not establish hosted CI or live agent behavior.

## 8. Open verification gaps (unknowns)

Everything this review could not establish is listed here with what would resolve it. None of these is hidden in a
finding's wording; each also has a row in the tracker. Items resolved during the review stay listed so the history is visible.

| ID | Unknown | Why it is unknown | Resolution | Status |
| --- | --- | --- | --- | --- |
| U-1 | Outcome of two truly concurrent `register()` calls on POSIX | Was inferred; the review host was Windows | Resolved by E-22: on real Linux the outcome is nondeterministic — crashes or a silent lost update; the fix is tracked in P4.2 | Resolved |
| U-2 | Whether an aborted updater run leaves false conflicts | Was inferred from the code | Resolved by E-21 (injected failure, observed); the fix is tracked in P6.4 | Resolved |
| U-3 | Hosted CI result for the current tree | Public API read (E-23): both workflows were red before this work; HEAD has no run; failure logs need authentication | P1.0 restores and observes it; the owner shares log output if the cause is not the missing dependency | Partly resolved |
| U-4 | Live Claude Code and Codex behavior for the storyboard flow and for the reduced skills | No agent scenario was run when the plan was written | Partly resolved: ten Claude agent runs and four Codex sessions (`codex exec`, workspace-write sandbox) followed the installed files, and Claude Code's headless session start ran, see the tracker (V-11, V-13, V-14, V-16, V-17). Not run: the interactive hook trust review, Codex's session start and long, messy conversations | Partly resolved |
| U-5 | Engine-side facts: export behavior of dot-prefixed folders and runtime loading of raw PNGs in exported builds | Documentation names `.gdignore` only; community reports are not authoritative; no export test was run; no engine work belongs in this repo (D-2). The engine workflow's hosted failure is observed (E-23) | Handed to the runtime's next owner in P5.2 | Open (out of scope) |
| U-6 | Current Claude Code and Codex hook/settings semantics (where machine-specific hooks belong, trust prompts, exit codes) | Not researched in the review | Resolved by the P6.5 research (tracker, verification record V-5): project root variable, personal settings file, SessionStart sources, Codex trust by hook hash. One correction it forced: Claude Code ignores `.claude/settings.local.json` only when it saves a setting there, so the updater adds the file to `.git/info/exclude` itself | Resolved |
| U-7 | Whether the Python an agent uses inside a game project has `jsonschema` | Cannot be known from this repository | Mitigated, not resolved: every script fails with a clear message when it is missing (tested), and README_INSTALL declares it; whether a given game's Python has it is only known when the agent runs there | Open (mitigated) |

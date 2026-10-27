# Reading coverage ledger

Every file below was read in full with the file reader (line counts are newline counts of the baseline tree; the same
69 files are hashed in `baseline_files.sha256`, checked equal when this ledger was generated). Reading was not
done with text-pattern searches. Pattern searches and a `diff` were used earlier only to navigate or cross-check; no
finding rests on them. This file was generated after the reads from the files' actual sizes.

This ledger describes the baseline tree before implementation. Several files listed here were later rewritten or removed (see the tracker's section on removed files); the hashes in `baseline_files.sha256` identify the baseline.

Repository files read: **69 files, 11,753 lines, 866,829 bytes.**

| File | Lines | Bytes | How read |
| --- | ---: | ---: | --- |
| `.agents/skills/animation-planner/SKILL.md` | 63 | 9471 | full, 1 read |
| `.agents/skills/art-profile/SKILL.md` | 46 | 7821 | full, 1 read |
| `.agents/skills/game-arts/SKILL.md` | 163 | 31101 | full, 1 read |
| `.agents/skills/game-arts-custom-instructions/SKILL.md` | 76 | 5883 | full, 1 read |
| `.agents/skills/game-arts-lifecycle/SKILL.md` | 123 | 15606 | full, 1 read |
| `.agents/skills/game-arts-mockup-creator/SKILL.md` | 97 | 14007 | full, 1 read |
| `.agents/skills/game-arts-project-setup/SKILL.md` | 94 | 9812 | full, 1 read |
| `.agents/skills/godot-validator/SKILL.md` | 21 | 3104 | full, 1 read |
| `.agents/skills/mockup-analyzer/SKILL.md` | 53 | 7134 | full, 1 read |
| `.agents/skills/sheet-atlas/SKILL.md` | 52 | 8062 | full, 1 read |
| `.claude/skills/animation-planner/SKILL.md` | 63 | 9471 | full, 1 read |
| `.claude/skills/art-profile/SKILL.md` | 42 | 6885 | full, 1 read |
| `.claude/skills/game-arts/SKILL.md` | 163 | 31101 | full, 1 read |
| `.claude/skills/game-arts-custom-instructions/SKILL.md` | 76 | 5883 | full, 1 read |
| `.claude/skills/game-arts-lifecycle/SKILL.md` | 123 | 15606 | full, 1 read |
| `.claude/skills/game-arts-mockup-creator/SKILL.md` | 97 | 14007 | full, 1 read |
| `.claude/skills/game-arts-project-setup/SKILL.md` | 94 | 9812 | full, 1 read |
| `.claude/skills/godot-validator/SKILL.md` | 21 | 3104 | full, 1 read |
| `.claude/skills/mockup-analyzer/SKILL.md` | 53 | 7134 | full, 1 read |
| `.claude/skills/sheet-atlas/SKILL.md` | 52 | 8062 | full, 1 read |
| `.github/workflows/atlas-tests.yml` | 48 | 1579 | full, 1 read |
| `.github/workflows/godot-runtime-tests.yml` | 47 | 1692 | full, 1 read |
| `AGENTS.md` | 128 | 24158 | full, 1 read |
| `CLAUDE.md` | 128 | 23978 | full, 1 read (counts are of the file as read, before the maintainer section was added) |
| `docs/ASSET_LIFECYCLE.md` | 146 | 13620 | full, 1 read |
| `docs/ATLAS_GENERATION.md` | 59 | 4117 | full, 1 read |
| `docs/COMMANDS.md` | 121 | 12593 | full, 1 read |
| `docs/COMPONENT_ANIMATION.md` | 160 | 14409 | full, 1 read |
| `docs/CUSTOM_INSTRUCTIONS.md` | 61 | 2954 | full, 1 read |
| `docs/GODOT_COMPONENT_RUNTIME.md` | 41 | 3656 | full, 1 read |
| `docs/PROJECT_SETTINGS.md` | 101 | 7567 | full, 1 read |
| `docs/USER_WORKFLOW.md` | 136 | 16145 | full, 1 read |
| `GAME_ARTS_MASTER_STANDARD_v7.7.md` | 1773 | 150956 | full, 4 reads: lines 1-450, 451-900, 900-1339, 1340-1773 |
| `godot/addons/gamearts/chroma_key.gdshader` | 12 | 346 | full, 1 read |
| `godot/addons/gamearts/game_arts_component.gd` | 315 | 13515 | full, 1 read |
| `godot/addons/gamearts/game_arts_component.tscn` | 6 | 221 | full, 1 read |
| `README.md` | 232 | 27704 | full, 1 read |
| `README_INSTALL.md` | 129 | 19773 | full, 1 read |
| `schemas/gamearts-assets-manifest.schema.json` | 65 | 1339 | full, 1 read |
| `schemas/gamearts-mockup-metadata.schema.json` | 102 | 1877 | full, 1 read |
| `schemas/gamearts-mockups-manifest.schema.json` | 127 | 2890 | full, 1 read |
| `schemas/gamearts-project.schema.json` | 243 | 6476 | full, 1 read |
| `schemas/mockup-blueprint.schema.json` | 423 | 12781 | full, 1 read |
| `scripts/build_component_bundle.py` | 357 | 17745 | full, 1 read |
| `scripts/build_sheet_atlas.py` | 189 | 8432 | full, 1 read |
| `scripts/gamearts_asset_lifecycle.py` | 1057 | 55249 | full, 4 reads: lines 1-360, 360-689, 690-979, 975-1057 |
| `scripts/generate_godot_scene.py` | 61 | 2413 | full, 1 read |
| `scripts/prepare_reference_crop.py` | 323 | 16929 | full, 1 read |
| `scripts/setup_gamearts.py` | 146 | 7747 | full, 1 read |
| `scripts/sync_local_agents.py` | 286 | 12521 | full, 2 reads: lines 1-120, 120-286 |
| `scripts/validate_blueprint.py` | 66 | 2719 | full, 1 read |
| `scripts/validate_component_bundle.py` | 218 | 11118 | full, 1 read |
| `scripts/validate_parent_cleanup.py` | 215 | 10813 | full, 1 read |
| `scripts/validate_sheet_atlas.py` | 35 | 1973 | full, 1 read |
| `scripts/visual_review_cleanup.py` | 399 | 20827 | full, 1 read |
| `templates/custom-instruction.md` | 11 | 283 | full, 1 read |
| `tests/create_godot_fixture.py` | 93 | 4360 | full, 1 read |
| `tests/godot/test_runtime.gd` | 74 | 3452 | full, 1 read |
| `tests/test_build_sheet_atlas.py` | 95 | 4256 | full, 1 read |
| `tests/test_component_bundle.py` | 104 | 5023 | full, 1 read |
| `tests/test_gamearts_asset_lifecycle.py` | 634 | 34843 | full, 1 read |
| `tests/test_generate_godot_scene.py` | 57 | 2527 | full, 1 read |
| `tests/test_parent_cleanup_bundle_gate.py` | 139 | 6873 | full, 1 read |
| `tests/test_prepare_reference_crop.py` | 275 | 14098 | full, 1 read |
| `tests/test_project_schema.py` | 59 | 2383 | full, 1 read |
| `tests/test_sync_local_agents.py` | 150 | 7913 | full, 1 read |
| `tests/test_validate_blueprint.py` | 52 | 1904 | full, 1 read |
| `tests/test_validate_parent_cleanup.py` | 214 | 10092 | full, 1 read |
| `tests/test_visual_review_cleanup.py` | 269 | 12924 | full, 1 read |

## Read outside this repository

| File | How read |
| --- | --- |
| `agentic-sdlc-framework/core/ENGINEERING_CONSTITUTION.md` | full |
| `agentic-sdlc-framework/core/EVIDENCE_POLICY.md` | full |
| `agentic-sdlc-framework/skills/sdlc-orch/SKILL.md` | full |
| `agentic-sdlc-framework/skills/sdlc-orchestrator/SKILL.md` | full |
| `agentic-sdlc-framework/skills/sdlc-planning/SKILL.md` | full |
| `agentic-sdlc-framework/templates/PHASE_PLAN.md` | full |
| `agentic-sdlc-framework/plans/enhancements/MASTER_TRACKER.md` | full |
| `agentic-sdlc-framework/plans/enhancements/P4_MASTER_USAGE.md` | full |

## Not read

- `.git/`, `.vs/` (IDE state), `__pycache__/*.pyc` binaries; `plans/` (authored by this task).
- Framework skills `sdlc-architecture`, `sdlc-implementation`, `sdlc-verification`, `sdlc-handoff` and its other
  docs: not needed for this plan and not opened.

# convert-to-scorm1.2

Convert SCORM 2004 course packages to **SCORM 1.2-like** packages with broader LMS compatibility, and patch supported custom HTML SCORM runtimes so LMS tracking works more reliably.

Many learning platforms still have better support for SCORM 1.2 than SCORM 2004. This project provides a practical conversion workflow for Rise-style packages, including asset-path repair and manifest/driver adjustments. It also includes a runtime tracking patcher for supported flat custom packages that use root `index.html` plus `js/SCORMlocal.js`.

## What this includes

- A reusable Codex skill: `scorm2004-to-12`
- A conversion/repair script:
  - `scorm2004-to-12/scripts/scorm_asset_doctor.py`
- A runtime tracking patch script:
  - `scorm2004-to-12/scripts/scorm_runtime12_patch.py`
- Documentation:
  - `scorm2004-to-12/SKILL.md`
  - `scorm2004-to-12/references/conversion-notes.md`
  - `scorm2004-to-12/references/runtime-tracking.md`
  - `scorm2004-to-12/references/runtime-debugging-notes.md`
- Agent metadata:
  - `scorm2004-to-12/agents/hermes.yaml`
  - `scorm2004-to-12/agents/openai.yaml`
  - `scorm2004-to-12/agents/openclaw.yaml`

## Quick start

Run inspect first:

```bash
python3 scorm2004-to-12/scripts/scorm_asset_doctor.py inspect course.zip
```

Convert SCORM 2004 package to SCORM 1.2-like output:

```bash
python3 scorm2004-to-12/scripts/scorm_asset_doctor.py convert12 course.zip --output course-scorm12.zip
```

If you only want asset/path repair without conversion:

```bash
python3 scorm2004-to-12/scripts/scorm_asset_doctor.py repair course.zip --output repaired.zip --ascii-assets
```

Validate output:

```bash
unzip -t course-scorm12.zip
python3 scorm2004-to-12/scripts/scorm_asset_doctor.py inspect course-scorm12.zip
```

Patch a supported flat custom runtime for SCORM 1.2 tracking and manifest framing:

```bash
python3 scorm2004-to-12/scripts/scorm_runtime12_patch.py inspect course.zip
python3 scorm2004-to-12/scripts/scorm_runtime12_patch.py patch course.zip --output course-scorm12.zip
unzip -t course-scorm12.zip
python3 scorm2004-to-12/scripts/scorm_runtime12_patch.py inspect course-scorm12.zip
```

Use the runtime patch only when `inspect` shows the supported flat layout. For other custom runtimes, inspect the loaded JavaScript first and port the same contract manually.

The runtime patcher repairs JavaScript tracking behavior, removes known SCORM 2004-only runtime field calls in supported vendor packages, injects the SCORM 1.2 `session_time` helper when needed, and rewrites a simple root `imsmanifest.xml` to SCORM 1.2 metadata. After patching, `inspect` should report `"scorm_12_manifest": true`, `"has_scorm12_time_helper": true`, and `"legacy_2004_field_count": 0`.

## Flat runtime repair checklist

For custom HTML packages, page display and LMS tracking often fail for different reasons. Check both before repackaging:

1. Confirm what the browser actually loads. If `index.html` loads `js/scripts.js`, changing only source files under `js/controller/` or `js/pages/` is not enough. Keep source files and the loaded bundle behavior aligned.
2. Keep SCORM 1.2 fields strict:
   - `cmi.core.lesson_status` for incomplete/completed/passed/failed
   - `cmi.core.lesson_location` for a short bookmark
   - `cmi.suspend_data` for JSON state
   - `cmi.core.score.raw` for final score
   - `cmi.core.session_time` for current session time
   - `cmi.core.exit` as `suspend` while unfinished and empty for final states
3. Store a language-aware bookmark for multilingual packages, for example `zh-cn|chapter-3-page`. This gives mobile LMS players a small, reliable resume key even when `suspend_data` handling differs.
4. On launch, read `cmi.core.lesson_location` before parsing `cmi.suspend_data`. If `suspend_data` is invalid or too large, the course should still resume from the short bookmark.
5. Do not gate resume on learning progress. A page bookmark should resume even if progress is `0`, partial, or already `1`.
6. Do not let a default `_goto=select-lang` launch parameter override a saved non-language page.
7. Commit immediately after language selection and after page transitions. Waiting for unload is unreliable on mobile browsers and in mobile LMS shells.
8. Keep `session_time` as a termination-time field by default. Bookmark/progress commits should save `lesson_location` and `suspend_data`; `cmi.core.session_time` should be written when `ScormTerminate()` runs through `pagehide`, `beforeunload`, `unload`, or a final submit path.
9. Do not mirror page progress into quiz score. `score.raw` is only for the final quiz or final assessment result.

## Expected validation targets

A good converted package should report:

- `scorm_version: SCORM 1.2-like`
- `missing_local_image_refs: 0`
- `risky_image_refs: 0`
- `manifest_missing_refs: 0`

For non-Rise packages, `scorm_asset_doctor.py inspect` may fail because there is no `scormcontent/index.html`. That is a package-shape mismatch, not proof that the ZIP is invalid. Use ZIP integrity, manifest review, runtime JavaScript inspection, and LMS smoke testing instead.

For patched flat custom packages, `scorm_runtime12_patch.py inspect` should report:

- `scorm_12_manifest: true`
- `has_tracking_patch: true`
- `has_scorm12_time_helper: true`
- `has_lesson_location: true`
- `has_lesson_status: true`
- `has_session_time: true`
- `legacy_2004_field_count: 0`

For runtime tracking repairs, verify in the target LMS:

- bookmark/resume returns to the last viewed page
- selected language is restored before loading the resumed page
- progress reaches 100% after the final quiz/completion path
- completion status is recorded as complete/passed
- final score is recorded in `cmi.core.score.raw`
- learning time increases through `cmi.core.session_time`
- the same resume path works on desktop and mobile LMS launchers

## Scope and limitation

This is a conservative engineering conversion and runtime repair workflow for real-world LMS compatibility. It is not an official Articulate re-export pipeline or a generic SCORM runtime generator. Always run an LMS smoke test before production use:

1. launch
2. navigation
3. bookmark/resume
4. completion status
5. score reporting
6. session time reporting
7. selected-language resume when the course supports multiple languages

## Runtime debugging notes

When a package uses custom runtime files such as `SCORMlocal.js` or `pipwerks.SCORM`, manifest conversion alone is usually not enough. Check the course-layer code that writes:

- `cmi.core.lesson_status`
- `cmi.core.lesson_location`
- `cmi.suspend_data`
- `cmi.core.score.raw`
- `cmi.core.session_time`
- `cmi.core.exit`

For learning time, start with the target LMS behavior. The runtime patcher uses a termination-only `session_time` write by default, adds `pagehide` alongside `beforeunload` and `unload`, and does not mark the launch as terminated unless `quit` is not clearly failed. This keeps short bookmark commits from creating misleading time fragments while still giving mobile LMS shells an earlier close signal.

Some LMS products still merge several short close/reopen cycles into one displayed learning-time row and split rows only after a longer idle gap. Treat that as platform aggregation unless `LMSFinish` is missing or `session_time` is not being written at termination.

For `cmi.core.exit`, prefer conditional final-state behavior when LMS testing shows both variants work: set `suspend` for unfinished attempts, and set an empty exit value after `completed`, `passed`, or `failed`. Always writing `suspend` is kept as an LMS-specific fallback, not the default recommendation.

See `scorm2004-to-12/references/runtime-debugging-notes.md` for the detailed gate.

## Agent compatibility

The skill is published as a plain `SKILL.md` directory with repo-relative CLI commands. It is usable by Codex and by Hermes/OpenClaw-style agents that support AgentSkills-style folders or can read markdown instructions and run local scripts.

This repository does not claim a separate Hermes or OpenClaw plugin runtime. The portable contract is:

- read `scorm2004-to-12/SKILL.md`
- run `scorm2004-to-12/scripts/scorm_asset_doctor.py`
- run `scorm2004-to-12/scripts/scorm_runtime12_patch.py` only for supported flat custom runtimes
- load `references/` only when deeper conversion or runtime-debugging guidance is needed
- optionally read `agents/hermes.yaml` or `agents/openclaw.yaml` for platform-neutral routing metadata

## Safety note

This repository intentionally excludes personal credentials and environment secrets. Do not commit LMS credentials, API tokens, or private course data.

# Changelog

## 2026-05-13

- Added `sessionTimeSaved` as a recommended runtime guard pattern for custom vendor packages where multiple exit events can submit the same `cmi.core.session_time`; documented that this should remain an inspected runtime fix, not an automatic converter patch.
- Clarified the recommended SCORM 1.2 `cmi.core.exit` behavior after LMS testing: use `suspend` for unfinished attempts and an empty exit value after `completed`, `passed`, or `failed` when both variants pass; keep always-`suspend` as an LMS-specific fallback.
- Expanded the public skill documentation for the verified desktop/mobile runtime repair flow.
- Updated `scripts/scorm_runtime12_patch.py` so patched flat runtimes use a language-aware short bookmark in `cmi.core.lesson_location`, for example `zh-cn|chapter-3-page`.
- Documented the launch-order requirement: restore `lesson_location` first, then merge `suspend_data`, and keep the bookmark if `suspend_data` cannot be parsed.
- Documented the mobile resume pitfall where `_goto=select-lang` or delayed unload-only commits can restart the course at language selection.
- Added clearer agent guidance for custom runtimes that load bundled `js/scripts.js`; source controller files and the loaded bundle must both reflect the same tracking behavior.
- Added Hermes/OpenClaw agent metadata and runtime debugging notes to help other agents avoid broken page display, missing progress commits, and incorrect final score handling.
- Added AgentSkills-style compatibility metadata to the skill frontmatter for Codex, Hermes, OpenClaw, and generic agent use without misusing OS-specific `platforms` filters.
- Added `scorm2004-to-12/agents/README.md` to document the portable skill boundary and avoid claiming unverified platform-specific runtimes.
- Expanded README validation guidance to include non-Rise package inspection fallback and learning-time LMS smoke testing.

## 2026-05-12

- Added `scripts/scorm_runtime12_patch.py` for supported flat custom HTML SCORM runtimes.
- Added SCORM 1.2 runtime tracking guidance for:
  - bookmark/resume through `cmi.core.lesson_location`
  - learning progress and selected language through `cmi.suspend_data`
  - completion/pass/fail through `cmi.core.lesson_status`
  - final score through `cmi.core.score.raw`
  - learning time through `cmi.core.session_time`
  - final persistence through commit plus finish/quit
- Added `references/runtime-tracking.md` with the SCORM 1.2 tracking contract and LMS smoke-test checklist.
- Updated the skill trigger description, workflow, and public README to cover both Rise asset conversion and custom runtime tracking repair.
- Documented that SCORM 1.2 should not use SCORM 2004-only fields such as `cmi.progress_measure`, `cmi.success_status`, or `cmi.score.scaled`.

## 2026-04-30

- Added `scorm2004-to-12` skill for SCORM 2004 to SCORM 1.2-like conversion.
- Added `scripts/scorm_asset_doctor.py` with `inspect`, `repair`, and `convert12` commands.
- Added support for both Rise course data formats:
  - inline base64 in `scormcontent/index.html`
  - JSONP base64 in `scormcontent/locales/*.js`
- Added asset-path normalization and manifest synchronization checks.
- Added public README with usage and validation guidance.

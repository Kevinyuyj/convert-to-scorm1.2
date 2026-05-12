# Changelog

## 2026-05-13

- Updated `scorm2004-to-12/SKILL.md` to use public repo-relative command examples instead of local machine paths.
- Added AgentSkills-style compatibility metadata to the skill frontmatter for Codex, Hermes, OpenClaw, and generic agent use without misusing OS-specific `platforms` filters.
- Added `scorm2004-to-12/agents/README.md` to document the portable skill boundary and avoid claiming unverified platform-specific runtimes.
- Added `scorm2004-to-12/references/runtime-debugging-notes.md` with guidance for non-Rise vendor packages, course-layer SCORM wrappers, bookmark/resume, completion/score, and learning-time reporting.
- Documented the learning-time fix pattern: write `cmi.core.session_time` once on real termination, not on every progress/bookmark commit.
- Expanded README validation guidance to include non-Rise package inspection fallback and learning-time LMS smoke testing.

## 2026-04-30

- Added `scorm2004-to-12` skill for SCORM 2004 to SCORM 1.2-like conversion.
- Added `scripts/scorm_asset_doctor.py` with `inspect`, `repair`, and `convert12` commands.
- Added support for both Rise course data formats:
  - inline base64 in `scormcontent/index.html`
  - JSONP base64 in `scormcontent/locales/*.js`
- Added asset-path normalization and manifest synchronization checks.
- Added public README with usage and validation guidance.

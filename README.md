# convert-to-scorm1.2

Convert SCORM 2004 course packages to **SCORM 1.2-like** packages with broader LMS compatibility.

Many learning platforms still have better support for SCORM 1.2 than SCORM 2004. This project provides a practical conversion workflow for Rise-style packages, including asset-path repair and manifest/driver adjustments. It also documents how to debug non-Rise vendor packages where progress, completion, resume, score, or learning-time behavior is controlled by custom course JavaScript.

## What this includes

- A reusable Codex skill: `scorm2004-to-12`
- A conversion/repair script:
  - `scorm2004-to-12/scripts/scorm_asset_doctor.py`
- Documentation:
  - `scorm2004-to-12/SKILL.md`
  - `scorm2004-to-12/references/conversion-notes.md`
  - `scorm2004-to-12/references/runtime-debugging-notes.md`
- Agent compatibility notes:
  - `scorm2004-to-12/agents/README.md`
  - `scorm2004-to-12/agents/openai.yaml`

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

## Expected validation targets

A good converted package should report:

- `scorm_version: SCORM 1.2-like`
- `missing_local_image_refs: 0`
- `risky_image_refs: 0`
- `manifest_missing_refs: 0`

## Scope and limitation

This is a conservative engineering conversion for real-world LMS compatibility. It is not an official Articulate re-export pipeline. Always run an LMS smoke test before production use:

1. launch
2. navigation
3. bookmark/resume
4. completion status
5. score reporting
6. learning-time reporting

For non-Rise packages, `scorm_asset_doctor.py inspect` may fail because there is no `scormcontent/index.html`. That is a package-shape mismatch, not proof that the ZIP is invalid. Use ZIP integrity, manifest review, runtime JavaScript inspection, and LMS smoke testing instead.

## Runtime debugging notes

When a package uses custom runtime files such as `SCORMlocal.js` or `pipwerks.SCORM`, manifest conversion alone is usually not enough. Check the course-layer code that writes:

- `cmi.core.lesson_status`
- `cmi.core.lesson_location`
- `cmi.suspend_data`
- `cmi.core.score.raw`
- `cmi.core.session_time`
- `cmi.core.exit`

Learning time should be written once at real session termination. Progress/bookmark commits should not repeatedly overwrite `cmi.core.session_time`, because some LMSs turn each commit into a separate learning-time row.

For `cmi.core.exit`, prefer conditional final-state behavior when LMS testing shows both variants work: set `suspend` for unfinished attempts, and set an empty exit value after `completed`, `passed`, or `failed`. Always writing `suspend` is kept as an LMS-specific fallback, not the default recommendation.

See `scorm2004-to-12/references/runtime-debugging-notes.md` for the detailed gate.

## Agent compatibility

The skill is published as a plain `SKILL.md` directory with repo-relative CLI commands. It is usable by Codex and by Hermes/OpenClaw-style agents that support AgentSkills-style folders or can read markdown instructions and run local scripts.

This repository does not claim a separate Hermes or OpenClaw plugin runtime. The portable contract is:

- read `scorm2004-to-12/SKILL.md`
- run `scorm2004-to-12/scripts/scorm_asset_doctor.py`
- load `references/` only when deeper conversion or runtime-debugging guidance is needed
- optionally read `agents/hermes.yaml` or `agents/openclaw.yaml` for platform-neutral routing metadata

## Safety note

This repository intentionally excludes personal credentials and environment secrets. Do not commit LMS credentials, API tokens, or private course data.

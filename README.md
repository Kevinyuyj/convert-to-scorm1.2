# convert-to-scorm1.2

Convert SCORM 2004 course packages to **SCORM 1.2-like** packages with broader LMS compatibility.

Many learning platforms still have better support for SCORM 1.2 than SCORM 2004. This project provides a practical conversion workflow for Rise-style packages, including asset-path repair and manifest/driver adjustments.

## What this includes

- A reusable Codex skill: `scorm2004-to-12`
- A conversion/repair script:
  - `scorm2004-to-12/scripts/scorm_asset_doctor.py`
- Documentation:
  - `scorm2004-to-12/SKILL.md`
  - `scorm2004-to-12/references/conversion-notes.md`

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

## Safety note

This repository intentionally excludes personal credentials and environment secrets. Do not commit LMS credentials, API tokens, or private course data.

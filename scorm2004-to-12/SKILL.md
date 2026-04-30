---
name: scorm2004-to-12
description: Repair and rebuild SCORM/Rise course packages, especially SCORM 2004 packages with broken image loading, asset path mismatches, URL-encoding problems, or requests to convert/rebuild as SCORM 1.2. Use when Codex is given SCORM ZIP files, Rise exports, imsmanifest.xml, scormcontent/index.html, or asks for SCORM 2004 to 1.2 conversion, localization without breaking assets, or image/resource loading diagnostics.
---

# SCORM 2004 To 1.2

## Operating Rule

Treat a SCORM package as a resource reference system, not as a normal web folder. Do not edit text or manifest files blindly before proving the resource chain is self-consistent.

The image loading chain is usually:

1. Course JSON embedded in `scormcontent/index.html` as `deserialize("base64...")`, or older Rise JSONP data in `scormcontent/locales/*.js` via `__resolveJsonp("course:...", "base64...")`.
2. Runtime image fields such as `src`, `crushedKey`, `key`, `originalUrl`, and sometimes nested media objects.
3. `imsmanifest.xml` `<file href="...">` entries.
4. Actual ZIP paths under `scormcontent/assets/...`.

A valid package must close this loop: JSON reference -> actual file -> manifest declaration.

## Decision Tree

1. If a known-good same-course SCORM 1.2 package exists, use it as the structural base. Copy only visible text/course data from the bad package and preserve the good package runtime, assets, manifest resource list, and SCORM driver.
2. If no SCORM 1.2 base exists, run the package through `convert12`: decode course JSON, audit assets, normalize risky paths, update JSON and manifest together, switch the Rustici driver standard to SCORM 1.2, and repackage.
3. Treat the result as `SCORM 1.2-like` unless an LMS smoke test confirms launch, bookmarking, completion, and score behavior.
4. Never mix runtime chunks from unrelated exports unless the course JSON and chunk manifests are proven compatible.

## Workflow

1. Work in an isolated directory; never modify the original ZIP.
2. Run the asset doctor inspection:

```bash
python3 scripts/scorm_asset_doctor.py inspect course.zip
```

3. Review:

- course data found or not found, including both inline base64 and older `locales/*.js` JSONP formats
- SCORM version inferred from `imsmanifest.xml`
- local image reference count
- missing image references
- URL-encoded, space, non-ASCII, or case-risk paths
- manifest declarations missing for referenced assets

4. Default conversion command:

```bash
python3 scripts/scorm_asset_doctor.py convert12 course.zip --output course-scorm12.zip
```

5. If the user only asks for asset repair without SCORM 1.2 conversion, run:

```bash
python3 scripts/scorm_asset_doctor.py repair course.zip --output repaired.zip --ascii-assets
```

6. If localizing from another package, do not migrate media/resource fields. Transfer only visible text fields from the reference course JSON. Preserve the destination package media keys and runtime fields.
7. Verify before delivery:

```bash
unzip -t course-scorm12.zip
python3 scripts/scorm_asset_doctor.py inspect course-scorm12.zip
```

Accept only if `scorm_version` is `SCORM 1.2-like`, `missing_local_image_refs` is `0`, `risky_image_refs` is `0`, `manifest_missing_refs` is `0`, and ZIP integrity passes.

## Text Migration Rules

When using a working package as a base, migrate only user-visible strings. Safe keys include:

- `title`
- `heading`
- `paragraph`
- `description`
- `caption`
- `feedback`
- `feedbackCorrect`
- `feedbackIncorrect`
- `completeHint`
- `matchTitle`
- `label`

Do not migrate these unless deliberately rebuilding assets:

- `id`, `courseId`, `globalBlockId`
- `key`, `src`, `crushedKey`, `thumbnail`, `originalUrl`
- runtime chunk names under `scormcontent/lib/...`
- SCORM driver files
- manifest schema declarations from another SCORM version

## SCORM 2004 To 1.2 Notes

SCORM 2004 to 1.2 is not a pure text transform. The manifest namespaces, sequencing metadata, and LMS API expectations differ. This skill now produces a conservative `SCORM 1.2-like` package by preserving the course runtime, normalizing assets, replacing the manifest with a SCORM 1.2 manifest, and setting Rustici `strLMSStandard` to `SCORM`. Report that LMS smoke testing is still required before treating the package as production-proven.

Use `references/conversion-notes.md` only when you need deeper conversion or manifest guidance.

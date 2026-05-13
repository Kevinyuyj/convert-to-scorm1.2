---
name: scorm2004-to-12
description: Repair and rebuild SCORM packages, especially SCORM 2004/Rise packages with broken image loading, asset path mismatches, or requests to convert/rebuild as SCORM 1.2; also patch flat custom HTML SCORM runtimes for SCORM 1.2 bookmark/resume, completion, score, session time, and language-aware resume. Use when Codex is given SCORM ZIP files, Rise exports, imsmanifest.xml, scormcontent/index.html, root index.html + js/SCORMlocal.js packages, or asks for SCORM 2004 to 1.2 conversion, runtime tracking repair, localization without breaking assets, or LMS completion diagnostics.
version: 0.2.3
license: MIT
compatibility:
  - codex
  - agent-skills
metadata:
  homepage: https://github.com/Kevinyuyj/convert-to-scorm1.2
  agents:
    openai: agents/openai.yaml
    hermes: agents/hermes.yaml
    openclaw: agents/openclaw.yaml
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

For non-Rise/custom HTML packages, first identify the runtime shape. A known supported flat custom runtime has:

- root `index.html`
- `js/SCORMlocal.js`
- `js/pages/closing-page.js`
- `js/pages/select-lang.js`
- `js/controller/moduleStart.js`
- often a bundled `js/scripts.js`

Treat runtime tracking as a SCORM API contract problem, not an asset problem.

## Decision Tree

1. If the package is a Rise export with `scormcontent/index.html`, use `scorm_asset_doctor.py`.
2. If the package is a flat custom runtime with root `index.html` and `js/SCORMlocal.js`, use `scorm_runtime12_patch.py` for tracking fixes.
3. If a known-good same-course SCORM 1.2 package exists, use it as the structural base. Copy only visible text/course data from the bad package and preserve the good package runtime, assets, manifest resource list, and SCORM driver.
4. If no SCORM 1.2 base exists, run the package through `convert12`: decode course JSON, audit assets, normalize risky paths, update JSON and manifest together, switch the Rustici driver standard to SCORM 1.2, and repackage.
5. Treat the result as `SCORM 1.2-like` unless an LMS smoke test confirms launch, bookmarking, completion, score, session time, and resume behavior.
6. Never mix runtime chunks from unrelated exports unless the course JSON and chunk manifests are proven compatible.
7. If the package is not Rise/Rustici based, inspect the course-layer runtime before promising conversion. Look for wrappers such as `pipwerks.SCORM`, custom `SCORMlocal.js`, navigation controllers, bookmark writes, and score/completion code.

## Workflow

1. Work in an isolated directory; never modify the original ZIP.
2. Run the asset doctor inspection:

```bash
python3 scripts/scorm_asset_doctor.py inspect course.zip
```

If your agent is running from the repository root, use `python3 scorm2004-to-12/scripts/scorm_asset_doctor.py ...`. If your agent expands a skill-relative base directory, use that base directory consistently.

3. Review:

- course data found or not found, including both inline base64 and older `locales/*.js` JSONP formats
- SCORM version inferred from `imsmanifest.xml`
- local image reference count
- missing image references
- URL-encoded, space, non-ASCII, or case-risk paths
- manifest declarations missing for referenced assets

4. Default Rise conversion command:

```bash
python3 scripts/scorm_asset_doctor.py convert12 course.zip --output course-scorm12.zip
```

5. If the user only asks for asset repair without SCORM 1.2 conversion, run:

```bash
python3 scripts/scorm_asset_doctor.py repair course.zip --output repaired.zip --ascii-assets
```

6. For a flat custom runtime, inspect then patch tracking:

```bash
python3 scorm2004-to-12/scripts/scorm_runtime12_patch.py inspect course.zip
python3 scorm2004-to-12/scripts/scorm_runtime12_patch.py patch course.zip --output course-scorm12.zip
```

Use this only when `inspect` reports a supported flat custom runtime. It repairs SCORM 1.2 runtime behavior for:

- bookmark/resume through `cmi.core.lesson_location`
- custom learning progress, selected language, and page state through `cmi.suspend_data`
- final quiz score through `cmi.core.score.raw`
- completion/pass/fail through `cmi.core.lesson_status`
- session duration through `cmi.core.session_time`
- end-of-attempt persistence through `LMSCommit` plus `LMSFinish`/`quit`
- known SCORM 2004-only runtime fields in supported vendor packages, including `cmi.progress_measure`, `cmi.completion_status`, `cmi.success_status`, `cmi.score.scaled`, `cmi.session_time`, and `cmi.exit`
- simple root manifest framing from SCORM 2004 metadata to SCORM 1.2 metadata

After patching, run `inspect` on the output ZIP. Do not deliver it as a fresh SCORM 1.2 conversion unless `scorm_12_manifest` is `true`, `has_scorm12_time_helper` is `true`, and `legacy_2004_field_count` is `0`. If any of those checks fail, treat it as a script gap or unsupported runtime shape and inspect manually before delivery.

7. If localizing from another package, do not migrate media/resource fields. Transfer only visible text fields from the reference course JSON. Preserve the destination package media keys and runtime fields.
8. Verify before delivery:

```bash
unzip -t course-scorm12.zip
python3 scripts/scorm_asset_doctor.py inspect course-scorm12.zip
```

Accept only if `scorm_version` is `SCORM 1.2-like`, `missing_local_image_refs` is `0`, `risky_image_refs` is `0`, `manifest_missing_refs` is `0`, and ZIP integrity passes.

For non-Rise packages, `scorm_asset_doctor.py inspect` may fail because there is no `scormcontent/index.html`. That is a package-shape mismatch, not proof that the ZIP is invalid. Fall back to manifest inspection, ZIP integrity, runtime JavaScript inspection, and LMS smoke testing.

For runtime patches, additionally run a local mock or LMS smoke test that confirms:

- `scorm_runtime12_patch.py inspect output.zip` reports `legacy_2004_field_count: 0`
- reopening resumes at the stored page
- selected language is restored before loading the resumed page
- progress reaches 100% only after the final page/quiz path
- passing quiz sets `cmi.core.lesson_status` to `passed` or LMS-equivalent complete
- score is recorded in `cmi.core.score.raw`
- learning time increases through `cmi.core.session_time`
- desktop and mobile LMS launchers both resume at the saved page and language

See `references/runtime-tracking.md` for the SCORM 1.2 tracking contract and patching rules.

## Flat Runtime Tracking Rules

When repairing a custom runtime, make the runtime contract explicit before editing:

- `lesson_location` is the short bookmark. For multilingual packages, store `languagecode|currentPage`, for example `zh-cn|chapter-3-page`.
- `suspend_data` is the rich JSON state. It should include page, progress, chapter state, quiz state, and language metadata.
- Restore `lesson_location` first on launch. Then parse and merge `suspend_data`. If `suspend_data` is invalid, keep the page/language from `lesson_location`.
- Commit immediately after language selection and page navigation. Mobile LMS shells may not reliably run unload handlers.
- Do not make resume depend on `learningProgress < 1`.
- Do not let a default `_goto=select-lang` parameter override a stored non-language page.
- Do not mirror progress into `cmi.core.score.raw`; only the final quiz or final assessment score belongs there.
- Guard final submit/quit so `LMSFinish` is called once.

For packages with both source files and a bundled runtime, inspect `index.html`. If the browser loads `js/scripts.js`, update or verify the bundle as the source of truth. A common broken patch changes `js/controller/moduleStart.js` but leaves `js/scripts.js` still launching `select-lang`.

Load `references/runtime-debugging-notes.md` when diagnosing duplicate learning time, conflicting unload handlers, or ambiguous final exit behavior.

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

Use `references/runtime-tracking.md` when diagnosing LMS progress, completion, score, selected-language resume, or learning-time issues.

Use `references/runtime-debugging-notes.md` when the package has custom course-layer SCORM JavaScript, bookmark/resume bugs, completion bugs, score bugs, suspicious learning-time records, duplicate unload/pagehide handlers, or uncertain `cmi.core.exit` behavior.

## Agent Compatibility

This skill is written as a plain `SKILL.md` directory so it can be read by Codex and by agents that support AgentSkills-style folders. The script does not depend on Codex-specific APIs. For agents that do not auto-expand skill-relative paths, run commands from the repository root or replace `scorm2004-to-12/` with the local skill directory.

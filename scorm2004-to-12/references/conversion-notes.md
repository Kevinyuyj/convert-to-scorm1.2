# Conversion Notes

## Common Failure Causes

- JSON references `foo%20bar.jpg` while the file is `foo bar.jpg`, or the reverse.
- The LMS treats manifest `href` literally and does not normalize URL encoding the same way as the browser runtime.
- Asset names contain spaces, non-ASCII characters, punctuation, or case differences.
- A package was rebuilt from a different Rise export, so `scormcontent/lib/mondrian/*.js` chunks and course JSON were generated together and should not be mixed casually.
- SCORM 2004 manifests include sequencing/navigation schemas and resources that are not equivalent to SCORM 1.2.

## Preferred Repair Strategy Without A 1.2 Base

1. Decode the embedded course JSON.
2. Build a table of every local media reference.
3. Normalize referenced files to safe ASCII names under `scormcontent/assets`.
4. Update all exact and URL-encoded references in course JSON.
5. Update `imsmanifest.xml` file declarations.
6. Re-encode the JSON and repackage.
7. Inspect the rebuilt ZIP and test in LMS.

## When A True 1.2 Output Is Safe

A 1.2 output is safe when one of these is true:

- A same-course SCORM 1.2 export exists and is used as the base.
- A known-compatible 1.2 template from the same authoring/runtime version exists and has been tested.
- The user accepts a smoke-tested but not specification-guaranteed conversion.

Otherwise, deliver a repaired 2004 package and explain that down-conversion needs a donor/template.

## Standards Anchors

Use these as guardrails when distinguishing SCORM-standard requirements from Rise-package implementation details:

- ADL SCORM 2004 4th Edition Testing Requirements require a content package to contain `imsmanifest.xml` at the package root, keep the manifest well-formed, validate against the relevant IMS/ADL XSDs, include required supporting schemas at package root, use a ZIP Package Interchange File, and contain at least one SCO or asset resource.
- The manifest/resource/file relationship is a SCORM content packaging concern. The internal Rise JSON fields such as `crushedKey`, `src`, and `originalUrl` are authoring-tool/runtime implementation details, not SCORM-standard fields.
- Treat asset repair as a runtime-package repair step. Treat SCORM 2004 to 1.2 conversion as a standards/profile change that needs a compatible 1.2 manifest/driver template or donor export.

Primary references checked:

- ADL SCORM 2004 4th Edition Testing Requirements: https://adlnet.gov/assets/uploads/SCORM_2004_4ED_v1_1_TR_20090814.pdf
- ADL SCORM Best Practices Guide for Programmers: https://adlnet.gov/assets/uploads/SCORM_Users_Guide_for_Programmers.pdf
- SCORM.com technical explanation of manifest structure: https://scorm.com/scorm-explained/technical-scorm/content-packaging/manifest-structure/

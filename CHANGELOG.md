# Changelog

## 2026-04-30

- Added `scorm2004-to-12` skill for SCORM 2004 to SCORM 1.2-like conversion.
- Added `scripts/scorm_asset_doctor.py` with `inspect`, `repair`, and `convert12` commands.
- Added support for both Rise course data formats:
  - inline base64 in `scormcontent/index.html`
  - JSONP base64 in `scormcontent/locales/*.js`
- Added asset-path normalization and manifest synchronization checks.
- Added public README with usage and validation guidance.

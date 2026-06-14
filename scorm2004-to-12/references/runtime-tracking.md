# Runtime Tracking Reference

Use this reference when a SCORM package launches but the LMS does not correctly record progress, completion, score, time, resume location, or selected language.

## SCORM 1.2 Runtime Contract

For SCORM 1.2, keep tracking inside these fields:

- `cmi.core.lesson_status`: `incomplete`, `completed`, `passed`, or `failed`.
- `cmi.core.lesson_location`: short bookmark string for resume. For multilingual packages, prefer `languagecode|page-id`, for example `zh-cn|chapter-3-page`.
- `cmi.suspend_data`: custom JSON state such as progress, completed chapters, current page, quiz state, and selected language.
- `cmi.core.score.raw`: final score only. Do not mirror page progress into score.
- `cmi.core.score.min` and `cmi.core.score.max`: normally `0` and `100`.
- `cmi.core.session_time`: current session duration in `HHHH:MM:SS.SS`.
- `cmi.core.exit`: `suspend` for incomplete attempts, empty string for final states.

SCORM 1.2 has no standard `cmi.progress_measure`, `cmi.success_status`, or `cmi.score.scaled`. Those are SCORM 2004 concepts.

## Bookmark And Language Resume

Persist both:

- `cmi.core.lesson_location = languagecode + "|" + moduleData.currentPage`
- `cmi.suspend_data = JSON.stringify(moduleData)`

`lesson_location` must be short and independently useful. Mobile LMS shells sometimes restore this field more reliably than large JSON state. Do not store the entire JSON object in `lesson_location`.

When the package has a language selection page, include language in both `lesson_location` and `suspend_data`:

```json
{
  "currentPage": "chap3-video-page",
  "learningProgress": 0.63,
  "languagecode": "zh-cn",
  "languagename": "Chinese (Simplified)",
  "bcp47languagetag": "zh-Hans"
}
```

On launch, restore the selected language before loading the resumed page. If a `_lang` URL parameter is present, treat it as an explicit override. Otherwise, do not default to English until after checking saved language.

Restore in this order:

1. Read and parse `cmi.core.lesson_location`.
2. Apply `languagecode` and `currentPage` from the bookmark if present.
3. Read and parse `cmi.suspend_data`.
4. Merge richer state from `suspend_data`, but do not let it erase the bookmark page or language.
5. If `suspend_data` is invalid, keep the bookmark restore and continue.

Do not make resume conditional on `learningProgress < 1`. The learner may close at any progress value, and completed attempts may still need a sensible review entry point.

If the launch URL contains `_goto=select-lang`, do not let it override a saved non-language page. A default language-selector launch parameter is a common reason desktop resume works while mobile resume starts over.

## Learning Time

Write `cmi.core.session_time` when the launch is terminating. Do not write it during ordinary bookmark/progress commits unless LMS testing proves termination-time reporting is lost.

For active sessions:

1. Calculate elapsed time from the SCO initialization timestamp.
2. Commit `cmi.suspend_data`, `cmi.core.lesson_location`, and the current non-final `lesson_status`.
3. Call `LMSCommit` through the wrapper.

For final pass/fail:

1. Set final `lesson_status`.
2. Set final score if a quiz score exists.
3. Set `cmi.core.session_time`.
4. Set `cmi.core.exit = ""`.
5. Commit, then call `LMSFinish`/wrapper `quit`.

Guard against duplicate finish calls because browsers often fire `pagehide`, `beforeunload`, and `unload`. Only mark a launch as terminated after `quit` does not clearly fail, so a later close event can retry if the first one was blocked.

## Flat Custom Runtime Patch Pattern

Use `scripts/scorm_runtime12_patch.py` for known packages with this layout:

```text
index.html
js/SCORMlocal.js
js/pages/closing-page.js
js/pages/select-lang.js
js/controller/moduleStart.js
js/scripts.js
```

The patch is pattern-based and should not be applied blindly to unrelated runtimes.

For this layout, check `index.html` before editing. If it loads `js/scripts.js`, that bundle is the browser source of truth. Updating only `js/controller/moduleStart.js`, `js/pages/select-lang.js`, or other source-like files can leave the actual course unchanged.

For supported flat custom runtimes, the patcher now also rewrites a simple root `imsmanifest.xml` from SCORM 2004 metadata to SCORM 1.2 metadata. This is intentionally conservative: it preserves the original identifier, organization, item, resource, title, and launch `href`, and it does not attempt to generate a full file inventory for arbitrary custom packages.

After patching, run `scripts/scorm_runtime12_patch.py inspect` on the output. Treat these as hard gates before delivery:

- `scorm_12_manifest` is `true`
- `manifest_scorm12_namespace` is `true`
- `manifest_scorm2004_namespace` is `false`
- `manifest_uses_scormtype_lower` is `true`
- `manifest_uses_scormType_camel` is `false`
- `manifest_scormtype_values` includes `sco`
- `manifest_missing_file_count` is `0`
- `has_scorm12_time_helper` is `true`
- `legacy_2004_field_count` is `0`

Expected behavior after patching:

- Mid-course page navigation commits `suspend_data`, language-aware `lesson_location`, and `lesson_status=incomplete`.
- Termination commits `session_time` and calls `LMSFinish` through the wrapper.
- Selected language is committed immediately after selection.
- Resume loads the saved language before loading the bookmarked page.
- Resume still works if `suspend_data` parsing fails but `lesson_location` is present.
- Passing final score automatically records score and `lesson_status=passed`.
- Final pass commits session time and calls `quit` exactly once.

## Common Failure Modes

- Page display breaks after patching: the bundle and source files are out of sync, or a minified replacement changed syntax. Compare the loaded `js/scripts.js` against the intended source behavior.
- Desktop resumes but mobile restarts at language selection: the package waits until unload to commit, `lesson_location` stores only the page without language, or `_goto=select-lang` overrides the bookmark.
- Progress records but resume fails: the LMS is receiving `suspend_data`, but the launch path ignores `cmi.core.lesson_location` or parses JSON before using the short bookmark.
- Resume works but selected language is wrong: language was only stored in `suspend_data` and not restored before page loading.
- Completion records but score is wrong: page progress was mirrored into `score.raw`. Only final quiz or final assessment score belongs in `score.raw`.
- Learning time is duplicated: `pagehide`, `beforeunload`, `unload`, and explicit final submit all call the same save path without a one-shot guard.
- Several short close/reopen cycles appear as one longer LMS row, but longer idle gaps appear as separate rows: usually LMS session aggregation, not a course-side `session_time` field bug.

## LMS Smoke Test

Always verify in the target LMS:

1. Start a new attempt, choose a non-default language, view several pages, close.
2. Relaunch and confirm the same language and page resume.
3. Continue to final quiz, pass, and close.
4. Confirm LMS status is complete or passed, progress is 100%, score is recorded, and learning time increased.
5. Relaunch after completion and confirm the LMS behavior is acceptable for review/completed attempts.

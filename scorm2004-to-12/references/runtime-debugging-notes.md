# Runtime Debugging Notes

## Why Manifest Conversion Is Not Enough

Some vendor SCORM packages are not Rise exports and do not use the same `scormcontent/index.html` structure. They may use a root `index.html`, a custom SCORM wrapper, and course-specific JavaScript for navigation, progress, score, bookmarking, and session time.

For these packages, treat the manifest as only one layer. The real LMS behavior is often controlled by files such as:

- `js/SCORM_API_wrapper.js`
- `js/SCORMlocal.js`
- `js/controller/navigationControl.js`
- `js/controller/moduleStart.js`
- bundled/minified runtime copies such as `js/scripts.js`

## SCORM 1.2 Runtime Fields

When converting course-layer runtime behavior toward SCORM 1.2, use SCORM 1.2 fields:

- `cmi.core.lesson_status` for `incomplete`, `completed`, `passed`, or `failed`
- `cmi.core.lesson_location` for bookmark/resume location
- `cmi.suspend_data` for custom serialized state
- `cmi.core.score.raw` for score when the LMS expects score display
- `cmi.core.session_time` only for the current session duration
- `cmi.core.exit` with `suspend` when the learner should resume later

Do not rely on SCORM 2004-only progress fields such as `cmi.progress_measure` when targeting SCORM 1.2.

## Exit State Gate

Do not treat `cmi.core.exit = "suspend"` as a universal learning-time fix. If both variants pass the LMS smoke test, prefer the cleaner SCORM 1.2 session semantics:

```js
var lessonStatus = scorm.get("cmi.core.lesson_status");
var isFinalStatus = lessonStatus == "completed" || lessonStatus == "passed" || lessonStatus == "failed";
scorm.set("cmi.core.exit", isFinalStatus ? "" : "suspend");
```

Use always-`suspend` only as an LMS-specific compatibility fallback when testing proves the conditional form fails to record the desired learning-time or resume behavior.

Smoke test both variants only when the LMS behavior is unclear:

1. Complete or pass the course and confirm completion/pass status remains stable.
2. Confirm learning time is recorded close to the actual open session time.
3. Relaunch after completion and confirm the LMS does not incorrectly force an unfinished resume state.
4. Relaunch before completion and confirm the unfinished attempt resumes correctly.

## Bookmark And Resume Gate

A converted package should not only write a bookmark during unload. Write and commit bookmark state when meaningful navigation happens, then verify that launch logic consumes the saved bookmark instead of always routing to the default first page.

Minimum smoke test:

1. Launch the package in an LMS.
2. Navigate to a middle page.
3. Close the course window.
4. Relaunch the same registration.
5. Confirm it resumes to the saved page and keeps the expected unlocked/progress state.

## Learning Time Gate

`cmi.core.session_time` should represent the elapsed time for the current launch session. The LMS is responsible for accumulating total time.

Avoid writing `cmi.core.session_time` on every progress or bookmark commit. If every progress save writes session time, some LMSs record each commit as a separate learning-time row, producing many small entries such as one-minute or two-minute fragments instead of one row for the actual time the learner kept the course open.

Recommended pattern:

1. Record a session start timestamp during SCORM initialization.
2. During progress/bookmark saves, commit `lesson_location`, `suspend_data`, status, and score as needed, but do not update `session_time`.
3. On real termination/unload, compute elapsed time once, set `cmi.core.session_time`, set `cmi.core.exit`, commit, then quit.

Smoke test:

1. Launch and wait three to five minutes without closing.
2. Navigate enough to trigger progress/bookmark saves.
3. Close the course.
4. Confirm the LMS reports one session duration close to the actual open time, not a sequence of one-minute fragments.

## Completion And Score Gate

Keep resume/progress and final score/pass behavior as separate acceptance gates. A package can resume correctly while still failing final completion or score reporting.

Minimum final gate:

1. Complete the final page or quiz.
2. Confirm `lesson_status` becomes `completed`, `passed`, or `failed` according to the course rules.
3. Confirm `score.raw` is reported only when the course actually has score semantics or the LMS requires score display.
4. Relaunch after completion and confirm the course does not incorrectly reset an already-final status.

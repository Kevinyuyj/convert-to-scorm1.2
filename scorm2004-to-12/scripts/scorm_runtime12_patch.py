#!/usr/bin/env python3
"""Patch known flat SCORM runtimes for stricter SCORM 1.2 tracking.

This script targets custom HTML packages that are not Rise exports and use a
root-level layout like:

  index.html
  js/SCORMlocal.js
  js/pages/closing-page.js
  js/pages/select-lang.js
  js/controller/moduleStart.js
  js/scripts.js

It is intentionally pattern-based. If the expected runtime files are missing,
inspect the package manually instead of pretending it is safe to patch.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any


RUNTIME_FILES = {
    "scorm": "js/SCORMlocal.js",
    "closing": "js/pages/closing-page.js",
    "select_lang": "js/pages/select-lang.js",
    "module_start": "js/controller/moduleStart.js",
    "bundle": "js/scripts.js",
}


TRACKING_PATCH_MARKER = "SCORM_RUNTIME12_TRACKING_PATCH"


TRACKING_PATCH = r'''

// SCORM_RUNTIME12_TRACKING_PATCH
(function () {
  if (window.__scormRuntime12TrackingPatch) return;
  window.__scormRuntime12TrackingPatch = true;

  function parseLessonLocation(location) {
    var parsedLocation = { languagecode: "", currentPage: "" };
    if (!location || location == "null") return parsedLocation;
    var parts = String(location).split("|");
    if (parts.length > 1) {
      parsedLocation.languagecode = parts[0];
      parsedLocation.currentPage = parts.slice(1).join("|");
    } else {
      parsedLocation.currentPage = location;
    }
    return parsedLocation;
  }

  function buildLessonLocation() {
    if (typeof moduleData == "undefined" || !moduleData.currentPage) return "";
    if (typeof localData != "undefined" && localData.languagecode) {
      return localData.languagecode + "|" + moduleData.currentPage;
    }
    return moduleData.currentPage;
  }

  function elapsedSessionTime() {
    var dtm = new Date();
    var n = dtm.getTime() - g_dtmInitialized.getTime();
    return centisecsToSCORM12Time(Math.floor(n / 10));
  }

  function syncRuntimeState() {
    if (typeof moduleData == "undefined" || typeof localData == "undefined") return;
    moduleData.languagecode = localData.languagecode;
    moduleData.languagename = localData.languagename;
    moduleData.bcp47languagetag = localData.bcp47languagetag;
    scorm.set("cmi.suspend_data", JSON.stringify(moduleData));
    scorm.set("cmi.core.lesson_location", buildLessonLocation());
    scorm.set("cmi.core.session_time", elapsedSessionTime());
  }

  function isFinalStatus(status) {
    return status == "completed" || status == "passed" || status == "failed";
  }

  var originalScormInitialize = window.ScormInitialize;
  window.ScormInitialize = function () {
    originalScormInitialize.apply(this, arguments);
    try {
      var lessonLocation = parseLessonLocation(scorm.get("cmi.core.lesson_location"));
      if (typeof moduleData != "undefined" && lessonLocation.currentPage) {
        moduleData.currentPage = lessonLocation.currentPage;
      }
      if (typeof localData != "undefined" && lessonLocation.languagecode) {
        localData.languagecode = lessonLocation.languagecode;
      }
      var suspendedData = scorm.get("cmi.suspend_data");
      if (suspendedData && suspendedData != "null" && typeof localData != "undefined") {
        var data = JSON.parse(suspendedData);
        localData.languagecode = lessonLocation.languagecode || data.languagecode || localData.languagecode;
        localData.languagename = data.languagename || localData.languagename;
        localData.bcp47languagetag = data.bcp47languagetag || localData.bcp47languagetag;
        if (typeof moduleData != "undefined") {
          moduleData.currentPage = lessonLocation.currentPage || data.currentPage || moduleData.currentPage;
        }
      }
    } catch (e) {
      console.log("SCORM runtime12 restore patch kept lesson_location and skipped invalid suspend_data", e);
    }
  };

  var originalSaveData = window.SaveData;
  window.SaveData = function () {
    if (window.__scormRuntime12Terminated) return;
    syncRuntimeState();
    var lessonStatus = scorm.get("cmi.core.lesson_status");
    scorm.set("cmi.core.exit", isFinalStatus(lessonStatus) ? "" : "suspend");
    originalSaveData.apply(this, arguments);
  };

  var originalSuspendData = window.SuspendData;
  window.SuspendData = function () {
    if (window.__scormRuntime12Terminated) return;
    if (originalSuspendData) originalSuspendData.apply(this, arguments);
    syncRuntimeState();
    scorm.save();
  };

  var originalScormTerminate = window.ScormTerminate;
  window.ScormTerminate = function () {
    if (window.__scormRuntime12Terminated) return;
    window.SaveData();
    scorm.quit();
    window.__scormRuntime12Terminated = true;
  };

  var originalStoreFinalScore = window.StoreFinalScore;
  window.StoreFinalScore = function (score) {
    if (window.__scormRuntime12Terminated) return;
    if (originalStoreFinalScore) originalStoreFinalScore.apply(this, arguments);
    var currentScore = score * 100 | 0;
    var previous = Number(previousScore || 0);
    var threshold = Number(masteryScore || 0);
    if (currentScore >= threshold || previous >= threshold) {
      scorm.set("cmi.core.lesson_status", "passed");
    } else {
      scorm.set("cmi.core.lesson_status", "failed");
    }
    syncRuntimeState();
    scorm.save();
  };
})();
'''


def unzip_to(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def zip_dir(src: Path, out_zip: Path) -> None:
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            zf.write(path, path.relative_to(src).as_posix())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def detect_runtime(root: Path) -> dict[str, Any]:
    files = {name: root / rel for name, rel in RUNTIME_FILES.items()}
    present = {name: path.exists() for name, path in files.items()}
    scorm_text = read_text(files["scorm"]) if present["scorm"] else ""
    manifest_text = read_text(root / "imsmanifest.xml") if (root / "imsmanifest.xml").exists() else ""
    return {
        "layout": "flat-custom-runtime" if present["scorm"] else "unknown",
        "present": present,
        "scorm_12_manifest": "<schemaversion>1.2</schemaversion>" in manifest_text,
        "uses_pipwerks": "pipwerks.SCORM" in scorm_text,
        "has_tracking_patch": TRACKING_PATCH_MARKER in scorm_text,
        "has_session_time": "cmi.core.session_time" in scorm_text,
        "has_lesson_location": "cmi.core.lesson_location" in scorm_text,
        "has_suspend_data": "cmi.suspend_data" in scorm_text,
        "has_lesson_status": "cmi.core.lesson_status" in scorm_text,
    }


def require_flat_runtime(root: Path) -> None:
    report = detect_runtime(root)
    missing = [name for name, ok in report["present"].items() if name in {"scorm", "closing", "select_lang", "module_start"} and not ok]
    if missing:
        raise SystemExit(f"not a supported flat custom runtime; missing: {', '.join(missing)}")
    if not report["uses_pipwerks"]:
        raise SystemExit("unsupported runtime: js/SCORMlocal.js does not use pipwerks.SCORM")


def replace_once(text: str, old: str, new: str) -> tuple[str, bool]:
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def patch_scormlocal(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    text, changed = replace_once(text, 'scorm.version = "2004";', 'scorm.version = "1.2";')
    if changed:
        changes.append("set scorm.version to 1.2")
    text, changed = replace_once(text, "var mirrorProgressToScore = true;", "var mirrorProgressToScore = false;")
    if changed:
        changes.append("disabled progress-to-score mirroring")
    if TRACKING_PATCH_MARKER not in text:
        text = text.rstrip() + TRACKING_PATCH + "\n"
        changes.append("appended SCORM 1.2 tracking patch")
    write_text(path, text)
    return changes


def patch_module_start(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    old = 'localData.languagecode = "en-gb";'
    new = 'if (!localData.languagecode) localData.languagecode = "en-gb";'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("preserve restored language before defaulting to English")
    old = 'else goto("select-lang");'
    new = 'else goto(moduleData.currentPage && moduleData.currentPage != "select-lang" ? moduleData.currentPage : "select-lang");'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("resume from stored lesson_location/currentPage")
    old = 'if(GetURLParameter("_goto")) goto(GetURLParameter("_goto"));'
    new = 'var resumePage = moduleData.currentPage && moduleData.currentPage != "select-lang" ? moduleData.currentPage : "select-lang";\n    var forcedPage = GetURLParameter("_goto");\n    if (forcedPage && !(resumePage != "select-lang" && forcedPage == "select-lang")) goto(forcedPage);'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("prevent _goto=select-lang from overriding stored bookmark")
    write_text(path, text)
    return changes


def patch_bundle(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    old = 'localData.languagecode="en-gb"'
    new = 'localData.languagecode||(localData.languagecode="en-gb")'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("preserve restored language in bundled startup code")
    old = 'GetURLParameter("_goto")?goto(GetURLParameter("_goto")):goto("select-lang")'
    new = 'GetURLParameter("_goto")&&!(moduleData.currentPage&&"select-lang"!==moduleData.currentPage&&"select-lang"===GetURLParameter("_goto"))?goto(GetURLParameter("_goto")):goto(moduleData.currentPage&&"select-lang"!==moduleData.currentPage?moduleData.currentPage:"select-lang")'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("resume bookmarked page in bundled startup code")
    old = 'localData.languagecode+"|"+(e||"")'
    if old in text:
        changes.append("bundled navigation already stores language-aware lesson_location")
    else:
        old = 'scorm.set("cmi.core.lesson_location",e||"")'
        new = 'scorm.set("cmi.core.lesson_location",localData.languagecode?localData.languagecode+"|"+(e||""):e||"")'
        text, changed = replace_once(text, old, new)
        if changed:
            changes.append("store language-aware lesson_location in bundled navigation")
    write_text(path, text)
    return changes


def patch_select_lang(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    anchor = "loadLocalizableResources(`data/${localData.languagecode}/select-lang.json`);"
    if anchor in text and "SuspendData();" not in text[text.index(anchor):text.index(anchor) + 160]:
        text = text.replace(anchor, anchor + "\n    SuspendData();", 1)
        changes.append("persist selected language immediately")
    write_text(path, text)
    return changes


def patch_closing(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    if "ScormTerminate();" not in text:
        pattern = re.compile(r"(if\s*\(\s*moduleData\.currentScore\s*>=\s*(\d+)\s*\)\s*\{\s*)")
        match = pattern.search(text)
        if match:
            max_score = 5
            insert = f"{match.group(1)}\n    StoreFinalScore(moduleData.currentScore / {max_score});\n    ScormTerminate();\n"
            text = text[:match.start()] + insert + text[match.end():]
            changes.append("auto-submit and terminate on passing final score")
    write_text(path, text)
    return changes


def patch_root(root: Path) -> dict[str, Any]:
    require_flat_runtime(root)
    changes: dict[str, list[str]] = {}
    for name, fn in [
        ("js/SCORMlocal.js", patch_scormlocal),
        ("js/controller/moduleStart.js", patch_module_start),
        ("js/scripts.js", patch_bundle),
        ("js/pages/select-lang.js", patch_select_lang),
        ("js/pages/closing-page.js", patch_closing),
    ]:
        path = root / name
        file_changes = fn(path)
        if file_changes:
            changes[name] = file_changes
    return {"changes": changes, "after": detect_runtime(root)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect or patch flat custom SCORM runtimes for SCORM 1.2 tracking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("zip")
    p_patch = sub.add_parser("patch")
    p_patch.add_argument("zip")
    p_patch.add_argument("--output", required=True)
    args = ap.parse_args()

    zip_path = Path(args.zip).resolve()
    with tempfile.TemporaryDirectory(prefix="scorm-runtime12-") as td:
        root = Path(td) / "pkg"
        root.mkdir()
        unzip_to(zip_path, root)
        if args.cmd == "inspect":
            print(json.dumps(detect_runtime(root), ensure_ascii=False, indent=2))
        elif args.cmd == "patch":
            report = patch_root(root)
            out = Path(args.output).resolve()
            zip_dir(root, out)
            report["output"] = str(out)
            print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

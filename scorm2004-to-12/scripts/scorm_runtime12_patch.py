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
from xml.sax.saxutils import escape


RUNTIME_FILES = {
    "scorm": "js/SCORMlocal.js",
    "closing": "js/pages/closing-page.js",
    "select_lang": "js/pages/select-lang.js",
    "module_start": "js/controller/moduleStart.js",
    "loadmodule": "js/controller/loadmodule.js",
    "bundle": "js/scripts.js",
}


TRACKING_PATCH_MARKER = "SCORM_RUNTIME12_TRACKING_PATCH"

LEGACY_2004_FIELDS = (
    "cmi.progress_measure",
    "cmi.completion_status",
    "cmi.success_status",
    "cmi.score.raw",
    "cmi.score.min",
    "cmi.score.max",
    "cmi.score.scaled",
    "cmi.session_time",
    "cmi.exit",
)


SCORM12_TIME_HELPER = r'''
function centisecsToSCORM12Time(n) {
  n = Math.max(n, 0);
  var totalSeconds = Math.floor(n / 100);
  var hours = Math.floor(totalSeconds / 3600);
  var minutes = Math.floor((totalSeconds % 3600) / 60);
  var seconds = totalSeconds % 60;
  var centiseconds = n % 100;
  return [hours, minutes, seconds].map(function (part) {
    return String(part).padStart(2, "0");
  }).join(":") + "." + String(centiseconds).padStart(2, "0");
}
'''


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
    if (window.__scormRuntime12Terminated) return true;
    window.SaveData();
    var quitResult = scorm.quit();
    if (quitResult !== false || !scorm.connection || !scorm.connection.isActive) {
      window.__scormRuntime12Terminated = true;
    }
    return quitResult;
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
    legacy_fields = [field for field in LEGACY_2004_FIELDS if field in scorm_text]
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
        "has_scorm12_time_helper": "function centisecsToSCORM12Time" in scorm_text,
        "legacy_2004_fields": legacy_fields,
        "legacy_2004_field_count": len(legacy_fields),
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


def replace_all(text: str, old: str, new: str) -> tuple[str, bool]:
    if old not in text:
        return text, False
    return text.replace(old, new), True


def inject_scorm12_time_helper(text: str) -> tuple[str, bool]:
    if "function centisecsToSCORM12Time" in text:
        return text, False
    marker = "\n// SCORM_RUNTIME12_TRACKING_PATCH"
    if marker in text:
        return text.replace(marker, "\n" + SCORM12_TIME_HELPER + marker, 1), True
    return text.rstrip() + "\n" + SCORM12_TIME_HELPER + "\n", True


def rewrite_scorm12_data_model(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    replacements = [
        ('console.log(`COMPLETION STATUS: ${scorm.get("cmi.completion_status")}`);\n    console.log(`SUCCESS STATUS: ${scorm.get("cmi.success_status")}`);', 'console.log(`LESSON STATUS: ${scorm.get("cmi.core.lesson_status")}`);'),
        ('console.log(`MINIMUM SCORE: ${scorm.get("cmi.score.min")}%`);', 'console.log(`MINIMUM SCORE: ${scorm.get("cmi.core.score.min")}%`);'),
        ('console.log(`MAXIMUM SCORE: ${scorm.get("cmi.score.max")}%`);', 'console.log(`MAXIMUM SCORE: ${scorm.get("cmi.core.score.max")}%`);'),
        ('console.log(`SCORE: ${scorm.get("cmi.score.raw")}%`);\n    console.log(`SCORE SCALED: ${scorm.get("cmi.score.scaled")}/1`);', 'console.log(`SCORE: ${scorm.get("cmi.core.score.raw")}%`);'),
        ('scorm.set("cmi.score.min", 0);', 'scorm.set("cmi.core.score.min", 0);'),
        ('scorm.set("cmi.score.max", 100);', 'scorm.set("cmi.core.score.max", 100);'),
        ('previousScore = scorm.get("cmi.score.raw");', 'previousScore = scorm.get("cmi.core.score.raw");'),
        ('scorm.set("cmi.score.raw", 0);', 'scorm.set("cmi.core.score.raw", 0);'),
        ('var previousProgress = scorm.get("cmi.progress_measure");\n    console.log(`PREVIOUS PROGRESS: ${previousProgress}/1`);\n\n    if (previousProgress == 1) {\n      console.log(`PREVIOUS COMPLETION STATUS: ${scorm.get("cmi.completion_status")}`);\n    }\n    else {\n      console.log("SETTING COMPLETION STATUS");\n      scorm.set("cmi.completion_status", "incomplete");\n      console.log(`NEW COMPLETION STATUS: ${scorm.get("cmi.completion_status")}`);\n\n      console.log("SETTING SUCCESS STATUS");\n      scorm.set("cmi.success_status", "unknown");\n      console.log(`NEW SUCCESS STATUS: ${scorm.get("cmi.success_status")}`);\n    }', 'var lessonStatus = scorm.get("cmi.core.lesson_status");\n    console.log(`PREVIOUS LESSON STATUS: ${lessonStatus}`);\n\n    if (lessonStatus == "completed" || lessonStatus == "passed") {\n      console.log(`PREVIOUS LESSON STATUS: ${lessonStatus}`);\n    }\n    else {\n      console.log("SETTING LESSON STATUS");\n      scorm.set("cmi.core.lesson_status", "incomplete");\n      console.log(`NEW LESSON STATUS: ${scorm.get("cmi.core.lesson_status")}`);\n    }'),
        ('scorm.set("cmi.session_time", centisecsToISODuration(Math.floor(n / 10)));', 'scorm.set("cmi.core.session_time", centisecsToSCORM12Time(Math.floor(n / 10)));'),
        ('scorm.set("cmi.exit", "suspend");', 'scorm.set("cmi.core.exit", "suspend");'),
        ('var previousProgress = scorm.get("cmi.progress_measure");\n  var currentProgress = number;\n\n  if (!previousProgress) previousProgress = 0;\n\n  if (currentProgress > previousProgress) {\n    scorm.set("cmi.progress_measure", currentProgress);\n    console.log(`NEW STORED PROGRESS: ${scorm.get("cmi.progress_measure")}/1`);\n  }', 'var currentProgress = number;\n  console.log(`CURRENT PROGRESS: ${currentProgress}/1`);'),
        ('scorm.set("cmi.completion_status", "completed");', 'scorm.set("cmi.core.lesson_status", "completed");'),
        ('console.log(`NEW STORED COMPLETION STATUS: ${scorm.get("cmi.completion_status")}`);', 'console.log(`NEW STORED LESSON STATUS: ${scorm.get("cmi.core.lesson_status")}`);'),
        ('scorm.set("cmi.score.raw", currentScore);\n    scorm.set("cmi.score.scaled", scaledScore);\n    console.log(`NEW STORED SCORE: ${scorm.get("cmi.score.raw")}% (SCALED: ${scorm.get("cmi.score.scaled")}/1)`);', 'scorm.set("cmi.core.score.raw", currentScore);\n    console.log(`NEW STORED SCORE: ${scorm.get("cmi.core.score.raw")}%`);'),
        ('scorm.set("cmi.success_status", "failed");', 'scorm.set("cmi.core.lesson_status", "failed");'),
        ('console.log(`NEW SUCCESS STATUS: ${scorm.get("cmi.success_status")}`);', 'console.log(`NEW LESSON STATUS: ${scorm.get("cmi.core.lesson_status")}`);'),
        ('console.log(`SUCCESS STATUS: ${scorm.get("cmi.success_status")}`);', 'console.log(`LESSON STATUS: ${scorm.get("cmi.core.lesson_status")}`);'),
        ('scorm.set("cmi.success_status", "passed");', 'scorm.set("cmi.core.lesson_status", "passed");'),
        ('console.log(`SCORE STORED IN LMS: ${scorm.get("cmi.score.raw")}%`);', 'console.log(`SCORE STORED IN LMS: ${scorm.get("cmi.core.score.raw")}%`);'),
    ]
    for old, new in replacements:
        text, changed = replace_all(text, old, new)
        if changed:
            changes.append("rewrote SCORM 2004 data-model calls to SCORM 1.2")
    return text, sorted(set(changes))


def patch_scormlocal(path: Path) -> list[str]:
    text = read_text(path)
    changes: list[str] = []
    text, changed = replace_once(text, 'scorm.version = "2004";', 'scorm.version = "1.2";')
    if changed:
        changes.append("set scorm.version to 1.2")
    text, field_changes = rewrite_scorm12_data_model(text)
    changes.extend(field_changes)
    text, changed = replace_once(text, "var mirrorProgressToScore = true;", "var mirrorProgressToScore = false;")
    if changed:
        changes.append("disabled progress-to-score mirroring")
    if TRACKING_PATCH_MARKER not in text:
        text = text.rstrip() + TRACKING_PATCH + "\n"
        changes.append("appended SCORM 1.2 tracking patch")
    text, changed = inject_scorm12_time_helper(text)
    if changed:
        changes.append("added SCORM 1.2 session_time helper")
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
    old = '$(function(){ScormInitialize(),moduleStart.init(),$(window).on("unload",function(){ScormTerminate()}),$(window).on("beforeunload",function(e){ScormTerminate()})})'
    new = '$(function(){ScormInitialize(),moduleStart.init();var e=function(){ScormTerminate()};$(window).on("pagehide",e),$(window).on("beforeunload",e),$(window).on("unload",e)})'
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("add pagehide and shared termination handler in bundled startup code")
    write_text(path, text)
    return changes


def patch_loadmodule(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = read_text(path)
    changes: list[str] = []
    old = '''  $(window).on("unload", function () {
    ScormTerminate();
  });

  $(window).on("beforeunload", function (event) {
    ScormTerminate();
  });'''
    new = '''  var terminateSession = function () {
    ScormTerminate();
  };

  $(window).on("pagehide", terminateSession);
  $(window).on("beforeunload", terminateSession);
  $(window).on("unload", terminateSession);'''
    text, changed = replace_once(text, old, new)
    if changed:
        changes.append("add pagehide and shared termination handler")
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


def first_match(text: str, pattern: str, default: str) -> str:
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else default


def patch_manifest(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = read_text(path)
    if "<schemaversion>1.2</schemaversion>" in text:
        return []

    identifier = first_match(text, r'<manifest[^>]*\sidentifier="([^"]+)"', "converted_course")
    org_default = first_match(text, r'<organizations[^>]*\sdefault="([^"]+)"', "ORG")
    org_id = first_match(text, r'<organization[^>]*\sidentifier="([^"]+)"', org_default)
    item_id = first_match(text, r'<item[^>]*\sidentifier="([^"]+)"', "ITEM")
    item_ref = first_match(text, r'<item[^>]*\sidentifierref="([^"]+)"', "RES")
    resource_id = first_match(text, r'<resource[^>]*\sidentifier="([^"]+)"', item_ref)
    href = first_match(text, r'<resource[^>]*\shref="([^"]+)"', "index.html")
    titles = re.findall(r"<title>(.*?)</title>", text, re.DOTALL)
    org_title = titles[0].strip() if titles else identifier
    item_title = titles[1].strip() if len(titles) > 1 else org_title

    manifest = f'''<?xml version="1.0" standalone="no"?>
<manifest identifier="{escape(identifier)}" version="1.2"
    xmlns="http://www.imsproject.org/xsd/imscp_v1p1"
    xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:lom="http://ltsc.ieee.org/xsd/LOM"
    xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                        http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd
                        http://ltsc.ieee.org/xsd/LOM lom.xsd">
    <metadata>
        <schema>ADL SCORM</schema>
        <schemaversion>1.2</schemaversion>
    </metadata>
    <organizations default="{escape(org_default)}">
        <organization identifier="{escape(org_id)}">
            <title>{escape(org_title)}</title>
            <item identifier="{escape(item_id)}" identifierref="{escape(item_ref)}" isvisible="true">
                <title>{escape(item_title)}</title>
            </item>
        </organization>
    </organizations>
    <resources>
        <resource identifier="{escape(resource_id)}" type="webcontent" adlcp:scormType="sco" href="{escape(href)}">
            <file href="{escape(href)}"/>
        </resource>
    </resources>
</manifest>
'''
    write_text(path, manifest)
    return ["converted manifest metadata to SCORM 1.2"]


def patch_root(root: Path) -> dict[str, Any]:
    require_flat_runtime(root)
    changes: dict[str, list[str]] = {}
    for name, fn in [
        ("js/SCORMlocal.js", patch_scormlocal),
        ("js/controller/moduleStart.js", patch_module_start),
        ("js/controller/loadmodule.js", patch_loadmodule),
        ("js/scripts.js", patch_bundle),
        ("js/pages/select-lang.js", patch_select_lang),
        ("js/pages/closing-page.js", patch_closing),
    ]:
        path = root / name
        file_changes = fn(path)
        if file_changes:
            changes[name] = file_changes
    manifest_changes = patch_manifest(root / "imsmanifest.xml")
    if manifest_changes:
        changes["imsmanifest.xml"] = manifest_changes
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

#!/usr/bin/env python3
"""Inspect and convert Articulate Storyline SCORM 2004 packages to SCORM 1.2.

This targets Storyline exports with:

  index_lms.html
  story.html
  lms/scormdriver.js
  imsmanifest.xml

The conversion is intentionally narrow: preserve all course files, switch the
Storyline driver standard from SCORM2004 to SCORM, and rewrite the manifest
from SCORM 2004 CAM 1.3 framing to SCORM 1.2 framing.
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


SCORM12_ADLCP_NS = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
SCORM2004_MARKERS = ("adlcp_v1p3", "adlseq_v1p3", "adlnav_v1p3", "imsss")
STORYLINE_FILES = ("index_lms.html", "story.html", "lms/scormdriver.js", "imsmanifest.xml")


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
    return path.read_text(encoding="utf-8-sig", errors="replace")


def first_match(text: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else default


def inspect_root(root: Path) -> dict[str, Any]:
    names = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    present = {name: name in names for name in STORYLINE_FILES}
    manifest_text = read_text(root / "imsmanifest.xml") if present["imsmanifest.xml"] else ""
    driver_text = read_text(root / "lms/scormdriver.js") if present["lms/scormdriver.js"] else ""

    schema = first_match(manifest_text, r"<schema>(.*?)</schema>")
    schemaversion = first_match(manifest_text, r"<schemaversion>(.*?)</schemaversion>")
    href = first_match(manifest_text, r'<resource[^>]*\shref="([^"]+)"')
    file_hrefs = re.findall(r'<file\b[^>]*\shref="([^"]+)"', manifest_text)
    missing_files = [href for href in file_hrefs if href not in names]
    driver_standards = re.findall(r'var\s+strLMSStandard\s*=\s*"([^"]+)"', driver_text)
    scormtype_values = re.findall(r"adlcp:scorm[Tt]ype=\"([^\"]+)\"", manifest_text)

    is_storyline = all(present.values())
    scorm_12_manifest = (
        schema == "ADL SCORM"
        and schemaversion == "1.2"
        and SCORM12_ADLCP_NS in manifest_text
        and not any(marker in manifest_text for marker in SCORM2004_MARKERS)
        and 'adlcp:scormtype="sco"' in manifest_text
        and "adlcp:scormType" not in manifest_text
        and not missing_files
    )
    scorm_2004_manifest = (
        schema == "ADL SCORM"
        and schemaversion == "CAM 1.3"
        and any(marker in manifest_text for marker in SCORM2004_MARKERS)
    )

    return {
        "layout": "storyline" if is_storyline else "unknown",
        "present": present,
        "manifest_schema": schema,
        "manifest_schemaversion": schemaversion,
        "manifest_scorm12_namespace": SCORM12_ADLCP_NS in manifest_text,
        "manifest_scorm2004_namespace": any(marker in manifest_text for marker in SCORM2004_MARKERS),
        "manifest_uses_scormtype_lower": 'adlcp:scormtype="' in manifest_text,
        "manifest_uses_scormType_camel": "adlcp:scormType" in manifest_text,
        "manifest_scormtype_values": sorted(set(scormtype_values)),
        "manifest_resource_href": href,
        "manifest_file_count": len(file_hrefs),
        "manifest_missing_files": missing_files,
        "manifest_missing_file_count": len(missing_files),
        "scorm_12_manifest": scorm_12_manifest,
        "scorm_2004_manifest": scorm_2004_manifest,
        "driver_standards": driver_standards,
        "driver_standard_is_scorm": driver_standards == ["SCORM"],
        "driver_standard_is_scorm2004": driver_standards == ["SCORM2004"],
    }


def require_storyline_2004(root: Path) -> dict[str, Any]:
    report = inspect_root(root)
    missing = [name for name, ok in report["present"].items() if not ok]
    if missing:
        raise SystemExit(f"not a supported Storyline package; missing: {', '.join(missing)}")
    if not report["scorm_2004_manifest"]:
        raise SystemExit("not a SCORM 2004 CAM 1.3 Storyline manifest")
    if not report["driver_standard_is_scorm2004"]:
        raise SystemExit("expected lms/scormdriver.js strLMSStandard to be SCORM2004")
    if report["manifest_missing_file_count"]:
        raise SystemExit(f"manifest references missing files: {report['manifest_missing_files'][:10]}")
    return report


def manifest_file_hrefs(text: str) -> list[str]:
    seen = set()
    hrefs = []
    for href in re.findall(r'<file\b[^>]*\shref="([^"]+)"', text):
        if href not in seen:
            seen.add(href)
            hrefs.append(href)
    return hrefs


def rewrite_manifest_12(text: str) -> str:
    identifier = first_match(text, r'<manifest[^>]*\sidentifier="([^"]+)"', "converted_course")
    org_default = first_match(text, r'<organizations[^>]*\sdefault="([^"]+)"', "ORG")
    org_id = first_match(text, r'<organization[^>]*\sidentifier="([^"]+)"', org_default)
    item_id = first_match(text, r'<item[^>]*\sidentifier="([^"]+)"', "ITEM")
    item_ref = first_match(text, r'<item[^>]*\sidentifierref="([^"]+)"', "RES")
    resource_id = first_match(text, r'<resource[^>]*\sidentifier="([^"]+)"', item_ref)
    href = first_match(text, r'<resource[^>]*\shref="([^"]+)"', "index_lms.html")
    titles = re.findall(r"<title>(.*?)</title>", text, re.DOTALL)
    org_title = titles[0].strip() if titles else identifier
    item_title = titles[1].strip() if len(titles) > 1 else org_title

    hrefs = manifest_file_hrefs(text)
    if href and href not in hrefs:
        hrefs.insert(0, href)
    file_lines = "\n".join(f'      <file href="{escape(file_href)}" />' for file_href in hrefs)

    return f'''<?xml version="1.0" encoding="utf-8" standalone="no"?>
<manifest identifier="{escape(identifier)}" version="1.2"
  xmlns="http://www.imsproject.org/xsd/imscp_v1p1"
  xmlns:adlcp="{SCORM12_ADLCP_NS}"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                      {SCORM12_ADLCP_NS} adlcp_rootv1p2.xsd">
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
    <resource identifier="{escape(resource_id)}" type="webcontent" adlcp:scormtype="sco" href="{escape(href)}">
{file_lines}
    </resource>
  </resources>
</manifest>
'''


def convert_root(root: Path) -> dict[str, Any]:
    before = require_storyline_2004(root)
    driver_path = root / "lms/scormdriver.js"
    manifest_path = root / "imsmanifest.xml"

    driver_text = read_text(driver_path)
    driver_text = driver_text.replace(
        'var strLMSStandard = "SCORM2004"',
        'var strLMSStandard = "SCORM"',
        1,
    )
    driver_path.write_text(driver_text, encoding="utf-8")
    manifest_path.write_text(rewrite_manifest_12(read_text(manifest_path)), encoding="utf-8")

    return {
        "before": before,
        "after": inspect_root(root),
        "changes": {
            "lms/scormdriver.js": ["set strLMSStandard from SCORM2004 to SCORM"],
            "imsmanifest.xml": ["rewrote SCORM 2004 CAM 1.3 manifest to SCORM 1.2 manifest"],
        },
    }


def run_on_zip(zip_path: Path, action: str, output: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="scorm-storyline12-") as td:
        root = Path(td) / "pkg"
        root.mkdir()
        unzip_to(zip_path, root)
        if action == "inspect":
            return inspect_root(root)
        if action == "convert12":
            if output is None:
                raise SystemExit("--output is required for convert12")
            report = convert_root(root)
            zip_dir(root, output.resolve())
            report["output"] = str(output.resolve())
            return report
        raise SystemExit(f"unknown action: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or convert Articulate Storyline SCORM 2004 packages to SCORM 1.2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inspect_p = sub.add_parser("inspect")
    inspect_p.add_argument("zip")
    convert_p = sub.add_parser("convert12")
    convert_p.add_argument("zip")
    convert_p.add_argument("--output", required=True)
    args = parser.parse_args()

    zip_path = Path(args.zip).resolve()
    output = Path(args.output).resolve() if getattr(args, "output", None) else None
    print(json.dumps(run_on_zip(zip_path, args.cmd, output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Inspect and repair SCORM/Rise asset references.

This script is intentionally conservative. It repairs broken or risky asset
paths in the embedded Rise course JSON and manifest, but it does not claim to
perform a full SCORM 2004 -> 1.2 standards conversion by itself.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

COURSE_RE = re.compile(r'deserialize\("([A-Za-z0-9+/=]+)"\)')
JSONP_RE = re.compile(r'__resolveJsonp\("course:([^"\\]+)","([A-Za-z0-9+/=]+)"\)')
LOCAL_PREFIXES = ("http://", "https://", "assets/rise/", "rise/")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def unzip_to(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def zip_dir(src: Path, out_zip: Path) -> None:
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            zf.write(path, path.relative_to(src).as_posix())


def find_index(root: Path) -> Path:
    p = root / "scormcontent" / "index.html"
    if not p.exists():
        raise SystemExit("scormcontent/index.html not found")
    return p


def decode_course_payload(encoded: str) -> dict[str, Any]:
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def encode_course_payload(data: dict[str, Any]) -> str:
    return base64.b64encode(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def load_course(root: Path) -> tuple[dict[str, Any], str, Path, str, str | None]:
    index = find_index(root)
    html = index.read_text(encoding="utf-8")
    m = COURSE_RE.search(html)
    if m:
        return decode_course_payload(m.group(1)), html, index, "inline", None

    locales = root / "scormcontent" / "locales"
    if locales.exists():
        for locale_file in sorted(locales.glob("*.js")):
            text = locale_file.read_text(encoding="utf-8")
            jm = JSONP_RE.search(text)
            if jm:
                return decode_course_payload(jm.group(2)), text, locale_file, "jsonp", jm.group(1)

    raise SystemExit("embedded Rise course data not found in index.html or scormcontent/locales/*.js")


def save_course(data: dict[str, Any], text: str, source_path: Path, mode: str, locale_name: str | None) -> None:
    encoded = encode_course_payload(data)
    if mode == "inline":
        new_text = COURSE_RE.sub(f'deserialize("{encoded}")', text, count=1)
    elif mode == "jsonp":
        if not locale_name:
            raise SystemExit("cannot save JSONP course without locale name")
        new_text = JSONP_RE.sub(f'__resolveJsonp("course:{locale_name}","{encoded}")', text, count=1)
    else:
        raise SystemExit(f"unknown course data mode: {mode}")
    source_path.write_text(new_text, encoding="utf-8")


def infer_scorm_version(root: Path) -> str:
    manifest = root / "imsmanifest.xml"
    if not manifest.exists():
        return "unknown-no-manifest"
    text = manifest.read_text(encoding="utf-8", errors="replace")
    if "imsss" in text or "adlseq" in text or "SCORM 2004" in text:
        return "SCORM 2004-like"
    if "adlcp_rootv1p2" in text or "scormtype" in text.lower():
        return "SCORM 1.2-like"
    return "unknown"


def walk_strings(obj: Any, path: tuple[str, ...] = ()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, path + (str(i),))
    elif isinstance(obj, str):
        yield path, obj


def collect_image_refs(data: dict[str, Any], include_original_url: bool = False) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    runtime_keys = {"src", "crushedKey", "thumbnail"}
    if include_original_url:
        runtime_keys.add("originalUrl")
    for path, value in walk_strings(data):
        key = path[-1] if path else ""
        if key not in runtime_keys:
            continue
        if not value or value.startswith(LOCAL_PREFIXES):
            continue
        suffix = Path(urllib.parse.unquote(value)).suffix.lower()
        if suffix not in IMAGE_EXTS:
            continue
        refs.append({"path": "/".join(path), "key": key, "value": value})
    return refs


def asset_exists(asset_dir: Path, ref: str) -> bool:
    return (asset_dir / ref).exists() or (asset_dir / urllib.parse.unquote(ref)).exists()


def risk_flags(ref: str) -> list[str]:
    flags = []
    decoded = urllib.parse.unquote(ref)
    if "%" in ref:
        flags.append("url-encoded")
    if any(ch.isspace() for ch in decoded):
        flags.append("space")
    if any(ord(ch) > 127 for ch in decoded):
        flags.append("non-ascii")
    if decoded != unicodedata.normalize("NFC", decoded):
        flags.append("unicode-normalization")
    if re.search(r"[^A-Za-z0-9._/\-]", decoded):
        flags.append("special-char")
    return sorted(set(flags))


def manifest_hrefs(root: Path) -> set[str]:
    manifest = root / "imsmanifest.xml"
    if not manifest.exists():
        return set()
    text = manifest.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r'<file\s+href="([^"]+)"', text))


def inspect_root(root: Path) -> dict[str, Any]:
    data, _, _, _, _ = load_course(root)
    asset_dir = root / "scormcontent" / "assets"
    refs = collect_image_refs(data)
    source_refs = collect_image_refs(data, include_original_url=True)
    original_url_refs = [r for r in source_refs if r["key"] == "originalUrl"]
    hrefs = manifest_hrefs(root)
    missing = [r for r in refs if not asset_exists(asset_dir, r["value"])]
    risky = [{**r, "flags": risk_flags(r["value"])} for r in refs if risk_flags(r["value"])]
    original_url_risky = [{**r, "flags": risk_flags(r["value"])} for r in original_url_refs if risk_flags(r["value"])]
    manifest_missing = []
    for r in refs:
        decoded = urllib.parse.unquote(r["value"])
        candidates = {
            "scormcontent/assets/" + r["value"],
            "scormcontent/assets/" + decoded,
            "scormcontent/assets/" + urllib.parse.quote(decoded),
        }
        if hrefs and not (hrefs & candidates):
            manifest_missing.append(r)
    return {
        "title": data.get("course", {}).get("title"),
        "scorm_version": infer_scorm_version(root),
        "local_image_refs": len(refs),
        "missing_local_image_refs": len(missing),
        "risky_image_refs": len(risky),
        "manifest_missing_refs": len(manifest_missing),
        "original_url_risky_metadata_refs": len(original_url_risky),
        "missing": missing,
        "risky": risky[:200],
        "original_url_risky_metadata": original_url_risky[:200],
        "manifest_missing": manifest_missing[:200],
    }


def safe_component(name: str) -> str:
    stem, ext = os.path.splitext(name)
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower() or "asset"
    ext = re.sub(r"[^A-Za-z0-9.]", "", ext.lower())
    return stem + ext


def set_string_at_path(obj: Any, path: str, value: str) -> None:
    cur = obj
    parts = path.split("/")
    for part in parts[:-1]:
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def repair_root(root: Path, ascii_assets: bool) -> dict[str, Any]:
    data, course_text, course_path, course_mode, locale_name = load_course(root)
    asset_dir = root / "scormcontent" / "assets"
    refs = collect_image_refs(data)
    mapping: dict[str, str] = {}
    used: set[str] = set()

    for r in refs:
        raw = r["value"]
        decoded = urllib.parse.unquote(raw)
        src = asset_dir / decoded
        if not src.exists():
            src = asset_dir / raw
        if not src.exists():
            continue
        rel = src.relative_to(asset_dir).as_posix()
        if not ascii_assets and not risk_flags(rel):
            continue
        parts = rel.split("/")
        safe_parts = [safe_component(p) if i == len(parts) - 1 else safe_component(p) for i, p in enumerate(parts)]
        new_rel = "/".join(safe_parts)
        base = Path(new_rel)
        counter = 2
        while new_rel in used or (asset_dir / new_rel).exists() and new_rel != rel:
            new_rel = (base.with_name(f"{base.stem}_{counter}{base.suffix}")).as_posix()
            counter += 1
        used.add(new_rel)
        if new_rel != rel:
            # Use a temporary hop so case-only renames are preserved on case-insensitive filesystems.
            tmp = asset_dir / f".scorm_tmp_{len(mapping)}_{safe_component(Path(rel).name)}"
            src.rename(tmp)
            parent = asset_dir / Path(rel).parent
            while parent != asset_dir:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            dest = asset_dir / new_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(dest)
        mapping[raw] = new_rel
        mapping[decoded] = new_rel
        mapping[urllib.parse.quote(decoded)] = new_rel

    for r in refs:
        if r["value"] in mapping:
            set_string_at_path(data, r["path"], mapping[r["value"]])

    save_course(data, course_text, course_path, course_mode, locale_name)

    manifest = root / "imsmanifest.xml"
    if manifest.exists() and mapping:
        text = manifest.read_text(encoding="utf-8", errors="replace")
        for old, new in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            text = text.replace("scormcontent/assets/" + old, "scormcontent/assets/" + new)
            text = text.replace("scormcontent/assets/" + urllib.parse.quote(old), "scormcontent/assets/" + new)
        manifest.write_text(text, encoding="utf-8")
    result = inspect_root(root)
    result["renamed_assets"] = len({v for v in mapping.values()})
    return result


def package_files(root: Path, exclude_root: set[str]) -> list[str]:
    files: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in exclude_root:
            continue
        files.append(rel)
    return files


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def convert_root_to_scorm12(root: Path, ascii_assets: bool = True) -> dict[str, Any]:
    # Repair assets first so the generated manifest describes the final file names.
    repair_report = repair_root(root, ascii_assets=ascii_assets)
    data, _, _, _, _ = load_course(root)
    title = data.get("course", {}).get("title") or "Converted SCORM Course"
    course_id = data.get("course", {}).get("id") or "converted_course"
    identifier = re.sub(r"[^A-Za-z0-9_-]+", "_", str(course_id)).strip("_") or "converted_course"

    manifest = root / "imsmanifest.xml"
    exclude_root = {
        "imsmanifest.xml",
        "XMLSchema.dtd",
        "datatypes.dtd",
        "imscp_v1p1.xsd",
        "adlcp_v1p3.xsd",
        "adlseq_v1p3.xsd",
        "adlnav_v1p3.xsd",
        "imsss_v1p0.xsd",
        "imsss_v1p0control.xsd",
        "imsss_v1p0delivery.xsd",
        "xml.xsd",
    }
    files = package_files(root, exclude_root)

    # SCORM 1.2 packages need these schema/support files when present in Rise exports.
    for required in ("imscp_rootv1p1p2.xsd", "adlcp_rootv1p2.xsd"):
        if not (root / required).exists():
            raise SystemExit(f"cannot convert to SCORM 1.2: missing {required}")

    lines = [
        '<?xml version="1.0" ?>',
        f'<manifest identifier="{xml_escape(identifier)}_scorm12" version="1"',
        '  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"',
        '  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd',
        '                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">',
        '  <metadata>',
        '    <schema>ADL SCORM</schema>',
        '    <schemaversion>1.2</schemaversion>',
    ]
    if (root / "metadata.xml").exists():
        lines.append('    <adlcp:location>metadata.xml</adlcp:location>')
    lines.extend([
        '  </metadata>',
        '  <organizations default="articulate_rise">',
        '    <organization identifier="articulate_rise">',
        f'      <title>{xml_escape(str(title))}</title>',
        '      <item identifier="i1" identifierref="r1" isvisible="true">',
        f'        <title>{xml_escape(str(title))}</title>',
        '      </item>',
        '    </organization>',
        '  </organizations>',
        '  <resources>',
        '    <resource identifier="r1" type="webcontent" adlcp:scormtype="sco" href="scormdriver/indexAPI.html">',
    ])
    for rel in files:
        lines.append(f'      <file href="{xml_escape(rel)}" />')
    lines.extend([
        '    </resource>',
        '  </resources>',
        '</manifest>',
    ])
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    driver = root / "scormdriver" / "driverOptions.js"
    if driver.exists():
        text = driver.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r'scope\.strLMSStandard\s*=\s*"SCORM2004"\s*;', 'scope.strLMSStandard = "SCORM";', text)
        driver.write_text(text, encoding="utf-8")

    result = inspect_root(root)
    result["converted_to"] = "SCORM 1.2-like"
    result["resource_files"] = len(files)
    result["renamed_assets"] = repair_report.get("renamed_assets", 0)
    return result


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect or repair SCORM/Rise asset references")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("zip")
    p_repair = sub.add_parser("repair")
    p_repair.add_argument("zip")
    p_repair.add_argument("--output", required=True)
    p_repair.add_argument("--ascii-assets", action="store_true", help="rename referenced assets to safe ASCII paths")
    p_convert = sub.add_parser("convert12")
    p_convert.add_argument("zip")
    p_convert.add_argument("--output", required=True)
    p_convert.add_argument("--keep-asset-names", action="store_true", help="do not normalize risky asset names before conversion")
    args = ap.parse_args()

    zip_path = Path(args.zip).resolve()
    with tempfile.TemporaryDirectory(prefix="scorm-doctor-") as td:
        root = Path(td) / "pkg"
        root.mkdir()
        unzip_to(zip_path, root)
        if args.cmd == "inspect":
            print_report(inspect_root(root))
        elif args.cmd == "repair":
            report = repair_root(root, args.ascii_assets)
            zip_dir(root, Path(args.output).resolve())
            report["output"] = str(Path(args.output).resolve())
            print_report(report)
        elif args.cmd == "convert12":
            report = convert_root_to_scorm12(root, ascii_assets=not args.keep_asset_names)
            zip_dir(root, Path(args.output).resolve())
            report["output"] = str(Path(args.output).resolve())
            print_report(report)


if __name__ == "__main__":
    main()

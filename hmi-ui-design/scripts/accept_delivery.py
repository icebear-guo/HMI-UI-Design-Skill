#!/usr/bin/env python3
"""Read-only file and pure-logic acceptance; never starts a browser or server."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import warnings
import zipfile

from PIL import Image
sys.dont_write_bytecode = True


BAD_PATH = re.compile(r'[<>:"|?*\x00-\x1f]')
DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def require(value, message):
    if not value:
        raise ValueError(message)


def no_links(path):
    for item in (path, *path.parents):
        require(not item.is_symlink() and not item.is_junction(), f"Linked path: {item}")


def relative(value):
    require(isinstance(value, str) and value, "Nonempty relative path required")
    parts = value.replace("\\", "/").split("/")
    require(all(p not in ("", ".", "..") and not BAD_PATH.search(p)
                and not p.endswith((".", " ")) and not DEVICE.match(p) for p in parts), "Unsafe relative path")
    return Path(*parts)


def package_file(root, value):
    path = root / relative(value)
    no_links(path)
    require(root in path.resolve().parents and path.is_file(), f"Missing package file: {value}")
    return path


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def json_value(value):
    return json.loads(value, object_pairs_hook=pairs_unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {v}")))


def numbers(value, length, positive=False):
    require(isinstance(value, list) and len(value) == length, "Invalid numeric array")
    require(all(type(v) in (int, float) and math.isfinite(v) and (v > 0 if positive else v >= 0)
                for v in value), "Invalid numeric values")
    return value


def unique(value, seen):
    require(isinstance(value, str) and ID.fullmatch(value), "Invalid identifier")
    require(value.casefold() not in seen, f"Duplicate identifier: {value}")
    seen.add(value.casefold())


def inventory(root):
    result = {}
    folded = set()
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            no_links(Path(current) / name)
        for name in files:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            relative(rel)
            require(rel.casefold() not in folded, "Case-insensitive duplicate file")
            folded.add(rel.casefold())
            result[rel] = path
    return result


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.resources, self.data_scripts, self.scripts, self.styles = [], [], [], []
        self.active, self.buffer = None, []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        require(tag != "base", "HTML base elements are unsupported")
        require(not any(k.lower().startswith("on") for k in attrs), "Inline event attributes are unsupported")
        require(not (tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh"), "HTML refresh is unsupported")
        for key in ("src", "href", "poster"):
            if attrs.get(key):
                self.resources.append(attrs[key])
        require("srcset" not in attrs, "Unexpected srcset")
        if tag == "script":
            require("src" not in attrs, "External script is unsupported")
            self.active = "data" if attrs.get("id") == "design-data" else "script"
            if self.active == "data":
                require(attrs.get("type") == "application/json", "Invalid design-data type")
            self.buffer = []
        elif tag == "style":
            self.active, self.buffer = "style", []
        if attrs.get("style"):
            self.styles.append(attrs["style"])

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.active:
            target = {"data": self.data_scripts, "script": self.scripts, "style": self.styles}[self.active]
            target.append("".join(self.buffer))
            self.active, self.buffer = None, []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)


def check_manifest(root, state):
    files = inventory(root)
    for folder in ("preview", "assets", "fonts", "specs"):
        require((root / folder).is_dir(), f"Missing folder: {folder}")
    require({"index.html", "manifest.json", "specs/design.json"} <= files.keys(), "Missing required files")
    manifest = json_value(files["manifest.json"].read_text(encoding="utf-8-sig"))
    model = json_value(files["specs/design.json"].read_text(encoding="utf-8-sig"))
    require(manifest["schema_version"] == model["schema_version"] and model["schema_version"] in {"1.0", "1.1"}, "Unsupported schema")
    require(isinstance(manifest["files"], list) and manifest["files"], "Empty manifest inventory")
    listed = set()
    for item in manifest["files"]:
        path = package_file(root, item["file"])
        rel = path.relative_to(root).as_posix()
        require(rel not in listed and rel != "manifest.json", "Duplicate or self-referential manifest entry")
        listed.add(rel)
        payload = path.read_bytes()
        require(type(item["bytes"]) is int and item["bytes"] == len(payload), f"Byte count mismatch: {rel}")
        require(item["sha256"] == hash_bytes(payload), f"Hash mismatch: {rel}")
    require(listed == set(files) - {"manifest.json"}, "Manifest inventory has omitted or extra files")
    for field in ("pages", "assets", "fonts"):
        require(isinstance(model[field], list), f"Invalid {field} collection")
        require(manifest[field] == len(model[field]), f"Count mismatch: {field}")
    require(model["pages"] and model["assets"], "Full delivery requires pages and assets")
    state.update(files=files, model=model)
    return f"{len(files)} files matched hashes and inventory"


def check_html(root, state):
    doc = Document((root / "index.html").read_text(encoding="utf-8-sig"))
    require(len(doc.data_scripts) == 1, "Exactly one design-data block required")
    require(json_value(doc.data_scripts[0]) == state["model"], "Embedded data differs from design.json")
    template = Path(__file__).resolve().parents[1] / "assets/delivery-viewer.template.html"
    trusted = Document(template.read_text(encoding="utf-8"))
    require([s.strip().replace("\r\n", "\n") for s in doc.scripts] ==
            [s.strip().replace("\r\n", "\n") for s in trusted.scripts], "Viewer behavior differs from maintained template")
    for style in doc.styles:
        require(not re.search(r"@import\b", style, re.I), "CSS imports are unsupported")
        doc.resources.extend(re.findall(r"url\(\s*['\"]?([^'\")\s]+)", style, re.I))
    for resource in doc.resources:
        if resource.startswith("#"):
            continue
        require(not re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", resource, re.I), "Remote/protocol resource is unsupported")
        package_file(root, resource)
    return "Embedded data, trusted behavior, and local HTML resources matched"


def png(root, item, path_key, size_key, scale_key):
    path = package_file(root, item[path_key])
    require(path.suffix.lower() == ".png", "PNG resource required")
    design = numbers(item["design_size_px"], 2, True)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            require(image.format == "PNG" and getattr(image, "n_frames", 1) == 1, "Static PNG required")
            require(image.getexif().get(274, 1) == 1, "Unexpected image orientation")
            image.load()
            size, rgba = list(image.size), image.convert("RGBA")
            alpha = rgba.getchannel("A").getextrema()
            pixel_hash = hash_bytes(rgba.tobytes())
    scale = [size[i] / design[i] for i in (0, 1)]
    require(item[size_key] == size, "Actual image dimensions differ from specification")
    require(all(abs(scale[i] - item[scale_key][i]) < 1e-8 for i in (0, 1)) and abs(scale[0] - scale[1]) < 1e-8,
            "Image scale or aspect ratio differs")
    require([item["alpha_min"], item["alpha_max"]] == list(alpha), "Alpha extrema differ")
    require(item["rgba_sha256"] == pixel_hash and item["sha256"] == hash_bytes(path.read_bytes())
            and item["bytes"] == path.stat().st_size, "Image hashes or byte counts differ")
    return design, size, pixel_hash


def check_design(root, state):
    model, page_ids, asset_ids, groups, referenced = state["model"], set(), set(), {}, set()
    for page in model["pages"]:
        unique(page["id"], page_ids)
        design, _, _ = png(root, page, "preview", "actual_preview_px", "preview_scale_xy")
        require(relative(page["preview"]).parts[0] == "preview", "Page must reference preview folder")
        referenced.add(page["preview"])
        require(isinstance(page["layers"], list) and page["layers"], "Explicit layers required")
        layers = set()
        for layer in page["layers"]:
            unique(layer["id"], layers)
            x, y, w, h = numbers(layer["rect_px"], 4)
            require(w > 0 and h > 0 and x + w <= design[0] and y + h <= design[1], "Layer exceeds logical canvas")
    for asset in model["assets"]:
        unique(asset["id"], asset_ids)
        identifier, code = asset["component_id"], asset["state"]
        require(isinstance(identifier, str) and ID.fullmatch(identifier) and isinstance(code, str) and code.strip(), "Invalid component/state")
        design, size, pixel_hash = png(root, asset, "file", "actual_size_px", "export_scale_xy")
        require(relative(asset["file"]).parts[0] == "assets", "Asset must reference assets folder")
        referenced.add(asset["file"])
        group = groups.setdefault(identifier, {})
        require(code.casefold() not in group, "Duplicate component state")
        require(not group or next(iter(group.values()))[:2] == (design, size), "State canvases differ")
        group[code.casefold()] = (design, size, pixel_hash)
    for page in model["pages"]:
        for layer in page["layers"]:
            if layer["type"].lower() in {"button", "control"}:
                states = groups.get(layer["id"], {})
                require({"s0", "s1"} <= states.keys(), "Button is missing s0/s1")
                require(all(states[s][0] == layer["rect_px"][2:] for s in ("s0", "s1")), "Button canvas differs from layer")
                require(states["s0"][2] != states["s1"][2], "Button states have identical RGBA pixels")
    actual = {r for r in state["files"] if relative(r).parts[0] in {"preview", "assets"}}
    require(referenced == actual, "Unreferenced or omitted image resources")
    return f"{len(model['pages'])} pages, {len(model['assets'])} assets, {len(groups)} state groups verified"


def check_fonts(root, state):
    fonts, listed = state["model"]["fonts"], set()
    for font in fonts:
        path = package_file(root, font["file"])
        require(relative(font["file"]).parts[0] == "fonts" and path.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}, "Invalid font resource")
        require(font["usage_allowed"] is True and font["file"] not in listed, "Unconfirmed or duplicate font")
        require(font["sha256"] == hash_bytes(path.read_bytes()) and font["bytes"] == path.stat().st_size, "Font hash/bytes differ")
        listed.add(font["file"])
    if not fonts:
        require(package_file(root, "fonts/README.txt").read_text(encoding="utf-8").strip(), "Missing font explanation")
        listed.add("fonts/README.txt")
    require(listed == {f for f in state["files"] if relative(f).parts[0] == "fonts"}, "Font inventory differs")
    return "Font permission records/files or explicit missing-font explanation verified"


def check_interactions(root, state):
    from interaction_contract import validate_simulation
    return validate_simulation(state["model"])


def check_zip(root, state):
    archive = root.with_name(root.name + ".zip")
    no_links(archive)
    require(archive.is_file(), "Missing adjacent ZIP")
    seen = set()
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            path = relative(item.filename.rstrip("/"))
            require(path.parts[0] == root.name and len(path.parts) > 1, "ZIP root/path differs")
            require((item.external_attr >> 16) & 0o170000 != 0o120000, "ZIP symbolic link")
            if item.is_dir():
                continue
            rel = Path(*path.parts[1:]).as_posix()
            require(rel.casefold() not in seen and rel in state["files"], "ZIP duplicate or extra file")
            seen.add(rel.casefold())
            payload = state["files"][rel].read_bytes()
            require(item.file_size == len(payload) and zipped.read(item) == payload, f"ZIP content mismatch: {rel}")
    require(seen == {f.casefold() for f in state["files"]}, "ZIP omits package files")
    return f"ZIP contains exactly {len(seen)} matching files"


def acceptance(package, scope, node):
    checks, state = [], {}
    root = package.absolute()
    try:
        no_links(root)
        root = root.resolve(strict=True)
        require(root.is_dir(), "Package must be a directory")
        for name, check in (("manifest_and_files", check_manifest), ("html_data_and_resources", check_html),
                            ("images_layers_and_states", check_design), ("interaction_contract", check_interactions),
                            ("fonts", check_fonts), ("zip", check_zip)):
            try:
                detail = check(root, state)
                checks.append({"group": "files", "name": name, "status": "pass", "detail": detail})
            except (ValueError, OSError, KeyError, TypeError, IndexError, zipfile.BadZipFile, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                checks.append({"group": "files", "name": name, "status": "fail", "detail": str(error)})
                if not state:
                    break
    except (ValueError, OSError) as error:
        checks.append({"group": "files", "name": "package_access", "status": "fail", "detail": str(error)})
    file_status = "fail" if any(c["status"] == "fail" for c in checks) else "pass"
    logic_status, logic_detail = "blocked", "Node executable was not supplied"
    if file_status == "pass" and node:
        helper = Path(__file__).with_name("check_viewer_logic.cjs")
        if not helper.is_file():
            logic_detail = "Pure-logic helper is not available"
        else:
            try:
                response = subprocess.run([str(node), str(helper), str(root / "index.html")], capture_output=True,
                                          text=True, encoding="utf-8", timeout=30)
                result = json_value(response.stdout)
                require(result.get("backend") == "pure-js-simulation" and result.get("status") in {"pass", "fail"}, "Invalid logic report")
                logic_status = "pass" if result["status"] == "pass" and response.returncode == 0 else "fail"
                logic_detail = result
            except (OSError, subprocess.TimeoutExpired) as error:
                logic_detail = str(error)
            except (ValueError, TypeError) as error:
                logic_status, logic_detail = "fail", str(error)
    elif file_status == "fail":
        logic_detail = "File checks failed; untrusted package code was not executed"
    checks.append({"group": "logic", "name": "viewer_pure_logic", "status": logic_status, "detail": logic_detail})
    overall = "fail" if file_status == "fail" or logic_status == "fail" else (
        "blocked" if scope == "complete" or logic_status == "blocked" else "pass")
    return {"schema_version": "1.0", "scope": scope, "package": str(root), "overall": overall,
            "file_acceptance": file_status, "logic_acceptance": logic_status, "logic_environment": "pure-js-simulation",
            "prototype_delivery": "provided" if state.get("model", {}).get("simulation") else "missing_annotation_only",
            "browser_acceptance": "blocked", "visual_acceptance": "not_checked", "browser_verified": False,
            "limitation": "No browser, network, server or OS UI was accessed. Pure logic is not browser or visual acceptance.",
            "checks": checks}, {"pass": 0, "fail": 1, "blocked": 3}[overall]


def report_path(package, explicit):
    no_links(package.absolute())
    root = package.absolute().resolve()
    if explicit:
        target = explicit.absolute()
        no_links(target)
        require(not target.exists(), "Explicit report already exists")
    else:
        target = root.with_name(root.name + ".acceptance.json")
        index = 2
        while target.exists():
            target = root.with_name(root.name + f".acceptance-{index}.json")
            index += 1
        no_links(target)
    require(target.parent.is_dir(), "Report parent must already exist")
    relative(target.name)
    target = target.parent.resolve(strict=True) / target.name
    require(target != root and root not in target.parents, "Report must be outside the package")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--node", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--scope", choices=("complete", "files-and-logic"), default="complete")
    args = parser.parse_args()
    try:
        require(sys.version_info >= (3, 12), "Python 3.12+ is required")
        target = report_path(args.package, args.report)
        report, code = acceptance(args.package, args.scope, args.node)
        report["report_file"] = str(target)
        with target.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (ValueError, OSError) as error:
        print(json.dumps({"overall": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

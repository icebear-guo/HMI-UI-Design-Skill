#!/usr/bin/env python3
"""Build an offline annotated UI package from existing PNGs and an explicit manifest."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from PIL import Image
sys.dont_write_bytecode = True
from interaction_contract import validate_simulation
from asset_coverage import validate_asset_coverage, ROLES


VERSION = "1.2"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def no_links(path):
    for node in (path, *path.parents):
        require(not node.is_symlink() and not node.is_junction(), f"Linked paths are unsupported: {node}")


def safe_relative(value):
    require(isinstance(value, str) and value, "Input path must be a nonempty relative string")
    parts = value.replace("\\", "/").split("/")
    for part in parts:
        require(part not in ("", ".", "..") and not BAD.search(part)
                and not part.endswith((".", " ")) and not DEVICE.match(part), f"Unsafe input path: {value}")
    return Path(*parts)


def input_file(root, value):
    path = root / safe_relative(value)
    no_links(path.absolute())
    path = path.resolve(strict=True)
    require(root in path.parents and path.is_file(), "Input must be a file inside the manifest directory")
    return path


def identifier(value, label):
    require(isinstance(value, str) and ID.fullmatch(value) and not DEVICE.match(value),
            f"{label} must use lowercase ASCII letters, digits, hyphens or underscores")
    return value


def text(value, label):
    require(isinstance(value, str) and value.strip() and len(value) <= 500, f"{label} must be nonempty text")
    return value


def numbers(value, length, label, positive=False):
    require(isinstance(value, list) and len(value) == length, f"{label} has an invalid length")
    require(all(type(v) in (int, float) and math.isfinite(v) and (v > 0 if positive else v >= 0)
                for v in value), f"{label} must contain finite {'positive' if positive else 'nonnegative'} numbers")
    return value


def keys(value, required, optional, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(not (required - value.keys()), f"{label}: missing {sorted(required - value.keys())}")
    require(not (value.keys() - required - optional), f"{label}: unsupported fields {sorted(value.keys() - required - optional)}")


def unique(value, seen, label):
    identifier(value, label)
    require(value.casefold() not in seen, f"Duplicate {label}: {value}")
    seen.add(value.casefold())


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_info(path, design):
    require(path.suffix.lower() == ".png", "Pages and assets must be PNG files")
    with Image.open(path) as image:
        require(image.format == "PNG" and getattr(image, "n_frames", 1) == 1, "A static PNG is required")
        require(image.getexif().get(274, 1) == 1, "Normalize image orientation before packaging")
        image.load()
        size = list(image.size)
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A").getextrema()
        pixel_hash = hashlib.sha256(rgba.tobytes()).hexdigest()
    scale = [size[i] / design[i] for i in (0, 1)]
    require(abs(scale[0] - scale[1]) < 1e-8, "Image and design aspect ratios differ")
    return {"actual_size_px": size, "export_scale_xy": scale, "alpha_min": alpha[0],
            "alpha_max": alpha[1], "rgba_sha256": pixel_hash, "sha256": hash_file(path), "bytes": path.stat().st_size}


def duplicate_keys(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, f"Duplicate JSON key: {k}")
        result[k] = v
    return result


def prepare(manifest_path):
    no_links(manifest_path.absolute())
    manifest_path = manifest_path.resolve(strict=True)
    raw = manifest_path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=duplicate_keys)
    keys(data, {"schema_version", "pages", "assets"}, {"fonts", "simulation", "element_inventory"}, "manifest")
    require(data["schema_version"] in {"1.0", "1.1", VERSION}, "schema_version must be '1.0', '1.1' or '1.2'")
    require(isinstance(data["pages"], list) and data["pages"], "Complete delivery requires pages")
    require(isinstance(data["assets"], list) and data["assets"], "Complete delivery requires independent assets")
    require(isinstance(data.get("fonts", []), list), "fonts must be an array")
    root, copies, pages, assets, fonts = manifest_path.parent, [], [], [], []
    page_ids, asset_ids, component_states, component_sizes = set(), set(), set(), {}
    for p in data["pages"]:
        keys(p, {"id", "name", "design_size_px", "preview", "layers"}, set(), "page")
        unique(p["id"], page_ids, "page id")
        name = text(p["name"], "page name")
        design = numbers(p["design_size_px"], 2, "page design_size_px", True)
        require(isinstance(p["layers"], list) and p["layers"], "Each page requires explicit layers")
        source = input_file(root, p["preview"])
        info = png_info(source, design)
        relative = f"preview/{p['id']}.png"
        copies.append((source, relative))
        layer_ids, layers = set(), []
        for layer in p["layers"]:
            keys(layer, {"id", "name", "type", "rect_px"}, {"font", "fill", "text", "interaction"}, "layer")
            unique(layer["id"], layer_ids, "layer id")
            text(layer["name"], "layer name")
            text(layer["type"], "layer type")
            x, y, w, h = numbers(layer["rect_px"], 4, "layer rect_px")
            require(w > 0 and h > 0 and x + w <= design[0] and y + h <= design[1], "Layer exceeds design canvas")
            if "fill" in layer:
                require(isinstance(layer["fill"], str) and re.fullmatch(r"#[0-9a-fA-F]{6}", layer["fill"]), "fill must be #RRGGBB")
            if "text" in layer:
                require(isinstance(layer["text"], str), "layer text must be a string")
            if "font" in layer:
                font = layer["font"]
                keys(font, {"family", "size_px"}, {"weight"}, "font")
                text(font["family"], "font family")
                numbers([font["size_px"]], 1, "font size_px", True)
                if "weight" in font:
                    require((type(font["weight"]) is int and 100 <= font["weight"] <= 900)
                            or font["weight"] in ("normal", "bold"), "Invalid font weight")
            layers.append(layer.copy())
        pages.append({"id": p["id"], "name": name, "design_size_px": design, "preview": relative,
                      "actual_preview_px": info.pop("actual_size_px"), "preview_scale_xy": info.pop("export_scale_xy"),
                      "layers": layers, **info})
    for a in data["assets"]:
        keys(a, {"id", "file", "component_id", "state", "design_size_px"}, {"asset_role"}, "asset")
        unique(a["id"], asset_ids, "asset id")
        identifier(a["component_id"], "component_id")
        state = text(a["state"], "asset state")
        role = a.get("asset_role", "control_plate")
        if "asset_role" in a:
            require(isinstance(role, str) and role in ROLES, "Unknown asset_role")
        pair = (a["component_id"].casefold(), role, state.casefold())
        require(pair not in component_states, "Duplicate state for component")
        component_states.add(pair)
        design = numbers(a["design_size_px"], 2, "asset design_size_px", True)
        source = input_file(root, a["file"])
        info = png_info(source, design)
        signature = (design, info["actual_size_px"])
        group_key = (a["component_id"], role)
        if group_key in component_sizes:
            require(component_sizes[group_key] == signature, "Component role state canvases differ")
        component_sizes[group_key] = signature
        relative = f"assets/{a['id']}.png"
        copies.append((source, relative))
        assets.append({"id": a["id"], "file": relative, "component_id": a["component_id"],
                       "state": state, "design_size_px": design, **({"asset_role":role} if "asset_role" in a else {}), **info})
    for index, f in enumerate(data.get("fonts", []), 1):
        keys(f, {"file", "usage_allowed"}, {"family"}, "font resource")
        require(f["usage_allowed"] is True, "Font distribution permission must be explicit")
        source = input_file(root, f["file"])
        require(source.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}, "Unsupported font format")
        family = text(f["family"], "font family") if "family" in f else ""
        relative = f"fonts/font-{index:03}{source.suffix.lower()}"
        copies.append((source, relative))
        fonts.append({"file": relative, "family": family, "usage_allowed": True,
                      "sha256": hash_file(source), "bytes": source.stat().st_size})
    for page in pages:
        for layer in page["layers"]:
            if data["schema_version"] != "1.2" and layer["type"].lower() in {"button", "control"}:
                states = {a["state"].casefold(): a for a in assets if a["component_id"] == layer["id"] and a.get("asset_role", "control_plate")=="control_plate"}
                require({"s0", "s1"} <= states.keys(), f"Button {layer['id']} requires s0 and s1 assets")
                require(all(states[s]["design_size_px"] == layer["rect_px"][2:] for s in ("s0", "s1")),
                        f"Button {layer['id']} asset canvas must match its logical rectangle")
                require(states["s0"]["rgba_sha256"] != states["s1"]["rgba_sha256"],
                        f"Button {layer['id']} s0 and s1 must contain different RGBA pixels")
    result = {"schema_version": data["schema_version"], "input_manifest_sha256": hashlib.sha256(raw).hexdigest(),
              "pages": pages, "assets": assets, "fonts": fonts}
    if "simulation" in data:
        result["simulation"] = data["simulation"]
    if "element_inventory" in data:
        inventory = data["element_inventory"]
        if isinstance(inventory, str):
            inventory = json.loads(input_file(root, inventory).read_text(encoding="utf-8-sig"), object_pairs_hook=duplicate_keys)
        result["element_inventory"] = inventory
    validate_simulation(result)
    validate_asset_coverage(result)
    return result, copies


def build(manifest_path, out):
    require(sys.version_info >= (3, 12), "Python 3.12+ is required")
    out = out.absolute()
    no_links(out)
    require(out.parent.is_dir(), "Output parent directory must already exist")
    out = out.parent.resolve(strict=True) / out.name
    archive = out.with_name(out.name + ".zip")
    require(not out.exists() and not archive.exists(), "Output directory or ZIP already exists")
    model, copies = prepare(manifest_path)
    template_path = Path(__file__).resolve().parents[1] / "assets/delivery-viewer.template.html"
    template = template_path.read_text(encoding="utf-8")
    require(template.count("__DESIGN_DATA__") == 1, "Viewer template marker is invalid")
    encoded = json.dumps(model, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    stage = Path(tempfile.mkdtemp(prefix=".delivery-build-", dir=out.parent))
    written = False
    archive_written = False
    try:
        for folder in ("preview", "assets", "fonts", "specs"):
            (stage / folder).mkdir()
        for source, relative in copies:
            shutil.copyfile(source, stage / relative)
            require(hash_file(source) == hash_file(stage / relative), "Copied file hash differs")
        if not model["fonts"]:
            (stage / "fonts/README.txt").write_text("未提供可随交付分发的字体文件。请确认目标设备字体与回退方案。\n", encoding="utf-8")
        (stage / "index.html").write_text(template.replace("__DESIGN_DATA__", encoded), encoding="utf-8")
        payload = json.dumps(model, ensure_ascii=False, indent=2) + "\n"
        (stage / "specs/design.json").write_text(payload, encoding="utf-8")
        manifest = {"schema_version": model["schema_version"], "pages": len(model["pages"]), "assets": len(model["assets"]),
                    "fonts": len(model["fonts"]), "files": []}
        for file in sorted(stage.rglob("*")):
            if file.is_file():
                manifest["files"].append({"file": file.relative_to(stage).as_posix(), "sha256": hash_file(file), "bytes": file.stat().st_size})
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out.mkdir()  # Atomic reservation, never reuse an existing output directory.
        written = True
        for child in stage.iterdir():
            child.rename(out / child.name)
        with archive.open("xb") as stream:
            archive_written = True
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
                for file in sorted(out.rglob("*")):
                    if file.is_file():
                        zipped.write(file, (Path(out.name) / file.relative_to(out)).as_posix())
    except BaseException:
        if archive_written:
            archive.unlink(missing_ok=True)
        if written and out.parent == stage.parent:
            shutil.rmtree(out)
        raise
    finally:
        require(stage.parent == out.parent and stage.name.startswith(".delivery-build-"), "Invalid cleanup target")
        shutil.rmtree(stage)
    return {"status": "written", "directory": str(out), "zip": str(archive), "pages": len(model["pages"]),
            "assets": len(model["assets"]), "fonts": len(model["fonts"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.manifest, args.out), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

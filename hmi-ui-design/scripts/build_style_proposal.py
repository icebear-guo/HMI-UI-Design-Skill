#!/usr/bin/env python3
"""Build offline direction samples from a shared scene and versioned theme/layout profiles."""
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

sys.dont_write_bytecode = True
ASSETS = Path(__file__).resolve().parents[1] / "assets"
ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+\Z")
COLORS = {"background", "surface", "surface_alt", "text_primary", "text_secondary", "divider", "accent", "text_on_accent", "button_s0", "button_s1", "text_on_button", "indicator_on", "indicator_off", "warning", "fault"}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def fields(obj, required, optional=()):
    need(isinstance(obj, dict) and set(required) <= obj.keys() <= set(required) | set(optional), "Invalid object fields")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def label(value):
    need(isinstance(value, str) and value.strip() and len(value) <= 300, "Expected nonempty text up to 300 characters")


def unique_ids(items):
    need(isinstance(items, list) and items, "Expected a nonempty array")
    seen = set()
    for item in items:
        need(isinstance(item, dict) and isinstance(item.get("id"), str) and ID.fullmatch(item["id"]), "Invalid ID")
        need(item["id"] not in seen, "Duplicate ID")
        seen.add(item["id"])
    return seen


def no_links(path):
    for node in (path, *path.parents):
        need(not node.is_symlink() and not node.is_junction(), "Linked paths are unsupported")


def pairs(pairs):
    result = {}
    for k, v in pairs:
        need(k not in result, "Duplicate JSON key")
        result[k] = v
    return result


def load(path):
    no_links(path.absolute())
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs), hashlib.sha256(raw).hexdigest()


def profile_file(assets, value, folder):
    need(isinstance(value, str) and re.fullmatch(folder + r"/[a-z0-9-]+\.json", value), "Unsafe catalog path")
    path = assets / value
    no_links(path.absolute())
    need(path.resolve().is_relative_to(assets.resolve()), "Profile must stay inside the asset library")
    return path


def validate_profile(profile, kind):
    common = {"schema_version", "id", "version", "status", "name", "description"}
    fields(profile, common | ({"tone", "colors"} if kind == "themes" else {"navigation_position", "composition", "min_canvas_px", "regions"}))
    need(profile["schema_version"] == "1.0" and ID.fullmatch(profile["id"]) and VERSION.fullmatch(profile["version"]), "Invalid profile identity/version")
    need(profile["status"] in {"proposed", "validated", "approved", "deprecated"}, "Invalid profile status")
    label(profile["name"]); label(profile["description"])
    if kind == "themes":
        need(profile["tone"] in {"light", "dark"}, "Invalid theme tone")
        fields(profile["colors"], COLORS)
        need(all(isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) for v in profile["colors"].values()), "Colors must be #RRGGBB")
    else:
        need(profile["navigation_position"] in {"bottom", "left", "top"}, "Unsupported navigation position")
        need(profile["composition"] in {"balanced-columns", "process-focus", "metrics-first"}, "Unsupported composition")
        size = profile["min_canvas_px"]
        need(isinstance(size, list) and len(size) == 2 and all(type(v) is int and v > 0 for v in size), "Invalid minimum canvas")
        fields(profile["regions"], {"status", "alarm", "navigation", "content"})
        rects = list(profile["regions"].values())
        for rect in rects:
            need(isinstance(rect, list) and len(rect) == 4 and all(finite(v) and v >= 0 for v in rect), "Invalid normalized rectangle")
            x,y,w,h = rect
            need(w > 0 and h > 0 and x+w <= 1+1e-8 and y+h <= 1+1e-8, "Profile rectangle exceeds canvas")
        for i,a in enumerate(rects):
            for b in rects[i+1:]:
                need(min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]) <= 1e-8 or min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]) <= 1e-8, "Profile regions overlap")


def resolve_catalog(assets):
    catalog, _ = load(assets / "style-catalog.json")
    fields(catalog, {"schema_version", "themes", "layouts"})
    need(catalog["schema_version"] == "1.0", "Unsupported catalog schema")
    result = {}
    for kind in ("themes", "layouts"):
        need(isinstance(catalog[kind], list) and catalog[kind], "Empty profile catalog")
        indexed = {}
        for row in catalog[kind]:
            fields(row, {"id", "version", "file"})
            profile, digest = load(profile_file(assets, row["file"], kind))
            validate_profile(profile, kind)
            need((row["id"],row["version"]) == (profile["id"],profile["version"]), "Catalog identity does not match profile")
            key = (row["id"],row["version"])
            need(key not in indexed, "Duplicate profile registration")
            indexed[key] = {"profile": profile, "sha256": digest}
        result[kind] = indexed
    return result


def prepare(path, assets=ASSETS):
    data, digest = load(path)
    fields(data, {"schema_version", "title", "canvas_px", "physical_size", "representative_page_id", "navigation_items", "snapshot", "variants", "assumptions"})
    need(data["schema_version"] == "1.0", "Unsupported proposal schema")
    label(data["title"])
    size = data["canvas_px"]
    need(isinstance(size, list) and len(size) == 2 and all(type(v) is int and 0 < v <= 8192 for v in size), "Explicit canvas_px required")
    fields(data["physical_size"], {"diagonal_in", "visible_width_mm", "visible_height_mm"})
    need(all(v is None or finite(v) and v > 0 for v in data["physical_size"].values()), "Invalid physical size")
    nav_ids = unique_ids(data["navigation_items"])
    need(data["representative_page_id"] in nav_ids, "Representative page is not in navigation")
    need(len(nav_ids) <= 12, "More than 12 navigation items needs a dedicated profile")
    for item in data["navigation_items"]:
        fields(item, {"id", "label"}); label(item["label"])
    scene = data["snapshot"]
    fields(scene, {"page_title", "object_label", "mode", "connection", "alarm", "metrics", "units", "actions"})
    for key in ("page_title", "object_label", "mode", "connection", "alarm"):
        label(scene[key])
    for key, maximum in (("metrics", 6), ("units", 6), ("actions", 4)):
        unique_ids(scene[key]); need(len(scene[key]) <= maximum, f"Too many {key} for the sample renderer")
    for m in scene["metrics"]:
        fields(m, {"id", "label", "value", "min", "max", "unit"}); label(m["label"])
        need(isinstance(m["unit"], str) and len(m["unit"]) <= 20, "Invalid metric unit")
        need(all(finite(m[k]) for k in ("value", "min", "max")) and m["min"] < m["max"] and m["min"] <= m["value"] <= m["max"], "Invalid metric bounds")
    for unit in scene["units"]:
        fields(unit, {"id", "label", "on"}); label(unit["label"]); need(type(unit["on"]) is bool, "Unit state must be boolean")
    for action in scene["actions"]:
        fields(action, {"id", "label", "effect"}); label(action["label"])
        need(action["effect"] in {"start", "stop", "reset"}, "Unsupported local action")
    unique_ids(data["variants"])
    need(len(data["variants"]) <= 9, "Limit each comparison round to 9 samples")
    need(isinstance(data["assumptions"], list), "assumptions must be an array")
    for assumption in data["assumptions"]:
        label(assumption)
    catalog = resolve_catalog(assets)
    themes, layouts = {}, {}
    for variant in data["variants"]:
        fields(variant, {"id", "title", "theme_id", "theme_version", "layout_id", "layout_version"}); label(variant["title"])
        for kind, target in (("themes", themes), ("layouts", layouts)):
            prefix = "theme" if kind == "themes" else "layout"
            key = (variant[prefix+"_id"], variant[prefix+"_version"])
            need(key in catalog[kind], f"Unknown {prefix} ID/version")
            target['@'.join(key)] = catalog[kind][key]
            profile = target['@'.join(key)]["profile"]
            need(profile["status"] != "deprecated", "Cannot use deprecated profiles for a new proposal")
            if kind == "layouts":
                need(all(size[i] >= profile["min_canvas_px"][i] for i in (0,1)), "Selected layout needs a dedicated smaller-canvas adaptation")
                scale = min(size[0]/1024, size[1]/600)
                gap = 16*scale
                region = profile["regions"]["content"]
                width, usable = region[2]*size[0]-2*gap, region[3]*size[1]-3*gap-48*scale
                count = len(scene["metrics"])
                if profile["composition"] == "metrics-first":
                    card_width, card_height = (width-gap*(count-1))/count, usable*.38-gap/2
                else:
                    ratio = .4 if profile["composition"] == "balanced-columns" else .3
                    card_width, card_height = width*ratio-gap/2, (usable-gap*(count-1))/count
                need(card_width >= 180*scale-1e-8 and card_height >= 80*scale-1e-8,
                     "Metric content exceeds selected layout capacity; choose a different composition or adapt the layout")
    return {**data, "input_sha256": digest, "themes": themes, "layouts": layouts, "selection_status": "pending"}


def build(path, out, assets=ASSETS):
    need(sys.version_info >= (3,12), "Python 3.12+ required")
    no_links(out.absolute())
    need(out.parent.is_dir(), "Output parent must exist")
    out = out.parent.resolve() / out.name
    archive = out.with_name(out.name+".zip")
    need(not out.exists() and not archive.exists(), "Output directory or ZIP exists")
    model = prepare(path, assets)
    template = (assets / "style-proposal-viewer.template.html").read_text(encoding="utf-8")
    need(template.count("__PROPOSAL_DATA__") == 1, "Invalid proposal template marker")
    encoded = json.dumps(model, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    stage = Path(tempfile.mkdtemp(prefix=".proposal-", dir=out.parent))
    owned = False
    archive_owned = False
    try:
        (stage / "index.html").write_text(template.replace("__PROPOSAL_DATA__", encoded), encoding="utf-8")
        (stage / "proposal.json").write_text(json.dumps(model, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        (stage / "selection.pending.json").write_text(json.dumps({"status":"pending", "theme":None, "layout":None, "canvas_px": model["canvas_px"], "representative_page_id":model["representative_page_id"]}, indent=2)+"\n", encoding="utf-8")
        manifest = {"schema_version":"1.0", "kind":"style-proposal", "files":[]}
        for file in sorted(stage.iterdir()):
            raw = file.read_bytes(); manifest["files"].append({"file":file.name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        out.mkdir(); owned = True
        for file in stage.iterdir():
            file.rename(out / file.name)
        with archive.open("xb") as stream:
            archive_owned = True
            with zipfile.ZipFile(stream,"w",zipfile.ZIP_DEFLATED) as zipped:
                for file in sorted(out.iterdir()):
                    zipped.write(file, out.name+"/"+file.name)
    except BaseException:
        if owned:
            if archive_owned and archive.exists():
                archive.unlink()
            shutil.rmtree(out)
        raise
    finally:
        shutil.rmtree(stage)
    return {"status":"written", "directory":str(out), "zip":str(archive), "variants":len(model["variants"]), "selection":"pending", "browser_verified":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.manifest,args.out),ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({"status":"fail","error":str(error)},ensure_ascii=False));return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

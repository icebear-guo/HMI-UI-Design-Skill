#!/usr/bin/env python3
"""Crop explicit PNG rectangles without resizing, masking, or inferred geometry."""

import argparse
import hashlib
import io
import json
import re
import sys
import warnings
from pathlib import Path

VERSION = "1.0"
REPORT_NAME = "slice-report.json"
if sys.version_info < (3, 12):
    print(json.dumps({"schema_version": VERSION, "tool": "slice_assets.py", "status": "failed",
                      "error_type": "UnsupportedPythonVersion",
                      "message": "Python 3.12+ is required for Windows junction path validation"}), file=sys.stderr)
    sys.exit(2)

from PIL import Image


BAD_NAME = re.compile(r'[<>:"|?*\x00-\x1f]')
DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])\s*(?:\.|$)", re.I)


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise Invalid(f"Invalid JSON constant: {value}")


def exact_keys(obj, required, optional, label):
    require(isinstance(obj, dict), f"{label} must be an object")
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    require(not missing, f"{label}: missing keys {sorted(missing)}")
    require(not unknown, f"{label}: unknown keys {sorted(unknown)}")


def integer_list(value, length, label, minimum=0):
    require(isinstance(value, list) and len(value) == length,
            f"{label} must be an array of {length} integers")
    require(all(type(item) is int and item >= minimum for item in value),
            f"{label} must contain integers >= {minimum}; booleans are invalid")
    return value


def relative_path(value, label):
    require(isinstance(value, str) and value, f"{label} must be a nonempty path")
    # Both separators are understood, including when run on a non-Windows host.
    normalized = value.replace("\\", "/")
    require(not normalized.startswith("/"), f"{label}: absolute paths are forbidden")
    parts = normalized.split("/")
    for part in parts:
        require(part not in ("", ".", ".."), f"{label}: empty, . and .. components are forbidden")
        require(not BAD_NAME.search(part), f"{label}: illegal Windows filename: {part!r}")
        require(not part.endswith((".", " ")), f"{label}: trailing dots/spaces are forbidden")
        require(not DEVICE.match(part), f"{label}: reserved Windows device name: {part!r}")
    return Path(*parts), "/".join(parts)


def is_link(path):
    return path.is_symlink() or path.is_junction()


def inside(path, root):
    return path == root or root in path.parents


def checked_target(root, relative):
    candidate = root / relative
    current = root
    require(not is_link(current), f"Output directory may not be a symlink/junction: {current}")
    for component in relative.parts:
        current = current / component
        require(not is_link(current), f"Symlink/junction in output path: {current}")
    require(inside(candidate.resolve(), root), f"Output escapes destination: {relative}")
    require(not candidate.exists(), f"Refusing to overwrite existing output: {candidate}")
    for parent in candidate.parents:
        if parent == root.parent:
            break
        require(not parent.exists() or parent.is_dir(), f"Output parent is not a directory: {parent}")
    return candidate


def alpha_stats(crop):
    alpha = crop.convert("RGBA").getchannel("A")
    histogram = alpha.histogram()
    return {
        "has_alpha_channel": "A" in crop.getbands(),
        "has_transparency_metadata": "transparency" in crop.info,
        "min": alpha.getextrema()[0],
        "max": alpha.getextrema()[1],
        "transparent_pixels": histogram[0],
        "semi_transparent_pixels": sum(histogram[1:255]),
        "opaque_pixels": histogram[255],
    }


def prepare(manifest_path, out_path, dry_run):
    manifest_path = manifest_path.resolve(strict=True)
    manifest_bytes = manifest_path.read_bytes()
    data = json.loads(manifest_bytes.decode("utf-8-sig"),
                      object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    exact_keys(data, {"schema_version", "source", "canvas_px", "assets"}, set(), "manifest")
    require(data["schema_version"] == VERSION, "schema_version must be '1.0'")
    canvas = integer_list(data["canvas_px"], 2, "canvas_px", minimum=1)
    require(isinstance(data["assets"], list) and data["assets"], "assets must be a nonempty array")
    source_relative, source_declared = relative_path(data["source"], "source")
    source_path = manifest_path.parent / source_relative
    cursor = manifest_path.parent
    for part in source_relative.parts:
        cursor = cursor / part
        require(not is_link(cursor), f"Source may not cross a symlink/junction: {cursor}")
    source_path = source_path.resolve(strict=True)
    require(inside(source_path, manifest_path.parent), "source escapes the manifest directory")
    require(source_path != manifest_path, "source and manifest may not be the same file")
    out_absolute = out_path.absolute()
    # Inspect the spelling supplied by the caller before resolve() erases junctions.
    for ancestor in (out_absolute, *out_absolute.parents):
        require(not is_link(ancestor), f"Symlink/junction in output path or ancestor: {ancestor}")
    out_root = out_absolute.resolve()
    require(not out_root.exists() or out_root.is_dir(), "Output root is not a directory")
    require(not inside(source_path, out_root) and not inside(manifest_path, out_root),
            "Output directory must not contain the source or manifest; use a separate export directory")
    report_path = checked_target(out_root, Path(REPORT_NAME))
    source_bytes = source_path.read_bytes()
    require(len(source_bytes) >= 33 and source_bytes[:8] == b"\x89PNG\r\n\x1a\n"
            and source_bytes[8:16] == b"\x00\x00\x00\rIHDR", "source must have a valid PNG signature and IHDR")
    # Pillow can decode 16-bit RGB/RGBA to 8-bit modes, so mode alone is insufficient.
    bit_depth = source_bytes[24]
    require(bit_depth in {1, 2, 4, 8}, f"Unsupported PNG IHDR bit depth {bit_depth}; 16-bit sources are forbidden")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        source = Image.open(io.BytesIO(source_bytes))
        require(source.format == "PNG", "source must be a PNG image")
        require(getattr(source, "n_frames", 1) == 1, "Animated PNG sources are unsupported")
        require(source.mode in {"1", "L", "LA", "P", "RGB", "RGBA"},
                f"Unsupported source mode {source.mode!r}; supply an 8-bit PNG")
        require(source.getexif().get(274, 1) == 1,
                "EXIF-oriented PNG is unsupported; normalize orientation before defining rectangles")
        source.load()
    require(list(source.size) == canvas,
            f"canvas_px mismatch: declared {canvas}, actual {list(source.size)}")
    paths_seen = {REPORT_NAME.casefold()}
    ids_seen = set()
    groups = {}
    prepared = []
    reports = []
    for index, item in enumerate(data["assets"]):
        label = f"assets[{index}]"
        exact_keys(item, {"id", "file", "rect_px", "state", "expected_size_px", "alpha_required"},
                   {"padding_px", "same_canvas_group"}, label)
        asset_id = item["id"]
        require(isinstance(asset_id, str) and asset_id.strip(), f"{label}.id must be nonempty")
        require(asset_id.casefold() not in ids_seen, f"Duplicate id (case-insensitive): {asset_id}")
        ids_seen.add(asset_id.casefold())
        label = f"asset {asset_id!r}"
        require(isinstance(item["state"], str) and item["state"].strip(), f"{label}: state must be nonempty")
        require(type(item["alpha_required"]) is bool, f"{label}: alpha_required must be a boolean")
        relative, filename = relative_path(item["file"], f"{label}.file")
        require(relative.suffix.lower() == ".png", f"{label}: output filename must end in .png")
        path_key = filename.casefold()
        require(path_key not in paths_seen, f"Duplicate/reserved output path (case-insensitive): {filename}")
        # Catch a.png versus a.png/b.png before any directories or files are created.
        require(not any(path_key.startswith(key + "/") or key.startswith(path_key + "/")
                        for key in paths_seen), f"Output file/directory conflict: {filename}")
        paths_seen.add(path_key)
        destination = checked_target(out_root, relative)
        x, y, width, height = integer_list(item["rect_px"], 4, f"{label}.rect_px")
        require(width > 0 and height > 0, f"{label}: crop width and height must be positive")
        require(x + width <= canvas[0] and y + height <= canvas[1], f"{label}: rectangle exceeds source canvas")
        expected = integer_list(item["expected_size_px"], 2, f"{label}.expected_size_px", minimum=1)
        require(expected == [width, height], f"{label}: expected_size_px differs from crop; resizing is forbidden")
        padding = integer_list(item.get("padding_px", [0, 0, 0, 0]), 4, f"{label}.padding_px")
        left, top, right, bottom = padding
        require(left + right < width and top + bottom < height, f"{label}: padding leaves no content area")
        group = item.get("same_canvas_group")
        if group is not None:
            require(isinstance(group, str) and group.strip(), f"{label}: same_canvas_group must be nonempty")
            group_key = group.casefold()
            if group_key in groups:
                require(groups[group_key]["size"] == expected, f"{label}: same_canvas_group dimensions differ")
                require(item["state"].casefold() not in groups[group_key]["states"],
                        f"{label}: duplicate state in same_canvas_group")
                groups[group_key]["states"].add(item["state"].casefold())
            else:
                groups[group_key] = {"size": expected, "states": {item["state"].casefold()}}
        crop = source.crop((x, y, x + width, y + height))
        alpha = alpha_stats(crop)
        require(not item["alpha_required"] or alpha["min"] < 255,
                f"{label}: alpha_required=true but the crop has no transparent or semi-transparent pixels")
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG", optimize=False)
        output_bytes = buffer.getvalue()
        # Validate encoded output, rather than assuming the writer preserved its alpha/palette.
        with Image.open(io.BytesIO(output_bytes)) as decoded:
            decoded.load()
            require(decoded.size == crop.size and decoded.convert("RGBA").tobytes() == crop.convert("RGBA").tobytes(),
                    f"{label}: PNG round-trip changed image pixels")
        prepared.append((destination, output_bytes))
        reports.append({
            "id": asset_id, "file": filename, "state": item["state"],
            "status": "validated" if dry_run else "written", "rect_px": [x, y, width, height],
            "expected_size_px": expected, "actual_size_px": list(crop.size), "mode": crop.mode,
            "padding_px": padding, "content_rect_px": [left, top, width - left - right, height - top - bottom],
            "same_canvas_group": group, "alpha_required": item["alpha_required"], "alpha": alpha,
            "sha256": sha256(output_bytes), "bytes": len(output_bytes), "pixel_roundtrip_verified": True,
        })
    source.close()
    report = {
        "schema_version": VERSION, "tool": "slice_assets.py", "status": "dry_run_ok" if dry_run else "written",
        "dry_run": dry_run, "manifest": {"path": str(manifest_path), "sha256": sha256(manifest_bytes)},
        "source": {"path": str(source_path), "declared_path": source_declared,
                   "sha256": sha256(source_bytes), "canvas_px": canvas, "bit_depth": bit_depth},
        "output_directory": str(out_root), "report_file": REPORT_NAME, "assets": reports,
    }
    return report, prepared, report_path


def write_batch(prepared):
    """Exclusive creation; roll back only paths created by this invocation on failure."""
    created_files = []
    created_dirs = []
    try:
        for destination, payload in prepared:
            missing = []
            parent = destination.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()  # An unexpected competing creator is an error.
                created_dirs.append(directory)
            require(not any(is_link(parent) for parent in destination.parents),
                    f"Symlink/junction appeared in output path: {destination}")
            # xb never replaces a file, even when a competing process creates it after validation.
            with destination.open("xb") as stream:
                created_files.append(destination)
                stream.write(payload)
    except BaseException:
        for path in reversed(created_files):
            try:
                path.unlink()
            except OSError:
                pass
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="UTF-8 JSON manifest")
    parser.add_argument("--out", required=True, type=Path, help="Separate export directory; never overwrites")
    parser.add_argument("--dry-run", action="store_true", help="Validate and encode in memory; create no files/directories")
    args = parser.parse_args()
    try:
        report, prepared, report_path = prepare(args.manifest, args.out, args.dry_run)
        if not args.dry_run:
            report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            write_batch(prepared + [(report_path, report_bytes)])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (Invalid, OSError, ValueError, KeyError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        print(json.dumps({"schema_version": VERSION, "tool": "slice_assets.py", "status": "failed",
                          "error_type": type(error).__name__, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

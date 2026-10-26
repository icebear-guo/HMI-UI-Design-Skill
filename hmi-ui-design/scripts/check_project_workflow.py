#!/usr/bin/env python3
"""Read-only check of customer review records and the exact reviewed artifact snapshots."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

STAGES = ("parameters", "direction", "interactive_ui")
REQUIRED = {"samples": 1, "ui": 2, "slicing": 3, "delivery": 3}
ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def fields(obj, required, optional=()):
    need(isinstance(obj, dict) and set(required) <= obj.keys() <= set(required) | set(optional), "Invalid workflow fields")


def no_links(path):
    for node in (path, *path.parents):
        need(not node.is_symlink() and not node.is_junction(), "Linked paths are unsupported")


def relative(value):
    need(isinstance(value, str) and value, "Artifact path must be relative text")
    parts = value.replace("\\", "/").split("/")
    need(all(p not in ("", ".", "..") and not BAD.search(p) and not DEVICE.match(p)
             and not p.endswith((".", " ")) for p in parts), "Unsafe artifact path")
    return Path(*parts)


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def pairs_unique(pairs):
    result = {}
    for k, v in pairs:
        need(k not in result, "Duplicate workflow key")
        result[k] = v
    return result


def stage_result(record, name, root, prior):
    stage = record["stages"][name]
    common = {"revision", "status", "artifact_dir", "entry", "files", "depends_on", "customer_confirmation"}
    fields(stage, common | ({"pages"} if name == "interactive_ui" else set()))
    need(isinstance(stage["revision"], str) and stage["revision"].strip(), "Stage revision required")
    need(stage["status"] in {"pending", "awaiting_customer", "changes_requested", "confirmed"}, "Invalid stage status")
    fields(stage["depends_on"], set(prior))
    need(isinstance(stage["files"], list), "Stage files must be an array")
    path = root / relative(stage["artifact_dir"])
    no_links(path.absolute())
    entry = relative(stage["entry"]).as_posix()
    reasons, listed, snapshot = [], set(), []
    if not path.is_dir():
        reasons.append("Review artifact directory is missing")
    else:
        actual = set()
        for file in path.rglob("*"):
            no_links(file.absolute())
            if file.is_file():
                actual.add(file.relative_to(path).as_posix())
        need(len(actual) == len({p.casefold() for p in actual}), "Artifact paths collide by letter case")
        for item in stage["files"]:
            fields(item, {"file", "sha256"}, {"origin"})
            origin = item.get("origin", "generated")
            need(origin in {"generated", "existing_asset"}, "Invalid reviewed file origin")
            rel = relative(item["file"]).as_posix()
            need(rel.casefold() not in listed and isinstance(item["sha256"], str) and SHA.fullmatch(item["sha256"]), "Invalid or duplicate reviewed file")
            listed.add(rel.casefold())
            file = path / relative(item["file"])
            if not file.is_file():
                reasons.append("Reviewed file is missing: "+rel)
                continue
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            snapshot.append({"file": rel, "sha256": digest, "origin": origin})
            if file.suffix.lower() == ".png" and origin != "existing_asset":
                reasons.append("Review must remain HTML-first; newly generated PNG is not allowed: "+rel)
            if digest != item["sha256"]:
                reasons.append("Reviewed file changed: "+rel)
        if not listed or listed != {p.casefold() for p in actual}:
            reasons.append("Review inventory is empty or does not match all artifact files")
        if entry.casefold() not in listed:
            reasons.append("Review entry is not in the snapshot")
    if name != "parameters" and not entry.lower().endswith(".html"):
        reasons.append("An actual HTML review entry is required")
    pages = None
    if name == "interactive_ui":
        need(isinstance(stage["pages"], list), "UI pages must be an array")
        pages = []
        for page in stage["pages"]:
            fields(page, {"id", "entry"})
            need(isinstance(page["id"], str) and ID.fullmatch(page["id"]), "Invalid review page ID")
            page_entry = relative(page["entry"]).as_posix()
            need(page_entry.lower().endswith(".html"), "UI page entry must be HTML")
            pages.append({"id": page["id"], "entry": page_entry})
            if page_entry.casefold() not in listed:
                reasons.append("UI page HTML not in review snapshot: "+page["id"])
        ids = [p["id"] for p in pages]
        if ids != record["page_ids"] or len(ids) != record["page_count"] or len(set(ids)) != len(ids):
            reasons.append("UI page count/order/IDs differ from confirmed scope")
    dependencies = {k: prior[k]["review_digest"] for k in prior}
    digest = canonical({"stage": name, "revision": stage["revision"], "project_revision": record["project_revision"],
                        "artifact_dir": relative(stage["artifact_dir"]).as_posix(), "entry": entry,
                        "scope_pages": record["page_ids"], "page_count": record["page_count"],
                        "files": sorted(snapshot, key=lambda item: item["file"]), "dependencies": dependencies, "pages": pages})
    for key in prior:
        if prior[key]["state"] != "confirmed":
            reasons.append("Upstream customer confirmation is not current: "+key)
        if stage["depends_on"][key] != dependencies[key]:
            reasons.append("Upstream review digest is not current: "+key)
    confirmation = stage["customer_confirmation"]
    if stage["status"] != "confirmed":
        reasons.append("Waiting for an explicit customer confirmation of this stage/version")
    if confirmation is None:
        reasons.append("Customer confirmation evidence is missing")
    else:
        fields(confirmation, {"customer_message", "message_ref", "confirmed_at", "reviewed_digest"})
        need(all(isinstance(confirmation[k], str) and confirmation[k].strip()
                 for k in ("customer_message", "message_ref", "confirmed_at", "reviewed_digest")), "Incomplete customer confirmation evidence")
        try:
            timestamp = datetime.fromisoformat(confirmation["confirmed_at"].replace("Z", "+00:00"))
            need(timestamp.tzinfo is not None, "Customer confirmation timestamp needs a timezone")
        except ValueError as error:
            raise ValueError("Invalid customer confirmation timestamp") from error
        if confirmation["reviewed_digest"] != digest:
            reasons.append("Customer confirmation refers to a different review snapshot")
    if not record["page_ids"] or record["page_count"] != len(record["page_ids"]):
        reasons.append("An explicit nonempty page scope/count is required")
    return {"stage": name, "state": "confirmed" if not reasons else "blocked", "review_digest": digest, "reasons": reasons}


def check(path, action):
    no_links(path.absolute())
    root = path.resolve(strict=True).parent
    record = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs_unique)
    fields(record, {"schema_version", "scope", "project_revision", "page_count", "page_ids", "stages"})
    need(record["schema_version"] == "1.0" and record["scope"] == "full-ui-project", "Unsupported workflow scope/schema")
    need(isinstance(record["project_revision"], str) and record["project_revision"].strip(), "Project revision required")
    need(record["page_count"] is None or type(record["page_count"]) is int and record["page_count"] > 0, "Invalid page_count")
    need(isinstance(record["page_ids"], list) and all(isinstance(v, str) and ID.fullmatch(v) for v in record["page_ids"])
         and len(set(record["page_ids"])) == len(record["page_ids"]), "Invalid or duplicate page IDs")
    fields(record["stages"], set(STAGES))
    results = {}
    for name in STAGES:
        try:
            result = stage_result(record, name, root, results.copy())
        except (ValueError, OSError) as error:
            result = {"stage": name, "state": "blocked", "review_digest": None, "reasons": [str(error)]}
        results[name] = result
    needed = STAGES[:REQUIRED[action]]
    ready = all(results[name]["state"] == "confirmed" for name in needed)
    return {"status": "ready" if ready else "blocked", "action": action, "required_stages": list(needed),
            "stages": list(results.values()), "human_evidence_verified": False,
            "limitation": "Checks recorded evidence and artifact identity only; cannot authenticate customer messages or validate browser/device behavior."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--for", dest="action", choices=tuple(REQUIRED), required=True)
    args = parser.parse_args()
    try:
        result = check(args.record, args.action)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ready" else 3
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

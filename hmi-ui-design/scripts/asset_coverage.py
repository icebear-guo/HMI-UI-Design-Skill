"""Validate the registered visible-element inventory and each element's final delivery."""
from datetime import datetime
import math
import re

ROLES = {"background", "panel", "control_plate", "icon", "indicator", "device_illustration", "decoration", "frame", "track", "needle"}
GRAPHIC_TYPES = {"icon", "indicator", "led", "decoration", "image", "bitmap", "illustration", "logo", "background", "panel"}
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def validate_asset_coverage(model):
    def need(ok, message):
        if not ok:
            raise ValueError(message)

    def fields(obj, required, optional=()):
        need(isinstance(obj, dict) and set(required) <= obj.keys() <= set(required) | set(optional), "Invalid element inventory fields")

    def nonempty(value, label):
        need(isinstance(value, str) and value.strip(), label+" is required")

    inventory = model.get("element_inventory")
    if inventory is None:
        need(model["schema_version"] != "1.2", "Schema 1.2 requires a visible-element inventory")
        return {"status":"missing_legacy_inventory", "note":"Legacy file checks do not prove full element coverage"}
    fields(inventory, {"schema_version", "ui_revision", "reviewed_page_ids", "elements"})
    need(inventory["schema_version"] == "1.0", "Unsupported element inventory schema")
    nonempty(inventory["ui_revision"], "Reviewed UI revision")
    pages = {p["id"]:p for p in model["pages"]}
    need(inventory["reviewed_page_ids"] == list(pages), "Inventory must cover every delivered page in order")
    need(isinstance(inventory["elements"], list) and inventory["elements"], "Visible-element inventory cannot be empty")
    layers = {(p["id"],l["id"]):l for p in model["pages"] for l in p["layers"]}
    assets = {a["id"]:a for a in model["assets"]}
    need(len(assets) == len(model["assets"]), "Duplicate asset IDs")
    mapped, indexed, used, waivers = {}, {}, set(), 0
    for element in inventory["elements"]:
        fields(element, {"id", "page_id", "layer_id", "category", "asset_role", "rect_px", "required_states", "delivery_mode"},
               {"asset_refs", "native_spec", "customer_waiver", "merged_into"})
        need(isinstance(element["id"], str) and ID.fullmatch(element["id"]), "Invalid inventory element ID")
        key = (element["page_id"], element["id"])
        need(key not in indexed, "Duplicate page/element inventory entry")
        layer_key = (element["page_id"],element["layer_id"])
        need(layer_key in layers, "Inventory references an unknown page/layer")
        indexed[key] = element
        mapped.setdefault(layer_key, []).append(element)
        category, role, mode = element["category"], element["asset_role"], element["delivery_mode"]
        need(category in {"graphic", "editable_text", "dynamic_content"}, "Invalid visible-element category")
        need(role in ROLES if category == "graphic" else role in {"editable_text", "dynamic_content"}, "Invalid role/category pairing")
        rect = element["rect_px"]
        need(isinstance(rect,list) and len(rect)==4 and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in rect), "Invalid element rectangle")
        x,y,w,h = rect; canvas = pages[element["page_id"]]["design_size_px"]
        need(w>0 and h>0 and x+w<=canvas[0] and y+h<=canvas[1], "Inventory element exceeds page canvas")
        states = element["required_states"]
        need(isinstance(states,list) and states and all(isinstance(s,str) and s.strip() for s in states)
             and len({s.casefold() for s in states})==len(states), "Explicit unique required states are required")
        need(mode in {"export", "native", "merged"}, "Unresolved or invalid element delivery mode")
        if mode == "export":
            need(category=="graphic" and "native_spec" not in element and "merged_into" not in element and "customer_waiver" not in element, "Export element has conflicting delivery fields")
            refs = element.get("asset_refs")
            need(isinstance(refs,list) and refs, "Exported graphic needs independent asset references: "+element["page_id"]+"/"+element["id"])
            bound = {}
            for ref in refs:
                fields(ref,{"state","asset_id"})
                need(isinstance(ref["state"],str) and ref["state"].casefold() not in bound, "Duplicate element state mapping")
                need(ref["asset_id"] in assets, "Element references a missing asset")
                asset = assets[ref["asset_id"]]
                need(asset.get("asset_role")==role, "Asset role does not match element role")
                need(asset["state"].casefold()==ref["state"].casefold(), "Mapped state differs from asset state")
                need(asset["design_size_px"]==rect[2:], "Independent asset canvas differs from element rectangle")
                bound[ref["state"].casefold()] = asset
                used.add(asset["id"])
            need(set(bound)=={s.casefold() for s in states}, "Missing or extra states in element export: "+element["page_id"]+"/"+element["id"])
            if len(states)>1 and role=="indicator":
                hashes = [a.get("rgba_sha256") for a in bound.values()]
                if all(hashes):
                    need(len(set(hashes))==len(hashes), "Indicator states must have distinct decoded pixels")
        elif mode == "native":
            need("asset_refs" not in element and "merged_into" not in element, "Native element has conflicting export fields")
            spec = element.get("native_spec")
            fields(spec,{"target_control","parameters","state_map"})
            nonempty(spec["target_control"],"Target native control")
            need(isinstance(spec["parameters"],dict) and spec["parameters"], "Native control requires reproducible parameters")
            need(isinstance(spec["state_map"],dict) and set(spec["state_map"])==set(states), "Native state map is incomplete")
            for value in spec["state_map"].values():
                nonempty(value,"Native state implementation")
        else:
            need(category=="graphic" and role!="indicator" and len(states)==1 and "asset_refs" not in element and "native_spec" not in element, "Dynamic indicator/state graphics cannot be merged into a static background")
            nonempty(element.get("merged_into"),"Parent exported element")
        if category=="graphic" and mode!="export":
            waiver = element.get("customer_waiver")
            fields(waiver,{"status","ui_revision","reason","customer_message","message_ref","confirmed_at"})
            need(waiver["status"]=="confirmed" and waiver["ui_revision"]==inventory["ui_revision"], "Graphic export exemption needs current customer confirmation")
            for field in ("reason","customer_message","message_ref","confirmed_at"):
                nonempty(waiver[field],field)
            try:
                need(datetime.fromisoformat(waiver["confirmed_at"].replace("Z","+00:00")).tzinfo is not None, "Waiver timestamp needs a timezone")
            except ValueError as error:
                raise ValueError("Invalid graphic exemption timestamp") from error
            waivers += 1
        elif "customer_waiver" in element:
            need(False,"Waivers apply only to native/merged graphic exceptions")
    need(set(mapped)==set(layers), "Missing element delivery decisions for layers: "+", ".join(p+"/"+l for p,l in sorted(set(layers)-set(mapped))))
    for key, layer in layers.items():
        entries = mapped[key]
        if layer["type"].lower() in GRAPHIC_TYPES:
            need(any(e["category"]=="graphic" for e in entries), "Graphic layer cannot be relabeled as native text/dynamic data")
        if layer["type"].lower() in {"button","control"}:
            plates = [e for e in entries if e["asset_role"]=="control_plate" and e["delivery_mode"]=="export"]
            need(len(plates)==1 and {"s0","s1"}<=set(plates[0]["required_states"]), "Button/control requires one independent exported s0/s1 plate entry")
            plate = plates[0]
            need(plate["rect_px"]==layer["rect_px"], "Button plate must cover its declared logical control rectangle")
            states = {ref["state"].casefold():assets[ref["asset_id"]] for ref in plate["asset_refs"]}
            if states["s0"].get("rgba_sha256") and states["s1"].get("rgba_sha256"):
                need(states["s0"]["rgba_sha256"]!=states["s1"]["rgba_sha256"], "Button plate s0/s1 must have distinct decoded pixels")
    for element in indexed.values():
        if element["delivery_mode"]=="merged":
            parent = indexed.get((element["page_id"],element["merged_into"]))
            need(parent is not None and parent is not element and parent["delivery_mode"]=="export" and parent["asset_role"] in {"background","panel"}
                 and len(parent["required_states"])==1, "Merged element must map to one exported static parent on the same page")
            x,y,w,h = element["rect_px"]; px,py,pw,ph = parent["rect_px"]
            need(px<=x and py<=y and x+w<=px+pw and y+h<=py+ph, "Merged child is outside its parent asset")
    need(used==set(assets), "Asset package includes files not mapped to any inventoried element")
    return {"status":"complete_registered_inventory", "pages":len(pages), "elements":len(indexed), "assets":len(used),
            "graphic_customer_exemptions":waivers, "visual_inventory_verified":False,
            "note":"Checks registered layers/elements only. Compare every approved HTML page visually; undeclared elements cannot be inferred."}

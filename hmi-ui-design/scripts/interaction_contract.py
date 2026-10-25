"""Declarative local-simulation contract shared by packaging and acceptance."""
import math
import re

KINDS = {"momentary", "toggle", "indicator", "io-input", "output", "navigation", "parameter", "gauge", "bar"}
CLICKABLE = KINDS - {"gauge", "bar"}


def validate_simulation(model):
    def need(ok, message):
        if not ok:
            raise ValueError(message)

    def fields(obj, required, optional=()):
        need(isinstance(obj, dict) and set(required) <= obj.keys()
             and obj.keys() <= set(required) | set(optional), "Invalid simulation fields")

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    simulation = model.get("simulation")
    if model["schema_version"] == "1.0":
        need(simulation is None, "Use schema 1.1 for interactive prototypes")
        need(not any("interaction" in layer for page in model["pages"] for layer in page["layers"]),
             "Use schema 1.1 for layer interactions")
        return "Legacy annotation-only package; no functional prototype"
    need(model["schema_version"] == "1.1", "Unsupported simulation schema")
    fields(simulation, ("variables", "required_features"))
    need(isinstance(simulation["variables"], list), "variables must be an array")
    variables = {}
    for v in simulation["variables"]:
        fields(v, ("id", "type", "initial"), ("min", "max", "step", "unit", "animate"))
        need(isinstance(v["id"], str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", v["id"])
             and v["id"] not in variables, "Invalid or duplicate variable id")
        need(v["type"] in {"boolean", "number"}, "Variable type must be boolean or number")
        if v["type"] == "boolean":
            need(type(v["initial"]) is bool and set(v) == {"id", "type", "initial"}, "Invalid boolean variable")
        else:
            need(all(k in v and finite(v[k]) for k in ("initial", "min", "max", "step")), "Numeric bounds/step required")
            need(v["min"] < v["max"] and v["step"] > 0 and v["min"] <= v["initial"] <= v["max"], "Invalid numeric range")
            for value in (v["initial"], v["max"]):
                q = (value - v["min"]) / v["step"]
                need(math.isclose(q, round(q), abs_tol=1e-7), "Value must align with step from min")
            need(isinstance(v.get("unit", ""), str) and len(v.get("unit", "")) <= 32, "Invalid unit")
            need(type(v.get("animate", False)) is bool, "animate must be boolean")
        variables[v["id"]] = v
    required = simulation["required_features"]
    need(isinstance(required, list) and required and all(isinstance(k, str) and k in KINDS for k in required)
         and len(required) == len(set(required)), "Declare unique required_features")
    page_ids = {p["id"] for p in model["pages"]}
    features, bindings = set(), {}
    for page in model["pages"]:
        for layer in page["layers"]:
            it = layer.get("interaction")
            if it is None:
                need(layer["type"].lower() not in {"button", "control", "gauge", "bar", "indicator", "io-input", "output", "parameter"},
                     f"Interactive layer {layer['id']} needs an explicit behavior")
                continue
            fields(it, ("kind",), ("variable", "target_page", "orientation"))
            kind = it["kind"]
            need(isinstance(kind, str) and kind in KINDS, "Unknown interaction kind")
            need(isinstance(layer.get("text"), str) and layer["text"].strip(), "Interactive label must be explicit editable text")
            if kind in CLICKABLE:
                need(layer["type"].lower() in {"button", "control"}, "Clickable layers must use button/control and s0/s1 assets")
            if kind == "navigation":
                need(set(it) == {"kind", "target_page"} and it["target_page"] in page_ids, "Invalid navigation target")
            else:
                need(it.get("variable") in variables and "target_page" not in it, "Unknown bound variable")
                numeric = kind in {"parameter", "gauge", "bar"}
                need(variables[it["variable"]]["type"] == ("number" if numeric else "boolean"), "Binding type mismatch")
                need("orientation" not in it or kind == "bar" and it["orientation"] in {"horizontal", "vertical"}, "Invalid bar orientation")
            signature = tuple(sorted(it.items()))
            need(layer["id"] not in bindings or bindings[layer["id"]] == signature, "Shared component behavior differs across pages")
            bindings[layer["id"]] = signature
            features.add(kind)
    need(set(required) <= features, f"Missing required interactive features: {sorted(set(required) - features)}")
    need(features, "An interactive prototype requires functional components")
    momentary = {b["variable"] for p in model["pages"] for l in p["layers"] if (b := l.get("interaction", {})).get("kind") == "momentary"}
    need(all(variables[k]["initial"] is False for k in momentary), "Momentary command variables must initially be false")
    need(not any(l.get("interaction", {}).get("variable") in momentary and l["interaction"]["kind"] in {"toggle", "indicator", "io-input", "output"}
                 for p in model["pages"] for l in p["layers"]), "Momentary command variables cannot also be latching controls")
    return f"{len(variables)} variables; interactive features: {', '.join(sorted(features))}"

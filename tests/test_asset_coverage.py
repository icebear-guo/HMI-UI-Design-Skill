"""Synthetic inventories test independent graphic delivery, state coverage and explicit exceptions."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from PIL import Image

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO / "hmi-ui-design/scripts"))
from asset_coverage import validate_asset_coverage
from build_delivery import build


def fixture():
    layers=[{"id":"user","name":"User symbol","type":"icon","rect_px":[10,10,20,20]},
            {"id":"led","name":"IO LED","type":"indicator","rect_px":[40,10,14,14]},
            {"id":"label","name":"Label","type":"text","rect_px":[10,50,100,20]}]
    assets=[{"id":"user-default","component_id":"user","asset_role":"icon","state":"default","design_size_px":[20,20],"rgba_sha256":"c"*64},
            {"id":"led-off","component_id":"led","asset_role":"indicator","state":"off","design_size_px":[14,14],"rgba_sha256":"a"*64},
            {"id":"led-on","component_id":"led","asset_role":"indicator","state":"on","design_size_px":[14,14],"rgba_sha256":"b"*64}]
    entries=[]
    for layer in layers:
        e={"id":layer["id"],"page_id":"overview","layer_id":layer["id"],"rect_px":layer["rect_px"],"category":"graphic","asset_role":"icon" if layer["id"]=="user" else "indicator","required_states":["default"] if layer["id"]=="user" else ["off","on"],"delivery_mode":"export"}
        if layer["id"]=="label":
            e.update(category="editable_text",asset_role="editable_text",required_states=["default"],delivery_mode="native",native_spec={"target_control":"editable text","parameters":{"size_px":16,"text":"Label"},"state_map":{"default":"show editable text"}})
        else:
            e["asset_refs"]=[{"state":a["state"],"asset_id":a["id"]} for a in assets if a["component_id"]==layer["id"]]
        entries.append(e)
    return {"schema_version":"1.2","pages":[{"id":"overview","design_size_px":[200,100],"layers":layers}],"assets":assets,
            "element_inventory":{"schema_version":"1.0","ui_revision":"synthetic-review-v1","reviewed_page_ids":["overview"],"elements":entries}}


def waiver():
    return {"status":"confirmed","ui_revision":"synthetic-review-v1","reason":"Synthetic test exception only","customer_message":"SYNTHETIC TEST ONLY: this individual exception is accepted","message_ref":"synthetic-test","confirmed_at":"2026-10-25T12:00:00+08:00"}


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.model=fixture()

    def reject_coverage(self, model=None):
        with self.assertRaises(ValueError):
            validate_asset_coverage(self.model if model is None else model)

    def native_user(self):
        e=self.model["element_inventory"]["elements"][0]
        e.pop("asset_refs")
        e.update(delivery_mode="native",native_spec={"target_control":"user symbol control","parameters":{"size_px":[20,20],"stroke_px":2,"shape":"head and shoulders"},"state_map":{"default":"draw user symbol"}})
        self.model["assets"]=[a for a in self.model["assets"] if a["id"]!="user-default"]
        return e

    def merged_user(self):
        e=self.native_user(); e.pop("native_spec")
        e.update(delivery_mode="merged",merged_into="background",customer_waiver=waiver())
        self.model["pages"][0]["layers"].append({"id":"background","name":"Background","type":"background","rect_px":[0,0,200,100]})
        self.model["assets"].append({"id":"background-default","component_id":"background","asset_role":"background","state":"default","design_size_px":[200,100]})
        self.model["element_inventory"]["elements"].append({"id":"background","page_id":"overview","layer_id":"background","category":"graphic","asset_role":"background","rect_px":[0,0,200,100],"required_states":["default"],"delivery_mode":"export","asset_refs":[{"state":"default","asset_id":"background-default"}]})
        return e

    def test_complete_registered_graphics(self):
        result=validate_asset_coverage(self.model)
        self.assertEqual(result["status"],"complete_registered_inventory")
        self.assertEqual(result["elements"],3)
        self.assertFalse(result["visual_inventory_verified"])

    def test_new_schema_requires_inventory(self):
        del self.model["element_inventory"]; self.reject_coverage()

    def test_old_schema_is_explicitly_limited(self):
        del self.model["element_inventory"]; self.model["schema_version"]="1.1"
        self.assertEqual(validate_asset_coverage(self.model)["status"],"missing_legacy_inventory")

    def test_user_icon_not_listed_fails(self):
        self.model["element_inventory"]["elements"].pop(0); self.reject_coverage()

    def test_missing_user_icon_file_reference_fails(self):
        self.model["assets"].pop(0); self.reject_coverage()

    def test_led_on_state_missing_fails(self):
        self.model["element_inventory"]["elements"][1]["asset_refs"].pop(); self.reject_coverage()

    def test_identical_led_pixels_fail(self):
        self.model["assets"][2]["rgba_sha256"]=self.model["assets"][1]["rgba_sha256"]; self.reject_coverage()

    def test_role_mismatch_fails(self):
        self.model["assets"][0]["asset_role"]="control_plate"; self.reject_coverage()

    def test_native_icon_without_customer_exception_fails(self):
        self.native_user(); self.reject_coverage()

    def test_native_icon_with_current_individual_exception(self):
        self.native_user()["customer_waiver"]=waiver()
        self.assertEqual(validate_asset_coverage(self.model)["graphic_customer_exemptions"],1)

    def test_stale_exception_fails(self):
        self.native_user()["customer_waiver"]=waiver()
        self.model["element_inventory"]["ui_revision"]="synthetic-review-v2"; self.reject_coverage()

    def test_pending_exception_fails(self):
        e=self.native_user(); e["customer_waiver"]=waiver(); e["customer_waiver"]["status"]="pending"; self.reject_coverage()

    def test_native_icon_needs_reproducible_parameters(self):
        e=self.native_user(); e["customer_waiver"]=waiver(); e["native_spec"]["parameters"]={}; self.reject_coverage()

    def test_native_state_map_must_cover_states(self):
        e=self.native_user(); e["customer_waiver"]=waiver(); e["native_spec"]["state_map"]={}; self.reject_coverage()

    def test_graphic_cannot_be_called_editable_text(self):
        e=self.native_user(); e.update(category="editable_text",asset_role="editable_text"); self.reject_coverage()

    def test_static_merge_requires_exported_parent(self):
        self.merged_user()
        self.assertEqual(validate_asset_coverage(self.model)["graphic_customer_exemptions"],1)

    def test_missing_merge_parent_fails(self):
        self.merged_user()["merged_into"]="missing"; self.reject_coverage()

    def test_indicator_cannot_be_hidden_in_background(self):
        e=self.model["element_inventory"]["elements"][1]
        e.pop("asset_refs"); e.update(delivery_mode="merged",merged_into="user",customer_waiver=waiver()); self.reject_coverage()

    def test_extra_unmapped_asset_fails(self):
        asset=copy.deepcopy(self.model["assets"][0]); asset["id"]="extra"; self.model["assets"].append(asset); self.reject_coverage()

    def test_missing_page_inventory_fails(self):
        self.model["element_inventory"]["reviewed_page_ids"]=[]; self.reject_coverage()

    def test_shared_asset_maps_each_instance(self):
        page=copy.deepcopy(self.model["pages"][0]); page["id"]="settings"; self.model["pages"].append(page)
        entries=copy.deepcopy(self.model["element_inventory"]["elements"])
        for e in entries:e["page_id"]="settings"
        self.model["element_inventory"]["elements"].extend(entries)
        self.model["element_inventory"]["reviewed_page_ids"].append("settings")
        self.assertEqual(validate_asset_coverage(self.model)["assets"],3)

    def test_duplicate_instance_fails(self):
        self.model["element_inventory"]["elements"].append(copy.deepcopy(self.model["element_inventory"]["elements"][0])); self.reject_coverage()

    def test_asset_canvas_mismatch_fails(self):
        self.model["assets"][0]["design_size_px"]=[40,40]; self.reject_coverage()

    def test_pending_disposition_fails(self):
        self.model["element_inventory"]["elements"][0]["delivery_mode"]="pending"; self.reject_coverage()

    def test_roles_and_shared_button_instances_can_build(self):
        with tempfile.TemporaryDirectory(prefix="coverage-build-",dir=Path(__file__).parent) as temp:
            root=Path(temp)
            source=REPO / "examples/interactive-preview/inputs"
            import shutil
            shutil.copytree(source,root / "inputs")
            path=root / "inputs/delivery-manifest.json"
            data=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("element_inventory"),str):
                data["element_inventory"]=json.loads((path.parent/data["element_inventory"]).read_text(encoding="utf-8"))
            Image.new("RGBA",(20,20),(0,0,0,255)).save(path.parent / "assets/start-icon.png")
            data["assets"].insert(0,{"id":"start-icon","file":"assets/start-icon.png","component_id":"start","asset_role":"icon","state":"s0","design_size_px":[20,20]})
            data["element_inventory"]["elements"].append({"id":"start-icon","page_id":"overview","layer_id":"start","category":"graphic","asset_role":"icon","rect_px":[32,118,20,20],"required_states":["s0"],"delivery_mode":"export","asset_refs":[{"state":"s0","asset_id":"start-icon"}]})
            # The second navigation instance reuses the first instance's plate assets.
            for layer in data["pages"][1]["layers"]:
                if layer["id"]=="nav-overview":layer["id"]="shared-home-instance"
            for element in data["element_inventory"]["elements"]:
                if element["page_id"]=="io" and element["layer_id"]=="nav-overview":
                    element["layer_id"]="shared-home-instance"
                    element["id"]=element["id"].replace("nav-overview","shared-home-instance",1)
            path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
            build(path,root / "package")
            result=json.loads((root / "package/specs/design.json").read_text(encoding="utf-8"))
            self.assertEqual(validate_asset_coverage(result)["status"],"complete_registered_inventory")
            import os
            node=os.environ.get("HMI_TEST_NODE") or shutil.which("node")
            p=subprocess.run([sys.executable,str(REPO / "hmi-ui-design/scripts/accept_delivery.py"),"--package",str(root / "package"),"--node",str(node),"--scope","files-and-logic"],capture_output=True,text=True,encoding="utf-8")
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads(p.stdout)["element_coverage"]["status"],"complete_registered_inventory")

    def test_button_plate_cannot_use_native_graphic_exception(self):
        self.model["pages"][0]["layers"][0]["type"]="button"
        self.native_user()["customer_waiver"]=waiver()
        self.reject_coverage()


if __name__ == "__main__":
    unittest.main(verbosity=2)

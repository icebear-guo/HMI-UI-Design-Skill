"""Portable checks for maintained resources, direction proposals and offline prototype logic."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "hmi-ui-design"
if not SKILL.is_dir():
    raise RuntimeError("Run this suite from the repository's tests directory")
sys.path.insert(0, str(SKILL / "scripts"))
from build_style_proposal import build, prepare, resolve_catalog
from build_delivery import build as build_delivery

NODE = os.environ.get("HMI_TEST_NODE") or shutil.which("node")


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill-check-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.data = json.loads((SKILL / "assets/style-proposal.template.json").read_text(encoding="utf-8"))
        self.input = self.root / "input.json"
        self.assets = SKILL / "assets"

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.input.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def reject(self):
        self.write()
        with self.assertRaises((ValueError, OSError)):
            build(self.input, self.root / "out", self.assets)
        self.assertFalse((self.root / "out").exists())
        self.assertFalse((self.root / "out.zip").exists())

    def library_copy(self):
        self.assets = self.root / "assets"
        shutil.copytree(SKILL / "assets", self.assets)

    def mutate_library(self, relative, mutation):
        path = self.assets / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        mutation(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def node_check(self, script, html):
        self.assertTrue(NODE, "Node.js is needed for declared logic checks")
        p = subprocess.run([str(NODE), str(SKILL / "scripts" / script), str(html)], capture_output=True, text=True, encoding="utf-8")
        result = json.loads(p.stdout)
        self.assertEqual(p.returncode, 0, str(result))
        self.assertEqual(result["backend"], "pure-js-simulation")
        self.assertEqual(result["browser_rendering"], "not_checked")
        return result

    def test_resource_links_and_json(self):
        for document in [REPO / "README.md", *SKILL.rglob("*.md")]:
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((document.parent / target.split("#")[0]).exists(), f"Broken link in {document.name}: {target}")
        for path in (SKILL / "assets").rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue((SKILL / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: hmi-ui-design\n"))

    def test_catalog_registration(self):
        catalog = resolve_catalog(SKILL / "assets")
        self.assertGreaterEqual(len(catalog["themes"]), 3)
        self.assertGreaterEqual(len(catalog["layouts"]), 3)

    def test_navigation_and_button_text_contrast(self):
        def luminance(color):
            channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
            channels = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
            return .2126*channels[0]+.7152*channels[1]+.0722*channels[2]
        for row in resolve_catalog(SKILL / "assets")["themes"].values():
            colors = row["profile"]["colors"]
            for foreground,background in (("text_on_accent","accent"),("text_on_button","button_s0"),("text_on_button","button_s1"),("text_primary","surface")):
                a,b = sorted([luminance(colors[foreground]),luminance(colors[background])])
                self.assertGreaterEqual((b+.05)/(a+.05),4.5)

    def test_actual_proposal_package_and_logic(self):
        self.write()
        out = self.root / "out"
        result = build(self.input, out)
        self.assertEqual(result["selection"], "pending")
        self.assertFalse(result["browser_verified"])
        self.node_check("check_style_logic.cjs", out / "index.html")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256((out / item["file"]).read_bytes()).hexdigest())
        with zipfile.ZipFile(self.root / "out.zip") as zipped:
            for file in out.iterdir():
                self.assertEqual(zipped.read("out/"+file.name), file.read_bytes())
        self.assertEqual(json.loads((out / "selection.pending.json").read_text(encoding="utf-8"))["status"], "pending")

    def test_new_theme_registration_without_rewriting_skill(self):
        self.library_copy()
        source = self.assets / "themes/neutral-light.json"
        theme = json.loads(source.read_text(encoding="utf-8"))
        theme.update(id="custom-light", version="1.1.0", name="新增浅色")
        (self.assets / "themes/custom-light.json").write_text(json.dumps(theme), encoding="utf-8")
        self.mutate_library("style-catalog.json", lambda c: c["themes"].append({"id":"custom-light","version":"1.1.0","file":"themes/custom-light.json"}))
        self.data["variants"][0].update(theme_id="custom-light", theme_version="1.1.0")
        self.write()
        model = prepare(self.input, self.assets)
        self.assertIn("custom-light@1.1.0", model["themes"])

    def test_missing_canvas_is_rejected(self):
        del self.data["canvas_px"]; self.reject()

    def test_new_layout_registration_without_rewriting_skill(self):
        self.library_copy()
        layout = json.loads((self.assets / "layouts/bottom-balanced.json").read_text(encoding="utf-8"))
        layout.update(id="custom-bottom", version="1.1.0", name="新增底部布局")
        layout["regions"].update(content=[0,.14,1,.72], navigation=[0,.86,1,.14])
        (self.assets / "layouts/custom-bottom.json").write_text(json.dumps(layout), encoding="utf-8")
        self.mutate_library("style-catalog.json", lambda c: c["layouts"].append({"id":"custom-bottom","version":"1.1.0","file":"layouts/custom-bottom.json"}))
        self.data["variants"][0].update(layout_id="custom-bottom", layout_version="1.1.0")
        self.write(); build(self.input, self.root / "out", self.assets)
        self.node_check("check_style_logic.cjs", self.root / "out/index.html")

    def test_physical_size_is_independent(self):
        self.data["physical_size"].update(diagonal_in=10.1, visible_width_mm=220, visible_height_mm=130)
        self.write(); model = prepare(self.input)
        self.assertEqual(model["canvas_px"], [1024,600])
        self.assertEqual(model["physical_size"]["diagonal_in"], 10.1)

    def test_invalid_physical_size(self):
        self.data["physical_size"]["diagonal_in"] = -1; self.reject()

    def test_profile_version_must_match(self):
        self.data["variants"][0]["theme_version"] = "9.0.0"; self.reject()

    def test_catalog_path_cannot_escape(self):
        self.library_copy()
        self.mutate_library("style-catalog.json", lambda c: c["themes"][0].update(file="../private.json")); self.reject()

    def test_catalog_identity_must_match(self):
        self.library_copy()
        self.mutate_library("themes/neutral-light.json", lambda c: c.update(version="2.0.0")); self.reject()

    def test_overlapping_regions(self):
        self.library_copy()
        self.mutate_library("layouts/bottom-balanced.json", lambda c: c["regions"].update(content=[0,0,1,1])); self.reject()

    def test_unsupported_small_canvas(self):
        self.data["canvas_px"] = [320,240]; self.reject()

    def test_deprecated_profile_not_chosen_for_new_work(self):
        self.library_copy()
        self.mutate_library("themes/neutral-light.json", lambda c: c.update(status="deprecated")); self.reject()

    def test_invalid_color_is_rejected(self):
        self.library_copy()
        self.mutate_library("themes/neutral-light.json", lambda c: c["colors"].update(background="url(private.png)")); self.reject()

    def test_snapshot_must_have_valid_ranges(self):
        self.data["snapshot"]["metrics"][0]["value"] = 101; self.reject()

    def test_metric_capacity_depends_on_layout(self):
        for i in range(3):
            row = copy.deepcopy(self.data["snapshot"]["metrics"][0])
            row.update(id="extra-"+str(i),label="新增指标")
            self.data["snapshot"]["metrics"].append(row)
        self.reject()

    def test_representative_page_must_exist(self):
        self.data["representative_page_id"] = "unknown"; self.reject()

    def test_duplicate_variant_id(self):
        self.data["variants"][1]["id"] = self.data["variants"][0]["id"]; self.reject()

    def test_unsafe_content_stays_data(self):
        injection = '</script><img src=x onerror="throw 0">'
        self.data["snapshot"]["page_title"] = injection
        self.write(); build(self.input, self.root / "out")
        self.assertNotIn(injection, (self.root / "out/index.html").read_text(encoding="utf-8"))
        self.node_check("check_style_logic.cjs", self.root / "out/index.html")

    def test_existing_output_not_overwritten(self):
        self.write(); build(self.input, self.root / "out")
        old = (self.root / "out/index.html").read_bytes()
        with self.assertRaises(ValueError):
            build(self.input, self.root / "out")
        self.assertEqual(old, (self.root / "out/index.html").read_bytes())

    def test_profile_snapshot_is_frozen(self):
        self.library_copy(); self.write(); build(self.input, self.root / "out", self.assets)
        raw = (self.root / "out/proposal.json").read_bytes()
        self.mutate_library("themes/neutral-light.json", lambda c: c["colors"].update(background="#AAAAAA"))
        self.assertEqual(raw, (self.root / "out/proposal.json").read_bytes())

    def test_modified_behavior_not_executed(self):
        self.write(); build(self.input, self.root / "out")
        path = self.root / "out/index.html"
        path.write_text(path.read_text(encoding="utf-8").replace("'use strict';", "'use strict';throw 0;"), encoding="utf-8")
        p = subprocess.run([str(NODE), str(SKILL / "scripts/check_style_logic.cjs"), str(path)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode,1)
        self.assertIn("Untrusted", json.loads(p.stdout)["checks"][0]["detail"])

    def test_full_interactive_delivery_and_scoped_acceptance(self):
        source = REPO / "examples/interactive-preview/inputs/delivery-manifest.json"
        out = self.root / "interactive"
        build_delivery(source, out)
        self.node_check("check_viewer_logic.cjs", out / "index.html")
        for scope, expected in (("files-and-logic",0),("complete",3)):
            p = subprocess.run([sys.executable, str(SKILL / "scripts/accept_delivery.py"), "--package", str(out), "--node", str(NODE), "--scope", scope], capture_output=True, text=True, encoding="utf-8")
            report = json.loads(p.stdout)
            self.assertEqual(p.returncode,expected,str(report))
            self.assertEqual(report["file_acceptance"],"pass")
            self.assertEqual(report["logic_acceptance"],"pass")
            self.assertFalse(report["browser_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Synthetic review records test phase conditions; no customer approval or rendering is performed."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hmi-ui-design/scripts"))
from check_project_workflow import check


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-test-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.path = self.root / "project-workflow.json"
        self.record = json.loads((REPO / "hmi-ui-design/assets/project-workflow.template.json").read_text(encoding="utf-8"))
        self.record.update(page_count=2, page_ids=["overview", "io"])
        for name, stage in self.record["stages"].items():
            directory = self.root / stage["artifact_dir"]
            directory.mkdir(parents=True)
            if name == "parameters":
                (directory / stage["entry"]).write_text("Synthetic parameter review; 2 pages, 1024x600", encoding="utf-8")
            else:
                (directory / "index.html").write_text("<!doctype html><title>Synthetic HTML review</title>", encoding="utf-8")
                (directory / "style.css").write_text("body{color:#17212b}", encoding="utf-8")
            if name == "interactive_ui":
                stage["pages"] = [{"id":"overview","entry":"overview.html"},{"id":"io","entry":"io.html"}]
                for page in stage["pages"]:
                    (directory / page["entry"]).write_text("<!doctype html><title>"+page["id"]+"</title>", encoding="utf-8")
            self.snapshot(name)
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, name):
        stage = self.record["stages"][name]
        directory = self.root / stage["artifact_dir"]
        stage["files"] = [{"file":file.relative_to(directory).as_posix(),"sha256":hashlib.sha256(file.read_bytes()).hexdigest()}
                          for file in sorted(directory.rglob("*")) if file.is_file()]

    def write(self):
        self.path.write_text(json.dumps(self.record, ensure_ascii=False, indent=2), encoding="utf-8")

    def result(self, action="slicing"):
        self.write()
        return check(self.path, action)

    def approve(self, name):
        stage = self.record["stages"][name]
        results = {r["stage"]:r for r in self.result()["stages"]}
        for upstream in stage["depends_on"]:
            stage["depends_on"][upstream] = results[upstream]["review_digest"]
        digest = {r["stage"]:r for r in self.result()["stages"]}[name]["review_digest"]
        stage.update(status="confirmed", customer_confirmation={
            "customer_message":"SYNTHETIC TEST ONLY: this stage/version is accepted",
            "message_ref":"synthetic-unit-test-message", "confirmed_at":"2026-10-25T12:00:00+08:00", "reviewed_digest":digest})
        self.write()

    def approve_all(self):
        for name in ("parameters", "direction", "interactive_ui"):
            self.approve(name)

    def blocked(self, action="slicing"):
        self.assertEqual(self.result(action)["status"], "blocked")

    def test_no_confirmations_does_not_advance(self):
        for action in ("samples", "ui", "slicing", "delivery"):
            self.blocked(action)

    def test_parameters_only_allow_html_samples(self):
        self.approve("parameters")
        self.assertEqual(self.result("samples")["status"], "ready")
        self.blocked("ui"); self.blocked("slicing")

    def test_two_confirmations_allow_ui_but_not_slicing(self):
        self.approve("parameters"); self.approve("direction")
        self.assertEqual(self.result("ui")["status"], "ready")
        self.blocked("slicing"); self.blocked("delivery")

    def test_all_three_current_records_are_ready(self):
        self.approve_all()
        self.assertEqual(self.result()["status"], "ready")
        self.assertEqual(self.result("delivery")["status"], "ready")
        self.assertFalse(self.result()["human_evidence_verified"])

    def test_preference_without_html_approval_is_blocked(self):
        self.approve("parameters")
        self.record["stages"]["direction"]["customer_confirmation"] = {"customer_message":"warm light with left navigation"}
        self.blocked("ui")

    def test_status_confirmed_without_evidence_is_blocked(self):
        self.record["stages"]["parameters"]["status"] = "confirmed"
        self.blocked("samples")

    def test_missing_actual_html_is_blocked(self):
        self.approve_all()
        path = self.root / self.record["stages"]["direction"]["artifact_dir"] / "index.html"
        path.unlink(); self.blocked()

    def test_modified_direction_requires_confirmation_again(self):
        self.approve_all()
        (self.root / self.record["stages"]["direction"]["artifact_dir"] / "index.html").write_text("changed",encoding="utf-8")
        self.blocked()

    def test_modified_linked_css_invalidates_review(self):
        self.approve_all()
        (self.root / self.record["stages"]["interactive_ui"]["artifact_dir"] / "style.css").write_text("changed",encoding="utf-8")
        self.blocked()

    def test_resnapshot_without_new_customer_confirmation_is_blocked(self):
        self.approve_all()
        (self.root / self.record["stages"]["direction"]["artifact_dir"] / "index.html").write_text("changed",encoding="utf-8")
        self.snapshot("direction"); self.blocked()

    def test_upstream_change_invalidates_downstream(self):
        self.approve_all()
        (self.root / self.record["stages"]["parameters"]["artifact_dir"] / self.record["stages"]["parameters"]["entry"]).write_text("new scope",encoding="utf-8")
        self.snapshot("parameters"); self.approve("parameters")
        self.blocked()

    def test_extra_file_is_not_silently_ignored(self):
        self.approve_all()
        (self.root / self.record["stages"]["interactive_ui"]["artifact_dir"] / "extra.css").write_text("changed",encoding="utf-8")
        self.blocked()

    def test_wrong_page_count_is_blocked(self):
        self.approve_all(); self.record["page_count"] = 3; self.blocked()

    def test_missing_page_is_blocked_even_with_new_snapshot(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["pages"].pop()
        self.approve("interactive_ui"); self.blocked()

    def test_duplicate_or_reordered_pages_are_blocked(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["pages"].reverse()
        self.approve("interactive_ui"); self.blocked()

    def test_newly_generated_png_in_review_is_blocked(self):
        self.approve_all()
        path = self.root / self.record["stages"]["direction"]["artifact_dir"] / "early.png"
        path.write_bytes(b"synthetic placeholder, no rendering")
        self.snapshot("direction"); self.approve("direction"); self.approve("interactive_ui")
        self.blocked()

    def test_explicit_existing_customer_asset_can_be_referenced(self):
        self.approve("parameters")
        path = self.root / self.record["stages"]["direction"]["artifact_dir"] / "existing.png"
        path.write_bytes(b"synthetic existing-asset placeholder")
        self.snapshot("direction")
        # Existing assets are explicitly distinguished from generated review output.
        for item in self.record["stages"]["direction"]["files"]:
            item["origin"] = "existing_asset" if item["file"] == "existing.png" else "generated"
        self.approve("direction"); self.approve("interactive_ui")
        self.assertEqual(self.result()["status"], "ready")

    def test_revision_change_invalidates_confirmation(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["revision"] = "u2"
        self.blocked()

    def test_parameter_review_cannot_generate_png_early(self):
        directory = self.root / self.record["stages"]["parameters"]["artifact_dir"]
        (directory / "early.png").write_bytes(b"synthetic placeholder")
        self.snapshot("parameters"); self.approve("parameters")
        self.blocked("samples")

    def test_review_entry_change_invalidates_confirmation(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["entry"] = "overview.html"
        self.blocked()

    def test_changes_requested_cannot_be_ready(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["status"] = "changes_requested"
        self.blocked()

    def test_bad_confirmation_timestamp_is_blocked(self):
        self.approve_all()
        self.record["stages"]["interactive_ui"]["customer_confirmation"]["confirmed_at"] = "unknown"
        self.blocked()

    def test_escaping_artifact_path_is_blocked(self):
        self.record["stages"]["parameters"]["artifact_dir"] = "../elsewhere"
        self.blocked("samples")

    def test_empty_published_template_is_blocked(self):
        self.record = json.loads((REPO / "hmi-ui-design/assets/project-workflow.template.json").read_text(encoding="utf-8"))
        self.blocked()

    def test_checker_is_read_only(self):
        self.approve_all(); self.write()
        files = [self.path, *self.root.rglob("*.html"), *self.root.rglob("*.css")]
        before = {str(p):p.read_bytes() for p in files}
        self.assertEqual(check(self.path,"delivery")["status"],"ready")
        self.assertEqual(before, {str(p):p.read_bytes() for p in files})

    def test_cli_blocked_exit_and_invalid_record(self):
        p = subprocess.run([sys.executable,str(REPO / "hmi-ui-design/scripts/check_project_workflow.py"),"--record",str(self.path),"--for","slicing"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(p.returncode,3)
        self.assertEqual(json.loads(p.stdout)["status"],"blocked")
        self.record["scope"] = "unknown"; self.write()
        p = subprocess.run([sys.executable,str(REPO / "hmi-ui-design/scripts/check_project_workflow.py"),"--record",str(self.path),"--for","delivery"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(p.returncode,1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

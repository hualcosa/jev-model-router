import contextlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import fcntl
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from router_core.cli import main
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.explain import ExplainError, explain_history, scope_hash_for
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.state import PrivateStateStore, StateScope, StateError
from router_core.telemetry import TelemetryLog, TelemetryRecord, activity_record
from router_core.privacy import SYNTHETIC_SMOKE


class ExplainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = os.path.realpath(self.tmp.name)
        self.root = Path(self.project)/"state"
        self.store = PrivateStateStore(self.root)
        self.scope = StateScope("claude",self.project,"PRIVATE_SESSION")
        self.scope_hash = scope_hash_for("claude",self.project,"PRIVATE_SESSION")
        self.log = TelemetryLog(self.store)
        self.calls = []
        profile = bootstrap_profile("claude","cli","2.1.303")
        self.adapter = NativeAdapter(profile,
            merge_config_layers({"mode":"shadow","consent":{"synthetic_tasks":True}},{}),
            self.store,self.classify,project_id=self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def classify(self, payload):
        self.calls.append(payload)
        return ProviderResult(ProviderStatus.SUCCESS,
            TaskRequirements(0,0,0,.99,"T0",risk="low",provider_raw_tier="PRIVATE_PROVIDER_TIER"),
            provider="PRIVATE_PROVIDER",reason_code="PRIVATE_PROVIDER_REASON")

    def event(self, **changes):
        return dict(cwd=self.project,session_id="PRIVATE_SESSION",hook_event_name="PreToolUse",
                    permission_mode="default",tool_name="Agent",tool_use_id="PRIVATE_CALL",
                    tool_input={"prompt":SYNTHETIC_SMOKE,"description":"PRIVATE_DESCRIPTION"},**changes)

    def prepare(self):
        self.assertIsNone(self.adapter.handle(self.event()))
        return next(r for r in self.log.read() if r.to_dict()["source"]=="assessment")

    def view(self, **kwargs):
        return explain_history(self.store,self.scope_hash,**kwargs)

    def tree(self):
        if not self.root.exists():
            return None
        return (self.root.stat().st_mtime_ns,{p.name:(p.stat().st_ino,p.stat().st_mtime_ns,p.stat().st_mode,p.read_bytes())
                for p in self.root.iterdir() if p.is_file() and not p.is_symlink()})

    def test_recorded_route_reason_provenance_and_catalog_not_live(self):
        record=self.prepare()
        report=self.view(row_id=record.to_dict()["row_id"])
        self.assertEqual(report["status"],"explained")
        self.assertEqual(report["external_calls"],0)
        self.assertFalse(report["state_modified"])
        self.assertFalse(report["current_runtime_checked"])
        item=report["records"][0]
        self.assertEqual(item["record"]["data"]["recommended_model"],"haiku")
        self.assertEqual(item["policy_provenance"],"policy_prior")
        self.assertIn("Shadow mode",item["explanation"])
        self.assertEqual(item["catalog"]["status"],"recorded_snapshot")
        self.assertEqual(item["catalog"]["policy_version"],"1.0.0")
        self.assertFalse(item["catalog"]["live_checked"])
        self.assertEqual(item["catalog"]["recorded_policy_controls"]["min_confidence_for_auto"],.75)
        self.assertEqual(item["catalog"]["recorded_policy_controls"]["mode"],"shadow")
        self.assertEqual(item["catalog"]["mapping_identity"],"unique")
        mapping=item["catalog"]["matched_mappings"][0]
        self.assertEqual(mapping["runtime_model_id"],"haiku")
        self.assertEqual(mapping["availability_source"],"user_assumption")
        self.assertEqual(mapping["mapping_provenance"],"p0_cli_spike_2026-10-19")
        self.assertEqual(len(self.calls),1)
        for secret in ("PRIVATE_",self.project,"imaginary files","task_summary","mapping_evidence\":"):
            self.assertNotIn(secret,json.dumps(report))

    def test_no_writes_no_temporary_cleanup_and_no_provider_recall(self):
        self.prepare()
        temporary=self.root/(".tmp-"+"a"*32)
        temporary.write_text("PRIVATE_ORPHAN")
        temporary.chmod(0o600)
        before=self.tree()
        with patch.object(self.store,"_transaction",side_effect=AssertionError("read used transaction")):
            self.view()
            self.view()
        self.assertEqual(self.tree(),before)
        self.assertEqual(len(self.calls),1)
        self.assertTrue(temporary.exists())

    def test_empty_history_neither_creates_files_nor_proves_disabled(self):
        result=self.view()
        self.assertEqual(result["status"],"no_records")
        self.assertFalse(self.root.exists())
        self.assertIn("does not prove disabled",result["notice"])
        self.root.mkdir(mode=0o700)
        self.view()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_missing_expired_and_corrupt_state_do_not_reclassify_or_echo_contents(self):
        record=self.prepare()
        row_id=record.to_dict()["row_id"]
        path=self.root/"state.json"
        original=path.read_bytes()
        path.unlink()
        self.assertEqual(self.view(row_id=row_id)["records"][0]["catalog"]["status"],"missing_or_expired")
        self.assertFalse(path.exists())
        path.write_bytes(original);path.chmod(0o600)
        now=self.store.clock()
        self.store.clock=lambda:now+90000
        before=self.tree()
        self.assertEqual(self.view(row_id=row_id)["records"][0]["catalog"]["status"],"missing_or_expired")
        self.assertEqual(self.tree(),before)
        self.store.clock=lambda:now
        path.write_text("PRIVATE_INVALID_STATE")
        report=self.view(row_id=row_id)
        self.assertEqual(report["records"][0]["catalog"]["status"],"unavailable")
        self.assertNotIn("PRIVATE",json.dumps(report))
        self.assertEqual(path.read_text(),"PRIVATE_INVALID_STATE")
        self.assertEqual(len(self.calls),1)

    def test_hash_mismatch_never_attaches_wrong_catalog(self):
        record=self.prepare().to_dict()
        for field in ("catalog_hash","policy_hash"):
            row=json.loads(json.dumps(record))
            row["row_id"]=secrets.token_hex(16)
            row["data"][field]="0"*64
            self.log.append(TelemetryRecord(json.dumps(row)))
            item=self.view(row_id=row["row_id"])["records"][0]
            self.assertEqual(item["catalog"]["status"],"hash_mismatch")
            self.assertEqual(item["catalog"]["matched_mappings"],[])

    def test_snapshot_lookup_is_scoped_even_for_same_content_hash(self):
        record=self.prepare().to_dict()
        missing_scope=scope_hash_for("claude",self.project,"different-private-session")
        row=json.loads(json.dumps(record));row["scope_hash"]=missing_scope;row["row_id"]=secrets.token_hex(16)
        self.log.append(TelemetryRecord(json.dumps(row)))
        report=explain_history(self.store,missing_scope,row_id=row["row_id"])
        self.assertEqual(report["records"][0]["catalog"]["status"],"missing_or_expired")
        wrong=self.view(row_id=row["row_id"])
        self.assertEqual(wrong["status"],"no_records")
        self.assertEqual(wrong["records"],[])

    def test_scope_runtime_row_selector_and_persisted_limit(self):
        self.prepare()
        records=[]
        for _ in range(7):
            record=activity_record(self.adapter.profile.spawn,"shadow",self.scope,"spawn","pinned","explicit_pin",tool_id="PRIVATE_PIN")
            self.log.append(record);records.append(record)
        report=self.view(limit=3)
        self.assertEqual([i["record"]["row_id"] for i in report["records"]],[r.to_dict()["row_id"] for r in records[-3:]])
        self.assertEqual(report["returned_records"],3)
        self.assertGreater(report["retained_scope_records"],3)
        self.assertEqual(self.view(runtime="codex")["status"],"no_records")
        self.assertEqual(self.view(surface="desktop")["status"],"no_records")
        self.assertEqual(self.view(row_id=records[0].to_dict()["row_id"])["returned_records"],1)

    def test_old_telemetry_does_not_invent_provenance(self):
        row=self.prepare().to_dict()
        row["data"].pop("policy_provenance")
        row["row_id"]=secrets.token_hex(16)
        self.log.append(TelemetryRecord(json.dumps(row)))
        item=self.view(row_id=row["row_id"])["records"][0]
        self.assertEqual(item["policy_provenance"],"unknown_not_recorded")
        self.assertEqual(item["catalog"]["status"],"recorded_snapshot")

    def test_unknown_catalog_provenance_and_evidence_are_not_echoed(self):
        self.adapter.profile=replace(self.adapter.profile,catalog=type(self.adapter.profile.catalog)(tuple(
            replace(r,mapping_provenance="PRIVATE_SOURCE",mapping_evidence="PRIVATE_EVIDENCE")
            for r in self.adapter.profile.catalog.records)))
        record=self.prepare()
        report=self.view(row_id=record.to_dict()["row_id"])
        item=report["records"][0]
        self.assertEqual(item["catalog"]["matched_mappings"][0]["mapping_provenance"],"unrecognized_source")
        self.assertNotIn("PRIVATE",json.dumps(report))

    def test_children_are_not_joined_to_routes_by_scope_or_time(self):
        self.prepare()
        for name in ("SubagentStart","SubagentStop"):
            event=self.event()
            event.update(hook_event_name=name,agent_id="PRIVATE_CHILD",effort={"level":"medium"},model="claude-opus-5-5")
            self.adapter.handle(event)
        report=self.view()
        self.assertEqual(report["execution_correlation"],"unverified_no_parent_tool_to_child_join")
        children=[i for i in report["records"] if i["record"]["source"].startswith("Subagent")]
        self.assertEqual(len(children),2)
        for item in children:
            self.assertIsNone(item["record"]["data"]["actual_model"])
            self.assertEqual(item["record"]["data"]["correlation"],"unverified")
            self.assertNotIn("catalog",item)
        self.assertEqual(children[-1]["record"]["data"]["actual_effort"],"medium")
        self.assertEqual(children[-1]["record"]["data"]["actual_execution"],"reported_by_host")
        self.assertNotIn("PRIVATE",json.dumps(report))

    def test_multiple_tool_mappings_are_explicitly_ambiguous_not_guessed(self):
        record=self.adapter.profile.catalog.records[0]
        self.adapter.profile=replace(self.adapter.profile,catalog=type(self.adapter.profile.catalog)(
            self.adapter.profile.catalog.records+(replace(record,tool_name="Task"),)))
        row=self.prepare()
        catalog=self.view(row_id=row.to_dict()["row_id"])["records"][0]["catalog"]
        self.assertEqual(catalog["mapping_identity"],"ambiguous")
        self.assertEqual({r["tool_name"] for r in catalog["matched_mappings"]},{"Agent","Task"})

    def test_concurrent_writer_and_explain_reads_remain_parsable(self):
        def write(index):
            event=self.event();event["tool_use_id"]=str(index)
            self.adapter.handle(event)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(write,i) for i in range(10)]
            for _ in range(10):
                report=self.view(limit=5)
                self.assertEqual(report["external_calls"],0)
                self.assertFalse(report["state_modified"])
                self.assertIn(report["status"],("no_records","explained"))
                json.dumps(report,allow_nan=False)
            for future in futures:future.result()
        self.assertEqual(len(self.calls),10)
        report=self.view(limit=50)
        self.assertEqual(len([r for r in report["records"] if r["record"]["source"]=="assessment"]),10)

    def test_invalid_selection_rejected_before_read(self):
        with patch.object(self.store,"_open_root",side_effect=AssertionError("must not read")):
            for change in ({"limit":0},{"limit":True},{"limit":51},{"row_id":"PRIVATE"},{"runtime":"PRIVATE"}):
                with self.subTest(change=change),self.assertRaises(ExplainError) as error:
                    self.view(**change)
                self.assertEqual(str(error.exception),"invalid_explain_selection")
            with self.assertRaises(ExplainError):
                explain_history(self.store,"PRIVATE_SCOPE")
        self.assertFalse(self.root.exists())

    def test_public_root_symlink_log_and_missing_lock_are_not_repaired(self):
        self.prepare()
        log=self.root/"telemetry.jsonl"
        outside=Path(self.project)/"PRIVATE_KEY_FILE"
        outside.write_text("PRIVATE_SECRET")
        log.unlink();log.symlink_to(outside)
        with self.assertRaises(ExplainError) as error:self.view()
        self.assertEqual(str(error.exception),"explain_unavailable")
        self.assertEqual(outside.read_text(),"PRIVATE_SECRET")
        self.assertTrue(log.is_symlink())
        log.unlink()
        (self.root/"state.lock").unlink()
        with self.assertRaises(ExplainError):self.view()
        self.assertFalse((self.root/"state.lock").exists())
        self.root.chmod(0o755)
        with self.assertRaises(ExplainError):self.view()
        self.assertEqual(self.root.stat().st_mode & 0o777,0o755)

    def test_unsafe_snapshot_file_does_not_expose_key_or_hide_decision(self):
        record=self.prepare()
        outside=Path(self.project)/"PRIVATE_KEY_FILE";outside.write_text("PRIVATE_SECRET")
        state=self.root/"state.json";state.unlink();state.symlink_to(outside)
        report=self.view(row_id=record.to_dict()["row_id"])
        self.assertEqual(report["records"][0]["catalog"]["status"],"unavailable")
        self.assertNotIn("PRIVATE",json.dumps(report))
        self.assertTrue(state.is_symlink())
        self.assertEqual(outside.read_text(),"PRIVATE_SECRET")

    def test_conflicting_duplicate_row_ids_are_corruption_not_arbitrarily_selected(self):
        row=self.prepare().to_dict()
        raw=(TelemetryRecord(json.dumps(row)).encoded+"\n").encode("ascii")
        archive=self.root/"telemetry.1.jsonl"
        archive.write_bytes(raw);archive.chmod(0o600)
        self.assertEqual(len([r for r in self.log.read() if r.to_dict()["row_id"]==row["row_id"]]),1)
        row["data"]["confidence"]=.5
        archive.write_text(TelemetryRecord(json.dumps(row)).encoded+"\n")
        before=self.tree()
        with self.assertRaises(ExplainError):self.view()
        self.assertEqual(self.tree(),before)

    def test_shared_lock_timeout_is_bounded_and_no_fallback_writer(self):
        self.prepare()
        before=self.tree()
        fd=os.open(self.root/"state.lock",os.O_RDONLY)
        self.store.lock_wait_seconds=0
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(ExplainError):self.view()
        finally:os.close(fd)
        self.assertEqual(self.tree(),before)

    def test_snapshot_batch_input_and_missing_root_are_read_only(self):
        self.assertEqual(self.store.read_snapshots(self.scope_hash,{"a"*64}),{"a"*64:None})
        self.assertFalse(self.root.exists())
        for scope,refs in (("PRIVATE",{"a"*64}),(self.scope_hash,{"PRIVATE"}),(self.scope_hash,["a"*64]*51)):
            with self.assertRaises(StateError):self.store.read_snapshots(scope,refs)
        self.assertFalse(self.root.exists())

    def test_cli_never_reads_stdin_runtime_config_key_or_calls_provider(self):
        self.prepare()
        before=self.tree()
        with contextlib.ExitStack() as stack:
            for name in ("load_config","runtime_version","load_private_key","JevClient","discover_codex_models",
                         "read_codex_hooks","binary_identity","load_capability_profile"):
                stack.enter_context(patch("router_core.cli."+name,side_effect=AssertionError("unexpected dependency")))
            stack.enter_context(patch("sys.stdin",None))
            stack.enter_context(patch.dict(os.environ,{"ROUTER_DISABLE":"true","TYPESAFE_API_KEY":"PRIVATE_KEY"}))
            output=stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(main(["explain","--runtime","claude","--session-id","PRIVATE_SESSION",
                "--project",self.project,"--state-dir",str(self.root),"--global-config","/PRIVATE_CONFIG"]),0)
            result=json.loads(output.getvalue())
            self.assertEqual(result["status"],"explained")
            self.assertNotIn("PRIVATE",output.getvalue())
        self.assertEqual(before,self.tree())
        self.assertEqual(len(self.calls),1)

    def test_cli_scope_and_execution_flags_reject_before_store_or_io(self):
        cases=[[],["--runtime","claude","--session-id","PRIVATE_SESSION"],
               ["--scope-hash",self.scope_hash,"--project",self.project],
               ["--scope-hash",self.scope_hash,"--session-id","PRIVATE_SESSION"]]
        cases += [["--scope-hash",self.scope_hash,flag,"/PRIVATE_VALUE"] for flag in ("--runtime-binary","--key-file","--capability-profile")]
        cases += [["--scope-hash",self.scope_hash,flag] for flag in ("--send","--write-profile")]
        with patch("router_core.cli.PrivateStateStore",side_effect=AssertionError("must reject before store")),patch("sys.stdin",None):
            for arguments in cases:
                with self.subTest(arguments=arguments),contextlib.redirect_stderr(io.StringIO()) as stderr,self.assertRaises(SystemExit) as error:
                    main(["explain",*arguments])
                self.assertEqual(error.exception.code,2)
                self.assertNotIn("PRIVATE",stderr.getvalue())
        self.assertFalse(self.root.exists())

    def test_cli_invalid_selector_and_limit_are_sanitized(self):
        for args in (["--scope-hash","PRIVATE"],["--scope-hash",self.scope_hash,"--row-id","PRIVATE"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout,patch("sys.stdin",None):
                self.assertEqual(main(["explain","--state-dir",str(self.root),*args]),2)
                self.assertEqual(json.loads(stdout.getvalue())["reason_code"],"invalid_explain_selection")
                self.assertNotIn("PRIVATE",stdout.getvalue())
        for value in ("0","51","PRIVATE","9"*1000):
            with contextlib.redirect_stderr(io.StringIO()) as stderr,self.assertRaises(SystemExit):
                main(["explain","--scope-hash",self.scope_hash,"--limit",value])
            if len(value)>2:
                self.assertNotIn(value,stderr.getvalue())
        self.assertFalse(self.root.exists())

    def test_reproducible_offline_subprocess_smoke(self):
        from scripts.spikes.explain_offline_smoke import run
        report=run()
        self.assertEqual(report["status"],"passed")
        self.assertTrue(report["state_bytes_modes_inodes_mtimes_unchanged"])
        self.assertEqual(report["seed_classifications"],1)
        self.assertEqual(report["external_provider_calls"],0)
        self.assertEqual(report["native_host_calls"],0)

    def test_real_launcher_offline_no_state_creation(self):
        root=Path(self.project)/"not-created"
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/"scripts/router_cli.py"),
            "explain","--scope-hash",self.scope_hash,"--state-dir",str(root)],
            stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=3,cwd="/tmp")
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)["status"],"no_records")
        self.assertFalse(result.stderr)
        self.assertFalse(root.exists())


if __name__=="__main__":
    unittest.main()

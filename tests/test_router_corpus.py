"""Structural validation for the manually authored RTE035 fixture corpus.

These checks protect corpus shape and provenance; they do not assert that a
router currently matches the expectations or that any task succeeded.
"""
import json
import re
import unittest
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "fixtures" / "intelligent-router" / "representative-corpus.json"
VALID_TIERS = {"T0", "T1", "T2", "T3"}
VALID_RISKS = {"low", "medium", "high"}
VALID_EFFORTS = {"low", "medium", "high"}
VALID_RUNTIMES = {"claude", "codex", "both"}
VALID_BOUNDARY = {"NEW_TASK", "CONTINUATION", "UNKNOWN"}


def evaluate_boundaries(corpus=None):
    """Return plan-vs-current boundary mismatches without requiring zero.

    Translation is intentionally direct: each JSON sequence gets one scoped
    BoundaryState; event kind, timestamp, event_id, turn_id, task_id,
    linked_task_id, prompt, and trusted_native map to their same-named core
    fields. Missing IDs remain None. This is a diagnostic, not a release gate.
    """
    from router_core.boundary import (
        BoundaryEvent,
        BoundaryScope,
        Lifecycle,
        initial_state,
        transition,
    )

    if corpus is None:
        corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    mismatches = []
    event_count = 0
    for sequence in corpus["boundary_sequences"]:
        scope = BoundaryScope(sequence["runtime"], "fixture-project", sequence["id"])
        state = initial_state(scope)
        for event in sequence["events"]:
            translated = BoundaryEvent(
                scope=scope,
                kind=Lifecycle(event["kind"].lower()),
                timestamp=event["timestamp_seconds"],
                event_id=event.get("event_id"),
                turn_id=event.get("turn_id"),
                task_id=event.get("task_id"),
                linked_task_id=event.get("linked_task_id"),
                prompt=event["prompt"],
                trusted_native=event.get("trusted_native", False),
            )
            result = transition(state, translated)
            event_count += 1
            expected = event["expected_class"].lower()
            actual = result.classification.value
            if expected != actual:
                mismatches.append({
                    "sequence_id": sequence["id"],
                    "sequence_title": sequence["title"],
                    "record_id": event["record_id"],
                    "event_id": event.get("event_id"),
                    "turn_id": event.get("turn_id"),
                    "kind": event["kind"],
                    "prompt": event["prompt"],
                    "expected": event["expected_class"],
                    "actual": actual.upper(),
                    "reason": result.reason,
                })
            state = result.state
    return {"event_count": event_count, "mismatch_count": len(mismatches), "mismatches": mismatches}


class RepresentativeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CORPUS_PATH.read_text(encoding="utf-8")
        cls.data = json.loads(cls.raw)

    def test_provenance_disclaims_dataset_and_benchmark_claims(self):
        self.assertEqual(self.data["schema_version"], "rte035.v1")
        provenance = self.data["provenance"]
        self.assertTrue(provenance["real_project_content"] is False)
        self.assertTrue(provenance["actual_success_dataset"] is False)
        self.assertTrue(provenance["provider_calls"] is False)
        self.assertTrue(provenance["benchmark_claim"] is False)
        self.assertIn("do not change labels", provenance["labeling_policy"])

    def test_at_least_sixty_distinct_task_scenarios_with_required_labels(self):
        tasks = self.data["task_cases"]
        self.assertGreaterEqual(len(tasks), 60)
        ids = [item["id"] for item in tasks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["TASK-%03d" % n for n in range(1, len(ids) + 1)])
        self.assertEqual(len({item["title"] for item in tasks}), len(tasks))
        self.assertGreaterEqual(len({item["description"] for item in tasks}), 60)
        for item in tasks:
            with self.subTest(task=item["id"]):
                self.assertTrue(item["title"].strip())
                self.assertTrue(item["description"].strip())
                self.assertIn("Manually authored synthetic", item["provenance"])
                expectation = item["expectation"]
                self.assertIn(expectation["tier"], VALID_TIERS)
                self.assertIn(expectation["risk"], VALID_RISKS)
                self.assertIsInstance(expectation["reasoning"], (int, float))
                self.assertGreaterEqual(expectation["reasoning"], 0)
                self.assertLessEqual(expectation["reasoning"], 1)
                self.assertIn(expectation["effort"], VALID_EFFORTS)
                self.assertIsInstance(expectation["pins"], dict)
                self.assertIn(expectation["runtime_applicability"], VALID_RUNTIMES)
                self.assertTrue(expectation["rationale"])
                self.assertTrue(item["outcome_verification"]["notes"])
                self.assertTrue(item["outcome_verification"]["provenance"])

    def test_task_coverage_includes_complexity_risk_pins_and_unknowns(self):
        tasks = self.data["task_cases"]
        tiers = {t["expectation"]["tier"] for t in tasks}
        risks = {t["expectation"]["risk"] for t in tasks}
        runtimes = {t["expectation"]["runtime_applicability"] for t in tasks}
        self.assertTrue({"T0", "T1", "T2", "T3"}.issubset(tiers))
        self.assertEqual(risks, VALID_RISKS)
        self.assertTrue({"claude", "codex", "both"}.issubset(runtimes))
        self.assertTrue(any(t["expectation"]["risk"] == "high" and len(t["description"]) < 150 for t in tasks),
                        "include short high-risk tasks")
        self.assertTrue(any(t["expectation"]["risk"] == "high" and any(k in (t["title"] + t["description"]).lower() for k in ("security", "authorization", "path traversal", "refund", "payment", "financial")) for t in tasks))
        self.assertTrue(any(t["expectation"]["pins"].get("model") for t in tasks))
        self.assertTrue(any(t["expectation"]["pins"].get("reasoning_effort") for t in tasks))
        self.assertTrue(any(t["expectation"]["pins"].get("agent_type") for t in tasks))
        self.assertTrue(any("catalog" in (t["title"] + t["description"]).lower() for t in tasks))
        self.assertTrue(any("malformed" in (t["title"] + t["description"]).lower() for t in tasks))
        self.assertTrue(any("efficiency" in (t["title"] + t["description"]).lower() or "cache" in t["title"].lower() for t in tasks))

    def test_at_least_thirty_multiturn_sequences_cover_boundary_edges(self):
        sequences = self.data["boundary_sequences"]
        self.assertGreaterEqual(len(sequences), 30)
        sequence_ids = [s["id"] for s in sequences]
        self.assertEqual(len(sequence_ids), len(set(sequence_ids)))
        self.assertEqual(sequence_ids, ["BOUNDARY-%02d" % n for n in range(1, len(sequence_ids) + 1)])
        all_event_ids = []
        all_record_ids = []
        for seq in sequences:
            with self.subTest(sequence=seq["id"]):
                self.assertTrue(seq["title"])
                self.assertIn(seq["runtime"], {"claude", "codex"})
                self.assertGreaterEqual(len(seq["events"]), 1)
                self.assertGreaterEqual(sum(e["kind"] == "USER_PROMPT" for e in seq["events"]), 2,
                                        "a multi-turn sequence needs two user prompts, not just lifecycle records")
                self.assertIn("not current-code behavior", seq["provenance"])
                last_ts = -1
                for event in seq["events"]:
                    all_event_ids.append(event["event_id"])
                    self.assertTrue(event["record_id"])
                    all_record_ids.append(event["record_id"])
                    self.assertIn(event["kind"], {"USER_PROMPT", "PREFLIGHT", "TASK_CREATED", "TASK_COMPLETED", "SUBAGENT_SPAWN", "TOOL_ACTIVITY", "STOP", "SESSION_START", "RESUME", "COMPACTION", "SESSION_END"})
                    self.assertIn(event["expected_class"], VALID_BOUNDARY)
                    self.assertGreater(event["timestamp_seconds"], last_ts)
                    last_ts = event["timestamp_seconds"]
        labels = {e["expected_class"] for s in sequences for e in s["events"]}
        self.assertEqual(labels, VALID_BOUNDARY)
        self.assertGreaterEqual(len({s["runtime"] for s in sequences}), 2)
        self.assertEqual(len(all_record_ids), len(set(all_record_ids)))
        # Duplicate event IDs are intentional in two dedicated replay sequences.
        event_ids = [event_id for event_id in all_event_ids if event_id is not None]
        self.assertLess(len(set(event_ids)), len(event_ids))
        missing_identity = next(s for s in sequences if s["title"] == "Event identity missing")
        self.assertIsNone(missing_identity["events"][0]["event_id"])
        self.assertIsNone(missing_identity["events"][0].get("turn_id"))
        self.assertIn("Portuguese", " ".join(s["title"] for s in sequences))
        self.assertTrue(any("/new-task" in e["prompt"] for s in sequences for e in s["events"]))
        self.assertTrue(any(e["kind"] == "TASK_CREATED" and e.get("trusted_native") and e.get("task_id") for s in sequences for e in s["events"]))
        self.assertTrue(any(s["title"] == "Two native children share one root turn" and len({e["task_id"] for e in s["events"] if e.get("task_id")}) == 2 for s in sequences))
        self.assertTrue(any(s["title"] == "TTL expires evidence, not novelty" and max(e["timestamp_seconds"] for e in s["events"]) > 1800 for s in sequences))

    def test_boundary_evaluator_returns_structured_diagnostics_without_zero_gate(self):
        report = evaluate_boundaries(self.data)
        self.assertEqual(report["event_count"], sum(len(s["events"]) for s in self.data["boundary_sequences"]))
        self.assertEqual(report["mismatch_count"], len(report["mismatches"]))
        for mismatch in report["mismatches"]:
            self.assertTrue(mismatch["sequence_id"])
            self.assertTrue(mismatch["record_id"])
            self.assertIn(mismatch["expected"], {"NEW_TASK", "CONTINUATION", "UNKNOWN"})
            self.assertIn(mismatch["actual"], {"NEW_TASK", "CONTINUATION", "UNKNOWN"})
            self.assertNotEqual(mismatch["expected"], mismatch["actual"])
            self.assertTrue(mismatch["reason"])

    def test_artifact_contains_no_secret_shapes_or_real_repository_paths(self):
        # Fail closed on common credential/path shapes; generic words like
        # "token" and fictional fixture identifiers are permitted.
        patterns = [
            r"\bsk-[A-Za-z0-9_-]{16,}\b",
            r"\bAKIA[0-9A-Z]{16}\b",
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"(?i)(?:api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9/+=_-]{24,}",
            r"/Users/[A-Za-z0-9._-]+/Documents/",
            r"/home/[A-Za-z0-9._-]+/",
        ]
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, self.raw), "secret/path-shaped content matched: " + pattern)
        forbidden_project_terms = ("model-router-hook", "flood-surge-claims", "edtech-project", "cognition-happyrobot")
        lowered = self.raw.lower()
        for term in forbidden_project_terms:
            self.assertNotIn(term, lowered)
        self.assertNotIn("/Users/", self.raw)


if __name__ == "__main__":
    unittest.main()

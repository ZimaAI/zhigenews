import copy
import unittest

from zhigenews.evaluation import (
    EvaluationInputError,
    evaluate_dataset,
    evaluate_record,
    freeze_dataset,
    rule_scores,
)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.article = dict(id="synthetic-news", title="Synthetic report", source="fixture", url="https://example.com/report", publishedAt="2026-09-18T07:00:00Z", citations=[{"url": "https://example.com/report"}])
        self.case = dict(id="synthetic-case", revision=1, name="Synthetic case", preference="Agent", expected="Cited evidence", preferenceSnapshot={"version": 0, "role": "Agent", "topics": [], "keywords": []}, fixedAt="2026-09-18T08:00:00Z", sourceSnapshotIds=["snapshot-1"])
        self.snapshots = {"snapshot-1": [self.article]}

    def dataset(self):
        return freeze_dataset([self.case], self.snapshots)

    def run_evaluation(self, **kwargs):
        return evaluate_dataset(self.dataset(), evaluation_id="eval-1", name="Synthetic experiment", config_version="v1", model_id="model-1", generate=lambda _: {"items": [self.article]}, **kwargs)

    def test_dataset_is_stable_and_copies_case_and_source_revisions(self):
        frozen = self.dataset()
        self.assertEqual(frozen.version, self.dataset().version)
        self.case["preference"] = "different"
        self.snapshots["snapshot-1"][0]["title"] = "changed"
        self.assertEqual(frozen.cases[0]["preference"], "Agent")
        self.assertEqual(frozen.cases[0]["evidence"][0]["title"], "Synthetic report")
        self.assertNotEqual(frozen.version, self.dataset().version)

    def test_empty_dataset_and_missing_snapshot_are_not_live_fallbacks(self):
        with self.assertRaisesRegex(EvaluationInputError, "EMPTY_DATASET"):
            freeze_dataset([], {})
        with self.assertRaisesRegex(EvaluationInputError, "MISSING_SNAPSHOT"):
            freeze_dataset([self.case], {})
        self.case["sourceSnapshotIds"] = []
        self.assertEqual(self.dataset().cases[0]["evidence"], [])

    def test_rules_use_fixed_clock_and_detect_unknown_dates_duplicates_and_bad_citations(self):
        valid = copy.deepcopy(self.article)
        old = {**self.article, "url": "https://example.com/other", "publishedAt": None, "citations": [{"url": "https://evil.example/unfounded"}]}
        scores = {row["metric"]: row for row in rule_scores(self.dataset().cases[0], [valid, old])}
        self.assertEqual(scores["freshness"]["value"], 50)
        self.assertEqual(scores["deduplication"]["value"], 50)
        self.assertEqual(scores["citationAccuracy"]["value"], 50)
        self.assertFalse(scores["citationAccuracy"]["passed"])
        self.assertEqual(valid["publishedAt"], "2026-09-18T07:00:00Z")

    def test_missing_judge_keeps_llm_and_cost_metrics_unknown(self):
        result = self.run_evaluation()
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["relevance"])
        self.assertIsNone(result["faithfulness"])
        self.assertIsNone(result["cost"])
        self.assertEqual(result["citations"], 100)
        self.assertEqual(result["datasetVersion"], self.dataset().version)

    def test_judge_failure_does_not_fabricate_score_or_expose_secret(self):
        def judge(*_):
            raise RuntimeError("provider failure secret-token-123")
        result = self.run_evaluation(judge=judge)
        self.assertIsNone(result["relevance"])
        self.assertNotIn("secret-token", str(result))
        self.assertTrue(any(score["error"] == "JUDGE_UNAVAILABLE" for score in result["results"][0]["scores"]))

    def test_invalid_judge_values_do_not_become_real_scores(self):
        result = self.run_evaluation(judge=lambda *_: {"relevance": float("nan"), "faithfulness": 6})
        self.assertIsNone(result["relevance"])
        self.assertIsNone(result["faithfulness"])

    def test_generator_failure_is_not_zero_or_published_success(self):
        def generate(_):
            raise RuntimeError("failed")
        result = evaluate_dataset(self.dataset(), evaluation_id="eval-1", name="Synthetic", config_version="v1", model_id="model-1", generate=generate)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["citations"])
        self.assertIsNone(result["cost"])
        self.assertEqual(result["results"][0]["status"], "failed")

    def test_empty_output_has_no_measured_accuracy(self):
        result = evaluate_dataset(self.dataset(), evaluation_id="eval-1", name="Synthetic", config_version="v1", model_id="model-1", generate=lambda _: {"items": []})
        self.assertIsNone(result["citations"])
        self.assertIsNone(result["relevance"])

    def test_record_adapter_rejects_changed_persisted_dataset(self):
        record = dict(id="eval-1", name="Synthetic", configVersion="v1", modelId="provider-model", datasetVersion=self.dataset().version, snapshot={"cases": [self.case], "sources": self.snapshots})
        result = evaluate_record(record, {"modelId": "model-1"}, generate=lambda _: {"items": [self.article], "cost": 0.01}, judge=lambda *_: {"relevance": 4, "faithfulness": 5, "cost": 0.02})
        self.assertAlmostEqual(result["cost"], 0.03)
        self.assertEqual(result["modelId"], "provider-model")
        self.assertNotIn("snapshot", result)
        self.case["revision"] = 2
        with self.assertRaisesRegex(EvaluationInputError, "DATASET_CHANGED"):
            evaluate_record(record, {"modelId": "model-1"}, generate=lambda _: {"items": []})


if __name__ == "__main__":
    unittest.main()

"""Testes dos módulos de avaliação (metrics, explanation_quality, runlog) e progress."""

import json
from pathlib import Path

from src.evaluation import metrics as MET
from src.evaluation import explanation_quality as EQ
from src.evaluation import runlog as RL
from src.utils.progress import format_duration, ProgressTracker


class TestMetrics:
    def test_canonical_and_threat(self):
        assert MET.canonical("normal") == "Benign"
        assert MET.canonical("C2") == "Botnet"
        assert MET.canonical("ddos") == "DDoS"
        assert not MET.is_threat("Benign")
        assert MET.is_threat("DoS")

    def test_compute_metrics_perfect(self):
        recs = [
            {"attack_type": "DDoS", "ground_truth": "DDoS", "confidence": 0.9, "elapsed_seconds": 1},
            {"attack_type": "Benign", "ground_truth": "Benign", "confidence": 0.9, "elapsed_seconds": 1},
        ]
        m = MET.compute_metrics(recs)
        assert m["n_scored"] == 2
        assert m["accuracy_exact"] == 1.0
        assert m["binary"]["accuracy"] == 1.0
        assert m["binary"]["confusion"] == {"tp": 1, "tn": 1, "fp": 0, "fn": 0}

    def test_compute_metrics_counts_fp_fn(self):
        recs = [
            {"attack_type": "DDoS", "ground_truth": "Benign"},   # FP
            {"attack_type": "Benign", "ground_truth": "DoS"},    # FN
        ]
        m = MET.compute_metrics(recs)
        c = m["binary"]["confusion"]
        assert c == {"tp": 0, "tn": 0, "fp": 1, "fn": 1}

    def test_empty(self):
        assert MET.compute_metrics([])["n_scored"] == 0


class TestExplanationQuality:
    def test_valid_mitre_explanation_scores_high(self):
        rec = {
            "attack_type": "DDoS", "severity": "high", "confidence": 0.9,
            "explanation": "Fluxo TCP com FLOOD de pacotes SYN, taxa muito alta — DDoS volumétrico.",
            "recommendations": ["rate limiting"],
            "record_description": "Fluxo TCP FLOOD SYN taxa alta",
            "mitre_techniques": ["T1498"], "retrieved_context_titles": ["T1498 Network DoS"],
        }
        s = EQ.score_record(rec, valid_mitre={"T1498"})
        assert s["mitre_validity"] == 1.0
        assert s["composite"] > 0.7

    def test_invalid_mitre_detected(self):
        rec = {
            "attack_type": "DoS", "severity": "high", "confidence": 0.8,
            "explanation": "Ataque DoS com técnica T9999 inexistente.",
            "recommendations": [], "record_description": "fluxo dos",
            "mitre_techniques": ["T9999"], "retrieved_context_titles": [],
        }
        s = EQ.score_record(rec, valid_mitre={"T1498"})
        assert "T9999" in s["mitre_invalid"]
        assert s["mitre_validity"] == 0.0

    def test_evaluate_skips_prefiltered(self):
        recs = [
            {"explanation": "", "stage_skipped": "rf_prefilter"},
            {"explanation": "Ataque DoS volumétrico real.", "attack_type": "DoS",
             "severity": "high", "confidence": 0.8, "record_description": "dos",
             "mitre_techniques": [], "recommendations": ["x"]},
        ]
        rep = EQ.evaluate_results(recs)
        assert rep["n_explained"] == 1


class TestRunlog:
    def test_config_slug(self):
        assert RL.config_slug({"use_rag": False}) == "norag"
        assert RL.config_slug({"use_rag": True, "use_rerank": True}) == "rag-rerank"
        assert RL.config_slug({"use_rag": True, "use_rerank": True, "use_rf": True}) == "rag-rerank-rf"
        assert RL.config_slug({"use_rag": True, "use_rerank": True, "use_rf": True,
                               "two_stage": True}) == "rag-rerank-rf-2stage"

    def test_save_run_writes_schema_and_manifest(self, tmp_path):
        recs = [{"attack_type": "DoS", "ground_truth": "DoS", "confidence": 0.8,
                 "elapsed_seconds": 1, "explanation": "DoS real", "severity": "high",
                 "record_description": "dos", "mitre_techniques": [], "recommendations": ["x"]}]
        run_dir = RL.make_run_dir(tmp_path, "cic", "rag", 1, 7, "20260101_000000")
        assert run_dir.name == "run_20260101_000000_cic_rag_n1_seed7"
        meta = {"id": run_dir.name, "timestamp": "t", "config": "rag", "dataset": "cic",
                "n_records": 1, "seed": 7, "model": "m", "flags": {"use_rag": True}}
        manifest = tmp_path / "runs_index.jsonl"
        summary = RL.save_run(recs, meta, run_dir, manifest_path=manifest,
                              with_explanation_quality=False)
        assert summary["accuracy_binary"] == 1.0
        payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        assert payload["schema_version"] == RL.SCHEMA_VERSION
        assert set(payload.keys()) >= {"run", "summary", "metrics", "records"}
        # manifesto é JSONL legível por pandas
        lines = manifest.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["run_id"] == run_dir.name


class TestProgress:
    def test_format_duration(self):
        assert format_duration(5) == "5s"
        assert format_duration(75) == "1m 15s"
        assert format_duration(3700) == "1h 01m"

    def test_tracker_advances(self):
        msgs = []
        prog = ProgressTracker(total=2, printer=msgs.append)
        prog.start_step("a"); prog.end_step()
        prog.start_step("b"); prog.end_step()
        prog.finish()
        assert prog.done == 2
        assert any("100.0%" in m for m in msgs)

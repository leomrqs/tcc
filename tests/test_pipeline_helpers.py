"""Testes das funções auxiliares do llm/pipeline."""

import pandas as pd
import pytest

from src.llm.pipeline import _matches_label, select_records


class TestMatchesLabel:
    def test_exact_match(self):
        assert _matches_label("DDoS", "DDoS")

    def test_case_insensitive(self):
        assert _matches_label("ddos", "DDoS")
        assert _matches_label("DDoS", "ddos")

    def test_benign_normal_alias(self):
        assert _matches_label("Benign", "Normal")
        assert _matches_label("Normal", "Benign")

    def test_brute_force_alias(self):
        assert _matches_label("Brute Force", "brute-force")
        assert _matches_label("bruteforce", "Brute Force")

    def test_web_attack_alias(self):
        assert _matches_label("Web Attack", "webattack")

    def test_no_match(self):
        assert not _matches_label("DDoS", "DoS")
        assert not _matches_label("Benign", "Botnet")

    def test_empty_strings(self):
        assert not _matches_label("", "DDoS")
        assert not _matches_label("DDoS", "")
        assert not _matches_label("", "")

    def test_none_values(self):
        assert not _matches_label(None, "DDoS")
        assert not _matches_label("DDoS", None)


class TestSelectRecords:
    def _make_df(self, n=100):
        import numpy as np
        labels = ["Benign"] * 50 + ["DDoS"] * 30 + ["DoS"] * 20
        return pd.DataFrame({
            "label": labels[:n],
            "feature_a": np.random.rand(n),
        })

    def test_returns_correct_count(self):
        df = self._make_df(100)
        result = select_records(df, n=10)
        assert len(result) == 10

    def test_stratified_covers_classes(self):
        df = self._make_df(100)
        result = select_records(df, n=30, stratified=True)
        classes_found = set(result["label"].unique())
        assert len(classes_found) >= 2

    def test_n_larger_than_df(self):
        df = self._make_df(5)
        result = select_records(df, n=100)
        assert len(result) == 5

    def test_reproducible_with_seed(self):
        df = self._make_df(100)
        r1 = select_records(df, n=10, seed=42)
        r2 = select_records(df, n=10, seed=42)
        assert list(r1.index) == list(r2.index)

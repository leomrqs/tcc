"""Testes do registry de modelos e do ensemble (src/ml/models.py)."""

import numpy as np
import pandas as pd
import pytest

from src.ml import models as M


class TestFeaturePrep:
    def _df(self):
        return pd.DataFrame({
            "f1": [1.0, 2.0, np.inf, 4.0],
            "f2": [0.1, np.nan, 0.3, 0.4],
            "label": ["Benign", "DoS", "Normal", "Exploits"],
            "label_original": ["BENIGN", "Hulk", "Normal", "Exploits"],
            "dataset_source": ["CIC", "CIC", "UNSW", "UNSW"],
        })

    def test_is_benign(self):
        assert M.is_benign("Benign")
        assert M.is_benign("normal")
        assert M.is_benign("BACKGROUND")
        assert not M.is_benign("DoS")
        assert not M.is_benign(None)

    def test_select_numeric_features_excludes_labels(self):
        cols = M.select_numeric_features(self._df())
        assert cols == ["f1", "f2"]

    def test_prepare_xy_cleans_and_binarizes(self):
        X, y, cols = M.prepare_xy(self._df())
        assert cols == ["f1", "f2"]
        # inf e NaN viram 0
        assert np.isfinite(X.values).all()
        assert X.loc[2, "f1"] == 0.0
        assert X.loc[1, "f2"] == 0.0
        # Benign/Normal -> 0, resto -> 1
        assert list(y) == [0, 1, 0, 1]

    def test_prepare_xy_raises_without_numeric(self):
        df = pd.DataFrame({"label": ["Benign"], "dataset_source": ["CIC"]})
        with pytest.raises(ValueError):
            M.prepare_xy(df)


class TestRegistry:
    def test_build_specs_has_core_models(self):
        names = M.available_model_names()
        for expected in ["RandomForest", "ExtraTrees", "HistGradientBoosting",
                         "LogisticRegression", "DecisionTree", "GaussianNB"]:
            assert expected in names

    def test_positive_class_weight(self):
        y = [0, 0, 0, 1]  # 3 neg, 1 pos
        assert M.positive_class_weight(y) == pytest.approx(3.0)
        assert M.positive_class_weight([0, 0]) == 1.0  # sem positivos

    def test_specs_are_fittable(self):
        # treina um modelo rápido de ponta a ponta num dataset minúsculo
        X = pd.DataFrame({"a": range(20), "b": range(20, 40)})
        y = pd.Series([0, 1] * 10)
        spec = next(s for s in M.build_model_specs() if s.name == "DecisionTree")
        model = spec.factory(42, 1.0)
        model.fit(X, y)
        proba = model.predict_proba(X)
        assert proba.shape == (20, 2)


class TestSoftVotingEnsemble:
    def test_averages_member_probabilities(self):
        class Dummy:
            def __init__(self, p):
                self._p = p
            def predict_proba(self, X):
                return np.tile(self._p, (len(X), 1))

        members = [("a", Dummy([0.8, 0.2])), ("b", Dummy([0.4, 0.6]))]
        ens = M.SoftVotingEnsemble(members)
        X = pd.DataFrame({"x": [1, 2, 3]})
        proba = ens.predict_proba(X)
        assert proba.shape == (3, 2)
        np.testing.assert_allclose(proba[0], [0.6, 0.4])
        # média da classe 0 (0.6) > classe 1 -> predição 0
        assert list(ens.predict(X)) == [0, 0, 0]

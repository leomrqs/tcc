"""
Registry de modelos de Machine Learning clássicos para o pré-classificador
binário (Benign vs Threat) e para o estudo comparativo.

Cada dataset (CIC-IDS2017 e UNSW-NB15) tem features diferentes, então os
modelos são treinados separadamente. Este módulo concentra:

- A preparação compartilhada de features (seleção numérica, limpeza de NaN/inf)
- A construção dos estimadores (com scaling embutido via Pipeline nos modelos
  sensíveis à escala, mantendo uma interface uniforme predict_proba sobre
  features brutas)
- A detecção opcional de XGBoost e LightGBM (usados se instalados)

Convenção de classes: 0 = Benign, 1 = Threat. A coluna 0 de predict_proba é
sempre a probabilidade de Benign.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from sklearn.ensemble import (
    RandomForestClassifier,
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Detecção opcional de boosters externos (gold standard, usados se disponíveis)
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False


# Preparação de features

_BENIGN_LABELS = {"benign", "normal", "background"}
_DROP_COLUMNS = {"label", "label_original", "dataset_source"}


def is_benign(label) -> bool:
    """True se o rótulo pertence à classe benigna (Benign/Normal/Background)."""
    return label is not None and str(label).strip().lower() in _BENIGN_LABELS


def select_numeric_features(df: pd.DataFrame) -> list[str]:
    """Colunas numéricas do DataFrame, exceto rótulos e metadados."""
    return [
        col for col in df.columns
        if col not in _DROP_COLUMNS and pd.api.types.is_numeric_dtype(df[col])
    ]


def prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """
    Converte o DataFrame em (X, y, feature_cols) prontos para treino.

    X: features numéricas com NaN/inf substituídos por 0.
    y: rótulo binário (0 = Benign, 1 = Threat).
    """
    feature_cols = select_numeric_features(df)
    if not feature_cols:
        raise ValueError("Nenhuma coluna numérica encontrada para treino")
    X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = df["label"].apply(lambda lbl: 0 if is_benign(lbl) else 1)
    return X, y, feature_cols


# Registry de modelos

# Metadados por modelo: factory (recebe seed e scale_pos_weight), família e se é
# notoriamente lento (para permitir pular em modos rápidos).
class ModelSpec:
    def __init__(
        self,
        name: str,
        factory: Callable,
        family: str,
        needs_scaling: bool = False,
        slow: bool = False,
    ):
        self.name = name
        self.factory = factory
        self.family = family
        self.needs_scaling = needs_scaling
        self.slow = slow


def _wrap(model, needs_scaling: bool):
    """Embute StandardScaler nos modelos sensíveis à escala."""
    if needs_scaling:
        return Pipeline([("scaler", StandardScaler()), ("clf", model)])
    return model


def build_model_specs() -> list[ModelSpec]:
    """
    Lista ordenada de specs de modelos disponíveis no ambiente atual.

    XGBoost e LightGBM entram automaticamente se as bibliotecas estiverem
    instaladas. A ordem reflete a expectativa de desempenho em features de
    fluxo de rede (ensembles de árvore no topo).
    """
    specs: list[ModelSpec] = [
        ModelSpec(
            "RandomForest",
            lambda seed, spw: RandomForestClassifier(
                n_estimators=200, max_depth=24, n_jobs=-1,
                random_state=seed, class_weight="balanced",
            ),
            family="bagging",
        ),
        ModelSpec(
            "ExtraTrees",
            lambda seed, spw: ExtraTreesClassifier(
                n_estimators=200, max_depth=24, n_jobs=-1,
                random_state=seed, class_weight="balanced",
            ),
            family="bagging",
        ),
        ModelSpec(
            "HistGradientBoosting",
            lambda seed, spw: HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.1, max_depth=None,
                random_state=seed, class_weight="balanced",
            ),
            family="boosting",
        ),
        ModelSpec(
            "DecisionTree",
            lambda seed, spw: DecisionTreeClassifier(
                max_depth=24, random_state=seed, class_weight="balanced",
            ),
            family="tree",
        ),
        ModelSpec(
            "LogisticRegression",
            lambda seed, spw: _wrap(
                LogisticRegression(
                    max_iter=2000, n_jobs=-1, random_state=seed,
                    class_weight="balanced",
                ),
                needs_scaling=True,
            ),
            family="linear",
            needs_scaling=True,
        ),
        ModelSpec(
            "GaussianNB",
            lambda seed, spw: _wrap(GaussianNB(), needs_scaling=True),
            family="probabilistic",
            needs_scaling=True,
        ),
        ModelSpec(
            "KNN",
            lambda seed, spw: _wrap(
                KNeighborsClassifier(n_neighbors=15, n_jobs=-1),
                needs_scaling=True,
            ),
            family="instance",
            needs_scaling=True,
            slow=True,
        ),
        ModelSpec(
            "MLP",
            lambda seed, spw: _wrap(
                MLPClassifier(
                    hidden_layer_sizes=(128, 64), max_iter=80,
                    early_stopping=True, random_state=seed,
                ),
                needs_scaling=True,
            ),
            family="neural",
            needs_scaling=True,
            slow=True,
        ),
    ]

    if HAS_XGB:
        specs.insert(3, ModelSpec(
            "XGBoost",
            lambda seed, spw: XGBClassifier(
                n_estimators=400, max_depth=8, learning_rate=0.1,
                subsample=0.9, colsample_bytree=0.9, tree_method="hist",
                eval_metric="logloss", random_state=seed,
                scale_pos_weight=spw, n_jobs=-1,
            ),
            family="boosting",
        ))
    if HAS_LGBM:
        specs.insert(4, ModelSpec(
            "LightGBM",
            lambda seed, spw: LGBMClassifier(
                n_estimators=400, max_depth=-1, learning_rate=0.1,
                subsample=0.9, colsample_bytree=0.9, random_state=seed,
                class_weight="balanced", n_jobs=-1, verbose=-1,
            ),
            family="boosting",
        ))

    return specs


def positive_class_weight(y) -> float:
    """scale_pos_weight = n_negativos / n_positivos (para XGBoost)."""
    y = np.asarray(y)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    return (n_neg / n_pos) if n_pos > 0 else 1.0


def available_model_names() -> list[str]:
    return [s.name for s in build_model_specs()]


# Ensemble por média de probabilidades (soft voting)

class SoftVotingEnsemble:
    """
    Ensemble que combina modelos JÁ TREINADOS pela média das probabilidades.

    Diferente do VotingClassifier do sklearn, não retreina os membros — reusa
    os estimadores fitados, evitando custo dobrado de treino. Picklável e com a
    mesma interface predict/predict_proba dos demais modelos (0 = Benign).
    """

    def __init__(self, members: list[tuple[str, object]], weights: list[float] | None = None):
        self.members = members
        self.weights = weights
        self.classes_ = np.array([0, 1])
        self.member_names = [name for name, _ in members]

    def predict_proba(self, X) -> np.ndarray:
        probs = [model.predict_proba(X) for _, model in self.members]
        return np.average(np.stack(probs, axis=0), axis=0, weights=self.weights)

    def predict(self, X) -> np.ndarray:
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]

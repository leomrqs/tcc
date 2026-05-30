"""
Pré-classificador binário (Benign vs Threat) usado antes do LLM.

Objetivo: filtrar fluxos benignos óbvios com um modelo clássico rápido, para
que o LLM se concentre nos casos ambíguos. Isso reduz o custo de inferência e
resolve o problema de TN=0 do LLM isolado.

O treino e a comparação de modelos vivem em `src.ml.benchmark`. Este módulo
concentra a INFERÊNCIA em produção (classe PreClassifier) e mantém um atalho de
treino apenas do Random Forest para o caminho rápido documentado no README.

O PreClassifier pode carregar três variantes (uma por dataset):
- "rf"       → Random Forest (rf_<ds>.joblib) — default, compatível com o legado
- "best"     → melhor modelo do benchmark (best_<ds>.joblib)
- "ensemble" → soft-voting dos melhores (ensemble_<ds>.joblib)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src import config
from src.ml import models as M
from src.utils.logger import get_logger

logger = get_logger(__name__)


MODELS_DIR = config.PROJECT_ROOT / "data" / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

CIC_MODEL_PATH = MODELS_DIR / "rf_cic.joblib"
UNSW_MODEL_PATH = MODELS_DIR / "rf_unsw.joblib"
META_PATH = MODELS_DIR / "rf_meta.json"

# Mapeia o nome do dataset (record['dataset_source']) para a chave de arquivo.
_SOURCE_TO_KEY = {"CIC-IDS2017": "cic", "UNSW-NB15": "unsw"}


# Treino (atalho Random Forest)

def train_rf(
    df: pd.DataFrame,
    output_path: Path,
    dataset_name: str,
    sample_size: Optional[int] = None,
    test_fraction: float = 0.2,
    random_state: int = 42,
) -> dict:
    """Treina um Random Forest binário (Benign vs Threat) e persiste em disco."""
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, confusion_matrix,
    )
    import joblib

    if sample_size is not None and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=random_state).reset_index(drop=True)
        logger.info(f"  Subamostra de {len(df):,} registros para treino")

    X, y, feature_cols = M.prepare_xy(df)
    n_benign, n_threat = int((y == 0).sum()), int((y == 1).sum())
    logger.info(f"  Distribuição: {n_benign:,} benign | {n_threat:,} threat")
    if n_benign == 0 or n_threat == 0:
        raise ValueError(f"Dataset não tem ambas as classes (benign={n_benign}, threat={n_threat})")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_fraction, random_state=random_state, stratify=y
    )

    logger.info(f"  Treinando RF ({len(X_train):,} train | {len(X_test):,} test)...")
    rf_spec = next(s for s in M.build_model_specs() if s.name == "RandomForest")
    clf = rf_spec.factory(random_state, M.positive_class_weight(y_train))
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred).tolist()

    benign_mask = y_test == 0
    benign_high_conf = float((y_prob[benign_mask, 0] >= 0.95).mean()) if benign_mask.any() else 0.0
    threat_mask = y_test == 1
    threat_misclass_high_conf = float((y_prob[threat_mask, 0] >= 0.95).mean()) if threat_mask.any() else 0.0

    logger.info(f"  Acurácia (holdout): {acc:.4f}")
    logger.info(f"  Precisão: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f}")
    logger.info(f"  Cobertura Benign com conf>=0.95: {benign_high_conf:.1%}")
    logger.info(f"  Risco — Threats classificados Benign com conf>=0.95: {threat_misclass_high_conf:.2%}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": clf, "feature_cols": feature_cols, "model_name": "RandomForest",
                 "dataset": dataset_name}, output_path)
    logger.info(f"  Modelo salvo em {output_path}")

    return {
        "dataset": dataset_name,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": acc,
        "precision_threat": prec,
        "recall_threat": rec,
        "f1_threat": f1,
        "benign_high_confidence_coverage": benign_high_conf,
        "threat_misclassified_high_conf": threat_misclass_high_conf,
        "confusion_matrix": cm,
        "feature_count": len(feature_cols),
    }


def train_all(sample_size: Optional[int] = 200_000) -> dict:
    """Treina RFs para CIC e UNSW separadamente."""
    all_metrics = {}
    for key, path, name, out in [
        ("cic", config.CIC_PROCESSED_FILE, "CIC-IDS2017", CIC_MODEL_PATH),
        ("unsw", config.UNSW_PROCESSED_FILE, "UNSW-NB15", UNSW_MODEL_PATH),
    ]:
        if not path.exists():
            logger.warning(f"{name} parquet não encontrado em {path}")
            continue
        logger.info("=" * 60)
        logger.info(f"TREINANDO RF — {name}")
        logger.info("=" * 60)
        df = pd.read_parquet(path)
        df["dataset_source"] = name
        all_metrics[key] = train_rf(df, out, key, sample_size=sample_size)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)
    logger.info(f"Metadata salvo em {META_PATH}")
    return all_metrics


# Inferência

class PreClassifier:
    """
    Carrega os modelos binários (um por dataset) e roteia a predição com base em
    record['dataset_source']. A variante é escolhida por `model_kind`.
    """

    def __init__(self, model_kind: str = "rf"):
        import joblib
        self.model_kind = model_kind
        self._models = {}
        for source, key in _SOURCE_TO_KEY.items():
            path = MODELS_DIR / f"{model_kind}_{key}.joblib"
            if path.exists():
                self._models[source] = joblib.load(path)
                logger.info(f"  Modelo {model_kind} {key.upper()} carregado de {path.name}")
            else:
                logger.warning(
                    f"  Modelo '{model_kind}' para {key.upper()} não encontrado em {path.name} — "
                    f"treine com: python -m src.ml.benchmark"
                )

    def is_ready(self) -> bool:
        return len(self._models) > 0

    def predict(self, record: pd.Series) -> tuple[str, float]:
        """Prediz ('Benign'|'Threat', confidence 0-1) para um registro. ('Unknown', 0.0) se sem modelo."""
        source = record.get("dataset_source", "")
        bundle = self._models.get(source)
        if bundle is None:
            return ("Unknown", 0.0)

        clf = bundle["clf"]
        feature_cols = bundle["feature_cols"]

        x = []
        for col in feature_cols:
            v = record.get(col, 0.0)
            try:
                x.append(float(v) if pd.notna(v) else 0.0)
            except (TypeError, ValueError):
                x.append(0.0)
        X = pd.DataFrame([x], columns=feature_cols)

        prob = clf.predict_proba(X)[0]
        pred_idx = int(np.argmax(prob))
        return ("Benign" if pred_idx == 0 else "Threat", float(prob[pred_idx]))


# CLI

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Treina o atalho Random Forest para CIC e UNSW")
    parser.add_argument("--sample-size", type=int, default=200_000,
                        help="Subamostra por dataset (default 200000, 0 = usar tudo)")
    args = parser.parse_args()

    sample_size = args.sample_size if args.sample_size > 0 else None
    metrics = train_all(sample_size=sample_size)

    print("\n" + "=" * 60)
    print("TREINAMENTO CONCLUÍDO")
    print("=" * 60)
    for ds, m in metrics.items():
        print(f"\n[{ds.upper()}]")
        print(f"  Acurácia:                  {m['accuracy']:.4f}")
        print(f"  F1 (threat):               {m['f1_threat']:.4f}")
        print(f"  Cobertura Benign conf>=95%: {m['benign_high_confidence_coverage']:.1%}")
        print(f"  Risco threats->benign 95%: {m['threat_misclassified_high_conf']:.2%}")
    print("\nPara o estudo comparativo completo: python -m src.ml.benchmark")


if __name__ == "__main__":
    main()

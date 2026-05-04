"""
Pre-classificador Random Forest para filtrar Benign de alta confiança
antes do LLM.

Objetivo: reduzir custo do LLM e melhorar métricas operacionais filtrando
fluxos benignos óbvios. O LLM se concentra nos casos ambíguos.

Estratégia:
- Treina UM RF binário (Benign vs Threat) por dataset (CIC e UNSW separados,
  porque têm features diferentes)
- Usa as features numéricas do parquet, descartando colunas string e label
- Persiste em disco (joblib) para reuso entre runs
- Em inferência, retorna (predição, confiança) — caller decide se confia
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


MODELS_DIR = config.PROJECT_ROOT / "data" / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

CIC_MODEL_PATH = MODELS_DIR / "rf_cic.joblib"
UNSW_MODEL_PATH = MODELS_DIR / "rf_unsw.joblib"
META_PATH = MODELS_DIR / "rf_meta.json"


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

_BENIGN_LABELS = {"benign", "normal", "background"}


def _is_benign(label: str) -> bool:
    return label is not None and str(label).strip().lower() in _BENIGN_LABELS


def _select_numeric_features(df: pd.DataFrame) -> list[str]:
    """Pega colunas numéricas, descarta label e dataset_source."""
    drop = {"label", "label_original", "dataset_source"}
    cols = []
    for col in df.columns:
        if col in drop:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


# ════════════════════════════════════════════════════════════════
# Treinamento
# ════════════════════════════════════════════════════════════════

def train_rf(
    df: pd.DataFrame,
    output_path: Path,
    dataset_name: str,
    sample_size: Optional[int] = None,
    test_fraction: float = 0.2,
    random_state: int = 42,
) -> dict:
    """
    Treina um Random Forest binário (Benign vs Threat).

    Args:
        df: DataFrame com coluna 'label' e features numéricas
        output_path: onde salvar o modelo (joblib)
        dataset_name: "cic" ou "unsw" (para metadata)
        sample_size: se não None, sub-amostra para acelerar treino
        test_fraction: proporção de holdout para validação
        random_state: seed

    Returns:
        Dict com métricas de avaliação no holdout
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        classification_report, confusion_matrix,
    )
    import joblib

    if sample_size is not None and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=random_state).reset_index(drop=True)
        logger.info(f"  Sub-amostra de {len(df):,} registros para treino")

    feature_cols = _select_numeric_features(df)
    if not feature_cols:
        raise ValueError("Nenhuma coluna numérica encontrada para treino")

    X = df[feature_cols].fillna(0.0).replace([np.inf, -np.inf], 0.0)
    y = df["label"].apply(lambda lbl: 0 if _is_benign(lbl) else 1)

    n_benign = int((y == 0).sum())
    n_threat = int((y == 1).sum())
    logger.info(f"  Distribuição: {n_benign:,} benign | {n_threat:,} threat")

    if n_benign == 0 or n_threat == 0:
        raise ValueError(
            f"Dataset não tem ambas as classes (benign={n_benign}, threat={n_threat})"
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_fraction, random_state=random_state, stratify=y
    )

    logger.info(f"  Treinando RF ({len(X_train):,} train | {len(X_test):,} test)...")
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=20,
        n_jobs=-1,
        random_state=random_state,
        class_weight="balanced",  # compensar desbalanceamento
    )
    clf.fit(X_train, y_train)

    # Avaliação
    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred).tolist()

    # Avaliar quanto do conjunto Benign teria conf >= 0.95
    benign_mask = y_test == 0
    benign_high_conf = float(((y_prob[benign_mask, 0] >= 0.95)).mean()) if benign_mask.any() else 0.0
    threat_mask = y_test == 1
    threat_misclass_high_conf = float(((y_prob[threat_mask, 0] >= 0.95)).mean()) if threat_mask.any() else 0.0

    logger.info(f"  Acurácia (holdout): {acc:.4f}")
    logger.info(f"  Precisão: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f}")
    logger.info(f"  Cobertura Benign com conf≥0.95: {benign_high_conf:.1%}")
    logger.info(f"  Risco — Threats classificados Benign com conf≥0.95: {threat_misclass_high_conf:.2%}")
    logger.info(f"  Confusion matrix: {cm}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": clf, "feature_cols": feature_cols}, output_path)
    logger.info(f"  Modelo salvo em {output_path}")

    metrics = {
        "dataset": dataset_name,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_benign_train": int((y_train == 0).sum()),
        "n_threat_train": int((y_train == 1).sum()),
        "accuracy": acc,
        "precision_threat": prec,
        "recall_threat": rec,
        "f1_threat": f1,
        "benign_high_confidence_coverage": benign_high_conf,
        "threat_misclassified_high_conf": threat_misclass_high_conf,
        "confusion_matrix": cm,
        "feature_count": len(feature_cols),
        "n_estimators": 100,
        "max_depth": 20,
    }
    return metrics


def train_all(sample_size: Optional[int] = 200_000) -> dict:
    """
    Treina RFs para CIC e UNSW separadamente.

    Args:
        sample_size: tamanho de amostra para acelerar (default 200K por dataset)

    Returns:
        Dict com métricas dos dois treinamentos.
    """
    all_metrics = {}

    if config.CIC_PROCESSED_FILE.exists():
        logger.info("=" * 60)
        logger.info("TREINANDO RF — CIC-IDS2017")
        logger.info("=" * 60)
        df_cic = pd.read_parquet(config.CIC_PROCESSED_FILE)
        df_cic["dataset_source"] = "CIC-IDS2017"
        all_metrics["cic"] = train_rf(df_cic, CIC_MODEL_PATH, "cic", sample_size=sample_size)
    else:
        logger.warning(f"CIC parquet não encontrado em {config.CIC_PROCESSED_FILE}")

    if config.UNSW_PROCESSED_FILE.exists():
        logger.info("=" * 60)
        logger.info("TREINANDO RF — UNSW-NB15")
        logger.info("=" * 60)
        df_unsw = pd.read_parquet(config.UNSW_PROCESSED_FILE)
        df_unsw["dataset_source"] = "UNSW-NB15"
        all_metrics["unsw"] = train_rf(df_unsw, UNSW_MODEL_PATH, "unsw", sample_size=sample_size)
    else:
        logger.warning(f"UNSW parquet não encontrado em {config.UNSW_PROCESSED_FILE}")

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)
    logger.info(f"Metadata salvo em {META_PATH}")

    return all_metrics


# ════════════════════════════════════════════════════════════════
# Inferência
# ════════════════════════════════════════════════════════════════

class PreClassifier:
    """
    Wrapper de inferência. Carrega modelos CIC e UNSW e roteia
    a predição com base em record['dataset_source'].
    """

    def __init__(self):
        import joblib
        self._models = {}
        if CIC_MODEL_PATH.exists():
            self._models["CIC-IDS2017"] = joblib.load(CIC_MODEL_PATH)
            logger.info(f"  RF CIC carregado de {CIC_MODEL_PATH.name}")
        else:
            logger.warning(f"  RF CIC não encontrado — treine com: python -m src.ml.preclassifier")
        if UNSW_MODEL_PATH.exists():
            self._models["UNSW-NB15"] = joblib.load(UNSW_MODEL_PATH)
            logger.info(f"  RF UNSW carregado de {UNSW_MODEL_PATH.name}")
        else:
            logger.warning(f"  RF UNSW não encontrado — treine com: python -m src.ml.preclassifier")

    def is_ready(self) -> bool:
        return len(self._models) > 0

    def predict(self, record: pd.Series) -> tuple[str, float]:
        """
        Prediz ('Benign' ou 'Threat', confidence 0-1) para um único registro.
        Se o modelo do dataset não estiver carregado, retorna ('Unknown', 0.0).
        """
        source = record.get("dataset_source", "")
        bundle = self._models.get(source)
        if bundle is None:
            return ("Unknown", 0.0)

        clf = bundle["clf"]
        feature_cols = bundle["feature_cols"]

        # Construir vetor de features na ordem do treino
        x = []
        for col in feature_cols:
            v = record.get(col, 0.0)
            try:
                x.append(float(v) if pd.notna(v) else 0.0)
            except (TypeError, ValueError):
                x.append(0.0)
        X = np.asarray([x], dtype=np.float64)
        X[~np.isfinite(X)] = 0.0

        prob = clf.predict_proba(X)[0]
        pred_idx = int(np.argmax(prob))
        confidence = float(prob[pred_idx])
        label = "Benign" if pred_idx == 0 else "Threat"
        return (label, confidence)


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Treina pre-classificadores RF para CIC e UNSW"
    )
    parser.add_argument(
        "--sample-size", type=int, default=200_000,
        help="Sub-amostra por dataset (default 200000, 0 = usar tudo)",
    )
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
        print(f"  Cobertura Benign conf≥95%: {m['benign_high_confidence_coverage']:.1%}")
        print(f"  Risco threats→benign 95%:  {m['threat_misclassified_high_conf']:.2%}")


if __name__ == "__main__":
    main()

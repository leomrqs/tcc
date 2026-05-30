"""
Estudo comparativo de modelos de Machine Learning clássicos para a
classificação binária Benign vs Threat, treinado nos datasets completos
(CIC-IDS2017 e UNSW-NB15).

Diferente do pré-classificador (que treinava apenas um Random Forest), este
módulo treina e compara toda a família de modelos do registry (models.py),
produzindo:

- Métricas no holdout: acurácia, balanced accuracy, precisão, recall, F1,
  ROC-AUC, PR-AUC, matriz de confusão, tempos de treino/inferência
- Cross-validation estratificada (média ± desvio) para significância estatística
- Um ensemble por soft-voting dos melhores modelos
- Modelos persistidos para uso em produção (PreClassifier)
- Gráficos e relatórios (JSON + Markdown) para o manuscrito

Uso:
    python -m src.ml.benchmark                          # ambos, amostra 200k
    python -m src.ml.benchmark --sample-size 0          # datasets completos
    python -m src.ml.benchmark --datasets cic --cv-folds 5
    python -m src.ml.benchmark --no-slow                # pula KNN e MLP
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src import config
from src.ml import models as M
from src.utils.logger import get_logger
from src.utils.progress import ProgressTracker, banner

logger = get_logger(__name__)


MODELS_DIR = config.PROJECT_ROOT / "data" / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
BENCHMARK_DIR = config.OUTPUTS_DIR / "ml_benchmark"

# Modelos que entram no ensemble por soft-voting (os mais fortes em fluxo de rede).
ENSEMBLE_CANDIDATES = ["RandomForest", "ExtraTrees", "HistGradientBoosting", "XGBoost", "LightGBM"]

# Modelos lentos (KNN, MLP) não escalam para milhões de registros — treinam numa
# subamostra estratificada deste tamanho. O holdout de avaliação continua completo.
SLOW_TRAIN_CAP = 100_000

_DATASET_FILES = {
    "cic": (config.CIC_PROCESSED_FILE, "CIC-IDS2017"),
    "unsw": (config.UNSW_PROCESSED_FILE, "UNSW-NB15"),
}


# Avaliação de um modelo

def _evaluate(name: str, model, X_test, y_test, train_time: float) -> tuple[dict, np.ndarray]:
    """Calcula o conjunto completo de métricas no holdout. Retorna (métricas, y_prob_threat)."""
    from sklearn.metrics import (
        accuracy_score, balanced_accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, average_precision_score, confusion_matrix,
    )

    t0 = time.time()
    y_prob = model.predict_proba(X_test)
    predict_time = time.time() - t0
    p_benign = y_prob[:, 0]
    p_threat = y_prob[:, 1]
    y_pred = (p_threat >= 0.5).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[0, 1]).ravel()
    benign_mask = (y_test.values if hasattr(y_test, "values") else y_test) == 0
    threat_mask = ~benign_mask

    metrics = {
        "model": name,
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, y_pred)),
        "precision_threat": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall_threat": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1_threat": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, p_threat)),
        "pr_auc": float(average_precision_score(y_test, p_threat)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "benign_high_confidence_coverage": float((p_benign[benign_mask] >= 0.95).mean()) if benign_mask.any() else 0.0,
        "threat_misclassified_high_conf": float((p_benign[threat_mask] >= 0.95).mean()) if threat_mask.any() else 0.0,
        "train_time_s": round(train_time, 2),
        "predict_time_s": round(predict_time, 3),
        "predict_ms_per_1k": round(1000 * predict_time / max(len(X_test), 1) * 1000, 3),
    }
    return metrics, p_threat


def _cross_validate(spec: M.ModelSpec, X, y, folds: int, cap: int, seed: int) -> dict:
    """Cross-validation estratificada (F1 e ROC-AUC) numa subamostra para tratabilidade."""
    from sklearn.model_selection import StratifiedKFold, train_test_split
    from sklearn.metrics import f1_score, roc_auc_score

    if folds < 2:
        return {}

    Xc, yc = X, y
    if cap and cap < len(X):
        Xc, _, yc, _ = train_test_split(X, y, train_size=cap, random_state=seed, stratify=y)

    Xc = Xc.reset_index(drop=True)
    yc = yc.reset_index(drop=True)
    spw = M.positive_class_weight(yc)
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    f1s, aucs = [], []
    for tr, te in skf.split(Xc, yc):
        model = spec.factory(seed, spw)  # factory retorna estimador novo a cada chamada
        model.fit(Xc.iloc[tr], yc.iloc[tr])
        prob = model.predict_proba(Xc.iloc[te])[:, 1]
        pred = (prob >= 0.5).astype(int)
        f1s.append(f1_score(yc.iloc[te], pred, zero_division=0))
        aucs.append(roc_auc_score(yc.iloc[te], prob))

    return {
        "cv_folds": folds,
        "cv_n": int(len(Xc)),
        "cv_f1_mean": float(np.mean(f1s)),
        "cv_f1_std": float(np.std(f1s)),
        "cv_roc_auc_mean": float(np.mean(aucs)),
        "cv_roc_auc_std": float(np.std(aucs)),
    }


# Benchmark de um dataset

def run_dataset_benchmark(
    df: pd.DataFrame,
    dataset_key: str,
    dataset_name: str,
    out_dir: Path,
    sample_size: Optional[int] = 200_000,
    cv_folds: int = 5,
    cv_cap: int = 60_000,
    test_fraction: float = 0.2,
    seed: int = 42,
    include_slow: bool = True,
    save_models: bool = True,
    tracker: ProgressTracker | None = None,
) -> dict:
    """Treina e compara todos os modelos para um dataset. Retorna o relatório completo."""
    from sklearn.model_selection import train_test_split

    logger.info("=" * 64)
    logger.info(f"BENCHMARK DE MODELOS — {dataset_name}")
    logger.info("=" * 64)

    if sample_size and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=seed).reset_index(drop=True)
        logger.info(f"  Subamostra de {len(df):,} registros")

    X, y, feature_cols = M.prepare_xy(df)
    n_benign, n_threat = int((y == 0).sum()), int((y == 1).sum())
    logger.info(f"  {len(X):,} registros | {len(feature_cols)} features | {n_benign:,} benign / {n_threat:,} threat")
    if n_benign == 0 or n_threat == 0:
        raise ValueError(f"{dataset_name}: dataset não tem ambas as classes")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_fraction, random_state=seed, stratify=y
    )
    spw = M.positive_class_weight(y_train)

    specs = M.build_model_specs()
    if not include_slow:
        specs = [s for s in specs if not s.slow]

    results: list[dict] = []
    roc_curves: dict[str, np.ndarray] = {}
    fitted: dict[str, object] = {}

    for spec in specs:
        if tracker:
            tracker.start_step(f"{spec.name} ({dataset_name})")
        try:
            model = spec.factory(seed, spw)
            # Modelos lentos treinam numa subamostra estratificada (KNN/MLP)
            Xtr, ytr = X_train, y_train
            if spec.slow and len(X_train) > SLOW_TRAIN_CAP:
                from sklearn.model_selection import train_test_split as _tts
                Xtr, _, ytr, _ = _tts(X_train, y_train, train_size=SLOW_TRAIN_CAP,
                                      random_state=seed, stratify=y_train)
                logger.info(f"     {spec.name}: treino limitado a {SLOW_TRAIN_CAP:,} (modelo lento)")
            t0 = time.time()
            model.fit(Xtr, ytr)
            train_time = time.time() - t0
            metrics, p_threat = _evaluate(spec.name, model, X_test, y_test, train_time)
            metrics["family"] = spec.family
            if cv_folds >= 2:
                metrics.update(_cross_validate(spec, X_train, y_train, cv_folds, cv_cap, seed))
            results.append(metrics)
            roc_curves[spec.name] = p_threat
            fitted[spec.name] = model
            summary = (f"acc={metrics['accuracy']:.4f} f1={metrics['f1_threat']:.4f} "
                       f"roc_auc={metrics['roc_auc']:.4f}")
            logger.info(f"     {summary} train={train_time:.1f}s")
            if tracker:
                tracker.end_step(summary)
        except Exception as e:
            logger.error(f"     FALHOU {spec.name}: {e}")
            if tracker:
                tracker.end_step(f"FALHOU: {e}")

    # Ensemble por soft-voting dos melhores candidatos disponíveis
    ens_members = [(n, fitted[n]) for n in ENSEMBLE_CANDIDATES if n in fitted]
    ensemble = None
    if len(ens_members) >= 2:
        if tracker:
            tracker.start_step(f"Ensemble ({dataset_name})")
        logger.info(f"  Ensemble (soft-voting de {[n for n, _ in ens_members]})...")
        ensemble = M.SoftVotingEnsemble(ens_members)
        metrics, p_threat = _evaluate("Ensemble", ensemble, X_test, y_test, 0.0)
        metrics["family"] = "ensemble"
        metrics["members"] = [n for n, _ in ens_members]
        results.append(metrics)
        roc_curves["Ensemble"] = p_threat
        ens_summary = (f"acc={metrics['accuracy']:.4f} f1={metrics['f1_threat']:.4f} "
                       f"roc_auc={metrics['roc_auc']:.4f}")
        logger.info(f"     {ens_summary}")
        if tracker:
            tracker.end_step(ens_summary)

    results.sort(key=lambda m: m["f1_threat"], reverse=True)
    best_name = results[0]["model"] if results else None
    logger.info(f"  Melhor modelo por F1: {best_name}")

    # Persistência dos modelos
    if save_models:
        _save_models(fitted, ensemble, feature_cols, dataset_key, dataset_name, best_name)

    # Gráficos
    y_test_arr = y_test.values if hasattr(y_test, "values") else np.asarray(y_test)
    _plot_metric_bars(results, dataset_name, out_dir / f"metrics_{dataset_key}.png")
    _plot_roc(roc_curves, y_test_arr, dataset_name, out_dir / f"roc_{dataset_key}.png")
    if best_name:
        best_cm = next(m["confusion_matrix"] for m in results if m["model"] == best_name)
        _plot_confusion(best_cm, f"{dataset_name} — {best_name}", out_dir / f"confusion_{dataset_key}.png")
    _plot_feature_importance(fitted, feature_cols, dataset_name, out_dir / f"importance_{dataset_key}.png")

    return {
        "dataset": dataset_name,
        "dataset_key": dataset_key,
        "n_total": int(len(X)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_features": len(feature_cols),
        "n_benign": n_benign,
        "n_threat": n_threat,
        "seed": seed,
        "best_model": best_name,
        "models": results,
    }


def _save_models(fitted, ensemble, feature_cols, dataset_key, dataset_name, best_name):
    import joblib

    def bundle(model, name):
        return {"clf": model, "feature_cols": feature_cols, "model_name": name, "dataset": dataset_name}

    # Random Forest com o nome legado (compatibilidade com PreClassifier/triage existente)
    if "RandomForest" in fitted:
        joblib.dump(bundle(fitted["RandomForest"], "RandomForest"), MODELS_DIR / f"rf_{dataset_key}.joblib")
    if best_name and best_name in fitted:
        joblib.dump(bundle(fitted[best_name], best_name), MODELS_DIR / f"best_{dataset_key}.joblib")
    if ensemble is not None:
        joblib.dump(bundle(ensemble, "Ensemble"), MODELS_DIR / f"ensemble_{dataset_key}.joblib")
    logger.info(f"  Modelos salvos em {MODELS_DIR}")


# Gráficos

def _setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _plot_metric_bars(results: list[dict], dataset_name: str, path: Path):
    plt = _setup_plt()
    names = [m["model"] for m in results]
    f1 = [m["f1_threat"] for m in results]
    auc = [m["roc_auc"] for m in results]
    x = np.arange(len(names))
    w = 0.38
    fig, ax = plt.subplots(figsize=(max(8, len(names) * 0.9), 5))
    ax.bar(x - w / 2, f1, w, label="F1 (threat)", color="#2c7fb8")
    ax.bar(x + w / 2, auc, w, label="ROC-AUC", color="#7fcdbb")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=35, ha="right")
    ax.set_ylim(min(0.5, min(f1 + auc) - 0.05), 1.005)
    ax.set_ylabel("Score")
    ax.set_title(f"Comparação de modelos — {dataset_name}")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _plot_roc(roc_curves: dict, y_test, dataset_name: str, path: Path):
    from sklearn.metrics import roc_curve, roc_auc_score
    plt = _setup_plt()
    fig, ax = plt.subplots(figsize=(7, 6))
    for name, p_threat in sorted(roc_curves.items(), key=lambda kv: -roc_auc_score(y_test, kv[1])):
        fpr, tpr, _ = roc_curve(y_test, p_threat)
        ax.plot(fpr, tpr, lw=1.4, label=f"{name} (AUC={roc_auc_score(y_test, p_threat):.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
    ax.set_xlabel("Taxa de falsos positivos")
    ax.set_ylabel("Taxa de verdadeiros positivos")
    ax.set_title(f"Curvas ROC — {dataset_name}")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _plot_confusion(cm: list, title: str, path: Path):
    plt = _setup_plt()
    cm = np.array(cm)
    fig, ax = plt.subplots(figsize=(4.5, 4))
    im = ax.imshow(cm, cmap="Blues")
    labels = ["Benign", "Threat"]
    ax.set_xticks([0, 1]); ax.set_xticklabels(labels)
    ax.set_yticks([0, 1]); ax.set_yticklabels(labels)
    ax.set_xlabel("Predito"); ax.set_ylabel("Real")
    ax.set_title(title)
    total = cm.sum()
    for i in range(2):
        for j in range(2):
            pct = 100 * cm[i, j] / total if total else 0
            ax.text(j, i, f"{cm[i, j]:,}\n{pct:.1f}%", ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _plot_feature_importance(fitted: dict, feature_cols: list, dataset_name: str, path: Path):
    """Importância de features do melhor modelo baseado em árvore disponível."""
    plt = _setup_plt()
    importances = None
    source = None
    for name in ["RandomForest", "ExtraTrees", "XGBoost", "LightGBM"]:
        model = fitted.get(name)
        if model is not None and hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_)
            source = name
            break
    if importances is None:
        return
    order = np.argsort(importances)[::-1][:15]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.barh([feature_cols[i] for i in order][::-1], importances[order][::-1], color="#2c7fb8")
    ax.set_title(f"Top 15 features — {dataset_name} ({source})")
    ax.set_xlabel("Importância")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# Relatórios

def _write_reports(reports: list[dict], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "model_comparison.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)

    lines = ["# Comparação de Modelos — Benign vs Threat", ""]
    for rep in reports:
        lines += [
            f"## {rep['dataset']}",
            "",
            f"- Registros: {rep['n_total']:,} ({rep['n_benign']:,} benign / {rep['n_threat']:,} threat)",
            f"- Treino/Teste: {rep['n_train']:,} / {rep['n_test']:,} | Features: {rep['n_features']} | Seed: {rep['seed']}",
            f"- Melhor modelo (F1): **{rep['best_model']}**",
            "",
            "| Modelo | Família | Acc | Bal.Acc | Precisão | Recall | F1 | ROC-AUC | PR-AUC | CV F1 (μ±σ) | Treino(s) |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for m in rep["models"]:
            cv = (f"{m['cv_f1_mean']:.4f}±{m['cv_f1_std']:.4f}"
                  if "cv_f1_mean" in m else "—")
            lines.append(
                f"| {m['model']} | {m.get('family','')} | {m['accuracy']:.4f} | "
                f"{m['balanced_accuracy']:.4f} | {m['precision_threat']:.4f} | "
                f"{m['recall_threat']:.4f} | {m['f1_threat']:.4f} | {m['roc_auc']:.4f} | "
                f"{m['pr_auc']:.4f} | {cv} | {m['train_time_s']} |"
            )
        lines.append("")
    with open(out_dir / "model_comparison.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Relatórios salvos em {out_dir}")


# Compatibilidade: regenera rf_meta.json no formato esperado pelo código legado

def _write_rf_meta(reports: list[dict]):
    meta = {}
    for rep in reports:
        rf = next((m for m in rep["models"] if m["model"] == "RandomForest"), None)
        if rf is None:
            continue
        meta[rep["dataset_key"]] = {
            "dataset": rep["dataset_key"],
            "accuracy": rf["accuracy"],
            "precision_threat": rf["precision_threat"],
            "recall_threat": rf["recall_threat"],
            "f1_threat": rf["f1_threat"],
            "benign_high_confidence_coverage": rf["benign_high_confidence_coverage"],
            "threat_misclassified_high_conf": rf["threat_misclassified_high_conf"],
            "confusion_matrix": rf["confusion_matrix"],
        }
    with open(MODELS_DIR / "rf_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# CLI

def main():
    parser = argparse.ArgumentParser(description="Estudo comparativo de modelos ML (Benign vs Threat)")
    parser.add_argument("--sample-size", type=int, default=200_000,
                        help="Subamostra por dataset (0 = usar tudo, default 200000)")
    parser.add_argument("--datasets", nargs="+", choices=["cic", "unsw"], default=["cic", "unsw"])
    parser.add_argument("--cv-folds", type=int, default=5, help="Folds de cross-validation (0 desativa)")
    parser.add_argument("--cv-cap", type=int, default=60_000, help="Tamanho máx. da subamostra de CV")
    parser.add_argument("--no-slow", action="store_true", help="Pula modelos lentos (KNN, MLP)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-save-models", action="store_true", help="Não persistir os modelos")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = BENCHMARK_DIR / f"bench_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_size = args.sample_size if args.sample_size > 0 else None

    specs = M.build_model_specs()
    if args.no_slow:
        specs = [s for s in specs if not s.slow]
    datasets = [k for k in args.datasets if _DATASET_FILES[k][0].exists()]
    # passos = (modelos + 1 ensemble) por dataset disponível
    total_steps = len(datasets) * (len(specs) + 1)

    print(banner(f"BENCHMARK DE MODELOS ML — {len(datasets)} dataset(s), "
                 f"{len(specs)} modelos, {total_steps} passos"))
    logger.info(f"Modelos: {[s.name for s in specs]}")
    logger.info(f"XGBoost={M.HAS_XGB} | LightGBM={M.HAS_LGBM} | CV={args.cv_folds}-fold | seed={args.seed}")
    tracker = ProgressTracker(total=total_steps, label="Benchmark de modelos ML")

    reports = []
    for key in datasets:
        path, name = _DATASET_FILES[key]
        df = pd.read_parquet(path)
        df["dataset_source"] = name
        rep = run_dataset_benchmark(
            df, key, name, out_dir,
            sample_size=sample_size, cv_folds=args.cv_folds, cv_cap=args.cv_cap,
            seed=args.seed, include_slow=not args.no_slow,
            save_models=not args.no_save_models, tracker=tracker,
        )
        reports.append(rep)
        _write_reports(reports, out_dir)  # incremental

    tracker.finish()

    if reports and not args.no_save_models:
        _write_rf_meta(reports)

    print("\n" + "=" * 64)
    print("BENCHMARK CONCLUÍDO")
    print("=" * 64)
    for rep in reports:
        print(f"\n[{rep['dataset']}] melhor: {rep['best_model']}")
        for m in rep["models"][:5]:
            print(f"  {m['model']:<22} f1={m['f1_threat']:.4f}  roc_auc={m['roc_auc']:.4f}  acc={m['accuracy']:.4f}")
    print(f"\nRelatórios e gráficos: {out_dir}")


if __name__ == "__main__":
    main()

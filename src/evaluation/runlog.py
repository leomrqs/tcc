"""
Persistência padronizada das runs de triagem.

Centraliza o formato dos resultados para que a "pilha de dados" gerada pelas
baterias seja fácil de agregar depois (gráficos, tabelas, análise):

- Nome de pasta consistente e parseável:
  run_<timestamp>_<dataset>_<config>_n<N>_seed<seed>/
- results.json com schema explícito e legível (blocos run / summary / metrics /
  explanation_quality / records)
- Um manifesto append-only (runs_index.jsonl) com uma linha achatada por run —
  basta `pandas.read_json(path, lines=True)` para ter tudo tabelado.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 3
MANIFEST_PATH = config.TRIAGE_RUNS_DIR / "runs_index.jsonl"


def config_slug(flags: dict) -> str:
    """Slug curto e estável da configuração, a partir das flags ativas."""
    if not flags.get("use_rag"):
        parts = ["norag"]
    else:
        parts = ["rag"]
        if flags.get("use_rerank"):
            parts.append("rerank")
    if flags.get("use_rf"):
        # distingue a variante do pré-classificador (rf / best / ensemble)
        parts.append(flags.get("clf_kind") or "rf")
    if flags.get("two_stage"):
        parts.append("2stage")
    return "-".join(parts)


def make_run_dir(base: Path, dataset: str, slug: str, n: int, seed: int,
                 timestamp: str | None = None) -> Path:
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base / f"run_{ts}_{dataset}_{slug}_n{n}_seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _flat_summary(run_meta: dict, metrics: dict, expl: dict | None) -> dict:
    """Linha achatada (uma run) para o manifesto e o bloco summary do results.json."""
    b = metrics.get("binary", {})
    cm = b.get("confusion", {})
    return {
        "run_id": run_meta["id"],
        "timestamp": run_meta["timestamp"],
        "config": run_meta["config"],
        "dataset": run_meta["dataset"],
        "n_records": run_meta["n_records"],
        "n_scored": metrics.get("n_scored"),
        "seed": run_meta["seed"],
        "model": run_meta.get("model"),
        "accuracy_exact": metrics.get("accuracy_exact"),
        "accuracy_binary": b.get("accuracy"),
        "precision": b.get("precision"),
        "recall": b.get("recall"),
        "f1": b.get("f1"),
        "specificity": b.get("specificity"),
        "macro_f1": metrics.get("macro_f1"),
        "weighted_f1": metrics.get("weighted_f1"),
        "tp": cm.get("tp"), "tn": cm.get("tn"), "fp": cm.get("fp"), "fn": cm.get("fn"),
        "avg_confidence": metrics.get("avg_confidence"),
        "avg_elapsed_seconds": metrics.get("avg_elapsed_seconds"),
        "explanation_composite": (expl or {}).get("composite_mean"),
        "explanation_mitre_validity": (expl or {}).get("mitre_validity_mean"),
        "n_explained": (expl or {}).get("n_explained"),
    }


def save_run(
    records: list[dict],
    run_meta: dict,
    run_dir: Path,
    manifest_path: Path | None = MANIFEST_PATH,
    with_explanation_quality: bool = True,
) -> dict:
    """
    Salva a run no formato padronizado e devolve o resumo achatado.

    run_meta deve conter: id, timestamp, config, dataset, n_records, seed, model, flags.
    """
    from src.evaluation import metrics as M

    metrics = M.compute_metrics(records)

    expl = None
    if with_explanation_quality:
        try:
            from src.evaluation import explanation_quality as EQ
            expl_full = EQ.evaluate_results(records)
            # guarda só o agregado no results.json (per_record fica em arquivo à parte)
            expl = {k: v for k, v in expl_full.items() if k != "per_record"}
            if expl_full.get("n_explained"):
                (run_dir / "explanation_quality.json").write_text(
                    json.dumps(expl_full, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as e:
            logger.warning(f"Qualidade das explicações não avaliada: {e}")

    summary = _flat_summary(run_meta, metrics, expl)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run": run_meta,
        "summary": summary,
        "metrics": metrics,
        "explanation_quality": expl,
        "records": records,
    }
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    logger.info(f"Run salva em {run_dir}")
    logger.info(f"Manifesto atualizado: {manifest_path}")
    return summary

"""
Métricas agregadas de avaliação da triagem do LLM.

Vai além do resumo embutido no pipeline: calcula métricas por classe, matriz de
confusão multiclasse e permite AGREGAR várias runs (pool de registros) para
obter N estatisticamente relevante — mitigando a limitação de amostras pequenas
por run.

Uso:
    # Analisa uma run (gera metrics_detailed.json + gráficos na pasta da run)
    python -m src.evaluation.metrics outputs/triage_runs/run_.../results.json

    # Agrega todas as runs de uma config (ou de um benchmark inteiro)
    python -m src.evaluation.metrics --aggregate "outputs/triage_runs/*rag_rerank_rf*"
"""

from __future__ import annotations

import glob
import json
from collections import Counter
from pathlib import Path

import numpy as np

# Categorias canônicas (15 ataques + Benign). "Unknown"/"Other" capturam ruído.
CANONICAL_CATEGORIES = [
    "Benign", "DoS", "DDoS", "Brute Force", "Botnet", "Reconnaissance",
    "Web Attack", "Exploits", "Fuzzers", "Backdoor", "Generic",
    "Analysis", "Shellcode", "Worms", "Infiltration",
]
_BENIGN_LABELS = {"benign", "normal", "background"}

_ALIASES = {
    "bruteforce": "Brute Force", "brute-force": "Brute Force",
    "denial of service": "DoS", "distributed denial of service": "DDoS",
    "command and control": "Botnet", "c2": "Botnet", "c&c": "Botnet",
    "port scan": "Reconnaissance", "portscan": "Reconnaissance", "scan": "Reconnaissance",
    "webattack": "Web Attack", "web-attack": "Web Attack",
    "backdoors": "Backdoor", "attack": "Generic",
}


def canonical(label: str) -> str:
    """Mapeia um rótulo livre para uma categoria canônica."""
    if not label:
        return "Unknown"
    key = str(label).strip().lower()
    if key in _BENIGN_LABELS:
        return "Benign"
    if key in _ALIASES:
        return _ALIASES[key]
    for cat in CANONICAL_CATEGORIES:
        if key == cat.lower():
            return cat
    return str(label).strip().title()


def is_threat(label: str) -> bool:
    return bool(label) and str(label).strip().lower() not in _BENIGN_LABELS


# Cálculo de métricas

def compute_metrics(results: list[dict]) -> dict:
    """Calcula o bloco completo de métricas a partir de uma lista de registros triados."""
    scored = [r for r in results if r.get("ground_truth") is not None]
    n = len(scored)
    if n == 0:
        return {"n_scored": 0}

    y_true = [canonical(r["ground_truth"]) for r in scored]
    y_pred = [canonical(r.get("attack_type", "Unknown")) for r in scored]

    # Acurácia exata
    exact = sum(1 for t, p in zip(y_true, y_pred) if t == p)

    # Binária (ameaça vs benigno)
    tb = [is_threat(r["ground_truth"]) for r in scored]
    pb = [is_threat(r.get("attack_type")) for r in scored]
    tp = sum(1 for t, p in zip(tb, pb) if t and p)
    tn = sum(1 for t, p in zip(tb, pb) if not t and not p)
    fp = sum(1 for t, p in zip(tb, pb) if not t and p)
    fn = sum(1 for t, p in zip(tb, pb) if t and not p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0

    # Por classe (precision/recall/f1/support) sobre todas as categorias presentes
    labels = sorted(set(y_true) | set(y_pred))
    per_class = {}
    for c in labels:
        c_tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        c_fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        c_fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        support = sum(1 for t in y_true if t == c)
        pr = c_tp / (c_tp + c_fp) if (c_tp + c_fp) else 0.0
        rc = c_tp / (c_tp + c_fn) if (c_tp + c_fn) else 0.0
        per_class[c] = {
            "precision": round(pr, 4), "recall": round(rc, 4),
            "f1": round(2 * pr * rc / (pr + rc), 4) if (pr + rc) else 0.0,
            "support": support,
        }

    present = [c for c in labels if per_class[c]["support"] > 0]
    macro_f1 = float(np.mean([per_class[c]["f1"] for c in present])) if present else 0.0
    weighted_f1 = (
        float(np.average([per_class[c]["f1"] for c in present],
                         weights=[per_class[c]["support"] for c in present]))
        if present else 0.0
    )

    # Matriz de confusão multiclasse (linhas = real, colunas = predito)
    cm_labels = labels
    idx = {c: i for i, c in enumerate(cm_labels)}
    cm = np.zeros((len(cm_labels), len(cm_labels)), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[idx[t], idx[p]] += 1

    return {
        "n_scored": n,
        "accuracy_exact": round(exact / n, 4),
        "binary": {
            "accuracy": round((tp + tn) / n, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "specificity": round(specificity, 4),
            "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        },
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_class": per_class,
        "confusion_matrix": {"labels": cm_labels, "matrix": cm.tolist()},
        "predicted_distribution": dict(Counter(y_pred)),
        "truth_distribution": dict(Counter(y_true)),
        "avg_confidence": round(float(np.mean([r.get("confidence", 0.0) for r in scored])), 4),
        "avg_elapsed_seconds": round(float(np.mean([r.get("elapsed_seconds", 0.0) for r in scored])), 2),
    }


# Gráficos

def _setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_confusion(cm_block: dict, title: str, path: Path):
    plt = _setup_plt()
    labels = cm_block["labels"]
    cm = np.array(cm_block["matrix"])
    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 0.6), max(4, len(labels) * 0.55)))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Predito"); ax.set_ylabel("Real"); ax.set_title(title)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=7)
    fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_per_class_f1(per_class: dict, title: str, path: Path):
    plt = _setup_plt()
    items = [(c, d) for c, d in per_class.items() if d["support"] > 0]
    items.sort(key=lambda kv: kv[1]["f1"], reverse=True)
    names = [c for c, _ in items]
    f1 = [d["f1"] for _, d in items]
    fig, ax = plt.subplots(figsize=(max(6, len(names) * 0.7), 4.5))
    ax.bar(range(len(names)), f1, color="#2c7fb8")
    ax.set_ylim(0, 1.02); ax.set_ylabel("F1")
    ax.set_title(title)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=40, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# Análise de runs

def analyze_run(results_path: Path, plots: bool = True) -> dict:
    """Analisa uma run individual, salvando metrics_detailed.json e gráficos."""
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    results = data.get("results", data if isinstance(data, list) else [])
    metrics = compute_metrics(results)
    out_dir = Path(results_path).parent
    (out_dir / "metrics_detailed.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if plots and metrics.get("n_scored", 0) > 0:
        plot_confusion(metrics["confusion_matrix"], f"Confusão — {out_dir.name}",
                       out_dir / "confusion_matrix.png")
        plot_per_class_f1(metrics["per_class"], f"F1 por classe — {out_dir.name}",
                          out_dir / "per_class_f1.png")
    return metrics


def aggregate_runs(pattern: str, out_dir: Path | None = None) -> dict:
    """Agrega (pool de registros) várias runs para obter N maior e métricas estáveis."""
    paths = sorted(glob.glob(pattern))
    pooled = []
    run_names = []
    for p in paths:
        rp = Path(p)
        if rp.is_dir():
            rp = rp / "results.json"
        if not rp.exists():
            continue
        data = json.loads(rp.read_text(encoding="utf-8"))
        pooled.extend(data.get("results", []))
        run_names.append(rp.parent.name)

    metrics = compute_metrics(pooled)
    metrics["n_runs_pooled"] = len(run_names)
    metrics["runs"] = run_names
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "aggregate_metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if metrics.get("n_scored", 0) > 0:
            plot_confusion(metrics["confusion_matrix"], "Confusão — agregado", out_dir / "confusion_matrix.png")
            plot_per_class_f1(metrics["per_class"], "F1 por classe — agregado", out_dir / "per_class_f1.png")
    return metrics


def _print_summary(metrics: dict):
    if metrics.get("n_scored", 0) == 0:
        print("Sem registros com ground truth.")
        return
    b = metrics["binary"]
    print(f"  N avaliado:        {metrics['n_scored']}"
          + (f" (pool de {metrics['n_runs_pooled']} runs)" if "n_runs_pooled" in metrics else ""))
    print(f"  Acurácia exata:    {metrics['accuracy_exact']:.1%}")
    print(f"  Binária:           acc={b['accuracy']:.1%} prec={b['precision']:.1%} "
          f"recall={b['recall']:.1%} f1={b['f1']:.1%} spec={b['specificity']:.1%}")
    print(f"    TP={b['confusion']['tp']} TN={b['confusion']['tn']} "
          f"FP={b['confusion']['fp']} FN={b['confusion']['fn']}")
    print(f"  Macro-F1: {metrics['macro_f1']:.3f} | Weighted-F1: {metrics['weighted_f1']:.3f}")


def main():
    import argparse
    from src import config

    parser = argparse.ArgumentParser(description="Métricas detalhadas da triagem do LLM")
    parser.add_argument("path", nargs="?", help="results.json ou pasta da run")
    parser.add_argument("--aggregate", help="glob de runs para agregar (pool de registros)")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    if args.aggregate:
        out = config.OUTPUTS_DIR / "evaluation" / "aggregate"
        print(f"Agregando runs: {args.aggregate}")
        metrics = aggregate_runs(args.aggregate, out_dir=out)
        _print_summary(metrics)
        print(f"\nSalvo em: {out}")
    elif args.path:
        rp = Path(args.path)
        if rp.is_dir():
            rp = rp / "results.json"
        print(f"Analisando: {rp.parent.name}")
        metrics = analyze_run(rp, plots=not args.no_plots)
        _print_summary(metrics)
    else:
        parser.error("informe um caminho de run ou --aggregate <glob>")


if __name__ == "__main__":
    main()

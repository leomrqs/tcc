"""
CLI da Etapa 3: Pipeline de triagem.

Carrega registros do dataset processado, executa o pipeline completo
(descrição → RAG → LLM → triagem) e salva os resultados.

Uso:
    # Triar 10 registros aleatórios do dataset unificado
    python -m src.llm.pipeline --n 10

    # Triar registros estratificados (igual nº de cada classe)
    python -m src.llm.pipeline --n 5 --stratified

    # Triar só registros do CIC-IDS2017
    python -m src.llm.pipeline --n 10 --dataset cic

    # Triar sem RAG (baseline)
    python -m src.llm.pipeline --n 5 --no-rag

    # Triar um registro específico (índice no dataset)
    python -m src.llm.pipeline --index 12345
"""

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from src.llm.triage import TriageEngine, TriageResult
from src.utils.logger import get_logger
from src import config

logger = get_logger(__name__)


def load_dataset(dataset_choice: str, sample_size: int | None, seed: int = None) -> pd.DataFrame:
    """
    Carrega o dataset NÃO normalizado para o pipeline de triagem.

    O unified_dataset.parquet está normalizado (0-1), o que inutiliza o
    text_converter. Por isso, para 'unified', concatenamos os dois datasets
    individuais (que preservam os valores brutos).

    Args:
        dataset_choice: "unified", "cic" ou "unsw"
        sample_size: se não-None, amostra estratificada de N linhas por dataset
            para evitar carregar 5M+ registros desnecessariamente.
    """
    rng_seed = seed if seed is not None else config.RANDOM_SEED
    if dataset_choice == "unified":
        frames = []
        for choice, path in [("cic", config.CIC_PROCESSED_FILE), ("unsw", config.UNSW_PROCESSED_FILE)]:
            if not path.exists():
                raise FileNotFoundError(
                    f"Dataset '{choice}' não encontrado em {path}. "
                    f"Rode primeiro: python -m src.data.pipeline"
                )
            sub = pd.read_parquet(path)
            if sample_size is not None:
                n = min(sample_size, len(sub))
                sub = sub.sample(n=n, random_state=rng_seed).reset_index(drop=True)
            frames.append(sub)
        df = pd.concat(frames, ignore_index=True)
        logger.info(f"Carregando unified (não normalizado): {len(df):,} registros, {len(df.columns)} colunas")
        return df

    paths = {"cic": config.CIC_PROCESSED_FILE, "unsw": config.UNSW_PROCESSED_FILE}
    path = paths.get(dataset_choice)
    if path is None or not path.exists():
        raise FileNotFoundError(
            f"Dataset '{dataset_choice}' não encontrado em {path}. "
            f"Rode primeiro: python -m src.data.pipeline"
        )

    logger.info(f"Carregando {path.name}...")
    df = pd.read_parquet(path)
    logger.info(f"  {len(df):,} registros, {len(df.columns)} colunas")

    if sample_size is not None and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=rng_seed).reset_index(drop=True)
        logger.info(f"  Pré-amostrado para {len(df):,} registros")

    return df


def select_records(
    df: pd.DataFrame,
    n: int,
    stratified: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Seleciona registros para triagem.

    Args:
        df: DataFrame completo
        n: número de registros desejado
        stratified: se True, tenta pegar n/k registros de cada classe
        seed: para reprodutibilidade
    """
    if stratified and "label" in df.columns:
        per_class = max(1, n // df["label"].nunique())
        logger.info(f"Amostragem estratificada: ~{per_class} registros por classe")
        frames = [
            group.sample(min(len(group), per_class), random_state=seed)
            for _, group in df.groupby("label", group_keys=False)
        ]
        return pd.concat(frames).reset_index(drop=True)

    return df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)


def save_results(results: list[TriageResult], output_path: Path):
    """Salva resultados em arquivo JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    has_gt = all(r.ground_truth is not None for r in results)
    correct = sum(1 for r in results if _matches_label(r.attack_type, r.ground_truth)) if has_gt else None
    tp = sum(1 for r in results if _is_threat(r.attack_type) and _is_threat(r.ground_truth)) if has_gt else None
    tn = sum(1 for r in results if not _is_threat(r.attack_type) and not _is_threat(r.ground_truth)) if has_gt else None
    fp = sum(1 for r in results if _is_threat(r.attack_type) and not _is_threat(r.ground_truth)) if has_gt else None
    fn = sum(1 for r in results if not _is_threat(r.attack_type) and _is_threat(r.ground_truth)) if has_gt else None
    payload = {
        "n_records": len(results),
        "n_valid": sum(1 for r in results if r.is_valid),
        "avg_elapsed_seconds": sum(r.elapsed_seconds for r in results) / len(results) if results else 0,
        "accuracy_exact": round(correct / len(results), 4) if correct is not None else None,
        "accuracy_binary": round((tp + tn) / len(results), 4) if tp is not None else None,
        "precision": round(tp / (tp + fp), 4) if tp is not None and (tp + fp) > 0 else None,
        "recall": round(tp / (tp + fn), 4) if tp is not None and (tp + fn) > 0 else None,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn} if has_gt else None,
        "results": [r.to_dict() for r in results],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info(f"Resultados salvos em {output_path}")


_BENIGN_LABELS = {"benign", "normal", "background"}

def _is_threat(label: str) -> bool:
    return label is not None and label.strip().lower() not in _BENIGN_LABELS

def print_summary(results: list[TriageResult]):
    """Imprime resumo dos resultados no console."""
    from collections import Counter
    print()
    print("=" * 70)
    print(f"RESUMO DA TRIAGEM ({len(results)} registros)")
    print("=" * 70)

    has_gt = all(r.ground_truth is not None for r in results)

    if has_gt:
        # Acurácia exata por categoria
        correct = sum(
            1 for r in results
            if r.attack_type and _matches_label(r.attack_type, r.ground_truth)
        )
        print(f"Acurácia (categoria exata): {correct}/{len(results)} ({100*correct/len(results):.1f}%)")

        # Acurácia binária: ameaça vs benigno
        tp = sum(1 for r in results if _is_threat(r.attack_type) and _is_threat(r.ground_truth))
        tn = sum(1 for r in results if not _is_threat(r.attack_type) and not _is_threat(r.ground_truth))
        fp = sum(1 for r in results if _is_threat(r.attack_type) and not _is_threat(r.ground_truth))
        fn = sum(1 for r in results if not _is_threat(r.attack_type) and _is_threat(r.ground_truth))
        bin_acc = (tp + tn) / len(results) if results else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"Acurácia (ameaça vs benigno): {bin_acc:.1%} | Precisão: {precision:.1%} | Recall: {recall:.1%} | F1: {f1:.1%}")
        print(f"  TP={tp} TN={tn} FP={fp} FN={fn}")

    # Distribuição de categorias preditas
    attack_counts = Counter(r.attack_type for r in results)
    print(f"Predições por categoria: {dict(attack_counts)}")

    # Distribuição de severidade
    sev_counts = Counter(r.severity for r in results)
    print(f"Distribuição de severidade: {dict(sev_counts)}")

    # Confiança média
    avg_conf = sum(r.confidence for r in results) / len(results) if results else 0
    print(f"Confiança média: {avg_conf:.2f}")

    # Tempo
    avg = sum(r.elapsed_seconds for r in results) / len(results) if results else 0
    print(f"Tempo médio por triagem: {avg:.2f}s")

    # Mostrar uma amostra
    print()
    print("--- AMOSTRAS ---")
    for i, r in enumerate(results[:3], 1):
        print(f"\n[{i}] Ground truth: {r.ground_truth}")
        print(f"    Triagem: {r.attack_type} ({r.severity}, conf={r.confidence:.2f})")
        print(f"    MITRE: {', '.join(r.mitre_techniques) or '(nenhum)'}")
        exp = r.explanation[:150] + "..." if len(r.explanation) > 150 else r.explanation
        print(f"    Explicação: {exp}")
        if r.validation_errors:
            print(f"    ⚠ Erros: {r.validation_errors}")
    print("=" * 70)


_LABEL_ALIASES = {
    "benign": {"benign", "normal", "background"},
    "brute force": {"brute force", "bruteforce", "brute-force"},
    "dos": {"dos", "denial of service"},
    "ddos": {"ddos", "distributed denial of service"},
    "web attack": {"web attack", "webattack", "web-attack"},
}

def _matches_label(predicted: str, actual: str) -> bool:
    """Comparação flexível entre rótulos (case insensitive, com aliases)."""
    if not predicted or not actual:
        return False
    p = predicted.strip().lower()
    a = actual.strip().lower()
    if p == a:
        return True
    for aliases in _LABEL_ALIASES.values():
        if p in aliases and a in aliases:
            return True
    return False


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de triagem (Etapa 3): RAG + LLM"
    )
    parser.add_argument(
        "--dataset",
        choices=["unified", "cic", "unsw"],
        default="unified",
        help="Dataset a usar (default: unified)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=10,
        help="Número de registros a triar (default: 10)",
    )
    parser.add_argument(
        "--stratified",
        action="store_true",
        help="Amostragem estratificada (tentar pegar de cada classe)",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="Triar um registro específico pelo índice",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Rodar SEM RAG (baseline para avaliação)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Número de docs a buscar no RAG (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed da amostragem (default: aleatório a cada run)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Arquivo JSON de saída (default: outputs/triage_<timestamp>.json)",
    )
    parser.add_argument(
        "--two-stage",
        action="store_true",
        help="Ativar two-stage classification (Stage 1 binário rápido, opcional)",
    )
    parser.add_argument(
        "--use-rf",
        action="store_true",
        help="Ativar pre-classificador Random Forest (filtra Benign de alta confiança)",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Desativar cross-encoder re-ranking no RAG (default: ativo)",
    )
    parser.add_argument(
        "--rag-threshold",
        type=float,
        default=0.55,
        help="Threshold de distância RAG para descartar contexto (default: 0.55)",
    )
    parser.add_argument(
        "--rf-threshold",
        type=float,
        default=0.95,
        help="Confiança mínima do RF para skipar LLM (default: 0.95)",
    )

    args = parser.parse_args()

    # Seed: aleatório a cada run, exceto se passado explicitamente
    import random as _r
    seed = args.seed if args.seed is not None else _r.randint(1, 999999)
    logger.info(f"Seed da amostragem: {seed}")

    # Carregar dataset — pré-amostrar por dataset para cobrir classes raras
    preload_size = (args.n * 50) if args.index is None else None
    df = load_dataset(args.dataset, sample_size=preload_size, seed=seed)

    # Selecionar registros
    if args.index is not None:
        if args.index >= len(df):
            raise ValueError(f"Índice {args.index} fora do range [0, {len(df)})")
        sample = df.iloc[[args.index]].reset_index(drop=True)
    else:
        sample = select_records(df, args.n, stratified=args.stratified, seed=seed)

    logger.info(f"{len(sample)} registros selecionados para triagem")

    # Pre-classificador RF (opcional)
    rf_classifier = None
    if args.use_rf:
        from src.ml.preclassifier import PreClassifier
        rf_classifier = PreClassifier()
        if not rf_classifier.is_ready():
            logger.warning("RF não disponível — siga: python -m src.ml.preclassifier")
            rf_classifier = None

    # Retriever com cross-encoder re-rank (opcional)
    retriever = None
    if not args.no_rag:
        from src.rag.retriever import Retriever
        retriever = Retriever(use_reranker=not args.no_rerank)

    # Inicializar engine
    engine = TriageEngine(
        retriever=retriever,
        use_rag=not args.no_rag,
        rag_top_k=args.top_k,
        rag_distance_threshold=args.rag_threshold,
        use_two_stage=args.two_stage,
        rf_classifier=rf_classifier,
        rf_confidence_threshold=args.rf_threshold,
    )

    # Rodar triagem em lote
    results = engine.triage_batch(sample)

    # Salvar resultados — cada run vai para uma subpasta própria
    output_path = args.output
    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        tags = []
        tags.append("norag" if args.no_rag else "rag")
        if not args.no_rag and not args.no_rerank:
            tags.append("rerank")
        if args.two_stage:
            tags.append("2stage")
        if rf_classifier is not None:
            tags.append("rf")
        tags.append("stratified" if args.stratified else "random")
        suffix = "_".join(tags)
        run_dir = config.TRIAGE_RUNS_DIR / f"run_{timestamp}_{suffix}_n{len(sample)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = run_dir / "results.json"
    else:
        output_path = Path(output_path)

    save_results(results, output_path)

    # Resumo no console
    print_summary(results)


if __name__ == "__main__":
    main()
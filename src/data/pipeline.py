"""
Orquestrador do pipeline de ingestão e pré-processamento.

Executa a sequência completa:
1. Carrega os datasets brutos
2. Pré-processa cada um individualmente
3. Remove features constantes e altamente correlacionadas
4. Normaliza features numéricas
5. Salva os datasets processados (individual e unificado)
6. Gera relatório de pré-processamento

Uso:
    python -m src.data.pipeline
    python -m src.data.pipeline --dataset cic    # só CIC-IDS2017
    python -m src.data.pipeline --dataset unsw   # só UNSW-NB15
    python -m src.data.pipeline --skip-corr      # pular remoção de correlação
"""

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from src.data.loader import load_cic_ids2017, load_unsw_nb15
from src.data.preprocessor import (
    preprocess_cic,
    preprocess_unsw,
    normalize_features,
    remove_constant_columns,
    remove_high_correlation,
)
from src.utils.logger import get_logger
from src import config

logger = get_logger(__name__)


def run_pipeline(
    datasets: str = "both",
    skip_correlation: bool = False,
    correlation_threshold: float = 0.95,
    sample_fraction: float | None = None,
) -> dict:
    """
    Executa o pipeline completo de ingestão e pré-processamento.

    Args:
        datasets: "cic", "unsw", ou "both"
        skip_correlation: se True, não remove features correlacionadas
        correlation_threshold: limiar para remoção de correlação (default 0.95)
        sample_fraction: fração de amostragem (None = usar tudo)

    Returns:
        Dicionário com metadados do pipeline (contagens, colunas, tempos)
    """
    start_time = time.time()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "datasets": {},
    }

    processed_frames = []

    # ── CIC-IDS2017 ──
    if datasets in ("cic", "both"):
        logger.info("=" * 60)
        logger.info("PROCESSANDO CIC-IDS2017")
        logger.info("=" * 60)

        df_cic = _process_single_dataset(
            name="CIC-IDS2017",
            load_fn=load_cic_ids2017,
            preprocess_fn=preprocess_cic,
            output_path=config.CIC_PROCESSED_FILE,
            skip_correlation=skip_correlation,
            correlation_threshold=correlation_threshold,
            sample_fraction=sample_fraction,
        )
        report["datasets"]["CIC-IDS2017"] = _build_dataset_report(df_cic)
        processed_frames.append(df_cic)

    # ── UNSW-NB15 ──
    if datasets in ("unsw", "both"):
        logger.info("=" * 60)
        logger.info("PROCESSANDO UNSW-NB15")
        logger.info("=" * 60)

        df_unsw = _process_single_dataset(
            name="UNSW-NB15",
            load_fn=load_unsw_nb15,
            preprocess_fn=preprocess_unsw,
            output_path=config.UNSW_PROCESSED_FILE,
            skip_correlation=skip_correlation,
            correlation_threshold=correlation_threshold,
            sample_fraction=sample_fraction,
        )
        report["datasets"]["UNSW-NB15"] = _build_dataset_report(df_unsw)
        processed_frames.append(df_unsw)

    # ── Dataset unificado ──
    if datasets == "both" and len(processed_frames) == 2:
        logger.info("=" * 60)
        logger.info("CRIANDO DATASET UNIFICADO")
        logger.info("=" * 60)

        df_unified = _create_unified_dataset(
            processed_frames[0], processed_frames[1]
        )

        # Normalizar o dataset unificado
        df_unified_norm, norm_params = normalize_features(df_unified)

        # Salvar
        df_unified_norm.to_parquet(config.UNIFIED_PROCESSED_FILE, index=False)
        logger.info(f"Dataset unificado salvo em {config.UNIFIED_PROCESSED_FILE}")

        # Salvar parâmetros de normalização
        norm_path = config.PROCESSED_DIR / "normalization_params.json"
        with open(norm_path, "w") as f:
            json.dump(norm_params, f, indent=2)
        logger.info(f"Parâmetros de normalização salvos em {norm_path}")

        report["unified"] = {
            "total_records": len(df_unified_norm),
            "columns": len(df_unified_norm.columns),
            "shared_features": list(
                set(processed_frames[0].columns) & set(processed_frames[1].columns)
            ),
            "label_distribution": df_unified_norm["label"].value_counts().to_dict(),
        }

    elapsed = time.time() - start_time
    report["elapsed_seconds"] = round(elapsed, 2)

    # Salvar relatório
    report_path = config.PROCESSED_DIR / "preprocessing_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"Relatório salvo em {report_path}")

    logger.info("=" * 60)
    logger.info(f"Pipeline concluído em {elapsed:.1f}s")
    logger.info("=" * 60)

    return report


def _process_single_dataset(
    name: str,
    load_fn,
    preprocess_fn,
    output_path: Path,
    skip_correlation: bool,
    correlation_threshold: float,
    sample_fraction: float | None,
) -> pd.DataFrame:
    """Processa um único dataset: carregar → limpar → reduzir → salvar."""

    # Carregar
    df = load_fn()

    # Amostrar se solicitado
    if sample_fraction and sample_fraction < 1.0:
        n_before = len(df)
        df = df.sample(frac=sample_fraction, random_state=config.RANDOM_SEED)
        logger.info(f"  Amostrado: {n_before} → {len(df)} registros ({sample_fraction:.0%})")

    # Pré-processar
    df = preprocess_fn(df)

    # Remover colunas constantes
    df = remove_constant_columns(df)

    # Remover features altamente correlacionadas
    if not skip_correlation:
        df = remove_high_correlation(df, threshold=correlation_threshold)

    # Salvar versão individual (sem normalização, para flexibilidade)
    df.to_parquet(output_path, index=False)
    logger.info(f"  {name} salvo em {output_path}")

    return df


def _create_unified_dataset(df_cic: pd.DataFrame, df_unsw: pd.DataFrame) -> pd.DataFrame:
    """
    Cria um dataset unificado a partir dos dois datasets processados.

    Os datasets têm schemas diferentes (features distintas), então a
    unificação mantém apenas as colunas de metadados comuns (label,
    label_original, dataset_source) e concatena com colunas disjuntas
    preenchidas com 0.

    Isso permite que o pipeline de triagem opere sobre ambos os datasets
    de forma uniforme, enquanto a coluna 'dataset_source' permite
    separar os resultados na avaliação.
    """
    # Colunas de metadados (sempre presentes em ambos)
    meta_cols = ["label", "label_original", "dataset_source"]

    # Concatenar com fill_value=0 para colunas que só existem em um dataset
    df_unified = pd.concat([df_cic, df_unsw], ignore_index=True).fillna(0)

    # Forçar conversão numérica em colunas não-meta que ficaram com tipo misto
    # (ex: 'protocol' vem como string do CIC e como int 0 do fillna)
    for col in df_unified.columns:
        if col in meta_cols:
            continue
        if not pd.api.types.is_numeric_dtype(df_unified[col]):
            df_unified[col] = pd.to_numeric(df_unified[col], errors="coerce").fillna(0)

    n_shared = len(set(df_cic.columns) & set(df_unsw.columns) - set(meta_cols))
    n_cic_only = len(set(df_cic.columns) - set(df_unsw.columns))
    n_unsw_only = len(set(df_unsw.columns) - set(df_cic.columns))

    logger.info(
        f"  Dataset unificado: {len(df_unified)} registros, "
        f"{len(df_unified.columns)} colunas "
        f"({n_shared} compartilhadas, {n_cic_only} só CIC, {n_unsw_only} só UNSW)"
    )
    _log_unified_distribution(df_unified)

    return df_unified


def _build_dataset_report(df: pd.DataFrame) -> dict:
    """Gera relatório para um dataset processado."""
    return {
        "records": len(df),
        "columns": len(df.columns),
        "numeric_features": len(df.select_dtypes(include=["number"]).columns),
        "label_distribution": df["label"].value_counts().to_dict(),
        "column_names": list(df.columns),
    }


def _log_unified_distribution(df: pd.DataFrame):
    """Loga distribuição do dataset unificado por fonte e rótulo."""
    for source in df["dataset_source"].unique():
        subset = df[df["dataset_source"] == source]
        logger.info(f"  [{source}] {len(subset)} registros:")
        for label, count in subset["label"].value_counts().items():
            logger.info(f"    {label}: {count}")


# CLI

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de ingestão e pré-processamento dos datasets"
    )
    parser.add_argument(
        "--dataset",
        choices=["cic", "unsw", "both"],
        default="both",
        help="Qual dataset processar (default: both)",
    )
    parser.add_argument(
        "--skip-corr",
        action="store_true",
        help="Pular remoção de features correlacionadas",
    )
    parser.add_argument(
        "--corr-threshold",
        type=float,
        default=0.95,
        help="Limiar de correlação para remoção (default: 0.95)",
    )
    parser.add_argument(
        "--sample",
        type=float,
        default=None,
        help="Fração de amostragem (ex: 0.1 para 10%%)",
    )

    args = parser.parse_args()

    run_pipeline(
        datasets=args.dataset,
        skip_correlation=args.skip_corr,
        correlation_threshold=args.corr_threshold,
        sample_fraction=args.sample,
    )


if __name__ == "__main__":
    main()
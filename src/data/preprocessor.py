"""
Módulo de pré-processamento dos datasets.

Responsável por:
- Limpeza de valores inválidos (NaN, infinitos, negativos impossíveis)
- Remoção de colunas identificadoras e redundantes
- Normalização de features numéricas
- Codificação de variáveis categóricas
- Mapeamento de rótulos para categorias unificadas

Cada dataset tem seus problemas específicos, então existem funções
dedicadas para cada um antes da unificação final.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from src.utils.logger import get_logger
from src import config

logger = get_logger(__name__)


# Pré-processamento do CIC-IDS2017

def preprocess_cic(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline de limpeza do CIC-IDS2017.

    Problemas conhecidos deste dataset:
    1. Colunas com espaços no nome (já tratado no loader)
    2. Valores infinitos em 'Flow Bytes/s' e 'Flow Packets/s'
    3. Linhas com NaN em múltiplas colunas
    4. Colunas identificadoras que vazariam informação (IPs, portas, timestamp)
    5. Rótulos com nomes longos e inconsistentes
    """
    logger.info("Pré-processando CIC-IDS2017...")
    df = df.copy()
    n_original = len(df)

    # 1. Remover colunas identificadoras
    cols_to_drop = [c for c in config.CIC_DROP_COLUMNS if c in df.columns]
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)
        logger.info(f"  Removidas {len(cols_to_drop)} colunas identificadoras: {cols_to_drop}")

    # 2. Identificar coluna de rótulo
    label_col = _find_label_column(df, ["Label"])
    if label_col is None:
        raise ValueError("Coluna 'Label' não encontrada no CIC-IDS2017")
    logger.info(f"  Coluna de rótulo: '{label_col}'")

    # 3. Limpar rótulos (strip whitespace)
    df[label_col] = df[label_col].astype(str).str.strip()

    # 4. Substituir infinitos por NaN e depois tratar
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    inf_count = np.isinf(df[num_cols]).sum().sum()
    if inf_count > 0:
        df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
        logger.info(f"  Substituídos {inf_count} valores infinitos por NaN")

    # 5. Remover linhas onde todas as features numéricas são NaN
    all_nan_mask = df[num_cols].isna().all(axis=1)
    if all_nan_mask.any():
        df = df[~all_nan_mask]
        logger.info(f"  Removidas {all_nan_mask.sum()} linhas completamente vazias")

    # 6. Preencher NaN restantes com a mediana de cada coluna
    nan_count = df[num_cols].isna().sum().sum()
    if nan_count > 0:
        for col in num_cols:
            if df[col].isna().any():
                median_val = df[col].median()
                df[col] = df[col].fillna(median_val)
        logger.info(f"  Preenchidos {nan_count} valores NaN com mediana")

    # 7. Remover valores negativos em colunas que não podem ser negativas
    #    (duração, contadores de pacotes/bytes)
    non_negative_patterns = ["Fwd", "Bwd", "Flow", "Total", "Avg", "Max", "Min", "Std"]
    for col in num_cols:
        if any(p in col for p in non_negative_patterns):
            neg_count = (df[col] < 0).sum()
            if neg_count > 0:
                df[col] = df[col].clip(lower=0)
                logger.info(f"  Clipados {neg_count} valores negativos em '{col}'")

    # 8. Mapear rótulos para categorias unificadas
    df["label_original"] = df[label_col]
    df["label"] = df[label_col].map(config.CIC_LABEL_MAP)
    unmapped = df["label"].isna().sum()
    if unmapped > 0:
        unknown_labels = df.loc[df["label"].isna(), label_col].unique()
        logger.warning(f"  {unmapped} registros com rótulos desconhecidos: {unknown_labels}")
        df["label"] = df["label"].fillna("Unknown")

    if label_col != "label":
        df.drop(columns=[label_col], inplace=True)

    # 9. Adicionar coluna de origem
    df["dataset_source"] = "CIC-IDS2017"

    logger.info(
        f"  CIC-IDS2017 pré-processado: {n_original} → {len(df)} registros, "
        f"{len(df.columns)} colunas"
    )
    _log_label_distribution(df, "CIC-IDS2017")

    return df


# Pré-processamento do UNSW-NB15

def preprocess_unsw(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline de limpeza do UNSW-NB15.

    Problemas conhecidos deste dataset:
    1. Coluna 'attack_cat' com espaços e inconsistências de capitalização
    2. Coluna 'label' é binária (0/1), precisamos da 'attack_cat' para tipo
    3. Colunas 'srcip', 'sport', 'dstip', 'dsport' são identificadores
    4. Algumas features categóricas (proto, service, state) precisam encoding
    5. Valores '-' em campos numéricos
    """
    logger.info("Pré-processando UNSW-NB15...")
    df = df.copy()
    n_original = len(df)

    # 1. Remover colunas identificadoras
    cols_to_drop = [c for c in config.UNSW_DROP_COLUMNS if c in df.columns]
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)
        logger.info(f"  Removidas {len(cols_to_drop)} colunas identificadoras: {cols_to_drop}")

    # 2. Identificar colunas de rótulo
    attack_col = _find_label_column(df, ["attack_cat", "Attack_cat", "attack_category"])
    binary_label_col = _find_label_column(df, ["label", "Label"])

    if attack_col:
        # Nos arquivos numerados (1-4), attack_cat é NaN para tráfego normal.
        # Precisamos usar a coluna binária 'label' para resolver:
        #   attack_cat=NaN + label=0 → "Normal"
        #   attack_cat=NaN + label=1 → mantém (raro, mas possível)
        is_null = df[attack_col].isna()

        if binary_label_col and is_null.any():
            is_benign = is_null & (df[binary_label_col] == 0)
            is_attack_no_cat = is_null & (df[binary_label_col] == 1)
            df.loc[is_benign, attack_col] = "Normal"
            df.loc[is_attack_no_cat, attack_col] = "Attack"
            logger.info(
                f"  Rótulos resolvidos via coluna binária: "
                f"{is_benign.sum()} Normal, {is_attack_no_cat.sum()} Attack sem categoria"
            )

        # Limpar: strip whitespace
        df[attack_col] = df[attack_col].astype(str).str.strip()
        # Tratar valores residuais vazios
        df.loc[df[attack_col].isin(["", " ", "nan", "None", "<NA>"]), attack_col] = "Normal"
        logger.info(f"  Coluna de tipo de ataque: '{attack_col}'")
    elif binary_label_col:
        logger.warning("  'attack_cat' não encontrada, usando 'label' binário")
        df["attack_cat"] = df[binary_label_col].map({0: "Normal", 1: "Attack"})
        attack_col = "attack_cat"
    else:
        raise ValueError("Nenhuma coluna de rótulo encontrada no UNSW-NB15")

    # 3. Forçar conversão numérica em colunas que deveriam ser número
    #    Nos arquivos numerados, colunas como 'ct_ftp_cmd' podem ter
    #    valores mistos (string '0' junto com int 0). Parquet não aceita
    #    tipos mistos, então forçamos a conversão sempre.
    meta_cols = [attack_col, "proto", "service", "state", binary_label_col]
    meta_cols = [c for c in meta_cols if c]
    converted_count = 0
    for col in df.columns:
        if col in meta_cols:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].replace("-", np.nan)
            df[col] = pd.to_numeric(df[col], errors="coerce")
            converted_count += 1
    if converted_count > 0:
        logger.info(f"  {converted_count} colunas convertidas para numérico")

    # 4. Codificar variáveis categóricas nominais
    categorical_cols = ["proto", "service", "state"]
    existing_cat = [c for c in categorical_cols if c in df.columns]
    if existing_cat:
        df = _encode_categoricals(df, existing_cat)
        logger.info(f"  Codificadas {len(existing_cat)} variáveis categóricas: {existing_cat}")

    # 5. Tratar infinitos e NaN nas numéricas
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    inf_count = np.isinf(df[num_cols]).sum().sum()
    if inf_count > 0:
        df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
        logger.info(f"  Substituídos {inf_count} valores infinitos")

    nan_count = df[num_cols].isna().sum().sum()
    if nan_count > 0:
        for col in num_cols:
            if df[col].isna().any():
                df[col] = df[col].fillna(df[col].median())
        logger.info(f"  Preenchidos {nan_count} valores NaN com mediana")

    # 6. Mapear rótulos para categorias unificadas
    df["label_original"] = df[attack_col]
    df["label"] = df[attack_col].map(config.UNSW_LABEL_MAP)
    unmapped = df["label"].isna().sum()
    if unmapped > 0:
        unknown_labels = df.loc[df["label"].isna(), attack_col].unique()
        logger.warning(f"  {unmapped} registros com rótulos desconhecidos: {unknown_labels}")
        df["label"] = df["label"].fillna("Unknown")

    # Remover colunas de rótulo originais (manter só 'label' unificado)
    for col in [attack_col, binary_label_col]:
        if col and col in df.columns and col != "label":
            df.drop(columns=[col], inplace=True)

    # 7. Adicionar coluna de origem
    df["dataset_source"] = "UNSW-NB15"

    logger.info(
        f"  UNSW-NB15 pré-processado: {n_original} → {len(df)} registros, "
        f"{len(df.columns)} colunas"
    )
    _log_label_distribution(df, "UNSW-NB15")

    return df


# Normalização (aplicada após unificação)

def normalize_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Normaliza features numéricas usando Min-Max scaling para [0, 1].

    Retorna o DataFrame normalizado e um dicionário com os parâmetros
    de normalização (min, max) para cada coluna, necessário para
    aplicar a mesma transformação em dados novos.

    Escolha do Min-Max sobre Z-score:
    - Mantém os valores em range interpretável [0, 1]
    - Não assume distribuição normal dos dados (tráfego de rede raramente é normal)
    - Compatível com a conversão textual posterior (estágio 3 do pipeline)
    """
    logger.info("Normalizando features numéricas...")
    df = df.copy()

    # Colunas que NÃO devem ser normalizadas
    exclude = ["label", "label_original", "dataset_source"]
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in exclude
    ]

    norm_params = {}
    for col in num_cols:
        col_min = df[col].min()
        col_max = df[col].max()
        norm_params[col] = {"min": float(col_min), "max": float(col_max)}

        if col_max - col_min > 0:
            df[col] = (df[col] - col_min) / (col_max - col_min)
        else:
            # Coluna constante → todos os valores viram 0
            df[col] = 0.0

    logger.info(f"  {len(num_cols)} colunas normalizadas para [0, 1]")

    return df, norm_params


# Funções auxiliares

def remove_high_correlation(df: pd.DataFrame, threshold: float = 0.95) -> pd.DataFrame:
    """
    Remove uma de cada par de colunas com correlação acima do threshold.

    Em datasets de tráfego de rede é comum ter features altamente
    correlacionadas (ex: 'Fwd Packet Length Mean' vs 'Avg Fwd Segment Size').
    Removê-las reduz dimensionalidade sem perda de informação significativa.
    """
    logger.info(f"Removendo features com correlação > {threshold}...")

    exclude = ["label", "label_original", "dataset_source"]
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in exclude
    ]

    if len(num_cols) < 2:
        return df

    corr_matrix = df[num_cols].corr().abs()

    # Pegar triângulo superior (sem diagonal)
    upper = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    )

    # Encontrar colunas com correlação alta
    to_drop = [col for col in upper.columns if any(upper[col] > threshold)]

    if to_drop:
        df = df.drop(columns=to_drop)
        logger.info(f"  Removidas {len(to_drop)} colunas altamente correlacionadas")
    else:
        logger.info("  Nenhuma coluna removida")

    return df


def remove_constant_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove colunas com variância zero (valor constante em todas as linhas)."""
    exclude = ["label", "label_original", "dataset_source"]
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in exclude
    ]

    constant_cols = [c for c in num_cols if df[c].nunique() <= 1]

    if constant_cols:
        df = df.drop(columns=constant_cols)
        logger.info(f"  Removidas {len(constant_cols)} colunas constantes: {constant_cols}")

    return df


def _encode_categoricals(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Codifica variáveis categóricas com LabelEncoder.

    Para o escopo deste projeto, LabelEncoder é suficiente porque:
    - As variáveis categóricas (proto, service, state) são nominais com cardinalidade moderada
    - O consumo principal é pelo LLM (via descrição textual), não por um modelo ML tradicional
    - One-hot encoding explodiria a dimensionalidade sem benefício claro
    """
    for col in columns:
        if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))
    return df


def _find_label_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Busca uma coluna de rótulo por nome (case-insensitive)."""
    col_map = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in col_map:
            return col_map[name.lower()]
    return None


def _log_label_distribution(df: pd.DataFrame, name: str):
    """Loga a distribuição de rótulos."""
    dist = df["label"].value_counts()
    logger.info(f"  Distribuição de rótulos ({name}):")
    for label, count in dist.items():
        pct = 100 * count / len(df)
        logger.info(f"    {label}: {count} ({pct:.1f}%)")
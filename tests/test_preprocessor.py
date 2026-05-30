"""
Testes do pipeline de pré-processamento.

Usa dados sintéticos que simulam a estrutura real dos datasets
para validar cada etapa do pipeline sem precisar dos CSVs originais.

Rodar: pytest tests/test_preprocessor.py -v
"""

import numpy as np
import pandas as pd
import pytest

from src.data.preprocessor import (
    preprocess_cic,
    preprocess_unsw,
    normalize_features,
    remove_constant_columns,
    remove_high_correlation,
)


# Fixtures: dados sintéticos que imitam cada dataset


@pytest.fixture
def fake_cic_df():
    """Simula um DataFrame CIC-IDS2017 com problemas conhecidos."""
    np.random.seed(42)
    n = 200
    return pd.DataFrame({
        "Flow ID": [f"flow_{i}" for i in range(n)],
        "Source IP": [f"192.168.1.{i % 255}" for i in range(n)],
        "Source Port": np.random.randint(1024, 65535, n),
        "Destination IP": [f"10.0.0.{i % 255}" for i in range(n)],
        "Destination Port": np.random.choice([80, 443, 22, 8080], n),
        "Timestamp": pd.date_range("2017-07-03", periods=n, freq="s").astype(str),
        "Flow Duration": np.random.exponential(10000, n),
        "Total Fwd Packets": np.random.randint(1, 1000, n),
        "Total Backward Packets": np.random.randint(0, 500, n),
        "Flow Bytes/s": np.concatenate([
            np.random.exponential(50000, n - 3),
            [np.inf, -np.inf, np.nan],  # problemas conhecidos
        ]),
        "Flow Packets/s": np.random.exponential(100, n),
        "Fwd Packet Length Mean": np.concatenate([
            np.random.exponential(500, n - 2),
            [-5, -10],  # valores negativos impossíveis
        ]),
        "Label": np.random.choice(
            ["BENIGN", "DDoS", "PortScan", "Bot", "FTP-Patator"],
            n,
            p=[0.6, 0.15, 0.1, 0.1, 0.05],
        ),
    })


@pytest.fixture
def fake_unsw_df():
    """Simula um DataFrame UNSW-NB15 com problemas conhecidos."""
    np.random.seed(42)
    n = 150
    return pd.DataFrame({
        "srcip": [f"192.168.1.{i % 255}" for i in range(n)],
        "sport": np.random.randint(1024, 65535, n),
        "dstip": [f"10.0.0.{i % 255}" for i in range(n)],
        "dsport": np.random.choice([80, 443, 22], n),
        "proto": np.random.choice(["tcp", "udp", "icmp"], n),
        "service": np.random.choice(["http", "dns", "ssh", "-", "ftp"], n),
        "state": np.random.choice(["FIN", "CON", "INT", "REQ"], n),
        "dur": np.random.exponential(1.0, n),
        "sbytes": np.random.randint(0, 100000, n),
        "dbytes": np.random.randint(0, 50000, n),
        "sttl": np.random.randint(30, 255, n),
        "dttl": np.random.randint(30, 255, n),
        "ct_srv_src": np.random.randint(1, 50, n),
        "attack_cat": np.random.choice(
            ["Normal", "DoS", "Exploits", "Fuzzers", "Reconnaissance", " ", "Generic"],
            n,
            p=[0.5, 0.1, 0.1, 0.1, 0.05, 0.05, 0.1],
        ),
        "label": np.random.choice([0, 1], n, p=[0.5, 0.5]),
    })


# Testes: CIC-IDS2017


class TestCICPreprocessing:

    def test_removes_identifier_columns(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        for col in ["Flow ID", "Source IP", "Destination IP", "Timestamp"]:
            assert col not in result.columns, f"Coluna identificadora '{col}' não foi removida"

    def test_no_infinities(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        num_cols = result.select_dtypes(include=[np.number]).columns
        assert not np.isinf(result[num_cols]).any().any(), "Valores infinitos restantes"

    def test_no_nans_in_numeric(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        num_cols = result.select_dtypes(include=[np.number]).columns
        assert not result[num_cols].isna().any().any(), "NaN restantes em colunas numéricas"

    def test_labels_mapped(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        assert "label" in result.columns
        assert "Unknown" not in result["label"].values, "Rótulos não mapeados encontrados"

    def test_preserves_original_label(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        assert "label_original" in result.columns

    def test_has_dataset_source(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        assert "dataset_source" in result.columns
        assert (result["dataset_source"] == "CIC-IDS2017").all()

    def test_negative_values_clipped(self, fake_cic_df):
        result = preprocess_cic(fake_cic_df)
        fwd_col = "Fwd Packet Length Mean"
        if fwd_col in result.columns:
            assert (result[fwd_col] >= 0).all(), "Valores negativos não foram clipados"


# Testes: UNSW-NB15


class TestUNSWPreprocessing:

    def test_removes_identifier_columns(self, fake_unsw_df):
        result = preprocess_unsw(fake_unsw_df)
        for col in ["srcip", "sport", "dstip", "dsport"]:
            assert col not in result.columns, f"Coluna identificadora '{col}' não foi removida"

    def test_categoricals_encoded(self, fake_unsw_df):
        result = preprocess_unsw(fake_unsw_df)
        for col in ["proto", "service", "state"]:
            if col in result.columns:
                assert result[col].dtype in [np.int64, np.int32, np.float64], \
                    f"'{col}' não foi codificada"

    def test_labels_mapped(self, fake_unsw_df):
        result = preprocess_unsw(fake_unsw_df)
        assert "label" in result.columns
        # Espaços na attack_cat devem virar "Benign" (mapeados de "Normal")
        assert "Unknown" not in result["label"].values or result["label"].value_counts().get("Unknown", 0) == 0

    def test_has_dataset_source(self, fake_unsw_df):
        result = preprocess_unsw(fake_unsw_df)
        assert (result["dataset_source"] == "UNSW-NB15").all()

    def test_no_nans(self, fake_unsw_df):
        result = preprocess_unsw(fake_unsw_df)
        num_cols = result.select_dtypes(include=[np.number]).columns
        assert not result[num_cols].isna().any().any()


# Testes: Utilidades


class TestNormalization:

    def test_values_in_range(self):
        df = pd.DataFrame({
            "a": [1, 2, 3, 4, 5],
            "b": [10, 20, 30, 40, 50],
            "label": ["A", "B", "A", "B", "A"],
        })
        result, params = normalize_features(df)
        assert result["a"].min() == pytest.approx(0.0)
        assert result["a"].max() == pytest.approx(1.0)
        assert result["b"].min() == pytest.approx(0.0)
        assert result["b"].max() == pytest.approx(1.0)

    def test_constant_column_becomes_zero(self):
        df = pd.DataFrame({
            "a": [5, 5, 5, 5],
            "label": ["X", "X", "X", "X"],
        })
        result, _ = normalize_features(df)
        assert (result["a"] == 0.0).all()

    def test_params_returned(self):
        df = pd.DataFrame({"a": [0, 10], "label": ["X", "Y"]})
        _, params = normalize_features(df)
        assert "a" in params
        assert params["a"]["min"] == 0.0
        assert params["a"]["max"] == 10.0


class TestCorrelationRemoval:

    def test_removes_highly_correlated(self):
        df = pd.DataFrame({
            "a": [1, 2, 3, 4, 5],
            "b": [2, 4, 6, 8, 10],  # perfeitamente correlacionado com a
            "c": [5, 3, 1, 4, 2],   # não correlacionado
            "label": ["X"] * 5,
        })
        result = remove_high_correlation(df, threshold=0.95)
        # Uma de a/b deve ter sido removida
        assert len(result.columns) < len(df.columns)

    def test_keeps_uncorrelated(self):
        np.random.seed(42)
        df = pd.DataFrame({
            "a": np.random.randn(100),
            "b": np.random.randn(100),
            "label": ["X"] * 100,
        })
        result = remove_high_correlation(df, threshold=0.95)
        assert "a" in result.columns and "b" in result.columns


class TestConstantRemoval:

    def test_removes_constant_columns(self):
        df = pd.DataFrame({
            "a": [1, 1, 1, 1],
            "b": [1, 2, 3, 4],
            "label": ["X"] * 4,
        })
        result = remove_constant_columns(df)
        assert "a" not in result.columns
        assert "b" in result.columns

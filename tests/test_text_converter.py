"""Testes do módulo text_converter."""

import pandas as pd
import pytest

from src.llm.text_converter import record_to_text, _fmt_bytes, _fmt_time, _fmt_rate


def _cic_record(**kwargs) -> pd.Series:
    base = {
        "dataset_source": "CIC-IDS2017",
        "Protocol": 6,
        "Flow Duration": 1500000,  # microseconds
        "Total Fwd Packets": 7,
        "Total Backward Packets": 3,
        "Total Length of Fwd Packets": 1024,
        "Min Packet Length": 64,
        "Max Packet Length": 512,
        "Packet Length Mean": 200,
        "Flow Bytes/s": 682.6,
        "Flow Packets/s": 6.6,
        "SYN Flag Count": 1,
        "FIN Flag Count": 1,
        "RST Flag Count": 0,
        "PSH Flag Count": 0,
        "ACK Flag Count": 5,
        "ECE Flag Count": 0,
        "CWE Flag Count": 0,
        "Init_Win_bytes_forward": 65535,
    }
    base.update(kwargs)
    return pd.Series(base)


def _unsw_record(**kwargs) -> pd.Series:
    base = {
        "dataset_source": "UNSW-NB15",
        "proto": 6,
        "service": 4,
        "state": 1,
        "dur": 0.5,
        "sbytes": 2048,
        "dbytes": 512,
        "Spkts": 8,
        "Sload": 32768.0,
        "Dload": 8192.0,
        "smeansz": 256,
        "sttl": 64,
        "dttl": 128,
    }
    base.update(kwargs)
    return pd.Series(base)


class TestRecordToText:
    def test_cic_returns_string(self):
        text = record_to_text(_cic_record())
        assert isinstance(text, str)
        assert len(text) > 20

    def test_cic_contains_protocol(self):
        text = record_to_text(_cic_record(protocol=6))
        assert "TCP" in text

    def test_cic_icmp_protocol(self):
        text = record_to_text(_cic_record(**{"Protocol": 1}))
        assert "ICMP" in text

    def test_cic_ack_flag_correct(self):
        text = record_to_text(_cic_record(**{"ACK Flag Count": 5, "ECE Flag Count": 0}))
        assert "ACK" in text

    def test_cic_ece_only_when_present(self):
        text = record_to_text(_cic_record(**{"ACK Flag Count": 0, "ECE Flag Count": 2}))
        assert "ECE" in text

    def test_unsw_returns_string(self):
        text = record_to_text(_unsw_record())
        assert isinstance(text, str)
        assert len(text) > 20

    def test_unsw_contains_protocol(self):
        text = record_to_text(_unsw_record(proto=6))
        assert "TCP" in text

    def test_generic_fallback(self):
        rec = pd.Series({"col_a": 1.5, "col_b": 100, "label": "Benign"})
        text = record_to_text(rec)
        assert isinstance(text, str)
        assert "col_a" in text or "col_b" in text


class TestFormatters:
    def test_fmt_bytes_zero(self):
        assert _fmt_bytes(0) == "0 bytes"

    def test_fmt_bytes_kb(self):
        assert "KB" in _fmt_bytes(2048)

    def test_fmt_bytes_mb(self):
        assert "MB" in _fmt_bytes(2 * 1024 * 1024)

    def test_fmt_time_instant(self):
        assert _fmt_time(0) == "instantânea"

    def test_fmt_time_ms(self):
        assert "ms" in _fmt_time(0.5)

    def test_fmt_time_seconds(self):
        assert "s" in _fmt_time(10.0)

    def test_fmt_time_minutes(self):
        assert "min" in _fmt_time(120.0)

    def test_fmt_rate_zero(self):
        assert _fmt_rate(0) == "0"

    def test_fmt_rate_kilo(self):
        assert "K" in _fmt_rate(5000)

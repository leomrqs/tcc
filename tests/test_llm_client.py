"""Testes do módulo llm_client (parsing JSON, sem chamar Ollama)."""

import pytest

from src.llm.llm_client import parse_json_response, _find_json_block, _clean_json


class TestParseJsonResponse:
    def test_valid_json(self):
        result = parse_json_response('{"attack_type": "DDoS", "confidence": 0.9}')
        assert result == {"attack_type": "DDoS", "confidence": 0.9}

    def test_json_with_preamble(self):
        raw = 'Aqui está minha análise:\n{"attack_type": "Benign", "severity": "low"}\n'
        result = parse_json_response(raw)
        assert result is not None
        assert result["attack_type"] == "Benign"

    def test_json_with_trailing_text(self):
        raw = '{"confidence": 0.5} Isso conclui minha análise.'
        result = parse_json_response(raw)
        assert result is not None
        assert result["confidence"] == 0.5

    def test_trailing_comma_cleaned(self):
        raw = '{"attack_type": "DoS", "severity": "high",}'
        result = parse_json_response(raw)
        assert result is not None
        assert result["attack_type"] == "DoS"

    def test_empty_string(self):
        assert parse_json_response("") is None

    def test_none_input(self):
        assert parse_json_response(None) is None

    def test_no_json_in_text(self):
        assert parse_json_response("Sem JSON aqui, só texto.") is None

    def test_nested_json(self):
        raw = '{"outer": {"inner": 1}, "value": 2}'
        result = parse_json_response(raw)
        assert result["value"] == 2
        assert result["outer"]["inner"] == 1


class TestFindJsonBlock:
    def test_simple(self):
        assert _find_json_block('{"a": 1}') == '{"a": 1}'

    def test_with_prefix(self):
        assert _find_json_block('prefix {"a": 1} suffix') == '{"a": 1}'

    def test_no_json(self):
        assert _find_json_block("no json here") is None

    def test_nested_braces(self):
        s = '{"a": {"b": 2}}'
        assert _find_json_block(s) == s


class TestCleanJson:
    def test_removes_trailing_comma_before_brace(self):
        cleaned = _clean_json('{"a": 1,}')
        assert cleaned == '{"a": 1}'

    def test_removes_trailing_comma_before_bracket(self):
        cleaned = _clean_json('{"a": [1, 2,]}')
        assert cleaned == '{"a": [1, 2]}'

    def test_no_change_when_clean(self):
        s = '{"a": 1}'
        assert _clean_json(s) == s

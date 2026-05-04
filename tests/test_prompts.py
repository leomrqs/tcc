"""Testes do módulo prompts."""

import pytest

from src.llm.prompts import (
    validate_triage_output,
    build_user_prompt,
    VALID_ATTACK_TYPES,
    VALID_SEVERITY,
)


VALID_OUTPUT = {
    "attack_type": "DDoS",
    "severity": "high",
    "confidence": 0.87,
    "mitre_techniques": ["T1498", "T1499"],
    "explanation": "O fluxo apresenta padrões de inundação volumétrica.",
    "recommendations": ["Ativar rate limiting", "Notificar NOC"],
}


class TestValidateTriageOutput:
    def test_valid_output_passes(self):
        ok, errors = validate_triage_output(VALID_OUTPUT)
        assert ok
        assert errors == []

    def test_missing_attack_type(self):
        data = {**VALID_OUTPUT}
        del data["attack_type"]
        ok, errors = validate_triage_output(data)
        assert not ok
        assert any("attack_type" in e for e in errors)

    def test_invalid_attack_type(self):
        data = {**VALID_OUTPUT, "attack_type": "MegaHack"}
        ok, errors = validate_triage_output(data)
        assert not ok
        assert any("attack_type" in e for e in errors)

    def test_invalid_severity(self):
        data = {**VALID_OUTPUT, "severity": "extreme"}
        ok, errors = validate_triage_output(data)
        assert not ok
        assert any("severity" in e for e in errors)

    def test_confidence_out_of_range(self):
        data = {**VALID_OUTPUT, "confidence": 1.5}
        ok, errors = validate_triage_output(data)
        assert not ok

    def test_confidence_negative(self):
        data = {**VALID_OUTPUT, "confidence": -0.1}
        ok, errors = validate_triage_output(data)
        assert not ok

    def test_mitre_not_list(self):
        data = {**VALID_OUTPUT, "mitre_techniques": "T1498"}
        ok, errors = validate_triage_output(data)
        assert not ok

    def test_empty_mitre_list_is_valid(self):
        data = {**VALID_OUTPUT, "mitre_techniques": []}
        ok, errors = validate_triage_output(data)
        assert ok

    def test_missing_explanation(self):
        data = {**VALID_OUTPUT}
        del data["explanation"]
        ok, errors = validate_triage_output(data)
        assert not ok

    def test_not_dict(self):
        ok, errors = validate_triage_output("not a dict")
        assert not ok

    def test_all_valid_attack_types_accepted(self):
        for attack in VALID_ATTACK_TYPES:
            data = {**VALID_OUTPUT, "attack_type": attack}
            ok, _ = validate_triage_output(data)
            assert ok, f"Attack type '{attack}' deveria ser válido"

    def test_all_valid_severities_accepted(self):
        for sev in VALID_SEVERITY:
            data = {**VALID_OUTPUT, "severity": sev}
            ok, _ = validate_triage_output(data)
            assert ok, f"Severity '{sev}' deveria ser válida"


class TestBuildUserPrompt:
    def test_contains_description(self):
        prompt = build_user_prompt("Fluxo TCP suspeito", "contexto RAG aqui")
        assert "Fluxo TCP suspeito" in prompt

    def test_contains_rag_context(self):
        prompt = build_user_prompt("desc", "contexto importante")
        assert "contexto importante" in prompt

    def test_empty_rag_shows_fallback(self):
        prompt = build_user_prompt("desc", "")
        assert "nenhum contexto" in prompt.lower()

    def test_returns_string(self):
        assert isinstance(build_user_prompt("a", "b"), str)

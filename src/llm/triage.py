"""
Orquestrador de triagem (v2 — two-stage + pré-classificador opcional).

Pipeline:
1. Recebe um registro pré-processado
2. Converte em descrição textual discriminativa (text_converter v2)
3. [Opcional] Pre-screening com Random Forest — Benign de alta confiança skipa o LLM
4. STAGE 1 (LLM rápido): BENIGN vs THREAT
5. Se BENIGN, retorna imediatamente
6. STAGE 2 (LLM completo): RAG + categoria detalhada + JSON estruturado
"""

import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

from src.llm.text_converter import record_to_text
from src.llm.llm_client import OllamaClient, parse_json_response
from src.llm.prompts import (
    SYSTEM_PROMPT,
    STAGE1_SYSTEM_PROMPT,
    build_user_prompt,
    build_stage1_prompt,
    validate_triage_output,
)
from src.rag.retriever import Retriever
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ════════════════════════════════════════════════════════════════
# Normalização de attack_type
# ════════════════════════════════════════════════════════════════

_ATTACK_TYPE_MAP = {
    # Exact valid values
    "benign": "Benign", "dos": "DoS", "ddos": "DDoS",
    "brute force": "Brute Force", "bruteforce": "Brute Force",
    "botnet": "Botnet", "reconnaissance": "Reconnaissance",
    "web attack": "Web Attack", "exploits": "Exploits",
    "fuzzers": "Fuzzers", "backdoor": "Backdoor",
    "generic": "Generic", "analysis": "Analysis",
    "shellcode": "Shellcode", "worms": "Worms", "infiltration": "Infiltration",
    # Common model aliases
    "command and control": "Botnet", "c2": "Botnet", "c2 communication": "Botnet",
    "c&c": "Botnet", "malware": "Botnet",
    "suspicious_activity": "Generic", "suspicious activity": "Generic",
    "network activity": "Generic", "network": "Generic",
    "network traffic analysis": "Analysis",
    "port scan": "Reconnaissance", "scanning": "Reconnaissance",
    "scan": "Reconnaissance", "probe": "Reconnaissance",
    "sql injection": "Web Attack", "xss": "Web Attack",
    "reverse shell": "Exploits", "potential reverse shell activity": "Exploits",
    "exploit": "Exploits", "exploitation": "Exploits",
    "brute-force": "Brute Force", "password attack": "Brute Force",
    "credential stuffing": "Brute Force",
    "denial of service": "DoS", "denial-of-service": "DoS",
    "distributed denial of service": "DDoS",
    "syn flood": "DDoS", "udp flood": "DDoS", "icmp flood": "DDoS",
    "exfiltration": "Generic", "data exfiltration": "Generic",
    "fuzz": "Fuzzers", "fuzzing": "Fuzzers",
    "normal": "Benign", "legitimate": "Benign", "clean": "Benign",
    "benign traffic": "Benign", "no attack": "Benign",
}

def _normalize_attack_type(raw: str) -> str:
    """Mapeia a saída livre do modelo para uma categoria válida."""
    if not raw:
        return "Generic"
    key = raw.strip().lower()
    if key in _ATTACK_TYPE_MAP:
        return _ATTACK_TYPE_MAP[key]
    # Substring matching como fallback
    for k, v in _ATTACK_TYPE_MAP.items():
        if k in key:
            return v
    return "Generic"


# ════════════════════════════════════════════════════════════════
# TriageResult
# ════════════════════════════════════════════════════════════════

@dataclass
class TriageResult:
    """Resultado completo de uma triagem."""
    attack_type: str
    severity: str
    confidence: float
    mitre_techniques: list[str]
    explanation: str
    recommendations: list[str]

    # Metadados
    record_description: str = ""
    retrieved_context_titles: list[str] = field(default_factory=list)
    rag_distances: list[float] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    model_name: str = ""

    # Rastreabilidade
    ground_truth: Optional[str] = None
    raw_llm_response: str = ""
    validation_errors: list[str] = field(default_factory=list)

    # Metadados two-stage
    stage1_decision: Optional[str] = None
    stage_skipped: Optional[str] = None  # "rf_prefilter" ou "stage1_benign"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0


# ════════════════════════════════════════════════════════════════
# Engine de triagem
# ════════════════════════════════════════════════════════════════

class TriageEngine:
    """
    Orquestrador completo do pipeline de triagem v2.

    Suporta:
    - Pre-classificador Random Forest (opcional, --use-rf)
    - Two-stage LLM (opcional, --two-stage)
    - RAG com cross-encoder re-ranking (configurável no Retriever)
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        llm_client: Optional[OllamaClient] = None,
        rag_top_k: int = 5,
        rag_max_tokens: int = 1500,
        rag_distance_threshold: float = 0.55,
        use_rag: bool = True,
        use_two_stage: bool = False,  # opt-in (Foundation-Sec-8B é instável no binário)
        rf_classifier=None,  # PreClassifier opcional
        rf_confidence_threshold: float = 0.95,
    ):
        self.use_rag = use_rag
        self.rag_top_k = rag_top_k
        self.rag_max_tokens = rag_max_tokens
        self.rag_distance_threshold = rag_distance_threshold
        self.use_two_stage = use_two_stage
        self.rf_classifier = rf_classifier
        self.rf_confidence_threshold = rf_confidence_threshold

        if use_rag:
            self.retriever = retriever or Retriever()
        else:
            self.retriever = None
            logger.info("Modo SEM RAG (baseline)")

        self.llm_client = llm_client or OllamaClient()

        if not self.llm_client.health_check():
            logger.warning(
                f"⚠ Ollama não está respondendo em {self.llm_client.host}. "
                f"Inicie o Ollama antes de rodar triagens."
            )
        elif not self.llm_client.model_available():
            logger.warning(
                f"⚠ Modelo '{self.llm_client.model}' não disponível no Ollama."
            )

        if self.rf_classifier is not None:
            logger.info(f"Pre-classificador RF ativo (threshold={rf_confidence_threshold})")
        if self.use_two_stage:
            logger.info("Two-stage classification ativo")

    # ────────────────────────────────────────────────────────────
    # Triagem de um único registro
    # ────────────────────────────────────────────────────────────

    def triage_record(self, record: pd.Series) -> TriageResult:
        t_start = time.time()

        # 1. Descrição textual
        description = record_to_text(record)
        logger.info(f"  [DESCRIÇÃO] {description[:200]}{'...' if len(description) > 200 else ''}")

        # 2. Pre-classificador RF (se ativo)
        if self.rf_classifier is not None:
            rf_pred, rf_conf = self.rf_classifier.predict(record)
            logger.info(f"  [RF] predição={rf_pred} conf={rf_conf:.3f}")
            if rf_pred == "Benign" and rf_conf >= self.rf_confidence_threshold:
                logger.info(f"  [RF] Skip LLM — Benign de alta confiança ({rf_conf:.3f})")
                return self._build_skip_result(
                    description, attack_type="Benign",
                    confidence=rf_conf, source="rf_prefilter",
                    elapsed=time.time() - t_start,
                    ground_truth=record.get("label"),
                )

        # 3. STAGE 1 (binário) — se two-stage ativo
        stage1_decision = None
        if self.use_two_stage:
            try:
                stage1_response = self.llm_client.generate(
                    prompt=build_stage1_prompt(description),
                    system=STAGE1_SYSTEM_PROMPT,
                    temperature=0.0,
                    max_tokens=10,
                    structured_output=False,  # raw text, sem schema
                )
                stage1_decision = stage1_response.strip().upper()
                # Pega só a primeira palavra
                stage1_decision = stage1_decision.split()[0] if stage1_decision else "THREAT"
                stage1_decision = "BENIGN" if "BENIGN" in stage1_decision else "THREAT"
                logger.info(f"  [STAGE 1] {stage1_decision}")

                if stage1_decision == "BENIGN":
                    return self._build_skip_result(
                        description, attack_type="Benign",
                        confidence=0.75, source="stage1_benign",
                        elapsed=time.time() - t_start,
                        ground_truth=record.get("label"),
                        stage1_decision=stage1_decision,
                    )
            except Exception as e:
                logger.warning(f"  [STAGE 1] Erro: {e} — caindo para stage 2 direto")
                stage1_decision = "ERROR"

        # 4. RAG (se habilitado)
        rag_results = []
        rag_context = ""
        if self.use_rag and self.retriever is not None:
            rag_results = self.retriever.search(
                query=description, top_k=self.rag_top_k
            )
            titles = [r["title"] for r in rag_results]
            dists = [f"{r['distance']:.3f}" for r in rag_results]
            logger.info(f"  [RAG] {len(rag_results)} docs recuperados:")
            for t, d in zip(titles[:3], dists[:3]):
                logger.info(f"        • {t} (dist={d})")

            # Usa distância densa (não a do rerank) para filtro de qualidade —
            # o threshold 0.55 foi calibrado em distâncias densas.
            # rag_results[0] é o melhor APÓS rerank, mas tem dense_distance preservada.
            best_dense = min(
                (r.get("dense_distance", r["distance"]) for r in rag_results),
                default=1.0,
            )
            if best_dense <= self.rag_distance_threshold:
                rag_context = self.retriever.format_context(
                    rag_results, max_tokens=self.rag_max_tokens
                )
            else:
                logger.info(
                    f"  [RAG] Contexto descartado (best dense={best_dense:.3f} > {self.rag_distance_threshold})"
                )

        # 5. STAGE 2 — categoria detalhada
        user_prompt = build_user_prompt(description, rag_context)
        logger.info(f"  [STAGE 2] Enviando para o modelo ({self.llm_client.model})...")

        raw_response = ""
        try:
            raw_response = self.llm_client.generate(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1024,
            )
            logger.info(f"  [STAGE 2] Resposta recebida ({len(raw_response)} chars)")
        except Exception as e:
            logger.error(f"  [STAGE 2] ERRO: {e}")
            return self._build_error_result(
                description, rag_results,
                error_msg=f"LLM falhou: {e}",
                elapsed=time.time() - t_start,
                ground_truth=record.get("label"),
                stage1_decision=stage1_decision,
            )

        # 6. Parsear JSON
        parsed = parse_json_response(raw_response)
        if parsed is None:
            logger.warning("  [PARSE] LLM não retornou JSON parseável")
            return self._build_error_result(
                description, rag_results,
                error_msg="resposta do LLM não é JSON válido",
                elapsed=time.time() - t_start,
                raw_response=raw_response,
                ground_truth=record.get("label"),
                stage1_decision=stage1_decision,
            )

        # 7. Normalizar
        raw_conf = float(parsed.get("confidence", 0.0))
        parsed["confidence"] = raw_conf / 100.0 if raw_conf > 1.0 else raw_conf
        parsed["attack_type"] = _normalize_attack_type(parsed.get("attack_type", "Generic"))
        parsed["severity"] = parsed.get("severity", "informational").lower()

        cleaned_mitre = []
        for t in parsed.get("mitre_techniques", []) or []:
            m = re.search(r"T\d{4}(?:\.\d{3})?", str(t))
            if m:
                cleaned_mitre.append(m.group(0))
        parsed["mitre_techniques"] = cleaned_mitre

        # 8. Validar
        is_valid, errors = validate_triage_output(parsed)
        if not is_valid:
            logger.warning(f"  [VALIDAÇÃO] Campos inválidos: {errors}")

        return TriageResult(
            attack_type=parsed["attack_type"],
            severity=parsed["severity"],
            confidence=parsed["confidence"],
            mitre_techniques=list(parsed.get("mitre_techniques", [])),
            explanation=str(parsed.get("explanation", "")),
            recommendations=list(parsed.get("recommendations", [])),
            record_description=description,
            retrieved_context_titles=[r["title"] for r in rag_results],
            rag_distances=[r["distance"] for r in rag_results],
            elapsed_seconds=round(time.time() - t_start, 2),
            model_name=self.llm_client.model,
            ground_truth=record.get("label"),
            raw_llm_response=raw_response,
            validation_errors=errors,
            stage1_decision=stage1_decision,
        )

    # ────────────────────────────────────────────────────────────
    # Triagem em lote
    # ────────────────────────────────────────────────────────────

    def triage_batch(self, df: pd.DataFrame) -> list[TriageResult]:
        results = []
        n = len(df)
        sep = "─" * 60
        mode_tags = []
        if self.use_rag: mode_tags.append("RAG")
        if self.use_two_stage: mode_tags.append("2STAGE")
        if self.rf_classifier is not None: mode_tags.append("RF")
        mode = "+".join(mode_tags) if mode_tags else "BASELINE"

        logger.info(f"\n{sep}")
        logger.info(f"TRIAGEM EM LOTE: {n} registros | Modo: {mode} | Modelo: {self.llm_client.model}")
        logger.info(sep)

        for i, (_, row) in enumerate(df.iterrows(), 1):
            pct = 100 * i / n
            gt = row.get("label", "?")
            src = row.get("dataset_source", "?")
            logger.info(f"\n{'='*60}")
            logger.info(f"[{i}/{n}] ({pct:.0f}%) — ground truth: {gt} | fonte: {src}")

            result = self.triage_record(row)
            results.append(result)

            elapsed_total = sum(r.elapsed_seconds for r in results)
            avg_time = elapsed_total / len(results)
            remaining = avg_time * (n - i)

            status = "✓ VÁLIDO" if result.is_valid else "⚠ INVÁLIDO"
            logger.info(f"  [RESULTADO] {status}")
            logger.info(f"  → attack_type : {result.attack_type}")
            logger.info(f"  → severity    : {result.severity}")
            logger.info(f"  → confidence  : {result.confidence:.2f}")
            logger.info(f"  → MITRE       : {', '.join(result.mitre_techniques) or '(nenhum)'}")
            logger.info(f"  → ground truth: {result.ground_truth}")
            match = "✓ ACERTO" if (
                result.ground_truth and result.attack_type and
                result.attack_type.lower() == (result.ground_truth or "").lower()
            ) else "✗ ERRO"
            logger.info(f"  → match       : {match}")
            logger.info(f"  → tempo       : {result.elapsed_seconds:.1f}s | média: {avg_time:.1f}s | restante: ~{remaining:.0f}s")

        logger.info(f"\n{sep}")
        logger.info(f"LOTE CONCLUÍDO: {n} registros em {sum(r.elapsed_seconds for r in results):.0f}s")
        logger.info(sep)
        return results

    # ────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────

    def _build_skip_result(
        self, description: str, attack_type: str, confidence: float,
        source: str, elapsed: float, ground_truth: Optional[str] = None,
        stage1_decision: Optional[str] = None,
    ) -> TriageResult:
        explanation_map = {
            "rf_prefilter": "Random Forest classificou como Benign de alta confiança — LLM pulado.",
            "stage1_benign": "Stage 1 (LLM binário) classificou como BENIGN — Stage 2 pulado.",
        }
        return TriageResult(
            attack_type=attack_type,
            severity="informational",
            confidence=confidence,
            mitre_techniques=[],
            explanation=explanation_map.get(source, f"Skipped via {source}"),
            recommendations=[],
            record_description=description,
            retrieved_context_titles=[],
            rag_distances=[],
            elapsed_seconds=round(elapsed, 2),
            model_name=self.llm_client.model,
            ground_truth=ground_truth,
            raw_llm_response="",
            validation_errors=[],
            stage1_decision=stage1_decision,
            stage_skipped=source,
        )

    def _build_error_result(
        self, description: str, rag_results: list[dict],
        error_msg: str, elapsed: float, raw_response: str = "",
        ground_truth: Optional[str] = None,
        stage1_decision: Optional[str] = None,
    ) -> TriageResult:
        return TriageResult(
            attack_type="Unknown",
            severity="informational",
            confidence=0.0,
            mitre_techniques=[],
            explanation=f"[FALHA] {error_msg}",
            recommendations=[],
            record_description=description,
            retrieved_context_titles=[r["title"] for r in rag_results],
            rag_distances=[r["distance"] for r in rag_results],
            elapsed_seconds=round(elapsed, 2),
            model_name=self.llm_client.model,
            ground_truth=ground_truth,
            raw_llm_response=raw_response,
            validation_errors=[error_msg],
            stage1_decision=stage1_decision,
        )

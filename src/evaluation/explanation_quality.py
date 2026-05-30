"""
Avaliação automática da QUALIDADE DAS EXPLICAÇÕES geradas pelo LLM.

A triagem explicada é o diferencial do projeto, mas até aqui só a classificação
era medida — não a explicação em si. Este módulo fornece um proxy automático
(complementar à avaliação humana planejada) com sub-scores objetivos:

- validade MITRE: as técnicas citadas (T####) existem no ATT&CK e estão no
  formato correto? (detecta alucinação de técnicas inexistentes)
- relevância: a explicação menciona os sinais reais do registro (protocolo,
  flags, taxa, forma do fluxo)?
- estrutura: a explicação tem corpo suficiente, não truncado, com recomendações?
- consistência: severidade coerente com o tipo de ataque, confiança em [0,1],
  texto coerente com a categoria predita?
- ancoragem (grounding): a explicação se apoia no contexto RAG recuperado?

Cada sub-score vai de 0 a 1; o composto é a média ponderada. É um indicador de
triagem, não um juízo definitivo de correção técnica.

Uso:
    python -m src.evaluation.explanation_quality outputs/triage_runs/run_.../results.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from src import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_MITRE_ID_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
_MITRE_SOURCE = config.DATA_DIR / "rag" / "sources" / "enterprise-attack.json"
_MITRE_CACHE = config.DATA_DIR / "rag" / "mitre_technique_ids.json"

_BENIGN = {"benign", "normal", "background"}
_LOW_SEV = {"informational", "low"}

# Sinais discriminativos que esperamos ver referenciados numa boa explicação.
_SIGNAL_TERMS = {
    "syn", "ack", "fin", "rst", "psh", "urg", "tcp", "udp", "icmp", "http",
    "flood", "scan", "probe", "handshake", "payload", "beacon", "beaconing",
    "exfiltra", "unidirec", "simétric", "simetric", "porta", "port", "pacote",
    "packet", "fluxo", "flow", "duração", "duration", "taxa", "rate", "bytes",
    "brute", "ddos", "dos", "reconnaissance", "botnet", "exploit", "backdoor",
}


def load_valid_mitre_ids() -> set[str] | None:
    """Conjunto de IDs de técnicas MITRE válidos (com cache). None se indisponível."""
    if _MITRE_CACHE.exists():
        try:
            return set(json.loads(_MITRE_CACHE.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not _MITRE_SOURCE.exists():
        logger.warning("MITRE STIX não encontrado — validação MITRE só por formato.")
        return None
    logger.info("Extraindo IDs de técnicas MITRE do STIX (uma vez, será cacheado)...")
    data = json.loads(_MITRE_SOURCE.read_text(encoding="utf-8"))
    ids = set()
    for obj in data.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                ext = ref.get("external_id", "")
                if _MITRE_ID_RE.fullmatch(ext):
                    ids.add(ext)
    _MITRE_CACHE.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    logger.info(f"  {len(ids)} técnicas MITRE cacheadas em {_MITRE_CACHE.name}")
    return ids


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zá-ú]{3,}", str(text).lower()))


def score_record(record: dict, valid_mitre: set[str] | None) -> dict:
    """Calcula os sub-scores de qualidade da explicação de um registro."""
    explanation = str(record.get("explanation", "")).strip()
    recs = record.get("recommendations", []) or []
    attack = str(record.get("attack_type", "")).strip().lower()
    severity = str(record.get("severity", "")).strip().lower()
    confidence = record.get("confidence", 0.0)
    desc = str(record.get("record_description", ""))
    titles = " ".join(record.get("retrieved_context_titles", []) or [])
    cited = _MITRE_ID_RE.findall(explanation + " " + " ".join(str(t) for t in record.get("mitre_techniques", []) or []))
    cited = list(dict.fromkeys(cited))  # únicos, preservando ordem
    is_benign = attack in _BENIGN

    # 1. Estrutura
    structure = 0.0
    if explanation:
        structure += 0.5 if len(explanation) >= 60 else len(explanation) / 120
        if not explanation.endswith((",", "(", "-")) and explanation[-1:] in ".!?\"'" or len(explanation) >= 60:
            structure += 0.25
    if len(recs) >= 1:
        structure += 0.25
    structure = min(structure, 1.0)

    # 2. Validade MITRE
    if not cited:
        mitre_validity = 1.0 if is_benign else 0.4  # benigno pode não citar técnica
    else:
        fmt_ok = [c for c in cited if _MITRE_ID_RE.fullmatch(c)]
        if valid_mitre is not None:
            valid = [c for c in cited if c.split(".")[0] in valid_mitre or c in valid_mitre]
            mitre_validity = len(valid) / len(cited)
        else:
            mitre_validity = len(fmt_ok) / len(cited)

    # 3. Relevância: sobreposição com descrição do registro + termos de sinal
    exp_tok = _tokens(explanation)
    desc_tok = _tokens(desc)
    overlap = len(exp_tok & desc_tok)
    signal_hits = sum(1 for s in _SIGNAL_TERMS if s in explanation.lower())
    relevance = min(1.0, 0.5 * min(overlap / 8.0, 1.0) + 0.5 * min(signal_hits / 4.0, 1.0))

    # 4. Consistência
    consistency = 1.0
    try:
        c = float(confidence)
        if not (0.0 <= c <= 1.0):
            consistency -= 0.3
    except (TypeError, ValueError):
        consistency -= 0.3
    if is_benign and severity not in _LOW_SEV and severity:
        consistency -= 0.3  # benigno deveria ser baixa severidade
    if (not is_benign) and severity in _LOW_SEV:
        consistency -= 0.2  # ameaça com severidade muito baixa é incoerente
    # menção da categoria predita no texto
    if attack and attack not in _BENIGN and attack.split()[0] not in explanation.lower():
        consistency -= 0.1
    consistency = max(0.0, consistency)

    # 5. Ancoragem no RAG (neutro se não houve contexto)
    if titles.strip():
        title_tok = _tokens(titles)
        grounding = 1.0 if (exp_tok & title_tok) or any(c in titles for c in cited) else 0.4
    else:
        grounding = None  # não penaliza ausência de RAG

    parts = {
        "structure": round(structure, 3),
        "mitre_validity": round(mitre_validity, 3),
        "relevance": round(relevance, 3),
        "consistency": round(consistency, 3),
    }
    weights = {"structure": 0.2, "mitre_validity": 0.3, "relevance": 0.3, "consistency": 0.2}
    if grounding is not None:
        parts["grounding"] = round(grounding, 3)
        weights = {"structure": 0.15, "mitre_validity": 0.25, "relevance": 0.25,
                   "consistency": 0.15, "grounding": 0.2}
    composite = sum(parts[k] * weights[k] for k in parts)

    return {
        **parts,
        "composite": round(composite, 3),
        "mitre_cited": cited,
        "mitre_invalid": [c for c in cited if valid_mitre is not None
                          and c.split(".")[0] not in valid_mitre and c not in valid_mitre],
    }


def evaluate_results(results: list[dict]) -> dict:
    """Aplica o scoring a uma lista de registros e agrega."""
    valid_mitre = load_valid_mitre_ids()
    # só registros que passaram pelo LLM (têm explicação real)
    scored = [r for r in results if str(r.get("explanation", "")).strip()
              and not r.get("stage_skipped")]
    per = [score_record(r, valid_mitre) for r in scored]
    if not per:
        return {"n_explained": 0}

    def avg(key):
        vals = [p[key] for p in per if key in p]
        return round(float(np.mean(vals)), 4) if vals else None

    all_invalid = [m for p in per for m in p["mitre_invalid"]]
    return {
        "n_explained": len(per),
        "composite_mean": avg("composite"),
        "composite_std": round(float(np.std([p["composite"] for p in per])), 4),
        "structure_mean": avg("structure"),
        "mitre_validity_mean": avg("mitre_validity"),
        "relevance_mean": avg("relevance"),
        "consistency_mean": avg("consistency"),
        "grounding_mean": avg("grounding"),
        "n_mitre_invalid": len(all_invalid),
        "mitre_invalid_examples": list(dict.fromkeys(all_invalid))[:10],
        "per_record": per,
    }


def analyze_run(results_path: Path) -> dict:
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    results = data.get("results", data if isinstance(data, list) else [])
    report = evaluate_results(results)
    out = Path(results_path).parent / "explanation_quality.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Avalia a qualidade das explicações da triagem")
    parser.add_argument("path", help="results.json ou pasta da run")
    args = parser.parse_args()
    rp = Path(args.path)
    if rp.is_dir():
        rp = rp / "results.json"
    report = analyze_run(rp)
    if report.get("n_explained", 0) == 0:
        print("Nenhuma explicação para avaliar (todos pulados pelo pré-filtro?).")
        return
    print(f"Explicações avaliadas: {report['n_explained']}")
    print(f"  Score composto:   {report['composite_mean']:.3f} ± {report['composite_std']:.3f}")
    print(f"  Estrutura:        {report['structure_mean']:.3f}")
    print(f"  Validade MITRE:   {report['mitre_validity_mean']:.3f}")
    print(f"  Relevância:       {report['relevance_mean']:.3f}")
    print(f"  Consistência:     {report['consistency_mean']:.3f}")
    if report.get("grounding_mean") is not None:
        print(f"  Ancoragem RAG:    {report['grounding_mean']:.3f}")
    print(f"  Técnicas MITRE inválidas citadas: {report['n_mitre_invalid']}")


if __name__ == "__main__":
    main()

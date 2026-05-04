"""
Templates de prompts para o LLM de triagem.

Estratégia v2 (chain-of-thought + few-shot):
- System prompt define um PROTOCOLO DE RACIOCÍNIO explícito
- Inclui 6 exemplos canônicos cobrindo: Benign, DDoS, DoS, Reconnaissance,
  Brute Force, Exploits, Exfiltração
- Cada exemplo tem reasoning antes da decisão
- Define explicitamente quando classificar como Benign (resolve TN=0)
"""

# ════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Stage 2 (categoria detalhada)
# ════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a senior network security analyst doing real-time triage of network flows.

Your input is a structured network flow description with categorical labels (FLOOD/HIGH/MODERATE/LOW for rates, INSTANT/SHORT/MEDIUM/LONG for duration, UNIDIRECIONAL/EXFILTRACAO/DOWNLOAD/SIMETRICO for shape) plus heuristic signature hints.

# REASONING PROTOCOL (think through these steps internally before answering):

Step 1 — Read the FORMA DO FLUXO:
  - SIMÉTRICO + payload + standard service → likely Benign
  - UNIDIRECIONAL → scan, drop, or one-way attack
  - EXFILTRAÇÃO → data theft (Generic/Infiltration)
  - HANDSHAKE-ONLY → port scan or probe (Reconnaissance)

Step 2 — Read TAXA DE PACOTES:
  - FLOOD (>1000 pkt/s) → DDoS volumétrico
  - ALTA (>100 pkt/s) → DoS, brute force, or aggressive scan
  - MODERADA → normal traffic or slow attack
  - BAIXA/QUASE ZERO → reconnaissance, beaconing, or idle

Step 3 — Read DURAÇÃO:
  - INSTANT (<10ms) + UNIDIRECIONAL → single-shot exploit or probe
  - SHORT + brute force pattern → Brute Force attempt
  - LONG + low rate + symmetric → C2 beaconing (Botnet) or persistent tunnel
  - VERY LONG + unidirectional → idle scan or stuck connection

Step 4 — Cross-reference ASSINATURAS DETECTADAS hints (they encode known patterns).

Step 5 — Apply BENIGN rule: classify as Benign if AT LEAST 2 of these hold:
  - SIMÉTRICO flow shape
  - MODERATE rate (1-100 pkt/s)
  - Duration between 0.5s and 5min
  - Has actual payload (>100B)
  - Standard service (HTTP, DNS, SSH, HTTPS, etc.)
  - "✓ PADRÃO Benigno provável" signature is present

# OUTPUT FORMAT:

Return ONLY a JSON object with these EXACT keys:
- "attack_type": one of [Benign, DoS, DDoS, Brute Force, Botnet, Reconnaissance, Web Attack, Exploits, Fuzzers, Backdoor, Generic, Analysis, Shellcode, Worms, Infiltration]
- "severity": one of [informational, low, medium, high, critical]
- "confidence": float 0.0-1.0 (NOT a percentage)
- "mitre_techniques": array of MITRE IDs like ["T1498"] (just IDs, no descriptions)
- "explanation": 1-3 sentences explaining your reasoning, citing the categorical labels
- "recommendations": array of action strings

# CANONICAL EXAMPLES:

## Example 1 — DDoS volumétrico
Input contains: "TAXA DE PACOTES: FLOOD (5000 pkt/s)" + "DURAÇÃO: SHORT" + "FLAGS TCP: SYN=5000" + "ASSINATURAS DETECTADAS: ⚠ ASSINATURA SYN flood"
Reasoning: FLOOD rate + SYN-only + no response = textbook SYN flood DDoS
Output: {"attack_type": "DDoS", "severity": "critical", "confidence": 0.95, "mitre_techniques": ["T1498", "T1498.001"], "explanation": "FLOOD rate of 5000 pkt/s with SYN-only flags indicates a SYN flood DDoS attack — connection table exhaustion attempt.", "recommendations": ["Enable SYN cookies", "Rate-limit at edge", "Engage DDoS mitigation provider"]}

## Example 2 — Reconnaissance (port scan)
Input contains: "FORMA DO FLUXO: HANDSHAKE-ONLY" + "DURAÇÃO: INSTANT" + "VOLUME: 1 pkt fwd, 0 pkt bwd" + "PADRÃO DE FLAGS: SYN-only"
Reasoning: Single SYN, no response, instant duration = active port probe
Output: {"attack_type": "Reconnaissance", "severity": "low", "confidence": 0.85, "mitre_techniques": ["T1046", "T1595.001"], "explanation": "Single SYN packet with no response and INSTANT duration is classic SYN scanning behavior, mapping open ports without completing handshake.", "recommendations": ["Block source IP if not authorized", "Review firewall logs for scan source"]}

## Example 3 — Benign HTTPS
Input contains: "FORMA DO FLUXO: SIMÉTRICO (razão fwd/bwd=0.45)" + "TAXA DE PACOTES: MODERADA (15 pkt/s)" + "DURAÇÃO: MEDIUM (4.2s)" + "✓ PADRÃO Benigno provável"
Reasoning: SIMÉTRICO + MODERATE rate + MEDIUM duration + benign signature → routine HTTPS session
Output: {"attack_type": "Benign", "severity": "informational", "confidence": 0.85, "mitre_techniques": [], "explanation": "Symmetric flow with moderate rate over 4.2s matches normal HTTPS browsing — bidirectional payload exchange consistent with benign client traffic.", "recommendations": []}

## Example 4 — Brute Force (SSH/FTP password attack)
Input contains: "DURAÇÃO: SHORT (~1-5s)" + "TAXA DE PACOTES: ALTA" + "FORMA DO FLUXO: SIMÉTRICO" + "SERVIÇO: SSH ou FTP" + "CONEXÕES PRÉVIAS no mesmo state/TTL: ≥5"
Reasoning: Short bursts of repeated SSH/FTP connections from same source = credential stuffing
Output: {"attack_type": "Brute Force", "severity": "high", "confidence": 0.85, "mitre_techniques": ["T1110", "T1110.001"], "explanation": "Repeated short connections to authentication service with multiple prior connections indicates credential brute force attempt.", "recommendations": ["Lock source IP at firewall", "Enable account lockout policy", "Force password rotation if any account succeeded"]}

## Example 5 — Exfiltration (Generic data theft)
Input contains: "FORMA DO FLUXO: EXFILTRAÇÃO (envia ~150x mais que recebe)" + "TAXA DE BYTES: ALTA" + "DURAÇÃO: LONG" + "SERVIÇO: FTP/HTTP"
Reasoning: Sustained one-way large upload to outside = data exfiltration via standard protocol
Output: {"attack_type": "Generic", "severity": "high", "confidence": 0.8, "mitre_techniques": ["T1041", "T1048"], "explanation": "EXFILTRACAO flow shape with ALTA byte rate over LONG duration on FTP indicates sustained data exfiltration.", "recommendations": ["Quarantine source host", "Inspect uploaded payload via DLP", "Audit accessed files on source"]}

## Example 6 — DoS application-layer
Input contains: "TAXA DE PACOTES: ALTA (200 pkt/s)" + "DURAÇÃO: LONG" + "FORMA DO FLUXO: UNIDIRECIONAL" + "TAMANHO PKT: pequenos" + "SERVIÇO: HTTP"
Reasoning: Sustained moderate-high rate over long duration with no response = slow HTTP DoS (Slowloris-like)
Output: {"attack_type": "DoS", "severity": "high", "confidence": 0.8, "mitre_techniques": ["T1499", "T1499.002"], "explanation": "ALTA rate sustained over LONG duration without server response on HTTP indicates application-layer DoS, exhausting server worker threads.", "recommendations": ["Tune connection timeouts", "Deploy WAF with rate-limiting", "Scale backend horizontally"]}

## Example 7 — Exploit/Shellcode (small UNSW flow, NOT DDoS)
Input contains: "FLUXO protocolo 122 (UNSW-NB15)" + "DURAÇÃO: INSTANT (10μs)" + "TAXA DE PACOTES: INDETERMINADA (200K pkt/s instantânea — fluxo curto demais)" + "VOLUME: 2 pkts src→dst (754B)" + "ANOMALIA: protocolo desconhecido com duração instantânea — possível Exploit ou Fuzzer"
Reasoning: VOLUME is tiny (2 packets) so the instantaneous rate label is INDETERMINADA — NOT a real flood. Non-standard protocol + INSTANT + payload of 754B suggests a single weaponized packet — classic Exploit or Shellcode delivery, NOT DDoS.
Output: {"attack_type": "Exploits", "severity": "high", "confidence": 0.75, "mitre_techniques": ["T1190", "T1210"], "explanation": "Single 754-byte packet to non-standard protocol 122 with INSTANT duration matches exploit attempt signature — NOT a volumetric attack despite high instantaneous rate (only 2 packets).", "recommendations": ["Block protocol 122 at perimeter", "Investigate source IP", "Review IDS for related CVEs"]}

## Example 8 — Fuzzer (small UNSW flow with malformed pattern)
Input contains: "FLUXO protocolo 117" + "DURAÇÃO: INSTANT" + "VOLUME: 2 pkts src→dst (78B)" + "ANOMALIA: protocolo desconhecido com duração instantânea — possível Exploit ou Fuzzer" + "ESTADO: REQ (request only)"
Reasoning: 2-packet INSTANT flow on undefined protocol with no response — likely automated random-input testing. Tiny payload suggests random byte pattern rather than weaponized exploit.
Output: {"attack_type": "Fuzzers", "severity": "medium", "confidence": 0.7, "mitre_techniques": ["T1190", "T1133"], "explanation": "Tiny single-shot packet to non-standard protocol 117 with REQ-only state matches automated fuzzing pattern testing edge cases.", "recommendations": ["Block protocol 117 if not legitimate", "Inspect payload for malformed structures"]}

# CRITICAL DISCRIMINATION RULES (memorize these):

## DDoS vs DoS vs Reconnaissance — the most confused triplet:

DDoS = SUSTAINED FLOOD rate (>1000 pkt/s) over LONG/MEDIUM duration with MANY packets (>100).
  → If "FLOOD" label is INDETERMINADA or BURST (only because the flow is microseconds long with 2 packets), it is NOT DDoS.
  → DDoS requires real volume sustained — see VOLUME line.

DoS = ALTA rate (100-1000 pkt/s) sustained for LONG duration, often unidirectional, application-layer.
  → Slowloris is the exception: LOW rate + VERY LONG + UNIDIRECIONAL on HTTP.

Reconnaissance = small probes — typically 1-5 packets per flow, INSTANT/SHORT duration.
  → SYN scan: single SYN, no response, multiple destinations.
  → ACK scan: single ACK, no response.
  → A flow with 2 packets and INSTANT duration is almost ALWAYS Reconnaissance OR Exploit, NOT DDoS.

## When VOLUME is small (≤5 packets) but rate looks high (FLOOD/ALTA):
Trust the VOLUME, not the instantaneous rate. The label "INDETERMINADA" or "BURST" tells you the rate is artifact.
- Single packet to UDP/non-standard port → Exploit or Fuzzer
- Single SYN → Reconnaissance
- Single packet with payload to FTP/HTTP → Brute Force probe or Exploit attempt

## UNSW protocol numbers ≥100 (95, 117, 120, 122, etc):
These are non-standard / experimental protocols. Combined with INSTANT duration and UNIDIRECIONAL,
they typically indicate Exploits, Fuzzers, Shellcode, Backdoor — NOT DDoS.

# OUTPUT RULES:

1. confidence MUST be a float between 0.0 and 1.0 (NOT 70 — use 0.7).
2. mitre_techniques MUST contain ONLY IDs (e.g. "T1498"), never with descriptions.
3. ALWAYS consider Benign — if SIMÉTRICO + MODERATE + standard service, lean Benign.
4. NEVER default to DDoS for fluxos minúsculos (≤5 pkts, INSTANT duration). Look at VOLUME.
5. The categorical labels (FLOOD, HIGH, INDETERMINADA, BURST, etc.) and ⚠ signatures are PRE-COMPUTED — trust them.
6. If uncertain between Reconnaissance and Exploits for a small unidirectional flow:
   - Has SYN flag only → Reconnaissance
   - Has payload (>50B) and goes to non-standard port → Exploits
   - Has malformed-looking traffic → Fuzzers"""


# ════════════════════════════════════════════════════════════════
# USER PROMPT TEMPLATE
# ════════════════════════════════════════════════════════════════

USER_PROMPT_TEMPLATE = """# NETWORK FLOW TO TRIAGE:

{record_description}

# REFERENCE CONTEXT (relevant attack patterns from knowledge base):

{rag_context}

Apply the REASONING PROTOCOL from your system prompt and return the JSON triage object.
Remember: trust the categorical labels and ⚠ signatures — they encode pre-analyzed evidence."""


# ════════════════════════════════════════════════════════════════
# Stage 1 prompt — binary triage (Benign vs Threat)
# ════════════════════════════════════════════════════════════════

STAGE1_SYSTEM_PROMPT = """You are a CONSERVATIVE network triage filter. Your job: decide BENIGN or THREAT.

# CRITICAL: The default answer is THREAT. Only output BENIGN if you have STRONG positive evidence.

# OUTPUT BENIGN only if ALL of these hold simultaneously:
  1. FORMA DO FLUXO is SIMÉTRICO (NOT UNIDIRECIONAL, NOT HANDSHAKE-ONLY, NOT EXFILTRAÇÃO)
  2. TAXA DE PACOTES is MODERADA (between 1 and 100 pkt/s, NOT BAIXA, NOT QUASE ZERO)
  3. TAXA DE BYTES is at least MODERADA (NOT ZERO, NOT QUASE ZERO)
  4. DURAÇÃO is MEDIUM (between 0.5s and 5min)
  5. The flow has REAL PAYLOAD in both directions (visible in VOLUME line, both fwd and bwd > 0 bytes)
  6. EITHER "✓ PADRÃO Benigno" signature is present, OR the service is a standard one (HTTP, HTTPS, DNS, SSH, SMTP)

# OUTPUT THREAT immediately if ANY of these hold:
  - "⚠" signature is present in description
  - FORMA DO FLUXO is UNIDIRECIONAL or HANDSHAKE-ONLY (no response = scan/attack)
  - FORMA DO FLUXO is EXFILTRAÇÃO (data theft)
  - TAXA DE PACOTES is FLOOD or ALTA (volumetric attack)
  - VOLUME shows fwd_bytes=0 or bwd_bytes=0 (no real dialog)
  - Description contains "scan", "flood", "exploit", "probe"
  - Anomaly detected (LAND attack, IPs/ports iguais, TTL=0, etc.)

# Examples:
  - "FORMA: SIMÉTRICO + TAXA: MODERADA + bytes both directions + ⌐MEDIUM duration" → BENIGN
  - "FORMA: UNIDIRECIONAL + 2 pkts fwd, 0 pkts bwd" → THREAT
  - "FORMA: HANDSHAKE-ONLY + ACK only" → THREAT
  - "TAXA: FLOOD" → THREAT (DDoS)
  - "DURAÇÃO: VERY LONG + TAXA: BAIXA + UNIDIRECIONAL" → THREAT (slow scan or stuck)

Output EXACTLY one word: BENIGN or THREAT. Nothing else. When in doubt, output THREAT."""


STAGE1_USER_PROMPT_TEMPLATE = """{record_description}

Decision (BENIGN or THREAT):"""


# ════════════════════════════════════════════════════════════════
# Builders
# ════════════════════════════════════════════════════════════════

def build_user_prompt(record_description: str, rag_context: str) -> str:
    """Monta o prompt do Stage 2 (categoria detalhada)."""
    return USER_PROMPT_TEMPLATE.format(
        record_description=record_description.strip(),
        rag_context=rag_context.strip() if rag_context else "(nenhum contexto recuperado — use apenas as evidências do fluxo)",
    )


def build_stage1_prompt(record_description: str) -> str:
    """Monta o prompt do Stage 1 (binário benigno vs ameaça)."""
    return STAGE1_USER_PROMPT_TEMPLATE.format(
        record_description=record_description.strip(),
    )


# ════════════════════════════════════════════════════════════════
# Validação da saída do LLM
# ════════════════════════════════════════════════════════════════

VALID_ATTACK_TYPES = {
    "Benign", "DoS", "DDoS", "Brute Force", "Botnet", "Reconnaissance",
    "Web Attack", "Exploits", "Fuzzers", "Backdoor", "Generic",
    "Analysis", "Shellcode", "Worms", "Infiltration",
}

VALID_SEVERITY = {"informational", "low", "medium", "high", "critical"}


def validate_triage_output(output: dict) -> tuple[bool, list[str]]:
    """
    Valida a saída do LLM contra o schema esperado.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    if not isinstance(output, dict):
        return False, ["output não é um dicionário"]

    attack = output.get("attack_type")
    if not attack:
        errors.append("campo 'attack_type' ausente")
    elif attack not in VALID_ATTACK_TYPES:
        errors.append(f"attack_type inválido: '{attack}'")

    sev = output.get("severity")
    if not sev:
        errors.append("campo 'severity' ausente")
    elif sev.lower() not in VALID_SEVERITY:
        errors.append(f"severity inválida: '{sev}'")

    conf = output.get("confidence")
    if conf is None:
        errors.append("campo 'confidence' ausente")
    else:
        try:
            cf = float(conf)
            if not (0.0 <= cf <= 1.0):
                errors.append(f"confidence fora do intervalo [0,1]: {cf}")
        except (TypeError, ValueError):
            errors.append(f"confidence não é numérica: {conf}")

    mitre = output.get("mitre_techniques")
    if mitre is None:
        errors.append("campo 'mitre_techniques' ausente")
    elif not isinstance(mitre, list):
        errors.append("mitre_techniques deve ser uma lista")

    exp = output.get("explanation")
    if not exp or not isinstance(exp, str):
        errors.append("explanation ausente ou inválida")

    recs = output.get("recommendations")
    if recs is None:
        errors.append("campo 'recommendations' ausente")
    elif not isinstance(recs, list):
        errors.append("recommendations deve ser uma lista")

    return len(errors) == 0, errors

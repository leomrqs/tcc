"""
Conversão de registros de tráfego de rede em descrição textual discriminativa.

Esse módulo é a ponte entre a Etapa 1 (dados pré-processados) e o
restante do pipeline (RAG + LLM). Ele recebe uma linha do dataset
(um fluxo de rede) e gera uma descrição em linguagem natural.

Estratégia v2 (discriminativa):
- Em vez de listar features brutas ("3 pacotes em 10s"), classifica em
  categorias semânticas: FLOOD/HIGH/MODERATE/LOW para taxa,
  UNIDIRECIONAL/EXFILTRACAO/DOWNLOAD/SIMETRICO para forma do fluxo,
  INSTANT/SHORT/MEDIUM/LONG para duração.
- Inclui pistas heurísticas explícitas ao final (ex: "padrão consistente
  com SYN flood") para ajudar o LLM a discriminar entre categorias
  morfologicamente similares.
- Sempre inclui um veredicto categórico que contextualiza a leitura
  numérica para o LLM.
"""

import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════════
# Mapeamentos auxiliares
# ════════════════════════════════════════════════════════════════

PROTOCOL_NAMES = {
    1: "ICMP",
    6: "TCP",
    17: "UDP",
    47: "GRE",
    50: "ESP",
    51: "AH",
}

# Portas conhecidas para detecção de serviço padrão
COMMON_PORTS = {
    20, 21,   # FTP
    22,       # SSH
    23,       # Telnet
    25,       # SMTP
    53,       # DNS
    80, 8080, # HTTP
    110,      # POP3
    143,      # IMAP
    443, 8443,# HTTPS
    445,      # SMB
    993,      # IMAPS
    995,      # POP3S
    3306,     # MySQL
    3389,     # RDP
    5432,     # PostgreSQL
    6379,     # Redis
}


# ════════════════════════════════════════════════════════════════
# Categorias discriminativas
# ════════════════════════════════════════════════════════════════

def _classify_packet_rate(rate: float, total_pkts: int = None, duration: float = None) -> str:
    """
    Classifica taxa de pacotes em categoria semântica.

    Para fluxos minúsculos (poucos pacotes ou duração sub-segundo), a taxa
    instantânea é um artefato — usa VOLUME como sanity check.
    """
    if rate is None or pd.isna(rate) or rate <= 0:
        return "ZERO (sem fluxo de pacotes)"

    # Sanity check: para classificar FLOOD/ALTA, exigir volume mínimo OU duração mínima
    has_volume = (total_pkts is None) or (total_pkts >= 20)
    has_duration = (duration is None) or (duration >= 0.1)  # 100ms+

    if rate > 1000:
        if not has_volume or not has_duration:
            return f"INDETERMINADA ({_fmt_rate(rate)} pkt/s instantânea — fluxo curto demais para confirmar FLOOD; provável burst único)"
        return f"FLOOD ({_fmt_rate(rate)} pkt/s — típico de DDoS volumétrico sustentado)"
    if rate > 100:
        if not has_volume or not has_duration:
            return f"BURST ({_fmt_rate(rate)} pkt/s instantânea, mas fluxo curto — não sustentada; provável probe ou single shot)"
        return f"ALTA ({_fmt_rate(rate)} pkt/s — típico de DoS, brute force ou scan agressivo)"
    if rate > 10:
        return f"MODERADA ({_fmt_rate(rate)} pkt/s — tráfego normal de aplicação)"
    if rate > 0.1:
        return f"BAIXA ({_fmt_rate(rate)} pkt/s — tráfego idle ou reconnaissance lento)"
    return f"QUASE ZERO ({_fmt_rate(rate)} pkt/s — scan stealth, conexão presa ou fluxo abandonado)"


def _classify_byte_rate(rate: float, total_bytes: float = None, duration: float = None) -> str:
    """
    Classifica taxa de bytes em categoria semântica.

    Mesmo princípio: para fluxos minúsculos, a taxa instantânea é artefato.
    """
    if rate is None or pd.isna(rate) or rate <= 0:
        return "ZERO"

    has_volume = (total_bytes is None) or (total_bytes >= 10_000)  # 10KB+
    has_duration = (duration is None) or (duration >= 0.1)

    if rate > 10_000_000:
        if not has_volume or not has_duration:
            return f"INDETERMINADA ({_fmt_rate(rate)} B/s instantânea — payload total é minúsculo, não é bandwidth attack real)"
        return f"FLOOD ({_fmt_rate(rate)} B/s — bandwidth attack sustentado)"
    if rate > 1_000_000:
        if not has_volume or not has_duration:
            return f"BURST ({_fmt_rate(rate)} B/s instantânea, mas payload pequeno — single packet ou probe)"
        return f"ALTA ({_fmt_rate(rate)} B/s — transferência intensa, possível exfiltração)"
    if rate > 10_000:
        return f"MODERADA ({_fmt_rate(rate)} B/s — uso normal de aplicação)"
    if rate > 100:
        return f"BAIXA ({_fmt_rate(rate)} B/s — controle ou keep-alive)"
    return f"QUASE ZERO ({_fmt_rate(rate)} B/s — sem payload significativo)"


def _classify_duration(seconds: float) -> str:
    """Classifica duração em categoria semântica."""
    if seconds is None or pd.isna(seconds) or seconds <= 0:
        return "INSTANTÂNEA (0s — fluxo único, não estabelecido)"
    s = float(seconds)
    if s < 0.001:
        return f"INSTANT ({_fmt_time(s)} — single packet, possível probe ou single shot exploit)"
    if s < 1:
        return f"SHORT ({_fmt_time(s)} — handshake rápido ou requisição curta)"
    if s < 60:
        return f"MEDIUM ({_fmt_time(s)} — sessão típica de aplicação)"
    if s < 600:
        return f"LONG ({_fmt_time(s)} — conexão persistente ou C2 beaconing)"
    return f"VERY LONG ({_fmt_time(s)} — túnel persistente, lateral movement ou idle TCP)"


def _classify_flow_shape(fwd_pkts, bwd_pkts, fwd_bytes, bwd_bytes) -> str:
    """Classifica forma do fluxo (direcionalidade)."""
    fwd_pkts = int(fwd_pkts or 0)
    bwd_pkts = int(bwd_pkts or 0)
    fwd_bytes = float(fwd_bytes or 0)
    bwd_bytes = float(bwd_bytes or 0)

    if fwd_pkts == 0 and bwd_pkts == 0:
        return "VAZIO (nenhum pacote — fluxo não estabelecido)"

    if bwd_pkts == 0:
        return ("UNIDIRECIONAL (sem resposta do destino — porta fechada, "
                "drop por firewall, scan stealth ou one-way attack/exfiltration)")

    if fwd_pkts == 0:
        return "REVERSO ANÔMALO (apenas tráfego dest→src — possível resposta órfã)"

    # Ambos têm pacotes — analisar bytes
    if fwd_bytes == 0 and bwd_bytes == 0:
        return "HANDSHAKE-ONLY (ACK puros sem payload — scan ou probe)"

    if bwd_bytes == 0:
        return "QUERY (envia dados, recebe só ACK — request sem resposta de dados)"

    if fwd_bytes == 0:
        return "ANSWER (recebe dados sem enviar — comportamento incomum)"

    ratio = fwd_bytes / max(bwd_bytes, 1.0)
    if ratio > 100:
        return f"EXFILTRAÇÃO (envia ~{ratio:.0f}x mais que recebe — upload massivo, data theft)"
    if ratio > 10:
        return f"UPLOAD (envia ~{ratio:.0f}x mais que recebe — POST de payload grande)"
    if ratio < 0.01:
        return f"DOWNLOAD (recebe ~{1/ratio:.0f}x mais que envia — fetch de conteúdo)"
    if ratio < 0.1:
        return f"DOWNLOAD-HEAVY (recebe ~{1/ratio:.0f}x mais — file download)"
    return f"SIMÉTRICO (razão fwd/bwd={ratio:.2f} — diálogo balanceado, sessão normal)"


def _classify_tcp_flag_pattern(rec: pd.Series, source: str) -> str:
    """Identifica padrões clássicos de flags TCP que indicam ataques."""
    if source == "CIC-IDS2017":
        syn = int(rec.get("SYN Flag Count", 0) or 0)
        ack = int(rec.get("ACK Flag Count", 0) or 0)
        fin = int(rec.get("FIN Flag Count", 0) or 0)
        rst = int(rec.get("RST Flag Count", 0) or 0)
        psh = int(rec.get("PSH Flag Count", 0) or 0)
        urg = int(rec.get("URG Flag Count", 0) or 0)
    else:
        return ""

    patterns = []
    if syn > 0 and ack == 0 and fin == 0:
        patterns.append("SYN-only (handshake incompleto — típico de SYN flood ou half-open scan)")
    if ack > 0 and syn == 0 and fin == 0 and psh == 0 and urg == 0:
        patterns.append("ACK-only (sem dados — TCP keep-alive, ACK scan ou conexão idle)")
    if fin == 1 and syn == 0:
        patterns.append("FIN scan (fechamento sem handshake — evasão de IDS)")
    if rst > 0 and syn > 0:
        patterns.append("SYN+RST (rejeição rápida — porta fechada ou RST attack)")
    if urg > 0 and psh > 0 and fin > 0:
        patterns.append("XMAS scan (URG+PSH+FIN — assinatura clássica de port scan)")
    if syn > 0 and ack > 0 and psh > 0:
        patterns.append("SYN+ACK+PSH (handshake + dados — sessão TCP normal estabelecida)")

    return "; ".join(patterns)


def _heuristic_attack_signatures(rec: pd.Series, source: str,
                                  packet_rate: float, byte_rate: float,
                                  duration: float, flow_shape_str: str,
                                  fwd_pkts: int, bwd_pkts: int) -> list[str]:
    """
    Lista assinaturas heurísticas explícitas que casam com este fluxo.
    Ajuda o LLM a discriminar entre categorias morfologicamente similares.
    """
    sigs = []
    total_pkts = (fwd_pkts or 0) + (bwd_pkts or 0)
    is_sustained = (duration is not None) and (duration >= 0.1) and (total_pkts >= 20)

    # SYN Flood / DDoS volumétrico — exige sustentação (não burst único)
    if packet_rate and packet_rate > 1000 and is_sustained:
        sigs.append("⚠ ASSINATURA DDoS volumétrico (FLOOD rate sustentado)")
    if source == "CIC-IDS2017":
        syn = int(rec.get("SYN Flag Count", 0) or 0)
        ack = int(rec.get("ACK Flag Count", 0) or 0)
        if syn > 0 and ack == 0 and bwd_pkts == 0:
            if syn >= 5:
                sigs.append("⚠ ASSINATURA SYN flood (múltiplos SYN sem resposta)")
            else:
                sigs.append("⚠ ASSINATURA SYN scan (single SYN sem resposta — Reconnaissance)")

    # Reconnaissance (scan lento, múltiplos probes)
    if duration and duration > 60 and fwd_pkts <= 5 and bwd_pkts == 0:
        sigs.append("⚠ ASSINATURA Reconnaissance lento (poucos pacotes, longa duração, sem resposta)")

    # Brute Force (muitas conexões curtas para mesma porta — proxy via duration+pkts)
    if duration and 0.1 < duration < 10 and fwd_pkts > 5 and bwd_pkts > 0:
        if source == "CIC-IDS2017":
            psh = int(rec.get("PSH Flag Count", 0) or 0)
            if psh > 0:
                sigs.append("⚠ POSSÍVEL Brute Force (conexão curta com troca de credenciais)")

    # Exfiltração — exige volume real transferido (>100KB) e sustentação
    fwd_bytes_total = float(rec.get("Total Length of Fwd Packets", 0) or rec.get("sbytes", 0) or 0)
    if (fwd_bytes_total > 100_000 and is_sustained and
        fwd_pkts > bwd_pkts * 2 and byte_rate and byte_rate > 100_000):
        sigs.append("⚠ ASSINATURA Exfiltração (upload massivo unidirecional sustentado)")

    # C2 Beaconing (conexão longa, baixo volume, simétrico)
    if duration and duration > 300 and packet_rate and packet_rate < 10:
        if "SIMÉTRICO" in flow_shape_str or "DOWNLOAD" in flow_shape_str:
            sigs.append("⚠ POSSÍVEL Botnet C2 beaconing (sessão longa, baixa taxa, periódica)")

    # Tráfego benigno claro
    if (packet_rate and 1 < packet_rate < 100 and
        duration and 0.5 < duration < 300 and
        ("SIMÉTRICO" in flow_shape_str or "DOWNLOAD" in flow_shape_str)):
        sigs.append("✓ PADRÃO Benigno provável (taxa moderada, simétrica, duração típica de aplicação)")

    return sigs


# ════════════════════════════════════════════════════════════════
# Função pública principal
# ════════════════════════════════════════════════════════════════

def record_to_text(record: pd.Series) -> str:
    """
    Converte um registro de tráfego em descrição textual discriminativa.

    Returns:
        String estruturada com:
        - Identificação do fluxo (protocolo, serviço)
        - Métricas categóricas (FLOOD/HIGH/.../ZERO)
        - Padrões de flags TCP detectados
        - Assinaturas heurísticas que casam
    """
    source = record.get("dataset_source", "")

    if source == "CIC-IDS2017":
        return _cic_record_to_text(record)
    elif source == "UNSW-NB15":
        return _unsw_record_to_text(record)
    else:
        return _generic_record_to_text(record)


def records_to_text_batch(df: pd.DataFrame) -> list[str]:
    """Converte múltiplos registros em descrições, mantendo ordem."""
    return [record_to_text(row) for _, row in df.iterrows()]


# ════════════════════════════════════════════════════════════════
# Conversão CIC-IDS2017
# ════════════════════════════════════════════════════════════════

def _cic_record_to_text(rec: pd.Series) -> str:
    parts = []

    # ── Identificação ──
    proto = _proto_name(rec.get("Protocol"))
    duration_raw = rec.get("Flow Duration", 0)
    # CIC duration vem em microsegundos
    duration = float(duration_raw) / 1e6 if duration_raw and duration_raw > 1000 else float(duration_raw or 0)

    fwd_pkts = int(rec.get("Total Fwd Packets", 0) or 0)
    bwd_pkts = int(rec.get("Total Backward Packets", 0) or 0)
    fwd_bytes = float(rec.get("Total Length of Fwd Packets", 0) or 0)
    bwd_bytes = float(rec.get("Total Length of Bwd Packets", 0) or 0)
    # CIC tem 'Flow Packets/s' / 'Flow Bytes/s' mas eles são computados sobre
    # Flow Duration em microssegundos no dataset original — gera valores absurdos
    # para fluxos curtos. Recomputa a partir de volumes reais.
    total_pkts = fwd_pkts + bwd_pkts
    total_bytes = fwd_bytes + bwd_bytes
    pkt_rate = (total_pkts / duration) if duration > 0 else 0.0
    byte_rate = (total_bytes / duration) if duration > 0 else 0.0

    # Header
    parts.append(f"=== FLUXO {proto} (CIC-IDS2017) ===")

    # ── Métricas categóricas (o coração da nova abordagem) ──
    parts.append(f"DURAÇÃO: {_classify_duration(duration)}")
    parts.append(f"TAXA DE PACOTES: {_classify_packet_rate(pkt_rate, total_pkts, duration)}")
    parts.append(f"TAXA DE BYTES: {_classify_byte_rate(byte_rate, total_bytes, duration)}")
    parts.append(f"FORMA DO FLUXO: {_classify_flow_shape(fwd_pkts, bwd_pkts, fwd_bytes, bwd_bytes)}")

    # ── Volume bruto (referência) ──
    parts.append(
        f"VOLUME: {fwd_pkts} pkts fwd ({_fmt_bytes(fwd_bytes)}) | "
        f"{bwd_pkts} pkts bwd ({_fmt_bytes(bwd_bytes)})"
    )

    # ── Tamanho dos pacotes ──
    pkt_min = rec.get("Min Packet Length", 0)
    pkt_max = rec.get("Max Packet Length", 0)
    pkt_mean = rec.get("Packet Length Mean", 0)
    pkt_std = rec.get("Packet Length Std", 0)
    if pkt_max and pkt_max > 0:
        size_note = ""
        if pkt_max <= 60 and pkt_mean <= 60:
            size_note = " — pacotes pequenos (controle/scan, sem payload real)"
        elif pkt_min == pkt_max:
            size_note = " — todos do mesmo tamanho (assinatura de bot/script)"
        elif pkt_std and pkt_std > pkt_mean:
            size_note = " — alta variância (mistura de controle e dados)"
        parts.append(
            f"TAMANHO PKT: min={int(pkt_min)}, max={int(pkt_max)}, "
            f"média={int(pkt_mean)} bytes{size_note}"
        )

    # ── Flags TCP (com interpretação) ──
    flag_pattern = _classify_tcp_flag_pattern(rec, "CIC-IDS2017")
    raw_flags = _format_tcp_flags_cic_raw(rec)
    if raw_flags:
        parts.append(f"FLAGS TCP: {raw_flags}")
    if flag_pattern:
        parts.append(f"PADRÃO DE FLAGS: {flag_pattern}")

    # ── Janela TCP (indicador de SO/dispositivo) ──
    fwd_win = rec.get("Init_Win_bytes_forward", 0) or 0
    bwd_win = rec.get("Init_Win_bytes_backward", 0) or 0
    if fwd_win > 0:
        win_note = ""
        if fwd_win < 1024:
            win_note = " — janela pequena (raw scan, tcpdump)"
        elif fwd_win > 60000:
            win_note = " — janela ampla (TCP scaling — host moderno)"
        bwd_str = f", bwd={int(bwd_win)}" if bwd_win > 0 else ""
        parts.append(f"JANELA TCP: fwd={int(fwd_win)}{bwd_str}{win_note}")

    # ── Assinaturas heurísticas ──
    flow_shape_str = _classify_flow_shape(fwd_pkts, bwd_pkts, fwd_bytes, bwd_bytes)
    sigs = _heuristic_attack_signatures(
        rec, "CIC-IDS2017", pkt_rate, byte_rate, duration,
        flow_shape_str, fwd_pkts, bwd_pkts
    )
    if sigs:
        parts.append("ASSINATURAS DETECTADAS:")
        for s in sigs:
            parts.append(f"  {s}")

    return "\n".join(parts)


def _format_tcp_flags_cic_raw(rec: pd.Series) -> str:
    """Lista flags TCP observadas com contagens."""
    flag_cols = {
        "SYN": "SYN Flag Count",
        "FIN": "FIN Flag Count",
        "RST": "RST Flag Count",
        "PSH": "PSH Flag Count",
        "ACK": "ACK Flag Count",
        "URG": "URG Flag Count",
        "ECE": "ECE Flag Count",
        "CWR": "CWE Flag Count",
    }
    observed = []
    for flag, col in flag_cols.items():
        count = rec.get(col, 0)
        if count and count > 0:
            observed.append(f"{flag}={int(count)}")
    return ", ".join(observed) if observed else "(nenhuma)"


# ════════════════════════════════════════════════════════════════
# Conversão UNSW-NB15
# ════════════════════════════════════════════════════════════════

UNSW_SERVICE_HINTS = {
    0: "service desconhecido",
    1: "DNS",
    2: "FTP",
    3: "FTP-data",
    4: "HTTP",
    5: "IRC",
    6: "POP3",
    7: "RADIUS",
    8: "SMTP",
    9: "SNMP",
    10: "SSH",
    11: "SSL",
    12: "outro",
}

UNSW_STATE_HINTS = {
    0: "estado desconhecido",
    1: "FIN (encerrado)",
    2: "CON (conectado)",
    3: "INT (interrompido)",
    4: "REQ (requisição)",
    5: "RST (reset)",
    6: "ACC (aceito)",
    7: "CLO (fechado)",
}

UNSW_STATE_INTERPRETATION = {
    1: "conexão fechou normalmente",
    2: "ainda ativa",
    3: "interrompida — RST inesperado, possível scan ou drop",
    4: "apenas request — sem resposta, possível scan",
    5: "RST — porta fechada, drop ou scan rejeitado",
    6: "aceito — handshake completo",
    7: "fechado normalmente",
}


def _unsw_record_to_text(rec: pd.Series) -> str:
    parts = []

    # ── Identificação ──
    proto = _proto_name(rec.get("proto"))
    service_id = int(rec.get("service", 0) or 0)
    state_id = int(rec.get("state", 0) or 0)
    service = UNSW_SERVICE_HINTS.get(service_id, "outro")
    state = UNSW_STATE_HINTS.get(state_id, "desconhecido")
    state_interp = UNSW_STATE_INTERPRETATION.get(state_id, "")

    duration = float(rec.get("dur", 0) or 0)
    sbytes = float(rec.get("sbytes", 0) or 0)
    dbytes = float(rec.get("dbytes", 0) or 0)
    spkts = int(rec.get("Spkts", 0) or 0)
    dpkts = int(rec.get("Dpkts", 0) or 0)
    sload = float(rec.get("Sload", 0) or 0)  # bytes/s source
    dload = float(rec.get("Dload", 0) or 0)

    # Aproximar packet rate total
    total_pkts = spkts + dpkts
    total_bytes = sbytes + dbytes
    pkt_rate = total_pkts / duration if duration > 0 else 0
    byte_rate = total_bytes / duration if duration > 0 else 0

    # Header
    parts.append(f"=== FLUXO {proto} (UNSW-NB15) ===")
    parts.append(f"SERVIÇO: {service} | ESTADO: {state} ({state_interp})")

    # ── Métricas categóricas ──
    parts.append(f"DURAÇÃO: {_classify_duration(duration)}")
    parts.append(f"TAXA DE PACOTES: {_classify_packet_rate(pkt_rate, total_pkts, duration)}")
    parts.append(f"TAXA DE BYTES: {_classify_byte_rate(byte_rate, total_bytes, duration)}")
    parts.append(f"FORMA DO FLUXO: {_classify_flow_shape(spkts, dpkts, sbytes, dbytes)}")

    # ── Volume bruto ──
    parts.append(
        f"VOLUME: {spkts} pkts src→dst ({_fmt_bytes(sbytes)}) | "
        f"{dpkts} pkts dst→src ({_fmt_bytes(dbytes)})"
    )

    # ── Carga (load) ──
    if sload > 0 or dload > 0:
        parts.append(f"BPS: src={_fmt_rate(sload)}, dst={_fmt_rate(dload)}")

    # ── Tamanho médio do pacote ──
    smean = rec.get("smeansz", 0)
    dmean = rec.get("dmeansz", 0)
    if smean or dmean:
        parts.append(f"TAMANHO MÉDIO PKT: src={int(smean or 0)}B, dst={int(dmean or 0)}B")

    # ── TTL (indica SO/distância) ──
    sttl = int(rec.get("sttl", 0) or 0)
    dttl = int(rec.get("dttl", 0) or 0)
    if sttl > 0 or dttl > 0:
        ttl_note = ""
        if dttl == 0 and sttl > 0:
            ttl_note = " — destino TTL=0 sugere drop, scan stealth ou ataque sem resposta"
        elif sttl == 254 or sttl == 255:
            ttl_note = " — TTL inicial alto (Linux/Unix ou ferramenta de scan)"
        elif sttl == 64:
            ttl_note = " — TTL típico Linux"
        elif sttl == 128:
            ttl_note = " — TTL típico Windows"
        parts.append(f"TTL: src={sttl}, dst={dttl}{ttl_note}")

    # ── Métricas de conexão (anteriores no mesmo padrão) ──
    ct_state = int(rec.get("ct_state_ttl", 0) or 0)
    if ct_state > 0:
        ct_note = ""
        if ct_state >= 5:
            ct_note = " — repetição alta (scan sistemático ou flood)"
        parts.append(f"CONEXÕES PRÉVIAS no mesmo state/TTL: {ct_state}{ct_note}")

    is_sm_ports = int(rec.get("is_sm_ips_ports", 0) or 0)
    if is_sm_ports == 1:
        parts.append("⚠ ANOMALIA: IP+porta source IGUAIS a IP+porta dest (LAND attack ou loop)")

    # ── Indicadores HTTP/FTP ──
    http_methods = int(rec.get("ct_flw_http_mthd", 0) or 0)
    if http_methods > 0:
        parts.append(f"MÉTODOS HTTP no fluxo: {http_methods}")

    is_ftp = int(rec.get("is_ftp_login", 0) or 0)
    ftp_cmd = int(rec.get("ct_ftp_cmd", 0) or 0)
    if is_ftp > 0 or ftp_cmd > 0:
        parts.append(f"COMANDOS FTP: {ftp_cmd} (login={is_ftp})")

    # ── Assinaturas heurísticas ──
    flow_shape_str = _classify_flow_shape(spkts, dpkts, sbytes, dbytes)
    sigs = _heuristic_attack_signatures(
        rec, "UNSW-NB15", pkt_rate, byte_rate, duration,
        flow_shape_str, spkts, dpkts
    )

    # Heurísticas específicas UNSW
    if state_id == 5 and dpkts == 0:  # RST + sem resposta
        sigs.append("⚠ ASSINATURA Scan rejeitado (RST sem resposta — porta fechada)")
    if state_id == 4:  # REQ apenas
        sigs.append("⚠ ASSINATURA Probe (apenas request — possível Reconnaissance ou Fuzzing)")
    if service_id == 0 and proto.startswith("protocolo") and duration < 0.001:
        sigs.append("⚠ ANOMALIA: protocolo desconhecido com duração instantânea — possível Exploit ou Fuzzer")
    if service_id == 2 and dpkts == 0:  # FTP sem resposta
        sigs.append("⚠ ASSINATURA FTP probe (FTP sem resposta — Reconnaissance ou Brute Force)")

    if sigs:
        parts.append("ASSINATURAS DETECTADAS:")
        for s in sigs:
            parts.append(f"  {s}")

    return "\n".join(parts)


# ════════════════════════════════════════════════════════════════
# Fallback genérico
# ════════════════════════════════════════════════════════════════

def _generic_record_to_text(rec: pd.Series) -> str:
    parts = ["Registro de tráfego de rede com características"]
    items = []
    for col, val in rec.items():
        if col in ("label", "label_original", "dataset_source"):
            continue
        if pd.isna(val) or val == 0:
            continue
        items.append(f"{col}={_fmt_value(val)}")
        if len(items) >= 15:
            break
    parts.append(", ".join(items))
    return ": ".join(parts) + "."


# ════════════════════════════════════════════════════════════════
# Helpers de formatação
# ════════════════════════════════════════════════════════════════

def _proto_name(proto_val) -> str:
    if proto_val is None or pd.isna(proto_val):
        return "desconhecido"
    try:
        return PROTOCOL_NAMES.get(int(proto_val), f"protocolo {int(proto_val)}")
    except (ValueError, TypeError):
        return "desconhecido"


def _fmt_time(seconds) -> str:
    if pd.isna(seconds) or seconds <= 0:
        return "0s"
    s = float(seconds)
    if s < 0.001:
        return f"{s * 1_000_000:.0f}μs"
    if s < 1:
        return f"{s * 1000:.1f}ms"
    if s < 60:
        return f"{s:.2f}s"
    if s < 3600:
        return f"{s / 60:.1f}min"
    return f"{s / 3600:.1f}h"


def _fmt_bytes(b) -> str:
    if pd.isna(b) or b <= 0:
        return "0 B"
    b = float(b)
    if b < 1024:
        return f"{b:.0f}B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f}KB"
    if b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f}MB"
    return f"{b / 1024 ** 3:.2f}GB"


def _fmt_int(n) -> str:
    if pd.isna(n):
        return "0"
    return f"{int(n):,}".replace(",", ".")


def _fmt_rate(r) -> str:
    if pd.isna(r) or r <= 0:
        return "0"
    r = float(r)
    if r < 1000:
        return f"{r:.1f}"
    if r < 1_000_000:
        return f"{r / 1000:.1f}K"
    if r < 1_000_000_000:
        return f"{r / 1_000_000:.1f}M"
    return f"{r / 1_000_000_000:.2f}G"


def _fmt_value(v):
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return f"{v:.3f}"
    return str(v)

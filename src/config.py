"""
Configuração centralizada do projeto.
Todos os caminhos, constantes e parâmetros ficam aqui.
"""

from pathlib import Path

# ── Raiz do projeto ──
PROJECT_ROOT = Path(__file__).parent.parent

# ── Caminhos de dados ──
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

CIC_RAW_DIR = RAW_DIR / "cic-ids2017"
UNSW_RAW_DIR = RAW_DIR / "unsw-nb15"

# ── Arquivos de saída do pré-processamento ──
CIC_PROCESSED_FILE = PROCESSED_DIR / "cic_ids2017_clean.parquet"
UNSW_PROCESSED_FILE = PROCESSED_DIR / "unsw_nb15_clean.parquet"
UNIFIED_PROCESSED_FILE = PROCESSED_DIR / "unified_dataset.parquet"

# ── Outputs ──
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
TRIAGE_RUNS_DIR = OUTPUTS_DIR / "triage_runs"
EVALUATION_DIR = OUTPUTS_DIR / "evaluation"

# ── Parâmetros de pré-processamento ──

# Features que sabidamente são identificadores ou não carregam informação útil
# Suporta ambas as variantes de nomes (original e versão com underscore)
CIC_DROP_COLUMNS = [
    # Formato original
    "Flow ID", "Source IP", "Source Port", "Destination IP", "Destination Port", "Timestamp",
    # Formato alternativo (lowercase com underscore)
    "flow_id", "src_ip", "src_port", "dst_ip", "dst_port", "timestamp",
]

UNSW_DROP_COLUMNS = [
    "srcip",
    "sport",
    "dstip",
    "dsport",
]

# Mapeamento de rótulos do CIC-IDS2017 para categorias unificadas
# Suporta ambas as variantes de nomes encontradas em diferentes versões do dataset
CIC_LABEL_MAP = {
    # Formato original
    "BENIGN": "Benign",
    "FTP-Patator": "Brute Force",
    "SSH-Patator": "Brute Force",
    "DoS slowloris": "DoS",
    "DoS Slowhttptest": "DoS",
    "DoS Hulk": "DoS",
    "DoS GoldenEye": "DoS",
    "Heartbleed": "Exploits",
    "Web Attack \u2013 Brute Force": "Brute Force",
    "Web Attack \u2013 XSS": "Web Attack",
    "Web Attack \u2013 Sql Injection": "Web Attack",
    # Variantes com espa\u00e7o duplo (alguns arquivos CIC omitem o em-dash)
    "Web Attack  Brute Force": "Brute Force",
    "Web Attack  XSS": "Web Attack",
    "Web Attack  Sql Injection": "Web Attack",
    "Infiltration": "Infiltration",
    "Bot": "Botnet",
    "PortScan": "Reconnaissance",
    "DDoS": "DDoS",
    # Formato alternativo (underscore)
    "Benign": "Benign",
    "DoS_Hulk": "DoS",
    "DoS_GoldenEye": "DoS",
    "DoS_Slowhttptest": "DoS",
    "DoS_Slowloris": "DoS",
    "DDoS_LOIT": "DDoS",
    "Port_Scan": "Reconnaissance",
    "Botnet_ARES": "Botnet",
    "Web_Brute_Force": "Brute Force",
    "Web_XSS": "Web Attack",
    "Web_SQL_Injection": "Web Attack",
}

# Mapeamento de rótulos do UNSW-NB15 para categorias unificadas
UNSW_LABEL_MAP = {
    "Normal": "Benign",
    "Attack": "Attack",  # Fallback: label=1 mas sem categoria específica
    "Fuzzers": "Fuzzers",
    "Analysis": "Analysis",
    "Backdoors": "Backdoor",
    "Backdoor": "Backdoor",
    "DoS": "DoS",
    "Exploits": "Exploits",
    "Generic": "Generic",
    "Reconnaissance": "Reconnaissance",
    "Shellcode": "Shellcode",
    "Worms": "Worms",
}

# Proporção de amostragem para datasets muito grandes (None = usar tudo)
SAMPLE_FRACTION = None

# Seed para reprodutibilidade
RANDOM_SEED = 42
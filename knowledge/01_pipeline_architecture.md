# Arquitetura do Pipeline

Sistema de triagem explicada de incidentes de rede que combina três etapas independentes mas integradas.

## Visão Geral

```
[Etapa 1] CSVs brutos → Pré-processamento → Parquets limpos
[Etapa 2] MITRE ATT&CK + Sigma Rules → Embeddings → ChromaDB
[Etapa 3] Registro → Descrição → RAG → LLM (Ollama) → Triagem JSON
```

Toda a stack roda **localmente** (sem chamadas a APIs externas).

---

## Etapa 1 — Pré-processamento de Dados

**Entrada**: CSVs do CIC-IDS2017 (~3.1M registros) e UNSW-NB15 (~2.5M registros).
**Saída**: Parquets limpos e normalizados.

### Operações

1. **Carregamento** (`src/data/loader.py`)
   - CIC: 8 CSVs concatenados, encoding latin-1 quando necessário, strip de espaços nas colunas
   - UNSW: 4 arquivos numerados, 1 arquivo de header separado

2. **Limpeza** (`src/data/preprocessor.py`)
   - Remoção de colunas identificadoras (IPs, portas, timestamps) — evita data leakage
   - Substituição de valores infinitos por NaN
   - Preenchimento de NaN com mediana da coluna
   - Clip de valores negativos impossíveis (contadores não podem ser negativos)
   - Mapeamento de rótulos para 15 categorias unificadas entre datasets

3. **Redução de dimensionalidade**
   - Remoção de 8 colunas constantes (variância zero)
   - Remoção de 25+ colunas com correlação > 0.95

4. **Codificação categórica**
   - LabelEncoder para `proto`, `service`, `state` no UNSW (cardinalidade moderada)

5. **Normalização** (apenas no dataset unificado)
   - Min-Max scaling para [0,1]
   - Justificativa: tráfego de rede não é gaussiano (Z-score inadequado)

### Outputs

| Arquivo | Conteúdo | Uso |
|---------|----------|-----|
| `cic_ids2017_clean.parquet` | 2.83M registros, valores brutos | Triagem LLM |
| `unsw_nb15_clean.parquet` | 2.54M registros, valores brutos | Triagem LLM |
| `unified_dataset.parquet` | 5.37M registros, normalizado [0,1] | ML clássico (futuro) |
| `normalization_params.json` | Min/max de cada coluna | Reprodutibilidade |
| `preprocessing_report.json` | Estatísticas completas | Manuscrito |

### Distribuição de Rótulos (após limpeza)

**CIC-IDS2017** (2.83M registros):
- Benign: 2.27M (80.3%)
- DoS: 252K (8.9%)
- Reconnaissance: 159K (5.6%)
- DDoS: 128K (4.5%)
- Brute Force: 14K (0.5%)
- Botnet, Infiltration, Exploits: <1%

**UNSW-NB15** (2.54M registros):
- Benign: 2.22M (87.4%)
- Generic: 215K (8.5%)
- Exploits: 45K (1.8%)
- Fuzzers: 24K (1.0%)
- DoS: 16K (0.6%)
- Reconnaissance, Analysis, Backdoor, Shellcode, Worms: <1%

**Observação importante**: forte desequilíbrio de classes (~85% Benign) — implica em estratificação obrigatória para avaliação justa.

---

## Etapa 2 — Base de Conhecimento RAG

**Entrada**: MITRE ATT&CK Enterprise (STIX 2.1 JSON, ~49MB) + Sigma Rules (repositório GitHub, ~4.189 YAMLs).
**Saída**: Índice vetorial ChromaDB persistente.

### Pipeline

1. **Download** (`src/rag/download.py`)
   - MITRE ATT&CK via `urllib.request` (URL pública do GitHub)
   - Sigma Rules via `git clone --depth 1` (shallow clone, ~50MB)

2. **Parsing**
   - **MITRE** (`src/rag/sources/mitre.py`): extrai 691 técnicas/sub-técnicas de objetos `attack-pattern` do STIX, resolvendo relações com mitigações e detecções
   - **Sigma** (`src/rag/sources/sigma.py`): extrai 3.728 regras válidas dos YAMLs, transformando seções estruturadas (logsource, detection, condition) em texto legível

3. **Embeddings** (`src/rag/embeddings.py`)
   - Modelo: `all-MiniLM-L6-v2` (384 dimensões)
   - Batch de 64, GPU se disponível
   - Cache local (offline após primeiro download)

4. **Indexação** (`src/rag/vectorstore.py`)
   - ChromaDB persistente em `data/rag/chromadb/`
   - Métrica: cosine similarity
   - Metadata por documento: source, technique_id, tactics, etc.

### Total Indexado

- 4.419 documentos = 691 MITRE + 3.728 Sigma
- ~1-2 minutos para indexação completa em GPU

### Recuperação

- `Retriever.search(query, top_k=5)` retorna os top-5 documentos mais similares
- **Filtro de qualidade**: se `best_distance > 0.55`, descarta o contexto (semanticamente irrelevante)
- Implementado em `src/llm/triage.py` — não no `retriever.py`, para permitir auditoria do que foi descartado

---

## Etapa 3 — Triagem com LLM

**Entrada**: registro de tráfego (linha do Parquet).
**Saída**: `TriageResult` JSON com classificação, severidade, MITRE techniques, explicação.

### Fluxo Completo

```
record (pd.Series)
  ↓
text_converter.record_to_text()        # features → descrição em PT-BR
  ↓
retriever.search(description, top_k=5) # busca semântica em ChromaDB
  ↓ (filtro: descarta se dist > 0.55)
prompts.build_user_prompt()             # monta prompt com contexto RAG
  ↓
llm_client.generate()                   # /api/chat + JSON Schema → Ollama
  ↓
parse_json_response()                   # extrai JSON
  ↓
normalização (confidence ÷100, attack_type alias, MITRE regex)
  ↓
validate_triage_output()                # valida schema
  ↓
TriageResult dataclass
```

### Componentes

#### `text_converter.py`
- Converte features brutas em descrição legível em português
- Detecta dataset via `dataset_source` (CIC ou UNSW)
- **Crítico**: usa nomes reais das colunas (não snake_case)
  - CIC: `"Flow Duration"`, `"Total Fwd Packets"`, `"SYN Flag Count"`, etc.
  - UNSW: `"dur"`, `"sbytes"`, `"Spkts"`, `"sttl"`, etc.
- Formatadores (`_fmt_bytes`, `_fmt_time`, `_fmt_rate`) para legibilidade

#### `prompts.py`
- System prompt em **inglês** (modelo é Llama 3 fine-tuned em inglês)
- Inclui exemplo concreto de output JSON
- Lista categorias e severidades válidas

#### `llm_client.py`
- Endpoint: `/api/chat` (não `/api/generate`) — aplica template Llama 3
- **JSON Schema com enum** força chaves e valores válidos via grammar sampling
- `num_ctx: 8192` (dobro do padrão Ollama)
- Carrega `.env` com `python-dotenv`

#### `triage.py`
- `TriageEngine`: orquestrador completo
- Logging verboso por registro (descrição, RAG, LLM, resultado, match)
- Normalização robusta:
  - `confidence`: divide por 100 se > 1.0 (modelo às vezes retorna 0-100)
  - `attack_type`: dicionário de aliases mapeia "C2 Communication" → "Botnet"
  - `mitre_techniques`: regex extrai apenas IDs `Txxxx` ou `Txxxx.yyy` de strings com descrição

#### `pipeline.py` (CLI)
- Pré-amostra `n × 50` registros por dataset (evita carregar 5M linhas)
- Amostragem estratificada via `groupby` + `pd.concat` (compatível com pandas 2.x)
- Métricas binárias salvas no JSON: `accuracy_exact`, `accuracy_binary`, `precision`, `recall`, matriz de confusão
- Cada run gera subpasta `outputs/triage_runs/run_<timestamp>_<rag|norag>_n<N>_<strat>/`

---

## Stack Técnico

| Componente | Versão | Uso |
|-----------|--------|-----|
| Python | 3.13 | Linguagem principal |
| pandas + pyarrow | 2.x / 14+ | Manipulação de dados (Parquet) |
| sentence-transformers | 5.x | Embeddings (all-MiniLM-L6-v2) |
| chromadb | 0.4+ | Banco vetorial persistente |
| ollama | 0.12.3 | LLM local |
| Foundation-Sec-8B-Instruct | Q8_0 GGUF | LLM especializado em segurança |
| pytest | 9.x | Testes (78 unitários) |

---

## Diagrama de Dependências entre Módulos

```
src/config.py  (caminhos e constantes)
    ↑
    │
    ├── src/data/    (Etapa 1, independente)
    │      └── loader, preprocessor, pipeline
    │
    ├── src/rag/     (Etapa 2, independente)
    │      ├── sources/{mitre,sigma}
    │      ├── download
    │      ├── embeddings
    │      ├── vectorstore
    │      ├── retriever
    │      └── pipeline
    │
    └── src/llm/     (Etapa 3, depende de rag/)
           ├── text_converter   (lê Parquet da Etapa 1)
           ├── llm_client       (chama Ollama)
           ├── prompts
           ├── triage           (usa retriever + llm_client)
           └── pipeline
```

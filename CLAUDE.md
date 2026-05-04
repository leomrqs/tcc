# CLAUDE.md — Documentação Técnica Interna

> Este arquivo é lido automaticamente pelo Claude Code a cada sessão.
> Mantém contexto técnico completo do projeto para não precisar reexplicar.

---

## O que é este projeto

TCC de Ciência da Computação (PUCPR, Turma 7B, Grupo 3).  
Sistema de triagem automática de incidentes de rede 100% local usando LLM + RAG.  
Stack: Python 3.13, ChromaDB, sentence-transformers, Ollama (Foundation-Sec-8B-Instruct), pandas.

---

## Estrutura de Diretórios

```
tcc/
├── src/
│   ├── config.py                  # Caminhos, constantes, label maps
│   ├── utils/logger.py            # Logger com timestamp
│   ├── data/                      # Etapa 1
│   │   ├── loader.py              # Carrega CSVs brutos (CIC + UNSW)
│   │   ├── preprocessor.py        # Limpeza, encoding, normalização
│   │   └── pipeline.py            # CLI Etapa 1
│   ├── rag/                       # Etapa 2
│   │   ├── download.py            # Baixa MITRE ATT&CK + Sigma Rules
│   │   ├── sources/mitre.py       # Parser STIX 2.1
│   │   ├── sources/sigma.py       # Parser YAML
│   │   ├── sources/ids_classes.py # NOVO: descrições canônicas das 15 classes IDS
│   │   ├── embeddings.py          # all-MiniLM-L6-v2, com cache de query
│   │   ├── vectorstore.py         # ChromaDB wrapper, auto-reparo se corrompido
│   │   ├── retriever.py           # Busca + cross-encoder re-rank (top-20 → top-5)
│   │   └── pipeline.py            # CLI Etapa 2
│   ├── ml/                        # NOVO: pre-classificador clássico
│   │   └── preclassifier.py       # Random Forest binário (Benign vs Threat)
│   └── llm/                       # Etapa 3
│       ├── text_converter.py      # v2: features categóricas (FLOOD/HIGH/.../assinaturas)
│       ├── llm_client.py          # /api/chat + JSON Schema (sem `pattern`!)
│       ├── prompts.py             # v2: chain-of-thought + 6 few-shot examples
│       ├── triage.py              # TriageEngine + two-stage (opt-in) + RF pre-filter (opt-in)
│       └── pipeline.py            # CLI Etapa 3 + flags --use-rf --two-stage --no-rerank
├── tests/                         # 78 testes (pytest)
├── data/ml_models/                # NOVO: rf_cic.joblib + rf_unsw.joblib (treinados)
├── run_evaluation.ps1             # Script: roda RAG + no-RAG sequencial
├── run_benchmark.ps1              # NOVO: bateria 2-3h com 6 configs × N × seeds
├── .env                           # OLLAMA_HOST + OLLAMA_MODEL
├── models/Modelfile               # FROM ./foundation-sec-8b-instruct-q8_0.gguf
└── outputs/
    ├── triage_runs/               # Por run: run_<ts>_<tags>_n<N>/results.json
    └── benchmarks/                # NOVO: bench_<ts>/{summary,ranking}.json
```

---

## Fluxo de Dados

```
CSVs brutos
  → data/pipeline.py
  → cic_ids2017_clean.parquet  (não normalizado, valores brutos)
  → unsw_nb15_clean.parquet    (não normalizado, valores brutos)
  → unified_dataset.parquet    (normalizado [0,1] — NÃO usar para triagem LLM)

MITRE ATT&CK JSON + Sigma YAMLs
  → rag/pipeline.py
  → ChromaDB (4.419 docs: 691 MITRE + 3.728 Sigma)

Triagem (Etapa 3):
  Parquet individual (NÃO normalizado)
    → text_converter.py → descrição textual com features reais
    → retriever.py → top-5 docs ChromaDB (filtrado se dist > 0.55)
    → prompts.py → prompt EN com exemplo JSON
    → llm_client.py → /api/chat + JSON Schema → resposta estruturada
    → triage.py → normaliza confidence (÷100 se >1) + mapeia attack_type
    → outputs/triage_runs/run_.../results.json
```

---

## Comandos Essenciais (Windows PowerShell)

```powershell
# Ativar venv
.\.venv\Scripts\Activate.ps1

# Etapa 1
python -m src.data.pipeline

# Etapa 2
python -m src.rag.pipeline --test

# Etapa 3 (Ollama deve estar rodando em outro terminal)
ollama serve
python -m src.llm.pipeline --n 5 --stratified
python -m src.llm.pipeline --n 5 --stratified --no-rag

# Avaliação completa automática
.\run_evaluation.ps1 -N 5

# Testes
python -m pytest tests/ -v

# Limpar e re-indexar ChromaDB
Remove-Item -Recurse -Force data\rag\chromadb
python -m src.rag.pipeline --reset
```

---

## Configuração .env

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=foundation-sec-8b-instruct
```

Carregado via `python-dotenv` em `llm_client.py` na inicialização do módulo.

---

## Modelo LLM

- **Nome**: Foundation-Sec-8B-Instruct (Llama 3 fine-tuned em cibersegurança)
- **Quantização**: Q8_0 (~8.5GB) — registrado como `foundation-sec-8b-instruct`
- **Arquivo**: `models/foundation-sec-8b-instruct-q8_0.gguf`
- **GPU**: RTX 5060 8GB → 22/33 camadas na GPU, resto CPU (low VRAM mode)
- **Velocidade**: ~20s/registro com config atual
- **num_ctx**: 8192 tokens (dobro do padrão Ollama de 4096)
- **Temperatura**: 0.2 (consistência)
- **Endpoint**: `/api/chat` (não `/api/generate` — aplica template Llama 3)
- **Structured output**: JSON Schema via `"format": {...}` no payload Ollama

---

## Bugs Corrigidos Nesta Sessão

| # | Arquivo | Bug | Fix |
|---|---------|-----|-----|
| 1 | `llm/pipeline.py` | `load_dataset` ignorava `sample_size` | Agora pré-amostra por dataset antes de selecionar |
| 2 | `llm/pipeline.py` | `groupby().apply()` no pandas 2.x dropa coluna `label` | Substituído por `pd.concat` de grupos individuais |
| 3 | `llm/text_converter.py` | Flag ACK mapeada para coluna ECE | Corrigido: `ack_flag_counts` separado de `ece_flag_counts` |
| 4 | `llm/text_converter.py` | Nomes de coluna CIC em snake_case inexistentes | Corrigido para nomes reais: `"Flow Duration"`, `"Total Fwd Packets"`, etc. |
| 5 | `llm/pipeline.py` | `_matches_label` exact match falhava em variantes | Dicionário de aliases por categoria |
| 6 | `llm/client.py` | `.env` carregado manualmente | Substituído por `load_dotenv()` |
| 7 | `rag/embeddings.py` | `get_sentence_embedding_dimension()` depreciado | Usa `get_embedding_dimension()` com fallback |
| 8 | `rag/vectorstore.py` | ChromaDB corrompido causava crash | Auto-detecta e recria o índice |
| 9 | `llm/client.py` | Usava `/api/generate` — system prompt ignorado | Migrado para `/api/chat` com template Llama 3 |
| 10 | `llm/client.py` | `format: "json"` não garante chaves certas | JSON Schema estruturado com `required` fields |
| 11 | `llm/triage.py` | Normalização de confidence/attack_type após validação | Movido para antes da validação |
| 12 | `llm/pipeline.py` | Carregava unified_dataset normalizado para triagem | Agora carrega parquets individuais não-normalizados |
| 13 | `config.py` | "Web Attack  Brute Force" (espaço duplo) não mapeado | Adicionadas variantes com espaço duplo no CIC_LABEL_MAP |

---

## Decisões de Design Importantes

### Por que parquets individuais para triagem (não unified)?
O `unified_dataset.parquet` está normalizado [0,1]. O `text_converter.py` converte features em texto legível (ex: "230 pacotes", "1.5s") — com valores normalizados, `0.001` vira `"0 pacotes"` e a descrição fica vazia. Solução: carregar `cic_ids2017_clean.parquet` + `unsw_nb15_clean.parquet` que preservam valores brutos.

### Por que /api/chat e não /api/generate?
O modelo Foundation-Sec-8B é baseado em Llama 3, que usa um template de chat específico (`<|start_header_id|>system<|end_header_id|>...`). O endpoint `/api/generate` com campo `"system"` não aplica esse template corretamente, fazendo o modelo ignorar as instruções do system prompt. O `/api/chat` aplica o template automaticamente.

### Por que JSON Schema no format?
`"format": "json"` garante JSON válido mas não garante chaves específicas. O modelo retornava `{"analysis": {...}}` em vez de `{"attack_type": "..."}`. Com JSON Schema em `"format"`, o Ollama usa grammar-based sampling que fisicamente impede gerar outras chaves.

### Por que filtro de distância RAG (> 0.55)?
Observado empiricamente: quando o melhor documento recuperado tem distância > 0.55, o contexto é semanticamente irrelevante para o registro atual. Nesse caso, o contexto piora a classificação ao induzir o modelo a citar C2/Botnet (os documentos Sigma mais "comuns" no índice). Sem contexto, o modelo classifica com menor confiança mas com maior diversidade de categorias.

### Nomes de colunas do CIC-IDS2017
Após `df.columns.str.strip()`, os nomes são em Title Case com espaços:
- `"Protocol"`, `"Flow Duration"`, `"Total Fwd Packets"`, `"Total Backward Packets"`
- `"Total Length of Fwd Packets"`, `"Min Packet Length"`, `"Max Packet Length"`, `"Packet Length Mean"`
- `"Flow Bytes/s"`, `"Flow Packets/s"`
- `"SYN Flag Count"`, `"FIN Flag Count"`, `"RST Flag Count"`, `"PSH Flag Count"`, `"ACK Flag Count"`, `"ECE Flag Count"`, `"CWE Flag Count"`
- `"Init_Win_bytes_forward"`

### Normalização de confidence do modelo
O modelo retorna confidence como 0-100 (ex: `85`) em vez de 0.0-1.0.
Fix em `triage.py`: `confidence = raw_conf / 100.0 if raw_conf > 1.0 else raw_conf`

### Mapeamento de attack_type
O modelo usa nomes livres ("Command and Control", "suspicious_activity", "C2 Communication").
Fix: dicionário `_ATTACK_TYPE_MAP` em `triage.py` mapeia para as categorias válidas.

---

## Estrutura do Output JSON

```json
{
  "n_records": 9,
  "n_valid": 9,
  "avg_elapsed_seconds": 20.3,
  "accuracy_exact": 0.11,
  "accuracy_binary": 0.67,
  "precision": 0.80,
  "recall": 0.75,
  "confusion": {"tp": 6, "tn": 0, "fp": 1, "fn": 2},
  "results": [{
    "attack_type": "Botnet",
    "severity": "high",
    "confidence": 0.85,
    "mitre_techniques": ["T1071.001"],
    "explanation": "...",
    "recommendations": ["..."],
    "record_description": "Fluxo TCP...",
    "retrieved_context_titles": ["Cleartext Protocol Usage", ...],
    "rag_distances": [0.618, 0.621, ...],
    "elapsed_seconds": 20.6,
    "model_name": "foundation-sec-8b-instruct",
    "ground_truth": "Analysis",
    "raw_llm_response": "{...}",
    "validation_errors": []
  }]
}
```

---

## Métricas de Avaliação

**Acurácia exata**: predição == ground truth (case-insensitive + aliases).  
**Acurácia binária**: ameaça vs benigno (ignora categoria específica, mais justa para comparação).  
**Precisão**: TP / (TP + FP) — dos que prediu como ameaça, quantos eram ameaças reais.  
**Recall**: TP / (TP + FN) — das ameaças reais, quantas foram detectadas.  
**F1**: média harmônica de precisão e recall.

Labels consideradas "Benign": `{"benign", "normal", "background"}` — tudo mais é ameaça.

---

## Resultados Observados (amostra de 9 registros, UNSW-NB15 + CIC)

| Modo | Acurácia Exata | Acurácia Binária | Conf. Média | Tempo/reg |
|------|---------------|-----------------|-------------|-----------|
| Com RAG | 0% | ~67% | 0.78 | ~20s |
| Sem RAG | 11% | ~56% | 0.63 | ~22s |

**Observações importantes:**
- RAG aumenta confiança mas induz viés para Botnet/C2 quando documentos são irrelevantes
- Filtro de distância (> 0.55) mitiga o viés mas não elimina completamente
- Amostra pequena (9 reg.) — resultados não são estatisticamente significativos
- Para TCC: usar `--n 3 --stratified` (~45 registros) como mínimo viável

---

## Troubleshooting Rápido

| Sintoma | Causa | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: sentence_transformers` | venv não ativado | `.\.venv\Scripts\Activate.ps1` |
| `Error loading hnsw index` | ChromaDB corrompido | `Remove-Item -Recurse data\rag\chromadb` |
| `404 Not Found /api/generate` | Nome do modelo errado | `ollama list` → ajustar `.env` |
| Descrições vazias ("duração instantânea") | Usando unified_dataset normalizado | pipeline.py carrega parquets individuais — verificar |
| LLM sempre retorna Botnet | RAG com distâncias altas | Filtro 0.55 ativo — normal para UNSW com protocolos desconhecidos |
| `getaddrinfo failed` no embedding | Sem internet, versão nova tenta checar | `local_files_only=True` já tratado |
| Confidence sempre 0.0 | Validação antes da normalização | Corrigido — normalização ocorre antes |

---

## Categorias de Ataque Válidas

```
Benign, DoS, DDoS, Brute Force, Botnet, Reconnaissance,
Web Attack, Exploits, Fuzzers, Backdoor, Generic,
Analysis, Shellcode, Worms, Infiltration
```

Severidades válidas: `informational`, `low`, `medium`, `high`, `critical`

---

## Testes (78 unitários)

```
tests/test_text_converter.py    — conversão CIC/UNSW → texto (17 testes)
tests/test_prompts.py           — validação schema JSON (16 testes)
tests/test_llm_client.py        — parsing JSON do LLM (15 testes)
tests/test_pipeline_helpers.py  — amostragem estratificada, label matching (12 testes)
tests/test_preprocessor.py      — limpeza, normalização, correlação (18 testes)
```

---

## Etapas Futuras (Etapa 4)

- `src/app/` — Interface Streamlit com upload de registros e visualização
- `src/evaluation/` — Matriz de confusão completa, curva ROC, análise por classe
- Avaliação qualitativa das explicações (coerência, precisão técnica)
- Manuscrito final do TCC com análise comparativa RAG vs no-RAG

---

## Pipeline v2 — Melhorias Implementadas (após Bug #19)

### Melhorias arquiteturais

| Melhoria | Arquivo | Impacto esperado |
|----------|---------|-----------------|
| **text_converter v2** discriminativo | `src/llm/text_converter.py` | descrições com FLOOD/HIGH/MODERADA + assinaturas heurísticas (⚠) ajudam o LLM a discriminar |
| **prompts v2** chain-of-thought + few-shot | `src/llm/prompts.py` | 6 exemplos canônicos com reasoning explícito + protocolo de 5 passos |
| **two-stage classification** (opt-in) | `src/llm/triage.py` | Stage 1 binário Benign/Threat (rápido) + Stage 2 detalhado |
| **base RAG curada** (16 docs IDS) | `src/rag/sources/ids_classes.py` | descrições canônicas das 15 classes + taxonomia decision tree |
| **cross-encoder re-rank** | `src/rag/retriever.py` | top-20 denso → re-classifica com ms-marco-MiniLM-L-6-v2 → top-5 |
| **Random Forest pre-filter** (opt-in) | `src/ml/preclassifier.py` | RF treinado: 99.8% acc CIC, 99.1% acc UNSW; skip LLM se Benign conf≥95% |

### Novos comandos

```powershell
# Treinar Random Forest (uma única vez, ~2 minutos)
python -m src.ml.preclassifier --sample-size 200000

# Re-indexar RAG com novos ids_classes
python -m src.rag.pipeline --reset --skip-download

# Pipeline com RF + RAG + cross-encoder rerank
python -m src.llm.pipeline --n 5 --stratified --use-rf

# Pipeline com tudo: RF + 2-stage + RAG rerank
python -m src.llm.pipeline --n 5 --stratified --use-rf --two-stage

# Bateria longa (2-3h) — 6 configs × tamanhos × seeds, ranking final
.\run_benchmark.ps1
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 3,5,10
.\run_benchmark.ps1 -Quick   # versão rápida (1 seed × N=3)
```

### Flags do pipeline LLM

- `--no-rag` — desativa RAG (baseline)
- `--no-rerank` — usa retriever denso direto, sem cross-encoder
- `--two-stage` — ativa Stage 1 binário (opt-in — Foundation-Sec-8B oscila)
- `--use-rf` — ativa pre-classificador RF (filtra Benigns com ~98% cobertura)
- `--rag-threshold 0.55` — threshold de descarte (default 0.55)
- `--rf-threshold 0.95` — confiança mínima do RF para skipar LLM
- `--seed N` — seed da amostragem (default aleatório)

### Bug crítico corrigido

**Bug #20 — `Flow Packets/s` do CIC inconsistente**: o CIC computa essa coluna em microssegundos, gerando valores absurdos (FLOOD para fluxos de 2 pacotes em 48s). Fix: text_converter v2 recalcula taxa a partir de `total_pkts / duration` real.

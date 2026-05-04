# Triagem Explicada de Incidentes de Rede com LLM e RAG Local

**Projeto Transformador I** — Bacharelado em Ciência da Computação, PUCPR  
Turma 7B — Grupo 3

---

## Visão Geral

Sistema **100% local** de triagem automática de incidentes de rede que combina:

- **LLM especializado em cibersegurança** (Foundation-Sec-8B-Instruct via Ollama) com prompt chain-of-thought + few-shot examples
- **RAG local** com MITRE ATT&CK Enterprise (691 técnicas) + Sigma Rules (3.728 regras) + **base curada de descrições de classes IDS** (16 docs canônicos)
- **Cross-encoder re-ranking** (`ms-marco-MiniLM-L-6-v2`) para melhorar a qualidade dos top-K do RAG
- **Pre-classificador Random Forest** (99.8% acc CIC, 99.1% acc UNSW) para filtrar Benigns óbvios antes do LLM
- **Two-stage classification** opt-in (binário rápido + categoria detalhada)
- **Dois datasets de benchmark**: CIC-IDS2017 (~3.1M registros) e UNSW-NB15 (~2.5M registros)
- **Bateria de avaliação automatizada**: 6 configurações × N tamanhos × seeds com ranking final

Nenhum dado sai da máquina — LLM, embeddings, RF e base vetorial rodam localmente.

---

## Estrutura do Projeto

```
tcc/
├── src/
│   ├── config.py                   # Caminhos e constantes centralizados
│   ├── utils/logger.py             # Logger padronizado
│   ├── data/                       # Etapa 1: ingestão e pré-processamento
│   │   ├── loader.py               # Carrega CSVs brutos (CIC e UNSW)
│   │   ├── preprocessor.py         # Limpeza, encoding, normalização
│   │   └── pipeline.py             # Orquestrador CLI da Etapa 1
│   ├── rag/                        # Etapa 2: base de conhecimento RAG
│   │   ├── download.py             # Baixa MITRE ATT&CK e Sigma Rules
│   │   ├── sources/
│   │   │   ├── mitre.py            # Parser STIX 2.1 → documentos textuais
│   │   │   ├── sigma.py            # Parser YAML → documentos textuais
│   │   │   └── ids_classes.py      # Descrições canônicas das 15 classes IDS (curado)
│   │   ├── embeddings.py           # Wrapper sentence-transformers (all-MiniLM-L6-v2)
│   │   ├── vectorstore.py          # Wrapper ChromaDB (cosine similarity)
│   │   ├── retriever.py            # Busca semântica + cross-encoder re-rank (top-20 → top-5)
│   │   └── pipeline.py             # Orquestrador CLI da Etapa 2
│   ├── ml/                         # Pre-classificador clássico
│   │   └── preclassifier.py        # Random Forest binário (Benign vs Threat)
│   └── llm/                        # Etapa 3: triagem com LLM
│       ├── text_converter.py       # v2: features categóricas (FLOOD/HIGH/...) + assinaturas
│       ├── llm_client.py           # Cliente HTTP para Ollama (/api/chat + JSON schema)
│       ├── prompts.py              # v2: chain-of-thought + 6 few-shot examples
│       ├── triage.py               # TriageEngine: RF pre-filter + 2-stage + RAG + LLM
│       └── pipeline.py             # Orquestrador CLI da Etapa 3 (--use-rf, --two-stage)
├── tests/                          # 78 testes unitários
│   ├── test_text_converter.py
│   ├── test_prompts.py
│   ├── test_llm_client.py
│   ├── test_pipeline_helpers.py
│   └── test_preprocessor.py
├── data/
│   ├── raw/                        # Datasets brutos (não versionados)
│   │   ├── cic-ids2017/            # CSVs do CIC-IDS2017
│   │   └── unsw-nb15/              # CSVs do UNSW-NB15
│   ├── processed/                  # Parquets gerados pela Etapa 1 (não versionados)
│   ├── rag/
│   │   ├── sources/                # MITRE ATT&CK JSON + Sigma Rules YAMLs
│   │   └── chromadb/               # Índice vetorial persistente (não versionado)
│   └── ml_models/                  # Random Forest treinados (não versionados)
│       ├── rf_cic.joblib
│       ├── rf_unsw.joblib
│       └── rf_meta.json            # Métricas de treino dos RFs
├── models/
│   ├── Modelfile                   # Receita para registrar o GGUF no Ollama
│   └── foundation-sec-8b-instruct-q8_0.gguf  # Modelo LLM (não versionado)
├── outputs/
│   ├── triage_runs/                # Resultados organizados por run
│   │   └── run_<timestamp>_<tags>_n<N>/
│   │       └── results.json
│   └── benchmarks/                 # Bateria longa
│       └── bench_<timestamp>/
│           ├── benchmark.log
│           ├── summary.json        # Todas as runs detalhadas
│           └── ranking.json        # Ranking final por configuração
├── knowledge/                      # Documentação para o TCC
├── run_evaluation.ps1              # Script: RAG + no-RAG sequencial
├── run_benchmark.ps1               # Bateria 2-3h: 6 configs × tamanhos × seeds
├── .env                            # Configuração local (não versionar)
├── requirements.txt
├── CLAUDE.md                       # Documentação técnica interna (para Claude)
└── README.md
```

---

## Setup Inicial

### Pré-requisitos

- Python 3.11+
- Git
- [Ollama](https://ollama.com/download) instalado
- GPU NVIDIA recomendada (funciona em CPU, mas é ~5x mais lento)

### Instalar dependências

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows
# source .venv/bin/activate        # Linux/Mac
pip install -r requirements.txt
```

### Configurar .env

Crie o arquivo `.env` na raiz do projeto:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=foundation-sec-8b-instruct
```

### Resumo do setup completo

Para colocar o projeto rodando do zero, você precisa executar **na ordem**:

1. **Etapa 1** — Pré-processar datasets (Parquets)
2. **Etapa 2** — Baixar e indexar base RAG (MITRE + Sigma + classes IDS)
3. **Etapa 2.5** — Treinar Random Forest pre-classificador
4. **Etapa 3** — Registrar modelo Foundation-Sec no Ollama

Cada etapa é detalhada nas seções abaixo. Veja também a seção
[Comandos Rápidos](#comandos-rápidos--setup-completo-do-zero) para um único bloco
copy-paste com todos os comandos em ordem.

---

## Etapa 1 — Pré-processamento dos Datasets

### 1.1 Obter os Datasets

**CIC-IDS2017** → [unb.ca/cic/datasets/ids-2017.html](https://www.unb.ca/cic/datasets/ids-2017.html)  
Coloque os CSVs em `data/raw/cic-ids2017/`

**UNSW-NB15** → [research.unsw.edu.au/projects/unsw-nb15-dataset](https://research.unsw.edu.au/projects/unsw-nb15-dataset)  
Coloque os CSVs em `data/raw/unsw-nb15/`

### 1.2 Rodar o Pipeline

```powershell
# Ambos os datasets (~2 minutos)
python -m src.data.pipeline

# Só um dataset
python -m src.data.pipeline --dataset cic
python -m src.data.pipeline --dataset unsw

# Teste rápido com 10% dos dados
python -m src.data.pipeline --sample 0.1
```

### 1.3 O que é feito

- Remove colunas identificadoras (IPs, portas, timestamps)
- Substitui valores infinitos por NaN, preenche NaN com mediana
- Clipa valores negativos impossíveis (contadores de bytes/pacotes)
- Remove 8 colunas constantes e 25+ colunas altamente correlacionadas (>0.95)
- Mapeia rótulos para categorias unificadas entre os dois datasets
- Normaliza features numéricas para [0,1] no dataset unificado (Min-Max)
- Salva: `cic_ids2017_clean.parquet`, `unsw_nb15_clean.parquet`, `unified_dataset.parquet`

### 1.4 Saída

```
data/processed/
├── cic_ids2017_clean.parquet      # 2.83M registros, não normalizado
├── unsw_nb15_clean.parquet        # 2.54M registros, não normalizado
├── unified_dataset.parquet        # 5.37M registros, normalizado [0,1]
├── normalization_params.json      # Min/max de cada coluna
└── preprocessing_report.json      # Relatório completo
```

---

## Etapa 2 — Base de Conhecimento RAG

### Pré-requisitos

- Git instalado (para clonar Sigma Rules)
- GPU recomendada para geração de embeddings (~1-2 min com GPU, ~5 min em CPU)

### 2.1 Baixar as Fontes

```powershell
python -m src.rag.download
```

Baixa:
- MITRE ATT&CK Enterprise STIX 2.1 JSON (~49MB)
- Sigma Rules (repositório completo, ~4.189 arquivos YAML)

### 2.2 Rodar o Pipeline RAG

```powershell
# Indexar + rodar testes de busca semântica
python -m src.rag.pipeline --test

# Só indexar (sem testes)
python -m src.rag.pipeline

# Re-indexar do zero (necessário ao adicionar novas fontes)
python -m src.rag.pipeline --reset --skip-download

# Pular download (se fontes já existem)
python -m src.rag.pipeline --skip-download --test
```

> **Importante**: ao atualizar a base curada de classes IDS (`src/rag/sources/ids_classes.py`),
> rode `python -m src.rag.pipeline --reset --skip-download` para re-indexar o ChromaDB.

### 2.3 Saída

```
data/rag/chromadb/    # ~4.435 documentos indexados
                      # 16 descrições canônicas das classes IDS (curado)
                      # 691 técnicas MITRE ATT&CK
                      # 3.728 regras Sigma
```

Os testes de busca validam a qualidade do RAG com 8 queries de cibersegurança (SSH brute force, DDoS, SQL injection, etc.).

---

## Etapa 2.5 — Pre-classificador Random Forest (opcional, mas recomendado)

O pre-classificador RF filtra Benigns óbvios antes do LLM, resolvendo o problema de TN=0
e acelerando muito a triagem.

### 2.5.1 Treinar os modelos

```powershell
# Treina RF binário (Benign vs Threat) para CIC e UNSW separadamente (~2 min)
python -m src.ml.preclassifier --sample-size 200000

# Usar todos os registros (mais lento, marginalmente melhor)
python -m src.ml.preclassifier --sample-size 0
```

### 2.5.2 Saída

```
data/ml_models/
├── rf_cic.joblib       # Acurácia ~99.8%, captura ~98% dos Benigns com conf≥95%
├── rf_unsw.joblib      # Acurácia ~99.1%, captura ~98% dos Benigns com conf≥95%
└── rf_meta.json        # Métricas detalhadas dos treinos
```

**Risco controlado**: 0.04% das ameaças são mal classificadas como Benign com conf≥95%.

---

## Etapa 3 — Triagem com LLM

### 3.1 Instalar o Modelo

O modelo Foundation-Sec-8B-Instruct não está disponível em GGUF direto pelo Ollama. É necessário baixar e importar manualmente:

```powershell
# Baixar o GGUF (~8.5GB) — executar na pasta tcc/
python -c "from huggingface_hub import hf_hub_download; hf_hub_download('fdtn-ai/Foundation-Sec-8B-Instruct-Q8_0-GGUF', filename='foundation-sec-8b-instruct-q8_0.gguf', local_dir='./models')"

# Registrar no Ollama
ollama create foundation-sec-8b-instruct -f models\Modelfile

# Confirmar
ollama list
```

### 3.2 Iniciar o Servidor Ollama

**Em um terminal separado** (manter aberto durante toda a triagem):

```powershell
ollama serve
```

### 3.3 Rodar Triagem Individual

```powershell
# Stack completa recomendada: RF + RAG + cross-encoder rerank (default)
python -m src.llm.pipeline --n 5 --stratified --use-rf

# Tudo ligado: RF + 2-stage + RAG + rerank
python -m src.llm.pipeline --n 5 --stratified --use-rf --two-stage

# 5 registros por classe (estratificado) — sem RF
python -m src.llm.pipeline --n 5 --stratified

# 10 registros aleatórios do dataset unificado
python -m src.llm.pipeline --n 10

# Só CIC-IDS2017
python -m src.llm.pipeline --n 10 --dataset cic --stratified

# Baseline SEM RAG (para comparação)
python -m src.llm.pipeline --n 5 --stratified --no-rag

# Sem cross-encoder (RAG denso puro, mais rápido)
python -m src.llm.pipeline --n 5 --stratified --no-rerank

# Registro específico pelo índice
python -m src.llm.pipeline --index 12345

# Salvar em caminho customizado
python -m src.llm.pipeline --n 20 --output outputs/meu_teste.json
```

#### Flags disponíveis

| Flag | Default | Descrição |
|------|---------|-----------|
| `--n N` | 10 | Número de registros a triar |
| `--stratified` | false | Amostragem estratificada (igual nº por classe) |
| `--dataset {unified,cic,unsw}` | unified | Qual dataset usar |
| `--seed N` | aleatório | Seed da amostragem (reprodutibilidade) |
| `--no-rag` | false | Desativa RAG (baseline) |
| `--no-rerank` | false | Desativa cross-encoder re-rank (RAG denso direto) |
| `--use-rf` | false | Ativa pre-classificador Random Forest |
| `--rf-threshold 0.95` | 0.95 | Confiança mínima do RF para skipar LLM |
| `--two-stage` | false | Ativa Stage 1 binário (Benign/Threat rápido) |
| `--rag-threshold 0.55` | 0.55 | Threshold de descarte do RAG (distância densa) |
| `--top-k N` | 5 | Quantos docs RAG buscar |

### 3.4 Rodar Avaliação Completa (RAG + No-RAG automaticamente)

```powershell
# Roda RAG e no-RAG em sequência e exibe comparativo
.\run_evaluation.ps1

# Customizado
.\run_evaluation.ps1 -N 3
.\run_evaluation.ps1 -N 2 -Dataset cic
```

### 3.5 Bateria Longa Automatizada (2-3h)

Roda 6 configurações × N tamanhos × seeds e gera ranking final:

```powershell
# Bateria padrão (~2-3h): 6 configs × 3 tamanhos × 2 seeds = 36 runs
.\run_benchmark.ps1

# Versão rápida (~10min) para validar
.\run_benchmark.ps1 -Quick

# Customizada
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 3,5,10
.\run_benchmark.ps1 -SkipBaseline   # pular config baseline (mais rápido)
```

**Configurações testadas**:
1. `baseline` — sem RAG
2. `rag_only` — RAG denso puro
3. `rag_rerank` — RAG + cross-encoder
4. `rag_rerank_2stage` — + Stage 1 binário
5. `rag_rerank_rf` — RAG + Random Forest pre-filter
6. `full_stack` — tudo: RF + 2-stage + RAG rerank

**Output**: `outputs/benchmarks/bench_<timestamp>/{summary.json, ranking.json, benchmark.log}`

### 3.6 Saída

Cada run cria uma subpasta própria em `outputs/triage_runs/`. O nome contém as tags
das features usadas:

```
outputs/triage_runs/
└── run_20260503_160000_rag_rerank_rf_stratified_n9/   # rag + rerank + rf + stratified, N=9
    └── results.json
```

O JSON contém:

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
  "results": [
    {
      "attack_type": "DDoS",
      "severity": "high",
      "confidence": 0.85,
      "mitre_techniques": ["T1498", "T1498.001"],
      "explanation": "O fluxo apresenta padrão de inundação volumétrica...",
      "recommendations": ["Ativar rate limiting", "Bloquear IPs de origem"],
      "record_description": "Fluxo TCP duração 0.5s, 230 pacotes...",
      "retrieved_context_titles": ["T1498 - Network DoS", ...],
      "rag_distances": [0.37, 0.40, 0.47],
      "ground_truth": "DDoS",
      "elapsed_seconds": 20.1,
      "validation_errors": []
    }
  ]
}
```

O console exibe métricas detalhadas:

```
RESUMO DA TRIAGEM (9 registros)
Acurácia (categoria exata): 1/9 (11.1%)
Acurácia (ameaça vs benigno): 6/9 (66.7%) | Precisão: 80.0% | Recall: 75.0% | F1: 77.4%
  TP=6 TN=0 FP=1 FN=2
Predições por categoria: {'Botnet': 7, 'Generic': 2}
Distribuição de severidade: {'high': 3, 'medium': 5, 'low': 1}
Confiança média: 0.78
Tempo médio por triagem: 20.34s
```

---

## Desempenho Observado

| Configuração | Tempo/registro | Total 50 registros |
|---|---|---|
| Q8_0 + RTX 5060 8GB (22/33 camadas na GPU) | ~20s | ~17 min |
| Q4_K_M + GPU completa | ~8-10s | ~7 min |
| CPU only | ~90-120s | ~1.5h |

---

## Testes

```powershell
# Rodar todos os 78 testes unitários
python -m pytest tests/ -v

# Só um módulo
python -m pytest tests/test_prompts.py -v
python -m pytest tests/test_text_converter.py -v
```

Cobertura de testes:
- `test_text_converter.py` — conversão de registros CIC/UNSW em descrição textual
- `test_prompts.py` — validação de schema JSON da triagem
- `test_llm_client.py` — parsing de JSON do LLM (com trailing commas, preambles, etc.)
- `test_pipeline_helpers.py` — amostragem estratificada, matching de labels
- `test_preprocessor.py` — limpeza, normalização, correlação

---

## Problemas Conhecidos e Soluções

### ChromaDB corrompido ao inicializar

O `vectorstore.py` detecta e corrige automaticamente. Se persistir:

```powershell
Remove-Item -Recurse -Force data\rag\chromadb
python -m src.rag.pipeline --reset
```

### Modelo de embeddings sem internet

O `embeddings.py` tenta `local_files_only=True` primeiro. O modelo fica em cache em `~/.cache/huggingface/`. Funciona offline após o primeiro download.

### Ollama não encontra o modelo

```powershell
ollama list    # ver nome exato
# Ajustar OLLAMA_MODEL no .env com o nome exato mostrado
```

### Pipeline LLM lento (>60s/registro)

O modelo Q8_0 (8.5GB) pode não caber inteiro na GPU. Verifique com `ollama serve` quantas camadas estão offloaded. Alternativa: baixar o Q4_K_M (~4.5GB) que cabe em GPUs com 6GB+ VRAM:

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; hf_hub_download('fdtn-ai/Foundation-Sec-8B-Q4_K_M-GGUF', filename='foundation-sec-8b-q4_k_m.gguf', local_dir='./models')"
```

Atualize `models\Modelfile` e `.env` com o novo nome.

### LLM classifica tudo como Botnet/C2

É um comportamento esperado para registros UNSW-NB15 com protocolos desconhecidos. O `triage.py` tem um filtro de qualidade RAG (distância > 0.55 descarta o contexto) para reduzir esse viés. Para análise no TCC, use a métrica binária (ameaça vs benigno) em vez da acurácia por categoria exata.

---

## Arquitetura de Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Embeddings | all-MiniLM-L6-v2 (384 dims) | Equilíbrio velocidade/qualidade, funciona offline |
| Banco vetorial | ChromaDB (cosine) | Persistência local, zero dependência externa |
| Normalização | Min-Max [0,1] | Tráfego de rede não é gaussiano — Z-score inadequado |
| Chunking RAG | 1 documento por técnica/regra | Granularidade ideal para recuperação semântica |
| LLM endpoint | `/api/chat` (não `/api/generate`) | Aplica template Llama 3 corretamente (system prompt) |
| Structured output | JSON Schema no Ollama | Grammar sampling garante campos obrigatórios |
| Dataset para triagem | Parquets individuais (não normalizados) | `text_converter` precisa de valores brutos |
| Temperatura LLM | 0.2 | Consistência > criatividade para triagem de segurança |
| Filtro RAG | Descarta se dist > 0.55 | Contexto irrelevante piora classificação |

---

## Comandos Rápidos — Setup Completo do Zero

Estes são todos os passos necessários para colocar o projeto rodando do zero, em ordem:

```powershell
# ── 0. Ativar venv (toda nova sessão) ──
.\.venv\Scripts\Activate.ps1

# ── 1. Instalar dependências (uma vez) ──
pip install -r requirements.txt

# ── 2. Criar .env ──
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_MODEL=foundation-sec-8b-instruct

# ── 3. Pré-processar datasets (~2 min, uma vez) ──
python -m src.data.pipeline

# ── 4. Baixar fontes RAG (~1 min, uma vez) ──
python -m src.rag.download

# ── 5. Indexar base RAG com classes IDS curadas (~2 min, uma vez OU após mudar fontes) ──
python -m src.rag.pipeline --reset --skip-download

# ── 6. Treinar Random Forest (~2 min, uma vez OU após re-processar dados) ──
python -m src.ml.preclassifier --sample-size 200000

# ── 7. Registrar o modelo Foundation-Sec no Ollama (uma vez) ──
# Baixar GGUF (~8.5GB):
python -c "from huggingface_hub import hf_hub_download; hf_hub_download('fdtn-ai/Foundation-Sec-8B-Instruct-Q8_0-GGUF', filename='foundation-sec-8b-instruct-q8_0.gguf', local_dir='./models')"
ollama create foundation-sec-8b-instruct -f models\Modelfile

# ── 8. Iniciar Ollama (terminal separado, manter aberto) ──
ollama serve

# ── 9. Validar com run rápida (~2 min) ──
python -m src.llm.pipeline --n 2 --stratified --use-rf

# ── 10. Avaliação completa RAG vs no-RAG ──
.\run_evaluation.ps1 -N 5

# ── 11. Bateria longa para resultados estatísticos (~2-3h) ──
.\run_benchmark.ps1

# ── Testes ──
python -m pytest tests/ -v
```

### Quando re-rodar cada passo

| Mudança | Re-rodar |
|---------|----------|
| Adicionou novos CSVs em `data/raw/` | passos 3, 5, 6 |
| Editou `src/data/preprocessor.py` | passos 3, 6 |
| Adicionou descrição em `src/rag/sources/ids_classes.py` | passo 5 |
| Editou `src/llm/text_converter.py` ou `prompts.py` | nenhum (efeito imediato na próxima run) |
| Mudou Ollama para outro modelo | passo 8 (reiniciar `ollama serve`) |
| Atualizou Sigma Rules / MITRE | `python -m src.rag.download` + passo 5 |

---

## Próximas Etapas (Etapa 4)

- `src/app/` — Interface Streamlit para demonstração interativa
- `src/evaluation/` — Módulo de métricas quantitativas completo (matriz de confusão, curva ROC, análise por classe)
- Análise qualitativa das explicações geradas (coerência, relevância das técnicas MITRE)
- Manuscrito final do TCC

---

## Equipe

- Igor Mamus dos Santos
- Felipe Ribas Boaretto
- Leonardo dos Santos Marques
- João Vitor Manfrim

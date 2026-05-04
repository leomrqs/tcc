# Reprodutibilidade dos Experimentos

Guia completo para replicar todos os experimentos do TCC do zero.

---

## Pré-requisitos

| Componente | Versão | Onde obter |
|-----------|--------|-----------|
| Python | 3.13 | python.org |
| CUDA | 12.x | nvidia.com |
| Ollama | 0.12.3+ | ollama.com |
| Git | qualquer | git-scm.com |
| PowerShell | 5.1+ | nativo no Windows 10/11 |

**Hardware mínimo**: 16GB RAM, GPU 8GB VRAM (para carregar 22/33 camadas do modelo Q8_0).

**Hardware usado nos experimentos**: Windows 11 Pro, RTX 5060 8GB, 32GB RAM.

---

## Etapa 0 — Preparação do Ambiente

```powershell
# Clonar repositório (ou usar a pasta do projeto)
cd c:\Users\leomr\Documents\GoogleDrive\Workspace\Projetos_Pessoais\TCC\tcc

# Criar e ativar venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
```

### Arquivo .env

Criar `tcc/.env` com:
```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=foundation-sec-8b-instruct
```

---

## Etapa 1 — Dados Brutos

### Obter os datasets

**CIC-IDS2017**: https://www.unb.ca/cic/datasets/ids-2017.html
- Baixar todos os CSVs (Monday, Tuesday, Wednesday, Thursday, Friday)
- Salvar em `data/raw/cic/`

**UNSW-NB15**: https://research.unsw.edu.au/projects/unsw-nb15-dataset
- Baixar os 4 arquivos CSV + o arquivo de features (UNSW-NB15_features.csv)
- Salvar em `data/raw/unsw/`

### Pré-processar

```powershell
python -m src.data.pipeline
```

**Saídas esperadas** (em `data/processed/`):
- `cic_ids2017_clean.parquet` (~2.83M registros)
- `unsw_nb15_clean.parquet` (~2.54M registros)
- `unified_dataset.parquet` (~5.37M registros, normalizado)
- `normalization_params.json`
- `preprocessing_report.json`

**Tempo estimado**: 15-30 minutos dependendo do hardware.

---

## Etapa 2 — Base de Conhecimento RAG

### Baixar e indexar

```powershell
python -m src.rag.pipeline
```

**O que faz**:
1. Baixa MITRE ATT&CK Enterprise JSON (~49MB do GitHub da MITRE)
2. Faz `git clone --depth 1` do repositório SigmaHQ (~50MB)
3. Parseia 691 técnicas MITRE + 3.728 regras Sigma
4. Gera embeddings com `all-MiniLM-L6-v2` (GPU se disponível)
5. Indexa no ChromaDB em `data/rag/chromadb/`

**Tempo estimado**: 5-10 minutos (download dependente da internet, indexação ~2 minutos com GPU).

**Verificar**:
```powershell
python -m src.rag.pipeline --test
```
Deve retornar 5 documentos para uma query de teste.

### Re-indexar do zero (se necessário)

```powershell
python -m src.rag.pipeline --reset
```

---

## Etapa 3 — Modelo LLM

### Registrar o modelo no Ollama

O modelo `foundation-sec-8b-instruct-q8_0.gguf` deve estar em `models/`.

```powershell
# Em um terminal separado, iniciar o Ollama
ollama serve

# Em outro terminal (com venv ativo):
ollama create foundation-sec-8b-instruct -f models/Modelfile
ollama list  # verificar se aparece na lista
```

**Conteúdo do Modelfile** (`models/Modelfile`):
```
FROM ./foundation-sec-8b-instruct-q8_0.gguf
```

---

## Etapa 4 — Executar Avaliação

### Avaliação completa (RAG + No-RAG com mesmo seed)

```powershell
.\run_evaluation.ps1 -N 5
```

### Com seed fixo (para reprodutibilidade exata da amostra)

```powershell
.\run_evaluation.ps1 -N 5 -Seed 42
```

### Dataset específico

```powershell
.\run_evaluation.ps1 -N 5 -Dataset cic
.\run_evaluation.ps1 -N 5 -Dataset unsw
.\run_evaluation.ps1 -N 5 -Dataset unified
```

### Apenas um modo

```powershell
.\.venv\Scripts\python.exe -m src.llm.pipeline --n 5 --dataset unified --stratified --seed 42
.\.venv\Scripts\python.exe -m src.llm.pipeline --n 5 --dataset unified --stratified --no-rag --seed 42
```

---

## Etapa 5 — Testes

```powershell
python -m pytest tests/ -v
```

**78 testes, todos devem passar.** Se algum falhar:

| Falha | Causa provável |
|-------|---------------|
| `test_text_converter` | Parquets não gerados (Etapa 1 pendente) |
| `test_prompts` | Mudança no JSON Schema |
| `test_llm_client` | Mudança na estrutura do payload |
| `test_pipeline_helpers` | Mudança na lógica de amostragem |
| `test_preprocessor` | Mudança nas colunas dos datasets |

---

## Onde ficam os resultados

```
outputs/
└── triage_runs/
    ├── run_<timestamp>_rag_n<N>_stratified/
    │   └── results.json
    └── run_<timestamp>_norag_n<N>_stratified/
        └── results.json
```

O nome da pasta codifica os parâmetros: timestamp, modo (rag/norag), N por classe, estratificação.

---

## Seeds Usados nos Experimentos do TCC

| Data | Seed | Runs | Observações |
|------|------|------|-------------|
| 2026-05-03 | 537631 | rag+norag, N=7 | Descartada — bug #19 (HTTP 500) |
| 2026-05-03 | (fixo) | rag, N=10 | run_20260503_123456 — válida |

> Atualizar esta tabela conforme novas runs forem realizadas.

---

## Checklist de Reprodutibilidade

- [ ] Dataset CIC baixado e em `data/raw/cic/`
- [ ] Dataset UNSW baixado e em `data/raw/unsw/`
- [ ] `python -m src.data.pipeline` executado com sucesso
- [ ] `python -m src.rag.pipeline` executado com sucesso
- [ ] `ollama serve` rodando em terminal separado
- [ ] `ollama list` mostra `foundation-sec-8b-instruct`
- [ ] `python -m pytest tests/ -v` — 78 passed
- [ ] `.\run_evaluation.ps1 -N 5 -Seed 42` executa sem erros HTTP 500
- [ ] Resultados em `outputs/triage_runs/`

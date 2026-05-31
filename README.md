# Triagem Explicada de Incidentes de Rede com LLM e RAG Local

**Projeto Transformador I** — Bacharelado em Ciência da Computação, PUCPR
Turma 7B — Grupo 3

---

## Visão Geral

Sistema **100% local** de triagem automática de incidentes de rede. Nenhum dado sai
da máquina — LLM, embeddings, modelos de ML e base vetorial rodam localmente.

A arquitetura combina **duas camadas complementares**:

1. **Camada de ML clássico** — um classificador binário (Benign vs Threat) que filtra,
   com rigor estatístico e latência de milissegundos, o tráfego benigno em massa.
2. **Camada de LLM + RAG** — um modelo especializado em cibersegurança que produz a
   **triagem explicada** (categoria + severidade + técnicas MITRE + justificativa +
   recomendações) dos casos que importam, contextualizada por uma base de conhecimento local.

> A pergunta de pesquisa não é "o LLM classifica melhor que ML?" (não classifica, e não
> precisa). É: **"um pipeline local de duas camadas produz triagens corretas na detecção
> e úteis na explicação, sem enviar dados para fora?"**

### Componentes

- **Estudo comparativo de ML** (Benign vs Threat): até 10 modelos clássicos
  (RandomForest, ExtraTrees, HistGradientBoosting, **XGBoost**, **LightGBM**,
  DecisionTree, LogisticRegression, GaussianNB, KNN, MLP) + **ensemble por soft-voting**,
  treinados nos datasets **completos** com cross-validation (média ± desvio), ROC-AUC e PR-AUC.
- **LLM especializado** (Foundation-Sec-8B-Instruct via Ollama) com prompt
  chain-of-thought + few-shot e saída JSON estruturada.
- **RAG local**: MITRE ATT&CK Enterprise (691 técnicas) + Sigma Rules (3.728 regras)
  + **base curada de descrições de classes IDS** (16 docs canônicos), com
  **cross-encoder re-ranking** (`ms-marco-MiniLM-L-6-v2`).
- **Pré-classificador** plugável (RF, melhor modelo ou ensemble) que filtra Benigns antes do LLM.
- **Avaliação rica**: métricas por classe, matriz de confusão, agregação de runs e
  **scoring automático da qualidade das explicações** (validade MITRE, relevância,
  consistência, ancoragem no RAG).
- **Dois datasets**: CIC-IDS2017 (~2,83M registros) e UNSW-NB15 (~2,54M registros).
- **Baterias automatizadas** com progresso/ETA no terminal e saída agregável (manifesto JSONL).

---

## Resultados Principais (Data Science)

Resumo dos achados; tabelas completas em [Resultados Detalhados](#resultados-detalhados).

1. **A camada de ML é o que torna o sistema viável.** Em tráfego realista (~87% benigno),
   o LLM isolado é inutilizável — classifica **todo benigno como ameaça** (acurácia
   binária **0,125**, falso-positivo em massa). Com o pré-filtro de ML: binária **1,000**
   e **~7× mais rápido** (o benigno pula o LLM). *É o argumento central da arquitetura.*

2. **O ML clássico satura a detecção binária** (~99% em ambos os datasets, treinado em
   milhões de registros com cross-validation de desvio mínimo). **XGBoost** é o melhor
   (CIC: F1 0,9976 / ROC-AUC 1,0000; UNSW: F1 0,9731 / ROC-AUC 0,9998).

3. **ML e LLM são complementares, não redundantes.** Decompondo a acurácia exata: o ML
   acerta o benigno; o **RAG melhora a categorização das ameaças** (no CIC). Juntos
   superam cada parte isolada.

4. **A contribuição do RAG depende do dataset**: ajuda no CIC, é neutro/negativo no
   UNSW (protocolos abstratos → contexto recuperado menos pertinente).

5. **Teto de acurácia exata é limitação intrínseca do dado**, não do modelo: um fluxo
   individual de DDoS, DoS e Reconnaissance é morfologicamente quase idêntico — visível
   na matriz de confusão (viés sistemático para "Reconnaissance").

6. **O two-stage (Stage 1 binário do LLM) é nocivo** e foi descartado, com evidência
   consistente (recall despenca, FN em massa).

---

## Arquitetura — as duas camadas

```
                       registro / incidente de rede
                                   │
        ┌──────────────────────────▼───────────────────────────┐
        │  CAMADA 1 — Classificador clássico (Benign vs Threat) │
        │  RandomForest / XGBoost(best) / Ensemble              │
        │  treinado nos datasets completos, ~99% acc            │
        └──────────────────────────┬───────────────────────────┘
                                   │
            Benign (conf ≥ 0,95) ──┤──►  decide Benign, PULA o LLM (ms)
                                   │
              Threat / incerteza ──▼
        ┌──────────────────────────────────────────────────────┐
        │  CAMADA 2 — LLM especializado + RAG                   │
        │  descrição textual → recupera contexto (MITRE/Sigma/  │
        │  classes IDS) → cross-encoder rerank → prompt CoT →   │
        │  JSON: categoria + severidade + MITRE + explicação +  │
        │  recomendações                                        │
        └──────────────────────────────────────────────────────┘
```

Cada camada é avaliada pelo que entrega: a Camada 1 pela **detecção** (rigor
estatístico em milhões de registros); a Camada 2 pela **qualidade da explicação** dos
casos relevantes.

---

## Estrutura do Projeto

```
tcc/
├── src/
│   ├── config.py                   # Caminhos, constantes, label maps
│   ├── data/                       # Etapa 1: ingestão e pré-processamento
│   │   ├── loader.py               # Carrega CSVs brutos (CIC e UNSW)
│   │   ├── preprocessor.py         # Limpeza, encoding, normalização
│   │   └── pipeline.py             # Orquestrador CLI da Etapa 1
│   ├── rag/                        # Etapa 2: base de conhecimento RAG
│   │   ├── download.py             # Baixa MITRE ATT&CK e Sigma Rules
│   │   ├── sources/{mitre,sigma,ids_classes}.py  # Parsers + base curada
│   │   ├── embeddings.py           # sentence-transformers (all-MiniLM-L6-v2)
│   │   ├── vectorstore.py          # ChromaDB (cosine), auto-reparo
│   │   ├── retriever.py            # Busca densa + cross-encoder rerank (top-20→top-5)
│   │   └── pipeline.py             # Orquestrador CLI da Etapa 2
│   ├── ml/                         # Etapa 2.5: classificadores clássicos
│   │   ├── models.py               # Registry de modelos + ensemble + prep de features
│   │   ├── benchmark.py            # Estudo comparativo (CV, ROC/PR-AUC, plots, relatórios)
│   │   └── preclassifier.py        # Atalho RF + PreClassifier (rf/best/ensemble)
│   ├── llm/                        # Etapa 3: triagem com LLM
│   │   ├── text_converter.py       # features → descrição discriminativa + assinaturas
│   │   ├── llm_client.py           # Cliente Ollama (/api/chat + JSON Schema)
│   │   ├── prompts.py              # chain-of-thought + few-shot
│   │   ├── triage.py               # TriageEngine: pré-filtro + 2-stage + RAG + LLM
│   │   └── pipeline.py             # Orquestrador CLI da Etapa 3
│   ├── evaluation/                 # Avaliação e análise
│   │   ├── metrics.py              # Por classe, confusão, agregação de runs
│   │   ├── explanation_quality.py  # Scoring automático das explicações
│   │   └── runlog.py               # Persistência padronizada (schema v3 + manifesto)
│   └── utils/{logger,progress}.py  # Logger UTF-8 + progresso/ETA das baterias
├── tests/                          # 97 testes unitários (pytest)
├── data/                           # (raw/processed/chromadb/ml_models — NÃO versionados)
├── models/Modelfile                # Receita do GGUF no Ollama (modelo não versionado)
├── outputs/                        # Resultados atuais da v3 (ver "Formato de Saída")
├── outputsold/                     # Resultados da v2 — arquivo histórico (evolução do projeto)
├── run_benchmark.ps1               # Ablation do LLM (7 configs × tamanhos × seeds)
├── run_ml_benchmark.ps1            # Estudo comparativo de ML
├── run_night.ps1                   # Orquestrador overnight (CIC + UNSW + high-benign)
├── run_evaluation.ps1              # RAG vs no-RAG sequencial (rápido)
├── requirements.txt
└── README.md
```

> **Não versionados** (regeneráveis, e/ou grandes demais para o GitHub): `data/raw/`,
> `data/processed/`, `data/rag/chromadb/`, `data/ml_models/` (`*.joblib`), o GGUF do
> modelo. Todos são reconstruídos pelos comandos de setup.

---

## Setup Inicial

### Pré-requisitos

- Python 3.11+ · Git · [Ollama](https://ollama.com/download) · GPU NVIDIA recomendada (~5× mais rápido que CPU)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Crie o `.env` na raiz:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=foundation-sec-8b-instruct
```

Ordem das etapas: **1** pré-processar → **2** indexar RAG → **2.5** treinar ML →
**3** registrar LLM no Ollama. Bloco copy-paste completo em
[Comandos Rápidos](#comandos-rápidos--setup-completo-do-zero).

---

## Etapa 1 — Pré-processamento dos Datasets

Coloque os CSVs em `data/raw/cic-ids2017/` ([CIC-IDS2017](https://www.unb.ca/cic/datasets/ids-2017.html))
e `data/raw/unsw-nb15/` ([UNSW-NB15](https://research.unsw.edu.au/projects/unsw-nb15-dataset)).

```powershell
python -m src.data.pipeline                 # ambos (~2 min)
python -m src.data.pipeline --dataset cic   # só um
python -m src.data.pipeline --sample 0.1    # teste rápido (10%)
```

**O que é feito**: remove colunas identificadoras (IPs, portas, timestamps —
prevenção de data leakage); troca infinitos/NaN por mediana; clipa negativos
impossíveis; remove 8 colunas constantes e 25+ com correlação >0,95; mapeia rótulos
para 15 categorias unificadas; normaliza MinMax no dataset unificado.

**Saída** (`data/processed/`): `cic_ids2017_clean.parquet` (2,83M, bruto),
`unsw_nb15_clean.parquet` (2,54M, bruto), `unified_dataset.parquet` (normalizado),
+ `normalization_params.json`, `preprocessing_report.json`.

---

## Etapa 2 — Base de Conhecimento RAG

```powershell
python -m src.rag.download                          # MITRE STIX (~49MB) + Sigma Rules
python -m src.rag.pipeline --test                   # indexa + testa busca
python -m src.rag.pipeline --reset --skip-download  # re-indexa do zero
```

> Ao editar a base curada (`src/rag/sources/ids_classes.py`), rode
> `python -m src.rag.pipeline --reset --skip-download`.

**Saída** (`data/rag/chromadb/`): ~4.435 documentos — 16 descrições canônicas das
classes IDS (curado) + 691 técnicas MITRE + 3.728 regras Sigma.

---

## Etapa 2.5 — Classificadores clássicos e estudo comparativo

A camada de ML filtra o tráfego benigno antes do LLM (resolve o TN=0 e acelera). Como
ela carrega boa parte do desempenho, é tratada como objeto de estudo: um **benchmark
de até 10 modelos** nos datasets completos, com cross-validation.

```powershell
python -m src.ml.benchmark                  # CIC + UNSW, 200k/dataset, CV 5-fold (~10-30 min)
python -m src.ml.benchmark --sample-size 0  # datasets completos (várias horas)
python -m src.ml.benchmark --no-slow --cv-folds 3   # pula KNN/MLP (rápido)

.\run_ml_benchmark.ps1            # via script, com progresso/ETA
.\run_ml_benchmark.ps1 -Full      # datasets completos
```

**Saída**: modelos em `data/ml_models/` (`rf_<ds>`, `best_<ds>`, `ensemble_<ds>`,
`.joblib`) e relatórios em `outputs/ml_benchmark/bench_<ts>/`
(`model_comparison.{json,md}` + gráficos `metrics_`, `roc_`, `confusion_`, `importance_`).

Resultados em [Resultados Detalhados → ML](#a-estudo-comparativo-de-ml).

---

## Etapa 3 — Triagem com LLM

### 3.1 Instalar o modelo

```powershell
# GGUF (~8.5GB) — na pasta tcc/
python -c "from huggingface_hub import hf_hub_download; hf_hub_download('fdtn-ai/Foundation-Sec-8B-Instruct-Q8_0-GGUF', filename='foundation-sec-8b-instruct-q8_0.gguf', local_dir='./models')"
ollama create foundation-sec-8b-instruct -f models\Modelfile
ollama list
```

### 3.2 Rodar (com `ollama serve` aberto em outro terminal)

```powershell
# Stack recomendada: pré-filtro (melhor modelo = XGBoost) + RAG + rerank
python -m src.llm.pipeline --n 10 --stratified --use-rf --clf-kind best

python -m src.llm.pipeline --n 10 --stratified                 # sem pré-filtro
python -m src.llm.pipeline --n 10 --stratified --no-rag        # baseline
python -m src.llm.pipeline --n 10 --dataset cic --stratified   # só CIC
python -m src.llm.pipeline --index 12345                       # registro específico
```

#### Flags

| Flag | Default | Descrição |
|------|---------|-----------|
| `--n N` | 10 | Nº de registros a triar |
| `--stratified` | false | Amostragem estratificada (≈igual por classe) |
| `--dataset {unified,cic,unsw}` | unified | Qual dataset |
| `--seed N` | aleatório | Seed da amostragem |
| `--no-rag` / `--no-rerank` | false | Desativa RAG / cross-encoder |
| `--use-rf` | false | Ativa o pré-classificador clássico |
| `--clf-kind {rf,best,ensemble}` | rf | Variante do pré-classificador |
| `--two-stage` | false | Stage 1 binário (experimental — **nocivo**, ver resultados) |
| `--rf-threshold 0.95` / `--rag-threshold 0.55` / `--top-k 5` | — | Limiares |
| `--run-dir PATH` | outputs/triage_runs | Pasta base da run |

### 3.3 Baterias

```powershell
# Ablation do LLM — 7 configs × tamanhos × seeds (com progresso/ETA)
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 30,50
.\run_benchmark.ps1 -Dataset cic -Sizes 40          # só CIC
.\run_benchmark.ps1 -Stratified:$false -Sizes 60    # tráfego natural (high-benign)
.\run_benchmark.ps1 -Quick                          # validação rápida

# Orquestrador overnight: CIC + UNSW + high-benign em sequência
.\run_night.ps1
```

**7 configurações do ablation**: `baseline_norag`, `norag_rf`, `rag_only`,
`rag_rerank`, `rag_rerank_rf`, `rag_rerank_best` (recomendada), `rag_rerank_rf_2stage`.

---

## Metodologia de Avaliação

**Métricas** (operando sobre os registros triados):

- **Acurácia exata**: categoria predita = ground truth (com aliases).
- **Acurácia binária** (métrica primária operacional): ameaça vs benigno.
- **Precisão / Recall / F1 / Especificidade** + matriz de confusão (TP/TN/FP/FN).
  FN = ameaça não detectada = o erro mais crítico.
- **Por classe** (precisão/recall/F1/suporte), **macro-F1** e **weighted-F1**.
- **Qualidade da explicação** (proxy automático): validade MITRE, relevância,
  consistência, ancoragem no RAG.

**Ablation study**: as configurações são executadas com o **mesmo seed** de amostragem
— a única variável é a combinação de componentes ativos.

**Agregação para significância**: cada run individual triou poucos registros; o módulo
`metrics.py --aggregate` faz **pool dos registros** de várias runs da mesma config,
elevando o N efetivo. A camada de ML, por outro lado, é avaliada diretamente em
milhões de registros com **cross-validation** (média ± desvio).

---

## Resultados Detalhados

### A. Estudo comparativo de ML

Treinado nos datasets **completos** (CIC 2,83M / UNSW 2,54M), holdout 80/20
estratificado, seed 42, cross-validation 5-fold.

**CIC-IDS2017 — melhor: XGBoost**

| Modelo | F1 | ROC-AUC | CV F1 (μ±σ) |
|---|---|---|---|
| **XGBoost** | **0,9976** | **1,0000** | 0,9963 ± 0,0009 |
| Ensemble (soft-voting) | 0,9974 | 0,9999 | — |
| RandomForest | 0,9970 | 0,9999 | 0,9937 ± 0,0013 |
| LightGBM | 0,9958 | 0,9991 | 0,9965 ± 0,0004 |
| LogisticRegression | 0,7648 | 0,9735 | 0,7828 ± 0,0277 |
| GaussianNB | 0,5501 | 0,8349 | 0,5574 ± 0,0091 |

**UNSW-NB15 — melhor: XGBoost**: F1 **0,9731**, ROC-AUC 0,9998, CV F1 0,9671 ± 0,0020.

**Leitura**: ensembles de árvore e boosting saturam a tarefa (~0,99); modelos lineares
e Naive Bayes despencam — evidência de que as features de fluxo são **fortemente
não-lineares**. Desvios de CV minúsculos ⇒ resultado estável (significância estatística).
Pré-filtro: ~98-99% de cobertura de Benigns com conf≥0,95; **risco** (ameaça filtrada
como benigna) < 0,03%.

### B. Ablation do LLM (unified, N=116/config — pool de 4 runs)

| Configuração | Exata | Binária | TN | FN | Expl. |
|---|---|---|---|---|---|
| baseline (norag) | 0,078 | 0,905 | 0 | 0 | 0,945 |
| norag-rf | 0,164 | **1,000** | 11 | 0 | 0,951 |
| rag | 0,112 | 0,897 | 0 | 1 | 0,954 |
| rag-rerank | 0,129 | 0,905 | 0 | 0 | 0,934 |
| rag-rerank-rf | 0,215 | **1,000** | 11 | 0 | 0,931 |
| **rag-rerank-best** | **0,224** | **1,000** | 11 | 0 | 0,936 |
| rag-rerank-rf-2stage | 0,155 | 0,457 | 11 | **63** | 0,951 |

**Decomposição da exata** (acerto de benigno vs de ameaça): o **pré-filtro ML** acerta
o benigno (0 → 11); o **RAG+rerank** melhora a categoria da ameaça (9 → 15 acertos).
Juntos somam — *complementaridade*. O **two-stage** é catastrófico (FN=63).
A binária das configs com pré-filtro é **1,000 com desvio 0** entre seeds (robusto).

### C. Por dataset (run_night, 3 seeds/fase)

| | melhor config | exata | RAG ajuda? |
|---|---|---|---|
| **CIC** | rag-rerank-rf | **0,377** | **Sim** (rag 0,245 vs baseline 0,057) |
| **UNSW** | norag-rf | 0,222 | **Não** (rag-rerank 0,044 < baseline 0,089) |

A utilidade do RAG é **dependente do dataset**: ajuda no CIC, neutro/negativo no UNSW.

### D. Tráfego realista (high-benign, ~87% benigno) — o resultado mais forte

| | Binária | FP | s/registro |
|---|---|---|---|
| LLM-só (baseline/rag) | **0,125** | 63/63 benignos | ~30 s |
| **Com pré-filtro ML** | **1,000** | 0 | **~4 s (≈7× mais rápido)** |

Sem a camada de ML, o LLM **soterra o analista de falsos-positivos** (classifica todo
benigno como ameaça). Com ela: detecção perfeita e ~7× mais rápido (benigno pula o LLM).

> **Honestidade**: a acurácia *exata* nas configs com pré-filtro neste cenário (~0,93)
> é inflada pela predominância de benignos — a leitura correta aqui é a **binária** e o
> **throughput**, não a exata.

### E. Teto da acurácia exata (limitação do dado)

A matriz de confusão revela **viés sistemático para Reconnaissance**: DDoS, Generic,
Exploits etc. são quase sempre preditos como Reconnaissance, porque um fluxo individual
(poucos pacotes, curta duração, unidirecional) casa com a assinatura de scan. Só
classes com assinatura de fluxo distinta (DoS, Reconnaissance) recebem acerto. Não é
falha do modelo — é a **ambiguidade intrínseca do fluxo isolado**, já que os rótulos
foram atribuídos observando padrões **agregados** de milhares de fluxos.

### Desempenho de inferência (LLM)

| Configuração | Tempo/registro |
|---|---|
| Q8_0 + RTX 5060 8GB (22/33 camadas na GPU) | ~20-28 s |
| Q4_K_M + GPU completa | ~8-10 s |
| CPU only | ~90-120 s |

---

## Qualidade das Explicações

`src/evaluation/explanation_quality.py` mede um **proxy automático** da explicação
gerada pelo LLM (a contribuição central do projeto):

- **validade MITRE** — as técnicas T#### citadas existem no ATT&CK? (anti-alucinação,
  validado contra os IDs reais extraídos do STIX);
- **relevância** — a explicação menciona os sinais reais do registro?
- **consistência** — severidade coerente com a categoria, confiança em [0,1]?
- **ancoragem** — a explicação se apoia no contexto RAG recuperado?

O composto fica ~0,93-0,96 nas runs. **É um indicador de triagem, não prova de
qualidade** — deve ser complementado por **avaliação humana** (planejada, 20-30 casos
com rubrica), validando o proxy.

```powershell
python -m src.evaluation.explanation_quality outputs/triage_runs/run_...
```

---

## Formato de Saída e Análise

Cada run grava `results.json` no **schema v3** e adiciona uma linha ao manifesto
`outputs/triage_runs/runs_index.jsonl` — a "pilha de dados" do projeto, pronta para pandas.

**Nome de pasta parseável**: `run_<timestamp>_<dataset>_<config>_n<N>_seed<seed>/`

**`results.json`** (blocos): `run` (metadados + flags), `summary` (linha achatada),
`metrics` (por classe + confusão), `explanation_quality` (agregado), `records` (cada
registro: attack_type, severity, confidence, mitre_techniques, explanation,
recommendations, retrieved_context_titles, rag_distances, ground_truth, …).

```powershell
# métricas detalhadas de uma run (por classe + confusão + gráficos)
python -m src.evaluation.metrics outputs/triage_runs/run_...
# agregar várias runs (pool -> N relevante)
python -m src.evaluation.metrics --aggregate "outputs/triage_runs/*rag-rerank-best*"
```

```python
import pandas as pd
df = pd.read_json("outputs/triage_runs/runs_index.jsonl", lines=True)
df.groupby(["dataset", "config"])[["accuracy_binary", "f1", "explanation_composite"]].mean()
```

---

## Jornada Experimental — o que observamos e como superamos

Cada decisão de design veio de uma observação empírica durante o desenvolvimento. Esta
é a espinha dorsal de data science do projeto — o raciocínio por trás de cada escolha:

| Observação (o que vimos) | Resposta (como superamos) |
|---|---|
| O LLM **nunca prediz Benign** (TN=0): a binária travava em ~0,90 e, em tráfego realista, despencava para **0,125** (todo benigno virava falso-positivo) | Adicionamos a **camada de ML clássico** como pré-filtro → TN restaurado, binária **1,000** e ~7× mais rápido |
| A acurácia **exata é baixa (~15%) e estável** mesmo no melhor modelo | Diagnóstico: **teto intrínseco do dado** — fluxo isolado de DDoS/DoS/Recon é ambíguo. Confirmado na matriz de confusão (viés sistemático para Reconnaissance) |
| Runs de **7-10 registros** não têm significância estatística | **Pool de runs** (agregação) eleva o N efetivo; e o **benchmark de ML** roda em milhões de registros com cross-validation |
| O **RAG às vezes piorava** a classificação (recuperava contexto irrelevante) | **Filtro de distância densa > 0,55** descarta o contexto quando o melhor doc é semanticamente distante |
| O **rerank parecia atrapalhar** (visto em 1 seed) | Mais seeds revelaram que era **ruído** — com 4 runs o rerank ajuda a categorização |
| A amostragem estratificada **sub-amostra o benigno** (~1 por run) | Criamos a condição **high-benign** (amostragem natural) → ~60 benignos/config, firmando a especificidade |
| Estratificado no `unified` **não separa os datasets** | Runs **CIC-only / UNSW-only** → descoberta: o RAG ajuda no CIC, mas é neutro/negativo no UNSW |
| O **two-stage** (Stage 1 binário do LLM) derrubava o recall | **Desativado**, com evidência consistente (FN em massa nos 3 cenários) |
| A explicação (contribuição central) **não era medida** | Módulo de **qualidade das explicações** (validade MITRE anti-alucinação, relevância, consistência, ancoragem) |
| Modelos full-data **> 100MB** travavam o `git push` | Modelos **fora do versionamento** (regeneráveis via `src.ml.benchmark`) |

### Correções de qualidade de dado (rigor)

Alguns bugs eram de **dados**, não de código — e detectá-los foi parte do trabalho de data science:

- **`Flow Packets/s` do CIC vinha em microssegundos** → gerava taxas absurdas (FLOOD
  para um fluxo de 2 pacotes em 48s). Corrigido recalculando a taxa real (`pacotes / duração`).
- **A triagem carregava o `unified_dataset` normalizado [0,1]** → descrições vazias
  ("0 pacotes", "duração instantânea"). Corrigido para usar os parquets individuais
  (valores brutos), que o `text_converter` precisa.
- **A confiança do LLM vinha em 0-100** (ex.: `85`) → normalizada para [0,1] **antes** da validação.
- **Bug no loop de seeds da bateria** (variável `$s` colidindo) rodava só metade das
  runs → corrigido; re-execução completa.

## Evolução do Projeto (resumo por versão)

| Versão | Foco | Principais entregas |
|--------|------|---------------------|
| **v1** | Pipeline inicial | Pré-processamento, RAG (MITRE+Sigma), triagem LLM básica |
| **v2** | Qualidade do LLM | Prompts chain-of-thought + few-shot, cross-encoder rerank, base curada de classes IDS, Random Forest pré-filtro, text_converter discriminativo |
| **v3** | Rigor + coerência | **Estudo comparativo de 10 modelos** (XGBoost/LightGBM) + ensemble, **framework de avaliação** (métricas por classe, agregação, **qualidade das explicações**), **formato de saída padronizado** (schema v3 + manifesto), baterias por dataset e high-benign, progresso/ETA, logger UTF-8. Testes 78 → 97 |

A v3 atacou os pontos fracos de rigor: a detecção passou de "amostras de 7-10
registros" para "milhões de registros com cross-validation", e a contribuição central
(as explicações) passou a ser **medida**.

> **Arquivo histórico (`outputsold/`)**: preserva os resultados das execuções da **v2**
> (formato antigo de saída — baterias, runs de triagem e comparativos). É mantido
> versionado **de propósito**, como evidência da evolução do projeto ao longo do tempo
> e da diversidade de experimentos realizados. Os resultados atuais (v3) ficam em
> `outputs/`; os da v2, em `outputsold/`.

---

## Arquitetura de Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Duas camadas (ML + LLM) | ML detecta, LLM explica | Cada um onde tem vantagem; LLM-só inviável em tráfego real |
| Pré-filtro | XGBoost (`best`) ou ensemble | Melhor F1/cobertura; ensemble é mais conservador (menor risco) |
| ML por dataset | CIC e UNSW separados | Features distintas — modelo único exigiria imputação massiva |
| Embeddings | all-MiniLM-L6-v2 (384d) | Equilíbrio velocidade/qualidade, offline |
| Banco vetorial | ChromaDB (cosine) | Persistência local, zero dependência externa |
| LLM endpoint | `/api/chat` (não `/generate`) | Aplica o template Llama 3 (system prompt) |
| Structured output | JSON Schema no Ollama | Grammar sampling garante os campos obrigatórios |
| Dataset p/ triagem | Parquets individuais (não normalizados) | `text_converter` precisa de valores brutos |
| Temperatura LLM | 0.2 | Consistência > criatividade |
| Filtro de qualidade RAG | descarta se dist densa > 0,55 | Contexto irrelevante piora a classificação |
| Two-stage | desativado | Nocivo (recall despenca) — evidência no ablation |

---

## Testes

```powershell
python -m pytest tests/ -v        # 97 testes
```

Cobertura: `test_text_converter`, `test_prompts`, `test_llm_client`,
`test_pipeline_helpers`, `test_preprocessor`, `test_rag_parsing` (parsing MITRE/Sigma),
`test_ml_models` (prep de features, registry, ensemble), `test_evaluation` (métricas,
qualidade das explicações, runlog, progresso).

---

## Problemas Conhecidos e Soluções

| Sintoma | Causa | Solução |
|---|---|---|
| `Error loading hnsw index` | ChromaDB corrompido | `Remove-Item -Recurse data\rag\chromadb` + `python -m src.rag.pipeline --reset` |
| `getaddrinfo failed` no embedding | Sem internet | `local_files_only=True` já tratado; cache em `~/.cache/huggingface/` |
| Ollama não encontra o modelo | Nome errado no `.env` | `ollama list` → ajustar `OLLAMA_MODEL` |
| Pipeline LLM >60s/registro | Q8_0 não cabe na GPU | Usar Q4_K_M (`fdtn-ai/Foundation-Sec-8B-Q4_K_M-GGUF`) + atualizar Modelfile/.env |
| Push rejeitado no git | `.joblib` > 100MB | Modelos não são versionados (gitignored) — regenere com `src.ml.benchmark` |

---

## Comandos Rápidos — Setup Completo do Zero

```powershell
.\.venv\Scripts\Activate.ps1                          # 0. venv
pip install -r requirements.txt                       # 1. deps
# 2. criar .env (OLLAMA_HOST, OLLAMA_MODEL)
python -m src.data.pipeline                            # 3. pré-processar (~2 min)
python -m src.rag.download                             # 4. baixar fontes RAG
python -m src.rag.pipeline --reset --skip-download     # 5. indexar RAG
python -m src.ml.benchmark                             # 6. treinar/comparar ML (gera ensemble)
# 7. registrar o LLM no Ollama:
python -c "from huggingface_hub import hf_hub_download; hf_hub_download('fdtn-ai/Foundation-Sec-8B-Instruct-Q8_0-GGUF', filename='foundation-sec-8b-instruct-q8_0.gguf', local_dir='./models')"
ollama create foundation-sec-8b-instruct -f models\Modelfile
ollama serve                                           # 8. terminal separado, manter aberto
python -m src.llm.pipeline --n 5 --stratified --use-rf --clf-kind best   # 9. validar
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 30,50     # 10. ablation do LLM
python -m pytest tests/ -v                             # testes
```

| Mudou | Re-rodar |
|-------|----------|
| Novos CSVs em `data/raw/` | passos 3, 5, 6 |
| `src/data/preprocessor.py` | passos 3, 6 |
| `src/rag/sources/ids_classes.py` | passo 5 |
| `src/llm/text_converter.py` ou `prompts.py` | nada (efeito imediato) |
| Atualizar Sigma/MITRE | `src.rag.download` + passo 5 |

---

## Próximas Etapas

- **Avaliação humana** das explicações (20-30 casos, rubrica) validando o proxy automático.
- **Agregação por incidente** (re-processar do bruto mantendo IP/porta/tempo como chave
  de agrupamento) — janela de fluxos em vez de fluxo único, para atacar o teto da
  acurácia exata na raiz (ablation de granularidade: por-fluxo vs por-incidente).
- **Verificador de fidelidade** das explicações (cruzar o que o LLM afirma vs os valores
  reais do fluxo — detecção automática de alucinação).
- `src/app/` — interface Streamlit de demonstração.
- Manuscrito final do TCC.

---

## Equipe

- Igor Mamus dos Santos
- Felipe Ribas Boaretto
- Leonardo dos Santos Marques
- João Vitor Manfrim

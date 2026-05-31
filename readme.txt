========================================================================
TRIAGEM EXPLICADA DE INCIDENTES DE REDE COM LLM E RAG LOCAL
Projeto Transformador I - Bacharelado em Ciencia da Computacao - PUCPR
Turma 7B - Grupo 3
Equipe: Igor Mamus dos Santos, Felipe Ribas Boaretto,
        Leonardo dos Santos Marques, Joao Vitor Manfrim
========================================================================

DESCRICAO DO MANIFESTO
----------------------
Este arquivo lista, de forma objetiva, todos os artefatos entregues do
projeto: codigo-fonte, dados, modelos treinados, resultados, figuras e
logs, com a referencia ao diretorio correspondente e os parametros de
execucao quando aplicavel. A documentacao tecnica completa esta em
README.md (na raiz). Os comandos abaixo assumem o ambiente virtual
ativado (.venv) e Python 3.11+.

OBSERVACAO IMPORTANTE SOBRE OS ARTEFATOS PESADOS
------------------------------------------------
Por limite de tamanho do GitHub (arquivos > 100 MB sao rejeitados) e por
serem regeneraveis, os seguintes diretorios NAO estao no repositorio Git
e sao entregues a parte (pasta de nuvem) e/ou regeneraveis pelos comandos
indicados: data/raw/, data/processed/, data/rag/chromadb/, data/ml_models/
e o arquivo GGUF do modelo LLM. Cada item esta marcado abaixo com sua
origem (REPO = versionado no Git; NUVEM = entregue na pasta de nuvem;
REGENERAVEL = reconstruido pelo comando indicado).


========================================================================
1. CODIGO-FONTE  (src/)  [REPO]
========================================================================

src/data/pipeline.py
  Etapa 1: pre-processamento dos datasets brutos. Limpa, codifica,
  remove colunas identificadoras/constantes/correlacionadas, mapeia
  rotulos para 15 categorias e gera os parquets.
  Parametros: --dataset {cic,unsw} (default: ambos);
              --sample FRACAO (ex.: 0.1 para 10%).

src/rag/download.py
  Baixa as fontes da base RAG (MITRE ATT&CK STIX 2.1 e Sigma Rules).

src/rag/pipeline.py
  Etapa 2: indexa a base RAG no ChromaDB e testa a busca semantica.
  Parametros: --test (roda queries de validacao);
              --reset (re-indexa do zero);
              --skip-download (usa fontes ja baixadas).

src/ml/models.py
  Registry dos modelos de ML, preparacao de features e ensemble por
  soft-voting. Usado pelo benchmark e pelo pre-classificador.

src/ml/benchmark.py
  Etapa 2.5: estudo comparativo de ate 10 modelos (RandomForest,
  ExtraTrees, HistGradientBoosting, XGBoost, LightGBM, DecisionTree,
  LogisticRegression, GaussianNB, KNN, MLP) + ensemble. Treina nos
  datasets, avalia com holdout + cross-validation e salva modelos,
  relatorios e figuras.
  Parametros: --sample-size N (0 = datasets completos; default 200000);
              --datasets cic unsw;
              --cv-folds N (default 5; 0 desativa);
              --cv-cap N (subamostra da CV; default 60000);
              --no-slow (pula KNN e MLP);
              --seed N (default 42);
              --no-save-models.
  Saida: data/ml_models/ (modelos) e outputs/ml_benchmark/ (relatorios e figuras).

src/ml/preclassifier.py
  Atalho de treino apenas do Random Forest e classe PreClassifier
  (inferencia: carrega rf/best/ensemble por dataset).
  Parametros: --sample-size N (default 200000; 0 = tudo).

src/llm/pipeline.py
  Etapa 3: pipeline de triagem com LLM (descricao -> RAG -> LLM).
  Requer o servidor Ollama em execucao (ollama serve).
  Parametros: --n N (registros);
              --stratified (amostragem estratificada por classe);
              --dataset {unified,cic,unsw};
              --seed N (reprodutibilidade da amostragem);
              --use-rf (ativa o pre-classificador);
              --clf-kind {rf,best,ensemble} (variante do pre-classificador);
              --no-rag / --no-rerank (desativa RAG / cross-encoder);
              --two-stage (Stage 1 binario - experimental);
              --rf-threshold 0.95 / --rag-threshold 0.55 / --top-k 5;
              --run-dir CAMINHO (pasta base de saida);
              --index N (triar um registro especifico);
              --output CAMINHO.
  Saida: outputs/triage_runs/ (ou --run-dir) e linha no manifesto.

src/evaluation/metrics.py
  Metricas detalhadas da triagem: por classe, matriz de confusao,
  agregacao de varias runs (pool de registros).
  Parametros: CAMINHO (results.json ou pasta da run);
              --aggregate "GLOB" (agrega varias runs);
              --no-plots.

src/evaluation/explanation_quality.py
  Avaliacao automatica da qualidade das explicacoes do LLM (validade
  das tecnicas MITRE, relevancia, consistencia, ancoragem no RAG).
  Parametros: CAMINHO (results.json ou pasta da run).

src/evaluation/runlog.py
  Persistencia padronizada das runs (schema v3 + manifesto JSONL).

src/utils/logger.py, src/utils/progress.py
  Logger (UTF-8) e acompanhamento de progresso/ETA das baterias.

src/config.py
  Caminhos, constantes e mapeamentos de rotulos centralizados.


========================================================================
2. SCRIPTS DE EXECUCAO  (raiz/*.ps1)  [REPO]
========================================================================

run_ml_benchmark.ps1
  Bateria do estudo comparativo de ML (chama src.ml.benchmark).
  Parametros: -SampleSize N; -CvFolds N; -Full (datasets completos);
              -NoSlow; -Datasets {cic,unsw,both}.

run_benchmark.ps1
  Ablation study do LLM: 7 configuracoes x tamanhos x seeds.
  Parametros: -SeedsPerConfig N; -Sizes 30,50; -Dataset {unified,cic,unsw};
              -Stratified $true/$false (false = amostragem natural/high-benign);
              -Quick; -SkipBaseline.
  Saida: outputs/benchmarks/bench_<timestamp>/ (summary.json, ranking.json,
         benchmark.log, runs/).

run_night.ps1
  Orquestrador que encadeia 3 baterias do LLM (CIC isolado, UNSW isolado,
  high-benign) para deixar rodando em sequencia.
  Parametros: -Seeds N; -CicSize N; -UnswSize N; -BenignSize N.

run_evaluation.ps1
  Comparativo rapido RAG vs no-RAG.
  Parametros: -N N; -Dataset {unified,cic,unsw}.


========================================================================
3. DADOS  (data/)
========================================================================

data/raw/cic-ids2017/   [NUVEM ou download oficial]
data/raw/unsw-nb15/     [NUVEM ou download oficial]
  Datasets brutos (CSV). Publicos:
   - CIC-IDS2017: https://www.unb.ca/cic/datasets/ids-2017.html
   - UNSW-NB15:   https://research.unsw.edu.au/projects/unsw-nb15-dataset
  Nao versionados por tamanho. Colocar os CSV nestes diretorios.

data/processed/   [REGENERAVEL via: python -m src.data.pipeline]
  Parquets limpos: cic_ids2017_clean.parquet (2,83M registros),
  unsw_nb15_clean.parquet (2,54M), unified_dataset.parquet (normalizado),
  normalization_params.json, preprocessing_report.json.

data/rag/sources/   [REGENERAVEL via: python -m src.rag.download]
  enterprise-attack.json (MITRE ATT&CK STIX) e repositorio Sigma Rules.

data/rag/chromadb/   [REGENERAVEL via: python -m src.rag.pipeline --reset --skip-download]
  Indice vetorial persistente (~4.435 documentos).


========================================================================
4. MODELOS TREINADOS  (data/ml_models/)  [NUVEM; REGENERAVEL via src.ml.benchmark]
========================================================================

data/ml_models/rf_cic.joblib, rf_unsw.joblib
  Random Forest binario (Benign vs Threat), um por dataset.
data/ml_models/best_cic.joblib, best_unsw.joblib
  Melhor modelo do benchmark por F1 (XGBoost em ambos os datasets).
data/ml_models/ensemble_cic.joblib, ensemble_unsw.joblib
  Ensemble por soft-voting dos melhores modelos.
data/ml_models/rf_meta.json
  Metricas resumidas do Random Forest.
  (Treinados nos datasets completos com seed 42. Para regenerar:
   python -m src.ml.benchmark --sample-size 0 --cv-folds 5)

models/Modelfile   [REPO]
models/foundation-sec-8b-instruct-q8_0.gguf   [download HuggingFace]
  Receita e arquivo do modelo LLM (Foundation-Sec-8B-Instruct Q8_0).
  GGUF nao versionado (~8,5 GB). Download e registro no README.md (Etapa 3.1).


========================================================================
5. RESULTADOS E FIGURAS  (outputs/)  [REPO]
========================================================================

outputs/ml_benchmark/bench_<timestamp>/
  model_comparison.json  - metricas completas de todos os modelos de ML.
  model_comparison.md    - tabela comparativa (CIC e UNSW).
  metrics_<ds>.png       - barras F1 / ROC-AUC por modelo  [FIGURA].
  roc_<ds>.png           - curvas ROC sobrepostas           [FIGURA].
  confusion_<ds>.png     - matriz de confusao do melhor modelo [FIGURA].
  importance_<ds>.png    - top-15 features                  [FIGURA].

outputs/benchmarks/bench_<timestamp>/
  summary.json   - todas as runs do ablation do LLM (detalhado).
  ranking.json   - ranking final por configuracao.
  benchmark.log  - log completo da bateria (mensagens, metricas, ETA).
  runs/          - subpastas por run, cada uma com results.json (schema v3).

outputs/triage_runs/runs_index.jsonl
  Manifesto agregavel (uma linha por run). Carregar com:
  pandas.read_json("outputs/triage_runs/runs_index.jsonl", lines=True).

  Estrutura de cada results.json (schema v3): blocos run (metadados+flags),
  summary (metricas achatadas), metrics (por classe + matriz de confusao),
  explanation_quality (qualidade das explicacoes), records (registros triados).

outputsold/   [REPO]
  Arquivo HISTORICO dos resultados da VERSAO 2 do projeto (formato de saida
  antigo). Mantido versionado de proposito para evidenciar a evolucao do
  trabalho ao longo do tempo e a diversidade de experimentos realizados.
  Contem benchmarks/, ml_benchmark/, triage_runs/ e evaluation/ da v2.
  Os resultados atuais (v3) estao em outputs/.


========================================================================
6. TESTES  (tests/)  [REPO]
========================================================================

97 testes unitarios (pytest). Executar: python -m pytest tests/ -v
Cobertura: pre-processamento, conversao de features, prompts, cliente LLM,
parsing RAG, modelos de ML/ensemble, metricas e qualidade das explicacoes.


========================================================================
7. DOCUMENTACAO
========================================================================

README.md   [REPO]
  Documentacao tecnica completa: arquitetura, etapas, setup do zero,
  metodologia, RESULTADOS detalhados (data science) e jornada experimental.

requirements.txt   [REPO]
  Dependencias Python.

knowledge/   [NUVEM - documentacao interna de apoio ao manuscrito]
  Notas de data science: metodologia comparativa, analises das runs
  (por dataset, high-benign), decisoes de design e changelog. Nao
  versionado no Git (uso interno do grupo).


========================================================================
RESUMO DOS PRINCIPAIS RESULTADOS
========================================================================
- ML (datasets completos, CV 5-fold): XGBoost e o melhor (CIC F1 0,9976 /
  ROC-AUC 1,0000; UNSW F1 0,9731 / ROC-AUC 0,9998).
- Em trafego realista (~87% benigno), o LLM isolado e inutilizavel
  (binaria 0,125; falso-positivo em massa); com o pre-filtro de ML a
  binaria sobe para 1,000 e fica ~7x mais rapido.
- RAG ajuda a categorizacao no CIC, mas e neutro/negativo no UNSW.
- O two-stage do LLM e nocivo (recall despenca) e foi desativado.
Detalhes em README.md (secao "Resultados Detalhados").
========================================================================

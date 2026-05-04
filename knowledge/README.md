# Knowledge Base — Documentação para o TCC

Pasta de conhecimento acumulado durante o desenvolvimento do projeto, organizada para alimentar o manuscrito final.

## Índice

| Arquivo | Conteúdo |
|---------|----------|
| [01_pipeline_architecture.md](01_pipeline_architecture.md) | Arquitetura técnica completa do sistema (Etapas 1-3) |
| [02_design_decisions.md](02_design_decisions.md) | Decisões de design com justificativa técnica e acadêmica |
| [03_bugs_and_fixes.md](03_bugs_and_fixes.md) | Histórico cronológico de 19 bugs descobertos e correções |
| [04_results_observations.md](04_results_observations.md) | Resultados experimentais, padrões observados e próximas runs |
| [05_limitations.md](05_limitations.md) | 9 limitações conhecidas com respostas fundamentadas para a banca |
| [06_evaluation_methodology.md](06_evaluation_methodology.md) | Metodologia de avaliação, métricas e protocolo de execução |
| [07_reproducibility.md](07_reproducibility.md) | Guia completo para reproduzir todos os experimentos do zero |
| [runs/](runs/) | Análise detalhada de execuções específicas |

## Análises de Runs

| Arquivo | Pipeline | Conteúdo |
|---------|---------|----------|
| [runs/run_20260503_123456_vs_124005_rag_vs_norag.md](runs/run_20260503_123456_vs_124005_rag_vs_norag.md) | v1 | RAG vs No-RAG, N=10, seed fixo — análise registro a registro |
| [runs/bench_20260503_224512_quick_analysis.md](runs/bench_20260503_224512_quick_analysis.md) | v2 | Benchmark Quick — 6 configs, N=3, seed 834338 — ranking e ablation study |

## Como usar este conhecimento

- **Para o manuscrito do TCC**: cada arquivo contém seções prontas para copiar, com referências cruzadas
- **Para revisão metodológica**: a pasta `runs/` documenta cada experimento relevante
- **Para defender escolhas em banca**: `02_design_decisions.md` justifica todas as decisões técnicas
- **Para discutir resultados**: `05_limitations.md` antecipa críticas comuns com respostas fundamentadas

## Convenção de atualização

Sempre que houver:
- Nova run relevante → adicionar em `runs/`
- Bug descoberto → registrar em `03_bugs_and_fixes.md`
- Resultado novo → atualizar `04_results_observations.md`
- Decisão de design → adicionar em `02_design_decisions.md`

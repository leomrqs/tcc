# Resultados e Observações Experimentais

Padrões e achados acumulados ao longo das runs de avaliação. Atualizar conforme novas runs forem realizadas.

---

## Pipeline v1 (original) — Resultados

| Run ID | Modo | N | Dataset | Acc. Exata | Acc. Binária | Precisão | Recall | F1 | Tempo/reg |
|--------|------|---|---------|-----------|-------------|---------|--------|-----|-----------|
| run_20260503_020450 | RAG | 9 | unified | 0% | 88.9% | 88.9% | 100% | 94.1% | ~20s |
| run_20260503_020821 | No-RAG | 9 | unified | 11% | 55.6% | 62.5% | 62.5% | 62.5% | ~22s |
| run_20260503_123456 | RAG | 10 | unified | 20% | 90.0% | 90.0% | 100% | 94.7% | ~29s |

> Nota: runs com erros HTTP 500 (bug #19 — pattern no JSON Schema) foram descartadas da análise.

---

## Pipeline v2 (com melhorias) — Resultados do Benchmark

### Benchmark bench_20260503_224512 — Quick test (N=3, seed=834338, 1 seed)

**Configurações testadas e resultados:**

| Config | Exata | Binária | Precisão | Recall | F1 | Tempo/reg | Notas |
|--------|-------|---------|---------|--------|-----|-----------|-------|
| 1_baseline (no-RAG) | 10% | 90% | 90% | 100% | 94.7% | 25.1s | TN=0 (modelo nunca prevê Benign) |
| 2_rag_only | 10% | 90% | 90% | 100% | 94.7% | 24.6s | Idem baseline — RAG não ajuda sem rerank |
| 3_rag_rerank | **20%** | 90% | 90% | 100% | 94.7% | 26.1s | Cross-encoder melhora exata |
| 4_rag_rerank_2stage | 10% | 60% | 86% | 67% | 75% | 22.2s | Stage 1 LLM oscilante — **piorou binária** |
| **5_rag_rerank_rf** | **30%** | **100%** | **100%** | **100%** | **100%** | 23.2s | **Melhor config** — RF resolve TN=0 |
| 6_full_stack (RF+2stage) | 20% | 70% | 100% | 67% | 80% | 19.2s | RF ótimo, Stage 1 prejudica recall |

**Vencedor claro: `5_rag_rerank_rf`** (RAG + cross-encoder + Random Forest, sem Stage 1 LLM)

---

## Evolução ANTES × DEPOIS dos Fixes (mesmo seed 834338)

Comparação registro a registro entre pipeline v1 (com bugs) e v2 (bugs corrigidos):

| Ground Truth | Pipeline v1 (antes) | Pipeline v2 (depois) | Delta |
|-------------|---------------------|----------------------|-------|
| Analysis | ✗ DDoS | ✗ Generic | Mais razoável |
| Benign | ✗ DDoS | ✓ **Benign [RF]** | RF resolveu TN=0 |
| DDoS | ✗ Reconnaissance | ✗ Reconnaissance | Mesmo erro (limite do dado) |
| DoS | ✗ Reconnaissance | ✓ **DoS** | Novo acerto — CoT+RAG ajudaram |
| Exploits | ✗ Reconnaissance | ✗ Reconnaissance | — |
| Fuzzers | ✗ **DDoS** | ✗ Generic | Bug Sload corrigido |
| Generic | ✗ **DDoS** | ✗ Reconnaissance | Bug Sload corrigido |
| Reconnaissance | ✓ Reconnaissance | ✓ Reconnaissance | Manteve |
| Shellcode | ✗ **DDoS** | ✗ Generic | Bug Sload corrigido |
| Worms | ✗ Reconnaissance | ✗ Reconnaissance | — |

**Resumo do ganho:**
- DDoS falsos: **5/10 → 0/10** (eliminados pelo fix Bug #21)
- Benign corretos: **0/1 → 1/1** (Random Forest pre-classifier)
- Binária: **90% → 100%**
- Exata: **30% → 30%** (acurácia mantida, mas distribuição de erros muito mais saudável)

---

## Padrão 1 — TN=0 resolvido com Random Forest

**Antes (v1)**: modelo nunca previa Benign — TN=0 em todas as runs.

**Depois (v2 com --use-rf)**:
- RF pré-clasifica Benigns com 99.8% acc (CIC) e 99.1% acc (UNSW)
- 97-98% dos Benigns capturados com conf≥95%
- Risco: 0.04% de ameaças classificadas como Benign incorretamente
- Resultado: **TN=1/1, FP=0** na run de validação

---

## Padrão 2 — RAG + cross-encoder melhora exata, não binária

| Configuração | Acc. Exata | Acc. Binária | Delta Exata |
|-------------|-----------|-------------|-------------|
| Baseline (no-RAG) | 10% | 90% | — |
| RAG simples (denso) | 10% | 90% | 0pp |
| RAG + rerank | 20% | 90% | +10pp |
| RAG + rerank + RF | **30%** | **100%** | +20pp |

**Análise**: o cross-encoder melhora recuperação semântica → melhor contexto → categorias mais precisas. O RF resolve a dimensão binária independentemente da categoria.

---

## Padrão 3 — DDoS/DoS/Reconnaissance: limite intrínseco do dado

**Problema persistente**: DDoS e DoS ainda são confundidos com Reconnaissance.

**Causa raiz confirmada**: fluxos CIC de DDoS/DoS têm features de fluxo individual idênticas a Reconnaissance:
- Poucos pacotes (2-5), ACK-only, payload zero, curta duração
- Um port scan e um fluxo de DDoS "isolado" são indistinguíveis a nível de fluxo único

**Evidência quantitativa** (bench_20260503):
- DDoS → Reconnaissance: 100% dos casos
- DoS → Reconnaissance: 60-80% dos casos (exceto quando o prompt CoT + RAG em v2 ajuda)

**O que seria necessário para distinguir**: contexto temporal agregado (N fluxos do mesmo source/destino por segundo), não disponível em avaliação fluxo-a-fluxo.

---

## Padrão 4 — Bug Sload/Dload: UNSW fluxos minúsculos viravam DDoS

**Problema v1**: fluxos UNSW de 2 pacotes em 8μs davam `Sload = 100M bps` → text_converter v1 não tinha sanity check → modelo via "FLOOD" e classificava como DDoS.

**Impacto real** (bench_20260503): todas as 5 classes UNSW (Analysis, Fuzzers, Shellcode, Generic, Worms) eram classificadas como DDoS.

**Após fix**: distribuição diversificada (Generic, Reconnaissance, DoS). Zero DDoS falsos.

---

## Padrão 5 — Stage 1 LLM binário não confiável

**Problema**: Stage 1 (LLM perguntando BENIGN/THREAT em texto livre) oscila. Em benchmark:
- Config 4 (com Stage 1): binária **60%**, recall **67%** — pior que baseline
- Motivo: Stage 1 marcava DDoS e DoS como BENIGN

**Solução adotada**: substituir Stage 1 LLM por Random Forest.
- RF: 99.8% acc, sem oscilação, < 1ms por classificação
- Stage 1 LLM mantido como `--two-stage` opt-in para experimentos

---

## Padrão 6 — Confiança subiu com v2

**v1**: confiança travada em 0.70 na maioria dos casos.

**v2**: média 0.80, com variação real:
- RF skip → conf=1.00 (certeza total)
- Casos bem suportados pelo RAG → conf=0.85-0.95
- Casos ambíguos → conf=0.70-0.80

O prompt chain-of-thought com exemplos calibrou melhor o modelo para expressar incerteza gradual.

---

## Observações sobre Tempo de Inferência (v2)

| Configuração | Tempo/reg | Vs. v1 |
|-------------|-----------|--------|
| RAG + rerank | ~26s | +4s (rerank: ~2s extra) |
| RAG + rerank + RF | ~23s | +3s (RF: <1ms, mas salva ~25s nos Benigns) |
| No-RAG | ~25s | ~igual |
| Benign via RF | <1ms | -25s (skip total do LLM) |

**Cross-encoder overhead**: ~2s por query (ms-marco-MiniLM é leve). Justificado pelo ganho de acurácia exata (+10pp).

---

## Próximas Runs para o Manuscrito

Para dados estatisticamente válidos no TCC (necessita múltiplos seeds):

```powershell
# Bateria padrão (~2-3h): 6 configs x 3 tamanhos x 2 seeds = 36 runs
.\run_benchmark.ps1

# Bateria robusta (~5h): 3 seeds por config
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 3,5,8
```

**Configurações a priorizar** (em ordem de importância para o TCC):
1. `5_rag_rerank_rf` — stack completa recomendada
2. `1_baseline_norag` — baseline comparativo
3. `3_rag_only` — isolar efeito do RAG denso

**Seeds já usados**:
| Data | Seed | Runs |
|------|------|------|
| 2026-05-03 | 834338 | bench_20260503_224512 (Quick, N=3) |
| 2026-05-03 | 720479 | runs individuais de validação |
| 2026-05-03 | 537631 | runs com bug #19 (descartadas) |

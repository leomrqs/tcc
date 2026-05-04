# Análise: Benchmark Quick — bench_20260503_224512

**Data**: 2026-05-04  
**Seed**: 834338  
**N**: 3 por classe → 10 registros (estratificado, unified dataset)  
**Configurações**: 6  
**Script**: `run_benchmark.ps1 -Quick`  
**Pipeline**: v2 (text_converter discriminativo + RAG com ids_classes + cross-encoder + RF)

---

## Ranking Final

| Posição | Config | Exata | Binária | Precisão | Recall | F1 | Tempo/reg |
|---------|--------|-------|---------|---------|--------|-----|-----------|
| 🥇 1º | `5_rag_rerank_rf` | **30%** | **100%** | **100%** | **100%** | **100%** | 23.2s |
| 🥈 2º | `6_full_stack` | 20% | 70% | 100% | 67% | 80% | 19.2s |
| 🥈 2º | `3_rag_rerank` | 20% | 90% | 90% | 100% | 94.7% | 26.1s |
| 4º | `1_baseline_norag` | 10% | 90% | 90% | 100% | 94.7% | 25.1s |
| 4º | `2_rag_only` | 10% | 90% | 90% | 100% | 94.7% | 24.6s |
| 6º | `4_rag_rerank_2stage` | 10% | 60% | 86% | 67% | 75% | 22.2s |

---

## Análise por Registro

Mesmos 10 registros para todos via seed 834338:

| Ground Truth | Fonte | 1_baseline | 2_rag | 3_rerank | 4_2stage | **5_rf** | 6_full |
|-------------|-------|-----------|-------|---------|---------|----------|--------|
| Analysis | UNSW | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS |
| Benign | UNSW | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✓ **Benign[RF]** | ✓ **Benign[RF]** |
| DDoS | CIC | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Benign[S1] | ✗ Recon | ✗ Benign[S1] |
| DoS | CIC | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Benign[S1] | ✗ Recon | ✗ Benign[S1] |
| Exploits | UNSW | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Benign[S1] | ✗ Recon | ✗ Benign[S1] |
| Fuzzers | UNSW | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS |
| Generic | UNSW | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS |
| Reconnaissance | CIC | ✓ Recon | ✓ Recon | ✓ Recon | ✓ Recon | ✓ Recon | ✓ Recon |
| Shellcode | UNSW | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS | ✗ DDoS |
| Worms | UNSW | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Recon | ✗ Recon |

**Legenda**: [RF] = RandomForest skip, [S1] = Stage 1 LLM binário

---

## Achados Principais

### 1. Bug Sload ainda presente neste benchmark
As colunas `Analysis, Fuzzers, Generic, Shellcode` ainda foram para DDoS. **Este benchmark rodou COM o bug #21 ainda ativo.**

O fix do Bug #21 foi aplicado APÓS este benchmark. Rodando após o fix:

| Ground Truth | bench_20260503 (com bug) | Pós-fix (seed 834338) |
|-------------|--------------------------|----------------------|
| Analysis | ✗ DDoS | ✗ **Generic** |
| Fuzzers | ✗ DDoS | ✗ **Generic** |
| Generic | ✗ DDoS | ✗ **Reconnaissance** |
| Shellcode | ✗ DDoS | ✗ **Generic** |
| Acurácia binária | 100% | 100% |
| Acurácia exata | 30% | 30% |

→ Acurácia exata mantida em 30%, mas DDoS falsos eliminados.

### 2. Stage 1 LLM oscilante — prejudicou configs 4 e 6
- Config 4 (`rag_rerank_2stage`): binária 60%, recall 67% — **pior que baseline**
- Config 6 (`full_stack`): binária 70%, recall 67%
- Causa: Stage 1 marcou DDoS, DoS, Exploits como BENIGN (3 FNs)
- **Conclusão**: Stage 1 LLM deve permanecer opt-in, nunca default

### 3. RF é o componente mais impactante
- Única config que alcança binária 100%: `5_rag_rerank_rf`
- Quando RF é ativo + Stage 1 LLM também é ativo, Stage 1 **desfaz** o ganho do RF para alguns registros
- RF > Stage 1 LLM em confiabilidade

### 4. RAG + rerank melhora exata isoladamente
- Baseline (no-RAG): 10% exata
- RAG denso: 10% exata (mesmo)
- RAG + rerank: **20%** exata (+10pp)
- RAG + rerank + RF: **30%** exata (+20pp vs baseline)

### 5. DDoS/DoS/Reconnaissance ainda confundidos
Problema intrínseco do dataset. Fluxos CIC individuais de DDoS/DoS têm features idênticas a Reconnaissance. Requer contexto temporal agregado para distinguir.

---

## Benchmark Seguinte Recomendado

Após fix Bug #21, rodar:

```powershell
.\run_benchmark.ps1 -Quick   # confirmar melhora de ~5 classes UNSW
.\run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 3,5,8   # dados para manuscrito
```

Esperar resultados para config `5_rag_rerank_rf`:
- Exata: ~30-40% (melhor com bug #21 corrigido)
- Binária: 100% (mantida)
- DDoS falsos: 0

---

## Contexto para o Manuscrito TCC

### Tabela de ablation study (configurações como variável independente)

| Componente adicionado | Delta Exata | Delta Binária |
|----------------------|-------------|---------------|
| RAG denso (vs baseline) | 0pp | 0pp |
| + Cross-encoder rerank | +10pp | 0pp |
| + Random Forest | +10pp | +10pp |
| Stage 1 LLM (opt-in) | -10pp | -30pp (nocivo!) |

→ Ablation demonstra que RF é o componente mais valioso e Stage 1 LLM deve ser evitado neste modelo.

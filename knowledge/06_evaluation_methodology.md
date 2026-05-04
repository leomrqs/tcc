# Metodologia de Avaliação

Descreve como os experimentos são conduzidos, quais métricas são usadas e como interpretar os resultados.

---

## Design Experimental

### Comparação RAG vs No-RAG

O experimento central compara dois modos do mesmo pipeline:

- **RAG (com recuperação)**: o modelo recebe contexto de MITRE ATT&CK + Sigma Rules recuperado por similaridade semântica
- **No-RAG (baseline)**: o modelo opera apenas com o system prompt e a descrição do registro

**Por que comparar os dois**: o objetivo é medir o valor marginal do RAG. Se RAG não melhora a classificação, a complexidade adicional não se justifica.

**Controle experimental**: ambas as runs usam o **mesmo seed de amostragem** (gerado pelo `run_evaluation.ps1` e passado como `--seed` para ambas). Isso garante que os mesmos registros são avaliados nos dois modos — a única variável é a presença ou ausência do contexto RAG.

---

## Amostragem Estratificada

**Por que estratificar**: os datasets têm ~80-87% de registros Benign. Uma amostra aleatória simples de 10 registros teria ~8 Benigns e 2 ameaças — insuficiente para avaliar diversidade de categorias.

**Como funciona**:
1. Pre-sample de `N × 50` registros por dataset (evita carregar 5M linhas)
2. `groupby("label")` para separar por classe
3. `sample(min(len(group), N))` por classe → no máximo N por classe
4. `pd.concat` dos grupos → amostra estratificada final

**Resultado**: com N=5, seleciona no máximo 5 registros de cada classe existente no pre-sample. Classes raras podem ter menos de 5 registros disponíveis no pre-sample.

**Parâmetro**: `--n N --stratified` no CLI, ou `.\run_evaluation.ps1 -N 5`.

---

## Métricas Adotadas

### Acurácia Exata

```
acurácia_exata = n_predições_corretas / n_total
```

Uma predição é "correta" quando `attack_type` predito corresponde ao `ground_truth` via dicionário de aliases (`_LABEL_ALIASES` em `pipeline.py`):

```python
_LABEL_ALIASES = {
    "benign": {"benign", "normal", "background"},
    "brute force": {"brute force", "bruteforce", "brute-force"},
    "dos": {"dos", "dos slowloris", "dos slowhttptest", "dos hulk", "dos goldeneye", "heartbleed"},
    # ...
}
```

**Limitação**: exige que o modelo use exatamente a categoria correta entre as 15 disponíveis. Erros entre categorias correlatas (Reconnaissance vs Exploits) penalizam igual a erros grosseiros (Benign vs DDoS).

### Acurácia Binária (Ameaça vs Benigno)

```
acurácia_binária = (TP + TN) / (TP + TN + FP + FN)
```

Simplifica o problema para detecção binária: o sistema detectou que há uma ameaça?

**Mapeamento binário**:
- Benigno: `{"benign", "normal", "background"}`
- Ameaça: qualquer outra categoria (DoS, DDoS, Reconnaissance, Exploits, etc.)

**Por que esta métrica é mais relevante**: operacionalmente, o passo mais crítico é detectar a presença de uma ameaça. A categoria específica pode ser refinada por analistas humanos.

### Precisão, Recall e F1

```
precisão = TP / (TP + FP)    # dos alertados como ameaça, quantos eram reais
recall   = TP / (TP + FN)    # das ameaças reais, quantas foram detectadas
F1       = 2 × (P × R) / (P + R)
```

Onde:
- **TP** (True Positive): prediu ameaça, era ameaça
- **TN** (True Negative): prediu benigno, era benigno
- **FP** (False Positive): prediu ameaça, era benigno
- **FN** (False Negative): prediu benigno, era ameaça

**Atenção**: TN=0 em todas as runs observadas. O modelo nunca prevê benigno.

### Confiança Média

Média dos valores de `confidence` das predições válidas (excluindo erros de LLM).

**Uso**: indicador de certeza do modelo. RAG tende a aumentar confiança média vs no-RAG.

---

## Protocolo de Execução

### Avaliação Padrão

```powershell
# Avaliação completa com seed aleatório
.\run_evaluation.ps1 -N 5

# Avaliação com seed fixo (reprodutibilidade)
.\run_evaluation.ps1 -N 5 -Seed 42

# Dataset específico
.\run_evaluation.ps1 -N 5 -Dataset cic
.\run_evaluation.ps1 -N 5 -Dataset unsw
```

### Outputs Gerados

Cada run cria uma subpasta em `outputs/triage_runs/`:

```
run_<timestamp>_<rag|norag>_n<N>_<strat>/
    └── results.json
```

O `results.json` contém:
- Métricas agregadas (`accuracy_exact`, `accuracy_binary`, `precision`, `recall`, `confusion`)
- Detalhes por registro (`attack_type`, `severity`, `confidence`, `mitre_techniques`, `explanation`, `record_description`, `retrieved_context_titles`, `rag_distances`, `ground_truth`, `elapsed_seconds`, `raw_llm_response`, `validation_errors`)

---

## Interpretação dos Resultados

### O que esperar

| Cenário | Acc. Binária RAG | Acc. Binária No-RAG | Interpretação |
|---------|-----------------|-------------------|---------------|
| RAG >> No-RAG | >80% | <60% | RAG agrega valor claro |
| RAG ≈ No-RAG | ~70% | ~70% | RAG neutro — filtro descartando tudo |
| RAG < No-RAG | <60% | >70% | RAG prejudicando — contexto irrelevante |

### Armadilhas Comuns

1. **Acc. binária alta com TN=0**: acontece quando há poucas amostras Benign. Precision 90% com FP=1 e apenas 1 registro benigno na amostra não é representativo.

2. **Acc. exata 0% não é catástrofe**: o modelo pode estar classificando corretamente "ameaça vs benigno" mas errando a categoria específica (DDoS vs Reconnaissance). Analisar acc. binária primeiro.

3. **Seed importa**: dois seeds diferentes podem dar resultados muito diferentes com amostras pequenas (N=5-10). Agregar resultados de múltiplos seeds para conclusões robustas.

---

## Mínimo para o Manuscrito

Para o TCC, as seguintes runs devem ser documentadas:

1. **3 runs RAG + 3 runs No-RAG** com seeds diferentes, N=3 (45 registros por par)
2. **1 run CIC-only** e **1 run UNSW-only** para análise por dataset
3. **Tabela comparativa** com médias e desvio padrão das métricas

Isso requer aproximadamente 6 horas de inferência com o hardware atual.

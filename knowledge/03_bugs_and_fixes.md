# Bugs Descobertos e Correções

Histórico cronológico de problemas encontrados durante o desenvolvimento. Cada entrada documenta sintoma, causa raiz e fix aplicado.

---

## Bug #1 — `load_dataset` ignorava `sample_size`

**Arquivo**: `src/llm/pipeline.py`

**Sintoma**: pipeline LLM levava ~30s só para carregar dataset, mesmo para 5 registros.

**Causa**: parâmetro `sample_size` declarado mas nunca usado — sempre carregava 5.37M linhas inteiras.

**Fix**: pré-amostra `n × 50` registros por dataset antes da seleção estratificada.

**Impacto**: redução de ~25s no tempo total para amostras pequenas.

---

## Bug #2 — pandas 2.x dropa coluna na amostragem estratificada

**Arquivo**: `src/llm/pipeline.py:select_records`

**Sintoma**: após estratificação, coluna `label` desaparecia → ground truth perdido.

**Causa**: `df.groupby("label", group_keys=False).apply(...)` no pandas 2.x consome a coluna usada como chave do groupby.

**Fix**: substituído por `pd.concat` de grupos individuais via list comprehension:
```python
frames = [
    group.sample(min(len(group), per_class), random_state=seed)
    for _, group in df.groupby("label", group_keys=False)
]
return pd.concat(frames).reset_index(drop=True)
```

**Lição**: APIs de agregação do pandas mudam comportamento entre versões — tests revelaram o problema.

---

## Bug #3 — Flag ACK mapeada para coluna ECE

**Arquivo**: `src/llm/text_converter.py:_format_tcp_flags_cic`

**Sintoma**: descrições mostravam contagens erradas de flags TCP.

**Causa**: dicionário tinha `"ACK": "ece_flag_counts"` (comentário antigo dizia que CIC unia ACK com ECE em algumas versões — não verdadeiro).

**Fix**: separados em entradas distintas:
```python
"ACK": "ack_flag_counts",
"ECE": "ece_flag_counts",
```

---

## Bug #4 — `_matches_label` exact match falhava em variantes

**Arquivo**: `src/llm/pipeline.py:_matches_label`

**Sintoma**: "Benign" vs "Normal" (sinônimos) contavam como erro na avaliação.

**Causa**: comparação literal case-insensitive.

**Fix**: dicionário de aliases por categoria:
```python
_LABEL_ALIASES = {
    "benign": {"benign", "normal", "background"},
    "brute force": {"brute force", "bruteforce", "brute-force"},
    ...
}
```

---

## Bug #5 — `.env` carregado manualmente

**Arquivo**: `src/llm/llm_client.py`

**Sintoma**: variáveis do `.env` não eram aplicadas, modelo padrão errado.

**Causa**: parsing manual frágil em vez de usar `python-dotenv` (já no requirements.txt).

**Fix**:
```python
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")
```

---

## Bug #6 — `get_sentence_embedding_dimension()` depreciado

**Arquivo**: `src/rag/embeddings.py`

**Sintoma**: FutureWarning a cada execução.

**Causa**: sentence-transformers 5.x renomeou para `get_embedding_dimension()`.

**Fix**: `getattr` com fallback para compatibilidade entre versões.

---

## Bug #7 — ChromaDB corrompido causava crash

**Arquivo**: `src/rag/vectorstore.py`

**Sintoma**: `Error loading hnsw index` ao iniciar pipeline; nem `--reset` resolvia (falhava no `__init__` antes de chegar ao reset).

**Causa**: índice HNSW do ChromaDB pode corromper se o processo for interrompido durante escrita.

**Fix**: detecta erro no `count()` inicial e recria automaticamente:
```python
try:
    count = self.collection.count()
except Exception:
    logger.warning("Índice corrompido — recriando...")
    shutil.rmtree(self.persist_dir, ignore_errors=True)
    # ... reinicializa
```

---

## Bug #8 — `/api/generate` ignorava system prompt

**Arquivo**: `src/llm/llm_client.py`

**Sintoma**: modelo retornava JSON em formato livre (chaves erradas), ignorando todas as instruções do system prompt.

**Causa**: endpoint `/api/generate` com campo `"system"` não aplica template Llama 3 — system prompt entra como texto comum, modelo não entende.

**Fix**: migrado para `/api/chat` com mensagens estruturadas:
```python
messages = [
    {"role": "system", "content": system},
    {"role": "user", "content": prompt}
]
payload = {"model": ..., "messages": messages, ...}
requests.post(f"{host}/api/chat", json=payload)
```

**Impacto**: taxa de respostas válidas pulou de ~0% para 100%.

---

## Bug #9 — `format: "json"` não restringia chaves

**Arquivo**: `src/llm/llm_client.py`

**Sintoma**: mesmo com `format: "json"`, modelo retornava `{"analysis": ..., "findings": [...]}` em vez de `{"attack_type": ..., ...}`.

**Causa**: `"format": "json"` apenas garante JSON sintaticamente válido — não impõe schema.

**Fix**: passou JSON Schema completo no campo `format`:
```python
"format": {
    "type": "object",
    "properties": {...},
    "required": [...]
}
```

Ollama 0.5+ usa grammar-based sampling para garantir o schema.

---

## Bug #10 — Severity inválida aceita ("not yet assessed")

**Arquivo**: `src/llm/llm_client.py`

**Sintoma**: campo `severity` aceitava qualquer string, falhando na validação posterior.

**Causa**: JSON Schema só restringia tipo (`string`), não valores.

**Fix**: adicionado `enum` no schema para `attack_type` (15 categorias) e `severity` (5 níveis). Modelo agora não consegue gerar valores fora do enum.

---

## Bug #11 — Normalização após validação

**Arquivo**: `src/llm/triage.py`

**Sintoma**: warnings constantes "attack_type inválido" e "confidence fora do intervalo", mesmo com normalização implementada.

**Causa**: ordem de execução errada — validava com valores brutos, normalizava depois.

**Fix**: invertida a ordem — normalização primeiro, validação depois:
```python
parsed["confidence"] = raw_conf / 100.0 if raw_conf > 1.0 else raw_conf
parsed["attack_type"] = _normalize_attack_type(parsed.get("attack_type"))
parsed["severity"] = parsed.get("severity").lower()
is_valid, errors = validate_triage_output(parsed)  # depois!
```

---

## Bug #12 — Pipeline LLM usava dataset normalizado

**Arquivo**: `src/llm/pipeline.py:load_dataset`

**Sintoma**: descrições geradas pelo `text_converter` saíam vazias ou inúteis ("Fluxo de rede desconhecido com duração instantânea").

**Causa**: pipeline carregava `unified_dataset.parquet` (normalizado para [0,1]). Como `text_converter` checa `if packets > 0`, valores normalizados como 0.001 viravam "0 pacotes" no formatter.

**Fix**: para `dataset_choice == "unified"`, concatenar os parquets individuais (`cic_clean` + `unsw_clean`) que preservam valores brutos.

---

## Bug #13 — "Web Attack  Brute Force" (espaço duplo) não mapeado

**Arquivo**: `src/config.py:CIC_LABEL_MAP`

**Sintoma**: 2.180 registros do CIC ficavam com label "Unknown".

**Causa**: alguns CSVs do CIC usam espaço duplo em vez do em-dash (–) original. Mapa só tinha as variantes com em-dash.

**Fix**: adicionadas variantes:
```python
"Web Attack  Brute Force": "Brute Force",   # espaço duplo
"Web Attack  XSS": "Web Attack",
"Web Attack  Sql Injection": "Web Attack",
```

---

## Bug #14 — Nomes de colunas CIC errados em text_converter

**Arquivo**: `src/llm/text_converter.py:_cic_record_to_text`

**Sintoma**: descrições do CIC sempre vazias, mesmo com dataset não-normalizado.

**Causa**: função usava nomes snake_case (`packets_count`, `bytes_rate`) que **nunca existiram** no CIC. As colunas reais são `"Total Fwd Packets"`, `"Flow Bytes/s"`, etc.

**Fix**: substituídos todos os nomes para os reais (Title Case com espaços):
```python
proto = _proto_name(rec.get("Protocol"))
duration = rec.get("Flow Duration", 0)
fwd_pkts = rec.get("Total Fwd Packets", 0)
# ... etc
```

---

## Bug #15 — Modelo retorna confidence 0-100 em vez de 0-1

**Arquivo**: `src/llm/triage.py`

**Sintoma**: validation error "confidence fora do intervalo [0,1]: 85.0".

**Causa**: modelo às vezes retorna `85` (interpretando como porcentagem) em vez de `0.85`.

**Fix**: normalização condicional:
```python
parsed["confidence"] = raw_conf / 100.0 if raw_conf > 1.0 else raw_conf
```

---

## Bug #16 — MITRE techniques com descrição misturada

**Arquivo**: `src/llm/triage.py`

**Sintoma**: campo `mitre_techniques` continha `"T1071 - Application Layer Protocol"` em vez de só `"T1071"`.

**Causa**: modelo gerava ID + descrição na mesma string.

**Fix**: regex para extrair apenas o ID:
```python
import re
cleaned = []
for t in parsed.get("mitre_techniques", []):
    m = re.search(r"T\d{4}(?:\.\d{3})?", str(t))
    if m:
        cleaned.append(m.group(0))
parsed["mitre_techniques"] = cleaned
```

---

## Bug #17 — Mesmo seed sempre (random_state=42)

**Arquivo**: `src/llm/pipeline.py`

**Sintoma**: toda execução produzia exatamente os mesmos 9 registros — runs supostamente independentes eram idênticas.

**Causa**: `select_records` e `load_dataset` usavam `config.RANDOM_SEED` fixo.

**Fix**: parâmetro `--seed` opcional; se não passado, gera seed aleatório a cada run. Script `run_evaluation.ps1` gera **um** seed e passa para RAG e no-RAG (garantindo mesma amostra entre os dois modos para comparação justa).

---

## Bug #18 — Outputs todos na mesma pasta

**Arquivo**: `src/llm/pipeline.py`

**Sintoma**: dezenas de JSONs na raiz de `outputs/`, difícil comparar runs.

**Causa**: nome de arquivo incluía timestamp mas todos iam pra mesma pasta.

**Fix**: cada run cria subpasta auto-descritiva:
```
outputs/triage_runs/run_<timestamp>_<rag|norag>_n<N>_<strat>/
    └── results.json
```

---

## Bug #19 — `pattern` no JSON Schema causa HTTP 500 no Ollama

**Arquivo**: `src/llm/llm_client.py`

**Sintoma**: 100% das requisições ao Ollama retornavam `500 Internal Server Error`.

**Causa**: adicionado `"pattern": "^T\\d{4}(\\.\\d{3})?$"` no schema do campo `mitre_techniques`. O Ollama usa `llama.cpp` para grammar-based sampling, que implementa apenas um subconjunto do JSON Schema — suporta `type`, `enum`, `required`, `properties`, `minimum`/`maximum`, mas **não suporta `pattern`**. O motor de grammar trava ao tentar compilar o regex.

**Fix**: removido o `pattern` — limpeza dos IDs MITRE já feita via regex em `triage.py`:
```python
# Antes (quebrava):
"mitre_techniques": {"type": "array", "items": {"type": "string", "pattern": "^T\\d{4}(\\.\\d{3})?$"}}

# Depois (correto):
"mitre_techniques": {"type": "array", "items": {"type": "string"}}
```

**Lição**: Ollama JSON Schema suportado pelo grammar sampling é limitado. Nunca usar `pattern`, `anyOf`, `oneOf`, `$ref`, `additionalProperties`, ou `if/then/else`. Validação de formato deve ser feita no código Python após a resposta.

---

## Bug #20 — `Flow Packets/s` do CIC inconsistente (taxa instantânea inflada)

**Arquivo**: `src/llm/text_converter.py:_cic_record_to_text`

**Sintoma**: text_converter v2 marcava fluxos benignos como `FLOOD` (41.7K pkt/s para 2 pacotes em 48s).

**Causa**: a coluna `Flow Packets/s` do CIC é computada com `Flow Duration` em microssegundos. Para fluxos curtos isso gera taxas absurdas que não refletem comportamento real.

**Fix**: text_converter v2 recalcula taxa via `total_pkts / duration` (em segundos), ignorando o campo do CIC.

```python
total_pkts = fwd_pkts + bwd_pkts
pkt_rate = (total_pkts / duration) if duration > 0 else 0.0
```

---

## Bug #21 — Fluxos minúsculos UNSW disparam falso FLOOD/Exfiltração

**Arquivo**: `src/llm/text_converter.py:_classify_packet_rate, _classify_byte_rate, _heuristic_attack_signatures`

**Sintoma**: classes UNSW (Generic, Fuzzers, Shellcode, Worms) eram classificadas como **DDoS** em todas as configs do benchmark — mesmo padrão de erro repetido 5+ vezes no `summary.json` do bench_20260503_224512.

**Causa**: para fluxos UNSW de 2 pacotes em 8μs (200B), a taxa instantânea calculada é 100M B/s e 250K pkt/s. O `_classify_*` interpretava como FLOOD, e a heurística "Exfiltração" disparava por `byte_rate > 1M`.

**Fix**: classificar como `INDETERMINADA`/`BURST` quando volume é minúsculo (<20 pkts ou <10KB ou <100ms duração). Heurística de exfiltração agora exige `fwd_bytes > 100KB` E `is_sustained` (≥0.1s + ≥20 pkts).

```python
def _classify_packet_rate(rate, total_pkts=None, duration=None):
    has_volume = (total_pkts is None) or (total_pkts >= 20)
    has_duration = (duration is None) or (duration >= 0.1)
    if rate > 1000:
        if not has_volume or not has_duration:
            return f"INDETERMINADA — fluxo curto demais para confirmar FLOOD; provável burst único"
        return f"FLOOD — DDoS volumétrico sustentado"
    # ...
```

**Lição**: nunca confiar em taxa sem checar volume. Datasets de IDS têm muitos fluxos minúsculos onde a taxa é ruído.

---

## Bug #22 — Stage 1 LLM binário (Foundation-Sec-8B) não confiável

**Arquivo**: `src/llm/triage.py` + `src/llm/prompts.py:STAGE1_SYSTEM_PROMPT`

**Sintoma**: config `4_rag_rerank_2stage` (com Stage 1) classificava DDoS, DoS, Exploits como **BENIGN** — gerando 3 FNs e queda da acurácia binária de 0.9 para 0.6.

**Causa**: Foundation-Sec-8B tem viés instável em decisões binárias com prompt zero-shot. Mesmo com prompt conservador ("default THREAT"), o modelo oscilava.

**Fix**: substituir Stage 1 LLM pelo **Random Forest** (99.8% acc, 0.04% risco de classificar threat como benign). Stage 1 LLM continua opt-in via `--two-stage` para experimentação, mas removido do benchmark default.

**Resultado prévio**: `5_rag_rerank_rf` (sem Stage 1, com RF) chegou a binária 100% no quick test.

---

## Estatísticas Gerais

- **22 bugs corrigidos** durante o desenvolvimento
- **Tempo médio para identificar cada bug**: ~10-15 min via análise de logs
- **Cobertura de testes pós-correção**: 78 testes unitários, 100% passando

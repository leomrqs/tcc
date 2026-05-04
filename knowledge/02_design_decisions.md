# Decisões de Design

Cada decisão técnica do projeto, com justificativa e alternativas consideradas.

---

## 1. Modelo de Embeddings: all-MiniLM-L6-v2

**Escolha**: 384 dimensões, modelo SentenceTransformers padrão.

**Justificativa**:
- Equilíbrio velocidade/qualidade comprovado em benchmarks
- Funciona offline após primeiro download (~80MB)
- Suficiente para RAG semântico em domínio aberto

**Alternativas consideradas**:
- `all-mpnet-base-v2` (768 dims): qualidade superior mas 3x mais lento
- Modelos especializados em segurança (ex: SecBERT): falta de modelo amplamente validado

**Limitação observada**: o modelo é genérico — não captura bem semântica específica de cibersegurança. Distâncias entre queries de tráfego de rede e regras Sigma ficam em 0.5-0.7 (alto), indicando match fraco.

---

## 2. Banco Vetorial: ChromaDB

**Escolha**: ChromaDB com cosine similarity, persistente em disco.

**Justificativa**:
- 100% local, sem dependência externa
- API simples e estável
- Suporte nativo a metadata por documento (filtragem por source)
- Persistência transparente (SQLite + HNSW)

**Alternativas**:
- FAISS: mais rápido mas requer mais código boilerplate
- Pinecone/Weaviate: SaaS, viola requisito de stack 100% local
- Qdrant: bom mas overkill para o tamanho do índice (4.4K docs)

---

## 3. Normalização Min-Max [0,1] (não Z-score)

**Escolha**: Min-Max scaling no dataset unificado.

**Justificativa**:
- Tráfego de rede tem distribuições altamente assimétricas (long-tail) — Z-score assume normalidade
- Mantém valores em range interpretável
- Compatível com algoritmos sensíveis a escala (futuras integrações com modelos ML clássicos)

**Decisão crítica**: o pipeline de triagem LLM **não usa o dataset normalizado**. Os parquets individuais (`cic_clean`, `unsw_clean`) preservam valores brutos para que o `text_converter` produza descrições com números reais ("230 pacotes" e não "0.001 pacotes").

---

## 4. Endpoint Ollama: /api/chat (não /api/generate)

**Escolha**: Migrado de `/api/generate` para `/api/chat`.

**Justificativa**:
- O modelo Foundation-Sec-8B é Llama 3 fine-tuned
- Llama 3 usa template de chat específico (`<|start_header_id|>system<|end_header_id|>...`)
- `/api/generate` com campo `"system"` **não aplica esse template** corretamente
- Resultado observado: com `/api/generate`, modelo ignorava completamente o system prompt e retornava JSON em formato livre

**Impacto**: mudança trouxe a taxa de respostas válidas de ~0% para 100%.

---

## 5. JSON Schema com Enum Restrito

**Escolha**: `"format"` com schema completo (não apenas `"json"`).

**Justificativa**:
- `"format": "json"` garante JSON válido mas **não restringe chaves nem valores**
- Modelo retornava `{"analysis": {...}}` ou `{"event": {...}}` em vez do esperado
- Schema com `enum` em `attack_type` e `severity` força grammar sampling no Ollama
- Modelo **fisicamente não consegue** gerar valores fora do enum

**Schema atual**:
```python
"format": {
  "type": "object",
  "properties": {
    "attack_type": {"type": "string", "enum": [15 categorias]},
    "severity": {"type": "string", "enum": ["informational", ..., "critical"]},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    "mitre_techniques": {"type": "array", "items": {"pattern": "^T\\d{4}(\\.\\d{3})?$"}},
    "explanation": {"type": "string", "minLength": 20},
    "recommendations": {"type": "array", "items": {"type": "string"}}
  },
  "required": [todas as 6 chaves]
}
```

---

## 6. Filtro de Qualidade RAG (distância > 0.55)

**Escolha**: Descartar contexto RAG quando o melhor documento tem distância > 0.55.

**Justificativa empírica**:
- Observado em runs: contextos com dist > 0.55 são semanticamente irrelevantes
- O modelo, vendo sempre os mesmos documentos (Cleartext Protocol, ComRAT, BITS Transfer), passa a classificar **tudo** como Botnet/C2
- Sem RAG, o modelo classifica com mais diversidade (apesar de menor confiança)

**Threshold escolhido**: 0.55 — calibrado em ~30 queries de teste. Valores entre 0.45 e 0.55 são "borderline relevantes"; acima de 0.55 são ruído.

**Impacto observado**: em runs com UNSW (protocolos numéricos abstratos), 6 de 9 contextos são descartados.

---

## 7. Temperatura LLM: 0.2 (não 0.7)

**Escolha**: Temperatura baixa para inferência.

**Justificativa**:
- Triagem de segurança requer **consistência**, não criatividade
- Mesma entrada deve produzir mesma saída (reprodutibilidade)
- Baixa temperatura reduz variabilidade entre runs
- 0.2 ainda permite alguma variação (não totalmente determinístico)

---

## 8. Quantização Q8_0 (não Q4)

**Escolha**: Modelo Foundation-Sec-8B Q8_0 (~8.5GB).

**Justificativa**:
- Q8_0 tem qualidade quase idêntica ao FP16 original
- Q4_K_M (~4.5GB) seria mais rápido mas com perda perceptível em tarefas estruturadas
- Hardware do projeto (RTX 5060 8GB): Q8_0 carrega 22/33 camadas na GPU (modo low VRAM)
- Q4_K_M caberia inteiro na GPU, mas a perda de qualidade não compensa em uma tarefa sensível

**Trade-off documentado**: ~22s/registro com Q8_0 vs estimados ~10s com Q4_K_M.

---

## 9. Prompt em Inglês (não Português)

**Escolha**: System prompt e instruções em inglês.

**Justificativa**:
- Foundation-Sec-8B foi treinado predominantemente em inglês
- Documentação MITRE ATT&CK e Sigma Rules são em inglês
- Modelos Llama 3 seguem instruções melhor em inglês

**Excessão**: a descrição do registro (`record_description`) permanece em português — é gerada pelo pipeline e o LLM consegue interpretá-la.

---

## 10. Carregamento dos Parquets Individuais (não unified) na Triagem

**Escolha**: `load_dataset("unified")` concatena `cic_clean.parquet` + `unsw_clean.parquet` em vez de usar `unified_dataset.parquet`.

**Justificativa**:
- O `unified_dataset.parquet` está **normalizado** [0,1]
- O `text_converter` converte features em texto (ex: "230 pacotes") com base nos valores brutos
- Com valores normalizados, `0.001 pacotes` → arredondado para 0 → descrição vazia
- **Bug original**: pipeline carregava unified e gerava descrições inúteis ("Fluxo de rede desconhecido com duração instantânea.")

---

## 11. Estratificação na Amostragem

**Escolha**: Amostra com `~n` registros por classe (não amostragem aleatória global).

**Justificativa**:
- Datasets têm 80-87% de Benign — amostra aleatória de 10 registros tem ~8 Benigns
- Estratificação garante representação de classes raras (Botnet, Worms, Backdoor)
- Implementação: `df.groupby("label")` + `pd.concat` (evita bug do `groupby().apply()` no pandas 2.x que dropa coluna)

---

## 12. Logger Customizado (não logging padrão)

**Escolha**: `src/utils/logger.py` com `StreamHandler` + formato com timestamp.

**Justificativa**:
- Formato consistente entre módulos
- Timestamps facilitam medição de performance
- Single point of configuration para nível de log

---

## 13. Outputs Organizados por Run

**Escolha**: cada execução cria subpasta `outputs/triage_runs/run_<timestamp>_<rag|norag>_n<N>_<strat>/`.

**Justificativa**:
- Facilita comparação entre runs
- Evita poluição de uma pasta única com múltiplos JSONs
- Nome da pasta auto-documenta os parâmetros da run
- Permite anexar artefatos extras (gráficos, análises) por run no futuro

---

## 14. Seed Aleatório por Default

**Escolha**: `--seed` opcional; se omitido, usa seed aleatório gerado por Python.

**Justificativa**:
- Seeds fixos (ex: 42) mascaram problemas — sempre os mesmos registros
- Aleatoriedade revela inconsistências
- Pode ser fixado com `--seed 42` para reprodutibilidade quando necessário
- Script `run_evaluation.ps1` gera UM seed e passa para RAG e no-RAG (garantindo amostra **idêntica** entre os dois modos para comparação justa)

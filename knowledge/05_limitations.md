# Limitações Conhecidas

Material para a seção de discussão honesta do TCC. Cada limitação inclui uma resposta fundamentada para defesa em banca.

---

## L1 — Amostra de Avaliação Pequena

**Limitação**: runs com 7-10 registros não são estatisticamente significativas. Intervalos de confiança são amplos — um único acerto ou erro move a acurácia binária em 10-14pp.

**Por que acontece**: o modelo leva ~20-30s por registro. Para 45 registros (N=3 por classe), são ~15-22 minutos por run. Sem GPU dedicada de alta capacidade, avaliações grandes são impraticais em ambiente de desenvolvimento.

**Resposta para a banca**: "O objetivo desta etapa é validação de conceito (proof-of-concept). Os resultados são consistentes entre runs com seeds diferentes, sugerindo estabilidade mesmo com amostras pequenas. A metodologia está documentada para replicação com hardware adequado."

**Mitigação parcial**: estratificação garante representação de todas as classes mesmo em amostras pequenas.

---

## L2 — Modelo LLM nunca prediz "Benign" (TN = 0) — MITIGADO com RF

**Limitação original**: o modelo Foundation-Sec-8B tem viés forte para identificar ameaças. Tráfego benigno é invariavelmente classificado como Reconnaissance ou Exploits.

**Mitigação implementada**: Random Forest pre-classifier (99.8% acc CIC, 99.1% acc UNSW).
- 97-98% dos Benigns são capturados com confiança ≥95% e o LLM é saltado
- Risco residual de 0.04% de ameaças mal classificadas como Benign

**Resultado observado**: TN=1/1 (100%) no benchmark `5_rag_rerank_rf`.

**Limitação residual**: o LLM sozinho (sem RF) ainda não prevê Benign. Para registros onde o RF não tem confiança ≥95%, o LLM ainda tende a classificar como ameaça.

---

## L3 — Acurácia por Categoria Exata Baixa (0-20%)

**Limitação**: distinguir DoS de DDoS de Reconnaissance a partir de features de fluxo de rede é inerentemente difícil sem contexto temporal agregado. Um único fluxo TCP com poucos pacotes e ACK flags pode ser qualquer uma dessas três categorias dependendo do contexto maior (volume de fluxos simultâneos, padrão histórico do host).

**Causa técnica**: o `text_converter.py` descreve um único registro — sem visão agregada (ex: "1000 fluxos similares por segundo desta fonte"). O modelo não tem como distinguir DDoS de Reconnaissance sem essa informação.

**Resposta para a banca**: "A tarefa definida — classificar incidentes a partir de registros individuais sem contexto histórico — é um problema difícil até para analistas humanos. A acurácia binária (ameaça vs benigno) de 88-90% é mais relevante operacionalmente. A classificação exata é útil para priorização, não para detecção inicial."

---

## L4 — RAG com Baixa Relevância Semântica para Dados UNSW

**Limitação**: a base de conhecimento (MITRE ATT&CK + Sigma Rules) é em inglês, focada em técnicas de alto nível. Os registros UNSW têm protocolos numéricos abstratos (114, 120, 122) sem mapeamento semântico óbvio. Resultado: 60-70% dos registros UNSW têm distância RAG > 0.55 e o contexto é descartado.

**Impacto**: o RAG não agrega valor para a maioria dos registros UNSW. O pipeline degenera para o modo "no-RAG" implicitamente.

**Resposta para a banca**: "O filtro de qualidade (distância > 0.55) está funcionando como projetado — evita que contexto irrelevante piore a classificação. Uma melhoria futura seria adicionar à base de conhecimento documentação específica sobre datasets IDS (ex: descrições dos protocolos UNSW, payloads típicos por classe) ou usar um modelo de embeddings especializado em tráfego de rede."

---

## L5 — Modelo de Embeddings Genérico (all-MiniLM-L6-v2)

**Limitação**: `all-MiniLM-L6-v2` é treinado em corpus genérico (Wikipedia, web text). Não captura bem semântica específica de cibersegurança ou tráfego de rede. Distâncias entre queries de tráfego e regras Sigma ficam sistematicamente em 0.5-0.7 (alto), indicando match semântico fraco.

**Impacto**: a recuperação RAG é menos precisa do que seria com um modelo de embeddings especializado.

**Resposta para a banca**: "Modelos de embeddings especializados em cibersegurança (ex: SecBERT, CySecBERT) existem mas têm suporte limitado e não são amplamente validados. A escolha de `all-MiniLM-L6-v2` prioriza reprodutibilidade e estabilidade. O filtro de distância mitiga parcialmente o problema ao descartar recuperações irrelevantes."

---

## L6 — Stack 100% Local: Limitações de Hardware

**Limitação**: Foundation-Sec-8B Q8_0 (~8.5GB) não cabe inteiro na RTX 5060 8GB. Modo low-VRAM (22/33 camadas na GPU) resulta em ~20-30s por inferência. Em produção real, latências dessa magnitude são impraticáveis.

**Resposta para a banca**: "O requisito de stack 100% local é intencional — muitos ambientes de segurança têm restrições de conectividade que impedem uso de APIs externas. A proposta é demonstrar viabilidade conceitual, não performance de produção. Com hardware adequado (A100 80GB ou similar), o mesmo modelo rodaria em <2s por inferência."

---

## L7 — Dependência de Ollama e Foundation-Sec-8B

**Limitação**: o sistema depende do Ollama rodando localmente e do modelo específico `foundation-sec-8b-instruct`. Se o modelo for descontinuado ou o Ollama mudar a API, o pipeline quebra.

**Mitigações implementadas**:
- `.env` permite trocar o modelo sem alterar código
- `OllamaClient` encapsula a comunicação — uma mudança de endpoint requer alteração apenas em `llm_client.py`
- Testado apenas com Foundation-Sec-8B; outros modelos Llama 3 devem funcionar mas não foram validados

---

## L8 — Sem Validação Qualitativa das Explicações

**Limitação**: as explicações e recomendações geradas são avaliadas apenas quanto à validade estrutural (comprimento mínimo, formato JSON). Não há avaliação se a explicação é tecnicamente correta ou operacionalmente útil.

**Impacto para o TCC**: a qualidade das explicações é um diferencial do sistema, mas não está quantificada.

**Mitigação proposta**: avaliação qualitativa por amostra — selecionar 10-20 registros com especialistas em segurança que avaliem a coerência das explicações em escala Likert.

---

## L9 — Reprodutibilidade Parcial com LLM

**Limitação**: mesmo com temperatura 0.2, o LLM não é deterministico. A mesma entrada pode gerar respostas ligeiramente diferentes entre execuções. Seeds fixos na amostragem garantem os mesmos registros, mas não as mesmas respostas do modelo.

**Mitigação**: documentação do seed de cada run (`run_evaluation.ps1` loga o seed usado). Para reprodução exata, seria necessário `temperature=0` e uso do mesmo hardware/versão do Ollama.

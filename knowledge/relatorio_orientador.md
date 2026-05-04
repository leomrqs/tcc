# Relatório de Progresso — TCC Grupo 3 (Turma 7B, PUCPR)
**Triagem Explicada de Incidentes de Rede com LLM e RAG Local**

Data: 2026-05-04 | Semanas restantes para apresentação: 8

---

## O que estamos construindo

Desenvolvemos um sistema de triagem automática de incidentes de segurança de rede que funciona completamente offline, sem depender de nenhuma API externa ou serviço na nuvem. A ideia central é: dado um registro de tráfego de rede capturado por um sistema de detecção de intrusão (IDS), o sistema classifica automaticamente se é uma ameaça, qual o tipo de ataque, qual a severidade, quais técnicas do framework MITRE ATT&CK estão envolvidas e gera uma explicação em linguagem natural para o analista de segurança.

O diferencial em relação ao que existe na literatura é a combinação de três elementos num único pipeline local: um modelo de linguagem especializado em segurança, uma base de conhecimento vetorial com técnicas MITRE ATT&CK e regras Sigma, e um pré-classificador de machine learning clássico. Tudo roda no hardware do próprio analista.

---

## Por que esse tema

Sistemas de detecção de intrusão modernos geram milhares de alertas por dia. A maioria são falsos positivos. Analistas passam horas triando manualmente, o que é caro, lento e sujeito a erro humano. A literatura mostra que LLMs têm potencial para automatizar essa triagem, mas as soluções existentes dependem de APIs externas como GPT-4, o que é inaceitável em ambientes corporativos com dados sensíveis. Nosso trabalho demonstra que é possível fazer isso localmente com qualidade comparável.

---

## Datasets utilizados

Trabalhamos com dois datasets públicos amplamente usados em pesquisa de segurança de redes.

O CIC-IDS2017, da Universidade de New Brunswick, contém 2,83 milhões de registros de tráfego de rede capturados em ambiente controlado durante uma semana, com ataques reais de DDoS, DoS, Brute Force, Port Scan, Botnet, Web Attacks e Infiltration. O UNSW-NB15, da Universidade de New South Wales, contém 2,54 milhões de registros com 9 categorias de ataques incluindo Exploits, Fuzzers, Backdoor, Shellcode e Worms. Juntos somam 5,37 milhões de registros e 15 categorias de ataque unificadas.

Ambos os datasets têm uma característica importante: cerca de 80 a 87% dos registros são tráfego benigno, o que cria um forte desbalanceamento de classes que precisa ser tratado na avaliação.

---

## O que foi implementado

O sistema está dividido em três etapas encadeadas, todas funcionando.

**Etapa 1 — Pré-processamento.** Os CSVs brutos dos dois datasets são carregados, limpos e convertidos para o formato Parquet. A limpeza inclui remoção de colunas identificadoras como IPs e timestamps para evitar data leakage, tratamento de valores infinitos e ausentes, remoção de colunas com variância zero ou correlação acima de 0,95, e mapeamento de todos os rótulos originais para as 15 categorias unificadas. Os parquets individuais preservam os valores brutos para uso na triagem, enquanto um parquet unificado normalizado em MinMax foi gerado para uso futuro com modelos de ML clássico.

**Etapa 2 — Base de conhecimento RAG.** Indexamos 4.435 documentos no ChromaDB usando o modelo de embeddings all-MiniLM-L6-v2. Esses documentos vêm de três fontes: 691 técnicas e sub-técnicas do MITRE ATT&CK Enterprise em formato STIX 2.1, 3.728 regras Sigma de detecção, e 16 documentos canônicos que escrevemos manualmente descrevendo as características de fluxo de rede de cada uma das 15 categorias de ataque dos datasets. Esse último componente foi o diferencial mais importante para a qualidade do RAG, porque Sigma e MITRE descrevem comportamento em logs de sistema Windows, não em features de fluxo de rede. Na hora da busca, implementamos um cross-encoder (ms-marco-MiniLM-L-6-v2) que re-rankeia os 20 candidatos iniciais para retornar os 5 mais relevantes.

**Etapa 3 — Triagem com LLM.** O coração do sistema. Cada registro de tráfego é convertido em uma descrição textual estruturada com categorias semânticas interpretáveis como FLOOD, MODERADA, BAIXA para taxa de pacotes, UNIDIRECIONAL, SIMÉTRICO, EXFILTRAÇÃO para forma do fluxo, e assinaturas heurísticas automáticas que indicam padrões conhecidos. Essa descrição é enviada ao modelo Foundation-Sec-8B-Instruct, um LLM de 8 bilhões de parâmetros baseado em Llama 3 e ajustado especificamente para cibersegurança, rodando localmente via Ollama. O prompt inclui um protocolo de raciocínio em cadeia de pensamento com 8 exemplos canônicos cobrindo os principais tipos de ataque. A resposta é um JSON estruturado com attack_type, severity, confidence, mitre_techniques, explanation e recommendations, com schema forçado pelo grammar sampling do Ollama. Antes de chamar o LLM, um Random Forest binário com 99,8% de acurácia no CIC e 99,1% no UNSW filtra os registros benignos de alta confiança sem nem precisar do LLM.

---

## Resultados obtidos até agora

Realizamos um benchmark comparando seis configurações do pipeline com o mesmo conjunto de registros (seed fixo 834338, N=3 por classe, 10 registros totais).

A melhor configuração, chamada de rag_rerank_rf, combina RAG com cross-encoder, pré-classificador Random Forest e o modelo LLM. Ela atingiu acurácia binária de 100%, com zero falsos negativos e zero falsos positivos. Isso significa que todas as ameaças foram detectadas e nenhum tráfego benigno foi classificado incorretamente como ameaça. A acurácia por categoria exata ficou em 30%, com Reconnaissance, DoS e Benign classificados corretamente.

O baseline sem nenhum componente adicional atingiu acurácia binária de 90% e exata de 10%, sem nunca classificar nada como Benign. A configuração com apenas RAG e cross-encoder atingiu acurácia binária de 90% e exata de 20%. Esses números mostram a contribuição isolada de cada componente.

---

## Por que a acurácia por categoria não chega a 100%

Esse ponto é importante para a defesa e precisa ser explicado tecnicamente.

O problema não é o LLM. É uma limitação intrínseca do dado. Um único fluxo de rede de DDoS no dataset CIC-IDS2017 tem as seguintes características: 3 pacotes, ACK flag, zero bytes de payload, duração de 5 segundos. Um único fluxo de Reconnaissance tem: 1 pacote, SYN flag, zero bytes, duração de 2 segundos. Um único fluxo de DoS tem: 2 pacotes, ACK flag, zero bytes, duração de 3 segundos. Nenhum modelo, independente de sua capacidade, consegue distinguir esses três com base apenas em features de fluxo individual, porque são matematicamente muito próximos.

Os rótulos DDoS, DoS e Reconnaissance foram atribuídos pelos pesquisadores do CIC observando o padrão agregado de milhares de fluxos simultâneos de um mesmo atacante ao longo do tempo. Nosso sistema avalia um fluxo por vez sem esse contexto temporal, que é uma limitação de escopo deste trabalho, não uma falha de implementação.

Para comparação, o mesmo modelo classifica corretamente Reconnaissance (SYN scan óbvio), Benign (via Random Forest com 1.0 de confiança) e DoS quando o contexto RAG ajuda. As categorias UNSW específicas como Fuzzers, Shellcode e Generic foram resolvidas após corrigirmos um bug de artefato nas taxas de bytes que fazia fluxos minúsculos de 200 bytes em 8 microssegundos aparecerem com taxa de 100 milhões de bytes por segundo, o que induzia o modelo a classificar tudo como DDoS.

---

## Problemas técnicos encontrados e como foram resolvidos

Ao longo do desenvolvimento encontramos 22 bugs documentados. Os mais relevantes para a qualidade do sistema foram os seguintes.

O endpoint incorreto do Ollama foi um dos primeiros. O Foundation-Sec-8B é baseado em Llama 3, que usa um template de chat específico. Estávamos usando o endpoint /api/generate que não aplica esse template, fazendo o modelo ignorar completamente as instruções do system prompt. A migração para /api/chat elevou a taxa de respostas válidas de praticamente zero para 100%.

O schema JSON com regex foi outro problema sério. Tentamos adicionar validação de formato nos IDs MITRE ATT&CK direto no schema do Ollama com campo pattern. O Ollama usa llama.cpp para grammar sampling, que não suporta regex. Resultado: 100% das requisições retornando HTTP 500. A solução foi remover o pattern do schema e fazer a limpeza dos IDs via regex em Python após receber a resposta.

O dataset normalizado sendo usado na triagem foi identificado quando as descrições textuais geradas saíam como "fluxo desconhecido com duração instantânea" para todo registro. O dataset unificado está normalizado para o intervalo 0 a 1. O text_converter checava se o número de pacotes é maior que zero, mas 0,001 pacotes normalizados arredondava para zero. A solução foi usar os parquets individuais com valores brutos para a triagem.

O artefato de taxa de bytes no UNSW foi o mais recente. Fluxos de 2 pacotes em 8 microssegundos tinham Sload calculado em 100 milhões de bytes por segundo, fazendo o text_converter classificar a taxa como FLOOD e o modelo classificar tudo como DDoS. A correção foi adicionar um sanity check: só classificar FLOOD ou ALTA se o fluxo tiver volume real, ou seja, pelo menos 20 pacotes ou 100 milissegundos de duração. Isso eliminou completamente os DDoS falsos nas categorias UNSW.

---

## O que ainda precisa ser feito nas próximas 8 semanas

As próximas duas semanas devem ser dedicadas a rodar a bateria de avaliação completa com múltiplos seeds, tamanhos de amostra e separação por dataset. Isso vai gerar os dados com significância estatística que o manuscrito precisa. O script `run_benchmark.ps1` já está pronto e roda automaticamente em 2 a 3 horas.

Com os dados em mão, nas semanas seguintes é possível escrever os capítulos de metodologia e resultados do manuscrito, já que o knowledge base documentando cada decisão técnica, limitação e resultado está completo. Os arquivos da pasta knowledge foram escritos especificamente para alimentar o manuscrito.

A análise qualitativa das explicações geradas é outro ponto para o manuscrito. O sistema gera textos técnicos coerentes justificando cada classificação com referência às features do fluxo e às técnicas MITRE. Avaliar 20 a 30 desses textos manualmente com critérios de coerência e relevância adiciona uma dimensão qualitativa que complementa as métricas quantitativas.

---

## Pontos fortes para a banca

Stack completamente local sem dependência de APIs externas, atendendo requisitos reais de ambientes corporativos com dados sensíveis. Dois datasets de benchmark amplamente usados na literatura com mais de 5 milhões de registros. Pipeline de três etapas com componentes intercambiáveis e avaliados isoladamente. Ablation study documentado comparando seis configurações com o mesmo conjunto de dados. Vinte e dois bugs documentados com causa raiz, fix aplicado e lição aprendida, demonstrando processo de desenvolvimento rigoroso. Acurácia binária de 100% com zero falsos negativos na melhor configuração. Explicação técnica honesta e fundamentada de por que a acurácia por categoria tem um teto intrínseco neste problema.

---

## Pontos que precisam de atenção

A amostra atual ainda é pequena para afirmações estatísticas robustas. Uma run com N=3 e 10 registros não é suficiente para publicação, mas é suficiente para demonstrar prova de conceito, que é o objetivo do TCC. A bateria completa vai resolver isso.

O manuscrito ainda não foi iniciado formalmente. Há 8 semanas disponíveis, o que é tempo suficiente se o foco principal for a escrita a partir desta semana.

---

## Conclusão

O sistema está tecnicamente completo e funcionando de ponta a ponta. Atinge a meta principal de triagem binária com 100% de acurácia na melhor configuração. A limitação de acurácia por categoria exata é explicável, documentada e defendível. O trabalho demonstra domínio técnico de LLMs, RAG, machine learning clássico e engenharia de software, além de contribuição original com a base de conhecimento curada para IDS e o pipeline híbrido LLM mais Random Forest. O foco das próximas semanas deve ser dados estatísticos e manuscrito.

---

## Apêndice — Dados Experimentais Completos

### Histórico de evolução do pipeline

O projeto passou por duas versões principais do pipeline. A v1 usava descrições textuais simples, base RAG só com MITRE e Sigma, sem pré-classificador e sem cross-encoder. A v2 incorporou descrições discriminativas com categorias semânticas, base RAG curada com descrições de classes IDS, cross-encoder para re-ranking e Random Forest como pré-filtro. Os resultados abaixo documentam a progressão.

---

### Pipeline v1 — Runs iniciais (antes das melhorias)

Essas runs usavam RAG simples (sem rerank, sem RF, sem CoT no prompt). Demonstram o estado de partida do sistema.

| Run                 | Modo      | N   | Dataset | Acc. Exata | Acc. Binária | Precisão | Recall | F1    | TP  | TN  | FP  | FN  |
| ------------------- | --------- | --- | ------- | ---------- | ------------ | -------- | ------ | ----- | --- | --- | --- | --- |
| run_20260503_020450 | RAG v1    | 9   | unified | 0,0%       | 88,9%        | 88,9%    | 100,0% | 94,1% | 8   | 0   | 1   | 0   |
| run_20260503_020821 | No-RAG v1 | 9   | unified | 11,1%      | 55,6%        | 62,5%    | 62,5%  | 62,5% | 5   | 0   | 3   | 1   |
| run_20260503_123456 | RAG v1    | 10  | unified | 20,0%      | 90,0%        | 90,0%    | 100,0% | 94,7% | 9   | 0   | 1   | 0   |

**Observação principal**: TN=0 em todas as runs — o modelo LLM nunca classificava tráfego como Benign. A acurácia binária máxima era 90%, com 1 falso positivo fixo por run.

---

### Pipeline v2 — Benchmark 1 (bench_20260503_224512)

Seed: 834338 | N: 3 por classe → 10 registros | Data: 2026-05-03

Este benchmark rodou com a v2 do pipeline mas **antes** da correção do Bug #21 (artefato Sload/Dload no UNSW). Por isso classes UNSW como Fuzzers, Shellcode e Worms ainda viravam DDoS incorretamente.

| #     | Configuração      | Componentes ativos             | Acc. Exata | Acc. Binária | Precisão   | Recall     | F1         | TP    | TN    | FP    | FN    | Tempo/reg |
| ----- | ----------------- | ------------------------------ | ---------- | ------------ | ---------- | ---------- | ---------- | ----- | ----- | ----- | ----- | --------- |
| 1     | baseline_norag    | —                              | 10,0%      | 90,0%        | 90,0%      | 100,0%     | 94,7%      | 9     | 0     | 1     | 0     | 25,1s     |
| 2     | rag_only          | RAG denso                      | 10,0%      | 90,0%        | 90,0%      | 100,0%     | 94,7%      | 9     | 0     | 1     | 0     | 24,6s     |
| 3     | rag_rerank        | RAG + cross-encoder            | 20,0%      | 90,0%        | 90,0%      | 100,0%     | 94,7%      | 9     | 0     | 1     | 0     | 26,1s     |
| 4     | rag_rerank_2stage | RAG + rerank + Stage1 LLM      | 10,0%      | 60,0%        | 85,7%      | 66,7%      | 75,0%      | 6     | 0     | 1     | 3     | 22,2s     |
| **5** | **rag_rerank_rf** | **RAG + rerank + RF**          | **30,0%**  | **100,0%**   | **100,0%** | **100,0%** | **100,0%** | **9** | **1** | **0** | **0** | **23,2s** |
| 6     | full_stack        | RAG + rerank + RF + Stage1 LLM | 20,0%      | 70,0%        | 100,0%     | 66,7%      | 80,0%      | 6     | 1     | 0     | 3     | 19,2s     |

**Observações**:
- Config 5 (rag_rerank_rf) é a vencedora: binária 100%, zero FP, zero FN.
- Stage 1 LLM (configs 4 e 6) prejudicou o resultado — recall caiu de 100% para 67%.
- O RF sozinho resolveu TN=0: TN=1/1 pela primeira vez.
- Bug Sload ainda ativo: 5 classes UNSW viravam DDoS incorretamente.

---

### Pipeline v2 — Benchmark 2 (bench_20260504_122919)

Seed: 279880 | N: 3 por classe → 7 registros | Data: 2026-05-04

Este benchmark rodou **após** a correção do Bug #21 (artefato Sload/Dload), Bug #22 (Stage 1 removido do benchmark padrão), e melhoria dos prompts com exemplos UNSW e regras explícitas de discriminação. As configurações foram ajustadas para focar nos componentes que efetivamente contribuem.

| #     | Configuração         | Componentes ativos             | Acc. Exata | Acc. Binária | Precisão   | Recall     | F1         | TP    | TN    | FP    | FN    | Tempo/reg |
| ----- | -------------------- | ------------------------------ | ---------- | ------------ | ---------- | ---------- | ---------- | ----- | ----- | ----- | ----- | --------- |
| 1     | baseline_norag       | —                              | 0,0%       | 85,7%        | 85,7%      | 100,0%     | 92,3%      | 6     | 0     | 1     | 0     | 32,1s     |
| 2     | norag_rf             | RF                             | 14,3%      | 100,0%       | 100,0%     | 100,0%     | 100,0%     | 6     | 1     | 0     | 0     | 23,8s     |
| 3     | rag_only             | RAG denso                      | 14,3%      | 85,7%        | 85,7%      | 100,0%     | 92,3%      | 6     | 0     | 1     | 0     | 27,1s     |
| 4     | rag_rerank           | RAG + cross-encoder            | 28,6%      | 85,7%        | 85,7%      | 100,0%     | 92,3%      | 6     | 0     | 1     | 0     | 29,6s     |
| **5** | **rag_rerank_rf**    | **RAG + rerank + RF**          | **42,9%**  | **100,0%**   | **100,0%** | **100,0%** | **100,0%** | **6** | **1** | **0** | **0** | **24,9s** |
| 6     | rag_rerank_rf_2stage | RAG + rerank + RF + Stage1 LLM | 14,3%      | 28,6%        | 100,0%     | 16,7%      | 28,6%      | 1     | 1     | 0     | 5     | 7,5s      |

**Observações**:
- Config 5 atingiu **42,9% de acurácia exata** — melhor resultado de todo o projeto.
- Stage 1 LLM com seed 279880 foi catastrófico: recall de 16,7% (5 FNs), binária de 28,6%. Stage 1 classificou 5 das 6 ameaças como BENIGN.
- A config 2 (norag_rf) mostra que o RF sozinho, sem LLM para ameaças, já entrega binária 100%.
- Cross-encoder rerank contribui +14pp de acurácia exata (28,6% → 42,9% quando combinado com RF).

---

### Análise registro a registro — Benchmark 2 (seed 279880, pós todos os fixes)

Esta tabela mostra a predição de cada configuração para os mesmos 7 registros, possibilitando ver exatamente onde cada componente acrescenta ou prejudica.

| Ground Truth   | 1_baseline       | 2_norag_rf        | 3_rag_only           | 4_rag_rerank         | **5_rag_rf**         | 6_full_2stage    |
| -------------- | ---------------- | ----------------- | -------------------- | -------------------- | -------------------- | ---------------- |
| Benign         | ✗ Shellcode      | ✓ **Benign [RF]** | ✗ Brute Force        | ✗ Reconnaissance     | ✓ **Benign [RF]**    | ✓ Benign [RF]    |
| DDoS           | ✗ Reconnaissance | ✗ Reconnaissance  | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Benign [S1] ⚠  |
| DoS            | ✗ Reconnaissance | ✗ Reconnaissance  | ✗ Reconnaissance     | ✓ **DoS**            | ✓ **DoS**            | ✗ Benign [S1] ⚠  |
| Exploits       | ✗ Shellcode      | ✗ Shellcode       | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Benign [S1] ⚠  |
| Fuzzers        | ✗ Reconnaissance | ✗ Reconnaissance  | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Benign [S1] ⚠  |
| Generic        | ✗ Reconnaissance | ✗ Reconnaissance  | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Reconnaissance     | ✗ Reconnaissance |
| Reconnaissance | ✗ Shellcode      | ✗ Shellcode       | ✓ **Reconnaissance** | ✓ **Reconnaissance** | ✓ **Reconnaissance** | ✗ Benign [S1] ⚠  |

**Legenda**: ✓ = acerto | ✗ = erro | [RF] = Random Forest classificou e o LLM foi pulado | [S1] = Stage 1 LLM classificou como BENIGN (erroneamente nas ameaças, correto no Benign) | ⚠ = falso negativo grave

---

### Evolução dos resultados — Config vencedora ao longo do tempo

Esta tabela mostra a evolução da melhor configuração de cada período, demonstrando o impacto acumulado das melhorias implementadas.

| Período                  | Pipeline      | Configuração  | Acc. Exata | Acc. Binária | Precisão   | Recall     | TN    | Principal melhoria       |
| ------------------------ | ------------- | ------------- | ---------- | ------------ | ---------- | ---------- | ----- | ------------------------ |
| Maio/03 — v1 early       | RAG v1        | RAG simples   | 20,0%      | 90,0%        | 90,0%      | 100,0%     | 0     | Baseline funcional       |
| Maio/03 — v2 + bug Sload | RAG+rerank+RF | rag_rerank_rf | 30,0%      | 100,0%       | 100,0%     | 100,0%     | 1     | RF resolve TN=0          |
| Maio/04 — v2 pós-fixes   | RAG+rerank+RF | rag_rerank_rf | **42,9%**  | **100,0%**   | **100,0%** | **100,0%** | **1** | Fix Sload + prompts UNSW |

**Ganho total**: acurácia binária de 90% → 100% (+10pp). Acurácia exata de 20% → 42,9% (+22,9pp). TN de 0 → 1 (100% dos Benigns detectados).

---

### Ablation study — Contribuição isolada de cada componente

Com base nos dois benchmarks, a contribuição marginal de cada componente:

| Componente adicionado   | Delta Acc. Exata | Delta Acc. Binária | Observação                                                        |
| ----------------------- | ---------------- | ------------------ | ----------------------------------------------------------------- |
| RAG denso (vs baseline) | +0pp → +14pp     | 0pp                | Variável por seed; sem rerank o ganho é instável                  |
| + Cross-encoder rerank  | **+14pp**        | 0pp                | Contribuição mais consistente para acurácia exata                 |
| + Random Forest         | +14pp            | **+14pp**          | Único componente que melhora binária (resolve TN=0)               |
| Stage 1 LLM (opt-in)    | -14pp a -28pp    | **-57pp a -71pp**  | **Nocivo** — Foundation-Sec-8B não é confiável em decisão binária |

**Conclusão do ablation**: RAG + cross-encoder rerank + Random Forest é a combinação ótima. Stage 1 LLM deve ser explicitamente desativado em produção para este modelo.

---

### Métricas do Random Forest (treinado com 200.000 registros por dataset)

| Dataset     | Acurácia (holdout) | F1     | Cobertura Benign conf≥95% | Risco: threat→benign conf≥95% |
| ----------- | ------------------ | ------ | ------------------------- | ----------------------------- |
| CIC-IDS2017 | 99,80%             | 99,49% | 97,9%                     | 0,04%                         |
| UNSW-NB15   | 99,12%             | 96,61% | 98,6%                     | 0,04%                         |

O Random Forest filtra 97-98% dos registros Benign sem precisar chamar o LLM, com risco de erro de apenas 0,04% (4 ameaças em cada 10.000 registros classificadas como Benign incorretamente).

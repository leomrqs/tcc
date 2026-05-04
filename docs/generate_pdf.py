#!/usr/bin/env python3
"""Gera docs/bcc.pdf - estado atual completo do projeto TCC Grupo 3.
   Execute: python docs/generate_pdf.py
"""
from fpdf import FPDF
import os

# ── Layout (A4 = 210 x 297 mm) ───────────────────────────────────────────────
LM, RM, TM, BM = 15, 15, 17, 22
GAP = 5
CW  = (210 - LM - RM - GAP) / 2   # 87.5 mm por coluna
PB  = 297 - BM                      # 275 mm (fundo utilizável)
XC  = [LM, LM + CW + GAP]          # x inicial de cada coluna

# ── Tamanhos de fonte ─────────────────────────────────────────────────────────
F_TITLE = 16
F_AUTH  = 10
F_SEC   = 9.5
F_BODY  = 9
F_TBL   = 7.8
F_NOTE  = 7.3
LH_B    = 4.3   # line-height body
LH_T    = 3.8   # line-height table


class Doc(FPDF):
    def __init__(self):
        super().__init__(format='A4')
        self.set_auto_page_break(False)
        self.set_margins(LM, TM, RM)
        self._c  = 0
        self._cy = [TM, TM]

    def footer(self):
        self.set_y(-(BM - 5))
        self.set_font('Times', 'I', 7)
        self.cell(0, 5, str(self.page_no()), align='C')

    # ── helpers ───────────────────────────────────────────────────────────────
    @property
    def _x(self): return XC[self._c]
    @property
    def _y(self): return self._cy[self._c]
    def _adv(self, h): self._cy[self._c] += h
    def _rem(self): return PB - self._cy[self._c]
    def _go(self): self.set_xy(self._x, self._y)

    def _ensure(self, h):
        """Garantir espaco h mm na coluna atual; mudar coluna/página se necessário."""
        if self._rem() < h:
            if self._c == 0:
                self._rc()
                if self._rem() < h:
                    self._np()
            else:
                self._np()

    def _np(self):
        self.add_page(); self._cy = [TM, TM]; self._c = 0; self._go()

    def _rc(self):
        self._c = 1; self._go()

    def _gap(self, h=2): self._adv(h)

    def _sh(self, txt):
        self._ensure(14)
        self.set_xy(self._x, self._y)
        self.set_font('Times', 'B', F_SEC)
        self.multi_cell(CW, 5, txt, align='C')
        self._cy[self._c] = self.get_y()
        self._adv(1.5)

    def _p(self, txt, bold=False):
        self._ensure(LH_B * 2)
        self.set_font('Times', 'B' if bold else '', F_BODY)
        self.set_xy(self._x, self._y)
        self.multi_cell(CW, LH_B, txt, align='J')
        self._cy[self._c] = self.get_y()

    def _li(self, txt):
        self._ensure(LH_B * 2)
        indent = 3
        sym = '  -  '
        self.set_font('Times', '', F_BODY)
        self.set_xy(self._x + indent, self._y)
        sw = self.get_string_width(sym)
        self.cell(sw, LH_B, sym, new_x='END', new_y='LAST')
        self.multi_cell(CW - indent - sw, LH_B, txt, align='J')
        self._cy[self._c] = self.get_y()

    def _note(self, txt):
        self._ensure(LH_B)
        self.set_font('Times', 'I', F_NOTE)
        self.set_xy(self._x, self._y)
        self.multi_cell(CW, 3.4, txt, align='J')
        self._cy[self._c] = self.get_y()

    # ── table ─────────────────────────────────────────────────────────────────
    def _tbl(self, caption, headers, rows, ws, note=''):
        rh = LH_T
        est = rh * (len(rows) + 1) + 14 + (5 if note else 0)
        self._ensure(est)
        self._gap(2)

        self.set_font('Times', 'B', F_NOTE + 0.5)
        self.set_xy(self._x, self._y)
        self.multi_cell(CW, 3.5, caption, align='C')
        self._cy[self._c] = self.get_y()
        self._gap(0.5)

        def _fit(s, w):
            """Truncate string to fit within w mm (leaving 1.5mm padding)."""
            avail = w - 1.5
            if self.get_string_width(s) <= avail:
                return s
            while len(s) > 1 and self.get_string_width(s + '.') > avail:
                s = s[:-1]
            return s.rstrip() + '.'

        def _row(cells, bold=False, shade=False):
            x0, y0 = self._x, self._y
            self.set_font('Times', 'B' if bold else '', F_TBL)
            if shade:
                self.set_fill_color(220, 220, 220)
            elif bold:
                self.set_fill_color(200, 200, 200)
            for txt, w in zip(cells, ws):
                self.set_xy(x0, y0)
                fill = bold or shade
                self.rect(x0, y0, w, rh, 'F' if fill else '')
                self.rect(x0, y0, w, rh)
                s = _fit(str(txt), w)
                self.set_xy(x0 + 0.5, y0 + 0.4)
                self.cell(w - 1, rh - 0.5, s, align='C' if bold else 'L')
                x0 += w
            self._cy[self._c] = y0 + rh

        _row(headers, bold=True)
        for i, row in enumerate(rows):
            _row(row, shade=(i % 2 == 1))

        if note:
            self._gap(0.5)
            self._note(note)
        self._gap(3)

    def _refs(self, items):
        self.set_font('Times', '', F_NOTE)
        for item in items:
            self._ensure(LH_B)
            self.set_xy(self._x, self._y)
            self.multi_cell(CW, 3.4, item, align='J')
            self._cy[self._c] = self.get_y()
            self._gap(0.5)


# ═════════════════════════════════════════════════════════════════════════════
def build():
    pdf = Doc()
    pdf.add_page()

    # ── TÍTULO ───────────────────────────────────────────────────────────────
    fw = 210 - LM - RM
    pdf.set_font('Times', 'B', F_TITLE)
    pdf.set_xy(LM, TM)
    pdf.multi_cell(fw, 8,
        'Triagem Explicada de Incidentes de Rede com LLM Especializado e RAG Local',
        align='C')
    pdf.ln(2)
    pdf.set_font('Times', '', 9)
    pdf.multi_cell(fw, 4.5,
        'Experiencia Criativa: Projeto Transformador I  -  Bacharelado em Ciencia da Computacao - PUCPR',
        align='C')
    pdf.multi_cell(fw, 4.5, 'Turma 7B - Grupo 3', align='C')
    pdf.ln(2)
    pdf.set_font('Times', 'B', F_AUTH)
    pdf.multi_cell(fw, 5,
        'Igor Mamus dos Santos, Felipe Ribas Boaretto, Leonardo dos Santos Marques, Joao Vitor Manfrim',
        align='C')
    pdf.set_font('Times', 'I', 9)
    pdf.multi_cell(fw, 4.5,
        '{igor.mamus, felipe.boaretto, leonardo.marques, joao.manfrim}@pucpr.edu.br',
        align='C')
    pdf.ln(3)
    hy = pdf.get_y()
    pdf.line(LM, hy, 210 - RM, hy)
    sy = hy + 4
    pdf._cy = [sy, sy]

    # ══ PÁGINA 1 ══════════════════════════════════════════════════════════════
    # SEcÃO I - coluna esquerda
    pdf._sh('I. DESCRICAO DO PROJETO')
    pdf._p('A triagem de incidentes de seguranca em redes de computadores e uma '
           'atividade critica para a protecao de infraestruturas de TI [1]. Sistemas '
           'de deteccao de intrusao (IDS) geram grandes volumes de alertas diariamente '
           'e uma parcela significativa sao falsos positivos ou carecem de contexto '
           'suficiente para tomada de decisao rapida [1],[3].')
    pdf._gap(1.5)
    pdf._p('A literatura recente demonstra avancos no uso de Large Language Models '
           '(LLMs) para ciberseguranca, incluindo analise de logs e classificacao de '
           'ameacas [7],[9]. Contudo, a maioria das solucoes depende de APIs '
           'proprietarias em nuvem, levantando preocupacoes de privacidade, custo e '
           'dependencia de fornecedores externos [8].')
    pdf._gap(1.5)
    pdf._p('Este projeto constroi um sistema 100% local de triagem explicada de '
           'incidentes de rede, combinando: (i) LLM especializado em ciberseguranca; '
           '(ii) Retrieval-Augmented Generation (RAG) [6] com base de conhecimento '
           'curada; e (iii) pre-classificador de Machine Learning classico. O sistema '
           'opera sem enviar dados a servicos externos.')
    pdf._gap(1.5)
    pdf._p('Pergunta de pesquisa: Um LLM especializado, operando localmente com RAG, '
           'pode produzir triagens de incidentes de rede com classificacoes e '
           'explicacoes corretas, contextualizadas e uteis para analistas?')
    pdf._gap(1.5)
    pdf._p('Objetivos especificos:', bold=True)
    pdf._li('Implementar pipeline de pre-processamento para CIC-IDS2017 [3] e UNSW-NB15 [4] com 15 categorias unificadas.')
    pdf._li('Construir base RAG local com 4.435 documentos indexados em ChromaDB [12] (MITRE ATT&CK, Sigma Rules e documentos canonicos de classes IDS).')
    pdf._li('Integrar Foundation-Sec-8B [7] Q8_0 via Ollama [11] com prompts chain-of-thought e saida JSON estruturada.')
    pdf._li('Implementar pre-classificador Random Forest binario com acuracia >=99% para filtragem de trafego benigno.')
    pdf._li('Conduzir ablation study de 6 configuracoes para medir contribuicao isolada de cada componente.')

    # SEcÃO II - coluna direita
    pdf._rc()
    pdf._sh('II. MATERIAIS E METODOS')
    pdf._p('O CIC-IDS2017 [3] contem 2,83 milhoes de registros com 80 features '
           'cobrindo DDoS, DoS, Brute Force, Port Scan, Botnet, Web Attacks e '
           'Infiltration. O UNSW-NB15 [4] contem 2,54 milhoes de registros com '
           '49 features e 9 tipos de ataque (Exploits, Fuzzers, Backdoor, Shellcode, '
           'Worms etc.). Juntos totalizam 5,37 milhoes de registros e 15 categorias '
           'unificadas, com 80-87% de trafego benigno.')
    pdf._gap(1.5)
    pdf._p('A base RAG e composta por tres fontes: 691 tecnicas MITRE ATT&CK [2] '
           '(STIX 2.1), 3.728 regras Sigma [5] de deteccao, e 16 documentos '
           'canonicos desenvolvidos neste projeto descrevendo caracteristicas de '
           'fluxo de rede para cada classe IDS. Este ultimo componente e o '
           'diferencial mais impactante, pois MITRE e Sigma descrevem '
           'comportamento em logs de sistema, nao em features de rede.')
    pdf._gap(1.5)
    pdf._p('O Foundation-Sec-8B [7] (Llama 3 fine-tuned em ciberseguranca, '
           'quantizacao Q8_0, ~8,5 GB) e inferido via Ollama [11] usando '
           '/api/chat com JSON Schema estruturado para saida garantida. '
           'Embeddings: all-MiniLM-L6-v2 [10] (384 dims). Re-ranking: '
           'cross-encoder ms-marco-MiniLM-L-6-v2 [14] (top-20 -> top-5). '
           'Pre-classificador Random Forest [13] binario treinado com '
           '200.000 registros por dataset.')
    pdf._gap(1.5)
    pdf._p('Stack: Python 3.13, pandas 2.x, ChromaDB 0.4+, sentence-transformers '
           '5.x, scikit-learn, Ollama 0.12.3. Hardware: RTX 5060 8 GB '
           '(22/33 camadas do modelo na GPU), 64 GB RAM. Latencia: ~22s/registro.')
    pdf._gap(1.5)

    # Tabela I - Materiais (coluna direita, mas fica larga demais, usamos a coluna atual)
    ws_mat = [22, 37, 28.5]   # soma = 87.5mm
    hdrs_mat = ['Categoria', 'Descricao', 'Papel no Projeto']
    rows_mat = [
        ['Datasets', 'CIC-IDS2017 [3], UNSW-NB15 [4]', 'Registros rotulados (5,37M)'],
        ['Bases RAG', 'MITRE ATT&CK [2], Sigma [5], IDS classes', 'Contexto para triagem'],
        ['Modelo LLM', 'Foundation-Sec-8B Q8_0 [7]', 'Geracao de triagens'],
        ['Embeddings', 'all-MiniLM-L6-v2 [10]', 'Vetorizacao RAG'],
        ['Re-ranking', 'ms-marco-MiniLM-L-6-v2 [14]', 'Cross-encoder top20->top5'],
        ['Pre-classif.', 'Random Forest [13] binario', 'Filtro Benign (>=99% acc)'],
        ['Inferencia', 'Ollama 0.12.3 [11], ChromaDB [12]', 'Servidor LLM + vectorstore'],
        ['Dev Stack', 'Python 3.13, pandas 2.x, scikit-learn', 'Pre-processamento e ML'],
        ['Hardware', 'RTX 5060 8GB, 64GB RAM', 'Inferencia local (~22s/reg)'],
    ]
    pdf._tbl('Tabela I - Resumo de Materiais e Metodos', hdrs_mat, rows_mat, ws_mat)

    # ══ PÁGINA 2 ══════════════════════════════════════════════════════════════
    pdf._np()

    # SEcÃO III - coluna esquerda
    pdf._sh('III. ARQUITETURA E IMPLEMENTACAO')
    pdf._p('O sistema e dividido em tres etapas encadeadas:', bold=True)
    pdf._gap(1)
    pdf._p('Etapa 1 - Pre-processamento:', bold=True)
    pdf._p('Carregamento de 8 CSVs CIC e 4 arquivos UNSW; remocao de colunas '
           'identificadoras (IPs, timestamps - prevencao de data leakage); '
           'substituicao de infinitos e NaN por mediana; clip de valores negativos; '
           'mapeamento de rotulos para 15 categorias unificadas; remocao de 8 '
           'colunas constantes e 25+ com correlacao >0,95; normalizacao MinMax '
           'no dataset unificado (parquets individuais preservam valores brutos '
           'para uso na triagem LLM).')
    pdf._gap(1.5)
    pdf._p('Etapa 2 - Base RAG:', bold=True)
    pdf._p('4.435 documentos indexados em ChromaDB com similaridade coseno. '
           'Recuperacao em dois estagios: busca densa (top-20 candidatos) '
           'seguida de re-ranking com cross-encoder (top-5 finais). Filtro '
           'de qualidade: contexto descartado se distancia densa >0,55 '
           '(calibrado empiricamente). Overhead do cross-encoder: ~2s/query.')
    pdf._gap(1.5)
    pdf._p('Etapa 3 - Triagem com LLM:', bold=True)
    pdf._p('(a) text_converter v2: features brutas convertidas em descricao '
           'textual com categorias discriminativas: FLOOD/ALTA/MODERADA/BAIXA '
           'para taxa de pacotes; UNIDIRECIONAL/SIMETRICO/EXFILTRACAO para '
           'forma do fluxo; assinaturas heuristicas automaticas para padroes '
           'conhecidos. Sanity check para micro-fluxos evita classificacao '
           'incorreta como FLOOD (Bug #21 corrigido).')
    pdf._gap(1)
    pdf._p('(b) Prompts v2 com chain-of-thought: protocolo de raciocinio em '
           '5 passos + 8 exemplos canonicos (DDoS, Reconnaissance, Benign, '
           'Brute Force, DoS, Exploits, Fuzzers, Backdoor). Saida JSON com '
           'attack_type (enum 15 categorias), severity, confidence, '
           'mitre_techniques, explanation e recommendations. JSON Schema '
           'forcado via grammar sampling no Ollama.')
    pdf._gap(1)
    pdf._p('(c) Random Forest pre-filtro: treinado separadamente para CIC '
           '(99,8% acc) e UNSW (99,1% acc). Benigns com confianca >=95% '
           'saltam o LLM completamente, eliminando o problema de TN=0 do '
           'modelo LLM isolado e reduzindo latencia media.')

    # SEcÃO IV - coluna direita
    pdf._rc()
    pdf._sh('IV. METODOLOGIA DE AVALIACAO')
    pdf._p('O experimento principal e um ablation study com 6 configuracoes '
           'executadas com o mesmo seed de amostragem. A unica variavel entre '
           'configuracoes e a combinacao de componentes ativos. Seeds fixos '
           'garantem conjunto de registros identico para comparacao justa.')
    pdf._gap(1.5)
    pdf._p('Amostragem estratificada: N registros por classe (N=3 nos benchmarks), '
           'garantindo representacao de todas as 15 categorias mesmo com 80-87% '
           'de registros benignos. Pre-amostra de N*50 por dataset evita '
           'carregar 5 milhoes de linhas em memoria.')
    pdf._gap(1.5)
    pdf._p('Metricas adotadas:')
    pdf._li('Acuracia Exata: attack_type predito = ground truth (com dicionario de aliases para variantes de nomenclatura).')
    pdf._li('Acuracia Binaria (metrica primaria): deteccao correta de Ameaca vs. Benigno - operacionalmente mais relevante.')
    pdf._li('Precisao: TP/(TP+FP) - dos alertados como ameaca, quantos eram reais.')
    pdf._li('Recall: TP/(TP+FN) - das ameacas reais, quantas foram detectadas.')
    pdf._li('Matriz de confusao: TP, TN, FP, FN - FN = ameaca nao detectada = critico.')
    pdf._gap(1.5)
    pdf._p('As 6 configuracoes avaliadas:')
    pdf._li('1_baseline_norag: LLM puro, sem RAG, sem RF (baseline).')
    pdf._li('2_norag_rf: LLM + Random Forest, sem RAG.')
    pdf._li('3_rag_only: LLM + RAG denso, sem rerank nem RF.')
    pdf._li('4_rag_rerank: LLM + RAG + cross-encoder rerank, sem RF.')
    pdf._li('5_rag_rerank_rf: LLM + RAG + rerank + RF (configuracao recomendada).')
    pdf._li('6_rag_rerank_rf_2stage: Config 5 + Stage 1 LLM binario (opt-in experimental).')
    pdf._gap(1.5)
    pdf._p('Seeds utilizados: 834338 (Benchmark 1, antes do fix Bug #21) e '
           '279880 (Benchmark 2, pos todos os fixes). Outputs em '
           'outputs/benchmarks/bench_<timestamp>/summary.json.')

    # ══ PÁGINA 3 - RESULTADOS ═════════════════════════════════════════════════
    pdf._np()
    pdf._sh('V. RESULTADOS EXPERIMENTAIS')

    # Benchmark 1 - coluna esquerda
    ws_b = [30, 10.5, 10.5, 10.5, 10.5, 11.5]   # soma = 84mm (deixa 3.5mm de margem)
    # Ajuste: 30+10.5+10.5+10.5+10.5+11.5 = 83.5  →  distribuir 4mm extras
    ws_b = [32, 11, 11, 11, 11, 11.5]   # 87.5mm
    hdrs_b = ['Configuracao', 'Exata', 'Binaria', 'Precis.', 'Recall', 'Tp/reg']
    rows_b1 = [
        ['1_baseline_norag',    '10,0%',  '90,0%',  '90,0%', '100%', '25,1s'],
        ['2_rag_only',          '10,0%',  '90,0%',  '90,0%', '100%', '24,6s'],
        ['3_rag_rerank',        '20,0%',  '90,0%',  '90,0%', '100%', '26,1s'],
        ['4_rag_rerank_2stage', '10,0%',  '60,0%',  '85,7%', '66,7%','22,2s'],
        ['5_rag_rerank_rf *',   '30,0%',  '100,0%', '100%',  '100%', '23,2s'],
        ['6_full_stack',        '20,0%',  '70,0%',  '100%',  '66,7%','19,2s'],
    ]
    pdf._tbl(
        'Tabela II - Benchmark 1 (seed 834338, N=3/classe, 10 registros)',
        hdrs_b, rows_b1, ws_b,
        note='* Melhor resultado. Bug #21 (Sload UNSW) ainda ativo neste benchmark. '
             'Config 5: TP=9 TN=1 FP=0 FN=0. Config 4 e 6: Stage 1 LLM prejudicou recall.'
    )

    # Benchmark 2 - ainda coluna esquerda ou direita (depende do espaco)
    rows_b2 = [
        ['1_baseline_norag',   '0,0%',   '85,7%',  '85,7%', '100%',  '32,1s'],
        ['2_norag_rf',         '14,3%',  '100,0%', '100%',  '100%',  '23,8s'],
        ['3_rag_only',         '14,3%',  '85,7%',  '85,7%', '100%',  '27,1s'],
        ['4_rag_rerank',       '28,6%',  '85,7%',  '85,7%', '100%',  '29,6s'],
        ['5_rag_rerank_rf *',  '42,9%',  '100,0%', '100%',  '100%',  '24,9s'],
        ['6_rf_2stage',        '14,3%',  '28,6%',  '100%',  '16,7%', ' 7,5s'],
    ]
    pdf._tbl(
        'Tabela III - Benchmark 2 (seed 279880, N=3/classe, 7 reg - pos fixes)',
        hdrs_b, rows_b2, ws_b,
        note='* Melhor resultado do projeto: 42,9% exata, 100% binaria. '
             'Config 6 catastrofica: Stage 1 LLM classificou 5/6 ameacas como Benign (FN=5).'
    )

    # Analise registro a registro - coluna direita
    pdf._rc()
    pdf._sh('V.A - Predicoes por Registro (Benchmark 2, seed 279880)')
    ws_pr = [21, 13, 13, 13, 13.5, 14]
    hdrs_pr = ['Ground Truth', '1_base', '2_rf', '3_rag', '4_rank', '5_rf*']
    rows_pr = [
        ['Benign',          'x Shell', 'Ben[RF]', 'x BF',   'x Recon', 'Ben[RF]'],
        ['DDoS',            'x Recon', 'x Recon', 'x Recon','x Recon', 'x Recon'],
        ['DoS',             'x Recon', 'x Recon', 'x Recon','v DoS',   'v DoS'],
        ['Exploits',        'x Shell', 'x Shell', 'x Recon','x Recon', 'x Recon'],
        ['Fuzzers',         'x Recon', 'x Recon', 'x Recon','x Recon', 'x Recon'],
        ['Generic',         'x Recon', 'x Recon', 'x Recon','x Recon', 'x Recon'],
        ['Reconnaissance',  'x Shell', 'x Shell', 'v Recon','v Recon', 'v Recon'],
    ]
    pdf._tbl(
        'Tabela IV - Predicao por registro (v=acerto, x=erro, [RF]=RF skip LLM)',
        hdrs_pr, rows_pr, ws_pr,
        note='DDoS->Recon e limite intrinsseco do dado: fluxos CIC individuais '
             'de DDoS e Reconnaissance sao morfologicamente identicos. '
             'Config 6 omitida (Stage 1 LLM: FN=5, binaria 28,6%).'
    )

    pdf._gap(2)
    pdf._sh('V.B - Evolucao Temporal da Melhor Config')
    ws_evo = [24, 22, 14, 14, 13.5]   # soma = 87.5mm
    hdrs_evo = ['Periodo', 'Config', 'Exata', 'Binaria', 'TN']
    rows_evo = [
        ['Mai/03 v1',       'RAG simples',    '20,0%', '90,0%', '0'],
        ['Mai/03 v2',       'rag_rerank_rf',  '30,0%', '100%',  '1'],
        ['Mai/04 v2+fixes', 'rag_rerank_rf',  '42,9%', '100%',  '1'],
    ]
    pdf._tbl(
        'Tabela V - Evolucao temporal: melhor config por periodo',
        hdrs_evo, rows_evo, ws_evo,
        note='Ganho total: +22,9pp exata, +10pp binaria, TN 0->1. '
             'Principal contribuicao: Random Forest (TN) + fix Bug #21 + prompts v2 (exata).'
    )

    # ══ PÁGINA 4 - ABLATION + DISCUSSAO ══════════════════════════════════════
    pdf._np()
    pdf._sh('VI. ANALISE ABLATIVA')

    ws_abl = [34, 14, 15, 24.5]   # soma = 87.5mm
    hdrs_abl = ['Componente adicionado', 'D Exata', 'D Binaria', 'Observacao']
    rows_abl = [
        ['RAG denso (vs baseline)',  '+0 a +14pp', '0pp',         'Instavel sem rerank'],
        ['+ Cross-encoder rerank',   '+14pp',      '0pp',         'Ganho consistente'],
        ['+ Random Forest',          '+14pp',      '+14pp',       'Unico que melhora binaria'],
        ['Stage 1 LLM (opt-in)',     '-14 a -28pp','-57 a -71pp', 'NOCIVO - desativado'],
    ]
    pdf._tbl(
        'Tabela VI - Ablation Study: contribuicao marginal de cada componente',
        hdrs_abl, rows_abl, ws_abl,
        note='Baseado em 2 benchmarks (seeds 834338 e 279880). '
             'Stack otima: RAG + cross-encoder + Random Forest. Stage 1 LLM desativado em producao.'
    )

    ws_rf = [24, 14, 14, 35.5]   # soma = 87.5mm
    hdrs_rf = ['Dataset', 'Acuracia', 'F1', 'Cobertura Benign (conf>=95%)']
    rows_rf = [
        ['CIC-IDS2017', '99,80%', '99,49%', '97,9%  (risco 0,04% de FN)'],
        ['UNSW-NB15',   '99,12%', '96,61%', '98,6%  (risco 0,04% de FN)'],
    ]
    pdf._tbl(
        'Tabela VII - Random Forest: metricas de classificacao binaria',
        hdrs_rf, rows_rf, ws_rf,
        note='Treinado separadamente para CIC e UNSW. '
             'Risco: 4 ameacas em 10.000 podem ser incorretamente filtradas como Benign.'
    )

    # SEcÃO VII - coluna direita
    pdf._rc()
    pdf._sh('VII. DISCUSSAO E LIMITACOES')
    pdf._p('Por que a acuracia exata tem teto intrinsseco:', bold=True)
    pdf._p('Um unico fluxo CIC de DDoS tem: ~3 pacotes, ACK flag, payload zero, '
           '5 segundos. Um fluxo de DoS: ~2 pacotes, ACK, zero bytes, 3 segundos. '
           'Um fluxo de Reconnaissance: 1 pacote, SYN, zero bytes, 2 segundos. '
           'Nenhum modelo pode distinguir esses tres apenas com features de fluxo '
           'individual. Os rotulos foram atribuidos pelos pesquisadores do CIC '
           'observando padroes agregados de milhares de fluxos simultaneos. '
           'Esta e uma limitacao do dado, nao do modelo.')
    pdf._gap(1.5)
    pdf._p('Limitacoes documentadas:')
    pdf._li('L1: Amostras pequenas (7-10 reg/run) sem significancia estatistica. Mitigacao: estratificacao + multiplos seeds.')
    pdf._li('L2: LLM isolado nunca prevê Benign (TN=0). Solucionado pelo Random Forest.')
    pdf._li('L3: RAG com distancias altas para UNSW (protocolos numericos abstratos). Filtro 0,55 mitiga contexto irrelevante.')
    pdf._li('L4: Stage 1 LLM binario nao confiavel com Foundation-Sec-8B - recall cai ate 16,7%. Descartado em producao.')
    pdf._li('L5: Latencia ~22s/registro - impraticavel em producao sem GPU maior. Com A100 80GB: estimados <2s.')
    pdf._li('L6: Reproducibilidade parcial - temperatura 0,2 nao e totalmente deterministica. Seeds fixos na amostragem, nao nas respostas do LLM.')
    pdf._gap(1.5)
    pdf._p('Pontos fortes para defesa:', bold=True)
    pdf._li('Stack 100% local sem dependencia de APIs externas.')
    pdf._li('5,37M registros de dois datasets publicos amplamente usados na literatura.')
    pdf._li('Ablation study rigoroso: 6 configs, seeds fixos, metrica por componente.')
    pdf._li('22 bugs documentados com causa raiz, fix aplicado e licao aprendida.')
    pdf._li('100% acuracia binaria (FN=0, FP=0) na melhor configuracao.')
    pdf._li('Teto de acuracia exata fundamentado tecnicamente e defensavel.')

    # ══ PÁGINA 5 - PROXIMAS ETAPAS + REFERENCIAS ═════════════════════════════
    pdf._np()
    pdf._sh('VIII. PROXIMAS ETAPAS (8 SEMANAS RESTANTES)')

    pdf._p('Semanas 1-2 - Bateria de avaliacao completa:', bold=True)
    pdf._li('run_benchmark.ps1 -SeedsPerConfig 3 -Sizes 3,5,8 (~5h, 36 runs).')
    pdf._li('Separacao CIC-only e UNSW-only para analise por dataset.')
    pdf._li('Dados com significancia estatistica para o manuscrito.')
    pdf._gap(1)
    pdf._p('Semanas 3-5 - Manuscrito final:', bold=True)
    pdf._li('Capitulos de Introducao, Revisao da Literatura e Metodologia.')
    pdf._li('Resultados com tabelas, matrizes de confusao e ablation study.')
    pdf._li('Discussao: limitacoes intrinssecas vs. de implementacao.')
    pdf._gap(1)
    pdf._p('Semanas 6-7 - Avaliacao qualitativa:', bold=True)
    pdf._li('Selecao de 20-30 explicacoes geradas para avaliacao por especialistas.')
    pdf._li('Criterios: coerencia tecnica, relevancia MITRE, acionabilidade.')
    pdf._gap(1)
    pdf._p('Semana 8 - Revisao final:', bold=True)
    pdf._li('Interface Streamlit (opcional, se tempo permitir).')
    pdf._li('Organizacao final do repositorio, testes adicionais, entrega.')
    pdf._gap(2)

    # Cronograma atualizado
    ws_sch = [51.5, 10, 10, 10, 6]   # soma = 87.5mm
    hdrs_sch = ['Atividade', 'Sem1-2', 'Sem3-5', 'Sem6-7', 'S8']
    rows_sch = [
        ['Etapa 1: Pre-processamento datasets',        'DONE', '-',    '-',    '-'],
        ['Etapa 2: Base RAG + ChromaDB + rerank',      'DONE', '-',    '-',    '-'],
        ['Etapa 3: LLM + RF + prompts v2',             'DONE', '-',    '-',    '-'],
        ['Bateria benchmark (multiplos seeds)',        'Em andamento', '-', '-', '-'],
        ['Manuscrito TCC',                             '-',    'X',    '-',    '-'],
        ['Avaliacao qualitativa explicacoes',          '-',    '-',    'X',    '-'],
        ['Interface Streamlit (opcional)',             '-',    '-',    'X',    'X'],
        ['Revisao final e entrega',                    '-',    '-',    '-',    'X'],
    ]
    pdf._tbl(
        'Tabela VIII - Cronograma atualizado',
        hdrs_sch, rows_sch, ws_sch,
        note='DONE = etapa concluida e funcional. Etapas 1-3 completas e testadas.'
    )

    # REFERÊNCIAS - coluna direita
    pdf._rc()
    pdf._sh('REFERENCIAS')
    refs = [
        '[1] S. Bhatt, P. K. Manadhata, L. Zomlot, "The operational role of SIEM systems," IEEE Security & Privacy, vol. 12, no. 5, pp. 35-41, 2014.',
        '[2] MITRE Corporation, "MITRE ATT&CK Framework," 2024. https://attack.mitre.org/',
        '[3] I. Sharafaldin, A. H. Lashkari, A. A. Ghorbani, "Toward generating a new intrusion detection dataset," in Proc. ICISSP, 2018, pp. 108-116.',
        '[4] N. Moustafa, J. Slay, "UNSW-NB15: A comprehensive dataset for NIDS," in Proc. MilCIS, 2015, pp. 1-6.',
        '[5] T. Florek, S. Piekarski, "SigmaHQ Rules for SIEM systems," 2024. github.com/SigmaHQ/sigma',
        '[6] P. Lewis et al., "Retrieval-Augmented Generation for NLP tasks," NeurIPS, vol. 33, 2020, pp. 9459-9474.',
        '[7] Cisco, "Foundation-Sec-8B: A cybersecurity LLM," 2024. github.com/cisco-open/foundation-sec-8b',
        '[8] N. Moustafa et al., "Network intrusion detection using deep learning," IEEE Access, vol. 7, 2019.',
        '[9] A. Vaswani et al., "Attention is all you need," NeurIPS, 2017, pp. 5998-6008.',
        '[10] N. Reimers, I. Gurevych, "Sentence-BERT: Sentence embeddings using Siamese BERT-networks," EMNLP, 2019.',
        '[11] Ollama, "Run large language models locally," 2024. https://ollama.com/',
        '[12] ChromaDB, "Chroma: The open-source embedding database," 2024. trychroma.com',
        '[13] L. Breiman, "Random forests," Machine Learning, vol. 45, pp. 5-32, 2001.',
        '[14] R. Nogueira, K. Cho, "Passage re-ranking with BERT," arXiv:1901.04085, 2019.',
    ]
    pdf._refs(refs)

    # ── salvar ────────────────────────────────────────────────────────────────
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bcc.pdf')
    pdf.output(out)
    print(f'PDF gerado: {out}')
    return out


if __name__ == '__main__':
    build()


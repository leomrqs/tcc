(.venv) PS C:\Users\leomr\Documents\GoogleDrive\Workspace\Projetos_Pessoais\TCC\tcc> .\run_benchmark.ps1       
======================================================================
BATERIA DE BENCHMARK - 36 runs no total
Configs: 6 | Tamanhos: 3,5,8 | Seeds/cfg: 2
Output: outputs\benchmarks\bench_20260504_142445
======================================================================

=== TAMANHO N=3, SEED=103730 (par 1/2) ===

[1/36] 1_baseline_norag | N=3 | seed=103730 | ETA ~?
  concluido em 221s
  exata=0.1429 binaria=0.8571 prec=0.8571 recall=1.0

[2/36] 2_norag_rf | N=3 | seed=103730 | ETA ~129 min
  concluido em 178s
  exata=0.2857 binaria=1.0 prec=1.0 recall=1.0

[3/36] 3_rag_only | N=3 | seed=103730 | ETA ~113 min
  concluido em 185s
  exata=0.1429 binaria=0.8571 prec=0.8571 recall=1.0

[4/36] 4_rag_rerank | N=3 | seed=103730 | ETA ~107 min
  concluido em 213s
  exata=0.2857 binaria=0.8571 prec=0.8571 recall=1.0

[5/36] 5_rag_rerank_rf | N=3 | seed=103730 | ETA ~106 min
  concluido em 191s
  exata=0.4286 binaria=1.0 prec=1.0 recall=1.0

[6/36] 6_rag_rerank_rf_2stage | N=3 | seed=103730 | ETA ~102 min
  concluido em 116s
  exata=0.2857 binaria=0.5714 prec=1.0 recall=0.5

=== TAMANHO N=3, SEED=493249 (par 2/2) ===

[7/36] 1_baseline_norag | N=3 | seed=493249 | ETA ~92 min
  concluido em 257s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[8/36] 2_norag_rf | N=3 | seed=493249 | ETA ~94 min
  concluido em 226s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[9/36] 3_rag_only | N=3 | seed=493249 | ETA ~93 min
  concluido em 243s
  exata=0.2222 binaria=0.8889 prec=0.8889 recall=1.0

[10/36] 4_rag_rerank | N=3 | seed=493249 | ETA ~91 min
  ERRO: pipeline retornou codigo 1 - pulando

[11/36] 5_rag_rerank_rf | N=3 | seed=493249 | ETA ~89 min
  concluido em 212s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[12/36] 6_rag_rerank_rf_2stage | N=3 | seed=493249 | ETA ~86 min
  concluido em 86s
  exata=0.1111 binaria=0.3333 prec=1.0 recall=0.25

=== TAMANHO N=5, SEED=785917 (par 1/2) ===

[13/36] 1_baseline_norag | N=5 | seed=785917 | ETA ~79 min
  concluido em 259s
  exata=0.0 binaria=0.8889 prec=0.8889 recall=1.0

[14/36] 2_norag_rf | N=5 | seed=785917 | ETA ~77 min
  concluido em 218s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[15/36] 3_rag_only | N=5 | seed=785917 | ETA ~74 min
  concluido em 215s
  exata=0.1111 binaria=0.8889 prec=0.8889 recall=1.0

[16/36] 4_rag_rerank | N=5 | seed=785917 | ETA ~71 min
  concluido em 235s
  exata=0.0 binaria=0.8889 prec=0.8889 recall=1.0

[17/36] 5_rag_rerank_rf | N=5 | seed=785917 | ETA ~68 min
  concluido em 210s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[18/36] 6_rag_rerank_rf_2stage | N=5 | seed=785917 | ETA ~65 min
  concluido em 108s
  exata=0.1111 binaria=0.4444 prec=1.0 recall=0.375

=== TAMANHO N=5, SEED=482835 (par 2/2) ===

[19/36] 1_baseline_norag | N=5 | seed=482835 | ETA ~60 min
  concluido em 234s
  exata=0.0 binaria=0.8889 prec=0.8889 recall=1.0

[20/36] 2_norag_rf | N=5 | seed=482835 | ETA ~57 min
  concluido em 203s
  exata=0.1111 binaria=1.0 prec=1.0 recall=1.0

[21/36] 3_rag_only | N=5 | seed=482835 | ETA ~54 min
  concluido em 217s
  exata=0.0 binaria=0.8889 prec=0.8889 recall=1.0

[22/36] 4_rag_rerank | N=5 | seed=482835 | ETA ~51 min
  concluido em 234s
  exata=0.1111 binaria=0.8889 prec=0.8889 recall=1.0

[23/36] 5_rag_rerank_rf | N=5 | seed=482835 | ETA ~48 min
  concluido em 216s
  exata=0.2222 binaria=1.0 prec=1.0 recall=1.0

[24/36] 6_rag_rerank_rf_2stage | N=5 | seed=482835 | ETA ~44 min
  concluido em 142s
  exata=0.1111 binaria=0.5556 prec=1.0 recall=0.5

=== TAMANHO N=8, SEED=517285 (par 1/2) ===

[25/36] 1_baseline_norag | N=8 | seed=517285 | ETA ~40 min
  concluido em 208s
  exata=0.0 binaria=0.875 prec=0.875 recall=1.0

[26/36] 2_norag_rf | N=8 | seed=517285 | ETA ~37 min
  concluido em 189s
  exata=0.125 binaria=1.0 prec=1.0 recall=1.0

[27/36] 3_rag_only | N=8 | seed=517285 | ETA ~34 min
  concluido em 197s
  exata=0.125 binaria=0.875 prec=0.875 recall=1.0

[28/36] 4_rag_rerank | N=8 | seed=517285 | ETA ~30 min
  concluido em 214s
  exata=0.0 binaria=0.875 prec=0.875 recall=1.0

[29/36] 5_rag_rerank_rf | N=8 | seed=517285 | ETA ~27 min
  concluido em 190s
  exata=0.125 binaria=1.0 prec=1.0 recall=1.0

[30/36] 6_rag_rerank_rf_2stage | N=8 | seed=517285 | ETA ~24 min
  concluido em 114s
  exata=0.125 binaria=0.5 prec=1.0 recall=0.4286

=== TAMANHO N=8, SEED=253746 (par 2/2) ===

[31/36] 1_baseline_norag | N=8 | seed=253746 | ETA ~20 min
  concluido em 272s
  exata=0.0909 binaria=0.9091 prec=0.9091 recall=1.0

[32/36] 2_norag_rf | N=8 | seed=253746 | ETA ~17 min
  concluido em 261s
  exata=0.1818 binaria=1.0 prec=1.0 recall=1.0

[33/36] 3_rag_only | N=8 | seed=253746 | ETA ~14 min
  concluido em 263s
  exata=0.0909 binaria=0.9091 prec=0.9091 recall=1.0

[34/36] 4_rag_rerank | N=8 | seed=253746 | ETA ~10 min
  concluido em 279s
  exata=0.2727 binaria=0.9091 prec=0.9091 recall=1.0

[35/36] 5_rag_rerank_rf | N=8 | seed=253746 | ETA ~7 min
  concluido em 263s
  exata=0.3636 binaria=1.0 prec=1.0 recall=1.0

[36/36] 6_rag_rerank_rf_2stage | N=8 | seed=253746 | ETA ~3 min
  concluido em 193s
  exata=0.3636 binaria=0.6364 prec=1.0 recall=0.6

======================================================================
BATERIA CONCLUIDA em 125 minutos
======================================================================

RANKING POR CONFIGURACAO (media entre todas as runs):


config                 runs avg_exact avg_binary avg_precision avg_recall avg_time
------                 ---- --------- ---------- ------------- ---------- --------
5_rag_rerank_rf           6    0.2269          1             1          1     22.9
6_rag_rerank_rf_2stage    6    0.1846     0.5068             1     0.4423     12.9
2_norag_rf                6    0.1543          1             1          1     22.7
4_rag_rerank              5    0.1339     0.8838        0.8838          1     25.6
3_rag_only                6    0.1154     0.8846        0.8846          1     23.7
1_baseline_norag          6    0.0575     0.9032        0.9032          1     26.3




Resultados detalhados: outputs\benchmarks\bench_20260504_142445\summary.json
Ranking final:         outputs\benchmarks\bench_20260504_142445\ranking.json
Log completo:          outputs\benchmarks\bench_20260504_142445\benchmark.log
(.venv) PS C:\Users\leomr\Documents\GoogleDrive\Workspace\Projetos_Pessoais\TCC\tcc> 
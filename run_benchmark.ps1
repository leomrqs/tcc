# ============================================================
# Bateria longa de avaliacao (2-3h)
# Roda multiplas configuracoes e tamanhos de amostra,
# salva resultados em outputs/triage_runs/, gera summary.json
# e tabela comparativa final.
#
# Configuracoes testadas:
#   1. baseline                  -> no-rag
#   2. rag_only                  -> rag denso, sem rerank
#   3. rag_rerank                -> rag + cross-encoder re-rank
#   4. rag_rerank_2stage         -> +two-stage
#   5. rag_rerank_rf             -> +Random Forest pre-filter
#   6. full_stack                -> RF + 2-stage + RAG rerank
#
# Tamanhos: N=3 (agil), N=5 (medio), N=8 (grande)
#
# Uso:
#   .\run_benchmark.ps1
#   .\run_benchmark.ps1 -SeedsPerConfig 3
#   .\run_benchmark.ps1 -Quick          # versao rapida para testar
# ============================================================

param(
    [int]$SeedsPerConfig = 2,
    [int[]]$Sizes = @(3, 5, 8),
    [switch]$Quick,
    [switch]$SkipBaseline
)

if ($Quick) {
    $SeedsPerConfig = 1
    $Sizes = @(3)
    Write-Host "Modo QUICK ativo: 1 seed x 3 registros x 6 configs" -ForegroundColor Yellow
}

$Sep = "=" * 70
$Python = ".\.venv\Scripts\python.exe"

# Verificacoes
if (-not (Test-Path $Python)) {
    Write-Host "ERRO: venv nao encontrado em .\.venv\Scripts\python.exe" -ForegroundColor Red
    exit 1
}

# Pasta de bateria
$BenchmarkRoot = "outputs\benchmarks\bench_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $BenchmarkRoot -Force | Out-Null
$LogFile = Join-Path $BenchmarkRoot "benchmark.log"
$SummaryFile = Join-Path $BenchmarkRoot "summary.json"
$ResultsIndex = @()

function Write-Log {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyString()][string]$Msg,
        [string]$Color = "White"
    )
    Write-Host $Msg -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $Msg
}

# Configuracoes a testar
# Nota: Stage 1 (LLM binario) foi removido das configs principais — RF eh
# muito mais confiavel. Stage 1 fica disponivel via --two-stage para experimentos.
$Configs = @(
    @{ Name = "1_baseline_norag";        ExtraArgs = @("--no-rag") },
    @{ Name = "2_norag_rf";              ExtraArgs = @("--no-rag", "--use-rf") },
    @{ Name = "3_rag_only";              ExtraArgs = @("--no-rerank") },
    @{ Name = "4_rag_rerank";            ExtraArgs = @() },
    @{ Name = "5_rag_rerank_rf";         ExtraArgs = @("--use-rf") },
    @{ Name = "6_rag_rerank_rf_2stage";  ExtraArgs = @("--use-rf", "--two-stage") }
)

if ($SkipBaseline) {
    $Configs = $Configs | Where-Object { $_.Name -ne "1_baseline" }
}

$TotalRuns = $Configs.Count * $Sizes.Count * $SeedsPerConfig
$RunIdx = 0
$T_START = Get-Date

Write-Log $Sep "Cyan"
Write-Log "BATERIA DE BENCHMARK - $TotalRuns runs no total" "Cyan"
$cfgCount = $Configs.Count
$sizesStr = ($Sizes -join ',')
Write-Log "Configs: $cfgCount | Tamanhos: $sizesStr | Seeds/cfg: $SeedsPerConfig" "Cyan"
Write-Log "Output: $BenchmarkRoot" "Cyan"
Write-Log $Sep "Cyan"

# Execucao
foreach ($size in $Sizes) {
    for ($s = 0; $s -lt $SeedsPerConfig; $s++) {
        $seed = Get-Random -Minimum 1 -Maximum 999999
        $seedNum = $s + 1
        Write-Log ""
        Write-Log "=== TAMANHO N=$size, SEED=$seed (par $seedNum/$SeedsPerConfig) ===" "Yellow"

        foreach ($cfg in $Configs) {
            $RunIdx++
            $cfgName = $cfg.Name
            $cfgArgs = $cfg.ExtraArgs

            # ETA calculation
            $elapsed = (Get-Date) - $T_START
            if ($RunIdx -gt 1) {
                $perRun = $elapsed.TotalMinutes / ($RunIdx - 1)
                $remainingMin = [int]($perRun * ($TotalRuns - $RunIdx + 1))
                $eta = "ETA ~$remainingMin min"
            } else {
                $eta = "ETA ~?"
            }

            $header = "[$RunIdx/$TotalRuns] $cfgName | N=$size | seed=$seed | $eta"
            Write-Log ""
            Write-Log $header "Green"

            $tStart = Get-Date
            $allArgs = @("--n", "$size", "--dataset", "unified", "--stratified", "--seed", "$seed") + $cfgArgs

            try {
                & $Python -m src.llm.pipeline @allArgs 2>&1 | Out-File -Append -FilePath $LogFile
                if ($LASTEXITCODE -ne 0) {
                    $errMsg = "  ERRO: pipeline retornou codigo $LASTEXITCODE - pulando"
                    Write-Log $errMsg "Red"
                    continue
                }
            } catch {
                $errMsg = "  EXCEPTION: $_"
                Write-Log $errMsg "Red"
                continue
            }

            $tElapsed = [int]((Get-Date) - $tStart).TotalSeconds
            Write-Log "  concluido em ${tElapsed}s" "Gray"

            # Localizar a ultima run criada
            $lastRun = Get-ChildItem -Path "outputs\triage_runs" -Directory |
                       Sort-Object LastWriteTime -Descending |
                       Select-Object -First 1
            if ($lastRun) {
                $resultsJson = Join-Path $lastRun.FullName "results.json"
                if (Test-Path $resultsJson) {
                    $r = Get-Content $resultsJson -Raw | ConvertFrom-Json
                    $entry = [PSCustomObject]@{
                        config = $cfgName
                        n = $size
                        seed = $seed
                        run_dir = $lastRun.Name
                        accuracy_exact = $r.accuracy_exact
                        accuracy_binary = $r.accuracy_binary
                        precision = $r.precision
                        recall = $r.recall
                        n_valid = $r.n_valid
                        avg_elapsed = $r.avg_elapsed_seconds
                        confusion = $r.confusion
                    }
                    $ResultsIndex += $entry
                    $metricsLine = "  exata=$($r.accuracy_exact) binaria=$($r.accuracy_binary) prec=$($r.precision) recall=$($r.recall)"
                    Write-Log $metricsLine "Cyan"

                    # Salva summary incremental
                    $ResultsIndex | ConvertTo-Json -Depth 5 | Out-File $SummaryFile -Encoding utf8
                }
            }
        }
    }
}

# Analise final
$totalMin = [int]((Get-Date) - $T_START).TotalMinutes
Write-Log ""
Write-Log $Sep "Cyan"
Write-Log "BATERIA CONCLUIDA em $totalMin minutos" "Cyan"
Write-Log $Sep "Cyan"

# Agregar por configuracao
Write-Log ""
Write-Log "RANKING POR CONFIGURACAO (media entre todas as runs):" "Yellow"
Write-Log ""

$grouped = $ResultsIndex | Group-Object config | ForEach-Object {
    $g = $_.Group
    [PSCustomObject]@{
        config = $_.Name
        runs = $_.Count
        avg_exact = [math]::Round(($g | Measure-Object accuracy_exact -Average).Average, 4)
        avg_binary = [math]::Round(($g | Measure-Object accuracy_binary -Average).Average, 4)
        avg_precision = [math]::Round(($g | Measure-Object precision -Average).Average, 4)
        avg_recall = [math]::Round(($g | Measure-Object recall -Average).Average, 4)
        avg_time = [math]::Round(($g | Measure-Object avg_elapsed -Average).Average, 1)
    }
} | Sort-Object avg_exact -Descending

$tableStr = $grouped | Format-Table -AutoSize | Out-String
Write-Log $tableStr

# Salvar tabela final
$FinalTable = Join-Path $BenchmarkRoot "ranking.json"
$grouped | ConvertTo-Json -Depth 5 | Out-File $FinalTable -Encoding utf8

Write-Log ""
Write-Log "Resultados detalhados: $SummaryFile" "Green"
Write-Log "Ranking final:         $FinalTable" "Green"
Write-Log "Log completo:          $LogFile" "Green"

# ============================================================
# Script de avaliação completa: RAG vs No-RAG
# Roda as duas triagens sequencialmente e exibe comparativo.
#
# Uso:
#   .\run_evaluation.ps1              # padrão: 5 por classe, estratificado
#   .\run_evaluation.ps1 -N 3         # 3 por classe
#   .\run_evaluation.ps1 -N 2 -Dataset cic  # só CIC-IDS2017
# ============================================================

param(
    [int]$N = 5,
    [string]$Dataset = "unified",
    [switch]$NoStratified,
    [int]$Seed = 0  # 0 = aleatório a cada run
)

$Strat = if ($NoStratified) { "" } else { "--stratified" }
if ($Seed -eq 0) { $Seed = Get-Random -Minimum 1 -Maximum 999999 }
$SeedArg = "--seed", $Seed
$Sep = "=" * 60

Write-Host ""
Write-Host $Sep
Write-Host "  AVALIACAO TCC: RAG vs No-RAG"
Write-Host "  Dataset: $Dataset | N por classe: $N | Estratificado: $(-not $NoStratified)"
Write-Host "  Seed (mesma amostra nos dois): $Seed"
Write-Host $Sep
Write-Host ""

# Verificar venv
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "ERRO: .venv nao encontrado. Execute na pasta tcc\ com o venv criado."
    exit 1
}

$Python = ".\.venv\Scripts\python.exe"

# ── Etapa 1: COM RAG ──────────────────────────────────────
Write-Host $Sep
Write-Host "  [1/2] TRIAGEM COM RAG"
Write-Host $Sep
Write-Host ""

$T1 = Get-Date
& $Python -m src.llm.pipeline --n $N --dataset $Dataset $Strat @SeedArg
$T1_elapsed = [int]((Get-Date) - $T1).TotalSeconds

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO na triagem com RAG. Abortando."
    exit 1
}

Write-Host ""
Write-Host "  Tempo RAG: ${T1_elapsed}s"
Write-Host ""

# ── Etapa 2: SEM RAG (baseline) ───────────────────────────
Write-Host $Sep
Write-Host "  [2/2] TRIAGEM SEM RAG (baseline)"
Write-Host $Sep
Write-Host ""

$T2 = Get-Date
& $Python -m src.llm.pipeline --n $N --dataset $Dataset $Strat --no-rag @SeedArg
$T2_elapsed = [int]((Get-Date) - $T2).TotalSeconds

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO na triagem sem RAG."
    exit 1
}

Write-Host ""
Write-Host "  Tempo No-RAG: ${T2_elapsed}s"
Write-Host ""

# ── Resumo final ──────────────────────────────────────────
$Total = $T1_elapsed + $T2_elapsed
Write-Host $Sep
Write-Host "  AVALIACAO CONCLUIDA"
Write-Host "  Tempo total: ${Total}s (~$([int]($Total/60)) min)"
Write-Host "  Resultados em: outputs\triage_runs\"
Write-Host $Sep

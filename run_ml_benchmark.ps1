# ============================================================
# Bateria do estudo comparativo de modelos ML (Benign vs Threat)
# Treina e compara todos os modelos do registry (RandomForest, ExtraTrees,
# HistGradientBoosting, XGBoost, LightGBM, DecisionTree, LogisticRegression,
# GaussianNB, KNN, MLP) + ensemble, para CIC-IDS2017 e UNSW-NB15.
#
# O progresso (passo X/Y, %, decorrido, ETA) aparece sempre no terminal.
# Saidas: outputs/ml_benchmark/bench_<timestamp>/ (json + md + graficos)
#         data/ml_models/ (modelos persistidos: rf_, best_, ensemble_)
#
# Uso:
#   .\run_ml_benchmark.ps1                 # amostra 200k/dataset, CV 5-fold
#   .\run_ml_benchmark.ps1 -Full           # datasets completos (varias horas)
#   .\run_ml_benchmark.ps1 -NoSlow         # pula KNN e MLP (mais rapido)
#   .\run_ml_benchmark.ps1 -SampleSize 500000 -CvFolds 3
# ============================================================

param(
    [int]$SampleSize = 200000,
    [int]$CvFolds = 5,
    [switch]$Full,
    [switch]$NoSlow,
    [ValidateSet("cic", "unsw", "both")]
    [string]$Datasets = "both"
)

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "ERRO: venv nao encontrado em $Python" -ForegroundColor Red
    exit 1
}

if ($Full) { $SampleSize = 0 }
$dsArgs = if ($Datasets -eq "both") { @("cic", "unsw") } else { @($Datasets) }

$Sep = "=" * 70
Write-Host ""
Write-Host $Sep -ForegroundColor Cyan
Write-Host "BATERIA DE MODELOS ML - Benign vs Threat" -ForegroundColor Cyan
Write-Host $Sep -ForegroundColor Cyan
$sizeLabel = if ($SampleSize -eq 0) { "COMPLETO (todos os registros)" } else { "$SampleSize/dataset" }
Write-Host "Amostra:   $sizeLabel"
Write-Host "Datasets:  $($dsArgs -join ', ')"
Write-Host "CV folds:  $CvFolds"
Write-Host "Modelos lentos (KNN/MLP): $(if ($NoSlow) { 'NAO' } else { 'SIM' })"
Write-Host "Inicio:    $(Get-Date -Format 'HH:mm:ss')"
Write-Host $Sep -ForegroundColor Cyan
Write-Host ""

$cmdArgs = @("-m", "src.ml.benchmark",
             "--sample-size", "$SampleSize",
             "--cv-folds", "$CvFolds",
             "--datasets") + $dsArgs
if ($NoSlow) { $cmdArgs += "--no-slow" }

$T0 = Get-Date
& $Python @cmdArgs
$code = $LASTEXITCODE
$mins = [int]((Get-Date) - $T0).TotalMinutes

Write-Host ""
Write-Host $Sep -ForegroundColor Cyan
if ($code -eq 0) {
    Write-Host "BATERIA DE MODELOS CONCLUIDA em $mins min" -ForegroundColor Green
    Write-Host "Relatorios: outputs/ml_benchmark/  |  Modelos: data/ml_models/" -ForegroundColor Green
} else {
    Write-Host "BATERIA FALHOU (codigo $code)" -ForegroundColor Red
}
Write-Host $Sep -ForegroundColor Cyan
exit $code

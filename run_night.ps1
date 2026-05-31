# ============================================================
# Orquestrador para deixar rodando a noite: encadeia tres baterias
# que cobrem os buracos da run anterior (unified estratificada):
#
#   1. CIC-IDS2017 isolado    -> isola o colapso morfologico do CIC
#   2. UNSW-NB15 isolado      -> idem para o UNSW
#   3. high-benign (natural)  -> amostragem nao estratificada, muitos
#                                benignos, para firmar a binaria/especificidade
#
# Cada fase chama run_benchmark.ps1 (que mostra progresso/ETA) e cria sua
# propria pasta em outputs/benchmarks/. Tudo entra no manifesto global
# outputs/triage_runs/runs_index.jsonl (campos dataset + stratified
# distinguem as fases na hora de agregar).
#
# Tempo estimado total: ~7h (3 seeds/fase, N pequeno -> agrega bem no pool).
# Para encurtar: baixe -Seeds ou os tamanhos. Para aprofundar: suba os tamanhos.
#
# Uso:
#   .\run_night.ps1
#   .\run_night.ps1 -Seeds 2 -CicSize 30 -UnswSize 30 -BenignSize 40
# ============================================================

param(
    [int]$Seeds = 3,
    [int]$CicSize = 20,
    [int]$UnswSize = 20,
    [int]$BenignSize = 24
)

$ErrorActionPreference = "Continue"
$Sep = "#" * 70
$T0 = Get-Date

function Phase {
    param([string]$Title, [scriptblock]$Action)
    Write-Host ""
    Write-Host $Sep -ForegroundColor Magenta
    Write-Host "# $Title" -ForegroundColor Magenta
    Write-Host "# inicio: $(Get-Date -Format 'HH:mm:ss') | decorrido total: $([int]((Get-Date)-$T0).TotalMinutes) min" -ForegroundColor Magenta
    Write-Host $Sep -ForegroundColor Magenta
    & $Action
}

Write-Host $Sep -ForegroundColor Cyan
Write-Host "# RUN NIGHT - 3 baterias encadeadas (CIC, UNSW, high-benign)" -ForegroundColor Cyan
Write-Host "# Seeds/config: $Seeds | CIC N=$CicSize | UNSW N=$UnswSize | benign N=$BenignSize" -ForegroundColor Cyan
Write-Host "# inicio: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host $Sep -ForegroundColor Cyan

Phase "FASE 1/3 - CIC-IDS2017 isolado (estratificada)" {
    & .\run_benchmark.ps1 -Dataset cic -Sizes $CicSize -SeedsPerConfig $Seeds
}

Phase "FASE 2/3 - UNSW-NB15 isolado (estratificada)" {
    & .\run_benchmark.ps1 -Dataset unsw -Sizes $UnswSize -SeedsPerConfig $Seeds
}

Phase "FASE 3/3 - high-benign (unified, amostragem natural)" {
    & .\run_benchmark.ps1 -Dataset unified -Stratified:$false -Sizes $BenignSize -SeedsPerConfig $Seeds
}

$totalMin = [int]((Get-Date) - $T0).TotalMinutes
Write-Host ""
Write-Host $Sep -ForegroundColor Green
Write-Host "# RUN NIGHT CONCLUIDO em $totalMin min" -ForegroundColor Green
Write-Host "# Resultados de todas as fases no manifesto global:" -ForegroundColor Green
Write-Host "#   outputs/triage_runs/runs_index.jsonl" -ForegroundColor Green
Write-Host "# Filtre por dataset (cic/unsw/unified) e stratified (true/false)." -ForegroundColor Green
Write-Host $Sep -ForegroundColor Green

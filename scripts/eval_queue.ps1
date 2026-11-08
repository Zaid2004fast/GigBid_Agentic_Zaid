# Runs every evaluation sequentially (avoids CPU contention on a laptop). Logs -> evals/results/*.log
$ErrorActionPreference = "Continue"
$py = Join-Path $PSScriptRoot "..\..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONPATH = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:GIGBID_PROFILE = "offline"
Set-Location $env:PYTHONPATH
$steps = @(
  @("rag_rest",   "-m evals.runners.rag_eval --variants best C4 V8 C7"),
  @("ablation",   "-m evals.runners.ablation"),
  @("decision",   "-m evals.runners.decision_eval --per-persona 200"),
  @("outcomes",   "-m evals.runners.gigsim_outcomes --variants V0 V2 C1 best --per-persona 20"),
  @("claims",     "-m evals.runners.claims_eval --per-persona 40"),
  @("abtest",     "-m evals.runners.ab_test --per-persona 40"),
  @("injection",  "-m evals.runners.injection_eval --n 30"),
  @("tools",      "-m evals.runners.tool_granularity"),
  @("multiagent", "-m evals.runners.multiagent_compare --n 8"),
  @("judge",      "-m evals.runners.judge_calibration sample --n 30"),
  @("judge2",     "-m evals.runners.judge_calibration judge"),
  @("tables",     "-m evals.runners.make_results_table")
)
foreach ($s in $steps) {
  $t = Get-Date
  "=== $($s[0]) start $t" | Out-File -Append evals/results/queue.log
  & $py -u @($s[1] -split " ") *> "evals/results/$($s[0]).log"
  "=== $($s[0]) exit $LASTEXITCODE after $([math]::Round(((Get-Date)-$t).TotalMinutes,1)) min" | Out-File -Append evals/results/queue.log
}

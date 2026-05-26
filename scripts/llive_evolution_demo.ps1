# llive 進化デモ — 進化を回して「進化の樹」を 貯蔵庫 ON/OFF 比較で見る
#
# 取得して実行 (1 行ずつ):
#   git clone -b optimize/core-2026-05-20 https://github.com/furuse-kazufumi/llive.git
#   & ".\llive\scripts\llive_evolution_demo.ps1"
# 既に clone 済なら:  & "D:\projects\llive\scripts\llive_evolution_demo.ps1"
#
# proxy fitness なので LLM 不要・各数秒。$PSScriptRoot 基準で repo 位置に依存しない。

$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

Write-Host "[ON] 貯蔵庫あり 進化中..." -ForegroundColor Cyan
py -3.11 scripts\run_persona_evolution_long.py --fitness rich-proxy --selection lldarwin --novelty --lineage-reservoir --generations 60 --population 24 --out out\demo_on --patience 999 --max-stall 0 | Out-Null
py -3.11 scripts\evolution_tree.py out\demo_on | Out-Null
py -3.11 scripts\evolution_swarm.py --reservoir --out out\demo_on\swarm.svg | Out-Null

Write-Host "[OFF] 貯蔵庫なし 進化中..." -ForegroundColor Cyan
py -3.11 scripts\run_persona_evolution_long.py --fitness rich-proxy --selection lldarwin --novelty --generations 60 --population 24 --out out\demo_off --patience 999 --max-stall 0 | Out-Null
py -3.11 scripts\evolution_tree.py out\demo_off | Out-Null

Start-Process "$repo\out\demo_on\tree.svg"
Start-Process "$repo\out\demo_off\tree.svg"
Start-Process "$repo\out\demo_on\swarm.svg"

Write-Host ""
Write-Host "完了。進化の樹を比較してください:" -ForegroundColor Green
Write-Host "  demo_on\tree.svg  = 貯蔵庫ON  -> 全8系統が生き残る (◦=復活)"
Write-Host "  demo_off\tree.svg = 貯蔵庫OFF -> 枝が枯れ系統が絶滅 (✕)"

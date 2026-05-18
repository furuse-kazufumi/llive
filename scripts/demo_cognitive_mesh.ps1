# SPDX-License-Identifier: Apache-2.0
# llive v0.8 Cognitive Mesh - 統合 demo 連続再生スクリプト (PowerShell)
#
# requirements_v0.8_cognitive_mesh.md / project_proactive_llive_demo Phase 0
# 動きで魅せる demo (project_f25_demo_polish 整合)。
#
# 実行:
#   pwsh scripts/demo_cognitive_mesh.ps1
#
# asciinema 録画:
#   asciinema rec demo-cognitive-mesh.cast
#   # 中で pwsh scripts/demo_cognitive_mesh.ps1
#   # 終了は exit
#
# 環境:
#   Python 3.11 が PATH に必要、`py -3.11` で起動できること

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Yellow
    Write-Host $Text -ForegroundColor Yellow
    Write-Host ("=" * 70) -ForegroundColor Yellow
    Write-Host ""
}

function Pause-Demo {
    param([int]$Seconds = 3)
    Start-Sleep -Seconds $Seconds
}

# 共通 env
$env:LLIVE_TZ = "Asia/Tokyo"
$env:LLIVE_QUIET_HOURS_START = "22"
$env:LLIVE_QUIET_HOURS_END = "8"
$env:LLIVE_QUIET_HOURS_ENABLED = "1"

Write-Section "llive Cognitive Mesh - Integrated Demo (連続再生)"
Write-Host "5 サブシステムが Active / Quiet で挙動を変える様子を見せます。"
Write-Host "  - Active (10:00 JST): 発話 / ingest / risk alert すべて動作"
Write-Host "  - Quiet  (02:00 JST): proactive / ingest 抑止、risk alert は例外通過"
Pause-Demo 2

# Active mode
Write-Section "Run 1: Active (10:00 JST)"
$env:LLIVE_DEMO_FORCE_TIME = "2026-05-19T10:00:00+09:00"
py -3.11 -m llive.cognitive_mesh.demo
Pause-Demo 4

# Quiet mode
Write-Section "Run 2: Quiet Hours (02:00 JST)"
$env:LLIVE_DEMO_FORCE_TIME = "2026-05-19T02:00:00+09:00"
py -3.11 -m llive.cognitive_mesh.demo
Pause-Demo 4

# 差分のまとめ
Write-Section "Summary - Active vs Quiet"
Write-Host @"
  サブシステム          | Active (10:00) | Quiet (02:00)
  ---------------------|----------------|----------------
  ProactiveLoop        | 発話            | 抑制 (Quiet Hours gate)
  IdleTrainingScheduler| ingest 実行     | no ingest (Quiet Hours gate)
  TonicRiskMonitor     | ALERT 発火      | ALERT 発火 (例外通過カテゴリ)
  TitleRecallPlanner   | recall_rate 0.75| recall_rate 0.75 (時刻独立)
  QuietHoursGuard      | in=False        | in=True
"@
Write-Host ""
Write-Host "詳細: https://furuse-kazufumi.github.io/fullsense/cognitive-mesh/" -ForegroundColor Cyan
Write-Host ""

"""llive デモパッケージ — TRIZ #1 分割 × #15 動的化 × #25 セルフサービス。

各 ``scenario_*`` モジュールは独立した 30秒〜2分の mini-demo で、共通の
``Scenario`` 基底クラスを実装する。``py -3.11 -m llive.demo`` で全シナリオを
順番に再生、``py -3.11 -m llive.demo --only 3`` で個別実行可能。

設計指針 (TRIZ + memory:project_f25_demo_polish):

* **#1 分割** — 1 シナリオ 1 機能、混ぜない
* **#15 動的化** — synthetic データを動的に生成し、毎回少し違う結果を出す
* **#25 セルフサービス** — mock backend で完結、API キー / 実 RAD コーパス不要
* **#19 周期的アクション** — 全シナリオは何度回しても安全 (tmp_path で隔離)
* **#35 パラメータ変更** — シナリオが引数を受け取り、入力を変えると結果が変わる
"""

from llive.demo.runner import (
    Scenario,
    ScenarioContext,
    list_scenarios,
    run_all,
    run_one,
)

__all__ = [
    "Scenario",
    "ScenarioContext",
    "list_scenarios",
    "run_all",
    "run_one",
]

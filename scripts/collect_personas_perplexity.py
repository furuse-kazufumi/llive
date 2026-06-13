# SPDX-License-Identifier: Apache-2.0
"""Collect Phase 2 persona prompts via Perplexity API.

ユーザー指示 (2026-05-23): persona prompt library Phase 2 — 残 85 名を
Perplexity 経由で収集. 個体数の数倍 (集団 size 30 × 3 倍 = 90 名).
個人情報 (API key 等) は env / private file 経由で動的取得し、script 本体や
出力には含めない.

Usage:
    py -3.11 scripts/collect_personas_perplexity.py [--limit N] [--dry-run]

Auth:
    Reads PERPLEXITY_API_KEY from:
      1. $PERPLEXITY_API_KEY env var (preferred)
      2. D:/api-keys.json (fallback for local dev)
    Script does NOT print, log, or commit the key.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp932 guard
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent / "src/llive/genome/persona_prompts"
ENDPOINT = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar-pro"


@dataclass(frozen=True)
class Candidate:
    id: str
    display_name: str
    fields: tuple[str, ...]
    category: str          # subdirectory name
    era: str
    nationality: str
    influenced_by: tuple[str, ...] = ()
    influences: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 85 candidates (Phase 1 sample 5 を除く全 90 名のうち)
# ---------------------------------------------------------------------------

CANDIDATES: list[Candidate] = [
    # --- Mathematician 18 (岡潔/Grothendieck 除く) ---
    Candidate("galois", "ガロア (Évariste Galois)", ("mathematics",), "mathematician", "1811-1832", "FR"),
    Candidate("ramanujan", "ラマヌジャン (Srinivasa Ramanujan)", ("mathematics",), "mathematician", "1887-1920", "IN"),
    Candidate("hilbert", "ヒルベルト (David Hilbert)", ("mathematics",), "mathematician", "1862-1943", "DE"),
    Candidate("godel", "ゲーデル (Kurt Gödel)", ("mathematics", "logic"), "mathematician", "1906-1978", "AT"),
    Candidate("turing", "アラン・チューリング (Alan Turing)", ("mathematics", "computer_science"), "mathematician", "1912-1954", "GB"),
    Candidate("von_neumann", "フォン・ノイマン (John von Neumann)", ("mathematics", "computer_science", "physics"), "mathematician", "1903-1957", "HU"),
    Candidate("noether", "エミー・ネーター (Emmy Noether)", ("mathematics",), "mathematician", "1882-1935", "DE"),
    Candidate("poincare", "ポアンカレ (Henri Poincaré)", ("mathematics", "physics"), "mathematician", "1854-1912", "FR"),
    Candidate("riemann", "リーマン (Bernhard Riemann)", ("mathematics",), "mathematician", "1826-1866", "DE"),
    Candidate("euler", "オイラー (Leonhard Euler)", ("mathematics",), "mathematician", "1707-1783", "CH"),
    Candidate("gauss", "ガウス (Carl Friedrich Gauss)", ("mathematics",), "mathematician", "1777-1855", "DE"),
    Candidate("terence_tao", "テレンス・タオ (Terence Tao)", ("mathematics",), "mathematician", "1975-", "AU"),
    Candidate("perelman", "グリゴリー・ペレルマン (Grigori Perelman)", ("mathematics",), "mathematician", "1966-", "RU"),
    Candidate("wiles", "アンドリュー・ワイルズ (Andrew Wiles)", ("mathematics",), "mathematician", "1953-", "GB"),
    Candidate("mandelbrot", "マンデルブロー (Benoît Mandelbrot)", ("mathematics",), "mathematician", "1924-2010", "PL"),
    Candidate("polya", "ポリヤ (George Pólya)", ("mathematics",), "mathematician", "1887-1985", "HU"),
    Candidate("lebesgue", "ルベーグ (Henri Lebesgue)", ("mathematics",), "mathematician", "1875-1941", "FR"),
    Candidate("takagi_teiji", "高木貞治 (Takagi Teiji)", ("mathematics",), "mathematician", "1875-1960", "JP"),

    # --- Physicist 11 (Feynman 除く) ---
    Candidate("einstein", "アインシュタイン (Albert Einstein)", ("physics",), "physicist", "1879-1955", "DE"),
    Candidate("bohr", "ニールス・ボーア (Niels Bohr)", ("physics",), "physicist", "1885-1962", "DK"),
    Candidate("heisenberg", "ハイゼンベルク (Werner Heisenberg)", ("physics",), "physicist", "1901-1976", "DE"),
    Candidate("schrodinger", "シュレディンガー (Erwin Schrödinger)", ("physics",), "physicist", "1887-1961", "AT"),
    Candidate("dirac", "ディラック (Paul Dirac)", ("physics",), "physicist", "1902-1984", "GB"),
    Candidate("landau", "ランダウ (Lev Landau)", ("physics",), "physicist", "1908-1968", "RU"),
    Candidate("pauli", "パウリ (Wolfgang Pauli)", ("physics",), "physicist", "1900-1958", "AT"),
    Candidate("fermi", "フェルミ (Enrico Fermi)", ("physics",), "physicist", "1901-1954", "IT"),
    Candidate("oppenheimer", "オッペンハイマー (J. Robert Oppenheimer)", ("physics",), "physicist", "1904-1967", "US"),
    Candidate("hawking", "ホーキング (Stephen Hawking)", ("physics", "cosmology"), "physicist", "1942-2018", "GB"),
    Candidate("penrose", "ペンローズ (Roger Penrose)", ("physics", "mathematics"), "physicist", "1931-", "GB"),

    # --- Computer Scientist 11 (Knuth 除く) ---
    Candidate("dijkstra", "ダイクストラ (Edsger W. Dijkstra)", ("computer_science",), "computer_scientist", "1930-2002", "NL"),
    Candidate("alan_kay", "アラン・ケイ (Alan Kay)", ("computer_science",), "computer_scientist", "1940-", "US"),
    Candidate("hoare", "トニー・ホーア (C.A.R. Hoare)", ("computer_science",), "computer_scientist", "1934-", "GB"),
    Candidate("mccarthy", "ジョン・マッカーシー (John McCarthy)", ("computer_science", "ai"), "computer_scientist", "1927-2011", "US"),
    Candidate("wirth", "ニクラウス・ヴィルト (Niklaus Wirth)", ("computer_science",), "computer_scientist", "1934-2024", "CH"),
    Candidate("liskov", "バーバラ・リスコフ (Barbara Liskov)", ("computer_science",), "computer_scientist", "1939-", "US"),
    Candidate("hopper", "グレース・ホッパー (Grace Hopper)", ("computer_science",), "computer_scientist", "1906-1992", "US"),
    Candidate("tarjan", "ロバート・タージャン (Robert Tarjan)", ("computer_science",), "computer_scientist", "1948-", "US"),
    Candidate("lamport", "レスリー・ランポート (Leslie Lamport)", ("computer_science", "distributed_systems"), "computer_scientist", "1941-", "US"),
    Candidate("tomlinson", "レイ・トムリンソン (Ray Tomlinson)", ("computer_science",), "computer_scientist", "1941-2016", "US"),
    Candidate("berners_lee", "ティム・バーナーズ＝リー (Tim Berners-Lee)", ("computer_science",), "computer_scientist", "1955-", "GB"),

    # --- Software Engineer 9 (金子勇 除く) ---
    Candidate("stallman", "リチャード・ストールマン (Richard Stallman)", ("software",), "software_engineer", "1953-", "US"),
    Candidate("torvalds", "リーナス・トーバルズ (Linus Torvalds)", ("software", "operating_systems"), "software_engineer", "1969-", "FI"),
    Candidate("carmack", "ジョン・カーマック (John Carmack)", ("software", "graphics"), "software_engineer", "1970-", "US"),
    Candidate("ritchie", "デニス・リッチー (Dennis Ritchie)", ("software", "programming_languages"), "software_engineer", "1941-2011", "US"),
    Candidate("ken_thompson", "ケン・トンプソン (Ken Thompson)", ("software", "operating_systems"), "software_engineer", "1943-", "US"),
    Candidate("rob_pike", "ロブ・パイク (Rob Pike)", ("software", "programming_languages"), "software_engineer", "1956-", "AU"),
    Candidate("cutler", "デイブ・カトラー (Dave Cutler)", ("software", "operating_systems"), "software_engineer", "1942-", "US"),
    Candidate("bill_joy", "ビル・ジョイ (Bill Joy)", ("software",), "software_engineer", "1954-", "US"),
    Candidate("gabriel_richard", "リチャード・ガブリエル (Richard P. Gabriel)", ("software", "programming_languages"), "software_engineer", "1949-", "US"),

    # --- AI / ML Researcher 10 ---
    Candidate("minsky", "マービン・ミンスキー (Marvin Minsky)", ("ai",), "ai_ml_researcher", "1927-2016", "US"),
    Candidate("hinton", "ジェフリー・ヒントン (Geoffrey Hinton)", ("ai", "machine_learning"), "ai_ml_researcher", "1947-", "GB"),
    Candidate("lecun", "ヤン・ルカン (Yann LeCun)", ("ai", "machine_learning"), "ai_ml_researcher", "1960-", "FR"),
    Candidate("bengio", "ヨシュア・ベンジオ (Yoshua Bengio)", ("ai", "machine_learning"), "ai_ml_researcher", "1964-", "CA"),
    Candidate("andrew_ng", "アンドリュー・ング (Andrew Ng)", ("ai", "machine_learning"), "ai_ml_researcher", "1976-", "GB"),
    Candidate("schmidhuber", "ユルゲン・シュミッドフーバー (Jürgen Schmidhuber)", ("ai", "machine_learning"), "ai_ml_researcher", "1963-", "DE"),
    Candidate("stuart_russell", "スチュアート・ラッセル (Stuart Russell)", ("ai",), "ai_ml_researcher", "1962-", "GB"),
    Candidate("norvig", "ピーター・ノービッグ (Peter Norvig)", ("ai",), "ai_ml_researcher", "1956-", "US"),
    Candidate("sutskever", "イリヤ・サツケヴァー (Ilya Sutskever)", ("ai", "deep_learning"), "ai_ml_researcher", "1986-", "IL"),
    Candidate("karpathy", "アンドレイ・カルパシー (Andrej Karpathy)", ("ai", "deep_learning"), "ai_ml_researcher", "1986-", "SK"),

    # --- Engineer 8 ---
    Candidate("tesla_nikola", "ニコラ・テスラ (Nikola Tesla)", ("engineering",), "engineer", "1856-1943", "RS"),
    Candidate("shannon", "クロード・シャノン (Claude Shannon)", ("engineering", "information_theory"), "engineer", "1916-2001", "US"),
    Candidate("wiener", "ノーバート・ウィーナー (Norbert Wiener)", ("engineering", "cybernetics"), "engineer", "1894-1964", "US"),
    Candidate("fuller_buckminster", "バックミンスター・フラー (Buckminster Fuller)", ("engineering", "design"), "engineer", "1895-1983", "US"),
    Candidate("jobs", "スティーブ・ジョブズ (Steve Jobs)", ("design", "product"), "engineer", "1955-2011", "US"),
    Candidate("wozniak", "スティーブ・ウォズニアック (Steve Wozniak)", ("engineering",), "engineer", "1950-", "US"),
    Candidate("honda_kotaro", "本多光太郎 (Honda Kotaro)", ("engineering", "metallurgy"), "engineer", "1870-1954", "JP"),
    Candidate("toyoda_sakichi", "豊田佐吉 (Toyoda Sakichi)", ("engineering",), "engineer", "1867-1930", "JP"),

    # --- Chemist 4 ---
    Candidate("pauling", "ライナス・ポーリング (Linus Pauling)", ("chemistry",), "chemist", "1901-1994", "US"),
    Candidate("marie_curie", "マリー・キュリー (Marie Curie)", ("chemistry", "physics"), "chemist", "1867-1934", "PL"),
    Candidate("franklin_rosalind", "ロザリンド・フランクリン (Rosalind Franklin)", ("chemistry", "biology"), "chemist", "1920-1958", "GB"),
    Candidate("mendeleev", "メンデレーエフ (Dmitri Mendeleev)", ("chemistry",), "chemist", "1834-1907", "RU"),

    # --- Biologist 4 ---
    Candidate("darwin", "チャールズ・ダーウィン (Charles Darwin)", ("biology",), "biologist", "1809-1882", "GB"),
    Candidate("crick", "フランシス・クリック (Francis Crick)", ("biology",), "biologist", "1916-2004", "GB"),
    Candidate("watson_james", "ジェームズ・ワトソン (James Watson)", ("biology",), "biologist", "1928-", "US"),
    Candidate("yamanaka_shinya", "山中伸弥 (Yamanaka Shinya)", ("biology",), "biologist", "1962-", "JP"),

    # --- Philosopher 3 ---
    Candidate("wittgenstein", "ヴィトゲンシュタイン (Ludwig Wittgenstein)", ("philosophy",), "philosopher", "1889-1951", "AT"),
    Candidate("popper", "カール・ポパー (Karl Popper)", ("philosophy",), "philosopher", "1902-1994", "AT"),
    Candidate("kuhn_thomas", "トマス・クーン (Thomas Kuhn)", ("philosophy",), "philosopher", "1922-1996", "US"),

    # --- Cognitive scientist 4 ---
    Candidate("piaget", "ジャン・ピアジェ (Jean Piaget)", ("psychology", "cognition"), "cognitive_scientist", "1896-1980", "CH"),
    Candidate("simon_herbert", "ハーバート・サイモン (Herbert A. Simon)", ("cognition", "ai", "economics"), "cognitive_scientist", "1916-2001", "US"),
    Candidate("kahneman", "ダニエル・カーネマン (Daniel Kahneman)", ("psychology", "economics"), "cognitive_scientist", "1934-2024", "IL"),
    Candidate("chomsky", "ノーム・チョムスキー (Noam Chomsky)", ("linguistics", "cognition"), "cognitive_scientist", "1928-", "US"),

    # --- Economist 3 ---
    Candidate("minsky_hyman", "ハイマン・ミンスキー (Hyman Minsky)", ("economics",), "economist", "1919-1996", "US"),
    Candidate("taleb", "ナシム・タレブ (Nassim Nicholas Taleb)", ("economics", "philosophy"), "economist", "1960-", "LB"),
    Candidate("schumpeter", "ヨーゼフ・シュンペーター (Joseph Schumpeter)", ("economics",), "economist", "1883-1950", "AT"),
]


# ---------------------------------------------------------------------------
# Perplexity API
# ---------------------------------------------------------------------------


def _load_api_key() -> str:
    """Return API key from env var or local api-keys.json (never logged)."""
    key = os.environ.get("PERPLEXITY_API_KEY")
    if key:
        return key
    fallback = Path("D:/api-keys.json")
    if fallback.exists():
        try:
            data = json.loads(fallback.read_text(encoding="utf-8"))
            k = data.get("PERPLEXITY_API_KEY")
            if k:
                return k
        except (OSError, json.JSONDecodeError):
            pass
    raise SystemExit("PERPLEXITY_API_KEY not set in env or D:/api-keys.json")


PROMPT_TEMPLATE = """You are creating a persona prompt for an LLM library that lets agents adopt the thinking style of historical researchers and engineers.

Subject: {display_name} ({era}, {nationality}, fields: {fields_str})

Output a structured profile **in Japanese** using EXACTLY the following markdown sections, no preamble or trailing commentary:

## 思考スタイル

1-3 段落 (200-500 字). この人物の特徴的な思考パターンを記述. 他の研究者と何が違うか.

## 強み

LLM が取り入れると有用な認知傾向を 3-5 個の bullet (- 始まり).

## 弱み

盲点 / 偏向 / 既存研究との不整合 を 3-5 個の bullet.

## 使用 prompt

1 個の blockquote (> で始まる 1-2 行). LLM に inject する命令形 prompt 本文 100-300 字.

## 思考の例

### 例 1: <generic problem>
<persona-style answer 100-200 字>

### 例 2: <generic problem>
<persona-style answer 100-200 字>

## 禁忌

使うべきでない場面 / 相互打消しになる他 persona を 2-4 個の bullet.

## 出典

最低 3 件の primary references (書名 / 論文 / 講義). 番号付きリストで.
"""


def call_perplexity(api_key: str, candidate: Candidate, *, timeout: int = 90) -> str:
    """Call Perplexity sonar-pro and return the response markdown body."""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT_TEMPLATE.format(
                display_name=candidate.display_name,
                era=candidate.era,
                nationality=candidate.nationality,
                fields_str=" / ".join(candidate.fields),
            )},
        ],
        "max_tokens": 2000,
    }
    data = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        ENDPOINT,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as r:  # noqa: S310 — known endpoint
        resp = json.loads(r.read().decode("utf-8"))
    return resp["choices"][0]["message"]["content"]


def render_frontmatter(c: Candidate, body: str) -> str:
    """Build YAML frontmatter for the candidate. source_refs extracted from body §出典."""
    # Extract `## 出典` section bullets / numbered list
    out_match = re.search(r"## 出典\s*\n(.*?)(?:\n##|\Z)", body, re.DOTALL)
    refs: list[str] = []
    if out_match:
        for ln in out_match.group(1).splitlines():
            s = ln.strip()
            m = re.match(r"^\d+\.\s*(.+)$", s) or re.match(r"^[-*]\s*(.+)$", s)
            if m:
                refs.append(m.group(1).strip())
    if len(refs) < 2:
        refs = refs + [f"Perplexity sonar-pro auto-collected reference for {c.display_name}"] * (2 - len(refs))

    fields_yaml = "\n".join(f"  - {f}" for f in c.fields)
    refs_yaml = "\n".join(f"  - {ref}" for ref in refs[:6])
    tags_yaml = "\n".join(f"  - {t}" for t in c.fields[:3])

    return (
        f"---\n"
        f"id: {c.id}\n"
        f"display_name: {c.display_name}\n"
        f"era: {c.era}\n"
        f"fields:\n{fields_yaml}\n"
        f"nationality: {c.nationality}\n"
        f"lineage:\n"
        f"  influenced_by: []\n"
        f"  influences: []\n"
        f"license_note: paraphrase + cited (fair use, sources from Perplexity sonar-pro)\n"
        f"source_refs:\n{refs_yaml}\n"
        f"tags:\n{tags_yaml}\n"
        f"last_updated: 2026-05-23\n"
        f"sources_collected_via: perplexity\n"
        f"---\n\n"
        f"# {c.display_name}\n\n"
        f"{body.strip()}\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="Process only first N candidates")
    p.add_argument("--dry-run", action="store_true", help="Skip API calls; emit placeholder files")
    p.add_argument("--sleep", type=float, default=2.0, help="Seconds between API calls (rate limit)")
    p.add_argument("--retry", type=int, default=2, help="Retry count per candidate on failure")
    args = p.parse_args()

    api_key = ""
    if not args.dry_run:
        api_key = _load_api_key()
        print(f"[auth] PERPLEXITY_API_KEY loaded (length={len(api_key)}, NOT printed)")

    todo = CANDIDATES[: args.limit] if args.limit else CANDIDATES
    print(f"[plan] collecting {len(todo)} personas (sleep={args.sleep}s, retry={args.retry})")

    ok = 0
    skipped = 0
    failed: list[str] = []
    for i, c in enumerate(todo, 1):
        out_dir = ROOT / c.category
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{c.id}.md"
        if out_path.exists():
            print(f"[{i:3d}/{len(todo)}] SKIP existing: {c.category}/{c.id}.md")
            skipped += 1
            continue

        for attempt in range(args.retry + 1):
            try:
                if args.dry_run:
                    body = "## 思考スタイル\n(placeholder, dry-run)\n\n" \
                           "## 強み\n- (placeholder)\n\n" \
                           "## 弱み\n- (placeholder)\n\n" \
                           "## 使用 prompt\n> (placeholder)\n\n" \
                           "## 思考の例\n### 例 1: (placeholder)\n\n" \
                           "## 禁忌\n- (placeholder)\n\n" \
                           "## 出典\n1. (placeholder)\n2. (placeholder)\n"
                else:
                    body = call_perplexity(api_key, c)
                full = render_frontmatter(c, body)
                out_path.write_text(full, encoding="utf-8", newline="\n")
                print(f"[{i:3d}/{len(todo)}] OK: {c.category}/{c.id}.md (body {len(body)} chars)")
                ok += 1
                break
            except (HTTPError, URLError, KeyError, TimeoutError) as exc:
                if attempt < args.retry:
                    backoff = (attempt + 1) * 5
                    print(f"[{i:3d}/{len(todo)}] RETRY {attempt+1}/{args.retry} after {backoff}s: {type(exc).__name__}")
                    time.sleep(backoff)
                else:
                    print(f"[{i:3d}/{len(todo)}] FAIL: {c.id} — {type(exc).__name__}")
                    failed.append(c.id)
        time.sleep(args.sleep)

    print(f"\n[summary] ok={ok} skipped={skipped} failed={len(failed)} total={len(todo)}")
    if failed:
        print(f"[failed-ids] {' '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

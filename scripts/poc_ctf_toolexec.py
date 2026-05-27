# SPDX-License-Identifier: Apache-2.0
"""PoC-CTF-2 (tool-exec): モデルにコードを書かせ安全 sandbox で実行する agentic 戦略が
blind-spot タスクの coverage を上げるか (FAIL->PASS 反転) を検証する.

親ゴール: 進化型オーケストラ + RAPTOR 決定論オラクル + 無制限 test-time compute で
Claude Mythos をセキュリティ領域で超える
([[goal_surpass_mythos_evolutionary]] /
 fullsense docs/research/mythos_surpass_design_2026_05_27.md §8b/§8c)。

確定済み実機所見 (§8b/§8c)
--------------------------
単一 qwen2.5:14b は CTF マイクロバッテリ 8 問中 base64/hex/reverse/url (4 問) を解くが
**rot13 / caesar / atbash / binary (4 問) を解けない**。qwen7b / llama3.2 は url のみ
(1 問)。失敗は **真の能力盲点** で、特に **文字レベル / 算術の実行誤り**
(qwen7b caesar はシフト法は正しいが末尾算術を外す)。cross-family 脱相関は実機で
観測されず (弱モデルは盲点を共有 = 劣位包含) → 真の entanglement / coverage 天井は本物。

falsifiable 命題 (PoC-CTF-2)
----------------------------
    **モデルにコードを書かせ安全 sandbox で実行し stdout を決定論オラクルで検証する
      "tool-exec" は、同モデルの "no-tool" (直接回答) より blind-spot タスクの
      coverage を上げる (FAIL->PASS 反転)。**

上がらなければ正直にそう報告する ([[feedback_benchmark_honest_disclosure]])。
Mythos の CTF 制覇も agentic code execution による (公開記述「launches containers,
executes code」)。cipher/encoding は Python で自明に解けるため、モデルの「頭の中の
算術盲点」を「正しい実行」に変換できれば coverage 天井を突破できる、という仮説。

安全 sandbox (untrusted code として厳格に — RAPTOR 流 fail-closed)
-----------------------------------------------------------------
生成コードは untrusted。以下の多層防御で実行する:
  * ``subprocess.run([sys.executable, "-I", tmpfile])`` で **別プロセス** 実行。
    ``-I`` (isolated mode) で PYTHON* env / user site / 現在 dir の sys.path 注入を遮断。
  * **timeout=10s** (超過は kill -> FAIL)。``cwd`` = 使い捨て temp dir。
  * ``env`` = 最小 (PATH と SystemRoot/TEMP のみ; PYTHONPATH 等は継承しない)。
  * stdin を閉じる。stdout/stderr は 64KB 上限で truncate。
  * 例外 / non-zero exit は FAIL 扱いで継続。
  * **実行前の危険トークン静的チェック** (fail-closed): ``import os`` / ``subprocess``
    / ``socket`` / ``open(...,'w')`` / ``shutil`` / ``eval`` / ``exec`` / ``__import__``
    等を検出したら **実行拒否 = FAIL** + reason 記録。完全防御でなく PoC の安全弁。

評価モード
----------
- ``--mock``: LLM を呼ばず、blind-spot タスクに **正しい復号コードを返す canned
  responder** と、わざと **危険トークンを含むコード片** を 1 つ混ぜて、
  sandbox の抽出 / 実行 / 危険検出 / オラクル / 反転集計のロジックを inference ゼロで
  検証する (実機予言ではない — honest)。
- 実機 (既定): on-prem ollama (``llive.llm.backend.OllamaBackend`` 再利用)。
  measurement purity = on-prem only ([[feedback_llive_measurement_purity]])。
  実機 29-52s/call の結合制約のため real は極小 (8 問 x 1-2 モデル, temp=0)。

使い方
------
::

    # ロジック検証 (compute ゼロ)
    py -3.11 scripts/poc_ctf_toolexec.py --mock --out out/poc_ctf_toolexec

    # 極小実機 (frugal, temp=0)
    $env:PYTHONPATH='D:\\projects\\llive\\src'
    py -3.11 scripts/poc_ctf_toolexec.py --models qwen2.5:14b --out out/poc_ctf_toolexec
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# 既存ハーネスを再利用 (編集しない — additive 制約)。
# RAPTOR/CLAUDE.md: sys.path には RAPTOR_DIR 以外を足さない。llive の scripts は
# PYTHONPATH=src 経由で llive を import する運用だが、poc_ctf_coverage は同じ
# scripts/ ディレクトリにあるため、scripts/ を sys.path 先頭に入れて import する。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_ctf_coverage import (  # noqa: E402
    BATTERY,
    PERSONAS,
    CTFTask,
)


def _ensure_utf8_stdout() -> None:
    # Windows cp932 console で em-dash / 日本語を出力する CLI 規約
    # ([[feedback_cli_utf8_stdout_pattern]])。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# blind-spot タスク (§8b/§8c 確定: 単一 qwen2.5:14b が解けない 4 問)。
# 反転 (FAIL->PASS) を最も見たいタスク群。
BLIND_SPOT_TIDS: frozenset[str] = frozenset({"rot13", "caesar", "atbash", "binary"})

# ---------------------------------------------------------------------------
# tool-exec 用 persona (analyst 系: コードだけを出させる)
# ---------------------------------------------------------------------------

TOOL_PERSONA: str = (
    "You are a meticulous CTF solver who writes Python code instead of decoding "
    "in your head. You ONLY output a single Python code block. Do not explain."
)

# モデルに「コードだけ」を出させる指示テンプレート。task.prompt (元の暗号文を含む)
# を埋め込み、復号結果を print させる。
_TOOL_INSTR = (
    "Solve the following CTF challenge by WRITING PYTHON CODE that decodes it and "
    "prints ONLY the recovered flag in the exact form flag{{...}}.\n"
    "Output ONLY a single Python code block fenced with ```python ... ```. "
    "Do not decode by hand. Do not add explanation. The code must `print` the flag.\n\n"
    "Challenge:\n{challenge}"
)


def build_tool_prompt(task: CTFTask) -> str:
    """tool-exec フローのプロンプト (コードだけを要求)。"""
    return _TOOL_INSTR.format(challenge=task.prompt)


# ---------------------------------------------------------------------------
# コードブロック抽出
# ---------------------------------------------------------------------------

# ```python ... ``` を最優先、無ければ最初の ``` ... ``` フェンスを拾う。
_FENCE_PY = re.compile(r"```[ \t]*python[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_FENCE_ANY = re.compile(r"```[ \t]*[a-zA-Z0-9_-]*[ \t]*\r?\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str | None:
    """モデル出力から Python コードブロックを抽出する。

    優先順: (1) ```python フェンス -> (2) 最初の ``` フェンス。
    どちらも無ければ None (= 抽出失敗 = FAIL)。
    """
    if not text:
        return None
    m = _FENCE_PY.search(text)
    if m:
        return m.group(1).strip("\n")
    m = _FENCE_ANY.search(text)
    if m:
        return m.group(1).strip("\n")
    return None


# ---------------------------------------------------------------------------
# 危険トークン静的チェック (fail-closed の安全弁) — 過剰拒否を絞った v2
# ---------------------------------------------------------------------------
#
# 完全防御ではない (PoC の安全弁)。subprocess の isolated + timeout + temp cwd +
# 最小 env と多層で組み合わせる。検出したら実行拒否 = FAIL + reason 記録。
#
# ## network 真隔離は OS レベルが本筋 (token チェックは PoC 安全弁)
# token ブラックリストは bypass 容易 (getattr / 文字列連結 / __import__ 等) であり、
# **network/fs 漏洩の本当の隔離は OS レベル** (seccomp / namespace / firewall /
# 専用ユーザの mount+net 制限 / Windows なら Job Object + AppContainer) が本筋。
# 本 PoC の静的トークン検出は「自明な危険呼び出しを早期に弾く安全弁」であって
# sandbox 全体の依存先ではない (RAPTOR fail-closed: subprocess isolated + timeout +
# temp cwd + 最小 env + stdin 閉 + stdout cap と多層で守る)。実 deploy では
# OS レベル network 遮断 (Docker --network=none 等) に置き換える前提。
#
# ## v2 の方針 (false-positive 修正)
# §8c 実機で url タスクが退行した原因 = 旧フィルタが ``urllib`` トークンを一律拒否し、
# 無害な文字列操作 ``urllib.parse.unquote`` まで過剰拒否 (false-positive) したこと。
# v2 では「危険な API を狙い撃ち」する:
#   * ``urllib`` は一律拒否でなく ``urllib.request`` / ``urllib.error`` /
#     ``urllib.urlopen`` / ``urllib.robotparser`` (= network) のみ拒否し、
#     ``urllib.parse`` (quote/unquote = 無害な文字列操作) は **許可**。
#   * ``os`` は ``import os`` 単体で即拒否せず、``os.system`` / ``os.popen`` /
#     ``os.remove`` / ``os.exec*`` / ``os.spawn*`` 等の **危険メンバ呼び出し** に絞る。
#   * ``sys`` も単なる import は許可 (sys.stdin/stdout は無害) し、危険操作のみ拒否。
#
# 許可される benign stdlib (cipher/encoding を解くのに必要・無害):
#   urllib.parse (quote/unquote), base64, codecs, binascii, string, re, hashlib,
#   math, itertools, collections, textwrap, struct, json, functools。
# 引き続きブロック (network / fs-write / process exec / unsafe deserialization):
#   urllib.request/error/urlopen, socket, http.client, requests, subprocess,
#   os.system/os.popen/os.remove/os.exec*/os.spawn*, eval(/exec(/__import__/compile(,
#   write-mode open(), shutil, ctypes/cffi, pickle/marshal, pty/popen。

_DANGER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # --- network (狙い撃ち: urllib.parse は無害なので許可、request/urlopen のみ拒否) ---
    ("urllib.request/error/urlopen (network)",
     re.compile(r"\burllib\.(request|error|urlopen|robotparser)\b")),
    ("from urllib.request/error import (network)",
     re.compile(r"\bfrom\s+urllib\.(request|error|robotparser)\b")),
    ("urllib.request.urlopen / urlretrieve",
     re.compile(r"\b(urlopen|urlretrieve|URLopener)\s*\(")),
    ("requests (http client)", re.compile(r"\brequests\b")),
    ("http.client / httplib / urllib3",
     re.compile(r"\b(http\.client|httplib|urllib3)\b")),
    ("socket", re.compile(r"\bsocket\b")),
    ("ftplib/smtplib/telnetlib (network)",
     re.compile(r"\b(ftplib|smtplib|telnetlib|poplib|imaplib|asyncio\.open_connection)\b")),
    # --- process exec ---
    ("subprocess", re.compile(r"\bsubprocess\b")),
    ("os.system / os.popen / os.exec* / os.spawn* (process exec)",
     re.compile(r"\bos\.(system|popen|exec[lv][pe]*|spawn[lv][pe]*|startfile|fork|kill)\b")),
    ("pty/popen", re.compile(r"\b(pty\b|popen2?\b)")),
    # --- filesystem write / destructive os members ---
    ("os.remove / os.unlink / os.rmdir / os.rename (fs mutate)",
     re.compile(r"\bos\.(remove|unlink|rmdir|removedirs|rename|replace|truncate|chmod|chown|mkdir|makedirs|symlink|link)\b")),
    ("shutil", re.compile(r"\bshutil\b")),
    ("open() write/append/binary-write mode",
     re.compile(r"\bopen\s*\([^)]*['\"][rwaxb+]*[wax+][rwaxb+]*['\"]")),
    ("pathlib write (write_text/write_bytes/unlink/mkdir)",
     re.compile(r"\.(write_text|write_bytes|unlink|mkdir|rmdir|rename|replace|touch)\s*\(")),
    # --- dynamic code execution ---
    ("eval(", re.compile(r"\beval\s*\(")),
    ("exec(", re.compile(r"\bexec\s*\(")),
    ("__import__", re.compile(r"__import__")),
    ("compile(", re.compile(r"\bcompile\s*\(")),
    # --- unsafe deserialization / FFI ---
    ("ctypes/cffi", re.compile(r"\b(ctypes|cffi)\b")),
    ("pickle/marshal", re.compile(r"\b(pickle|marshal)\b")),
)

#: 明示的に許可される benign stdlib (観測/honest_notes 用; scan では「狙い撃ち」拒否
#: ルールに当たらないものはすべて許可されるため、本リストは documentation/可視化用)。
BENIGN_STDLIB_ALLOWED: tuple[str, ...] = (
    "urllib.parse (quote/unquote)", "base64", "codecs", "binascii", "string",
    "re", "hashlib", "math", "itertools", "collections", "textwrap", "struct",
    "json", "functools", "import os (members are gated, not the import)",
    "import sys (members are gated, not the import)",
)


def scan_dangerous(code: str) -> str | None:
    """危険トークンを検出したら理由文字列を返す (= 実行拒否)。無ければ None。

    v2: 過剰拒否 (false-positive) を絞った。``import os`` / ``import sys`` /
    ``import urllib.parse`` 単体は許可し、**危険な API 呼び出し** (os.system /
    urllib.request 等) のみ狙い撃ちで拒否する。完全防御ではない PoC 安全弁であり、
    network/fs の真の隔離は OS レベルが本筋 (上記コメント参照)。
    """
    for label, pat in _DANGER_RULES:
        if pat.search(code):
            return label
    return None


# ---------------------------------------------------------------------------
# 安全 sandbox 実行
# ---------------------------------------------------------------------------

_OUTPUT_CAP = 64 * 1024  # 64KB 上限


@dataclass
class ExecResult:
    """sandbox 実行の結果 (オラクル適用前)。"""

    ran: bool                     # subprocess を起動したか
    refused: bool                 # 危険検出で実行拒否したか
    refuse_reason: str | None     # 拒否理由 / 抽出失敗理由
    stdout: str                   # 64KB cap 後
    stderr: str
    returncode: int | None
    timed_out: bool


def _minimal_env() -> dict[str, str]:
    """sandbox 用の最小 env。PATH と Windows 必須変数のみ継承。"""
    keep = ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "ComSpec",
            "NUMBER_OF_PROCESSORS", "PATHEXT")
    env: dict[str, str] = {}
    for k in keep:
        v = os.environ.get(k)
        if v is not None:
            env[k] = v
    # PYTHONPATH 等は意図的に落とす (-I でも二重に保証)。
    return env


def run_in_sandbox(code: str, timeout: float = 10.0) -> ExecResult:
    """生成コードを別プロセス isolated mode で安全実行する.

    多層防御:
      1. 危険トークン静的チェック (fail-closed) -> 検出時は実行せず refused。
      2. subprocess.run([python, "-I", tmpfile]) で別プロセス + isolated。
      3. timeout (超過は kill -> timed_out)。cwd = 使い捨て temp dir。
      4. env = 最小。stdin 閉じる (= b"")。
      5. stdout/stderr を 64KB cap。
    """
    reason = scan_dangerous(code)
    if reason is not None:
        return ExecResult(ran=False, refused=True, refuse_reason=reason,
                          stdout="", stderr="", returncode=None, timed_out=False)

    # 使い捨て temp dir を cwd にし、その中にスクリプトを置く。
    with tempfile.TemporaryDirectory(prefix="ctf_sbx_") as td:
        script = Path(td) / "solve.py"
        script.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=td,
                env=_minimal_env(),
                input=b"",                 # stdin 閉じる
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                shell=False,               # shell=True 禁止
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"")[:_OUTPUT_CAP]
            err = (exc.stderr or b"")[:_OUTPUT_CAP]
            return ExecResult(
                ran=True, refused=False, refuse_reason=None,
                stdout=out.decode("utf-8", "replace"),
                stderr=err.decode("utf-8", "replace"),
                returncode=None, timed_out=True,
            )
        except Exception as exc:  # noqa: BLE001 - 堅牢性: 起動失敗も FAIL で続行
            return ExecResult(
                ran=False, refused=False,
                refuse_reason=f"exec_error:{type(exc).__name__}",
                stdout="", stderr=str(exc), returncode=None, timed_out=False,
            )

        out = proc.stdout[:_OUTPUT_CAP].decode("utf-8", "replace")
        err = proc.stderr[:_OUTPUT_CAP].decode("utf-8", "replace")
        return ExecResult(
            ran=True, refused=False, refuse_reason=None,
            stdout=out, stderr=err, returncode=proc.returncode, timed_out=False,
        )


# ---------------------------------------------------------------------------
# Responder 抽象: (model, persona, prompt) -> 出力テキスト
# ---------------------------------------------------------------------------

Responder = Callable[[str, str, str], str]  # (model, system, prompt) -> text


class RealResponder:
    """on-prem ollama backend を叩く実 responder (measurement purity)。

    poc_ctf_coverage.RealResponder と同様、cold ロード timeout 対策として
    timeout 既定 300s + ``warmup()`` を持つ。temp=0 決定論。
    """

    def __init__(self, host: str | None = None, max_tokens: int = 512,
                 timeout: float = 300.0) -> None:
        from llive.llm.backend import OllamaBackend  # 遅延 import

        self._backend = OllamaBackend(host=host, timeout=timeout)
        self._max_tokens = max_tokens
        self.calls = 0
        self._warmed: set[str] = set()

    def warmup(self, models: list[str]) -> None:
        from llive.llm.backend import GenerateRequest

        for m in models:
            if m in self._warmed:
                continue
            print(f"  [warmup] loading {m} ...", file=sys.stderr)
            try:
                self._backend.generate(
                    GenerateRequest(prompt="ok", max_tokens=1,
                                    temperature=0.0, model=m)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [warmup] {m} failed ({type(exc).__name__})",
                      file=sys.stderr)
            self._warmed.add(m)

    def __call__(self, model: str, system: str, prompt: str) -> str:
        from llive.llm.backend import GenerateRequest

        self.calls += 1
        try:
            resp = self._backend.generate(
                GenerateRequest(
                    prompt=prompt,
                    system=system,
                    max_tokens=self._max_tokens,
                    temperature=0.0,   # 決定論
                    model=model,
                )
            )
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] ollama failed ({type(exc).__name__}): {exc}",
                  file=sys.stderr)
            return ""


class MockResponder:
    """合成 responder — inference ゼロで tool-exec パイプラインを検証する.

    挙動 (mode で分岐):
      * no_tool: blind-spot は誤答 (頭の中の算術盲点を模倣)、easy/url は正答。
      * tool_exec: blind-spot に **正しい復号コード** を返す。ただし 1 タスク
        (caesar) には **危険トークン入りコード** を返し、sandbox の拒否ロジックを
        踏ませる (= honest: 反転が「危険拒否」で潰れる様も検証)。

    これは実機予言ではなく、抽出 / 実行 / 危険検出 / オラクル / 反転集計の
    ロジック健全性検証専用。
    """

    # blind-spot タスクごとの「正しい復号コード」(tool_exec で返す)。
    _CANNED_CODE: dict[str, str] = {
        "rot13": (
            "import codecs\n"
            "ct = 'synt{ebg13}'\n"
            "print(codecs.decode(ct, 'rot_13'))\n"
        ),
        "atbash": (
            "ct = 'uozt{zgyzh}'\n"
            "def atbash(s):\n"
            "    out = []\n"
            "    for c in s:\n"
            "        if 'a' <= c <= 'z':\n"
            "            out.append(chr(ord('z') - (ord(c) - ord('a'))))\n"
            "        elif 'A' <= c <= 'Z':\n"
            "            out.append(chr(ord('Z') - (ord(c) - ord('A'))))\n"
            "        else:\n"
            "            out.append(c)\n"
            "    return ''.join(out)\n"
            "print(atbash(ct))\n"
        ),
        "binary": (
            "bits = '01100110 01101100 01100001 01100111 01111011 "
            "01100010 01101001 01101110 01111101'.split()\n"
            "print(''.join(chr(int(b, 2)) for b in bits))\n"
        ),
        # caesar には **わざと危険トークン** を混ぜる (sandbox 拒否を踏ませる)。
        # 正しいシフトロジックだが import os を含むため refused = FAIL になるべき。
        "caesar": (
            "import os  # injected dangerous token for sandbox test\n"
            "ct = 'iodj{fdhvdu}'\n"
            "def shift(s, n):\n"
            "    out = []\n"
            "    for c in s:\n"
            "        if 'a' <= c <= 'z':\n"
            "            out.append(chr((ord(c) - ord('a') - n) % 26 + ord('a')))\n"
            "        else:\n"
            "            out.append(c)\n"
            "    return ''.join(out)\n"
            "print(shift(ct, 3))\n"
        ),
    }

    # easy/url タスクの「直接回答」(no_tool でも tool_exec でも正答)。
    # tool_exec ではコードブロックにくるんで返す (print する自明コード)。
    _ANSWER: dict[str, str] = {t.tid: t.answer for t in BATTERY}

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, model: str, system: str, prompt: str) -> str:
        self.calls += 1
        # prompt から tid を推定 (challenge 文に元の暗号文が含まれるため照合)。
        tid = self._infer_tid(prompt)
        is_tool = "WRITING PYTHON CODE" in prompt  # build_tool_prompt の特徴語
        if is_tool:
            return self._tool_response(tid)
        return self._no_tool_response(tid)

    def _infer_tid(self, prompt: str) -> str:
        for t in BATTERY:
            # task.prompt の特徴的な暗号文断片で照合。
            marker = t.prompt.splitlines()[-1] if t.prompt else ""
            if marker and marker in prompt:
                return t.tid
        return "unknown"

    def _no_tool_response(self, tid: str) -> str:
        # blind-spot は誤答 (頭の中の盲点)。それ以外は正答。
        if tid in BLIND_SPOT_TIDS:
            return "flag{wrong_guess}"
        return self._ANSWER.get(tid, "flag{wrong_guess}")

    def _tool_response(self, tid: str) -> str:
        if tid in self._CANNED_CODE:
            return f"```python\n{self._CANNED_CODE[tid]}```"
        # easy/url: 自明な print コードをコードブロックで返す。
        ans = self._ANSWER.get(tid, "flag{unknown}")
        return f"```python\nprint({ans!r})\n```"


# ---------------------------------------------------------------------------
# 条件評価
# ---------------------------------------------------------------------------


@dataclass
class TaskOutcome:
    tid: str
    kind: str
    is_blind_spot: bool
    passed: bool
    detail: dict = field(default_factory=dict)


def eval_no_tool(task: CTFTask, model: str, responder: Responder) -> TaskOutcome:
    """no-tool 条件: 直接回答させ、出力にオラクルを適用 (poc_ctf_coverage 流)。"""
    out = responder(model, PERSONAS["analyst"], task.prompt)
    passed = task.oracle(out)
    return TaskOutcome(
        tid=task.tid, kind=task.kind,
        is_blind_spot=task.tid in BLIND_SPOT_TIDS, passed=passed,
        detail={"raw_len": len(out), "raw_head": out[:200]},
    )


def eval_tool_exec(task: CTFTask, model: str, responder: Responder,
                   timeout: float = 10.0) -> TaskOutcome:
    """tool-exec 条件: コードを書かせ -> 抽出 -> sandbox 実行 -> stdout にオラクル。"""
    raw = responder(model, TOOL_PERSONA, build_tool_prompt(task))
    code = extract_code(raw)
    if code is None:
        return TaskOutcome(
            tid=task.tid, kind=task.kind,
            is_blind_spot=task.tid in BLIND_SPOT_TIDS, passed=False,
            detail={"phase": "extract", "reason": "no_code_block",
                    "raw_head": raw[:200]},
        )
    ex = run_in_sandbox(code, timeout=timeout)
    passed = (not ex.refused) and ex.ran and task.oracle(ex.stdout)
    detail = {
        "phase": "exec",
        "refused": ex.refused,
        "refuse_reason": ex.refuse_reason,
        "timed_out": ex.timed_out,
        "returncode": ex.returncode,
        "stdout_head": ex.stdout[:200],
        "stderr_head": ex.stderr[:200],
        "code_head": code[:200],
    }
    return TaskOutcome(
        tid=task.tid, kind=task.kind,
        is_blind_spot=task.tid in BLIND_SPOT_TIDS, passed=passed, detail=detail,
    )


def run_model(model: str, tasks: list[CTFTask], responder: Responder,
              timeout: float) -> dict:
    """1 モデルで no_tool vs tool_exec を全タスク評価し、反転を集計する。"""
    no_tool: list[TaskOutcome] = []
    tool_exec: list[TaskOutcome] = []
    for task in tasks:
        no_tool.append(eval_no_tool(task, model, responder))
        tool_exec.append(eval_tool_exec(task, model, responder, timeout=timeout))

    nt = {o.tid: o for o in no_tool}
    te = {o.tid: o for o in tool_exec}

    n = len(tasks)
    cov_no = round(sum(1 for o in no_tool if o.passed) / n, 4) if n else 0.0
    cov_te = round(sum(1 for o in tool_exec if o.passed) / n, 4) if n else 0.0

    blind = [t for t in tasks if t.tid in BLIND_SPOT_TIDS]
    nb = len(blind)
    blind_no = sum(1 for t in blind if nt[t.tid].passed)
    blind_te = sum(1 for t in blind if te[t.tid].passed)

    # 反転集計: no_tool FAIL かつ tool_exec PASS = 真の反転。
    flips: list[str] = [t.tid for t in tasks
                        if (not nt[t.tid].passed) and te[t.tid].passed]
    regressions: list[str] = [t.tid for t in tasks
                              if nt[t.tid].passed and (not te[t.tid].passed)]
    blind_flips = [tid for tid in flips if tid in BLIND_SPOT_TIDS]

    refused = [te[t.tid].tid for t in tasks if te[t.tid].detail.get("refused")]

    return {
        "model": model,
        "n_tasks": n,
        "coverage": {"no_tool": cov_no, "tool_exec": cov_te,
                     "delta(tool_exec-no_tool)": round(cov_te - cov_no, 4)},
        "blind_spot": {
            "n": nb,
            "no_tool_solved": blind_no,
            "tool_exec_solved": blind_te,
            "blind_flips(FAIL->PASS)": blind_flips,
            "n_blind_flips": len(blind_flips),
        },
        "flips(FAIL->PASS)": flips,
        "regressions(PASS->FAIL)": regressions,
        "sandbox_refused": refused,
        "n_sandbox_refused": len(refused),
        "per_task": {
            t.tid: {
                "kind": t.kind,
                "is_blind_spot": t.tid in BLIND_SPOT_TIDS,
                "no_tool": {"passed": nt[t.tid].passed, **nt[t.tid].detail},
                "tool_exec": {"passed": te[t.tid].passed, **te[t.tid].detail},
            }
            for t in tasks
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true",
                    help="inference ゼロの合成 responder でパイプライン検証")
    ap.add_argument("--models", nargs="+", default=["qwen2.5:14b"],
                    help="評価するモデル群 (実機; 主=qwen2.5:14b, 任意で 7b)")
    ap.add_argument("--max-tasks", type=int, default=None,
                    help="バッテリ先頭から使うタスク数 (frugal)")
    ap.add_argument("--host", default=None, help="ollama host (既定=env/localhost)")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="sandbox 実行 timeout 秒 (超過は FAIL)")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_ctf_toolexec"))
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    tasks = list(BATTERY)
    if args.max_tasks is not None:
        tasks = tasks[: args.max_tasks]

    responder: Responder
    if args.mock:
        responder = MockResponder()
        mode = "mock"
    else:
        responder = RealResponder(host=args.host, max_tokens=args.max_tokens)
        mode = "real"

    print(f"[poc_ctf_toolexec] mode={mode} tasks={len(tasks)} "
          f"models={args.models} sandbox_timeout={args.timeout}s")

    if not args.mock:
        responder.warmup(args.models)  # type: ignore[attr-defined]

    t0 = time.time()
    model_results = [run_model(m, tasks, responder, args.timeout)
                     for m in args.models]
    elapsed = time.time() - t0
    calls = getattr(responder, "calls", 0)

    # 集約: 全モデル横断の blind-spot 反転数。
    total_blind_flips = sum(r["blind_spot"]["n_blind_flips"] for r in model_results)
    total_refused = sum(r["n_sandbox_refused"] for r in model_results)

    out = {
        "schema": "poc_ctf_toolexec/v1",
        "proposition": (
            "PoC-CTF-2: コードを書かせ安全 sandbox で実行し stdout を決定論オラクルで "
            "検証する tool-exec は、同モデルの no-tool より blind-spot の coverage を "
            "上げる (FAIL->PASS 反転) か。"),
        "mode": mode,
        "blind_spot_tids": sorted(BLIND_SPOT_TIDS),
        "n_tasks": len(tasks),
        "task_kinds": {t.tid: t.kind for t in tasks},
        "models": model_results,
        "aggregate": {
            "total_blind_flips": total_blind_flips,
            "total_sandbox_refused": total_refused,
        },
        "sandbox": {
            "isolation": "subprocess.run([python, '-I', tmpfile]) 別プロセス + isolated",
            "timeout_seconds": args.timeout,
            "cwd": "throwaway temp dir",
            "env": "minimal (PATH + Windows essentials; no PYTHONPATH)",
            "stdin": "closed (b'')",
            "output_cap_bytes": _OUTPUT_CAP,
            "danger_check": [label for label, _ in _DANGER_RULES],
            "fail_closed": "危険トークン検出 / 抽出失敗 / 例外 / non-zero / timeout は FAIL",
        },
        "compute": {"llm_calls": calls, "elapsed_seconds": round(elapsed, 2)},
        "honest_notes": [
            "mock は canned responder (正しい復号コード + 1 つ危険トークン入り) で "
            "抽出/実行/危険検出/オラクル/反転集計のロジック検証専用。実機予言ではない。",
            "危険トークン静的チェックは完全防御でない PoC 安全弁。subprocess isolated "
            "+ timeout + temp cwd + 最小 env と多層で組み合わせる。",
            "blind_flips = no_tool が FAIL で tool_exec が PASS のタスク (真のレバー実証)。",
            "オラクルは正規化部分文字列一致。偶然一致確率は低いがゼロでない。",
            "real は計算リソース限定のため極小 (temp=0 決定論, warmup 済)。",
        ],
    }

    out_json = args.out / f"ctf_toolexec_{mode}.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    _write_summary_md(out, args.out)

    _print_summary(out)
    print(f"\n[poc_ctf_toolexec] wrote {out_json} "
          f"({elapsed:.1f}s, {calls} llm calls)")
    return 0


def _print_summary(out: dict) -> None:
    print("\n===== PoC-CTF-2 TOOL-EXEC SUMMARY =====")
    print(f"mode={out['mode']} n_tasks={out['n_tasks']} "
          f"blind_spot={out['blind_spot_tids']}")
    for r in out["models"]:
        cov = r["coverage"]
        bs = r["blind_spot"]
        print(f"\n  model={r['model']}")
        print(f"    coverage  no_tool={cov['no_tool']:.3f}  "
              f"tool_exec={cov['tool_exec']:.3f}  "
              f"delta={cov['delta(tool_exec-no_tool)']:+.3f}")
        print(f"    blind-spot solved  no_tool={bs['no_tool_solved']}/{bs['n']}  "
              f"tool_exec={bs['tool_exec_solved']}/{bs['n']}")
        print(f"    blind FAIL->PASS flips: {bs['blind_flips(FAIL->PASS)']} "
              f"(n={bs['n_blind_flips']})")
        if r["regressions(PASS->FAIL)"]:
            print(f"    regressions PASS->FAIL: {r['regressions(PASS->FAIL)']}")
        if r["sandbox_refused"]:
            print(f"    sandbox refused (danger): {r['sandbox_refused']}")
    agg = out["aggregate"]
    print(f"\n  AGGREGATE: total blind flips={agg['total_blind_flips']}  "
          f"sandbox refused={agg['total_sandbox_refused']}")


def _write_summary_md(out: dict, out_dir: Path) -> None:
    """honest 結論を SUMMARY.md に書く。"""
    lines: list[str] = []
    lines.append("# PoC-CTF-2 (tool-exec) SUMMARY\n")
    lines.append(f"- mode: **{out['mode']}**")
    lines.append(f"- proposition: {out['proposition']}")
    lines.append(f"- blind-spot tasks: `{', '.join(out['blind_spot_tids'])}`")
    lines.append(f"- compute: {out['compute']['llm_calls']} llm calls, "
                 f"{out['compute']['elapsed_seconds']}s\n")

    lines.append("## Sandbox (untrusted code, fail-closed)\n")
    sb = out["sandbox"]
    lines.append(f"- isolation: {sb['isolation']}")
    lines.append(f"- timeout: {sb['timeout_seconds']}s (超過は kill -> FAIL)")
    lines.append(f"- cwd: {sb['cwd']} / env: {sb['env']} / stdin: {sb['stdin']}")
    lines.append(f"- output cap: {sb['output_cap_bytes']} bytes")
    lines.append(f"- danger tokens (実行拒否): `{', '.join(sb['danger_check'])}`")
    lines.append(f"- fail-closed: {sb['fail_closed']}\n")

    lines.append("## Results per model\n")
    lines.append("| model | cov no_tool | cov tool_exec | delta | "
                 "blind solved no->tool | blind flips | refused |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in out["models"]:
        cov = r["coverage"]
        bs = r["blind_spot"]
        lines.append(
            f"| {r['model']} | {cov['no_tool']:.3f} | {cov['tool_exec']:.3f} | "
            f"{cov['delta(tool_exec-no_tool)']:+.3f} | "
            f"{bs['no_tool_solved']}->{bs['tool_exec_solved']} / {bs['n']} | "
            f"{', '.join(bs['blind_flips(FAIL->PASS)']) or '-'} | "
            f"{', '.join(r['sandbox_refused']) or '-'} |")

    agg = out["aggregate"]
    lines.append(f"\n**Aggregate**: total blind FAIL->PASS flips = "
                 f"{agg['total_blind_flips']}, "
                 f"sandbox refused = {agg['total_sandbox_refused']}\n")

    lines.append("## Honest notes\n")
    for note in out["honest_notes"]:
        lines.append(f"- {note}")

    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n",
                                        encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

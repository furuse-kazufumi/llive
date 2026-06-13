# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_intercode_multiturn.py 機構ハードニング.

GPU/Docker/ollama ゼロの CPU 検証 (mock_script + 純関数)。検証対象:
  * parse_action の回帰 (submit / command / fenced / prose 前置き / none)
  * no_action retry-nudge: 綴り損ない 1 ターンからの復帰 / 枯渇 / 無効化(旧挙動)
  * binary 観察 sanitize: _looks_binary / _sanitize_observation
親ゴール: [[goal_surpass_mythos_evolutionary]] Phase D-1 機構ハードニング。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_intercode_multiturn as mt  # noqa: E402
from poc_intercode_agentic import IntercodeTask  # noqa: E402


# ---------------------------------------------------------------------------
# parse_action 回帰
# ---------------------------------------------------------------------------

def test_parse_action_submit():
    act = mt.parse_action("submit picoCTF{abc_123}")
    assert act.kind == "submit"
    assert act.payload == "picoCTF{abc_123}"


def test_parse_action_submit_with_surrounding_noise():
    act = mt.parse_action("Here is the flag:\nsubmit picoCTF{hello_world}\nthanks")
    assert act.kind == "submit"
    assert act.payload == "picoCTF{hello_world}"


def test_parse_action_plain_command():
    act = mt.parse_action("ls -la")
    assert act.kind == "command"
    assert act.payload == "ls -la"


def test_parse_action_fenced_command():
    act = mt.parse_action("```bash\ncat flag\n```")
    assert act.kind == "command"
    assert act.payload == "cat flag"


def test_parse_action_skips_prose_prefix():
    # "I will run:" は末尾コロン散文 → スキップして次のコマンド行を採る。
    act = mt.parse_action("I will run:\nls -la")
    assert act.kind == "command"
    assert act.payload == "ls -la"


def test_parse_action_empty_is_none():
    assert mt.parse_action("").kind == "none"
    assert mt.parse_action("   \n  \n").kind == "none"


# ---------------------------------------------------------------------------
# parse_action 頑健化 (2026-05-28): 散文の誤コマンド化を防ぎ none に倒す
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prose", [
    # 末尾句読点なしの英語散文 (旧 _looks_like_command はこれを command 化していた)。
    "Let me look at the files first",
    "Let me think about this",
    "I will start by examining the directory",
    "The flag is probably hidden in one of these files",
    "I need to figure out what kind of encoding this is",
    # 末尾句点ありの日本語散文。
    "まず ls してみます。",
    "次に何をすべきか考えます。",
    # 疑問文。
    "What files are in this directory?",
    "どのファイルにフラグがあるだろうか？",
])
def test_parse_action_prose_only_is_none(prose):
    """散文のみ (コマンドを含まない) は none。誤ってシェル実行しない。"""
    assert mt.parse_action(prose).kind == "none"


def test_parse_action_english_prose_prefix_then_command():
    """前置き散文 + コマンド ("I will run the following:\\nls -la") → ls -la 抽出。"""
    act = mt.parse_action("I will run the following:\nls -la")
    assert act.kind == "command"
    assert act.payload == "ls -la"


def test_parse_action_prose_no_punct_then_command():
    """末尾句読点なし散文 + コマンド → コマンド行を採る (散文行をスキップ)。"""
    act = mt.parse_action("Let me look at the files first\ncat flag")
    assert act.kind == "command"
    assert act.payload == "cat flag"


def test_parse_action_japanese_prefix_then_command():
    """日本語前置き ("次のコマンドを実行します\\ncat flag") → cat flag 抽出。"""
    act = mt.parse_action("次のコマンドを実行します\ncat flag")
    assert act.kind == "command"
    assert act.payload == "cat flag"


def test_parse_action_fenced_command_with_prose_before():
    """前置き散文の後にコードフェンス → フェンス内コマンドを抽出 (回帰防止)。"""
    act = mt.parse_action("I will run the following command:\n```bash\nls -la\n```")
    assert act.kind == "command"
    assert act.payload == "ls -la"


def test_parse_action_fenced_with_leading_prose_line():
    """フェンス内に散文行 + コマンド行 → コマンド行を採る。"""
    act = mt.parse_action("```\nFirst I will list files\nls -la\n```")
    assert act.kind == "command"
    assert act.payload == "ls -la"


def test_parse_action_shell_operator_line_is_command():
    """既知コマンド先頭でなくてもシェル演算子を含む行は command。"""
    act = mt.parse_action("strings file | grep -ao 'picoCTF{[^}]*}'")
    assert act.kind == "command"
    assert "grep" in act.payload


def test_parse_action_submit_regression_with_prose():
    """散文に混じった submit は submit を優先抽出 (回帰防止)。"""
    act = mt.parse_action("I found it. submit picoCTF{found_it_123}")
    assert act.kind == "submit"
    assert act.payload == "picoCTF{found_it_123}"


def test_parse_action_bare_submit_with_flag_in_text():
    """裸 submit (フェンスなし) でも picoCTF を含めば submit に昇格 (回帰防止)。"""
    act = mt.parse_action("submit picoCTF{bare_flag_xyz}")
    assert act.kind == "submit"
    assert act.payload == "picoCTF{bare_flag_xyz}"


def test_parse_action_short_bare_token_is_command():
    """短い裸トークン (id/pwd 等) は散文でないので command として救済。"""
    assert mt.parse_action("pwd").kind == "command"
    assert mt.parse_action("ls").kind == "command"


# ---------------------------------------------------------------------------
# binary 観察 sanitize
# ---------------------------------------------------------------------------

def test_looks_binary_text_is_false():
    assert mt._looks_binary("hello world\npicoCTF{x}\n") is False
    assert mt._looks_binary("") is False


def test_looks_binary_nullbyte_is_true():
    assert mt._looks_binary("\x00\x01\x02ELF\x7f garbage") is True


def test_looks_binary_replacement_chars_is_true():
    # decode("utf-8","replace") 由来の U+FFFD だらけ = binary。
    assert mt._looks_binary(mt._REPLACEMENT_CHAR * 200) is True


def test_sanitize_observation_passthrough_text():
    text = "flag\npicoCTF{readable_text}\n"
    assert mt._sanitize_observation(text) == text


def test_sanitize_observation_suppresses_binary():
    binary = "\x00" * 50 + "junk"
    out = mt._sanitize_observation(binary)
    assert out.startswith("[non-text/binary output suppressed")
    # 誘導ツール名が含まれる (strings/file/xxd へ誘導)。
    assert "strings" in out and "xxd" in out


# ---------------------------------------------------------------------------
# no_action retry-nudge (mock end-to-end)
# ---------------------------------------------------------------------------

def _file_backed_task() -> IntercodeTask:
    """_mock_exec が認識する file-backed タスク (task_id=4, flag ファイル)。"""
    return IntercodeTask(
        task_id=4, query="find the flag", tags=["General Skills"],
        gold="picoCTF{s4n1ty_v3r1f13d_2fd6ed29}", file_backed=True,
    )


def _run(task, script, **kw):
    return mt.run_multiturn_task(
        task, max_turns=kw.pop("max_turns", 8), timeout=1.0,
        responder=None, model="mock", mock_script=script, **kw,
    )


def test_retry_nudge_recovers_from_noaction():
    """turn1 が解析不能 → 矯正 → 後続コマンドで正答 (ic22 救済シナリオ)。"""
    task = _file_backed_task()
    # 先頭が空 (no_action) → 矯正後に ls→cat→submit で解く。
    script = ["", "ls -la", "cat flag", f"submit {task.gold}"]
    tr = _run(task, script, max_self_checks=1, max_retry_nudges=2)
    assert tr.retry_nudges_used == 1
    assert tr.solved is True
    assert tr.stop_reason == "submit_correct"


def test_retry_nudge_exhausted_then_no_action():
    """矯正枠を使い切っても解析不能なら no_action で終了 (有界性)。"""
    task = _file_backed_task()
    script = ["", "", ""]  # 全ターン解析不能
    tr = _run(task, script, max_self_checks=0, max_retry_nudges=2)
    assert tr.retry_nudges_used == 2
    assert tr.solved is False
    assert tr.stop_reason == "no_action"


def test_retry_nudge_disabled_is_old_behaviour():
    """max_retry_nudges=0 で即終了 = 旧挙動 (回帰確認)。"""
    task = _file_backed_task()
    tr = _run(task, [""], max_self_checks=0, max_retry_nudges=0)
    assert tr.retry_nudges_used == 0
    assert tr.stop_reason == "no_action"


def test_retry_nudge_does_not_break_clean_solve():
    """解析可能な軌跡では nudge は発火しない (副作用なし)。"""
    task = _file_backed_task()
    script = ["ls -la", "cat flag", f"submit {task.gold}"]
    tr = _run(task, script, max_self_checks=1, max_retry_nudges=2)
    assert tr.retry_nudges_used == 0
    assert tr.solved is True


# ---------------------------------------------------------------------------
# persistent-session scaffold (opt-in; 実 Docker 未検証=環境待ち)
#
# ここでは subprocess を一切呼ばず、run_fn / exec_fn / rm_fn を差し替えて
# ライフサイクル (start→複数 exec で状態持続→close で破棄) のロジックのみを検証する。
# これは実 Docker の予言ではない ([[feedback_benchmark_honest_disclosure]])。
# ---------------------------------------------------------------------------

from poc_intercode_agentic import DockerExecResult  # noqa: E402


class _FakeContainer:
    """状態を持つ偽コンテナ — exec 間で書込が持続することを表現する (state persistence)。"""

    def __init__(self):
        self.started = False
        self.removed = False
        self.run_calls = []
        self.exec_calls = []
        self.fs = {}            # 揮発作業域 (tmpfs 相当)。exec 間で持続する。

    def run_fn(self, argv, timeout):
        # docker run -d ... が来た = 起動。
        assert argv[:3] == ["docker", "run", "-d"]
        assert "--network=none" in argv
        # 書込が要るので --read-only は付けない (persistent 設計)。
        assert "--read-only" not in argv
        assert "--memory" in argv and "--pids-limit" in argv
        self.started = True
        self.run_calls.append(argv)

    def exec_fn(self, command, timeout):
        # ごく簡単なコマンドエミュ: `echo X > f` で書込、`cat f` で読出 (状態持続を示す)。
        self.exec_calls.append(command)
        cmd = command.strip()
        if ">" in cmd and cmd.startswith("echo"):
            # echo VALUE > NAME
            value = cmd.split("echo", 1)[1].split(">")[0].strip()
            name = cmd.split(">", 1)[1].strip()
            self.fs[name] = value
            return DockerExecResult(ran=True, stdout="", stderr="", returncode=0,
                                    timed_out=False)
        if cmd.startswith("cat "):
            name = cmd.split(None, 1)[1].strip()
            return DockerExecResult(ran=True, stdout=self.fs.get(name, ""),
                                    stderr="", returncode=0, timed_out=False)
        return DockerExecResult(ran=True, stdout="", stderr="", returncode=0,
                                timed_out=False)

    def rm_fn(self, name):
        self.removed = True


def _session(task_id=4, **kw):
    fake = _FakeContainer()
    sess = mt.PersistentContainerSession(
        task_id=task_id, run_fn=fake.run_fn, exec_fn=fake.exec_fn,
        rm_fn=fake.rm_fn, **kw)
    return sess, fake


def test_session_lifecycle_start_exec_close():
    """start (1 回) → 複数 exec → close で rm。idempotent start も確認。"""
    sess, fake = _session()
    assert fake.started is False
    sess.start()
    assert fake.started is True
    sess.start()  # idempotent: 2 回目は run_fn を呼ばない。
    assert len(fake.run_calls) == 1
    sess.exec("ls -la")
    sess.exec("cat flag")
    assert fake.exec_calls == ["ls -la", "cat flag"]
    assert fake.removed is False
    sess.close()
    assert fake.removed is True
    sess.close()  # idempotent: 2 回目は no-op。
    assert fake.removed is True


def test_session_state_persists_across_exec():
    """ターンを跨いだ状態持続: turn t で書いたファイルを turn t+1 で読める。"""
    sess, fake = _session()
    sess.start()
    sess.exec("echo hello_from_turn1 > note.txt")    # turn t: 書込
    res = sess.exec("cat note.txt")                  # turn t+1: 読出 (持続)
    assert res.stdout == "hello_from_turn1"
    sess.close()


def test_session_exec_auto_starts():
    """start を明示しなくても最初の exec で自動起動する。"""
    sess, fake = _session()
    assert fake.started is False
    sess.exec("ls")
    assert fake.started is True
    sess.close()


def test_session_exec_after_close_is_fail_closed():
    """close 後の exec は実行せず session_closed エラーを返す (fail-closed)。"""
    sess, fake = _session()
    sess.start()
    sess.close()
    res = sess.exec("ls")
    assert res.ran is False
    assert res.error == "session_closed"


def test_session_context_manager_always_closes():
    """with ブロックを抜けるとき (例外でも) 必ず close (rm) する (fail-closed)。"""
    sess, fake = _session()
    with pytest.raises(RuntimeError):
        with sess:
            assert fake.started is True
            raise RuntimeError("boom inside session")
    assert fake.removed is True


def test_session_close_swallows_rm_errors():
    """rm が例外を投げても close は握り潰す (ttl sleep が二重安全弁; 例外伝播しない)。"""
    def _boom_rm(name):
        raise RuntimeError("docker rm failed")

    sess = mt.PersistentContainerSession(
        task_id=4, run_fn=lambda a, t: None, exec_fn=lambda c, t: None,
        rm_fn=_boom_rm)
    sess.start()
    sess.close()  # 例外を伝播しないこと。
    assert sess._closed is True


def test_run_multiturn_uses_injected_session():
    """run_multiturn_task に session を注入すると command が session.exec 経由になる。

    mock_script でモデル出力を与えつつ、command 実行のみ session に流す
    (mock_script is None でないと _mock_exec が優先されるため、None + 注入 exec を使う)。
    """
    task = _file_backed_task()
    fake = _FakeContainer()
    # flag ファイルを偽コンテナに仕込む (cat flag で読めるように)。
    fake.fs["flag"] = task.gold
    sess = mt.PersistentContainerSession(
        task_id=task.task_id, run_fn=fake.run_fn, exec_fn=fake.exec_fn,
        rm_fn=fake.rm_fn)

    # mock_script=None で実モデル経路を使うため responder を偽装する。
    class _FakeResponder:
        calls = 0
        _backend = None
        _max_tokens = 64

    # _real_turn を差し替えて canned なモデル出力を返す (LLM ゼロ)。
    outputs = iter(["ls -la", "cat flag", f"submit {task.gold}"])
    orig_real_turn = mt._real_turn
    mt._real_turn = lambda responder, system, prompt, model: next(outputs, "")
    try:
        tr = mt.run_multiturn_task(
            task, max_turns=8, timeout=1.0, responder=_FakeResponder(),
            model="fake", mock_script=None, max_self_checks=1,
            max_retry_nudges=0, session=sess)
    finally:
        mt._real_turn = orig_real_turn

    # command (ls/cat) が session.exec を通った。注入 session なので close は呼び出し側責任。
    assert "ls -la" in fake.exec_calls
    assert "cat flag" in fake.exec_calls
    assert tr.solved is True
    assert tr.stop_reason == "submit_correct"
    sess.close()
    assert fake.removed is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

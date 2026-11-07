"""Repo hygiene: a committed .venv symlink replaced the real virtualenv at a merge on 7 Nov. Never again."""
import subprocess


def _tracked(path: str) -> str:
    return subprocess.run(["git", "ls-files", "--", path], capture_output=True, text=True, cwd=".").stdout.strip()


def test_no_virtualenv_is_tracked():
    assert _tracked(".venv") == "" and _tracked("venv") == ""


def test_no_runtime_data_is_tracked():
    for f in ("data/kaiku.sqlite", "data/wa_sends.jsonl", "data/wa_status.jsonl", "data/call_log.jsonl",
              "data/email_log.jsonl", "data/text_declines.jsonl", "data/decide_tokens.json", "data/chat_sessions.json"):
        assert _tracked(f) == "", f

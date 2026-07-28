"""Regression tests for the claude-cli binding's argv/stdin split.

The binding shells out to the ``claude`` executable, so anything of unbounded
size must travel over stdin. Windows caps a command line at ~32k characters;
exceeding it fails the whole call with ``[WinError 206] The filename or
extension is too long``.
"""

import json

import pytest

from forgemind.llm import claude_cli

# Comfortably past the ~32767-character Windows command-line limit, matching the
# scale of a real query-path system prompt (entities + relations + chunks).
_HUGE_SYSTEM_PROMPT = "RAG CONTEXT LINE\n" * 4000

# Windows' documented CreateProcess command-line ceiling.
_WINDOWS_CMDLINE_LIMIT = 32767


@pytest.fixture
def captured_call(monkeypatch):
    """Capture the argv/stdin the binding would hand to the CLI."""
    captured = {}

    async def fake_run_cli(argv, prompt, timeout):
        captured["argv"] = argv
        captured["stdin"] = prompt
        captured["timeout"] = timeout
        return json.dumps({"result": "ok", "is_error": False})

    monkeypatch.setattr(claude_cli, "_run_cli", fake_run_cli)
    monkeypatch.setattr(claude_cli, "_resolve_executable", lambda: "claude")
    return captured


async def test_large_system_prompt_stays_off_argv(captured_call):
    """A query-sized system prompt must not be passed as ``--system-prompt``.

    Regression: the RAG context is formatted into ``system_prompt`` by
    ``operate.py``; putting it on argv broke every query on Windows.
    """
    result = await claude_cli.claude_cli_complete_if_cache(
        "haiku",
        "What is hydra completion?",
        system_prompt=_HUGE_SYSTEM_PROMPT,
    )

    assert result == "ok"

    argv = captured_call["argv"]
    argv_size = sum(len(part) for part in argv) + len(argv)
    assert argv_size < _WINDOWS_CMDLINE_LIMIT, (
        f"argv is {argv_size} chars, over the Windows limit -- something "
        f"size-unbounded leaked onto the command line"
    )

    # The context must still reach the model, just via stdin.
    assert _HUGE_SYSTEM_PROMPT in captured_call["stdin"]


async def test_base_persona_still_passed_on_argv(captured_call):
    """The fixed persona is small and stays on argv, replacing the agent prompt."""
    await claude_cli.claude_cli_complete_if_cache("haiku", "hi")

    argv = captured_call["argv"]
    assert "--system-prompt" in argv
    assert argv[argv.index("--system-prompt") + 1] == claude_cli._BASE_SYSTEM_PROMPT


async def test_history_and_system_prompt_both_reach_stdin(captured_call):
    """History replay and instructions coexist in the single stdin payload."""
    await claude_cli.claude_cli_complete_if_cache(
        "haiku",
        "third turn",
        system_prompt="follow these rules",
        history_messages=[
            {"role": "user", "content": "first turn"},
            {"role": "assistant", "content": "second turn"},
        ],
    )

    stdin = captured_call["stdin"]
    assert "follow these rules" in stdin
    assert "first turn" in stdin
    assert "second turn" in stdin
    assert stdin.rstrip().endswith("third turn")

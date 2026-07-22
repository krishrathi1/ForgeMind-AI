"""Claude Code CLI binding.

Drives the locally installed ``claude`` executable in print mode
(``claude -p --output-format json``) instead of calling an HTTP API, so the
binding authenticates through whatever credentials the CLI already holds
(OAuth subscription login or ``ANTHROPIC_API_KEY``). No key needs to live in
``.env``.

Each completion spawns one short-lived ``claude`` process. Process startup
dominates latency (roughly 3-7s per call), so keep ``MAX_ASYNC_LLM`` modest and
expect ingestion to be slower than an HTTP binding.

Anthropic exposes no embedding endpoint and the CLI returns text only, so this
module deliberately provides no embedding function -- pair it with a local
embedding binding (e.g. ollama).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from typing import Any, AsyncIterator, Union

from forgemind.utils import logger

__all__ = ["claude_cli_complete_if_cache", "claude_cli_model_complete"]

# The CLI resolves CLAUDE.md, settings and plugins relative to its working
# directory. Running from the repo would inject unrelated project instructions
# into every extraction prompt, so calls are made from an empty scratch dir.
_NEUTRAL_CWD = os.path.join(tempfile.gettempdir(), "forgemind-claude-cli")

# Replaces Claude Code's coding-agent system prompt. ForgeMind supplies its own
# task instructions via ``system_prompt``; the agent persona only adds noise and
# encourages tool use we explicitly disallow.
_BASE_SYSTEM_PROMPT = (
    "You are a text-processing engine. Follow the user's instructions exactly "
    "and reply with the requested output only, with no preamble, commentary, "
    "or markdown fences unless the instructions ask for them."
)


def _decode(raw: bytes) -> str:
    """Decode CLI output; the console codepage can emit stray bytes on Windows."""
    return raw.decode("utf-8", errors="replace")


def _resolve_executable() -> str:
    """Locate the ``claude`` CLI, honouring an explicit override."""
    override = os.getenv("CLAUDE_CLI_PATH")
    if override:
        if not os.path.isfile(override):
            raise RuntimeError(f"CLAUDE_CLI_PATH points at a missing file: {override}")
        return override

    resolved = shutil.which("claude")
    if not resolved:
        raise RuntimeError(
            "Claude Code CLI not found on PATH. Install it "
            "(https://claude.com/claude-code) or set CLAUDE_CLI_PATH to the "
            "executable."
        )
    return resolved


def _render_prompt(
    prompt: str,
    history_messages: list[dict[str, Any]] | None,
) -> str:
    """Flatten history into the single prompt the CLI accepts.

    ``claude -p`` is stateless per invocation, so prior turns are replayed as
    a transcript prefix rather than as structured messages.
    """
    if not history_messages:
        return prompt

    lines: list[str] = ["<conversation_history>"]
    for message in history_messages:
        role = str(message.get("role", "user")).strip() or "user"
        content = message.get("content", "")
        if isinstance(content, list):
            # Multimodal payloads: keep the text parts, drop image blocks the
            # CLI cannot accept on the command line.
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        lines.append(f"<{role}>{content}</{role}>")
    lines.append("</conversation_history>")
    lines.append("")
    lines.append(prompt)
    return "\n".join(lines)


async def _run_cli(argv: list[str], prompt: str, timeout: float) -> str:
    """Run the CLI with ``prompt`` on stdin, returning stdout.

    The prompt goes through stdin rather than argv for two reasons: ForgeMind's
    templates start with ``---Task---``, which the CLI's option parser would
    read as a flag, and a full extraction prompt can exceed the ~32k Windows
    command-line limit.

    Raises on non-zero exit or timeout.
    """
    os.makedirs(_NEUTRAL_CWD, exist_ok=True)

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_NEUTRAL_CWD,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode("utf-8")), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"Claude CLI timed out after {timeout}s") from None

    if process.returncode != 0:
        detail = _decode(stderr).strip() or _decode(stdout).strip()
        raise RuntimeError(
            f"Claude CLI exited with code {process.returncode}: {detail[:800]}"
        )

    return _decode(stdout)


def _extract_result(raw_stdout: str) -> str:
    """Pull the assistant text out of ``--output-format json`` stdout.

    The CLI may print advisory lines (workspace-trust notices, update banners)
    before the JSON object, so the payload is located by its first brace rather
    than by parsing the whole stream.
    """
    start = raw_stdout.find("{")
    if start == -1:
        raise RuntimeError(
            f"Claude CLI returned no JSON payload: {raw_stdout.strip()[:800]}"
        )

    try:
        payload = json.loads(raw_stdout[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Claude CLI returned malformed JSON: {raw_stdout[start:][:800]}"
        ) from exc

    if payload.get("is_error"):
        raise RuntimeError(
            f"Claude CLI reported an error: {payload.get('result') or payload}"
        )

    result = payload.get("result")
    if not isinstance(result, str):
        raise RuntimeError(f"Claude CLI payload has no text result: {payload}")

    return result


async def claude_cli_complete_if_cache(
    model: str,
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    stream: bool = False,
    **kwargs: Any,
) -> Union[str, AsyncIterator[str]]:
    """Complete ``prompt`` by shelling out to the Claude Code CLI.

    ``stream=True`` is honoured at the interface level -- the caller receives an
    async iterator -- but the CLI is invoked in single-shot mode, so the whole
    answer arrives as one chunk once the process exits.
    """
    if history_messages is None:
        history_messages = []

    # Kwargs are shared across every binding; drop the ones that only make sense
    # for HTTP providers rather than passing them to a subprocess.
    timeout = float(kwargs.get("timeout") or os.getenv("LLM_TIMEOUT", 240))

    argv = [
        _resolve_executable(),
        "-p",
        "--output-format",
        "json",
        # One turn only: without this the CLI can spin on tool calls it has no
        # business making for a completion request.
        "--max-turns",
        "1",
        "--disallowedTools",
        "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task",
    ]

    if model:
        argv += ["--model", model]

    combined_system = _BASE_SYSTEM_PROMPT
    if system_prompt:
        combined_system = f"{_BASE_SYSTEM_PROMPT}\n\n{system_prompt}"
    argv += ["--system-prompt", combined_system]

    rendered_prompt = _render_prompt(prompt, history_messages)

    logger.debug(f"Claude CLI invoking model={model or 'default'} timeout={timeout}s")
    raw_stdout = await _run_cli(argv, rendered_prompt, timeout)
    result = _extract_result(raw_stdout)

    if not stream:
        return result

    async def _single_chunk() -> AsyncIterator[str]:
        yield result

    return _single_chunk()


async def claude_cli_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    keyword_extraction: bool = False,
    entity_extraction: bool = False,
    **kwargs: Any,
) -> Union[str, AsyncIterator[str]]:
    """ForgeMind entry point; resolves the model name from the global config."""
    if history_messages is None:
        history_messages = []

    hashing_kv = kwargs.get("hashing_kv")
    model_name = kwargs.pop("model_name", None)
    if not model_name and hashing_kv is not None:
        model_name = hashing_kv.global_config.get("llm_model_name")

    return await claude_cli_complete_if_cache(
        model_name or os.getenv("LLM_MODEL", "sonnet"),
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )

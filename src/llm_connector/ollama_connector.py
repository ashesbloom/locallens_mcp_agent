"""
LocalLens LLM Connector — Ollama Connector
=============================================
Thin wrapper around Ollama's chat API with:
  - Tool-calling loop (ReAct-style agent)
  - Streaming generator for Gradio
  - Configurable max steps and context limits
  - Graceful import guard (works even if `ollama` isn't installed)
"""

import json
import logging
import os
import re
import sys
from typing import Any, Callable, Dict, Generator, List, Optional

try:
    import ollama
except Exception as exc:  # pragma: no cover - import guard
    ollama = None
    _ollama_import_error = exc
else:
    _ollama_import_error = None


_log = logging.getLogger("locallens_mcp.ollama")
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[locallens-mcp] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False


# ---------------------------------------------------------------------------
#  Configuration via environment variables
# ---------------------------------------------------------------------------

def _default_model() -> str:
    # llama3.2:3b: benchmarked at 1.3s tool calls on M2, English-only, proper API tool calling.
    # Faster and more reliable than mistral:7b-instruct for LocalLens tool use.
    # Override via LOCALLENS_OLLAMA_MODEL env var (e.g. "mistral:7b-instruct", "qwen2.5:7b").
    return os.getenv("LOCALLENS_OLLAMA_MODEL", "llama3.2:3b")


def _default_host() -> str:
    return os.getenv("OLLAMA_HOST", "").strip()


def _max_steps() -> int:
    try:
        return int(os.getenv("LOCALLENS_CHAT_MAX_STEPS", "10"))
    except ValueError:
        return 10


def _num_ctx() -> int:
    """Context window size passed to Ollama on every call.

    The vram-based Ollama default (4096) is nearly full before the user
    types anything — tool specs alone consume ~3,000 tokens. 8192 gives
    comfortable headroom and costs only ~112 MB of extra KV cache on Metal.
    Override via LOCALLENS_CHAT_CTX_LEN.
    """
    try:
        return int(os.getenv("LOCALLENS_CHAT_CTX_LEN", "8192"))
    except ValueError:
        return 8192


def _max_history_messages() -> int:
    """Maximum number of messages to keep in conversation history.

    We always keep the system prompt (first message) and trim oldest
    user/assistant pairs from the middle when the limit is exceeded.
    """
    try:
        return int(os.getenv("LOCALLENS_CHAT_MAX_HISTORY", "40"))
    except ValueError:
        return 40


# ---------------------------------------------------------------------------
#  Connector
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#  Text-mode tool call recovery
# ---------------------------------------------------------------------------

def _extract_text_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """
    Recover a tool call that the model wrote as raw JSON text instead of
    invoking it through the API (text-mode tool calling / qwen2.5 quirk).

    Looks for: {"name": "...", "arguments": {...}} anywhere in the content.
    Returns {"name": ..., "arguments": {...}} or None.
    """
    if not content or "{" not in content:
        return None
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", " ", content).strip()
    # Find the first balanced { ... } block
    start = cleaned.find("{")
    if start == -1:
        return None
    depth, end = 0, start
    for i, ch in enumerate(cleaned[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        return None
    try:
        data = json.loads(cleaned[start:end])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name") or data.get("function")
    args = data.get("arguments") or data.get("parameters") or data.get("args") or {}
    if not name or not isinstance(args, dict):
        return None
    return {"name": name, "arguments": args}


class OllamaConnector:
    """Wrapper around Ollama chat with tool calling, streaming, and context management."""

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None) -> None:
        if ollama is None:
            raise RuntimeError(f"ollama package not available: {_ollama_import_error}")

        self.model = model or _default_model()
        self.host = host or _default_host()
        self._client = None

        if hasattr(ollama, "Client"):
            self._client = ollama.Client(host=self.host) if self.host else ollama.Client()

    # ── Low-level chat calls ──────────────────────────────────────────

    def _chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Any:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "options": {"num_ctx": _num_ctx()},
        }
        if tools:
            kwargs["tools"] = tools
        if stream:
            kwargs["stream"] = True

        if self._client:
            return self._client.chat(**kwargs)
        return ollama.chat(**kwargs)

    # ── Context window management ─────────────────────────────────────

    @staticmethod
    def trim_history(
        messages: List[Dict[str, Any]],
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Trim conversation history to fit within limits.

        Keeps the system prompt (index 0) and the most recent messages.
        Trims from the middle (oldest non-system messages first).
        """
        limit = max_messages or _max_history_messages()
        if len(messages) <= limit:
            return messages

        # Always keep the system prompt and the last (limit - 1) messages
        system = [messages[0]] if messages and messages[0].get("role") == "system" else []
        tail_count = limit - len(system)
        return system + messages[-tail_count:]

    # ── Tool dispatch helper ──────────────────────────────────────────

    @staticmethod
    def _process_tool_calls(
        assistant_message: Dict[str, Any],
        tool_handler: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        working_messages: List[Dict[str, Any]],
    ) -> List[str]:
        """Process tool calls from an assistant message. Returns list of tool result summaries."""
        tool_calls = assistant_message.get("tool_calls") or []
        summaries = []

        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            raw_args = function.get("arguments")

            if not name:
                _log.warning("Tool call missing name: %s", call)
                continue

            args = {}
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    _log.warning("Tool call arguments not valid JSON: %s", raw_args)

            result = tool_handler(name, args)
            result_json = json.dumps(result)
            working_messages.append({
                "role": "tool",
                "name": name,
                "content": result_json,
            })
            summaries.append(name)  # Store bare tool name for logging

        return summaries

    # ── Synchronous (non-streaming) tool loop ─────────────────────────

    def run_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_handler: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        max_steps: Optional[int] = None,
    ) -> str:
        """Run a tool-calling loop until the model returns a final response."""
        if not messages:
            return ""

        steps = max_steps or _max_steps()

        if not tools:
            response = self._chat(messages)
            return response.get("message", {}).get("content", "")

        working_messages = list(messages)

        for step in range(steps):
            response = self._chat(working_messages, tools=tools)
            assistant_message = response.get("message", {})
            working_messages.append(assistant_message)

            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                return assistant_message.get("content", "")

            self._process_tool_calls(assistant_message, tool_handler, working_messages)
            _log.info("Completed tool step %s/%s", step + 1, steps)

        return "I could not complete the request within the tool call limit."

    # ── Streaming tool loop (generator for Gradio) ────────────────────

    def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_handler: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        max_steps: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """Streaming tool-calling loop. Yields partial text as it arrives.

        During tool-call steps, yields status indicators like "[tool_name]".
        During the final text response, yields the content directly.
        Compatible with Gradio's streaming ChatInterface.

        Includes recovery for text-mode tool calls: if qwen2.5 writes a tool
        call as raw JSON in the response text instead of using the tool_calls
        API field, we parse and execute it automatically.
        """
        if not messages:
            return

        steps = max_steps or _max_steps()
        working_messages = list(messages)

        for step in range(steps):
            # Non-streaming call to detect tool calls.
            # Streaming tool-call JSON is unreliable in Ollama.
            response = self._chat(working_messages, tools=tools if tools else None)
            assistant_message = response.get("message", {})
            content = assistant_message.get("content", "")

            tool_calls = assistant_message.get("tool_calls") or []

            if tool_calls:
                # Proper API tool call — process and continue
                working_messages.append(assistant_message)
                summaries = self._process_tool_calls(
                    assistant_message, tool_handler, working_messages,
                )
                for name in summaries:
                    yield f"[{name}]\n"
                _log.info("Step %s/%s: %s", step + 1, steps, ", ".join(summaries))
                continue

            # --- Text-mode tool call recovery ---
            # qwen2.5 sometimes writes {"name": "tool", "arguments": {...}}
            # as plain text instead of using the tool_calls field.
            text_call = _extract_text_tool_call(content)
            if text_call and text_call["name"] in {t["function"]["name"] for t in (tools or [])}:
                name = text_call["name"]
                args = text_call["arguments"]
                _log.warning(
                    "Step %s/%s: text-mode tool call detected (%s) — recovering",
                    step + 1, steps, name,
                )
                # Inject the assistant message then the tool result
                working_messages.append({"role": "assistant", "content": content})
                result = tool_handler(name, args)
                working_messages.append({
                    "role": "tool",
                    "name": name,
                    "content": json.dumps(result),
                })
                yield f"[{name}]\n"
                _log.info("Step %s/%s: %s (recovered)", step + 1, steps, name)
                continue

            # Final response — yield content directly.
            if content:
                yield content
            return

        yield "I could not complete the request within the tool call limit."

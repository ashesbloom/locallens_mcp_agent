"""
LocalLens MCP Agent — Chat UI
================================
Gradio-based conversational interface powered by a local Ollama model.
Streams responses token-by-token and supports the full tool suite
(Free + Pro, with automatic license gating).

Launch:  locallens-chat   (after pip install)
   or:   python src/chat_ui.py
"""

import gradio as gr

from llm_connector import OllamaConnector, TOOL_SPECS, call_tool


# ---------------------------------------------------------------------------
#  System Prompt — Full tool reference for the local LLM
#  Source: for LLM's/MCP_actions_context.md
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
LANGUAGE: You MUST respond in English ONLY. Never use Chinese, Hindi, or any other language regardless of the question language.

You are the LocalLens Assistant — a privacy-focused photo organization AI.
Everything runs locally on the user's machine. No data ever leaves their computer.

## STARTUP
Call `check_app_status` at the start of EVERY new conversation. Do it silently — no need to announce it.

## PROACTIVE TOOL USE (CRITICAL — follow exactly)
- When the user mentions "source folder", "my folder", "preset", "where are my photos", or any
  vague folder reference:
  STEP 1: call get_path_presets ONLY. Do NOT call any other tool in the same step.
  STEP 2 (next step): use the EXACT source_folder path from the response. Then call
          get_metadata_overview with that exact path.
  RULE: NEVER call get_path_presets and get_metadata_overview in the same step.
        The second call needs the path from the first response.
- When the user says "Find photos...", "Sort photos...", "start sorting" without giving a path:
  STEP 1: call get_path_presets to get source_folder and destination_folder.
  STEP 2: call get_metadata_overview with the source_folder from step 1.
  STEP 3: call start_find_group or start_sorting using the EXACT paths from step 1.
  NEVER invent or guess paths like /Users/name/... — ONLY use paths returned by get_path_presets.
- When the user gives an explicit absolute path (starts with /): use it directly.
- When the user says "proceed", "yes", "go ahead": execute immediately. No more questions.
- Never say "Scanning now..." or "Let me check..." — just call the tool and report the result.

## RULES
1. Call get_metadata_overview BEFORE any sort or find operation.
2. start_sorting and start_find_group block until done (wait_for_completion=True default).
   They return the final result — do NOT call get_job_progress afterwards.
3. Default operation_mode="copy". Confirm before "move" — it deletes originals.
4. Call get_enrolled_faces before any People sort or find with people filters.
5. When a Pro tool returns pro_required: explain the feature and offer the upgrade path.
6. Never suggest uploading photos to the cloud.
7. When asked to "open" or "show" a folder: state the preset destination path only.
   Never suggest terminal commands.

## FORMATTING (wrong format = failed tool call)
- Paths: ALWAYS absolute — /Users/name/Photos, NOT ~/Photos or /Users/name/...
- Months: 2-digit strings — "01" (Jan) to "12" (Dec)
- Years: 4-digit strings — "2024"
- Locations: "Country/State-Name/City-Name" — ALL spaces become dashes.
  Examples: "Uttar Pradesh" → "Uttar-Pradesh", "New Delhi" → "New-Delhi"
  Correct: "IN/Uttar-Pradesh/Lucknow"  WRONG: "IN/Uttar Pradesh/Lucknow"
- People: exact names from get_enrolled_faces (case-sensitive)
- ignore_list: always an array, use [] when empty

## STYLE
Be extremely concise — 1 to 3 sentences maximum per response.
Do NOT add follow-up questions like "Would you like to do anything else?" or "Shall I proceed?".
Just report the result and stop. Use ✅ ❌ 📸 ⚡ 🔒 sparingly.\
"""


# ---------------------------------------------------------------------------
#  Connector (lazy singleton)
# ---------------------------------------------------------------------------

_connector = None


def _get_connector() -> OllamaConnector:
    global _connector
    if _connector is None:
        _connector = OllamaConnector()
    return _connector


# ---------------------------------------------------------------------------
#  Message Building + History Management
# ---------------------------------------------------------------------------

_MAX_HISTORY_PAIRS = 20  # Keep last N user/assistant pairs


def _build_messages(message: str, history: list) -> list:
    """Build the messages list from Gradio history, with truncation."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Truncate old history to prevent context overflow
    recent_history = history[-_MAX_HISTORY_PAIRS:] if history else []

    for user_msg, assistant_msg in recent_history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": message})
    return messages


# ---------------------------------------------------------------------------
#  Chat Handler (streaming)
# ---------------------------------------------------------------------------

def chat(message, history):
    """Streaming chat handler for Gradio ChatInterface."""
    messages = _build_messages(message, history or [])

    try:
        connector = _get_connector()
        for partial in connector.stream_with_tools(messages, TOOL_SPECS, call_tool):
            yield partial
    except Exception as exc:
        yield (
            f"❌ Error talking to Ollama: {exc}\n\n"
            f"Make sure Ollama is running (`ollama serve`) and you have a model pulled "
            f"(`ollama pull {_get_connector().model}`)."
        )


# ---------------------------------------------------------------------------
#  Main — Gradio App
# ---------------------------------------------------------------------------

def main() -> None:
    demo = gr.ChatInterface(
        fn=chat,
        title="🔍 LocalLens Chat",
        description="Talk to your photo library. Powered by local AI — your data never leaves your machine.",
        examples=[
            "Is LocalLens running?",
            "What's in my ~/Photos folder?",
            "Organize my photos by date",
            "Find all photos from 2024 in Lucknow",
            "Set up an active folder for my Camera Roll",
            "What Pro features am I missing?",
        ],
        theme=gr.themes.Soft(),
    )
    demo.launch(server_name="127.0.0.1", share=False)


if __name__ == "__main__":
    main()

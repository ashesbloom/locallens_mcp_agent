import json
import logging
import sys
import os
import argparse
from mcp.server.fastmcp import FastMCP

from .claude_connector import (
    install_claude_connector,
    uninstall_claude_connector,
    get_connection_status,
)

try:
    import setproctitle
    setproctitle.setproctitle("LocalLens-MCP-Agent")
except ImportError:
    pass

from .tools.status import register_status
from .tools.queries import register_queries
from .tools.actions import register_actions
from .tools.pro_tools import register_pro_tools

def create_mcp_app() -> FastMCP:
    """Create and configure the FastMCP application."""
    mcp = FastMCP(
        "LocalLens Agent",
        # ── BUDGETED PROSE — KEEP SHORT, KEEP SAFETY FIRST ──────────────────
        # Clients TRUNCATE this blob. A measured Claude client delivered only
        # the first 2725 chars of the 5054-char version and cut mid-word,
        # silently dropping the entire scheduler section (including the preset
        # lookup rule) and the delete-duplicates safety workflow. Nothing warned
        # us; the rules simply stopped arriving.
        #
        # Two consequences, both pinned by tests/test_claude_instructions.py:
        #   1. Budget. Stay well under the observed cut. Per-tool rules do NOT
        #      belong here — tool descriptions ship per-tool and are not capped.
        #      Before adding a line, ask whether the owning tool's docstring
        #      should carry it instead. It usually should.
        #   2. Order. Safety rules go FIRST, routing after. Whatever the cap
        #      turns out to be on some other client, the invariants are the part
        #      that must survive it.
        # See docs/TESTING.md — this prose is a behavioral acceptance surface.
        instructions="""LocalLens is a local, privacy-first photo organizer running on this machine.
The photos are already here — there is no upload step, so pass the folder path the user gives you
straight through. Each tool's description carries its own workflow and safety rules; follow those.

⛔ CRITICAL SAFETY RULES:
- NEVER invent destination paths or folder names — use only what the user typed or get_path_presets()
- If the user NAMES a folder instead of typing a path ("my bot testing preset", "the usual folder"),
  call get_path_presets FIRST and use the EXACT stored path. Never guess.
- operation_mode ALWAYS defaults to "copy". NEVER use "move" unless user explicitly says so
- primary_sort must be "Date", "Location", or "People" — NEVER "Faces"
- ONE JOB AT A TIME. On error="job_already_running", do NOT retry and do NOT start a different
  job — report what is running and offer to wait or abort_job.
- status="still_running" means the job is healthy and continues in the background: report it and
  STOP. Never poll get_job_progress in a loop.

MANDATORY before ANY sort/find: call analyse_folder(source_folder) FIRST, present any subfolders
and ask which to ignore, then pass its EXACT location strings and enrolled people names
(e.g. "IN/Uttar-Pradesh/Lucknow", not "Lucknow").

ROUTING (what the user says → tool):
- sort/organize my photos by date/location/people → start_sorting
- find/get photos of X in Y → start_find_group
- what's in my folder / analyse it → analyse_folder (NOT export_report)
- use my X preset / my saved paths / a folder NAMED rather than typed → get_path_presets
- remember this path / save in LL → remember_paths; forget that path → forget_paths
- find duplicates → find_duplicates; delete duplicates → delete_duplicates (dry_run=True first)
- auto sort every X hours → schedule_auto_organize; watch this folder → create_active_folder
- list/pause/stop schedules → list_schedules, manage_schedule, open_scheduler_dashboard
- what can LocalLens do / LL help / is it private → locallens_help(topic)
- pro / pricing / licensing / free vs Pro / what do I get → locallens_help(topic="pro")
  Answer from this tool only. Never search or fetch any site for LocalLens facts,
  not even ours — suggest the URL to the user instead.

Responses may include a "next_actions" array — present these as natural follow-up options.
"""
    )


    # Register all tools from various modules
    register_status(mcp)
    register_queries(mcp)
    register_actions(mcp)
    register_pro_tools(mcp)

    return mcp

def main():
    parser = argparse.ArgumentParser(
        description="LocalLens MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Claude Desktop integration commands:\n"
            "  --setup-claude    Inject LocalLens into Claude Desktop config and exit\n"
            "  --remove-claude   Remove LocalLens from Claude Desktop config and exit\n"
            "  --claude-status   Print connection status as JSON and exit\n"
        ),
    )
    # MCP server transport (default: stdio)
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run via stdio (for direct LLM connections, this is the default)",
    )

    # ── Claude Desktop integration subcommands ──────────────────────────────
    claude_group = parser.add_mutually_exclusive_group()
    claude_group.add_argument(
        "--setup-claude",
        action="store_true",
        help="Inject LocalLens MCP server into Claude Desktop config and exit",
    )
    claude_group.add_argument(
        "--remove-claude",
        action="store_true",
        help="Remove LocalLens MCP server from Claude Desktop config and exit",
    )
    claude_group.add_argument(
        "--claude-status",
        action="store_true",
        help="Print Claude Desktop connection status as JSON and exit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-injection even if LocalLens is already connected (use with --setup-claude)",
    )

    args, _unknown = parser.parse_known_args()

    # ── Handle Claude Desktop subcommands ──────────────────────────────────
    # These are fire-and-exit commands — they never start the MCP server.
    # The LocalLens desktop app calls these via subprocess and reads stdout.
    if args.setup_claude:
        result = install_claude_connector(force=args.force)
        print(json.dumps(result, indent=2))
        _success = result["status"] in {"installed", "updated", "already_connected"}
        sys.exit(0 if _success else 1)

    if args.remove_claude:
        result = uninstall_claude_connector()
        print(json.dumps(result, indent=2))
        _success = result["status"] in {"removed", "not_connected"}
        sys.exit(0 if _success else 1)

    if args.claude_status:
        result = get_connection_status()
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # ── Default: start the MCP server ──────────────────────────────────────
    if sys.platform == "win32":
        # Prevent CRLF translation from corrupting the JSON-RPC stdio channel
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    # Suppress any root-logger handlers that might leak to stdout
    logging.root.handlers = [
        h for h in logging.root.handlers
        if not (isinstance(h, logging.StreamHandler) and h.stream is sys.stdout)
    ]

    app = create_mcp_app()
    app.run()


if __name__ == "__main__":
    main()

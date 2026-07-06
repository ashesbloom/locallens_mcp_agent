import sys
import argparse
from mcp.server.fastmcp import FastMCP

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
        instructions="""You are connected to LocalLens — a local, privacy-first photo organization app running on the user's machine.
You have FULL ACCESS to the user's filesystem through these tools. NEVER say "I can't access your files" or "upload your files". Just USE the tools.

LOCALLENS GUIDE:
- locallens_help(topic) is an interactive guide about LocalLens features, privacy, and tools.
  Call it when the user asks about LocalLens specifically — e.g. "what can LocalLens do?",
  "LL help", "is LocalLens private?", "LocalLens features", "LL free vs pro".
  Topics: "welcome", "quickstart", "organize", "find", "people", "duplicates", "automation", "privacy", "pro".
  When presenting the response: follow the 'guidance' field, show 'explore_next' as a numbered menu.

TOOL SELECTION:
- "sort/organize my photos by X" → start_sorting
- "find photos of X in Y" / "get pictures from Z" → start_find_group
- "what's in my folder" / "analyse my folder" → analyse_folder (NOT export_report)
- "open the folder" / "show me the results" → open_folder
- "remember this path" / "save for next time" / "save in LL" → remember_paths
- "forget that path" / "remove from memory" → forget_paths
- "find duplicates" / "find copies" → find_duplicates
- "delete duplicates" / "clean up copies" → delete_duplicates (Pro, ALWAYS dry_run=True first)

MANDATORY WORKFLOW before ANY sort/find action:
1. Call analyse_folder(source_folder) FIRST — returns subfolders, photo counts, locations, people
2. If subfolders exist → PRESENT the list and ASK which to ignore
3. Use EXACT location strings from analyse_folder (e.g. "IN/Uttar-Pradesh/Lucknow") — if user says "Lucknow", map it to the full string
4. Use EXACT enrolled people names — if unsure, call get_enrolled_faces

⛔ CRITICAL SAFETY RULES:
- NEVER invent destination paths or folder names. Use only what the user typed or get_path_presets()
- operation_mode ALWAYS defaults to "copy". NEVER use "move" unless user explicitly says so
- primary_sort must be "Date", "Location", or "People" — NEVER "Faces"
- For start_find_group: if user says "put in /a/b/c" → destination_folder="/a/b", folder_name="c"

After tool calls complete, the response may include a "next_actions" array — present these as natural follow-up options.

📂 OPEN FOLDER:
- Call open_folder() any time user says "show me results", "open the folder", "where are my photos?"

💾 PATH MEMORY (remember_paths / forget_paths):
- When user says "remember this", "save for next time", "add to LL memory" → call remember_paths()
- To remove: "forget the X path" → call forget_paths(preset_name="X")

🗑️ DELETE DUPLICATES SAFETY WORKFLOW (MANDATORY — NEVER SKIP):
1. Run find_duplicates() → response contains next_actions with pre-populated file list
2. Call delete_duplicates(file_paths=[...], dry_run=True) → shows what WOULD be deleted
3. Present the list to the user and ask for confirmation
4. Only call delete_duplicates(dry_run=False) after EXPLICIT confirmation
5. Never delete ALL files in a group — keep at least one

📅 SCHEDULER (Pro):
- "schedule auto organize" / "auto sort every X hours" → schedule_auto_organize (periodic sweeps)
- "watch this folder" / "real-time organize" → create_active_folder (instant detection)
- "list my schedules" / "what's running?" → list_schedules
- "pause/stop/delete schedule" → manage_schedule
- "open scheduler dashboard" / "scheduler logs" → open_scheduler_dashboard

🎨 SMART ALBUM SUGGESTIONS (Pro):
- "suggest albums" / "what albums should I create?" → smart_album_suggestions
"""
    )


    # Register all tools from various modules
    register_status(mcp)
    register_queries(mcp)
    register_actions(mcp)
    register_pro_tools(mcp)

    return mcp

def main():
    parser = argparse.ArgumentParser(description="LocalLens MCP Server")
    # For standalone LLMs that connect via stdio
    parser.add_argument("--stdio", action="store_true", help="Run via stdio (for direct LLM connections)")
    args, _unknown = parser.parse_known_args()

    app = create_mcp_app()
    
    if args.stdio:
        # Default behavior: run on stdio, typical for MCP
        app.run()
    else:
        # By default, FastMCP runs with stdio if run() is called directly without specific server transports.
        app.run()

if __name__ == "__main__":
    main()

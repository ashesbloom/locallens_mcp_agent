import asyncio
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, Optional

from ..config import get_locallens_url
from ..license import get_license_info
from ..updater import check_for_updates


def register_status(mcp: FastMCP):

    from ..updater import MCP_VERSION

    @mcp.tool()
    async def check_app_status() -> Dict[str, Any]:
        """
        Check if LocalLens is running and healthy.
        Use this when the user asks if the app is running, or generally to confirm connection.
        Also checks if heavy dependencies (like face_recognition) are available.
        """
        try:
            status = {}
            async with httpx.AsyncClient() as client:
                r1 = await client.get(f"{get_locallens_url()}/api/health", timeout=3)
                if r1.status_code == 200:
                    status["health"] = r1.json()

                r2 = await client.get(f"{get_locallens_url()}/api/check-dependencies", timeout=3)
                if r2.status_code == 200:
                    status["dependencies"] = r2.json()

            # Include license tier so the LLM always knows the user's plan
            status["license"] = get_license_info()
            status["mcp_version"] = MCP_VERSION

            # Non-blocking update check (runs in thread pool, never slows down health check)
            update_info = await asyncio.to_thread(check_for_updates)
            if update_info:
                status["update_available"] = update_info
                # Build the upgrade instructions section
                highlights_str = ""
                if update_info.get("highlights"):
                    highlights_str = "".join(
                        f"  - {h}\n" for h in update_info["highlights"]
                    )
                notes_url = update_info.get("release_notes_url", "https://locallens.app/changelog")
                cmd = update_info.get("upgrade_command", "pip install --upgrade locallens-mcp")

                whats_new_block = f"### What is new:\n{highlights_str}" if highlights_str else ""

                if update_info.get("is_critical"):
                    status["update_guidance"] = (
                        "IMPORTANT — Show this PROMINENTLY at the TOP of your response, "
                        "before the status table. Format it exactly like this:\n\n"
                        f"---\n"
                        f"## 🚨 Critical Update Required\n\n"
                        f"**LocalLens MCP {update_info['latest_version']}** is available "
                        f"and your version (`{update_info['current_version']}`) is **no longer supported**.\n\n"
                        f"{whats_new_block}"
                        f"### How to upgrade:\n"
                        f"Open your terminal and run:\n"
                        f"```\n{cmd}\n```\n"
                        f"Then restart Claude Desktop.\n\n"
                        f"[📋 Full release notes]({notes_url})\n\n"
                        f"---\n"
                    )
                else:
                    status["update_guidance"] = (
                        "IMPORTANT — Show this as a highlighted section AFTER the status table. "
                        "Format it exactly like this:\n\n"
                        f"---\n"
                        f"## ✨ Update Available — v{update_info['latest_version']}\n\n"
                        f"A new version of LocalLens MCP is ready! "
                        f"You are on `{update_info['current_version']}`.\n\n"
                        f"{whats_new_block}"
                        f"### How to upgrade:\n"
                        f"Open your terminal and run:\n"
                        f"```\n{cmd}\n```\n"
                        f"Then restart Claude Desktop to get the new features.\n\n"
                        f"[📋 Full release notes]({notes_url})\n\n"
                        f"---\n"
                    )

            # Build the human-readable summary parts
            health_ok = status.get("health", {}).get("status") == "ok"
            deps = status.get("dependencies", {})
            face_active = deps.get("face_recognition_installed", False)
            license_info = status.get("license", {})
            tier = license_info.get("tier", "free")

            status["guidance"] = (
                "Present this as a clean, structured status card. "
                "If 'update_guidance' exists, follow those instructions EXACTLY "
                "(critical updates go BEFORE the table, normal updates go AFTER). "
                "Format the status like this:\n\n"
                "## 🟢 LocalLens Status\n"
                "| Item | Status |\n"
                "|---|---|\n"
                f"| Backend | {'✅ Running & Healthy' if health_ok else '🔴 Not Responding'} |\n"
                f"| Face Recognition | {'✅ Active' if face_active else '❌ Not Installed'} |\n"
                f"| License | {'⭐ Pro' if tier == 'pro' else '🆓 Free'} |\n"
                f"| MCP Version | `{MCP_VERSION}` |\n\n"
                "Then ask: 'What would you like to do? You can say things like "
                "\"sort my photos by date\" or \"what can you do?\"'"
            )

            return status if status else {"status": "offline", "message": "LocalLens is not responding"}
        except Exception:
            return {
                "status": "offline",
                "message": "LocalLens is not running or accessible",
                "guidance": (
                    "Tell the user clearly: '🔴 LocalLens is not running. "
                    "Please start the LocalLens app first, then try again.' "
                    "Don't speculate about why it's down."
                ),
            }

    @mcp.tool()
    async def get_stats() -> Dict[str, Any]:
        """
        Get a comprehensive snapshot of the LocalLens installation.
        Use this to give the user an overview of their setup, or to check capabilities before running actions.

        Response fields:
        - app_version: Full application version string (e.g. "2.3.0")
        - api_title: Application name
        - platform: OS name ("Darwin" = macOS, "Windows", "Linux")
        - python_version: Python interpreter version
        - backend_uptime_seconds: Seconds since the backend started
        - face_recognition_active: True if the AI face library is loaded and usable
        - image_format_types_supported: Count of distinct image FORMAT TYPES LocalLens understands
            e.g. .jpg, .png, .heic, .cr2, .dng — currently 19 types.
            ⚠️  This is NOT the count of photos in any folder.
            To count actual photos or inspect a folder, call analyse_folder(source_folder) instead.
        - enrolled_faces_count: Number of DISTINCT people enrolled for face recognition
        - presets_count: Number of saved source/destination path presets
        - data_dir: Filesystem path where LocalLens stores its data (encodings, presets, config)
        - license: Current license status object containing:
            - activated (bool): True if Pro is active
            - tier (str): "free" or "pro"
            - activated_at (str|null): ISO timestamp of activation
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{get_locallens_url()}/api/stats", timeout=5)
                r.raise_for_status()
                stats = r.json()

            # Inject local license info into the stats response
            stats["license"] = get_license_info()
            stats["mcp_version"] = MCP_VERSION

            # Build structured formatting guidance
            platform = stats.get("platform", "Unknown")
            platform_name = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform, platform)
            app_version = stats.get("app_version", "?")
            face_active = stats.get("face_recognition_active", False)
            enrolled = stats.get("enrolled_faces_count", 0)
            presets = stats.get("presets_count", 0)
            formats = stats.get("image_format_types_supported", 0)
            uptime_s = stats.get("backend_uptime_seconds", 0)
            uptime_h = round(uptime_s / 3600, 1) if uptime_s else 0
            tier = stats.get("license", {}).get("tier", "free")

            stats["guidance"] = (
                "Present this as a detailed, well-formatted system overview. Format like this:\n\n"
                f"## 📊 LocalLens System Overview\n\n"
                "| Component | Details |\n"
                "|---|---|\n"
                f"| App Version | `{app_version}` |\n"
                f"| MCP Version | `{MCP_VERSION}` |\n"
                f"| Platform | {platform_name} |\n"
                f"| License | {'⭐ Pro' if tier == 'pro' else '🆓 Free'} |\n"
                f"| Uptime | {uptime_h}h |\n\n"
                "### Capabilities\n"
                "| Feature | Status |\n"
                "|---|---|\n"
                f"| Face Recognition | {'✅ Active' if face_active else '❌ Not Available'} |\n"
                f"| Enrolled People | {enrolled} |\n"
                f"| Saved Presets | {presets} |\n"
                f"| Image Formats | {formats} types supported |\n\n"
                "After the table, ask if they'd like to do something: "
                "'Want to organize some photos, check your schedules, or explore features?'"
            )

            return stats
        except Exception as e:
            return {
                "error": str(e),
                "message": "Could not retrieve stats",
                "guidance": (
                    "Tell the user: '🔴 Could not connect to LocalLens to retrieve stats. "
                    "Make sure the app is running and try again.'"
                ),
            }



    @mcp.tool()
    async def get_job_progress() -> Dict[str, Any]:
        """
        Check the full progress and context of the current (or most recently completed) job.
        Use when the user asks 'how is it going?', 'is it done yet?', or 'what is being processed?'.

        Response fields (all fields persist after completion so you can still read the last job):

        Core status:
        - is_active (bool): True if a job is currently running
        - status (str): "running" | "complete" | "aborted" | "error" | "ready"
        - progress (int): 0–100 percentage complete
        - message (str): Latest human-readable status message from the backend

        Job identity:
        - job_type (str|null): "sorting" | "find_group" | "enrollment" | null (no job yet)
        - operation_mode (str|null): "copy" or "move" — find_group is always "copy"

        Location context:
        - source_folder (str|null): Folder being scanned/processed
        - destination_folder (str|null): Where results are written

        Sorting context (only set for sorting jobs):
        - primary_sort (str|null): "Date" | "Location" | "People" | "Hybrid"
        - face_mode (str|null): "Fast (HOG)" | "Balanced" | "Accurate (CNN)"
          — only present when primary_sort is "People"; null for Date/Location sorts

        Find & Group context (only set for find_group jobs):
        - folder_name (str|null): Name of the target subfolder inside destination_folder
        - filters_applied (dict|null): Active filter criteria, e.g.:
            { "years": ["2024"], "people": ["Mayank"] }
          — null if no filters (which would match all photos)

        File scope:
        - total_files (int): Total supported image files found in source_folder,
          after applying ignore_list — this is the exact count the job processes
        - ignore_list (list): Subfolders excluded from this job
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{get_locallens_url()}/api/job-status", timeout=5)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"error": str(e)}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERACTIVE HELP — Dynamic, step-by-step guided tour
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    async def locallens_help(topic: str = "welcome") -> Dict[str, Any]:
        """
        📖 Interactive LocalLens guide. Call this when the user asks:
        - "what is LocalLens?" / "what can I do?" / "help" / "features"
        - "what tools do you have?" / "how does this work?"
        - "is my data safe?" / "privacy?" / "where is my data stored?"
        - "what's the difference between free and pro?" / "upgrade"
        - "show me examples" / "what can I try?"

        ⚠️ IMPORTANT: This is an INTERACTIVE GUIDE — do NOT dump the full response as raw JSON.
        Present the content conversationally using the 'guidance' field instructions, then
        show the user their navigation options from 'explore_next'.

        topic options:
        - "welcome"    — Short intro + interactive topic menu (DEFAULT — use for general questions)
        - "organize"   — Photo sorting & organization features
        - "find"       — Search & filter capabilities
        - "people"     — Face recognition & people management
        - "duplicates" — Duplicate detection & cleanup
        - "automation" — Scheduler, active folders, auto-organize
        - "privacy"    — Privacy & security deep-dive
        - "pro"        — Free vs Pro comparison with feature showcase
        - "quickstart" — 3 things to try right now
        """

        # ── Inject license status for contextual Pro messaging ──
        license_info = get_license_info()
        is_pro = license_info.get("activated", False)

        # ══════════════════════════════════════════════
        # WELCOME — The landing page
        # ══════════════════════════════════════════════
        if topic == "welcome":
            welcome = {
                "intro": {
                    "tagline": "LocalLens — Your Photos. Your Machine. Your Rules.",
                    "one_liner": (
                        "AI-powered photo organization that runs 100% on your computer. "
                        "Sort by date, location, or faces — just by asking in plain English."
                    ),
                    "key_differentiator": "🔒 Unlike Google Photos or iCloud, your photos NEVER leave your machine. Not even metadata.",
                },
                "what_can_you_do": [
                    "📸 \"Sort my vacation photos by location\" → Organized in seconds",
                    "👤 \"Find all photos of Mom\" → AI face recognition pulls them out",
                    "🗑️ \"Find duplicate photos\" → Reclaim gigabytes of storage",
                    "⚡ \"Watch this folder\" → New photos auto-organized instantly",
                ],
                "license_status": "Pro ✅" if is_pro else "Free tier — Pro features available",
                "explore_topics": [
                    {"topic": "quickstart", "label": "🚀 Quick Start — 3 things to try right now"},
                    {"topic": "organize", "label": "📂 Organizing — Sort photos by date, location, people"},
                    {"topic": "find", "label": "🔍 Search & Find — Locate specific photos instantly"},
                    {"topic": "people", "label": "👤 People — Face recognition & management"},
                    {"topic": "duplicates", "label": "🗑️ Duplicates — Find and clean up copies"},
                    {"topic": "automation", "label": "⚡ Automation — Scheduled & real-time organizing"},
                    {"topic": "privacy", "label": "🔒 Privacy — How your data stays safe"},
                    {"topic": "pro", "label": "⭐ Free vs Pro — What's included"},
                    {"topic": "whats_new", "label": "🆕 What's New — Latest updates & coming soon"},
                ],
                "guidance": (
                    "Present the tagline and one_liner enthusiastically but briefly (2-3 lines max). "
                    "Show the 4 'what_can_you_do' examples as exciting highlights. "
                    "Then present explore_topics as a numbered menu and ask: "
                    "'What would you like to explore? Pick a number or just ask me anything!' "
                    "DO NOT dump all topic contents. This is a MENU, not a manual."
                ),
            }
            return welcome

        # ══════════════════════════════════════════════
        # QUICKSTART — Get them doing something in 30 seconds
        # ══════════════════════════════════════════════
        if topic == "quickstart":
            return {
                "title": "🚀 3 Things to Try Right Now",
                "try_these": [
                    {
                        "step": 1,
                        "say_this": "\"Analyze my photos folder\"",
                        "what_happens": "Scans your folder — shows photo count, locations detected, people recognized, date range.",
                        "example_result": "→ '186 photos • 5 locations (Delhi, Lucknow, Mumbai) • 3 people • Jan–Jul 2024'",
                        "tool": "analyse_folder",
                    },
                    {
                        "step": 2,
                        "say_this": "\"Sort them by location\"",
                        "what_happens": "Every photo organized into country/state/city folders. Originals untouched — copies.",
                        "example_result": "→ /India/Delhi/ (52) • /India/Lucknow/ (89) • /Unknown/ (45)",
                        "tool": "start_sorting",
                    },
                    {
                        "step": 3,
                        "say_this": "\"Open the output folder\"",
                        "what_happens": "Finder pops open showing your organized library.",
                        "example_result": "→ Beautiful folder structure, ready to browse 🎉",
                        "tool": "open_folder",
                    },
                ],
                "after_that": "That's it — 3 sentences to organize your entire library.",
                "explore_next": [
                    {"topic": "organize", "label": "📂 More sorting options (date, people)"},
                    {"topic": "people", "label": "👤 Set up face recognition"},
                    {"topic": "automation", "label": "⚡ Auto-organize without lifting a finger"},
                ],
                "guidance": (
                    "Present as a fun 1-2-3 walkthrough. Show each step clearly with what to say "
                    "and what happens. Use the say_this as literal user input. "
                    "After the 3 steps, ask which feature they'd like to explore next."
                ),
            }

        # ══════════════════════════════════════════════
        # ORGANIZE — Sorting features
        # ══════════════════════════════════════════════
        if topic == "organize":
            result = {
                "title": "📂 Photo Organization",
                "intro": "Tell me how you want your photos grouped. No manual dragging.",
                "sort_modes": [
                    {
                        "mode": "📅 By Date",
                        "say": "\"Sort my photos by date\"",
                        "result": "/2024/January/, /2024/February/, /2023/December/",
                        "best_for": "Chronological archives, yearly backups",
                        "tier": "free",
                    },
                    {
                        "mode": "📍 By Location",
                        "say": "\"Sort by location\"",
                        "result": "/India/Delhi/, /USA/New-York/, /Unknown/",
                        "best_for": "Travel photos, vacation albums",
                        "tier": "free",
                    },
                    {
                        "mode": "👤 By People",
                        "say": "\"Sort by people\"",
                        "result": "/Mayank/, /Vidushi/, /Unknown/",
                        "best_for": "Family albums, individual collections",
                        "tier": "pro",
                    },
                ],
                "safety": "🛡️ Default is COPY — originals never moved unless you ask.",
                "pro_tip": "💡 Always 'analyze my folder' first — see what's inside before sorting.",
                "scenario": {
                    "title": "Post-vacation: 423 photos dumped in one folder",
                    "flow": [
                        "You: \"What's in /Users/me/DCIM?\"",
                        "→ '423 photos • Paris, London, Rome • Mar 12–19'",
                        "You: \"Sort by location\"",
                        "→ /France/Paris/ (156) • /UK/London/ (134) • /Italy/Rome/ (98)",
                        "You: \"Open the folder\" → Finder opens 🎉",
                        "You: \"Remember as 'Europe 2024'\" → Saved for next time",
                    ],
                },
                "explore_next": [
                    {"topic": "find", "label": "🔍 Find specific photos instead"},
                    {"topic": "people", "label": "👤 Set up face recognition"},
                    {"topic": "automation", "label": "⚡ Auto-sort on a schedule"},
                ],
            }
            if not is_pro:
                result["pro_hint"] = (
                    "⭐ Sort by People uses AI to give every person their own folder. "
                    "Imagine: one click → every photo of Mom in /Mom/. Available with Pro."
                )
            result["guidance"] = (
                "Show the 3 sort modes as clear options with what to say and what you get. "
                "Walk through the vacation scenario briefly. "
                "If free tier, mention People sort naturally as an exciting upgrade — don't be pushy. "
                "End with explore_next."
            )
            return result

        # ══════════════════════════════════════════════
        # FIND — Search & filter
        # ══════════════════════════════════════════════
        if topic == "find":
            return {
                "title": "🔍 Find & Group Specific Photos",
                "intro": "Don't sort everything — just pull out exactly what you need.",
                "examples": [
                    {"say": "\"Find all photos of Mayank\"", "result": "→ Every photo with Mayank's face, copied to one folder"},
                    {"say": "\"Get pictures from Lucknow\"", "result": "→ All GPS-tagged Lucknow photos grouped together"},
                    {"say": "\"Pull out July 2024 photos\"", "result": "→ Date-filtered extraction"},
                    {"say": "\"Find Vidushi in Delhi from 2024\"", "result": "→ Person + location + year — exact matches only"},
                ],
                "safety": "🛡️ Always COPIES — originals stay exactly where they are.",
                "explore_next": [
                    {"topic": "people", "label": "👤 Teach it new faces"},
                    {"topic": "organize", "label": "📂 Sort entire folder instead"},
                    {"topic": "duplicates", "label": "🗑️ Find duplicate photos"},
                ],
                "guidance": (
                    "Present examples as 'you say → you get'. Emphasize combined filters. "
                    "Mention safety (copies only). End with explore_next."
                ),
            }

        # ══════════════════════════════════════════════
        # PEOPLE — Face recognition
        # ══════════════════════════════════════════════
        if topic == "people":
            result = {
                "title": "👤 Face Recognition & People",
                "intro": "Teach LocalLens faces, then sort or search by person.",
                "how": [
                    "1️⃣ Enroll — Give 3-5 clear photos + their name",
                    "2️⃣ Recognize — AI learns their face (128-dim math model)",
                    "3️⃣ Organize — Sort library by person, or find all photos of someone",
                ],
                "scenario": {
                    "title": "Making a birthday slideshow for Mom",
                    "flow": [
                        "\"Add Mom to face recognition\" → Provide 4 photos",
                        "\"Find all photos of Mom\" → 147 photos across 5 years",
                        "\"Sort them by date\" → /2019/, /2020/, /2021/...",
                        "→ Birthday slideshow ready in under a minute 🎂",
                    ],
                },
                "privacy": "🔒 Face data = 128 numbers, NOT images. Never leaves your machine. Delete anytime.",
                "explore_next": [
                    {"topic": "find", "label": "🔍 Find photos of someone"},
                    {"topic": "organize", "label": "📂 Sort whole library by people"},
                    {"topic": "automation", "label": "⚡ Auto-sort by person for new photos"},
                ],
            }
            if not is_pro:
                result["tier"] = "pro"
                result["pro_pitch"] = {
                    "problem": "10,000 photos. Can't find your kids without scrolling for hours.",
                    "solution": "Enroll once → 'find all photos of [name]' → every match, instantly.",
                    "hook": "Sort by People is the #1 reason users upgrade to Pro.",
                }
            else:
                result["tier"] = "pro ✅ (unlocked)"
                result["quick_action"] = "Say 'who do you recognize?' or 'add [name] to face recognition'."
            result["guidance"] = (
                "Show the 3-step flow and the birthday scenario. "
                "If free: present pro_pitch as problem→solution (don't be salesy). "
                "If Pro: show quick_action to get started. End with explore_next."
            )
            return result

        # ══════════════════════════════════════════════
        # DUPLICATES — Storage cleanup
        # ══════════════════════════════════════════════
        if topic == "duplicates":
            result = {
                "title": "🗑️ Duplicate Detection & Cleanup",
                "intro": "Reclaim storage by finding and safely removing duplicates.",
                "how": [
                    "1️⃣ Scan — Detects exact copies and near-duplicates",
                    "2️⃣ Review — Shows groups with a recommended 'keeper'",
                    "3️⃣ Clean — Moves to Trash (recoverable!) — never permanent",
                ],
                "scenario": {
                    "title": "Phone sync synced 3 copies of everything",
                    "flow": [
                        "\"Find duplicates in my phone backup\"",
                        "→ '234 groups • 412 redundant files • 8.7 GB recoverable'",
                        "\"Delete the duplicates\"",
                        "→ Dry run first: 'These 412 files would go to Trash. Proceed?'",
                        "\"Yes\" → 8.7 GB freed! Recoverable from Trash ♻️",
                    ],
                },
                "safety": [
                    "✅ Dry run shown first — nothing happens without explicit OK",
                    "✅ Files go to Trash — recoverable, not permanent",
                    "✅ Keeps at least one copy — never deletes all versions",
                ],
                "explore_next": [
                    {"topic": "organize", "label": "📂 Organize the cleaned folder"},
                    {"topic": "automation", "label": "⚡ Auto-organize to prevent future mess"},
                    {"topic": "privacy", "label": "🔒 How your data stays private"},
                ],
            }
            if not is_pro:
                result["tier"] = "pro"
                result["pro_pitch"] = {
                    "problem": "Average library: 15-30% duplicates. Gigabytes wasted.",
                    "solution": "One sentence: 'Find duplicates.' Scans, groups, cleans — zero risk.",
                    "hook": "Most users recover 5-15 GB on their first scan.",
                }
            else:
                result["tier"] = "pro ✅ (unlocked)"
                result["quick_action"] = "Say 'find duplicates in [folder]' to start now."
            result["guidance"] = (
                "Lead with the phone sync scenario — everyone relates. "
                "Emphasize safety steps prominently. "
                "If free: use pro_pitch with storage savings hook. "
                "If Pro: show quick_action. End with explore_next."
            )
            return result

        # ══════════════════════════════════════════════
        # AUTOMATION — Scheduler & Active Folders
        # ══════════════════════════════════════════════
        if topic == "automation":
            result = {
                "title": "⚡ Automation — Set It and Forget It",
                "intro": "Why organize manually when LocalLens does it automatically?",
                "two_modes": [
                    {
                        "mode": "🕐 Scheduled Sweeps",
                        "tool": "schedule_auto_organize",
                        "say": "\"Auto sort my camera folder every 6 hours\"",
                        "best_for": "Network drives, shared folders, weekly cleanup",
                        "how": "Every N hours, scans for NEW photos only. Already-sorted skipped.",
                    },
                    {
                        "mode": "⚡ Active Folder (Real-Time)",
                        "tool": "create_active_folder",
                        "say": "\"Watch my AirDrop folder and sort instantly\"",
                        "best_for": "AirDrop, phone sync, camera imports, screenshots",
                        "how": "Detects new photos THE INSTANT they land. Plus daily safety sweep.",
                    },
                ],
                "scenario": {
                    "title": "The AirDrop workflow",
                    "flow": [
                        "\"Watch my AirDrop folder and organize by date\"",
                        "→ Active folder created. Daemon running silently.",
                        "You AirDrop a photo from your phone...",
                        "→ 3 seconds later, it's in /2024/July/ — automatically ✨",
                        "\"Open the scheduler dashboard\" → Live web UI with timers",
                    ],
                },
                "management": [
                    "\"List my schedules\" → See status, timing, last run",
                    "\"Pause schedule X\" / \"Delete it\" → Full control",
                    "\"Trigger it now\" → Immediate sweep",
                    "\"Open the dashboard\" → Visual web UI with live countdown",
                ],
                "explore_next": [
                    {"topic": "organize", "label": "📂 Sorting options"},
                    {"topic": "privacy", "label": "🔒 How automation stays private"},
                    {"topic": "pro", "label": "⭐ See all Pro features"},
                ],
            }
            if not is_pro:
                result["tier"] = "pro"
                result["pro_pitch"] = {
                    "problem": "50 photos a day. End of month: 1,500 unsorted photos.",
                    "solution": "Set up once. Every photo auto-organizes the moment it arrives.",
                    "hook": "Like a personal photo librarian that never sleeps.",
                }
            else:
                result["tier"] = "pro ✅ (unlocked)"
                result["quick_action"] = "Try: 'Watch my [folder] and organize by location' or 'Auto sort every 2 hours'."
            result["guidance"] = (
                "Present the two modes as a clear comparison. Walk through the AirDrop scenario. "
                "Show management commands as a quick reference list. "
                "If free: 'personal librarian' hook. If Pro: quick_action. End with explore_next."
            )
            return result

        # ══════════════════════════════════════════════
        # PRIVACY — Deep dive
        # ══════════════════════════════════════════════
        if topic == "privacy":
            return {
                "title": "🔒 Privacy & Security",
                "intro": "This is why LocalLens exists. Not a feature — a principle.",
                "the_promise": [
                    "🖥️ Everything runs on YOUR machine — AI, sorting, face recognition",
                    "🌐 Zero internet for any feature (except one-time license activation)",
                    "📡 Zero outbound connections — verify with 'lsof -i'",
                    "📂 All data at ~/.config/LocalLens/ — nothing else, nowhere else",
                ],
                "what_is_stored": [
                    "Face encodings — 128 numbers per person (math, NOT images)",
                    "Path presets — Your saved folder pairs",
                    "Scheduler configs — Timing and folder settings",
                    "License key — Pro activation (if applicable)",
                ],
                "never_done": [
                    "❌ Photos NEVER uploaded anywhere",
                    "❌ Metadata NEVER sent to any server",
                    "❌ Face data NEVER leaves your machine",
                    "❌ No telemetry, no analytics, no tracking",
                    "❌ Originals NEVER modified — reads EXIF, doesn't write",
                ],
                "vs_others": {
                    "google_photos": "Uploads everything. Scans in their cloud. Trains their AI with your data.",
                    "icloud_photos": "Stored on Apple servers. Cloud processing for shared albums.",
                    "locallens": "Nothing leaves. Face math stays local. Delete the folder = gone forever.",
                },
                "verification": [
                    "🔓 Backend is fully open-source — read the code",
                    "🔓 MCP agent under BSL — publicly readable and auditable",
                    "🔓 Run 'lsof -i | grep LocalLens' — zero external connections",
                ],
                "explore_next": [
                    {"topic": "welcome", "label": "🏠 Back to main menu"},
                    {"topic": "organize", "label": "📂 Start organizing"},
                    {"topic": "pro", "label": "⭐ Free vs Pro"},
                ],
                "guidance": (
                    "Present confidently and directly. Lead with the promise. "
                    "The vs_others comparison is powerful — show it as a quick table. "
                    "End with: 'Your photos, your machine, your rules.'"
                ),
            }

        # ══════════════════════════════════════════════
        # PRO — Free vs Pro with professional upsell
        # ══════════════════════════════════════════════
        if topic == "pro":
            result = {"title": "⭐ Free vs Pro"}

            if is_pro:
                result["status"] = "🎉 You have Pro — everything is unlocked!"
                result["your_features"] = [
                    {"feature": "👤 Sort by People", "try": "\"Sort my photos by people\""},
                    {"feature": "👤 Enroll Faces", "try": "\"Add [name] to face recognition\""},
                    {"feature": "🗑️ Find Duplicates", "try": "\"Find duplicates in [folder]\""},
                    {"feature": "🗑️ Delete Duplicates", "try": "\"Delete those duplicates\""},
                    {"feature": "📊 Export Reports", "try": "\"Export a report\""},
                    {"feature": "🎨 Smart Albums", "try": "\"Suggest albums\""},
                    {"feature": "⏰ Scheduled Sweeps", "try": "\"Auto sort every 6 hours\""},
                    {"feature": "⚡ Active Folders", "try": "\"Watch my AirDrop folder\""},
                    {"feature": "📊 Dashboard", "try": "\"Open scheduler dashboard\""},
                ]
                result["guidance"] = (
                    "Celebrate! Present features as a quick-reference card with 'try it now' commands. "
                    "Make them feel like they're getting value. Ask which to explore."
                )
            else:
                result["free_tier"] = [
                    "✅ Sort by Date — Chronological folders",
                    "✅ Sort by Location — GPS-based sorting",
                    "✅ Analyze Folders — See what's inside",
                    "✅ Find & Group — Pull out specific photos",
                    "✅ Path Presets — Save favorites",
                    "✅ Open Folder — Quick access",
                    "✅ Stats & Status — Full overview",
                ]
                result["pro_showcase"] = [
                    {
                        "feature": "👤 Sort by People",
                        "problem": "10,000 photos, 50 people. Finding someone? Scroll for hours.",
                        "solution": "One click → everyone gets their own folder.",
                    },
                    {
                        "feature": "🗑️ Duplicate Cleanup",
                        "problem": "15-30% of your library is duplicates. Gigabytes wasted.",
                        "solution": "Scan, review, clean. Most users save 5-15 GB instantly.",
                    },
                    {
                        "feature": "⚡ Auto-Organize",
                        "problem": "Photos pile up. You forget to sort. Chaos returns.",
                        "solution": "Set once → photos organize THE INSTANT they arrive. Forever.",
                    },
                    {
                        "feature": "🎨 Smart Albums",
                        "problem": "You don't even know what albums to create.",
                        "solution": "AI suggests: 'Trip to Goa', 'Family 2023', 'Sunsets'.",
                    },
                ]
                result["cta"] = "One-time purchase. No subscription. Say 'activate my pro license' when ready."
                result["guidance"] = (
                    "Show Free tier as solid and valuable — don't make it feel limited. "
                    "Then present Pro features using problem→solution format. "
                    "Let the features sell themselves. CTA at the end, not pushy."
                )

            result["explore_next"] = [
                {"topic": "quickstart", "label": "🚀 Try something right now"},
                {"topic": "privacy", "label": "🔒 Privacy deep-dive"},
                {"topic": "welcome", "label": "🏠 Main menu"},
            ]
            return result

        # ══════════════════════════════════════════════
        # WHAT'S NEW — Updates, changelog, roadmap
        # ══════════════════════════════════════════════
        if topic == "whats_new":
            # Run update check in thread pool so it doesn't block the event loop
            update_info = await asyncio.to_thread(check_for_updates)

            result = {
                "title": "🆕 What's New in LocalLens",
                "installed_version": MCP_VERSION,
            }

            # ── Dynamic update section (from version.json) ─────────────
            if update_info and update_info.get("update_available"):
                latest_v = update_info["latest_version"]
                cmd = update_info.get("upgrade_command", "pip install --upgrade locallens-mcp")
                notes_url = update_info.get("release_notes_url", "https://locallens.app/changelog")
                highlights = update_info.get("highlights", [])

                result["update"] = {
                    "available": True,
                    "latest_version": latest_v,
                    "is_critical": update_info.get("is_critical", False),
                    "highlights": highlights,
                    "upgrade_command": cmd,
                    "release_notes_url": notes_url,
                }
            else:
                result["update"] = {"available": False}

            # ── What shipped in your current version ───────────────────
            result["your_version_includes"] = {
                "version": MCP_VERSION,
                "date": "July 2026",
                "features": [
                    "📂 Smart sorting by date, location, and people",
                    "👤 Face recognition with enrollment and search",
                    "🗑️ Duplicate detection and safe cleanup",
                    "⚡ Scheduled auto-organize and real-time folder watching",
                    "📊 Export reports for organized collections",
                    "🔒 100% local — zero data leaves your machine",
                ],
            }

            # ── Roadmap (hardcoded — updated each release) ─────────────
            # If a coming_soon item appears in the update highlights, it's no longer "coming soon"
            update_highlights_lower = set()
            if update_info and update_info.get("highlights"):
                update_highlights_lower = {h.lower() for h in update_info["highlights"]}

            roadmap_items = [
                {
                    "feature": "🎨 Smart Album Suggestions",
                    "status": "In Development",
                    "description": "AI-powered album ideas based on your photo history.",
                    "eta": "Next update",
                },
                {
                    "feature": "💬 Built-in Chat UI",
                    "status": "Planned",
                    "description": (
                        "A local chat interface powered by Ollama — "
                        "organize photos without needing Claude Desktop."
                    ),
                    "eta": "Coming soon",
                },
                {
                    "feature": "📱 Mobile Companion",
                    "status": "Exploring",
                    "description": "Send photos from your phone directly to LocalLens.",
                    "eta": "Future",
                },
            ]

            # Filter out roadmap items that appear in the update's highlights
            result["coming_soon"] = []
            for item in roadmap_items:
                feature_name = item["feature"].split(" ", 1)[-1].lower()  # strip emoji
                is_released = any(feature_name in h for h in update_highlights_lower)
                if not is_released:
                    result["coming_soon"].append(item)

            # ── Pro perks ──────────────────────────────────────────────
            if is_pro:
                result["pro_insider"] = {
                    "badge": "⭐ Pro Member",
                    "message": "You'll get early access to new features as soon as they're ready.",
                    "perks": [
                        "Early access to beta features",
                        "Priority support",
                        "Shape the roadmap — your feedback matters most",
                    ],
                }
            else:
                result["pro_teaser"] = {
                    "message": (
                        "Pro members get early access to upcoming features. "
                        "Upgrade anytime to be first in line!"
                    ),
                }

            result["feedback"] = {
                "message": "Have a feature request or found a bug? Let us know!",
                "url": "https://locallens.app/feedback",
            }
            result["explore_next"] = [
                {"topic": "quickstart", "label": "🚀 Try something right now"},
                {"topic": "pro", "label": "⭐ Free vs Pro"},
                {"topic": "welcome", "label": "🏠 Main menu"},
            ]

            # ── Guidance — tells the LLM exactly how to format the response ──
            if update_info and update_info.get("update_available"):
                latest_v = update_info["latest_version"]
                cmd = update_info.get("upgrade_command", "pip install --upgrade locallens-mcp")
                notes_url = update_info.get("release_notes_url", "https://locallens.app/changelog")
                highlights = update_info.get("highlights", [])
                highlights_bullets = "\n".join(f"  - {h}" for h in highlights)
                is_critical = update_info.get("is_critical", False)

                result["guidance"] = (
                    f"{'🚨 CRITICAL — ' if is_critical else ''}"
                    "Show the update section FIRST and PROMINENTLY. "
                    "Format it exactly like this:\n\n"
                    f"---\n"
                    f"## {'🚨 Critical Update Required' if is_critical else '✨ Update Available'} — v{latest_v}\n\n"
                    f"{'**Your version is no longer supported.** ' if is_critical else ''}"
                    f"You are on `{MCP_VERSION}` → **`{latest_v}`** is available.\n\n"
                    f"### What's new:\n"
                    f"{highlights_bullets}\n\n"
                    f"### Upgrade in 2 steps:\n"
                    f"1. Open your terminal and run:\n"
                    f"```\n{cmd}\n```\n"
                    f"2. Restart Claude Desktop\n\n"
                    f"[📋 Full release notes]({notes_url})\n\n"
                    f"---\n\n"
                    "THEN show the 'coming_soon' roadmap items (if any remain after filtering). "
                    "If the user is Pro, show pro_insider warmly. "
                    "End with explore_next as a numbered menu."
                )
            else:
                result["guidance"] = (
                    "You're on the latest version — show 'your_version_includes' as a brief feature list. "
                    "Then show 'coming_soon' roadmap items with emoji status badges. "
                    "If the user is Pro, highlight their pro_insider perks warmly. "
                    "If not Pro, mention the pro_teaser casually (never pushy). "
                    "End with the feedback link and explore_next menu."
                )

            return result

        # ══════════════════════════════════════════════
        # FALLBACK — handles "all" and unknown topics
        # ══════════════════════════════════════════════
        # For backward compatibility: "all" redirects to welcome
        if topic == "all":
            return await locallens_help("welcome")

        return {
            "error": f"Unknown topic: '{topic}'",
            "available_topics": [
                "welcome", "quickstart", "organize", "find",
                "people", "duplicates", "automation", "privacy", "pro", "whats_new"
            ],
            "guidance": "Show the user the available topics and ask what they'd like to explore.",
        }


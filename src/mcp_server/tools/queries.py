import os
import httpx
from mcp.server.fastmcp import FastMCP
import mcp.types as types
from typing import List, Dict, Any, Optional

from ..config import get_locallens_url

# Must match backend/organizer_logic.py SUPPORTED_EXTENSIONS exactly
SUPPORTED_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
    '.heic', '.heif',
    '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf',
    '.avif',
    '.psd', '.hdr'
)

def _handle_error(e: Exception) -> Dict[str, Any]:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            return {"error": e.response.json()}
        except ValueError:
            return {"error": e.response.text}
    return {"error": str(e)}


async def resolve_path_preset(value: str, side: str = "source") -> Dict[str, Any]:
    """
    Turn a folder argument into a real path, accepting a saved preset NAME as well as a path.

    Prose alone could not keep the assistant reaching for get_path_presets — the rule telling it
    to lived in the server `instructions` blob, past the point where the client truncates (see
    main.py). This is the same rule enforced in code, so a preset name works even when no prose
    survives the trip.

    Returns one of:
        {"path": "/real/path"}     - use this; either it was already a directory, or the value
                                     matched a saved preset name
        {"error": ...}             - not a directory and not a known preset; the message lists
                                     the saved preset names so the caller can pick one

    `side` picks which half of the preset to return ("source" or "destination").

    Deliberately narrow: a preset is only substituted when `value` is NOT an existing directory,
    so a real path always wins and nothing is silently redirected. Substituting a path the user
    saved themselves is not the same as inventing one.
    """
    expanded = os.path.expanduser((value or "").strip())
    if os.path.isdir(expanded):
        return {"path": expanded}

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{get_locallens_url()}/api/presets/paths", timeout=5)
            r.raise_for_status()
            presets = r.json() or {}
    except Exception:
        # Backend unreachable — say the path is bad, not that presets are broken.
        return {"error": f"'{value}' is not an existing folder."}

    if not isinstance(presets, dict):
        return {"error": f"'{value}' is not an existing folder."}

    needle = (value or "").strip().lower()
    for name, paths in presets.items():
        if name.strip().lower() == needle and isinstance(paths, dict):
            stored = paths.get(side)
            if stored:
                return {"path": os.path.expanduser(stored), "resolved_from_preset": name}

    known = ", ".join(f'"{n}"' for n in presets) or "none saved yet"
    return {
        "error": (
            f"'{value}' is not an existing folder, and no saved path preset has that name. "
            f"Saved presets: {known}. Ask the user which one they meant, or ask for the full "
            f"path — do not guess."
        )
    }


def _scan_subfolders(root: str, ignore_set: set) -> List[Dict[str, Any]]:
    """Walk root and return a list of immediate subfolders with supported photo counts."""
    subfolders = []
    try:
        for entry in sorted(os.scandir(root), key=lambda e: e.name.lower()):
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            abs_path = entry.path
            if abs_path in ignore_set:
                continue
            # Count supported files recursively inside this subfolder
            count = 0
            for dirpath, _, filenames in os.walk(abs_path):
                if dirpath in ignore_set:
                    continue
                for f in filenames:
                    if f.lower().endswith(SUPPORTED_EXTENSIONS):
                        count += 1
            subfolders.append({
                "name": entry.name,
                "path": abs_path,
                "supported_files": count
            })
    except PermissionError:
        pass
    return subfolders


def _count_top_level_files(root: str) -> int:
    """Count supported image files directly in root (not in subfolders)."""
    count = 0
    try:
        for entry in os.scandir(root):
            if entry.is_file() and entry.name.lower().endswith(SUPPORTED_EXTENSIONS):
                count += 1
    except PermissionError:
        pass
    return count


def register_queries(mcp: FastMCP):
    
    @mcp.tool()
    async def get_enrolled_faces() -> Dict[str, Any]:
        """
        Get a list of all people enrolled in the face recognition system, along with the count of images for each person.
        Use this when asked 'who have I enrolled' or 'which faces do you know'.
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{get_locallens_url()}/api/enrolled-faces", timeout=5)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def get_path_presets() -> Dict[str, Any]:
        """
        Look up the user's saved folder paths by the NAME they gave them.

        A "path preset" is a named source → destination pair the user saved earlier via
        remember_paths. Users refer to them by name and expect you to know the paths:
        - "use my bot testing preset"      - "sort my work photos folder"
        - "the usual folder" / "same as last time"
        - "use my saved paths" / "my LL presets"

        CALL THIS WHENEVER THE USER NAMES A FOLDER INSTEAD OF TYPING A PATH.
        The name they say ("Bot testing") is not a path — this tool is how you turn it into one.
        Do not ask the user to re-type a path they already saved, and do not guess a path from
        the preset's name; look it up here first.

        Returns a mapping of preset name → paths:
            {"Bot testing": {"source": "/Users/me/Photos/inbox",
                             "destination": "/Users/me/Photos/sorted"}}

        Match the user's wording to a preset name case-insensitively ("bot testing" → "Bot
        testing"). If several could match, show the names and ask which. If none match, show
        the names you did find rather than inventing a path.

        The user may override one side while still meaning the preset for the other — e.g.
        "use my bot testing preset but put results in /tmp/out" means the preset's source with
        their explicit destination.
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{get_locallens_url()}/api/presets/paths", timeout=5)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return _handle_error(e)

    @mcp.tool()
    async def analyse_folder(
        source_folder: str,
        ignore_list: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse my folder — scan a photo folder to see what's inside before sorting.
        Use this to check a folder, see its contents, count photos, list subfolders, and determine if sorting by Date/Location/People would work.

        The scan runs on the user's own machine, so there is no upload step — pass the
        folder path straight through.

        Use this BEFORE start_sorting or start_find_group to:
        1. Show the user what subfolders exist and how many photos each has
        2. Ask the user which subfolders to ignore (build the ignore_list for start_sorting)
        3. Confirm if Location/People/Date sort is viable based on metadata

        RESPONSE FIELDS:
        - subfolders: list of {name, path, supported_files} for each subfolder
            → If this list is non-empty, PRESENT it to the user and ASK which (if any) to skip
            → If this list is empty, no subfolders exist — proceed without asking
        - top_level_files: count of supported images directly in root (not in subfolders)
        - total_supported_files: sum of all supported images across root + all subfolders
        - locations: GPS location strings in "CC/State/City" format from EXIF
        - dates: nested dict { "YYYY": ["MM", ...] } from EXIF date tags
        - people: enrolled person names whose faces were DETECTED in this folder

        CRITICAL BEHAVIOR FOR LLMs:
        - If subfolders is non-empty → ALWAYS present the list and ask user which to ignore before sorting
        - If subfolders is empty → just proceed, don't ask about ignore_list
        - If people is empty → BLOCK People sort. Tell user: "No faces enrolled. Enroll someone first
          or try Date/Location sort." DO NOT proceed with primary_sort="People" — it wastes time
          and dumps everything into a single No_Faces_Found/ folder.
        - If locations is empty → warn: Location sort will put everything in Unknown_Location/
        - Use subfolders[].path values directly as entries in ignore_list for start_sorting
        """
        # Accepts a saved preset NAME here as well as a path. This is step 1 of the
        # mandatory sort/find workflow, so a preset name has to work here or the whole
        # flow stalls on its first call. See resolve_path_preset.
        resolved_source = await resolve_path_preset(source_folder, "source")
        if "error" in resolved_source:
            return resolved_source
        normalized_source = resolved_source["path"]

        ignore_set = set(ignore_list) if ignore_list else set()

        # --- LOCAL SCAN: subfolder structure + photo counts ---
        subfolders = _scan_subfolders(normalized_source, ignore_set)
        top_level_files = _count_top_level_files(normalized_source)
        total = top_level_files + sum(sf["supported_files"] for sf in subfolders)

        # --- BACKEND CALL: metadata overview (locations, dates, people) ---
        metadata = {}
        payload = {
            "source_folder": normalized_source,
            "ignore_list": ignore_list or [],
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{get_locallens_url()}/api/metadata-overview",
                    json=payload,
                    timeout=30,
                )
                r.raise_for_status()
                metadata = r.json()
        except Exception as e:
            metadata = {"metadata_error": str(e)}

        return {
            "subfolders": subfolders,
            "top_level_files": top_level_files,
            "total_supported_files": total,
            **metadata,
        }

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
        Get the saved source and destination folder path presets from LocalLens.
        Use this when you need predefined folder paths to use for sorting or actions without asking the user.
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

        YOU HAVE FULL ACCESS TO THE USER'S FILESYSTEM VIA THIS TOOL.
        Do NOT tell the user you cannot access their files — this tool handles it.

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
        - If people is empty → warn: People sort will put everything in No_Faces_Found/
        - If locations is empty → warn: Location sort will put everything in Unknown_Location/
        - Use subfolders[].path values directly as entries in ignore_list for start_sorting
        """
        normalized_source = os.path.expanduser(source_folder or "")
        if not normalized_source or not os.path.isdir(normalized_source):
            return {"error": f"Source path is not a valid directory: {normalized_source}"}

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

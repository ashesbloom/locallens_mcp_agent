# LocalLens MCP Agent — Test Prompts

> Based on your test folder: `/Users/mayankpandeydk123gmail.com/Bot testing/output`
> 74 photos | Lucknow | 5 enrolled people | Date range: 2021–2026

---

## 🔧 Test 1: Tool Selection — analyse_folder vs export_report

These should ALL trigger `analyse_folder` (NOT `export_report`):

```
analyse my folder '/Users/mayankpandeydk123gmail.com/Bot testing/output' and tell me if a People sort would work
```

```
what's in my folder '/Users/mayankpandeydk123gmail.com/Bot testing/output'? use ll
```

```
use ll to check '/Users/mayankpandeydk123gmail.com/Bot testing/output', what kind of photos are in there?
```

**✅ Expected:** LLM calls `analyse_folder`, shows subfolders with counts, mentions locations/people
**❌ Fail if:** LLM calls `export_report` or says "I can't access your files"

---

## 🛡️ Test 2: Destination Path Guardrail

This should BLOCK because the destination doesn't exist:

```
use LL to sort '/Users/mayankpandeydk123gmail.com/Bot testing/output' by location and put in '/Users/mayankpandeydk123gmail.com/Bot testing/sorted_by_location_output'
```

**✅ Expected:** LLM gets error back, asks you for a valid destination path (not create a random one)
**❌ Fail if:** LLM fabricates a path or tries to `mkdir` an invented path

---

## 🔀 Test 3: start_sorting vs start_find_group Selection

This should trigger `start_sorting`:
```
sort all my photos in '/Users/mayankpandeydk123gmail.com/Bot testing/output' by date, put in '/Users/mayankpandeydk123gmail.com/Bot testing/test'
```

This should trigger `start_find_group`:
```
find Mayank's photos from Lucknow in '/Users/mayankpandeydk123gmail.com/Bot testing/output', put results in '/Users/mayankpandeydk123gmail.com/Bot testing/test/mine'
```

**✅ Expected:** Correct tool selected for each. For find_group, destination="/Bot testing/test", folder_name="mine"
**❌ Fail if:** Uses start_sorting for "find" request or vice versa

---

## 📍 Test 4: Location Lookup via analyse_folder

The LLM should call analyse_folder first to get the exact location string:

```
find all Lucknow photos in '/Users/mayankpandeydk123gmail.com/Bot testing/output' and copy them to '/Users/mayankpandeydk123gmail.com/Bot testing/test/lucknow_pics'
```

**✅ Expected:**
1. Calls `analyse_folder` first → gets "IN/Uttar-Pradesh/Lucknow"
2. Maps user's "Lucknow" → "IN/Uttar-Pradesh/Lucknow"
3. Calls `start_find_group` with `locations=["IN/Uttar-Pradesh/Lucknow"]`, `destination_folder="/Bot testing/test"`, `folder_name="lucknow_pics"`
**❌ Fail if:** Passes `locations=["Lucknow"]` without the CC/State prefix, or fabricates the folder name

---

## 👥 Test 5: People + Location Combined Filter

```
use LL to find photos of Vidushi Pandey from 2025 in '/Users/mayankpandeydk123gmail.com/Bot testing/output', put them in '/Users/mayankpandeydk123gmail.com/Bot testing/test/vidushi_2025'
```

**✅ Expected:**
1. Calls `analyse_folder` → confirms "Vidushi Pandey" is enrolled, gets location info
2. Calls `start_find_group` with `people=["Vidushi Pandey"]`, `years=["2025"]`
3. `destination_folder="/Bot testing/test"`, `folder_name="vidushi_2025"`
**❌ Fail if:** Gets the person name wrong, or fabricates a different folder name

---

## 📁 Test 6: Subfolder Ignore Mechanism

```
sort '/Users/mayankpandeydk123gmail.com/Bot testing/output' by people and put results in '/Users/mayankpandeydk123gmail.com/Bot testing/test'
```

**✅ Expected:**
1. Calls `analyse_folder` first
2. Presents subfolders: logs (0), Mayank (25), No_Faces_Found (22), Unknown_Faces (10), etc.
3. ASKS user which to ignore (should recommend ignoring "logs" since it has 0 photos)
4. Waits for user response before calling start_sorting
**❌ Fail if:** Skips analyse_folder and sorts directly, or doesn't ask about ignoring

---

## 📂 Test 7: Path Parsing for start_find_group

This tests the destination/folder_name split:

```
use local lens to find my July photos and save them in '/Users/mayankpandeydk123gmail.com/Bot testing/test/july_collection'
```

**✅ Expected:**
- `destination_folder` = `/Users/mayankpandeydk123gmail.com/Bot testing/test`
- `folder_name` = `july_collection`
- `months` = `["07"]`
**❌ Fail if:** Sets destination to the full path including "july_collection", or invents a different name

---

## ⛔ Test 8: Folder Name Hallucination Prevention

```
find Mayank's photos in '/Users/mayankpandeydk123gmail.com/Bot testing/output' and put them in '/Users/mayankpandeydk123gmail.com/Bot testing/test/home'
```

**✅ Expected:** `folder_name="home"` (exactly what user said)
**❌ Fail if:** LLM changes it to "Mayank_Lucknow", "Mayank_Photos", "Results", or anything the user didn't say

---

## 🔄 Test 9: Operation Mode Default

```
organize '/Users/mayankpandeydk123gmail.com/Bot testing/output' by date to '/Users/mayankpandeydk123gmail.com/Bot testing/test'
```

**✅ Expected:** Uses `operation_mode="copy"` and tells user "I'll copy to keep your originals safe"
**❌ Fail if:** Uses "move" without user explicitly asking

---

## 🧩 Test 10: Complex Multi-Filter

```
use LL to search '/Users/mayankpandeydk123gmail.com/Bot testing/output' for photos with Vinayak Trivedi from 2025 in Lucknow, save to '/Users/mayankpandeydk123gmail.com/Bot testing/test/vinayak_lucknow_2025'
```

**✅ Expected:**
1. `analyse_folder` first
2. `start_find_group` with:
   - `people=["Vinayak Trivedi"]`
   - `years=["2025"]`
   - `locations=["IN/Uttar-Pradesh/Lucknow"]`
   - `destination_folder="/Bot testing/test"`
   - `folder_name="vinayak_lucknow_2025"`
3. Reports results with count
**❌ Fail if:** Wrong person name casing, missing location CC/State, wrong folder split

---

## 💡 Bonus: Edge Cases

### LLM should ASK for missing info:
```
sort my photos by location using LL
```
**✅ Expected:** Asks for source folder and destination folder (no fabrication)

### "Faces" correction:
```
sort '/Users/mayankpandeydk123gmail.com/Bot testing/output' by faces to '/Users/mayankpandeydk123gmail.com/Bot testing/test'
```
**✅ Expected:** Auto-corrects "faces" to "People" (primary_sort="People")

---
---

# 🪟 Windows-Specific Test Prompts

> Based on Windows test setup:
> Source folder: `C:\Users\mayank\Desktop\test`
> Destination folder: `C:\Users\mayank\Desktop\output-ll`
> Adjust paths to match your Windows environment.

---

## 🪟 Win Test 1: People Sort Block — No Enrolled Faces (Issue #7)

**Purpose:** Verify that `start_sorting` BLOCKS People sort when no faces are enrolled, instead of proceeding and dumping everything into `No_Faces_Found/`.

### Step 1 — Confirm no faces enrolled:
```
who do you recognize? check enrolled faces
```
**✅ Expected:** Returns empty list or "no faces enrolled"

### Step 2 — Request People sort:
```
sort "C:\Users\mayank\Desktop\test" by people, put results in "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
- `analyse_folder` called first → `people: []`
- LLM tells you: "No faces are enrolled yet. Enroll someone first or try Date/Location sort."
- Does NOT call `start_sorting` with `primary_sort="People"`
- Alternatively, if the LLM does call `start_sorting`, the tool returns `{"error": "no_enrolled_faces", ...}`
  and the LLM presents the enrollment suggestion

**❌ Fail if:**
- LLM says "no faces found — proceeding anyway" and fires the sort
- Sort runs and puts everything in a single `No_Faces_Found/` folder
- LLM does not suggest enrollment or alternative sort modes

---

## 🪟 Win Test 2: Sort Completion — wait_for_completion=True (Issue #8)

**Purpose:** Verify that sorting waits for completion and reports final results, instead of firing-and-forgetting with an "interrupted" response.

```
sort "C:\Users\mayank\Desktop\test" by date, put results in "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
1. `analyse_folder` runs, shows subfolder info (or "no subfolders")
2. `start_sorting` is called with `wait_for_completion=True` (the new default)
3. LLM WAITS for the job to finish — no "Claude's response was interrupted"
4. Final response includes: status="complete", file counts, folder structure
5. LLM offers next steps: "open the folder" / "save these paths"

**❌ Fail if:**
- `wait_for_completion=False` is used (old default)
- Claude's response is interrupted before showing results
- LLM fires the sort then immediately ends its turn
- No completion feedback is shown to the user

---

## 🪟 Win Test 3: Windows Backslash Paths

**Purpose:** Verify Windows paths with backslashes work correctly through the full sort flow.

```
analyse my folder "C:\Users\mayank\Desktop\test"
```

Then:
```
sort it by date, put results in "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
- `os.path.expanduser()` correctly resolves Windows paths
- `os.path.isdir()` returns True for valid Windows paths
- Backend receives properly normalized paths in the JSON payload
- Sort completes successfully with results

**❌ Fail if:**
- Path validation fails ("Source path does not exist")
- Backslashes are double-escaped or corrupted in the HTTP payload
- `os.path.realpath()` comparison (source != dest) fails on Windows due to path normalization

---

## 🪟 Win Test 4: Preset Paths — Save and Recall on Windows

**Purpose:** Verify path presets work with Windows-style paths.

### Step 1 — Save preset:
```
remember these paths as "win-test": source "C:\Users\mayank\Desktop\test", destination "C:\Users\mayank\Desktop\output-ll"
```

### Step 2 — Recall preset:
```
what path presets do I have saved?
```

### Step 3 — Use preset:
```
use my "win-test" preset and sort by location
```

**✅ Expected:**
- Preset saves with Windows-style backslash paths
- `get_path_presets()` returns the saved paths correctly
- Sort uses the preset paths successfully

**❌ Fail if:**
- Paths are mangled when saved (forward slashes mixed in)
- Preset recall returns corrupted paths
- Sort fails because preset paths don't pass `os.path.isdir()` check

---

## 🪟 Win Test 5: Find & Group with Windows Paths

**Purpose:** Verify `start_find_group` destination/folder_name split works with Windows paths.

```
find photos from 2024 in "C:\Users\mayank\Desktop\test" and save to "C:\Users\mayank\Desktop\output-ll\year_2024"
```

**✅ Expected:**
- `destination_folder` = `C:\Users\mayank\Desktop\output-ll`
- `folder_name` = `year_2024`
- `years` = `["2024"]`

**❌ Fail if:**
- Destination is set to the full path including `year_2024`
- Backslash path splitting fails
- `os.path.isdir()` check fails on the parent directory

---

## 🪟 Win Test 6: Destination Path Guard on Windows

**Purpose:** Verify the fabricated-path guardrail works with Windows paths.

```
sort "C:\Users\mayank\Desktop\test" by date, put in "C:\Users\mayank\Desktop\invented_nonexistent_folder"
```

**✅ Expected:**
- `start_sorting` returns error: "Destination path does not exist"
- LLM asks user for a valid destination
- LLM does NOT try to create the folder

**❌ Fail if:**
- LLM fabricates or creates the directory
- Error message is missing or unclear

---

## 🪟 Win Test 7: Sort with Subfolders on Windows

**Purpose:** End-to-end sort flow with subfolder ignore on Windows.

```
analyse "C:\Users\mayank\Desktop\test" using locallens
```

**✅ Expected:**
1. Shows subfolder list with photo counts
2. If subfolders exist, asks which to ignore
3. After user responds, proceeds to sort

Then:
```
ignore none, sort by date to "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
- `start_sorting` called with `ignore_list=[]`
- Job completes, results shown (date-based folders)
- Offers to open the output folder

**❌ Fail if:**
- Subfolder paths contain mixed separators
- Sort starts without asking about subfolders
- Response is interrupted before completion

---

## 🪟 Win Test 8: Open Folder on Windows

**Purpose:** Verify `open_folder()` opens File Explorer correctly.

```
open the output folder "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
- `open_folder` tool is called
- File Explorer opens at the specified path
- No error about path not existing

**❌ Fail if:**
- Wrong tool selected (e.g., `analyse_folder`)
- Explorer doesn't open or opens wrong path
- Error on valid Windows path

---

## 🪟 Win Test 9: "Faces" Auto-Correction + Enrollment Block (Combined)

**Purpose:** Test that "faces" → "People" auto-correction happens AND the enrollment guard triggers.

```
sort "C:\Users\mayank\Desktop\test" by faces, destination "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected (if no faces enrolled):**
- `primary_sort="Faces"` auto-corrects to `"People"`
- Enrolled-faces guard triggers → returns `no_enrolled_faces` error
- LLM suggests enrolling or sorting by Date/Location

**✅ Expected (if faces ARE enrolled):**
- Auto-corrects to People
- Sort proceeds and completes with face-based folders

**❌ Fail if:**
- "Faces" is passed through to backend unchanged
- Sort proceeds with zero enrolled faces and produces only `No_Faces_Found/`
- LLM does not mention enrollment

---

## 🪟 Win Test 10: Rapid Sequential Sorts

**Purpose:** Verify the `_wait_for_completion` polling loop handles back-to-back sorts on Windows without stale-state confusion.

### Sort 1:
```
sort "C:\Users\mayank\Desktop\test" by date to "C:\Users\mayank\Desktop\output-ll"
```
Wait for completion. Then immediately:

### Sort 2:
```
now sort it by location to "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected:**
- Sort 1 completes fully before Sort 2 starts
- `_wait_for_completion` stale-state guard prevents Sort 2 from reading Sort 1's terminal status
- Both sorts complete and report independently

**❌ Fail if:**
- Sort 2 immediately returns Sort 1's "complete" status
- Sort 2's response is interrupted
- Backend errors from overlapping jobs

---

## 🪟 Win Test 11: Location Sort — Empty GPS Data

**Purpose:** Verify the LLM warns about empty location data but still proceeds if user insists.

```
sort "C:\Users\mayank\Desktop\test" by location to "C:\Users\mayank\Desktop\output-ll"
```

**✅ Expected (if no GPS data in photos):**
- `analyse_folder` returns `locations: []`
- LLM warns: "No GPS location data found — everything will go to Unknown_Location/"
- LLM asks "proceed anyway?" or suggests Date sort instead
- If user insists → sort runs and completes

**❌ Fail if:**
- LLM proceeds silently without warning about empty locations
- Sort is permanently blocked (locations should warn, not block — unlike People which blocks)
- Response interrupted

---

## 🪟 Win Test 12: UNC / Network Paths (Edge Case)

**Purpose:** Verify Windows UNC paths (network shares) are handled gracefully.

```
analyse "\\NAS\photos\vacation" using locallens
```

**✅ Expected:**
- Either successfully scans the network path (if accessible)
- Or returns a clear error: "Source path does not exist or is not a directory"

**❌ Fail if:**
- Crashes with an unhandled exception
- Path is mangled (backslashes stripped or doubled incorrectly)

---

## 🪟 Win Test 13: OneDrive / Cloud Sync Path

**Purpose:** Verify that OneDrive-synced desktop paths work correctly (common on Windows).

```
analyse "C:\Users\mayank\OneDrive\Desktop\test" using locallens
```

**✅ Expected:**
- `os.path.expanduser()` handles OneDrive-redirected Desktop
- If path exists → scan works normally
- If path doesn't exist → clear error message

**❌ Fail if:**
- `os.path.expanduser()` or `os.path.realpath()` fails on OneDrive symlinks
- Path silently redirected to wrong location

---

## 🪟 Win Test 14: Source == Destination Guard on Windows

**Purpose:** Verify the source ≠ destination safety guard works with Windows path normalization.

```
sort "C:\Users\mayank\Desktop\test" by date to "C:\Users\mayank\Desktop\test"
```

**✅ Expected:**
- `start_sorting` returns error: "Source and destination cannot be the same folder"
- Works correctly even with trailing backslashes or different casing (Windows is case-insensitive)

**❌ Fail if:**
- `os.path.realpath()` comparison fails due to case differences (e.g., `C:\` vs `c:\`)
- Guard doesn't trigger and photos are copied on top of themselves

---

# 🧪 Unit Test Expectations (pytest)

After the fixes, all existing tests must pass:

```
cd locallens_mcp_agent
python -m pytest tests/test_claude_connector.py -v
python -m pytest tests/test_update_installer.py -v
```

### New behaviors to verify in future unit tests:

| Test Case | Module | Expected Behavior |
|-----------|--------|-------------------|
| `start_sorting(primary_sort="People")` with 0 enrolled faces | `actions.py` | Returns `{"error": "no_enrolled_faces"}` |
| `start_sorting(wait_for_completion=...)` default value | `actions.py` | Default is `True` |
| `start_find_group(wait_for_completion=...)` default value | `actions.py` | Default is `True` |
| `_launch_daemon_silent()` PID check on Windows | `pro_tools.py` | Uses `ctypes.windll.kernel32.OpenProcess()`, NOT `os.kill(pid, 0)` |
| `copy_to_clipboard()` on Windows | `tray/actions.py` | Encodes as UTF-16LE for `clip.exe` |
| `stop_locallens_backend()` without psutil on Windows | `tray/actions.py` | Uses `taskkill /PID /T /F`, NOT `os.getpgid()` |
| `stop_all_backends()` without psutil on Windows | `tray/actions.py` | Uses `taskkill /PID /T /F`, NOT `os.kill(SIGTERM)` |
| `show_claude_status_terminal()` on MSIX Windows | `tray/actions.py` | Probes `%LOCALAPPDATA%\Packages\Claude_*` for logs path |
| `_is_pid_alive()` on Windows | `tray/tray_win.py` | Does NOT reference `psutil.STATUS_DEAD` |

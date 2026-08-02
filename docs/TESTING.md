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

# 🚀 Revolutionary Use Case Tests

> These aren't correctness tests for a single tool — they're conversational flows that only make sense because the assistant, not a fixed UI, is driving. Each one is "old way vs. new way": what a normal photo app forces you to click through, versus what this does in a sentence. Grounded in shipped tools only (see the corrected `Marketing Needed` section above — no smart albums, no Ollama Chat UI claims here).

## Test 11: Multi-Person Enrollment in One Message

**Old way:** face-tagging wizards make you add one person at a time, click-by-click.

```
enroll two people using LL: Priya from '/Users/mayankpandeydk123gmail.com/Bot testing/faces/priya', and Raj from '/Users/mayankpandeydk123gmail.com/Bot testing/faces/raj'
```

**✅ Expected:** Single `add_face_enroll` call with `{"Priya": ".../priya", "Raj": ".../raj"}` — not two separate calls, not a double-nested `{"enrollments": {...}}` dict.
**❌ Fail if:** Only enrolls one person, asks the user to repeat the request per-person, or produces the double-nested dict bug the guard in `pro_tools.py` exists to catch.

---

## Test 12: Judgment-Based Duplicate Cleanup (Staged, Not Blind)

**Old way:** duplicate finders show a report, then a single "delete all" button with no room for a threshold conversation.

```
find duplicates in '/Users/mayankpandeydk123gmail.com/Bot testing/output' using LL, but only show me what's over 95% similar before deleting anything
```

**✅ Expected:** Calls `find_duplicates`, presents the matches above the requested threshold, and explicitly waits for confirmation before ever calling `delete_duplicates`.
**❌ Fail if:** Deletes without confirmation, ignores the similarity threshold, or treats "show me" as permission to delete.

---

## Test 13: Mid-Job Abort by Just Saying Stop

**Old way:** the only "cancel" for a runaway sort is force-quitting the app.

```
[mid-sort] actually stop that, I picked the wrong folder
```

**✅ Expected:** Calls `abort_job` for the active job, confirms it stopped, and does not silently let the original sort keep running in the background.
**❌ Fail if:** Ignores the interruption and lets the job finish, or calls `abort_job` on the wrong/stale job.

---

## Test 14: Conversational Schedule Editing (No Settings Dig)

**Old way:** changing a recurring task means reopening a settings screen and finding the right toggle again.

```
Step 1: schedule a weekly date-sort for '/Users/mayankpandeydk123gmail.com/Bot testing/output' every Sunday, using LL
Step 2 (later turn): actually pause that Sunday job for the next two weeks
```

**✅ Expected:** Step 1 calls `schedule_auto_organize`. Step 2 calls `list_schedules` to find the right job (using conversational memory, not asking the user to re-supply the schedule ID from scratch) then `manage_schedule` to pause it.
**❌ Fail if:** Step 2 asks the user to look up and paste a schedule ID/name it already has from Step 1, or creates a duplicate schedule instead of modifying the existing one.

---

## Test 15: Driving LocalLens From Inside a Coding Session (Cross-App Crossover)

**Old way:** photo organizing means alt-tabbing out to a dedicated app.

```
[in Cursor, mid coding-session] before I forget — clean up the screenshots in '/Users/mayankpandeydk123gmail.com/Bot testing/output' by date using LL
```

**✅ Expected:** Same `start_sorting` call and guardrails as in Claude Desktop — no LocalLens-specific setup needed inside Cursor beyond the MCP connection already existing.
**❌ Fail if:** Tool behaves differently or is missing entirely outside Claude Desktop (would indicate a Claude-Desktop-specific assumption leaking into tool code, which breaks the "works in any MCP client" claim).

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

--

# 📣 Marketing Needed (Features)

> Niche/unique/revolutionary angles surfaced by reading `for LLM's/`, `docs/`, and the tool source. These are real capabilities, not aspirational copy — each maps to a shipped tool. Full campaign material lives in [`marketing/`](../marketing/).

- **The only photo organizer you can talk to, that never talks back to the cloud.** LocalLens exposes itself as an MCP server — the same protocol Claude Desktop, Cursor, and any future agentic client speak. "Sort my Lucknow trip by who's in it" is a sentence, not a settings dialog, and it never leaves the machine (one-time license ping aside).
- **Works in any MCP client, forever.** Most "AI-powered" desktop apps bolt a chatbot onto their own UI. LocalLens built the AI surface as a standard MCP server instead — so it already works in Claude Desktop today and in whatever agentic client ships next, with zero app-side changes. That's a genuine first-mover angle: "MCP-native" as a badge, not a buzzword.
- **Conversational multi-filter photo search ("Spotlight for photos").** `start_find_group` combines person + location + date in one request — "find Vidushi's 2025 photos from Lucknow" — something no drag-and-drop photo app UI does in one step.
- **The assistant remembers your library, not just the last message.** Path presets and enrolled faces persist across turns (`notes_and_nomenclature.md` §3) — the LLM doesn't re-ask "which folder?" every time, which is the difference between a demo and a tool people keep using.
- **Set-and-forget autonomous organizing, described in English (Pro scheduler).** `schedule_auto_organize` / `manage_schedule` / `list_schedules` turn "watch my camera roll and sort it every Sunday night" into a standing instruction — and changing it later is another sentence ("pause that for two weeks"), not a re-dig through a settings screen.
- **Multi-person face enrollment in one message.** `add_face_enroll` takes a whole `{"Name": "/folder"}` map at once — "here's Priya's folder, here's Raj's, enroll both" — instead of the tedious one-at-a-time tagging wizard most face-sort tools force you through.
- **Duplicate cleanup with judgment, not a blind "delete all" button.** `find_duplicates` → `export_report` → `delete_duplicates` can be chained conversationally with a human-in-the-loop threshold — "show me what you'd delete above 95% similarity before you touch anything" — the kind of staged, reasoned batch decision a fixed UI checkbox flow can't offer.
- **Clean mid-job abort, by just saying stop.** `abort_job` interrupts an in-flight sort or find-group operation on request, instead of the old-way fallback of force-quitting the app and hoping nothing half-written got left behind.
- **It lives wherever you already work, not in a separate app.** Because it's MCP, the same tools are reachable from Cursor while you're mid-coding-session — "clean up my screenshots folder" without alt-tabbing to a dedicated photo app. No photo organizer has ever been able to piggyback on a tool you were already in for unrelated work.
- **Guardrails as the actual trust story.** Source≠destination checks and path-hallucination prevention (Test 8) are what make "let an LLM touch my photo library" viable at all — worth stating plainly, but note this is table-stakes safety, not a differentiator on its own.

> Not yet shippable as marketing claims — code exists but isn't ready to promote: `smart_album_suggestions` (Pro tool is registered but not ready for users yet) and the Ollama-backed Chat UI (`chat_ui.py`, not currently a supported/finished surface). Don't reference either until they're actually live.

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
| `_ensure_daemon()` when the daemon cannot start | `pro_tools.py` | Returns `daemon_running: False`, verified via `/api/scheduler/daemon-status` — never assumed from a bare `Popen` |
| `schedule_auto_organize` guidance with a dead daemon | `pro_tools.py` | Says the schedule is saved but NOT monitored; must not claim sweeps will run |
| `schedule_auto_organize` next_actions | `pro_tools.py` | Includes `open_scheduler_dashboard`, matching `create_active_folder` and `list_schedules` |
| Any daemon start/stop from the MCP | `pro_tools.py` | Issues **no** `POST /api/scheduler/daemon-command`. Frozen, that endpoint's `sys.executable` is the backend binary, so it boots a backend clone that overwrites `port.txt` and makes the next call clone again |
| `manage_schedule(action="stop_daemon")` | `pro_tools.py` | Signals the PID in `scheduler.pid` with `SIGTERM`, then verifies via `daemon-status`; reports `still_running` if it did not stop |
| `copy_to_clipboard()` on Windows | `tray/actions.py` | Encodes as UTF-16LE for `clip.exe` |
| `stop_locallens_backend()` without psutil on Windows | `tray/actions.py` | Uses `taskkill /PID /T /F`, NOT `os.getpgid()` |
| `stop_all_backends()` without psutil on Windows | `tray/actions.py` | Uses `taskkill /PID /T /F`, NOT `os.kill(SIGTERM)` |
| `show_claude_status_terminal()` on MSIX Windows | `tray/actions.py` | Probes `%LOCALAPPDATA%\Packages\Claude_*` for logs path |
| `_is_pid_alive()` on Windows | `tray/tray_win.py` | Does NOT reference `psutil.STATUS_DEAD` |

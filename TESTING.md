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

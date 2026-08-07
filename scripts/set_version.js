#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

// Usage: node set_version.js <version> [highlight1] [highlight2] ...
const args = process.argv.slice(2);

if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
  console.log(`
LocalLens Version Bumper & Release Preparation Tool
===================================================
Usage: node set_version.js <version> ["Highlight 1"] ["Highlight 2"] ...

Example:
  node set_version.js 1.0.18 "Fixed macOS build trap cleanup" "Added manual build dispatch to CI"

Actions performed:
  1. Updates version in pyproject.toml
  2. Updates MCP_VERSION in src/mcp_server/updater.py
  3. Prepends to mcp.changelog in version.json (Application GUI Release Log)
  4. Generates release_notes_v<VERSION>.md (GitHub Release Page Release Notes)

Deliberately NOT updated: mcp.latest in version.json. That field is what every
installed client polls, so publishing it before the release assets exist leaves
clients announcing an update they cannot download. CI sets it in the same commit
as the download URLs + checksums — see the update-version-manifest job in
.github/workflows/release.yml.
`);
  process.exit(0);
}

const rawVersion = args[0].trim();
const version = rawVersion.startsWith('v') ? rawVersion.slice(1) : rawVersion;

if (!/^\d+\.\d+\.\d+.*$/.test(version)) {
  console.error(`Error: Invalid version format "${rawVersion}". Expected semver (e.g. 1.0.18)`);
  process.exit(1);
}

const highlights = args.slice(1);

// Highlights may be written "Fixed: …", "Added: …", "Improved: …", "Changed: …".
// The prefix drives the grouped "What Changed" section on the GitHub release page
// and is stripped everywhere else — version.json feeds the desktop UI and the
// assistant, where a bare sentence reads better than a category label.
// Keep in lockstep with scripts/set_version.py.
const CATEGORY_ORDER = ['Added', 'Fixed', 'Improved', 'Changed', 'Removed'];
const PREFIX_RE = /^(Added|Fixed|Improved|Changed|Removed)\s*:\s*/i;

function splitHighlight(text) {
  const match = text.match(PREFIX_RE);
  if (!match) return { category: null, text };
  const category = match[1][0].toUpperCase() + match[1].slice(1).toLowerCase();
  return { category, text: text.slice(match[0].length).trim() };
}

function buildReleaseSections(highlightList) {
  const pairs = highlightList.map(splitHighlight);

  const bullets = pairs.map(p => `- ${p.text}`).join('\n');
  let sections = `## ✨ Highlights\n\n${bullets}\n`;

  const grouped = {};
  for (const { category, text } of pairs) {
    if (category) (grouped[category] = grouped[category] || []).push(text);
  }

  const present = CATEGORY_ORDER.filter(c => grouped[c]);
  if (present.length) {
    const blocks = present.map(c => `### ${c}\n\n${grouped[c].map(t => `- ${t}`).join('\n')}`);
    sections += `\n---\n\n## 🔧 What Changed\n\n${blocks.join('\n\n')}\n`;
  }

  return `${sections}\n---`;
}

if (highlights.length === 0) {
  highlights.push(`LocalLens MCP Agent v${version} release.`);
}

const rootDir = path.join(__dirname, '..');
const monthYear = new Date().toLocaleString('en-US', { month: 'long', year: 'numeric' });

console.log(`\n🚀 Preparing Release v${version} (${monthYear})\n`);

// 1. Update pyproject.toml
const pyprojectPath = path.join(rootDir, 'pyproject.toml');
if (fs.existsSync(pyprojectPath)) {
  let pyprojectContent = fs.readFileSync(pyprojectPath, 'utf8');
  pyprojectContent = pyprojectContent.replace(/version\s*=\s*"[^"]+"/, `version = "${version}"`);
  fs.writeFileSync(pyprojectPath, pyprojectContent, 'utf8');
  console.log(` ✅ Updated pyproject.toml -> version = "${version}"`);
} else {
  console.warn(` ⚠️ pyproject.toml not found at ${pyprojectPath}`);
}

// 2. Update src/mcp_server/updater.py
const updaterPath = path.join(rootDir, 'src', 'mcp_server', 'updater.py');
if (fs.existsSync(updaterPath)) {
  let updaterContent = fs.readFileSync(updaterPath, 'utf8');
  updaterContent = updaterContent.replace(/MCP_VERSION\s*=\s*"[^"]+"/, `MCP_VERSION = "${version}"`);
  fs.writeFileSync(updaterPath, updaterContent, 'utf8');
  console.log(` ✅ Updated src/mcp_server/updater.py -> MCP_VERSION = "${version}"`);
} else {
  console.warn(` ⚠️ updater.py not found at ${updaterPath}`);
}

// 3. Update version.json (Application GUI Release Log)
const versionJsonPath = path.join(rootDir, 'version.json');
let newChangelogEntry = null;
if (fs.existsSync(versionJsonPath)) {
  let versionJsonData = JSON.parse(fs.readFileSync(versionJsonPath, 'utf8'));
  // mcp.latest is intentionally left alone — CI publishes it alongside the
  // download URLs and checksums. A changelog entry for a version that is not
  // yet `latest` is inert: check_for_updates() only reads highlights for the
  // version it is announcing.
  const existingIdx = versionJsonData.mcp.changelog.findIndex(entry => entry.version === version);
  newChangelogEntry = {
    version: version,
    date: monthYear,
    // Prefixes are for the GitHub page's grouped section only. This list is read
    // by the desktop "What's New" panel and quoted verbatim by the assistant,
    // where a leading "Fixed:" is noise.
    highlights: highlights.map(h => splitHighlight(h).text)
  };

  if (existingIdx !== -1) {
    versionJsonData.mcp.changelog[existingIdx] = newChangelogEntry;
  } else {
    versionJsonData.mcp.changelog.unshift(newChangelogEntry);
  }

  fs.writeFileSync(versionJsonPath, JSON.stringify(versionJsonData, null, 2) + '\n', 'utf8');
  console.log(` ✅ Updated version.json changelog -> v${version} (mcp.latest is published by CI)`);
} else {
  console.warn(` ⚠️ version.json not found at ${versionJsonPath}`);
}

// 4. Generate release_notes/release_notes_v<VERSION>.md (GitHub Release Page Notes)
const templatePath = path.join(rootDir, 'release_notes', 'release_notes_template.md');
if (fs.existsSync(templatePath)) {
  let template = fs.readFileSync(templatePath, 'utf8');

  if (template.includes('## GitHub Release Note Template')) {
    template = template.split('## GitHub Release Note Template')[1].trim();
    if (template.startsWith('```markdown')) {
      template = template.replace(/^```markdown\n/, '').replace(/\n```\s*$/, '');
    }
  }

  let ghReleaseNotes = template.replace(/{VERSION}/g, `v${version}`);

  const releaseSections = buildReleaseSections(highlights);

  if (ghReleaseNotes.includes('{RELEASE_SECTIONS}')) {
    ghReleaseNotes = ghReleaseNotes.replace('{RELEASE_SECTIONS}', releaseSections);
  } else {
    // Template predates the placeholder — prepend rather than lose the notes.
    console.warn(' ⚠️ {RELEASE_SECTIONS} not found in template — prepending instead');
    ghReleaseNotes = `${releaseSections}\n\n${ghReleaseNotes}`;
  }

  const releaseNotesFileName = `release_notes_v${version}.md`;
  const releaseNotesPath = path.join(rootDir, 'release_notes', releaseNotesFileName);
  // Trailing newline: the template is trim()ed above, so without this the file
  // ends mid-line. CI appends a "---" separator to it, and markdown reads "---"
  // directly under text as a setext H2 underline — the closing line of v1.0.32's
  // notes shipped as a heading because of it. Keep in lockstep with set_version.py.
  fs.writeFileSync(releaseNotesPath, ghReleaseNotes.replace(/\n+$/, '') + '\n', 'utf8');
  console.log(` ✅ Generated release_notes/${releaseNotesFileName} (GitHub Release Page Notes)`);
} else {
  console.warn(` ⚠️ release_notes_template.md not found at ${templatePath}`);
}

console.log(`\n───────────────────────────────────────────────────`);
console.log(`📋 1. Application GUI Release Log (version.json):`);
if (newChangelogEntry) {
  console.log(JSON.stringify(newChangelogEntry, null, 2));
}
console.log(`\n📋 2. GitHub Release Page Notes (release_notes_v${version}.md) generated.`);
console.log(`───────────────────────────────────────────────────\n`);
console.log(`🎉 Version ${version} preparation complete!\n`);

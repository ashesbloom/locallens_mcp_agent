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
  3. Updates mcp.latest and prepends to mcp.changelog in version.json (Application GUI Release Log)
  4. Generates release_notes_v<VERSION>.md (GitHub Release Page Release Notes)
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
if (highlights.length === 0) {
  highlights.push(`LocalLens MCP Agent v${version} release.`);
}

const rootDir = __dirname;
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
  versionJsonData.mcp.latest = version;

  const existingIdx = versionJsonData.mcp.changelog.findIndex(entry => entry.version === version);
  newChangelogEntry = {
    version: version,
    date: monthYear,
    highlights: highlights
  };

  if (existingIdx !== -1) {
    versionJsonData.mcp.changelog[existingIdx] = newChangelogEntry;
  } else {
    versionJsonData.mcp.changelog.unshift(newChangelogEntry);
  }

  fs.writeFileSync(versionJsonPath, JSON.stringify(versionJsonData, null, 2) + '\n', 'utf8');
  console.log(` ✅ Updated version.json (Application GUI Log) -> latest version: ${version}`);
} else {
  console.warn(` ⚠️ version.json not found at ${versionJsonPath}`);
}

// 4. Generate release_notes_v<VERSION>.md (GitHub Release Page Notes)
const templatePath = path.join(rootDir, 'release_notes_template.md');
if (fs.existsSync(templatePath)) {
  let template = fs.readFileSync(templatePath, 'utf8');

  if (template.includes('## GitHub Release Note Template')) {
    template = template.split('## GitHub Release Note Template')[1].trim();
    if (template.startsWith('```markdown')) {
      template = template.replace(/^```markdown\n/, '').replace(/\n```\s*$/, '');
    }
  }

  let ghReleaseNotes = template.replace(/{VERSION}/g, `v${version}`);

  const highlightsList = highlights.map(h => `- ${h}`).join('\n');
  const releaseHeader = `## What's New in v${version}\n\n${highlightsList}\n\n---`;

  if (ghReleaseNotes.includes("## What's Included")) {
    ghReleaseNotes = ghReleaseNotes.replace("## What's Included", `${releaseHeader}\n\n## What's Included`);
  } else {
    ghReleaseNotes = `${releaseHeader}\n\n${ghReleaseNotes}`;
  }

  const releaseNotesFileName = `release_notes_v${version}.md`;
  const releaseNotesPath = path.join(rootDir, releaseNotesFileName);
  fs.writeFileSync(releaseNotesPath, ghReleaseNotes, 'utf8');
  console.log(` ✅ Generated ${releaseNotesFileName} (GitHub Release Page Notes)`);
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

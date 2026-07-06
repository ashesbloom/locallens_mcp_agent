## LocalLens MCP Release — {{tag_name}}

This release bundles `locallens-mcp` into standalone native executables for macOS, Windows, and Linux. No Python runtime is required on your machine.

---

### 📦 Installation (1-Click / CLI Setup)

1. Download the zip/tar.gz archive below that matches your operating system and CPU architecture.
2. Extract the archive.
3. Open your terminal, navigate to the extracted file, and run:

#### macOS / Linux
```bash
./locallens-mcp --setup-claude
```
*(macOS users: If blocked by Gatekeeper, run `xattr -dr com.apple.quarantine locallens-mcp` to unquarantine the binary).*

#### Windows
```cmd
.\locallens-mcp.exe --setup-claude
```

4. **Restart Claude Desktop**. LocalLens tools will appear in your tool panel automatically.

---

### 🚀 What's New in this Release

*Add release highlights / changelog here*

---

### 🛠️ Developer Installation

If you prefer to install via python/pip:
```bash
pip install locallens-mcp=={{tag_name}}
```

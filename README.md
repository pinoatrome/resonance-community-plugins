# Resonance Community Plugins

[![Update Index](https://github.com/endegelaende/resonance-community-plugins/actions/workflows/update-index.yml/badge.svg)](https://github.com/endegelaende/resonance-community-plugins/actions/workflows/update-index.yml)

Community plugin repository for the [Resonance](https://github.com/endegelaende/resonance-server) music server.

Plugins listed here appear in the **Available** tab of the Resonance Plugin Manager UI and can be installed with a single click.

---

## 📦 Available Plugins

| Plugin | Version | Description | Author |
|--------|---------|-------------|--------|
| [raopbridge](plugins/raopbridge/) | 0.1.0 | AirPlay bridge — uses philippe44's squeeze2raop to make AirPlay devices available as Squeezebox players. Full Web UI via Server-Driven UI (SDUI) with device management, settings, and per-device configuration. | Pinoatrome |

---

## 🏗️ How It Works

```
                ┌─────────────────────┐
                │  Plugin Author      │
                │  pushes tag v1.2.3  │
                └────────┬────────────┘
                         │
                         ▼
                ┌─────────────────────┐
                │  GitHub Actions     │
                │  build-release.yml  │
                │  • zip plugin       │
                │  • compute SHA-256  │
                │  • create Release   │
                └────────┬────────────┘
                         │
                         ▼
                ┌─────────────────────┐
                │  GitHub Actions     │
                │  update-index.yml   │
                │  • scan all plugins │
                │  • generate index   │
                │  • deploy to Pages  │
                └────────┬────────────┘
                         │
                         ▼
                ┌─────────────────────┐
                │  GitHub Pages       │
                │  index.json         │
                │  (public URL)       │
                └────────┬────────────┘
                         │
                         ▼
                ┌─────────────────────┐
                │  Resonance Server   │
                │  fetches index.json │
                │  shows "Available"  │
                │  installs plugin    │
                └─────────────────────┘
```

### Repository Structure

```
resonance-community-plugins/
├── .github/
│   └── workflows/
│       ├── build-release.yml    # Builds ZIP + SHA for tagged releases
│       └── update-index.yml     # Generates index.json → GitHub Pages
├── plugins/
│   └── raopbridge/              # One folder per plugin
│       ├── plugin.toml          # Plugin manifest (name, version, etc.)
│       ├── __init__.py          # Plugin entry point (setup/teardown/get_ui)
│       ├── bridge.py            # AirPlay bridge subprocess management
│       ├── config.py            # Device & config XML parsing
│       └── tests/               # Plugin test suite
├── LICENSE
└── README.md
```

### Index Format

The `index.json` served via GitHub Pages has this structure:

```json
{
  "version": 1,
  "generated": "2025-01-15T12:00:00Z",
  "plugins": [
    {
      "name": "my-plugin",
      "version": "1.0.0",
      "description": "A cool community plugin",
      "author": "Your Name",
      "category": "tools",
      "icon": "",
      "min_resonance_version": "0.1.0",
      "url": "https://github.com/endegelaende/resonance-community-plugins/releases/download/my-plugin-v1.0.0/my-plugin-1.0.0.zip",
      "sha256": "abc123...",
      "homepage": "https://github.com/endegelaende/resonance-community-plugins/tree/main/plugins/my-plugin",
      "changelog": "",
      "tags": ["utility"]
    }
  ]
}
```

---

## 🚀 Installing Plugins

### Via the Web UI

1. Open the Resonance web interface
2. Navigate to **Settings → Plugins → Available**
3. Click **Install** on the plugin you want
4. Restart Resonance if prompted

### Via JSON-RPC

```json
{
  "method": "slim.request",
  "params": ["-", ["pluginmanager", "installrepo", "name:my-plugin"]]
}
```

---

## 🤝 Contributing

We welcome community plugin contributions! Here's how to add your plugin:

### Requirements

- A valid `plugin.toml` manifest with all required fields
- A working `setup()` function in `__init__.py`
- Clean `teardown()` — no resource leaks
- Compatibility with the current Resonance release
- No malicious code, no telemetry without consent

### Steps to Submit a Plugin

1. **Fork** this repository
2. **Create** a new folder under `plugins/your-plugin-name/`
3. **Add** your plugin code with a valid `plugin.toml`:

   ```toml
   [plugin]
   name = "your-plugin-name"
   version = "1.0.0"
   description = "Short description of what it does"
   author = "Your Name"
   min_resonance_version = "0.1.0"
   category = "music"  # music, radio, podcast, tools, misc

   [ui]
   enabled = true              # Optional: enables a Web UI page via SDUI
   sidebar_label = "My Plugin"
   sidebar_icon = "sparkles"   # Any Lucide icon name
   ```

4. **Test** your plugin locally by placing it in `data/installed_plugins/` of your Resonance server
5. **Open a Pull Request** with a clear description of your plugin

### Adding a Web UI (SDUI)

Plugins can provide a full Web UI page without writing any JavaScript. Using the
Server-Driven UI (SDUI) system, your plugin describes its UI declaratively in Python
and the Resonance frontend renders it automatically.

To add a UI page, implement `get_ui()` and `handle_action()` in your `__init__.py` and
set `[ui] enabled = true` in `plugin.toml`. See the
[SDUI documentation (§19)](https://github.com/endegelaende/resonance-server/blob/main/docs/PLUGIN_API.md#19-server-driven-ui-sdui)
and the [raopbridge plugin](plugins/raopbridge/) as a reference implementation.

### Plugin Guidelines

- **Naming**: Use lowercase, hyphen-separated names (e.g., `my-cool-plugin`)
- **Versioning**: Follow [SemVer](https://semver.org/) (MAJOR.MINOR.PATCH)
- **Settings**: Use `SettingDefinition` for user-configurable options — avoid hardcoded values
- **Logging**: Use `logging.getLogger(__name__)` — never `print()`
- **Dependencies**: Avoid heavy external dependencies; if needed, document them clearly
- **Security**: Never store credentials in plain text; use the plugin settings API with `masked=True`

### Categories

| Category | Use for |
|----------|---------|
| `music` | Music discovery, metadata, lyrics, etc. |
| `radio` | Internet radio sources |
| `podcast` | Podcast directories and tools |
| `tools` | Utilities, maintenance, integrations |
| `misc` | Everything else |

---

## 🔧 For Maintainers

### Creating a Release

Releases are created automatically when you push a version tag:

```bash
# After merging a plugin update:
git tag my-plugin-v1.0.0
git push origin my-plugin-v1.0.0
```

The `build-release.yml` workflow will:
1. Package the plugin directory into a ZIP
2. Compute the SHA-256 checksum
3. Create a GitHub Release with the ZIP attached

The `update-index.yml` workflow then:
1. Scans all `plugins/*/plugin.toml` files
2. Matches them with the latest GitHub Release
3. Generates `index.json`
4. Deploys to GitHub Pages

### Manual Index Rebuild

```bash
# Trigger via GitHub Actions UI or:
gh workflow run update-index.yml
```

---

## 📄 License

Community plugins are contributed under their respective licenses as specified by each plugin author. The repository infrastructure (workflows, scripts) is licensed under the [MIT License](LICENSE).

---

## 🔗 Links

- [Resonance Server](https://github.com/endegelaende/resonance-server) — the main server project
- [Plugin API Reference](https://github.com/endegelaende/resonance-server/blob/main/docs/PLUGIN_API.md) — complete API docs including SDUI (§19)
- [Plugin Tutorial](https://github.com/endegelaende/resonance-server/blob/main/docs/PLUGIN_TUTORIAL.md) — step-by-step guide to building a plugin
- [Plugin Repository Guide](https://github.com/endegelaende/resonance-server/blob/main/docs/PLUGIN_REPOSITORY.md) — how to publish plugins
- [Plugin System Overview](https://github.com/endegelaende/resonance-server/blob/main/docs/PLUGINS.md) — general plugin system overview
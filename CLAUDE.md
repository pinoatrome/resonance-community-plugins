# CLAUDE.md — Einstiegspunkt Community-Plugins

Stand: Maerz 2026

> **KI-Assistenten: Lies diese Datei zuerst.**
> Die vollstaendige Plugin-API-Doku liegt im Server-Repo:
>
> - `resonance-server/docs/PLUGIN_API.md` — API-Referenz inkl. §19 SDUI
> - `resonance-server/docs/PLUGIN_TUTORIAL.md` — Schritt-fuer-Schritt Tutorial
> - `resonance-server/CLAUDE.md` — Globaler Projektkontext

---

## 1) Was ist das?

Community-Plugins fuer den [Resonance](https://github.com/endegelaende/resonance-server) Musikserver.
Plugins werden hier entwickelt, ueber GitHub Actions als ZIP gepackt und via GitHub Pages
als `index.json` veroeffentlicht. Der Resonance Server fetcht diesen Index und zeigt
verfuegbare Plugins im Plugin Manager UI an.

---

## 2) Repos und Pfade

| Repo                            | Lokaler Pfad                                                | GitHub                                                                                                  |
| ------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **resonance-community-plugins** | `C:\Users\stephan\Desktop\resonance-community-plugins-main` | [endegelaende/resonance-community-plugins](https://github.com/endegelaende/resonance-community-plugins) |
| **resonance-server**            | `C:\Users\stephan\Desktop\resonance-server`                 | [endegelaende/resonance-server](https://github.com/endegelaende/resonance-server)                       |
| **slimserver-public**           | `C:\Users\stephan\Desktop\slimserver-public-9.2`            | — (LMS 9.2, read-only Referenz)                                                                         |

---

## 3) Aktueller Stand

- GitHub Actions laufen, alle gruen
- **raopbridge v0.1.0** released (v0.2.0 lokal, noch nicht getaggt)
- GitHub Pages Index live: `https://endegelaende.github.io/resonance-community-plugins/index.json`
- End-to-End Pipeline funktioniert: Tag → CI → Release → Index → Server Install

---

## 4) Repo-Struktur

```text
resonance-community-plugins/
├── .github/workflows/
│   ├── build-release.yml         # Tag → ZIP + SHA256 → GitHub Release
│   └── update-index.yml          # Scan → index.json → GitHub Pages
├── plugins/
│   └── raopbridge/               # AirPlay Bridge (v0.2.0 lokal)
│       ├── plugin.toml
│       ├── __init__.py           # get_ui(), handle_action(), setup(), teardown()
│       ├── bridge.py             # Subprocess-Management
│       ├── config.py             # Device/Config XML-Parsing
│       ├── serializers.py
│       ├── CHANGELOG             # Aenderungshistorie
│       ├── pytest.ini            # Test-Konfiguration
│       └── tests/
└── README.md
```

---

## 5) Release-Flow

1. Code in `plugins/<name>/` entwickeln
2. Version in `plugin.toml` bumpen
3. Committen + pushen auf `main`
4. Tag: `git tag <name>-v<version>` → `git push origin <name>-v<version>`
5. CI baut ZIP + SHA256 → GitHub Release → Index → GitHub Pages
6. Server sieht neues Plugin unter "Available"

**Tag-Format:** `<plugin-name>-v<version>` (z.B. `raopbridge-v0.2.0`).
Workflow splittet auf dem letzten `-v` und validiert gegen `plugin.toml`.

---

## 6) raopbridge Plugin

AirPlay Bridge — nutzt philippe44's squeeze2raop Binary.

| Datei         | Inhalt                                                 |
| ------------- | ------------------------------------------------------ |
| `__init__.py` | 5-Tab SDUI UI, Device Modal, Settings Form, Actions    |
| `bridge.py`   | RaopBridge Klasse, Binary-Download, Config-Generierung |
| `config.py`   | RaopDevice, RaopCommonOptions, XML-Parsing             |
| `plugin.toml` | Manifest v0.2.0 (lokal), v0.1.0 (released)             |

**SDUI Tabs:** Status (Badge + Buttons) · Devices (Tabelle + Modal) · Settings (Form) · Advanced (Collapsible KV) · About (Markdown)

---

## 7) Plugin-Entwicklung Kurzreferenz

### Manifest (`plugin.toml`)

```toml
[plugin]
name = "mein-plugin"
version = "1.0.0"
description = "Kurze Beschreibung"
author = "Name"
min_resonance_version = "0.1.0"
category = "tools"   # music, radio, podcast, tools, misc

[ui]
enabled = true
sidebar_label = "Mein Plugin"
sidebar_icon = "sparkles"   # Lucide Icon
```

### Entry Point (`__init__.py`)

Muss `async def setup(ctx: PluginContext)` enthalten.
Optional: `teardown(ctx)`, `get_ui(ctx)`, `handle_action(action, params, ctx)`.

### Lokales Testen

Plugin in `data/installed_plugins/` des Resonance Servers kopieren, oder:

```powershell
cd plugins/raopbridge
python -m pytest tests/ -v
```

---

## 8) Regeln

- **Namen:** lowercase, Bindestrich-getrennt (`my-cool-plugin`)
- **Versioning:** SemVer (MAJOR.MINOR.PATCH)
- **Logging:** `logging.getLogger(__name__)` — niemals `print()`
- **Settings:** `SettingDefinition` nutzen, keine hardcoded Werte
- **Security:** Keine Credentials in Plain Text, `masked=True` fuer Secrets
- **Cleanup:** `teardown()` muss sauber aufraeumen

---

## 9) Offene Aufgaben

- [ ] raopbridge v0.2.0 taggen und releasen
- [x] `help_text` Prop fuer SDUI Form-Widgets (Server-seitig) — erledigt
- [x] SDUI Widget Polish: MarkdownBlock (GFM via `marked`), Row/Column gap fix, ActionButton icon+spinner, Toggle layout, Modal focus-trap — erledigt
- [ ] Duplicate-Name-Validation fuer Device-Namen (Backend)
- [ ] Weitere Community-Plugins entwickeln

---

## 10) Dokument-Relationen (Was muss mit-aktualisiert werden?)

> **Regel:** Wenn du ein Dokument oder eine Quelldatei aenderst, pruefe die Spalte
> "Muss auch aktualisiert werden" und passe die abhaengigen Dateien an.
> Die vollstaendige Relationen-Tabelle (inkl. Code→Doku) liegt in `resonance-server/CLAUDE.md` §12.

### Dokument → Dokument (dieses Repo)

| Wenn du aenderst...           | Muss auch aktualisiert werden                                                | Grund                                                   |
| ----------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------- |
| **`CLAUDE.md`** (dieses File) | `resonance-server/CLAUDE.md` (§3 Stand, §6 Community-Struktur, §11 Aufgaben) | Beide teilen Status, Repo-Tabelle und offene Aufgaben   |
| **`README.md`**               | Keine zwingenden Abhaengigkeiten                                             | Eigenstaendig — nur von Server-Repo CHEATSHEET erwaehnt |
| **`.github/workflows/*.yml`** | `CLAUDE.md` §5 (Release-Flow), `README.md` (CI-Beschreibung)                 | CI/CD-Pipeline-Beschreibung in beiden Docs              |

### Code → Dokument

| Wenn du aenderst...                          | Muss auch aktualisiert werden                                                                                                        | Grund                                                               |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| **`plugins/*/plugin.toml`** (Version-Bump)   | `CLAUDE.md` §6 (Version), `resonance-server/CLAUDE.md` §3 (Stand)                                                                    | Version muss in beiden CLAUDE.md stimmen                            |
| **`plugins/*/__init__.py`** (SDUI-Aenderung) | `resonance-server/docs/PLUGIN_API.md` §19 (wenn neue Widgets/Props genutzt), `resonance-server/docs/PLUGIN_CASESTUDY.md` (Beispiele) | Casestudy und API-Doku referenzieren raopbridge als Referenz-Plugin |
| **`plugins/*/bridge.py`** oder `config.py`   | `CLAUDE.md` §6 (Datei-Tabelle, falls neue Dateien)                                                                                   | Repo-Struktur-Beschreibung aktuell halten                           |
| **Neues Plugin hinzugefuegt**                | `CLAUDE.md` §3 (Stand), §4 (Repo-Struktur), `README.md`, `resonance-server/CLAUDE.md` §3                                             | Alle Inventarlisten muessen das neue Plugin enthalten               |

### Repo-uebergreifende Sync-Pflichten

| Aenderung                     | Dieses Repo                                | Server-Repo                                                     |
| ----------------------------- | ------------------------------------------ | --------------------------------------------------------------- |
| Neues Plugin released (Tag)   | `CLAUDE.md` §3 (Stand), §6 (Version)       | `CLAUDE.md` §3 (Stand, erledigt-Tabelle), §11 (Aufgaben)        |
| Offene Aufgabe erledigt       | `CLAUDE.md` §9 (Aufgaben)                  | `CLAUDE.md` §3 (erledigt-Tabelle) + §11 (Aufgaben)              |
| Neues SDUI Widget im Plugin   | Plugin-Code                                | `ui/__init__.py`, `registry.ts`, `.svelte`, `PLUGIN_API.md` §19 |
| Plugin nutzt neues Server-API | Plugin-Code, `CLAUDE.md` §7 (Kurzreferenz) | `plugin.py`, `PLUGIN_API.md` (betroffene Sektion)               |
| CI-Workflow geaendert         | `CLAUDE.md` §5, `README.md`                | `CLAUDE.md` §6 (Community-Struktur), `docs/dev/CHEATSHEET.md`   |

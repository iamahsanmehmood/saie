# Publishing SAIE

Release pipeline for getting SAIE in front of users.

This document covers **every channel SAIE publishes to**, what each one needs, and how to ship a release.

---

## Release Channels

| Channel | URL | What we publish |
|---|---|---|
| **PyPI** | <https://pypi.org/project/saie/> | Python wheel + sdist, installs `saie` + `saie-mcp` console scripts |
| **GitHub Releases** | <https://github.com/iamahsanmehmood/saie/releases> | Tagged source + Ruby plugin zip + checksums |
| **Anthropic MCP Registry** | <https://modelcontextprotocol.io/registry> | Listing for one-click Claude Desktop install |
| **Smithery** | <https://smithery.ai/server/saie> | Hosted catalog entry with auto-install instructions |
| **mcp.so** | <https://mcp.so/server/saie> | Community MCP directory |
| **Cline marketplace** | Cline VS Code extension | Install card |

---

## Pre-flight Checklist

- [ ] `CHANGELOG.md` has an entry for the new version under `## [X.Y.Z] - YYYY-MM-DD`
- [ ] `pyproject.toml` `version` bumped
- [ ] `ruby_plugin/su_mcp_bridge/main.rb` `PLUGIN_VERSION` bumped
- [ ] `src/su_mcp_bridge/__init__.py` `__version__` bumped
- [ ] All unit + integration tests pass: `pytest tests/`
- [ ] `ruff check src/` clean
- [ ] README badges still resolve
- [ ] `saie --help` and `saie-mcp --help` work in a fresh venv
- [ ] Manual smoke test: `saie ping`, `saie agent "create a wall"`, live stream loads in browser

---

## 1. PyPI

### One-time setup

Create a PyPI account at <https://pypi.org/account/register/>, generate an API token, store it:

```bash
# ~/.pypirc
[pypi]
username = __token__
password = pypi-AgEI...your-token...
```

Or use trusted publishing via GitHub Actions (the `release.yml` workflow already supports it — configure the PyPI project's *Trusted Publishers* tab to accept `iamahsanmehmood/saie`).

### Build

```bash
pip install -U build twine
python -m build           # produces dist/saie-X.Y.Z-py3-none-any.whl + .tar.gz
twine check dist/*
```

### Upload

```bash
twine upload dist/*
```

After upload, `pip install saie` works worldwide within ~1 min.

---

## 2. GitHub Releases

The CI workflow `.github/workflows/release.yml` triggers on tag push:

```bash
git tag v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

CI will:

1. Run all tests + lints
2. Build the Python wheel + sdist
3. Build a Ruby plugin zip (`saie-plugin-vX.Y.Z.zip` containing `ruby_plugin/`)
4. Compute SHA-256 checksums
5. Create a GitHub Release, attaching the wheel, sdist, plugin zip, and checksums
6. Upload to PyPI (if Trusted Publishing is configured)

Edit the release notes on the GitHub UI afterwards — paste the relevant `CHANGELOG.md` section.

---

## 3. Anthropic MCP Registry

The MCP registry expects an `mcp.json` manifest at the repo root or `.well-known/`:

```json
{
  "name": "saie",
  "displayName": "SAIE — SketchUp Automation & Intelligence Engine",
  "description": "AI-powered architectural modeling for SketchUp 2025.",
  "version": "1.0.0",
  "homepage": "https://github.com/iamahsanmehmood/saie",
  "license": "MIT",
  "author": { "name": "Ahsan Mehmood", "url": "https://github.com/iamahsanmehmood" },
  "repository": "https://github.com/iamahsanmehmood/saie",
  "transport": "stdio",
  "install": {
    "pip": "pip install saie",
    "command": "saie-mcp"
  },
  "requirements": {
    "python": ">=3.10",
    "host_os": ["windows", "darwin"],
    "external": ["SketchUp 2025"]
  },
  "tags": ["sketchup", "3d", "cad", "bim", "architecture", "automation"]
}
```

Submit via the registry's PR template at <https://github.com/modelcontextprotocol/registry>.

---

## 4. Smithery

Smithery auto-discovers MCP servers from `smithery.yaml`. Already included in the repo root — Smithery picks it up automatically when the GitHub repo is connected.

```yaml
# smithery.yaml (see repo root)
startCommand:
  type: stdio
  configSchema: ...
```

To list: open <https://smithery.ai/new>, connect the GitHub repo, confirm the auto-detected fields, publish.

---

## 5. mcp.so

Submit at <https://mcp.so/submit>. Required fields:

- Name: `saie`
- Repo: `https://github.com/iamahsanmehmood/saie`
- Install: `pip install saie`
- Command: `saie-mcp`
- Tags: sketchup, architecture, cad

The site re-syncs from the GitHub README weekly.

---

## 6. Cline Marketplace

Cline pulls MCP servers from <https://github.com/cline/mcp-marketplace>. Open a PR adding:

```json
// servers/saie.json
{
  "id": "saie",
  "name": "SAIE — SketchUp",
  "description": "AI control over SketchUp 2025.",
  "type": "stdio",
  "install": "pip install saie",
  "command": "saie-mcp",
  "githubUrl": "https://github.com/iamahsanmehmood/saie",
  "category": "design"
}
```

---

## Versioning policy

SAIE follows [Semantic Versioning](https://semver.org):

- **MAJOR** — breaking changes to MCP tool names / parameters, breaking changes to `saie.toml` schema, breaking Python API removals.
- **MINOR** — new tools, new config fields with safe defaults, additive Python API.
- **PATCH** — bug fixes, doc fixes, performance improvements.

When publishing a new MAJOR, leave the previous MAJOR's wheels available on PyPI and document the migration in `CHANGELOG.md`.

---

## Post-release

After every release:

1. Tweet / post the GitHub Release URL.
2. Update <https://modelcontextprotocol.io/servers> if the listing is stale.
3. Open the Smithery + mcp.so listings to confirm the new version banner.
4. Update the README badge: `[![PyPI](https://img.shields.io/pypi/v/saie.svg)]` auto-refreshes.
5. Watch <https://github.com/iamahsanmehmood/saie/issues> for upgrade reports for 48 hours.

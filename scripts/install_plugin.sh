#!/usr/bin/env bash
# Install the SAIE SketchUp plugin into the user's Plugins directory.
#
# Usage:
#   ./install_plugin.sh                 # copy mode, version from saie.toml
#   ./install_plugin.sh --symlink       # dev mode — symlink to repo
#   ./install_plugin.sh --version 2024  # SketchUp 2024
#   ./install_plugin.sh --force         # overwrite without prompting

set -euo pipefail

VERSION=""
SYMLINK=0
FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)  VERSION="$2"; shift 2 ;;
        --symlink)  SYMLINK=1; shift ;;
        --force|-f) FORCE=1; shift ;;
        -h|--help)
            sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ─── Locate repo root ────────────────────────────────────────────────────────
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
SRC_ROOT="$REPO_ROOT/ruby_plugin"
SRC_DIR="$SRC_ROOT/su_mcp_bridge"
SRC_LDR="$SRC_ROOT/su_mcp_bridge.rb"

if [[ ! -d "$SRC_DIR" || ! -f "$SRC_LDR" ]]; then
    echo "Error: SAIE plugin source not found at $SRC_ROOT" >&2
    exit 1
fi

# ─── Resolve version ─────────────────────────────────────────────────────────
if [[ -z "$VERSION" ]]; then
    if [[ -f "$REPO_ROOT/saie.toml" ]]; then
        VERSION="$(grep -E '^\s*version\s*=' "$REPO_ROOT/saie.toml" | head -1 | sed -E 's/.*"([0-9]+)".*/\1/')"
    fi
    [[ -z "$VERSION" ]] && VERSION="2025"
fi

# ─── Resolve OS-specific Plugins directory ───────────────────────────────────
case "$(uname -s)" in
    Darwin)
        PLUGINS_DIR="$HOME/Library/Application Support/SketchUp $VERSION/SketchUp/Plugins"
        ;;
    Linux|*)
        echo "Note: SketchUp doesn't run natively on Linux." >&2
        echo "If you're using SketchUp through Wine, point this script at the Wine APPDATA path manually." >&2
        exit 1
        ;;
esac

DST_DIR="$PLUGINS_DIR/su_mcp_bridge"
DST_LDR="$PLUGINS_DIR/su_mcp_bridge.rb"

echo "SAIE plugin installer"
echo "  SketchUp version: $VERSION"
echo "  Source:           $SRC_ROOT"
echo "  Destination:      $PLUGINS_DIR"
echo

if [[ ! -d "$PLUGINS_DIR" ]]; then
    echo "Plugins directory not found." >&2
    echo "Make sure SketchUp $VERSION has been launched at least once."
    if [[ $FORCE -eq 0 ]]; then
        read -r -p "Create it anyway? (y/N) " resp
        [[ "$resp" != "y" ]] && exit 1
    fi
    mkdir -p "$PLUGINS_DIR"
fi

if [[ -e "$DST_DIR" || -e "$DST_LDR" ]]; then
    if [[ $FORCE -eq 0 ]]; then
        echo "SAIE plugin already installed."
        read -r -p "Overwrite? (y/N) " resp
        [[ "$resp" != "y" ]] && exit 0
    fi
    rm -rf "$DST_DIR" "$DST_LDR"
fi

# ─── Install ─────────────────────────────────────────────────────────────────
if [[ $SYMLINK -eq 1 ]]; then
    echo "Creating symlinks (dev mode)..."
    ln -s "$SRC_DIR" "$DST_DIR"
    cp "$SRC_LDR" "$DST_LDR"
else
    echo "Copying plugin files..."
    cp -R "$SRC_DIR" "$DST_DIR"
    cp "$SRC_LDR" "$DST_LDR"
fi

# ─── Seed user config ────────────────────────────────────────────────────────
USER_CFG_DIR="$HOME/.saie"
USER_CFG="$USER_CFG_DIR/saie.toml"
REPO_CFG="$REPO_ROOT/saie.toml"

if [[ -f "$REPO_CFG" && ! -f "$USER_CFG" ]]; then
    mkdir -p "$USER_CFG_DIR"
    cp "$REPO_CFG" "$USER_CFG"
    echo "Seeded user config at $USER_CFG"
fi

echo
echo "✓ SAIE plugin installed."
echo
echo "Next steps:"
echo "  1. Launch SketchUp $VERSION."
echo "  2. Look for 'Extensions → SAIE' in the menu bar."
echo "  3. Verify with: saie ping"

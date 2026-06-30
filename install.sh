#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/tomklino/tmux-mcp.git"

echo "Installing tmux-mcp..."
echo ""

if ! command -v pipx &>/dev/null; then
    echo "Error: pipx is not installed." >&2
    echo "" >&2
    echo "Install it with:" >&2
    echo "  brew install pipx        # macOS with Homebrew" >&2
    echo "  pip install --user pipx  # other" >&2
    exit 1
fi

pipx install "git+${REPO_URL}"

echo ""
echo "Installed successfully:"
echo "  tmux-cli        — manage tmux sessions"
echo "  tmux-mcp-server — MCP server (used by agents)"
echo ""

read -r -p "Configure your installed agents now? [Y/n] " answer
answer="${answer:-y}"
if [[ "${answer,,}" =~ ^(y|yes)$ ]]; then
    tmux-cli setup-agents
else
    echo ""
    echo "Run 'tmux-cli setup-agents' at any time to configure agents."
fi

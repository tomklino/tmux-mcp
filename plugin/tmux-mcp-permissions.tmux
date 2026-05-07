#!/usr/bin/env bash

# tmux-mcp-permissions TPM plugin
#
# Adds:
# - Prefix+P to cycle tmux-mcp permissions for the current session
# - A status-right segment showing current permissions
# - status-interval 5 (for out-of-band file edits)

set -e

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$CURRENT_DIR/../scripts"

TOGGLE="$SCRIPTS_DIR/tmux_mcp_toggle.py"
STATUS="$SCRIPTS_DIR/tmux_mcp_status.py"

tmux set -g status-interval 5

# Prefix+P: toggle and refresh status line immediately
tmux bind-key P run-shell "$TOGGLE --session '#{session_name}' >/dev/null 2>&1; tmux refresh-client -S"

# Status-right integration intentionally left to user config.
# (We previously tried to manage status-right automatically, but that was brittle.)

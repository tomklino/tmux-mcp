"""Configuration for tmux-buddy.

Holds the default socket name. Resolution order, highest priority first:
  1. TMUX_MCP_SOCKET environment variable
  2. defaultSocket field in the config JSON file
  3. literal fallback "tmux-mcp"

The config file path follows the same convention as permissions.py:
  1. TMUX_MCP_CONFIG_FILE environment variable (full path)
  2. $XDG_CONFIG_HOME/tmux-mcp/config.json
  3. ~/.config/tmux-mcp/config.json
"""

import json
import os
from pathlib import Path


FALLBACK_SOCKET = "tmux-mcp"


def config_file_path() -> Path:
    override = os.environ.get("TMUX_MCP_CONFIG_FILE")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "tmux-mcp" / "config.json"

    return Path.home() / ".config" / "tmux-mcp" / "config.json"


def default_socket() -> str:
    env = os.environ.get("TMUX_MCP_SOCKET")
    if env:
        return env

    path = config_file_path()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        sock = data.get("defaultSocket")
        if isinstance(sock, str) and sock:
            return sock
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"defaultSocket": FALLBACK_SOCKET}, indent=2),
            encoding="utf-8",
        )
    except (json.JSONDecodeError, OSError):
        pass

    return FALLBACK_SOCKET

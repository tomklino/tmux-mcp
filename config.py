"""Configuration for tmux-buddy.

Holds the default socket name. Resolution order, highest priority first:
  1. TMUX_MCP_SOCKET environment variable
  2. defaultSocket field in the config YAML file
  3. literal fallback "tmux-mcp"

The config file path follows the same convention as permissions.py:
  1. TMUX_MCP_CONFIG_FILE environment variable (full path)
  2. $XDG_CONFIG_HOME/tmux-mcp/config.yaml
  3. ~/.config/tmux-mcp/config.yaml
"""

import os
from pathlib import Path

import yaml


FALLBACK_SOCKET = "tmux-mcp"

_CONFIG_TEMPLATE = """\
# tmux-mcp configuration
# Uncomment and edit any option to override the default.

# Default tmux socket name used by tmux-cli and the MCP server.
# Can be overridden at runtime with the TMUX_MCP_SOCKET environment variable.
# defaultSocket: tmux-mcp
"""


def config_file_path() -> Path:
    override = os.environ.get("TMUX_MCP_CONFIG_FILE")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "tmux-mcp" / "config.yaml"

    return Path.home() / ".config" / "tmux-mcp" / "config.yaml"


def default_socket() -> str:
    env = os.environ.get("TMUX_MCP_SOCKET")
    if env:
        return env

    path = config_file_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sock = data.get("defaultSocket")
        if isinstance(sock, str) and sock:
            return sock
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
    except (yaml.YAMLError, OSError):
        pass

    return FALLBACK_SOCKET

"""Configuration for tmux-buddy.

Holds the default socket name. Resolution order, highest priority first:
  1. TMUX_MCP_SOCKET environment variable
  2. defaultSocket field in the config JSON file
  3. literal fallback "tmux-mcp"

Session flag defaults (record, experimentalScrollPopup, withAgent) can also
be set in the config file and are overridden by explicit CLI arguments.

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

    try:
        raw = config_file_path().read_text(encoding="utf-8")
        data = json.loads(raw)
        sock = data.get("defaultSocket")
        if isinstance(sock, str) and sock:
            return sock
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    return FALLBACK_SOCKET


def session_defaults() -> dict:
    """Return per-session flag defaults from the config file.

    Keys: 'record', 'experimental_scroll_popup', 'with_agent'.
    CLI arguments take precedence over these values.

    Config JSON keys:
      record                  -> bool
      experimentalScrollPopup -> bool
      withAgent               -> str | bool

    record and experimental_scroll_popup are True/False when set, None when
    absent. with_agent is the agent command name (str), True to request the
    default agent without naming it, or None when absent/invalid.
    """
    try:
        raw = config_file_path().read_text(encoding="utf-8")
        data = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}

    result: dict = {}
    for dest, json_key in [
        ("record", "record"),
        ("experimental_scroll_popup", "experimentalScrollPopup"),
    ]:
        val = data.get(json_key)
        result[dest] = bool(val) if isinstance(val, bool) else None

    agent = data.get("withAgent")
    if isinstance(agent, str) and agent:
        result["with_agent"] = agent
    elif agent is True:
        result["with_agent"] = True
    else:
        result["with_agent"] = None

    return result

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

# One-time prompts / UX flags.
# When true/missing, tmux-cli may ask to configure Pi MCP on first use of --with-agent pi.
# promptSetupPiMcp: true
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


def session_defaults() -> dict:
    """Return per-session flag defaults from the config file.

    Keys: 'record', 'experimental_scroll_popup', 'with_agent'.
    CLI arguments take precedence over these values.

    Config YAML keys:
      record                  -> bool
      experimentalScrollPopup -> bool
      withAgent               -> str | bool
    """
    try:
        data = yaml.safe_load(config_file_path().read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        data = {}

    result: dict = {}
    for dest, yaml_key in [
        ("record", "record"),
        ("experimental_scroll_popup", "experimentalScrollPopup"),
    ]:
        val = data.get(yaml_key)
        result[dest] = bool(val) if isinstance(val, bool) else None

    agent = data.get("withAgent")
    if isinstance(agent, str) and agent:
        result["with_agent"] = agent
    elif agent is True:
        result["with_agent"] = True
    else:
        result["with_agent"] = None

    return result


def should_prompt_setup_pi_mcp() -> bool:
    """Whether tmux-cli should prompt to set up Pi MCP integration.

    Stored in the YAML config as `promptSetupPiMcp`.
    Defaults to True if the key is missing.
    """
    try:
        data = yaml.safe_load(config_file_path().read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return True

    val = data.get("promptSetupPiMcp", True)
    return bool(val) if isinstance(val, bool) else True


def set_prompt_setup_pi_mcp(value: bool) -> None:
    """Persist `promptSetupPiMcp` in the YAML config."""
    path = config_file_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
    except (yaml.YAMLError, OSError):
        data = {}

    data["promptSetupPiMcp"] = bool(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path


def _default_permissions() -> dict:
    return {"version": 1, "defaultMode": "deny", "sessions": {}}


def _permissions_file_path(cli_file: str | None) -> Path:
    if cli_file:
        return Path(cli_file).expanduser()

    override = os.environ.get("TMUX_MCP_PERMISSIONS_FILE")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "tmux-mcp" / "permissions.json"

    return Path.home() / ".config" / "tmux-mcp" / "permissions.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _default_permissions()


def _segment(mode: str) -> str:
    # Colors per design:
    # deny=green, read=yellow, read_send=orange, execute=red
    mapping = {
        "deny": ("colour46", "MCP:DENY"),
        "read": ("colour226", "MCP:READ"),
        "read_send": ("colour208", "MCP:SEND"),
        "execute": ("colour196", "MCP:EXEC"),
    }

    color, label = mapping.get("deny")
    if mode in mapping:
        color, label = mapping[mode]

    return f"#[fg={color}]{label}#[default]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--file")
    args = parser.parse_args()

    path = _permissions_file_path(args.file)
    data = _load(path)

    sessions = data.get("sessions", {})

    # managed-only semantics: unlisted => deny
    mode = "deny"
    if isinstance(sessions, dict) and args.session in sessions:
        mode = sessions.get(args.session) or data.get("defaultMode", "deny")

    if mode not in {"deny", "read", "read_send", "execute"}:
        mode = data.get("defaultMode", "deny")

    if mode not in {"deny", "read", "read_send", "execute"}:
        mode = "deny"

    print(_segment(mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

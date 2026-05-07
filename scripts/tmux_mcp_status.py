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
    # Use a colored *background* for visibility regardless of the user's status bar
    # background, then reset with #[default].
    mapping = {
        # (bg, fg, label)
        "deny": ("colour46", "colour0", "MCP:DENY"),  # green bg, black text
        "read": ("colour226", "colour0", "MCP:READ"),  # yellow bg, black text
        "read_send": ("colour208", "colour0", "MCP:SEND"),  # orange bg, black text
        "execute": ("colour196", "colour15", "MCP:EXEC"),  # red bg, white text
    }

    bg, fg, label = mapping["deny"]
    if mode in mapping:
        bg, fg, label = mapping[mode]

    style = f"#[bg={bg},fg={fg}]"
    if mode == "execute":
        style = f"#[bg={bg},fg={fg},bold]"

    return f"{style}{label}#[default]"


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

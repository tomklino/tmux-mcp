#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
from typing import Literal


Mode = Literal["deny", "read", "read_send", "execute"]


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


def _load_or_create(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _default_permissions()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data
    except json.JSONDecodeError:
        # fail safe for UI: treat as default deny
        return _default_permissions()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--mode", choices=["deny", "read", "read_send", "execute"])
    parser.add_argument("--file")
    args = parser.parse_args()

    path = _permissions_file_path(args.file)
    data = _load_or_create(path)

    sessions = data.setdefault("sessions", {})

    if args.mode is not None:
        sessions[args.session] = args.mode
        path.write_text(json.dumps(data), encoding="utf-8")
        return 0

    # First toggle registers the session at deny and stops.
    if args.session not in sessions:
        sessions[args.session] = "deny"
        path.write_text(json.dumps(data), encoding="utf-8")
        return 0

    # Cycle existing
    current = sessions.get(args.session, data.get("defaultMode", "deny"))
    order: list[Mode] = ["deny", "read", "read_send", "execute"]
    try:
        idx = order.index(current)  # type: ignore[arg-type]
    except ValueError:
        idx = 0
    sessions[args.session] = order[(idx + 1) % len(order)]

    path.write_text(json.dumps(data), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

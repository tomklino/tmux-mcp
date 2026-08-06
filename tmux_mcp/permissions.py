import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Mode = Literal["deny", "read", "read_send", "execute"]
Tool = Literal[
    "get_last_lines",
    "get_last_command_output",
    "wait_for_completion",
    "send_command",
    "execute_command",
    "send_interrupt",
]


@dataclass(frozen=True)
class Permissions:
    version: int
    default_mode: Mode
    sessions: dict[str, str]


def _default_permissions() -> dict:
    return {"version": 1, "defaultMode": "deny", "sessions": {}}


def ensure_session_registered(session_name: str) -> None:
    """Ensure a session has an explicit entry in the permissions file.

    Policy: registering a session always resets it to defaultMode (safe by default).
    """

    path = permissions_file_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(_default_permissions())

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _default_permissions()

    sessions = data.setdefault("sessions", {})
    default_mode = data.get("defaultMode", "deny")
    if default_mode not in {"deny", "read", "read_send", "execute"}:
        default_mode = "deny"

    sessions[session_name] = default_mode

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def permissions_file_path() -> Path:
    override = os.environ.get("TMUX_MCP_PERMISSIONS_FILE")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "tmux-mcp" / "permissions.json"

    return Path.home() / ".config" / "tmux-mcp" / "permissions.json"


def load_permissions() -> Permissions:
    path = permissions_file_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_default_permissions()), encoding="utf-8")
        raw = path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # fail closed: treat as default deny
        data = _default_permissions()

    return Permissions(
        version=int(data.get("version", 1)),
        default_mode=str(data.get("defaultMode", "deny")),
        sessions=dict(data.get("sessions", {})),
    )


def is_session_listed(perms: Permissions, session_name: str) -> bool:
    return session_name in perms.sessions


def effective_mode(perms: Permissions, session_name: str) -> Mode:
    if not is_session_listed(perms, session_name):
        return "deny"

    mode = perms.sessions.get(session_name)
    if mode in {"deny", "read", "read_send", "execute"}:
        return mode  # type: ignore[return-value]

    # invalid/missing -> defaultMode
    dm = perms.default_mode
    if dm in {"deny", "read", "read_send", "execute"}:
        return dm
    return "deny"


def is_tool_allowed(mode: Mode, tool: Tool) -> bool:
    if mode == "deny":
        return False

    if tool in {"get_last_lines", "get_last_command_output", "wait_for_completion"}:
        return mode in {"read", "read_send", "execute"}

    if tool == "send_command":
        return mode in {"read_send", "execute"}

    if tool in {"execute_command", "send_interrupt"}:
        return mode == "execute"

    return False


def assert_allowed(session_name: str, tool: Tool) -> None:
    perms = load_permissions()
    mode = effective_mode(perms, session_name)
    if not is_tool_allowed(mode, tool):
        raise PermissionError(
            f"tmux-mcp permission denied: session={session_name} mode={mode} tool={tool}"
        )

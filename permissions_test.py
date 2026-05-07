import json
import os
from pathlib import Path

import pytest

import tmux_mcp


def _write_permissions(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture()
def permissions_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "permissions.json"
    monkeypatch.setenv("TMUX_MCP_PERMISSIONS_FILE", str(p))
    return p


def test_get_last_lines_denied_for_unlisted_session(permissions_file: Path, monkeypatch):
    """Managed-only: if session isn't explicitly listed, deny everything."""

    _write_permissions(
        permissions_file,
        {"version": 1, "defaultMode": "deny", "sessions": {}},
    )

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "get_n_last_lines", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.get_last_lines("green", lines=3)


def test_get_last_lines_allowed_for_listed_session_in_read_mode(
    permissions_file: Path, monkeypatch
):
    _write_permissions(
        permissions_file,
        {"version": 1, "defaultMode": "deny", "sessions": {"green": "read"}},
    )

    monkeypatch.setattr(tmux_mcp.tmux_lib, "get_n_last_lines", lambda *_: "ok")

    assert tmux_mcp.get_last_lines("green", lines=3) == "ok"


def test_wait_for_completion_allowed_for_listed_session_in_read_mode(
    permissions_file: Path, monkeypatch
):
    _write_permissions(
        permissions_file,
        {"version": 1, "defaultMode": "deny", "sessions": {"green": "read"}},
    )

    monkeypatch.setattr(
        tmux_mcp.tmux_lib,
        "wait_for_command_completion",
        lambda *_: None,
    )

    assert tmux_mcp.wait_for_completion("green", timeout=0.01) == {
        "prompt": "",
        "command": "",
        "output": "",
        "status": "timeout",
    }


def test_send_command_denied_in_read_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {"version": 1, "defaultMode": "deny", "sessions": {"green": "read"}},
    )

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "send_to_terminal", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.send_command("green", "echo hi", prompt_verify_string=None)


def test_send_command_allowed_in_read_send_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "read_send"},
        },
    )

    monkeypatch.setattr(tmux_mcp.tmux_lib, "send_to_terminal", lambda *_: True)

    assert (
        tmux_mcp.send_command("green", "echo hi", prompt_verify_string=None) == "sent"
    )


def test_send_interrupt_denied_in_read_send_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "read_send"},
        },
    )

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "send_interrupt", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.send_interrupt("green")


def test_send_interrupt_allowed_in_execute_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "execute"},
        },
    )

    monkeypatch.setattr(tmux_mcp.tmux_lib, "send_interrupt", lambda *_: None)

    assert tmux_mcp.send_interrupt("green") == "sent"


def test_execute_command_denied_in_read_send_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "read_send"},
        },
    )

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "execute_in_terminal", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.execute_command("green", "echo hi")


def test_execute_command_allowed_in_execute_mode(permissions_file: Path, monkeypatch):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "execute"},
        },
    )

    # simplest result path: tmux_lib returns a string => tmux_mcp maps it to status=free
    monkeypatch.setattr(
        tmux_mcp.tmux_lib, "execute_in_terminal", lambda *_args, **_kw: ""
    )

    assert tmux_mcp.execute_command("green", "echo hi") == {
        "prompt": "",
        "command": "",
        "output": "",
        "status": "free",
    }


def test_missing_permissions_file_is_created_and_unlisted_session_denied(
    permissions_file: Path, monkeypatch
):
    # Ensure file does not exist
    permissions_file.unlink(missing_ok=True)

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "get_n_last_lines", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.get_last_lines("green", lines=3)

    assert permissions_file.exists(), "server should create permissions file if missing"


def test_invalid_json_denies(permissions_file: Path, monkeypatch):
    permissions_file.parent.mkdir(parents=True, exist_ok=True)
    permissions_file.write_text("{not-json", encoding="utf-8")

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "get_n_last_lines", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.get_last_lines("green", lines=3)


def test_invalid_mode_for_listed_session_falls_back_to_default_mode(
    permissions_file: Path, monkeypatch
):
    _write_permissions(
        permissions_file,
        {
            "version": 1,
            "defaultMode": "deny",
            "sessions": {"green": "not_a_real_mode"},
        },
    )

    def _should_not_be_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("tmux_lib should not be called when denied")

    monkeypatch.setattr(tmux_mcp.tmux_lib, "get_n_last_lines", _should_not_be_called)

    with pytest.raises(PermissionError):
        tmux_mcp.get_last_lines("green", lines=3)

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def test_toggle_missing_file_creates_file_and_registers_session_as_deny(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", env=env)

    assert result.returncode == 0
    assert permissions_file.exists()

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["defaultMode"] == "deny"
    assert data["sessions"]["green"] == "deny"


def test_toggle_mode_explicitly_sets_mode(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", "--mode", "read_send", env=env)

    assert result.returncode == 0

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["sessions"]["green"] == "read_send"


def test_status_unlisted_session_shows_deny(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    # managed-only: unlisted => deny
    permissions_file.write_text(
        json.dumps({"version": 1, "defaultMode": "deny", "sessions": {}}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_status.py"

    result = _run(script, "--session", "green", env=env)

    assert result.returncode == 0
    assert result.stdout.strip() == "#[fg=colour46]MCP:DENY#[default]"


def test_toggle_cycles_deny_to_read(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    permissions_file.write_text(
        json.dumps(
            {
                "version": 1,
                "defaultMode": "deny",
                "sessions": {"green": "deny"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", env=env)
    assert result.returncode == 0

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["sessions"]["green"] == "read"


def test_toggle_cycles_read_to_read_send(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    permissions_file.write_text(
        json.dumps(
            {
                "version": 1,
                "defaultMode": "deny",
                "sessions": {"green": "read"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", env=env)
    assert result.returncode == 0

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["sessions"]["green"] == "read_send"


def test_toggle_cycles_read_send_to_execute(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    permissions_file.write_text(
        json.dumps(
            {
                "version": 1,
                "defaultMode": "deny",
                "sessions": {"green": "read_send"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", env=env)
    assert result.returncode == 0

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["sessions"]["green"] == "execute"


def test_toggle_cycles_execute_to_deny(tmp_path: Path):
    permissions_file = tmp_path / "permissions.json"

    permissions_file.write_text(
        json.dumps(
            {
                "version": 1,
                "defaultMode": "deny",
                "sessions": {"green": "execute"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["TMUX_MCP_PERMISSIONS_FILE"] = str(permissions_file)

    script = Path(__file__).parent / "scripts" / "tmux_mcp_toggle.py"

    result = _run(script, "--session", "green", env=env)
    assert result.returncode == 0

    data = json.loads(permissions_file.read_text(encoding="utf-8"))
    assert data["sessions"]["green"] == "deny"

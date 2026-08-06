import json
import sys
from pathlib import Path
from unittest import mock

import tmux_mcp.tmux_cli as tmux_cli


def _args(session_name="green", with_agent=None, record=False, experimental_scroll_popup=False):
    args = mock.Mock()
    args.session_name = session_name
    args.record = record
    args.experimental_scroll_popup = experimental_scroll_popup
    args.with_agent = with_agent
    return args


def _stub_create_session(monkeypatch):
    # Avoid tmux interactions
    monkeypatch.setattr(tmux_cli.tmux_lib, "create_tmux_session", lambda *a, **k: "tmux-mcp")
    monkeypatch.setattr(tmux_cli.subprocess, "run", lambda *a, **k: mock.MagicMock(returncode=0))


def test_pi_first_time_with_agent_pi_prompts_and_sets_flag(monkeypatch):
    _stub_create_session(monkeypatch)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "should_prompt_setup_pi_mcp", lambda: True)

    set_calls = []
    monkeypatch.setattr(tmux_cli.config, "set_prompt_setup_pi_mcp", lambda v: set_calls.append(v))

    # User says "no"; we still flip the flag.
    monkeypatch.setattr("builtins.input", lambda _: "n")

    tmux_cli.cmd_new(_args(with_agent="pi"))

    assert set_calls == [False]


def test_pi_first_time_without_with_agent_does_not_prompt_and_flag_unchanged(monkeypatch):
    _stub_create_session(monkeypatch)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "should_prompt_setup_pi_mcp", lambda: True)

    set_calls = []
    monkeypatch.setattr(tmux_cli.config, "set_prompt_setup_pi_mcp", lambda v: set_calls.append(v))

    # If prompt happened it would read input; make that a hard fail.
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("prompted")))

    tmux_cli.cmd_new(_args(with_agent=None))

    assert set_calls == []


def test_pi_answer_yes_creates_mcp_json_and_installs_adapter(monkeypatch, tmp_path: Path):
    _stub_create_session(monkeypatch)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "should_prompt_setup_pi_mcp", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "set_prompt_setup_pi_mcp", lambda v: None)

    monkeypatch.setattr("builtins.input", lambda _: "y")

    installed = []
    monkeypatch.setattr(tmux_cli, "_ensure_pi_mcp_adapter_installed", lambda: installed.append(True) or True)

    pi_config = tmp_path / ".pi" / "agent" / "mcp.json"

    real_configure = tmux_cli._configure_pi_mcp

    def _configure_override() -> bool:
        return real_configure(pi_config=pi_config)

    monkeypatch.setattr(tmux_cli, "_configure_pi_mcp", _configure_override)

    tmux_cli.cmd_new(_args(with_agent="pi"))

    assert installed == [True]
    assert pi_config.exists()

    data = json.loads(pi_config.read_text(encoding="utf-8"))
    assert data["mcpServers"]["tmux"]["command"] == "bash"
    assert data["mcpServers"]["tmux"]["args"][0] == "-lc"
    # ensure it runs this interpreter
    assert sys.executable in data["mcpServers"]["tmux"]["args"][1]
    assert "-m tmux_mcp.tmux_mcp" in data["mcpServers"]["tmux"]["args"][1]


def test_pi_answer_yes_verifies_correct_installation_command(monkeypatch, capsys):
    """Red-phase regression test.

    The Pi MCP adapter should be installed using the correct command.
    This test documents the desired behavior and should fail until implemented.
    """

    _stub_create_session(monkeypatch)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "should_prompt_setup_pi_mcp", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "set_prompt_setup_pi_mcp", lambda v: None)

    monkeypatch.setattr("builtins.input", lambda _: "y")

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pi_mcp_adapter":
            raise ImportError
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    calls = []

    def fake_run(cmd, capture_output=True, text=True):
        calls.append(cmd)
        if cmd[:2] == ["/usr/bin/pi", "install"]:
            return mock.MagicMock(returncode=0, stdout="", stderr="")
        return mock.MagicMock(
            returncode=1,
            stdout="",
            stderr="unexpected installer used",
        )

    monkeypatch.setattr(tmux_cli.shutil, "which", lambda name: "/usr/bin/pi" if name == "pi" else None)
    monkeypatch.setattr(tmux_cli.subprocess, "run", fake_run)

    ok = tmux_cli._ensure_pi_mcp_adapter_installed()

    assert ok is True
    assert calls == [["/usr/bin/pi", "install", "npm:pi-mcp-adapter"]]

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "attempting to install it via `pi install npm:pi-mcp-adapter`" in combined


def test_pi_answer_yes_merges_existing_mcp_json_untouched_other_content(monkeypatch, tmp_path: Path):
    _stub_create_session(monkeypatch)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "should_prompt_setup_pi_mcp", lambda: True)
    monkeypatch.setattr(tmux_cli.config, "set_prompt_setup_pi_mcp", lambda v: None)

    monkeypatch.setattr("builtins.input", lambda _: "y")
    monkeypatch.setattr(tmux_cli, "_ensure_pi_mcp_adapter_installed", lambda: True)

    pi_config = tmp_path / ".pi" / "agent" / "mcp.json"
    pi_config.parent.mkdir(parents=True, exist_ok=True)
    pi_config.write_text(
        json.dumps(
            {
                "mcpServers": {"other": {"command": "echo", "args": ["hi"]}},
                "topLevel": {"keep": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    real_configure = tmux_cli._configure_pi_mcp

    def _configure_override() -> bool:
        return real_configure(pi_config=pi_config)

    monkeypatch.setattr(tmux_cli, "_configure_pi_mcp", _configure_override)

    tmux_cli.cmd_new(_args(with_agent="pi"))

    data = json.loads(pi_config.read_text(encoding="utf-8"))

    # Existing content remains
    assert data["topLevel"] == {"keep": True}
    assert data["mcpServers"]["other"]["command"] == "echo"

    # tmux server entry is present/updated
    assert data["mcpServers"]["tmux"]["command"] == "bash"
    assert data["mcpServers"]["tmux"]["args"][0] == "-lc"
    assert sys.executable in data["mcpServers"]["tmux"]["args"][1]

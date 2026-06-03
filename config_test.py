"""Tests for config loading (default socket name)."""

import json

import pytest

import config


def test_default_socket_env_var_takes_precedence(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"defaultSocket": "filesock"}))
    monkeypatch.setenv("TMUX_MCP_SOCKET", "envsock")
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "envsock"


def test_default_socket_reads_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"defaultSocket": "filesock"}))
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "filesock"


def test_default_socket_fallback_when_no_env_or_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(tmp_path / "missing.json"))

    assert config.default_socket() == "tmux-mcp"


def test_default_socket_fallback_when_config_invalid_json(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("not valid json")
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "tmux-mcp"


def test_default_socket_fallback_when_key_missing(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"unrelated": "value"}))
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "tmux-mcp"


def test_config_file_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.json"
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(target))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert config.config_file_path() == target


def test_config_file_path_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert config.config_file_path() == tmp_path / "tmux-mcp" / "config.json"


def test_config_file_path_default(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config.config_file_path() == tmp_path / ".config" / "tmux-mcp" / "config.json"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

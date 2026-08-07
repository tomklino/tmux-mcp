"""Tests for config loading (default socket name)."""

import pytest
import yaml

from tmux_mcp import config


def test_default_socket_env_var_takes_precedence(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"defaultSocket": "filesock"}))
    monkeypatch.setenv("TMUX_MCP_SOCKET", "envsock")
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "envsock"


def test_default_socket_reads_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"defaultSocket": "filesock"}))
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "filesock"


def test_default_socket_fallback_when_no_env_or_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(tmp_path / "missing.yaml"))

    assert config.default_socket() == "tmux-mcp"


def test_default_socket_fallback_when_config_invalid_yaml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("key: [unclosed bracket")
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "tmux-mcp"


def test_default_socket_fallback_when_key_missing(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"unrelated": "value"}))
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert config.default_socket() == "tmux-mcp"


def test_default_socket_creates_config_file_on_first_access(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
    cfg = tmp_path / "tmux-mcp" / "config.yaml"
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    assert not cfg.exists()
    result = config.default_socket()
    assert result == "tmux-mcp"
    assert cfg.exists()
    assert "defaultSocket" in cfg.read_text()


def test_config_file_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.yaml"
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(target))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert config.config_file_path() == target


def test_config_file_path_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert config.config_file_path() == tmp_path / "tmux-mcp" / "config.yaml"


def test_config_file_path_default(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX_MCP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config.config_file_path() == tmp_path / ".config" / "tmux-mcp" / "config.yaml"


def _write_yaml_config(path, data):
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_session_defaults_reads_all_flags(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml_config(cfg, {"record": True, "experimentalScrollPopup": True, "withAgent": "claude"})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["record"] is True
    assert defaults["experimental_scroll_popup"] is True
    assert defaults["with_agent"] == "claude"


def test_session_defaults_with_agent_true_means_default(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml_config(cfg, {"withAgent": True})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["with_agent"] is True


def test_session_defaults_absent_keys_are_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml_config(cfg, {"record": False})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["record"] is False
    assert defaults["experimental_scroll_popup"] is None
    assert defaults["with_agent"] is None
    assert defaults["sandbox"] is None


def test_session_defaults_missing_file_all_none(monkeypatch, tmp_path):
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(tmp_path / "does-not-exist.yaml"))

    defaults = config.session_defaults()

    assert defaults == {
        "record": None,
        "experimental_scroll_popup": None,
        "with_agent": None,
        "sandbox": None,
    }


def test_session_defaults_invalid_yaml_all_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("key: [unclosed bracket", encoding="utf-8")
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults == {
        "record": None,
        "experimental_scroll_popup": None,
        "with_agent": None,
        "sandbox": None,
    }


def test_session_defaults_non_bool_values_are_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml_config(cfg, {"record": "yes", "withAgent": 1})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["record"] is None
    assert defaults["with_agent"] is None
    assert defaults["sandbox"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

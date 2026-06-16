import json

import config


def _write_config(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_session_defaults_reads_all_flags(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    _write_config(
        cfg,
        {
            "record": True,
            "experimentalScrollPopup": True,
            "withAgent": "claude",
        },
    )
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["record"] is True
    assert defaults["experimental_scroll_popup"] is True
    assert defaults["with_agent"] == "claude"


def test_session_defaults_with_agent_true_means_default(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    _write_config(cfg, {"withAgent": True})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    # `true` requests the default agent without naming it.
    assert defaults["with_agent"] is True


def test_session_defaults_absent_keys_are_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    _write_config(cfg, {"record": False})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults["record"] is False
    assert defaults["experimental_scroll_popup"] is None
    assert defaults["with_agent"] is None


def test_session_defaults_missing_file_all_none(monkeypatch, tmp_path):
    cfg = tmp_path / "does-not-exist.json"
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults == {
        "record": None,
        "experimental_scroll_popup": None,
        "with_agent": None,
    }


def test_session_defaults_invalid_json_all_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    assert defaults == {
        "record": None,
        "experimental_scroll_popup": None,
        "with_agent": None,
    }


def test_session_defaults_non_bool_values_are_none(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    _write_config(cfg, {"record": "yes", "withAgent": 1})
    monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(cfg))

    defaults = config.session_defaults()

    # record only accepts real booleans; withAgent only str or `true`.
    assert defaults["record"] is None
    assert defaults["with_agent"] is None

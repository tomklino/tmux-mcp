from pathlib import Path


def test_plugin_file_exists_and_references_scripts():
    plugin = Path(__file__).parent / "plugin" / "tmux-mcp-permissions.tmux"
    assert plugin.exists()

    content = plugin.read_text(encoding="utf-8")

    # Basic sanity checks: keybinding + status segment wired to our scripts
    assert "bind-key P" in content
    assert "tmux_mcp_toggle.py" in content
    assert "tmux_mcp_status.py" in content
    assert "status-right" in content
    assert "status-interval 5" in content

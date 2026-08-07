from pathlib import Path


def test_pi_image_bakes_tmux_mcp_prompt_flag_disabled():
    dockerfile = Path("docker/pi.Dockerfile").read_text(encoding="utf-8")
    assert "/root/.config/tmux-mcp/config.yaml" in dockerfile
    assert "promptSetupPiMcp: false" in dockerfile


def test_pi_image_keeps_container_managed_mcp_config_only():
    dockerfile = Path("docker/pi.Dockerfile").read_text(encoding="utf-8")
    assert "/root/.pi/agent/mcp.json" in dockerfile
    assert "/root/.pi-host" not in dockerfile
    assert "sandbox-state" not in dockerfile


def test_pi_runtime_does_not_special_case_mcp_cache_mounts_in_image():
    dockerfile = Path("docker/pi.Dockerfile").read_text(encoding="utf-8")
    assert "mcp-cache.json" not in dockerfile

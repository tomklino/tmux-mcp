from pathlib import Path

import pytest

from tmux_mcp import container_runtime

from tmux_mcp import sandbox


def test_agent_prompt_extension_includes_session_and_container_notice():
    text = sandbox.build_agent_prompt_extension(session_name="green")

    assert "green" in text
    assert "container" in text.lower()
    assert "session_name='green'" in text


def test_choose_random_human_branch_name_avoids_existing(monkeypatch):
    names = iter(["calm-river", "bright-forest"])
    monkeypatch.setattr(sandbox, "generate_human_branch_name", lambda: next(names))

    chosen = sandbox.choose_worktree_branch_name(existing_names={"calm-river"})

    assert chosen == "bright-forest"


def test_plan_mount_for_non_git_directory_returns_direct_mount(tmp_path: Path):
    project_dir = tmp_path / "plain"
    project_dir.mkdir()

    plan = sandbox.plan_workspace_mount(project_dir)

    assert plan.mode == "direct"
    assert plan.host_path == project_dir.resolve()
    assert plan.branch_name is None


def test_plan_mount_for_git_directory_uses_branch_and_worktree(monkeypatch, tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(sandbox, "is_git_directory", lambda path: True)
    monkeypatch.setattr(sandbox, "choose_worktree_branch_name", lambda existing_names, requested_name=None: "green-hill")
    monkeypatch.setattr(
        sandbox,
        "default_worktree_path",
        lambda repo_root, branch_name: repo_root / ".tmux-mcp-worktrees" / branch_name,
    )

    plan = sandbox.plan_workspace_mount(repo_dir)

    assert plan.mode == "git-worktree"
    assert plan.branch_name == "green-hill"
    assert plan.host_path == repo_dir / ".tmux-mcp-worktrees" / "green-hill"


def test_plan_mount_for_git_directory_preserves_requested_branch(monkeypatch, tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(sandbox, "is_git_directory", lambda path: True)
    monkeypatch.setattr(
        sandbox,
        "choose_worktree_branch_name",
        lambda existing_names, requested_name=None: requested_name,
    )
    monkeypatch.setattr(
        sandbox,
        "default_worktree_path",
        lambda repo_root, branch_name: repo_root / ".tmux-mcp-worktrees" / branch_name,
    )

    plan = sandbox.plan_workspace_mount(repo_dir, branch_name="feature-sandbox")

    assert plan.branch_name == "feature-sandbox"
    assert plan.host_path == repo_dir / ".tmux-mcp-worktrees" / "feature-sandbox"


def test_agent_image_name_for_pi():
    assert sandbox.agent_image_name("pi") == "tmux-mcp-sandbox-pi"


def test_agent_image_name_for_claude():
    assert sandbox.agent_image_name("claude") == "tmux-mcp-sandbox-claude"


def test_agent_image_name_requires_supported_agent():
    with pytest.raises(ValueError):
        sandbox.agent_image_name("unknown")


def test_default_runtime_is_docker_plugin():
    runtime = sandbox.default_container_runtime()

    assert runtime.name == "docker"


def test_sandbox_container_name_uses_session_name(monkeypatch):
    runtime = sandbox.default_container_runtime()

    monkeypatch.setattr(sandbox.random, "choices", lambda seq, k: list("abc"))

    assert runtime.container_name("green") == "tmux-mcp-sandbox-green-abc"


def test_docker_runtime_run_command_for_pi_agent(monkeypatch, tmp_path: Path):
    runtime = sandbox.default_container_runtime()
    monkeypatch.setattr(sandbox.random, "choices", lambda seq, k: list("abc"))
    monkeypatch.setattr(container_runtime.Path, "home", lambda: tmp_path)

    agent_dir = tmp_path / ".pi" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "auth.json").write_text("{}", encoding="utf-8")
    (agent_dir / "models.json").write_text("{}", encoding="utf-8")
    (agent_dir / "mcp-cache.json").write_text("{}", encoding="utf-8")

    command = runtime.run_container_command(
        container_name="tmux-mcp-sandbox-green-abc",
        session_name="green",
        agent="pi",
        prompt_extension="inside a container",
    )

    assert command[:6] == [
        "docker",
        "run",
        "--rm",
        "-it",
        "--name",
        "tmux-mcp-sandbox-green-abc",
    ]
    assert "-e" in command
    assert "TMUX_MCP_PROMPT_EXTENSION=inside a container" in command
    assert "-v" in command
    assert f"{agent_dir / 'auth.json'}:/root/.pi/agent/auth.json:ro" in command
    assert f"{agent_dir / 'models.json'}:/root/.pi/agent/models.json:ro" in command
    assert f"{agent_dir / 'mcp-cache.json'}:/root/.pi/agent/mcp-cache.json:ro" not in command
    assert command[-5:] == [
        "/opt/tmux-mcp-venv/bin/tmux-cli",
        "new",
        "green",
        "--with-agent=pi",
        "--sandbox=false",
    ]


def test_docker_runtime_only_mounts_existing_pi_files(monkeypatch, tmp_path: Path):
    runtime = sandbox.default_container_runtime()
    monkeypatch.setattr(container_runtime.Path, "home", lambda: tmp_path)

    agent_dir = tmp_path / ".pi" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "settings.json").write_text("{}", encoding="utf-8")

    command = runtime.run_container_command(
        container_name="tmux-mcp-sandbox-green-abc",
        session_name="green",
        agent="pi",
        prompt_extension="inside a container",
    )

    mounts = [part for part in command if ":/root/.pi/agent/" in part]
    assert mounts == [f"{agent_dir / 'settings.json'}:/root/.pi/agent/settings.json:ro"]

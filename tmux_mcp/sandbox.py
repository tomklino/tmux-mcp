from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random

from tmux_mcp.container_runtime import default_container_runtime


ADJECTIVES = [
    "calm",
    "bright",
    "gentle",
    "swift",
    "amber",
    "silver",
    "green",
    "quiet",
]

NOUNS = [
    "river",
    "forest",
    "hill",
    "meadow",
    "falcon",
    "brook",
    "sunrise",
    "harbor",
]


@dataclass(frozen=True)
class WorkspaceMountPlan:
    mode: str
    host_path: Path
    branch_name: str | None


def build_agent_prompt_extension(session_name: str) -> str:
    return (
        "You are running inside a container sandbox. "
        f"Use the tmux session named '{session_name}' for terminal access. "
        f"Always pass session_name='{session_name}' when using tmux MCP tools."
    )


def generate_human_branch_name() -> str:
    return f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}"


def choose_worktree_branch_name(
    existing_names: set[str], requested_name: str | None = None
) -> str:
    if requested_name:
        return requested_name

    while True:
        candidate = generate_human_branch_name()
        if candidate not in existing_names:
            return candidate


def is_git_directory(path: Path) -> bool:
    return (path / ".git").exists()


def default_worktree_path(repo_root: Path, branch_name: str) -> Path:
    return repo_root / ".tmux-mcp-worktrees" / branch_name


def agent_image_name(agent: str) -> str:
    if agent not in {"pi", "claude"}:
        raise ValueError(f"unsupported agent: {agent}")
    return f"tmux-mcp-sandbox-{agent}"


def plan_workspace_mount(
    project_dir: Path, branch_name: str | None = None
) -> WorkspaceMountPlan:
    project_dir = project_dir.resolve()

    if not is_git_directory(project_dir):
        return WorkspaceMountPlan(
            mode="direct",
            host_path=project_dir,
            branch_name=None,
        )

    chosen_branch = choose_worktree_branch_name(set(), requested_name=branch_name)
    return WorkspaceMountPlan(
        mode="git-worktree",
        host_path=default_worktree_path(project_dir, chosen_branch),
        branch_name=chosen_branch,
    )

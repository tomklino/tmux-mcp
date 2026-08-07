from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import random
import string

from tmux_mcp import sandbox


PI_AGENT_LOGIN_FILES = (
    "auth.json",
    "models.json",
    "models-store.json",
    "settings.json",
)


class ContainerRuntime(Protocol):
    @property
    def name(self) -> str: ...

    def container_name(self, session_name: str) -> str: ...
    def run_container_command(
        self,
        container_name: str,
        session_name: str,
        agent: str,
        prompt_extension: str,
    ) -> list[str]: ...


@dataclass(frozen=True)
class DockerRuntime:
    name: str = "docker"

    def container_name(self, session_name: str) -> str:
        suffix = "".join(random.choices(string.ascii_lowercase, k=3))
        return f"tmux-mcp-sandbox-{session_name}-{suffix}"

    def _pi_file_mounts(self) -> list[str]:
        agent_dir = Path.home() / ".pi" / "agent"
        mounts: list[str] = []

        for filename in PI_AGENT_LOGIN_FILES:
            host_path = agent_dir / filename
            if not host_path.is_file():
                continue
            mounts.extend([
                "-v",
                f"{host_path}:/root/.pi/agent/{filename}:ro",
            ])

        return mounts

    def run_container_command(
        self,
        container_name: str,
        session_name: str,
        agent: str,
        prompt_extension: str,
    ) -> list[str]:
        command = [
            "docker",
            "run",
            "--rm",
            "-it",
            "--name",
            container_name,
            "-e",
            f"TMUX_MCP_PROMPT_EXTENSION={prompt_extension}",
            *self._pi_file_mounts(),
            sandbox.agent_image_name(agent),
            "/opt/tmux-mcp-venv/bin/tmux-cli",
            "new",
            session_name,
            f"--with-agent={agent}",
            "--sandbox=false",
        ]
        return command


def default_container_runtime() -> ContainerRuntime:
    return DockerRuntime()

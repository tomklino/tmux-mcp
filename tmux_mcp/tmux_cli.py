#!/usr/bin/env python3

import argparse
import inspect
import json
import subprocess
import shutil
import sys

import datetime
import os
from pathlib import Path
from tmux_mcp import config
from tmux_mcp import tmux_lib


# Alias for testing
capture_pane = tmux_lib._capture_pane

TESTABLE_FUNCTIONS = [
    "capture_pane",
    "get_n_last_lines",
    "send_to_terminal",
    "execute_in_terminal",
    "get_last_command",
]

# Agent launched by a bare `--with-agent` (or config `withAgent: true`).
WITH_AGENT_DEFAULT = "claude"


def _resolve_flag(cli_value, config_value):
    """Return cli_value if explicitly set, else config_value, else False."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return False


def _resolve_agent(cli_value, config_value):
    """Resolve the split-pane agent. Returns (with_agent, agent_name).

    cli_value / config_value may be:
      None        -> not requested
      True        -> default agent (claude)
      "<name>"    -> launch that agent command
    The CLI value takes precedence over the config value.
    """
    value = cli_value if cli_value is not None else config_value
    if value is None or value is False:
        return False, WITH_AGENT_DEFAULT
    if value is True:
        return True, WITH_AGENT_DEFAULT
    return True, value


def cmd_new(args):
    """Create a new tmux session and attach to it."""
    color = args.session_name if tmux_lib.is_valid_color(args.session_name) else None

    cfg = config.session_defaults()
    record = _resolve_flag(args.record, cfg.get("record"))
    scroll_popup = _resolve_flag(args.experimental_scroll_popup, cfg.get("experimental_scroll_popup"))
    with_agent, agent = _resolve_agent(args.with_agent, cfg.get("with_agent"))

    # First-time UX: if user asked for Pi agent, offer to set up Pi MCP.
    if (
        with_agent
        and agent == "pi"
        and sys.stdin.isatty()
        and config.should_prompt_setup_pi_mcp()
    ):
        print("\nPi MCP setup detected (first time using --with-agent pi).")
        want = _prompt_yes(
            "Would you like tmux-cli to configure ~/.pi/agent/mcp.json for tmux-mcp and ensure pi-mcp-adapter is installed?"
        )
        # Flip the flag regardless of answer.
        try:
            config.set_prompt_setup_pi_mcp(False)
        except Exception:
            # Don't block session creation if config write fails.
            pass

        if want:
            if _ensure_pi_mcp_adapter_installed():
                _configure_pi_mcp()
            else:
                print(
                    f"  Skipping Pi MCP config because {PI_MCP_ADAPTER_PKG} could not be installed.",
                    file=sys.stderr,
                )

    if record:
        if shutil.which("asciinema") is None:
            print(
                    "Error: asciinema is not installed. Please install it to use the --record option. See https://docs.asciinema.org/getting-started for instructions.",
                    file=sys.stderr,
                )
            sys.exit(1)

    try:
        socket = tmux_lib.create_tmux_session(
            args.session_name,
            color=color,
            scroll_popup=scroll_popup,
            with_agent=with_agent,
            agent=agent,
            return_socket=True,
        )
    except tmux_lib.SessionNameConflictError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if socket:
        if color:
            print(f"Tmux session ready with {color} status bar: {args.session_name}")
        else:
            print(f"Tmux session ready: {args.session_name}")
        if record:
            recordings_dir = os.path.expanduser("~/.tmux-session-recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{recordings_dir}/{args.session_name}_{timestamp}.cast"
            subprocess.run(
                [
                    "asciinema",
                    "rec",
                    "--command",
                    f"tmux -L {socket} "
                    f"attach-session -t {args.session_name}",
                    filename,
                ]
            )
        else:
            attach_cmd: list[str] = [
                "tmux",
                "-L",
                socket,
                "attach-session",
                "-t",
                args.session_name,
            ]
            subprocess.run(attach_cmd, check=False)
    else:
        print(f"Failed to create tmux session: {args.session_name}", file=sys.stderr)
        sys.exit(1)


def cmd_test(args):
    """Test a tmux_lib function."""
    func_name = args.function
    if func_name not in TESTABLE_FUNCTIONS:
        print(f"Unknown function: {func_name}", file=sys.stderr)
        print(f"Available functions: {', '.join(TESTABLE_FUNCTIONS)}", file=sys.stderr)
        sys.exit(1)

    # Use the alias if that's what's passed
    if func_name == "capture_pane":
        func = capture_pane
    else:
        func = getattr(tmux_lib, func_name)

    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    # Parse arguments based on function signature
    func_args = args.args
    kwargs = {}

    for i, param_name in enumerate(params):
        param = sig.parameters[param_name]
        if i < len(func_args):
            value = func_args[i]
            # Type conversion based on annotation
            if param.annotation == int:
                value = int(value)
            elif param.annotation == float:
                value = float(value)
            elif param.annotation == bool:
                value = value.lower() in ("true", "1", "yes")
            kwargs[param_name] = value
        elif param.default is not inspect.Parameter.empty:
            continue  # Use default
        else:
            print(f"Missing required argument: {param_name}", file=sys.stderr)
            sys.exit(1)

    result = func(**kwargs)
    if result is not None:
        print(result)


MCP_SERVER_COMMAND = "tmux-mcp-server"
PI_MCP_ADAPTER_PKG = "pi-mcp-adapter"
PI_MCP_ADAPTER_INSTALL_SPEC = "npm:pi-mcp-adapter"


def _ensure_pi_mcp_adapter_installed() -> bool:
    """Ensure pi-mcp-adapter is installed in the current environment.

    Returns True if installed (or successfully installed), else False.
    """
    # Fast-path: if import works, we're good.
    try:  # pragma: no cover
        __import__("pi_mcp_adapter")
        return True
    except Exception:
        pass

    pi = shutil.which("pi")
    if not pi:
        print("  Error installing pi-mcp-adapter: `pi` command not found.", file=sys.stderr)
        return False

    print(
        f"  {PI_MCP_ADAPTER_PKG} not found; attempting to install it via `pi install {PI_MCP_ADAPTER_INSTALL_SPEC}`..."
    )
    result = subprocess.run(
        [pi, "install", PI_MCP_ADAPTER_INSTALL_SPEC],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        print(f"  Error installing {PI_MCP_ADAPTER_PKG}: {err}", file=sys.stderr)
        return False
    return True


def _configure_pi_mcp(pi_config: Path | None = None) -> bool:
    """Write Pi MCP config for tmux-mcp.

    Writes ~/.pi/agent/mcp.json to run tmux-mcp using the current interpreter.

    pi_config: override path for testing.
    """
    pi_config = pi_config or (Path.home() / ".pi" / "agent" / "mcp.json")
    pi_config.parent.mkdir(parents=True, exist_ok=True)

    # Use bash -lc to use allow using the installed python interperter from the
    # tmux-mcp installation venv without using a specific username in the config.
    python = sys.executable
    args = [
        "-lc",
        f"exec \"{python}\" -m tmux_mcp.tmux_mcp",
    ]

    try:
        data = json.loads(pi_config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Error reading {pi_config}: {exc}", file=sys.stderr)
        return False

    data.setdefault("mcpServers", {})["tmux"] = {
        "command": "bash",
        "args": args,
    }

    try:
        pi_config.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"  Error writing {pi_config}: {exc}", file=sys.stderr)
        return False

    print(f"  Wrote {pi_config}")
    print("  Reload Pi to pick up the new MCP config.")
    return True


def _prompt_yes(question: str) -> bool:
    answer = input(f"  {question} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def _configure_claude_code() -> bool:
    result = subprocess.run(
        ["claude", "mcp", "add", "--scope", "user", "tmux", MCP_SERVER_COMMAND],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Error: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _configure_opencode(config_path: Path) -> bool:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Error reading config: {exc}", file=sys.stderr)
        return False

    data.setdefault("mcp", {})["tmux"] = {
        "type": "local",
        "command": [MCP_SERVER_COMMAND],
        "enabled": True,
    }

    try:
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"  Error writing config: {exc}", file=sys.stderr)
        return False
    return True


def _configure_pi(config_path: Path) -> bool:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Error reading config: {exc}", file=sys.stderr)
        return False

    data.setdefault("mcpServers", {})["tmux"] = {
        "command": MCP_SERVER_COMMAND,
        "args": [],
    }

    try:
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"  Error writing config: {exc}", file=sys.stderr)
        return False
    return True


def cmd_setup_agents(args):
    """Detect installed agents and configure tmux-mcp for each."""
    found_any = False
    configured = 0

    if shutil.which("claude"):
        found_any = True
        print("Found: Claude Code")
        if _prompt_yes("Configure tmux-mcp for Claude Code?"):
            if _configure_claude_code():
                print("  Configured.")
                configured += 1

    opencode_config = Path.home() / ".config" / "opencode" / "opencode.json"
    if opencode_config.exists():
        found_any = True
        print("Found: OpenCode")
        if _prompt_yes("Configure tmux-mcp for OpenCode?"):
            if _configure_opencode(opencode_config):
                print("  Configured.")
                configured += 1

    pi_config = Path.home() / ".pi" / "agent" / "mcp.json"
    if pi_config.exists():
        found_any = True
        print("Found: Pi Agent")
        if _prompt_yes("Configure tmux-mcp for Pi Agent?"):
            if _configure_pi(pi_config):
                print("  Configured.")
                configured += 1

    if not found_any:
        print("No supported agents detected.")
        print("Manually add tmux-mcp-server to your agent's MCP config.")
        return

    if configured == 0:
        print("No agents configured.")
    else:
        print(f"\nConfigured {configured} agent(s). Restart your agent to pick up the changes.")


def main():
    parser = argparse.ArgumentParser(description="Tmux session management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # new subcommand
    new_parser = subparsers.add_parser("new", help="Create a new tmux session")
    new_parser.add_argument("session_name", help="Name for the tmux session")
    new_parser.add_argument(
        "--record",
        action="store_true",
        help="Record the tmux session using asciinema",
    )
    new_parser.add_argument(
        "--experimental-scroll-popup",
        action="store_true",
        help=(
            "Experimental: mouse-wheel-up on any pane opens a popup "
            "viewer of the pane's piped output (via less) instead of "
            "entering copy-mode. Installs per-session hooks and a "
            "WheelUpPane key bind gated on @tmux_mcp_managed."
        ),
    )
    new_parser.add_argument(
        "--with-agent",
        nargs="?",
        const=WITH_AGENT_DEFAULT,
        default=None,
        metavar="AGENT",
        help=(
            "Split the window side-by-side and launch an agent in the right "
            "pane, with added context telling it the terminal it controls "
            "is named after the session. MCP keeps driving the left shell "
            f"pane. Bare --with-agent launches '{WITH_AGENT_DEFAULT}'; pass "
            "--with-agent=<cmd> to launch a different agent."
        ),
    )
    new_parser.set_defaults(func=cmd_new)

    # test subcommand
    test_parser = subparsers.add_parser("test", help="Test a tmux_lib function")
    test_parser.add_argument(
        "function", help=f"Function to test: {', '.join(TESTABLE_FUNCTIONS)}"
    )
    test_parser.add_argument(
        "args", nargs="*", help="Arguments to pass to the function"
    )
    test_parser.set_defaults(func=cmd_test)

    # setup-agents subcommand
    setup_parser = subparsers.add_parser(
        "setup-agents",
        help="Detect installed agents and configure tmux-mcp for each",
    )
    setup_parser.set_defaults(func=cmd_setup_agents)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

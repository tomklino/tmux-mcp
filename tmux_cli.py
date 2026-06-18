#!/usr/bin/env python3

import argparse
import inspect
import subprocess
import shutil
import sys

import datetime
import os
import config
import tmux_lib


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
    scroll_popup = _resolve_flag(
        args.experimental_scroll_popup, cfg.get("experimental_scroll_popup")
    )
    with_claude, agent = _resolve_agent(args.with_agent, cfg.get("with_agent"))

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
            with_claude=with_claude,
            agent=agent,
            return_socket=True,
        )
    except tmux_lib.SessionNameConflictError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except tmux_lib.UnsupportedTmuxVersionError as exc:
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
            subprocess.run([
                "tmux", "-L", socket,
                "attach-session", "-t", args.session_name,
            ])
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


def main():
    parser = argparse.ArgumentParser(description="Tmux session management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # new subcommand
    new_parser = subparsers.add_parser("new", help="Create a new tmux session")
    new_parser.add_argument("session_name", help="Name for the tmux session")
    new_parser.add_argument(
        "--record",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Record the tmux session using asciinema "
            "(--no-record overrides a config-file default of true)"
        ),
    )
    new_parser.add_argument(
        "--experimental-scroll-popup",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Experimental: mouse-wheel-up on any pane opens a popup "
            "viewer of the pane's full scrollback (via less) instead "
            "of entering copy-mode. Installs a WheelUpPane key bind "
            "gated on @tmux_mcp_scroll_popup. "
            "(--no-experimental-scroll-popup overrides a config-file "
            "default of true)"
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

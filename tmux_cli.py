#!/usr/bin/env python3

import argparse
import inspect
import subprocess
import sys

import datetime
import os
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


def cmd_new(args):
    """Create a new tmux session and attach to it."""
    # Check if session name is a valid color
    color = args.session_name if tmux_lib.is_valid_color(args.session_name) else None
    
    if tmux_lib.create_tmux_session(args.session_name, color=color):
        if color:
            print(f"Tmux session ready with {color} status bar: {args.session_name}")
        else:
            print(f"Tmux session ready: {args.session_name}")
        # Attach to the session
        if args.record:
            recordings_dir = os.path.expanduser("~/.tmux-session-recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{recordings_dir}/{args.session_name}_{timestamp}.cast"
            subprocess.run(
                [
                    "asciinema",
                    "rec",
                    "--command",
                    f"tmux attach-session -t {args.session_name}",
                    filename,
                ]
            )
        else:
            subprocess.run(["tmux", "attach-session", "-t", args.session_name])
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
        action="store_true",
        help="Record the tmux session using asciinema",
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

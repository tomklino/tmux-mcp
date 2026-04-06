#!/usr/bin/env python3
"""
MCP server for interacting with tmux sessions.
Provides tools to read terminal output and execute commands in tmux sessions.
"""

from mcp.server.fastmcp import FastMCP

import tmux_lib

mcp = FastMCP("tmux")


@mcp.tool()
def get_last_lines(session_name: str, lines: int = 10) -> str:
    """
    Get the last N lines from a tmux terminal session.
    Use this to check the current state of the terminal, see command output,
    or verify what's currently displayed on screen.
    Args:
        session_name: Name of the tmux session to read from
        lines: Number of lines to return (default: 10)
    Returns:
        The last N non-empty lines from the terminal
    """
    return tmux_lib.get_n_last_lines(session_name, lines)


@mcp.tool()
def send_command(
    session_name: str, command: str, prompt_verify_string: str | None = None
) -> str:
    """
    Send a command to the terminal without executing it.
    Use this for risky commands or when the user asks to only send the
    command. This allows the user to review the command and execute it
    by themselves.
    Args:
        session_name: Name of the tmux session
        command: Command text to send (will NOT have newline appended)
        prompt_verify_string: If provided, only send if the current prompt
            contains this string. Useful to ensure the terminal is ready.
    Returns:
        "sent" if command was sent, "prompt_mismatch" if verification failed
    """
    success = tmux_lib.send_to_terminal(session_name, command, prompt_verify_string)
    return "sent" if success else "prompt_mismatch"


@mcp.tool()
def send_interrupt(session_name: str) -> str:
    """
    Send CTRL+C interrupt to the terminal.
    Use this to cancel a running command or break out of an interactive prompt.
    Args:
        session_name: Name of the tmux session
    Returns:
        "sent" when the interrupt was sent
    """
    tmux_lib.send_interrupt(session_name)
    return "sent"


@mcp.tool()
def execute_command(
    session_name: str,
    command: str,
    sync: bool = True,
    timeout: float = 30.0,
    prompt_verify_string: str | None = None,
) -> dict:
    """
    Execute a command in the terminal and wait for it to complete.
    Use this for commands where you need to see the output before proceeding.
    The function waits until a new prompt appears, indicating the command
    has finished.
    Args:
        session_name: Name of the tmux session
        command: Command to execute (newline will be appended automatically)
        timeout: Maximum seconds to wait for completion (default: 30)
        prompt_verify_string: If provided, only execute if the current prompt
            contains this string. Useful to ensure you're targeting the correct cluster.
    Returns:
        Dictionary with 'prompt', 'command', 'output', and 'status' keys.
        Status is "free" if completed, "interactive" if an interactive program
        was detected, "timeout" if the command didn't complete within the timeout
        period, or "prompt_mismatch" if prompt verification failed.
    """
    try:
        result = tmux_lib.execute_in_terminal(
            session_name,
            command,
            prompt_verify_string=prompt_verify_string,
            sync=sync,
            timeout=timeout,
        )
        if result is None:
            return {"prompt": "", "command": "", "output": "", "status": "timeout"}
        if isinstance(result, str):
            return {"prompt": "", "command": "", "output": result, "status": "free"}
        return {
            "prompt": result.prompt,
            "command": result.command,
            "output": result.output,
            "status": result.status,
        }
    except tmux_lib.PromptVerificationError:
        return {"prompt": "", "command": "", "output": "", "status": "prompt_mismatch"}


@mcp.tool()
def wait_for_completion(session_name: str, timeout: float = 30.0) -> dict:
    """
    Wait for a previously sent command to complete.
    Use this after send_command or after execute_command times out - when you need
    to wait for the command to finish and retrieve its output. Polls the terminal
    until a new empty prompt appears.
    Args:
        session_name: Name of the tmux session
        timeout: Maximum seconds to wait for completion (default: 30)
    Returns:
        Dictionary with 'prompt', 'command', 'output', and 'status' keys.
        Status is "free" if completed, "interactive" if an interactive program
        (e.g., less, vim, nano) was detected, or "timeout" if the command didn't
        complete within the timeout period.
    """
    result = tmux_lib.wait_for_command_completion(session_name, timeout)
    if result is None:
        return {"prompt": "", "command": "", "output": "", "status": "timeout"}
    return {
        "prompt": result.prompt,
        "command": result.command,
        "output": result.output,
        "status": result.status,
    }


@mcp.tool()
def get_last_command_output(session_name: str) -> dict:
    """
    Extract the last command and its output from the terminal.
    Use this to get structured information about what command was run
    and what output it produced.
    Args:
        session_name: Name of the tmux session
    Returns:
        Dictionary with 'prompt', 'command', and 'output' keys,
        or {'error': 'no_command_found'} if no command was detected
    """
    result = tmux_lib.get_last_command(session_name)
    if result is None:
        return {"error": "no_command_found"}
    return {"prompt": result.prompt, "command": result.command, "output": result.output}


if __name__ == "__main__":
    mcp.run()

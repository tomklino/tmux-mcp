# tmux_lib.py

import re
import subprocess
import sys
import time
from typing import NamedTuple

# This special prompt arrow is used to reliably find command prompts.
PROMPT_ARROW = "__>"


class CommandOutput(NamedTuple):
    prompt: str
    command: str
    output: str
    status: str  # "free", "running", or "interactive"


class PromptVerificationError(Exception):
    """Raised when terminal prompt verification fails."""

    pass


# PS1 prompt to be set in the tmux session.
TMUX_PS1 = r"$(kube_ps1)%(?:%{%}%1{__>%} :%{%}%1{__>%} ) %{%}%c%{%} "


def create_tmux_session(session_name: str) -> bool:
    """
    Create a new detached tmux session with predefined settings and PS1.
    Attaches to existing session if one already exists.
    Args:
        session_name: Name for the tmux session
    Returns:
        True if session was created/attached successfully, False otherwise
    """
    # Create a new detached session, or attach if it already exists
    create_result = subprocess.run(
        ["tmux", "new-session", "-Ad", "-s", session_name],
        capture_output=True,
        text=True,
    )
    if create_result.returncode != 0:
        print(f"Failed to create tmux session: {create_result.stderr}", file=sys.stderr)
        return False

    # Set scrollback buffer size
    subprocess.run(
        ["tmux", "set-option", "-g", "history-limit", "250000"],
        capture_output=True,
        text=True,
    )

    # Enable mouse mode
    subprocess.run(
        ["tmux", "set-option", "-g", "mouse", "on"], capture_output=True, text=True
    )

    # Set the PS1 prompt
    ps1_export = f"export PS1='{TMUX_PS1}'\n"
    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, ps1_export],
        capture_output=True,
        text=True,
    )

    return True


def _capture_pane(session_name: str) -> str:
    """
    Capture the current pane content.
    Args:
        session_name: Name of the tmux session
    Returns:
        The captured pane content as a string
    """
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-S", "-", "-t", session_name],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_n_last_lines(session_name: str, lines: int = 10) -> str:
    """
    Get the last N lines from the terminal.
    Args:
        session_name: Name of the tmux session
        lines: Number of lines to return (default: 10)
    Returns:
        The last N lines as a string
    """
    content = _capture_pane(session_name)
    content_lines = content.split("\n")

    # Strip control characters from each line
    cleaned_lines = []
    for line in content_lines:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", line)
        cleaned_lines.append(cleaned)

    # Find first and last non-empty lines to trim padding
    first_content = 0
    for i, line in enumerate(cleaned_lines):
        if line.strip():
            first_content = i
            break

    last_content = len(cleaned_lines) - 1
    for i in range(len(cleaned_lines) - 1, -1, -1):
        if cleaned_lines[i].strip():
            last_content = i
            break

    # Get content between first and last non-empty lines (inclusive)
    trimmed = cleaned_lines[first_content : last_content + 1]

    return "\n".join(trimmed[-lines:])


def _verify_terminal_prompt(session_name: str, verify_string: str) -> bool:
    """
    Verify if the terminal prompt contains a specific string.
    Args:
        session_name: Name of the tmux session
        verify_string: String to check for in the prompt
    Returns:
        True if the string is found, False otherwise
    """
    content = _capture_pane(session_name)
    lines = content.rstrip("\n").split("\n")
    # Check the last non-empty line for prompt
    last_line = ""
    for line in reversed(lines):
        if line.strip():
            last_line = line
            break

    return verify_string in last_line


def send_to_terminal(
    session_name: str, command: str, prompt_verify_string: str | None = None
) -> bool:
    """
    Send a command to the terminal without waiting for completion.
    Args:
        session_name: Name of the tmux session
        command: Command to send
        prompt_verify_string: If provided, only send if prompt contains this
    Returns:
        True if command was sent, False if prompt verification failed
    """
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            session_name=session_name, verify_string=prompt_verify_string
        ):
            return False

    # In tmux, send-keys sends keys, so no need to escape newlines
    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, command],
        capture_output=True,
        text=True,
    )
    return True


def send_interrupt(session_name: str) -> None:
    """
    Send CTRL+C interrupt to the terminal.
    Args:
        session_name: Name of the tmux session
    """
    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, "C-c"], capture_output=True, text=True
    )


def wait_for_command_completion(
    session_name: str, timeout: float = 30, poll_interval: float = 0.001
) -> str | None:
    """
    Wait for a command to complete by polling for a new empty prompt.
    Args:
        session_name: Name of the tmux session
        timeout: Maximum time to wait for command completion (seconds)
        poll_interval: How often to check for completion (seconds)
    Returns:
        Command output if completed, None if timeout
    """
    start_time = time.time()
    last_output = None
    while time.time() - start_time < timeout:
        time.sleep(poll_interval)

        result = get_last_command(session_name)
        if result is None:
            continue

        if result.status == "free":
            return result.output

        # Command still running - store output for potential return
        last_output = result.output

    return last_output  # Return last captured output on timeout


def execute_in_terminal(
    session_name: str,
    command: str,
    prompt_verify_string: str | None = None,
    sync: bool = True,
    timeout: float = 30.0,
    poll_interval: float = 0.001,
) -> str | None:
    """
    Execute a command in the terminal.
    Args:
        session_name: Name of the tmux session
        command: Command to execute
        prompt_verify_string: If provided, only execute if prompt contains this
        sync: If True, wait for command to finish and return output
        timeout: Maximum time to wait for command completion (seconds)
        poll_interval: How often to check for completion (seconds)
    Returns:
        If sync=True: Full output including prompts, or None if verification
            failed or timeout
        If sync=False: Empty string on success, None if verification failed
    """
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            session_name=session_name, verify_string=prompt_verify_string
        ):
            raise PromptVerificationError(
                f"Prompt does not contain '{prompt_verify_string}'"
            )

    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, command + "\n"],
        capture_output=True,
        text=True,
    )
    if not sync:
        return ""

    return wait_for_command_completion(session_name, timeout, poll_interval)


def get_last_command(session_name: str) -> CommandOutput | None:
    """
    Extract the last command and its output from terminal output.
    Args:
        session_name: Name of the tmux session
    Returns:
        CommandOutput with prompt, command, and output, or None if not found
    """
    terminal_output = _capture_pane(session_name)
    lines = terminal_output.strip().split("\n")

    # Find all prompt line indices (lines containing the prompt arrow)
    prompt_indices = []
    for i, line in enumerate(lines):
        if PROMPT_ARROW not in line:
            continue
        # Split on the arrow and take everything after it
        parts = line.split(PROMPT_ARROW, 1)
        after_arrow = parts[1] if len(parts) > 1 else ""
        # Extract prompt (directory/git info) and command
        tokens = after_arrow.strip().split()
        if not tokens:
            prompt_indices.append((i, "", ""))
            continue
        # Find where command starts (after dir and optional git:(branch))
        cmd_start = 1
        if len(tokens) > 1 and tokens[1].startswith("git:("):
            cmd_start = 2
        prompt = PROMPT_ARROW + " " + " ".join(tokens[:cmd_start])
        command = " ".join(tokens[cmd_start:])
        prompt_indices.append((i, prompt, command))

    if not prompt_indices:
        return None

    # If the last prompt has no command, the terminal is idle - use second-to-last
    # If the last prompt has a command, it's still running - use the last one
    last_idx, last_prompt, last_command = prompt_indices[-1]
    if last_command:
        idx, prompt, command = last_idx, last_prompt, last_command
        status = "running"
    elif len(prompt_indices) < 2:
        return None
    else:
        idx, prompt, command = prompt_indices[-2]
        status = "free"

    # Output is everything from this prompt line to the end
    output_lines = lines[idx:]
    output = "\n".join(output_lines)

    return CommandOutput(prompt=prompt, command=command, output=output, status=status)


def main():
    if len(sys.argv) < 2:
        print("Usage: tmux_lib.py <session_name>", file=sys.stderr)
        sys.exit(1)

    session_name = sys.argv[1]

    result = get_last_command(session_name)
    if result is None:
        print("No command found", file=sys.stderr)
        sys.exit(1)

    # print(result.prompt)
    # print(result.command)
    # print(result.output)
    print(result.status)


if __name__ == "__main__":
    main()

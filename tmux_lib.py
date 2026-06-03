# tmux_lib.py

import re
import subprocess
import sys
import time
import random
import string
from typing import NamedTuple

from colors import VALID_COLORS

import config
import permissions

from pathlib import Path

# This special prompt arrow is used to reliably find command prompts.
PROMPT_ARROW = "__>"

# Seconds to wait before confirming interactive mode to avoid false positives
INTERACTIVE_DETECTION_DELAY = 1.0

# Suffix appended to the default socket to derive the dedicated socket
# for sessions that opt into the experimental scroll-popup behaviour.
# The popup needs server-global key rebinds (WheelUpPane) that would
# otherwise leak into non-experimental sessions on the same server.
SCROLL_POPUP_SUFFIX = "-experimental-scroll"


def default_socket() -> str:
    """Default tmux socket name. Wraps config.default_socket()."""
    return config.default_socket()


def scroll_popup_socket() -> str:
    """Socket hosting sessions with the experimental scroll-popup feature."""
    return default_socket() + SCROLL_POPUP_SUFFIX


def managed_sockets() -> list[str]:
    """Every tmux socket this build of tmux-buddy knows how to manage.

    Default first, then the experimental-scroll socket. Iterated by
    resolve_socket so newly-added sockets are automatically monitored
    even when no sessions live on them yet.
    """
    return [default_socket(), scroll_popup_socket()]


class SessionNameConflictError(Exception):
    """A session of the same name lives on a different managed socket."""

    def __init__(self, session_name: str, existing_socket: str, target_socket: str):
        self.session_name = session_name
        self.existing_socket = existing_socket
        self.target_socket = target_socket
        super().__init__(
            f"Session '{session_name}' already exists on socket "
            f"'{existing_socket}'; cannot create it on '{target_socket}'."
        )


class SessionNotFoundError(Exception):
    """The named session is not on any managed socket."""

    def __init__(self, session_name: str):
        self.session_name = session_name
        super().__init__(
            f"Session '{session_name}' was not found on any managed socket: "
            f"{managed_sockets()}"
        )


def resolve_socket(session_name: str) -> str:
    """Return the managed socket hosting `session_name`.

    Scans every socket in managed_sockets() on each call (no caching).
    Raises SessionNotFoundError if the name is not on any of them.
    """
    for socket in managed_sockets():
        result = subprocess.run(
            ["tmux", "-L", socket, "list-sessions", "-F", "#S"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and session_name in result.stdout.split("\n"):
            return socket
    raise SessionNotFoundError(session_name)


def is_valid_color(name: str) -> bool:
    """Check if a name is a valid color.

    Args:
        name: The name to check
    Returns:
        True if the name is a valid color, False otherwise
    """
    return name.lower() in VALID_COLORS


def _set_status_bar_color(socket: str, session_name: str, color: str) -> bool:
    """Set the tmux status bar background color on the given socket."""
    result = subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status-style", f"bg={color}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


class CommandOutput(NamedTuple):
    prompt: str
    command: str
    output: str
    status: str  # "free", "running", or "interactive"


class PromptVerificationError(Exception):
    """Raised when terminal prompt verification fails."""

    pass


# PS1 prompt to be set in the tmux session.
TMUX_PS1 = r"·$(kube_ps1) %c %(?.%F{green}__>.%F{red}__>)%f "


def _repo_script_path(script_name: str) -> str:
    """Return an absolute path to a script shipped with this repo."""

    return str((Path(__file__).resolve().parent / "scripts" / script_name))


# Perl filter stripping control sequences from the popup log so less -R
# only sees SGR colour codes and printable text. Mirrors the body of
# tmux-scroll-viewer's bin/log-view.sh.
_SCROLL_POPUP_FILTER = r"""
s/\x1b\][^\x1b\x07]*(?:\x07|\x1b\\)//g;
s/\x1b[PXk^_][^\x1b]*\x1b\\//g;
s/\x1b\[[\d;?]*[A-LN-Za-ln-z]//g;
s/\x1b[^\[\]PXk^_]//g;
s/\r+\n/\n/g;
s/[^\n]*\r//g;
s/\A\n+//;
"""


def _setup_scroll_popup(socket: str, session_name: str) -> None:
    """Install the wheel-up scroll-popup hooks/keybind on `socket`.

    Mouse-wheel-up opens a display-popup viewer of the piped pane log
    (via less -R) instead of entering copy-mode. The WheelUpPane bind
    is server-global, so this must run on the experimental-scroll
    socket only.
    """
    # Marker for the popup bind to gate on.
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "@tmux_mcp_scroll_popup", "1"],
        capture_output=True, text=True,
    )

    # Stash the perl filter on tmux env so the popup bind can read it
    # via $ENV{TMUX_MCP_FILTER} (avoids nested shell-quoting).
    subprocess.run(
        ["tmux", "-L", socket, "set-environment", "-t", session_name,
         "TMUX_MCP_FILTER", _SCROLL_POPUP_FILTER],
        capture_output=True, text=True,
    )

    # Mirror each new pane's raw output to /tmp/tmux-pane-<session>-<id>.log.
    pipe_cmd = (
        'pipe-pane -o '
        '"cat > /tmp/tmux-pane-#{session_name}-#{pane_id}.log"'
    )
    for hook in ("after-new-window", "after-split-window"):
        subprocess.run(
            ["tmux", "-L", socket, "set-hook", "-t", session_name,
             hook, pipe_cmd],
            capture_output=True, text=True,
        )

    cleanup_cmd = (
        'run-shell '
        '"rm -f /tmp/tmux-pane-#{hook_session_name}-#{hook_pane}.log"'
    )
    for hook in ("pane-exited", "pane-died"):
        subprocess.run(
            ["tmux", "-L", socket, "set-hook", "-t", session_name,
             hook, cleanup_cmd],
            capture_output=True, text=True,
        )

    # Start the pipe for the initial pane (guarded so re-running setup is a no-op;
    # `pipe-pane -o` toggles if a pipe is already open).
    guarded_pipe = (
        f'pipe-pane -t {session_name} '
        '"cat > /tmp/tmux-pane-#{session_name}-#{pane_id}.log"'
    )
    subprocess.run(
        ["tmux", "-L", socket, "if-shell", "-F", "-t", session_name,
         "#{?pane_pipe,0,1}", guarded_pipe],
        capture_output=True, text=True,
    )

    subprocess.run(
        ["tmux", "-L", socket, "unbind-key", "-T", "root", "WheelUpPane"],
        capture_output=True, text=True,
    )

    # Bind popup action to mouse-wheel up.
    popup_cmd = (
        'tmux display-popup -E -w 90% -h 90% '
        '"perl -0777 -pe \\"eval \\\\\\$ENV{TMUX_MCP_FILTER}\\" '
        '< /tmp/tmux-pane-#{session_name}-#{pane_id}.log '
        '| less --mouse -R -f -X -e +G" || true'
    )
    popup_action = f"run-shell -b '{popup_cmd}'"
    passthrough_cond = (
        '#{||:#{alternate_on},#{pane_in_mode},#{mouse_any_flag},'
        '#{!=:#{@tmux_mcp_scroll_popup},1}}'
    )
    subprocess.run(
        ["tmux", "-L", socket, "bind-key", "-T", "root", "WheelUpPane",
         "if-shell", "-F", passthrough_cond,
         "send-keys -M",
         popup_action],
        capture_output=True, text=True,
    )


def create_tmux_session(
    session_name: str,
    color: str | None = None,
    scroll_popup: bool = False,
    return_socket: bool = False,
) -> bool | str:
    """
    Create a new detached tmux session with predefined settings and PS1.
    Attaches to existing session if one already exists.
    Args:
        session_name: Name for the tmux session
        color: Optional color name to set the status bar background
        scroll_popup: If True, create on the experimental-scroll socket
            and install the wheel-up popup hooks.
        return_socket: If True, return the socket name (str) instead of a bool.
    Returns:
        True/socket-name on success, False on failure. Raises
        SessionNameConflictError if the name lives on another managed socket.
    """
    socket = scroll_popup_socket() if scroll_popup else default_socket()

    # Reject cross-socket dups: tmux new-session -A only sees the target socket.
    for other in managed_sockets():
        if other == socket:
            continue
        result = subprocess.run(
            ["tmux", "-L", other, "list-sessions", "-F", "#S"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and session_name in result.stdout.split("\n"):
            raise SessionNameConflictError(session_name, other, socket)

    # Create a new detached session, or attach if it already exists
    create_result = subprocess.run(
        ["tmux", "-L", socket, "new-session", "-Ad", "-s", session_name],
        capture_output=True,
        text=True,
    )
    if create_result.returncode != 0:
        print(f"Failed to create tmux session: {create_result.stderr}", file=sys.stderr)
        return False

    # Set scrollback buffer size
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "history-limit", "250000"],
        capture_output=True,
        text=True,
    )

    # Enable mouse mode
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "mouse", "on"],
        capture_output=True, text=True,
    )

    # Set terminal title
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "set-titles", "on"],
        capture_output=True, text=True
    )
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "set-titles-string", "#S / #W"],
        capture_output=True, text=True
    )

    # Set status bar color if a valid color is provided
    if color and is_valid_color(color):
        _set_status_bar_color(socket, session_name, color)

    # Set the PS1 prompt
    ps1_export = f"export PS1='{TMUX_PS1}'\n"
    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", session_name, ps1_export],
        capture_output=True,
        text=True,
    )

    # Ensure the session is registered in the permissions file (safe default).
    permissions.ensure_session_registered(session_name)

    # Apply tmux-mcp UX settings for sessions created via this tool.
    status_script = _repo_script_path("tmux_mcp_status.py")
    toggle_script = _repo_script_path("tmux_mcp_toggle.py")

    # Mark session as managed by tmux-mcp
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "@tmux_mcp_managed", "1"],
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status", "on"],
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status-interval", "5"],
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status-right", f"#( {status_script} --session '#S' )"],
        capture_output=True,
        text=True,
    )

    # Ctrl+] (global, gated on @tmux_mcp_managed): cycle permissions + refresh status.
    subprocess.run(
        ["tmux", "-L", socket, "bind-key", "-n", "C-]", "run-shell",
         f"[ "
         f"\"$(tmux show-option -t '#S' -qv @tmux_mcp_managed)\" = '1' "
         f"] && {toggle_script} --session '#S' >/dev/null 2>&1; tmux refresh-client -S"],
        capture_output=True,
        text=True,
    )

    if scroll_popup:
        _setup_scroll_popup(socket, session_name)

    return socket if return_socket else True


def _capture_pane(socket: str, session_name: str) -> str:
    """Capture the current pane content on the given socket."""
    result = subprocess.run(
        ["tmux", "-L", socket, "capture-pane", "-p", "-S", "-",
         "-t", session_name],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _detect_interactive_mode(terminal_output: str) -> str | None:
    """
    Check terminal output for hints of interactive programs.
    Returns the program name if detected, None otherwise.
    """
    lines = terminal_output.strip().split("\n")
    if not lines:
        return None

    last_line = lines[-1]

    if last_line.strip() == ":" and PROMPT_ARROW not in last_line:
        return "less"

    if last_line.strip() == "(END)" and PROMPT_ARROW not in last_line:
        return "less"

    if all(line.startswith("~") for line in lines[-5:] if line.strip()):
        return "vim"

    if last_line.startswith("^") or "GNU nano" in terminal_output:
        return "nano"

    return None


def get_n_last_lines(session_name: str, lines: int = 10) -> str:
    """
    Get the last N lines from the terminal.
    Args:
        session_name: Name of the tmux session
        lines: Number of lines to return (default: 10)
    Returns:
        The last N lines as a string
    """
    socket = resolve_socket(session_name)
    content = _capture_pane(socket, session_name)
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


def _verify_terminal_prompt(
    socket: str, session_name: str, verify_string: str
) -> bool:
    """Check whether the prompt on the named session contains a string."""
    content = _capture_pane(socket, session_name)
    lines = content.rstrip("\n").split("\n")
    # Check the last non-empty line for prompt
    last_line = ""
    for line in reversed(lines):
        if line.strip():
            last_line = line
            break

    return verify_string in last_line


def _generate_random_buffer_name(prefix: str = "") -> str:
    """
    Generate a random name to use as a temporary tmux buffer.
    Args:
        prefix: optional prefix for the buffer name
    Returns:
        The name of the generated buffer
    """
    random_characters = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{prefix}{"-" if len(prefix) > 0 else ""}{random_characters}"


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
    socket = resolve_socket(session_name)
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            socket=socket,
            session_name=session_name,
            verify_string=prompt_verify_string,
        ):
            return False

    buffer_name = _generate_random_buffer_name(prefix=session_name)
    try:
        subprocess.run(
            ["tmux", "-L", socket, "set-buffer", "-b", buffer_name, command],
            capture_output=True, text=True
        )
        subprocess.run(
            ["tmux", "-L", socket, "paste-buffer", "-p", "-b", buffer_name,
             "-t", session_name],
            capture_output=True, text=True
        )
    finally:
        subprocess.run(
            ["tmux", "-L", socket, "delete-buffer", "-b", buffer_name],
            capture_output=True, text=True
        )

    return True


def send_interrupt(session_name: str) -> None:
    """Send CTRL+C interrupt to the terminal."""
    socket = resolve_socket(session_name)
    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", session_name, "C-c"],
        capture_output=True, text=True
    )


def wait_for_command_completion(
    session_name: str, timeout: float = 30, poll_interval: float = 0.001
) -> CommandOutput | None:
    """
    Wait for a command to complete by polling for a new empty prompt.
    Args:
        session_name: Name of the tmux session
        timeout: Maximum time to wait for command completion (seconds)
        poll_interval: How often to check for completion (seconds)
    Returns:
        CommandOutput with status "free" if completed, "interactive" if
        interactive program detected, or None if timeout
    """
    socket = resolve_socket(session_name)
    return _wait_for_command_completion_on(
        socket, session_name, timeout, poll_interval
    )


def _wait_for_command_completion_on(
    socket: str,
    session_name: str,
    timeout: float = 30,
    poll_interval: float = 0.001,
) -> CommandOutput | None:
    """Caller supplies the socket; avoids re-resolving on every poll."""
    start_time = time.time()
    last_output = None

    interactive_hint_detected_at: float | None = None
    interactive_hint_output: str | None = None

    while time.time() - start_time < timeout:
        time.sleep(poll_interval)

        result = _get_last_command_on(socket, session_name)
        if result is None:
            continue

        if result.status == "free":
            return result

        hint = _detect_interactive_mode(result.output)
        current_time = time.time()

        if hint:
            if interactive_hint_detected_at is None:
                interactive_hint_detected_at = current_time
                interactive_hint_output = result.output
            elif (
                current_time - interactive_hint_detected_at
                >= INTERACTIVE_DETECTION_DELAY
            ):
                if result.output == interactive_hint_output:
                    return CommandOutput(
                        prompt=result.prompt,
                        command=result.command,
                        output=result.output,
                        status="interactive",
                    )
        else:
            interactive_hint_detected_at = None
            interactive_hint_output = None

        last_output = result.output

    if last_output is not None:
        return CommandOutput(
            prompt="", command="", output=last_output, status="timeout"
        )
    return None


def execute_in_terminal(
    session_name: str,
    command: str,
    prompt_verify_string: str | None = None,
    sync: bool = True,
    timeout: float = 30.0,
    poll_interval: float = 0.001,
) -> str | CommandOutput | None:
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
        If sync=True: CommandOutput with output and status, or None if timeout
        If sync=False: Empty string on success, None if verification failed
    """
    socket = resolve_socket(session_name)
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            socket=socket,
            session_name=session_name,
            verify_string=prompt_verify_string,
        ):
            raise PromptVerificationError(
                f"Prompt does not contain '{prompt_verify_string}'"
            )

    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", session_name,
         command + "\n"],
        capture_output=True,
        text=True,
    )
    if not sync:
        return ""

    return _wait_for_command_completion_on(
        socket, session_name, timeout, poll_interval
    )


def get_last_command(session_name: str) -> CommandOutput | None:
    """Extract the last command and its output from the named session."""
    socket = resolve_socket(session_name)
    return _get_last_command_on(socket, session_name)


def _get_last_command_on(
    socket: str, session_name: str
) -> CommandOutput | None:
    """Caller supplies the socket."""
    terminal_output = _capture_pane(socket, session_name)
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

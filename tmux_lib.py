# tmux_lib.py

import re
import subprocess
import sys
import time
import random
import string
import logging
from typing import NamedTuple

from colors import VALID_COLORS

import config
import permissions

from pathlib import Path

# This special prompt arrow is used to reliably find command prompts.
PROMPT_ARROW = "__>"
PROMPT_PREFIX = "·"

# Seconds to wait before confirming interactive mode to avoid false positives
INTERACTIVE_DETECTION_DELAY = 1.0

# Suffix appended to the default socket to derive the dedicated socket
# for sessions that opt into the experimental scroll-popup behaviour.
# The popup needs server-global key rebinds (WheelUpPane) that would
# otherwise leak into non-experimental sessions on the same server.
SCROLL_POPUP_SUFFIX = "-experimental-scroll"
SCROLL_POPUP_MIN_TMUX_VERSION = "3.6a"


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


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("tmux_mcp")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_path = Path("~/tmux.logs").expanduser()
    handler = logging.FileHandler(log_path)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = _get_logger()


def _run_logged(args: list[str], **kwargs):
    log.info("subprocess.run args=%r kwargs=%r", args, kwargs)
    return subprocess.run(args, **kwargs)


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
        result = _run_logged(
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
    result = _run_logged(
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


class UnsupportedTmuxVersionError(Exception):
    """Raised when a feature requires a newer tmux version."""

    pass


# PS1 prompt to be set in the tmux session.
TMUX_PS1 = r"·$(kube_ps1) %c %(?.%F{green}__>.%F{red}__>)%f "


def _repo_script_path(script_name: str) -> str:
    """Return an absolute path to a script shipped with this repo."""

    return str((Path(__file__).resolve().parent / "scripts" / script_name))


def _parse_tmux_version(version_text: str) -> tuple[int, int, str]:
    """Parse `tmux -V` output like `tmux 3.6a` into comparable parts."""
    match = re.search(r"tmux\s+(\d+)\.(\d+)([a-z]?)", version_text.strip())
    if not match:
        raise ValueError(f"Unable to parse tmux version from: {version_text!r}")
    major, minor, suffix = match.groups()
    return int(major), int(minor), suffix or ""


def _tmux_version_at_least(current: str, minimum: str) -> bool:
    """Return True when `current` tmux version is >= `minimum`."""
    return _parse_tmux_version(current) >= _parse_tmux_version(f"tmux {minimum}")


def get_tmux_version() -> str:
    """Return the installed tmux version string from `tmux -V`."""
    result = _run_logged(["tmux", "-V"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def assert_scroll_popup_supported() -> None:
    """Fail if the installed tmux version does not support scroll popup."""
    version = get_tmux_version()
    if not _tmux_version_at_least(version, SCROLL_POPUP_MIN_TMUX_VERSION):
        raise UnsupportedTmuxVersionError(
            "--experimental-scroll-popup requires tmux "
            f"{SCROLL_POPUP_MIN_TMUX_VERSION}+; found {version}"
        )


def _setup_scroll_popup(socket: str, session_name: str) -> None:
    """Install the wheel-up scroll-popup keybind on `socket`.

    Mouse-wheel-up opens a display-popup viewer of the pane's full
    scrollback (captured live via `tmux capture-pane -e`, then piped
    into `less -R`) instead of entering copy-mode. The WheelUpPane
    bind is server-global, so this must run on the experimental-scroll
    socket only.
    """
    # Marker for the popup bind to gate on.
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "@tmux_mcp_scroll_popup", "1"],
        capture_output=True, text=True,
    )

    _run_logged(
        ["tmux", "-L", socket, "unbind-key", "-T", "root", "WheelUpPane"],
        capture_output=True, text=True,
    )

    # capture-pane -e keeps SGR colour escapes and drops everything else,
    # so less -R sees clean text. -J unwraps tmux's visual line-wrapping,
    # -S - asks for the full scrollback. #{pane_id} is the pane that
    # received the wheel event, expanded by tmux before the shell runs.
    popup_cmd = (
        'tmux display-popup -E -w 90% -h 90% '
        '"tmux capture-pane -e -p -J -S - -t #{pane_id} '
        '| less --mouse -R -f -X -e +G" || true'
    )
    popup_action = f"run-shell -b '{popup_cmd}'"
    passthrough_cond = (
        '#{||:#{alternate_on},#{pane_in_mode},#{mouse_any_flag},'
        '#{!=:#{@tmux_mcp_scroll_popup},1}}'
    )
    _run_logged(
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
        result = _run_logged(
            ["tmux", "-L", other, "list-sessions", "-F", "#S"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and session_name in result.stdout.split("\n"):
            raise SessionNameConflictError(session_name, other, socket)

    # Create a new detached session, or attach if it already exists
    create_result = _run_logged(
        ["tmux", "-L", socket, "new-session", "-Ad", "-s", session_name],
        capture_output=True,
        text=True,
    )
    if create_result.returncode != 0:
        print(f"Failed to create tmux session: {create_result.stderr}", file=sys.stderr)
        return False

    # Set scrollback buffer size
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "history-limit", "250000"],
        capture_output=True,
        text=True,
    )

    # Enable mouse mode
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "mouse", "on"],
        capture_output=True, text=True,
    )

    # Set terminal title
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "set-titles", "on"],
        capture_output=True, text=True
    )
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "set-titles-string", "#S / #W"],
        capture_output=True, text=True
    )

    # Set status bar color if a valid color is provided
    if color and is_valid_color(color):
        _set_status_bar_color(socket, session_name, color)

    # Set the PS1 prompt
    ps1_export = f"export PS1='{TMUX_PS1}'\n"
    _run_logged(
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
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "@tmux_mcp_managed", "1"],
        capture_output=True,
        text=True,
    )

    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status", "on"],
        capture_output=True,
        text=True,
    )
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status-interval", "5"],
        capture_output=True,
        text=True,
    )
    _run_logged(
        ["tmux", "-L", socket, "set-option", "-t", session_name,
         "status-right", f"#( {status_script} --session '#S' )"],
        capture_output=True,
        text=True,
    )

    # Ctrl+] (global, gated on @tmux_mcp_managed): cycle permissions + refresh status.
    _run_logged(
        ["tmux", "-L", socket, "bind-key", "-n", "C-]", "run-shell",
         f"[ "
         f"\"$(tmux show-option -t '#S' -qv @tmux_mcp_managed)\" = '1' "
         f"] && {toggle_script} --session '#S' >/dev/null 2>&1; tmux refresh-client -S"],
        capture_output=True,
        text=True,
    )

    if scroll_popup:
        assert_scroll_popup_supported()
        _setup_scroll_popup(socket, session_name)

    return socket if return_socket else True


def _capture_pane(socket: str, session_name: str) -> str:
    """Capture the current pane content on the given socket."""
    result = _run_logged(
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

    last_content = len(cleaned_lines)
    for i in range(len(cleaned_lines) - 1, -1, -1):
        if cleaned_lines[i].strip():
            last_content = i + 1
            break

    trimmed_lines = cleaned_lines[first_content:last_content]

    # Return last N lines
    return "\n".join(trimmed_lines[-lines:])


def get_last_command(session_name: str) -> tuple[str, str] | None:
    """
    Get the last command and its output from the terminal.
    Args:
        session_name: Name of the tmux session
    Returns:
        Tuple of (command, output) or None if no command found
    """
    socket = resolve_socket(session_name)
    content = _capture_pane(socket, session_name)
    lines = content.split("\n")

    prompt_line_idx = None
    prompt_text = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if PROMPT_ARROW in line:
            prompt_line_idx = i
            prompt_text = line
            break

    if prompt_line_idx is None:
        return None

    command = ""
    if prompt_text:
        prompt_pos = prompt_text.find(PROMPT_ARROW)
        command_start = prompt_pos + len(PROMPT_ARROW)
        command = prompt_text[command_start:].strip()

    output_lines = lines[prompt_line_idx + 1:]
    output = "\n".join(output_lines).rstrip()

    return command, output


def send_to_terminal(session_name: str, command: str) -> bool:
    """Send a command to the terminal without executing it."""
    socket = resolve_socket(session_name)
    result = subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", session_name, command],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _verify_prompt_contains(session_name: str, expected: str) -> bool:
    """Return True if the current prompt line contains the expected substring."""
    try:
        lines = get_n_last_lines(session_name, 10).split("\n")
        for line in reversed(lines):
            if PROMPT_ARROW in line or PROMPT_PREFIX in line:
                return expected in line
    except Exception:
        return False
    return False


def execute_in_terminal(
    session_name: str,
    command: str,
    timeout: float = 30.0,
    prompt_verify_string: str | None = None,
) -> CommandOutput:
    """Execute a command and wait for completion."""
    if prompt_verify_string and not _verify_prompt_contains(session_name, prompt_verify_string):
        raise PromptVerificationError(
            f"Prompt verification failed: expected '{prompt_verify_string}' in current prompt"
        )

    socket = resolve_socket(session_name)
    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", session_name, command, "Enter"],
        capture_output=True,
        text=True,
    )

    start_time = time.time()
    interactive_detected_at = None
    interactive_program = None

    while time.time() - start_time < timeout:
        content = _capture_pane(socket, session_name)
        lines = content.split("\n")
        last_non_empty = next((line for line in reversed(lines) if line.strip()), "")

        is_prompt = PROMPT_ARROW in last_non_empty

        current_interactive = _detect_interactive_mode(content)
        if current_interactive:
            if interactive_program != current_interactive:
                interactive_program = current_interactive
                interactive_detected_at = time.time()
            elif (time.time() - interactive_detected_at) >= INTERACTIVE_DETECTION_DELAY:
                result = get_last_command(session_name)
                if result:
                    cmd, output = result
                    return CommandOutput(prompt=last_non_empty, command=cmd, output=output, status="interactive")
                return CommandOutput(prompt=last_non_empty, command="", output=content.rstrip(), status="interactive")
        else:
            interactive_program = None
            interactive_detected_at = None

        if is_prompt:
            result = get_last_command(session_name)
            if result:
                cmd, output = result
                return CommandOutput(prompt=last_non_empty, command=cmd, output=output, status="free")
            return CommandOutput(prompt=last_non_empty, command="", output="", status="free")

        time.sleep(0.1)

    result = get_last_command(session_name)
    if result:
        cmd, output = result
        return CommandOutput(prompt="", command=cmd, output=output, status="running")
    return CommandOutput(prompt="", command="", output="", status="running")


def generate_session_name() -> str:
    adjectives = [
        "red", "blue", "green", "yellow", "purple", "orange", "pink", "brown",
        "gray", "black", "white", "silver", "gold", "cyan", "magenta", "lime",
        "navy", "teal", "maroon", "olive", "coral", "salmon", "violet", "indigo",
    ]
    nouns = [
        "tiger", "eagle", "shark", "wolf", "bear", "fox", "lion", "hawk",
        "panda", "otter", "falcon", "dolphin", "whale", "rabbit", "deer", "owl",
        "storm", "river", "mountain", "forest", "ocean", "desert", "thunder", "breeze",
    ]
    return f"{random.choice(adjectives)}-{random.choice(nouns)}-{''.join(random.choices(string.ascii_lowercase, k=4))}"

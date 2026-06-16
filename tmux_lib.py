# tmux_lib.py

import re
import shlex
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


# Session option holding the stable pane_id (e.g. "%5") that MCP tools must
# drive. Saved at creation time so MCP keeps targeting the original shell pane
# even after the user splits, moves, or re-lays-out the window.
TARGET_PANE_OPTION = "@tmux_mcp_target_pane"


def resolve_target(session_name: str) -> tuple[str, str]:
    """Return (socket, target) for MCP interaction with `session_name`.

    target is the saved shell pane_id when @tmux_mcp_target_pane is set,
    otherwise the session name itself (back-compat for sessions created
    before pane-id targeting existed).
    """
    socket = resolve_socket(session_name)
    result = _run_logged(
        ["tmux", "-L", socket, "show-option", "-t", session_name,
         "-qv", TARGET_PANE_OPTION],
        capture_output=True, text=True,
    )
    pane_id = result.stdout.strip() if result.returncode == 0 else ""
    return socket, (pane_id or session_name)


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
    # -B drops the popup border/frame; -w/-h/-x/-y size and place the popup
    # to overlay exactly the pane that was scrolled (matters in a split
    # layout, e.g. when an agent occupies the other pane).
    popup_cmd = (
        'tmux display-popup -E -B '
        '-w #{pane_width} -h #{pane_height} '
        '-x #{pane_left} -y #{pane_top} '
        '"tmux capture-pane -e -p -J -S - -t #{pane_id} '
        '| less --mouse -R -f -X -e -M +G" || true'
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


DEFAULT_AGENT = "claude"


def _agent_terminal_context(session_name: str) -> str:
    """System-prompt context telling the agent which terminal it controls."""
    return (
        "You share this tmux session with a human via the tmux-mcp server. "
        f"The terminal you run commands in (via the tmux MCP tools) is named "
        f"'{session_name}'. Always pass session_name='{session_name}' to those "
        "tools so your commands go to the correct terminal."
    )


def create_tmux_session(
    session_name: str,
    color: str | None = None,
    scroll_popup: bool = False,
    with_claude: bool = False,
    agent: str = DEFAULT_AGENT,
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
        with_claude: If True, split the window side-by-side and launch the
            agent in the right pane; the agent pane is left active.
        agent: The agent command to launch in the split pane (default 'claude').
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

    # Save the shell pane_id so MCP tools always drive this pane, even after
    # the user splits/moves the window later (see resolve_target).
    pane_result = _run_logged(
        ["tmux", "-L", socket, "display-message", "-p", "-t", session_name,
         "#{pane_id}"],
        capture_output=True, text=True,
    )
    shell_pane = pane_result.stdout.strip()
    if shell_pane:
        _run_logged(
            ["tmux", "-L", socket, "set-option", "-t", session_name,
             TARGET_PANE_OPTION, shell_pane],
            capture_output=True, text=True,
        )

    if with_claude:
        # Split side-by-side from the shell pane: shell stays left, agent
        # opens right and becomes the active pane (tmux default).
        agent_context = _agent_terminal_context(session_name)
        agent_cmd = f"{agent} --append-system-prompt {shlex.quote(agent_context)}"
        _run_logged(
            ["tmux", "-L", socket, "split-window", "-h",
             "-t", shell_pane or session_name, agent_cmd],
            capture_output=True, text=True,
        )

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
    socket, target = resolve_target(session_name)
    content = _capture_pane(socket, target)
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


def _generate_random_buffer_name(prefix: str = "") -> str:
    """Generate a random name to use as a temporary tmux buffer."""
    random_characters = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=4)
    )
    separator = "-" if prefix else ""
    return f"{prefix}{separator}{random_characters}"


def _verify_terminal_prompt(session_name: str, verify_string: str) -> bool:
    """Return True if the terminal's last non-empty line contains verify_string."""
    socket, target = resolve_target(session_name)
    content = _capture_pane(socket, target)
    lines = content.rstrip("\n").split("\n")
    last_line = ""
    for line in reversed(lines):
        if line.strip():
            last_line = line
            break
    return verify_string in last_line


def get_last_command(session_name: str, count: int | None = None):
    """Get the most recent command(s) and their output from tmux scrollback.

    Args:
        session_name: Name of the tmux session.
        count: Number of commands to return (most recent first).

    Returns:
        If count is omitted: a single CommandOutput (or None).
        If count is provided: a list[CommandOutput].
    """
    socket, target = resolve_target(session_name)
    terminal_output = _capture_pane(socket, target)
    lines = terminal_output.splitlines()

    # Gather prompt indices and parse prompt+command from each prompt line.
    prompts: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        if not line.startswith(PROMPT_PREFIX):
            continue
        if PROMPT_ARROW not in line:
            continue

        parts = line.split(PROMPT_ARROW, 1)
        after_arrow = parts[1] if len(parts) > 1 else ""
        tokens = after_arrow.strip().split()

        if not tokens:
            prompt = ""
            command = ""
        else:
            cmd_start = 1
            if len(tokens) > 1 and tokens[1].startswith("git:("):
                cmd_start = 2
            prompt = PROMPT_ARROW + " " + " ".join(tokens[:cmd_start])
            command = " ".join(tokens[cmd_start:])

        prompts.append((i, prompt, command))

    if not prompts:
        return None if count is None else []

    def _block_output(prompt_list_index: int) -> str:
        line_idx = prompts[prompt_list_index][0]
        next_line_idx = (
            prompts[prompt_list_index + 1][0]
            if prompt_list_index + 1 < len(prompts)
            else len(lines)
        )
        return "\n".join(lines[line_idx + 1 : next_line_idx]).rstrip("\n")

    if count is None:
        last_line_idx, last_prompt, last_command = prompts[-1]

        if last_command:
            chosen_line_idx, chosen_prompt, chosen_command = (
                last_line_idx,
                last_prompt,
                last_command,
            )
            status = "running"
        elif len(prompts) < 2:
            return None
        else:
            chosen_line_idx, chosen_prompt, chosen_command = prompts[-2]
            status = "free"

        # Legacy output includes the prompt line and runs to the end.
        output = "\n".join(lines[chosen_line_idx:])
        return CommandOutput(
            prompt=chosen_prompt, command=chosen_command, output=output, status=status
        )

    if count <= 0:
        return []

    results: list[CommandOutput] = []
    for idx_in_prompts, (_line_idx, prompt, command) in enumerate(prompts):
        if not command.strip():
            continue

        output = _block_output(idx_in_prompts)
        if not output.strip():
            continue

        results.append(
            CommandOutput(prompt=prompt, command=command, output=output, status="free")
        )

    window = results[-count:]
    window.reverse()
    return window


def send_to_terminal(
    session_name: str, command: str, prompt_verify_string: str | None = None
) -> bool:
    """Send a command to the terminal without executing it.

    Uses a temporary tmux buffer + bracketed paste so accidental
    execution can't occur. Returns False if prompt verification fails.
    """
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            session_name=session_name, verify_string=prompt_verify_string
        ):
            return False

    socket, target = resolve_target(session_name)
    buffer_name = _generate_random_buffer_name(prefix=session_name)
    try:
        subprocess.run(
            ["tmux", "-L", socket, "set-buffer", "-b", buffer_name, command],
            capture_output=True, text=True,
        )
        subprocess.run(
            ["tmux", "-L", socket, "paste-buffer", "-p", "-b", buffer_name,
             "-t", target],
            capture_output=True, text=True,
        )
    finally:
        subprocess.run(
            ["tmux", "-L", socket, "delete-buffer", "-b", buffer_name],
            capture_output=True, text=True,
        )

    return True


def send_interrupt(session_name: str) -> None:
    """Send CTRL+C interrupt to the terminal."""
    socket, target = resolve_target(session_name)
    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", target, "C-c"],
        capture_output=True, text=True,
    )


def wait_for_command_completion(
    session_name: str, timeout: float = 30, poll_interval: float = 0.001
) -> CommandOutput | None:
    """Wait for a command to complete by polling for a new empty prompt.

    Returns CommandOutput with status "free" if completed, "interactive"
    if an interactive program is detected, a "timeout" output if it timed
    out with output, or None if nothing was captured.
    """
    start_time = time.time()
    last_output = None

    interactive_hint_detected_at: float | None = None
    interactive_hint_output: str | None = None

    while time.time() - start_time < timeout:
        time.sleep(poll_interval)

        result = get_last_command(session_name)
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
    """Execute a command in the terminal.

    Args:
        session_name: Name of the tmux session
        command: Command to execute
        prompt_verify_string: If provided, only execute if prompt contains this
        sync: If True, wait for the command to finish and return output
        timeout: Maximum time to wait for command completion (seconds)
        poll_interval: How often to check for completion (seconds)

    Returns:
        If sync=True: CommandOutput with output and status, or None if timeout.
        If sync=False: empty string on success.
    """
    if prompt_verify_string is not None:
        if not _verify_terminal_prompt(
            session_name=session_name, verify_string=prompt_verify_string
        ):
            raise PromptVerificationError(
                f"Prompt does not contain '{prompt_verify_string}'"
            )

    socket, target = resolve_target(session_name)
    subprocess.run(
        ["tmux", "-L", socket, "send-keys", "-t", target, command + "\n"],
        capture_output=True,
        text=True,
    )
    if not sync:
        return ""

    return wait_for_command_completion(session_name, timeout, poll_interval)


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


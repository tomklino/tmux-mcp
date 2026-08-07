#!/usr/bin/env python3
"""Unit tests for _detect_interactive_mode in tmux_lib.py"""

import pytest
from tmux_mcp import tmux_lib
from tmux_mcp import permissions
from unittest.mock import MagicMock, call


class TestSocketTopology:
    """Tests for socket-name helpers (default_socket, scroll_popup_socket, managed_sockets)."""

    def test_scroll_popup_socket_suffixes_default(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "foo")
        assert tmux_lib.scroll_popup_socket() == "foo-experimental-scroll"

    def test_scroll_popup_socket_uses_fallback_when_unset(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("TMUX_MCP_SOCKET", raising=False)
        monkeypatch.setenv("TMUX_MCP_CONFIG_FILE", str(tmp_path / "missing.json"))
        assert tmux_lib.scroll_popup_socket() == "tmux-mcp-experimental-scroll"

    def test_managed_sockets_lists_both(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        sockets = tmux_lib.managed_sockets()
        assert sockets == ["tmux-mcp", "tmux-mcp-experimental-scroll"]

    def test_managed_sockets_reflects_custom_default(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "myname")
        assert tmux_lib.managed_sockets() == [
            "myname",
            "myname-experimental-scroll",
        ]


class TestResolveSocket:
    """resolve_socket scans managed sockets via tmux list-sessions.
    Returns the hosting socket; raises SessionNotFoundError if missing.
    Recomputes every call (no caching).
    """

    def _make_run(self, sessions_per_socket):
        """Fake subprocess.run honoring a {socket: {session, ...}} map.

        None as the value simulates a socket with no running server.
        """

        def _run(cmd, capture_output=True, text=True, check=False):
            assert cmd[:2] == ["tmux", "-L"]
            sock = cmd[2]
            if cmd[3:4] == ["list-sessions"]:
                value = sessions_per_socket.get(sock)
                if value is None:
                    return MagicMock(returncode=1, stdout="", stderr="no server")
                return MagicMock(
                    returncode=0,
                    stdout="\n".join(sorted(value)) + ("\n" if value else ""),
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        return _run

    def test_finds_session_on_default_socket(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        monkeypatch.setattr(
            tmux_lib.subprocess, "run",
            self._make_run({
                "tmux-mcp": {"green", "blue"},
                "tmux-mcp-experimental-scroll": set(),
            }),
        )
        assert tmux_lib.resolve_socket("green") == "tmux-mcp"

    def test_finds_session_on_experimental_socket(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        monkeypatch.setattr(
            tmux_lib.subprocess, "run",
            self._make_run({
                "tmux-mcp": {"blue"},
                "tmux-mcp-experimental-scroll": {"orange"},
            }),
        )
        assert tmux_lib.resolve_socket("orange") == "tmux-mcp-experimental-scroll"

    def test_raises_when_session_missing(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        monkeypatch.setattr(
            tmux_lib.subprocess, "run",
            self._make_run({
                "tmux-mcp": {"blue"},
                "tmux-mcp-experimental-scroll": {"orange"},
            }),
        )
        with pytest.raises(tmux_lib.SessionNotFoundError):
            tmux_lib.resolve_socket("nope")

    def test_skips_sockets_with_no_server(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        monkeypatch.setattr(
            tmux_lib.subprocess, "run",
            self._make_run({
                "tmux-mcp": None,
                "tmux-mcp-experimental-scroll": {"green"},
            }),
        )
        assert tmux_lib.resolve_socket("green") == "tmux-mcp-experimental-scroll"

    def test_recomputes_every_call(self, monkeypatch):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        calls: list[list[str]] = []

        def _run(cmd, capture_output=True, text=True, check=False):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="green\n", stderr="")

        monkeypatch.setattr(tmux_lib.subprocess, "run", _run)

        tmux_lib.resolve_socket("green")
        first_call_count = len(calls)
        tmux_lib.resolve_socket("green")
        assert len(calls) == first_call_count * 2


class TestPerSessionSocketPlumbing:
    """Each public op resolves the socket via resolve_socket and uses it.

    These tests pin `resolve_socket` to a known value and assert the
    socket actually used by subprocess.run matches.
    """

    @pytest.fixture
    def captured(self, monkeypatch):
        calls: list[list[str]] = []

        def _run(cmd, capture_output=True, text=True, check=False):
            calls.append(cmd)
            return MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

        monkeypatch.setattr(tmux_lib.subprocess, "run", _run)
        return calls

    @staticmethod
    def _sockets_used(calls: list[list[str]]) -> set[str]:
        out = set()
        for cmd in calls:
            if len(cmd) >= 3 and cmd[0] == "tmux" and cmd[1] == "-L":
                out.add(cmd[2])
        return out

    def test_send_interrupt_uses_resolved_socket(self, monkeypatch, captured):
        monkeypatch.setattr(
            tmux_lib, "resolve_socket", lambda name: "tmux-mcp-experimental-scroll"
        )
        tmux_lib.send_interrupt("orange")
        assert self._sockets_used(captured) == {"tmux-mcp-experimental-scroll"}

    def test_get_n_last_lines_uses_resolved_socket(self, monkeypatch, captured):
        monkeypatch.setattr(
            tmux_lib, "resolve_socket", lambda name: "tmux-mcp-experimental-scroll"
        )
        tmux_lib.get_n_last_lines("orange", lines=3)
        assert self._sockets_used(captured) == {"tmux-mcp-experimental-scroll"}

    def test_send_to_terminal_uses_resolved_socket(self, monkeypatch, captured):
        monkeypatch.setattr(
            tmux_lib, "resolve_socket", lambda name: "tmux-mcp-experimental-scroll"
        )
        monkeypatch.setattr(
            tmux_lib, "_generate_random_buffer_name", lambda prefix="": "buf"
        )
        tmux_lib.send_to_terminal("orange", "ls")
        # No verify string -> never reads pane; just buffer ops
        assert self._sockets_used(captured) == {"tmux-mcp-experimental-scroll"}

    def test_execute_in_terminal_uses_resolved_socket(self, monkeypatch, captured):
        monkeypatch.setattr(
            tmux_lib, "resolve_socket", lambda name: "tmux-mcp-experimental-scroll"
        )
        tmux_lib.execute_in_terminal("orange", "ls", sync=False)
        assert self._sockets_used(captured) == {"tmux-mcp-experimental-scroll"}

    def test_propagates_session_not_found(self, monkeypatch, captured):
        def _raise(name):
            raise tmux_lib.SessionNotFoundError(name)

        monkeypatch.setattr(tmux_lib, "resolve_socket", _raise)
        with pytest.raises(tmux_lib.SessionNotFoundError):
            tmux_lib.send_interrupt("ghost")


def test_create_tmux_session_registers_permissions(monkeypatch, tmp_path):
    # Use temp permissions file
    monkeypatch.setenv("TMUX_MCP_PERMISSIONS_FILE", str(tmp_path / "permissions.json"))

    # Avoid calling real tmux
    monkeypatch.setattr(
        tmux_lib.subprocess,
        "run",
        lambda *a, **k: MagicMock(returncode=0, stderr=""),
    )

    called: dict[str, str | None] = {"session": None}

    def _ensure(name: str) -> None:
        called["session"] = name

    monkeypatch.setattr(permissions, "ensure_session_registered", _ensure)

    assert tmux_lib.create_tmux_session("green") is True
    assert called["session"] == "green"


def test_create_tmux_session_sets_minimal_status_right_and_keybinding(monkeypatch):
    """Sessions created via tmux-cli new should get plugin UX without ~/.tmux.conf changes."""

    calls: list[list[str]] = []

    def _run(cmd, capture_output=True, text=True, check=False):
        # cmd is a list like ["tmux", "set-option", ...]
        calls.append(cmd)
        return MagicMock(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(tmux_lib.subprocess, "run", _run)
    monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

    assert tmux_lib.create_tmux_session("green") is True

    # We don't assert exact full command order; just that required config was applied.
    joined = [" ".join(c) for c in calls]

    # Plain session => default socket.
    socket_prefix = "tmux -L tmux-mcp"
    assert any(j.startswith(f"{socket_prefix} set-option -t green @tmux_mcp_managed 1") for j in joined), joined
    assert any(j.startswith(f"{socket_prefix} set-option -t green status on") for j in joined), joined
    assert any(j.startswith(f"{socket_prefix} set-option -t green status-interval 5") for j in joined), joined
    assert any(
        f"{socket_prefix} set-option -t green status-right" in j
        and "-m tmux_mcp.scripts.tmux_mcp_status" in j
        for j in joined
    ), joined

    # Binding is global (no -t <session>), but gated on @tmux_mcp_managed.
    assert any(
        j.startswith(f"{socket_prefix} bind-key -n C-] run-shell")
        and "@tmux_mcp_managed" in j
        and "-m tmux_mcp.scripts.tmux_mcp_toggle" in j
        for j in joined
    ), joined

class TestCreateTmuxSessionSocketChoice:
    """Tests for socket selection inside create_tmux_session."""

    @pytest.fixture
    def stub_subprocess(self, monkeypatch):
        """Capture all tmux calls; list-sessions returns empty by default
        (no cross-socket dup)."""
        calls: list[list[str]] = []

        def _run(cmd, capture_output=True, text=True, check=False):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(tmux_lib.subprocess, "run", _run)
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)
        return calls

    @staticmethod
    def _non_listsessions_sockets(calls):
        return {
            cmd[2] for cmd in calls
            if len(cmd) >= 4
            and cmd[0] == "tmux" and cmd[1] == "-L"
            and cmd[3] != "list-sessions"
        }

    def test_default_session_uses_default_socket(self, monkeypatch, stub_subprocess):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        assert tmux_lib.create_tmux_session("green", scroll_popup=False) is True
        assert self._non_listsessions_sockets(stub_subprocess) == {"tmux-mcp"}

    def test_scroll_popup_session_uses_experimental_socket(
        self, monkeypatch, stub_subprocess
    ):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        assert tmux_lib.create_tmux_session("orange", scroll_popup=True) is True
        assert self._non_listsessions_sockets(stub_subprocess) == {
            "tmux-mcp-experimental-scroll"
        }

    def test_returns_socket_used(self, monkeypatch, stub_subprocess):
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")

        assert tmux_lib.create_tmux_session(
            "orange", scroll_popup=True, return_socket=True
        ) == "tmux-mcp-experimental-scroll"
        assert tmux_lib.create_tmux_session(
            "green", scroll_popup=False, return_socket=True
        ) == "tmux-mcp"

    def test_refuses_when_name_taken_on_other_socket(self, monkeypatch):
        """'green' lives on the default socket; requesting --scroll-popup
        on it must hard-fail."""
        monkeypatch.setenv("TMUX_MCP_SOCKET", "tmux-mcp")
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

        def _run(cmd, capture_output=True, text=True, check=False):
            # Only the dup-check probe against the non-target socket returns
            # a name; everything else is empty.
            if cmd[3:4] == ["list-sessions"] and cmd[2] == "tmux-mcp":
                return MagicMock(returncode=0, stdout="green\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(tmux_lib.subprocess, "run", _run)

        with pytest.raises(tmux_lib.SessionNameConflictError) as exc:
            tmux_lib.create_tmux_session("green", scroll_popup=True)

        assert exc.value.session_name == "green"
        assert exc.value.existing_socket == "tmux-mcp"
        assert exc.value.target_socket == "tmux-mcp-experimental-scroll"


class TestRandomBufferName:
    """Tests for _generate_random_buffer_name function."""

    def test_with_prefix(self):
        """result should contain prefix and random characters"""
        generated_name = tmux_lib._generate_random_buffer_name("something")
        assert generated_name.startswith("something")
        assert len(generated_name) > len("something")

    def test_without_prefix(self):
        """result should contain a non empty string"""
        generated_name = tmux_lib._generate_random_buffer_name()
        assert len(generated_name) > 0

class TestDetectInteractiveMode:
    """Tests for the _detect_interactive_mode function."""

    # --- less detection ---

    def test_less_single_colon_prompt(self):
        """Detect less when last line is exactly a single ':'."""
        output = """Some file content
lines of text
more text
:"""
        assert tmux_lib._detect_interactive_mode(output) == "less"

    def test_less_single_colon_with_whitespace(self):
        """Detect less when last line is ':' with surrounding whitespace."""
        output = """content
  :  """
        assert tmux_lib._detect_interactive_mode(output) == "less"

    def test_less_not_detected_for_filename_ending_with_colon(self):
        """Do NOT detect less when a filename ends with ':'."""
        output = """content
myfile.txt:"""
        assert tmux_lib._detect_interactive_mode(output) is None

    def test_less_not_detected_when_prompt_arrow_present_with_colon(self):
        """Do NOT detect less if PROMPT_ARROW is in the last line."""
        output = """Some content
tmux-mcp __> some_command:
"""
        assert tmux_lib._detect_interactive_mode(output) is None

    def test_less_end_marker(self):
        """Detect less when last line is exactly '(END)'."""
        output = """File content here
More content
(END)"""
        assert tmux_lib._detect_interactive_mode(output) == "less"

    def test_less_end_marker_with_whitespace(self):
        """Detect less when last line is '(END)' with whitespace."""
        output = """content
  (END)"""
        # Note: strip() is called on last_line, but then compared to "(END)"
        # so this might NOT match - let's test actual behavior
        # The code does last_line.strip() == "(END)", so it should match
        assert tmux_lib._detect_interactive_mode(output) == "less"

    def test_less_end_marker_not_detected_with_prompt_arrow(self):
        """Do NOT detect less when (END) line contains PROMPT_ARROW."""
        output = """content
(END) tmux-mcp __>"""
        assert tmux_lib._detect_interactive_mode(output) is None

    # --- vim detection ---

    def test_vim_detected_with_tilde_lines(self):
        """Detect vim when last 5 non-empty lines all start with '~'."""
        output = """some content
~
~
~
~
~"""
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_vim_detected_with_mixed_content_above(self):
        """Detect vim even with content above the tilde lines."""
        output = """This is some file content
line 2
line 3
~
~
~
~
~"""
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_vim_not_detected_with_fewer_than_five_tilde_lines(self):
        """Do NOT detect vim with fewer than 5 tilde lines."""
        output = """content
~
~
~
~"""
        assert tmux_lib._detect_interactive_mode(output) is None

    def test_vim_detected_when_tilde_line_has_other_content(self):
        """Vim IS detected when tilde lines have content after tilde.

        The check is line.startswith("~"), so "~some text" still starts with "~".
        This matches actual vim behavior where tildes prefix the empty lines.
        """
        output = """content
~
~
~
~some text
~"""
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_vim_with_empty_lines_mixed_in(self):
        """Vim detection skips empty lines when checking last 5."""
        output = """content

~
~

~
~"""
        # Empty lines are skipped in the check: `if line.strip()`
        # So this should detect vim (5 non-empty tilde lines in last 5 checked)
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    # --- nano detection ---

    def test_nano_detected_with_caret_last_line(self):
        """Detect nano when last line starts with '^'."""
        output = """GNU nano 7.2               somefile.txt
some content here

^G Get Help  ^O Write Out  ^W Where Is  ^K Cut"""
        assert tmux_lib._detect_interactive_mode(output) == "nano"

    def test_nano_detected_with_gnu_nano_in_output(self):
        """Detect nano when 'GNU nano' appears anywhere in output."""
        output = """GNU nano 7.2
some file content
more content
last line"""
        assert tmux_lib._detect_interactive_mode(output) == "nano"

    def test_nano_detected_with_both_indicators(self):
        """Detect nano with both '^' on last line and 'GNU nano' in output."""
        output = """GNU nano 7.2               file.txt
content

^X Exit      ^O Write Out"""
        assert tmux_lib._detect_interactive_mode(output) == "nano"

    # --- no detection cases ---

    def test_no_detection_for_normal_output(self):
        """No detection for normal terminal output with prompt."""
        output = """some command output
more output
tmux-mcp __>"""
        assert tmux_lib._detect_interactive_mode(output) is None

    def test_empty_output_detects_vim_edge_case(self):
        """Empty output triggers vim detection due to all([]) == True.

        This is an edge case/bug: when lines[-5:] has only empty strings,
        the `if line.strip()` filter leaves an empty list, and all([]) is True.
        """
        output = ""
        # Edge case: empty list passes all() check
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_whitespace_only_detects_vim_edge_case(self):
        """Whitespace-only output triggers vim detection due to all([]) == True.

        Same edge case as empty output: all lines filtered out, all([]) is True.
        """
        output = "   \n   \n   "
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_no_detection_for_running_command(self):
        """No detection for a command that appears to be running."""
        output = """tmux-mcp __> some_long_command
Processing...
Still running..."""
        assert tmux_lib._detect_interactive_mode(output) is None

    # --- edge cases ---

    def test_less_not_detected_for_line_ending_with_colon(self):
        """Do NOT detect less when line ends with ':' but is not just ':'."""
        output = """content
ends with colon:"""
        assert tmux_lib._detect_interactive_mode(output) is None

    def test_priority_when_multiple_indicators(self):
        """Test priority when multiple indicators are present."""
        # vim is checked before nano, so if both match, vim wins
        output = """GNU nano
~
~
~
~
~"""
        assert tmux_lib._detect_interactive_mode(output) == "vim"

    def test_single_line_output(self):
        """Handle single line output correctly."""
        output = "(END)"
        assert tmux_lib._detect_interactive_mode(output) == "less"

    def test_colon_without_ending_with_colon(self):
        """Line with colon but not ending with colon should not detect less."""
        output = """content
: something here"""
        # Line has ":" but doesn't end with ":"
        assert tmux_lib._detect_interactive_mode(output) is None


class TestCreateSessionTargetPaneAndClaude:
    """create_tmux_session saves the shell pane and can split with an agent."""

    @staticmethod
    def _run_factory(calls):
        def _run(cmd, capture_output=True, text=True, check=False):
            calls.append(cmd)
            if "display-message" in cmd:
                return MagicMock(returncode=0, stdout="%5\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")
        return _run

    def test_saves_shell_pane_id(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(tmux_lib.subprocess, "run", self._run_factory(calls))
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

        assert tmux_lib.create_tmux_session("green") is True

        new_session = [c for c in calls if "new-session" in c][0]
        assert new_session[-1] == "zsh"

        joined = [" ".join(c) for c in calls]
        assert any(
            j.startswith("tmux -L tmux-mcp set-option -t green @tmux_mcp_target_pane %5")
            for j in joined
        ), joined

    def test_no_split_without_claude(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(tmux_lib.subprocess, "run", self._run_factory(calls))
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

        tmux_lib.create_tmux_session("green")

        joined = [" ".join(c) for c in calls]
        assert not any("split-window" in j for j in joined), joined

    def test_with_claude_splits_horizontally_and_launches_claude(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(tmux_lib.subprocess, "run", self._run_factory(calls))
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

        assert tmux_lib.create_tmux_session("green", with_agent=True) is True

        split = [c for c in calls if "split-window" in c]
        assert split, calls
        split_cmd = split[0]
        assert "-h" in split_cmd
        assert "%5" in split_cmd
        joined = " ".join(split_cmd)
        assert "claude" in joined
        assert "--append-system-prompt" in joined
        assert "green" in joined

    def test_with_custom_agent(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(tmux_lib.subprocess, "run", self._run_factory(calls))
        monkeypatch.setattr(permissions, "ensure_session_registered", lambda *_: None)

        tmux_lib.create_tmux_session("green", with_agent=True, agent="myagent")

        split = [c for c in calls if "split-window" in c]
        assert split, calls
        joined = " ".join(split[0])
        assert "myagent" in joined
        assert "claude" not in joined


class TestResolveTarget:
    """Tests for resolve_target: MCP must drive the saved shell pane_id."""

    def test_uses_saved_pane_id(self, monkeypatch):
        monkeypatch.setattr(tmux_lib, "resolve_socket", lambda *_: "tmux-mcp")

        def _run(cmd, capture_output=True, text=True, check=False):
            if "show-option" in cmd and "@tmux_mcp_target_pane" in cmd:
                return MagicMock(returncode=0, stdout="%5\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(tmux_lib.subprocess, "run", _run)
        assert tmux_lib.resolve_target("green") == ("tmux-mcp", "%5")

    def test_falls_back_to_session_name_when_unset(self, monkeypatch):
        monkeypatch.setattr(tmux_lib, "resolve_socket", lambda *_: "tmux-mcp")
        monkeypatch.setattr(
            tmux_lib.subprocess,
            "run",
            lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
        )
        assert tmux_lib.resolve_target("green") == ("tmux-mcp", "green")


class TestPaneTargeting:
    """All interaction functions must target the resolved pane, not the session."""

    def test_send_to_terminal_targets_resolved_pane(self, monkeypatch):
        mock_run = MagicMock(
            return_value=MagicMock(returncode=0, stdout="", stderr="")
        )
        monkeypatch.setattr(tmux_lib.subprocess, "run", mock_run)
        monkeypatch.setattr(tmux_lib, "resolve_target", lambda *_: ("tmux-mcp", "%7"))
        monkeypatch.setattr(tmux_lib, "_generate_random_buffer_name", lambda *a, **k: "buf-1")

        assert tmux_lib.send_to_terminal("green", "ls") is True

        paste = [c for c in mock_run.call_args_list if "paste-buffer" in c.args[0]]
        assert paste, mock_run.call_args_list
        assert "%7" in paste[0].args[0]
        assert "green" not in paste[0].args[0]

    def test_send_interrupt_targets_resolved_pane(self, monkeypatch):
        mock_run = MagicMock(
            return_value=MagicMock(returncode=0, stdout="", stderr="")
        )
        monkeypatch.setattr(tmux_lib.subprocess, "run", mock_run)
        monkeypatch.setattr(tmux_lib, "resolve_target", lambda *_: ("tmux-mcp", "%7"))

        tmux_lib.send_interrupt("green")

        sent = mock_run.call_args_list[-1].args[0]
        assert "%7" in sent
        assert "C-c" in sent

    def test_execute_in_terminal_sends_to_resolved_pane(self, monkeypatch):
        mock_run = MagicMock(
            return_value=MagicMock(returncode=0, stdout="", stderr="")
        )
        monkeypatch.setattr(tmux_lib.subprocess, "run", mock_run)
        monkeypatch.setattr(tmux_lib, "resolve_target", lambda *_: ("tmux-mcp", "%7"))
        monkeypatch.setattr(tmux_lib, "wait_for_command_completion", lambda *a, **k: None)

        tmux_lib.execute_in_terminal("green", "ls", sync=False)

        send = [c for c in mock_run.call_args_list if "send-keys" in c.args[0]]
        assert send, mock_run.call_args_list
        assert "%7" in send[0].args[0]


class TestSendToTerminal:
    """Tests for the send_to_terminal function."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.mock_run = MagicMock()
        self.mock_verify = MagicMock(return_value=True)
        self.mock_gen_name = MagicMock(return_value="test-buffer-123")

        monkeypatch.setattr(tmux_lib.subprocess, "run", self.mock_run)
        monkeypatch.setattr(tmux_lib, "_verify_terminal_prompt", self.mock_verify)
        monkeypatch.setattr(tmux_lib, "_generate_random_buffer_name", self.mock_gen_name)
        # send_to_terminal resolves the socket; pin it so the test
        # doesn't depend on real tmux state.
        monkeypatch.setattr(
            tmux_lib, "resolve_socket", lambda name: "tmux-mcp"
        )

    def test_send_to_terminal_calls_tmux(self):
        """Verify that send_to_terminal calls the correct tmux commands in order."""
        session = "test-session"
        cmd = "ls -l"
        buffer_name = "test-buffer-123"  # match the mock return value

        result = tmux_lib.send_to_terminal(session, cmd)

        assert result is True

        sock = "tmux-mcp"
        expected_calls = [
            call(
                ["tmux", "-L", sock, "set-buffer", "-b", buffer_name, cmd],
                capture_output=True,
                text=True,
            ),
            call(
                ["tmux", "-L", sock, "paste-buffer", "-p", "-b", buffer_name, "-t", session],
                capture_output=True,
                text=True,
            ),
            call(
                ["tmux", "-L", sock, "delete-buffer", "-b", buffer_name],
                capture_output=True,
                text=True,
            ),
        ]
        self.mock_run.assert_has_calls(expected_calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

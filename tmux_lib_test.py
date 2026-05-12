#!/usr/bin/env python3
"""Unit tests for _detect_interactive_mode in tmux_lib.py"""

import pytest
import tmux_lib
import permissions
from unittest.mock import MagicMock, call


def test_create_tmux_session_registers_permissions(monkeypatch, tmp_path):
    # Use temp permissions file
    monkeypatch.setenv("TMUX_MCP_PERMISSIONS_FILE", str(tmp_path / "permissions.json"))

    # Avoid calling real tmux
    monkeypatch.setattr(
        tmux_lib.subprocess,
        "run",
        lambda *a, **k: MagicMock(returncode=0, stderr=""),
    )

    called = {"session": None}

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

    assert any(j.startswith("tmux set-option -t green @tmux_mcp_managed 1") for j in joined), joined
    assert any(j.startswith("tmux set-option -t green status on") for j in joined), joined
    assert any(j.startswith("tmux set-option -t green status-interval 5") for j in joined), joined
    assert any(
        "tmux set-option -t green status-right" in j and "tmux_mcp_status.py" in j
        for j in joined
    ), joined

    # Binding is global (no -t <session>), but gated on @tmux_mcp_managed.
    assert any(
        j.startswith("tmux bind-key -n C-] run-shell")
        and "@tmux_mcp_managed" in j
        and "tmux_mcp_toggle.py" in j
        for j in joined
    ), joined

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


class TestGetLastCommand:
    """Tests for the get_last_command function."""

    def test_multiple_commands_filters_empty_output_and_returns_requested_count(self, monkeypatch):
        """Split scrollback into (prompt, command, output) blocks and filter empty outputs."""

        scrollback = "\n".join(
            [
                "some older noise",
                "·tmux-mcp __> ~/proj echo first",
                "first-out",
                "·tmux-mcp __> ~/proj true",
                "·tmux-mcp __> ~/proj echo second",
                "second-out-line-1",
                "second-out-line-2",
                "·tmux-mcp __> ~/proj",  # idle prompt
                "",
            ]
        )

        monkeypatch.setattr(tmux_lib, "_capture_pane", lambda session_name: scrollback)

        # New behavior: count parameter, returns list[CommandOutput]
        results = tmux_lib.get_last_command("blue", count=2)

        # Oldest-first within the returned window: most recent first
        assert [r.command for r in results] == ["echo second", "echo first"]
        assert results[0].output == "second-out-line-1\nsecond-out-line-2"
        assert results[1].output == "first-out"
        assert all(r.status == "free" for r in results)

    def test_idle_terminal_returns_second_to_last_prompt_block(self, monkeypatch):
        """When the last prompt has no command, get_last_command uses the previous prompt."""

        scrollback = "\n".join(
            [
                "some older noise",
                "·tmux-mcp __> ~/proj echo first",
                "first-out",
                "·tmux-mcp __> ~/proj echo second",
                "second-out",
                "·tmux-mcp __> ~/proj",  # idle prompt (no command)
                "",
            ]
        )

        monkeypatch.setattr(tmux_lib, "_capture_pane", lambda session_name: scrollback)

        result = tmux_lib.get_last_command("blue")

        assert result is not None
        assert result.status == "free"
        assert result.command == "echo second"
        # Current implementation includes the prompt line in output and captures to end
        assert result.output == "\n".join(
            [
                "·tmux-mcp __> ~/proj echo second",
                "second-out",
                "·tmux-mcp __> ~/proj",
            ]
        )


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

    def test_send_to_terminal_calls_tmux(self):
        """Verify that send_to_terminal calls the correct tmux commands in order."""
        session = "test-session"
        cmd = "ls -l"
        buffer_name = "test-buffer-123"  # match the mock return value

        result = tmux_lib.send_to_terminal(session, cmd)

        assert result is True

        expected_calls = [
            call(
                ["tmux", "set-buffer", "-b", buffer_name, cmd],
                capture_output=True,
                text=True,
            ),
            call(
                ["tmux", "paste-buffer", "-p", "-b", buffer_name, "-t", session],
                capture_output=True,
                text=True,
            ),
            call(
                ["tmux", "delete-buffer", "-b", buffer_name],
                capture_output=True,
                text=True,
            ),
        ]
        self.mock_run.assert_has_calls(expected_calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

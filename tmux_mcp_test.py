"""Regression tests exercising the registered MCP tools, not just helpers."""

import asyncio
from threading import Event, get_ident
from unittest.mock import MagicMock

import pytest

from tmux_mcp import permissions, tmux_lib, tmux_mcp


# /tmp/test.txt from the reported timeout: embedded so tests are self-contained.
RECORDED_TERMINAL = (
    "·(default) ansible __> .venv/bin/python -m pip install -r requirements.txt "
    "> /tmp/katavti-ansible-pip.log 2>&1; printf 'pip exit: %s\n"
    "' 0; tail -n 20 /t\n"
    "mp/katavti-ansible-pip.log\n"
)


@pytest.fixture
def allowed(monkeypatch):
    check = MagicMock()
    monkeypatch.setattr(permissions, "assert_allowed", check)
    return check


@pytest.mark.parametrize("tool_name", ["execute_command", "wait_for_completion"])
def test_get_last_lines_responds_while_command_waits(monkeypatch, allowed, tool_name):
    started, release, finished = Event(), Event(), Event()

    def blocking_wait(*args, **kwargs):
        started.set()
        # Safety bound: the old synchronous implementation blocks the event loop,
        # so the coroutine below cannot release us. Never hang the test runner.
        release.wait(timeout=1.0)
        finished.set()
        return tmux_lib.CommandOutput("", "", "", "timeout")

    monkeypatch.setattr(tmux_lib, "execute_in_terminal", blocking_wait)
    monkeypatch.setattr(tmux_lib, "wait_for_command_completion", blocking_wait)
    monkeypatch.setattr(tmux_lib, "resolve_target", lambda _: ("test", "%0"))
    monkeypatch.setattr(tmux_lib, "_capture_pane", lambda *_: RECORDED_TERMINAL)

    async def scenario():
        arguments = {"session_name": "green", "timeout": 240.0}
        if tool_name == "execute_command":
            arguments.update(command="long command", prompt_verify_string="ansible __>")
        waiter = asyncio.create_task(tmux_mcp.mcp.call_tool(tool_name, arguments))
        try:
            assert await asyncio.to_thread(started.wait, 2.0), "waiter never started"
            result = await asyncio.wait_for(
                tmux_mcp.mcp.call_tool(
                    "get_last_lines", {"session_name": "green", "lines": 20}
                ),
                timeout=0.5,
            )
            assert result[1] == {"result": RECORDED_TERMINAL.rstrip("\n")}
            assert not finished.is_set(), (
                "get_last_lines was starved until the blocking command waiter finished"
            )
            # A client timeout cancels its request, not the running shell command.
            # Subsequent reads must still work while the worker finishes waiting.
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            result = await asyncio.wait_for(
                tmux_mcp.mcp.call_tool(
                    "get_last_lines", {"session_name": "green", "lines": 20}
                ),
                timeout=0.5,
            )
            assert result[1] == {"result": RECORDED_TERMINAL.rstrip("\n")}
            assert not finished.is_set(), "cancelled waiter still starved reads"
        finally:
            release.set()
            await asyncio.gather(waiter, return_exceptions=True)

    asyncio.run(scenario())
    allowed.assert_any_call("green", "get_last_lines")


@pytest.mark.parametrize(
    "tool_name, helper, arguments, helper_result",
    [
        ("get_last_lines", "get_n_last_lines", {}, "output"),
        ("get_last_command_output", "get_last_command", {}, None),
        ("send_command", "send_to_terminal", {"command": "ls"}, True),
        ("send_interrupt", "send_interrupt", {}, None),
        ("execute_command", "execute_in_terminal", {"command": "ls"}, ""),
        ("wait_for_completion", "wait_for_command_completion", {}, None),
    ],
)
def test_registered_tools_run_blocking_helpers_off_event_loop(
    monkeypatch, allowed, tool_name, helper, arguments, helper_result
):
    helper_threads = []

    def record_thread(*args, **kwargs):
        helper_threads.append(get_ident())
        return helper_result

    monkeypatch.setattr(tmux_lib, helper, record_thread)

    async def scenario():
        event_loop_thread = get_ident()
        await tmux_mcp.mcp.call_tool(tool_name, {"session_name": "green", **arguments})
        assert len(helper_threads) == 1
        assert helper_threads[0] != event_loop_thread, (
            f"{tool_name} ran blocking tmux code on the MCP event-loop thread"
        )

    asyncio.run(scenario())
    allowed.assert_called_once_with("green", tool_name)


@pytest.mark.parametrize(
    "tool_name, helper, arguments",
    [
        ("get_last_lines", "get_n_last_lines", {}),
        ("get_last_command_output", "get_last_command", {}),
        ("send_command", "send_to_terminal", {"command": "ls"}),
        ("send_interrupt", "send_interrupt", {}),
        ("execute_command", "execute_in_terminal", {"command": "ls"}),
        ("wait_for_completion", "wait_for_command_completion", {}),
    ],
)
def test_registered_tools_still_check_permissions(
    monkeypatch, tmp_path, tool_name, helper, arguments
):
    permissions_path = tmp_path / "permissions.json"
    permissions_path.write_text(
        '{"version": 1, "defaultMode": "deny", "sessions": {}}'
    )
    monkeypatch.setenv("TMUX_MCP_PERMISSIONS_FILE", str(permissions_path))
    helper_mock = MagicMock(side_effect=AssertionError("denied tool reached tmux"))
    monkeypatch.setattr(tmux_lib, helper, helper_mock)

    async def scenario():
        # FastMCP wraps PermissionError as ToolError for protocol clients.
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError, match="permission denied"):
            await tmux_mcp.mcp.call_tool(tool_name, {"session_name": "green", **arguments})

    asyncio.run(scenario())
    helper_mock.assert_not_called()

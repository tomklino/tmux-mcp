import unittest
from unittest import mock
import sys
import os
import datetime
import subprocess
from io import StringIO

# Add the parent directory to the sys.path to allow importing tmux_cli
# Compatibility: keep legacy top-level module names for tests/mocks.
import tmux_mcp.tmux_cli as tmux_cli
import tmux_mcp.tmux_lib as tmux_lib

# Also alias to old module names so existing mock.patch('tmux_cli...') keeps working.
sys.modules.setdefault('tmux_cli', tmux_cli)
sys.modules.setdefault('tmux_lib', tmux_lib)

class TestTmuxCli(unittest.TestCase):

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_no_record(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = 'tmux-mcp'

        args = mock.Mock()
        args.session_name = 'test_session'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'test_session', color=None, scroll_popup=False,
            with_agent=False, agent='claude', return_socket=True,
        )
        mock_subprocess_run.assert_called_once_with(
            ['tmux', '-L', 'tmux-mcp', 'attach-session', '-t', 'test_session'],
            check=False,
        )
        mock_print.assert_called_with('Tmux session ready: test_session')

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_experimental_scroll_popup_uses_experimental_socket(
        self, mock_print, mock_subprocess_run, mock_create_tmux_session
    ):
        mock_create_tmux_session.return_value = 'tmux-mcp-experimental-scroll'

        args = mock.Mock()
        args.session_name = 'exp_session'
        args.record = False
        args.experimental_scroll_popup = True
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'exp_session', color=None, scroll_popup=True,
            with_agent=False, agent='claude', return_socket=True,
        )
        mock_subprocess_run.assert_called_once_with(
            ['tmux', '-L', 'tmux-mcp-experimental-scroll', 'attach-session', '-t', 'exp_session'],
            check=False,
        )

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.sys.exit')
    @mock.patch('sys.stderr', new_callable=StringIO)
    def test_cmd_new_hard_fails_on_session_name_conflict(
        self, mock_stderr, mock_sys_exit, mock_create_tmux_session
    ):
        mock_create_tmux_session.side_effect = tmux_lib.SessionNameConflictError(
            'green', 'tmux-mcp', 'tmux-mcp-experimental-scroll'
        )
        mock_sys_exit.side_effect = SystemExit

        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = True
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with self.assertRaises(SystemExit):
                tmux_cli.cmd_new(args)

        mock_sys_exit.assert_called_with(1)
        # The error message should name the conflicting session and socket.
        err = mock_stderr.getvalue()
        self.assertIn('green', err)
        self.assertIn('tmux-mcp', err)

    @mock.patch('tmux_cli.config.default_socket', return_value='tmux-mcp')
    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.shutil.which')
    @mock.patch('tmux_cli.os.makedirs')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.datetime')
    @mock.patch('tmux_cli.print')
    @mock.patch('tmux_cli.os.path.expanduser', return_value='/home/user/.tmux-session-recordings')
    def test_cmd_new_with_record_asciinema_installed(
        self,
        mock_expanduser,
        mock_print,
        mock_datetime,
        mock_subprocess_run,
        mock_os_makedirs,
        mock_shutil_which,
        mock_create_tmux_session,
        mock_default_socket
    ):
        mock_create_tmux_session.return_value = 'tmux-mcp'
        mock_shutil_which.return_value = '/usr/bin/asciinema' # asciinema is installed

        # Mock datetime to control the timestamp in the filename
        mock_now = mock.Mock()
        mock_now.strftime.return_value = '2026-05-03_10-30-00'
        mock_datetime.datetime.now.return_value = mock_now

        args = mock.Mock()
        args.session_name = 'test_recorded_session'
        args.record = True
        args.experimental_scroll_popup = False
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_shutil_which.assert_called_once_with('asciinema')
        mock_os_makedirs.assert_called_once_with('/home/user/.tmux-session-recordings', exist_ok=True)
        mock_create_tmux_session.assert_called_once_with(
            'test_recorded_session', color=None, scroll_popup=False,
            with_agent=False, agent='claude', return_socket=True,
        )

        expected_filename = '/home/user/.tmux-session-recordings/test_recorded_session_2026-05-03_10-30-00.cast'
        mock_subprocess_run.assert_called_once_with([
            'asciinema',
            'rec',
            '--command',
            'tmux -L tmux-mcp '
            'attach-session -t test_recorded_session',
            expected_filename,
        ])
        mock_print.assert_called_with('Tmux session ready: test_recorded_session')

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.shutil.which')
    @mock.patch('tmux_cli.sys.exit')
    @mock.patch('sys.stderr', new_callable=StringIO)
    def test_cmd_new_with_record_asciinema_not_installed(
        self,
        mock_stderr,
        mock_sys_exit,
        mock_shutil_which,
        mock_create_tmux_session
    ):
        mock_create_tmux_session.return_value = False # Should not be called
        mock_shutil_which.return_value = None # asciinema is not installed
        mock_sys_exit.side_effect = SystemExit # Ensure sys.exit raises an exception

        args = mock.Mock()
        args.session_name = 'test_session_no_asciinema'
        args.record = True
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with self.assertRaises(SystemExit):
                tmux_cli.cmd_new(args)

        mock_shutil_which.assert_called_once_with('asciinema')
        mock_create_tmux_session.assert_not_called()
        mock_sys_exit.assert_called_once_with(1)
        self.assertIn(
            "Error: asciinema is not installed",
            mock_stderr.getvalue()
        )

    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_bare_flag_uses_claude(self, mock_print):
        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = tmux_cli.WITH_AGENT_DEFAULT

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with mock.patch('tmux_cli._launch_sandbox', return_value='sandbox-container') as mock_launch_sandbox:
                tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_called_once_with(
            session_name='green',
            agent='claude',
            with_agent=True,
        )
        mock_print.assert_called_with('Sandbox ready: sandbox-container')

    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_custom_value(self, mock_print):
        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = 'pi'

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with mock.patch('tmux_cli._launch_sandbox', return_value='sandbox-container') as mock_launch_sandbox:
                with mock.patch('tmux_cli.config.should_prompt_setup_pi_mcp', return_value=False):
                    tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_called_once_with(
            session_name='green',
            agent='pi',
            with_agent=True,
        )
        mock_print.assert_called_with('Sandbox ready: sandbox-container')

    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_defaults_from_config(self, mock_print):
        args = mock.Mock()
        args.session_name = 'green'
        args.record = None
        args.experimental_scroll_popup = None
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={'with_agent': 'pi'}):
            with mock.patch('tmux_cli._launch_sandbox', return_value='sandbox-container') as mock_launch_sandbox:
                with mock.patch('tmux_cli.config.should_prompt_setup_pi_mcp', return_value=False):
                    tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_called_once_with(
            session_name='green',
            agent='pi',
            with_agent=True,
        )
        mock_print.assert_called_with('Sandbox ready: sandbox-container')

    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_config_true_uses_claude(self, mock_print):
        args = mock.Mock()
        args.session_name = 'green'
        args.record = None
        args.experimental_scroll_popup = None
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={'with_agent': True}):
            with mock.patch('tmux_cli._launch_sandbox', return_value='sandbox-container') as mock_launch_sandbox:
                tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_called_once_with(
            session_name='green',
            agent='claude',
            with_agent=True,
        )
        mock_print.assert_called_with('Sandbox ready: sandbox-container')

    def test_resolve_sandbox_defaults_true_when_cli_and_config_absent(self):
        self.assertTrue(tmux_cli._resolve_sandbox(None, None))

    def test_resolve_sandbox_uses_config_when_cli_absent(self):
        self.assertFalse(tmux_cli._resolve_sandbox(None, False))
        self.assertTrue(tmux_cli._resolve_sandbox(None, True))

    def test_resolve_sandbox_cli_takes_precedence_over_config(self):
        self.assertFalse(tmux_cli._resolve_sandbox(False, True))
        self.assertTrue(tmux_cli._resolve_sandbox(True, False))

    def test_main_parses_sandbox_false(self):
        with mock.patch.object(sys, 'argv', ['tmux-cli', 'new', 'green', '--sandbox=false']):
            with mock.patch('tmux_cli.cmd_new') as mock_cmd_new:
                tmux_cli.main()

        args = mock_cmd_new.call_args.args[0]
        self.assertEqual(args.session_name, 'green')
        self.assertFalse(args.sandbox)

    def test_main_parses_sandbox_true(self):
        with mock.patch.object(sys, 'argv', ['tmux-cli', 'new', 'green', '--sandbox=true']):
            with mock.patch('tmux_cli.cmd_new') as mock_cmd_new:
                tmux_cli.main()

        args = mock_cmd_new.call_args.args[0]
        self.assertEqual(args.session_name, 'green')
        self.assertTrue(args.sandbox)

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_sandbox_false_preserves_current_flow(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = 'tmux-mcp'

        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = None
        args.sandbox = False

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with mock.patch('tmux_cli._launch_sandbox') as mock_launch_sandbox:
                tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_not_called()
        mock_create_tmux_session.assert_called_once()
        mock_subprocess_run.assert_called_once()

    @mock.patch('tmux_cli.print')
    def test_cmd_new_sandbox_true_uses_sandbox_launcher(self, mock_print):
        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = 'claude'
        args.sandbox = True

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with mock.patch('tmux_cli._launch_sandbox', return_value='sandbox-container') as mock_launch_sandbox:
                tmux_cli.cmd_new(args)

        mock_launch_sandbox.assert_called_once_with(
            session_name='green',
            agent='claude',
            with_agent=True,
        )
        mock_print.assert_called_with('Sandbox ready: sandbox-container')

    @mock.patch('tmux_cli.subprocess.run')
    def test_launch_sandbox_uses_runtime_commands(self, mock_run):
        runtime = mock.Mock()
        runtime.run_container_command.return_value = ['runtime', 'run']
        runtime.container_name.return_value = 'tmux-mcp-sandbox-green-abc'

        with mock.patch('tmux_cli.default_container_runtime', return_value=runtime):
            name = tmux_cli._launch_sandbox(
                session_name='green',
                agent='pi',
                with_agent=True,
            )

        self.assertEqual(name, 'tmux-mcp-sandbox-green-abc')
        runtime.run_container_command.assert_called_once_with(
            container_name='tmux-mcp-sandbox-green-abc',
            session_name='green',
            agent='pi',
            prompt_extension=mock.ANY,
        )
        mock_run.assert_called_once_with(['runtime', 'run'], check=True)


if __name__ == '__main__':
    unittest.main()


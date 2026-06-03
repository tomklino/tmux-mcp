import unittest
from unittest import mock
import sys
import os
import datetime
import subprocess
from io import StringIO

# Add the parent directory to the sys.path to allow importing tmux_cli
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import tmux_cli
import tmux_lib

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

        tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'test_session', color=None, scroll_popup=False, return_socket=True,
        )
        mock_subprocess_run.assert_called_once_with(
            ['tmux', '-L', 'tmux-mcp', 'attach-session', '-t', 'test_session']
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

        tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'exp_session', color=None, scroll_popup=True, return_socket=True,
        )
        mock_subprocess_run.assert_called_once_with(
            ['tmux', '-L', 'tmux-mcp-experimental-scroll', 'attach-session', '-t', 'exp_session']
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

        with self.assertRaises(SystemExit):
            tmux_cli.cmd_new(args)

        mock_sys_exit.assert_called_with(1)
        # The error message should name the conflicting session and socket.
        err = mock_stderr.getvalue()
        self.assertIn('green', err)
        self.assertIn('tmux-mcp', err)

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
        mock_create_tmux_session
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

        tmux_cli.cmd_new(args)

        mock_shutil_which.assert_called_once_with('asciinema')
        mock_os_makedirs.assert_called_once_with('/home/user/.tmux-session-recordings', exist_ok=True)
        mock_create_tmux_session.assert_called_once_with(
            'test_recorded_session', color=None, scroll_popup=False, return_socket=True,
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

        with self.assertRaises(SystemExit):
            tmux_cli.cmd_new(args)

        mock_shutil_which.assert_called_once_with('asciinema')
        mock_create_tmux_session.assert_not_called()
        mock_sys_exit.assert_called_once_with(1)
        self.assertIn(
            "Error: asciinema is not installed",
            mock_stderr.getvalue()
        )

if __name__ == '__main__':
    unittest.main()


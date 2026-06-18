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

class TestTmuxCli(unittest.TestCase):

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_no_record(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = True

        args = mock.Mock()
        args.session_name = 'test_session'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'test_session',
            color=None,
            scroll_popup=False,
            with_claude=False,
            agent='claude',
            return_socket=True,
        )
        mock_subprocess_run.assert_called_once_with([
            'tmux', '-L', True, 'attach-session', '-t', 'test_session'
        ])
        mock_print.assert_called_with('Tmux session ready: test_session')

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
        mock_create_tmux_session.return_value = True
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
            'test_recorded_session',
            color=None,
            scroll_popup=False,
            with_claude=False,
            agent='claude',
            return_socket=True,
        )
        
        expected_filename = '/home/user/.tmux-session-recordings/test_recorded_session_2026-05-03_10-30-00.cast'
        mock_subprocess_run.assert_called_once_with([
            'asciinema',
            'rec',
            '--command',
            'tmux -L True attach-session -t test_recorded_session',
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
        args.experimental_scroll_popup = False
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

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.sys.exit')
    @mock.patch('sys.stderr', new_callable=StringIO)
    def test_cmd_new_with_unsupported_tmux_scroll_popup(
        self,
        mock_stderr,
        mock_sys_exit,
        mock_create_tmux_session,
    ):
        mock_create_tmux_session.side_effect = tmux_cli.tmux_lib.UnsupportedTmuxVersionError(
            '--experimental-scroll-popup requires tmux 3.6a+; found tmux 3.6'
        )
        mock_sys_exit.side_effect = SystemExit

        args = mock.Mock()
        args.session_name = 'test_session'
        args.record = False
        args.experimental_scroll_popup = True
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            with self.assertRaises(SystemExit):
                tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'test_session',
            color=None,
            scroll_popup=True,
            with_claude=False,
            agent='claude',
            return_socket=True,
        )
        mock_sys_exit.assert_called_once_with(1)
        self.assertIn(
            '--experimental-scroll-popup requires tmux 3.6a+',
            mock_stderr.getvalue()
        )

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_bare_flag_uses_claude(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = True

        # Bare --with-agent stores the sentinel default value.
        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = tmux_cli.WITH_AGENT_DEFAULT

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'green',
            color='green',
            scroll_popup=False,
            with_claude=True,
            agent='claude',
            return_socket=True,
        )

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_custom_value(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = True

        # --with-agent=pi launches a custom agent.
        args = mock.Mock()
        args.session_name = 'green'
        args.record = False
        args.experimental_scroll_popup = False
        args.with_agent = 'pi'

        with mock.patch('tmux_cli.config.session_defaults', return_value={}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'green',
            color='green',
            scroll_popup=False,
            with_claude=True,
            agent='pi',
            return_socket=True,
        )

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_defaults_from_config(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = True

        # CLI flag unset (None) -> config withAgent string should be used.
        args = mock.Mock()
        args.session_name = 'green'
        args.record = None
        args.experimental_scroll_popup = None
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={'with_agent': 'pi'}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'green',
            color='green',
            scroll_popup=False,
            with_claude=True,
            agent='pi',
            return_socket=True,
        )

    @mock.patch('tmux_cli.tmux_lib.create_tmux_session')
    @mock.patch('tmux_cli.subprocess.run')
    @mock.patch('tmux_cli.print')
    def test_cmd_new_with_agent_config_true_uses_claude(self, mock_print, mock_subprocess_run, mock_create_tmux_session):
        mock_create_tmux_session.return_value = True

        # config withAgent: true -> default agent (claude).
        args = mock.Mock()
        args.session_name = 'green'
        args.record = None
        args.experimental_scroll_popup = None
        args.with_agent = None

        with mock.patch('tmux_cli.config.session_defaults', return_value={'with_agent': True}):
            tmux_cli.cmd_new(args)

        mock_create_tmux_session.assert_called_once_with(
            'green',
            color='green',
            scroll_popup=False,
            with_claude=True,
            agent='claude',
            return_socket=True,
        )


if __name__ == '__main__':
    unittest.main()


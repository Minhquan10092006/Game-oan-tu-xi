from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .management.commands.classroom import check_sandbox


class ClassroomCommandTests(SimpleTestCase):
    @patch('web.management.commands.classroom.shutil.which', return_value=None)
    @patch('matches.bot_runner.find_isolate_cmd', return_value=None)
    def test_missing_sandbox_stops_before_serving(self, isolate, docker):
        with self.assertRaises(CommandError):
            check_sandbox()

    @override_settings(SETTINGS_MODULE='config.classroom_settings')
    @patch('web.management.commands.classroom.check_sandbox', return_value='Docker')
    @patch('web.management.commands.classroom.threading.Thread')
    @patch('web.management.commands.classroom.call_command')
    def test_classroom_runs_persistent_consumer_and_no_reloader(self, command, thread, sandbox):
        call_command('classroom', address='192.168.1.10', port=8001, stdout=StringIO())
        command.assert_any_call('migrate', interactive=False, verbosity=0)
        command.assert_any_call('collectstatic', interactive=False, verbosity=0)
        command.assert_any_call('runserver', '0.0.0.0:8001', use_reloader=False)
        thread.return_value.start.assert_called_once()
        thread.return_value.join.assert_called_once()

    @override_settings(SETTINGS_MODULE='config.classroom_settings')
    @patch('web.management.commands.classroom.check_sandbox', return_value='Isolate')
    @patch('web.management.commands.classroom.call_command')
    def test_preflight_does_not_migrate_or_start_web(self, command, sandbox):
        call_command('classroom', address='192.168.1.10', check_only=True, stdout=StringIO())
        command.assert_not_called()

    @override_settings(SETTINGS_MODULE='config.classroom_settings')
    def test_rejects_wildcard_address(self):
        with self.assertRaises(CommandError):
            call_command('classroom', address='0.0.0.0', stdout=StringIO())

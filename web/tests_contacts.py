"""Retired contact features and role-specific guidance."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
import io


class RetiredFeatureTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('representative')
        self.client.force_login(self.user)

    def test_old_contact_team_and_appeal_routes_are_inactive(self):
        for path in ('email/','email/check/','verify-email/','teams/join/','teams/1/email/',
                     'seasons/1/teams/','seasons/1/individual/','teams/1/rotate-code/',
                     'seasons/1/appeals/','appeals/1/resolve/'):
            with self.subTest(path=path):
                response=self.client.post('/api/competition/'+path,{},content_type='application/json')
                self.assertEqual(response.status_code,410)

    def test_legacy_email_command_cannot_send_queued_mail(self):
        with self.assertRaises(CommandError):
            call_command('send_tournament_emails',stdout=io.StringIO())

    def test_user_guide_cannot_switch_roles(self):
        page=self.client.get('/guide/?role=admin')
        self.assertContains(page,'Tham gia bằng một tài khoản đại diện')
        self.assertNotContains(page,'Vận hành mùa giải trong 5 bước')
        self.assertNotContains(page,'?role=admin')

    def test_admin_guide_only_covers_management(self):
        admin=get_user_model().objects.create_superuser('admin','admin@example.com','testing')
        self.client.force_login(admin)
        page=self.client.get('/guide/?role=user')
        self.assertContains(page,'Vận hành mùa giải trong 5 bước')
        self.assertNotContains(page,'Tham gia bằng một tài khoản đại diện')
        self.assertNotContains(page,'Gửi khiếu nại')

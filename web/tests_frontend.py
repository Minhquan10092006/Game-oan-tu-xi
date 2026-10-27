"""Public landing and dedicated account-flow regression checks."""
from django.contrib.auth.models import User
from django.test import Client, TestCase


class PublicFrontendTests(TestCase):
    def test_student_sees_real_draw_and_separate_48_team_preview(self):
        user=User.objects.create_user(username='draw-viewer')
        self.client.force_login(user)
        response=self.client.get('/tournament/')
        self.assertContains(response,'id="user-draw"')
        self.assertContains(response,'preview-world-cup-toggle')
        self.assertContains(response,'Minh họa, không phải kết quả mùa giải.')
        user.is_staff=True;user.save()
        self.assertContains(self.client.get('/tournament/'),'id="user-draw"')

    def test_guest_arena_explains_practice_requires_account(self):
        user=User.objects.create_user(username='guest-arena-viewer')
        self.client.force_login(user)
        session=self.client.session;session['is_guest']=True;session.save()
        response=self.client.get('/play/')
        self.assertContains(response,'Đăng ký để luyện tập')
        self.assertNotContains(response,'id="practice-form"')

    def test_home_logout_button_ends_session_and_preserves_account(self):
        user = User.objects.create_user(username='logout_player', password='testing')
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        page = client.get('/')
        self.assertContains(page, 'class="header-logout"')
        response = client.post('/logout/', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertRedirects(response, '/')
        self.assertNotIn('_auth_user_id', client.session)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertNotContains(client.get('/'), 'class="header-logout"')

    def test_home_is_public_and_has_real_navigation(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for text in (
            'Nước đi nhỏ.', 'Ý tưởng lớn.', 'id="luat-choi"', 'id="tham-gia"',
            'href="/register/"', 'data-motion-toggle', 'tối đa 4 mục/bảng',
            'href="/rules/download/"', 'href="/competition/"',
        ):
            self.assertContains(response, text)
        self.assertNotContains(response, 'auth-overlay')
        self.assertNotContains(response, 'name="password"')
        self.assertEqual(len(response.context['hero_cells']), 81)
        self.assertEqual(sum(bool(cell['symbol']) for cell in response.context['hero_cells']), 18)

    def test_rules_markdown_download_contains_tournament_format(self):
        response = self.client.get('/rules/download/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        content = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('Minh họa quy mô World Cup 48 đội', content)
        self.assertIn('8 đội hạng ba tốt nhất', content)

    def test_register_and_login_are_separate_pages(self):
        self.assertContains(self.client.get('/register/'), 'name="reg_username"')
        self.assertNotContains(self.client.get('/login/'), 'name="reg_username"')
        self.assertContains(self.client.get('/login/'), 'autocomplete="current-password"')

    def test_arena_requests_login_and_preserves_destination(self):
        response = self.client.get('/play/')
        self.assertRedirects(response, '/login/?next=/play/')
        response = self.client.get('/battlecode/')
        self.assertRedirects(response, '/login/?next=/battlecode/')

    def test_guest_reaches_requested_demo(self):
        response = self.client.post('/login/', {'action':'guest', 'next':'/battlecode/'})
        self.assertRedirects(response, '/battlecode/')
        self.assertTrue(self.client.session['is_guest'])

    def test_registration_clears_guest_status_and_reaches_submission(self):
        self.client.post('/login/', {'action':'guest'})
        response = self.client.post('/register/', {
            'action':'register', 'reg_username':'new_player',
            'reg_password1':'test-password-71', 'reg_password2':'test-password-71', 'next':'/ai/',
        })
        self.assertRedirects(response, '/ai/')
        self.assertFalse(self.client.session.get('is_guest', False))
        self.assertTrue(User.objects.filter(username='new_player').exists())

    def test_errors_keep_registration_page_and_entered_username(self):
        response = self.client.post('/register/', {'action':'register', 'reg_username':'player',
            'reg_password1':'abc', 'reg_password2':'different'})
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="player"')
        self.assertFalse(User.objects.filter(username='player').exists())

    def test_external_next_url_is_rejected(self):
        response = self.client.post('/login/', {'action':'guest', 'next':'https://example.com/steal'})
        self.assertRedirects(response, '/play/')

    def test_account_forms_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/register/', {'action':'register'}).status_code, 403)
        page = client.get('/login/?next=/battlecode/')
        self.assertContains(page, 'csrfmiddlewaretoken')
        response = client.post('/login/', {'action':'guest', 'next':'/battlecode/'},
                               HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertRedirects(response, '/battlecode/')

    def test_play_keeps_existing_game_dom_and_scripts(self):
        user = User.objects.create_user(username='player', password='testing')
        self.client.force_login(user)
        response = self.client.get('/play/')
        for content in ('id="screen-solo"', 'id="screen-multi"', 'id="screen-menu"', 'web/js/screen-manager.js', 'CHỌN NƯỚC ĐI TIẾP THEO.'):
            self.assertContains(response, content)
        self.assertNotContains(response, 'auth-overlay')

    def test_arena_destinations_use_shared_retro_shell(self):
        user = User.objects.create_user(username='archive_player', password='testing')
        self.client.force_login(user)
        from django.utils import timezone
        from .models import Season, CompetitionEntry
        season = Season.objects.create(name='Open submissions',start_date=timezone.localdate(),phase='submission')
        CompetitionEntry.objects.create(user=user,season=season,display_name='Archive player')
        for path, asset, marker in (
            ('/ai/', 'retro-submit.css', 'submission_console.exe'),
            ('/history/', 'retro-history.css', 'match_history.log'),
            ('/battlecode/', 'retro-arena.css', 'replay_viewer.exe'),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, asset)
            self.assertContains(response, marker)
            self.assertContains(response, 'site-header')

    def test_submission_page_remains_closed_without_an_open_entry(self):
        user = User.objects.create_user(username='closed-submission-player')
        self.client.force_login(user)
        response = self.client.get('/ai/')
        self.assertContains(response, 'Hiện không nhận bài nộp')
        self.assertNotContains(response, 'id="submit-btn"')

    def test_existing_home_post_remains_supported(self):
        response = self.client.post('/', {'action':'guest'})
        self.assertRedirects(response, '/play/')

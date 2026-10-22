"""Public landing and dedicated account-flow regression checks."""
from django.contrib.auth.models import User
from django.test import Client, TestCase


class PublicFrontendTests(TestCase):
    def test_home_is_public_and_has_real_navigation(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for text in ('NƯỚC ĐI NHỎ.', 'Ý TƯỞNG', 'id="luat-choi"', 'id="tham-gia"', 'href="/register/"', 'data-motion-toggle'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'auth-overlay')
        self.assertNotContains(response, 'name="password"')
        self.assertEqual(len(response.context['hero_cells']), 81)
        self.assertEqual(sum(bool(cell['symbol']) for cell in response.context['hero_cells']), 18)

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

    def test_existing_home_post_remains_supported(self):
        response = self.client.post('/', {'action':'guest'})
        self.assertRedirects(response, '/play/')

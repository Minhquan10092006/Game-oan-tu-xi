"""Single-computer classroom profile; no external database/cache/email services."""
from .settings import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                         'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 30}}}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# One continuous local consumer resumes persisted jobs after a restart.
LOCAL_JUDGE_AUTOSTART = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

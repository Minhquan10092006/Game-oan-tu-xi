"""Tests always use an isolated in-memory database, never the developer database."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

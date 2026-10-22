"""
Django settings for config project.
Đọc cấu hình từ .env (nếu có) qua python-dotenv.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file nếu tồn tại (development)
load_dotenv(BASE_DIR / '.env')

# ===========================================================
# SECURITY
# ===========================================================

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-tsjc3n$%t7tnmtb&i$enb-&d592zdbdtn%5zyoj!w$o)05vm*s',
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('1', 'true', 'yes')

if not DEBUG and not os.environ.get('DJANGO_SECRET_KEY'):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Production yêu cầu DJANGO_SECRET_KEY riêng.')

ALLOWED_HOSTS_ENV = os.environ.get('DJANGO_ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = ['*'] if DEBUG else [h.strip() for h in ALLOWED_HOSTS_ENV.split(',') if h.strip()]

# ===========================================================
# APPLICATION DEFINITION
# ===========================================================

INSTALLED_APPS = [
    'daphne',                         # phải đứng đầu để override runserver
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'channels',
    'rest_framework',
    'corsheaders',
    # Local apps
    'web',
    'submissions',
    'judge',
    'matches',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # serve static files trên production
    'corsheaders.middleware.CorsMiddleware',  # phải trước CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# ===========================================================
# DATABASE
# ===========================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    import dj_database_url
    DATABASES['default'] = dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )

# ===========================================================
# AUTHENTICATION
# ===========================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ===========================================================
# INTERNATIONALIZATION
# ===========================================================

LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# ===========================================================
# STATIC FILES
# ===========================================================

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # thư mục collectstatic output

# Whitenoise: nén và cache static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ===========================================================
# DJANGO REST FRAMEWORK
# ===========================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    # Không trả về stack trace ra client khi DEBUG=False
    'EXCEPTION_HANDLER': 'config.exception_handler.custom_exception_handler',
}

# ===========================================================
# CORS
# ===========================================================

# Cho phép frontend Django template và Node.js server gọi API
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',   # Node.js game server
    'http://127.0.0.1:3000',
    'http://localhost:8000',   # Django dev server
    'http://127.0.0.1:8000',
    'https://game-oan-tu-xi.onrender.com',  # Render production
]

# Render URL từ env (linh hoạt khi đổi service name)
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS = [RENDER_EXTERNAL_HOSTNAME] + ALLOWED_HOSTS
    CORS_ALLOWED_ORIGINS += [f'https://{RENDER_EXTERNAL_HOSTNAME}']
    CSRF_TRUSTED_ORIGINS = [f'https://{RENDER_EXTERNAL_HOSTNAME}']

CORS_ALLOW_CREDENTIALS = True

# ===========================================================
# JUDGE0 CONFIG (đọc từ env)
# ===========================================================

JUDGE0_BASE_URL = os.environ.get('JUDGE0_BASE_URL', 'https://ce.judge0.com').rstrip('/')
JUDGE0_API_KEY = os.environ.get('JUDGE0_API_KEY', '')
JUDGE0_CPU_TIME_LIMIT = float(os.environ.get('JUDGE0_CPU_TIME_LIMIT', '2'))
JUDGE0_WALL_TIME_LIMIT = float(os.environ.get('JUDGE0_WALL_TIME_LIMIT', '5'))
JUDGE0_MEMORY_LIMIT = int(os.environ.get('JUDGE0_MEMORY_LIMIT', '131072'))
JUDGE0_REQUEST_TIMEOUT = int(os.environ.get('JUDGE0_REQUEST_TIMEOUT', '30'))
JUDGE0_POLL_MAX_RETRIES = int(os.environ.get('JUDGE0_POLL_MAX_RETRIES', '15'))
JUDGE0_POLL_INTERVAL = float(os.environ.get('JUDGE0_POLL_INTERVAL', '2'))

# ===========================================================
# SUBMISSION CONFIG
# ===========================================================

SUBMISSION_MAX_CODE_SIZE = int(os.environ.get('SUBMISSION_MAX_CODE_SIZE', '65536'))
SUBMISSION_RATE_LIMIT_PER_DAY = int(os.environ.get('SUBMISSION_RATE_LIMIT_PER_DAY', '50'))

# ===========================================================
# EMAIL (console backend cho dev)
# ===========================================================

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

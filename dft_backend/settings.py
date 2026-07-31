"""
Django settings for dft_backend project.
"""

from datetime import timedelta
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure--7e7_j_k=^4k!l2$que8pib3h@fji_9dm1arxqu1$*hdrfkgn(')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,testserver,loonko-api2.ethioace.com,www.loonko-api2.ethioace.com',
    ).split(',')
    if h.strip()
]
# Always allow the production API hosts even if ALLOWED_HOSTS was set without them
_PRODUCTION_HOSTS = (
    'loonko-api2.ethioace.com',
    'www.loonko-api2.ethioace.com',
)
for _host in _PRODUCTION_HOSTS:
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
if DEBUG and 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'https://loonko-api2.ethioace.com,https://www.loonko-api2.ethioace.com,'
        'https://loonko.vercel.app,https://www.loonko.vercel.app,'
        'http://localhost:3000,http://127.0.0.1:3000',
    ).split(',')
    if o.strip()
]
_PRODUCTION_CSRF = (
    'https://loonko-api2.ethioace.com',
    'https://www.loonko-api2.ethioace.com',
    'https://loonko.vercel.app',
    'https://www.loonko.vercel.app',
)
for _origin in _PRODUCTION_CSRF:
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    # Local
    'accounts',
    'farm',
    'cattle',
    'milk',
    'health',
    'breeding',
    'husbandry',
    'finance.apps.FinanceConfig',
    'alerts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dft_backend.urls'

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

WSGI_APPLICATION = 'dft_backend.wsgi.application'

# Database: SQLite locally, PostgreSQL in production (cPanel).
# Set DB_ENGINE=postgresql in the server .env — leave unset (or sqlite) on your laptop.
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').lower().strip()

if DB_ENGINE in ('postgresql', 'postgres', 'pgsql'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'loonkoo'),
            'USER': os.getenv('DB_USER', ''),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': {
                'connect_timeout': 10,
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('SQLITE_NAME', 'db.sqlite3'),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Addis_Ababa'
USE_I18N = True
USE_TZ = True


STATIC_URL = '/static/'
STATIC_ROOT = Path(
    os.getenv('STATIC_ROOT', str(BASE_DIR / 'staticfiles'))
)

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(
    os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media'))
)



DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,https://loonko.vercel.app',
    ).split(',')
    if o.strip()
]
_PRODUCTION_CORS = (
    'https://loonko.vercel.app',
    'https://www.loonko.vercel.app',
)
for _origin in _PRODUCTION_CORS:
    if _origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_origin)

CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Low-milk alert: flag if total liters are below this fraction of cow's recent average
LOW_MILK_THRESHOLD_RATIO = float(os.getenv('LOW_MILK_THRESHOLD_RATIO', '0.7'))
# Hour (local) after which missing milk for *today* is alerted; yesterday always checked
MISSED_MILK_ALERT_AFTER_HOUR = int(os.getenv('MISSED_MILK_ALERT_AFTER_HOUR', '14'))
VACCINATION_DUE_DAYS = int(os.getenv('VACCINATION_DUE_DAYS', '7'))
CALVING_DUE_DAYS = int(os.getenv('CALVING_DUE_DAYS', '14'))

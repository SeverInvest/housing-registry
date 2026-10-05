import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY.strip():
    raise ImproperlyConfigured(
        "Переменная окружения DJANGO_SECRET_KEY должна содержать секретный ключ Django."
    )
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    value.strip()
    for value in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if value.strip()
]
CSRF_TRUSTED_ORIGINS = [
    value.strip()
    for value in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if value.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "registry",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "housing_registry.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "housing_registry.wsgi.application"
ASGI_APPLICATION = "housing_registry.asgi.application"

if os.getenv("DB_ENGINE", "postgresql") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    db_options = {}
    if sslmode := os.getenv("PGSSLMODE", "").strip():
        db_options["sslmode"] = sslmode
    if sslrootcert := os.getenv("PGSSLROOTCERT"):
        db_options["sslrootcert"] = sslrootcert

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("PGDATABASE", "housing_registry"),
            "USER": os.getenv("PGUSER", "housing_registry"),
            "PASSWORD": os.getenv("PGPASSWORD", ""),
            "HOST": os.getenv("PGHOST", "127.0.0.1"),
            "PORT": os.getenv("PGPORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": db_options,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

GIS_API_BASE_URL = os.getenv("GIS_API_BASE_URL", "https://dom.gosuslugi.ru")
GIS_REGION_CODE = os.getenv("GIS_REGION_CODE", "")
GIS_REGION_GUID = os.getenv("GIS_REGION_GUID", "")
GIS_REQUEST_TIMEOUT = float(os.getenv("GIS_REQUEST_TIMEOUT", "60"))
GIS_MAX_RETRIES = int(os.getenv("GIS_MAX_RETRIES", "4"))

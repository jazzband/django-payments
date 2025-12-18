from __future__ import annotations

import os
import sys

# Add testapp/testapp to Python path so testmain can be imported
TESTAPP_ROOT = os.path.join(os.path.dirname(__file__), "testapp", "testapp")
if TESTAPP_ROOT not in sys.path:
    sys.path.insert(0, TESTAPP_ROOT)

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "payments"))
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(PROJECT_ROOT, "templates")],
    }
]

SECRET_KEY = "NOTREALLY"
PAYMENT_HOST = "example.com"

INSTALLED_APPS = [
    "payments",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "testmain",
]

# Database configuration for tests that use ORM operations
# (e.g., wallet tests that verify model lifecycle and relationships)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

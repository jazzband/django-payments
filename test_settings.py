from __future__ import annotations

import os
import sys

from django.urls import include
from django.urls import path

# testmain (the example app with a concrete payment model) lives here.
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

ROOT_URLCONF = "test_settings"

urlpatterns = [
    path("payments/", include("payments.urls")),
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

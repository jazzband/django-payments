# Generated migration for wallet support
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("testmain", "0002_payment_billing_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="Wallet",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        blank=True,
                        default=None,
                        help_text="Payment method token/ID from provider (e.g., PaymentMethod ID for Stripe, card token for PayU, recurringDetailReference for Adyen)",
                        max_length=255,
                        null=True,
                        verbose_name="wallet token/id",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("active", "Active"),
                            ("erased", "Erased"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                (
                    "extra_data",
                    models.JSONField(
                        default=dict,
                        help_text="Provider-specific data (e.g., card details, expiry dates, customer IDs)",
                        verbose_name="extra data",
                    ),
                ),
                (
                    "payment_provider",
                    models.CharField(
                        help_text="Payment variant name (e.g., 'stripe-recurring', 'payu-recurring')",
                        max_length=50,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="payment",
            name="wallet",
            field=models.ForeignKey(
                blank=True,
                help_text="Wallet used for recurring payments",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="testmain.wallet",
            ),
        ),
    ]

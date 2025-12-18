# Generated migration for subscription support
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("testmain", "0003_wallet_payment_wallet"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "subscription_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Provider's subscription identifier "
                            "(e.g., Stripe subscription ID, "
                            "PayPal billing agreement ID)"
                        ),
                        max_length=255,
                        verbose_name="subscription ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("active", "Active"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                (
                    "extra_data",
                    models.JSONField(
                        default=dict,
                        help_text=(
                            "Provider-specific subscription data "
                            "(e.g., plan details, next billing date, "
                            "cancellation reason)"
                        ),
                        verbose_name="extra data",
                    ),
                ),
                (
                    "payment_provider",
                    models.CharField(
                        help_text=(
                            "Payment variant name "
                            "(e.g., 'stripe-subscription', "
                            "'paypal-subscription')"
                        ),
                        max_length=50,
                    ),
                ),
                (
                    "plan",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Subscription plan identifier (e.g., 'basic', 'premium')"
                        ),
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
            name="subscription",
            field=models.ForeignKey(
                blank=True,
                help_text="Subscription for provider-managed recurring payments",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="testmain.subscription",
            ),
        ),
    ]

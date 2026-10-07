from __future__ import annotations

import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("testmain", "0003_alter_payment_status"),
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
                        default="",
                        help_text="Stored payment method token/ID from the provider",
                        max_length=255,
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
                        help_text="Provider-specific data",
                        verbose_name="extra data",
                    ),
                ),
                ("payment_provider", models.CharField(max_length=50)),
            ],
        ),
        migrations.AddField(
            model_name="payment",
            name="wallet",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="testmain.wallet",
            ),
        ),
    ]

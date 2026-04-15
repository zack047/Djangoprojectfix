from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mentee", "0077_update_certification_verification_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="internshippbl",
            name="qr_detected",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="qr_payload",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="qr_url_accessible",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="qr_url_checked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="verification_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="verification_notes",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internshippbl",
            name="verification_status",
            field=models.CharField(
                choices=[("verified", "Verified"), ("verify_physically", "Verify Physically")],
                default="verify_physically",
                max_length=20,
            ),
        ),
    ]

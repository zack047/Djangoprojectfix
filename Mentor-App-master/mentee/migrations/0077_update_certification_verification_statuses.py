from django.db import migrations, models


def normalize_verification_status(apps, schema_editor):
    CertificationCourse = apps.get_model("mentee", "CertificationCourse")

    CertificationCourse.objects.filter(verification_status="manual_verified").update(verification_status="verified")
    CertificationCourse.objects.filter(verification_status__in=["pending", "unverified", "rejected"]).update(
        verification_status="verify_physically"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("mentee", "0076_certificationcourse_verification_fields"),
    ]

    operations = [
        migrations.RunPython(normalize_verification_status, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="certificationcourse",
            name="verification_status",
            field=models.CharField(
                choices=[("verified", "Verified"), ("verify_physically", "Verify Physically")],
                default="verify_physically",
                max_length=20,
            ),
        ),
    ]

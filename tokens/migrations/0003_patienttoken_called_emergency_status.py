from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0002_patienttoken_issue_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="patienttoken",
            name="called_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="patienttoken",
            name="is_emergency",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="patienttoken",
            name="status",
            field=models.CharField(
                choices=[
                    ("waiting", "Waiting"),
                    ("checked_in", "Checked In"),
                    ("called", "Called"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("missed", "Missed"),
                ],
                default="waiting",
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name="patienttoken",
            options={"ordering": ["date", "-is_emergency", "token_number"]},
        ),
    ]

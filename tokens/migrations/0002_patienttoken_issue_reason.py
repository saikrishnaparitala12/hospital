from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tokens', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='patienttoken',
            name='issue_reason',
            field=models.TextField(blank=True, help_text="Patient's complaint / reason for visit"),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("departments", "0002_delete_hospitalconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="department",
            name="reminder_threshold_tokens",
            field=models.PositiveIntegerField(
                default=3,
                help_text="Notify patients when they are this many tokens away",
            ),
        ),
    ]

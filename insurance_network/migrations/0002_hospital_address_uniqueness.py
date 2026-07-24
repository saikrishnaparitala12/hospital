from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("insurance_network", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="hospital",
            unique_together={("normalized_name", "normalized_address", "pincode")},
        ),
        migrations.AddIndex(
            model_name="hospital",
            index=models.Index(fields=["normalized_name", "pincode"], name="hospital_name_pin_idx"),
        ),
    ]

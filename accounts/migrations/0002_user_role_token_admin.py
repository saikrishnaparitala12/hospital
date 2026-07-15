from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('doctor', 'Doctor'),
                    ('token_admin', 'Token Admin'),
                    ('patient', 'Patient'),
                ],
                default='patient',
                max_length=20,
            ),
        ),
    ]

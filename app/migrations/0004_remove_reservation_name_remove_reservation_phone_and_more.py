# Generated by Django 5.0.7 on 2024-08-09 16:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_migrate_phone_to_text'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reservation',
            name='name',
        ),
        migrations.RemoveField(
            model_name='reservation',
            name='phone',
        ),
    ]

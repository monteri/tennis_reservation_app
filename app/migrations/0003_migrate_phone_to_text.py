# Generated by Django 5.0.7 on 2024-08-09 16:51

from django.db import migrations, models


def migrate_phone_to_text(apps, schema_editor):
    Reservation = apps.get_model('app', 'Reservation')
    for reservation in Reservation.objects.all():
        reservation.text = reservation.phone
        reservation.save()

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_adminsession'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='text',
            field=models.TextField(default='Null'),
            preserve_default=False,
        ),
        migrations.RunPython(migrate_phone_to_text),
    ]
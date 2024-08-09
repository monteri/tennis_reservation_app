from django.db import models
from django.contrib.auth.hashers import make_password


class Admin(models.Model):
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        # Hash the password before saving
        if not self.pk:
            self.password = make_password(self.password)
        super().save(*args, **kwargs)


class AdminSession(models.Model):
    chat_id = models.CharField(max_length=255)


class Reservation(models.Model):
    start_date = models.DateField()
    start_time = models.TimeField()
    duration = models.PositiveIntegerField()
    text = models.TextField()
    username = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed = models.BooleanField(default=False)

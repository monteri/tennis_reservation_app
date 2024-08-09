from django.contrib import admin
from .models import Admin, Reservation, AdminSession


@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display = ('username',)
    search_fields = ('username',)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('start_date', 'start_time', 'duration', 'username', 'text', 'created_at')
    search_fields = ('username', 'text')
    list_filter = ('start_date', 'created_at')

admin.site.register(AdminSession)
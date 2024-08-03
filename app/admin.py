from django.contrib import admin
from .models import Admin, Reservation, AdminSession


@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display = ('username',)
    search_fields = ('username',)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'start_time', 'duration', 'username', 'phone', 'created_at')
    search_fields = ('name', 'username', 'phone')
    list_filter = ('start_date', 'created_at')

admin.site.register(AdminSession)
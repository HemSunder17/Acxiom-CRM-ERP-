from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('CRM', {'fields': ('role', 'failed_login_count', 'lockout_end')}),)
    list_display = ('username', 'email', 'role', 'is_active')
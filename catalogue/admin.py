from django.contrib import admin

from .models import ChargeType


@admin.register(ChargeType)
class ChargeTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')

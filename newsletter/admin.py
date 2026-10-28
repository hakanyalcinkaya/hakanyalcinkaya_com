from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from newsletter.models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "status", "confirmed_at", "created_at")
    list_filter = ("status", "confirmed_at", "created_at")
    search_fields = ("email", "name")
    readonly_fields = ("confirm_token", "confirmed_at", "unsubscribed_at", "created_at", "updated_at")
    actions = ("confirm", "unsubscribe")

    @admin.action(description=_("Seçili aboneleri onayla"))
    def confirm(self, request, queryset):
        for subscriber in queryset:
            subscriber.confirm()

    @admin.action(description=_("Seçili aboneleri abonelikten çıkar"))
    def unsubscribe(self, request, queryset):
        for subscriber in queryset:
            subscriber.unsubscribe()

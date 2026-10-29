from django.contrib import admin

from mailing.models import EmailEvent, EmailLog


class EmailEventInline(admin.TabularInline):
    model = EmailEvent
    extra = 0
    can_delete = False
    fields = ("kind", "url", "user_agent", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Giden e-posta kayıtları yalnız görüntülenir (içerik Stüdyo → E-postalar → Gönderim günlüğü'nde)."""

    list_display = ("subject", "template", "to_email", "status", "open_count", "click_count", "created_at")
    list_filter = ("status", "template", "created_at")
    search_fields = ("to_email", "subject")
    list_select_related = ("user",)
    inlines = (EmailEventInline,)
    readonly_fields = (
        "token",
        "template",
        "to_email",
        "delivered_to",
        "user",
        "subject",
        "text_body",
        "html_body",
        "status",
        "error",
        "sent_at",
        "open_count",
        "first_opened_at",
        "click_count",
        "first_clicked_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

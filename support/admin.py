from django.contrib import admin

from support.models import Ticket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    fields = ("created_at", "from_staff", "author", "body")
    readonly_fields = ("created_at",)
    raw_id_fields = ("author",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "status", "has_unread_reply", "last_message_at")
    list_filter = ("status",)
    list_select_related = ("user",)
    search_fields = ("subject", "name", "email")
    raw_id_fields = ("user",)
    inlines = [TicketMessageInline]

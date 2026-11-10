from adminsortable2.admin import SortableAdminMixin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from account.models import AccountEvent, InstructorProfile, PageView, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Kişisel bilgiler"), {"fields": ("first_name", "last_name")}),
        (
            _("Yetkiler"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Önemli tarihler"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )


@admin.register(InstructorProfile)
class InstructorProfileAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("display_name", "user", "title", "status")
    list_editable = ("status",)
    list_filter = ("status", ("photo", admin.EmptyFieldListFilter))
    search_fields = ("display_name", "user__email", "user__first_name", "user__last_name")
    prepopulated_fields = {"slug": ("display_name",)}
    autocomplete_fields = ("user",)
    fieldsets = (
        (None, {"fields": ("user", "display_name", "slug", "title", "photo", "bio")}),
        (_("Bağlantılar"), {"fields": ("website", "youtube", "linkedin", "github")}),
        (_("Yayın"), {"fields": ("status", "published_at")}),
    )



@admin.register(AccountEvent)
class AccountEventAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "country", "device", "created_at")
    list_filter = ("kind", "created_at", ("ip_masked_at", admin.EmptyFieldListFilter))
    search_fields = ("user__email",)
    list_select_related = ("user",)
    raw_id_fields = ("user",)
    readonly_fields = ("user", "kind", "data", "ip_masked_at", "created_at", "updated_at")

    @admin.display(description=_("ülke"))
    def country(self, obj):
        return (obj.data.get("geo") or {}).get("country_code", "")

    @admin.display(description=_("cihaz"))
    def device(self, obj):
        return (obj.data.get("agent") or {}).get("type", "")


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ("__str__", "view_name", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__email", "path")
    list_select_related = ("user",)
    raw_id_fields = ("user",)
    readonly_fields = ("user", "path", "view_name", "data", "ip_masked_at", "created_at", "updated_at")

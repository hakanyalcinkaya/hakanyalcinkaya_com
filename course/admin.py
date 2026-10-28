from adminsortable2.admin import SortableAdminMixin, SortableTabularInline
from django.conf import settings
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import ParentFilteredSortableAdminMixin
from core.money import format_try
from course.models import (
    Bundle,
    BundleCourse,
    Category,
    Course,
    CourseHighlight,
    CourseInstructor,
    Lesson,
    LessonSubtitle,
    Review,
    Section,
    Technology,
    VideoUpload,
)
from course.vimeo import VimeoError

# Sıralama sürükle-bırak ile yapılır (django-admin-sortable2); sort_order formlarda gösterilmez.
PUBLISH_FIELDS = (_("Yayın"), {"fields": ("status", "published_at")})


def vimeo_ready(modeladmin, request):
    if settings.VIMEO_ACCESS_TOKEN:
        return True
    modeladmin.message_user(
        request, _("Vimeo API anahtarı (VIMEO_ACCESS_TOKEN) tanımlı değil; süre hesaplanamadı."), messages.ERROR
    )
    return False


@admin.register(Category)
class CategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "parent", "status")
    list_editable = ("status",)
    list_filter = ("status", "parent")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Technology)
class TechnologyAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class CourseInstructorInline(SortableTabularInline):
    model = CourseInstructor
    extra = 0
    autocomplete_fields = ("instructor",)


class CourseHighlightInline(SortableTabularInline):
    model = CourseHighlight
    extra = 0
    fields = ("kind", "title", "text")


class SectionInline(SortableTabularInline):
    model = Section
    extra = 0
    fields = ("title", "slug", "status")
    show_change_link = True


@admin.register(Course)
class CourseAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("title", "category", "level", "price_display", "status")
    list_editable = ("status",)
    list_filter = ("status", "category", "level", "subcategories", "technologies")
    search_fields = ("title", "short_title")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("category", "subcategories", "technologies")
    inlines = (CourseInstructorInline, CourseHighlightInline, SectionInline)
    actions = ("sync_durations",)
    fieldsets = (
        (None, {"fields": ("title", "short_title", "slug", "subtitle", "description", "image")}),
        (
            _("Vimeo"),
            {
                "fields": ("preview_vimeo_id", "preview_vimeo_hash", "preview_vimeo_title", "vimeo_folder_uri", "vimeo_folder_link"),
                "description": _("Tanıtım videosu ve klasör, stüdyodan yükleme yapınca kendiliğinden dolar."),
            },
        ),
        (_("Sınıflandırma"), {"fields": ("category", "subcategories", "technologies", "level")}),
        (_("Fiyat (₺, KDV dahil)"), {"fields": ("price", "list_price")}),
        (_("Sayfa"), {"fields": ("access_note",)}),
        PUBLISH_FIELDS,
    )

    readonly_fields = ("preview_vimeo_title", "vimeo_folder_link")

    @admin.display(description=_("Vimeo'da klasör"))
    def vimeo_folder_link(self, obj):
        if not obj.vimeo_folder_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.vimeo_folder_url, obj.vimeo_folder_url)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.queue_preview_title_sync():
            self.message_user(request, _("Tanıtım videosunun başlığı Vimeo'da da güncellenecek."))

    @admin.display(description=_("fiyat"), ordering="price")
    def price_display(self, obj):
        if obj.has_list_discount:
            return f"{format_try(obj.price)} (liste {format_try(obj.list_price)})"
        return format_try(obj.price)

    @admin.action(description=_("Seçili kursların tüm ders sürelerini Vimeo'dan hesapla"))
    def sync_durations(self, request, queryset):
        if not vimeo_ready(self, request):
            return
        for course in queryset:
            try:
                count = course.sync_durations()
            except VimeoError as error:
                self.message_user(request, f"{course}: {error}", messages.ERROR)
                continue
            self.message_user(request, _("%(course)s: %(count)s dersin süresi güncellendi.") % {"course": course, "count": count})


class LessonInline(SortableTabularInline):
    model = Lesson
    extra = 0
    fields = ("title", "slug", "kind", "is_preview", "vimeo_id", "vimeo_hash", "duration_seconds", "status")
    show_change_link = True


@admin.register(Section)
class SectionAdmin(ParentFilteredSortableAdminMixin, admin.ModelAdmin):
    # Listede sıralamak için kurs filtresi seçilmeli; kurs sayfasındaki bölüm tablosunda da sıralanabilir.
    sort_parent_filter = "course__id__exact"
    list_display = ("title", "course", "lesson_count", "status")
    list_editable = ("status",)
    list_filter = ("status", "course")
    search_fields = ("title", "course__title")
    list_select_related = ("course",)
    inlines = (LessonInline,)
    fields = ("course", "title", "slug", "status", "published_at")

    @admin.display(description=_("ders"))
    def lesson_count(self, obj):
        return obj.lessons.count()


@admin.register(Lesson)
class LessonAdmin(ParentFilteredSortableAdminMixin, admin.ModelAdmin):
    # Listede sıralamak için bölüm filtresi seçilmeli; bölüm sayfasındaki ders tablosunda da sıralanabilir.
    sort_parent_filter = "section__id__exact"
    list_display = ("title", "section", "kind", "is_preview", "duration_display", "status")
    list_editable = ("status",)
    list_filter = ("status", "kind", "is_preview", ("vimeo_id", admin.EmptyFieldListFilter), "section__course", "section")
    search_fields = ("title", "section__title", "section__course__title", "vimeo_id")
    list_select_related = ("section__course",)
    autocomplete_fields = ("section",)
    actions = ("sync_duration",)
    fieldsets = (
        (None, {"fields": ("section", "title", "slug", "kind", "is_preview")}),
        (_("Video (Vimeo)"), {"fields": ("vimeo_id", "vimeo_hash", "vimeo_title", "duration_seconds")}),
        (_("Diğer içerik"), {"fields": ("external_url", "body"), "classes": ("collapse",)}),
        PUBLISH_FIELDS,
    )

    readonly_fields = ("vimeo_title",)

    @admin.display(description=_("süre"))
    def duration_display(self, obj):
        return obj.duration_display

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.queue_vimeo_title_sync():
            self.message_user(request, _("Başlık Vimeo'da da güncellenecek."))

    @admin.action(description=_("Seçili derslerin süresini Vimeo'dan hesapla"))
    def sync_duration(self, request, queryset):
        if not vimeo_ready(self, request):
            return
        updated = 0
        for lesson in queryset.exclude(vimeo_id=""):
            try:
                lesson.sync_duration()
            except VimeoError as error:
                self.message_user(request, f"{lesson}: {error}", messages.ERROR)
                continue
            updated += 1
        self.message_user(request, _("%(count)s dersin süresi güncellendi.") % {"count": updated})


@admin.register(Review)
class ReviewAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("display_name", "course", "rating", "source", "status")
    list_editable = ("status",)
    list_filter = ("status", "source", "rating", "course", ("user", admin.EmptyFieldListFilter))
    search_fields = ("author_name", "text", "user__email")
    list_select_related = ("course", "user")
    autocomplete_fields = ("course", "user")
    fields = ("course", "user", "author_name", "text", "rating", "source", "status", "published_at")


class BundleCourseInline(SortableTabularInline):
    model = BundleCourse
    extra = 0
    autocomplete_fields = ("course",)


@admin.register(Bundle)
class BundleAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("title", "price_display", "status")
    list_editable = ("status",)
    list_filter = ("status", "courses")
    search_fields = ("title", "short_title")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (BundleCourseInline,)
    fieldsets = (
        (None, {"fields": ("title", "short_title", "slug", "description", "image")}),
        (_("Fiyat (₺, KDV dahil)"), {"fields": ("price",), "description": _("Liste fiyatı, paketteki kursların fiyat toplamıdır.")}),
        PUBLISH_FIELDS,
    )

    @admin.display(description=_("fiyat"), ordering="price")
    def price_display(self, obj):
        total = obj.compare_price
        if total and total > obj.price:
            return f"{format_try(obj.price)} (kurslar toplamı {format_try(total)})"
        return format_try(obj.price)


@admin.register(CourseInstructor)
class CourseInstructorAdmin(ParentFilteredSortableAdminMixin, admin.ModelAdmin):
    sort_parent_filter = "course__id__exact"
    list_display = ("course", "instructor")
    list_filter = ("course", "instructor")
    search_fields = ("course__title", "instructor__display_name")
    list_select_related = ("course", "instructor")
    autocomplete_fields = ("course", "instructor")


@admin.register(CourseHighlight)
class CourseHighlightAdmin(ParentFilteredSortableAdminMixin, admin.ModelAdmin):
    sort_parent_filter = "course__id__exact"
    list_display = ("__str__", "course", "kind")
    list_filter = ("kind", "course")
    search_fields = ("title", "text", "course__title")
    list_select_related = ("course",)
    autocomplete_fields = ("course",)
    fields = ("course", "kind", "title", "text")


@admin.register(BundleCourse)
class BundleCourseAdmin(ParentFilteredSortableAdminMixin, admin.ModelAdmin):
    sort_parent_filter = "bundle__id__exact"
    list_display = ("bundle", "course")
    list_filter = ("bundle", "course")
    search_fields = ("bundle__title", "course__title")
    list_select_related = ("bundle", "course")
    autocomplete_fields = ("course",)



@admin.register(VideoUpload)
class VideoUploadAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "progress", "vimeo_id", "created_by", "created_at")
    list_filter = ("status", ("course", admin.EmptyFieldListFilter), "lesson__section__course", "course")
    search_fields = ("lesson__title", "course__title", "original_name", "vimeo_id")
    list_select_related = ("lesson", "course", "created_by")
    autocomplete_fields = ("lesson", "course")
    readonly_fields = ("created_at", "finished_at")


@admin.register(LessonSubtitle)
class LessonSubtitleAdmin(admin.ModelAdmin):
    list_display = ("lesson", "language", "status")
    list_filter = ("status", "language", "lesson__section__course")
    search_fields = ("lesson__title",)
    list_select_related = ("lesson",)
    autocomplete_fields = ("lesson",)

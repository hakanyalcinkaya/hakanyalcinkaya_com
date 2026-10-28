from django.contrib import admin

from learning.models import Enrollment, LessonProgress, Note


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "source", "last_watched_at", "completed_at", "created_at")
    list_filter = ("source", ("completed_at", admin.EmptyFieldListFilter), "course", "last_watched_at")
    search_fields = ("user__email", "course__title")
    list_select_related = ("user", "course")
    autocomplete_fields = ("user", "course", "bundle", "last_lesson")
    readonly_fields = ("order", "created_at", "updated_at")


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "position_seconds", "completed_at", "updated_at")
    list_filter = (("completed_at", admin.EmptyFieldListFilter), "lesson__section__course", "updated_at")
    search_fields = ("user__email", "lesson__title")
    list_select_related = ("user", "lesson")
    autocomplete_fields = ("user", "lesson")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "lesson", "created_at")
    list_filter = ("course", ("lesson", admin.EmptyFieldListFilter), "created_at")
    search_fields = ("user__email", "text")
    list_select_related = ("user", "course", "lesson")
    autocomplete_fields = ("user", "course", "lesson")

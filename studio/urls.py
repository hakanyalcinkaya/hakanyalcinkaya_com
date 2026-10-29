from django.urls import path

from studio import views

app_name = "studio"

urlpatterns = [
    path("", views.course_list, name="course_list"),
    path("courses/<uuid:course_id>/", views.course_detail, name="course_detail"),
    path("courses/<uuid:course_id>/sync-titles/", views.course_sync_titles, name="course_sync_titles"),
    path("courses/<uuid:course_id>/videos/", views.course_videos, name="course_videos"),
    path("courses/<uuid:course_id>/structure/", views.course_structure, name="course_structure"),
    path("courses/<uuid:course_id>/sections/", views.section_create, name="section_create"),
    path("courses/<uuid:course_id>/lessons/bulk/", views.lesson_bulk, name="lesson_bulk"),
    path("courses/<uuid:course_id>/extra-contents/", views.course_extra_contents, name="course_extra_contents"),
    path("sections/<uuid:section_id>/", views.section_detail, name="section_detail"),
    path("sections/<uuid:section_id>/block/", views.section_block, name="section_block"),
    path("sections/<uuid:section_id>/videos/", views.section_videos, name="section_videos"),
    path("sections/<uuid:section_id>/title/", views.section_title, name="section_title"),
    path("sections/<uuid:section_id>/status/", views.section_status, name="section_status"),
    path("sections/<uuid:section_id>/delete/", views.section_delete, name="section_delete"),
    path("lessons/<uuid:lesson_id>/status/", views.lesson_status, name="lesson_status"),
    path("lessons/<uuid:lesson_id>/preview/", views.lesson_preview, name="lesson_preview"),
    path("lessons/<uuid:lesson_id>/delete/", views.lesson_delete, name="lesson_delete"),
    path("courses/<uuid:course_id>/preview/", views.course_preview, name="course_preview"),
    path("courses/<uuid:course_id>/preview/status/", views.course_preview_status, name="course_preview_status"),
    path("lessons/<uuid:lesson_id>/title/", views.lesson_title, name="lesson_title"),
    path("lessons/<uuid:lesson_id>/video/", views.lesson_video, name="lesson_video"),
    path("lessons/<uuid:lesson_id>/video/status/", views.lesson_video_status, name="lesson_video_status"),
    path("lessons/<uuid:lesson_id>/subtitles/", views.lesson_subtitles, name="lesson_subtitles"),
    path("lessons/<uuid:lesson_id>/subtitles/status/", views.lesson_subtitles_status, name="lesson_subtitles_status"),
    path("lessons/<uuid:lesson_id>/extra-content/", views.lesson_extra_content, name="lesson_extra_content"),
    path("lessons/<uuid:lesson_id>/extra-content/edit/", views.lesson_extra_content_edit, name="lesson_extra_content_edit"),
    path(
        "lessons/<uuid:lesson_id>/extra-content/delete/",
        views.lesson_extra_content_delete,
        name="lesson_extra_content_delete",
    ),
    path("extra-content/preview/", views.extra_content_preview, name="extra_content_preview"),
    path("subtitles/<uuid:subtitle_id>/retry/", views.subtitle_retry, name="subtitle_retry"),
    path("subtitles/<uuid:subtitle_id>/delete/", views.subtitle_delete, name="subtitle_delete"),
    path("settings/", views.site_settings, name="settings"),
    path("settings/check/<slug:platform>/", views.settings_check, name="settings_check"),
    path("queue/", views.queue, name="queue"),
    path("queue/clear/", views.queue_clear, name="queue_clear"),
    path("uploads/<uuid:upload_id>/retry/", views.upload_retry, name="upload_retry"),
    path("uploads/<uuid:upload_id>/cancel/", views.upload_cancel, name="upload_cancel"),
    path("uploads/<uuid:upload_id>/discard/", views.upload_discard, name="upload_discard"),
]

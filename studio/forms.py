from pathlib import Path

from django import forms
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.models import SiteSettings
from course import video_service
from course.models import (
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    Lesson,
    LessonKind,
    LessonSubtitle,
    Section,
    SubtitleLanguage,
    VideoUpload,
)

SUBTITLE_MAX_BYTES = 2 * 1024 * 1024


class LessonBulkAction(models.TextChoices):
    PUBLISH = "publish", _("Yayınla")
    DRAFT = "draft", _("Taslağa al")
    PREVIEW_ON = "preview_on", _("Önizlemeyi aç")
    PREVIEW_OFF = "preview_off", _("Önizlemeyi kapat")
    DELETE = "delete", _("Sil")
    DELETE_REMOTE = "delete_remote", _("Sil ve videolarını platformdan sil")


class LessonBulkForm(forms.Form):
    """Düzenleyicide seçilen videolara (derslere) toplu işlem; yalnız bu kursun dersleri seçilebilir."""

    action = forms.ChoiceField(choices=LessonBulkAction.choices)
    lessons = forms.ModelMultipleChoiceField(queryset=Lesson.objects.none())

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lessons"].queryset = Lesson.objects.filter(section__course=course)
        self.fields["lessons"].error_messages["required"] = _("Önce video seç.")

    @transaction.atomic
    def save(self):
        """İşlemi uygular, etkilenen ders sayısını döner."""
        action = self.cleaned_data["action"]
        lessons = list(self.cleaned_data["lessons"])
        for lesson in lessons:
            if action == LessonBulkAction.PUBLISH:
                lesson.publish()
            elif action == LessonBulkAction.DRAFT:
                lesson.make_draft()
            elif action in (LessonBulkAction.PREVIEW_ON, LessonBulkAction.PREVIEW_OFF):
                lesson.set_preview(action == LessonBulkAction.PREVIEW_ON)
            else:
                lesson.remove(delete_remote=action == LessonBulkAction.DELETE_REMOTE)
        return len(lessons)

    def message(self, count):
        action = self.cleaned_data["action"]
        texts = {
            LessonBulkAction.PUBLISH: _("%(count)s video yayına alındı."),
            LessonBulkAction.DRAFT: _("%(count)s video taslağa alındı."),
            LessonBulkAction.PREVIEW_ON: _("%(count)s videoda önizleme açıldı."),
            LessonBulkAction.PREVIEW_OFF: _("%(count)s videoda önizleme kapatıldı."),
            LessonBulkAction.DELETE: _("%(count)s video silindi; platformdaki videoları duruyor."),
            LessonBulkAction.DELETE_REMOTE: _("%(count)s video silindi; platformdaki videoları da silinecek."),
        }
        return texts[action] % {"count": count}


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ("video_platform", "sync_video_titles")
        widgets = {"video_platform": forms.RadioSelect}

    def clean_video_platform(self):
        platform = self.cleaned_data["video_platform"]
        missing = video_service.missing_settings(video_service.get(platform).REQUIRED_SETTINGS)
        if missing:
            raise forms.ValidationError(
                _("Bu platform seçilemez; .env dosyasında eksik: %(names)s") % {"names": ", ".join(missing)}
            )
        return platform


def _extension(upload):
    return Path(upload.name).suffix.lower()


class LessonTitleForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ("title",)
        widgets = {"title": forms.TextInput(attrs={"class": "form-control form-control-sm", "autofocus": True})}


class SectionTitleForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("title",)
        widgets = {"title": forms.TextInput(attrs={"class": "form-control form-control-sm", "autofocus": True})}


class SectionCreateForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("title",)
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": _("Yeni kategori adı")})
        }

    def save(self, course):
        section = super().save(commit=False)
        section.course = course
        section.sort_order = course.next_section_order()
        section.save()
        return section


class NewVideoLessonForm(forms.Form):
    """Sürükle-bırak yüklemesi: her dosya için bölümün sonuna taslak ders açılır, başlığı dosya adıdır."""

    file = forms.FileField()

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if _extension(upload) not in VIDEO_EXTENSIONS:
            raise forms.ValidationError(_("Desteklenen türler: %(types)s") % {"types": ", ".join(VIDEO_EXTENSIONS)})
        return upload

    @transaction.atomic
    def save(self, section, user):
        upload_file = self.cleaned_data["file"]
        lesson = Lesson.objects.create(
            section=section,
            title=Path(upload_file.name).stem[:250],
            kind=LessonKind.VIDEO,
            sort_order=section.next_lesson_order(),
        )
        upload = VideoUpload.objects.create(
            lesson=lesson,
            platform=video_service.current_name(),
            file=upload_file,
            original_name=upload_file.name,
            size=upload_file.size,
            created_by=user,
        )
        upload.read_duration()
        upload.queue()
        return lesson


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = VideoUpload
        fields = ("file",)
        widgets = {
            "file": forms.FileInput(attrs={"class": "form-control form-control-sm", "accept": ",".join(VIDEO_EXTENSIONS)})
        }

    def __init__(self, *args, lesson=None, course=None, **kwargs):
        # Hedef ya ders ya da kursun tanıtım videosudur.
        self.lesson = lesson
        self.course = course
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True
        self.fields["file"].label = _("Tanıtım videosu dosyası") if course else _("Video dosyası")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if _extension(upload) not in VIDEO_EXTENSIONS:
            raise forms.ValidationError(_("Desteklenen türler: %(types)s") % {"types": ", ".join(VIDEO_EXTENSIONS)})
        return upload

    def clean(self):
        busy = self.course.has_busy_preview_upload if self.course else self.lesson.has_busy_upload
        if busy:
            raise forms.ValidationError(_("Önceki yükleme henüz bitmedi."))
        return super().clean()

    def save(self, user):
        upload = super().save(commit=False)
        upload.lesson = self.lesson
        upload.course = self.course
        upload.platform = video_service.current_name()
        upload.original_name = upload.file.name
        upload.size = upload.file.size
        upload.created_by = user
        upload.save()
        upload.read_duration()
        upload.queue()
        return upload


class SubtitleForm(forms.Form):
    # data-* öznitelikleri: studio.js dili dosya adından tahmin edip listeyi seçer (ör. ders.en.srt → English).
    language = forms.ChoiceField(
        label=_("Dil"),
        choices=SubtitleLanguage.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm", "data-subtitle-language": ""}),
    )
    file = forms.FileField(
        label=_("SRT / VTT dosyası"),
        widget=forms.FileInput(
            attrs={"class": "form-control form-control-sm", "accept": ",".join(SUBTITLE_EXTENSIONS), "data-subtitle-file": ""}
        ),
    )

    def __init__(self, *args, lesson, **kwargs):
        self.lesson = lesson
        super().__init__(*args, **kwargs)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if _extension(upload) not in SUBTITLE_EXTENSIONS:
            raise forms.ValidationError(_("Yalnız .srt ve .vtt dosyaları yüklenebilir."))
        if upload.size > SUBTITLE_MAX_BYTES:
            raise forms.ValidationError(_("Altyazı dosyası en fazla 2 MB olabilir."))
        # Oynatıcı altyazıyı UTF-8 bekler; farklı kodlamada Türkçe karakterler bozulur.
        try:
            upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError(_("Dosya UTF-8 kodlamalı olmalı."))
        upload.seek(0)
        return upload

    def save(self):
        """Aynı dilde altyazı varsa dosyası değiştirilir; platformdaki eskisinin yerine geçer."""
        language = self.cleaned_data["language"]
        subtitle = LessonSubtitle.objects.filter(lesson=self.lesson, language=language).first()
        if subtitle is None:
            subtitle = LessonSubtitle(lesson=self.lesson, language=language)
        elif subtitle.file:
            subtitle.file.delete(save=False)
        subtitle.file = self.cleaned_data["file"]
        subtitle.save()
        subtitle.schedule()
        return subtitle

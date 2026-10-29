from pathlib import Path

from django import forms
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.models import SiteSettings
from course import video_service
from course.models import (
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    Category,
    Course,
    Lesson,
    LessonKind,
    LessonSubtitle,
    Review,
    ReviewSource,
    Section,
    SubtitleLanguage,
    VideoUpload,
)
from newsletter.models import AudienceKind, Issue

SUBTITLE_MAX_BYTES = 2 * 1024 * 1024
EXTRA_CONTENT_EXTENSIONS = (".md", ".markdown", ".txt", ".html", ".htm")
EXTRA_CONTENT_MAX_BYTES = 1024 * 1024


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
        fields = ("video_platform", "sync_video_titles", "lesson_notes_enabled")
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


def read_extra_content(upload):
    """Ek içerik dosyasını doğrular ve metnini döner (Markdown/TXT/HTML, UTF-8, en fazla 1 MB, boş olmayan)."""
    if _extension(upload) not in EXTRA_CONTENT_EXTENSIONS:
        raise forms.ValidationError(_("Desteklenen türler: %(types)s") % {"types": ", ".join(EXTRA_CONTENT_EXTENSIONS)})
    if upload.size > EXTRA_CONTENT_MAX_BYTES:
        raise forms.ValidationError(_("Ek içerik dosyası en fazla 1 MB olabilir."))
    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise forms.ValidationError(_("Dosya UTF-8 kodlamalı olmalı."))
    if not text.strip():
        raise forms.ValidationError(_("Dosya boş."))
    return text


class ExtraContentUploadForm(forms.Form):
    """Dersin ek içeriği dosyadan: Markdown, düz metin ya da HTML. Varsa mevcut içeriğin yerine geçer."""

    file = forms.FileField(
        label=_("Markdown / TXT / HTML dosyası"),
        widget=forms.FileInput(
            attrs={
                "class": "form-control form-control-sm",
                "accept": ",".join(EXTRA_CONTENT_EXTENSIONS),
                "data-extra-content-file": "",
            }
        ),
    )

    def __init__(self, *args, lesson, **kwargs):
        self.lesson = lesson
        super().__init__(*args, **kwargs)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        self.text = read_extra_content(upload)
        return upload

    def save(self):
        self.lesson.set_extra_content(self.text)
        return self.lesson


class ExtraContentBulkForm(forms.Form):
    """Toplu ek içerik: her istekte bir dosya gelir, kursun dersleriyle dosya adına göre eşleştirilir."""

    file = forms.FileField()
    overwrite = forms.BooleanField(required=False)

    def __init__(self, *args, course, **kwargs):
        self.course = course
        self.lesson = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("file")
        if upload is None:
            return cleaned
        self.text = read_extra_content(upload)
        self.lesson, reason = self.course.match_lesson_for_file(upload.name)
        if self.lesson is None:
            raise forms.ValidationError(reason)
        # İçeriği olan ders, üzerine yazma seçilmediyse değişmez.
        self.skipped = self.lesson.has_extra_content and not cleaned.get("overwrite")
        return cleaned

    def save(self):
        if not self.skipped:
            self.lesson.set_extra_content(self.text)
        return self.lesson


class ExtraContentForm(forms.ModelForm):
    """Ek içeriği düzenleyicide yazma; boş bırakılırsa içerik kaldırılır."""

    class Meta:
        model = Lesson
        fields = ("extra_content",)
        widgets = {
            "extra_content": forms.Textarea(
                attrs={"class": "form-control font-monospace small studio-md-input", "rows": 18, "data-md-input": ""}
            )
        }
        labels = {"extra_content": _("Ek içerik")}

    def save(self, commit=True):
        self.instance.set_extra_content(self.cleaned_data["extra_content"])
        return self.instance


class ReviewImportForm(forms.ModelForm):
    """Eski yorum: ad elle yazılır, puan isteğe bağlı. "Hemen onayla" seçiliyse sitede görünür (öne çıkarma seçenekleriyle)."""

    approve_now = forms.BooleanField(label=_("Hemen onayla"), required=False, initial=True)

    class Meta:
        model = Review
        fields = ("course", "author_name", "rating", "text", "written_at", "featured", "show_on_home")
        widgets = {
            "course": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "author_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": _("Ör. Ayşe K.")}),
            "rating": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "text": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
            "written_at": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}, format="%Y-%m-%d"),
        }
        labels = {"written_at": _("Yorum tarihi")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["author_name"].required = True
        self.fields["text"].required = True
        self.fields["rating"].required = False
        self.fields["written_at"].input_formats = ["%Y-%m-%d"]
        # UUID anahtar nesne açılırken atanır; yeni kayıt pk ile değil _state.adding ile anlaşılır.
        if not self.instance._state.adding:
            self.fields["course"].disabled = True
            self.fields["approve_now"].initial = self.instance.is_visible

    def save(self, commit=True):
        review = super().save(commit=False)
        review.source = ReviewSource.IMPORTED
        review.save()
        if self.cleaned_data["approve_now"]:
            review.approve()
        return review


class IssueForm(forms.ModelForm):
    """Bülten sayısı (yalnız taslak düzenlenir) ve hedef kitlesi. "Tüm aboneler" ve "Sadece aboneler"de eğitim/kategori,
    "satın alanlar" dışında bitirme oranı yok sayılır."""

    AUDIENCE_FIELDS = ("audience", "courses", "categories", "min_progress", "max_progress")

    class Meta:
        model = Issue
        fields = ("headline", "intro", "content", "cta_label", "cta_url", "audience", "courses", "categories", "min_progress", "max_progress")
        widgets = {
            "audience": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "courses": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "categories": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "min_progress": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 0, "max": 100, "placeholder": "0"}),
            "max_progress": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 0, "max": 100, "placeholder": "100"}),
            "headline": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Ör. Yeni kurs: Django ile API"), "data-personalize": ""}
            ),
            "intro": forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-personalize": ""}),
            "content": forms.Textarea(
                attrs={"class": "form-control font-monospace small", "rows": 14, "data-md-input": "", "data-personalize": ""}
            ),
            "cta_label": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Ör. Kursa göz at")}),
            "cta_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://hakanyalcinkaya.com/..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["courses"].queryset = Course.objects.order_by("title")
        self.fields["categories"].queryset = Category.objects.order_by("sort_order", "name")

    def clean_min_progress(self):
        return self._percent("min_progress")

    def clean_max_progress(self):
        return self._percent("max_progress")

    def _percent(self, name):
        value = self.cleaned_data.get(name)
        if value is not None and value > 100:
            raise forms.ValidationError(_("0 ile 100 arasında olmalı."))
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("cta_url") and not cleaned.get("cta_label"):
            self.add_error("cta_label", _("Düğme bağlantısı varsa yazısı da girilmeli."))
        audience = cleaned.get("audience")
        if audience in (AudienceKind.ALL, AudienceKind.SUBSCRIBERS):
            cleaned["courses"], cleaned["categories"] = Course.objects.none(), Category.objects.none()
        if audience != AudienceKind.BUYERS:
            cleaned["min_progress"] = cleaned["max_progress"] = None
        low, high = cleaned.get("min_progress"), cleaned.get("max_progress")
        if low is not None and high is not None and low > high:
            self.add_error("max_progress", _("En çok oran en az orandan küçük olamaz."))
        return cleaned

    def audience_kwargs(self):
        """Kayıt beklemeden kitle hesabı için (sayım): geçerli kitle alanları; hatalıysa None."""
        if any(name in self.errors for name in self.AUDIENCE_FIELDS):
            return None
        data = self.cleaned_data
        return dict(
            kind=data.get("audience") or AudienceKind.ALL,
            courses=data.get("courses") or (),
            categories=data.get("categories") or (),
            min_progress=data.get("min_progress"),
            max_progress=data.get("max_progress"),
        )

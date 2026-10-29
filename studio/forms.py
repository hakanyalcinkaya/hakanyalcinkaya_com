from datetime import datetime, time
from pathlib import Path

from django import forms
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from account.models import InstructorProfile, User
from core.models import SiteSettings
from course import video_service
from course.models import (
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    Bundle,
    BundleCourse,
    Category,
    Course,
    CourseHighlight,
    CourseInstructor,
    Lesson,
    LessonKind,
    LessonSubtitle,
    Review,
    ReviewSource,
    Section,
    SubtitleLanguage,
    Technology,
    VideoUpload,
)
from discount.forms import DiscountTargetsMixin
from discount.models import Discount
from newsletter.models import AudienceKind, Issue
from order.models import OrderStatus

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


# Katalog ve satış yönetimi: Django admin'deki kayıtlar stüdyodan düzenlenir. Sıra listelerde sürükle-bırak ile verilir.
DATETIME_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
DATETIME_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


def _append_order(model, **parent):
    last = model.objects.filter(**parent).order_by("-sort_order").values_list("sort_order", flat=True).first()
    return (last or 0) + 1


class SortedCreateMixin:
    """Yeni kayıt listenin sonuna eklenir (sort_order)."""

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance._state.adding:
            instance.sort_order = _append_order(type(instance))
        if commit:
            instance.save()
            self.save_m2m()
        return instance


def _sync_through(owner, through, owner_field, target_field, selected):
    """Ara tablolu çoklu seçimi kaydeder: kalanların sırası korunur, yeniler sona eklenir, seçilmeyenler çıkar."""
    links = through.objects.filter(**{owner_field: owner})
    selected_ids = {item.pk for item in selected}
    links.exclude(**{f"{target_field}__in": selected_ids}).delete()
    existing = set(links.values_list(f"{target_field}_id", flat=True))
    order = _append_order(through, **{owner_field: owner})
    for item in selected:
        if item.pk not in existing:
            through.objects.create(**{owner_field: owner, target_field: item, "sort_order": order})
            order += 1


class CourseForm(SortedCreateMixin, forms.ModelForm):
    """Kurs bilgileri; videolar ve tanıtım videosu kurs sayfasındaki düzenleyiciden yüklenir."""

    instructors = forms.ModelMultipleChoiceField(
        label=_("Eğitmenler"), queryset=InstructorProfile.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Course
        fields = (
            "title",
            "short_title",
            "slug",
            "subtitle",
            "description",
            "image",
            "category",
            "subcategories",
            "technologies",
            "level",
            "price",
            "list_price",
            "access_note",
            "status",
            "published_at",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "access_note": forms.Textarea(attrs={"rows": 2}),
            "subcategories": forms.CheckboxSelectMultiple,
            "technologies": forms.CheckboxSelectMultiple,
            "published_at": DATETIME_WIDGET,
        }
        help_texts = {"slug": _("Boş bırakılırsa başlıktan üretilir.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["published_at"].input_formats = DATETIME_FORMATS
        self.fields["instructors"].queryset = InstructorProfile.objects.order_by("sort_order", "display_name")
        if not self.instance._state.adding:
            self.fields["instructors"].initial = list(self.instance.instructors.values_list("pk", flat=True))

    def save(self, commit=True):
        course = super().save(commit=commit)
        _sync_through(course, CourseInstructor, "course", "instructor", self.cleaned_data["instructors"])
        return course


class CourseHighlightForm(forms.ModelForm):
    class Meta:
        model = CourseHighlight
        fields = ("kind", "title", "text")
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "title": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": _("Başlık (isteğe bağlı)")}),
            "text": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }


class BaseHighlightFormSet(forms.BaseInlineFormSet):
    def save(self, commit=True):
        """Maddeler formdaki sırayla kaydedilir; silinmek üzere işaretlenenler silinir, boş satırlar atlanır."""
        order = 0
        for form in self.forms:
            adding = form.instance._state.adding
            if form in self.deleted_forms:
                if not adding:
                    form.instance.delete()
                continue
            if adding and not form.has_changed():
                continue
            item = form.save(commit=False)
            item.course = self.instance
            item.sort_order = order
            item.save()
            order += 1


CourseHighlightFormSet = forms.inlineformset_factory(
    Course, CourseHighlight, form=CourseHighlightForm, formset=BaseHighlightFormSet, extra=3, can_delete=True
)


class BundleForm(SortedCreateMixin, forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        label=_("Kurslar"), queryset=Course.objects.none(), widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Bundle
        fields = ("title", "short_title", "slug", "description", "image", "price", "status", "published_at")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "published_at": DATETIME_WIDGET}
        help_texts = {"price": _("Liste fiyatı, paketteki kursların fiyat toplamıdır."), "slug": _("Boş bırakılırsa başlıktan üretilir.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["published_at"].input_formats = DATETIME_FORMATS
        self.fields["courses"].queryset = Course.objects.order_by("sort_order", "title")
        if not self.instance._state.adding:
            self.fields["courses"].initial = list(self.instance.courses.values_list("pk", flat=True))

    def save(self, commit=True):
        bundle = super().save(commit=commit)
        _sync_through(bundle, BundleCourse, "bundle", "course", self.cleaned_data["courses"])
        return bundle


class CategoryForm(SortedCreateMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug", "parent", "status")
        help_texts = {"parent": _("Üst kategori filtrelerde, alt kategoriler kurs başlığında etiket olarak görünür.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        parents = Category.objects.filter(parent__isnull=True)
        self.fields["parent"].queryset = parents.exclude(pk=self.instance.pk) if not self.instance._state.adding else parents


class TechnologyForm(SortedCreateMixin, forms.ModelForm):
    class Meta:
        model = Technology
        fields = ("name", "slug")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False


class InstructorForm(SortedCreateMixin, forms.ModelForm):
    """Eğitmen profili bir üyeye bağlıdır; üye e-postasıyla seçilir."""

    user_email = forms.EmailField(label=_("Üye e-postası"), help_text=_("Profil bu e-postayla kayıtlı üyeye bağlanır."))

    class Meta:
        model = InstructorProfile
        fields = ("display_name", "slug", "title", "photo", "bio", "website", "youtube", "linkedin", "github", "status")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    field_order = ("user_email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        if not self.instance._state.adding:
            self.fields["user_email"].initial = self.instance.user.email

    def clean_user_email(self):
        user = User.objects.with_email(self.cleaned_data["user_email"]).first()
        if user is None:
            raise forms.ValidationError(_("Bu e-postayla üye yok."))
        if InstructorProfile.objects.filter(user=user).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Bu üyenin zaten eğitmen profili var."))
        self.instance.user = user
        return user.email


class DiscountForm(DiscountTargetsMixin, forms.ModelForm):
    class Meta:
        model = Discount
        fields = (
            "code",
            "kind",
            "value",
            "note",
            "courses",
            "bundles",
            "valid_from",
            "valid_until",
            "max_uses",
            "max_uses_per_user",
            "status",
        )
        widgets = {
            "courses": forms.CheckboxSelectMultiple,
            "bundles": forms.CheckboxSelectMultiple,
            "valid_from": DATETIME_WIDGET,
            "valid_until": DATETIME_WIDGET,
        }
        help_texts = {"courses": _("Yüzde indirimde kurs ve paket seçilmezse hepsinde geçerlidir.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("valid_from", "valid_until"):
            self.fields[name].input_formats = DATETIME_FORMATS
        self.fields["courses"].queryset = Course.objects.order_by("sort_order", "title")
        self.fields["bundles"].queryset = Bundle.objects.order_by("sort_order", "title")


class EnrollmentGrantForm(forms.Form):
    """Üyeye elle kurs erişimi açar (hediye ya da manuel); zaten kayıtlı olduğu kurslar listelenmez."""

    course = forms.ModelChoiceField(label=_("Kurs"), queryset=Course.objects.none())
    source = forms.ChoiceField(label=_("Kaynak"), choices=())

    def __init__(self, *args, user, **kwargs):
        from learning.models import EnrollmentSource

        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["course"].queryset = Course.objects.exclude(enrollments__user=user).order_by("sort_order", "title")
        self.fields["source"].choices = [(EnrollmentSource.GIFT, EnrollmentSource.GIFT.label), (EnrollmentSource.MANUAL, EnrollmentSource.MANUAL.label)]
        self.fields["course"].widget.attrs["class"] = "form-select form-select-sm"
        self.fields["source"].widget.attrs["class"] = "form-select form-select-sm"

    def save(self):
        from learning.models import Enrollment

        return Enrollment.objects.create(user=self.user, course=self.cleaned_data["course"], source=self.cleaned_data["source"])


class MemberAccessForm(forms.ModelForm):
    """Üyenin hesabı açık mı; kapalı hesap giriş yapamaz. Kendi hesabını kapatamaz."""

    class Meta:
        model = User
        fields = ("is_active",)
        labels = {"is_active": _("Hesap açık")}

    def __init__(self, *args, editor, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk == editor.pk:
            for field in self.fields.values():
                field.disabled = True


class OrderFilterForm(forms.Form):
    """Sipariş listesi filtreleri (GET): durum, kurs/paket, ödeme sağlayıcı, para birimi, indirim kodu, tarih ve arama.
    Tarih aralığı ödeme tarihine, ödenmemişlerde oluşturulma tarihine bakar (yerel gün)."""

    DISCOUNT_CHOICES = (("", _("Kod: tümü")), ("var", _("Kodlu")), ("yok", _("Kodsuz")))

    q = forms.CharField(label=_("Ara"), required=False)
    durum = forms.ChoiceField(label=_("Durum"), required=False)
    kurs = forms.ModelChoiceField(label=_("Kurs"), queryset=Course.objects.none(), required=False, empty_label=_("Tüm kurslar"))
    paket = forms.ModelChoiceField(label=_("Paket"), queryset=Bundle.objects.none(), required=False, empty_label=_("Tüm paketler"))
    saglayici = forms.ChoiceField(label=_("Ödeme yolu"), required=False)
    para = forms.ChoiceField(label=_("Para birimi"), required=False)
    kod = forms.ChoiceField(label=_("İndirim kodu"), required=False, choices=DISCOUNT_CHOICES)
    baslangic = forms.DateField(label=_("Başlangıç"), required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    bitis = forms.DateField(label=_("Bitiş"), required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, orders, with_status=True, with_course=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["durum"].choices = [("", _("Tüm durumlar"))] + list(OrderStatus.choices)
        self.fields["kurs"].queryset = Course.objects.order_by("sort_order", "title")
        self.fields["paket"].queryset = Bundle.objects.order_by("sort_order", "title")
        providers = orders.exclude(payment_provider="").order_by().values_list("payment_provider", flat=True).distinct()
        self.fields["saglayici"].choices = [("", _("Tüm ödeme yolları"))] + [(name, name) for name in sorted(providers)]
        currencies = orders.order_by().values_list("currency", flat=True).distinct()
        self.fields["para"].choices = [("", _("Tüm para birimleri"))] + [(code, code) for code in sorted(currencies)]
        if not with_status:
            del self.fields["durum"]
        if not with_course:
            del self.fields["kurs"]
        for name, field in self.fields.items():
            css = "form-select form-select-sm w-auto" if isinstance(field, (forms.ChoiceField, forms.ModelChoiceField)) else "form-control form-control-sm w-auto"
            field.widget.attrs.setdefault("class", css)
            field.widget.attrs.setdefault("aria-label", field.label)
        self.fields["q"].widget.attrs.update(type="search", placeholder=_("E-posta ya da sipariş no"))

    def filter(self, orders):
        if not self.is_valid():
            return orders
        data = self.cleaned_data
        if data.get("q"):
            orders = orders.filter(Q(email__icontains=data["q"]) | Q(number__icontains=data["q"]) | Q(user__email__icontains=data["q"]))
        if data.get("durum"):
            orders = orders.filter(status=data["durum"])
        if data.get("kurs"):
            orders = orders.containing(data["kurs"])
        if data.get("paket"):
            orders = orders.filter(items__bundle=data["paket"]).distinct()
        if data.get("saglayici"):
            orders = orders.filter(payment_provider=data["saglayici"])
        if data.get("para"):
            orders = orders.filter(currency=data["para"])
        if data.get("kod") == "var":
            orders = orders.exclude(discount_code="")
        elif data.get("kod") == "yok":
            orders = orders.filter(discount_code="")
        if data.get("baslangic") or data.get("bitis"):
            orders = orders.annotate(sale_at=Coalesce("paid_at", F("created_at")))
            zone = timezone.get_current_timezone()
            if data.get("baslangic"):
                orders = orders.filter(sale_at__gte=datetime.combine(data["baslangic"], time.min, tzinfo=zone))
            if data.get("bitis"):
                orders = orders.filter(sale_at__lte=datetime.combine(data["bitis"], time.max, tzinfo=zone))
        return orders

    @property
    def is_filtered(self):
        return self.is_valid() and any(value for value in self.cleaned_data.values())

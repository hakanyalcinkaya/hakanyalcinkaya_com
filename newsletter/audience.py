"""Bülten hedef kitlesi: onaylı aboneler arasından satın alma, kurs/kategori ve bitirme oranına göre seçim.

Abone ile üye e-posta adresiyle eşleşir (büyük/küçük harf duyarsız). Kurs ya da kategori seçilmezse bütün kurslar
kapsamdadır. Bitirme oranı yalnız "satın alanlar"da kullanılır: kapsamdaki kurslardan en az birinde ilerlemesi aralıkta
olan üye seçilir (yayındaki derslere göre, %0-100).
"""

from django.db.models import Count, Q
from django.db.models.functions import Lower

from course.models import Course, Lesson
from core.models import Status
from learning.models import Enrollment, LessonProgress
from newsletter.models import AudienceKind, Subscriber


def scope_courses(courses=(), categories=()):
    """Seçilen kurslar ve seçilen kategorilerdeki (ana ya da alt kategori) kurslar; ikisi de boşsa None (hepsi)."""
    course_ids = {course.pk for course in courses}
    if categories:
        category_ids = [category.pk for category in categories]
        course_ids |= set(
            Course.objects.filter(Q(category__in=category_ids) | Q(subcategories__in=category_ids)).values_list("pk", flat=True)
        )
    if not courses and not categories:
        return None
    return course_ids


def _progress(enrollments):
    """{(kullanıcı, kurs): yüzde} yayındaki derslere göre; iki sorgu."""
    pairs = list(enrollments.values_list("user_id", "course_id"))
    course_ids = {course_id for _user, course_id in pairs}
    published = Lesson.objects.published().filter(section__course__in=course_ids, section__status=Status.PUBLISHED)
    totals = dict(published.values("section__course").annotate(n=Count("pk")).values_list("section__course", "n"))
    done = {
        (row["user"], row["lesson__section__course"]): row["n"]
        for row in LessonProgress.objects.filter(
            user__in={user_id for user_id, _course in pairs}, lesson__in=published, completed_at__isnull=False
        )
        .values("user", "lesson__section__course")
        .annotate(n=Count("pk"))
    }
    return {
        (user_id, course_id): round(done.get((user_id, course_id), 0) * 100 / totals[course_id]) if totals.get(course_id) else 0
        for user_id, course_id in pairs
    }


def buyer_emails(course_ids=None, min_progress=None, max_progress=None):
    """Kapsamdaki kurslara erişimi olan üyelerin e-postaları (küçük harf), isteğe bağlı bitirme oranı aralığıyla."""
    enrollments = Enrollment.objects.all()
    if course_ids is not None:
        enrollments = enrollments.filter(course__in=course_ids)
    if min_progress is None and max_progress is None:
        return set(enrollments.annotate(email_lower=Lower("user__email")).values_list("email_lower", flat=True))
    low, high = min_progress or 0, 100 if max_progress is None else max_progress
    user_ids = {user_id for (user_id, _course), percent in _progress(enrollments).items() if low <= percent <= high}
    return set(
        Enrollment.objects.filter(user__in=user_ids).annotate(email_lower=Lower("user__email")).values_list("email_lower", flat=True)
    )


def subscribers(kind, courses=(), categories=(), min_progress=None, max_progress=None):
    """Bültenin gideceği onaylı aboneler (QuerySet)."""
    confirmed = Subscriber.objects.confirmed().annotate(email_lower=Lower("email"))
    if kind == AudienceKind.ALL:
        return confirmed
    course_ids = scope_courses(courses, categories)
    if kind == AudienceKind.BUYERS:
        return confirmed.filter(email_lower__in=buyer_emails(course_ids, min_progress, max_progress))
    return confirmed.exclude(email_lower__in=buyer_emails(course_ids))

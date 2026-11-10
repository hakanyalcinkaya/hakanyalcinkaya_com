"""Ders izleme kaydı (LessonView): görünümlerden çağrılır; bir hata ders sayfasını ya da oynatıcının bildirimini
bozmasın diye loglanır ve geçilir."""

import logging

from learning.models import LessonView

logger = logging.getLogger(__name__)


def lesson_opened(request, lesson):
    try:
        LessonView.open(request, lesson)
    except Exception:  # noqa: BLE001
        logger.exception("Ders izleme kaydı açılamadı")


def position_saved(user, lesson, seconds):
    try:
        LessonView.record_position(user, lesson, seconds)
    except Exception:  # noqa: BLE001
        logger.exception("Ders izleme süresi yazılamadı")


def completed_changed(user, lesson, done):
    try:
        LessonView.record_completed(user, lesson, done)
    except Exception:  # noqa: BLE001
        logger.exception("Ders izleme tamamlanması yazılamadı")

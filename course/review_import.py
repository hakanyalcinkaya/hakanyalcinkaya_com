"""Başka platformdan (Udemy) çekilmiş yorumları kursa eski yorum olarak aktarır.

Dosya biçimi (Markdown): başlıkta "Çekilme tarihi: GG.AA.YYYY", her yorum "### 1. Ad — ★★★★★ (5.0) — 2 yıl önce" başlığı
ve altında metin. Kaynak yalnız göreli zaman verdiği için yorum tarihi çekilme tarihinden geriye hesaplanır (yaklaşık).
Yarım puanlar sitede tam sayı olduğu için aşağı yuvarlanır (4.5 → 4); puan şişirilmez.

Tekrar çalıştırılabilir: aynı kursta aynı ad ve metinli yorum ikinci kez eklenmez. Aktarılan yorumlar onaylı yayımlanır.
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from course.models import Review, ReviewSource

FETCHED = re.compile(r"Çekilme tarihi:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
HEADING = re.compile(r"^###\s+\d+\.\s+(?P<name>.+?)\s+—\s+[★½☆]*\s*\((?P<rating>[\d.]+)\)\s+—\s+(?P<ago>.+?)\s*$")
AGO = re.compile(r"(?P<amount>\d+|bir)\s+(?P<unit>yıl|ay|hafta|gün|saat|dakika)\s+önce")
UNIT_DAYS = {"yıl": 365, "ay": 30, "hafta": 7, "gün": 1, "saat": 1 / 24, "dakika": 1 / 1440}


class ReviewFileError(Exception):
    pass


@dataclass
class ParsedReview:
    name: str
    rating: int
    text: str
    written_at: datetime


def _written_at(ago, fetched):
    match = AGO.search(ago)
    if not match:
        return fetched
    amount = 1 if match.group("amount") == "bir" else int(match.group("amount"))
    return fetched - timedelta(days=amount * UNIT_DAYS[match.group("unit")])


def parse_reviews(text):
    """Dosyadaki yorumlar (ParsedReview listesi); çekilme tarihi yoksa ReviewFileError."""
    found = FETCHED.search(text)
    if not found:
        raise ReviewFileError("Dosyada “Çekilme tarihi: GG.AA.YYYY” satırı yok.")
    day, month, year = (int(part) for part in found.groups())
    fetched = timezone.make_aware(datetime(year, month, day, 12))
    reviews, current, lines = [], None, []

    def flush():
        if current is not None:
            body = "\n".join(lines).strip()
            reviews.append(ParsedReview(current["name"], current["rating"], body, current["written_at"]))

    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            rating = max(1, min(5, math.floor(float(match.group("rating")))))
            current = dict(name=match.group("name").strip(), rating=rating, written_at=_written_at(match.group("ago"), fetched))
            lines = []
        elif current is not None:
            lines.append(line)
    flush()
    if not reviews:
        raise ReviewFileError("Dosyada “### 1. Ad — ★★★★★ (5.0) — 2 yıl önce” biçiminde yorum yok.")
    return reviews


def import_reviews(course, reviews, dry_run=False):
    """Yorumları onaylı eski yorum olarak ekler; (eklenen, atlanan) döner."""
    added = skipped = 0
    with transaction.atomic():
        next_order = (course.reviews.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0) + 1
        for item in reviews:
            if course.reviews.filter(author_name=item.name, text=item.text).exists():
                skipped += 1
                continue
            review = Review.objects.create(
                course=course,
                author_name=item.name,
                rating=item.rating,
                text=item.text,
                written_at=item.written_at,
                source=ReviewSource.IMPORTED,
                sort_order=next_order,
            )
            review.approve()
            next_order += 1
            added += 1
        if dry_run:
            transaction.set_rollback(True)
    return added, skipped

"""Platformdaki fazla videolar: hiçbir derse ya da kurs tanıtımına bağlı olmayan, süren bir yüklemeye de ait olmayan
videolar (eski yüklemelerden, yarım kalan işlerden kalanlar). Stüdyoda listelenir, tek tek ya da toplu silinir; platform
panelinden toplu yüklenen videolar da buradan başlıklarına göre kursun derslerine bağlanır.

Karşılaştırma bu sunucunun veritabanıyla yapılır; başka bir veritabanına bağlı kopyada (ör. geliştirme) sonuç yanlıştır.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from course import video_service
from course.models import VIDEO_EXTENSIONS, Lesson, LessonKind, attached_video_ids, video_ids_in_use
from course.video_service import VideoServiceError

# Toplu silmede platforma aynı anda gönderilen istek sayısı
DELETE_WORKERS = 8


@dataclass
class OrphanVideo:
    video: object
    collection: str
    thumbnail_url: str
    dashboard_url: str


@dataclass
class LibraryReport:
    total: int
    in_use: int
    orphans: list = field(default_factory=list)
    # Sitede kayıtlı olup platformda bulunamayan videolar (ders/tanıtım oynamaz)
    missing: int = 0

    @property
    def orphan_size(self):
        return sum(orphan.video.size for orphan in self.orphans)


def library_report(platform):
    service = video_service.get(platform)
    videos = service.list_videos()
    collections = service.list_collections()
    in_use = video_ids_in_use(platform)
    library_ids = {video.id for video in videos}
    orphans = [
        OrphanVideo(
            video=video,
            collection=collections.get(video.collection_id, ""),
            thumbnail_url=service.thumbnail_url(video.id),
            dashboard_url=service.dashboard_url(video.id),
        )
        for video in videos
        if video.id not in in_use
    ]
    # En yeniler önce; tarihi olmayanlar sonda.
    orphans.sort(key=lambda orphan: (orphan.video.uploaded_at is not None, orphan.video.uploaded_at), reverse=True)
    return LibraryReport(
        total=len(videos),
        in_use=len(library_ids & in_use),
        orphans=orphans,
        missing=len(attached_video_ids(platform) - library_ids),
    )


def delete_orphans(platform, video_ids):
    """Verilen videoları platformdan siler; o arada bir derse bağlanmış ya da yüklemesi süren videolar atlanır.

    (silinen, atlanan, hata mesajları) döner.
    """
    service = video_service.get(platform)
    requested = set(video_ids)
    targets = requested - video_ids_in_use(platform)

    def delete(video_id):
        try:
            service.delete_video(video_id)
        except VideoServiceError as error:
            return str(error)
        return ""

    with ThreadPoolExecutor(max_workers=DELETE_WORKERS) as pool:
        errors = [error for error in pool.map(delete, sorted(targets)) if error]
    return len(targets) - len(errors), len(requested - targets), errors


def _file_name(title):
    """Platformdaki başlık dosya adı gibi eşleştirilir; uzantısız başlıkta ("React 18.x") son nokta uzantı sanılmasın."""
    return title if Path(title).suffix.lower() in VIDEO_EXTENSIONS else f"{title}.mp4"


def link_candidates(course, platform):
    """Bağlı olmayan platform videoları ve kursun dersleriyle eşleşmeleri: [(OrphanVideo, eşleşme satırı)].

    Yalnız kursun koleksiyonundaki ve koleksiyonsuz (kütüphane kökündeki) videolar; başka kursun koleksiyonundaki video
    aynı adlı derse eşleşmesin. Eşleşenler önce (ders sırasıyla), sonra eşleşmeyenler gelir. Satır
    `Course.match_video_files` biçimindedir.
    """
    collections = {"", getattr(course, video_service.get(platform).FOLDER_FIELD)}
    orphans = [orphan for orphan in library_report(platform).orphans if orphan.video.collection_id in collections]
    rows = course.match_video_files([_file_name(orphan.video.title) for orphan in orphans])
    pairs = list(zip(orphans, rows))
    pairs.sort(
        key=lambda pair: (
            pair[1]["lesson"] is None,
            (pair[1]["lesson"].section.sort_order, pair[1]["lesson"].sort_order) if pair[1]["lesson"] else (0, 0),
            pair[0].video.title,
        )
    )
    return pairs


def link_videos(course, platform, links):
    """Seçilen platform videolarını derslere bağlar; `links`: [(video kimliği, ders kimliği)].

    O arada başka yere bağlanmış ya da platformda bulunamayan video, kursa ait olmayan / video olmayan ders, aynı derse
    ikinci kez seçilen video atlanır. (bağlanan, atlanan) döner.
    """
    videos = {video.id: video for video in video_service.get(platform).list_videos()}
    in_use = video_ids_in_use(platform)
    lessons = {
        str(lesson.pk): lesson
        for lesson in Lesson.objects.filter(section__course=course, kind=LessonKind.VIDEO, pk__in=[lesson_id for _video_id, lesson_id in links])
    }
    linked, seen = 0, set()
    with transaction.atomic():
        for video_id, lesson_id in links:
            video = videos.get(video_id)
            lesson = lessons.get(lesson_id)
            if video is None or video_id in in_use or lesson is None or lesson.pk in seen:
                continue
            seen.add(lesson.pk)
            in_use.add(video_id)
            lesson.attach_video(platform, video.id, "", video.duration, video.title, file_name=video.title)
            linked += 1
    return linked, len(links) - linked

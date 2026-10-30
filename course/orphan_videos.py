"""Platformdaki fazla videolar: hiçbir derse ya da kurs tanıtımına bağlı olmayan, süren bir yüklemeye de ait olmayan
videolar (eski yüklemelerden, yarım kalan işlerden kalanlar). Stüdyoda listelenir, tek tek ya da toplu silinir.

Karşılaştırma bu sunucunun veritabanıyla yapılır; başka bir veritabanına bağlı kopyada (ör. geliştirme) sonuç yanlıştır.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from course import video_service
from course.models import attached_video_ids, video_ids_in_use
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

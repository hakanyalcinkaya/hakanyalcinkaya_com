import math
import os
import struct


def ceil_minutes(seconds):
    """Süreyi dakikaya yukarı yuvarlar: 1 dk 27 sn → 2 dk."""
    return math.ceil(seconds / 60) if seconds else 0


def clock(seconds):
    """Ders süresi gösterimi: 09:05 (dakika:saniye), bir saati aşınca 1:05:30."""
    minutes, secs = divmod(int(seconds or 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def hours_minutes(minutes):
    """Bölüm/kurs toplamı gösterimi: "2 sa 9 dk", bir saatin altında "45 dk"."""
    hours, rest = divmod(int(minutes or 0), 60)
    if hours and rest:
        return f"{hours} sa {rest} dk"
    if hours:
        return f"{hours} sa"
    return f"{rest} dk"


def video_file_seconds(path):
    """MP4/MOV/M4V dosyasının süresi (saniye); başlık bulunamazsa ya da biçim farklıysa None.

    Video servisi süreyi ancak işlemeye başlayınca bildiriyor; yükleme biter bitmez göstermek için dosyanın `moov/mvhd`
    kutusundaki süre okunur. Dosyanın tamamı okunmaz, kutular arasında atlanır.
    """
    try:
        with open(path, "rb") as file:
            file_end = os.fstat(file.fileno()).st_size
            moov = _find_box(file, b"moov", 0, file_end)
            mvhd = moov and _find_box(file, b"mvhd", moov[0], moov[0] + moov[1])
            if not mvhd:
                return None
            file.seek(mvhd[0])
            version = file.read(1)[0]
            file.seek(3 + (16 if version == 1 else 8), os.SEEK_CUR)
            timescale = struct.unpack(">I", file.read(4))[0]
            duration = struct.unpack(">Q" if version == 1 else ">I", file.read(8 if version == 1 else 4))[0]
    except (OSError, IndexError, struct.error):
        return None
    return round(duration / timescale) if timescale else None


def _find_box(file, name, start, end):
    """[start, end) aralığında adı verilen kutunun içerik başlangıcını ve boyunu döner."""
    position = start
    while position + 8 <= end:
        file.seek(position)
        size, kind = struct.unpack(">I4s", file.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", file.read(8))[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header:
            return None
        if kind == name:
            return position + header, size - header
        position += size
    return None

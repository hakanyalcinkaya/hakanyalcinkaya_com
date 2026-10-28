from django.utils.text import slugify

TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify_tr(text):
    """Türkçe harfleri Latin karşılığına çevirip slug üretir ("Işık Çalışması" → "isik-calismasi")."""
    return slugify(str(text).translate(TR_ASCII))

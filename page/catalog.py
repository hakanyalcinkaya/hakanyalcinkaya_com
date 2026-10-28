LOGIN_URL = "#"
JOIN_URL = "#"
PRIVACY_URL = "#"
TERMS_URL = "#"

NAV = (
    ("egitimler", "Kurslar"),
    ("yorumlar", "Öğrenci Yorumları"),
    ("hakkimda", "Hakkımda"),
)

_COURSES = (
    {
        "slug": "sifirdan-projelerle-front-end-ve-react-18-x-ogren",
        "title": "Sıfırdan Projelerle Front-End ve React 18.x Öğren",
        "short": "Front-End ve React 18.x",
        "description": "Front-End temellerinden React 18.x’e; sıfırdan, projelerle ilerleyen kapsamlı kurs.",
        "tags": ("Front-End", "React 18.x"),
        "duration": "52+ saat",
        "lessons": 335,
        "price": "€99.90",
        "image": "img/courses/react.jpg",
    },
    {
        "slug": "sifirdan-uctan-uca-projelerle-python-ve-django-ogren",
        "title": "Sıfırdan Uçtan Uca Projelerle Python ve Django Öğren",
        "short": "Python ve Django",
        "description": "Python ve Django ile sıfırdan başlayıp uçtan uca projeler geliştirdiğin kurs.",
        "tags": ("Python", "Django"),
        "duration": "51+ saat",
        "lessons": 327,
        "price": "€99.90",
        "image": "img/courses/django.jpg",
    },
    {
        "slug": "iki-egitmen-ile-sifirdan-python-ogren",
        "title": "İki Eğitmen ile Sıfırdan Python Öğren",
        "short": "Sıfırdan Python",
        "description": "İki eğitmenin anlatımıyla Python’a sıfırdan başlangıç.",
        "tags": ("Python", "Başlangıç"),
        "duration": "Süre: [eklenecek]",
        "lessons": 109,
        "price": "€99.90",
        "image": "img/courses/python.png",
    },
)

_REVIEWS = (
    (
        "Gülnisa",
        "Hocamızın emeğine sağlık. Anlamadığım birçok şeyi çok iyi anladım. Kurs içeriği çok güzel hazırlanmış. Hocamız her şeyi detaylıca anlatıyor ve konunun daha iyi anlaşılması için çeşitli örnek projeler yapıyor. Başka dersleri sabırsızlıkla bekliyorum",
    ),
    (
        "Ferdi S.",
        "Hakan Hocam gerçekten muazzam bilgi ve tecrübeleri ile harika bir eğitim hazırlamış. Eğitimi aldığım için çok mutluyum ve herkese tavsiye ederim.\n\nEdit: Eğitimin yarısı bitti bile ve çok eğlenceli geçiyor :)",
    ),
    (
        "Mustafa B.",
        "Dersine girdiğim en iyi Öğretmensiniz ve her bir kelimenizde ki bilgi benim için çok önemli . Totalde 52 saat ama bunun arka planında ki emeği görebiliyorum.\n\nUmarım bu bilgileri doğru bir şekilde kullanır ve sizinle paylaşma fırsatı yakalarım. Teşekürler",
    ),
    (
        "Umut K.",
        "Hakan hoca alanında gerçekten bayağı iyidir. Her eğitimini zevk alarak izleyeceğinizi düşünüyorum. İyi çalışmalar herkese :)",
    ),
    (
        "Onur I.",
        "Hakan hocamın Patika.dev deki eğitimlerinden oldukça memnun kaldığım için ve konu anlatımını kendi anlama biçimime yakın bulduğum gördüm ve bu eğitimi de ondan almaya karar verdim",
    ),
    (
        "Ahmet Fatih R.",
        "Her eğitiminde bir şeyleri öğretirken öylesine değil gerçekten öğrensinler şeklinde yaklaşımıyla, bence mükemmel üslubuyla. Kesinlikle çok kaliteli ve çok iyi bir eğitmen. Sayın Hakan Yalçınkaya benim nazarımda Hakan Yalçınkaya ve diğerleri gibi iddialı bir cümlenin karşılığı. Umarım hayatta her şey gönlünce olsun sayın Hocam. Sevgiler :)",
    ),
)


def course_catalog():
    courses = []
    for course in _COURSES:
        courses.append(
            {
                **course,
                "url": "#",
                "cart_url": "#",
                "alt": f"{course['title']} kursunun kapak görseli",
                "image_label": f"{course['title']} — kursu incele",
                "cart_label": f"{course['title']} — sepete ekle",
                "meta_line": f"{course['duration']} · {course['lessons']} ders",
                "tags_attr": "|".join(course["tags"]),
            }
        )
    return courses


def catalog_stats(courses):
    lessons = sum(course["lessons"] for course in courses)
    return {"courses": len(courses), "lessons": f"{(lessons // 10) * 10}+"}


def reviews():
    return [{"name": name, "text": text, "initial": name[0]} for name, text in _REVIEWS]

from django.urls import reverse
from django.utils import timezone

from page.catalog import JOIN_URL, LOGIN_URL, NAV, PRIVACY_URL, TERMS_URL, course_catalog


def site(request):
    index_url = reverse("index")
    return {
        "courses": course_catalog(),
        "nav_items": [
            {"id": item_id, "href": f"{index_url}#{item_id}", "label": label}
            for item_id, label in NAV
        ],
        "year": timezone.now().year,
        "login_url": LOGIN_URL,
        "join_url": JOIN_URL,
        "privacy_url": PRIVACY_URL,
        "terms_url": TERMS_URL,
    }

from django.shortcuts import render

from page.catalog import catalog_stats, course_catalog, reviews
from page.forms import NewsletterForm


def index(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        newsletter_pending = form.is_valid()
    else:
        form = NewsletterForm()
        newsletter_pending = False

    return render(
        request,
        "index.html",
        {
            "form": form,
            "newsletter_pending": newsletter_pending,
            "reviews": reviews(),
            "stats": catalog_stats(course_catalog()),
        },
    )

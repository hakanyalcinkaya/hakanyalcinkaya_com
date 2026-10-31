"""Stüdyo → Destek: talepler (durum, arama, kimden filtreleri GET parametresinde; seçilenlere toplu işlem) ve konuşma;
yanıt yazılınca müşteriye e-posta gider."""

from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_htmx.http import reswap

from studio.forms import SupportBulkForm
from studio.views import _first_error, _toast, superuser_required
from support.forms import ReplyForm
from support.models import Ticket, TicketStatus

# Listede en çok bu kadar talep gösterilir; daha eskiler arama ve filtrelerle bulunur.
LIST_LIMIT = 200

STATUS_FILTERS = (
    (TicketStatus.OPEN, "Yanıt bekleyen"),
    (TicketStatus.ANSWERED, "Yanıtlanan"),
    (TicketStatus.CLOSED, "Kapanan"),
    ("all", "Tümü"),
)
SENDER_FILTERS = {"member": ("Üye", dict(user__isnull=False)), "guest": ("Hesabı olmayan", dict(user__isnull=True))}


def _support_list_context(params):
    """Liste verisi; filtreler (durum, arama, kimden) GET'ten ya da toplu işlemde POST'tan gelir."""
    status = params.get("status", TicketStatus.OPEN)
    status = status if status in dict(STATUS_FILTERS) else TicketStatus.OPEN
    query = params.get("q", "").strip()
    sender = params.get("sender", "")
    sender = sender if sender in SENDER_FILTERS else ""
    base = Ticket.objects.search(query)
    if sender:
        base = base.filter(**SENDER_FILTERS[sender][1])
    counts = dict(base.order_by().values_list("status").annotate(total=Count("id", distinct=True)))
    filters = [
        dict(key=key, label=label, checked=key == status, count=sum(counts.values()) if key == "all" else counts.get(key, 0))
        for key, label in STATUS_FILTERS
    ]
    rows = base.select_related("user").annotate(message_count=Count("messages", distinct=True)).order_by("-last_message_at", "id")
    if status != "all":
        rows = rows.filter(status=status)
    return dict(
        tickets=rows[:LIST_LIMIT],
        total=rows.count(),
        filters=filters,
        status=status,
        query=query,
        sender=sender,
        senders=[(key, label) for key, (label, _filter) in SENDER_FILTERS.items()],
        filter_query=urlencode({key: value for key, value in (("q", query), ("sender", sender)) if value}),
    )


@superuser_required
def support_list(request):
    """Destek talepleri: filtreler GET parametresinde; HTMX isteğinde yalnız liste döner."""
    context = _support_list_context(request.GET)
    if request.htmx and not request.htmx.boosted:
        return render(request, "studio/partials/_support_list.html", context)
    return render(request, "studio/support_list.html", context)


@superuser_required
@require_POST
def support_bulk(request):
    """Seçilen taleplere toplu işlem; liste aynı filtrelerle yeniden çizilir."""
    form = SupportBulkForm(request.POST)
    if not form.is_valid():
        return _toast(reswap(HttpResponse(), "none"), "warning", _first_error(form))
    count = form.save()
    response = render(request, "studio/partials/_support_list.html", _support_list_context(request.POST))
    return _toast(response, "success", form.message(count))


@superuser_required
def support_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related("user"), pk=ticket_id)
    form = ReplyForm(request.POST if request.method == "POST" else None, label="Yanıtla")
    if form.is_valid():
        ticket.reply(request.user, form.cleaned_data["body"])
        sent_to = "panel bağlantısı" if ticket.user_id else "yanıt"
        messages.success(request, f"Yanıt gönderildi; {ticket.email} adresine {sent_to} e-postayla gidiyor.")
        return redirect(ticket.get_studio_url())
    return render(request, "studio/support_detail.html", dict(ticket=ticket, thread=ticket.messages.all(), form=form))


@superuser_required
@require_POST
def support_status(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    closed = request.POST.get("closed") == "1"
    ticket.set_closed(closed)
    messages.success(request, "Konuşma kapatıldı." if closed else "Konuşma yeniden açıldı.")
    return redirect(ticket.get_studio_url())

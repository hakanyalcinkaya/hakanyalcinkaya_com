"""Stüdyo → Destek: talepler (durum filtresi GET parametresinde) ve konuşma; yanıt yazılınca müşteriye e-posta gider."""

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from studio.views import superuser_required
from studio.views_sales import _page
from support.forms import ReplyForm
from support.models import Ticket, TicketStatus

STATUS_FILTERS = (
    (TicketStatus.OPEN, "Yanıt bekleyen"),
    (TicketStatus.ANSWERED, "Yanıtlanan"),
    (TicketStatus.CLOSED, "Kapanan"),
    ("all", "Tümü"),
)


@superuser_required
def support_list(request):
    status = request.GET.get("status", TicketStatus.OPEN)
    if status not in dict(STATUS_FILTERS):
        status = TicketStatus.OPEN
    counts = dict(Ticket.objects.values_list("status").annotate(total=Count("id")).order_by())
    filters = [
        dict(key=key, label=label, checked=key == status, count=sum(counts.values()) if key == "all" else counts.get(key, 0))
        for key, label in STATUS_FILTERS
    ]
    rows = Ticket.objects.select_related("user").annotate(message_count=Count("messages")).order_by("-last_message_at", "id")
    if status != "all":
        rows = rows.filter(status=status)
    return render(request, "studio/support_list.html", dict(page=_page(request, rows), filters=filters))


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

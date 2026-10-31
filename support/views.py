"""Destek: herkes için talep formu (/support/); üye taleplerini listeler, konuşmayı açıp yanıtlar."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from ipware import get_client_ip

from support import turnstile
from support.forms import GuestTicketForm, ReplyForm, TicketForm
from support.models import Ticket


def support(request):
    """Üye: yeni talep formu (konu, mesaj) ve kendi talepleri. Ziyaretçi: ad, e-posta, konu, mesaj ve bot doğrulaması."""
    data = request.POST if request.method == "POST" else None
    member = request.user.is_authenticated
    form = TicketForm(data) if member else GuestTicketForm(data, remote_ip=get_client_ip(request)[0] or "")
    if form.is_valid():
        ticket = form.save(request.user if member else None)
        if member:
            messages.success(request, "Mesajın gönderildi. Yanıt gelince burada ve e-postanda haber vereceğiz.")
            return redirect(ticket)
        return redirect("support:sent")
    tickets = Ticket.objects.for_user(request.user).annotate(message_count=Count("messages"))
    context = dict(form=form, tickets=tickets, turnstile=not member and turnstile.is_enabled())
    return render(request, "support/index.html", context)


def sent(request):
    return render(request, "support/sent.html")


@login_required
def ticket_detail(request, ticket_id):
    """Üyenin konuşması; açılınca yanıt okunmuş sayılır. Yanıt yazılınca (kapalı talep de) yeniden yanıt bekler."""
    ticket = get_object_or_404(Ticket.objects.for_user(request.user), pk=ticket_id)
    form = ReplyForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        ticket.add_customer_message(form.cleaned_data["body"])
        messages.success(request, "Yanıtın gönderildi.")
        return redirect(ticket)
    ticket.mark_read()
    context = dict(ticket=ticket, thread=ticket.messages.all(), form=form)
    return render(request, "support/ticket_detail.html", context)

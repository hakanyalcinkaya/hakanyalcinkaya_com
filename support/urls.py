from django.urls import path

from support import views

app_name = "support"

urlpatterns = [
    path("", views.support, name="support"),
    path("sent/", views.sent, name="sent"),
    path("<uuid:ticket_id>/", views.ticket_detail, name="ticket_detail"),
]

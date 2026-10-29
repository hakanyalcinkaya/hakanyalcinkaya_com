from django.urls import path

from mailing import views

app_name = "mailing"

urlpatterns = [
    path("o/<uuid:token>.gif", views.email_open, name="open"),
    path("c/<uuid:token>/", views.email_click, name="click"),
]

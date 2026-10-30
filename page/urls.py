from django.urls import path
from django.views.generic import RedirectView

from page import views

app_name = "page"

urlpatterns = [
    path("", views.index, name="index"),
    path("courses/", views.course_list, name="course_list"),
    path("cart/", views.cart, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("thanks/", views.thanks, name="thanks"),
    path("my-courses/", views.library, name="library"),
    # Eski Kurslarım adresleri (Podia'daki /p/products/library/ ve kısa süre kullanılan /library/): kalıcı yönlenir,
    # sorgu parametreleri korunur.
    path("library/", RedirectView.as_view(pattern_name="page:library", permanent=True, query_string=True)),
    path("p/products/library/", RedirectView.as_view(pattern_name="page:library", permanent=True, query_string=True)),
    # Eski platform (Podia) ders adresi: yeni adrese kalıcı yönlenir.
    path(
        "p/courses/<slug:course_slug>/<slug:section_slug>/<slug:lesson_slug>/",
        views.legacy_lesson,
        name="legacy_lesson",
    ),
    path("lessons/<uuid:lesson_id>/favorite/", views.lesson_favorite, name="lesson_favorite"),
    path("lessons/<uuid:lesson_id>/complete/", views.lesson_complete, name="lesson_complete"),
    path("courses/<slug:slug>/review/", views.course_review, name="course_review"),
    path("courses/<slug:slug>/reviews/", views.course_reviews, name="course_reviews"),
    path("reviews/", views.all_reviews, name="all_reviews"),
    path("account/login/", views.login, name="login"),
    path("account/signup/", views.signup, name="signup"),
    path("account/logout/", views.logout, name="logout"),
    path("account/password-reset/", views.password_reset, name="password_reset"),
    path("account/password-reset/sent/", views.password_reset_sent, name="password_reset_sent"),
    path("account/password-reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("account/settings/", views.account_settings, name="account_settings"),
    path("account/player-preferences/", views.player_preferences, name="player_preferences"),
    path("newsletter/confirm/", views.newsletter_confirm, name="newsletter_confirm"),
    path("newsletter/confirm/<uuid:token>/", views.newsletter_activate, name="newsletter_activate"),
    path("newsletter/resend/", views.newsletter_resend, name="newsletter_resend"),
    path("newsletter/unsubscribe/<uuid:token>/", views.newsletter_unsubscribe_link, name="newsletter_unsubscribe_link"),
    path("newsletter/manage/<uuid:token>/", views.newsletter_manage, name="newsletter_manage"),
    path("newsletter/confirmed/", views.newsletter_confirmed, name="newsletter_confirmed"),
    path("newsletter/unsubscribe/", views.newsletter_unsubscribe, name="newsletter_unsubscribe"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("cookies/", views.cookies, name="cookies"),
    path("<slug:slug>/add-to-cart/", views.add_to_cart, name="add_to_cart"),
    path("<slug:slug>/remove-from-cart/", views.remove_from_cart, name="remove_from_cart"),
    path("<slug:slug>/buy/", views.buy, name="buy"),
    path("<slug:slug>/", views.course_detail, name="course_detail"),
    path("<slug:course_slug>/<slug:section_slug>/<slug:lesson_slug>/", views.lesson, name="lesson"),
]

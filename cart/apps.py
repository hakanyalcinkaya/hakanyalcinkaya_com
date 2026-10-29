from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CartConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cart"
    verbose_name = _("Sepetler")

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from cart.request_cart import merge_guest_cart

        user_logged_in.connect(merge_guest_cart, dispatch_uid="cart_merge_guest_cart")

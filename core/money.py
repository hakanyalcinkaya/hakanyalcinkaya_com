from decimal import ROUND_HALF_UP, Decimal

CURRENCY_SYMBOL = "₺"


def format_try(amount):
    """Türk lirası, Türkçe biçim: ₺1.499,90 (kuruş yoksa ₺1.499)."""
    if amount is None:
        return ""
    value = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = f"{value:,.2f}".split(".")
    whole = whole.replace(",", ".")
    return f"{CURRENCY_SYMBOL}{whole}" if cents == "00" else f"{CURRENCY_SYMBOL}{whole},{cents}"


CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def format_money(amount, currency="TRY"):
    """Para birimine göre Türkçe biçim: ₺1.499,90 ya da 14,99 €."""
    if currency == "TRY":
        return format_try(amount)
    if amount is None:
        return ""
    value = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = f"{value:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents} {CURRENCY_SYMBOLS.get(currency, currency)}"

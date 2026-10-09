"""Bale messenger bot payments (Telegram-compatible Bot API at tapi.bale.ai).

Flow: the buyer opens the bot via a deep link carrying the order token, the bot
sends an invoice (card-to-card into `bale_provider_token`), Bale confirms the
payment with a `successful_payment` message and the order is marked paid.
"""

import logging
import re

import requests

from apps.siteconfig.models import SiteSettings

from . import services
from .models import Order

logger = logging.getLogger(__name__)

API_BASE = "https://tapi.bale.ai/bot{token}/{method}"
_TOKEN_RE = re.compile(r"\b([0-9a-f]{32})\b")
_NUMBER_RE = re.compile(r"\b(\d{4,8})\b")


class BaleError(Exception):
    pass


def call(method: str, payload: dict) -> dict:
    config = SiteSettings.load()
    if not config.bale_bot_token:
        raise BaleError("توکن ربات بله تنظیم نشده است.")
    try:
        response = requests.post(
            API_BASE.format(token=config.bale_bot_token, method=method), json=payload, timeout=10
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        # `from None`: the exception text contains the request URL, i.e. the bot token.
        raise BaleError(f"ارتباط با سرور بله برقرار نشد ({type(exc).__name__}).") from None
    if not data.get("ok"):
        raise BaleError(data.get("description") or f"HTTP {response.status_code}")
    return data.get("result") or {}


def set_webhook(url: str) -> None:
    call("setWebhook", {"url": url})


def deep_link(order: Order) -> str:
    username = SiteSettings.load().bale_bot_username.lstrip("@")
    return f"https://ble.ir/{username}?start={order.token.hex}"


def send_message(chat_id, text: str) -> None:
    try:
        call("sendMessage", {"chat_id": chat_id, "text": text})
    except BaleError as exc:
        logger.warning("Bale sendMessage failed: %s", exc)


def send_invoice(chat_id, order: Order) -> None:
    config = SiteSettings.load()
    call(
        "sendInvoice",
        {
            "chat_id": chat_id,
            "title": order.title[:32],
            "description": f"سفارش {order.number} — {order.title}"[:255],
            "payload": order.token.hex,
            "provider_token": config.bale_provider_token,
            "currency": "IRR",
            "prices": [{"label": order.title[:32], "amount": order.amount_rial}],
        },
    )


def _send_card_instructions(chat_id, order: Order) -> None:
    config = SiteSettings.load()
    lines = [
        f"📋 سفارش {order.number}",
        f"📦 {order.title}",
        f"💰 مبلغ: {order.total:,} تومان",
        "",
    ]
    if config.card_number:
        lines += [
            "لطفاً مبلغ را به کارت زیر واریز کنید:",
            f"💳 {config.card_number}",
        ]
        if config.card_holder:
            lines.append(f"به نام: {config.card_holder}")
        if config.card_bank:
            lines.append(f"بانک: {config.card_bank}")
        lines += [
            "",
            "پس از واریز، تصویر رسید را در صفحه سفارش سایت آپلود کنید تا تأیید شود.",
        ]
    else:
        lines.append("برای پرداخت به سایت برگردید و از روش کارت‌به‌کارت استفاده کنید.")
    send_message(chat_id, "\n".join(lines))


def _find_order_in_text(text: str) -> Order | None:
    if match := _TOKEN_RE.search(text):
        return Order.objects.filter(token=match.group(1)).first()
    if match := _NUMBER_RE.search(text):
        return Order.objects.filter(number=match.group(1)).first()
    return None


def _order_from_payload(payload: str | None) -> Order | None:
    if payload and _TOKEN_RE.fullmatch(payload):
        return Order.objects.filter(token=payload).first()
    return None


_DEFAULT_WELCOME = (
    "سلام! 👋\n\n"
    "این ربات فقط برای پرداخت سفارش‌های سایت استفاده می‌شود.\n\n"
    "برای پرداخت:\n"
    "۱. از سایت وارد صفحه سفارش شوید\n"
    "۲. روی «پرداخت با بله» بزنید\n"
    "۳. ربات فاکتور پرداخت را برای شما می‌فرستد\n\n"
    "همچنین می‌توانید شماره سفارش خود را اینجا بفرستید."
)


def _handle_text(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # Plain /start (no token) → welcome message
    if text.strip() in ("/start", "/start@" + (SiteSettings.load().bale_bot_username or "")):
        config = SiteSettings.load()
        welcome = config.bale_welcome_message.strip() or _DEFAULT_WELCOME
        send_message(chat_id, welcome)
        return

    order = _find_order_in_text(text)
    if order is None:
        # Unknown message — bot is payment-only, do not engage
        send_message(
            chat_id,
            "این ربات فقط برای پرداخت سفارش است.\n"
            "شماره سفارش خود را بفرستید یا از سایت روی «پرداخت با بله» بزنید.",
        )
        return
    if order.is_paid:
        send_message(chat_id, f"سفارش {order.number} قبلاً پرداخت شده است. ✅")
        return
    if not order.can_pay:
        send_message(chat_id, f"سفارش {order.number} قابل پرداخت نیست.")
        return
    order.bale_chat_id = str(chat_id)
    order.save(update_fields=["bale_chat_id", "updated_at"])
    config = SiteSettings.load()
    if config.bale_provider_token:
        try:
            send_invoice(chat_id, order)
            return
        except BaleError as exc:
            logger.warning("send_invoice failed for order %s: %s", order.number, exc)
    # No provider_token or invoice failed → send card-to-card instructions directly
    _send_card_instructions(chat_id, order)


def _handle_pre_checkout(query: dict) -> None:
    order = _order_from_payload(query.get("invoice_payload") or query.get("payload"))
    ok = bool(order and order.can_pay)
    total = query.get("total_amount")
    if ok and total is not None and int(total) != order.amount_rial:
        ok = False
    payload = {"pre_checkout_query_id": query["id"], "ok": ok}
    if not ok:
        payload["error_message"] = "این سفارش دیگر قابل پرداخت نیست."
    call("answerPreCheckoutQuery", payload)


def _handle_successful_payment(message: dict) -> None:
    payment = message["successful_payment"]
    order = _order_from_payload(payment.get("invoice_payload") or payment.get("payload"))
    chat_id = message["chat"]["id"]
    if order is None:
        logger.error("Bale payment for unknown order: %s", payment)
        return
    total = payment.get("total_amount")
    if total is not None and int(total) != order.amount_rial:
        logger.error("Bale payment amount mismatch for order %s: %s", order.number, payment)
        order.admin_note = f"مغایرت مبلغ پرداخت بله: {total} ریال"
        order.save(update_fields=["admin_note", "updated_at"])
        send_message(chat_id, "مبلغ پرداختی با سفارش مغایرت دارد؛ لطفاً با پشتیبانی تماس بگیرید.")
        return
    ref = (
        payment.get("provider_payment_charge_id") or payment.get("telegram_payment_charge_id") or ""
    )
    if services.mark_paid(order, Order.Method.BALE, ref=str(ref)):
        send_message(
            chat_id, f"پرداخت سفارش {order.number} با موفقیت انجام شد ✅\nبه سایت برگردید."
        )


def handle_update(update: dict) -> None:
    try:
        if "pre_checkout_query" in update:
            _handle_pre_checkout(update["pre_checkout_query"])
            return
        message = update.get("message") or {}
        if "successful_payment" in message:
            _handle_successful_payment(message)
        elif "text" in message and "chat" in message:
            _handle_text(message)
    except BaleError as exc:
        logger.warning("Bale API call failed while handling update: %s", exc)

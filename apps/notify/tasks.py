"""SMS notifications sent in the background through sms.ir templates."""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.accounts.sms import SMSError, send_template
from apps.core.templatetags.fa import jdate
from apps.siteconfig.models import SiteSettings

logger = logging.getLogger(__name__)

DAY_BEFORE = timedelta(hours=24)
HOUR_BEFORE = timedelta(hours=1)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_sms(self, phone: str, template_field: str, params: dict) -> None:
    """`template_field` names the SiteSettings field holding the template id; an
    empty field means the admin turned this notification off."""
    template_id = getattr(SiteSettings.load(), template_field)
    if not template_id:
        return
    try:
        send_template(phone, template_id, params)
    except SMSError as exc:
        raise self.retry(exc=exc) from None


def _send_after_commit(phone, template_field, params):
    transaction.on_commit(lambda: send_sms.delay(phone, template_field, params))


def order_paid(order) -> None:
    _send_after_commit(
        order.user.phone, "sms_paid_template_id", {"ORDER": order.number, "TITLE": order.title}
    )


def question_answered(question) -> None:
    _send_after_commit(
        question.user.phone, "sms_answer_template_id", {"TITLE": question.lesson.title}
    )


def receipt_rejected(order) -> None:
    _send_after_commit(order.user.phone, "sms_rejected_template_id", {"ORDER": order.number})


@shared_task
def send_live_reminders() -> int:
    """Runs every few minutes (Celery beat). Each reminder is claimed atomically so
    it is sent once even if two runs overlap. Returns the number of SMS queued."""
    from apps.live.models import LiveSession

    now = timezone.now()
    windows = [
        # (field, starts after, starts before)
        ("reminder_day_sent_at", now + HOUR_BEFORE, now + DAY_BEFORE),
        ("reminder_hour_sent_at", now, now + HOUR_BEFORE),
    ]
    queued = 0
    for field, after, before in windows:
        sessions = LiveSession.objects.filter(
            **{f"{field}__isnull": True},
            starts_at__gt=after,
            starts_at__lte=before,
            live_class__is_published=True,
        ).select_related("live_class")
        for session in sessions:
            claimed = LiveSession.objects.filter(
                pk=session.pk, **{f"{field}__isnull": True}
            ).update(**{field: now})
            if not claimed:
                continue
            params = {
                "TITLE": session.live_class.title,
                "TIME": jdate(session.starts_at, "%Y/%m/%d %H:%M"),
            }
            for registration in session.live_class.registrations.select_related("user"):
                send_sms.delay(registration.user.phone, "sms_reminder_template_id", params)
                queued += 1
    return queued

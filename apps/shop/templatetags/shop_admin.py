from django import template

from apps.shop.models import Order

register = template.Library()


@register.simple_tag
def pending_receipts():
    return Order.objects.filter(status=Order.Status.AWAITING_REVIEW).count()


@register.simple_tag
def unanswered_questions():
    from apps.qa.models import Question

    return Question.objects.filter(answer="", is_hidden=False).count()

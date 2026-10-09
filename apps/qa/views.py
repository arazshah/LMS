from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Lesson

from .forms import QuestionForm

DAILY_LIMIT = 10


def can_ask(user, lesson) -> bool:
    """Only students with access to the course (and the admin) take part in Q&A."""
    return user.is_authenticated and lesson.course.has_access(user)


@login_required
@require_POST
def ask(request, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.select_related("chapter__course"), pk=lesson_id, is_published=True
    )
    if not can_ask(request.user, lesson):
        raise Http404
    target = f"{lesson.get_absolute_url()}#questions"
    since = timezone.now() - timedelta(days=1)
    if request.user.questions.filter(created_at__gte=since).count() >= DAILY_LIMIT:
        messages.error(request, "تعداد سوال‌های امروز شما به حد مجاز رسیده است.")
        return redirect(target)
    form = QuestionForm(request.POST)
    if form.is_valid():
        question = form.save(commit=False)
        question.lesson = lesson
        question.user = request.user
        question.save()
        messages.success(request, "سوال شما ثبت شد؛ پس از پاسخ، پیامک دریافت می‌کنید.")
    else:
        messages.error(request, "متن سوال را وارد کنید.")
    return redirect(target)

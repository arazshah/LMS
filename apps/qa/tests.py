from unittest import mock

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Category, Chapter, Course, Enrollment, Lesson
from apps.siteconfig.models import SiteSettings

from .models import Question
from .views import DAILY_LIMIT


@pytest.fixture
def lesson(db):
    course = Course.objects.create(
        category=Category.objects.create(title="GeoAI"), title="دوره", price=100, is_published=True
    )
    chapter = Chapter.objects.create(course=course, title="فصل")
    return Lesson.objects.create(chapter=chapter, title="جلسه اول", is_free=True)


@pytest.fixture
def student(lesson):
    user = User.objects.create_user("09121111111", first_name="سارا")
    Enrollment.objects.create(user=user, course=lesson.course)
    return user


def ask(client, lesson, body="چطور داده را برچسب بزنم؟"):
    return client.post(reverse("qa:ask", args=[lesson.pk]), {"body": body})


def test_enrolled_student_can_ask_and_classmates_see_it(client, lesson, student):
    client.force_login(student)
    response = ask(client, lesson)
    assert response.url.endswith("#questions")
    question = Question.objects.get()
    assert question.user == student and question.lesson == lesson

    classmate = User.objects.create_user("09122222222")
    Enrollment.objects.create(user=classmate, course=lesson.course)
    client.force_login(classmate)
    body = client.get(lesson.get_absolute_url()).content.decode()
    assert "چطور داده را برچسب بزنم؟" in body and "سارا" in body
    assert "09121111111" not in body  # phone numbers are never shown to other students


def test_non_students_cannot_ask_or_read(client, lesson, student):
    client.force_login(student)
    ask(client, lesson)
    outsider = User.objects.create_user("09123333333")
    client.force_login(outsider)
    # The lesson is a free preview, but Q&A is for the course's students only.
    body = client.get(lesson.get_absolute_url()).content.decode()
    assert "چطور داده را برچسب بزنم؟" not in body and 'id="questions"' not in body
    assert ask(client, lesson).status_code == 404
    client.logout()
    assert ask(client, lesson).status_code == 302  # login required


def test_hidden_questions_are_not_shown(client, lesson, student):
    client.force_login(student)
    ask(client, lesson, "سوال نامناسب")
    Question.objects.update(is_hidden=True)
    assert "سوال نامناسب" not in client.get(lesson.get_absolute_url()).content.decode()


def test_empty_question_rejected_and_daily_limit(client, lesson, student):
    client.force_login(student)
    ask(client, lesson, "   ")
    assert not Question.objects.exists()
    for i in range(DAILY_LIMIT):
        ask(client, lesson, f"سوال {i}")
    ask(client, lesson, "یکی بیشتر")
    assert Question.objects.count() == DAILY_LIMIT


def test_admin_answer_sends_sms_once(client, lesson, student, django_capture_on_commit_callbacks):
    config = SiteSettings.load()
    config.sms_api_key = "KEY"
    config.sms_answer_template_id = 21
    config.save()
    question = Question.objects.create(lesson=lesson, user=student, body="سوال")
    admin = User.objects.create_superuser("09120000001", "pass-12345")
    client.force_login(admin)
    index = client.get(reverse("admin:index")).content.decode()
    assert "1 سوال بی‌پاسخ" in index

    url = reverse("admin:qa_question_change", args=[question.pk])
    sent = []
    with mock.patch("apps.notify.tasks.send_template", side_effect=lambda *a: sent.append(a)):
        with django_capture_on_commit_callbacks(execute=True):
            client.post(url, {"answer": "با QGIS", "is_hidden": ""})
        with django_capture_on_commit_callbacks(execute=True):
            client.post(url, {"answer": "با QGIS (ویرایش‌شده)", "is_hidden": ""})
    question.refresh_from_db()
    assert question.is_answered and question.answered_at
    assert sent == [("09121111111", 21, {"TITLE": "جلسه اول"})]

    client.force_login(student)
    body = client.get(lesson.get_absolute_url()).content.decode()
    assert "پاسخ مدرس" in body and "ویرایش‌شده" in body

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import LessonVideo


@receiver(post_delete, sender=LessonVideo)
def remove_video_files(sender, instance, **kwargs):
    instance.delete_files()

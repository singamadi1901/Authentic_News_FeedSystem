from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Article
from .tasks import send_news_alert_task

@receiver(post_save, sender=Article)
def send_news_alert_on_save(sender, instance, created, **kwargs):
    """
    Sends an email to all subscribed users when a new verified article is created.
    """
    # Only run if a new article was created and it is verified
    if created and instance.is_verified:
        # In a real-world app, this would be an asynchronous task (e.g., Celery).
        # For this project, we'll call the task function directly.
        send_news_alert_task(instance.id)



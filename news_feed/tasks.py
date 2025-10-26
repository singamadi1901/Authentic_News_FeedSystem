# news_feed/tasks.py
# In a production environment, this would be a Celery task.
# For this project, it's a placeholder function.
from news_feed.models import Article
from .models import UserSubscription
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

def send_news_alert_task(article_id):
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return

    subject = f"New Verified News: {article.title}"
    subscribed_users = UserSubscription.objects.filter(is_subscribed=True)
    recipient_list = [sub.user.email for sub in subscribed_users]

    if recipient_list:
        html_message = render_to_string('news_feed/email/news_alert.html', {'article': article})
        plain_message = f"Read more here: {article.source_url}"
        
        try:
            send_mail(
                subject,
                plain_message,
                settings.EMAIL_HOST_USER,
                recipient_list,
                html_message=html_message,
                fail_silently=False,
            )
            print(f"Sent news alert for '{article.title}' to {len(recipient_list)} users.")
        except Exception as e:
            print(f"Error sending email: {e}")


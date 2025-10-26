# Register your models here.
from django.contrib import admin
from .models import Article, UserSubscription, Feedback

admin.site.register(Article)
admin.site.register(UserSubscription)
admin.site.register(Feedback)

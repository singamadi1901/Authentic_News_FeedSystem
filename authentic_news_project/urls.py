"""
URL configuration for authentic_news_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

# authentic_news_project/urls.py
from django.contrib import admin
from django.urls import path, include

from django.contrib import admin
from django.urls import path, include
from news_feed import views as news_feed_views
from django.contrib.auth import views as auth_views


urlpatterns = [
    path('admin/', admin.site.urls),
    # Set the new landing_page as the root URL
    path('', news_feed_views.landing_page, name='landing_page'),
    # Include all the URLs from your news_feed app
    path('news/', include('news_feed.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/add-article/', news_feed_views.add_article_api, name='add_article_api'),
    
]



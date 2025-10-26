from django.urls import path
from . import views

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from news_feed import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('home/', views.homepage, name='homepage'),
    path("category/<slug:category>/", views.categorized_news, name="categorized_news"),
    path('search/', views.search_results, name='search_results'),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('weather/', views.weather_report, name='weather_report'),
    path('report_misinformation/', views.report_misinformation, name='report_misinformation'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='landing_page'), name='logout'),
    path('api/add-article/', views.add_article_api, name='add_article_api'),
    
]   
handler404 = 'news_feed.views.handler404'                               
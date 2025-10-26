from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Article, UserSubscription, Feedback
from django.db.models import Q
from datetime import datetime
import calendar
import requests
from urllib.parse import urlparse
from django.http import JsonResponse
from .forms import SignUpForm
from django.contrib.auth import login
from django.utils import timezone
import subprocess
import sys
import json
from datetime import datetime, timedelta
from django.views.decorators.csrf import csrf_exempt


CATEGORY_LIST = [
    "India", "World", "Local", "Business",
    "Technology", "Sports", "Health",
]
TOP_SOURCES = {'The Hindu','NDTV','Al Jazeera','Times of India'}

CATEGORY_FOR_YOU = "For You"
CATEGORY_SHOWCASE = "News Showcase"

RECENT = timezone.now() - timedelta(days=3)

def _recent(qs, minimum=30):
    qs_recent = qs.filter(publication_date__gte=RECENT)
    return qs_recent if qs_recent.count() >= minimum else qs[:minimum]

@csrf_exempt # Important: This is for API endpoints
def add_article_api(request):
    if request.method == 'POST':
        try:
            # Load the JSON data sent by n8n
            data = json.loads(request.body)

            # Create a new Article object
            new_article = Article.objects.create(
                title=data.get('title'),
                summary=data.get('summary'),
                category=data.get('category'),
                source_url=data.get('source_url'),
                credibility_score=int(data.get('credibility_score') or 0),
                source_name=data.get('source_name'),
                is_verified=True # Mark as verified
            )
            
            # Return a success message
            return JsonResponse({'status': 'success', 'message': f'Article "{new_article.title}" created successfully.'})
        
        except Exception as e:
            # Return an error message if something goes wrong
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
    if request.method == 'GET':
        try:
            # 1. Fetch all verified articles from the database, ordered by newest first.
            articles = Article.objects.filter(is_verified=True).order_by('-publication_date')
            
            # 2. Convert the Django objects into a list of dictionaries that can be turned into JSON.
            # We use .values() for efficiency.
            data = list(articles.values(
                'title', 
                'summary', 
                'category', 
                'source_url', 
                'publication_date',
                'credibility_score',
                'source_name'
            ))
            
            # 3. Return the list of articles as a JSON response.
            # `safe=False` is required to allow returning a list of objects.
            return JsonResponse(data, safe=False)
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # If the request method is not POST, return an error
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def get_weather_context(request):
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    api_key = '4723e60bee924b14862145249250509'
    days = 3
    
    location_query = f"{lat},{lon}" if lat and lon else "Nellore"
    url = f"https://api.weatherapi.com/v1/forecast.json?key={api_key}&q={location_query}&days={days}"

    temperature = condition = icon = city = 'N/A'
    forecast_days = []
    
    try:
        response = requests.get(url)
        if response.status_code == 200 and response.text.strip():
            weather_data = response.json()
            temperature = weather_data.get('current', {}).get('temp_c', 'N/A')
            condition = weather_data.get('current', {}).get('condition', {}).get('text', 'N/A')
            icon = weather_data.get('current', {}).get('condition', {}).get('icon', '')
            city = weather_data.get('location', {}).get('name', location_query)
            for day in weather_data.get('forecast', {}).get('forecastday', []):
                forecast_days.append({
                    'date': datetime.strptime(day['date'], "%Y-%m-%d").strftime('%a'),
                    'max_temp': int(day['day']['maxtemp_c']),
                    'min_temp': int(day['day']['mintemp_c']),
                    'icon': day['day']['condition']['icon'],
                })
    except Exception as e:
        print("Weather fetch error:", e)

    return {
        'city': city,
        'temperature': temperature,
        'condition': condition,
        'icon': icon,
        'forecast_days': forecast_days,
    }

def home_queryset():
     return Article.objects.filter(is_verified=True) \
        .exclude(publication_date__isnull=True) \
        .exclude(category__iexact='Local') \
        .order_by("-publication_date")

def user_preferred_categories(user):
    # Replace this with real preference storage when available
    # For now, return None to use the blended fallback for anonymous users
    return None
def for_you_queryset():
    base = list(Article.objects.filter(is_verified=True).exclude(publication_date__isnull=True).order_by("-publication_date")[:120])
    base.reverse()  # reverse of Home order
    # Light shuffle inside windows for a jumbled feel
    from random import shuffle
    WINDOW = 10
    jumbled = []
    for i in range(0, len(base), WINDOW):
        chunk = base[i:i+WINDOW]
        shuffle(chunk)
        jumbled.extend(chunk)
    return jumbled
def showcase_queryset():
    WINDOW_HRS = 24
    since = timezone.now() - timedelta(hours=WINDOW_HRS)
    recent_verified = Article.objects.filter(
        is_verified=True,
        verified_at__gte=since
    ).order_by("-verified_at", "-publication_date")

    if recent_verified.exists():
        # Optionally prefer top sources first within the recent set
        top = recent_verified.filter(source_name__in=TOP_SOURCES)[:50]
        return top if top else recent_verified[:50]
    qs = Article.objects.filter(is_verified=True).order_by("-verified_at", "-publication_date")
    # Prefer top sources when available, else fallback to all verified
    top = qs.filter(source_name__in=TOP_SOURCES)[:50]
    return top if top else qs[:50]

# news_feed/views.py

def landing_page(request):
    # If the user is already logged in, redirect them straight to the news feed.
    if request.user.is_authenticated:
        return redirect('homepage')
    # Otherwise, show them the new landing page.
    return render(request, 'news_feed/landing.html')


def signup_view(request):
    # If the request is a POST, it means the form has been submitted.
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        # Check if the form data is valid.
        if form.is_valid():
            user = form.save()  # Save the new user to the database.
            login(request, user)  # Log the user in immediately after signup.
            return redirect('homepage')  # Redirect to the main news feed.
    # If it's a GET request, just display a blank signup form.
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

def trigger_news_fetch_if_needed():
    """
    Checks if the news fetch command should be run and triggers it in the background.
    This prevents running the fetch on every single page load.
    """
    try:
        # Use a simple file to store the timestamp of the last run
        with open("last_fetch_run.tmp", "r") as f:
            last_run = datetime.fromisoformat(f.read())
    except (FileNotFoundError, ValueError):
        last_run = datetime.min

    # --- Run the fetch if more than 30 minutes have passed ---
    if datetime.now() - last_run > timedelta(minutes=30):
        print("Triggering background news fetch...")
        # Run the management command in a non-blocking background process
        subprocess.Popen([sys.executable, "manage.py", "fetch_and_verify_news"])
        
        # Update the timestamp file
        with open("last_fetch_run.tmp", "w") as f:
            f.write(datetime.now().isoformat())
# --- END OF ADDED FUNCTION ---

def homepage(request, category=None):
    trigger_news_fetch_if_needed()  
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    api_key = '4723e60bee924b14862145249250509'
    days = 3 
    show_subscription_popup = False
    categories = get_category_list() if "get_category_list" in globals() else []
    if lat and lon:
        location_query = f"{lat},{lon}"
    else:
        # Default location (your choice)
        location_query = "Avadi"
    
    url = f"https://api.weatherapi.com/v1/forecast.json?key={api_key}&q={location_query}&days={days}"

    temperature = condition = icon = 'N/A'
    forecast_days = []
    try:
        response = requests.get(url)
        # Always check response validity before .json()
        if response.status_code == 200 and response.text.strip():
            weather_data = response.json()
            temperature = weather_data.get('current', {}).get('temp_c', 'N/A')
            condition = weather_data.get('current', {}).get('condition', {}).get('text', 'N/A')
            icon = weather_data.get('current', {}).get('condition', {}).get('icon', '')
            city = weather_data.get('location', {}).get('name', location_query)
            for day in weather_data.get('forecast', {}).get('forecastday', []):
                forecast_days.append({
                    'date': datetime.strptime(day['date'], "%Y-%m-%d").strftime('%a'),  # e.g. "Sat"
                    'max_temp': int(day['day']['maxtemp_c']),
                    'min_temp': int(day['day']['mintemp_c']),
                    'icon': day['day']['condition']['icon'],
                })
            else:
                print("Weather API error:", response.text)
    except Exception as e:
        print("Weather fetch error:", e)
    
    if request.user.is_authenticated:
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            if not subscription.is_subscribed:
                show_subscription_popup = True
        except UserSubscription.DoesNotExist:
            show_subscription_popup = True

    articles = (Article.objects.filter(is_verified=True)
                         .exclude(category__iexact="Local")
                         .order_by("-publication_date")[:120])

    
    if category:
        articles = Article.objects.filter(is_verified=True, category__iexact=category).order_by('-publication_date')
    else:
        articles = Article.objects.filter(is_verified=True).exclude(category__iexact='Local').order_by('-publication_date')

    context = {
        'articles': articles,
        'show_subscription_popup': show_subscription_popup,
        'categories': get_category_list(),
        'city': city,
        'category': None,
        'temperature': temperature,
        'condition': condition,
        'icon': icon,
        'forecast_days': forecast_days, 
    }
    return render(request, 'news_feed/homepage.html', context)

def search_results(request):
    query = request.GET.get('q')
    if query:
        results = Article.objects.filter(Q(title__icontains=query) | Q(summary__icontains=query), is_verified=True).order_by('-publication_date')
    else:
        results = Article.objects.filter(is_verified=True).order_by('-publication_date')
    
    context = {
        'articles': results,
        'query': query,
    }   
    return render(request, 'news_feed/search_results.html', context)

@login_required
def subscribe(request):
    if request.method == 'POST':
        subscription, created = UserSubscription.objects.get_or_create(user=request.user)
        subscription.is_subscribed = True
        subscription.save()
        return redirect('homepage')
    return redirect('homepage')
def get_category_list():
    qs = (Article.objects
          .filter(is_verified=True)
          .exclude(category__isnull=True)
          .exclude(category__exact='')
          .exclude(category__iexact='General')  
          .values_list('category', flat=True)
          .distinct())
    cats = sorted([c for c in qs if c])  # remove Nones/empties
    # Optionally prepend a curated set for order
    have = sorted(c.strip() for c in qs if c and c.strip())
    have = [c for c in have if c not in {CATEGORY_FOR_YOU, CATEGORY_SHOWCASE,'General'}]
    preferred = ["India", "World", "Local", "Business",
                 "Technology", "Entertainment", "Sports", "Science", "Health"]
    ordered = [c for c in preferred if c in have]
    rest = [c for c in have if c not in set(ordered)]
    return ordered + rest
    #return preferred + rest

def weather_report(request):
    date = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
    api_key = '4723e60bee924b14862145249250509'
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    city = None
    if lat and lon:
        
        url = f"https://api.weatherapi.com/v1/current.json?key={api_key}&q={lat},{lon}"
    else:
        city = request.GET.get('city', 'London')
        url = f"https://api.weatherapi.com/v1/current.json?key=4723e60bee924b14862145249250509&q=London&aqi=no"
    
    weather_data = {}
    try:
        response = requests.get(url)
        weather_data = response.json()
        temperature = weather_data.get('current', {}).get('temp_c', 'N/A')
        condition = weather_data.get('current', {}).get('condition', {}).get('text', 'N/A')
        icon = weather_data.get('current', {}).get('condition', {}).get('icon', '')
        city_from_api = weather_data.get('location', {}).get('name')
        
        if city_from_api:
            city = city_from_api
    except Exception as e:
        temperature, condition = 'N/A', 'N/A'

    day_of_week = calendar.day_name[datetime.strptime(date, '%Y-%m-%d').weekday()]
    
    context = {
        'weather_data': weather_data,
        'date': date,
        'day_of_week': day_of_week,
        'city': city,
        'temperature': temperature,
        'condition': condition,
        'icon': icon,
        'city': city,
    }
    return render(request, 'news_feed/weather_report.html', context)
import requests
from datetime import datetime, timedelta

import reverse_geocode

def get_location_based_news(lat, lon):
    """
    Fetch local news based on latitude and longitude coordinates
    """
    try:
        import requests
        import json
        from django.utils import timezone
        
        # Get city name from coordinates using a reverse geocoding service
        try:
            geo_url = f"http://api.geonames.org/findNearbyPlaceNameJSON?lat={lat}&lng={lon}&username=demo"
            geo_response = requests.get(geo_url, timeout=5)
            if geo_response.status_code == 200:
                geo_data = geo_response.json()
                city = geo_data.get('geonames', [{}])[0].get('name', '')
            else:
                city = ''
        except:
            city = ''
        
        # If we can't get city name, try a simpler approach
        if not city:
            # Use weather API to get city name (you already have this API key)
            weather_url = f"https://api.weatherapi.com/v1/current.json?key=4723e60bee924b14862145249250509&q={lat},{lon}"
            try:
                weather_response = requests.get(weather_url, timeout=5)
                if weather_response.status_code == 200:
                    weather_data = weather_response.json()
                    city = weather_data.get('location', {}).get('name', '')
            except:
                city = 'Local'
        
        # For demo purposes, create some local news articles based on the detected city
        # In production, you would use a real news API here
        local_articles = []
        
        if city:
            # Create some sample local articles (replace this with real API calls)
            sample_local_news = [
                {
                    'title': f'{city} Weather Update: Current Conditions and Forecast',
                    'summary': f'Latest weather information for {city} area including temperature and forecast predictions.',
                    'source_name': f'{city} Weather Service',
                    'category': 'Local',
                },
                {
                    'title': f'{city} Local News: Community Updates',
                    'summary': f'Important local news and community updates from {city} region.',
                    'source_name': f'{city} Local News',
                    'category': 'Local',
                },
                {
                    'title': f'{city} Traffic and Transportation Update',
                    'summary': f'Current traffic conditions and transportation updates for {city} area.',
                    'source_name': f'{city} Traffic Authority',
                    'category': 'Local',
                }
            ]
            
            for i, news_item in enumerate(sample_local_news):
                article_data = {
                    'title': news_item['title'],
                    'summary': news_item['summary'],
                    'source_url': f'https://example.com/local-news-{i}',
                    'source_name': news_item['source_name'],
                    'publication_date': timezone.now(),
                    'category': 'Local',
                    'is_verified': True,
                    'credibility_score': 80,
                    'verified_by_sources': f'Location-based news for {city}',
                    'image_url': '',
                }
                
                # Try to create/get the article in database
                try:
                    article, created = Article.objects.get_or_create(
                        title=article_data['title'],
                        defaults=article_data
                    )
                    local_articles.append(article)
                except:
                    pass  # Skip if there's any error
        
        return local_articles
        
    except Exception as e:
        print(f"Error in location-based news fetching: {e}")
        return []

def get_enhanced_local_news(lat, lon, city_name="Avadi"):
    """
    Enhanced function to get more local Indian news articles

    """
    try:
        all_local_articles = []
        
        # Method 1: NewsData.io API (supports state-wise India news)
        newsdata_api_key = 'pub_aef1a2a7a7254c98b4605c9e11186d5c'  # Get from https://newsdata.io
        
        # Determine state/region based on coordinates or city
        state_mapping = {
            'nellore': 'andhra pradesh',
            'hyderabad': 'telangana',
            'bangalore': 'karnataka',
            'mumbai': 'maharashtra',
            'delhi': 'delhi',
            'chennai': 'tamil nadu',
            'kolkata': 'west bengal',
            'avadi' : 'tamil nadu',
        }
        
        state = state_mapping.get(city_name.lower(), 'andhra pradesh')
        search_terms = [city_name, state, f"{city_name} news", f"{state} news", "local news"]
        
        for term in search_terms[:3]:  # Limit API calls
            try:
                # NewsData.io API for regional Indian news
                url = f"https://newsdata.io/api/1/news?apikey={newsdata_api_key}&q={term}&country=in&language=en&size=5"
                
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    
                    for article in data.get('results', [])[:5]:
                        if article.get('title') and article.get('link'):
                            article_data = {
                                'title': article['title'],
                                'summary': article.get('description', 'No summary available.')[:500],
                                'source_url': article['link'],
                                'source_name': article.get('source_id', 'Regional Source'),
                                'publication_date': timezone.now(),
                                'category': 'Local',
                                'is_verified': True,
                                'credibility_score': 80,
                                'verified_by_sources': f'NewsData.io - {city_name} Regional',
                                'image_url': article.get('image_url', ''),
                            }
                            all_local_articles.append(article_data)
                            
            except Exception as e:
                print(f"NewsData API error for {term}: {e}")
                continue
        
        # Method 2: Use Indian Regional RSS Feeds
        regional_feeds = [
            f"https://www.ndtv.com/andhra-pradesh/rss",  # NDTV Andhra Pradesh
            f"https://timesofindia.indiatimes.com/rss.cms",  # TOI RSS
            f"https://www.thehindu.com/news/cities/Visakhapatnam/feeder/default.rss",  # Hindu Andhra
        ]
        
        for feed_url in regional_feeds:
            try:
                import feedparser
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:3]:  # Limit to 3 per feed
                    # Check if it's relevant to the location
                    title_lower = entry.title.lower()
                    summary_lower = entry.get('summary', '').lower()
                    
                    location_keywords = [city_name.lower(), state.lower(), 'local', 'district', 'region']
                    
                    if any(keyword in title_lower or keyword in summary_lower for keyword in location_keywords):
                        article_data = {
                            'title': entry.title,
                            'summary': entry.get('summary', 'No summary available.')[:500],
                            'source_url': entry.link,
                            'source_name': feed_url.split('//')[1].split('/')[0],  # Extract domain
                            'publication_date': timezone.now(),
                            'category': 'Local',
                            'is_verified': True,
                            'credibility_score': 85,
                            'verified_by_sources': f'RSS Feed - {city_name} Regional',
                            'image_url': '',
                        }
                        all_local_articles.append(article_data)
                        
            except Exception as e:
                print(f"RSS Feed error for {feed_url}: {e}")
                continue
        
        # Method 3: Use regional search terms with NewsAPI
        newsapi_key = 'eccc57e598f04fe1a13c7147cd377655'  # Get from newsapi.org
        local_keywords = [
            f"{city_name} news",
            f"{state} local news", 
            f"{city_name} district",
            "andhra pradesh local",
            f"{city_name} municipal"
        ]
        
        for keyword in local_keywords[:2]:  # Limit API calls
            try:
                url = f"https://newsapi.org/v2/everything?q={keyword}&domains=timesofindia.indiatimes.com,thehindu.com,ndtv.com&language=en&sortBy=publishedAt&pageSize=5&apiKey={newsapi_key}"
                
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    
                    for article in data.get('articles', [])[:3]:
                        if article.get('title') and article.get('url'):
                            article_data = {
                                'title': article['title'],
                                'summary': article.get('description', 'No summary available.')[:500],
                                'source_url': article['url'],
                                'source_name': article.get('source', {}).get('name', 'News Source'),
                                'publication_date': timezone.now(),
                                'category': 'Local',
                                'is_verified': True,
                                'credibility_score': 82,
                                'verified_by_sources': f'NewsAPI - {city_name} Local',
                                'image_url': article.get('urlToImage', ''),
                            }
                            all_local_articles.append(article_data) 
                            
            except Exception as e:
                print(f"NewsAPI error for {keyword}: {e}")
                continue
        
        return all_local_articles[:25]  # Return up to 15 local articles
        
    except Exception as e:
        print(f"Error in enhanced local news fetching: {e}")
        return []


def categorized_news(request, category):
    weather_context = get_weather_context(request)
    base_context = {
        'categories': get_category_list(),
        'show_subscription_popup': False, # You can make this dynamic if needed
    }
    categories = get_category_list() if "get_category_list" in globals() else []
    label = (category or "").strip().lower()
    if label in {"for-you", "for_you", "for you"}:
        articles = for_you_queryset()
        return render(request, "news_feed/homepage.html", {"articles": articles, "categories": categories, "category": "For you",
                                                            **base_context, **weather_context,})

    if label in {"news-showcase", "news_showcase", "news showcase"}:
        articles = showcase_queryset()
        return render(request, "news_feed/homepage.html", {"articles": articles, "categories": categories, "category": "News Showcase",
                                                            **base_context, **weather_context,})
    
    if label == "india":
        qs = (Article.objects
                        .filter(is_verified=True, category__iexact="India")
                        .order_by("-publication_date"))
        recent = qs.filter(publication_date__gte=timezone.now() -
                        timedelta(days=3))[:120]

        # fall back to older cards only if fewer than 30 remain
        articles = recent if recent.count() >= 30 else qs[:120]

        return render(request,
                    "news_feed/homepage.html",
                    {"articles": articles,
                    "categories": categories,
                    "category": "India",
                    **base_context,
                    **weather_context,})

    
    # Handle Local category with enhanced location-based news
    if label == "local":
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        
        # Get city name from weather data or use default
        city = "Nellore"  # You can make this dynamic from your weather widget
        
        # Get existing local articles from database
        db_articles = list(Article.objects.filter(is_verified=True, category__iexact=category).order_by('-publication_date')[:5])
        
        # Get enhanced location-based articles
        enhanced_articles = []
        try:
            enhanced_news_data = get_enhanced_local_news(lat, lon, city)
            
            # Save enhanced articles to database
            for article_data in enhanced_news_data:
                article, created = Article.objects.get_or_create(
                    title=article_data['title'],
                    source_url=article_data['source_url'],
                    defaults=article_data
                )
                enhanced_articles.append(article)
                
        except Exception as e:
            print(f"Error processing enhanced local news: {e}")
        
        # Combine and deduplicate
        all_articles = enhanced_articles + db_articles
        seen_urls = set()
        unique_articles = []
        
        for article in all_articles:
            if article.source_url not in seen_urls:
                seen_urls.add(article.source_url)
                unique_articles.append(article)
        
        # Sort by publication date
        articles = sorted(unique_articles, key=lambda x: x.publication_date or timezone.now(), reverse=True)[:20]
        
        context = {
            'articles': articles,
            'categories': categories,
            'category': category,
            **base_context,
            **weather_context,
           
        }
        return render(request, 'news_feed/homepage.html', context)
    
    if label == "technology":
        qs = (Article.objects.filter(is_verified=True,
                                    category__iexact="Technology")
                            .order_by("-publication_date")[:120])
        return render(request, "news_feed/homepage.html",
                    {"articles": qs,
                    "categories": categories,
                    "category": "Technology",
                    **base_context,
                    **weather_context,})

    if label == "sports":
        qs = (Article.objects.filter(is_verified=True,
                                    category__iexact="Sports")
                            .order_by("-publication_date")[:120])
        return render(request, "news_feed/homepage.html",
                    {"articles": qs,
                    "categories": categories,
                    "category": "Sports",
                    **base_context,
                    **weather_context,})

    if label == "science":
        qs = (Article.objects.filter(is_verified=True,
                                    category__iexact="Science")
                            .order_by("-publication_date")[:120])
        return render(request, "news_feed/homepage.html",
                    {"articles": qs,
                    "categories": categories,
                    "category": "Science",
                    **base_context,
                    **weather_context,})
    
    if label == "business":
        # 1. Query for RECENT Business articles (e.g., last 3 days)
        recent_qs = (Article.objects.filter(is_verified=True,
                                            category__iexact="Business",
                                            publication_date__gte=RECENT)
                                    .order_by("-publication_date")[:60]) # Limit to 60 recent attempts

        # 2. Check if enough recent articles exist
        if recent_qs.count() >= 10:
            # If we have at least 10 recent articles, use them.
            articles = recent_qs
        else:
            # FALLBACK: If we don't have enough recent articles,
            # query older verified Business articles to ensure the grid is full.
            articles = (Article.objects.filter(is_verified=True,
                                              category__iexact="Business")
                                       .order_by("-publication_date")[:40]) # Use up to 40 verified articles

        return render(request, "news_feed/homepage.html",
                      {"articles": articles,
                      "categories": categories,
                      "category": "Business",
                      **base_context,
                      **weather_context,})
   
    if label == "world":
        from django.db.models import Count
        
        # Get World articles and remove duplicates by similar titles
        base_qs = (Article.objects
                .filter(is_verified=True, category__iexact="World")
                .order_by("-publication_date"))
        
        # Apply 3-day filter with fallback
        recent_articles = base_qs.filter(publication_date__gte=RECENT)
        articles_list = list(recent_articles if recent_articles.count() >= 30 else base_qs[:120])
        
        # Remove duplicates by checking title similarity
        unique_articles = []
        seen_titles = set()
        
        for article in articles_list:
            # Create a normalized version of the title for comparison
            normalized = ' '.join(article.title.lower().split())
            
            # Check if we've seen a very similar title
            is_duplicate = False
            for seen_title in seen_titles:
                # Calculate similarity (you can adjust this threshold)
                if len(set(normalized.split()) & set(seen_title.split())) >= len(normalized.split()) * 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_titles.add(normalized)
                unique_articles.append(article)
                
            if len(unique_articles) >= 60:  # Limit to 60 unique articles
                break
        
        return render(request, "news_feed/homepage.html",
                    {"articles": unique_articles,
                    "categories": categories,
                    "category": "World",
                    **base_context,
                    **weather_context,})
    

    
    # Handle all other categories normally
    articles = Article.objects.filter(is_verified=True, category__iexact=category).order_by('-publication_date')
    
    context = {
        'articles': articles,
        'categories': categories,
        'category': category,
        **base_context,
        **weather_context,
    }
    return render(request, 'news_feed/homepage.html', context)




def report_misinformation(request):
    if request.method == 'POST':
        article_id = request.POST.get('article_id')
        reason = request.POST.get('reason')
        try:
            article = Article.objects.get(pk=article_id)
            Feedback.objects.create(
                user=request.user if request.user.is_authenticated else None,
                article=article,    
                reason=reason
            )
            return JsonResponse({'status': 'success'}, status=200)
        except Article.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Article not found'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

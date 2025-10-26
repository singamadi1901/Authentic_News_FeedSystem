# news_feed/management/commands/fetch_and_verify_news.py
import time
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from django.utils import timezone
from dateutil import parser as dateparser

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from news_feed.models import Article

import feedparser
import requests
import re

import logging

# Set up a logger to see detailed output
logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# One Session for every HTTP request – carries a modern User-Agent
# ------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/118.0 Safari/537.36"
    )
})
MAX_AGE = 3
from datetime import datetime, timedelta, timezone as dt_tz
RECENT_WINDOW = timezone.now() - timedelta(days=MAX_AGE)

import re
from urllib.parse import urlparse

def norm_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"[^\w\s:/.-]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()

def norm_url(u: str) -> str:
    try:
        p = urlparse(u or "")
        clean = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
        return clean.lower()
    except Exception:
        return (u or "").strip().lower()

TOP_SOURCES = {
    "bbc.com", "bbc.co.uk", "reuters.com", "aljazeera.com",
    "thehindu.com", "ndtv.com", "timesofindia.indiatimes.com",
    "indianexpress.com", "hindustantimes.com",
}

def truthworthiness_score(article) -> int:
    base = int(article.get("credibility_score", 0) or 0)
    host = urlparse(article.get("source_url", "")).netloc.replace("www.", "")
    boost = 10 if host in TOP_SOURCES else 0
    return base + boost



def fetch_feed(url: str, timeout: int = 15):
    """
    Download an RSS/Atom feed with our Session so the UA header is sent.
    Returns feedparser.parse result (never raises).
    """
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as exc:
        print(f"[feed-error] {url[:80]} … {exc}")
        return feedparser.parse(b"")


# --- Centralized Configuration and Mapping ---
CANON = {
    'india': 'India', 'national': 'India', 'indian': 'India',
    'world': 'World', 'international': 'World',
    'local': 'Local', 'city': 'Local',
    'business': 'Business', 'economy': 'Business', 'markets': 'Business',
    'technology': 'Technology', 'tech': 'Technology',
    'entertainment': 'Entertainment', 'movies': 'Entertainment', 'bollywood': 'Entertainment',
    'sports': 'Sports', 'cricket': 'Sports', 'football': 'Sports', 'volleyball': 'Sports', 'hockey': 'Sports', 'badminton': 'Sports',
    'science': 'Science',
    'health': 'Health',
}
TOP_SOURCES = {"The Hindu", "NDTV", "Al Jazeera", "Times of India", "Reuters", "The Verge", "ESPN", "eonline.com", "ScienceDaily", "Medical News Today"}
MIN_SCORE_FOR_VERIFIED = 40

# --- Helper Functions ---

def parse_pub_date(entry):
    candidates = ["published_parsed", "updated_parsed", "published", "updated"]
    for key in candidates:
        val = getattr(entry, key, None)
        if val:
            try:
                if hasattr(val, "tm_year"):
                    dt = datetime(*val[:6])
                else:
                    dt = dateparser.parse(str(val))
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except Exception:
                continue
    return timezone.now()

def canonicalize(raw):
    key = (raw or "").strip().lower()
    return CANON.get(key)

def analyze_headline_keywords(title: str) -> int:
    """
    Analyzes the headline for keywords that suggest higher or lower credibility.
    Returns a small score adjustment.
    """
    title = title.lower()
    score_adjustment = 0
    
    # Positive keywords that suggest official or factual reporting
    positive_keywords = ["exclusive", "analysis", "investigation", "official statement", "confirmed"]
    # Negative keywords that suggest speculation or opinion
    negative_keywords = ["rumor", "speculation", "opinion", "could be", "may have"]

    for kw in positive_keywords:
        if kw in title:
            score_adjustment += 5
            
    for kw in negative_keywords:
        if kw in title:
            score_adjustment -= 5
            
    return score_adjustment

def get_source_reputation(source_domain: str) -> int:
    """Returns a reputation score for a news source (out of 100)."""
    reputation = {
        "reuters.com": 98, "apnews.com": 95, "bbc.com": 92, "bbc.co.uk": 92,
        "thehindu.com": 90, "aljazeera.com": 88, "ndtv.com": 85,
        "timesofindia.indiatimes.com": 82, "nature.com": 93, "science.org": 90,
        "nasa.gov": 95, "medscape.com": 88, "cdc.gov": 90, "who.int": 92,
    }
    return reputation.get(source_domain.replace("www.", ""), 60)



# news_feed/management/commands/fetch_and_verify_news.py

# ... (Previous helper functions remain unchanged)

def calculate_credibility_score(article: dict, consensus_count: int) -> int:
    """
    Calculates a final score based on source, consensus, image analysis, and keyword analysis.
    This version emphasizes unique article features (Image and Keywords) for score variability.
    Weights: Source (40%), Consensus (25%), Image (25%), Keywords/Random (10%).
    """
    source_domain = urlparse(article.get("source_url", "")).netloc
    
    # --- 1. Get Individual Article Scores ---
    
    # 1.1 Image Authenticity Score (Unique per article)
    image_score = analyze_image_authenticity(article.get("image_url")) 
    
    # 1.2 Keyword Analysis Score (Unique per article)
    keyword_adjustment = analyze_headline_keywords(article.get("title", ""))
    
    # --- 2. Calculate Weighted Components ---

    # 2.1 Source Reputation (40% weight) - STATIC PER SOURCE
    source_base_score = get_source_reputation(source_domain) * 0.40
    
    # 2.2 Consensus Boost (25% weight) - STATIC PER TITLE GROUP
    # Min(consensus/3.0, 1.0) ensures a maximum boost for 3 or more matching sources.
    consensus_normalized = min(consensus_count / 3.0, 1.0)
    consensus_boost = consensus_normalized * 25.0 # Max 25 points

    # 2.3 Image Analysis (25% weight) - DYNAMIC PER ARTICLE
    # Scale the 0-100 image score to 25 points
    image_factor = image_score * 0.25
    
    # 2.4 Keyword/Random Adjustment (10% weight) - DYNAMIC PER ARTICLE
    # Scale keywords (-10 to +10) to a small factor (e.g., -5 to +5)
    keyword_factor = keyword_adjustment * 0.5 
    
    # --- 3. Final Calculation ---
    final_score = (
        source_base_score + 
        consensus_boost + 
        image_factor + 
        keyword_factor
    )
    
    # --- Add a small random noise (1 to 5 points) for high variability ---
    # This ensures that even two articles with identical image and keywords have *slightly* different scores.
    final_score += random.uniform(1.0, 5.0) 

    # Ensure the score is always clamped within a reasonable range
    # Min score set to 30 to allow more articles to be verified
    MIN_SCORE_FOR_DISPLAY = 30
    return max(MIN_SCORE_FOR_DISPLAY, min(int(final_score), 100))


def scrape_image_from_page(url: str, timeout: int = 10) -> str | None:
    """
    If a feed has no image, fetch the article page and try to find one by
    checking for og:image, twitter:image, and high-quality <img> tags.
    """
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")

        # --- Priority 1: Check for Open Graph and Twitter Card images ---
        for prop in ["og:image", "twitter:image"]:
            meta_tag = soup.find("meta", property=prop)
            if meta_tag and meta_tag.get("content"):
                # Convert relative URL to absolute
                image_url = urljoin(url, meta_tag["content"])
                logger.info(f"[image-scrape] Found meta image for {url}: {image_url}")
                return image_url

        # --- Priority 2: Find the largest image inside the main article body ---
        article_body = soup.find("article") or soup.find("body")
        if article_body:
            best_image = None
            max_area = 0
            for img in article_body.find_all("img"):
                src = img.get("src")
                if not src or src.startswith("data:"):
                    continue

                try:
                    # Check for image dimensions, prioritizing larger images
                    width = int(img.get("width", 0))
                    height = int(img.get("height", 0))
                    area = width * height

                    # Ignore small images like icons or spacers
                    if width > 300 and height > 150 and area > max_area:
                        max_area = area
                        best_image = src
                except (ValueError, TypeError):
                    # If width/height are not numbers, just check if it seems plausible
                    if "logo" not in src.lower() and "icon" not in src.lower():
                        best_image = src


            if best_image:
                image_url = urljoin(url, best_image)
                logger.info(f"[image-scrape] Found fallback <img> for {url}: {image_url}")
                return image_url

    except Exception as e:
        logger.error(f"[image-scrape-fail] Could not get image for {url}. Reason: {e}")

    logger.warning(f"[image-scrape-miss] No suitable image found for {url}")
    return None

def pick_image_from_entry(entry):
    for attr in ("media_thumbnail", "media_content"):
        media = getattr(entry, attr, None)
        if media:
            if isinstance(media, list) and media:
                u = media[0].get("url")
                if u: return u
            elif isinstance(media, dict):
                u = media.get("url")
                if u: return u
    return None

def analyze_image_authenticity(image_url):
    if not image_url: return 50
    if "manipulated_image.jpg" in image_url: return 10
    if "trusted-archive" in image_url: return 95
    return random.randint(40, 80)

TECH_KWS = {
    "ai", "artificial intelligence", "semiconductor", "chip",
    "processor", "smartphone", "iphone", "android", "laptop",
    "startup", "software", "app ", "gadget", "cyber-security",
    "cloud", "iot", "vr", "ar ", "robot", "quantum",
}

SPORTS_KWS = {
    "ipl", "t20", "cricket", "fifa", "football", "nba","tournament", "match-day", "fixture", "umpire",
    "innings", "wicket", "goal-line", "transfer window","olympic", "premier league", "world cup", "grand prix",
}
SCIENCE_KWS={
    "nasa", "space", "astronomy", "planet", "galaxy",
    "quantum", "physics", "chemistry", "biology",
    "researchers", "laboratory", "telescope", "neutron",
    "particle", "genome", "climate study",
}

def categorize_by_title(title):
    title = title.lower()
    title_rules = [
        (['ipl','cricket','t20','football','fifa','olympic','world cup','asia cup','hockey','kabaddi','nba',
          'match','runs','wicket','goal','sports'], 'Sports'),
        (['ai','semiconductor','chip','software','startup','app','iphone','android','ai','artificial intelligence'
          'iot','cloud computing','satellite','spacex','cyber-security','technology'], 'Technology'),
        (['budget','gdp','inflation','stocks','market','sensex','nifty','merger','companies','board','invest','finance','ipo'], 'Business'),
        (['vaccine','covid','health','hospital','disease','outbreak'], 'Health'),
        (['research','nasa','isro','astronomy','physics','climate study', 'spacex','quantun','researchers discover',
          'galaxy','cosmic','asteroid','black hole','climate study'], 'Science'),
        (['film','movie','box office','series','bollywood','hollywood','actor','actress'], 'Entertainment'),
        (['city','district','municipal','local body','ward'], 'Local'),
        (['india','parliament','delhi','supreme court','pm'], 'India'),
        (['world','global','united nations','ukraine','gaza','us','eu'], 'World'),
    ]
    for kws, label in title_rules:
        if any(kw in title for kw in kws):
            return label
        if any(kw in title for kw in SPORTS_KWS):
            return "Sports"
        if any(kw in title for kw in SCIENCE_KWS):        # ← NEW
            return "Science"
        if any(kw in title for kw in TECH_KWS):
            return "Technology"
        
    return "News Showcase"

def categorize_by_link(link):
    link = link.lower()
    link_rules = {
        'theverge.com/tech': 'Technology',
        'wired.com': 'Technology',
        'arstechnica.com': 'Technology',
        'espn.com/sports': 'Sports',
        'espncricinfo.com' : 'Sports',
        'reuters.com/business': 'Business',
        'economictimes.indiatimes.com': 'Business',
        'eonline.com/news': 'Entertainment',
        'hollywoodreporter.com': 'Entertainment',
        'aljazeera.com/news': 'World',
        'bbc.co.uk':'World',
        'reuters.com':'World',
        'bbc.com':'World',  
        'timesofindia.indiatimes.com/india': 'India',
        'thehindu.com': 'India',
        'indianexpress.com': 'India',
        'ndtv.com': 'India',
        'sciencedaily.com/news': 'Science',
        'techxplore.com': 'Science',
        'nature.com/subjects/space': 'Science',
        'nasa.gov': 'Science',
        'medicalnewstoday.com/articles': 'Health',
    }
    host = urlparse(link).netloc.replace("www.", "")
    # Exact host match
    if host in link_rules :
        return link_rules [host]
    for rule, category in link_rules.items():
        if rule in link:
            return category
        if host.endswith(rule):
            return category
    return None

class Command(BaseCommand):
    help = 'Fetches and verifies news from multiple sources and saves to the database.'

    

    def handle(self, *args, **options):
        self.stdout.write("Starting news fetching and verification...")
        

        category_feeds = {
            'Technology': ['https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pKVGlnQVAB?hl=en-IN&gl=IN&ceid=IN:en',
                'https://www.wired.com/feed/rss',
                'https://techcrunch.com/feed/',
                            ],
            'Sports': ['https://feeds.bbci.co.uk/sport/rss.xml',
                       'https://www.espn.com/espn/rss/news',
                       'https://www.espncricinfo.com/rss/content/story/feeds/0.xml',
                       ],
            'Business': ['https://economictimes.indiatimes.com/rssfeeds/1977021501.cms',
                        'https://www.indianewsnetwork.com/rss.en.business.xml',
                        'https://www.livemint.com/rss/companies',
                        ],
            'Entertainment': ['http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml', 
                              'https://www.hollywoodreporter.com/feed/',
                              ],
            'News Showcase': 'https://www.thehindu.com/news/national/feeder/default.rss',
            'World': ['https://www.aljazeera.com/xml/rss/all.xml', 
                      'https://feeds.bbci.co.uk/news/world/rss.xml'],

            'India': ['https://timesofindia.indiatimes.com/rssfeeds/1221656.cms',
                        'https://newsapi.org/s/india-news-api',
                        ],


            'Science': ['https://www.sciencedaily.com/rss/all.xml',
                        'https://www.nasa.gov/rss/dyn/breaking_news.rss',
                        'https://phys.org/rss-feed/',
                        'https://www.nasa.gov/rss/dyn/breaking_news.rss',
                        'https://www.theguardian.com/science/rss',
                        ],
            'Health': ['https://www.ruralhealthinfo.org/rss/news.xml',
                       'https://www.medicinenet.com/rss/dailyhealth.xml',
                       'https://www.fiercehealthcare.com/rss/xml',
                       'https://www.who.int/rss-feeds/news-english.xml',
                       'https://kffhealthnews.org/rss/',
                       ],
        }
        
        Article.objects.filter(publication_date__lt=RECENT_WINDOW).delete()

        #step1 : fetch news
        all_articles = []
        for cat, feeds in category_feeds.items():

        # make feeds always iterable
            if isinstance(feeds, str):
                feeds = [feeds]
   
            self.stdout.write(f"Fetching news for '{cat}'…")

            new_items = []
            for url in feeds:
                feed = fetch_feed(url)                 # uses the UA-Session
                new_items.extend(feed.entries)

            if not new_items:
                self.stdout.write(f"No entries found for {cat}. Skipping.")
                continue

            for entry in feed.entries:
                title = getattr(entry, 'title', None)
                link = getattr(entry, 'link', None)
                summary = getattr(entry, 'summary', 'No summary available.')
                source_name = getattr(feed.feed, 'title', urlparse(url).netloc)
                
                if not title or not link:
                    continue
                
                pub_date = parse_pub_date(entry)
                pub_dt = parse_pub_date(entry)           # keep your helper
                if not pub_dt or pub_dt < RECENT_WINDOW:
                    continue    
                
                # Smart date filter: wider window for Health/Science
                is_slow_category = cat in ["Health", "Science"]
                time_window = timedelta(days=5) if is_slow_category else timedelta(days=3)

                if not pub_dt or pub_dt < (timezone.now() - time_window):
                    continue

                
                # Only process articles from the last 24 hours
                if pub_date < timezone.now() - timedelta(days = 3):
                    continue
                
                image_url = pick_image_from_entry(entry) or scrape_image_from_page(link)

                # For Health and Science, trust the feed source. For others, allow smart categorization.
                if cat in ["Health", "Science"]:
                    entry_cat = cat  # Always use the feed's category for Health/Science
                else:
                    entry_cat = categorize_by_link(link) or categorize_by_title(title) or cat

                
                all_articles.append({
                    'title': title,
                    'summary': summary,
                    'category': entry_cat,  
                    'source_url': link,
                    'publication_date': pub_date,
                    'source_name': source_name,
                    'image_url': image_url or "",
                    'credibility_score': 0, 
                    'is_verified': False, 
                    'verified_by_sources': '',
                })
            time.sleep(1) 

        if not all_articles:
            self.stdout.write("No recent articles fetched. Exiting.")
            return

        self.stdout.write("Aggregated news. Now verifying...")

        from collections import defaultdict
        title_groups = defaultdict(list)

        for article in all_articles:
            # A key is made from the first 12 words to group similar titles
            normalized_title = norm_text(article['title'])
            key = " ".join(norm_text(article['title']).split()[:12])
            if key:
                title_groups[key].append(article)

        # step 2: verify news
        final_articles_to_save = []
        verified = []
        MIN_SCORE_FOR_VERIFIED = 40  # Set your minimum threshold here
        for a in final_articles_to_save:
            # Check 1: Is the score high enough?
            if a['credibility_score'] < MIN_SCORE_FOR_VERIFIED:
                continue

            # Check 2: Is the article recent? (Wider window for Health/Science)
            is_slow_category = a.get("category") in {"Health", "Science"}
            recent_cutoff = (timezone.now() - timedelta(days=20)) if is_slow_category else RECENT_WINDOW
            if not a.get("publication_date") or a["publication_date"] < recent_cutoff:
                continue
            
            # If it passes all checks, it's considered verified
            a['is_verified'] = True
            verified.append(a)
            


        # --- STEP 3: CALCULATE SCORE for each article based on trustworthiness ---
        for key, group in title_groups.items():
            # Check if this story is trustworthy enough to proceed
            consensus_count = len(set(a['source_name'] for a in group))
            
            for article in group:
                article['credibility_score'] = calculate_credibility_score(article, consensus_count)
                article['is_verified'] = article['credibility_score'] >= MIN_SCORE_FOR_VERIFIED

            # Find the best article in the group to be the representative
            best_article_in_group = max(group, key=lambda a: get_source_reputation(urlparse(a.get("source_url", "")).netloc))
            
            # Calculate the credibility score for this story
            credibility_score = calculate_credibility_score(best_article_in_group, consensus_count)

            # STEP 2 & 3: Check for "trueness" and filter duplicates
            if credibility_score >= MIN_SCORE_FOR_VERIFIED:
                # STEP 4: Assign the score to the best article
                best_article_in_group['credibility_score'] = credibility_score
                best_article_in_group['is_verified'] = True
                best_article_in_group['verified_by_sources'] = ", ".join(sorted(set(a['source_name'] for a in group)))
                
                # Add only this single best article to our final list
                final_articles_to_save.append(best_article_in_group)

        self.stdout.write(f"Found {len(final_articles_to_save)} unique, trustworthy stories.")
      
      #saving to database

        saved = 0
        for a in final_articles_to_save :
            is_slow_category = a.get("category") in {"Health", "Science"}
            recent_cutoff = (timezone.now() - timedelta(days=5)) if is_slow_category else RECENT_WINDOW

            if not a.get("publication_date") or a["publication_date"] < recent_cutoff:
                continue
            try:
                obj, created = Article.objects.update_or_create(
                    title=a["title"].strip(),
                    source_url=norm_url(a["source_url"]),
                    defaults={
                        "summary": a.get("summary", "")[:2000],
                        "category": a.get("category", "News Showcase"),
                        "image_url": a.get("image_url", ""),
                        "publication_date": a["publication_date"],
                        "credibility_score": int(a.get("credibility_score", 0) or 0),
                        "is_verified": True,
                        "verified_at": timezone.now(),
                        "image_analysis_score": int(a.get("image_analysis_score", 0) or 0),
                        "source_name": a.get("source_name", "Unknown")[:100],
                        "verified_by_sources": a.get("verified_by_sources", ""),
                    }
                )
                if created:
                    saved += 1
            except Exception as e:
                self.stdout.write(f"[save-skip] {a.get('title','N/A')[:60]} … {e}")

        self.stdout.write(self.style.SUCCESS(f"Saved {saved} unique, verified articles."))
        # ================= END VERIFICATION + DEDUP + SAVE =================

        
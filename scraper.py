import feedparser
import httpx
import asyncio
from bs4 import BeautifulSoup
from app import app, db
from models import NewsSource, Article
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import datetime, timedelta, UTC

BREAKING_KEYWORDS = [
    "BREAKING", "URGENT", "CRISIS", "DEADLY", "WAR", "ATTACK", "MASSIVE",
    "EXCLUSIVE", "TARIFFS", "EMERGENCY", "EVACUATION", "COLLAPSE",
    "EXPLOSION", "SHOOTING", "HOSTAGE", "THREAT", "Trump fires", "SANCTIONS"
]

SECURITY_KEYWORDS = [
    "data breach", "hacked", "cyber attack", "compromised", "leak",
    "phishing", "ransomware", "malware", "zero-day", "DDoS", "exfiltration",
    "spyware", "nation-state attack", "APT", "backdoor", "hack confirmed", "credential stuffing"
]

ECONOMIC_KEYWORDS = [
    "bankruptcy", "recession", "inflation", "market crash", "defaults",
    "federal reserve", "interest rates", "layoffs", "financial crisis",
    "economic downturn", "credit crunch", "debt ceiling"
]

DISASTER_KEYWORDS = [
    "earthquake", "hurricane", "tornado", "flood", "wildfire", "tsunami",
    "volcano", "landslide", "storm surge", "blizzard", "drought", "heatwave"
]

HEALTH_KEYWORDS = [
    "pandemic", "epidemic", "virus", "outbreak", "health crisis", "quarantine",
    "CDC warning", "WHO emergency", "public health emergency", "vaccine shortage"
]


FLUFF_KEYWORDS = [
    "Wordle", "Must-have", "Connections", "Horoscope", "Celebrity", "BBQ", "Best Products",
    "Comparison", "Unboxing", "Review", "Ranking", "Oscars", "Best", "Grammys",
    "TikTok", "Reddit", "Social Media Reacts", "Yielding", "Viral Video", "Investor", "Funniest Tweets"
]


HIGH_PRIORITY_SOURCES = [
    "nytimes.com", "reuters.com", "cbsnews.com", "cnbc.com", "apnews.com", "cnn.com", "foxnews.com", "bbc.com",
    "theguardian.com", "wsj.com", "npr.org", "aljazeera.com", "economist.com",
    "bloomberg.com", "forbes.com", "financialtimes.com", "businessinsider.com"
]

POLITICAL_KEYWORDS = [
    "Trump", "Biden", "White House", "Congress", "Senate", "House of Representatives",
    "Supreme Court", "Impeachment", "Election", "Vote", "Ballot", "Governor",
    "Legislation", "Bill", "Executive Order", "SCOTUS", "Subpoena", "Indictment",
    "Pardon", "Whistleblower", "Investigation", "DOJ", "FBI", "CIA", "Pentagon",
    "National Security", "Foreign Policy", "UN", "Purge", "NATO"
]


async def fetch_page(url):
    """Fetches a webpage asynchronously."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            return response.text
    except Exception as e:
        print(f"⚠️ Failed to fetch page: {url} | Error: {e}")
        return None

async def extract_image_from_page(article_url):
    """Attempts to extract an image from the article page (fallback)."""
    html = await fetch_page(article_url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')


    og_image = soup.find("meta", property="og:image")
    if og_image and "content" in og_image.attrs:
        return og_image["content"]

    first_img = soup.find("img")
    if first_img and "src" in first_img.attrs:
        return first_img["src"]

    return None  

def calculate_article_score(article, entry=None):
    """Determines how 'big' an article is based on multiple factors."""
    score = 0

    # Check engagement metrics
    if entry:
        try:
            feed_points = int(entry.get("points", 0)) if entry else 0
            score += min(feed_points * 0.1, 10)  
        except (ValueError, TypeError):
            pass

        try:
            feed_comments = int(entry.get("comments", 0)) if entry else 0
            score += min(feed_comments * 0.05, 5)  
        except (ValueError, TypeError):
            pass

    # Check Breaking Keywords
    if any(keyword.lower() in article.title.lower() for keyword in BREAKING_KEYWORDS):
        score += 12  

    # High Priority Source Bonus (fixed)
    if any(source in article.url.lower() for source in HIGH_PRIORITY_SOURCES):
        score += 8  

    # Keyword Category Boosts
    if any(keyword.lower() in article.title.lower() for keyword in SECURITY_KEYWORDS):
        score += 9
    if any(keyword.lower() in article.title.lower() for keyword in ECONOMIC_KEYWORDS):
        score += 7
    if any(keyword.lower() in article.title.lower() for keyword in DISASTER_KEYWORDS):
        score += 10  
    if any(keyword.lower() in article.title.lower() for keyword in HEALTH_KEYWORDS):
        score += 5
    if any(keyword.lower() in article.title.lower() for keyword in POLITICAL_KEYWORDS):
        score += 8  

    # Fluff Content Penalty
    if any(keyword.lower() in article.title.lower() for keyword in FLUFF_KEYWORDS):
        score -= 10  

    # Age Penalty (fixed order)
    age_penalty = max(0, (article.age_in_hours() / 12) * 2)  # Define first
    if any(keyword.lower() in article.title.lower() for keyword in POLITICAL_KEYWORDS):
        age_penalty *= 0.5  # Reduce age penalty for politics
    score -= age_penalty

    return max(0, score)  


async def update_existing_article_scores():
    """ Updates scores for all articles already in the database. """
    with app.app_context():
        Session = scoped_session(sessionmaker(bind=db.engine))
        session = Session()

        articles = session.query(Article).all()
        for article in articles:
            article.score = calculate_article_score(article)

        session.commit()
        session.close()
        print("✅ Re-scored existing articles in the database.")

async def scrape_articles(source_id=None):
    """Scrapes articles from a specific source or all sources if no ID is provided."""
    with app.app_context():
        Session = scoped_session(sessionmaker(bind=db.engine))
        session = Session()
        
        sources = session.query(NewsSource).filter(
            (NewsSource.id == source_id) if source_id else NewsSource.enabled == True
        ).all()

        for source in sources:
            print(f"🔄 Fetching articles from {source.name} ({source.url})...")
            feed = feedparser.parse(source.url)

            if "entries" not in feed or not feed.entries:
                print(f"❌ No entries found in {source.url}")
                source.scrape_status = "Error: No entries found"
                session.commit()
                continue

            source.scrape_status = "Success"
            session.commit()

            tasks = []  

            for entry in feed.entries:
                try:
                    title = entry.title.strip() if entry.title else "Untitled"
                    url = entry.link
                    image_url = None
                    if not title:
                         print(f"⚠️ Missing title for {entry.link}, skipping...")
                         continue

        
                    if "media_content" in entry and entry.media_content:
                        image_url = entry.media_content[0]['url']
                    elif "enclosures" in entry and entry.enclosures:
                        image_url = entry.enclosures[0]['href']

            
                    if not image_url:
                        tasks.append(url)

             
                    existing_article = session.query(Article).filter(
                        (Article.url == url) | (Article.image_url == image_url)
                    ).first()

                    if not existing_article:
                        new_article = Article(title=title, url=url, image_url=image_url, source_id=source.id)
                        new_article.score = calculate_article_score(new_article, entry=entry)  
                        session.add(new_article)
                        print(f"✅ Added: {title} (Score: {new_article.score}, Image: {image_url})")
                    else:
                        print(f"⚠️ Skipped duplicate: {title} (Existing Image: {existing_article.image_url})")

                except AttributeError as e:
                    print(f"⚠️ Skipping entry due to missing fields: {e}")

            session.commit()  


            if tasks:
                print(f"🔍 Fetching images for {len(tasks)} articles...")
                results = await asyncio.gather(*[extract_image_from_page(url) for url in tasks])

                for url, image_url in zip(tasks, results):
                    if image_url:
                        article = session.query(Article).filter_by(url=url).first()
                        if article:
                            article.image_url = image_url
                            session.commit()
                            print(f"📸 Updated image for: {article.title} -> {image_url}")

        session.close()
        print("✅ Scraping complete.")

def cleanup_old_articles():
    """Deletes articles older than 24 hours."""
    with app.app_context():
        Session = scoped_session(sessionmaker(bind=db.engine))
        session = Session()


        cutoff_time = datetime.now(UTC) - timedelta(hours=24)


        deleted_count = session.query(Article).filter(Article.timestamp < cutoff_time).delete(synchronize_session=False)

        session.commit()
        session.close()

        print(f"🗑️ Deleted {deleted_count} articles older than 24 hours.")

if __name__ == "__main__":
    import sys
    asyncio.run(scrape_articles())
    asyncio.run(update_existing_article_scores()) 
    cleanup_old_articles() 
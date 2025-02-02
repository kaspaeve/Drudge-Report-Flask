import feedparser, httpx, asyncio, re
from bs4 import BeautifulSoup
from app import app, db
from models import NewsSource, Article
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import datetime, timedelta, UTC

# Define keyword categories as sets for optimized lookup
BREAKING_KEYWORDS = {
    "TRADE WAR", "TRADE WARS", "BREAKING", "BREAKING NEWS", "JUST IN",
    "EMERGENCY", "EVACUATION", "COLLAPSE", "EXPLOSION", "ATTACK", "SANCTIONS",
    "TARIFF", "TARIFFS", "ECONOMIC SANCTIONS", "WAR", "WARS", "CONFLICT",
    "ESCALATION", "CYBER ATTACK", "CYBER ATTACKS", "RIOT", "RIOTS",
    "IMPEACHMENT", "NUCLEAR TEST", "NUCLEAR TESTS", "MISSILE LAUNCH", "MISSILE LAUNCHES"
}

SECURITY_KEYWORDS = {
    "data breach", "hacked", "cyber attack", "compromised", "leak",
    "phishing", "ransomware", "malware", "zero-day", "DDoS", "exfiltration",
    "spyware", "nation-state attack", "APT", "backdoor", "hack confirmed", "credential stuffing"
}

ECONOMIC_KEYWORDS = {
    "bankruptcy", "recession", "inflation", "market crash", "defaults",
    "federal reserve", "interest rates", "layoffs", "financial crisis",
    "economic downturn", "credit crunch", "debt ceiling"
}

DISASTER_KEYWORDS = {
    "earthquake", "hurricane", "tornado", "flood", "wildfire", "tsunami",
    "volcano", "landslide", "storm surge", "blizzard", "drought", "heatwave"
}

HEALTH_KEYWORDS = {
    "pandemic", "epidemic", "virus", "outbreak", "health crisis", "quarantine",
    "CDC warning", "WHO emergency", "public health emergency", "vaccine shortage"
}

FLUFF_KEYWORDS = {
    "Wordle", "Must-have", "Connections", "Horoscope", "Celebrity", "BBQ", "Best Products",
    "Comparison", "Unboxing", "Review", "Ranking", "Oscars", "Best", "Grammys",
    "TikTok", "Reddit", "Social Media Reacts", "Yielding", "Viral Video", "Investor", "Funniest Tweets"
}

HIGH_PRIORITY_SOURCES = {
    "nytimes.com", "reuters.com", "cbsnews.com", "cnbc.com", "apnews.com", "cnn.com", "foxnews.com", "bbc.com",
    "theguardian.com", "wsj.com", "npr.org", "aljazeera.com", "economist.com",
    "bloomberg.com", "forbes.com", "financialtimes.com", "businessinsider.com"
}

POLITICAL_KEYWORDS = {
    "Trump", "Trump's", "Biden", "Putin", "Russia", "China","White House", "Congress", "Senate", "House of Representatives",
    "Supreme Court", "Impeachment", "Election", "Vote", "Ballot", "Governor",
    "Legislation", "Bill", "Traitor", "Executive Order", "SCOTUS", "Subpoena", "Indictment",
    "Pardon", "Whistleblower", "Investigation", "DOJ", "FBI", "CIA", "Pentagon",
    "National Security", "Foreign Policy", "UN", "Purge", "NATO"
}

# Keyword dictionary for dynamic matching
KEYWORDS_SETS = {
    "breaking": BREAKING_KEYWORDS,
    "security": SECURITY_KEYWORDS,
    "economic": ECONOMIC_KEYWORDS,
    "disaster": DISASTER_KEYWORDS,
    "health": HEALTH_KEYWORDS,
    "political": POLITICAL_KEYWORDS,
    "fluff": FLUFF_KEYWORDS,
}
def matches_keyword(text, category):
    """Checks if the text contains any keywords from the given category using regex for more flexibility."""
    text_lower = text.lower()
    pattern = r'\b(' + '|'.join(re.escape(word.lower()) for word in KEYWORDS_SETS[category]) + r')\b'
    return bool(re.search(pattern, text_lower))

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

    # Engagement metrics
    if entry:
        try:
            score += min(int(entry.get("points", 0)) * 0.2, 20)
        except (ValueError, TypeError):
            pass  # Ignore invalid "points" values

        try:
            feed_comments = int(entry.get("comments", 0))  # ✅ Try to convert "comments" to int
            score += min(feed_comments * 0.1, 10)
        except (ValueError, TypeError):
            print(f"⚠️ Skipping invalid comment count: {entry.get('comments', 'N/A')}")
            feed_comments = 0  # ✅ Set to 0 if "comments" is not a number

    # Keyword Category Boosts
    for category, weight in {
        "breaking": 20, "security": 9, "economic": 7, "disaster": 11,
        "health": 5, "political": 12, "fluff": -10
    }.items():
        if matches_keyword(article.title, category):
            score += weight

    # High Priority Source Bonus
    if any(source in article.url.lower() for source in HIGH_PRIORITY_SOURCES):
        score += 8

    # Age Penalty
    age_penalty = max(0, (article.age_in_hours() / 12) * 2)
    if matches_keyword(article.title, "political"):
        age_penalty *= 0.25  # Reduce penalty if political
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

        new_articles_count = 0
        rescored_articles_count = 0

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

                    # Extract image if available
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
                        new_articles_count += 1
                        print(f"✅ Added: {title} (Score: {new_article.score}, Image: {image_url})")
                    else:
                        # Always recalculate score for existing articles
                        old_score = existing_article.score
                        new_score = calculate_article_score(existing_article, entry=entry)

                        if new_score != old_score:  # Only count it if score actually changes
                            existing_article.score = new_score
                            rescored_articles_count += 1
                            print(f"♻️ Re-scored: {title} (Old Score: {old_score} → New Score: {new_score})")

                except AttributeError as e:
                    print(f"⚠️ Skipping entry due to missing fields: {e}")


            session.commit()

            # Fetch missing images for articles without one
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

        # Print summary
        total_articles = session.query(Article).count()
        print("✅ Scraping complete.")
        print(f"🆕 New articles added: {new_articles_count}")
        print(f"🔄 Articles rescored: {rescored_articles_count}")
        print(f"📊 Total articles in database: {total_articles}")


def cleanup_old_articles():
    """Deletes articles older than 48 hours or articles with a score of 0 or less."""
    with app.app_context():
        session = scoped_session(sessionmaker(bind=db.engine))()
        cutoff_time = datetime.now(UTC) - timedelta(hours=48)  # ✅ Delete after 48 hours

        # Delete articles older than 48 hours
        old_deleted = session.query(Article).filter(Article.timestamp < cutoff_time).delete(synchronize_session=False)

        # Delete articles with a score of 0 or less
        score_deleted = session.query(Article).filter(Article.score <= 0).delete(synchronize_session=False)

        # Total number of deleted articles
        total_deleted = old_deleted + score_deleted  

        session.commit()
        session.close()

        print(f"🗑️ Deleted {old_deleted} articles older than 48 hours.")
        print(f"🗑️ Deleted {score_deleted} articles with a score of 0 or less.")
        print(f"🗑️ Total articles deleted: {total_deleted}.")  # ✅ Added total count



if __name__ == "__main__":
    import sys
    asyncio.run(scrape_articles())
    asyncio.run(update_existing_article_scores()) 
    cleanup_old_articles() 
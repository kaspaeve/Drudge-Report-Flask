import requests
from bs4 import BeautifulSoup
from app import app, db
from models import NewsSource

OPML_SOURCES = {
    "United States": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/countries/with_category/United%20States.opml",
    "Tech": "https://raw.githubusercontent.com/spians/awesome-RSS-feeds/master/recommended/with_category/Tech.opml"
}

def fetch_and_seed_opml(category, opml_url):
    """Fetch and parse OPML file, then insert feeds into the database."""
    response = requests.get(opml_url)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "xml")

        feeds = soup.find_all("outline", recursive=True)
        for feed in feeds:
            title = feed.get("title")
            xml_url = feed.get("xmlUrl")
            description = feed.get("description", "No description available")
            
            if title and xml_url:
                add_feed_to_db(title, xml_url, category, description)
    else:
        print(f"❌ Failed to fetch OPML file: {opml_url}. Status code: {response.status_code}")

def add_feed_to_db(name, url, category, description):
    """Insert a new RSS feed into the database if it doesn't already exist."""
    with app.app_context():
        if not NewsSource.query.filter_by(url=url).first():
            new_source = NewsSource(name=name, url=url, scraping_type="rss", category=category)
            db.session.add(new_source)
            db.session.commit()
            print(f"✅ Added: {name} - {url} (Category: {category})")
        else:
            print(f"⚠️ Already exists: {name} - {url}")

if __name__ == "__main__":
    for category, opml_url in OPML_SOURCES.items():
        print(f"\n🔄 Seeding category: {category} from {opml_url}")
        fetch_and_seed_opml(category, opml_url)

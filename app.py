import re, requests, logging, atexit, asyncio

from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_required, current_user
from models import db, User, Article, OllamaSettings, NewsSource
from auth import auth
from sqlalchemy.orm import sessionmaker, scoped_session
from flask_cors import CORS, cross_origin
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)
app.config.from_object("config.Config")
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
CORS(app, supports_credentials=True)

app.register_blueprint(auth)

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home():
    top_articles = Article.query.order_by(Article.score.desc()).limit(50).all()
    top_article = top_articles[0] if top_articles else None 
    
    return render_template("index.html", top_article=top_article, articles=top_articles, user=current_user)

@app.route("/settings")
@login_required
def settings():
    settings = OllamaSettings.get_settings()
    feeds = NewsSource.query.all()
    return render_template("settings.html", user=current_user, ollama_url=settings.base_url, enabled=settings.enabled, selected_model=settings.selected_model, feeds=feeds)

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.scheme in ["http", "https"] and parsed.netloc)

@app.route("/update-ollama", methods=["GET", "POST"])
@login_required
def update_ollama():
    if request.method == "GET":
        settings = OllamaSettings.get_settings()
        return jsonify({
            "base_url": settings.base_url,
            "enabled": settings.enabled,
            "selected_model": settings.selected_model
        }), 200

    if request.method == "POST":
        data = request.json
        base_url = data.get("base_url")
        enabled = data.get("enabled")
        selected_model = data.get("selected_model")

        if not base_url or not is_valid_url(base_url):
            return jsonify({"error": "Invalid Base URL. Must be HTTP or HTTPS."}), 400

        settings = OllamaSettings.get_settings()
        settings.update_settings(base_url=base_url, enabled=enabled, selected_model=selected_model)

        return jsonify({"message": "✅ Ollama settings updated successfully!"}), 200

@app.route("/get-ollama-models", methods=["GET"])
@login_required
def get_ollama_models():
    settings = OllamaSettings.get_settings()
    tags_url = f"{settings.base_url.rstrip('/')}/api/tags"
    
    logging.info(f"Fetching Ollama models from URL: {tags_url}")

    try:
        response = requests.get(tags_url, timeout=5)
        logging.info(f"Received response {response.status_code} from {tags_url}")
        response.raise_for_status()
        
        models_data = response.json()
        models = [model["model"] for model in models_data.get("models", [])]
        
        logging.info(f"Fetched models: {models}")
        
        return jsonify({"models": models, "selected_model": settings.selected_model}), 200

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch models from {tags_url}: {str(e)}")
        return jsonify({"error": "Failed to fetch models."}), 500


@app.route("/get-feeds", methods=["GET"])
@login_required
def get_feeds():
    feeds = NewsSource.query.all()
    return jsonify({
        "feeds": [
            {
                "id": feed.id,
                "name": feed.name,
                "url": feed.url,
                "category": feed.category,
                "enabled": feed.enabled,
                "scrape_status": feed.scrape_status or "Not scraped"
            } for feed in feeds
        ]
    }), 200

@app.route("/add-feed", methods=["POST"])
@login_required
def add_feed():
    data = request.json
    name = data.get("name")
    url = data.get("url")
    category = data.get("category")
    enabled = data.get("enabled", True)

    if not name or not url or not is_valid_url(url):
        return jsonify({"error": "Invalid feed details."}), 400

    new_feed = NewsSource(name=name, url=url, scraping_type="rss", category=category, enabled=enabled)
    db.session.add(new_feed)
    db.session.commit()
    return jsonify({"message": "✅ RSS feed added successfully!"}), 200

@app.route("/delete-feed/<int:feed_id>", methods=["DELETE"])
@login_required
def delete_feed(feed_id):
    feed = NewsSource.query.get(feed_id)
    if not feed:
        return jsonify({"error": "Feed not found."}), 404
    db.session.delete(feed)
    db.session.commit()
    return jsonify({"message": "✅ RSS feed deleted successfully!"}), 200

@app.route("/update-feed/<int:feed_id>", methods=["PUT"])
@login_required
def update_feed(feed_id):
    feed = NewsSource.query.get(feed_id)
    if not feed:
        return jsonify({"error": "Feed not found."}), 404

    data = request.json
    enabled = data.get("enabled")
    if enabled is None:
        return jsonify({"error": "Missing 'enabled' field."}), 400

    feed.enabled = enabled
    db.session.commit()
    return jsonify({"message": "✅ Feed updated successfully!"}), 200

def run_scraper():
    from scraper import scrape_articles
    asyncio.run(scrape_articles())

@app.route('/api/tags')
def get_tags():
    return {"message": "CORS enabled"}

scheduler = BackgroundScheduler()
scheduler.add_job(func=run_scraper, trigger='cron', hour='*/3')
scheduler.start()

atexit.register(lambda: scheduler.shutdown())


@app.route("/run-jobs", methods=["POST"])
@login_required
def run_jobs():
    try:
        scheduler.add_job(func=run_scraper)
        return jsonify({"message": "Job scheduled to run immediately!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

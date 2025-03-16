import re, requests, logging, atexit, asyncio
from db import db  # Ensure db is initialized in db.py
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_required, current_user
from auth import auth
from sqlalchemy.orm import sessionmaker, scoped_session
from flask_cors import CORS, cross_origin
from apscheduler.schedulers.background import BackgroundScheduler
from flask_socketio import SocketIO, emit
import subprocess
from models import Article, OllamaSettings, NewsSource
from flask import current_app

app = Flask(__name__)
app.config.from_object("config.Config")
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
CORS(app, supports_credentials=True)

socketio = SocketIO(app)
app.register_blueprint(auth)

db.init_app(app)  
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"

@login_manager.user_loader
def load_user(user_id):
    from models import User 
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

def send_logs(process):
    try:
        for line in iter(process.stdout.readline, ""):
            if line:
                socketio.emit('log', {'message': line.strip()})
        process.stdout.close()
        process.wait()
    except Exception as e:
        socketio.emit('log', {'message': f"Error while reading process output: {str(e)}"})
        current_app.logger.error(f"Error while reading process output: {str(e)}")
    finally:
        if process.returncode != 0:
            socketio.emit('log', {'message': f"Process failed with return code: {process.returncode}"})
            current_app.logger.error(f"Process failed with return code: {process.returncode}")
        else:
            socketio.emit('log', {'message': 'Process completed successfully'})


@app.route("/run-jobs", methods=["POST"])
@login_required
def run_jobs():
    try:
        current_app.logger.info("Starting job: scraper.py")

        process = subprocess.Popen(
            ['python3', '-u', 'scraper.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        socketio.emit('log', {'message': 'Job started, running scraper.py...'})
        

        socketio.start_background_task(target=send_logs, process=process)

        return jsonify({"message": "Job scheduled to run immediately!"}), 200

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        current_app.logger.error(error_message)
        socketio.emit('log', {'message': error_message})
        return jsonify({"error": error_message}), 500







@socketio.on('connect')
def handle_connect():
    print('Client connected.')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

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
    # Emit log to frontend when the job starts
    socketio.emit('log', {'message': 'Scraper started...'})
    
    try:
        # Emit log as the scraper works
        socketio.emit('log', {'message': 'Scraping in progress...'})
    except Exception as e:
        socketio.emit('log', {'message': f'Error occurred: {str(e)}'})
    
    # End of the job
    socketio.emit('log', {'message': 'Scraper job completed.'})

@app.route('/api/tags')
def get_tags():
    return {"message": "CORS enabled"}

# Scheduler for periodic scraping jobs every 3 hours
scheduler = BackgroundScheduler()
scheduler.add_job(func=run_scraper, trigger='cron', hour='*/3')
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

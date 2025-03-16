from db import db 
from flask_login import UserMixin
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from flask import jsonify, request

class FeedService:

    @staticmethod
    def add_feed():
        try:
            data = request.get_json()
            name = data.get("name")
            url = data.get("url")
            category = data.get("category")

            if not name or not url or not category:
                print("Missing fields:", {"name": name, "url": url, "category": category})
                return jsonify({"error": "All fields are required."}), 400


            existing_feed = NewsSource.query.filter_by(url=url).first()
            if existing_feed:
                print(f"Duplicate URL found: {url}")
                return jsonify({"error": "Feed URL already exists."}), 400
            print(f"Inserting new feed: {name} - {url}")
            new_feed = NewsSource(name=name, url=url, category=category)
            db.session.add(new_feed)
            db.session.commit()

            return jsonify({"message": f"Feed '{name}' added successfully!"}), 200

        except IntegrityError as e:
            db.session.rollback()
            print(f"Database IntegrityError: {e}")
            return jsonify({"error": "Integrity error occurred: " + str(e)}), 500

        except Exception as e:
            db.session.rollback()
            print(f"Error occurred: {e}")
            return jsonify({"error": "An error occurred: " + str(e)}), 500

class NewsSource(db.Model):
    __tablename__ = "news_source"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    scraping_type = db.Column(db.String(50), nullable=False, default="rss")
    category = db.Column(db.String(100), nullable=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    scrape_status = db.Column(db.String(255), nullable=True)

class Article(db.Model):
    __tablename__ = "article"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512), nullable=False)
    url = db.Column(db.String(1024), unique=True, nullable=False)
    image_url = db.Column(db.String(1024), nullable=True)
    source_id = db.Column(db.Integer, db.ForeignKey("news_source.id"), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(pytz.utc), nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    rss_position = db.Column(db.Integer, nullable=True)

    def age_in_hours(self):
        """Calculates the article's age in hours, considering timezone awareness."""
        if not self.timestamp:
            return 9999
        utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
        timestamp_aware = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=pytz.utc)
        return (utc_now - timestamp_aware).total_seconds() // 3600

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        """Sets password for the user after hashing."""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the hashed password."""
        return check_password_hash(self.password, password)

class OllamaSettings(db.Model):
    __tablename__ = "ollama_settings"

    id = db.Column(db.Integer, primary_key=True)
    base_url = db.Column(db.String(255), nullable=False, default="http://localhost:11434")
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    selected_model = db.Column(db.String(255), nullable=True)

    @staticmethod
    def get_settings():
        """Returns the Ollama settings."""
        settings = OllamaSettings.query.first()
        if not settings:
            settings = OllamaSettings(base_url="http://localhost:11434", enabled=True, selected_model=None)
            db.session.add(settings)
            db.session.commit()
        return settings

    def update_settings(self, base_url=None, enabled=None, selected_model=None):
        """Updates the Ollama settings."""
        if base_url:
            self.base_url = base_url.rstrip("/")
        if enabled is not None:
            self.enabled = enabled
        if selected_model is not None:
            self.selected_model = selected_model
        db.session.commit()

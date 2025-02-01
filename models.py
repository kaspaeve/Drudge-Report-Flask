from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, UTC
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

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
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    rss_position = db.Column(db.Integer, nullable=True)

    def age_in_hours(self):
        if not self.timestamp:
            return 9999
        return (datetime.utcnow() - self.timestamp).total_seconds() // 3600

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class OllamaSettings(db.Model):
    __tablename__ = "ollama_settings"

    id = db.Column(db.Integer, primary_key=True)
    base_url = db.Column(db.String(255), nullable=False, default="http://localhost:11434")
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    selected_model = db.Column(db.String(255), nullable=True)

    @staticmethod
    def get_settings():
        settings = OllamaSettings.query.first()
        if not settings:
            settings = OllamaSettings(base_url="http://localhost:11434", enabled=True, selected_model=None)
            db.session.add(settings)
            db.session.commit()
        return settings

    def update_settings(self, base_url=None, enabled=None, selected_model=None):
        if base_url:
            self.base_url = base_url.rstrip("/")
        if enabled is not None:
            self.enabled = enabled
        if selected_model is not None:
            self.selected_model = selected_model
        db.session.commit()

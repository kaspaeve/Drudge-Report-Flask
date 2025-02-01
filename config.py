import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "supersecretkey"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "news.db")  # SQLite
    # SQLALCHEMY_DATABASE_URI = "postgresql://user:password@localhost/drudge_clone"  # PostgreSQL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

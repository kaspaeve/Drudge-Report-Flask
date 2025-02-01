from app import app, db

# Ensure database tables are created
with app.app_context():
    db.create_all()
    print("✅ Database initialized successfully!")

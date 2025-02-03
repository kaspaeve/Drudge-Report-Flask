# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install necessary packages: git, sqlite3, nano, and tzdata
RUN apt-get update && apt-get install -y git sqlite3 nano tzdata && rm -rf /var/lib/apt/lists/*

# Set the timezone
ENV TZ=America/Chicago

# Set the working directory to /app
WORKDIR /app

# Clone the GitHub repository
RUN git clone https://github.com/kaspaeve/Drudge-Report-Flask.git .

# Copy requirements.txt first (to take advantage of caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Ensure scraper.py runs before starting the application
CMD ["sh", "-c", "python scraper.py && gunicorn --bind 0.0.0.0:5000 app:app"]

# Expose port 5000
EXPOSE 5000

# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Git (needed to clone the repo)
RUN apt-get update && apt-get install -y git

# Set the working directory to /app
WORKDIR /app

# Clone the GitHub repository
RUN git clone https://github.com/kaspaeve/Drudge-Report-Flask.git .

# Copy requirements.txt first (to take advantage of caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose port 5000 (or whichever port your Flask app uses)
EXPOSE 5000

# Start the application using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

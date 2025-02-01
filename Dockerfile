# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory to /app
WORKDIR /app

# Install system dependencies (e.g., gcc for compiling any packages)
RUN apt-get update && apt-get install -y gcc

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project files into the container
COPY . .

# Expose port 5000 (or whichever port your Flask app uses)
EXPOSE 5000

# Start the application using gunicorn.
# This assumes that your Flask instance is defined in app.py as "app"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

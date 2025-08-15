# Use official Python base image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script and languages.json
COPY process_pdfs.py .
COPY languages.json .

# Create input and output folders
RUN mkdir -p /app/input /app/output

# Default command
CMD ["python", "process_pdfs.py", "/app/input", "/app/output", "en"]

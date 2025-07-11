# Use official Python 3.12.1 image
FROM python:3.12.1-slim

# Set workdir
WORKDIR /app

# Install system dependencies for tesseract, poppler, and PIL
RUN apt-get update && \
    apt-get install -y tesseract-ocr poppler-utils libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Entrypoint
CMD ["python", "pdf_split_rotate.py"]

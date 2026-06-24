FROM python:3.12-slim

# System dependencies for Tesseract, Poppler, OpenCV, and HEIF
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libheif-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

COPY . .

# Create persistent data directories
RUN mkdir -p /app/data/storage/uploads

ENV DB_PATH=/app/data/invoice_ocr.db
ENV STORAGE_BASE=/app/data/storage/uploads
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

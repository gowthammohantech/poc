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

# Local working cache for originals, page renders and preprocessed images:
# poppler, OpenCV and Tesseract all need real files on disk. The durable copy
# lives in Azure Blob (AZURE_STORAGE_CONNECTION_STRING), and anything missing
# here is faulted back in on demand, so this no longer has to be a mounted
# volume and a redeploy onto empty disk is recoverable. Mounting one anyway
# just keeps the cache warm across deploys.
RUN mkdir -p /app/data/storage/uploads

ENV STORAGE_BASE=/app/data/storage/uploads
# MONGODB_URI and MONGO_DB_NAME are supplied by the environment.
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

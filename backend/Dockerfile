FROM python:3.12-slim

# System deps: Tesseract OCR (+ Russian/Kazakh), poppler for some PDF ops.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-kaz \
        poppler-utils \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bundled traineddata (rus/kaz/eng) as a fallback if distro packs are absent.
ENV TESSDATA_PREFIX=/app/tessdata

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

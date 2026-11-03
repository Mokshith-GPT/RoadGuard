FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_PATH=/app/models/best.pt

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-model.txt ./requirements-model.txt
RUN pip install -r requirements-model.txt

COPY modules ./modules
COPY model_service.py ./model_service.py
COPY models ./models

EXPOSE 8000
CMD ["uvicorn", "model_service:app", "--host", "0.0.0.0", "--port", "8000"]

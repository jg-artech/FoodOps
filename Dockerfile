FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic.ini ./

EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD sh -c "python -m alembic upgrade head && python -m uvicorn foodops.main:app --host 0.0.0.0 --port 8000 --workers 4"

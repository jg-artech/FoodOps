FROM python:3.10-slim

WORKDIR /app

# Instalar todas las dependencias de compilación
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt ./

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY src/ ./src/
COPY alembic.ini ./

# Expose puerto
EXPOSE 8000

# Set PYTHONPATH a src/
ENV PYTHONPATH=/app/src

# Run (import foodops, no src.foodops)
CMD ["python", "-m", "uvicorn", "foodops.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

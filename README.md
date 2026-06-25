# FoodOps - SaaS Platform for Restaurant Operations

Sistema especializado para gestión de operaciones en restaurantes y puntos de venta de comida.

## Features

- 🍗 POS Digital
- 📋 Gestión de Órdenes (Kanban FIFO)
- 🔥 Gestor inteligente de parrilla
- 📦 Inventario de ingredientes
- 📊 Dashboard gerencial
- 💰 Cierre automático
- 📱 Integraciones: WhatsApp, Telegram, FEL/SAT

## Stack

- Backend: FastAPI + Python 3.13
- Database: PostgreSQL
- Frontend: Vue3 PWA (próximamente)

## Instalación

```bash
# Instalar dependencias
pip install -r requirements.txt

# Crear variables de entorno
cp .env.example .env

# Ejecutar migraciones
alembic upgrade head

# Iniciar servidor
uvicorn src.foodops.main:app --reload
```

## Tests

```bash
pytest -v
```

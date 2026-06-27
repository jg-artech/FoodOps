# FoodOps - Project Context

## Resumen Ejecutivo

FoodOps es una plataforma SaaS para restaurantes QSR en Guatemala.

## Stack Técnico

- Backend: Python 3.13 + FastAPI + PostgreSQL
- Frontend: Vue3 + PWA
- Auth: JWT con bcrypt
- Database: SQLAlchemy async

## Estado Actual

✅ FastAPI corriendo en http://127.0.0.1:8000
✅ PostgreSQL con 5 tablas creadas
✅ APIs de autenticación y órdenes
✅ Tests pasando
✅ Git inicializado
✅ GitHub https://github.com/jg-artech/foodops

## Próximos Pasos

1. Seed data y tests
2. Inventario API
3. Parrilla inteligente
4. Frontend Vue3

## Instrucciones para Copilot

- Mantén async/await en operaciones DB
- Crea schemas Pydantic para inputs/outputs
- Sigue estructura: domain → db → api
- Tests para nuevos endpoints

## Inicio del Proyecto

```bash
cd /home/jg/proyectos/foodops
PYTHONPATH=src python3 -m uvicorn foodops.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs

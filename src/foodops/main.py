"""FastAPI application"""
import logging
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from foodops.api.router_auth import router as auth_router
from foodops.api.router_caja import router as caja_router
from foodops.api.router_config import router as config_router
from foodops.api.router_gerencia import router as gerencia_router
from foodops.api.router_ordenes import router as ordenes_router
from foodops.api.router_stock import router as stock_router

load_dotenv()

logger = logging.getLogger(__name__)

_is_production = os.getenv("APP_ENV") == "production"

app = FastAPI(
    title=os.getenv("APP_NAME", "FoodOps"),
    version="0.1.0",
    description="SaaS Platform for Restaurant Operations",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ordenes_router)
app.include_router(caja_router)
app.include_router(stock_router)
app.include_router(gerencia_router)
app.include_router(config_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    if _is_production:
        return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})
    raise exc


@app.get("/")
def root():
    return {"message": "FoodOps API", "version": "0.1.0", "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": os.getenv("APP_ENV", "development")}

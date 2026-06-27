"""FastAPI application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from foodops.api.router_auth import router as auth_router
from foodops.api.router_ordenes import router as ordenes_router

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "FoodOps"),
    version="0.1.0",
    description="SaaS Platform for Restaurant Operations"
)

# CORS Configuration - PERMITE TODOS LOS ORÍGENES PARA DESARROLLO
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En desarrollo: permitir todos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ordenes_router)

@app.get("/")
def root():
    return {"message": "FoodOps API", "version": "0.1.0", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": os.getenv("APP_ENV", "development")}

@app.post("/test-orden")
def test_orden(data: dict):
    return {"success": True, "message": "Test works", "data": data}

@app.post("/api/test-simple")
def test_simple(data: dict):
    return {"success": True, "data": data}

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

# CORS Middleware
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(auth_router)
app.include_router(ordenes_router)

@app.get("/")
async def root():
    return {
        "message": "FoodOps API",
        "version": "0.1.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": os.getenv("APP_ENV", "development")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "foodops.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

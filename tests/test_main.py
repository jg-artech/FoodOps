"""Tests para main.py"""

from fastapi.testclient import TestClient

from foodops.main import app


def test_root():
    with TestClient(app) as ac:
        response = ac.get("/")
        assert response.status_code == 200
        assert response.json()["message"] == "FoodOps API"


def test_health():
    with TestClient(app) as ac:
        response = ac.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

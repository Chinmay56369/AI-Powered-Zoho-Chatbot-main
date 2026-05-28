from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes_chat import router as chat_router


def test_health_endpoints_return_ok():
    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    for path in ("/health", "/api/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
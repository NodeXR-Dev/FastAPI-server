from fastapi import FastAPI
from app.api.router import api_router

app = FastAPI(title="NodeXR API")

app.include_router(api_router, prefix="/api")


@app.get("/")
def health_check():
    return {
        "message": "NodeXR FastAPI server is running"
    }
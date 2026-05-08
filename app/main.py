from fastapi import FastAPI

from app.storage.minio_client import init_minio

app = FastAPI()


@app.on_event("startup")
def startup():

    init_minio()


@app.get("/")
def root():
    return {
        "message": "NodeXR server running"
    }
from fastapi import APIRouter

# 각 API 파일 import
# from app.api.v1 import test
# from app.api.v1 import utterance
# from app.api.v1 import graph
# from app.api.v1 import asset
# from app.api.v1 import ai

api_router = APIRouter()


# 테스트용
@api_router.get("/")
def root():
    return {
        "message": "NodeXR API v1 running"
    }


# 이후 API 추가 시 사용
# api_router.include_router(
#     test.router,
#     prefix="/test",
#     tags=["Test"]
# )

# api_router.include_router(
#     utterance.router,
#     prefix="/utterances",
#     tags=["Utterances"]
# )

# api_router.include_router(
#     graph.router,
#     prefix="/graph",
#     tags=["Graph"]
# )

# api_router.include_router(
#     asset.router,
#     prefix="/assets",
#     tags=["Assets"]
# )

# api_router.include_router(
#     ai.router,
#     prefix="/ai",
#     tags=["AI"]
# )
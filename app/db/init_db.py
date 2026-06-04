# app/db/init_db.py

from app.db.base import Base
from app.db.session import engine

# 중요: 이 한 줄이 있어야 model/__init__.py 안의 모든 모델이 로드됨
import app.model


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
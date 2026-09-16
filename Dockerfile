FROM python:3.11-slim

WORKDIR /app

# torch 를 그냥 PyPI 에서 받으면 CUDA 빌드가 딸려온다.
# 실측: nvidia 2.7G + triton 691M + torch(CUDA) 1.2G = 이미지 8.89GB.
# 임베딩(ko-sroberta)은 CPU 로만 돌리고 배포 대상 VM 에도 GPU 가 없으므로
# CPU 전용 휠을 먼저 깔아 두면 아래 requirements 설치가 이걸 그대로 쓴다.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 임베딩 모델(약 440MB)을 이미지에 미리 받아 둔다.
# main.py 의 lifespan 이 get_embedding_model() 을 호출하므로, 이게 없으면
# 컨테이너가 뜰 때마다 HuggingFace 에서 내려받고 그게 실패하면 서버 자체가 안 뜬다.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('jhgan/ko-sroberta-multitask')"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

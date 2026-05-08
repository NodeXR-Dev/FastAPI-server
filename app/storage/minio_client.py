from minio import Minio
from app.core.config import settings


client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_USE_SSL,
)


def init_minio():

    bucket_name = settings.MINIO_BUCKET

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

        # public read 설정
        policy = f"""
        {{
          "Version":"2012-10-17",
          "Statement":[
            {{
              "Effect":"Allow",
              "Principal":{{"*":["*"]}},
              "Action":["s3:GetObject"],
              "Resource":["arn:aws:s3:::{bucket_name}/*"]
            }}
          ]
        }}
        """

        client.set_bucket_policy(
            bucket_name,
            policy
        )

        print(f"Bucket created: {bucket_name}")

    else:
        print(f"Bucket already exists: {bucket_name}")
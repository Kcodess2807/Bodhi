from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Proctoring API"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-in-production"

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "proctoring_db"

    #react and vite dev servers!!
    ALLOWED_ORIGINS: List[str]=[
        "http://localhost:3000",  
        "http://localhost:5173",   
    ]

    
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "proctoring-snapshots"


    # camera check and other thresholds
    FRAME_SAMPLE_INTERVAL: int = 3
    IDENTITY_REVERIFY_INTERVAL: int = 30
    FACE_SIMILARITY_THRESHOLD: float = 0.28
    GAZE_DEVIATION_THRESHOLD: float = 30.0
    VIOLATION_AUTO_FLAG_COUNT: int = 5

    # CV model configuration
    FACE_RECOGNITION_MODEL: str = "Facenet512"
    OBJECT_DETECTION_CONFIDENCE: float = 0.5
    YOLO_MODEL_VARIANT: str = "yolov8l"  # nano for local, override to yolov8m on AWS via .env

    class Config:
        env_file=".env"
        env_file_encoding="utf-8"
        extra = "ignore"


settings=Settings()
import os

import dotenv

dotenv.load_dotenv()

# App Settings
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# Database Settings
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Redis Settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# S3 Storage Settings
S3_HOST = os.getenv("S3_HOST", "localhost")
S3_PORT = int(os.getenv("S3_PORT", "9000"))
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_UPLOADS_BUCKET = os.getenv("S3_UPLOADS_BUCKET", "audio-uploads")
S3_RESULTS_BUCKET = os.getenv("S3_RESULTS_BUCKET", "audio-results")

# Model Settings
DEFAULT_MODEL_DEVICE = os.getenv("DEFAULT_MODEL_DEVICE", "cuda")  # or cpu
MODEL_CHUNK_DURATION = float(os.getenv("MODEL_CHUNK_DURATION", "30.0"))
MODEL_CHUNK_OVERLAP = float(os.getenv("MODEL_CHUNK_OVERLAP", "1.0"))

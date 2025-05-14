FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from pyproject.toml
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "boto3>=1.38.13" \
    "click>=8.2.0" \
    "fastapi>=0.104.0" \
    "uvicorn>=0.23.2" \
    "git-lfs>=1.6" \
    "python-dotenv>=1.1.0" \
    "resemble-enhance>=0.0.1" \
    "rq>=2.3.3" \
    "sqlalchemy>=2.0.40" \
    "python-multipart>=0.0.5" \
    "torchaudio>=2.0.0"

# Copy the application code
COPY . .

# Expose the port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"] 
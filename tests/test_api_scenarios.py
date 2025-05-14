import base64
import os
import shutil
import subprocess
import time

import boto3
import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import (
    DATABASE_URL,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    S3_ACCESS_KEY,
    S3_HOST,
    S3_PORT,
    S3_RESULTS_BUCKET,
    S3_SECRET_KEY,
    S3_UPLOADS_BUCKET,
)
from src.database.orm import Base
from src.main import app

TEST_AUDIO_FILE = "tests/data/41601__noisecollector__mysterysnippets.wav"


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        Base.metadata.create_all(engine)

        yield db
    finally:
        db.close()
        os.remove("app.db")


@pytest.fixture(scope="module", autouse=True)
def test_redis():
    try:
        process = subprocess.Popen(["redis-server", "--port", f"{REDIS_PORT}"])
        time.sleep(5)

        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        redis_conn.flushdb()

        yield redis_conn

    finally:
        redis_conn.flushdb()
        process.terminate()


@pytest.fixture(scope="module", autouse=True)
def test_s3():
    process = subprocess.Popen(["minio", "server", "/temp/shared", "--address", f"{S3_HOST}:{S3_PORT}"])
    time.sleep(5)

    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://{S3_HOST}:{S3_PORT}",
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    try:
        s3.create_bucket(Bucket=S3_UPLOADS_BUCKET)
        s3.create_bucket(Bucket=S3_RESULTS_BUCKET)
    except Exception as e:
        print(f"Error creating buckets: {e}")

    yield s3

    process.terminate()
    shutil.rmtree("/temp/shared")


# @pytest.fixture(scope="function", autouse=True)
# def test_worker(test_redis):
#     process = subprocess.Popen(["python", "-m", "src.workers.enhance"], start_new_session=True)
#     time.sleep(10)
#     try:
#         yield
#     finally:
#         process.terminate()


@pytest.fixture(scope="function", autouse=True)
def test_client():
    with TestClient(app) as client:
        time.sleep(5)
        yield client


def get_auth_header(username, password):
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def test_end_to_end_scenario(test_client):
    """Test complete user flow: create account, add tokens, use model, check status"""
    # 1. Create a new user
    user_data = {"username": "testuser", "password": "testpass"}
    response = test_client.post("/users/", data=user_data)
    assert response.status_code == 201
    assert "user_id" in response.json()

    # 2. Add tokens to user account
    auth_header = get_auth_header("testuser", "testpass")
    token_data = {"amount": 100.0}
    response = test_client.post("/tokens/add/", data=token_data, headers=auth_header)
    assert response.status_code == 200
    assert "message" in response.json()

    # 3. Check token balance
    response = test_client.get("/tokens/balance/", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["balance"] == 100.0

    # 4. List available models
    response = test_client.get("/models/", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["name"] == "audio_enhancer"

    # 5. Use model to enhance audio
    assert os.path.exists(TEST_AUDIO_FILE), f"Test audio file not found: {TEST_AUDIO_FILE}"

    with open(TEST_AUDIO_FILE, "rb") as audio_file:
        files = {"audio_file": (os.path.basename(TEST_AUDIO_FILE), audio_file, "audio/wav")}
        data = {"model_name": "audio_enhancer"}
        response = test_client.post("/models/use/", data=data, files=files, headers=auth_header)

    assert response.status_code == 200
    assert "task_id" in response.json()
    task_id = response.json()["task_id"]

    # 6. Check task status
    response = test_client.get(f"/tasks/{task_id}", headers=auth_header)
    assert response.status_code == 200
    while response.json()["status"] != "completed":
        time.sleep(1)
        response = test_client.get(f"/tasks/{task_id}", headers=auth_header)
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
    assert response.json()["status"] == "completed"
    assert "result_path" in response.json()

    # 7. Check token balance again (should be 90 after spending 10)
    response = test_client.get("/tokens/balance/", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["balance"] == 90.0

    # 8. Check usage history
    response = test_client.get("/usage/history/", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["tokens_spent"] == 10.0
    assert response.json()[0]["model"] == "audio_enhancer"


def test_insufficient_tokens(test_client):
    """Test scenario when user has insufficient tokens"""
    # 1. Create a new user
    user_data = {"username": "pooruser", "password": "testpass"}
    response = test_client.post("/users/", data=user_data)
    assert response.status_code == 201

    # 2. Try to use model without adding tokens
    auth_header = get_auth_header("pooruser", "testpass")

    with open(TEST_AUDIO_FILE, "rb") as audio_file:
        files = {"audio_file": (os.path.basename(TEST_AUDIO_FILE), audio_file, "audio/wav")}
        data = {"model_name": "audio_enhancer"}
        response = test_client.post("/models/use/", data=data, files=files, headers=auth_header)

    assert response.status_code == 402  # Payment Required
    assert "Insufficient tokens" in response.json()["detail"]


def test_invalid_credentials(test_client):
    """Test scenario with invalid credentials"""
    auth_header = get_auth_header("nonexistent", "wrongpass")
    response = test_client.get("/tokens/balance/", headers=auth_header)
    assert response.status_code == 401  # Unauthorized


def test_duplicate_username(test_client):
    """Test scenario with duplicate username"""
    # 1. Create first user
    user_data = {"username": "duplicate", "password": "testpass"}
    response = test_client.post("/users/", data=user_data)
    assert response.status_code == 201

    # 2. Try to create user with same username
    response = test_client.post("/users/", data=user_data)
    assert response.status_code == 400  # Bad Request
    assert "Username already exists" in response.json()["detail"]

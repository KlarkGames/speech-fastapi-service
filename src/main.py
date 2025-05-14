import hashlib
import io
from contextlib import asynccontextmanager

import redis
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from rq import Queue
from sqlalchemy.exc import IntegrityError

from src import config
from src.connections import _database_session, _redis_connection
from src.database.billing import Billing
from src.database.orm import Model, Token, UsageHistory, User
from src.file_storages import s3
from src.workers.models_info import MODELS_INFO


@asynccontextmanager
async def lifespan(app: FastAPI):
    with _database_session() as db:
        for model_name, model_info in MODELS_INFO.items():
            if not db.query(Model).filter(Model.name == model_name).first():
                db.add(Model(name=model_name, price=model_info.price))
            db.commit()

    # s3_client = s3.get_s3_client()
    # if config.S3_UPLOADS_BUCKET not in s3_client.list_buckets():
    #     s3_client.create_bucket(Bucket=config.S3_UPLOADS_BUCKET)
    # if config.S3_RESULTS_BUCKET not in s3_client.list_buckets():
    #     s3_client.create_bucket(Bucket=config.S3_RESULTS_BUCKET)

    yield


app = FastAPI(title="Audio Enhancement API with Billing", lifespan=lifespan)
security = HTTPBasic()


# Helper function to hash passwords
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Authentication function
def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):
    with _database_session() as db:
        user = db.query(User).filter(User.username == credentials.username).first()
        if not user or user.password != hash_password(credentials.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return user


@app.post("/users/", status_code=status.HTTP_201_CREATED)
def create_user(username: str = Form(...), password: str = Form(...)):
    with _database_session() as db:
        try:
            hashed_password = hash_password(password)
            user = User(username=username, password=hashed_password)
            db.add(user)
            db.commit()
            db.refresh(user)

            token = Token(user_id=user.id, amount=0.0)
            db.add(token)
            db.commit()

            return {"message": "User created successfully", "user_id": user.id}
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )


@app.post("/tokens/add/")
def add_tokens(amount: float = Form(...), user: User = Depends(authenticate_user)):
    with _database_session() as db:
        billing = Billing(db)
        if billing.add_tokens(user.id, amount):
            return {"message": f"Added {amount} tokens to account"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add tokens",
            )


@app.get("/tokens/balance/")
def get_balance(user: User = Depends(authenticate_user)):
    with _database_session() as db:
        billing = Billing(db)
        balance = billing.get_token_balance(user.id)
        if balance is not None:
            return {"balance": balance}
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token account not found")


@app.get("/usage/history/")
def get_usage_history(
    user: User = Depends(authenticate_user),
    redis_conn: redis.Redis = Depends(_redis_connection),
):
    """Get usage history for the user"""
    with _database_session() as db:
        billing = Billing(db)
        history = billing.get_usage_history(user.id)
        result = []
        for entry in history:
            model_name = db.query(Model.name).filter(Model.id == entry.model_id).scalar()
            # Get presigned URL from Redis if available
            result_url = redis_conn.get(f"task:{entry.id}:result_url")
            result_url = result_url.decode() if result_url else None

            result.append(
                {
                    "model": model_name,
                    "tokens_spent": entry.tokens_spent,
                    "timestamp": entry.timestamp,
                    "result_url": result_url,
                }
            )
        return result


@app.get("/models/")
def list_models():
    """List all available models"""
    with _database_session() as db:
        models = db.query(Model).all()
        return [{"name": model.name, "price": model.price} for model in models]


@app.post("/models/use/")
async def use_model(
    model_name: str = Form(...),
    audio_file: UploadFile = File(...),
    user: User = Depends(authenticate_user),
    redis_conn: redis.Redis = Depends(_redis_connection),
):
    """Use a model to enhance audio, spending tokens"""
    with _database_session() as db:
        billing = Billing(db)

        # Check if model exists
        model = db.query(Model).filter(Model.name == model_name).first()
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        # Try to spend tokens
        if not billing.spend_tokens(user.id, model_name):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient tokens or model not found",
            )

        # Upload file to S3
        contents = await audio_file.read()
        file_data = io.BytesIO(contents)
        s3_object_key = s3.upload_fileobj(
            file_data,
            original_filename=audio_file.filename,
            content_type=audio_file.content_type,
        )

        # Get the latest usage history entry for this transaction
        history_entry = (
            db.query(UsageHistory)
            .filter(UsageHistory.user_id == user.id)
            .order_by(UsageHistory.timestamp.desc())
            .first()
        )

        # Queue the task
        job = Queue(connection=redis_conn).enqueue(
            MODELS_INFO[model_name].worker,
            args=(s3_object_key, history_entry.id),
        )

        db.commit()

    return {
        "message": "Model task queued successfully",
        "job_id": job.id,
        "task_id": history_entry.id,
    }


@app.get("/tasks/{task_id}")
def get_task_status(
    task_id: int,
    user: User = Depends(authenticate_user),
    redis_conn: redis.Redis = Depends(_redis_connection),
):
    with _database_session() as db:
        task = db.query(UsageHistory).filter(UsageHistory.id == task_id, UsageHistory.user_id == user.id).first()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get the result URL from Redis
        result_url = redis_conn.get(f"task:{task_id}:result_url")
        result_url = result_url.decode() if result_url else None

    return {
        "id": task.id,
        "result_url": result_url,
        "tokens_spent": task.tokens_spent,
        "timestamp": task.timestamp,
        "status": task.status,
    }


@app.get("/results/{task_id}")
def get_result(
    task_id: int,
    user: User = Depends(authenticate_user),
    redis_conn: redis.Redis = Depends(_redis_connection),
):
    with _database_session() as db:
        task = db.query(UsageHistory).filter(UsageHistory.id == task_id, UsageHistory.user_id == user.id).first()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get the result URL from Redis
        result_url = redis_conn.get(f"task:{task_id}:result_url")

        if not result_url:
            raise HTTPException(status_code=404, detail="Result not found")

        # Redirect to the presigned URL
    return RedirectResponse(url=result_url.decode())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

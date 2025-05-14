from contextlib import contextmanager

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import config
from src.database.orm import Base


@contextmanager
def _database_session():
    engine = create_engine(config.DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _redis_connection():
    redis_conn = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)
    return redis_conn

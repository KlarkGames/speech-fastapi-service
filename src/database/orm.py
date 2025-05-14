from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    tokens = relationship("Token", back_populates="user")
    usage_history = relationship("UsageHistory", back_populates="user")


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    user = relationship("User", back_populates="tokens")


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    price = Column(Float, nullable=False)
    usage_history = relationship("UsageHistory", back_populates="model")


class UsageHistory(Base):
    __tablename__ = "usage_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    tokens_spent = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))
    status = Column(String(50), nullable=False, default="pending")

    user = relationship("User", back_populates="usage_history")
    model = relationship("Model", back_populates="usage_history")

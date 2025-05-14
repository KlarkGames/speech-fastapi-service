from typing import Optional

from sqlalchemy.orm import Session

from src.database.orm import Model, Token, UsageHistory


class Billing:
    def __init__(self, db_session: Session):
        self.db = db_session

    def add_tokens(self, user_id: int, amount: float) -> bool:
        try:
            token = self.db.query(Token).filter(Token.user_id == user_id).first()
            if not token:
                token = Token(user_id=user_id, amount=amount)
                self.db.add(token)
            else:
                token.amount += amount
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error adding tokens: {e}")
            return False

    def spend_tokens(self, user_id: int, model_name: str) -> bool:
        try:
            token = self.db.query(Token).filter(Token.user_id == user_id).first()
            if not token:
                return False

            model = self.db.query(Model).filter(Model.name == model_name).first()
            if not model:
                return False

            if token.amount < model.price:
                return False

            token.amount -= model.price

            usage = UsageHistory(user_id=user_id, model_id=model.id, tokens_spent=model.price)
            self.db.add(usage)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error spending tokens: {e}")
            return False

    def get_token_balance(self, user_id: int) -> Optional[float]:
        token = self.db.query(Token).filter(Token.user_id == user_id).first()
        return token.amount if token else None

    def get_usage_history(self, user_id: int) -> list:
        return (
            self.db.query(UsageHistory)
            .filter(UsageHistory.user_id == user_id)
            .order_by(UsageHistory.timestamp.desc())
            .all()
        )

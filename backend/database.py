import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "copilot.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    jd_url = Column(String, nullable=True)
    jd_raw_text = Column(Text, nullable=True)
    jd_summary = Column(Text, nullable=True)
    resume_text = Column(Text, nullable=True)
    gap_analysis = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)
    answers = Column(Text, nullable=True)
    tailored_resume = Column(Text, nullable=True)
    cover_letter = Column(Text, nullable=True)
    fit_score = Column(Text, nullable=True)
    status = Column(String, default="uploaded")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def set_json(self, field: str, value):
        setattr(self, field, json.dumps(value) if value is not None else None)

    def get_json(self, field: str):
        raw = getattr(self, field)
        return json.loads(raw) if raw else None


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

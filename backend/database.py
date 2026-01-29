from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()  

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()

# Test connection on startup
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception as e:
    raise RuntimeError(f"Could not connect to database: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


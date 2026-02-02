from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True, future=True)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Database connected successfully, result:", result.scalar())
except Exception as e:
    print("Connection failed:", e)


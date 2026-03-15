import asyncio
import os
from datetime import date
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, Column, String, Boolean, Date, Time, DateTime
from sqlalchemy.orm import DeclarativeBase
import uuid
from datetime import datetime

# Setup basic DB stuff inside the script to avoid import issues
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    fullname = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    place_of_birth = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Simple hash mock or import
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def get_password_hash(password):
        return pwd_context.hash(password)
except:
    def get_password_hash(password):
        return password # fallback

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

async def run():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Check if user exists by querying the table directly
        from sqlalchemy import text
        res = await session.execute(text("SELECT id FROM users WHERE email = 'admin@abrag.com'"))
        row = res.fetchone()
        
        hp = get_password_hash("123456")
        if not row:
            uid = str(uuid.uuid4())
            await session.execute(text(
                "INSERT INTO users (id, email, hashed_password, fullname, date_of_birth, place_of_birth, is_active, is_verified, created_at) "
                "VALUES (:id, :email, :hp, :fullname, :dob, :pob, :ia, :iv, :ca)"
            ), {
                "id": uid, "email": "admin@abrag.com", "hp": hp, "fullname": "Admin User", 
                "dob": date(1990, 1, 1), "pob": "Cairo", "ia": True, "iv": True, "ca": datetime.utcnow()
            })
            print("CREATED")
        else:
            await session.execute(text(
                "UPDATE users SET hashed_password = :hp, is_active = :ia, is_verified = :iv WHERE email = 'admin@abrag.com'"
            ), {"hp": hp, "ia": True, "iv": True})
            print("UPDATED")
        await session.commit()

if __name__ == "__main__":
    asyncio.run(run())

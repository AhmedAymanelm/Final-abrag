import asyncio
import os
from datetime import date
import sys

# Ensure current directory is in path for imports
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.auth.models import User
from app.auth.utils import hash_password, verify_password

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

async def run():
    print(f"Connecting to: {DATABASE_URL.split('@')[-1]}")
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == "admin@abrag.com"))
        user = result.scalar_one_or_none()
        
        new_hp = hash_password("123456")
        
        if not user:
            print("Creating new admin user...")
            user = User(
                email="admin@abrag.com",
                hashed_password=new_hp,
                fullname="Admin User",
                date_of_birth=date(1990, 1, 1),
                place_of_birth="Cairo",
                is_active=True,
                is_verified=True
            )
            session.add(user)
        else:
            print("Updating existing admin user...")
            user.hashed_password = new_hp
            user.is_active = True
            user.is_verified = True
            
        await session.commit()
        print("Commit successful.")
        
        # Verify immediately
        if verify_password("123456", user.hashed_password):
            print("Verification check: PASSED")
        else:
            print("Verification check: FAILED")

if __name__ == "__main__":
    asyncio.run(run())

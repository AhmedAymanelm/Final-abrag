from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "❌ DATABASE_URL environment variable is required but not set. "
        "Please configure it in your .env file."
    )

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session_maker() as session:
        yield session


async def init_db():
    # Import models here to avoid circular imports
    from app.auth.models import User
    from app.models.history import AssessmentHistory
    from app.models.payment import PaymentRecord
    from app.models.settings import SystemSetting

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

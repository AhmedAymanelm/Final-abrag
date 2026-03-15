import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, Date, Time, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    fullname = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    place_of_birth = Column(String, nullable=False)
    time_of_birth = Column(Time, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    profile_picture_url = Column(String, nullable=True)
    verification_code = Column(String(6), nullable=True)
    verification_code_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assessments = relationship("AssessmentHistory", backref="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"

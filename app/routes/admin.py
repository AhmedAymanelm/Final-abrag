from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.models.history import AssessmentHistory

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])

# ─── Schemas ───────────────────────────────────────────────────────────────────
class GrantAdminRequest(BaseModel):
    email: EmailStr

# ─── Admin Guard ───────────────────────────────────────────────────────────────
async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ─── Overview Stats ────────────────────────────────────────────────────────────

@router.get("/stats", summary="Get dashboard key metrics")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one_or_none() or 0
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar_one_or_none() or 0
    total_assessments = (await db.execute(select(func.count(AssessmentHistory.id)))).scalar_one_or_none() or 0
    total_videos = (await db.execute(
        select(func.count(AssessmentHistory.id)).where(AssessmentHistory.video_url.isnot(None))
    )).scalar_one_or_none() or 0
    
    # Breakdown of Users by Age Demographic (for Pie Chart)
    users_dob_result = await db.execute(select(User.date_of_birth).where(User.date_of_birth.isnot(None)))
    dobs = users_dob_result.scalars().all()
    
    age_groups = {"Under 25": 0, "25-34": 0, "35-44": 0, "45+": 0}
    today = datetime.utcnow().date()
    for dob in dobs:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 25: age_groups["Under 25"] += 1
        elif age < 35: age_groups["25-34"] += 1
        elif age < 45: age_groups["35-44"] += 1
        else: age_groups["45+"] += 1
        
    breakdown = {k: v for k, v in age_groups.items() if v > 0}
    if not breakdown:
        breakdown = {"No Data Yet": 1}

    # Journey Completion Rate (Drop-off Analysis)
    users_with_assessments_result = await db.execute(
        select(AssessmentHistory.user_id, AssessmentHistory.assessment_type)
        .order_by(AssessmentHistory.user_id, AssessmentHistory.created_at)
    )
    all_assessments = users_with_assessments_result.all()

    # Track how far each user got
    user_journey = {}
    for user_id, assessment_type in all_assessments:
        if user_id not in user_journey:
            user_journey[user_id] = set()
        user_journey[user_id].add(assessment_type)

    journey_stages = {
        "Only Psychology": 0,
        "Psychology + Neuroscience": 0,
        "Psychology + Neuro + Letter": 0,
        "Psychology + Neuro + Letter + Astrology": 0,
        "Fully Completed": 0
    }

    for user_id, completed_types in user_journey.items():
        if "comprehensive" in completed_types:
            journey_stages["Fully Completed"] += 1
        elif "astrology" in completed_types:
            journey_stages["Psychology + Neuro + Letter + Astrology"] += 1
        elif "letter" in completed_types:
            journey_stages["Psychology + Neuro + Letter"] += 1
        elif "neuroscience" in completed_types:
            journey_stages["Psychology + Neuroscience"] += 1
        elif "psychology" in completed_types:
            journey_stages["Only Psychology"] += 1

    journey_breakdown = {k: v for k, v in journey_stages.items() if v > 0}
    if not journey_breakdown:
        journey_breakdown = {"No Data Yet": 1}

    # New users in last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_users_30d = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= thirty_days_ago)
    )).scalar_one_or_none() or 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_assessments": total_assessments,
        "total_videos": total_videos,
        "new_users_30d": new_users_30d,
        "breakdown": breakdown,
        "journey": journey_breakdown
    }


@router.get("/users/growth", summary="Daily user registration counts (last 14 days)")
async def get_user_growth(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Returns daily registration count for the last 14 days."""
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    # Truncate to date to group by day
    result = await db.execute(
        select(
            func.date(User.created_at).label("day"),
            func.count(User.id).label("count")
        )
        .where(User.created_at >= fourteen_days_ago)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    rows = result.all()

    # Create a map of existing data
    data_map = {row.day: row.count for row in rows}
    
    # Fill in all 14 days, even if 0 registrations
    data = []
    for i in range(14, -1, -1):
        target_date = (datetime.utcnow() - timedelta(days=i)).date()
        count = data_map.get(target_date, 0)
        data.append({
            "month": target_date.strftime("%b %d"), # Keeping key as 'month' so frontend JS doesn't break
            "count": count
        })

    return data


# ─── User Management ───────────────────────────────────────────────────────────

@router.get("/users", summary="Get list of all users")
async def get_users(
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).order_by(User.created_at.desc()).offset(skip).limit(limit))
    users = result.scalars().all()

    # For each user, count their assessments
    user_ids = [u.id for u in users]
    counts_result = await db.execute(
        select(AssessmentHistory.user_id, func.count(AssessmentHistory.id))
        .where(AssessmentHistory.user_id.in_(user_ids))
        .group_by(AssessmentHistory.user_id)
    )
    counts_map = {str(row[0]): row[1] for row in counts_result.all()}

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "fullname": u.fullname,
            "date_of_birth": str(u.date_of_birth) if u.date_of_birth else None,
            "place_of_birth": u.place_of_birth,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "profile_picture_url": u.profile_picture_url,
            "created_at": u.created_at,
            "assessment_count": counts_map.get(str(u.id), 0)
        }
        for u in users
    ]


@router.get("/users/{user_id}/details", summary="Get single user details + their assessments")
async def get_user_details(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assessments_result = await db.execute(
        select(AssessmentHistory)
        .where(AssessmentHistory.user_id == user_id)
        .order_by(AssessmentHistory.created_at.desc())
    )
    assessments = assessments_result.scalars().all()

    return {
        "id": str(user.id),
        "email": user.email,
        "fullname": user.fullname,
        "date_of_birth": str(user.date_of_birth) if user.date_of_birth else None,
        "place_of_birth": user.place_of_birth,
        "time_of_birth": str(user.time_of_birth) if user.time_of_birth else None,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "profile_picture_url": user.profile_picture_url,
        "created_at": user.created_at,
        "assessments": [
            {
                "id": str(a.id),
                "type": a.assessment_type,
                "has_video": a.video_url is not None,
                "video_url": a.video_url,
                "created_at": a.created_at,
            }
            for a in assessments
        ]
    }


@router.post("/users/{user_id}/toggle-status", summary="Toggle user active status")
async def toggle_user_status(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active
    await db.commit()
    return {"message": f"User is now {'Active' if user.is_active else 'Inactive'}", "is_active": user.is_active}


@router.delete("/users/{user_id}", summary="Delete a user and all their data")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
    return {"message": "User deleted successfully"}


# ─── Assessment Management ─────────────────────────────────────────────────────

JOURNEY_STAGES = ["psychology", "neuroscience", "letter", "astrology", "comprehensive"]

@router.get("/assessments/journey", summary="Get user journey progress for all users")
async def get_user_journeys(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    # Get all users who have at least one assessment
    users_result = await db.execute(
        select(User)
        .join(AssessmentHistory, AssessmentHistory.user_id == User.id)
        .distinct()
        .order_by(User.created_at.desc())
    )
    users = users_result.scalars().all()

    # For each user, get their set of completed assessment types
    user_ids = [u.id for u in users]
    assessments_result = await db.execute(
        select(
            AssessmentHistory.user_id,
            AssessmentHistory.assessment_type,
            AssessmentHistory.video_url,
            AssessmentHistory.created_at
        )
        .where(AssessmentHistory.user_id.in_(user_ids))
        .order_by(AssessmentHistory.created_at)
    )
    all_assessments = assessments_result.all()

    # Build per-user data
    user_data = {str(u.id): {
        "id": str(u.id),
        "name": u.fullname,
        "email": u.email,
        "completed_stages": set(),
        "has_video": False,
        "last_activity": None
    } for u in users}

    for row in all_assessments:
        uid = str(row.user_id)
        if uid in user_data:
            user_data[uid]["completed_stages"].add(row.assessment_type.lower())
            if row.video_url:
                user_data[uid]["has_video"] = True
            if not user_data[uid]["last_activity"] or row.created_at > user_data[uid]["last_activity"]:
                user_data[uid]["last_activity"] = row.created_at

    # Format output
    return [
        {
            "id": d["id"],
            "name": d["name"],
            "email": d["email"],
            "has_video": d["has_video"],
            "last_activity": d["last_activity"].isoformat() if d["last_activity"] else None,
            "stages": {
                stage: (stage in d["completed_stages"])
                for stage in JOURNEY_STAGES
            },
            "completed_count": len(d["completed_stages"]),
            "total_stages": len(JOURNEY_STAGES)
        }
        for d in user_data.values()
    ]


@router.get("/assessments", summary="Get all assessments")
async def get_assessments(
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(
        select(AssessmentHistory, User.email.label("user_email"), User.fullname)
        .join(User, AssessmentHistory.user_id == User.id)
        .order_by(AssessmentHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.all()

    return [
        {
            "id": str(item.AssessmentHistory.id),
            "user_id": str(item.AssessmentHistory.user_id),
            "user_email": item.user_email,
            "user_name": item.fullname,
            "type": item.AssessmentHistory.assessment_type,
            "has_video": item.AssessmentHistory.video_url is not None,
            "video_url": item.AssessmentHistory.video_url,
            "created_at": item.AssessmentHistory.created_at
        }
        for item in items
    ]


@router.get("/assessments/{assessment_id}/result", summary="Get full result data of an assessment")
async def get_assessment_result(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(
        select(AssessmentHistory, User.email.label("user_email"), User.fullname)
        .join(User, AssessmentHistory.user_id == User.id)
        .where(AssessmentHistory.id == assessment_id)
    )
    item = result.first()
    if not item:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return {
        "id": str(item.AssessmentHistory.id),
        "user_email": item.user_email,
        "user_name": item.fullname,
        "type": item.AssessmentHistory.assessment_type,
        "input_data": item.AssessmentHistory.input_data,
        "result_data": item.AssessmentHistory.result_data,
        "video_url": item.AssessmentHistory.video_url,
        "created_at": item.AssessmentHistory.created_at
    }


@router.delete("/assessments/{assessment_id}", summary="Delete an assessment record")
async def delete_assessment(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(AssessmentHistory).where(AssessmentHistory.id == assessment_id))
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await db.delete(assessment)
    await db.commit()
    return {"message": "Assessment deleted successfully"}


# ─── System Health ─────────────────────────────────────────────────────────────

@router.get("/health", summary="System health and API key status")
async def get_system_health(
    admin: User = Depends(get_admin_user)
):
    import os

    keys_to_check = [
        ("OPENAI_API_KEY", "OpenAI"),
        ("STABILITY_API_KEY", "Stability AI"),
        ("D_ID_API_KEY", "D-ID"),
        ("DATABASE_URL", "Database"),
        ("SECRET_KEY", "JWT Secret"),
        ("CLOUDINARY_CLOUD_NAME", "Cloudinary"),
    ]

    health_status = {}
    all_ok = True
    for env_key, label in keys_to_check:
        val = os.getenv(env_key)
        configured = bool(val and len(val) > 5)
        if not configured:
            all_ok = False
        health_status[label] = {
            "configured": configured,
            "status": "✓ Active" if configured else "✗ Missing"
        }

    return {
        "overall": "healthy" if all_ok else "degraded",
        "services": health_status,
        "platform": "Abrag Admin Engine",
        "checked_at": datetime.utcnow().isoformat()
    }


# ─── Admin User Management ─────────────────────────────────────────────────────

@router.get("/admins", summary="List all admin users")
async def list_admins(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(
        select(User).where(User.is_admin == True)
    )
    admins = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.fullname,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in admins
    ]


@router.post("/admins/grant", summary="Grant admin access to a user by email")
async def grant_admin(
    body: GrantAdminRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found with that email")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="User is already an admin")
    user.is_admin = True
    await db.commit()
    return {"message": f"✅ {user.fullname} ({user.email}) is now an admin"}


@router.delete("/admins/revoke/{user_id}", summary="Revoke admin access from a user")
async def revoke_admin(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot revoke your own admin access")
    user.is_admin = False
    await db.commit()
    return {"message": f"❌ Admin access revoked for {user.fullname} ({user.email})"}

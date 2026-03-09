"""Announcement endpoints for the High School Management System API."""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Request payload for creating or updating an announcement."""

    message: str = Field(..., min_length=3, max_length=300)
    expiration_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class AnnouncementResponse(BaseModel):
    """API response model for an announcement."""

    id: str
    message: str
    expiration_date: str
    start_date: Optional[str] = None


def _validate_teacher_access(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Validate that the request is authorized by a signed-in teacher."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _parse_date(value: str, field_name: str) -> date:
    """Parse an ISO date string and return a date object."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format") from exc


def _to_response(doc: Dict[str, Any]) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=str(doc["_id"]),
        message=doc["message"],
        expiration_date=doc["expiration_date"],
        start_date=doc.get("start_date")
    )


@router.get("", response_model=List[AnnouncementResponse])
@router.get("/", response_model=List[AnnouncementResponse])
def list_announcements() -> List[AnnouncementResponse]:
    """List all announcements sorted by expiration date ascending."""
    docs = announcements_collection.find({}).sort("expiration_date", 1)
    return [_to_response(doc) for doc in docs]


@router.get("/active", response_model=List[AnnouncementResponse])
def list_active_announcements() -> List[AnnouncementResponse]:
    """List currently active announcements for the public banner."""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": ""},
            {"start_date": {"$lte": today}}
        ]
    }
    docs = announcements_collection.find(query).sort("expiration_date", 1)
    return [_to_response(doc) for doc in docs]


@router.post("", response_model=AnnouncementResponse)
@router.post("/", response_model=AnnouncementResponse)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Create a new announcement. Requires authentication."""
    _validate_teacher_access(teacher_username)

    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    expiration_date = _parse_date(payload.expiration_date, "expiration_date")
    start_date = None
    if payload.start_date:
        start_date = _parse_date(payload.start_date, "start_date")
        if start_date > expiration_date:
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be after expiration date"
            )

    document: Dict[str, Any] = {
        "_id": str(uuid4()),
        "message": clean_message,
        "expiration_date": expiration_date.isoformat(),
        "start_date": start_date.isoformat() if start_date else None
    }

    result = announcements_collection.insert_one(document)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _to_response(created)


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Update an existing announcement. Requires authentication."""
    _validate_teacher_access(teacher_username)

    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    expiration_date = _parse_date(payload.expiration_date, "expiration_date")
    start_date = None
    if payload.start_date:
        start_date = _parse_date(payload.start_date, "start_date")
        if start_date > expiration_date:
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be after expiration date"
            )

    update_result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": clean_message,
                "expiration_date": expiration_date.isoformat(),
                "start_date": start_date.isoformat() if start_date else None
            }
        }
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to read updated announcement")

    return _to_response(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement. Requires authentication."""
    _validate_teacher_access(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import BookingStatus, User
from app.schemas.booking import BookingCreate, BookingOut
from app.schemas.common import Page, PageParams, page_params
from app.services import bookings

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut, status_code=201)
def create_booking(
    data: BookingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return bookings.create_booking(db, user, data)


@router.get("/", response_model=Page[BookingOut])
def list_my_bookings(
    status: BookingStatus | None = None,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = bookings.list_bookings(db, user, page, status)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return bookings.get_booking(db, user, booking_id)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return bookings.cancel_booking(db, user, booking_id)

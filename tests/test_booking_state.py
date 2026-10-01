import pytest

from app.core.exceptions import ConflictError
from app.models import Booking, BookingStatus
from app.services.bookings import move_to


@pytest.mark.parametrize(
    "start,end",
    [
        (BookingStatus.PENDING, BookingStatus.CONFIRMED),
        (BookingStatus.PENDING, BookingStatus.FAILED),
        (BookingStatus.FAILED, BookingStatus.CONFIRMED),
        (BookingStatus.CONFIRMED, BookingStatus.CANCELLED),
    ],
)
def test_allowed_moves(start, end):
    b = Booking(status=start)
    move_to(b, end)
    assert b.status == end


@pytest.mark.parametrize(
    "start,end",
    [
        (BookingStatus.CANCELLED, BookingStatus.CONFIRMED),
        (BookingStatus.CANCELLED, BookingStatus.PENDING),
        (BookingStatus.CONFIRMED, BookingStatus.FAILED),
        (BookingStatus.CONFIRMED, BookingStatus.PENDING),
    ],
)
def test_blocked_moves(start, end):
    with pytest.raises(ConflictError):
        move_to(Booking(status=start), end)

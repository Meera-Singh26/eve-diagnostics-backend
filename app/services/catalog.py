from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest
from app.schemas.catalog import CentreCreate, OfferingCreate, TestCreate
from app.schemas.common import PageParams


def _count(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


def create_test(db: Session, data: TestCreate) -> DiagnosticTest:
    if db.scalar(select(DiagnosticTest.id).where(func.lower(DiagnosticTest.name) == data.name.lower())):
        raise ConflictError("A test with this name already exists")
    test = DiagnosticTest(name=data.name, description=data.description)
    db.add(test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("A test with this name already exists")
    return test


def list_tests(db: Session, page: PageParams, q: str | None) -> tuple[list[DiagnosticTest], int]:
    stmt = select(DiagnosticTest)
    if q:
        stmt = stmt.where(DiagnosticTest.name.ilike(f"%{q}%"))
    total = _count(db, stmt)
    rows = db.scalars(stmt.order_by(DiagnosticTest.name).limit(page.limit).offset(page.offset)).all()
    return list(rows), total


def create_centre(db: Session, data: CentreCreate) -> DiagnosticCentre:
    exists = db.scalar(
        select(DiagnosticCentre.id).where(
            func.lower(DiagnosticCentre.name) == data.name.lower(),
            func.lower(DiagnosticCentre.city) == data.city.lower(),
        )
    )
    if exists:
        raise ConflictError("A centre with this name already exists in this city")
    centre = DiagnosticCentre(name=data.name, city=data.city, address=data.address)
    db.add(centre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("A centre with this name already exists in this city")
    return centre


def _centre_query():
    return select(DiagnosticCentre).options(
        selectinload(DiagnosticCentre.offerings).selectinload(CentreTest.test)
    )


def get_centre(db: Session, centre_id: int) -> DiagnosticCentre:
    centre = db.scalar(_centre_query().where(DiagnosticCentre.id == centre_id))
    if centre is None:
        raise NotFoundError("Centre not found")
    return centre


def list_centres(
    db: Session, page: PageParams, city: str | None, test_id: int | None
) -> tuple[list[DiagnosticCentre], int]:
    stmt = select(DiagnosticCentre)
    if city:
        stmt = stmt.where(func.lower(DiagnosticCentre.city) == city.lower())
    if test_id:
        stmt = stmt.where(DiagnosticCentre.offerings.any(CentreTest.test_id == test_id))
    total = _count(db, stmt)
    rows = db.scalars(
        stmt.options(selectinload(DiagnosticCentre.offerings).selectinload(CentreTest.test))
        .order_by(DiagnosticCentre.name, DiagnosticCentre.id)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return list(rows), total


def add_offering(db: Session, centre_id: int, data: OfferingCreate) -> DiagnosticCentre:
    centre = get_centre(db, centre_id)
    if db.get(DiagnosticTest, data.test_id) is None:
        raise NotFoundError("Test not found")
    if any(o.test_id == data.test_id for o in centre.offerings):
        raise ConflictError("This centre already offers this test")
    db.add(CentreTest(centre_id=centre_id, test_id=data.test_id, price=data.price))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This centre already offers this test")
    db.expire(centre)
    return get_centre(db, centre_id)

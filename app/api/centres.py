from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.schemas.catalog import CentreCreate, CentreOut, OfferingCreate
from app.schemas.common import Page, PageParams, page_params
from app.services import catalog

router = APIRouter(prefix="/centres", tags=["centres"])


@router.get("/", response_model=Page[CentreOut])
def list_centres(
    city: str | None = Query(default=None, max_length=80),
    test_id: int | None = Query(default=None, gt=0),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    items, total = catalog.list_centres(db, page, city, test_id)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    return catalog.get_centre(db, centre_id)


@router.post("/", response_model=CentreOut, status_code=201, dependencies=[Depends(require_admin)])
def create_centre(data: CentreCreate, db: Session = Depends(get_db)):
    return catalog.get_centre(db, catalog.create_centre(db, data).id)


@router.post(
    "/{centre_id}/tests",
    response_model=CentreOut,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def add_test_to_centre(centre_id: int, data: OfferingCreate, db: Session = Depends(get_db)):
    return catalog.add_offering(db, centre_id, data)

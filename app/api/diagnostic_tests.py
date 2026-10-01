from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.schemas.catalog import TestCreate, TestOut
from app.schemas.common import Page, PageParams, page_params
from app.services import catalog

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("/", response_model=Page[TestOut])
def list_tests(
    q: str | None = Query(default=None, max_length=100),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    items, total = catalog.list_tests(db, page, q)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("/", response_model=TestOut, status_code=201, dependencies=[Depends(require_admin)])
def create_test(data: TestCreate, db: Session = Depends(get_db)):
    return catalog.create_test(db, data)

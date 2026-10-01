"""Creates tables, an admin user and a little sample catalogue. Safe to run more than once."""
from decimal import Decimal

from sqlalchemy import select

from app import models
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine

TESTS = [
    ("Complete Blood Count", "Red cells, white cells and platelets"),
    ("Lipid Profile", "Cholesterol and triglycerides"),
    ("HbA1c", "Average blood sugar over three months"),
    ("Thyroid Profile (T3, T4, TSH)", None),
    ("Vitamin D (25-OH)", None),
]

CENTRES = {
    ("Eve Diagnostics Andheri", "Mumbai", "12 Link Road, Andheri West"): {
        "Complete Blood Count": "350.00",
        "Lipid Profile": "600.00",
        "HbA1c": "500.00",
    },
    ("Eve Diagnostics Indiranagar", "Bengaluru", "80 Feet Road, Indiranagar"): {
        "Complete Blood Count": "400.00",
        "Thyroid Profile (T3, T4, TSH)": "750.00",
        "Vitamin D (25-OH)": "1200.00",
    },
    ("Eve Diagnostics Saket", "Delhi", "Press Enclave Road, Saket"): {
        "Lipid Profile": "550.00",
        "HbA1c": "450.00",
        "Vitamin D (25-OH)": "1100.00",
    },
}


def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        email = settings.seed_admin_email.lower()
        if not db.scalar(select(models.User).where(models.User.email == email)):
            db.add(
                models.User(
                    email=email,
                    full_name="Admin",
                    hashed_password=hash_password(settings.seed_admin_password),
                    is_admin=True,
                )
            )

        tests = {}
        for name, description in TESTS:
            test = db.scalar(select(models.DiagnosticTest).where(models.DiagnosticTest.name == name))
            if test is None:
                test = models.DiagnosticTest(name=name, description=description)
                db.add(test)
            tests[name] = test
        db.flush()

        for (name, city, address), prices in CENTRES.items():
            centre = db.scalar(
                select(models.DiagnosticCentre).where(
                    models.DiagnosticCentre.name == name, models.DiagnosticCentre.city == city
                )
            )
            if centre is None:
                centre = models.DiagnosticCentre(name=name, city=city, address=address)
                db.add(centre)
                db.flush()
                for test_name, price in prices.items():
                    db.add(
                        models.CentreTest(centre_id=centre.id, test_id=tests[test_name].id, price=Decimal(price))
                    )
        db.commit()
    print(f"Seeded. Admin login: {settings.seed_admin_email}")


if __name__ == "__main__":
    run()

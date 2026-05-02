from __future__ import annotations

import asyncio
import csv
import logging
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sqlmodel import select  # noqa: E402

from database.database_helper import db_helper  # noqa: E402
from models.user import (  # noqa: E402
    Doctor,
    Gender,
    GlucoseReading,
    Patient,
    Role,
    User,
)
from utils.security import get_password_hash  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("seed")

DATA_DIR = ROOT / "data"

SEED_DOCTOR_EMAIL = "seed-doctor@local"
SEED_DOCTOR_PASSWORD = "seed-pass-change-me"  # noqa: S105
SEED_PASSWORD = "patient-pass-change-me"  # noqa: S105
BATCH_SIZE = 2_000


async def get_or_create_seed_doctor(session) -> Doctor:
    stmt = select(User).where(User.email == SEED_DOCTOR_EMAIL)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None:
        user = User(
            email=SEED_DOCTOR_EMAIL,
            hashed_password=get_password_hash(SEED_DOCTOR_PASSWORD),
            role=Role.doctor,
        )
        session.add(user)
        await session.flush()

        doctor = Doctor(
            id=user.id,
            first_name="Seed",
            last_name="Doctor",
            birth_date=date(1980, 1, 1),
            gender=Gender.male,
        )
        session.add(doctor)
        await session.commit()
        logger.info("Created seed doctor id=%s", doctor.id)
        return doctor

    doctor = await session.get(Doctor, user.id)
    if doctor is None:
        doctor = Doctor(
            id=user.id,
            first_name="Seed",
            last_name="Doctor",
            birth_date=date(1980, 1, 1),
            gender=Gender.male,
        )
        session.add(doctor)
        await session.commit()
    return doctor


async def get_or_create_patient(
    session, pt_id: str, age_years: float, sex_letter: str, doctor_id: uuid.UUID
) -> Patient:
    email = f"seed-{pt_id.lower().replace('.', '-')}@local"

    stmt = select(User).where(User.email == email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is not None:
        patient = await session.get(Patient, user.id)
        if patient is not None:
            return patient

    user = User(
        email=email,
        hashed_password=get_password_hash(SEED_PASSWORD),
        role=Role.patient,
    )
    session.add(user)
    await session.flush()

    today = date.today()
    birth_year = today.year - int(round(age_years))
    birth_date = date(birth_year, 1, 1)

    gender = Gender.male if sex_letter.upper() == "M" else Gender.female

    patient = Patient(
        id=user.id,
        first_name="Patient",
        last_name=pt_id,
        birth_date=birth_date,
        gender=gender,
        doctor_id=doctor_id,
    )
    session.add(patient)
    await session.commit()
    logger.info(
        "Created patient pt_id=%s id=%s age=%.0f sex=%s",
        pt_id,
        patient.id,
        age_years,
        sex_letter,
    )
    return patient


async def import_csv_for_patient(session, csv_path: Path, doctor_id: uuid.UUID) -> None:
    logger.info("Reading %s", csv_path.name)

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        logger.warning("%s is empty — skipping", csv_path.name)
        return

    pt_id = rows[0]["PtID"]
    age = float(rows[0]["Age"])
    sex = rows[0]["Sex"]

    patient = await get_or_create_patient(session, pt_id, age, sex, doctor_id)

    stmt = (
        select(GlucoseReading.ts)
        .where(GlucoseReading.patient_id == patient.id)
        .order_by(GlucoseReading.ts.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    last_ts = (await session.execute(stmt)).scalar_one_or_none()
    if last_ts is not None:
        logger.info(
            "Measurements already exist for %s (last %s) — adding only newer ones",
            pt_id,
            last_ts,
        )
    else:
        logger.info("No measurements yet for %s — importing everything", pt_id)

    inserted = 0
    skipped = 0
    batch: list[GlucoseReading] = []

    for row in rows:
        ts = datetime.fromisoformat(row["ts"]).replace(tzinfo=UTC)
        if last_ts is not None and ts <= last_ts:
            skipped += 1
            continue

        glucose_str = row["GlucoseCGM"]
        if not glucose_str or glucose_str.lower() == "nan":
            skipped += 1
            continue

        batch.append(
            GlucoseReading(
                patient_id=patient.id,
                ts=ts,
                glucose=float(glucose_str),
                source="cgm",
            )
        )

        if len(batch) >= BATCH_SIZE:
            session.add_all(batch)
            await session.commit()
            inserted += len(batch)
            batch.clear()

    if batch:
        session.add_all(batch)
        await session.commit()
        inserted += len(batch)

    logger.info("%s: inserted %d measurements, skipped %d", pt_id, inserted, skipped)


async def main() -> None:
    csv_files = sorted(DATA_DIR.glob("*_WISDM.csv"))
    if not csv_files:
        logger.error("No *_WISDM.csv found in %s", DATA_DIR)
        sys.exit(1)

    async with db_helper.session_factory() as session:
        doctor = await get_or_create_seed_doctor(session)
        for csv_path in csv_files:
            await import_csv_for_patient(session, csv_path, doctor.id)

    await db_helper.dispose()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())

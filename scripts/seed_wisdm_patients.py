from __future__ import annotations

import asyncio
import csv
import logging
import random
import sys
from datetime import UTC, date, datetime, timedelta
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

NUM_SLICES = 3
BATCH_SIZE = 2_000

RNG = random.Random(42)

DOCTOR_FIRST_NAMES_M = ["James", "Michael", "Robert", "David", "Thomas", "Daniel"]
DOCTOR_FIRST_NAMES_F = ["Sarah", "Emily", "Rachel", "Anna", "Laura", "Jessica"]
DOCTOR_LAST_NAMES = [
    "Anderson",
    "Mitchell",
    "Carter",
    "Bennett",
    "Foster",
    "Hayes",
    "Sullivan",
    "Reed",
    "Hughes",
    "Coleman",
]

PATIENT_FIRST_NAMES_M = [
    "Liam",
    "Noah",
    "Oliver",
    "Ethan",
    "Lucas",
    "Mason",
    "Logan",
    "Henry",
    "Alexander",
    "Benjamin",
    "William",
    "Jacob",
    "Sebastian",
    "Owen",
    "Caleb",
]
PATIENT_FIRST_NAMES_F = [
    "Olivia",
    "Emma",
    "Ava",
    "Sophia",
    "Isabella",
    "Mia",
    "Charlotte",
    "Amelia",
    "Harper",
    "Evelyn",
    "Abigail",
    "Ella",
    "Scarlett",
    "Grace",
    "Lily",
]
PATIENT_LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Wilson",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "King",
    "Wright",
    "Scott",
    "Green",
    "Baker",
    "Adams",
    "Nelson",
    "Hill",
]


def random_doctor_name() -> tuple[str, str, Gender]:
    gender = RNG.choice([Gender.male, Gender.female])
    first_pool = DOCTOR_FIRST_NAMES_M if gender == Gender.male else DOCTOR_FIRST_NAMES_F
    return RNG.choice(first_pool), RNG.choice(DOCTOR_LAST_NAMES), gender


def random_patient_name(sex_letter: str) -> tuple[str, str]:
    pool = PATIENT_FIRST_NAMES_M if sex_letter.upper() == "M" else PATIENT_FIRST_NAMES_F
    return RNG.choice(pool), RNG.choice(PATIENT_LAST_NAMES)


SEED_DOCTOR_EMAIL = "doctor@example.com"
SEED_DOCTOR_PASSWORD = "doctor-pass"  # noqa: S105
SEED_PATIENT_PASSWORD = "patient-pass"  # noqa: S105


async def get_or_create_seed_doctor(session) -> Doctor:
    stmt = select(User).where(User.email == SEED_DOCTOR_EMAIL)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None:
        first, last, gender = random_doctor_name()
        user = User(
            email=SEED_DOCTOR_EMAIL,
            hashed_password=get_password_hash(SEED_DOCTOR_PASSWORD),
            role=Role.doctor,
        )
        session.add(user)
        await session.flush()

        doctor = Doctor(
            id=user.id,
            first_name=first,
            last_name=last,
            birth_date=date(1980, 1, 1),
            gender=gender,
        )
        session.add(doctor)
        await session.commit()
        logger.info(
            "Created doctor: %s %s (email=%s, id=%s)",
            first,
            last,
            SEED_DOCTOR_EMAIL,
            doctor.id,
        )
        return doctor

    doctor = await session.get(Doctor, user.id)
    if doctor is None:
        first, last, gender = random_doctor_name()
        doctor = Doctor(
            id=user.id,
            first_name=first,
            last_name=last,
            birth_date=date(1980, 1, 1),
            gender=gender,
        )
        session.add(doctor)
        await session.commit()
    logger.info("Doctor already exists: %s %s", doctor.first_name, doctor.last_name)
    return doctor


async def get_or_create_patient(
    session,
    *,
    email: str,
    age_years: float,
    sex_letter: str,
    doctor_id,
    slice_idx: int,
    pt_id: str,
) -> tuple[Patient, bool]:
    """Returns (Patient, created) — created=True if just created."""
    stmt = select(User).where(User.email == email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is not None:
        patient = await session.get(Patient, user.id)
        if patient is not None:
            return patient, False

    first, last = random_patient_name(sex_letter)

    user = User(
        email=email,
        hashed_password=get_password_hash(SEED_PATIENT_PASSWORD),
        role=Role.patient,
    )
    session.add(user)
    await session.flush()

    today = date.today()
    birth_year = today.year - int(round(age_years))
    birth_date_val = date(birth_year, 1, 1)

    gender = Gender.male if sex_letter.upper() == "M" else Gender.female

    patient = Patient(
        id=user.id,
        first_name=first,
        last_name=last,
        birth_date=birth_date_val,
        gender=gender,
        doctor_id=doctor_id,
    )
    session.add(patient)
    await session.commit()
    logger.info(
        "Created patient: %s %s (email=%s, source=%s slice=%d)",
        first,
        last,
        email,
        pt_id,
        slice_idx,
    )
    return patient, True


def slice_rows(rows: list[dict], num_slices: int) -> list[list[dict]]:
    """Slices a list of CSV rows into num_slices consecutive chunks."""
    n = len(rows)
    size = n // num_slices
    slices = []
    for i in range(num_slices):
        start = i * size
        end = (i + 1) * size if i < num_slices - 1 else n
        slices.append(rows[start:end])
    return slices


def shift_to_now(
    rows: list[dict], anchor_now: datetime
) -> list[tuple[datetime, float]]:
    if not rows:
        return []

    parsed = [
        (datetime.fromisoformat(r["ts"]).replace(tzinfo=UTC), float(r["GlucoseCGM"]))
        for r in rows
        if r.get("GlucoseCGM") and r["GlucoseCGM"].lower() != "nan"
    ]
    if not parsed:
        return []

    last_original = parsed[-1][0]
    delta = anchor_now - last_original
    return [(ts + delta, glucose) for ts, glucose in parsed]


async def import_csv_for_patient(
    session,
    csv_path: Path,
    doctor_id,
    *,
    num_slices: int,
    anchor_now: datetime,
) -> None:
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

    slices = slice_rows(rows, num_slices)
    for slice_idx, slice_rows_data in enumerate(slices):
        if not slice_rows_data:
            continue

        slug = pt_id.lower().replace(".", "-").replace("_", "-")
        email = f"patient-{slug}-s{slice_idx + 1}@example.com"

        # "Now" for this slice is anchor_now minus a random 0–6 hours,
        # just so patients don't have exactly the same 1-to-1 timestamps.
        per_slice_now = anchor_now - timedelta(minutes=RNG.randint(0, 6 * 60))

        patient, created = await get_or_create_patient(
            session,
            email=email,
            age_years=age,
            sex_letter=sex,
            doctor_id=doctor_id,
            slice_idx=slice_idx + 1,
            pt_id=pt_id,
        )

        if not created:
            # Check: if there are already readings for this patient, do not load
            # a second time. We don't try to append — that would create time gaps.
            stmt = (
                select(GlucoseReading.id)
                .where(GlucoseReading.patient_id == patient.id)
                .limit(1)
            )
            already = (await session.execute(stmt)).scalar_one_or_none()
            if already is not None:
                logger.info(
                    "Patient %s %s already has readings — skipping import",
                    patient.first_name,
                    patient.last_name,
                )
                continue

        shifted = shift_to_now(slice_rows_data, per_slice_now)
        if not shifted:
            logger.warning("Slice %d of %s is empty", slice_idx + 1, pt_id)
            continue

        batch: list[GlucoseReading] = []
        inserted = 0
        for ts, glucose in shifted:
            batch.append(
                GlucoseReading(
                    patient_id=patient.id,
                    ts=ts,
                    glucose=glucose,
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

        logger.info(
            "  %s %s: inserted %d readings (from %s to %s)",
            patient.first_name,
            patient.last_name,
            inserted,
            shifted[0][0].isoformat(timespec="minutes"),
            shifted[-1][0].isoformat(timespec="minutes"),
        )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main() -> None:
    csv_files = sorted(DATA_DIR.glob("*_WISDM.csv"))
    if not csv_files:
        logger.error("No *_WISDM.csv found in %s", DATA_DIR)
        sys.exit(1)

    # All slices are oriented around a single "anchor now" — the moment the script is run.
    anchor_now = datetime.now(UTC)

    async with db_helper.session_factory() as session:
        doctor = await get_or_create_seed_doctor(session)
        for csv_path in csv_files:
            await import_csv_for_patient(
                session,
                csv_path,
                doctor.id,
                num_slices=NUM_SLICES,
                anchor_now=anchor_now,
            )

    await db_helper.dispose()
    logger.info("Done.")
    logger.info("Doctor login: %s / %s", SEED_DOCTOR_EMAIL, SEED_DOCTOR_PASSWORD)
    logger.info("Patient login: <their email> / %s", SEED_PATIENT_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GlucoseReadingCreate(BaseModel):
    ts: datetime
    glucose: float = Field(..., ge=20.0, le=600.0, description="Глюкоза у mg/dL")
    source: str = Field(default="cgm")


class GlucoseReadingBatchCreate(BaseModel):
    readings: list[GlucoseReadingCreate]


class GlucoseReadingResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    ts: datetime
    glucose: float
    source: str


class PredictionPointResponse(BaseModel):
    ts: datetime
    glucose: float
    minutes_ahead: int


class PredictionResponse(BaseModel):
    patient_id: uuid.UUID
    horizon_min: int
    last_observed_ts: datetime
    last_observed_glucose: float
    predictions: list[PredictionPointResponse]

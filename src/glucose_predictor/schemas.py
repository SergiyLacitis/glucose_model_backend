from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GlucoseReading(BaseModel):
    ts: datetime
    glucose: float = Field(..., ge=20.0, le=600.0, description="Glucose in mg/dL")


class PatientInfo(BaseModel):
    age: float = Field(..., ge=0.0, le=120.0)
    sex: Literal["M", "F"]
    pt_mean: float | None = Field(
        None,
        description="Patient's mean glucose (mg/dL). If None, it is calculated from history",
    )
    pt_std: float | None = Field(
        None,
        description="Patient's glucose std. If None, it is calculated from history",
    )


class PredictionPoint(BaseModel):
    ts: datetime
    glucose: float
    minutes_ahead: int


class PredictionResult(BaseModel):
    predictions: list[PredictionPoint]
    horizon_min: int
    last_observed_ts: datetime
    last_observed_glucose: float

    @field_validator("predictions")
    @classmethod
    def must_be_nonempty(cls, v):
        if not v:
            raise ValueError("predictions cannot be empty")
        return v

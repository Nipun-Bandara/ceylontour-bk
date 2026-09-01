"""GET /api/dashboard/summary — the authority overview (features.md F8)."""

from pydantic import BaseModel, Field

from api.schemas.common import Band


class BandCounts(BaseModel):
    low: int = Field(ge=0)
    medium: int = Field(ge=0)
    high: int = Field(ge=0)


class HighPressureDestination(BaseModel):
    destination_id: int
    name: str
    region: str
    predicted_pressure: float = Field(ge=0, le=100)
    band: Band


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class DashboardSummaryData(BaseModel):
    destinations_monitored: int = Field(ge=0)
    band_counts: BandCounts
    highest_pressure: list[HighPressureDestination]
    recommended_action: str
    # Global SHAP view for the pressure model.
    global_feature_importance: list[FeatureImportance]

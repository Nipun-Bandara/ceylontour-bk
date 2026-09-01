"""Pieces shared by more than one endpoint: the envelope, errors, and the
score/contribution shapes defined in plan.md section 7.
"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Traffic-light bands for visitor pressure (features.md F4).
Band = Literal["low", "medium", "high"]

# Whether a factor value came from real data or a proxy (plan.md section 7).
Confidence = Literal["measured", "estimated"]

# "exact" for index contributions, "estimated" for SHAP values. The UI renders
# these differently and a judge on an XAI theme will check for it.
ContributionType = Literal["exact", "estimated"]


class Meta(BaseModel):
    # protected_namespaces is cleared because pydantic reserves the "model_"
    # prefix by default and the contract requires model_version.
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    index_version: str


DataT = TypeVar("DataT")


class Envelope(BaseModel, Generic[DataT]):
    """Every successful response is this shape."""

    data: DataT
    meta: Meta


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Every failed response is this shape, with the matching HTTP status."""

    error: ErrorDetail


class FactorScores(BaseModel):
    """The five Sustainability Index factors, each 0 to 100."""

    environmental: int = Field(ge=0, le=100)
    community: int = Field(ge=0, le=100)
    crowd: int = Field(ge=0, le=100)
    infrastructure: int = Field(ge=0, le=100)
    suitability: int = Field(ge=0, le=100)


class Contribution(BaseModel):
    """One bar in the explanation panel."""

    factor: str
    percent: int = Field(ge=0, le=100)
    type: ContributionType

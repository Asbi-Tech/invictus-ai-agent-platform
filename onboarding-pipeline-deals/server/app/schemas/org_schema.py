from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class OrgCreateRequest(BaseModel):
    name: str


class OrgJoinRequest(BaseModel):
    org_id: int
    migrate_data: bool = False


class OrgSettingsUpdate(BaseModel):
    custom_prompt: Optional[str] = None
    classification_limit: Optional[int] = None
    vectorization_limit: Optional[int] = None


class OrgResponse(BaseModel):
    id: int
    name: str
    classification_limit: int
    vectorization_limit: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgQuotaResponse(BaseModel):
    id: int
    name: str
    classification_used: int
    classification_limit: int
    vectorization_used: int
    vectorization_limit: int
    member_count: int
    custom_prompt: Optional[str] = None
    processing_timeout_hours: float

    model_config = {"from_attributes": True}


class OrgListItem(BaseModel):
    id: int
    name: str
    member_count: int

    model_config = {"from_attributes": True}

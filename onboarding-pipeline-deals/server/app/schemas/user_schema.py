from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DriveFolder(BaseModel):
    id: str
    label: str


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    refresh_token: Optional[str] = None


class UserUpdate(BaseModel):
    refresh_token: Optional[str] = None
    folder_id: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    company_name: Optional[str] = None
    custom_prompt: Optional[str] = None


class OrgBrief(BaseModel):
    id: int
    name: str
    classification_limit: int
    vectorization_limit: int

    model_config = {"from_attributes": True}


class UserResponse(UserBase):
    id: int
    organization_id: Optional[int] = None
    organization: Optional[OrgBrief] = None
    needs_org: bool = False
    folder_id: Optional[str] = None
    folder_ids: Optional[list[DriveFolder]] = None
    company_name: Optional[str] = None
    custom_prompt: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

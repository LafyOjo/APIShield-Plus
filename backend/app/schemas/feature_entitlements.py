from typing import Optional

from pydantic import BaseModel


class FeatureEntitlementRead(BaseModel):
    feature: str
    enabled: bool
    source: str
    source_plan_id: Optional[int]

    class Config:
        orm_mode = True

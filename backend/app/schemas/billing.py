from pydantic import BaseModel


class CheckoutSessionCreate(BaseModel):
    plan_key: str


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionResponse(BaseModel):
    portal_url: str

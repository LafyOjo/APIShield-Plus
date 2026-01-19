from typing import Optional

from pydantic import BaseModel


class MapSummaryPoint(BaseModel):
    count: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    asn_number: Optional[int] = None
    asn_org: Optional[str] = None
    is_datacenter: Optional[bool] = None


class MapSummaryResponse(BaseModel):
    items: list[MapSummaryPoint]


class MapDrilldownCountry(BaseModel):
    country_code: Optional[str] = None
    count: int


class MapDrilldownCity(BaseModel):
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    count: int


class MapDrilldownASN(BaseModel):
    asn_number: Optional[int] = None
    asn_org: Optional[str] = None
    count: int


class MapDrilldownIpHash(BaseModel):
    ip_hash: str
    count: int


class MapDrilldownPath(BaseModel):
    path: str
    count: int


class MapDrilldownResponse(BaseModel):
    countries: list[MapDrilldownCountry]
    cities: list[MapDrilldownCity]
    asns: list[MapDrilldownASN]
    ip_hashes: list[MapDrilldownIpHash]
    paths: list[MapDrilldownPath]

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.core.db import Base


class GeoEventAgg(Base):
    __tablename__ = "geo_event_aggs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "bucket_start",
            "event_category",
            "severity",
            "country_code",
            "region",
            "city",
            "latitude",
            "longitude",
            "asn_number",
            "asn_org",
            "is_datacenter",
            name="uq_geo_event_aggs_bucket_dims",
        ),
        Index("ix_geo_event_aggs_tenant_bucket", "tenant_id", "bucket_start"),
        Index(
            "ix_geo_event_aggs_tenant_website_bucket",
            "tenant_id",
            "website_id",
            "bucket_start",
        ),
        Index(
            "ix_geo_event_aggs_tenant_bucket_country",
            "tenant_id",
            "bucket_start",
            "country_code",
        ),
        Index(
            "ix_geo_event_aggs_tenant_bucket_latlon",
            "tenant_id",
            "bucket_start",
            "latitude",
            "longitude",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    bucket_start = Column(DateTime, nullable=False, index=True)
    event_category = Column(String, nullable=False)
    severity = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    asn_number = Column(Integer, nullable=True)
    asn_org = Column(String, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)
    count = Column(Integer, nullable=False, default=0)
    is_demo = Column(Boolean, nullable=False, default=False)

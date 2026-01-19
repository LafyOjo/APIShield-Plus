# ADR 0003: Geo-IP enrichment strategy
Status: Accepted  
Date: 2026-01-18

## Problem
APIShield+ needs to enrich client IPs into coarse geo and ASN metadata for security analytics. We must choose a strategy that scales with SaaS volume, respects privacy, and avoids unpredictable costs.

## Options considered
- **Option A: Local Geo DB (MMDB-style)**  
  Use a periodically updated IP database (City + ASN).  
  Pros: predictable cost, low latency, no per-request billing.  
  Cons: requires a scheduled data refresh and file distribution.

- **Option B: Geo-IP API provider**  
  Call an external API per lookup.  
  Pros: easiest initial setup.  
  Cons: variable cost at scale, latency, and external dependency.

## Decision
Adopt **Option A: Local Geo DB** as the default strategy. The system will support an API provider via configuration for early prototypes or special deployments, but production defaults to local DB files.

## Privacy notes
- Geo data is approximate and derived from IPs; it is **not** GPS-grade.  
- IP hashing and retention policies still apply; geo enrichment should not bypass privacy rules.  
- No raw IP is exposed to the UI unless explicitly enabled for admins within the retention window.

## Data accuracy expectations
- Country/region/city are **best-effort** and may be wrong or missing.  
- ASN data is used for coarse network grouping, not identity.  
- Enrichment should always be treated as advisory for analytics, not as an authorization signal.

## Update schedule
- Local Geo DB files must be updated on a regular cadence (monthly minimum).  
- A background job or CI/CD sync task should fetch updated MMDB files and place them at the configured paths.

## Configuration
- `GEO_PROVIDER=local|api`
- `GEO_DB_PATH=/data/geo/GeoLite2-City.mmdb`
- `GEO_ASN_DB_PATH=/data/geo/GeoLite2-ASN.mmdb`
- `GEO_API_KEY=` (only if provider is `api`)
- `GEO_API_BASE_URL=` (only if provider is `api`)

## Consequences
- Geo enrichment is centralized behind a provider interface; ingestion and analytics should call it, not implement geo logic themselves.
- Deployments must supply or mount the MMDB files for local mode.
- API mode remains optional and is not the default for production.

# Dev Tooling and Commands

## Backend
- `make fmt` — run isort + black + ruff format on `backend/`.
- `make lint` — run ruff lint checks.
- `make test` — run pytest.
- Config: `pyproject.toml` sets rules for Black, isort, Ruff (unused imports, timezone-aware datetime, no bare except, etc.).
- Pre-commit: install with `pip install pre-commit && pre-commit install` (uses Black, isort, Ruff, and basic sanity hooks).

## Frontend
- `npm run lint` — eslint over `src/` with hooks/unused-var rules.
- `npm run format` — prettier across JS/JSX/JSON/CSS/MD.
- Config: `.eslintrc.json`, `.eslintignore`, `.prettierrc`.

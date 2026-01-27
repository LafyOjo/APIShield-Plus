import os
from datetime import datetime

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.alerts import Alert  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402

client = TestClient(app)




def test_stats_endpoint():
    token = create_access_token({"sub": "user"})
    with SessionLocal() as db:
        user = create_user(db, username='user', password_hash=get_password_hash('pw'))
        tenant = create_tenant(db, name="Stats Tenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role="viewer",
            created_by_user_id=user.id,
        )
        tenant_slug = tenant.slug
        db.add(
            Alert(
                tenant_id=tenant.id,
                ip_address='1.1.1.1',
                total_fails=1,
                detail='Failed login',
                timestamp=datetime(2023, 1, 1, 0, 0, 0),
            )
        )
        db.add(
            Alert(
                tenant_id=tenant.id,
                ip_address='1.1.1.1',
                total_fails=2,
                detail='Blocked: too many failures',
                timestamp=datetime(2023, 1, 1, 0, 1, 0),
            )
        )
        db.add(
            Alert(
                tenant_id=tenant.id,
                ip_address='1.1.1.1',
                total_fails=3,
                detail='Blocked: invalid chain token',
                timestamp=datetime(2023, 1, 1, 0, 2, 0),
            )
        )
        db.commit()

    resp = client.get(
        '/api/alerts/stats',
        headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': tenant_slug},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]['invalid'] == 1
    assert data[1]['blocked'] == 1
    assert data[2]['blocked'] == 1

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

client = TestClient(app)




def test_stats_endpoint():
    token = create_access_token({"sub": "user"})
    with SessionLocal() as db:
        create_user(db, username='user', password_hash=get_password_hash('pw'))
        db.add(
            Alert(
                ip_address='1.1.1.1',
                total_fails=1,
                detail='Failed login',
                timestamp=datetime(2023, 1, 1, 0, 0, 0),
            )
        )
        db.add(
            Alert(
                ip_address='1.1.1.1',
                total_fails=2,
                detail='Blocked: too many failures',
                timestamp=datetime(2023, 1, 1, 0, 1, 0),
            )
        )
        db.add(
            Alert(
                ip_address='1.1.1.1',
                total_fails=3,
                detail='Blocked: invalid chain token',
                timestamp=datetime(2023, 1, 1, 0, 2, 0),
            )
        )
        db.commit()

    resp = client.get('/api/alerts/stats', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]['invalid'] == 1
    assert data[1]['blocked'] == 1
    assert data[2]['blocked'] == 1

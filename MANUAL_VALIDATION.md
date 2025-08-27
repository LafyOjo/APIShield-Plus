# Minimal Manual Validation Steps

The following checklist verifies basic end-to-end functionality of the demo stack.

1. **Start backend and run migrations**
   ```bash
   cd backend
   source .venv/bin/activate  # or create a venv and install requirements
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

2. **Start frontend dashboard**
   ```bash
   cd frontend
   npm install
   npm start
   ```

3. **Start Demo Shop**
   ```bash
   cd demo-shop
   npm install
   npm start
   ```

4. **From Demo Shop UI**
   - Attempt login for `alice` with a wrong password → a new event should appear with `action=login`, `success=false`, `source=demo-shop`.
   - Log in successfully as `alice` → a new event should appear with `action=login`, `success=true`, `source=demo-shop`.

5. **Run AttackSim stuffing attempt**
   - Open the AttackSim page in the dashboard and run a stuffing simulation targeting `alice`.
   - Expect a burst of events: multiple `action=stuffing_attempt`, `success=false` followed by one `success=true`, all with `source=apishield+`.

6. **Check dashboard table**
   - Visit the dashboard's *Recent Auth Activity* table and confirm the rows are ordered by descending `id`.

7. **Inspect raw events**
   ```bash
   curl 'http://localhost:8001/events/auth?limit=10' | jq
   ```
   Example output (IDs in descending order):
   ```json
   [
     {
       "id": 10,
       "user": "alice",
       "action": "stuffing_attempt",
       "success": true,
       "source": "apishield+",
       "created_at": "2024-05-21T12:35:40.123456"
     },
     {
       "id": 9,
       "user": "alice",
       "action": "stuffing_attempt",
       "success": false,
       "source": "apishield+",
       "created_at": "2024-05-21T12:35:39.987654"
     },
     {
       "id": 8,
       "user": "alice",
       "action": "stuffing_attempt",
       "success": false,
       "source": "apishield+",
       "created_at": "2024-05-21T12:35:39.876543"
     },
     {
       "id": 7,
       "user": "alice",
       "action": "stuffing_attempt",
       "success": false,
       "source": "apishield+",
       "created_at": "2024-05-21T12:35:39.765432"
     },
     {
       "id": 6,
       "user": "alice",
       "action": "login",
       "success": true,
       "source": "demo-shop",
       "created_at": "2024-05-21T12:34:10.000000"
     },
     {
       "id": 5,
       "user": "alice",
       "action": "login",
       "success": false,
       "source": "demo-shop",
       "created_at": "2024-05-21T12:33:58.000000"
     }
   ]
   ```

Actual IDs and timestamps will vary between runs.

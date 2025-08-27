FROM python:3.12-slim
WORKDIR /app

# install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy your code
COPY app/ ./app

# run uvicorn on 0.0.0.0 so it’s reachable in-cluster
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

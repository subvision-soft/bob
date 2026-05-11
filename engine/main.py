from collections import defaultdict, deque

import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

import time
from statistics import mean

from engine.routers.dependencies import validate_token
from engine.routers.private import event
from engine.routers.public import token, news

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    token.router,
    prefix="/api/token",
    tags=["token"],
    responses={404: {"description": "Not found"}},
)

app.include_router(
    event.router,
    prefix="/api/events",
    tags=["target"],
    dependencies=[Depends(validate_token)],
    responses={404: {"description": "Not found"}},
)

app.include_router(
    news.router,
    prefix="/news",
    tags=["news"],
    responses={404: {"description": "Not found"}})


@app.get("/health")
def health():
    return {"status": "ok"}


MAX_RECORDS = 100
response_times = defaultdict(lambda: deque(maxlen=MAX_RECORDS))


@app.middleware("http")
async def log_response_time(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    end_time = time.time()

    if response.status_code == 200:
        endpoint = request.url.path
        duration = end_time - start_time
        response_times[endpoint].append(duration)

    return response


@app.get("/metrics")
async def get_average_response_times():
    averages = {endpoint: mean(times) for endpoint, times in response_times.items() if times}
    return {"average_response_times": averages}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        port=9000,
    )

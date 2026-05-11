from datetime import timedelta
import datetime
from fastapi import APIRouter
import jwt

from engine.routers.dependencies import SECRET_KEY, ALGORITHM, TOKENS

TOKEN_EXPIRATION_HOURS = 3600

router = APIRouter()

@router.get("/")
def generate_token():
    expiration = datetime.datetime.now(datetime.timezone.utc) + timedelta(hours=TOKEN_EXPIRATION_HOURS)
    token = jwt.encode({
        "exp": expiration}, SECRET_KEY, algorithm=ALGORITHM)
    TOKENS[token] = expiration
    return {"token": token, "expiration": expiration}

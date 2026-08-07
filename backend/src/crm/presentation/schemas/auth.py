from pydantic import BaseModel


class LoginIn(BaseModel):
    password: str

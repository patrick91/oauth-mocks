from pydantic import BaseModel


class GoogleUserInfo(BaseModel):
    sub: str
    email: str
    email_verified: bool
    name: str
    given_name: str
    picture: str

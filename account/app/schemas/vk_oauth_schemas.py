from pydantic import BaseModel


class VKOAuthStartResponse(BaseModel):
    authorize_url: str


class VKGroupOption(BaseModel):
    id: int
    name: str
    screen_name: str
    photo_100: str | None = None


class VKOAuthCallbackResult(BaseModel):
    payload: str
    groups: list[VKGroupOption]


class VKOAuthConfirmRequest(BaseModel):
    payload: str
    group_id: int
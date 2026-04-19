from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    items: list

"""Authentication request and profile schemas."""

from pydantic import BaseModel, Field

from app.db.models import WorkerType


class SignupCredentials(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class StudentSignup(SignupCredentials):
    pass


class WardenSignup(SignupCredentials):
    pass


class WorkerSignup(SignupCredentials):
    worker_type: WorkerType


class ProfileOut(BaseModel):
    id: int
    name: str
    email: str
    role: str

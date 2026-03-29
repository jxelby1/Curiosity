from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=120)
    display_name: str = Field(min_length=2, max_length=120)


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=120)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class AuthForgotPasswordRequest(BaseModel):
    email: EmailStr


class AuthForgotPasswordResponse(BaseModel):
    message: str
    debug_reset_token: str | None = None


class AuthResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=120)


class AuthResetPasswordResponse(BaseModel):
    message: str


class AuthUserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    onboarding_state: str
    subscription_tier: str
    dev_tools_enabled: bool = False
    xp: int
    level: int
    preferences: dict
    current_goal_summary: str
    created_at: datetime
    updated_at: datetime

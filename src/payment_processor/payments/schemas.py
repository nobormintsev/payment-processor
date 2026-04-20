from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from payment_processor.payments.enums import Currency, PaymentStatus


class CreatePaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl


class CreatePaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID = Field(alias="id", serialization_alias="payment_id")
    status: PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="payment_metadata")
    status: PaymentStatus
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from payment_processor.payments.enums import Currency


class PaymentCreatedV1(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["payment.created.v1"] = "payment.created.v1"
    occurred_at: datetime

    payment_id: UUID
    amount: Decimal
    currency: Currency
    webhook_url: str

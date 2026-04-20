from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Header, status

from payment_processor.core.security import require_api_key
from payment_processor.payments.schemas import (
    CreatePaymentResponse,
    CreatePaymentRequest,
    PaymentResponse,
)
from payment_processor.payments.deps import get_payment_service
from payment_processor.payments.service import PaymentService

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    path="",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Создать платёж",
)
async def create_payment(
    data: CreatePaymentRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            description="Уникальный ключ для защиты от дублей",
        ),
    ],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> CreatePaymentResponse:
    payment = await service.create_payment(idempotency_key=idempotency_key, data=data)
    return CreatePaymentResponse.model_validate(payment)


@router.get(
    path="/payments/{payment_id}",
    response_model=PaymentResponse,
    summary="Получить платёж",
)
async def get_payment(
    payment_id: Annotated[
        UUID,
        Path(
            description="ID платежа",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentResponse:
    payment = await service.get_payment(payment_id)
    return PaymentResponse.model_validate(payment)

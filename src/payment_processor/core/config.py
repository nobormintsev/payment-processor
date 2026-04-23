from pydantic import Field, PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from payment_processor.core.enums import LogLevel


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="POSTGRES_",
        extra="ignore",
    )

    host: str
    port: PositiveInt = 5432
    user: str
    password: SecretStr
    db: str

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RabbitSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RABBITMQ_",
        extra="ignore",
    )

    host: str
    port: PositiveInt = 5672
    user: str
    password: SecretStr
    vhost: str = "/"

    @property
    def url(self) -> str:
        return (
            f"amqp://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.vhost}"
        )


class PaymentsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PAYMENTS_",
        extra="ignore",
    )

    processing_min_seconds: PositiveFloat = 2.0
    processing_max_seconds: PositiveFloat = 5.0
    success_rate: PositiveFloat = 0.9

    webhook_timeout_seconds: PositiveFloat = 5.0
    webhook_max_retries: PositiveInt = 3

    # TTL retry-очередей - длина = лимит попыток до DLQ
    retry_schedule_ms: tuple[PositiveInt, ...] = (1_000, 5_000, 25_000)


class OutboxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OUTBOX_",
        extra="ignore",
    )

    poll_interval_seconds: PositiveFloat = 1.0
    batch_size: PositiveInt = 100
    max_publish_attempts: PositiveInt = 10


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: LogLevel = LogLevel.INFO
    log_json: bool = False

    api_key: SecretStr = Field(description="Статический ключ для X-API-Key")

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbit: RabbitSettings = Field(default_factory=RabbitSettings)
    payments: PaymentsSettings = Field(default_factory=PaymentsSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)


# Значения подтянутся из env_file через model_config
settings = AppSettings()

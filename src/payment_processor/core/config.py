from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from payment_processor.core.enums import Environment, LogLevel


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="POSTGRES_",
        extra="ignore",
    )

    host: str
    port: int = 5432
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
    port: int = 5672
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

    processing_min_seconds: float = 2.0
    processing_max_seconds: float = 5.0
    success_rate: float = 0.9

    webhook_timeout_seconds: float = 5.0
    webhook_max_retries: int = 3

    consumer_max_retries: int = 3


class OutboxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OUTBOX_",
        extra="ignore",
    )

    poll_interval_seconds: float = 1.0
    batch_size: int = 100


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.LOCAL
    log_level: LogLevel = LogLevel.INFO
    log_json: bool = False

    api_key: SecretStr = Field(description="Статический ключ для X-API-Key")

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbit: RabbitSettings = Field(default_factory=RabbitSettings)
    payments: PaymentsSettings = Field(default_factory=PaymentsSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)


settings = AppSettings()

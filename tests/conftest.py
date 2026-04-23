import os

# Проставляем переменные окружения ДО импорта приложения - AppSettings
# инициализируется на импорте и требует API_KEY и Postgres/RabbitMQ параметры.
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("RABBITMQ_HOST", "localhost")
os.environ.setdefault("RABBITMQ_USER", "test")
os.environ.setdefault("RABBITMQ_PASSWORD", "test")

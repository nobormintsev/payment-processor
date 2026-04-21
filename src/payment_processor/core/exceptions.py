class AppError(Exception):
    """Базовое исключение приложения."""


class NotFoundError(AppError):
    """Ресурс не найден."""


class ConflictError(AppError):
    """Конфликт состояния (дубль, нарушение инварианта и т.п.)."""

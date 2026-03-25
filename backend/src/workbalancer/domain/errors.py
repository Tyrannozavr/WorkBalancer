class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class LimitExceededError(DomainError):
    pass

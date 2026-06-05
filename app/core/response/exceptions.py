from app.core.response.code import ResponseCode

class BaseCustomException(Exception):
    def __init__(self, code: ResponseCode, message: str | None = None):
        self.code = code
        self.message = message
        super().__init__(message)


class BadRequestException(BaseCustomException):
    pass


class NotFoundException(BaseCustomException):
    pass


class ServerException(BaseCustomException):
    pass

class UnauthorizedException(BaseCustomException):
    pass
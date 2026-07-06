from app.core.response.code import ResponseCode


class BaseWSException(Exception):
    def __init__(
        self,
        *,
        code: ResponseCode,
        message: str | None = None,
        detail: str | None = None,
        failed_event_type: str | None = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.failed_event_type = failed_event_type
        super().__init__(message or detail)


class WSBadRequestException(BaseWSException):
    def __init__(
        self,
        *,
        message: str | None = None,
        detail: str | None = None,
        failed_event_type: str | None = None,
    ):
        super().__init__(
            code=ResponseCode.WS400,
            message=message,
            detail=detail,
            failed_event_type=failed_event_type,
        )


class WSNotFoundException(BaseWSException):
    def __init__(
        self,
        *,
        message: str | None = None,
        detail: str | None = None,
        failed_event_type: str | None = None,
    ):
        super().__init__(
            code=ResponseCode.WS404,
            message=message,
            detail=detail,
            failed_event_type=failed_event_type,
        )


class WSConflictException(BaseWSException):
    def __init__(
        self,
        *,
        message: str | None = None,
        detail: str | None = None,
        failed_event_type: str | None = None,
    ):
        super().__init__(
            code=ResponseCode.WS409,
            message=message,
            detail=detail,
            failed_event_type=failed_event_type,
        )


class WSServerException(BaseWSException):
    def __init__(
        self,
        *,
        message: str | None = None,
        detail: str | None = None,
        failed_event_type: str | None = None,
    ):
        super().__init__(
            code=ResponseCode.WS500,
            message=message,
            detail=detail,
            failed_event_type=failed_event_type,
        )
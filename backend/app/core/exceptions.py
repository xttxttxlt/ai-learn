from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("exceptions")


class AppError(Exception):
    """业务异常基类：统一以 HTTP 200 + 业务 code 返回。"""

    code: int = 5000
    message: str = "服务器内部错误，请稍后重试"

    def __init__(self, message: str | None = None, code: int | None = None):
        self.message = message or self.__class__.message
        self.code = code if code is not None else self.__class__.code
        super().__init__(self.message)


class ValidationError(AppError):
    code = 4000
    message = "请求参数校验失败"


class QuizGenerationError(AppError):
    code = 4001
    message = "题库生成失败，请稍后重试"


class ReportGenerationError(AppError):
    code = 4002
    message = "报告生成失败，请稍后重试"


class ContentFilteredError(AppError):
    code = 4003
    message = "内容可能包含敏感信息，请调整后重试"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", path=request.url.path, code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("validation_error", path=request.url.path, errors=exc.errors())
    return JSONResponse(
        status_code=200,
        content={
            "code": ValidationError.code,
            "message": ValidationError.message,
            "data": {"errors": exc.errors()},
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=200,
        content={"code": 5000, "message": "服务器内部错误，请稍后重试", "data": None},
    )

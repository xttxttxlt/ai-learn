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


class WechatLoginError(AppError):
    code = 4004
    message = "微信登录失败，请稍后重试"


class KnowledgeBaseError(AppError):
    code = 4005
    message = "知识库操作失败，请稍后重试"


class DocumentProcessingError(AppError):
    code = 4006
    message = "文档处理失败，请稍后重试"


class KnowledgeBaseUnavailableError(AppError):
    code = 4007
    message = "知识库服务未配置或不可用，请检查 Embedding 配置"


class UnauthorizedError(AppError):
    code = 4010
    message = "未登录或登录已过期，请重新登录"


class NotFoundError(AppError):
    code = 4040
    message = "记录不存在"


class ServiceUnavailableError(AppError):
    code = 5001
    message = "服务暂时不可用，请稍后重试"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", path=request.url.path, code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


def _json_safe_errors(exc: RequestValidationError) -> list[dict]:
    """Pydantic 的 ctx.error 可能是异常对象，需转成字符串后再返回。"""
    errors = []
    for error in exc.errors():
        item = dict(error)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: str(value) if isinstance(value, BaseException) else value
                for key, value in ctx.items()
            }
        errors.append(item)
    return errors


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("validation_error", path=request.url.path, errors=exc.errors())
    return JSONResponse(
        status_code=200,
        content={
            "code": ValidationError.code,
            "message": ValidationError.message,
            "data": {"errors": _json_safe_errors(exc)},
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=200,
        content={"code": 5000, "message": "服务器内部错误，请稍后重试", "data": None},
    )

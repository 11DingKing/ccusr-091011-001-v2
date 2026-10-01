"""
全局异常处理模块
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404

logger = logging.getLogger('apps')


class BusinessException(Exception):
    """业务异常基类"""
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


class AuthenticationException(BusinessException):
    """认证异常"""
    def __init__(self, message="认证失败"):
        super().__init__(message, code=401)


class PermissionException(BusinessException):
    """权限异常"""
    def __init__(self, message="权限不足"):
        super().__init__(message, code=403)


class NotFoundException(BusinessException):
    """资源不存在异常"""
    def __init__(self, message="资源不存在"):
        super().__init__(message, code=404)


def _log_exception(exc, status_code):
    """
    按响应级别区分日志：
    - 4xx 属于用户输入/权限类问题，记 WARNING 且不带堆栈，避免污染错误日志
    - 5xx 才是真正的服务器异常，记 ERROR 并保留完整堆栈
    """
    if status_code >= 500:
        logger.error(f"Server exception occurred: {exc}", exc_info=True)
    else:
        logger.warning(f"Client request rejected ({status_code}): {exc}")


def custom_exception_handler(exc, context):
    """
    自定义异常处理器
    """
    # 处理业务异常
    if isinstance(exc, BusinessException):
        _log_exception(exc, exc.code)
        return Response({
            'success': False,
            'code': exc.code,
            'message': exc.message,
            'data': None
        }, status=exc.code)

    # 处理Django验证异常
    if isinstance(exc, DjangoValidationError):
        _log_exception(exc, 400)
        message = exc.message if hasattr(exc, 'message') else str(exc)
        return Response({
            'success': False,
            'code': 400,
            'message': str(message),
            'data': None
        }, status=status.HTTP_400_BAD_REQUEST)

    # 处理404异常
    if isinstance(exc, Http404):
        _log_exception(exc, 404)
        return Response({
            'success': False,
            'code': 404,
            'message': '资源不存在',
            'data': None
        }, status=status.HTTP_404_NOT_FOUND)

    # 调用默认的异常处理
    response = exception_handler(exc, context)

    if response is not None:
        _log_exception(exc, response.status_code)
        # 统一响应格式
        custom_response_data = {
            'success': False,
            'code': response.status_code,
            'message': response.data.get('detail', '请求失败') if isinstance(response.data, dict) else str(response.data),
            'data': None
        }
        response.data = custom_response_data
        return response

    # 处理未捕获的异常（真正的服务器内部错误）
    _log_exception(exc, 500)
    return Response({
        'success': False,
        'code': 500,
        'message': '服务器内部错误',
        'data': None
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

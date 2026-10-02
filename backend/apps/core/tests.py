"""
核心模块测试用例
"""
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from .exceptions import (
    BusinessException, AuthenticationException,
    PermissionException, NotFoundException, InvalidParameterException,
    custom_exception_handler
)
from .pagination import (
    parse_pagination_params, paginate_queryset,
    DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
)
from .response import success_response, error_response, created_response, deleted_response


class ExceptionTest(TestCase):
    """异常测试"""
    
    def test_business_exception(self):
        """测试业务异常"""
        exc = BusinessException('业务错误', code=400)
        self.assertEqual(exc.message, '业务错误')
        self.assertEqual(exc.code, 400)
    
    def test_authentication_exception(self):
        """测试认证异常"""
        exc = AuthenticationException()
        self.assertEqual(exc.message, '认证失败')
        self.assertEqual(exc.code, 401)
    
    def test_permission_exception(self):
        """测试权限异常"""
        exc = PermissionException()
        self.assertEqual(exc.message, '权限不足')
        self.assertEqual(exc.code, 403)
    
    def test_not_found_exception(self):
        """测试资源不存在异常"""
        exc = NotFoundException('用户不存在')
        self.assertEqual(exc.message, '用户不存在')
        self.assertEqual(exc.code, 404)


class ResponseTest(TestCase):
    """响应测试"""
    
    def test_success_response(self):
        """测试成功响应"""
        response = success_response(data={'id': 1}, message='操作成功')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], '操作成功')
        self.assertEqual(response.data['data']['id'], 1)
    
    def test_error_response(self):
        """测试错误响应"""
        response = error_response(message='操作失败', code=400)
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], '操作失败')
    
    def test_created_response(self):
        """测试创建成功响应"""
        response = created_response(data={'id': 1})
        
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
    
    def test_deleted_response(self):
        """测试删除成功响应"""
        response = deleted_response()
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])


class PaginationTest(TestCase):
    """分页参数校验测试"""

    def test_default_params(self):
        """缺省参数使用默认值"""
        self.assertEqual(parse_pagination_params({}), (DEFAULT_PAGE, DEFAULT_PAGE_SIZE))

    def test_empty_params_use_default(self):
        """空串参数视为未提供"""
        self.assertEqual(
            parse_pagination_params({'page': '', 'page_size': ''}),
            (DEFAULT_PAGE, DEFAULT_PAGE_SIZE)
        )

    def test_valid_params(self):
        """合法参数原样解析"""
        self.assertEqual(parse_pagination_params({'page': '2', 'page_size': '20'}), (2, 20))

    def test_non_numeric_params_rejected(self):
        """非数字参数抛出业务异常"""
        for params in ({'page': 'abc'}, {'page_size': '1.5'}, {'page': '1x'}):
            with self.assertRaises(InvalidParameterException):
                parse_pagination_params(params)

    def test_zero_and_negative_page_rejected(self):
        """页码为 0 或负数时抛出业务异常"""
        for bad in ('0', '-1', '-100'):
            with self.assertRaises(InvalidParameterException):
                parse_pagination_params({'page': bad})

    def test_zero_and_negative_page_size_rejected(self):
        """页尺寸为 0 或负数时抛出业务异常"""
        for bad in ('0', '-5'):
            with self.assertRaises(InvalidParameterException):
                parse_pagination_params({'page_size': bad})

    def test_oversized_page_size_rejected(self):
        """页尺寸超过上限抛出业务异常，上限值本身合法"""
        with self.assertRaises(InvalidParameterException):
            parse_pagination_params({'page_size': str(MAX_PAGE_SIZE + 1)})
        _, page_size = parse_pagination_params({'page_size': str(MAX_PAGE_SIZE)})
        self.assertEqual(page_size, MAX_PAGE_SIZE)

    def test_paginate_queryset_keeps_order_and_total(self):
        """分页不改变排序与总数"""
        from apps.authentication.models import User
        for name in ('u1', 'u2', 'u3'):
            User.objects.create_user(username=name, password='pass12345')
        queryset = User.objects.filter(username__in=('u1', 'u2', 'u3')).order_by('username')

        items, total, page, page_size = paginate_queryset(queryset, {'page': '2', 'page_size': '2'})

        self.assertEqual(total, 3)
        self.assertEqual((page, page_size), (2, 2))
        self.assertEqual([u.username for u in items], ['u3'])

    def test_paginate_queryset_rejects_invalid_params(self):
        """分页helper对非法参数抛出业务异常而非返回空列表"""
        from apps.authentication.models import User
        with self.assertRaises(InvalidParameterException):
            paginate_queryset(User.objects.all(), {'page': '0'})


class ExceptionHandlerLoggingTest(TestCase):
    """异常处理器日志级别测试：用户输入错误与服务器异常应可区分"""

    def test_business_exception_logged_as_warning(self):
        """业务异常记录 WARNING，不记录堆栈"""
        with self.assertLogs('apps', level='WARNING') as captured:
            response = custom_exception_handler(BusinessException('页码必须大于 0'), None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['message'], '页码必须大于 0')
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelname, 'WARNING')
        self.assertIsNone(captured.records[0].exc_info)

    def test_unhandled_exception_logged_as_error(self):
        """未捕获异常记录 ERROR 并附堆栈"""
        with self.assertLogs('apps', level='ERROR') as captured:
            response = custom_exception_handler(RuntimeError('boom'), None)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelname, 'ERROR')
        self.assertIsNotNone(captured.records[0].exc_info)


class LoggingConfigTest(TestCase):
    """日志配置测试"""
    
    def test_request_id(self):
        """测试请求ID"""
        from .logging_config import set_request_id, get_request_id, clear_request_id
        
        # 设置请求ID
        request_id = set_request_id()
        self.assertIsNotNone(request_id)
        self.assertEqual(len(request_id), 8)
        
        # 获取请求ID
        self.assertEqual(get_request_id(), request_id)
        
        # 清除请求ID
        clear_request_id()
        self.assertIsNone(get_request_id())
    
    def test_custom_request_id(self):
        """测试自定义请求ID"""
        from .logging_config import set_request_id, get_request_id, clear_request_id
        
        custom_id = 'test1234'
        set_request_id(custom_id)
        self.assertEqual(get_request_id(), custom_id)
        
        clear_request_id()
    
    def test_get_logger(self):
        """测试获取日志记录器"""
        from .logging_config import get_logger
        
        logger = get_logger('test')
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, 'test')

"""
核心模块测试用例
"""
from django.test import RequestFactory, TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from .exceptions import (
    BusinessException, AuthenticationException,
    PermissionException, NotFoundException, custom_exception_handler
)
from .pagination import (
    DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE,
    PaginationValidationError, get_pagination, paginate_queryset, pagination_payload
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


class PaginationHelperTest(TestCase):
    """统一分页校验语义测试"""

    def parse(self, **params):
        return get_pagination(params)

    def test_defaults_when_absent(self):
        self.assertEqual(self.parse(), (DEFAULT_PAGE, DEFAULT_PAGE_SIZE))

    def test_valid_values(self):
        self.assertEqual(self.parse(page='2', page_size='25'), (2, 25))

    def test_whitespace_is_trimmed(self):
        self.assertEqual(self.parse(page=' 2 ', page_size=' 15 '), (2, 15))

    def test_non_numeric_page_rejected(self):
        for value in ('abc', '1.5', '', ' '):
            with self.subTest(value=value):
                with self.assertRaises(PaginationValidationError):
                    self.parse(page=value)

    def test_non_numeric_page_size_rejected(self):
        for value in ('abc', '1.5', '', ' '):
            with self.subTest(value=value):
                with self.assertRaises(PaginationValidationError):
                    self.parse(page_size=value)

    def test_zero_and_negative_page_rejected(self):
        for value in ('0', '-1', '-100'):
            with self.subTest(value=value):
                with self.assertRaises(PaginationValidationError):
                    self.parse(page=value)

    def test_zero_and_negative_page_size_rejected(self):
        for value in ('0', '-1'):
            with self.subTest(value=value):
                with self.assertRaises(PaginationValidationError):
                    self.parse(page_size=value)

    def test_page_size_over_limit_rejected(self):
        with self.assertRaises(PaginationValidationError):
            self.parse(page_size=str(MAX_PAGE_SIZE + 1))

    def test_page_size_at_limit_accepted(self):
        self.assertEqual(self.parse(page_size=str(MAX_PAGE_SIZE)), (1, MAX_PAGE_SIZE))


class PaginationQuerysetTest(TestCase):
    """分页切片 + total 语义测试"""

    @classmethod
    def setUpTestData(cls):
        from apps.authentication.models import User
        cls.User = User
        for i in range(5):
            User.objects.create_user(username=f'page-user-{i}', password='x')

    def test_slice_and_total(self):
        qs = self.User.objects.all().order_by('id')
        params = RequestFactory().get('/', {'page': '2', 'page_size': '2'}).GET
        items, total, page, page_size = paginate_queryset(qs, params)
        self.assertEqual(total, 5)
        self.assertEqual(page, 2)
        self.assertEqual(page_size, 2)
        self.assertEqual(list(items), list(qs[2:4]))

    def test_page_beyond_range_keeps_total_and_empty_list(self):
        params = RequestFactory().get('/', {'page': '99'}).GET
        items, total, page, page_size = paginate_queryset(self.User.objects.all(), params)
        self.assertEqual(total, 5)
        self.assertEqual(list(items), [])
        self.assertEqual(
            pagination_payload([], total, page, page_size),
            {'list': [], 'total': 5, 'page': 99, 'page_size': 10}
        )

    def test_invalid_params_raise_business_error(self):
        with self.assertRaises(PaginationValidationError) as ctx:
            paginate_queryset(self.User.objects.all(), RequestFactory().get('/', {'page': 'abc'}).GET)
        self.assertEqual(ctx.exception.code, 400)


class ExceptionLoggingTest(TestCase):
    """异常处理器需区分输入错误与服务器异常的日志级别"""

    def _handle(self, exc):
        return custom_exception_handler(exc, {})

    def test_business_error_is_warning_without_traceback(self):
        with self.assertLogs('apps', level='WARNING') as logs:
            response = self._handle(PaginationValidationError('页码非法'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], '页码非法')
        self.assertTrue(any('WARNING' in line for line in logs.output))
        self.assertFalse(any('ERROR' in line for line in logs.output))

    def test_unexpected_error_is_error_with_traceback(self):
        # 在活跃的异常上下文中调用处理器，模拟 DRF handle_exception 的真实场景
        try:
            raise RuntimeError('boom')
        except RuntimeError as exc:
            with self.assertLogs('apps', level='ERROR') as logs:
                response = self._handle(exc)
        self.assertEqual(response.status_code, 500)
        error_lines = [line for line in logs.output if 'ERROR' in line]
        self.assertTrue(error_lines)
        # ERROR 行带完整堆栈，能定位到异常类型与抛出位置
        self.assertIn('RuntimeError', '\n'.join(error_lines))
        self.assertIn('boom', '\n'.join(error_lines))

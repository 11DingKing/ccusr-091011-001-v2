"""
统一分页模块

所有列表接口共用同一套分页参数校验语义：
- page / page_size 省略时使用默认值
- 非数字、小数、空白等无法解析为整数的参数 -> 业务错误（400）
- page 小于 1 -> 业务错误（400）
- page_size 小于 1 或超过上限 -> 业务错误（400）
- 页码超出总页数属于合法请求，返回空列表但 total 保持为真实总数

校验失败统一抛出 PaginationValidationError，由全局异常处理器转换为
稳定的业务错误响应，而不是 500。
"""
from .exceptions import BusinessException

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


class PaginationValidationError(BusinessException):
    """分页参数非法（用户输入错误），统一返回 400。"""

    def __init__(self, message):
        super().__init__(message, code=400)


def _parse_positive_int(raw_value, param_name, label):
    """把查询参数解析为正整数，非法时抛出 PaginationValidationError。"""
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if text == '':
        raise PaginationValidationError(f'分页参数 {param_name}（{label}）必须为整数')

    try:
        value = int(text)
    except (TypeError, ValueError):
        raise PaginationValidationError(f'分页参数 {param_name}（{label}）必须为整数')

    if value < 1:
        raise PaginationValidationError(f'分页参数 {param_name}（{label}）必须大于等于1')

    return value


def get_pagination(query_params):
    """
    校验并解析分页参数。

    Returns:
        (page, page_size)
    """
    page = _parse_positive_int(query_params.get('page'), 'page', '页码')
    page_size = _parse_positive_int(
        query_params.get('page_size'), 'page_size', '每页数量'
    )

    if page is None:
        page = DEFAULT_PAGE
    if page_size is None:
        page_size = DEFAULT_PAGE_SIZE

    if page_size > MAX_PAGE_SIZE:
        raise PaginationValidationError(
            f'分页参数 page_size（每页数量）不能超过{MAX_PAGE_SIZE}'
        )

    return page, page_size


def paginate_queryset(queryset, query_params):
    """
    用统一规则校验分页参数并对 queryset 切片。

    排序由调用方在传入前通过 order_by 确定，本函数不改变排序语义。

    Returns:
        (page_items, total, page, page_size)
    """
    page, page_size = get_pagination(query_params)

    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    page_items = queryset[start:end]

    return page_items, total, page, page_size


def pagination_payload(items_data, total, page, page_size):
    """构造与既有列表接口保持一致的分页响应体。"""
    return {
        'list': items_data,
        'total': total,
        'page': page,
        'page_size': page_size,
    }

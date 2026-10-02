"""
分页参数校验模块

所有列表接口统一通过本模块解析分页参数，保证各模块校验语义一致：
非法输入（非数字、页码小于 1、页尺寸越界）抛出 InvalidParameterException，
由全局异常处理器转换为稳定的 400 业务错误，而不是 500 服务器异常。
"""
from apps.core.exceptions import InvalidParameterException

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


def parse_pagination_params(query_params):
    """
    解析并校验分页参数。

    :param query_params: request.query_params
    :return: (page, page_size)，均为正整数且 page_size 不超过 MAX_PAGE_SIZE
    :raises InvalidParameterException: 参数非数字、小于 1 或页尺寸超过上限
    """
    page = _parse_positive_int(query_params.get('page'), '页码', DEFAULT_PAGE)
    page_size = _parse_positive_int(query_params.get('page_size'), '每页数量', DEFAULT_PAGE_SIZE)

    if page_size > MAX_PAGE_SIZE:
        raise InvalidParameterException(f'每页数量不能超过 {MAX_PAGE_SIZE}')

    return page, page_size


def _parse_positive_int(raw_value, label, default):
    """将查询参数解析为正整数；缺省或空串时返回默认值。"""
    if raw_value is None or raw_value == '':
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise InvalidParameterException(f'{label}必须为数字')
    if value < 1:
        raise InvalidParameterException(f'{label}必须大于 0')
    return value


def paginate_queryset(queryset, query_params):
    """
    校验分页参数并对查询集分页，不改变查询集原有的排序。

    :return: (当前页数据, 总条数, page, page_size)
    """
    page, page_size = parse_pagination_params(query_params)
    start = (page - 1) * page_size
    end = start + page_size
    total = queryset.count()
    return queryset[start:end], total, page, page_size

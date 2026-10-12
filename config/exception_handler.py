"""
Custom exception handler để không lộ thông tin nhạy cảm ra client.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Trả về lỗi theo định dạng chuẩn, không lộ stack trace.
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Chuẩn hóa format lỗi
        error_data = {
            'error': True,
            'status_code': response.status_code,
            'message': _extract_message(response.data),
        }
        response.data = error_data
        return response

    # Lỗi không xử lý được — log và trả về 500 chung
    logger.exception('Unhandled exception in API', exc_info=exc)
    return Response(
        {
            'error': True,
            'status_code': 500,
            'message': 'Lỗi server nội bộ. Vui lòng thử lại sau.',
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _extract_message(data):
    """Trích xuất message đầu tiên từ DRF response data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return str(data[0])
    if isinstance(data, dict):
        for key in ('detail', 'message', 'non_field_errors'):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return str(val[0])
                return str(val)
        # Lấy field lỗi đầu tiên
        for val in data.values():
            if isinstance(val, list) and val:
                return str(val[0])
            return str(val)
    return 'Yêu cầu không hợp lệ.'

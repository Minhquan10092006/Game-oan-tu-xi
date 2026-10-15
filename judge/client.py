"""
judge/client.py
---------------
Giao tiếp với Judge0 API.

Thiết kế:
- Không hard-code URL, language ID hay bất kỳ hằng số nào của Judge0.
- Tất cả config đọc từ Django settings (được load từ .env).
- Xử lý lỗi network, HTTP error, timeout và rate limit rõ ràng.
- Không dùng wait=true vì có thể bị tắt trên instance công khai.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Kết quả chuẩn hóa                                                   #
# ------------------------------------------------------------------ #

@dataclass
class Judge0Result:
    """Kết quả thực thi chuẩn hóa từ Judge0."""
    token: str
    status_id: int           # Judge0 status code
    status_description: str  # Mô tả trạng thái
    stdout: str = ''
    stderr: str = ''
    compile_output: str = ''
    time: Optional[float] = None      # CPU time (giây)
    wall_time: Optional[float] = None # Wall time (giây)
    memory: Optional[int] = None      # Memory (KB)
    exit_code: Optional[int] = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def is_accepted(self) -> bool:
        """Judge0 status 3 = Accepted (thực thi thành công)."""
        return self.status_id == 3

    @property
    def is_pending(self) -> bool:
        """Status 1=In Queue, 2=Processing."""
        return self.status_id in (1, 2)

    @property
    def is_error(self) -> bool:
        return not self.is_accepted and not self.is_pending

    def to_dict(self) -> dict:
        return {
            'token': self.token,
            'status_id': self.status_id,
            'status_description': self.status_description,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'compile_output': self.compile_output,
            'time': self.time,
            'wall_time': self.wall_time,
            'memory': self.memory,
            'exit_code': self.exit_code,
        }


# ------------------------------------------------------------------ #
# Exceptions                                                           #
# ------------------------------------------------------------------ #

class Judge0Error(Exception):
    """Lỗi khi giao tiếp với Judge0."""


class Judge0Unavailable(Judge0Error):
    """Judge0 không khả dụng (503, timeout, connection error)."""


class Judge0RateLimited(Judge0Error):
    """Judge0 trả 429 Too Many Requests."""


class Judge0AuthError(Judge0Error):
    """Lỗi xác thực (401, 403)."""


# ------------------------------------------------------------------ #
# Client                                                              #
# ------------------------------------------------------------------ #

class Judge0Client:
    """
    Client giao tiếp với Judge0 API.

    Sử dụng:
        client = Judge0Client()
        language_id = client.get_python3_language_id()
        token = client.submit(source_code, stdin_data, language_id)
        result = client.poll_result(token)
    """

    # Judge0 status codes
    STATUS_IN_QUEUE = 1
    STATUS_PROCESSING = 2
    STATUS_ACCEPTED = 3

    def __init__(self):
        self.base_url = settings.JUDGE0_BASE_URL.rstrip('/')
        self.api_key = getattr(settings, 'JUDGE0_API_KEY', '')
        self.cpu_time_limit = getattr(settings, 'JUDGE0_CPU_TIME_LIMIT', 2.0)
        self.wall_time_limit = getattr(settings, 'JUDGE0_WALL_TIME_LIMIT', 5.0)
        self.memory_limit = getattr(settings, 'JUDGE0_MEMORY_LIMIT', 131072)
        self.request_timeout = getattr(settings, 'JUDGE0_REQUEST_TIMEOUT', 30)
        self.poll_max_retries = getattr(settings, 'JUDGE0_POLL_MAX_RETRIES', 15)
        self.poll_interval = getattr(settings, 'JUDGE0_POLL_INTERVAL', 2.0)
        self._session = requests.Session()
        if self.api_key:
            # Thêm API key vào header (Judge0 CE dùng X-Auth-Token)
            self._session.headers.update({'X-Auth-Token': self.api_key})

    # ---- Language discovery ----------------------------------------

    def get_languages(self) -> list[dict]:
        """
        Lấy danh sách ngôn ngữ từ Judge0 instance.
        Tránh hard-code language ID.
        """
        url = f'{self.base_url}/languages'
        try:
            resp = self._session.get(url, timeout=self.request_timeout)
            self._raise_for_status(resp)
            return resp.json()
        except Judge0Error:
            raise
        except requests.Timeout:
            raise Judge0Unavailable('Judge0 request timed out khi lấy languages.')
        except requests.ConnectionError as e:
            raise Judge0Unavailable(f'Không thể kết nối Judge0: {e}')
        except Exception as e:
            raise Judge0Error(f'Lỗi không xác định khi lấy languages: {e}')

    def get_python3_language_id(self) -> int:
        """
        Tìm language ID của Python 3 trong instance hiện tại.
        Ưu tiên "Python (3.x.x)" mới nhất.
        Raises Judge0Error nếu không tìm thấy.
        """
        languages = self.get_languages()
        # Tìm tất cả Python 3 entries
        python3_langs = [
            lang for lang in languages
            if isinstance(lang.get('name'), str)
            and 'python' in lang['name'].lower()
            and '3' in lang['name']
        ]

        if not python3_langs:
            available = [f"{l['id']}: {l['name']}" for l in languages[:20]]
            raise Judge0Error(
                f'Không tìm thấy Python 3 trên instance {self.base_url}. '
                f'Ngôn ngữ có sẵn (20 đầu): {available}'
            )

        # Sắp xếp để lấy version mới nhất (theo tên)
        python3_langs.sort(key=lambda l: l.get('name', ''), reverse=True)
        chosen = python3_langs[0]
        logger.info('Judge0 Python3 language: id=%s name=%s', chosen['id'], chosen['name'])
        return chosen['id']

    # ---- Submit ----------------------------------------------------

    def submit(
        self,
        source_code: str,
        stdin: str = '',
        language_id: Optional[int] = None,
    ) -> str:
        """
        Gửi code lên Judge0.
        Trả về submission token.

        Dùng wait=false để không block (instance công khai có thể tắt wait=true).
        """
        if language_id is None:
            language_id = self.get_python3_language_id()

        url = f'{self.base_url}/submissions?base64_encoded=false&wait=false'

        payload = {
            'source_code': source_code,
            'language_id': language_id,
            'stdin': stdin,
            'cpu_time_limit': self.cpu_time_limit,
            'wall_time_limit': self.wall_time_limit,
            'memory_limit': self.memory_limit,
        }

        # Xóa các field mà instance không hỗ trợ (sẽ retry nếu cần)
        try:
            resp = self._session.post(
                url,
                json=payload,
                timeout=self.request_timeout,
            )
            # Một số instance công khai không cho phép set limits
            if resp.status_code == 422:
                logger.warning(
                    'Judge0 422 với limits, thử lại không có limits: %s',
                    resp.text,
                )
                payload_minimal = {
                    'source_code': source_code,
                    'language_id': language_id,
                    'stdin': stdin,
                }
                resp = self._session.post(
                    url,
                    json=payload_minimal,
                    timeout=self.request_timeout,
                )
            self._raise_for_status(resp)
            data = resp.json()
            token = data.get('token')
            if not token:
                raise Judge0Error(f'Judge0 không trả token: {data}')
            logger.info('Judge0 submission token: %s', token)
            return token

        except Judge0Error:
            raise
        except requests.Timeout:
            raise Judge0Unavailable('Judge0 request timed out khi submit.')
        except requests.ConnectionError as e:
            raise Judge0Unavailable(f'Không thể kết nối Judge0: {e}')
        except Exception as e:
            raise Judge0Error(f'Lỗi không xác định khi submit: {e}')

    # ---- Poll result -----------------------------------------------

    def get_result(self, token: str) -> Judge0Result:
        """
        Lấy kết quả một lần theo token.
        Trả về Judge0Result ngay cả khi vẫn đang pending.
        """
        url = f'{self.base_url}/submissions/{token}?base64_encoded=false'
        try:
            resp = self._session.get(url, timeout=self.request_timeout)
            self._raise_for_status(resp)
            data = resp.json()
            return self._parse_result(token, data)
        except Judge0Error:
            raise
        except requests.Timeout:
            raise Judge0Unavailable(f'Timeout khi lấy kết quả token={token}')
        except requests.ConnectionError as e:
            raise Judge0Unavailable(f'Không thể kết nối Judge0: {e}')
        except Exception as e:
            raise Judge0Error(f'Lỗi không xác định khi lấy kết quả: {e}')

    def poll_result(self, token: str) -> Judge0Result:
        """
        Poll cho đến khi có kết quả cuối (không còn pending).
        Ném Judge0Unavailable nếu vượt max retries.
        """
        for attempt in range(self.poll_max_retries):
            try:
                result = self.get_result(token)
            except Judge0Unavailable:
                if attempt < self.poll_max_retries - 1:
                    time.sleep(self.poll_interval)
                    continue
                raise

            if not result.is_pending:
                return result

            logger.debug(
                'Judge0 token=%s still pending (attempt %d/%d)',
                token, attempt + 1, self.poll_max_retries,
            )
            time.sleep(self.poll_interval)

        raise Judge0Unavailable(
            f'Judge0 không trả kết quả sau {self.poll_max_retries} lần thử '
            f'(token={token}).'
        )

    # ---- Submit + poll (convenience) --------------------------------

    def submit_and_wait(
        self,
        source_code: str,
        stdin: str = '',
        language_id: Optional[int] = None,
    ) -> Judge0Result:
        """Submit rồi poll cho đến khi có kết quả."""
        token = self.submit(source_code, stdin, language_id)
        return self.poll_result(token)

    # ---- Internal ---------------------------------------------------

    def _raise_for_status(self, resp: requests.Response):
        if resp.status_code == 401 or resp.status_code == 403:
            raise Judge0AuthError(
                f'Judge0 xác thực thất bại (HTTP {resp.status_code}). '
                'Kiểm tra JUDGE0_API_KEY.'
            )
        if resp.status_code == 429:
            raise Judge0RateLimited(
                'Judge0 rate limit — quá nhiều request. Thử lại sau.'
            )
        if resp.status_code == 503 or resp.status_code == 502:
            raise Judge0Unavailable(
                f'Judge0 không khả dụng (HTTP {resp.status_code}).'
            )
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise Judge0Error(f'Judge0 HTTP error: {e}, body: {resp.text[:200]}')

    @staticmethod
    def _parse_result(token: str, data: dict) -> Judge0Result:
        status = data.get('status') or {}
        return Judge0Result(
            token=token,
            status_id=status.get('id', 0),
            status_description=status.get('description', 'Unknown'),
            stdout=data.get('stdout') or '',
            stderr=data.get('stderr') or '',
            compile_output=data.get('compile_output') or '',
            time=float(data['time']) if data.get('time') else None,
            wall_time=float(data['wall_time']) if data.get('wall_time') else None,
            memory=int(data['memory']) if data.get('memory') else None,
            exit_code=data.get('exit_code'),
            raw=data,
        )


# Module-level singleton (lazy init để không crash khi import nếu settings chưa ready)
_client: Optional[Judge0Client] = None


def get_client() -> Judge0Client:
    """Trả singleton Judge0Client."""
    global _client
    if _client is None:
        _client = Judge0Client()
    return _client

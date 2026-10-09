"""Safe, consistent descriptions of upstream failures; never include response bodies."""

import httpx
from bilibili_api.exceptions import ApiException, WbiRetryTimesExceedException

REJECTED_CODES = {-101, -403, -412, -352, -509}
REJECTED_STATUSES = {401, 403, 412, 429}


def integer_code(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def request_reason(*, code=None, status=None):
    code, status = integer_code(code), integer_code(status)
    identifiers = ', '.join(filter(None, (
        f'HTTP {status}' if status is not None else '',
        f'API code {code}' if code is not None else '')))
    suffix = f' ({identifiers})' if identifiers else ''
    if code == -101 or status == 401:
        return f'Bilibili requires sign-in{suffix}. Sign in on the fetching Mac and try again.'
    if code in REJECTED_CODES or status in REJECTED_STATUSES:
        return (f'Bilibili rejected the request{suffix}. This may be a request-rate or risk-control block. '
                'Wait before trying again, lower collection requests per second, and check sign-in on the fetching Mac.')
    if status == 404 or code == -404:
        return f'Bilibili could not find the video or resource{suffix}. It may be unavailable or private.'
    if status is not None and status >= 500:
        return f'Bilibili returned a server error{suffix}. Try again later.'
    return f'Bilibili returned an error{suffix}.'


class BilibiliRequestError(ValueError):
    """A locally generated message retaining machine-readable upstream codes."""

    def __init__(self, message, *, code=None, status=None):
        super().__init__(message)
        self.code, self.status = integer_code(code), integer_code(status)


def request_error_message(exc):
    if isinstance(exc, BilibiliRequestError):
        return str(exc)
    if isinstance(exc, WbiRetryTimesExceedException):
        return ('The Bilibili SDK exhausted its WBI request retries (API code -403). '
                'Wait before trying again and check sign-in on the fetching Mac.')
    code, status = integer_code(getattr(exc, 'code', None)), integer_code(getattr(exc, 'status', None))
    if code is not None or status is not None:
        return request_reason(code=code, status=status)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return 'The Bilibili request timed out. Check the fetching Mac\'s internet connection and try again later.'
    if isinstance(exc, httpx.TransportError):
        return f'Network request failed ({type(exc).__name__}). Check the fetching Mac\'s internet connection.'
    return f'Bilibili request failed ({type(exc).__name__}). Check availability, sign-in, and connection.'


def public_error_message(exc):
    """Keep local validation messages, but redact SDK/transport response contents."""
    if isinstance(exc, (ApiException, BilibiliRequestError, httpx.TransportError, TimeoutError)):
        return request_error_message(exc)
    return str(exc)


def check_detail_rejection(item):
    code = integer_code(item.get('detail_error_code'))
    status = integer_code(item.get('detail_error_status'))
    kind = item.get('detail_error_kind')
    if (code in REJECTED_CODES or status in REJECTED_STATUSES
            or status is not None and status >= 500 or kind in ('timeout', 'network')):
        identity = item.get('bvid')
        context = f' for {identity}' if isinstance(identity, str) and len(identity) <= 12 and identity.isalnum() else ''
        reason = request_reason(code=code, status=status)
        if code is None and status is None and kind in ('timeout', 'network'):
            reason = ('The video-detail request timed out.' if kind == 'timeout' else 'The video-detail network request failed.')
            reason += ' Check the fetching Mac\'s internet connection and try again later.'
        raise BilibiliRequestError(f'Video collection stopped{context}. {reason}',
                                   code=code, status=status)

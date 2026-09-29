"""Process-local request settings and terminal session state."""

from .config import DEFAULT_REQUEST_FREQUENCY


REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
USE_GUEST_MODE = False
SELECTED_UID: str | None = None

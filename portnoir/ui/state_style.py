from __future__ import annotations

from .. import theme
from ..core.connection import ConnectionState as S

STATE_COLOR = {S.CONNECTED: theme.OK, S.DISCONNECTED: theme.OFFLINE,
               S.DISCOVERING: theme.WARN, S.CONNECTING: theme.WARN, S.AUTHENTICATING: theme.WARN}
STATE_LABEL = {S.CONNECTED: "Connected", S.DISCONNECTED: "Offline", S.DISCOVERING: "Searching",
               S.CONNECTING: "Connecting", S.AUTHENTICATING: "Signing in"}

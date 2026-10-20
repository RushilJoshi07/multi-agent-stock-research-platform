import socket

import pytest
from pytest_socket import SocketConnectBlockedError


def test_outbound_connection_is_blocked() -> None:
    # pytest-socket raises inside connect(), before any packet is sent, so this never
    # reaches 1.1.1.1.
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("1.1.1.1", 443), timeout=2)

"""Tests may use local transports, never external network services."""
import ipaddress
import socket
import pytest


@pytest.fixture(autouse=True)
def no_external_sockets(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            try:
                allowed = host == 'localhost' or ipaddress.ip_address(host).is_loopback
            except ValueError:
                allowed = False
            if not allowed:
                raise AssertionError(f'Test attempted an external connection: {host}')
        return original(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)

"""SSRF protection in tools/web_search._is_safe_url (finding 2.20)."""

from unittest.mock import patch

from tools.web_search import _is_safe_url


def _addrinfo(*ips):
    return [(2, 1, 6, "", (ip, 0)) for ip in ips]


def test_rejects_non_http_and_empty():
    assert not _is_safe_url("")
    assert not _is_safe_url("file:///etc/passwd")
    assert not _is_safe_url("ftp://example.com/x")


def test_rejects_blocked_hostnames_and_private_literals():
    assert not _is_safe_url("http://localhost/x")
    assert not _is_safe_url("http://127.0.0.1/x")
    assert not _is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not _is_safe_url("http://10.0.0.5/x")
    assert not _is_safe_url("http://192.168.1.1/x")
    assert not _is_safe_url("http://[::1]/x")


def test_allows_public_ip_literal():
    assert _is_safe_url("http://8.8.8.8/x")


def test_hostname_resolving_to_private_ip_is_rejected():
    with patch("tools.web_search.socket.getaddrinfo",
               return_value=_addrinfo("10.1.2.3")):
        assert not _is_safe_url("https://internal.example.com/x")


def test_hostname_with_mixed_resolution_is_rejected():
    # DNS rebinding pattern: one public + one private record → reject
    with patch("tools.web_search.socket.getaddrinfo",
               return_value=_addrinfo("93.184.216.34", "127.0.0.1")):
        assert not _is_safe_url("https://evil.example.com/x")


def test_hostname_resolving_publicly_is_allowed():
    with patch("tools.web_search.socket.getaddrinfo",
               return_value=_addrinfo("93.184.216.34")):
        assert _is_safe_url("https://example.com/x")


def test_unresolvable_hostname_is_rejected():
    import socket as socket_mod

    with patch("tools.web_search.socket.getaddrinfo",
               side_effect=socket_mod.gaierror):
        assert not _is_safe_url("https://does-not-exist.invalid/x")

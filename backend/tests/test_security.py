"""Tests for security headers and CSRF guard (SPEC 2.3, 2.4).

- Every response sends: X-Content-Type-Options, Referrer-Policy,
  X-Frame-Options, Content-Security-Policy.
- POST/PUT/PATCH/DELETE with Sec-Fetch-Site: cross-site → 403.
- POST/PUT/PATCH/DELETE with Origin host ≠ Host → 403.
- Same-origin POST and missing Origin pass the guard.
"""

from fastapi.testclient import TestClient

from app.main import _host_name, _origin_host, create_app

# ------------------------------------------------------------------
# Security headers (SPEC 2.4)
# ------------------------------------------------------------------

_EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "content-security-policy": "default-src 'self'",
}


def test_security_headers_on_healthz() -> None:
    """SPEC 2.4: /healthz includes all security headers."""
    with TestClient(create_app()) as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    for header, expected in _EXPECTED_HEADERS.items():
        assert r.headers.get(header) == expected, f"Missing or wrong header: {header}"


def test_security_headers_on_index(auth_client: TestClient) -> None:
    """SPEC 2.4: / includes all security headers."""
    r = auth_client.get("/")
    assert r.status_code == 200
    for header, expected in _EXPECTED_HEADERS.items():
        assert r.headers.get(header) == expected, f"Missing or wrong header: {header}"


def test_security_headers_on_unauthorized() -> None:
    """SPEC 2.4: 401 responses also include security headers."""
    with TestClient(create_app()) as c:
        r = c.get("/")
    assert r.status_code == 401
    for header, expected in _EXPECTED_HEADERS.items():
        assert r.headers.get(header) == expected


def test_security_headers_on_csrf_403() -> None:
    """SPEC 2.4: 403 CSRF responses also include security headers."""
    with TestClient(create_app()) as c:
        r = c.post("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    for header, expected in _EXPECTED_HEADERS.items():
        assert r.headers.get(header) == expected


# ------------------------------------------------------------------
# CSRF guard (SPEC 2.3)
# ------------------------------------------------------------------


def test_cross_site_post_returns_403() -> None:
    """Sec-Fetch-Site: cross-site on POST → 403."""
    with TestClient(create_app()) as c:
        r = c.post("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_cross_site_put_returns_403() -> None:
    """Sec-Fetch-Site: cross-site on PUT → 403."""
    with TestClient(create_app()) as c:
        r = c.put("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_cross_site_patch_returns_403() -> None:
    """Sec-Fetch-Site: cross-site on PATCH → 403."""
    with TestClient(create_app()) as c:
        r = c.patch("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_cross_site_delete_returns_403() -> None:
    """Sec-Fetch-Site: cross-site on DELETE → 403."""
    with TestClient(create_app()) as c:
        r = c.delete("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_different_origin_returns_403() -> None:
    """Origin host differs from Host → 403."""
    with TestClient(create_app()) as c:
        r = c.post(
            "/",
            headers={
                "Host": "example.com:8000",
                "Origin": "https://evil.com",
            },
        )
    assert r.status_code == 403


def test_same_origin_post_passes(auth_client: TestClient) -> None:
    """Same Origin as Host passes the CSRF guard (405 since no POST handler,
    not 403 — proves guard allows the request through)."""
    r = auth_client.post(
        "/",
        headers={
            "Host": "testserver",
            "Origin": "https://testserver",
        },
    )
    # No 403 from CSRF guard — route doesn't support POST → 405
    assert r.status_code == 405
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_same_origin_with_port_passes(auth_client: TestClient) -> None:
    """Origin without port matches Host with port via _host_name strip."""
    r = auth_client.post(
        "/",
        headers={
            "Host": "testserver:8000",
            "Origin": "https://testserver",
        },
    )
    # No 403 from CSRF guard — 405 from route
    assert r.status_code == 405
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_missing_origin_passes(auth_client: TestClient) -> None:
    """Missing Origin header passes the CSRF guard (405, not 403)."""
    r = auth_client.post("/", headers={"Host": "testserver"})
    assert r.status_code == 405
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_get_is_not_blocked(auth_client: TestClient) -> None:
    """GET requests are not affected by the CSRF guard."""
    r = auth_client.get(
        "/",
        headers={
            "Host": "testserver:8000",
            "Origin": "https://evil.com",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert r.status_code == 200


def test_missing_host_header_with_cross_site_returns_403() -> None:
    """Even without Host header, Sec-Fetch-Site: cross-site → 403."""
    with TestClient(create_app()) as c:
        r = c.post("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


# ------------------------------------------------------------------
# Helper unit tests
# ------------------------------------------------------------------


def test_origin_host_extraction() -> None:
    """_origin_host returns the host portion (without port) from a full URL."""
    assert _origin_host("https://example.com") == "example.com"
    assert _origin_host("https://example.com:443") == "example.com"
    assert _origin_host("http://localhost:8080/path") == "localhost"


def test_host_name_strips_port() -> None:
    """_host_name removes trailing :port."""
    assert _host_name("example.com") == "example.com"
    assert _host_name("example.com:8000") == "example.com"
    assert _host_name("example.com:443") == "example.com"

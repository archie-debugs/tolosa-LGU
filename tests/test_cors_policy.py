import os

import Backends.backend.main as main


def test_cors_allows_only_trusted_origins():
    origins = getattr(main, "CORS_ALLOWED_ORIGINS", None)
    assert origins is not None
    assert "*" not in origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins

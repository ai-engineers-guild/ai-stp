"""Uvicorn entrypoint for the API process."""

from __future__ import annotations


def main() -> None:
    """Run the API with uvicorn, building the app through the factory."""
    import os

    import uvicorn

    # The container binds all interfaces; only the reverse proxy is public.
    # X-Forwarded-* headers are trusted only from the listed proxies: the
    # shipped topology puts nginx on the host reaching this process over the
    # published loopback port. AI_STP_FORWARDED_ALLOW_IPS (comma-separated)
    # names the proxy range when the proxy moves off-loopback; widening the
    # published bind without scoping it lets any client spoof
    # X-Forwarded-For and defeat per-client rate limiting.
    forwarded_allow_ips = [
        entry.strip()
        for entry in os.environ.get("AI_STP_FORWARDED_ALLOW_IPS", "127.0.0.1").split(",")
        if entry.strip()
    ]
    uvicorn.run(
        "ai_stp_api.app:create_app",
        factory=True,
        log_config=None,
        access_log=False,
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()

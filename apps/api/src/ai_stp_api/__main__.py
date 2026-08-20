"""Uvicorn entrypoint for the API process."""

from __future__ import annotations


def main() -> None:
    """Run the API with uvicorn, building the app through the factory."""
    import uvicorn

    # The container binds all interfaces; only the reverse proxy is public.
    uvicorn.run(
        "ai_stp_api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )


if __name__ == "__main__":
    main()

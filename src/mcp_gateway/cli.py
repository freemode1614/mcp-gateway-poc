"""Command-line entry point for the MCP Gateway."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import NoReturn

from mcp_gateway.config import ConfigWatcher, load_config
from mcp_gateway.core import BackendConnectionManager
from mcp_gateway.frontend.app import build_app
from mcp_gateway.observability import configure_logging, get_logger

logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-gateway",
        description="Local MCP Gateway: aggregate multiple MCP backends behind one HTTP/SSE endpoint.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML config. Falls back to $MCP_GATEWAY_CONFIG, ./mcp-gateway.yaml, then ~/.config/mcp-gateway/config.yaml.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override gateway.host from config.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override gateway.port from config.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=("debug", "info", "warning", "error"),
        default=None,
        help="Override gateway.log_level from config.",
    )
    return parser


def _resolve_config_path(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env_path = os.environ.get("MCP_GATEWAY_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "mcp-gateway.yaml")
    candidates.append(Path.home() / ".config" / "mcp-gateway" / "config.yaml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit("No config file found. Tried: " + ", ".join(str(p) for p in candidates))


async def _run(args: argparse.Namespace) -> int:
    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)

    if args.host:
        config = config.model_copy(
            update={"gateway": config.gateway.model_copy(update={"host": args.host})}
        )
    if args.port is not None:
        config = config.model_copy(
            update={"gateway": config.gateway.model_copy(update={"port": args.port})}
        )
    if args.log_level:
        config = config.model_copy(
            update={"gateway": config.gateway.model_copy(update={"log_level": args.log_level})}
        )

    configure_logging(config.gateway.log_level)
    logger.info(
        "startup",
        config_path=str(config_path),
        host=config.gateway.host,
        port=config.gateway.port,
        backend_count=len(config.backends),
    )

    manager = BackendConnectionManager(config=config)
    watcher = ConfigWatcher(
        config_path=config_path,
        debounce_ms=config.gateway.reload.debounce_ms,
        on_change=lambda new_config: manager.reload(new_config),
    )

    app = build_app(manager=manager)

    import uvicorn

    server_config = uvicorn.Config(
        app=app,
        host=config.gateway.host,
        port=config.gateway.port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    stop_event = asyncio.Event()

    def _handle_signal(signum: int) -> None:
        logger.info("shutdown_signal", signal=signum)
        stop_event.set()
        server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, int(sig))

    try:
        await manager.start_all()
        await watcher.start()
        await server.serve()
    finally:
        await watcher.stop()
        await manager.stop_all()
        logger.info("shutdown_complete")
    return 0


def main() -> NoReturn:
    args = _build_parser().parse_args()
    try:
        rc = asyncio.run(_run(args))
    except KeyboardInterrupt:
        rc = 0
    sys.exit(rc)


if __name__ == "__main__":
    main()

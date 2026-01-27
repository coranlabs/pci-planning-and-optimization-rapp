# Copyright 2025-2026 coRAN LABS Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
)
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector

__all__ = [
    "get_registry",
    "metrics_router",
    "register_default_runtime_collectors",
    "reset_registry",
]


_registry: CollectorRegistry | None = None
_runtime_collectors_registered: bool = False


def get_registry() -> CollectorRegistry:
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


def reset_registry() -> None:
    global _registry, _runtime_collectors_registered
    _registry = None
    _runtime_collectors_registered = False


def register_default_runtime_collectors(
    registry: CollectorRegistry | None = None,
) -> None:
    global _runtime_collectors_registered
    if _runtime_collectors_registered:
        return
    target = registry if registry is not None else get_registry()
    ProcessCollector(registry=target)
    PlatformCollector(registry=target)
    GCCollector(registry=target)
    _runtime_collectors_registered = True


def metrics_router(
    *,
    registry: CollectorRegistry | None = None,
    path: str = "/metrics",
) -> APIRouter:
    target = registry if registry is not None else get_registry()
    router = APIRouter()

    @router.get(path)
    async def metrics_endpoint() -> Response:
        body = generate_latest(target)
        return Response(content=body, media_type=CONTENT_TYPE_LATEST)

    return router

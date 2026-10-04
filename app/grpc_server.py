"""gRPC server (ADR-0020): the app's service-to-service API.

Internal-only: listens on GRPC_PORT (9090 by convention), plaintext, reachable
only by other containers on the `home-platform` Docker network at
`<app-name>:9090`. Never routed through Traefik. Runs in the same process
and event loop as the FastAPI app (started from its lifespan in app/main.py).

Also serves the standard grpc.health.v1.Health service, so callers and
probes (e.g. `grpc_health_probe -addr=<app>:9090`) can check it.

CalendarSources serves near-raw calendar rows to calendar-svc
(proto/calendar_sources.proto, docs/phase-2.md Part A); Observations serves
near-raw time-series values to quote-svc (proto/observations.proto, Part B). ExampleService.Ping
is still the template's example.
"""

import asyncio

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app import db
from app.calendars import sources_api
from app.grpc_gen import (
    calendar_sources_pb2,
    calendar_sources_pb2_grpc,
    example_service_pb2,
    example_service_pb2_grpc,
    observations_pb2,
    observations_pb2_grpc,
)
from app.rates import api as obs_api

EXAMPLE_SERVICE = example_service_pb2.DESCRIPTOR.services_by_name["ExampleService"].full_name
CALENDAR_SOURCES = calendar_sources_pb2.DESCRIPTOR.services_by_name["CalendarSources"].full_name
OBSERVATIONS = observations_pb2.DESCRIPTOR.services_by_name["Observations"].full_name


class ExampleService(example_service_pb2_grpc.ExampleServiceServicer):
    # Method name comes from the proto, hence not snake_case.
    async def Ping(self, request, context):
        return example_service_pb2.PingResponse(message=f"pong: {request.message}")


def _list_sources() -> calendar_sources_pb2.ListSourcesResponse:
    with db.session() as s:
        rows = sources_api.list_sources(s)
    return calendar_sources_pb2.ListSourcesResponse(sources=[calendar_sources_pb2.SourceInfo(**r) for r in rows])


def _get_source(name: str, include_superseded: bool) -> calendar_sources_pb2.SourceRows:
    with db.session() as s:
        out = sources_api.source_rows(s, name, include_superseded)
    return calendar_sources_pb2.SourceRows(
        source=calendar_sources_pb2.SourceInfo(**out["source"]),
        years=[calendar_sources_pb2.SourceYear(**y) for y in out["years"]],
        days=[calendar_sources_pb2.SourceDay(**d) for d in out["days"]],
    )


class CalendarSources(calendar_sources_pb2_grpc.CalendarSourcesServicer):
    # The database work is synchronous SQLAlchemy, so it runs in a thread.
    async def ListSources(self, request, context):
        return await asyncio.to_thread(_list_sources)

    async def GetSource(self, request, context):
        try:
            return await asyncio.to_thread(_get_source, request.source.upper(), request.include_superseded)
        except sources_api.UnknownSource as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))


def _obs_sources() -> observations_pb2.ListObservationSourcesResponse:
    with db.session() as s:
        rows = obs_api.list_sources(s)
    return observations_pb2.ListObservationSourcesResponse(sources=[observations_pb2.ObservationSource(**r) for r in rows])


def _obs_periods(name: str, since: str) -> observations_pb2.ListPeriodsResponse:
    with db.session() as s:
        rows = obs_api.list_periods(s, name, since)
    return observations_pb2.ListPeriodsResponse(source=name, periods=[observations_pb2.PeriodInfo(**r) for r in rows])


def _obs_period(name: str, period: str, superseded: bool) -> observations_pb2.PeriodValues:
    with db.session() as s:
        rows = obs_api.get_period(s, name, period, superseded)
    return observations_pb2.PeriodValues(
        source=name, period=period, values=[observations_pb2.ObservationValue(**r) for r in rows]
    )


class Observations(observations_pb2_grpc.ObservationsServicer):
    # The database work is synchronous SQLAlchemy, so it runs in a thread.
    async def ListSources(self, request, context):
        return await asyncio.to_thread(_obs_sources)

    async def ListPeriods(self, request, context):
        try:
            return await asyncio.to_thread(_obs_periods, request.source.upper(), request.since_period)
        except obs_api.UnknownSource as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))

    async def GetPeriod(self, request, context):
        try:
            return await asyncio.to_thread(_obs_period, request.source.upper(), request.period, request.include_superseded)
        except obs_api.UnknownSource as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))


async def start_grpc_server(port: int) -> tuple[grpc.aio.Server, int]:
    """Start the server; returns it and the bound port (port 0 picks a free one)."""
    server = grpc.aio.server()
    example_service_pb2_grpc.add_ExampleServiceServicer_to_server(ExampleService(), server)
    calendar_sources_pb2_grpc.add_CalendarSourcesServicer_to_server(CalendarSources(), server)
    observations_pb2_grpc.add_ObservationsServicer_to_server(Observations(), server)

    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    bound = server.add_insecure_port(f"[::]:{port}")
    await server.start()
    # "" is the overall server status; each service also reports its own.
    for service in ("", EXAMPLE_SERVICE, CALENDAR_SOURCES, OBSERVATIONS):
        await health_servicer.set(service, health_pb2.HealthCheckResponse.SERVING)
    return server, bound

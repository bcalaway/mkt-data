import asyncio

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.grpc_gen import example_service_pb2, example_service_pb2_grpc
from app.grpc_server import CALENDAR_SOURCES, EXAMPLE_SERVICE, start_grpc_server


async def _call(fn):
    # Port 0: the OS picks a free port, so tests never collide with 9090.
    server, port = await start_grpc_server(0)
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            return await fn(channel)
    finally:
        await server.stop(grace=None)


def test_health_reports_serving():
    async def check(channel):
        stub = health_pb2_grpc.HealthStub(channel)
        overall = await stub.Check(health_pb2.HealthCheckRequest(service=""))
        example = await stub.Check(health_pb2.HealthCheckRequest(service=EXAMPLE_SERVICE))
        sources = await stub.Check(health_pb2.HealthCheckRequest(service=CALENDAR_SOURCES))
        return overall.status, example.status, sources.status

    serving = health_pb2.HealthCheckResponse.SERVING
    assert asyncio.run(_call(check)) == (serving, serving, serving)


def test_ping():
    async def ping(channel):
        stub = example_service_pb2_grpc.ExampleServiceStub(channel)
        return await stub.Ping(example_service_pb2.PingRequest(message="hello"))

    assert asyncio.run(_call(ping)).message == "pong: hello"


def test_calendar_sources(migrated_db, fed_html):
    from app import db
    from app.calendars import service
    from app.grpc_gen import calendar_sources_pb2, calendar_sources_pb2_grpc

    with db.session() as s:
        service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))

    async def read(channel):
        stub = calendar_sources_pb2_grpc.CalendarSourcesStub(channel)
        listed = await stub.ListSources(calendar_sources_pb2.ListSourcesRequest())
        rows = await stub.GetSource(calendar_sources_pb2.GetSourceRequest(source="fed-k8"))
        try:
            await stub.GetSource(calendar_sources_pb2.GetSourceRequest(source="NOPE"))
            missing = None
        except grpc.aio.AioRpcError as e:
            missing = e.code()
        return listed, rows, missing

    listed, rows, missing = asyncio.run(_call(read))
    assert listed.sources[0].name == "FED-K8" and listed.sources[0].latest_capture_id > 0
    assert rows.source.calendar == "FED" and len(rows.years) == 5 and len(rows.days) == 50
    assert missing == grpc.StatusCode.NOT_FOUND

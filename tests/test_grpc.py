import asyncio

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.grpc_gen import example_service_pb2, example_service_pb2_grpc
from app.grpc_server import CALENDAR_SOURCES, EXAMPLE_SERVICE, OBSERVATIONS, start_grpc_server


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
        obs = await stub.Check(health_pb2.HealthCheckRequest(service=OBSERVATIONS))
        return overall.status, example.status, sources.status, obs.status

    serving = health_pb2.HealthCheckResponse.SERVING
    assert asyncio.run(_call(check)) == (serving,) * 4


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


def test_observations(migrated_db):
    from app import db
    from app.grpc_gen import observations_pb2, observations_pb2_grpc
    from app.rates import sources as rates
    from tests.conftest import FIXTURES

    body = (FIXTURES / "ust_par_2026_10_capture32.xml").read_bytes()
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", "2026-10", lambda url: (200, "text/xml", body))

    async def read(channel):
        stub = observations_pb2_grpc.ObservationsStub(channel)
        listed = await stub.ListSources(observations_pb2.ListObservationSourcesRequest())
        periods = await stub.ListPeriods(observations_pb2.ListPeriodsRequest(source="ust-par"))
        values = await stub.GetPeriod(observations_pb2.GetPeriodRequest(source="UST-PAR", period="2026-10"))
        try:
            await stub.ListPeriods(observations_pb2.ListPeriodsRequest(source="NOPE"))
            missing = None
        except grpc.aio.AioRpcError as e:
            missing = e.code()
        return listed, periods, values, missing

    listed, periods, values, missing = asyncio.run(_call(read))
    assert {x.name for x in listed.sources} == {"UST-PAR", "H15-TCM", "TD-PRICES", "BLS-CPI"}
    assert [(p.period, p.values) for p in periods.periods] == [("2026-10", 28)]
    assert len(values.values) == 28 and values.values[0].unit == "percent"
    assert missing == grpc.StatusCode.NOT_FOUND


def test_records(migrated_db):
    import json

    from app import db
    from app.grpc_gen import records_pb2, records_pb2_grpc
    from app.securities import sources as sec
    from tests.conftest import FIXTURES

    body = (FIXTURES / "td_securities_2026_10_capture1261.json").read_bytes()
    with db.session() as s:
        sec.run_capture(s, "TD-SECURITIES", "2026-10", lambda url: (200, "application/json", body))

    async def read(channel):
        stub = records_pb2_grpc.RecordsStub(channel)
        listed = await stub.ListSources(records_pb2.ListRecordSourcesRequest())
        periods = await stub.ListPeriods(records_pb2.ListRecordPeriodsRequest(source="td-securities"))
        recs = await stub.GetPeriod(records_pb2.GetRecordPeriodRequest(source="TD-SECURITIES", period="2026-10"))
        try:
            await stub.ListPeriods(records_pb2.ListRecordPeriodsRequest(source="TD-PRICES"))
            missing = None
        except grpc.aio.AioRpcError as e:
            missing = e.code()
        return listed, periods, recs, missing

    listed, periods, recs, missing = asyncio.run(_call(read))
    assert {x.name for x in listed.sources} == {"TD-SECURITIES", "FD-AUCTIONS", "FD-MSPD-STRIPS"}
    assert [(p.period, p.records) for p in periods.periods] == [("2026-10", 11)]
    bond = next(r for r in recs.records if r.source_key == "912810UW6/2026-10-15")
    assert bond.record_type == "auction" and json.loads(bond.fields_json)["interestRate"] == "5.125000"
    assert missing == grpc.StatusCode.NOT_FOUND  # an observation source, not a record source


def test_source_status(migrated_db):
    from app.grpc_gen import source_status_pb2, source_status_pb2_grpc

    async def read(channel):
        stub = source_status_pb2_grpc.SourceStatusStub(channel)
        listed = await stub.ListSourceStatus(source_status_pb2.ListSourceStatusRequest())
        one = await stub.GetSourceStatus(source_status_pb2.GetSourceStatusRequest(source="ust-par"))
        try:
            await stub.GetSourceStatus(source_status_pb2.GetSourceStatusRequest(source="NOPE"))
            missing = None
        except grpc.aio.AioRpcError as e:
            missing = e.code()
        try:
            await stub.GetCaptureText(source_status_pb2.GetCaptureTextRequest(capture_id=999))
            no_capture = None
        except grpc.aio.AioRpcError as e:
            no_capture = e.code()
        return listed, one, missing, no_capture

    listed, one, missing, no_capture = asyncio.run(_call(read))
    assert no_capture == grpc.StatusCode.NOT_FOUND
    assert one.source.dag == "mkt_data__ust_par" and one.source.pulls and not one.source.late
    assert {"FED-K8", "UST-PAR", "TD-PRICES"} <= {x.name for x in listed.sources}
    assert one.source.name == "UST-PAR" and one.source.period_kind == "month" and not one.checks
    assert missing == grpc.StatusCode.NOT_FOUND

import pytest

from fake_broker import FakeBroker
from ngsi_ld_mcp import Config, Gateway
from ngsi_ld_mcp.broker import Broker

ID = "urn:ngsi-ld:Test:mcp-1"


def seed(fb: FakeBroker):
    fb.add({"id": ID, "type": "Test",
            "hours": {"type": "Property", "value": "9-17", "observedAt": "2026-11-06T10:00:00.000Z"},
            "temperature": [{"type": "Property", "value": 4, "unitCode": "CEL", "observedAt": "2026-11-06T10:00:00.000Z"},
                            {"type": "Property", "value": 5, "datasetId": "urn:ngsi-ld:dataset:src:b", "observedAt": "2026-11-06T10:01:00.000Z"}]})


@pytest.fixture(params=[False, True], ids=["orion-501", "native"])
def fb(request):
    f = FakeBroker(native_datasets=request.param)
    seed(f)
    return f


@pytest.fixture
def gw(fb, tmp_path):
    cfg = Config(url="http://fake", proposals_path=str(tmp_path / "p.json"))
    return Gateway(cfg, Broker(cfg, transport=fb.transport))

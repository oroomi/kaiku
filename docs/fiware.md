# Kaiku and FIWARE, for the FIWARE Open Innovation Award

**Live page, read-only, every figure read from the broker when it loads:** <https://kaiku.hankintaviikko.fi/fiware>

## What is integrated
Orion-LD (NGSI-LD v1) is the spine of Kaiku's holiday-hours chain, not a side store. The business is the entity
`urn:ngsi-ld:Store:furry-paw`, type `Store` from Smart Data Models `dataModel.PointOfInterest`, with the SDM context and the ETSI core
context in the `Link` header. Detect is a **subscription firing**, Suggest is a **proposed instance** written to the broker, Decide is the
owner's tap writing the **default instance**, and the broker notification then applies it to the listing (Yext sandbox). The Yext write
never depends on the broker: if Orion-LD is down the chain runs on an in-memory fallback and says "broker offline".

## Why one datasetId per source
Last year's hours, the website, Google, category peers, Kaiku's proposal and the owner's decision all have an opinion about Christmas Eve.
Each one is its own instance of the **same** attribute `holidayHours`, told apart by `datasetId`
(`urn:ngsi-ld:dataset:kaiku:{lastyear|website|google|peers|proposed}`), each with `observedAt`. The instance without a datasetId is the
default, the resolved truth. Nothing is merged lossily, and the disagreement is visible in one GET. A flat store would need five columns and
a convention; NGSI-LD gives provenance natively. `/fiware` shows the table with the default marked as the truth.

## The gate
Nothing physical or published without the owner's yes. A proposal is a `proposed` instance and cannot become live by itself; the owner's
approval is the only write of the default instance, and the subscription then drives the apply step. The broker holds both instances, so the
broker is the audit log.

## The MCP agent
`ngsi-ld-mcp/` (MIT, in this repo) is an MCP server for any NGSI-LD broker: `list_entity_types`, `query_entities`, `get_entity`,
`get_attribute_history`, `propose_update`, `list_proposals`, `subscribe`, `list_subscriptions`, `unsubscribe`, plus `approve` and `reject`
for humans. It is mounted at `/mcp` on the live host with approve and reject hidden: an external agent can read and propose, never decide.
`/fiware` lists the tools and runs one live read-only call (`query_entities` on `Store`).

## Aura, the same broker with city data
`/aura` puts Turku buses (Foli), ships (Digitraffic AIS) and weather (Open-Meteo) into the same Orion-LD as `Vehicle` and
`WeatherObserved` entities (Smart Data Models Transportation and Weather). Counts and capture time are on `/fiware` section 4.

## What did not work (tested, Orion-LD post-v1.12.0)
- `datasetId` instances are accepted only at entity creation; `POST/PATCH /attrs`, upsert and batch answer 501. We read, merge, delete and
  re-create the entity, serialised by a lock (not atomic across processes).
- `q=holidayHoursStatus.status=="missing"` is accepted but not evaluated against keys inside an object value. We subscribe on watched
  attributes and filter in our handler.
- A newly added attribute does not trigger a subscription, so the status attribute is seeded at creation.
- `holidayHours` is not in the SDM context; Orion expands it to its default vocabulary. A real rollout would publish a Kaiku context file.

## Verify in 60 seconds
```
curl -s http://127.0.0.1:1026/version                      # on the demo host: Orion-LD version
curl -s 'http://127.0.0.1:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Store:furry-paw?attrs=holidayHours' \
  -H 'Accept: application/json' \
  -H 'Link: <https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"' | python3 -m json.tool
# from anywhere, the same read through the read-only proxy (GET only, urn:ngsi-ld: ids only):
curl -s 'https://kaiku.hankintaviikko.fi/api/fiware/entity?id=urn:ngsi-ld:Store:furry-paw&attrs=holidayHours'
curl -s https://kaiku.hankintaviikko.fi/api/fiware/subscriptions
curl -s https://kaiku.hankintaviikko.fi/api/fiware/mcp
```
Expected: several `holidayHours` instances, one per datasetId, and one without a datasetId (the default). Details of the model and of the
subscriptions: [docs/broker.md](broker.md).

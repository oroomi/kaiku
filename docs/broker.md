# Broker (FIWARE Orion-LD), the spine of the chain

One business, many sources, one truth. Every source that has an opinion about Furry Paw's
Christmas Eve hours writes its own instance of the SAME attribute; the owner's tap writes the
default instance, which is the resolved truth that gets pushed to Yext.

## Run it
```
docker-compose -f kaiku/broker/docker-compose.yml up -d     # note: the box has docker-compose v1, not `docker compose`
curl http://127.0.0.1:1026/version
python -m kaiku.broker.smoke          # Orion-LD run, then the same run against a dead URL (fallback). --keep leaves the entity
pytest -q tests/test_broker.py
```
Orion-LD runs on the HOST network, bound to 127.0.0.1:1026 only (`-ipv4 -localIp 127.0.0.1`). MongoDB
has no published port; it sits on a private bridge (172.28.77.2). Reason: the host firewall (ufw) drops
container-to-host traffic, so a bridged Orion could not deliver notifications to our app on
127.0.0.1:8210. Host networking makes notification URLs plain `http://127.0.0.1:8210/broker/notify`.
Env: `KAIKU_BROKER_URL` (default http://127.0.0.1:1026), `PUBLIC_URL` (notification base, default http://127.0.0.1:8210).

## Entity model
`urn:ngsi-ld:Store:<business-id>` (Furry Paw: `urn:ngsi-ld:Store:furry-paw`), type `Store` from Smart Data
Models `dataModel.PointOfInterest`. Attributes: `name`, `address` (PostalAddress object), `location`
(GeoProperty Point, [lon, lat]), `openingHoursSpecification` (array, schema.org day URIs), `category`, `url`,
plus ours:

- `holidayHours`: value `{date, hours: [{start,end}] | "closed"}`, ONE INSTANCE PER SOURCE via `datasetId`
  `urn:ngsi-ld:dataset:kaiku:{lastyear|website|google|peers|proposed|owner}`, each with `observedAt`.
  The instance WITHOUT datasetId is the default = the resolved truth.
- `holidayHoursStatus`: `{date, status: missing|proposed|approved|applied}`.

`@context` goes in the `Link` header: `[SDM PointOfInterest context.jsonld, ETSI core context]`. The SDM URL
resolved from the broker, so no local context was needed. `holidayHours` and `holidayHoursStatus` are not
in the SDM context; Orion expands them to its default vocabulary, which is fine for a demo (a real rollout
would publish a Kaiku context file).

## Why datasetId per source
The disagreement IS the product. Last year says closed, Google says 9-13, our engine proposes 9-13,
the owner decides. Five opinions, one attribute, each with provenance (`observedAt`) and no lossy merging.
NGSI-LD gives this natively; a flat key-value store would need five columns and a convention.

Judge beat for the FIWARE CEO (one business, five datasetIds, one truth):
```
curl -s http://127.0.0.1:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Store:furry-paw?attrs=holidayHours \
  -H 'Accept: application/json' \
  -H 'Link: <https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"' | python3 -m json.tool
```
(`python -m kaiku.broker.smoke --keep` leaves an equivalent `urn:ngsi-ld:Store:furry-paw-smoke` in place.)

## Subscriptions (`subs.py`, created idempotently by `subscriptionName`)
- `kaiku-holiday-hours-missing`: watches `holidayHoursStatus`, notifies `{PUBLIC_URL}/broker/notify`. The
  router keeps only `status == "missing"` (DETECT).
- `kaiku-holiday-hours-resolved`: watches `holidayHours`; the router keeps only the default instance, deduped
  on `observedAt` (DECIDE).
`router.py` emits `Event(step="broker")` ("Tilaus laukesi: jouluaaton aukioloajat puuttuvat" / "Subscription
fired: Christmas Eve hours missing") when `kaiku.events` and `kaiku.schema` exist, otherwise logs. Core should
call `subs.ensure_subscriptions()` in its lifespan (router.on_event startup is ignored when an app has a lifespan);
`POST /broker/ensure` does the same, `GET /broker/status` shows `orion-ld` or `fallback`.

## Fallback (`fallback.py`)
Same interface, in memory, evaluates subscriptions on every write and delivers by POSTing the endpoint URL or
calling an in-process callable. `kaiku.broker.get_broker()` probes `/version` at first use; if Orion is down
it uses the fallback, and if Orion dies mid-run the first transport error switches to the fallback for the
rest of the process (state is not copied back). The Yext write never depends on the broker; events then say
"broker offline".

## What did not work (Orion-LD post-v1.12.0 build, tested)
- `datasetId` instances are accepted ONLY at entity creation. `POST/PATCH /entities/{id}/attrs`, upsert and
  batch update answer 501 ("datasetId instances are not supported"). So the client does read-modify-write:
  fetch, merge the instance, DELETE and re-POST the entity (one creation = one notification carrying every
  instance). A process lock serialises it; it is not atomic across processes. Writing the default instance of an
  attribute with no other instances is a normal `POST /attrs`.
- `q=holidayHoursStatus.status=="missing"` is accepted but not evaluated against keys inside an object value
  (it did not fire for "missing"). We subscribe on `watchedAttributes` and filter in the router. The fallback
  does evaluate the q (`KAIKU_BROKER_USE_Q=1` sends it to Orion anyway).
- A newly ADDED attribute does not trigger a subscription; seed `holidayHoursStatus` when the entity is created
  (`business_to_entity(..., status=...)`), then changes notify.
- Orion pauses a subscription after 3 deliveries that return non-204 without Content-Length. FastAPI replies
  with a JSON body, which is fine; the client re-activates paused subscriptions in `create_subscription`.
- Bridged Orion could not reach the host (ufw). Solved with host networking, see above.
- Smart Data Models context fetch worked; no local context fallback was needed.

# Collector capability matrix

This matrix is the public contract for what SUGAR currently attempts. A `false` cell means the
collector is not implemented for that operation; it does not mean that the platform has no such
data. Access failure, rate limiting, login gates, CAPTCHA/anti-bot responses, and unsupported
surfaces remain explicit outcomes and must not be converted into empty findings.

| Source | Keyword search | Known item | Comments | Profile timeline | Pagination | Date filtering | Location data | Engagement metrics | Authenticated search | Anonymous search | Access boundary |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| X | yes | no | no | no | yes | yes | author profile only | yes | yes | no | Bearer-token API; billing, permissions, and rate limits are surfaced |
| Bluesky | yes | no | no | no | yes | yes | no normalized profile location | yes | yes | yes | Public AppView or legitimate PDS app-password session |
| Mastodon | yes | no | no | no | yes/authenticated offset | yes/local filter | no normalized profile location | yes | yes | yes | Instance-scoped API; instance policy and rate limits apply |
| Bilibili | yes | yes | yes | no | yes | yes/local filter | no | yes | no | yes/fail-closed | Public web API only; access-control/WBI/login responses fail closed |
| Weibo | yes | yes | yes | no | yes | yes/local filter | author profile when supplied | yes | yes | yes/partial | Public/mobile-web or user-supplied legitimate session; availability is partial |

The authoritative runtime view is available from:

```bash
python -c "from sugar_core.collector_registry import collector_capabilities; import json; print(json.dumps(collector_capabilities(), indent=2, sort_keys=True))"
```

Every normalized record should preserve platform identity, canonical/source URLs, publication and
collection timestamps, query provenance, collector version, source/access mode, raw metrics, and
normalized metrics. Coverage claims must distinguish:

- `observed`: a record was returned and normalized;
- `not_returned`: the requested surface returned no record under the tested query/window;
- `unavailable`: the surface could not be tested or was blocked/unsupported;
- `unknown`: the available evidence is insufficient to classify the condition.

These states are not interchangeable with a boolean absence claim.

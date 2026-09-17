# Legal and data-handling boundaries

This is an operational project policy, not legal advice. A deploying team must obtain the review
required by its institution, sponsor, jurisdiction, and platform agreements before collecting or
sharing material.

## Access definitions

For SUGAR documentation:

- **Public-source access** means a source surface that can be reached without defeating a login,
  CAPTCHA, anti-bot challenge, paywall, technical control, or other access restriction. Publicly
  visible does not by itself resolve copyright, privacy, terms-of-service, or retention questions.
- **Explicitly authorized access** means the operator has a legitimate account/session or written
  permission to use the surface for the stated research purpose. Credentials must be supplied at
  runtime and never stored in SUGAR manifests, checkpoints, exports, fixtures, or issue reports.
- **Unsupported or denied access** is an observed collection boundary. It must be recorded as
  unavailable/partial rather than reported as evidence of no activity.

SUGAR must not solve CAPTCHAs, manufacture sessions, spoof devices, rotate identities or proxies
to evade controls, or weaken TLS/endpoint protections. Operators remain responsible for respecting
applicable law, institutional review, privacy/data-minimization rules, platform terms, and requests
to remove or restrict data.

## Research data handling

Treat raw posts, profile identifiers, session-derived material, geocoded locations, analyst notes,
and generated exports as research data. Use approved storage and access controls, minimize retained
personal data, keep provenance and collection context with derived claims, and avoid publishing
credentials or unnecessary personal information. Workspace manifests and SQLite registries are not
security boundaries or encryption at rest.

LLM prompts and responses are cached only in process memory and are not written to the workspace.
The on-disk cache is reserved for public geocoder provider metadata. Explicit output files remain
research data and must be protected by the operator's approved storage controls.

## Product disclaimers

SUGAR is a research tool. Density, engagement, reach, proximity, or platform presence do not by
themselves establish influence, coordination, intent, causation, institutional affiliation, or an
official government position. AI output is an assistive triage layer and requires evidence and human
review for high-consequence claims. The State-facing workflow is not an official Department of State
authorization, intelligence product, procurement approval, ATO, or AI certification.

## Third-party notices

The release owner must complete the generated dependency/license notice and any platform/API terms
review before distributing a production bundle. The Python dependency inventory is declared in
`pyproject.toml`; the tagged release workflow produces an SBOM for the exact build environment.

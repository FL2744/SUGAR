# Public repository boundaries

SUGAR's public repository contains a target-neutral research engine and generic platform adapters. Mission-specific targets, country/entity watchlists, operational query plans, real sponsor-focused case data, and customer-specific analytic prompts should be maintained outside the public repository.

Platform adapters may document the public or authorized surfaces they support, but should not encode why a particular project is interested in that platform. Analytic schemas use generic sponsor/state-support concepts so the same engine can be configured for different research questions without publishing the active target.

The public-OPSEC regression test scans tracked text for target-specific mission terminology and known real-case markers. A file-scoped exception permits the Confucius Institute public-directory adapter name in its implementation, CLI/workspace entry points, adapter tests, and release documentation. This names a supported public data provider; it does not authorize publishing case targets or watchlists.

The bundled Team 4 catalog is a deliberate product-data exception. The full-content exceptions are limited to `docs/team4-network-catalog.md`, `sugar_core/team_catalog.py`, and `sugar_core/data/team4_network_catalog.json`. The root `README.md`, `CHANGELOG.md`, this boundary note, and `tests/test_team_catalog.py` permit only the Confucius Institute and Luban Workshop names; the regression test continues checking those files for other mission markers. Source status labels remain claims; catalog records remain unverified until reviewed against dated evidence. Other mission markers and project-specific material remain outside this exception.

The editable default priority rubric and its regression tests also permit the
two workshop program-name terms needed for multilingual vocational-program
classification. That exception is limited to those terms and those two files;
it does not permit case records or institutional watchlists.

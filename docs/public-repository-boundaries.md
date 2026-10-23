# Public repository boundaries

SUGAR's public repository contains a target-neutral research engine and generic platform adapters. Mission-specific targets, country/entity watchlists, operational query plans, real sponsor-focused case data, and customer-specific analytic prompts should be maintained outside the public repository.

Platform adapters may document the public or authorized surfaces they support, but should not encode why a particular project is interested in that platform. Analytic schemas use generic sponsor/state-support concepts so the same engine can be configured for different research questions without publishing the active target.

The public-OPSEC regression test scans tracked text for target-specific mission terminology and known real-case markers. A file-scoped exception permits the Confucius Institute public-directory adapter name in its implementation, CLI/workspace entry points, adapter tests, and release documentation. This names a supported public data provider; it does not authorize publishing case targets or watchlists. Other mission markers remain checked in those files. Add project-specific configuration only through external/private project files.

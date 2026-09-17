# Public repository boundaries

SUGAR's public repository contains a target-neutral research engine and generic platform adapters. Mission-specific targets, country/entity watchlists, operational query plans, real sponsor-focused case data, and customer-specific analytic prompts should be maintained outside the public repository.

Platform adapters may document the public or authorized surfaces they support, but should not encode why a particular project is interested in that platform. Analytic schemas use generic sponsor/state-support concepts so the same engine can be configured for different research questions without publishing the active target.

The public-OPSEC regression test scans tracked text for target-specific mission terminology and known real-case markers. Add project-specific configuration only through external/private project files.

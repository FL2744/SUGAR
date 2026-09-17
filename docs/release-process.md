# Release process

SUGAR releases are created from an annotated semantic-version tag (`vMAJOR.MINOR.PATCH`) after the
professional release gate in the project checklist is complete. A tag must point to the exact commit
reviewed by the release owner; building from a mutable working tree is not a release process.

The tagged workflow produces:

- Python wheel and source distribution;
- `SHA256SUMS` checksums for every generated file;
- a CycloneDX environment SBOM;
- a GitHub Release containing the immutable build outputs.

The workflow does not claim platform signing. Production desktop distribution remains blocked until
the release owner supplies and protects the relevant identities:

- Windows Authenticode certificate and timestamping policy;
- macOS Developer ID application/installer identities, notarization credentials, and team ID;
- verification commands and a trusted place for public signing artifacts.

The release owner must also resolve before publishing:

- the repository license and copyright/ownership wording;
- any official institutional affiliation and project-name/trademark review;
- a concrete private vulnerability-reporting route;
- the supported upgrade/migration policy and exact changelog entry.

Never put signing keys, API credentials, cookies, private research data, or unsigned “production” claims
in the repository. A release candidate may be built and tested without signing, but it must be labeled
as such.

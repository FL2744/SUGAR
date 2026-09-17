# Security policy

SUGAR handles public-source research, API credentials, optional authenticated sessions, generated research files, and desktop packaging. Security issues should be treated separately from ordinary bugs when disclosure could expose credentials, enable unintended access, or weaken host protections.

## Reporting a vulnerability

Do not publish live credentials, session cookies, private research data, or a working exploit in a public GitHub issue.

If enabled for this repository, use the private [GitHub Security Advisory report form](https://github.com/FL2744/SUGAR/security/advisories/new). If that route is unavailable, contact the project maintainer through the institution-approved private project channel and ask for a secure reporting route before posting technical details publicly. A public issue may be opened later with sensitive details removed.

A useful report includes:

- affected SUGAR version/commit;
- operating system and packaging surface;
- affected module or workflow;
- impact and realistic preconditions;
- minimal reproduction steps using synthetic data where possible;
- whether credentials or stored research data may have been exposed.

## Credentials

SUGAR supports credentials such as:

- `SUGAR_X_BEARER_TOKEN`
- `SUGAR_LLM_API_KEY`
- `SUGAR_BLUESKY_IDENTIFIER`
- `SUGAR_BLUESKY_APP_PASSWORD`
- `SUGAR_MASTODON_TOKEN`
- `SUGAR_WEIBO_COOKIE`

Credentials must not be committed to Git, included in bug reports, copied into project manifests, or written into generated research exports by SUGAR.

Native applications may use platform-appropriate secure/session handling. The Windows workbench keeps entered secrets in memory for the application session and passes them to the backend through its process environment. The macOS application uses Keychain-backed storage where supported.

If a real credential is committed or posted, treat it as compromised: revoke/rotate it first, then remove the exposed value from the repository/history or discussion as appropriate. Deleting the visible file alone is not sufficient remediation.

## Project workspaces

`sugar-project.json` is intentionally non-secret and portable. `.sugar/workspace.sqlite3` stores artifact metadata and may include paths/labels supplied by users, but SUGAR does not intentionally persist credentials there.

Workspace metadata is not a security boundary. Research teams remain responsible for using approved storage locations, operating-system permissions, encryption, and institutional data-handling requirements appropriate to their material.

## Platform access boundaries

SUGAR is intended for public or explicitly authorized access. Security fixes must not be replaced with mechanisms that weaken access controls. The project does not use CAPTCHA solving, credential manufacture, device spoofing, proxy/account rotation to evade limits, or other access-control bypass as a reliability workaround.

A collector that encounters login gates, anti-bot verification, rate limits, or unsupported access should fail/defer explicitly.

## Desktop packaging

Development and CI desktop builds may be unsigned or locally signed for testing. Production distribution should use normal platform signing/notarization procedures. Do not instruct users to disable Gatekeeper, SmartScreen, antivirus, or endpoint protection as a permanent workaround for packaging problems.

The desktop bridge intentionally exposes named operations rather than arbitrary command execution. Changes that expand the bridge surface should preserve typed/validated inputs and avoid generic shell passthrough.

## Dependencies

Keep dependencies declared in `pyproject.toml`; SUGAR must not install or upgrade packages at runtime. Security-related dependency changes should remain reviewable and should not silently widen supported version ranges without testing.

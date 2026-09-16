# SUGAR classroom preview

This preview is designed for usability testing by people who did not build SUGAR. The goal is to identify where installation, navigation, terminology, source access, and research workflows are confusing while still giving everyone a known-good path through the application.

## The test

Please try SUGAR before asking a developer for help. If something is unclear, that is useful feedback.

### 1. Launch SUGAR

- **macOS:** download the architecture-specific SUGAR `.zip`, extract it, and open `SUGAR.app`. Choose the **ARM64 / Apple Silicon** build for Macs with an Apple chip and the **X64 / Intel** build for Intel Macs. The classroom build is not a notarized public release, so macOS may show its normal downloaded-app warning. Use only the project team's canonical build and do not disable macOS security features globally.
- **Windows:** download the single `SUGAR.exe` and run it. You do **not** need to install Python, extract a support folder, clone GitHub, or keep a second backend executable beside it.
- **CLI/development:** Python 3.11–3.13 is supported for developers and command-line users only.

If launch fails, record exactly what happened, your OS version, and (for Macs) whether the machine is Apple Silicon or Intel.

### 2. Prove the local app works before testing the internet

Start with the bundled sample files from the Welcome page:

1. Open the sample spreadsheet.
2. Open the sample map.
3. Open the sample report.
4. Create a new map from the sample spreadsheet.
5. Create a PDF report from the same sample.

This path requires no X token, ARC key, or other service credential. If it fails, report it as an application/packaging problem rather than a source-access problem.

### 3. Try a small live collection

Start with **Bilibili** when you want a credential-free keyword-search exercise. Keep the first run small: one query, about 10 records, one page. AI translation and location inference are optional and are off by default; leave them off if you do not have an approved LLM/ARC key.

Other useful classroom paths:

- **Weibo:** known public post/URL retrieval is a better reliability test than assuming anonymous keyword search will always be available.
- **WeChat Official Accounts, Douyin, and known Zhihu items:** use **Public URL Import** rather than treating them as generic keyword-search services.
- **X:** requires an API bearer token.
- **Zhihu keyword search:** requires approved Open Platform access; known public URL import is separate.

Source capabilities are intentionally different. A platform may support keyword search, known-public-URL import, comments, or authenticated access without supporting every other mode.

### 4. Understand partial collection

A provider can block or throttle a request even when SUGAR itself is healthy. In a **multi-source** search, SUGAR now preserves results from sources that succeed and explicitly reports any source that was unavailable. The output metadata records `partial_collection`, `successful_sources`, and `source_failures`.

For example, a run can legitimately finish as:

- Bluesky unavailable for this request;
- Bilibili collected records successfully;
- output saved with partial coverage.

Do not reinterpret a 403, 429, login/verification gate, or other access failure as evidence of zero activity on the platform.

### 5. Find your outputs

After an operation finishes, open at least one generated output directly from the Activity & Outputs area. Also try revealing it in Finder/Explorer. Note whether it is obvious where files were written and what each output means.

### 6. Report feedback

Use the GitHub **Usability feedback** issue form. Strong reports describe:

- what you were trying to accomplish;
- where you hesitated or got stuck;
- what happened;
- what you expected instead;
- operating system/version and Mac architecture when applicable;
- the SUGAR version/build shown in diagnostics;
- the support log when useful, after checking it contains no credentials.

Please report confusing behavior even when you eventually solve it yourself. Those are exactly the points the usability test is intended to find.

## Suggested classroom tasks

1. Launch SUGAR without developer help.
2. Find and open a bundled sample.
3. Create a map from the sample spreadsheet.
4. Create a short analysis report from the same spreadsheet.
5. Find and reopen the generated files.
6. Identify which sources can be used without credentials.
7. Run one small real collection or public-URL import.
8. If using multiple sources, notice whether a failed source is clearly distinguished from successful sources.
9. Submit at least one usability observation or confirm that the workflow was clear.

## Research and access rules

SUGAR uses ordinary public or explicitly authorized access. It does not solve CAPTCHAs, manufacture login/session state, spoof device identities, rotate accounts/proxies to evade controls, or treat an access failure as evidence of zero activity.

Heatmap density, engagement, geographic proximity, and causal influence are different concepts. SUGAR's outputs should preserve those distinctions.

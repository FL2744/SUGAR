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

### 3. Run the known-good live sanity check

For the most repeatable public-network check, use this public Weibo post that SUGAR's live CI exercises:

`https://m.weibo.cn/status/5320265912291527`

- **macOS:** use **Public URL Import → Weibo**.
- **Windows:** use **Weibo Research → Post Investigation**.

The current live test retrieves the seed post and public comments. Weibo's repost and author-timeline surfaces may require an authorized logged-in session; SUGAR reports those surfaces independently instead of turning restricted access into observed zeroes.

A successful seed/comment retrieval proves that the packaged application can reach a live source, normalize real public records, and write outputs without relying on keyword-search availability.

### 4. Try a small keyword search

**Bilibili** is useful as a credential-free keyword-search exercise, but keyword yield is provider/query dependent. A bounded CI probe has returned both real records and valid zero-result responses at different times, so do not treat a zero-result query by itself as proof that SUGAR is broken or that no relevant activity exists.

Keep the first keyword run small: one broad query, about 10 records, one page. AI translation and location inference are optional; leave them off if you do not have an approved LLM/ARC key.

Other useful classroom paths:

- **Weibo keyword search:** anonymous search availability can vary; the fixed public-post workflow above is the better sanity check.
- **WeChat Official Accounts, Douyin, and known Zhihu items:** use **Public URL Import** rather than treating them as generic keyword-search services.
- **X:** requires an API bearer token.
- **Zhihu keyword search:** requires approved Open Platform access; known public URL import is separate.

Source capabilities are intentionally different. A platform may support keyword search, known-public-URL import, comments, or authenticated access without supporting every other mode.

### 5. Understand partial collection

A provider can block or throttle a request even when SUGAR itself is healthy. In a **multi-source** search, SUGAR now preserves results from sources that succeed and explicitly reports any source that was unavailable. The output metadata records `partial_collection`, `successful_sources`, and `source_failures`.

For example, a run can legitimately finish as:

- Bluesky unavailable for this request;
- Bilibili collected records successfully;
- output saved with partial coverage.

Do not reinterpret a 403, 429, login/verification gate, or other access failure as evidence of zero activity on the platform.

### 6. Find your outputs

After an operation finishes, open at least one generated output directly from the Activity & Outputs area. Also try revealing it in Finder/Explorer. Note whether it is obvious where files were written and what each output means.

### 7. Report feedback

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
6. Run the fixed public Weibo sanity check.
7. Identify which other sources can be used without credentials.
8. Run one small keyword search or another public-URL import.
9. If using multiple sources, notice whether a failed source is clearly distinguished from successful sources.
10. Submit at least one usability observation or confirm that the workflow was clear.

## Research and access rules

SUGAR uses ordinary public or explicitly authorized access. It does not solve CAPTCHAs, manufacture login/session state, spoof device identities, rotate accounts/proxies to evade controls, or treat an access failure as evidence of zero activity.

Heatmap density, engagement, geographic proximity, and causal influence are different concepts. SUGAR's outputs should preserve those distinctions.

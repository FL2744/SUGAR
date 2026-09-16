# SUGAR classroom preview

This preview is designed for usability testing by people who did not build SUGAR. The goal is not to prove that every feature works perfectly; it is to identify where installation, navigation, terminology, source access, and research workflows are confusing.

## The test

Please try SUGAR before asking a developer for help. If something is unclear, that is useful feedback.

### 1. Launch SUGAR

- macOS: open the supplied SUGAR disk image and drag SUGAR to Applications. The classroom build may be unsigned; use only a build distributed by the project team. Do not disable macOS security features globally.
- Windows: extract the complete `SUGAR-Windows-x64.zip` folder and run `SUGAR.exe`. The packaged build includes its backend; installing Python is **not** required for ordinary use.
- CLI: Python 3.11–3.13 is supported for developers and command-line users.

If launch fails, record exactly what happened and your OS version/architecture.

### 2. Try SUGAR without credentials

Start with the bundled sample files. Open the sample spreadsheet, sample map, and sample report from the app's Welcome page. This path should work without an X token or LLM API key.

Then try creating a map or analysis report from the sample spreadsheet.

### 3. Try a small collection

Use a public source that does not require credentials when available. Keep the first run small (for example, one query, 10 records, one page). AI translation and location inference are optional; leave them off if you do not have an approved LLM/ARC key.

Source capabilities are intentionally different. A platform may support keyword search, known public URL import, comments, or authenticated access without supporting every other mode.

### 4. Find your outputs

After an operation finishes, open at least one generated output directly from the Activity/Outputs area. Note whether it is obvious where files were written and what each output means.

### 5. Report feedback

Use the GitHub **Usability feedback** issue form. Strong reports describe:

- what you were trying to accomplish;
- where you hesitated or got stuck;
- what happened;
- what you expected instead;
- operating system/version and Mac architecture when applicable;
- the support log when useful, after checking it contains no credentials.

Please report confusing behavior even when you eventually solve it yourself. Those are exactly the points the usability test is intended to find.

## Suggested classroom tasks

1. Launch SUGAR without developer help.
2. Find and open a bundled sample.
3. Create a map from the sample spreadsheet.
4. Create a short analysis report from the same spreadsheet.
5. Find the generated files again after the operation finishes.
6. Identify which sources can be used without credentials.
7. If you have appropriate access, run one small real collection or public-URL import.
8. Submit at least one usability observation or confirm that the workflow was clear.

## Research and access rules

SUGAR uses ordinary public or explicitly authorized access. It does not solve CAPTCHAs, manufacture login/session state, spoof device identities, rotate accounts/proxies to evade controls, or treat an access failure as evidence of zero activity.

Heatmap density, engagement, geographic proximity, and causal influence are different concepts. SUGAR's outputs should preserve those distinctions.

# Classroom desktop distribution

The classroom build is distributed through GitHub Releases as three validated ZIP archives:

- `SUGAR-Windows-x64.zip` for Windows 10/11 x64
- `SUGAR-macOS-Apple-Silicon.zip` for Apple Silicon Macs
- `SUGAR-macOS-Intel.zip` for Intel Macs

Students should use the latest GitHub Release rather than downloading source-code archives from the repository tag page.

For Virginia Tech ARC setup inside SUGAR, see [`arc-quick-start.md`](arc-quick-start.md). The desktop clients provide a **Get ARC API Key** action, an ARC provider/model selector, and a **Test ARC Connection** action before students begin AI-assisted workflows.

Windows classroom builds include their packaged backend and do not require a separate Python installation. macOS classroom builds target macOS 13 or newer and may require the normal first-launch Gatekeeper override when distributed without Apple notarization.

# Windows package entry point

Windows uses the shared SUGAR web interface. Its optional desktop package is built from the same React/TypeScript frontend as macOS, with `sugar_core` packaged as a Python sidecar.

From PowerShell at the repository root:

```powershell
.\SUGAR-Windows\scripts\build.ps1
```

The implementation and shared build instructions live in [`SUGAR-Desktop/`](../SUGAR-Desktop/). The previous PySide6 application source has been archived under `archive/legacy-native-ui/windows/` and is not a supported fallback.

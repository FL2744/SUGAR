# macOS package entry point

macOS uses the shared SUGAR web interface. Its optional desktop package is built from the same React/TypeScript frontend as Windows, with `sugar_core` packaged as a Python sidecar.

On a Mac with Xcode command line tools, Rust, and Python 3.12 installed:

```sh
./SUGAR-Desktop/scripts/build-macos.sh
```

From this directory, `./scripts/build_app.sh` is also available as a compatibility wrapper. The implementation and shared build instructions live in [`SUGAR-Desktop/`](../SUGAR-Desktop/). The previous SwiftUI application source has been archived under `archive/legacy-native-ui/macos/` and is not a supported fallback.

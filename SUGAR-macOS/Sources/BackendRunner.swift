import Foundation

/// Drain stdout and stderr while the child runs, preserving complete UTF-8 lines.
enum BackendRunner {
    nonisolated static func run(
        _ process: Process,
        onOutput: @escaping @MainActor @Sendable (String) -> Void
    ) async throws -> Int32 {
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        defer {
            try? pipe.fileHandleForReading.close()
            try? pipe.fileHandleForWriting.close()
        }
        try process.run()
        // Only the child should retain a writer, so its exit delivers EOF.
        try pipe.fileHandleForWriting.close()
        do {
            for try await line in pipe.fileHandleForReading.bytes.lines {
                await onOutput(line + "\n")
            }
        } catch {
            if process.isRunning { process.terminate() }
            process.waitUntilExit()
            throw error
        }
        process.waitUntilExit()
        return process.terminationStatus
    }
}

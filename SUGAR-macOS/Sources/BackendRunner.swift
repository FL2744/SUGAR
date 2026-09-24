import Foundation

private final class ProcessCancellation: @unchecked Sendable {
    let process: Process

    init(_ process: Process) { self.process = process }

    func terminate() {
        if process.isRunning { process.terminate() }
    }
}

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
        let cancellation = ProcessCancellation(process)
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            try process.run()
            if Task.isCancelled { cancellation.terminate() }
            // Only the child should retain a writer, so its exit delivers EOF.
            try pipe.fileHandleForWriting.close()
            do {
                for try await line in pipe.fileHandleForReading.bytes.lines {
                    await onOutput(line + "\n")
                }
            } catch {
                cancellation.terminate()
                process.waitUntilExit()
                throw error
            }
            process.waitUntilExit()
            return process.terminationStatus
        } onCancel: {
            cancellation.terminate()
        }
    }
}

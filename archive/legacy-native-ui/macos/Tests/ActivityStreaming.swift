import Foundation

@main
struct ActivityStreamingTest {
    @MainActor static func main() async throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = ["-c", "printf 'first\\n'; sleep 1; printf 'error\\n' >&2; printf 'caf\\303'; sleep 0.1; printf '\\251'; exit 7"]
        var output = ""
        var receivedBeforeExit = false
        let status = try await BackendRunner.run(process) { line in
            output += line
            if line == "first\n" { receivedBeforeExit = process.isRunning }
        }
        precondition(receivedBeforeExit, "Output was delayed until process exit")
        precondition(status == 7, "Nonzero exit status was lost")
        precondition(output == "first\nerror\ncafé\n", "Missing stderr, final line, or split UTF-8: \(output)")

        let large = Process()
        large.executableURL = URL(fileURLWithPath: "/bin/sh")
        large.arguments = ["-c", "i=0; while [ $i -lt 10000 ]; do printf 'progress message\\n'; i=$((i+1)); done"]
        var lines = 0
        let largeStatus = try await BackendRunner.run(large) { _ in lines += 1 }
        precondition(largeStatus == 0 && lines == 10000, "Large output was not fully drained")

        let missing = Process()
        missing.executableURL = URL(fileURLWithPath: "/nonexistent/sugar-backend")
        do {
            _ = try await BackendRunner.run(missing) { _ in }
            preconditionFailure("Missing executable should throw")
        } catch { }
        print("PASS: live delivery, stderr, split UTF-8, final line, exit status, large output, launch failure")
    }
}

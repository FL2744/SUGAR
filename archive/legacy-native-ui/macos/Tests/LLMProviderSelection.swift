import Foundation

@main
struct LLMProviderSelectionTest {
    static func main() {
        var selection = LLMSelection()
        precondition(selection.provider == .openAI)
        precondition(selection.model == "gpt-5.6-luna")
        selection.model = "gpt-5.6-sol"
        selection.provider = .arc
        precondition(selection.model == "gpt-oss-120b")
        selection.model = "Kimi-K3"
        selection.provider = .custom
        precondition(selection.model.isEmpty)
        selection.model = "local-model"
        selection.provider = .openAI
        precondition(selection.model == "gpt-5.6-sol")
        selection.provider = .arc
        precondition(selection.model == "Kimi-K3")
        selection.provider = .custom
        precondition(selection.model == "local-model")
        precondition(Set(LLMProvider.allCases.map(\.keychainAccount)).count == 3)
        for provider in LLMProvider.allCases {
            let key = provider.apiKey(openAI: "openai-test", arc: "arc-test", custom: "custom-test")
            precondition(key == provider.rawValue + "-test")
            let config = provider.configuration(model: "chosen-model", customBaseURL: "https://custom.invalid/v1")
            precondition(config["provider"] == provider.rawValue && config["model"] == "chosen-model")
            precondition(config["base_url"] == (provider == .custom ? "https://custom.invalid/v1" : ""))
        }
        precondition(LLMProvider.arc.apiKey(openAI: "openai-test", arc: "", custom: "custom-test").isEmpty)
        precondition(LLMProvider.openAI.apiKey(openAI: "", arc: "arc-test", custom: "custom-test").isEmpty)
        print("PASS: provider defaults, independent model selections, separate key accounts, key routing, no fallback to another provider, URL isolation")
    }
}

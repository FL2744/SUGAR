import Foundation

// Model catalogs checked against official provider documentation on 2026-09-10.
enum LLMProvider: String, CaseIterable, Identifiable {
    case openAI = "openai", arc, custom
    var id: String { rawValue }
    var title: String {
        switch self {
        case .openAI: "OpenAI"
        case .arc: "Virginia Tech ARC (llm.arc.vt.edu)"
        case .custom: "Custom endpoint"
        }
    }
    var models: [String] {
        switch self {
        case .openAI: ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"]
        case .arc: ["gpt-oss-120b", "DeepSeek-V4-Flash", "GLM-5.3", "Kimi-K3"]
        case .custom: []
        }
    }
    var defaultModel: String { models.first ?? "" }
    var keychainAccount: String {
        switch self {
        case .openAI: "openAIAPIKey"
        case .arc: "arcAPIKey"
        case .custom: "customLLMAPIKey"
        }
    }
    func apiKey(openAI: String, arc: String, custom: String) -> String {
        switch self {
        case .openAI: openAI
        case .arc: arc
        case .custom: custom
        }
    }
    func configuration(model: String, customBaseURL: String) -> [String: String] {
        ["provider": rawValue, "model": model,
         "base_url": self == .custom ? customBaseURL : ""]
    }
}

struct LLMSelection {
    var provider: LLMProvider = .openAI
    private var models: [LLMProvider: String] = [:]
    var model: String {
        get { models[provider] ?? provider.defaultModel }
        set { models[provider] = newValue }
    }
}

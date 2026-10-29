import Foundation
import Combine

@MainActor final class ShopStore: ObservableObject {
    @Published var deals: DealResults?
    @Published var products: [Product] = []
    @Published var saved: [Deal] = []
    @Published var messages: [Message] = []
    @Published var status: Status?
    @Published var hunting = false
    @Published var discovering = false
    @Published var chatting = false
    @Published var error: String?
    @Published var tab = 0
    private var chatTask: Task<Void, Never>?
    var base: String { UserDefaults.standard.string(forKey: "gatewayURL") ?? "http://127.0.0.1:4100" }
    init() { if let data = UserDefaults.standard.data(forKey: "savedDeals"), let items = try? JSONDecoder().decode([Deal].self, from: data) { saved = items } }
    func refreshStatus() async { do { status = try await API(base: base).call("status") } catch { status = nil; self.error = "Cannot reach the platform. Check Connection settings." } }
    func hunt(_ value: HuntRequest) async { hunting = true; error = nil; defer { hunting = false }; do { deals = try await API(base: base).call("deals", body: API.encode(value)) } catch { self.error = error.localizedDescription } }
    func discover(_ query: String, demo: Bool) async { discovering = true; error = nil; defer { discovering = false }; do { let result: ProductResults = try await API(base: base).call("products", query: [.init(name: "query", value: query), .init(name: "include_synthetic", value: String(demo))]); products = result.products } catch { self.error = error.localizedDescription } }
    func toggle(_ deal: Deal) { if let i = saved.firstIndex(where: { $0.id == deal.id }) { saved.remove(at: i) } else { saved.insert(deal, at: 0); saved = Array(saved.prefix(50)) }; if let data = try? JSONEncoder().encode(saved) { UserDefaults.standard.set(data, forKey: "savedDeals") } }
    func send(_ text: String, model: Bool) { guard !chatting, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }; let request = ChatRequest(message: text, history: messages.suffix(20).map { WireTurn(role: $0.role, content: String($0.content.prefix(8000))) }); messages.append(Message(role: "user", content: text)); chatting = true; error = nil
        chatTask = Task { defer { chatting = false }; do { let reply: Reply = try await API(base: base).call("chat", body: API.encode(request), query: [.init(name: "mode", value: model ? "model" : "data")]); messages.append(Message(role: "assistant", content: reply.answer)) } catch { self.error = Task.isCancelled ? "Response stopped." : error.localizedDescription } }
    }
    func stop() { chatTask?.cancel(); chatting = false }
}

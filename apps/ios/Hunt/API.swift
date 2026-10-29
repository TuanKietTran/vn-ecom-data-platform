import Foundation

struct API {
    let base: String
    func call<T: Decodable>(_ path: String, body: Data? = nil, query: [URLQueryItem] = []) async throws -> T {
        guard let root = URL(string: base), ["http", "https"].contains(root.scheme ?? ""), root.host != nil,
              var parts = URLComponents(url: root.appendingPathComponent(path), resolvingAgainstBaseURL: false) else { throw ClientError.message("Set a valid gateway URL in Connection settings.") }
        parts.queryItems = query.isEmpty ? nil : query
        guard let url = parts.url else { throw ClientError.message("The gateway URL is invalid.") }
        var request = URLRequest(url: url, timeoutInterval: 65)
        if let body { request.httpMethod = "POST"; request.httpBody = body; request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ClientError.message("No response from the service.") }
        guard (200..<300).contains(http.statusCode) else {
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            throw ClientError.message(json?["message"] as? String ?? json?["detail"] as? String ?? "The platform could not complete this request.")
        }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    static func encode<T: Encodable>(_ value: T) throws -> Data { let e = JSONEncoder(); e.keyEncodingStrategy = .convertToSnakeCase; return try e.encode(value) }
}
enum ClientError: LocalizedError { case message(String); var errorDescription: String? { if case .message(let text) = self { return text }; return nil } }
func money(_ value: Int64?) -> String { guard let value else { return "Not yet known" }; return value.formatted(.number) + " ₫" }
func observedTime(_ raw: String) -> String {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let value = fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    return value?.formatted(date: .abbreviated, time: .shortened) ?? raw
}
func safeURL(_ value: String?) -> URL? { guard let value, let url = URL(string: value), ["http", "https"].contains(url.scheme ?? "") else { return nil }; return url }

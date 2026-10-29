import Foundation

struct Offer: Codable, Identifiable {
    let offerId: String
    let productKey: String
    let title: String
    let platform: String
    let seller: String
    let priceVnd: Int64
    let shippingVnd: Int64?
    let observedAt: String
    let source: String
    let sourceTier: String
    let url: String?
    let variantVerified: Bool
    var id: String { offerId }
}
struct Discount: Codable { let code: String; let scope: String; let discountVnd: Int64 }
struct Deal: Codable, Identifiable {
    let offer: Offer
    let checkoutVnd: Int64?
    let shippingAfterDiscountVnd: Int64?
    let discounts: [Discount]
    let cashbackVnd: Int64
    let conditions: [String]
    let voucherCodes: [String]
    let eligible: Bool
    let withinTarget: Bool?
    let checkedAt: String
    let lowestObservedItemPriceVnd: Int64?
    let priceHistoryDays: Int
    var id: String { offer.offerId }
}
struct DealResults: Decodable { let eligible: [Deal]; let conditional: [Deal]; let fewestConditions: [Deal]; let priceHistory: [Deal]?; let notice: String }
struct Product: Decodable, Identifiable { let indexId: String; let title: String; let platform: String; let sourceTier: String; let priceVnd: Int64; let capturedAt: String; let url: String?; var id: String { indexId } }
struct ProductResults: Decodable { let products: [Product] }
struct Status: Decodable { let dataAvailable: Bool; let modelConfigured: Bool; let model: String }
struct WireTurn: Codable { let role: String; let content: String }
struct Message: Identifiable { let id = UUID(); let role: String; let content: String }
struct Reply: Decodable { let answer: String; let action: String? }
struct Eligibility: Encodable { let paymentMethod: String?; let memberships: [String]?; let newUser: Bool? }
struct HuntRequest: Encodable { let query: String; let productKey: String?; let targetVnd: Int64?; let includeSynthetic: Bool; let eligibility: Eligibility }
struct ChatRequest: Encodable { let message: String; let history: [WireTurn] }

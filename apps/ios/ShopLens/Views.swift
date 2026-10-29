import SwiftUI

struct RootView: View {
    @EnvironmentObject var store: ShopStore
    @State private var settings = false
    var body: some View {
        TabView(selection: $store.tab) {
            NavigationStack { HuntView().toolbar { connection } }.tabItem { Label("Hunt", systemImage: "ticket") }.tag(0)
            NavigationStack { DiscoverView().toolbar { connection } }.tabItem { Label("Discover", systemImage: "magnifyingglass") }.tag(1)
            NavigationStack { ChatView().toolbar { connection } }.tabItem { Label("Ask", systemImage: "bubble.left.and.bubble.right") }.tag(2)
            NavigationStack { List { if store.saved.isEmpty { ContentUnavailableView("No saved deals", systemImage: "heart", description: Text("Save a find from Deal hunt. Your shortlist stays on this device.")) }; ForEach(store.saved) { DealRow(deal: $0, snapshot: true) } }.navigationTitle("Saved") .toolbar { connection } }.tabItem { Label("Saved", systemImage: "heart") }.tag(3)
        }.sheet(isPresented: $settings) { ConnectionView() }.task { await store.refreshStatus() }
        .alert("ShopLens", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) { Button("OK") { store.error = nil } } message: { Text(store.error ?? "") }
    }
    @ToolbarContentBuilder var connection: some ToolbarContent { ToolbarItem(placement: .topBarTrailing) { Button { settings = true } label: { Image(systemName: store.status?.dataAvailable == true ? "wifi" : "wifi.slash") }.accessibilityLabel("Connection settings") } }
}
struct HuntView: View {
    @EnvironmentObject var store: ShopStore
    @State private var query = ""
    @State private var budget = ""
    @State private var payment = ""
    @State private var variant = ""
    @State private var memberships = ""
    @State private var newUser = ""
    @State private var demo = false
    @State private var eligibility = false
    @State private var ranking = 0
    var offers: [Deal] { guard let r = store.deals else { return [] }; switch ranking { case 1: return r.conditional; case 2: return r.fewestConditions; default: return r.eligible } }
    var body: some View {
        List {
            Section { Text("Find the product. Know the checkout.").font(.title2.bold()); Text("Compare eligible voucher combinations with the full price breakdown.").foregroundStyle(.secondary) }
            Section("Your hunt") { TextField("Product or exact model", text: $query).textInputAutocapitalization(.never); TextField("Target checkout price · VND", text: $budget).keyboardType(.numberPad); Toggle("Include synthetic demo offers", isOn: $demo); Button("Voucher eligibility & variant") { eligibility = true }; Button { Task { await search() } } label: { HStack { Text("Find deals"); Spacer(); if store.hunting { ProgressView() } else { Image(systemName: "arrow.up.right") } } }.disabled(store.hunting || query.trimmingCharacters(in: .whitespaces).count < 2) }
            if let results = store.deals { Section { Picker("Ranking", selection: $ranking) { Text("Eligible").tag(0); Text("Conditional").tag(1); Text("Fewer rules").tag(2) }.pickerStyle(.segmented); Text(results.notice).font(.caption).foregroundStyle(.secondary) }; if offers.isEmpty { ContentUnavailableView("No matching offers", systemImage: "ticket", description: Text("Try a specific product or change eligibility. Live offers require a validated feed.")) }; ForEach(offers) { DealRow(deal: $0) } }
            if store.deals == nil { Section { Text("Demo data is opt-in and never represents current marketplace offers.").font(.footnote).foregroundStyle(.secondary) } }
        }.navigationTitle("Deal hunt").sheet(isPresented: $eligibility) { NavigationStack { Form { Section("Eligibility · leave unknown when unsure") { TextField("Payment method", text: $payment); TextField("Memberships, comma-separated", text: $memberships); Picker("New user", selection: $newUser) { Text("Unknown").tag(""); Text("Eligible").tag("yes"); Text("Not eligible").tag("no") } }; Section("Exact variant") { TextField("Model, color, capacity & warranty key", text: $variant) }; Text("Eligibility is used for this search. We do not create a personal profile.").font(.footnote).foregroundStyle(.secondary) }.navigationTitle("Voucher eligibility").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { eligibility = false } } } }.presentationDetents([.medium, .large]) }
    }
    func search() async { await store.hunt(HuntRequest(query: query, productKey: variant.isEmpty ? nil : variant, targetVnd: Int64(budget), includeSynthetic: demo, eligibility: Eligibility(paymentMethod: payment.isEmpty ? nil : payment, memberships: memberships.isEmpty ? nil : memberships.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }, newUser: newUser.isEmpty ? nil : newUser == "yes"))) }
}
struct DealRow: View {
    @EnvironmentObject var store: ShopStore
    let deal: Deal
    var snapshot = false
    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                HStack { Label(deal.offer.sourceTier == "synthetic" ? "Synthetic demo" : deal.offer.sourceTier.capitalized, systemImage: "ticket").font(.caption); Spacer(); Button { store.toggle(deal) } label: { Image(systemName: store.saved.contains(where: { $0.id == deal.id }) ? "heart.fill" : "heart") }.buttonStyle(.borderless).accessibilityLabel("Toggle saved deal") }
                Text(deal.offer.title).font(.headline)
                Text(deal.offer.seller + " · " + deal.offer.platform).font(.subheadline).foregroundStyle(.secondary)
                Text(money(deal.checkoutVnd)).font(.title.bold()).monospacedDigit()
                Text(deal.eligible ? "Eligible estimate · confirm at checkout" : "Conditions apply").font(.caption).foregroundStyle(deal.eligible ? Color.green : Color.orange)
                if snapshot { Text("Saved snapshot. Recheck availability and price.").font(.caption).foregroundStyle(.secondary) }
                DisclosureGroup("How this price works") { VStack(spacing: 10) { price("Item", deal.offer.priceVnd); ForEach(deal.discounts, id: \.code) { d in HStack { Text(d.code); Spacer(); Text("−" + money(d.discountVnd)) }.font(.caption) }; price("Delivery after vouchers", deal.shippingAfterDiscountVnd); price("Payable estimate", deal.checkoutVnd); price("Future cashback · separate", deal.cashbackVnd); Text("Variant: " + deal.offer.productKey).font(.caption); Text("Observed: " + observedTime(deal.offer.observedAt)).font(.caption).foregroundStyle(.secondary); if let low = deal.lowestObservedItemPriceVnd { Text("Prior item low: \(money(low)) · \(deal.priceHistoryDays) observed dates. Gaps may exist; before vouchers.").font(.caption) } }.padding(.top, 10) }
                ForEach(deal.conditions, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
                if let url = safeURL(deal.offer.url) { Link("View listing", destination: url) }
            }.padding(.vertical, 8)
        }
    }
    func price(_ label: String, _ amount: Int64?) -> some View { HStack { Text(label); Spacer(); Text(money(amount)).monospacedDigit() }.font(.caption) }
}
struct DiscoverView: View {
    @EnvironmentObject var store: ShopStore
    @State private var query = ""
    @State private var demo = false
    var body: some View { List { Section { TextField("Product, model or brand", text: $query); Toggle("Include synthetic data", isOn: $demo); Button("Search products") { Task { await store.discover(query, demo: demo) } }.disabled(query.count < 2 || store.discovering) }; ForEach(store.products) { p in VStack(alignment: .leading, spacing: 7) { Text(p.title).font(.headline); Text(money(p.priceVnd)).monospacedDigit(); Text(p.platform + " · " + p.sourceTier).font(.caption).foregroundStyle(.secondary); Text("Observed: " + observedTime(p.capturedAt)).font(.caption).foregroundStyle(.secondary); Text("Candidate listing. Confirm the exact variant; shipping and vouchers are separate.").font(.caption).foregroundStyle(.secondary); if let url = safeURL(p.url) { Link("View listing", destination: url) } } }; if store.products.isEmpty { ContentUnavailableView("Find something specific", systemImage: "magnifyingglass", description: Text("Search fresh indexed listings. We never infer products from platform averages.")) } }.navigationTitle("Discover") }
}
struct ChatView: View {
    @EnvironmentObject var store: ShopStore
    @State private var draft = ""
    @State private var model = false
    var body: some View { VStack(spacing: 0) { ScrollViewReader { proxy in ScrollView { LazyVStack(alignment: .leading, spacing: 22) { if store.messages.isEmpty { ContentUnavailableView("Ask before checkout", systemImage: "bubble.left.and.bubble.right", description: Text("Try “Compare GMV yesterday” or “Help me combine vouchers”.")) }; ForEach(store.messages) { m in VStack(alignment: .leading, spacing: 8) { Text(m.role == "user" ? "You" : "ShopLens").font(.caption.bold()).foregroundStyle(.secondary); Text(m.content).textSelection(.enabled); if m.role == "assistant", m.content.contains("Deal hunt") { Button("Open Deal hunt") { store.tab = 0 } } }.frame(maxWidth: .infinity, alignment: m.role == "user" ? .trailing : .leading).id(m.id) }; if store.chatting { ProgressView("Checking evidence…") } }.padding() }.onChange(of: store.messages.count) { _, _ in if let id = store.messages.last?.id { withAnimation { proxy.scrollTo(id, anchor: .bottom) } } } }; Divider(); VStack(spacing: 10) { Toggle(store.status?.modelConfigured == true ? "Use \(store.status?.model ?? "model")" : "Data mode · model not connected", isOn: $model).disabled(store.status?.modelConfigured != true || store.chatting).font(.caption); HStack(alignment: .bottom) { TextField("Ask about your data…", text: $draft, axis: .vertical).lineLimit(1...5).textFieldStyle(.roundedBorder); Button { if store.chatting { store.stop() } else { let text = draft; draft = ""; store.send(text, model: model) } } label: { Image(systemName: store.chatting ? "stop.circle.fill" : "arrow.up.circle.fill").font(.title) }.disabled(!store.chatting && draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityLabel(store.chatting ? "Stop response" : "Send message") }; Text(model ? "Messages and gold context go to the configured model provider." : "Fixed data queries and product search. No LLM.").font(.caption2).foregroundStyle(.secondary) }.padding() }.navigationTitle("Ask ShopLens").toolbar { ToolbarItem(placement: .topBarLeading) { Button("New") { store.messages = [] }.disabled(store.chatting) } } }
}
struct ConnectionView: View {
    @EnvironmentObject var store: ShopStore
    @Environment(\.dismiss) private var dismiss
    @AppStorage("gatewayURL") private var url = "http://127.0.0.1:4100"
    var body: some View { NavigationStack { Form { Section("Client gateway URL") { TextField("https://your-gateway", text: $url).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled(); Text("The simulator can use localhost. A physical device needs a reachable gateway address. Release builds require HTTPS. Do not enter model API keys here.").font(.footnote).foregroundStyle(.secondary) }; Section { Label(store.status?.dataAvailable == true ? "Platform data available" : "Platform not connected", systemImage: "network"); Button("Test connection") { Task { await store.refreshStatus() } } } }.navigationTitle("Connection").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } } }
}

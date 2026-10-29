import SwiftUI

@main
@MainActor
struct ShopLensApp: App {
    @StateObject private var store = ShopStore()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(store).tint(.red) }
    }
}

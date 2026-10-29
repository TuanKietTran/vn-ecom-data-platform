import SwiftUI

@main
@MainActor
struct HuntApp: App {
    @StateObject private var store = HuntStore()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(store).tint(Color(red: 0.0, green: 0.35, blue: 0.95)) }
    }
}

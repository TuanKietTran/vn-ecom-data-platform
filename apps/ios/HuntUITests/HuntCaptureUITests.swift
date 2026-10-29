import XCTest

@MainActor
final class HuntCaptureUITests: XCTestCase {
    func testCaptureRealHuntNavigationStates() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-no-network"]
        app.launch()

        XCTAssertTrue(app.staticTexts["Upcoming voucher windows"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)
        attachCurrentScreen(app, name: "hunt-home-chat-upcoming-widget")

        for tab in ["Hunt", "Discover", "Saved"] {
            let control = app.tabBars.buttons[tab]
            XCTAssertTrue(control.waitForExistence(timeout: 5), "Missing native tab: \(tab)")
            control.tap()
            attachCurrentScreen(app, name: "hunt-\(tab.lowercased())")
        }
    }

    private func attachCurrentScreen(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}

import Carbon
import Foundation
import ServiceManagement
import XCTest
@testable import PivokiApp

private final class TestLoginService: LoginItemService {
    var status: SMAppService.Status = .notFound
    var result: SMAppService.Status = .enabled
    var fail = false
    var registrations = 0

    func register() throws {
        registrations += 1
        if fail { throw CocoaError(.fileWriteNoPermission) }
        status = result
    }

    func unregister() throws { status = .notRegistered }
}

final class LoginItemTests: XCTestCase {
    private let suite = "Pivoki.LoginItemTests." + UUID().uuidString
    private var defaults: UserDefaults { UserDefaults(suiteName: suite)! }
    private let service = TestLoginService()

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        super.tearDown()
    }

    private func launch() -> LoginItemController {
        let controller = LoginItemController(service: service, defaults: defaults)
        controller.applyDefault()
        return controller
    }

    func testFirstLaunchRegistersEvenWhenMacOSHasNoRecord() {
        XCTAssertEqual(launch().status, .enabled)
        XCTAssertEqual(launch().status, .enabled)
        XCTAssertEqual(service.registrations, 1)
    }

    func testFreshNotRegisteredAccountAlsoGetsDefault() {
        service.status = .notRegistered
        XCTAssertEqual(launch().status, .enabled)
    }

    func testOptOutSurvivesRelaunchAndCanBeReversed() {
        let controller = launch()
        controller.setEnabled(false)
        XCTAssertEqual(launch().status, .notRegistered)
        XCTAssertEqual(service.registrations, 1)
        controller.setEnabled(true)
        XCTAssertEqual(controller.status, .enabled)
    }

    func testRespectsSystemSettingsAndRefreshesAfterApproval() {
        service.result = .requiresApproval
        let controller = launch()
        XCTAssertEqual(controller.status, .requiresApproval)
        service.status = .enabled
        controller.refresh()
        XCTAssertEqual(controller.status, .enabled)
        service.status = .notFound
        XCTAssertEqual(launch().status, .notFound)
        XCTAssertEqual(service.registrations, 1)
    }

    func testExistingSystemRegistrationsNeedNoSecondRequest() {
        for status: SMAppService.Status in [.enabled, .requiresApproval] {
            defaults.removePersistentDomain(forName: suite)
            service.status = status
            XCTAssertEqual(launch().status, status)
            service.status = .notRegistered
            XCTAssertEqual(launch().status, .notRegistered)
        }
        XCTAssertEqual(service.registrations, 0)
    }

    func testMigrationPreservesAnExistingUnregisteredItem() {
        defaults.set(true, forKey: "hasOpened")
        service.status = .notRegistered
        XCTAssertEqual(launch().status, .notRegistered)
        XCTAssertEqual(service.registrations, 0)
    }

    func testFirstLaunchFromDiskImageDefersUntilAfterInstallation() {
        service.status = .notRegistered
        let preview = LoginItemController(service: service, defaults: defaults, canRegister: false)
        preview.applyDefault()
        XCTAssertEqual(service.registrations, 0)
        defaults.set(true, forKey: "hasOpened")
        XCTAssertEqual(launch().status, .enabled)
    }

    func testUserCanRetryAfterRegistrationFailure() {
        service.fail = true
        let controller = launch()
        XCTAssertNotNil(controller.errorMessage)
        XCTAssertEqual(controller.status, .notFound)
        service.fail = false
        controller.setEnabled(true)
        XCTAssertNil(controller.errorMessage)
        XCTAssertEqual(controller.status, .enabled)
    }

    func testLoginAppleEventKeepsTheHomeWindowClosed() {
        let event = NSAppleEventDescriptor(eventClass: AEEventClass(kCoreEventClass), eventID: AEEventID(kAEOpenApplication),
                                           targetDescriptor: nil, returnID: AEReturnID(kAutoGenerateReturnID), transactionID: AETransactionID(kAnyTransactionID))
        XCTAssertFalse(AppDelegate.isLoginLaunch(event))
        event.setParam(NSAppleEventDescriptor(enumCode: OSType(keyAELaunchedAsLogInItem)), forKeyword: AEKeyword(keyAEPropData))
        XCTAssertTrue(AppDelegate.isLoginLaunch(event))
    }
}

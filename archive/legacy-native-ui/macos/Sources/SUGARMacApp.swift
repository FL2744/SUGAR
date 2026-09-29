import SwiftUI

@main
struct SUGARMacApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
                .frame(minWidth: 940, minHeight: 680)
        }
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
        Settings {
            SettingsView().environmentObject(model).frame(width: 520, height: 360)
        }
    }
}

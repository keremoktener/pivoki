import AppKit
import SwiftUI
import PivokiCore
import UniformTypeIdentifiers
import ApplicationServices

struct SettingsView:View {
    @State private var section=SettingsSection.general
    @State private var selectedFormat="jpg"
    @State private var formatSearch=""
    @ObservedObject private var preferences=FormatPreferences.shared
    @AppStorage("enabled") private var enabled=true
    @AppStorage("reveal") private var reveal=true
    @AppStorage(StatusMenuItem.defaultsKey) private var hiddenStatusMenuItems=""
    @AppStorage("wheelScale") private var wheelScale=1.0
    @AppStorage("conversionFanTheme") private var fanTheme="glass"
    @AppStorage("soundsAndHapticsEnabled") private var feedback=true
    @AppStorage("floatWheelBehavior") private var floatBehavior="createNew"
    @AppStorage("fileActionsTerminalApplication") private var terminalApplication="com.apple.Terminal"
    @State private var shortcutsRevision=0
    @AppStorage("reduceAnimations") private var reduceAnimations=false
    @AppStorage("appAppearance") private var appAppearance="system"
    @AppStorage("appLanguage") private var appLanguage="en"
    @AppStorage("windowManagementEnabled") private var windowManagementEnabled=true
    @State private var windowAccessibility=AXIsProcessTrusted()
    @Environment(\.accessibilityReduceMotion) private var systemReducedMotion
    init(initialSection:SettingsSection = .general) {
        _section=State(initialValue:initialSection)
    }
    private var terminalApplications:[(String,String)] {
        var apps=[("com.apple.Terminal","Terminal")]
        if NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.googlecode.iterm2") != nil { apps.append(("com.googlecode.iterm2","iTerm2")) }
        if !apps.contains(where:{$0.0==terminalApplication}) { apps.append((terminalApplication,"\(terminalApplication) (Not installed)")) }
        return apps
    }
    var body:some View {
        HStack(spacing:0) {
            sidebar
            Divider()
            Group {
                switch section {
                case .general:general
                case .wheel:WheelSettings()
                case .formats:formats
                case .compatibility:CompatibilitySettingsView { format in selectedFormat=format;section = .formats }
                case .folders:FolderSettingsView()
                case .about:AboutSettingsView()
                }
            }
            .frame(maxWidth:.infinity,maxHeight:.infinity).id(section).transition(.opacity)
        }.frame(minWidth:790,minHeight:590).background(PivokiPalette.canvas).tint(.pivoki)
        .buttonStyle(PivokiButtonStyle()).toggleStyle(.switch).groupBoxStyle(PivokiGroupBoxStyle()).pivokiAnimation(value:section)
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("PivokiWheelSettings"))) { _ in section = .wheel }
        .onChange(of:feedback) { UserDefaults.standard.set($0,forKey:"sound") }
        .onChange(of:appAppearance) { PivokiAppearance.apply($0) }
        .onChange(of:appLanguage) { _ in NotificationCenter.default.post(name:.pivokiLanguageChanged,object:nil) }
        .onChange(of:terminalApplication) { UserDefaults.standard.set($0=="com.googlecode.iterm2" ? "iTerm2":"Terminal",forKey:"terminalApp") }
    }
    private var sidebar:some View {
            VStack(alignment:.leading,spacing:24) {
                HStack(spacing:9) { PivokiMark(size:32);Text("Make it yours").font(.system(size:14,weight:.bold,design:.rounded)) }.padding(.top,20)
                VStack(spacing:5) {
                    ForEach(SettingsSection.allCases) { item in
                        Button { section=item } label:{
                            HStack(spacing:10) { Image(systemName:item.symbol).frame(width:19);LText(item.rawValue).lineLimit(1).layoutPriority(1);Spacer() }
                                .font(.system(size:12,weight:section==item ? .semibold:.medium,design:.rounded))
                                .foregroundStyle(section==item ? PivokiPalette.forest:Color.secondary)
                                .padding(.horizontal,13).padding(.vertical,12)
                                .background(section==item ? PivokiPalette.sage:Color.clear,in:RoundedRectangle(cornerRadius:12))
                                .contentShape(RoundedRectangle(cornerRadius:12))
                        }.buttonStyle(.plain).accessibilityAddTraits(section==item ? .isSelected:[])
                    }
                }
                Spacer()
                Label("Local by design",systemImage:"lock.shield").font(.system(size:10,weight:.medium,design:.rounded)).foregroundStyle(.secondary).padding(.bottom,17)
            }.padding(.horizontal,16).frame(width:204).background(PivokiPalette.inset.opacity(0.6))
    }
    private var general:some View {
        ScrollView { VStack(alignment:.leading,spacing:20) {
            PivokiPageHeading(eyebrow:"General",title:"Your kind of flow.",subtitle:"A few small preferences. A smoother everyday.").padding(.bottom,4)
            GroupBox {
                VStack(spacing:16) {
                    HStack { Text("Language");Spacer();NativeLanguagePicker(language:$appLanguage).frame(width:230,height:26) }
                    HStack { Text("Appearance");Spacer();Picker("Appearance",selection:$appAppearance) { Text("System").tag("system");Text("Light").tag("light");Text("Dark").tag("dark") }.labelsHidden().pickerStyle(.segmented).frame(width:230) }
                    HStack { Text("Wheel finish");Spacer();Picker("Wheel finish",selection:$fanTheme) { Text("Glass").tag("glass");Text("Solid").tag("metallic") }.labelsHidden().pickerStyle(.segmented).frame(width:230) }
                    Divider()
                    LoginItemToggle(title: "Launch at login")
                    HStack {
                        Toggle("Sound and haptic feedback",isOn:$feedback)
                        Button("Try feedback") { _ = WheelFeedback.shared.testPreview() }
                            .disabled(!feedback)
                    }
                    Text("Sound follows your Mac’s volume. Haptics need a compatible Force Touch trackpad.")
                        .font(.caption).foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading)
                    Toggle("Subtle animations",isOn:Binding(get:{!reduceAnimations},set:{reduceAnimations = !$0}))
                    if systemReducedMotion { Text("macOS Reduce Motion is on. Pivoki keeps motion off.").font(.caption).foregroundStyle(.secondary) }
                }.padding(10)
            }
            GroupBox("Drag shortcuts") {
                VStack(alignment:.leading,spacing:16) {
                    ForEach(WheelShortcut.allCases) { wheel in HStack {
                        LText(wheel.title);Spacer()
                        Picker(LocalizedStringKey(wheel.title),selection:shortcut(wheel)) { ForEach(ModifierPreferences.available(for:wheel)) { chord in Text("\(chord.symbols)  \(chord.title)").tag(chord.rawValue) } }.labelsHidden().frame(maxWidth:240)
                    } }
                    Text("Tap the chosen modifier combination while dragging files.").font(.caption).foregroundStyle(.secondary)
                }.padding(10)
            }.id(shortcutsRevision)
            GroupBox("Window management") {
                VStack(alignment:.leading,spacing:13) {
                    Toggle("Arrange windows while dragging",isOn:$windowManagementEnabled)
                    Text("Drag a window by its title bar or resize border, then tap Shift or Command. Hover over a layout and release the mouse to place it. Escape cancels.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("1/3 left · middle · right   /   1/2 left · right   /   2/3 left · right")
                        .font(.caption).foregroundStyle(.secondary)
                    if !windowAccessibility {
                        HStack {
                            Text("Allow \(WindowManagementController.permissionName) once to move and resize other apps’ windows.").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Open permission settings…") { WindowManagementController.requestAccess() }
                        }
                    } else { Label("\(WindowManagementController.permissionName) is enabled",systemImage:"checkmark.circle").font(.caption).foregroundStyle(.secondary) }
                }.padding(10)
            }
            .onReceive(Timer.publish(every:2,on:.main,in:.common).autoconnect()) { _ in windowAccessibility=AXIsProcessTrusted() }
            GroupBox("Menu bar") {
                VStack(alignment:.leading,spacing:10) {
                    Text("Choose what appears when you click the Pivoki icon in the menu bar. Settings and Quit are always shown.").font(.caption).foregroundStyle(.secondary)
                    ForEach(StatusMenuItem.allCases) { row in Toggle(LocalizedStringKey(row.label),isOn:statusMenuBinding(row)) }
                }.frame(maxWidth:.infinity,alignment:.leading).padding(10)
            }
            GroupBox("File actions") {
                VStack(spacing:16) {
                    HStack { Text("Float Behaviour");Spacer();Picker("Float behavior",selection:$floatBehavior) { Text("Create a New Float").tag("createNew");Text("Add Files to an Existing Float").tag("addToExisting") }.labelsHidden().frame(maxWidth:240) }
                    HStack { Text("Terminal app");Spacer();Picker("Terminal app",selection:$terminalApplication) { ForEach(terminalApplications,id:\.0) { app in Text(app.1).tag(app.0) } }.labelsHidden().frame(maxWidth:240) }
                }.padding(10)
            }
            DisclosureGroup("Additional options") { VStack(alignment:.leading,spacing:13) {
                Toggle("Enable Pivoki",isOn:$enabled)
                Toggle("Reveal finished files in Finder",isOn:$reveal)
                HStack { Text("Wheel size");Slider(value:$wheelScale,in:0.85...1.4).frame(width:230);Text(Int(wheelScale*100),format:.percent).monospacedDigit().frame(width:40) }
            }.padding(.top,12) }
        }.padding(26).frame(maxWidth:680) }.frame(maxWidth:.infinity)
    }
    private var formats:some View {
        HStack(spacing:0) {
            VStack(spacing:0) {
                TextField("Search formats",text:$formatSearch).textFieldStyle(.roundedBorder).padding(12)
                List(selection:$selectedFormat) {
                    ForEach(FormatPreferenceItem.groups,id:\.0) { group in
                        let entries=FormatPreferenceItem.all.filter{$0.group==group.0 && (formatSearch.isEmpty || $0.title.localizedCaseInsensitiveContains(formatSearch) || $0.id.localizedCaseInsensitiveContains(formatSearch))}
                        if !entries.isEmpty { Section(LocalizedStringKey(group.0)) { ForEach(entries) { item in Text(item.id=="gz" ? "GZIP":item.id.uppercased()).tag(item.id) } } }
                    }
                }.listStyle(.sidebar)
            }.frame(width:154).background(PivokiPalette.surface)
            Divider()
            FormatSettingsDetail(format:FormatPreferenceItem.all.first{$0.id==selectedFormat} ?? FormatPreferenceItem.all[0],preferences:preferences).frame(maxWidth:.infinity,maxHeight:.infinity)
        }
    }
    private func statusMenuBinding(_ row:StatusMenuItem)->Binding<Bool> {
        Binding(get:{ !hiddenStatusMenuItems.split(separator:"\n").contains(Substring(row.rawValue)) },set:{ visible in
            var hidden=Set(hiddenStatusMenuItems.split(separator:"\n").map(String.init))
            if visible { hidden.remove(row.rawValue) } else { hidden.insert(row.rawValue) }
            hiddenStatusMenuItems=hidden.sorted().joined(separator:"\n")
        })
    }
    private func shortcut(_ wheel:WheelShortcut)->Binding<UInt> {
        Binding(get:{ModifierPreferences.chord(for:wheel).rawValue},set:{if ModifierPreferences.set(.init(rawValue:$0),for:wheel) { shortcutsRevision += 1 }})
    }

}

enum SettingsSection:String,CaseIterable,Identifiable {
    case general="General",wheel="Wheel",formats="Formats",compatibility="Compatibility",folders="Folders",about="About"
    var id:String { rawValue }
    var symbol:String { switch self { case .general:return "gearshape";case .wheel:return "circle.hexagongrid";case .formats:return "doc.on.doc";case .compatibility:return "square.grid.3x3";case .folders:return "folder";case .about:return "info.circle" } }
}

private struct FormatSettingsDetail:View {
    let format:FormatPreferenceItem
    @ObservedObject var preferences:FormatPreferences
    private var isVideo:Bool { ["mp4","mov","mkv","webm","avi","wmv"].contains(format.id) }
    private var hasQuality:Bool { ["jpg","webp","heic","avif"].contains(format.id) || isVideo }
    private var hasMetadata:Bool { ["jpg","png","webp","heic","tiff","avif"].contains(format.id) }
    private var hasAudioBitrate:Bool { ["mp3","m4a","ogg","opus","wma"].contains(format.id) }
    private var hasDepth:Bool { ["wav","aiff"].contains(format.id) }
    private var hasCompression:Bool { ["flac","zip","gz"].contains(format.id) }
    private var hasLayout:Bool { ["docx","pages","epub"].contains(format.id) }
    private var hasControls:Bool { hasQuality || hasMetadata || hasAudioBitrate || hasDepth || hasCompression || hasLayout || format.id=="gif" }
    var body:some View {
        ScrollView { VStack(alignment:.leading,spacing:20) {
            PivokiPageHeading(eyebrow:"Format preferences",title:"\(format.title) \(format.isInputOnly ? "input":"exports")",subtitle:format.isInputOnly ? "Bring this format in, then choose its next form.":"Your go-to settings whenever you save a \(format.title) file.")
            LText(format.compatibilityLabel).font(.caption).foregroundStyle(.secondary)
            if format.isInputOnly { Text("This format can be imported. Choose an output format in the sidebar to configure its defaults.").foregroundStyle(.secondary).padding(.vertical,14) }
            else if hasControls {
                GroupBox { VStack(alignment:.leading,spacing:18) {
                    HStack { Text("Conversion Settings").font(.headline);Spacer();Button("Restore Defaults") { preferences.restoreDefaults(for:format.id) }.controlSize(.small) }
                    Divider()
                    if hasQuality { row("Quality") { Picker("Quality",selection:profile(\.quality)) { ForEach(OutputQuality.allCases) { LText($0.title).tag($0) } }.labelsHidden() } }
                    if hasMetadata { Toggle("Preserve metadata",isOn:profile(\.preserveMetadata)) }
                    if hasAudioBitrate { row("Bitrate") { Picker("Audio bitrate",selection:profile(\.audioBitrate)) { ForEach([128,192,256,320],id:\.self) { Text("\($0) kbps").tag($0) } }.labelsHidden() } }
                    if hasDepth { row("Sample depth") { Picker("Sample depth",selection:profile(\.audioSampleDepth)) { Text("Match Source").tag("matchSource");Text("16-bit integer").tag("pcm16");Text("24-bit integer").tag("pcm24");Text("32-bit integer").tag("pcm32");Text("32-bit float").tag("float32") }.labelsHidden() } }
                    if isVideo { row("Maximum height") { Picker("Maximum video height",selection:profile(\.videoMaxHeight)) { Text("Original").tag(0);ForEach([2160,1080,720,480],id:\.self) { Text("\($0)p").tag($0) } }.labelsHidden() } }
                    if hasCompression { row("Compression") { compressionPicker(profile(\.compressionPreset)) } }
                    if format.id=="gif" {
                        row("Frame rate") { Picker("GIF frame rate",selection:profile(\.gifFrameRate)) { ForEach([10,15,24],id:\.self) { Text("\($0) fps").tag($0) } }.labelsHidden() }
                        row("Maximum width") { Picker("GIF maximum width",selection:profile(\.gifMaxWidth)) { ForEach([480,960,1280],id:\.self) { Text("\($0) px").tag($0) } }.labelsHidden() }
                        row("Compression") { compressionPicker(profile(\.compressionPreset)) }
                    }
                    if ["docx","pages"].contains(format.id) { row("PDF layout") { Picker("PDF output layout",selection:profile(\.pdfOfficeLayout)) { Text("Editable paragraphs and tables").tag("editable");Text("Preserve original pages").tag("preservePages") }.labelsHidden() } }
                    if format.id=="epub" { row("PDF layout") { Picker("EPUB layout",selection:profile(\.epubLayout)) { Text("Reflowable text").tag("reflowable");Text("Preserve original pages").tag("fixed") }.labelsHidden() } }
                }.padding(12) }
            } else { Text("This output format has no adjustable conversion defaults.").foregroundStyle(.secondary).padding(.vertical,14) }
            if ["jpg","png"].contains(format.id) { imageCompression }
            if isVideo || format.id=="gif" { videoCompression }
            Spacer(minLength:12)
        }.padding(14) }.id(format.id)
    }
    private var imageCompression:some View {
        GroupBox { VStack(alignment:.leading,spacing:17) {
            HStack { Text("Compression Settings").font(.headline);Spacer();Button("Restore Defaults") { preferences.restoreCompressionDefaults(video:false) }.controlSize(.small) }
            Divider()
            row("Image Compression") { Picker("Image compression",selection:Binding(get:{preferences.imageCompressionStrength},set:{preferences.setCompression($0,key:"defaultImageCompressionStrength")})) { Text("Balanced").tag("balanced");Text("Strong").tag("strong") }.labelsHidden() }
            row("Image size") { Picker("Image size",selection:Binding(get:{preferences.imageCompressionSize},set:{preferences.setCompression($0,key:"defaultImageCompressionSize")})) { Text("Keep original dimensions").tag("original");Text("Large · 2560 px").tag("large");Text("Medium · 1920 px").tag("medium");Text("Small · 1280 px").tag("small") }.labelsHidden() }
        }.padding(12) }
    }
    private var videoCompression:some View {
        GroupBox { VStack(alignment:.leading,spacing:17) {
            HStack { Text("Compression Settings").font(.headline);Spacer();Button("Restore Defaults") { preferences.restoreCompressionDefaults(video:true) }.controlSize(.small) }
            Divider()
            row("Video Compression") { Picker("Video compression",selection:Binding(get:{preferences.videoCompressionStrength},set:{preferences.setCompression($0,key:"defaultVideoCompressionStrength")})) { Text("Balanced").tag("balanced");Text("Strong").tag("strong") }.labelsHidden() }
        }.padding(12) }
    }
    private func profile<T>(_ key:WritableKeyPath<OutputFormatProfile,T>)->Binding<T> {
        Binding(get:{preferences.profile(for:format.id)[keyPath:key]},set:{value in var p=preferences.profile(for:format.id);p[keyPath:key]=value;preferences.save(p,for:format.id)})
    }
    private func row<Content:View>(_ title:String,@ViewBuilder content:()->Content)->some View { HStack(alignment:.center,spacing:12) { LText(title);Spacer(minLength:8);content().frame(maxWidth:260) } }
    private func compressionPicker(_ binding:Binding<String>)->some View { Picker("Compression",selection:binding) { Text("Faster").tag("fast");Text("Balanced").tag("balanced");Text("Smallest").tag("maximum") }.labelsHidden() }
}

private struct FolderSettingsView:View {
    @State private var folders:[AllowedFolder]=[]
    @State private var error:String?
    var body:some View {
        VStack(alignment:.leading,spacing:18) {
            Text("Folders").font(.title2.weight(.semibold))
            Text("Pivoki saves results beside the originals. Allow a folder once to include every folder inside it.").foregroundStyle(.secondary)
            if folders.isEmpty { VStack(spacing:9) { Image(systemName:"folder.badge.questionmark").font(.system(size:40)).foregroundStyle(.secondary);Text("No folders allowed yet.").foregroundStyle(.secondary) }.frame(maxWidth:.infinity,maxHeight:.infinity) }
            else { List { ForEach(folders) { grant in HStack {
                Image(systemName:"folder").foregroundStyle(Color.pivoki)
                VStack(alignment:.leading,spacing:3) { Text(URL(fileURLWithPath:grant.path).lastPathComponent);Text(grant.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                Spacer();Button { FolderAccessPreferences.remove(grant);refresh() } label:{Image(systemName:"minus.circle")}.buttonStyle(.plain).help("Remove folder access")
            } } }.listStyle(.inset) }
            if let error { LText(error).font(.caption).foregroundStyle(.red) }
            HStack { Button("Allow Folder…") { choose(home:false) };Button("Allow Home Folder Access…") { choose(home:true) };Spacer() }
        }.padding(24).onAppear(perform:refresh)
    }
    private func refresh() { folders=FolderAccessPreferences.grants() }
    private func choose(home:Bool) {
        let panel=NSOpenPanel();panel.title=L10n.text("Allow Folder Access");panel.prompt=L10n.text("Allow Access");panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.allowsMultipleSelection=true
        panel.message=L10n.text("Choose a folder where Pivoki may save results. Every folder inside it is included.")
        if home { panel.directoryURL=FileManager.default.homeDirectoryForCurrentUser }
        if panel.runModal() == .OK { do { try FolderAccessPreferences.add(panel.urls);error=nil;refresh() } catch { self.error=error.localizedDescription } }
    }
}

private struct CompatibilitySettingsView:View {
    let onSelectFormat:(String)->Void
    @State private var source="jpg"
    private var targets:[String] { FeatureCatalog.conversionMatrix[source] ?? [] }
    var body:some View {
        VStack(alignment:.leading,spacing:20) {
            Text("Format Compatibility").font(.title2.weight(.semibold))
            Text("Choose an input format to see its available outputs.").foregroundStyle(.secondary)
            Picker("Input format",selection:$source) { ForEach(FormatPreferenceItem.all.filter{!$0.isOutputOnly}) { LText($0.title).tag($0.id) } }.frame(width:270)
            Divider()
            Text("Convert to").font(.headline)
            LazyVGrid(columns:[GridItem(.adaptive(minimum:105))],alignment:.leading,spacing:12) { ForEach(targets,id:\.self) { format in Button { onSelectFormat(format) } label:{ Text(format=="gz" ? "GZIP":format.uppercased()).frame(maxWidth:.infinity).padding(.vertical,9) } } }
            Spacer()
            Text("Files are processed locally on your Mac.").font(.caption).foregroundStyle(.secondary)
        }.padding(28)
    }
}

private struct AboutSettingsView:View {
    private var version:String { Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "Development" }
    var body:some View {
        VStack(spacing:17) {
            Spacer()
            PivokiMark(size:96,happy:true)
            Text("Pivoki").font(.system(size:32,weight:.bold,design:.rounded))
            Text("Personal, non-commercial use.").font(.headline)
            Text("Version \(version)").foregroundStyle(.secondary)
            HStack {
                if let license=Bundle.main.url(forResource:"Pivoki-LICENSE",withExtension:"txt") { Button("View license") { NSWorkspace.shared.open(license) } }
                if let notices=Bundle.main.url(forResource:"THIRD-PARTY-NOTICES",withExtension:"txt") { Button("Third-party notices") { NSWorkspace.shared.open(notices) } }
            }
            Spacer()
        }.padding(30).frame(maxWidth:.infinity)
    }
}

/// Keep a named AppKit control in the accessibility tree across SwiftUI/macOS versions.
private struct NativeLanguagePicker: NSViewRepresentable {
    @Binding var language: String
    final class Coordinator: NSObject {
        var binding: Binding<String>
        init(_ binding: Binding<String>) { self.binding = binding }
        @objc func changed(_ sender: NSPopUpButton) {
            if let id = sender.selectedItem?.representedObject as? String { binding.wrappedValue = id }
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator($language) }
    func makeNSView(context: Context) -> NSPopUpButton {
        let popup = NSPopUpButton(frame:.zero, pullsDown:false)
        for (code,title) in [("en","English"),("tr","Türkçe"),("fr","Français")] {
            popup.addItem(withTitle:title); popup.lastItem?.representedObject = code
        }
        popup.target = context.coordinator
        popup.action = #selector(Coordinator.changed(_:))
        popup.setAccessibilityIdentifier("AppLanguage")
        return popup
    }
    func updateNSView(_ popup: NSPopUpButton, context: Context) {
        context.coordinator.binding = $language
        popup.setAccessibilityLabel(L10n.text("Language"))
        popup.selectItem(at: popup.indexOfItem(withRepresentedObject: language))
    }
}

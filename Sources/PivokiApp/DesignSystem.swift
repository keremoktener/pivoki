import AppKit
import SwiftUI

// One shared visual language, with native light/dark appearance and motion preferences.
enum PivokiPalette {
    static func adaptive(_ light:(Double,Double,Double),_ dark:(Double,Double,Double))->NSColor {
        NSColor(name:nil) { appearance in
            let rgb=appearance.bestMatch(from:[.darkAqua,.aqua]) == .darkAqua ? dark:light
            return NSColor(srgbRed:rgb.0,green:rgb.1,blue:rgb.2,alpha:1)
        }
    }
    static let canvas=Color(nsColor:adaptive((0.9843,0.9804,0.9647),(0.1176,0.1882,0.1490)))
    static let surface=Color(nsColor:adaptive((1,1,0.992),(0.157,0.227,0.184)))
    static let inset=Color(nsColor:adaptive((0.941,0.949,0.914),(0.102,0.161,0.125)))
    static let forest=Color(nsColor:adaptive((0.19,0.33,0.23),(0.70,0.82,0.62)))
    static let sand=Color(nsColor:adaptive((0.904,0.928,0.847),(0.171,0.255,0.187)))
    static let sage=Color(nsColor:adaptive((0.877,0.921,0.824),(0.140,0.221,0.156)))
    static let border=Color.primary.opacity(0.075)
    static let gold=adaptive((0.208,0.388,0.263),(0.843,0.929,0.600))
    static let ink=PivokiArtwork.ink
    static let goldInk=Color(nsColor:adaptive((0.208,0.388,0.263),(0.843,0.929,0.600)))
    static let buttonInk=Color(nsColor:adaptive((1,1,1),(0.125,0.161,0.129)))
    static let goldEnd=Color(nsColor:gold)
}
extension Color { static let pivoki=Color(nsColor:PivokiPalette.gold) }

enum PivokiMotion {
    static var enabled:Bool { !UserDefaults.standard.bool(forKey:"reduceAnimations") && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }
}
enum PivokiAppearance {
    @MainActor static func apply(_ choice:String?=nil) {
        let choice=choice ?? UserDefaults.standard.string(forKey:"appAppearance") ?? "system"
        NSApp.appearance=choice=="light" ? NSAppearance(named:.aqua):choice=="dark" ? NSAppearance(named:.darkAqua):nil
    }
}

struct PivokiMotionModifier<Value:Equatable>:ViewModifier {
    let value:Value
    @Environment(\.accessibilityReduceMotion) private var systemReduced
    @AppStorage("reduceAnimations") private var reduced=false
    func body(content:Content)->some View { content.animation(systemReduced || reduced ? nil:.spring(response:0.32,dampingFraction:0.88),value:value) }
}
struct PivokiEntrance:ViewModifier {
    var delay=0.0
    @State private var visible=false
    @Environment(\.accessibilityReduceMotion) private var systemReduced
    @AppStorage("reduceAnimations") private var reduced=false
    func body(content:Content)->some View {
        content.opacity(visible ? 1:0).offset(y:visible || systemReduced || reduced ? 0:8)
            .onAppear {
                if systemReduced || reduced { visible=true }
                else { withAnimation(.easeOut(duration:0.24).delay(delay)) { visible=true } }
            }
    }
}
extension View {
    func pivokiAnimation<V:Equatable>(value:V)->some View { modifier(PivokiMotionModifier(value:value)) }
    func pivokiEntrance(delay:Double=0)->some View { modifier(PivokiEntrance(delay:delay)) }
    func pivokiCard(radius:CGFloat=22)->some View {
        background(PivokiPalette.surface,in:RoundedRectangle(cornerRadius:radius,style:.continuous))
            .overlay(RoundedRectangle(cornerRadius:radius,style:.continuous).strokeBorder(PivokiPalette.border,lineWidth:1))
    }
}

enum PivokiButtonKind { case primary,secondary,quiet }
struct PivokiButtonStyle:ButtonStyle {
    var kind:PivokiButtonKind = .secondary
    var compact=false
    init(_ kind:PivokiButtonKind = .secondary,compact:Bool=false) { self.kind=kind;self.compact=compact }
    func makeBody(configuration:Configuration)->some View { PivokiButtonBody(configuration:configuration,kind:kind,compact:compact) }
}
private struct PivokiButtonBody:View {
    let configuration:ButtonStyleConfiguration
    let kind:PivokiButtonKind
    let compact:Bool
    @State private var hovered=false
    @Environment(\.isEnabled) private var enabled
    @Environment(\.isFocused) private var focused
    @Environment(\.accessibilityReduceMotion) private var systemReduced
    @AppStorage("reduceAnimations") private var reduced=false
    private var primary:Bool { kind == .primary }
    var body:some View {
        configuration.label.font(.system(size:compact ? 11:13,weight:.semibold,design:.rounded))
            .multilineTextAlignment(.center)
            .fixedSize(horizontal:false,vertical:true)
            .frame(minHeight:compact ? 14:18,alignment:.center)
            .padding(.horizontal,compact ? 10:15).padding(.vertical,compact ? 7:11)
            .foregroundStyle(primary ? PivokiPalette.buttonInk:Color.primary)
            .background {
                RoundedRectangle(cornerRadius:compact ? 10:13,style:.continuous)
                    .fill(primary ? AnyShapeStyle(LinearGradient(colors:[Color.pivoki,PivokiPalette.goldEnd],startPoint:.leading,endPoint:.trailing)):AnyShapeStyle(kind == .quiet ? Color.clear:PivokiPalette.surface))
                    .overlay(RoundedRectangle(cornerRadius:compact ? 10:13,style:.continuous).strokeBorder(primary ? Color.white.opacity(0.12):PivokiPalette.border,lineWidth:kind == .quiet ? 0:1))
            }
            .overlay(RoundedRectangle(cornerRadius:compact ? 10:13).fill(Color.primary.opacity(hovered && !primary ? 0.035:0)))
            .overlay(RoundedRectangle(cornerRadius:compact ? 10:13).strokeBorder(focused ? PivokiPalette.goldInk:Color.clear,lineWidth:2).padding(-3))
            .shadow(color:primary && enabled ? Color.pivoki.opacity(hovered ? 0.20:0.10):.clear,radius:hovered ? 9:5,y:3)
            .scaleEffect(systemReduced || reduced ? 1:configuration.isPressed ? 0.97:hovered && enabled ? 1.015:1)
            .opacity(enabled ? 1:0.4).contentShape(RoundedRectangle(cornerRadius:13))
            .onHover { hovered=$0 }
            .animation(systemReduced || reduced ? nil:.easeOut(duration:0.14),value:configuration.isPressed)
            .animation(systemReduced || reduced ? nil:.easeOut(duration:0.16),value:hovered)
    }
}
struct PivokiGroupBoxStyle:GroupBoxStyle {
    func makeBody(configuration:Configuration)->some View {
        VStack(alignment:.leading,spacing:16) {
            configuration.label.font(.system(size:13,weight:.semibold,design:.rounded)).foregroundStyle(PivokiPalette.forest)
            configuration.content
        }.padding(20).frame(maxWidth:.infinity,alignment:.leading).pivokiCard()
    }
}

struct PivokiMark:View {
    var size:CGFloat=44
    var happy=false
    var body:some View {
        Image(nsImage:PivokiArtwork.mark(size:size*2,happy:happy)).resizable().interpolation(.high).frame(width:size,height:size).accessibilityHidden(true)
    }
}

struct PivokiPill:View {
    let title:String
    var symbol:String?=nil
    var color:Color=PivokiPalette.forest
    var body:some View {
        HStack(spacing:5) { if let symbol { Image(systemName:symbol) };LText(title) }
            .font(.system(size:10,weight:.semibold,design:.rounded)).foregroundStyle(color == .pivoki ? PivokiPalette.goldInk:color)
            .padding(.horizontal,9).padding(.vertical,5).background(color.opacity(0.09),in:Capsule())
    }
}
struct PivokiPageHeading:View {
    let eyebrow:String
    let title:String
    let subtitle:String
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            LText(eyebrow.uppercased()).font(.system(size:10,weight:.bold,design:.rounded)).tracking(1.4).foregroundStyle(PivokiPalette.goldInk)
            LText(title).font(.system(size:27,weight:.bold,design:.rounded)).tracking(-0.7)
            LText(subtitle).font(.system(size:12)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
        }
    }
}
struct PivokiCheck:View {
    @State private var arrived=false
    var body:some View {
        Image(systemName:"checkmark").font(.system(size:14,weight:.bold)).foregroundStyle(PivokiPalette.forest)
            .frame(width:34,height:34).background(PivokiPalette.sage,in:Circle())
            .scaleEffect(arrived ? 1:0.75).opacity(arrived ? 1:0)
            .pivokiAnimation(value:arrived).onAppear{arrived=true}.accessibilityHidden(true)
    }
}

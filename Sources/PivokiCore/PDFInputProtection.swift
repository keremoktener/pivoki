import CoreGraphics
import Foundation
import PDFKit

public struct PDFSignatureNotice: LocalizedError {
    public let fileName: String
    public var errorDescription: String? {
        "Changing this PDF can invalidate its signatures: \(fileName). Use pivoki-cli studio --tool pdf-zip or pdf-copy with the original paths."
    }
}

enum PDFInputProtection {
    static func check(_ request: ConversionRequest, token: CancellationToken) throws {
        switch request.operation {
        case .convert(let format) where ["zip", "tar", "gz", "7z"].contains(format.lowercased()): return
        case .tool(.readQRCode): return
        default: break
        }
        for url in request.inputs where FileCategory.detect(url) == .pdf {
            try token.check()
            guard let document = CGPDFDocument(url as CFURL) else { throw PivokiError.invalidInput("This PDF could not be opened.") }
            if !document.isUnlocked { _ = document.unlockWithPassword(request.options.password) }
            guard document.isUnlocked else { throw PivokiError.invalidInput("This PDF is password protected. Enter its password.") }
            if document.isEncrypted, let pdf = PDFDocument(url: url) {
                if !request.options.password.isEmpty { _ = pdf.unlock(withPassword: request.options.password) }
                let permitted: Bool
                switch request.operation {
                case .tool(.mergePDF), .tool(.organizePDF), .tool(.splitPDF): permitted = pdf.allowsDocumentAssembly
                case .tool(.compress), .tool(.removeMetadata): permitted = pdf.allowsDocumentChanges
                default: permitted = pdf.allowsCopying
                }
                guard permitted else { throw PivokiError.invalidInput("The PDF permissions do not allow this operation.") }
            }
            if try containsSignature(document, token: token) { throw PDFSignatureNotice(fileName: url.lastPathComponent) }
        }
    }

    private static func containsSignature(_ document: CGPDFDocument, token: CancellationToken) throws -> Bool {
        guard let catalog = document.catalog else { throw PivokiError.invalidInput("The PDF catalog could not be inspected.") }
        var permissions: CGPDFDictionaryRef?
        if CGPDFDictionaryGetDictionary(catalog, "Perms", &permissions), let permissions,
           CGPDFDictionaryGetCount(permissions) > 0 { return true }
        var fields: [CGPDFDictionaryRef] = []
        func appendArray(_ parent: CGPDFDictionaryRef, _ key: String) {
            var array: CGPDFArrayRef?
            if CGPDFDictionaryGetArray(parent, key, &array), let array {
                for index in 0..<CGPDFArrayGetCount(array) {
                    var child: CGPDFDictionaryRef?
                    if CGPDFArrayGetDictionary(array, index, &child), let child { fields.append(child) }
                }
            }
        }
        var form: CGPDFDictionaryRef?
        if CGPDFDictionaryGetDictionary(catalog, "AcroForm", &form), let form { appendArray(form, "Fields") }
        if document.numberOfPages > 0 {
            for index in 1...document.numberOfPages {
                try token.check()
                if let page = document.page(at: index)?.dictionary { appendArray(page, "Annots") }
            }
        }
        var seen = Set<CGPDFDictionaryRef>()
        while let field = fields.popLast() {
            try token.check()
            guard seen.insert(field).inserted else { continue }
            var type: UnsafePointer<CChar>?
            if CGPDFDictionaryGetName(field, "FT", &type), let type, String(cString: type) == "Sig" { return true }
            var value: CGPDFDictionaryRef?, ranges: CGPDFArrayRef?
            if CGPDFDictionaryGetDictionary(field, "V", &value), let value,
               CGPDFDictionaryGetArray(value, "ByteRange", &ranges) { return true }
            appendArray(field, "Kids")
            var parent: CGPDFDictionaryRef?
            if CGPDFDictionaryGetDictionary(field, "Parent", &parent), let parent { fields.append(parent) }
        }
        return false
    }
}

import Foundation
import XCTest
@testable import PivokiCore

final class PDFInputProtectionTests: XCTestCase {
    private func writePDF(to path: URL, signatureField: Bool, registered: Bool) throws -> Data {
        let form = registered ? "/AcroForm << /Fields [5 0 R] >>" : ""
        let type = signatureField ? "/Sig" : "/Tx"
        let objects = [
            "<< /Type /Catalog /Pages 2 0 R \(form) >>",
            "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Annots [4 0 R] >>",
            "<< /Type /Annot /Subtype /Widget /Rect [0 0 1 1] /Parent 5 0 R >>",
            "<< /T (Approval) /FT \(type) /Kids [4 0 R] >>"
        ]
        var data = Data("%PDF-1.4\n".utf8)
        var offsets: [Int] = []
        for (index, object) in objects.enumerated() {
            offsets.append(data.count)
            data.append(Data("\(index + 1) 0 obj\n\(object)\nendobj\n".utf8))
        }
        let xref = data.count
        data.append(Data("xref\n0 \(objects.count+1)\n0000000000 65535 f \n".utf8))
        for offset in offsets { data.append(Data(String(format: "%010d 00000 n \n", offset).utf8)) }
        data.append(Data("trailer\n<< /Size \(objects.count+1) /Root 1 0 R >>\nstartxref\n\(xref)\n%%EOF\n".utf8))
        try data.write(to: path)
        return data
    }

    func testProtectedFieldStopsMixedBatchBeforeOutputAndLeavesOriginalsUnchanged() throws {
        let root = try OutputFiles.temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let clean = root.appendingPathComponent("Clean.pdf"), protectedURL = root.appendingPathComponent("Signed.pdf")
        let bytes = try writePDF(to: clean, signatureField: false, registered: true)
        for registered in [true, false] {
            let protectedBytes = try writePDF(to: protectedURL, signatureField: true, registered: registered)
            let request = ConversionRequest(inputs: [clean, protectedURL], operation: .convert("png"))
            XCTAssertThrowsError(try ConversionEngine.run(request)) { error in
                XCTAssertEqual((error as? PDFSignatureNotice)?.fileName, "Signed.pdf")
            }
            XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path).sorted(), ["Clean.pdf", "Signed.pdf"])
            XCTAssertEqual(try Data(contentsOf: clean), bytes)
            XCTAssertEqual(try Data(contentsOf: protectedURL), protectedBytes)
            XCTAssertNoThrow(try PDFInputProtection.check(.init(inputs: [protectedURL], operation: .convert("zip")), token: .init()))
        }
    }
}

import AppKit
import Dispatch
import SwiftUI

struct Game: Codable, Identifiable {
    var id: String
    var title: String
    var maker: String
    var category: String
    var form: String
    var genreCodes: [String]? = nil
    var genreLabels: [String: String]? = nil
    var sales: Int?
    var rating: Double?
    var ratingApproximate: Bool? = nil
    var price: Int?
    var registDate: String? = nil
    var rankDay: Int? = nil
    var rankWeek: Int? = nil
    var rankMonth: Int? = nil
    var rankTrend: Int? = nil
    var genrePos: [String: Int]? = nil
    var makerId: String? = nil
    var discountRate: Int? = nil
    var officialPrice: Int? = nil
    var ratingCount: Int? = nil
    var voice: Bool? = nil
    var music: Bool? = nil
    var video: Bool? = nil
    var imagePath: String
    var url: String

    var categories: [String] { Self.parts(category) }
    var forms: [String] { Self.parts(form) }
    var registYear: String? {
        guard let date = registDate, date.count >= 4 else { return nil }
        return String(date.prefix(4))
    }
    var hasVoice: Bool { voice == true }
    var hasMusic: Bool { music == true }
    var hasVideo: Bool { video == true }
    var makerDisplay: String { maker.isEmpty ? "制作者未知" : maker }
    var makerKey: String {
        let rawId = makerId ?? ""
        return rawId.isEmpty ? "n:\(maker)" : rawId
    }
    var heatText: String? {
        var parts: [String] = []
        if let day = rankDay { parts.append("日\(day)") }
        if let week = rankWeek { parts.append("周\(week)") }
        if let month = rankMonth { parts.append("月\(month)") }
        return parts.isEmpty ? nil : parts.joined(separator: " ")
    }

    static func parts(_ value: String) -> [String] {
        value.components(separatedBy: CharacterSet(charactersIn: "|;；、，,"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }
}

enum ImportError: LocalizedError {
    case unsupported
    case invalidJSON
    case invalidCSV
    case missingTitle
    case noRows

    var errorDescription: String? {
        switch self {
        case .unsupported: return "请选择 CSV、JSON 或保存的 HTML 页面。"
        case .invalidJSON: return "JSON 应为作品数组，或包含 works 数组的对象。"
        case .invalidCSV: return "CSV 格式有误，请检查引号和表头。"
        case .missingTitle: return "缺少 title（游戏名）列。"
        case .noRows: return "文件中没有可导入的作品。"
        }
    }
}

enum Importer {
    static func load(_ source: URL) throws -> [Game] {
        let data = try Data(contentsOf: source)
        let ext = source.pathExtension.lowercased()
        if ext == "html" || ext == "htm" {
            guard let string = String(data: data, encoding: .utf8) else { throw ImportError.invalidCSV }
            let games = parseSavedHTML(string)
            if !games.isEmpty { return games }
            if let detail = parseDetailHTML(string) { return [detail] }
            throw ImportError.noRows
        }
        let rows: [[String: Any]]
        if ext == "json" {
            let object = try JSONSerialization.jsonObject(with: data)
            if let array = object as? [[String: Any]] {
                rows = array
            } else if let dictionary = object as? [String: Any],
                      let array = dictionary["works"] as? [[String: Any]] {
                rows = array
            } else {
                throw ImportError.invalidJSON
            }
        } else if ext == "csv" {
            guard let string = String(data: data, encoding: .utf8) else { throw ImportError.invalidCSV }
            let matrix = try parseCSV(string)
            guard let header = matrix.first else { throw ImportError.noRows }
            let names = header.map { normalize($0) }
            rows = matrix.dropFirst().filter { $0.contains(where: { !$0.isEmpty }) }.map { cells in
                var row: [String: Any] = [:]
                for (index, name) in names.enumerated() where index < cells.count {
                    row[name] = cells[index]
                }
                return row
            }
        } else {
            throw ImportError.unsupported
        }
        guard !rows.isEmpty else { throw ImportError.noRows }

        var games: [Game] = []
        for (index, originalRow) in rows.enumerated() {
            var row: [String: Any] = [:]
            for (key, value) in originalRow { row[normalize(key)] = value }
            let title = string(row, ["title", "name", "游戏名", "作品名", "作品标题"])
            guard !title.isEmpty else { continue }
            let image = string(row, ["image_path", "image", "thumbnail", "预览图", "图片路径"])
            let imagePath: String
            if image.isEmpty {
                imagePath = ""
            } else if NSString(string: image).isAbsolutePath {
                imagePath = image
            } else {
                imagePath = source.deletingLastPathComponent().appendingPathComponent(image).path
            }
            games.append(Game(
                id: string(row, ["id", "product_id", "rj_id", "作品id"]).nonEmpty ?? "row-\(index)",
                title: title,
                maker: string(row, ["maker", "creator", "circle", "制作者", "社团"]),
                category: string(row, ["category", "categories", "分类", "标签"]),
                form: string(row, ["form", "work_type", "type", "作品形式", "形式"]),
                sales: integer(row, ["sales", "sales_count", "销量", "销售量"]),
                rating: decimal(row, ["rating", "average_rating", "score", "评价", "评分"]),
                price: integer(row, ["price", "price_jpy", "价格", "售价"]),
                registDate: string(row, ["regist_date", "release_date", "发售时间", "发售日", "発売日"]),
                rankDay: integer(row, ["rank_day_current", "日热度", "日榜"]),
                rankWeek: integer(row, ["rank_week_current", "周热度", "周榜"]),
                rankMonth: integer(row, ["rank_month_current", "月热度", "月榜"]),
                rankTrend: integer(row, ["rank_trend_current", "官方人气", "人气"]),
                genrePos: intDict(row, ["genre_pos", "分类人气"]),
                makerId: string(row, ["maker_id", "makerid", "作者id"]).nonEmpty,
                discountRate: integer(row, ["discount_rate", "折扣"]),
                officialPrice: integer(row, ["official_price", "原价"]),
                ratingCount: integer(row, ["rating_count", "评价人数"]),
                voice: boolean(row, ["voice", "配音"]),
                music: boolean(row, ["music", "音乐"]),
                video: boolean(row, ["video", "动画"]),
                imagePath: imagePath,
                url: string(row, ["url", "link", "作品链接", "链接"])
            ))
        }
        guard !games.isEmpty else { throw ImportError.missingTitle }
        return games
    }

    private static func normalize(_ key: String) -> String {
        key.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\u{FEFF}", with: "")
            .lowercased()
            .replacingOccurrences(of: " ", with: "_")
    }

    private static func string(_ row: [String: Any], _ keys: [String]) -> String {
        for key in keys {
            guard let value = row[key], !(value is NSNull) else { continue }
            if let parts = value as? [String] { return parts.joined(separator: " | ") }
            let text = String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty { return text }
        }
        return ""
    }

    private static func integer(_ row: [String: Any], _ keys: [String]) -> Int? {
        let raw = string(row, keys)
        let digits = raw.filter { $0.isNumber || $0 == "-" }
        return Int(digits)
    }

    private static func decimal(_ row: [String: Any], _ keys: [String]) -> Double? {
        let raw = string(row, keys).replacingOccurrences(of: ",", with: ".")
        let allowed = raw.filter { $0.isNumber || $0 == "." || $0 == "-" }
        return Double(allowed)
    }

    private static func boolean(_ row: [String: Any], _ keys: [String]) -> Bool? {
        for key in keys {
            guard let value = row[key], !(value is NSNull) else { continue }
            if let flag = value as? Bool { return flag }
            if let number = value as? NSNumber { return number.boolValue }
            let text = String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["true", "1", "yes", "是", "有"].contains(text) { return true }
            if ["false", "0", "no", "否", "无"].contains(text) { return false }
        }
        return nil
    }

    /// P19.1：``genre_pos``（{分类 id: 名次}）字典解析。
    private static func intDict(_ row: [String: Any], _ keys: [String]) -> [String: Int]? {
        for key in keys {
            guard let value = row[key], !(value is NSNull) else { continue }
            if let map = value as? [String: Int] {
                return map.isEmpty ? nil : map
            }
            if let raw = value as? [String: Any] {
                var result: [String: Int] = [:]
                for (name, item) in raw {
                    if let number = item as? NSNumber {
                        result[name] = number.intValue
                    } else if let text = item as? String, let number = Int(text) {
                        result[name] = number
                    }
                }
                return result.isEmpty ? nil : result
            }
            if let text = value as? String {
                // 兼容 CSV 里的 JSON 字串
                if let data = text.data(using: .utf8),
                   let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Int],
                   !parsed.isEmpty {
                    return parsed
                }
            }
        }
        return nil
    }

    private static func parseCSV(_ text: String) throws -> [[String]] {
        let chars = Array(text)
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var quoted = false
        var index = 0
        while index < chars.count {
            let char = chars[index]
            if quoted {
                if char == "\"" {
                    if index + 1 < chars.count && chars[index + 1] == "\"" {
                        field.append("\"")
                        index += 1
                    } else {
                        quoted = false
                    }
                } else {
                    field.append(char)
                }
            } else if char == "\"" && field.isEmpty {
                quoted = true
            } else if char == "," {
                row.append(field)
                field = ""
            } else if char == "\n" || char == "\r" {
                row.append(field)
                rows.append(row)
                row = []
                field = ""
                if char == "\r" && index + 1 < chars.count && chars[index + 1] == "\n" { index += 1 }
            } else {
                field.append(char)
            }
            index += 1
        }
        guard !quoted else { throw ImportError.invalidCSV }
        if !row.isEmpty || !field.isEmpty {
            row.append(field)
            rows.append(row)
        }
        return rows
    }

    // Reads only a user-supplied local snapshot. It never requests the site or image server.
    private static func parseSavedHTML(_ html: String) -> [Game] {
        guard let itemPattern = try? NSRegularExpression(pattern: #"<li\s+data-list_item_product_id="([^"]+)""#) else { return [] }
        let ns = html as NSString
        let matches = itemPattern.matches(in: html, range: NSRange(location: 0, length: ns.length))
        var games: [Game] = []
        for (index, match) in matches.enumerated() {
            let end = index + 1 < matches.count ? matches[index + 1].range.location : ns.length
            let segment = ns.substring(with: NSRange(location: match.range.location, length: end - match.range.location))
            let id = ns.substring(with: match.range(at: 1))
            let title = clean(capture(#"<dd class="work_name">.*?<a[^>]*>(.*?)</a>"#, in: segment))
            guard !title.isEmpty else { continue }
            let maker = clean(capture(#"<dd class="maker_name">.*?<a[^>]*>(.*?)</a>"#, in: segment))
            let form = clean(capture(#"<div class="work_category[^\"]*">.*?<a[^>]*>(.*?)</a>"#, in: segment))
            let price = Int(capture(#"<span class="work_price[^\"]*">\s*<span class="work_price_parts">.*?<span class="work_price_base">([^<]+)"#, in: segment).filter(\.isNumber))
            let sales = Int(capture(#"<span class="_dl_count_[^\"]+">([^<]+)"#, in: segment).filter(\.isNumber))
            let stars = Int(capture(#"star_rating star_(\d+) mini"#, in: segment))
            let url = capture(#"<dd class="work_name">.*?<a href="([^"]+)"#, in: segment)
            let attributes = capture(#"<input[^>]*class="__product_attributes"[^>]*value="([^"]+)""#, in: segment)
            let attributeTokens = attributes.components(separatedBy: ",")
                .map { $0.trimmingCharacters(in: .whitespaces) }
            let genreCodes = attributeTokens.filter {
                $0.range(of: #"^\d{3}$"#, options: .regularExpression) != nil
            }
            games.append(Game(id: id, title: title, maker: maker, category: "", form: form,
                              genreCodes: genreCodes,
                              sales: sales, rating: stars.map { Double($0) / 10 },
                              ratingApproximate: true, price: price,
                              makerId: attributeTokens.first { $0.hasPrefix("RG") },
                              voice: attributeTokens.contains("SND"),
                              music: attributeTokens.contains("MS2"),
                              video: attributeTokens.contains("MV2"),
                              imagePath: "", url: url))
        }
        return games
    }

    static func isDetailHTML(_ source: URL) -> Bool {
        guard ["html", "htm"].contains(source.pathExtension.lowercased()),
              let text = try? String(contentsOf: source, encoding: .utf8) else { return false }
        return text.contains("id=\"work_name\"") && !text.contains("data-list_item_product_id=\"")
    }

    private static func parseDetailHTML(_ html: String) -> Game? {
        let id = capture(#"product_id/(RJ[0-9]+)\.html"#, in: html)
        let title = clean(capture(#"<h1 itemprop="name" id="work_name">(.*?)</h1>"#, in: html))
        guard !id.isEmpty && !title.isEmpty else { return nil }
        let maker = clean(capture(#"<span itemprop="brand" class="maker_name">.*?<a[^>]*>(.*?)</a>"#, in: html))
        let formBlock = capture(#"<div class="work_genre" id="category_type">(.*?)</div>"#, in: html)
        let form = clean(capture(#"<span class="icon_[^\"]+"[^>]*>(.*?)</span>"#, in: formBlock))
        let genreBlock = capture(#"<div class="main_genre">(.*?)</div>"#, in: html)
        let genrePattern = try? NSRegularExpression(pattern: #"<a href="[^"]*/genre/(\d+)/[^"]*">(.*?)</a>"#, options: .dotMatchesLineSeparators)
        let ns = genreBlock as NSString
        var genreCodes: [String] = []
        var genreLabels: [String: String] = [:]
        for match in genrePattern?.matches(in: genreBlock, range: NSRange(location: 0, length: ns.length)) ?? [] {
            let code = ns.substring(with: match.range(at: 1))
            let label = clean(ns.substring(with: match.range(at: 2)))
            genreCodes.append(code)
            genreLabels[code] = label
        }
        let genres = genreCodes.compactMap { genreLabels[$0] }
        let rating = Double(capture(#"<meta itemprop="ratingValue" content="([^"]+)""#, in: html))
        let price = Int(capture(#"data-price="(\d+)""#, in: html))
        let url = capture(#"<link rel="canonical" href="([^"]+)""#, in: html)
        return Game(id: id, title: title, maker: maker, category: genres.joined(separator: " | "),
                    form: form, genreCodes: genreCodes, genreLabels: genreLabels,
                    sales: nil, rating: rating, ratingApproximate: false,
                    price: price, imagePath: "", url: url)
    }

    private static func capture(_ pattern: String, in text: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators) else { return "" }
        let ns = text as NSString
        guard let match = regex.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)),
              match.range(at: 1).location != NSNotFound else { return "" }
        return ns.substring(with: match.range(at: 1))
    }

    private static func clean(_ text: String) -> String {
        var value = text.replacingOccurrences(of: #"<[^>]*>"#, with: "", options: .regularExpression)
        for (entity, decoded) in ["&quot;": "\"", "&#039;": "'", "&#39;": "'", "&lt;": "<", "&gt;": ">", "&nbsp;": " ", "&amp;": "&"] {
            value = value.replacingOccurrences(of: entity, with: decoded)
        }
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

struct ImportProgress: Codable {
    var schemaVersion: Int?
    var updatedAt: String?
    var updatedTs: Int?
    var running: Bool?
    var phase: String
    var years: String?
    var enriched: Int
    var excluded: Int
    var skipped: Int?
    var failed: Int?
    var remaining: Int
    var total: Int?
    var minSales: Int?
    var freshDays: Int?
    var walkDone: Bool?
    var cursorPage: Int?
    var note: String?

    var summary: String? {
        let skippedCount = skipped ?? 0
        switch phase {
        case "enrich":
            let state = (running ?? false) ? "进行中" : "已暂停（打开「渐进导入」开关可继续）"
            if walkDone == false, let page = cursorPage {
                return "渐进导入\(state)：目录遍历第 \(page) 页（新作先登记，遍历完成后统一入库）· 已登记 \(remaining)"
            }
            return "渐进导入\(state)：已入库 \(enriched) · 排除非游戏 \(excluded) · 忽略低销旧作 \(skippedCount) · 剩余 \(remaining)\(progressPercentText)"
        case "done":
            return "渐进导入已完成：新增入库 \(enriched) 部（排除非游戏 \(excluded)，忽略低销旧作 \(skippedCount)）"
        default:
            return nil
        }
    }

    private var progressPercentText: String {
        guard let total, total > 0 else { return "" }
        let done = max(0, min(total, total - remaining))
        return " · 约 \(Int((Double(done) / Double(total) * 100).rounded()))%"
    }
}

/// P23：已覆盖最深位置（out/import-coverage.json；供「继续抓更早」显示与命令）
struct ImportCoverage: Codable {
    var schemaVersion: Int?
    var updatedAt: String?
    var years: String?
    var boundaryOld: Int?
    var boundaryModern: Int?
    var page: Int?
    var coveredDays: Int?
    var coveredYears: Double?
}

struct UpdateProgress: Codable {
    var schemaVersion: Int?
    var phase: String
    var detail: String?
    var years: String?
    var pid: Int?
    var updatedAt: String?
    var updatedTs: Int?

    var isStale: Bool {
        guard let ts = updatedTs else { return false }
        return Date().timeIntervalSince1970 - Double(ts) > 48 * 3600
    }

    var isRunningPhase: Bool { Self.runningPhases.contains(phase) }
    private static let runningPhases: Set<String> = ["rankings", "import", "sales", "images", "export"]

    private var scope: String {
        guard let years else { return "" }
        return "（\(yearsLabel(years))）"
    }

    func summary(importProgress: ImportProgress?) -> String? {
        switch phase {
        case "rankings":
            return "更新中\(scope)：正在抓取热榜（榜单/列表/人气序）并富化新作…"
        case "import":
            if let progress = importProgress, progress.phase == "enrich" {
                return "更新中\(scope)：导入进行中 — 已入库 \(progress.enriched) · 排除非游戏 \(progress.excluded) · 忽略低销旧作 \(progress.skipped ?? 0) · 剩余 \(progress.remaining)"
            }
            return "更新中\(scope)：导入进行中（断点续传）"
        case "sales":
            return "更新中\(scope)：正在刷新销量…"
        case "images":
            return "更新中\(scope)：正在补齐封面…"
        case "export":
            return "更新中\(scope)：正在导出数据…"
        case "done":
            return "更新完成\(scope)：\(detail ?? "数据已更新")"
        case "failed":
            return "更新中断\(scope)：\(detail ?? "详见 data/update.log")"
        case "busy":
            return detail ?? "已有更新在运行…"
        default:
            return nil
        }
    }

    var icon: String {
        switch phase {
        case "done": return "checkmark.seal"
        case "failed": return "exclamationmark.triangle"
        case "busy": return "hourglass"
        default: return "arrow.triangle.2.circlepath"
        }
    }
}

// MARK: - P19.1/P19.2 分类人气

struct GenreEntry: Codable, Identifiable {
    var id: String
    var name: String
    var count: Int? = nil
    var seenAt: String? = nil
    var depth: Int? = nil
    var watched: Bool? = nil
}

struct GenreCatalogEntry: Codable, Identifiable, Equatable {
    var id: String
    var name: String
}

struct GenreMetaCache: Codable {
    var genres: [GenreEntry] = []
    var genreCatalog: [GenreCatalogEntry] = []
}

struct GenreImportRequest: Identifiable, Equatable {
    let id: String
    let name: String
}

struct GenreProgress: Codable {
    var schemaVersion: Int?
    var genreId: String?
    var genreName: String?
    var phase: String
    var detail: String?
    var running: Bool?
    var done: Bool?
    var error: String?
    var more: Bool? = nil
    var pid: Int?
    var updatedAt: String?
    var updatedTs: Int?

    var isStale: Bool {
        guard let ts = updatedTs else { return false }
        return Date().timeIntervalSince1970 - Double(ts) > 6 * 3600
    }

    var displayName: String {
        if let name = genreName, !name.isEmpty { return name }
        return genreId ?? "分类"
    }

    var summary: String? {
        switch phase {
        case "fetch": return "分类人气：「\(displayName)」正在抓取人气榜…"
        case "enrich": return "分类人气：「\(displayName)」正在导入新作品（可能数分钟）…"
        case "images": return "分类人气：「\(displayName)」正在补齐封面…"
        case "export": return "分类人气：「\(displayName)」正在导出数据…"
        case "done": return "分类人气：「\(displayName)」已更新（\(detail ?? "完成")）"
        case "failed": return "分类人气更新失败：「\(displayName)」（\(error ?? detail ?? "详见 data/genre.log")）"
        case "busy": return detail
        default: return nil
        }
    }

    var icon: String {
        switch phase {
        case "done": return "checkmark.seal"
        case "failed": return "exclamationmark.triangle"
        case "busy": return "hourglass"
        default: return "chart.bar.xaxis"
        }
    }
}

final class Library: ObservableObject {
    @Published var games: [Game] = []
    @Published var sourcePath = ""
    @Published var status = "请选择数据文件开始使用"
    @Published var alert = ""
    @Published var importProgress: ImportProgress?
    @Published var updateProgress: UpdateProgress?
    @Published var genreProgress: GenreProgress?
    @Published var importCoverage: ImportCoverage?
    @Published var genreDoneEvent: GenreImportRequest?
    @Published var genres: [GenreEntry] = []
    @Published var genreCatalog: [GenreCatalogEntry] = []
    private var details: [String: Game] = [:]
    private var genreMap: [String: String] = [:]
    private var updateProcess: Process?
    private var lastAppliedUpdateKey: String?
    private var lastImportRefreshKey: String?
    private var lastGenreDoneKey: String?
    private var pollTimer: Timer?
    private var genrePollTimer: Timer?

    var banner: (icon: String, text: String)? {
        // P22.1：「进行中」优先于「已结束」——修复历史横幅（如分类任务 done）占位最长 6 小时，
        // 把随后启动的渐进导入/更新完全挡住的问题
        if let genre = genreProgress, genre.running == true, let text = genre.summary {
            return (genre.icon, text)
        }
        if let progress = importProgress, progress.running == true, let text = progress.summary {
            return ("arrow.triangle.2.circlepath", text)
        }
        if let update = updateProgress, !update.isStale, update.isRunningPhase,
           let text = update.summary(importProgress: importProgress) {
            return (update.icon, text)
        }
        if let genre = genreProgress, !genre.isStale, let text = genre.summary {
            return (genre.icon, text)
        }
        if let update = updateProgress, !update.isStale,
           let text = update.summary(importProgress: importProgress) {
            return (update.icon, text)
        }
        if let progress = importProgress, let text = progress.summary {
            let icon = (progress.running ?? false) ? "arrow.triangle.2.circlepath" : "clock.arrow.circlepath"
            return (icon, text)
        }
        return nil
    }

    var updateInFlight: Bool {
        if let update = updateProgress, !update.isStale, update.isRunningPhase { return true }
        if let progress = importProgress, progress.running == true { return true }
        return false
    }

    var importJobActive: Bool { importProgress?.phase == "enrich" }

    var genreJobActive: Bool {
        if let progress = genreProgress, !progress.isStale, progress.running == true { return true }
        return false
    }

    func setImportSwitch(_ on: Bool, years: String) {
        if on {
            startImport(years: years)
        } else {
            pauseImport()
        }
    }

    func startImport(years: String) { runImportAction(["start", years], waits: false) }
    func pauseImport() { runImportAction(["pause"], waits: true) }
    func cancelImport() { runImportAction(["cancel"], waits: true) }

    private func runImportAction(_ args: [String], waits: Bool) {
        guard !sourcePath.isEmpty else { chooseFile(); return }
        let projectURL = URL(fileURLWithPath: sourcePath)
            .deletingLastPathComponent().deletingLastPathComponent()
        let scriptURL = projectURL.appendingPathComponent("scripts/import.sh")
        guard FileManager.default.fileExists(atPath: scriptURL.path) else {
            alert = "未找到导入脚本：\n\(scriptURL.path)\n请选择管道项目的 out/works.json。"
            return
        }
        let launch = { [weak self] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = [scriptURL.path] + args
            process.currentDirectoryURL = projectURL
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                if waits { process.waitUntilExit() }
            } catch {
                DispatchQueue.main.async { self?.alert = "导入操作失败：\(error.localizedDescription)" }
            }
            DispatchQueue.main.async { self?.reloadProgressFiles() }
        }
        if waits {
            status = "正在执行（稍候自动刷新）…"
            DispatchQueue.global().async(execute: launch)
        } else {
            let scope = args.count > 1 ? yearsLabel(args[1]) : ""
            status = scope.isEmpty ? "已开启导入操作，后台执行中…" : "已开启渐进导入（\(scope)），后台分批入库中…"
            launch()
            // P22.1：启动后追加几次刷新，顶部横幅更快反映最新任务
            for delay in [1.5, 4.0, 9.0] {
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                    self?.reloadProgressFiles()
                }
            }
        }
    }

    private var supportDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DoujinGameFinder", isDirectory: true)
    }

    init() {
        sourcePath = UserDefaults.standard.string(forKey: "sourcePath") ?? ""
        let detailCache = supportDirectory.appendingPathComponent("details.json")
        if let data = try? Data(contentsOf: detailCache),
           let cached = try? JSONDecoder().decode([String: Game].self, from: data) { details = cached }
        let genreCache = supportDirectory.appendingPathComponent("genres.json")
        if let data = try? Data(contentsOf: genreCache),
           let cached = try? JSONDecoder().decode([String: String].self, from: data) { genreMap = cached }
        let genreMetaCache = supportDirectory.appendingPathComponent("genreMeta.json")
        if let data = try? Data(contentsOf: genreMetaCache),
           let cached = try? JSONDecoder().decode(GenreMetaCache.self, from: data) {
            genres = cached.genres
            genreCatalog = cached.genreCatalog
        }
        let cache = supportDirectory.appendingPathComponent("library.json")
        if let data = try? Data(contentsOf: cache), let cached = try? JSONDecoder().decode([Game].self, from: data) {
            games = cached
            status = "已加载上次导入的 \(games.count) 部作品"
        }
        if !sourcePath.isEmpty {
            let sourceURL = URL(fileURLWithPath: sourcePath)
            loadImportProgress(for: sourceURL)
            loadUpdateProgress(for: sourceURL)
            loadImportCoverage(for: sourceURL)
            // P16：数据文件比本地缓存新（如每日自动更新、外部导入）→ 启动即自动同步一次
            if FileManager.default.fileExists(atPath: sourcePath),
               let sourceAttrs = try? FileManager.default.attributesOfItem(atPath: sourcePath),
               let sourceDate = sourceAttrs[.modificationDate] as? Date,
               let cacheAttrs = try? FileManager.default.attributesOfItem(atPath: cache.path),
               let cacheDate = cacheAttrs[.modificationDate] as? Date,
               sourceDate > cacheDate {
                DispatchQueue.main.async { [weak self] in self?.refresh() }
            }
        }
        pollTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.reloadProgressFiles()
        }
    }

    deinit {
        pollTimer?.invalidate()
        genrePollTimer?.invalidate()
    }

    func chooseFile() {
        let panel = NSOpenPanel()
        panel.title = "选择游戏数据文件"
        panel.allowedContentTypes = [.commaSeparatedText, .json, .html]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url { importFile(url) }
    }

    func refresh() {
        guard !sourcePath.isEmpty else { chooseFile(); return }
        let source = URL(fileURLWithPath: sourcePath)
        let projectURL = source.deletingLastPathComponent().deletingLastPathComponent()
        let scriptURL = projectURL.appendingPathComponent("scripts/export.sh")
        guard FileManager.default.fileExists(atPath: scriptURL.path) else {
            importFile(source)  // 非管道项目布局：按原行为重读文件
            return
        }
        // P15.2：「更新」= 先本地同步导出（纯本机、不联网）再重读——始终与数据库对齐
        status = "正在同步本地数据…"
        DispatchQueue.global().async { [weak self] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = [scriptURL.path]
            process.currentDirectoryURL = projectURL
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try? process.run()
            process.waitUntilExit()
            DispatchQueue.main.async {
                guard let self else { return }
                self.importFile(URL(fileURLWithPath: self.sourcePath))
            }
        }
    }

    private func importFile(_ url: URL) {
        do {
            let imported = try Importer.load(url)
            if Importer.isDetailHTML(url), let detail = imported.first {
                details[detail.id] = detail
                genreMap.merge(detail.genreLabels ?? [:]) { _, new in new }
                if let index = games.firstIndex(where: { $0.id == detail.id }) {
                    games[index] = merge(games[index], with: detail)
                } else {
                    games.append(detail)
                }
                games = games.map(applyLabels)
                status = "已补充作品详情 · \(detail.id)"
            } else {
                games = imported.map { game in
                    applyLabels(details[game.id].map { detail in merge(game, with: detail) } ?? game)
                }
                sourcePath = url.path
                UserDefaults.standard.set(sourcePath, forKey: "sourcePath")
                loadImportProgress(for: url)
                loadWorksMeta(for: url)
                status = "已更新 \(imported.count) 部作品 · \(Date().formatted(date: .omitted, time: .shortened))"
            }
            try FileManager.default.createDirectory(at: supportDirectory, withIntermediateDirectories: true)
            try JSONEncoder().encode(games).write(to: supportDirectory.appendingPathComponent("library.json"), options: .atomic)
            try JSONEncoder().encode(details).write(to: supportDirectory.appendingPathComponent("details.json"), options: .atomic)
            try JSONEncoder().encode(genreMap).write(to: supportDirectory.appendingPathComponent("genres.json"), options: .atomic)
        } catch {
            alert = error.localizedDescription
            status = "更新失败；仍显示上次导入的作品"
        }
    }

    private func loadImportProgress(for url: URL) {
        let progressURL = url.deletingLastPathComponent()
            .appendingPathComponent("import-progress.json")
        guard let data = try? Data(contentsOf: progressURL) else {
            importProgress = nil
            return
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        importProgress = try? decoder.decode(ImportProgress.self, from: data)
        // P15 完成闭环：导入完成且其导出比当前数据文件新 → 自动重读一次
        if let parsed = importProgress, parsed.phase == "done", let ts = parsed.updatedTs {
            let key = String(ts)
            if key != lastImportRefreshKey,
               let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
               let modified = attributes[.modificationDate] as? Date,
               Date(timeIntervalSince1970: TimeInterval(ts)) > modified {
                lastImportRefreshKey = key
                DispatchQueue.main.async { [weak self] in self?.refresh() }
            }
        }
    }

    private func loadUpdateProgress(for url: URL) {
        let updateURL = url.deletingLastPathComponent()
            .appendingPathComponent("update-progress.json")
        guard let data = try? Data(contentsOf: updateURL) else {
            updateProgress = nil
            return
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let parsed = try? decoder.decode(UpdateProgress.self, from: data) else {
            updateProgress = nil
            return
        }
        updateProgress = parsed
        if parsed.phase == "done", let ts = parsed.updatedTs, !parsed.isStale {
            let key = String(ts)
            if key != lastAppliedUpdateKey {
                lastAppliedUpdateKey = key
                DispatchQueue.main.async { [weak self] in self?.refresh() }
            }
        }
    }

    private func reloadProgressFiles() {
        guard !sourcePath.isEmpty else { return }
        let url = URL(fileURLWithPath: sourcePath)
        loadImportProgress(for: url)
        loadUpdateProgress(for: url)
        loadGenreProgress(for: url)
        loadImportCoverage(for: url)
    }

    /// P23：已覆盖最深位置（续深模式显示/门控用）
    private func loadImportCoverage(for url: URL) {
        let path = url.deletingLastPathComponent().appendingPathComponent("import-coverage.json")
        guard let data = try? Data(contentsOf: path) else {
            importCoverage = nil
            return
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        importCoverage = try? decoder.decode(ImportCoverage.self, from: data)
    }

    /// P19.1：读容器元信息（分类人气列表 / 官方分类目录）并缓存到本机。
    private func loadWorksMeta(for url: URL) {
        guard url.pathExtension.lowercased() == "json",
              let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data),
              let root = object as? [String: Any] else {
            genres = []
            genreCatalog = []
            return
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let list = root["genres"],
           let payload = try? JSONSerialization.data(withJSONObject: list),
           let parsed = try? decoder.decode([GenreEntry].self, from: payload) {
            genres = parsed
        } else {
            genres = []
        }
        if let list = root["genre_catalog"],
           let payload = try? JSONSerialization.data(withJSONObject: list),
           let parsed = try? decoder.decode([GenreCatalogEntry].self, from: payload) {
            genreCatalog = parsed
        } else {
            genreCatalog = []
        }
        try? FileManager.default.createDirectory(at: supportDirectory, withIntermediateDirectories: true)
        let metaCache = GenreMetaCache(genres: genres, genreCatalog: genreCatalog)
        try? JSONEncoder().encode(metaCache).write(
            to: supportDirectory.appendingPathComponent("genreMeta.json"), options: .atomic
        )
    }

    private func loadGenreProgress(for url: URL) {
        let progressURL = url.deletingLastPathComponent()
            .appendingPathComponent("genre-progress.json")
        guard let data = try? Data(contentsOf: progressURL) else {
            genreProgress = nil
            return
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let parsed = try? decoder.decode(GenreProgress.self, from: data) else {
            genreProgress = nil
            return
        }
        genreProgress = parsed
        // P19.2 完成闭环：导入完成 → 自动重读；首次导入且未加入每日刷新 → 提示加入
        if parsed.phase == "done", let ts = parsed.updatedTs {
            let key = String(ts)
            if key != lastGenreDoneKey {
                lastGenreDoneKey = key
                DispatchQueue.main.async { [weak self] in self?.refresh() }
                let genreId = parsed.genreId ?? ""
                let watched = genres.first { $0.id == genreId }?.watched == true
                if !genreId.isEmpty, !watched, parsed.more != true {
                    genreDoneEvent = GenreImportRequest(id: genreId, name: parsed.genreName ?? genreId)
                }
            }
        }
    }

    /// P19.2：现导入 / 载入更多（后台跑 genre-import.sh；进度写 out/genre-progress.json）。
    func startGenreImport(genreId: String, more: Bool) {
        guard !sourcePath.isEmpty else { chooseFile(); return }
        guard !genreJobActive else {
            alert = "已有分类人气任务在进行中；完成后会自动刷新。"
            return
        }
        let projectURL = URL(fileURLWithPath: sourcePath)
            .deletingLastPathComponent().deletingLastPathComponent()
        let scriptURL = projectURL.appendingPathComponent("scripts/genre-import.sh")
        guard FileManager.default.fileExists(atPath: scriptURL.path) else {
            alert = "未找到分类导入脚本：\n\(scriptURL.path)\n请选择管道项目的 out/works.json。"
            return
        }
        var args = [scriptURL.path, genreId]
        if more { args.append("--more") }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = args
        process.currentDirectoryURL = projectURL
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.reloadProgressFiles()
                self?.stopGenrePolling()
            }
        }
        do {
            try process.run()
        } catch {
            alert = "无法启动分类导入：\(error.localizedDescription)"
            return
        }
        status = more ? "正在载入更多名次（进度见顶部横幅）…" : "正在导入分类人气（进度见顶部横幅）…"
        startGenrePolling()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.reloadProgressFiles()
        }
    }

    /// P19.2：把分类加入每日刷新列表（写入配置）。
    func joinGenreDaily(genreId: String) {
        guard !sourcePath.isEmpty else { chooseFile(); return }
        let projectURL = URL(fileURLWithPath: sourcePath)
            .deletingLastPathComponent().deletingLastPathComponent()
        let scriptURL = projectURL.appendingPathComponent("scripts/genre-import.sh")
        guard FileManager.default.fileExists(atPath: scriptURL.path) else { return }
        DispatchQueue.global().async { [weak self] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = [scriptURL.path, "watch", genreId]
            process.currentDirectoryURL = projectURL
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            var ok = false
            do {
                try process.run()
                process.waitUntilExit()
                ok = process.terminationStatus == 0
            } catch {
                ok = false
            }
            DispatchQueue.main.async {
                if ok {
                    self?.status = "已加入每日刷新列表；下次「更新」起自动刷新该分类"
                } else {
                    self?.alert = "加入每日刷新失败；详见 data/genre.log"
                }
            }
        }
    }

    private func startGenrePolling() {
        genrePollTimer?.invalidate()
        genrePollTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.reloadProgressFiles()
            if !self.genreJobActive { self.stopGenrePolling() }
        }
    }

    private func stopGenrePolling() {
        genrePollTimer?.invalidate()
        genrePollTimer = nil
    }

    func startUpdate(years: String) {
        launchPipeline(scriptName: "update-all.sh", arguments: [years],
                       statusText: "已启动更新（\(yearsLabel(years))）：导入 → 销量 → 封面 → 导出")
    }

    /// P27：一键执行与夜间计划完全相同的完整链路（热榜更新 → 在榜销量 → 封面 → 导出 → 导入续传）
    func startDailyUpdate() {
        launchPipeline(scriptName: "daily.sh", arguments: [],
                       statusText: "已启动完整维护（同每日计划）：榜单 → 销量 → 封面 → 导出")
    }

    /// P28：快版热榜更新（跳过分类人气页/封面/导入续传，约 3–5 分钟）
    func startQuickUpdate() {
        launchPipeline(scriptName: "quick-update.sh", arguments: [],
                       statusText: "已启动热榜更新（快版）：榜单 → 富化 → 销量 → 导出")
    }

    private func launchPipeline(scriptName: String, arguments: [String], statusText: String) {
        guard !sourcePath.isEmpty else { chooseFile(); return }
        guard !updateInFlight else {
            alert = "已有更新在进行中；进度见顶部横幅，完成后会自动刷新。"
            return
        }
        let projectURL = URL(fileURLWithPath: sourcePath)
            .deletingLastPathComponent().deletingLastPathComponent()
        let scriptURL = projectURL.appendingPathComponent("scripts/\(scriptName)")
        guard FileManager.default.fileExists(atPath: scriptURL.path) else {
            alert = "未找到更新脚本：\n\(scriptURL.path)\n请用「选择数据文件」选择管道项目的 out/works.json。"
            return
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [scriptURL.path] + arguments
        process.currentDirectoryURL = projectURL
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.status = "更新流程已结束（结果见顶部横幅）"
                self?.reloadProgressFiles()
            }
        }
        do {
            try process.run()
        } catch {
            alert = "无法启动更新：\(error.localizedDescription)"
            return
        }
        updateProcess = process
        status = statusText
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.reloadProgressFiles()
        }
    }

    private func merge(_ base: Game, with detail: Game) -> Game {
        Game(id: base.id, title: detail.title.isEmpty ? base.title : detail.title,
             maker: detail.maker.isEmpty ? base.maker : detail.maker,
             category: detail.category.isEmpty ? base.category : detail.category,
             form: detail.form.isEmpty ? base.form : detail.form,
             genreCodes: base.genreCodes ?? detail.genreCodes,
             genreLabels: detail.genreLabels,
             sales: base.sales ?? detail.sales, rating: detail.rating ?? base.rating,
             ratingApproximate: detail.rating == nil ? base.ratingApproximate : detail.ratingApproximate,
             price: base.price ?? detail.price,
             registDate: base.registDate ?? detail.registDate,
             rankDay: base.rankDay ?? detail.rankDay,
             rankWeek: base.rankWeek ?? detail.rankWeek,
             rankMonth: base.rankMonth ?? detail.rankMonth,
             rankTrend: base.rankTrend ?? detail.rankTrend,
             genrePos: base.genrePos ?? detail.genrePos,
             makerId: base.makerId ?? detail.makerId,
             discountRate: base.discountRate ?? detail.discountRate,
             officialPrice: base.officialPrice ?? detail.officialPrice,
             ratingCount: base.ratingCount ?? detail.ratingCount,
             voice: base.voice ?? detail.voice,
             music: base.music ?? detail.music,
             video: base.video ?? detail.video,
             imagePath: base.imagePath.isEmpty ? detail.imagePath : base.imagePath,
             url: base.url.isEmpty ? detail.url : base.url)
    }

    private func applyLabels(_ game: Game) -> Game {
        var result = game
        let names = (game.genreCodes ?? []).compactMap { genreMap[$0] }
        let combined = Game.parts(game.category) + names
        var unique: [String] = []
        for name in combined where !unique.contains(name) { unique.append(name) }
        result.category = unique.joined(separator: " | ")
        return result
    }
}

enum SortOrder: String, CaseIterable, Identifiable {
    case sales = "销量从高到低"
    case rating = "评分从高到低"
    case priceLow = "价格从低到高"
    case priceHigh = "价格从高到低"
    case registDate = "发售时间（新→旧）"
    case rankDay = "日热度从高到低"
    case rankWeek = "周热度从高到低"
    case rankMonth = "月热度从高到低"
    case trend = "人气（官方）"
    case title = "名称"
    var id: String { rawValue }
}

// MARK: - P16 显示模式

enum DisplayMode: String, CaseIterable, Identifiable {
    case largeCards = "大卡列表"
    case twoColumn = "双列卡片"
    case compact = "紧凑列表"
    case adaptiveGrid = "自适应网格"
    case coverWall = "封面墙"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .largeCards: return "list.bullet.rectangle"
        case .twoColumn: return "rectangle.grid.1x2"
        case .compact: return "list.bullet"
        case .adaptiveGrid: return "square.grid.2x2"
        case .coverWall: return "square.grid.3x2"
        }
    }

    var shortcut: KeyEquivalent {
        switch self {
        case .largeCards: return "1"
        case .twoColumn: return "2"
        case .compact: return "3"
        case .adaptiveGrid: return "4"
        case .coverWall: return "5"
        }
    }

    var isMultiColumn: Bool { self != .largeCards && self != .compact }
}

// MARK: - P17 收藏夹

struct FavoriteCollection: Codable, Identifiable, Equatable {
    var id: UUID = UUID()
    var name: String
    var workIDs: [String] = []
}

struct FollowedMaker: Codable, Identifiable, Equatable {
    var key: String
    var name: String
    var makerID: String = ""
    var id: String { key }
}

struct FavoritesData: Codable {
    var collections: [FavoriteCollection] = []
    var makers: [FollowedMaker] = []
}

final class FavoritesStore: ObservableObject {
    static let defaultCollectionName = "我的收藏"

    @Published private(set) var data = FavoritesData()
    @Published var pendingNewWorkID: String?

    private let fileURL: URL

    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DoujinGameFinder", isDirectory: true)
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        fileURL = support.appendingPathComponent("favorites.json")
        if let raw = try? Data(contentsOf: fileURL),
           let decoded = try? JSONDecoder().decode(FavoritesData.self, from: raw) {
            data = decoded
        }
    }

    private func persist() {
        guard let encoded = try? JSONEncoder().encode(data) else { return }
        try? encoded.write(to: fileURL, options: .atomic)
    }

    func collection(_ id: UUID) -> FavoriteCollection? {
        data.collections.first { $0.id == id }
    }

    func isFavorited(_ workID: String) -> Bool {
        data.collections.contains { $0.workIDs.contains(workID) }
    }

    func isFollowing(_ key: String) -> Bool {
        data.makers.contains { $0.key == key }
    }

    /// 心形快按：切换「我的收藏」（不存在时自动创建）
    func toggleDefault(_ workID: String) {
        let index = data.collections.firstIndex { $0.name == Self.defaultCollectionName }
        var collection = index.map { data.collections[$0] }
            ?? FavoriteCollection(name: Self.defaultCollectionName)
        if let position = collection.workIDs.firstIndex(of: workID) {
            collection.workIDs.remove(at: position)
        } else {
            collection.workIDs.append(workID)
        }
        if let index { data.collections[index] = collection } else { data.collections.append(collection) }
        persist()
    }

    func toggle(_ workID: String, in collectionID: UUID) {
        guard let index = data.collections.firstIndex(where: { $0.id == collectionID }) else { return }
        if let position = data.collections[index].workIDs.firstIndex(of: workID) {
            data.collections[index].workIDs.remove(at: position)
        } else {
            data.collections[index].workIDs.append(workID)
        }
        persist()
    }

    @discardableResult
    func createCollection(named name: String) -> UUID {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let collection = FavoriteCollection(name: trimmed.isEmpty ? "未命名收藏夹" : trimmed)
        data.collections.append(collection)
        persist()
        return collection.id
    }

    func rename(_ collectionID: UUID, to name: String) {
        guard let index = data.collections.firstIndex(where: { $0.id == collectionID }) else { return }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        data.collections[index].name = trimmed
        persist()
    }

    func delete(_ collectionID: UUID) {
        data.collections.removeAll { $0.id == collectionID }
        persist()
    }

    func requestNewCollection(adding workID: String) {
        pendingNewWorkID = workID
    }

    func toggleFollow(key: String, name: String, makerID: String) {
        if let index = data.makers.firstIndex(where: { $0.key == key }) {
            data.makers.remove(at: index)
        } else {
            data.makers.append(FollowedMaker(key: key, name: name, makerID: makerID))
        }
        persist()
    }
}

struct CollectionEditor: Identifiable {
    let id = UUID()
    var collectionID: UUID?
    var initialName: String = ""
}

enum ViewFilter: Equatable {
    case all
    case collection(UUID)
    case maker(key: String, name: String, makerId: String)

    var makerKey: String? {
        if case .maker(let key, _, _) = self { return key }
        return nil
    }
}

// MARK: - P16 卡片公用

enum ChipFilter {
    case category(String)
    case form(String)
    case badge(String)
}

/// P19.1/P19.4：卡片数据行里的名次展示（分类内人气 / 全站人气序）。
enum RankDisplay {
    case none
    case genre(String)
    case trend

    func text(for game: Game) -> String? {
        switch self {
        case .none:
            return nil
        case .genre(let genreId):
            guard let position = game.genrePos?[genreId] else { return nil }
            return "#\(position)"
        case .trend:
            guard let position = game.rankTrend else { return nil }
            return "#\(position)"
        }
    }
}

struct CardConfig {
    var showBadges = true
    var showDiscount = true
    var showRatingCount = true
    var rankDisplay: RankDisplay = .none
    var onChipFilter: ((ChipFilter) -> Void)? = nil

    func rankText(for game: Game) -> String? { rankDisplay.text(for: game) }

    var categoryTap: ((String) -> Void)? {
        onChipFilter.map { handler in { name in handler(.category(name)) } }
    }

    var formTap: ((String) -> Void)? {
        onChipFilter.map { handler in { name in handler(.form(name)) } }
    }

    var badgeTap: ((String) -> Void)? {
        onChipFilter.map { handler in { key in handler(.badge(key)) } }
    }
}

func openGame(_ game: Game) {
    guard let url = URL(string: game.url),
          ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return }
    NSWorkspace.shared.open(url)
}

func ratingText(_ game: Game, showCount: Bool) -> String {
    guard let rating = game.rating else { return "未评分" }
    let base = (game.ratingApproximate == true ? "≈" : "")
        + rating.formatted(.number.precision(.fractionLength(0...2)))
    if showCount, let count = game.ratingCount, count > 0 {
        return base + "（\(count)）"
    }
    return base
}

/// P21：评分星级分色——低档取整：≤3.5 蓝、≤4.0 紫、≤4.5 粉、>4.5 亮金；未评分保持次级色
func ratingColor(_ game: Game) -> Color {
    guard let rating = game.rating else { return .secondary }
    if rating <= 3.5 { return .blue }
    if rating <= 4.0 { return .purple }
    if rating <= 4.5 { return .pink }
    // P21.1：调亮为高亮度金黄 #FFC700（原 #D9A624 偏暗）
    return Color(red: 1.0, green: 0.78, blue: 0.0)
}

/// P16.1：数据行省字——今年作品显示 MM-DD，跨年显示 YYYY-MM（不截断、不缩字号）
func compactDateText(_ raw: String) -> String {
    let date = String(raw.prefix(10))
    let parts = date.split(separator: "-")
    guard parts.count == 3 else { return date }
    let year = String(parts[0])
    let currentYear = String(Calendar.current.component(.year, from: Date()))
    return year == currentYear ? "\(parts[1])-\(parts[2])" : "\(year)-\(parts[1])"
}

/// P22/P23/P27/P28：年份范围值 → 可读标签（"5" → 最近 5 年；"since:2018" → 自 2018 年至今；"deeper:7" → 续深至最近 7 年；"all" → 全部；"daily" → 完整维护；"quick" → 热榜快更）
func yearsLabel(_ years: String) -> String {
    let text = years.trimmingCharacters(in: .whitespaces)
    if text.lowercased() == "all" { return "全部" }
    if text.lowercased() == "daily" { return "完整维护" }
    if text.lowercased() == "quick" { return "热榜快更" }
    if text.lowercased().hasPrefix("since:") {
        return "自 \(text.dropFirst("since:".count)) 年至今"
    }
    if text.lowercased().hasPrefix("deeper:") {
        return "续深至最近 \(text.dropFirst("deeper:".count)) 年（跳过已覆盖段）"
    }
    return "最近 \(text) 年"
}

// MARK: - P16 封面图片缓存（异步降采样解码）

final class CoverImageCache {
    static let shared = CoverImageCache()

    private let cache = NSCache<NSString, NSImage>()
    private let queue = DispatchQueue(label: "cover-image-cache", qos: .userInitiated, attributes: .concurrent)

    private init() {
        cache.countLimit = 600
    }

    func cached(_ path: String, maxPixel: Int) -> NSImage? {
        cache.object(forKey: Self.key(path, maxPixel))
    }

    func load(_ path: String, maxPixel: Int, completion: @escaping (NSImage?) -> Void) {
        let key = Self.key(path, maxPixel)
        if let image = cache.object(forKey: key) {
            completion(image)
            return
        }
        queue.async {
            let image = Self.downsample(path: path, maxPixel: maxPixel)
            if let image { self.cache.setObject(image, forKey: key) }
            DispatchQueue.main.async { completion(image) }
        }
    }

    private static func key(_ path: String, _ maxPixel: Int) -> NSString {
        "\(path)@\(maxPixel)" as NSString
    }

    private static func downsample(path: String, maxPixel: Int) -> NSImage? {
        guard !path.isEmpty else { return nil }
        let url = URL(fileURLWithPath: path)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: max(maxPixel, 64),
        ]
        guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
    }
}

struct RangeFields: View {
    let title: String
    let unit: String
    @Binding var lower: String
    @Binding var upper: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 6) {
                TextField("最低", text: $lower).textFieldStyle(.roundedBorder)
                Text("至").foregroundStyle(.secondary)
                TextField("最高", text: $upper).textFieldStyle(.roundedBorder)
                Text(unit).font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct SetFilterMenu: View {
    let title: String
    let emptyLabel: String
    let options: [String]
    @Binding var selection: Set<String>

    var body: some View {
        Menu {
            Button("清除选择") { selection.removeAll() }
            if !options.isEmpty { Divider() }
            ForEach(options, id: \.self) { name in
                Button {
                    if selection.contains(name) { selection.remove(name) } else { selection.insert(name) }
                } label: {
                    if selection.contains(name) {
                        Label(name, systemImage: "checkmark")
                    } else {
                        Text(name)
                    }
                }
            }
        } label: {
            Text(selection.isEmpty ? "\(title)：\(emptyLabel)" : "\(title)：已选 \(selection.count) 项")
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct Cover: View {
    let path: String
    var width: CGFloat? = 104
    var height: CGFloat = 132

    @State private var image: NSImage?

    private var maxPixel: Int { Int(max(width ?? height, height) * 2) }

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().scaledToFill()
            } else {
                ZStack {
                    LinearGradient(colors: [Color(red: 0.29, green: 0.22, blue: 0.45), Color(red: 0.13, green: 0.19, blue: 0.30)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: "gamecontroller.fill").font(.system(size: 28)).foregroundStyle(.white.opacity(0.65))
                }
            }
        }
        .frame(width: width, height: height)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 9))
        .task(id: path) {
            guard !path.isEmpty else {
                image = nil
                return
            }
            if let cachedImage = CoverImageCache.shared.cached(path, maxPixel: maxPixel) {
                image = cachedImage
                return
            }
            image = nil
            let loaded = await withCheckedContinuation { continuation in
                CoverImageCache.shared.load(path, maxPixel: maxPixel) { continuation.resume(returning: $0) }
            }
            image = loaded
        }
    }
}

struct CategoryChip: View {
    let text: String
    var onTap: (() -> Void)? = nil

    var body: some View {
        let chip = Text(text)
            .lineLimit(1)
            .font(.system(size: 11))
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(Color.primary.opacity(0.08), in: Capsule())
            .foregroundStyle(.secondary)
        if let onTap {
            chip
                .contentShape(Capsule())
                .onTapGesture(perform: onTap)
                .help("点击筛选分类「\(text)」（再点取消）")
        } else {
            chip
        }
    }
}

/// 作品形式：实心彩色胶囊 + 白字（P16.1 决策：形式与标志颜色突出）
struct FormChip: View {
    let text: String
    var onTap: (() -> Void)? = nil

    var body: some View {
        let chip = Text(text)
            .lineLimit(1)
            .font(.system(size: 11, weight: .semibold))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Color.blue, in: Capsule())
            .foregroundStyle(.white)
        if let onTap {
            chip
                .contentShape(Capsule())
                .onTapGesture(perform: onTap)
                .help("点击筛选形式「\(text)」（再点取消）")
        } else {
            chip
        }
    }
}

struct MoreChip: View {
    let count: Int
    var body: some View {
        Text("+\(count)")
            .font(.system(size: 11))
            .padding(.horizontal, 6).padding(.vertical, 3)
            .foregroundStyle(.tertiary)
    }
}

/// 简易流式布局（自动换行）——芯片行与数据行均不截断
struct ChipsFlow: Layout {
    var spacing: CGFloat = 5
    var rowSpacing: CGFloat = 5

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let maxWidth = proposal.width ?? 260
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxWidth {
                usedWidth = max(usedWidth, x - spacing)
                x = 0
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        usedWidth = max(usedWidth, max(0, x - spacing))
        return CGSize(width: min(maxWidth, usedWidth), height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

struct CategoryChips: View {
    let categories: [String]
    var limit: Int
    var onTapCategory: ((String) -> Void)? = nil

    var body: some View {
        let shown = Array(categories.prefix(limit))
        ChipsFlow(spacing: 5, rowSpacing: 4) {
            ForEach(shown, id: \.self) { name in
                CategoryChip(text: name, onTap: onTapCategory.map { action in { action(name) } })
            }
            if categories.count > shown.count {
                MoreChip(count: categories.count - shown.count)
            }
        }
    }
}

struct FormChips: View {
    let forms: [String]
    var limit: Int
    var onTapForm: ((String) -> Void)? = nil

    var body: some View {
        let shown = Array(forms.prefix(limit))
        ChipsFlow(spacing: 5, rowSpacing: 4) {
            ForEach(shown, id: \.self) { name in
                FormChip(text: name, onTap: onTapForm.map { action in { action(name) } })
            }
            if forms.count > shown.count {
                MoreChip(count: forms.count - shown.count)
            }
        }
    }
}

/// 大卡专属：带行名标签的平级信息行（分类 / 形式 / 标志）
struct LabeledInfoRow<Content: View>: View {
    let label: String
    let content: Content

    init(label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 7) {
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
                .frame(width: 26, alignment: .leading)
                .padding(.top, 3)
            content
        }
    }
}

/// 数据行（销量 / 评分（人数）/ 日期 / 热度）：省字 + 自动换行，不截断
struct GameMetaFlow: View {
    let game: Game
    var showRatingCount = true
    var rankText: String? = nil

    var body: some View {
        ChipsFlow(spacing: 12, rowSpacing: 6) {
            if let rankText {
                Label(rankText, systemImage: "chart.bar.fill")
            }
            Label(game.sales.map { $0.formatted() } ?? "未知", systemImage: "bag.fill")
            Label(ratingText(game, showCount: showRatingCount), systemImage: "star.fill")
                .foregroundStyle(ratingColor(game))
            if let date = game.registDate, !date.isEmpty {
                Label(compactDateText(date), systemImage: "calendar")
            }
            if let heat = game.heatText {
                Label(heat, systemImage: "flame.fill")
            }
        }
    }
}

struct BadgeCapsule: View {
    let icon: String
    var text: String? = nil
    let tint: Color
    var help: String = ""

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: icon).font(.system(size: 9, weight: .semibold))
            if let text { Text(text).font(.system(size: 10, weight: .semibold)) }
        }
        .padding(.horizontal, 6).padding(.vertical, 3)
        .background(tint, in: Capsule())
        .foregroundStyle(.white)
        .help(help)
    }
}

struct GameBadges: View {
    let game: Game
    var showText = true
    var onTap: ((String) -> Void)? = nil

    var body: some View {
        if game.hasVoice || game.hasMusic || game.hasVideo {
            HStack(spacing: 4) {
                if game.hasVoice { badge(icon: "mic.fill", text: "配音", tint: Color(red: 0.83, green: 0.18, blue: 0.44), key: "voice", help: "有配音") }
                if game.hasMusic { badge(icon: "music.note", text: "音乐", tint: Color(red: 0.45, green: 0.29, blue: 0.85), key: "music", help: "有音乐") }
                if game.hasVideo { badge(icon: "film.fill", text: "动画", tint: Color(red: 0.02, green: 0.58, blue: 0.56), key: "video", help: "有动画") }
            }
        }
    }

    @ViewBuilder
    private func badge(icon: String, text: String, tint: Color, key: String, help: String) -> some View {
        let capsule = BadgeCapsule(icon: icon, text: showText ? text : nil, tint: tint, help: help)
        if let onTap {
            capsule
                .contentShape(Capsule())
                .onTapGesture { onTap(key) }
        } else {
            capsule
        }
    }
}

struct GamePrice: View {
    let game: Game
    let showDiscount: Bool
    var font: Font = .headline

    var body: some View {
        if showDiscount, let official = game.officialPrice, let price = game.price,
           official > price, let rate = game.discountRate, rate > 0 {
            HStack(spacing: 5) {
                Text("\(rate)%OFF")
                    .font(.system(size: 10, weight: .bold))
                    .padding(.horizontal, 4).padding(.vertical, 1.5)
                    .background(Color.red.opacity(0.85), in: Capsule())
                    .foregroundStyle(.white)
                Text("¥\(price.formatted())").font(font).foregroundStyle(.orange)
                Text("¥\(official.formatted())").font(.caption).strikethrough().foregroundStyle(.secondary)
            }
        } else {
            Text(game.price.map { "¥\($0.formatted())" } ?? "价格未知")
                .font(font).foregroundStyle(.orange)
        }
    }
}

struct MakerLabel: View {
    let game: Game
    let onTap: (Game) -> Void

    var body: some View {
        if game.maker.isEmpty {
            Text(game.makerDisplay).font(.subheadline).foregroundStyle(.secondary)
        } else {
            Button { onTap(game) } label: {
                Text(game.makerDisplay).font(.subheadline).foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help("显示该作者的全部作品")
        }
    }
}

struct HeartButton: View {
    let game: Game
    @EnvironmentObject private var favorites: FavoritesStore

    var body: some View {
        let favorited = favorites.isFavorited(game.id)
        Button { favorites.toggleDefault(game.id) } label: {
            Image(systemName: favorited ? "heart.fill" : "heart")
                .font(.system(size: 13))
                .foregroundStyle(favorited ? Color.pink : Color.secondary)
        }
        .buttonStyle(.plain)
        .help(favorited ? "移出「我的收藏」（右键管理收藏夹）" : "加入「我的收藏」（右键管理收藏夹）")
    }
}

struct GameContextMenu: View {
    let game: Game
    @EnvironmentObject private var favorites: FavoritesStore

    var body: some View {
        Button("打开作品页") { openGame(game) }
        Divider()
        Menu("加入收藏夹") {
            ForEach(favorites.data.collections) { collection in
                Button {
                    favorites.toggle(game.id, in: collection.id)
                } label: {
                    if collection.workIDs.contains(game.id) {
                        Label(collection.name, systemImage: "checkmark")
                    } else {
                        Text(collection.name)
                    }
                }
            }
            if !favorites.data.collections.isEmpty { Divider() }
            Button("新建收藏夹并加入…") { favorites.requestNewCollection(adding: game.id) }
        }
        Button(favorites.isFollowing(game.makerKey)
               ? "取消关注「\(game.makerDisplay)」"
               : "关注制作者「\(game.makerDisplay)」") {
            favorites.toggleFollow(key: game.makerKey, name: game.makerDisplay, makerID: game.makerId ?? "")
        }
    }
}

struct CardInteraction: ViewModifier {
    let game: Game
    var config: CardConfig
    var cornerRadius: CGFloat = 12
    @State private var hovering = false
    @State private var showInfo = false
    @State private var panelHovering = false
    @State private var openTask: Task<Void, Never>? = nil
    @State private var closeTask: Task<Void, Never>? = nil

    func body(content: Content) -> some View {
        content
            .contentShape(RoundedRectangle(cornerRadius: cornerRadius))
            .onTapGesture(count: 2) { openGame(game) }
            .onHover { isHovering in
                hovering = isHovering
                openTask?.cancel()
                closeTask?.cancel()
                if isHovering {
                    // P21：悬停 0.5 秒后弹出信息浮窗（移出即收；移入浮窗继续浏览不打断）
                    openTask = Task {
                        try? await Task.sleep(for: .milliseconds(500))
                        if !Task.isCancelled { showInfo = true }
                    }
                } else if !panelHovering {
                    closeTask = Task {
                        try? await Task.sleep(for: .milliseconds(300))
                        if !Task.isCancelled && !panelHovering { showInfo = false }
                    }
                }
            }
            .popover(isPresented: $showInfo, arrowEdge: .trailing) {
                GameHoverCard(game: game, showRatingCount: config.showRatingCount, showBadges: config.showBadges)
                    .onHover { inside in
                        panelHovering = inside
                        if inside {
                            closeTask?.cancel()
                        } else if !hovering {
                            closeTask = Task {
                                try? await Task.sleep(for: .milliseconds(300))
                                if !Task.isCancelled { showInfo = false }
                            }
                        }
                    }
            }
            .onChange(of: showInfo) { _, shown in
                if !shown { panelHovering = false }
            }
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(hovering ? Color.primary.opacity(0.22) : Color.clear, lineWidth: 1)
            )
            .contextMenu { GameContextMenu(game: game) }
    }
}

extension View {
    func cardInteraction(_ game: Game, config: CardConfig, cornerRadius: CGFloat = 12) -> some View {
        modifier(CardInteraction(game: game, config: config, cornerRadius: cornerRadius))
    }
}

/// P21：卡片悬停浮窗——展开被截断/省略的信息（全部分类/形式/标志、完整基础信息、全部名次）
struct GameHoverCard: View {
    let game: Game
    var showRatingCount = true
    var showBadges = true
    @EnvironmentObject private var library: Library

    private func genreName(_ id: String) -> String {
        library.genres.first { $0.id == id }?.name ?? "分类 \(id)"
    }

    private var rankItems: [String] {
        var items: [String] = []
        if let day = game.rankDay { items.append("日榜 #\(day)") }
        if let week = game.rankWeek { items.append("周榜 #\(week)") }
        if let month = game.rankMonth { items.append("月榜 #\(month)") }
        if let trend = game.rankTrend { items.append("官方人气 #\(trend)") }
        if let positions = game.genrePos {
            for (id, position) in positions.sorted(by: { $0.value < $1.value }) {
                items.append("\(genreName(id)) #\(position)")
            }
        }
        return items
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(game.title)
                .font(.headline)
                .lineLimit(6)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                Image(systemName: "person.crop.circle").font(.system(size: 11))
                Text(game.makerDisplay).font(.subheadline)
                Spacer(minLength: 8)
                Text(game.id).font(.caption).foregroundStyle(.tertiary)
            }
            .foregroundStyle(.secondary)
            if !game.categories.isEmpty {
                CategoryChips(categories: game.categories, limit: .max)
            }
            if !game.forms.isEmpty {
                FormChips(forms: game.forms, limit: .max)
            }
            if showBadges && (game.hasVoice || game.hasMusic || game.hasVideo) {
                GameBadges(game: game)
            }
            Divider()
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 14) {
                    Label(game.sales.map { $0.formatted() } ?? "销量未知", systemImage: "bag.fill")
                    Label(ratingText(game, showCount: showRatingCount), systemImage: "star.fill")
                        .foregroundStyle(ratingColor(game))
                }
                HStack(spacing: 14) {
                    if let date = game.registDate, !date.isEmpty {
                        Label(String(date.prefix(10)), systemImage: "calendar")
                    }
                    GamePrice(game: game, showDiscount: true, font: .subheadline)
                }
                if rankItems.isEmpty {
                    Label("暂无榜单名次", systemImage: "chart.bar.fill")
                        .foregroundStyle(.tertiary)
                } else {
                    Label(rankItems.joined(separator: " · "), systemImage: "chart.bar.fill")
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            Text("双击打开作品页 · 右键加入收藏夹")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(12)
        .frame(width: 320, alignment: .leading)
    }
}

struct GameRow: View {
    let game: Game
    let config: CardConfig
    let onMakerTap: (Game) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Cover(path: game.imagePath, width: 110, height: 146)
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline) {
                    Text(game.title).font(.headline).lineLimit(2)
                    Spacer(minLength: 12)
                    GamePrice(game: game, showDiscount: config.showDiscount)
                }
                MakerLabel(game: game, onTap: onMakerTap)
                // 三类平级信息：分类 / 形式 / 标志——分行展示（大卡标注行名）
                if !game.categories.isEmpty {
                    LabeledInfoRow(label: "分类") { CategoryChips(categories: game.categories, limit: 8, onTapCategory: config.categoryTap) }
                }
                if !game.forms.isEmpty {
                    LabeledInfoRow(label: "形式") { FormChips(forms: game.forms, limit: 2, onTapForm: config.formTap) }
                }
                if config.showBadges, game.hasVoice || game.hasMusic || game.hasVideo {
                    LabeledInfoRow(label: "标志") { GameBadges(game: game, onTap: config.badgeTap) }
                }
                Spacer(minLength: 0)
                HStack(spacing: 10) {
                    GameMetaFlow(game: game, showRatingCount: config.showRatingCount, rankText: config.rankText(for: game))
                    Spacer(minLength: 8)
                    HeartButton(game: game)
                    Button { openGame(game) } label: {
                        Image(systemName: "arrow.up.right.square")
                    }
                    .buttonStyle(.plain)
                    .help("打开作品页")
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
            .frame(minHeight: 146)
        }
        .padding(13)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .cardInteraction(game, config: config, cornerRadius: 14)
    }
}

struct MediumGameCard: View {
    let game: Game
    let config: CardConfig
    let onMakerTap: (Game) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .top, spacing: 11) {
                Cover(path: game.imagePath, width: 92, height: 122)
                VStack(alignment: .leading, spacing: 4) {
                    Text(game.title)
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(2)
                    MakerLabel(game: game, onTap: onMakerTap)
                    // 与大卡同类别、同顺序的三行（中卡不标行名；分类做取舍：5 枚 + N，P21 由 3+N 提升）
                    if !game.categories.isEmpty {
                        CategoryChips(categories: game.categories, limit: 5, onTapCategory: config.categoryTap)
                    }
                    if !game.forms.isEmpty {
                        FormChips(forms: game.forms, limit: 1, onTapForm: config.formTap)
                    }
                    if config.showBadges, game.hasVoice || game.hasMusic || game.hasVideo {
                        GameBadges(game: game, onTap: config.badgeTap)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(minHeight: 122)
            }
            GameMetaFlow(game: game, showRatingCount: config.showRatingCount, rankText: config.rankText(for: game))
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 6) {
                GamePrice(game: game, showDiscount: config.showDiscount, font: .subheadline)
                Spacer(minLength: 0)
                HeartButton(game: game)
                Button { openGame(game) } label: {
                    Image(systemName: "arrow.up.right.square")
                }
                .buttonStyle(.plain)
                .help("打开作品页")
            }
        }
        .padding(11)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .cardInteraction(game, config: config)
    }
}

struct CompactGameRow: View {
    let game: Game
    let config: CardConfig
    let onMakerTap: (Game) -> Void

    var body: some View {
        HStack(spacing: 11) {
            Cover(path: game.imagePath, width: 50, height: 64)
            VStack(alignment: .leading, spacing: 2) {
                Text(game.title).font(.subheadline.weight(.semibold)).lineLimit(1)
                HStack(spacing: 8) {
                    if game.maker.isEmpty {
                        Text(game.makerDisplay).font(.caption).foregroundStyle(.secondary)
                    } else {
                        Button { onMakerTap(game) } label: {
                            Text(game.makerDisplay).font(.caption).foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("显示该作者的全部作品")
                    }
                    if config.showBadges { GameBadges(game: game, showText: false, onTap: config.badgeTap) }
                }
            }
            Spacer(minLength: 8)
            if let rank = config.rankText(for: game) {
                Label(rank, systemImage: "chart.bar.fill").font(.caption).foregroundStyle(.secondary)
            }
            if let date = game.registDate, !date.isEmpty {
                Text(compactDateText(date)).font(.caption).foregroundStyle(.secondary)
            }
            Label(game.sales.map { $0.formatted() } ?? "未知", systemImage: "bag.fill")
                .font(.caption).foregroundStyle(.secondary)
                .frame(width: 76, alignment: .trailing)
            Label(ratingText(game, showCount: config.showRatingCount), systemImage: "star.fill")
                .font(.caption).foregroundStyle(ratingColor(game))
                .frame(width: 118, alignment: .trailing)
            GamePrice(game: game, showDiscount: config.showDiscount, font: .subheadline)
                .frame(width: 190, alignment: .trailing)
            HeartButton(game: game)
            Button { openGame(game) } label: {
                Image(systemName: "arrow.up.right.square")
            }
            .buttonStyle(.plain)
            .help("打开作品页")
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 7)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        .cardInteraction(game, config: config, cornerRadius: 10)
    }
}

struct CoverWallTile: View {
    let game: Game
    let config: CardConfig
    @State private var hovering = false

    var body: some View {
        ZStack {
            Cover(path: game.imagePath, width: nil, height: 196)
            if hovering {
                LinearGradient(colors: [Color.black.opacity(0.05), Color.black.opacity(0.78)],
                               startPoint: .top, endPoint: .bottom)
                VStack(alignment: .leading, spacing: 4) {
                    Spacer()
                    Text(game.title)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    HStack(spacing: 6) {
                        if config.showBadges { GameBadges(game: game, showText: false, onTap: config.badgeTap) }
                        Spacer()
                        Text(game.price.map { "¥\($0.formatted())" } ?? "")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.white)
                    }
                }
                .padding(8)
                VStack {
                    HStack {
                        Spacer()
                        HeartButton(game: game)
                            .padding(7)
                            .background(.black.opacity(0.35), in: Circle())
                    }
                    Spacer()
                }
                .padding(6)
            }
        }
        .frame(height: 196)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .onHover { hovering = $0 }
        .onTapGesture(count: 2) { openGame(game) }
        .contextMenu { GameContextMenu(game: game) }
        .help(game.title)
    }
}

/// P22/P23：年份选择弹窗的用途
enum YearPickTarget: Int, Identifiable {
    case update
    case importStart
    case continueDeeper
    var id: Int { rawValue }
}

struct ContentView: View {
    @StateObject private var library = Library()
    @StateObject private var favorites = FavoritesStore()
    @State private var query = ""
    @State private var ratingLow = ""
    @State private var ratingHigh = ""
    @State private var salesLow = ""
    @State private var salesHigh = ""
    @State private var priceLow = ""
    @State private var priceHigh = ""
    @State private var selectedCategories: Set<String> = []
    @State private var excludedCategories: Set<String> = []
    @State private var selectedYears: Set<String> = []
    @State private var form = "全部"
    @State private var sortOrder: SortOrder = .sales
    @State private var includeUnrated = false
    @State private var importYears = "1"
    @State private var confirmCancelImport = false
    // P22：年份选择弹窗（自定义更新范围 / 自定义导入起始年份）
    @State private var yearPickTarget: YearPickTarget? = nil
    @State private var yearPickValue = Calendar.current.component(.year, from: Date()) - 5
    @State private var deeperTargetYears = 8

    // P19.1–P19.3：分类人气浏览 / 搜索 / 现导入
    @State private var selectedGenre: String?
    @State private var genreSearch = ""
    @State private var categorySearch = ""
    @State private var confirmGenreImport: GenreImportRequest?
    @State private var joinDailyPrompt: GenreImportRequest?

    // P16：显示形式（记住选择，默认大卡列表）+ 个性化 + 侧栏/徽章筛选
    @AppStorage("displayMode") private var displayModeRaw = DisplayMode.largeCards.rawValue
    @AppStorage("showBadges") private var showBadges = true
    @AppStorage("showDiscount") private var showDiscount = true
    @AppStorage("showRatingCount") private var showRatingCount = true
    @AppStorage("sidebarVisible") private var sidebarVisible = true
    @State private var showPersonalization = false
    @State private var filterVoice = false
    @State private var filterMusic = false
    @State private var filterVideo = false

    // P17：收藏夹与制作者视图
    @State private var viewFilter: ViewFilter = .all
    @State private var collectionEditor: CollectionEditor?
    @State private var newCollectionName = ""
    @State private var confirmDeleteCollection: FavoriteCollection?

    private var displayMode: DisplayMode {
        DisplayMode(rawValue: displayModeRaw) ?? .largeCards
    }

    /// 侧栏固定宽度（P16.1：取消拖拽，窗口大小由用户调整窗口边缘控制）
    private let sidebarWidth: CGFloat = 280

    private var importToggle: Binding<Bool> {
        Binding(
            get: { library.importProgress?.running == true },
            set: { library.setImportSwitch($0, years: importYears) }
        )
    }

    private var categories: [String] { Set(library.games.flatMap(\.categories)).sorted() }
    private var forms: [String] { ["全部"] + Set(library.games.flatMap(\.forms)).sorted() }
    private var releaseYears: [String] {
        Set(library.games.compactMap(\.registYear)).sorted(by: >)
    }

    /// 分类人气区块的行数据：默认列已导入分类；输入搜索词后匹配官方全量目录（198 项）。
    private var genreEntries: [GenreEntry] {
        let keyword = genreSearch.trimmingCharacters(in: .whitespaces)
        if keyword.isEmpty { return library.genres }
        let known = Dictionary(uniqueKeysWithValues: library.genres.map { ($0.id, $0) })
        let source: [GenreCatalogEntry] = library.genreCatalog.isEmpty
            ? library.genres.map { GenreCatalogEntry(id: $0.id, name: $0.name) }
            : library.genreCatalog
        return source
            .filter { $0.name.localizedCaseInsensitiveContains(keyword) || $0.id.contains(keyword) }
            .prefix(60)
            .map { entry in
                known[entry.id] ?? GenreEntry(id: entry.id, name: entry.name)
            }
    }

    private var activeGenre: GenreEntry? {
        guard let selectedGenre else { return nil }
        return library.genres.first { $0.id == selectedGenre }
    }

    private func bound(_ text: String) -> Double? { Double(text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")) }
    private func matches(_ value: Double?, _ low: String, _ high: String, includeMissing: Bool = false) -> Bool {
        guard let lower = bound(low), let upper = bound(high) else {
            if low.isEmpty && high.isEmpty { return true }
            if value == nil { return includeMissing }
            if let lower = bound(low), let value, value < lower { return false }
            if let upper = bound(high), let value, value > upper { return false }
            return true
        }
        guard let value else { return includeMissing }
        return value >= lower && value <= upper
    }

    private var visibleGames: [Game] {
        let genreFilter = selectedGenre
        let filtered = library.games.filter { game in
            (genreFilter == nil || game.genrePos?[genreFilter!] != nil) &&
            (query.isEmpty || game.title.localizedCaseInsensitiveContains(query) || game.maker.localizedCaseInsensitiveContains(query)) &&
            // P25：包含分类 = 取交集（同时满足所选全部分类；此前误为并集/任一命中）
            (selectedCategories.isEmpty || selectedCategories.isSubset(of: game.categories)) &&
            excludedCategories.isDisjoint(with: game.categories) &&
            (selectedYears.isEmpty || (game.registYear.map { selectedYears.contains($0) } ?? false)) &&
            (form == "全部" || game.forms.contains(form)) &&
            (!filterVoice || game.hasVoice) &&
            (!filterMusic || game.hasMusic) &&
            (!filterVideo || game.hasVideo) &&
            matchesViewFilter(game) &&
            matches(game.rating, ratingLow, ratingHigh, includeMissing: includeUnrated) &&
            matches(game.sales.map(Double.init), salesLow, salesHigh) &&
            matches(game.price.map(Double.init), priceLow, priceHigh)
        }
        if let genre = genreFilter {
            // P19.1 人气态：按该分类官方人气名次升序（未上榜的排后，同档优先销量）
            return filtered.sorted { left, right in
                let leftRank = left.genrePos?[genre] ?? Int.max
                let rightRank = right.genrePos?[genre] ?? Int.max
                if leftRank != rightRank { return leftRank < rightRank }
                return (left.sales ?? -1) > (right.sales ?? -1)
            }
        }
        return filtered.sorted { left, right in
            switch sortOrder {
            case .sales: return (left.sales ?? -1) > (right.sales ?? -1)
            case .rating: return (left.rating ?? -1) > (right.rating ?? -1)
            case .priceLow: return (left.price ?? Int.max) < (right.price ?? Int.max)
            case .priceHigh: return (left.price ?? -1) > (right.price ?? -1)
            case .registDate: return (left.registDate ?? "") > (right.registDate ?? "")
            case .rankDay: return (left.rankDay ?? Int.max) < (right.rankDay ?? Int.max)
            case .rankWeek: return (left.rankWeek ?? Int.max) < (right.rankWeek ?? Int.max)
            case .rankMonth: return (left.rankMonth ?? Int.max) < (right.rankMonth ?? Int.max)
            case .trend:
                // P19.4：官方全站人气序（未入前 N 的排后，同档优先销量）
                let leftRank = left.rankTrend ?? Int.max
                let rightRank = right.rankTrend ?? Int.max
                if leftRank != rightRank { return leftRank < rightRank }
                return (left.sales ?? -1) > (right.sales ?? -1)
            case .title: return left.title.localizedStandardCompare(right.title) == .orderedAscending
            }
        }
    }

    private func matchesViewFilter(_ game: Game) -> Bool {
        switch viewFilter {
        case .all:
            return true
        case .collection(let id):
            return favorites.collection(id)?.workIDs.contains(game.id) ?? false
        case .maker(let key, _, _):
            return game.makerKey == key
        }
    }

    var body: some View {
        let visible = visibleGames
        let rankDisplay: RankDisplay = selectedGenre.map { .genre($0) } ?? (sortOrder == .trend ? .trend : .none)
        let config = CardConfig(
            showBadges: showBadges,
            showDiscount: showDiscount,
            showRatingCount: showRatingCount,
            rankDisplay: rankDisplay,
            onChipFilter: { action in handleChipFilter(action) }
        )

        GeometryReader { geometry in
            let contentWidth = max(320, geometry.size.width - (sidebarVisible ? sidebarWidth + 6 : 0))
            HStack(spacing: 0) {
                if sidebarVisible {
                    sidebar.frame(width: sidebarWidth)
                    Divider()
                }
                VStack(alignment: .leading, spacing: 0) {
                    header
                    if let banner = library.banner {
                        HStack(spacing: 8) {
                            Image(systemName: banner.icon).foregroundStyle(.secondary)
                            Text(banner.text).font(.caption).foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal, 22).padding(.vertical, 8)
                        .background(Color.accentColor.opacity(0.08))
                        Divider()
                    }
                    if viewFilter != .all {
                        activeFilterStrip(count: visible.count)
                        Divider()
                    }
                    if let entry = activeGenre {
                        genreStrip(entry)
                        Divider()
                    }
                    HStack {
                        Text("找到 \(visible.count) 部作品").font(.subheadline).foregroundStyle(.secondary)
                        Spacer()
                        Picker("排序", selection: $sortOrder) {
                            ForEach(SortOrder.allCases) { order in Text(order.rawValue).tag(order) }
                        }
                        .frame(width: 205)
                    }
                    .padding(.horizontal, 22).padding(.vertical, 13)
                    contentList(visible: visible, config: config, contentWidth: contentWidth)
                }
            }
            .frame(minWidth: 940, minHeight: 620)
        }
        .environmentObject(favorites)
        .environmentObject(library)
        .onReceive(library.$importProgress) { progress in
            // P22.1：任务进行中时，范围选择器同步显示实际运行范围（防止「选了 7 年却跑 1 年」式错觉）
            if let progress, progress.phase == "enrich", let years = progress.years,
               !years.isEmpty, importYears != years {
                importYears = years
            }
        }
        .alert("无法更新", isPresented: Binding(get: { !library.alert.isEmpty }, set: { if !$0 { library.alert = "" } })) {
            Button("知道了", role: .cancel) { library.alert = "" }
        } message: { Text(library.alert) }
        .sheet(item: $collectionEditor) { editor in
            collectionEditorSheet(editor)
        }
        .onChange(of: favorites.pendingNewWorkID) { _, workID in
            if workID != nil {
                newCollectionName = ""
                collectionEditor = CollectionEditor(collectionID: nil)
            }
        }
        .alert(
            "导入分类人气",
            isPresented: Binding(
                get: { confirmGenreImport != nil },
                set: { if !$0 { confirmGenreImport = nil } }
            ),
            presenting: confirmGenreImport
        ) { request in
            Button("开始导入（前 200 名）") {
                library.startGenreImport(genreId: request.id, more: false)
                confirmGenreImport = nil
            }
            Button("取消", role: .cancel) { confirmGenreImport = nil }
        } message: { request in
            Text("「\(request.name)」尚未导入人气数据。现在抓取并入库？（含榜上新作品，约 1–3 分钟；进度见顶部横幅）")
        }
        .alert(
            "加入每日刷新？",
            isPresented: Binding(
                get: { joinDailyPrompt != nil },
                set: { if !$0 { joinDailyPrompt = nil } }
            ),
            presenting: joinDailyPrompt
        ) { request in
            Button("加入") {
                library.joinGenreDaily(genreId: request.id)
                joinDailyPrompt = nil
            }
            Button("不用", role: .cancel) { joinDailyPrompt = nil }
        } message: { request in
            Text("「\(request.name)」已导入。是否加入每日自动刷新列表？（写入配置 genre_rank_ids）")
        }
        .onChange(of: library.genreDoneEvent) { _, event in
            guard let event else { return }
            joinDailyPrompt = event
            library.genreDoneEvent = nil
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("同人游戏筛选器").font(.system(size: 25, weight: .bold))
                Text(library.status).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                toggleSidebar()
            } label: {
                Image(systemName: "sidebar.left")
            }
            .help(sidebarVisible ? "收起筛选侧栏（窗口同步缩回）" : "展开筛选侧栏（窗口同步扩展）")

            Menu {
                ForEach(DisplayMode.allCases) { mode in
                    Button {
                        displayModeRaw = mode.rawValue
                    } label: {
                        if displayMode == mode {
                            Label(mode.rawValue, systemImage: "checkmark")
                        } else {
                            Text(mode.rawValue)
                        }
                    }
                    .keyboardShortcut(mode.shortcut, modifiers: .command)
                }
            } label: {
                Label(displayMode.rawValue, systemImage: displayMode.icon)
            }
            .help("显示形式（⌘1–⌘5，记住选择）")

            Button {
                showPersonalization.toggle()
            } label: {
                Label("个性化", systemImage: "slider.horizontal.3")
            }
            .popover(isPresented: $showPersonalization, arrowEdge: .bottom) {
                personalizationPopover
            }

            Button("选择数据文件") { library.chooseFile() }
            Menu {
                Button("立即更新热榜（快）") { library.startQuickUpdate() }
                Button("完整维护（同每日计划）") { library.startDailyUpdate() }
                Divider()
                Button("最近一年") { library.startUpdate(years: "1") }
                Button("最近三年") { library.startUpdate(years: "3") }
                Button("最近五年") { library.startUpdate(years: "5") }
                Button("最近七年") { library.startUpdate(years: "7") }
                Divider()
                Button("自定义年份至今…") {
                    yearPickValue = Calendar.current.component(.year, from: Date()) - 5
                    yearPickTarget = .update
                }
                Button("继续抓更早…") {
                    if let covered = library.importCoverage?.coveredYears {
                        deeperTargetYears = min(max(Int(covered.rounded(.up)) + 1, 2), 29)
                    }
                    yearPickTarget = .continueDeeper
                }
                .disabled(library.importCoverage == nil)
            } label: {
                Label("开始更新数据", systemImage: "tray.and.arrow.down")
            }
            Button { library.refresh() } label: { Label("更新", systemImage: "arrow.clockwise") }
                .buttonStyle(.borderedProminent)
        }
        .padding(22)
        .sheet(item: $yearPickTarget) { target in
            if target == .continueDeeper {
                deeperPickerSheet
            } else {
                yearPickerSheet(target)
            }
        }
    }

    /// P22：可选起始年份（2006 → 今年，倒序）
    private var yearPickChoices: [Int] {
        let current = Calendar.current.component(.year, from: Date())
        return Array((2006...current).reversed())
    }

    @ViewBuilder
    private func yearPickerSheet(_ target: YearPickTarget) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(target == .update ? "自定义更新范围" : "自定义导入起始年份")
                .font(.headline)
            Text(target == .update
                 ? "更新将导入 \(yearPickValue) 年至今的作品（导入 → 销量 → 封面 → 导出）。"
                 : "设置后，打开「渐进导入」开关即可从 \(yearPickValue) 年至今分批入库。")
                .font(.caption).foregroundStyle(.secondary)
            Picker("起始年份", selection: $yearPickValue) {
                ForEach(yearPickChoices, id: \.self) { year in
                    Text("\(String(year)) 年").tag(year)
                }
            }
            .frame(width: 240)
            HStack {
                Spacer()
                Button("取消") { yearPickTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button(target == .update ? "开始更新" : "确定") {
                    let value = "since:\(yearPickValue)"
                    yearPickTarget = nil
                    if target == .update {
                        library.startUpdate(years: value)
                    } else {
                        importYears = value
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(20)
        .frame(width: 400)
    }

    /// P23：续深目标档位（比已覆盖深 1–8 年，封顶 30）
    private var deeperOptions: [Int] {
        let covered = library.importCoverage?.coveredYears ?? 3
        let base = min(max(Int(covered.rounded(.down)) + 1, 2), 29)
        return Array(base...min(base + 8, 30))
    }

    @ViewBuilder
    private var deeperPickerSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("继续抓更早").font(.headline)
            if let coverage = library.importCoverage {
                Text("已覆盖 \(coverageText(coverage))（约第 \(coverage.page ?? 0) 页）；新任务将跳过这一段，从覆盖点继续往更早抓。")
                    .font(.caption).foregroundStyle(.secondary)
                Picker("目标总深度", selection: $deeperTargetYears) {
                    ForEach(deeperOptions, id: \.self) { year in
                        Text("最近 \(String(year)) 年").tag(year)
                    }
                }
                .frame(width: 220)
            } else {
                Text("还没有已覆盖记录（完成过一次目录遍历导入后可用）。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button("取消") { yearPickTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button("开始更新") {
                    let value = "deeper:\(deeperTargetYears)"
                    yearPickTarget = nil
                    library.startUpdate(years: value)
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(library.importCoverage == nil)
            }
        }
        .padding(20)
        .frame(width: 440)
    }

    private func coverageText(_ coverage: ImportCoverage) -> String {
        if let years = coverage.coveredYears {
            return String(format: "≈%.1f 年", years)
        }
        return "（年限未知）"
    }

    private var personalizationPopover: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("个性化显示").font(.headline)
            Divider()
            Toggle("徽章（配音 / 音乐 / 动画）", isOn: $showBadges).toggleStyle(.checkbox)
            Toggle("折扣角标与原价划线", isOn: $showDiscount).toggleStyle(.checkbox)
            Toggle("评价人数", isOn: $showRatingCount).toggleStyle(.checkbox)
            Text("偏好保存在本机，立即生效。").font(.caption).foregroundStyle(.tertiary)
        }
        .padding(14)
        .frame(width: 250, alignment: .leading)
    }

    private func activeFilterStrip(count: Int) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "line.3.horizontal.decrease.circle.fill").foregroundStyle(.secondary)
            Text(activeFilterTitle).font(.subheadline.weight(.medium))
            Text("· 命中 \(count) 部").font(.caption).foregroundStyle(.secondary)
            Spacer()
            if case .maker(let key, let name, let makerId) = viewFilter {
                if !makerId.isEmpty {
                    Button {
                        if let url = URL(string: "https://www.dlsite.com/maniax/circle/profile/=/maker_id/\(makerId).html") {
                            NSWorkspace.shared.open(url)
                        }
                    } label: {
                        Label("在 DLsite 查看全量作品", systemImage: "arrow.up.right.square")
                    }
                    .font(.caption)
                    .help("打开该作者主页（网页端，包含未在本机入库的作品）")
                }
                Button(favorites.isFollowing(key) ? "取消关注" : "关注此作者") {
                    favorites.toggleFollow(key: key, name: name, makerID: makerId)
                }
                .font(.caption)
            }
            Button("返回全部作品") { viewFilter = .all }
                .font(.caption)
        }
        .padding(.horizontal, 22).padding(.vertical, 8)
        .background(Color.accentColor.opacity(0.07))
    }

    private var activeFilterTitle: String {
        switch viewFilter {
        case .all:
            return ""
        case .collection(let id):
            return "收藏夹「\(favorites.collection(id)?.name ?? "已删除")」"
        case .maker(_, let name, _):
            return "制作者「\(name)」"
        }
    }

    @ViewBuilder
    private func contentList(visible: [Game], config: CardConfig, contentWidth: CGFloat) -> some View {
        ScrollView {
            if library.games.isEmpty {
                emptyState("导入 CSV、JSON 或保存的 HTML 页面后，作品会显示在这里。")
            } else if visible.isEmpty {
                emptyState("当前条件没有匹配的作品，请调整筛选区间或收藏夹。")
            } else {
                switch displayMode {
                case .largeCards:
                    LazyVStack(spacing: 10) {
                        ForEach(visible) { game in
                            GameRow(game: game, config: config, onMakerTap: showMaker)
                        }
                    }
                    .padding(.horizontal, 22).padding(.bottom, 22)
                case .twoColumn:
                    LazyVGrid(columns: gridColumns(count: multiColumnCount(maximum: 2, for: contentWidth)), spacing: 12) {
                        ForEach(visible) { game in
                            MediumGameCard(game: game, config: config, onMakerTap: showMaker)
                        }
                    }
                    .padding(.horizontal, 22).padding(.bottom, 22)
                case .adaptiveGrid:
                    LazyVGrid(columns: gridColumns(count: multiColumnCount(maximum: 4, for: contentWidth)), spacing: 12) {
                        ForEach(visible) { game in
                            MediumGameCard(game: game, config: config, onMakerTap: showMaker)
                        }
                    }
                    .padding(.horizontal, 22).padding(.bottom, 22)
                case .compact:
                    LazyVStack(spacing: 6) {
                        ForEach(visible) { game in
                            CompactGameRow(game: game, config: config, onMakerTap: showMaker)
                        }
                    }
                    .padding(.horizontal, 22).padding(.bottom, 22)
                case .coverWall:
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 150, maximum: 230), spacing: 14)], spacing: 14) {
                        ForEach(visible) { game in
                            CoverWallTile(game: game, config: config)
                        }
                    }
                    .padding(.horizontal, 22).padding(.bottom, 22)
                }
            }
            if let genre = selectedGenre, let entry = activeGenre {
                genreFooter(genre: genre, entry: entry)
            }
        }
    }

    private func showMaker(_ game: Game) {
        viewFilter = .maker(key: game.makerKey, name: game.makerDisplay, makerId: game.makerId ?? "")
    }

    /// 侧栏常驻设计：多列模式按可用宽度自适应列数（放不下两张就单列），不再自动隐藏侧栏。
    private func multiColumnCount(maximum: Int, for width: CGFloat) -> Int {
        let usable = max(0, width - 44)
        let count = Int((usable + 12) / 308)
        return max(1, min(maximum, count))
    }

    private func gridColumns(count: Int) -> [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: 12), count: max(1, count))
    }

    /// 侧栏开关（P16.1）：窗口向外扩展/缩回，关闭时内容与右缘完全不动。
    /// 打开：左侧空间足够 → 全部向左扩展（内容零位移）；不足 → 「尽量左扩 + 剩余右扩」，
    /// 仅剩少量右扩时内容一次性微移，随后随窗口位置自然收敛为零位移。
    private func toggleSidebar() {
        let window = NSApp.keyWindow ?? NSApp.windows.first(where: { $0.isVisible })
        let delta = sidebarWidth
        if sidebarVisible {
            withAnimation(.easeInOut(duration: 0.22)) { sidebarVisible = false }
            guard let window else { return }
            var frame = window.frame
            let targetWidth = max(600, frame.size.width - delta)
            frame.origin.x += frame.size.width - targetWidth   // 右缘与内容不动，仅左缘回缩
            frame.size.width = targetWidth
            window.setFrame(frame, display: true, animate: true)
        } else {
            withAnimation(.easeInOut(duration: 0.22)) { sidebarVisible = true }
            guard let window else { return }
            var frame = window.frame
            let screenMinX = window.screen?.visibleFrame.minX
                ?? NSScreen.main?.visibleFrame.minX
                ?? 0
            let leftRoom = max(0, frame.minX - screenMinX)
            let leftPart = min(delta, leftRoom)
            frame.origin.x -= leftPart
            frame.size.width += delta
            window.setFrame(frame, display: true, animate: true)
        }
    }

    private func collectionEditorSheet(_ editor: CollectionEditor) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(editor.collectionID == nil ? "新建收藏夹" : "重命名收藏夹").font(.headline)
            TextField("收藏夹名称", text: $newCollectionName)
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
                .onSubmit { commitCollectionEditor(editor) }
            HStack {
                Spacer()
                Button("取消") {
                    if editor.collectionID == nil { favorites.pendingNewWorkID = nil }
                    collectionEditor = nil
                }
                Button("确定") { commitCollectionEditor(editor) }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(22)
    }

    private func commitCollectionEditor(_ editor: CollectionEditor) {
        if let collectionID = editor.collectionID {
            favorites.rename(collectionID, to: newCollectionName)
        } else {
            let created = favorites.createCollection(named: newCollectionName)
            if let workID = favorites.pendingNewWorkID {
                favorites.toggle(workID, in: created)
                favorites.pendingNewWorkID = nil
            }
        }
        collectionEditor = nil
    }

    private func emptyState(_ message: String) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "square.stack.3d.up.slash").font(.system(size: 44)).foregroundStyle(.secondary)
            Text(message).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 370)
    }

    /// P19.3：卡片胶囊点击 → 切换对应筛选（与侧栏同一状态）。
    private func handleChipFilter(_ action: ChipFilter) {
        switch action {
        case .category(let name):
            if selectedCategories.contains(name) {
                selectedCategories.remove(name)
            } else {
                selectedCategories.insert(name)
            }
            excludedCategories.remove(name)
        case .form(let name):
            form = (form == name) ? "全部" : name
        case .badge(let key):
            switch key {
            case "voice": filterVoice.toggle()
            case "music": filterMusic.toggle()
            case "video": filterVideo.toggle()
            default: break
            }
        }
    }

    private func handleGenreTap(_ entry: GenreEntry) {
        if (entry.depth ?? 0) > 0 {
            selectedGenre = (selectedGenre == entry.id) ? nil : entry.id
        } else {
            confirmGenreImport = GenreImportRequest(id: entry.id, name: entry.name)
        }
    }

    private func genreRowTrailing(_ entry: GenreEntry) -> String {
        guard (entry.depth ?? 0) > 0 else { return "未导入" }
        if let count = entry.count { return "\(count) 件" }
        return "已导入"
    }

    @ViewBuilder
    private func genreRow(_ entry: GenreEntry) -> some View {
        let selected = selectedGenre == entry.id
        let running = library.genreJobActive && library.genreProgress?.genreId == entry.id
        Button {
            handleGenreTap(entry)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: selected ? "chart.bar.fill" : "chart.bar")
                    .font(.system(size: 12))
                    .foregroundStyle(selected ? Color.accentColor : Color.secondary)
                    .frame(width: 16)
                Text(entry.name).font(.subheadline).lineLimit(1)
                if running {
                    ProgressView().controlSize(.mini)
                }
                Spacer()
                Text(genreRowTrailing(entry)).font(.caption).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(selected ? Color.accentColor.opacity(0.14) : Color.clear, in: RoundedRectangle(cornerRadius: 7))
            .contentShape(RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
        .help((entry.depth ?? 0) > 0 ? "点击按「\(entry.name)」官方人气名次浏览；再点取消" : "尚未导入：点击现导入前 200 名")
    }

    private func genreStrip(_ entry: GenreEntry) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "chart.bar.fill").foregroundStyle(.secondary)
            Text("分类人气：「\(entry.name)」按官方人气名次").font(.subheadline.weight(.medium))
            Spacer()
            Button("返回全部作品") { selectedGenre = nil }.font(.caption)
        }
        .padding(.horizontal, 22).padding(.vertical, 8)
        .background(Color.accentColor.opacity(0.07))
    }

    @ViewBuilder
    private func genreFooter(genre: String, entry: GenreEntry) -> some View {
        let depth = entry.depth ?? 0
        let count = entry.count
        let loading = library.genreJobActive
        VStack(alignment: .leading, spacing: 8) {
            Divider().padding(.horizontal, 22)
            HStack(spacing: 10) {
                if let count {
                    Text("「\(entry.name)」已加载名次 \(min(depth, count))/\(count)")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("「\(entry.name)」已加载名次 \(depth)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let seen = entry.seenAt, seen.count >= 10 {
                    Text("数据 \(String(seen.prefix(10)))").font(.caption).foregroundStyle(.tertiary)
                }
                Spacer()
                if loading {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("正在导入…").font(.caption).foregroundStyle(.secondary)
                    }
                } else if let count, depth >= count {
                    Text("已到末尾").font(.caption).foregroundStyle(.tertiary)
                } else {
                    Button {
                        library.startGenreImport(genreId: genre, more: true)
                    } label: {
                        Label("载入更多（下一 100 名，含新作品入库）", systemImage: "ellipsis.circle")
                    }
                    .controlSize(.small)
                    .help("现抓下一段人气名次；榜上不在库的作品会顺带入库")
                }
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 18)
        }
    }

    @ViewBuilder
    private var categorySearchResults: some View {
        let keyword = categorySearch.trimmingCharacters(in: .whitespaces)
        let matches = categories.filter { $0.localizedCaseInsensitiveContains(keyword) }.prefix(40)
        if matches.isEmpty {
            Text("没有匹配的分类").font(.caption).foregroundStyle(.tertiary)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(matches), id: \.self) { name in
                    categoryResultRow(name)
                }
            }
        }
    }

    private func categoryResultRow(_ name: String) -> some View {
        let selected = selectedCategories.contains(name)
        let excluded = excludedCategories.contains(name)
        return Button {
            if selected {
                selectedCategories.remove(name)
            } else {
                selectedCategories.insert(name)
                excludedCategories.remove(name)
            }
        } label: {
            HStack(spacing: 6) {
                Text(name).font(.caption).lineLimit(1)
                Spacer()
                if excluded { Text("已排除").font(.caption2).foregroundStyle(.tertiary) }
                if selected { Image(systemName: "checkmark").font(.system(size: 10)) }
            }
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(selected ? Color.accentColor.opacity(0.12) : Color.clear, in: RoundedRectangle(cornerRadius: 5))
            .contentShape(RoundedRectangle(cornerRadius: 5))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button(excluded ? "移出排除" : "排除此分类") {
                if excluded {
                    excludedCategories.remove(name)
                } else {
                    excludedCategories.insert(name)
                    selectedCategories.remove(name)
                }
            }
        }
    }

    private var sidebar: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("收藏").font(.title3.bold())
                navRow(icon: "square.grid.2x2", title: "全部作品", count: library.games.count, selected: viewFilter == .all) {
                    viewFilter = .all
                }
                ForEach(favorites.data.collections) { collection in
                    navRow(icon: "folder", title: collection.name, count: collection.workIDs.count,
                           selected: viewFilter == .collection(collection.id)) {
                        viewFilter = .collection(collection.id)
                    }
                    .contextMenu {
                        Button("重命名…") {
                            newCollectionName = collection.name
                            collectionEditor = CollectionEditor(collectionID: collection.id, initialName: collection.name)
                        }
                        Button("删除收藏夹", role: .destructive) {
                            confirmDeleteCollection = collection
                        }
                    }
                }
                Button {
                    newCollectionName = ""
                    collectionEditor = CollectionEditor(collectionID: nil)
                } label: {
                    Label("新建收藏夹", systemImage: "plus")
                }
                .buttonStyle(.link)
                .font(.caption)

                if !favorites.data.makers.isEmpty {
                    Text("关注的制作者").font(.caption).foregroundStyle(.secondary).padding(.top, 2)
                    ForEach(favorites.data.makers) { maker in
                        navRow(icon: "person.crop.circle", title: maker.name, count: nil,
                               selected: viewFilter.makerKey == maker.key) {
                            viewFilter = .maker(key: maker.key, name: maker.name, makerId: maker.makerID)
                        }
                        .contextMenu {
                            Button("取消关注", role: .destructive) {
                                favorites.toggleFollow(key: maker.key, name: maker.name, makerID: maker.makerID)
                            }
                        }
                    }
                }

                Divider()
                Text("分类人气").font(.title3.bold())
                VStack(alignment: .leading, spacing: 7) {
                    TextField("搜索分类（官方全量目录）", text: $genreSearch)
                        .textFieldStyle(.roundedBorder)
                    if genreEntries.isEmpty {
                        Text(library.genreCatalog.isEmpty ? "尚无分类人气数据：先点「开始更新数据」，或输入分类名用「现导入」。" : "没有匹配的分类。")
                            .font(.caption).foregroundStyle(.tertiary)
                    } else {
                        ForEach(genreEntries.prefix(24)) { entry in
                            genreRow(entry)
                        }
                        if genreEntries.count > 24 {
                            Text("还有 \(genreEntries.count - 24) 个结果；继续输入可缩小范围")
                                .font(.caption).foregroundStyle(.tertiary)
                        }
                    }
                }

                Divider()
                Text("筛选条件").font(.title3.bold())
                VStack(alignment: .leading, spacing: 7) {
                    Text("游戏名或制作者").font(.caption).foregroundStyle(.secondary)
                    TextField("搜索", text: $query).textFieldStyle(.roundedBorder)
                }
                RangeFields(title: "评分区间", unit: "星", lower: $ratingLow, upper: $ratingHigh)
                Toggle("包含未评分作品", isOn: $includeUnrated).font(.caption)
                RangeFields(title: "销量区间", unit: "份", lower: $salesLow, upper: $salesHigh)
                RangeFields(title: "价格区间", unit: "日元", lower: $priceLow, upper: $priceHigh)
                VStack(alignment: .leading, spacing: 7) {
                    Text("分类 / 标签（已识别；多选取交集，同时满足全部所选）").font(.caption).foregroundStyle(.secondary)
                    TextField("搜索分类…", text: $categorySearch)
                        .textFieldStyle(.roundedBorder)
                    if categorySearch.trimmingCharacters(in: .whitespaces).isEmpty {
                        SetFilterMenu(title: "包含分类（交集）", emptyLabel: "全部", options: categories, selection: $selectedCategories)
                        SetFilterMenu(title: "排除分类", emptyLabel: "不排除", options: categories, selection: $excludedCategories)
                    } else {
                        categorySearchResults
                    }
                }
                VStack(alignment: .leading, spacing: 7) {
                    Text("作品形式（如 RPG、SLG）").font(.caption).foregroundStyle(.secondary)
                    Picker("作品形式", selection: $form) {
                        ForEach(forms, id: \.self) { Text($0).tag($0) }
                    }.labelsHidden()
                }
                VStack(alignment: .leading, spacing: 7) {
                    Text("发售年份（可多选）").font(.caption).foregroundStyle(.secondary)
                    SetFilterMenu(title: "包含年份", emptyLabel: "全部", options: releaseYears, selection: $selectedYears)
                }
                VStack(alignment: .leading, spacing: 7) {
                    Text("内容标志（可多选，同时满足）").font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 14) {
                        Toggle("配音", isOn: $filterVoice)
                        Toggle("音乐", isOn: $filterMusic)
                        Toggle("动画", isOn: $filterVideo)
                    }
                    .toggleStyle(.checkbox)
                    .font(.caption)
                }
                Divider()
                VStack(alignment: .leading, spacing: 7) {
                    Text("渐进导入（后台分批入库）").font(.caption).foregroundStyle(.secondary)
                    Toggle("开启（关闭 = 暂停，可随时再开）", isOn: importToggle).font(.caption)
                    Picker("范围", selection: $importYears) {
                        Text("最近一年").tag("1")
                        Text("最近三年").tag("3")
                        Text("最近五年").tag("5")
                        Text("最近七年").tag("7")
                        if importYears.hasPrefix("since:") {
                            Text("自 \(importYears.dropFirst("since:".count)) 年").tag(importYears)
                        }
                    }
                    .labelsHidden()
                    .disabled(library.importJobActive)
                    Button("自选起始年份…") { yearPickTarget = .importStart }
                        .buttonStyle(.link)
                        .font(.caption)
                        .disabled(library.importJobActive)
                    if library.importJobActive {
                        if let job = library.importProgress {
                            Text("当前任务：\(yearsLabel(job.years ?? "1")) · \((job.running ?? false) ? "进行中" : "已暂停")")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Button("取消导入任务…") { confirmCancelImport = true }
                            .buttonStyle(.link)
                            .font(.caption)
                            .alert("取消导入任务？", isPresented: $confirmCancelImport) {
                                Button("取消任务", role: .destructive) { library.cancelImport() }
                                Button("再想想", role: .cancel) {}
                            } message: {
                                Text("任务定义将被删除，已入库的作品保留；之后可随时重新开启。")
                            }
                    }
                }
                Button("清空筛选") {
                    query = ""; ratingLow = ""; ratingHigh = ""; salesLow = ""; salesHigh = "";
                    priceLow = ""; priceHigh = ""; selectedCategories = []; excludedCategories = []; form = "全部"; includeUnrated = false; selectedYears = []
                    filterVoice = false; filterMusic = false; filterVideo = false
                    selectedGenre = nil; genreSearch = ""; categorySearch = ""
                }
                .buttonStyle(.link)
                Spacer(minLength: 10)
                Text("数据来自你导入的文件。「更新」重读同一文件；「开始更新数据」运行本地管道（导入 → 销量 → 封面 → 导出），完成后自动刷新。收藏与偏好保存在本机。")
                    .font(.caption).foregroundStyle(.tertiary)
            }
            .padding(20)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .alert("删除收藏夹？", isPresented: Binding(
            get: { confirmDeleteCollection != nil },
            set: { if !$0 { confirmDeleteCollection = nil } }
        )) {
            Button("删除", role: .destructive) {
                if let collection = confirmDeleteCollection {
                    if case .collection(let id) = viewFilter, id == collection.id { viewFilter = .all }
                    favorites.delete(collection.id)
                }
                confirmDeleteCollection = nil
            }
            Button("取消", role: .cancel) { confirmDeleteCollection = nil }
        } message: {
            Text("只会移除这个收藏夹，作品与本地数据不受影响。")
        }
    }

    private func navRow(icon: String, title: String, count: Int?, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundStyle(selected ? Color.accentColor : Color.secondary)
                    .frame(width: 16)
                Text(title).font(.subheadline).lineLimit(1)
                Spacer()
                if let count {
                    Text("\(count)").font(.caption).foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(selected ? Color.accentColor.opacity(0.14) : Color.clear, in: RoundedRectangle(cornerRadius: 7))
            .contentShape(RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
    }
}

@main
struct DoujinGameFinderApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
            .windowStyle(.titleBar)
    }
}

import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { SpreadsheetFile, Workbook } = require("@oai/artifact-tool");

const root = path.resolve(import.meta.dirname, "..");
const sourceDir = path.join(root, "experiments", "analysis", "xxl10_four_method_final");
const outputPath = path.join(sourceDir, "xxl10_four_method_results.xlsx");
const previewDir = path.join(process.env.TEMP, "codex-xxl10-four-method-workbook-preview");
const font = "Arial";
const darkBlue = "#405B73";
const steelBlue = "#6F8FA8";
const paleBlue = "#D4E0E9";
const blueGray = "#B7C1CA";
const textColor = "#333333";

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted && ch === '"' && text[i + 1] === '"') {
      cell += '"';
      i += 1;
    } else if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function typed(rows) {
  const textColumns = new Set([
    "method", "condition_id", "classification", "solver_status", "stop_reason",
    "instance_hash", "x0_hash", "source_file", "source_sha256", "baseline", "comparator", "path",
  ]);
  const headers = rows[0];
  return [headers, ...rows.slice(1).map((row) => row.map((value, index) => {
    if (value === "") return null;
    const header = headers[index];
    if (textColumns.has(header)) return value;
    if (value === "True") return true;
    if (value === "False") return false;
    const number = Number(value);
    return Number.isFinite(number) ? number : value;
  }))];
}

async function csv(name) {
  return typed(parseCsv(await fs.readFile(path.join(sourceDir, name), "utf8")));
}

function addTableSheet(workbook, name, title, data, options = {}) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: font, size: 14, bold: true, color: textColor };
  sheet.getRange("A3").values = [[options.note ?? "Source: frozen formal result artifacts; generated without optimization."]];
  sheet.getRange("A3").format.font = { name: font, size: 9, italic: true, color: "#5C7488" };
  const rowCount = data.length;
  const colCount = data[0].length;
  const target = sheet.getRangeByIndexes(3, 0, rowCount, colCount);
  target.values = data;
  target.format.font = { name: font, size: 9, color: textColor };
  target.format.verticalAlignment = "center";
  const header = sheet.getRangeByIndexes(3, 0, 1, colCount);
  header.format.fill = darkBlue;
  header.format.font = { name: font, size: 9, bold: true, color: "#FFFFFF" };
  header.format.horizontalAlignment = "center";
  header.format.wrapText = true;
  const body = sheet.getRangeByIndexes(4, 0, Math.max(rowCount - 1, 1), colCount);
  body.format.borders = { insideHorizontal: { style: "thin", color: "#D9DDE2" }, bottom: { style: "thin", color: "#D9DDE2" } };
  target.format.autofitColumns();
  target.format.autofitRows();
  for (let index = 0; index < colCount; index += 1) {
    const heading = data[0][index];
    const column = sheet.getRangeByIndexes(4, index, Math.max(rowCount - 1, 1), 1);
    if (heading.includes("rate") || heading.includes("gap") || heading.includes("p_")) column.format.numberFormat = "0.0000";
    if (heading.includes("time") || heading.includes("seconds")) column.format.numberFormat = "0.000";
    if (heading.includes("memory_gib")) column.format.numberFormat = "0.000";
    if (heading === "objective" || heading === "lower_bound" || heading === "upper_bound") column.format.numberFormat = "#,##0.000";
  }
  sheet.freezePanes.freezeRows(4);
  if (options.tabColor) sheet.tabColor = options.tabColor;
  return sheet;
}

const summary = await csv("xxl10_four_method_summary.csv");
const comparisons = await csv("xxl10_paired_comparisons.csv");
const records = await csv("xxl10_four_method_records.csv");
const direct = await csv("xxl10_direct_diagnostics.csv");
const sources = await csv("xxl10_data_sources.csv");
const manifest = await csv("xxl10_source_sha256_manifest.csv");
summary[0] = ["Method", "Scheduled", "Executed", "Certified", "Certification rate", "Limited", "Mean core time (s)", "Mean oracle time (s)"];
comparisons[0] = ["Baseline", "Comparator", "N", "GM time ratio", "Comparator wins", "Baseline wins", "Ties", "Wilcoxon W", "Two-sided p"];

const workbook = Workbook.create();
const summarySheet = addTableSheet(
  workbook,
  "Summary",
  "XXL10 four-method computational comparison",
  summary,
  { tabColor: darkBlue, note: "Exact-certified core-time means exclude Direct time-limited runs." },
);
summarySheet.getRange("A10").values = [["Paired comparisons"]];
summarySheet.getRange("A10").format.font = { name: font, size: 12, bold: true, color: textColor };
const compareRange = summarySheet.getRangeByIndexes(11, 0, comparisons.length, comparisons[0].length);
compareRange.values = comparisons;
compareRange.format.font = { name: font, size: 9, color: textColor };
summarySheet.getRangeByIndexes(11, 0, 1, comparisons[0].length).format = {
  fill: steelBlue,
  font: { name: font, size: 9, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  wrapText: true,
};
compareRange.format.autofitColumns();
compareRange.format.autofitRows();
summarySheet.getRange("A20").values = [["Interpretation"]];
summarySheet.getRange("A20").format.font = { name: font, size: 11, bold: true, color: textColor };
summarySheet.getRange("A21:H24").values = [
  ["Direct", "3/10 exact-certified; seven limited runs remain in the denominator and are excluded from ordinary exact-pair speedups.", null, null, null, null, null, null],
  ["Seed 20260922", "Historical report retained as STOPPED_INTEGRITY_FAILURE; independent audit classifies the preserved evidence as TIME_LIMIT_NO_INCUMBENT.", null, null, null, null, null, null],
  ["Seed 20260927", "Outer monitor hard limit; no objective, bound, gap, or final solver status inferred.", null, null, null, null, null, null],
  ["Environment", "Direct and EF-BD: Python 3.12.7 / Gurobi 13.0.1. Historical Scaling V2 solver version remains not fully verifiable.", null, null, null, null, null, null],
];
summarySheet.getRange("A21:A24").format.fill = paleBlue;
summarySheet.getRange("A21:A24").format.font = { name: font, size: 9, bold: true, color: textColor };
summarySheet.getRange("B21:H24").merge(true);
summarySheet.getRange("B21:H24").format.wrapText = true;
summarySheet.getRange("A21:H24").format.font = { name: font, size: 9, color: textColor };
summarySheet.getRange("A21:H24").format.autofitRows();
summarySheet.getRange("A:A").format.columnWidth = 19;
summarySheet.getRange("B:B").format.columnWidth = 21;
summarySheet.getRange("C:I").format.columnWidth = 15;
summarySheet.getRange("B21:H24").format.columnWidth = 16;
summarySheet.getRange("A4:I4").format.rowHeight = 30;
summarySheet.getRange("A12:I12").format.rowHeight = 30;

addTableSheet(workbook, "All records", "Forty seed-method records", records, { tabColor: steelBlue });
addTableSheet(workbook, "Direct diagnostics", "Direct completion and resource diagnostics", direct, { tabColor: steelBlue });
addTableSheet(workbook, "Sources", "Result sources and hashes", sources, { tabColor: blueGray });
addTableSheet(workbook, "SHA-256 manifest", "Archived source-file manifest", manifest, { tabColor: blueGray });

workbook.recalculate();
const summaryCheck = await workbook.inspect({ kind: "table", sheetId: "Summary", range: "A2:I24", include: "values,formulas", tableMaxRows: 24, tableMaxCols: 9, maxChars: 12000 });
const errorCheck = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.mkdir(previewDir, { recursive: true });
for (const name of ["Summary", "All records", "Direct diagnostics", "Sources", "SHA-256 manifest"]) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${name.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewDir, summaryCheck: summaryCheck.ndjson, errorCheck: errorCheck.ndjson }, null, 2));

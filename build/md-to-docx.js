// Generic Markdown -> Word converter for the deliverable documents.
// Supports: # headings (1-3), paragraphs, **bold** runs, `code` runs, - bullets, 1. numbered items, pipe tables.
const fs = require('fs'); const D = require('docx');
const {Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, AlignmentType, Footer, PageNumber} = D;
const INK = '15201C', MUT = '5C6862', RULE = 'D9DEDA', HEAD = 'F1F5F3', ACC = '058C72';
const hair = {style: BorderStyle.SINGLE, size: 4, color: RULE};
const borders = {top: hair, bottom: hair, left: hair, right: hair};
function runs(text, base = {}) {
  const out = []; const re = /(\*\*[^*]+\*\*|`[^`]+`)/g; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({text: text.slice(last, m.index), font: 'Calibri', size: 21, color: INK, ...base}));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({text: t.slice(2, -2), bold: true, font: 'Calibri', size: 21, color: INK, ...base}));
    else out.push(new TextRun({text: t.slice(1, -1), font: 'Consolas', size: 19, color: ACC, ...base}));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({text: text.slice(last), font: 'Calibri', size: 21, color: INK, ...base}));
  return out;
}
function table(lines) {
  const rows = lines.filter(l => !/^\|\s*-+/.test(l)).map(l => l.replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
  const ncol = Math.max(...rows.map(r => r.length)); const w = Math.floor(9360 / ncol);
  return new Table({width: {size: 9360, type: WidthType.DXA}, rows: rows.map((r, i) => new TableRow({
    tableHeader: i === 0,
    children: Array.from({length: ncol}, (_, j) => new TableCell({
      borders, width: {size: w, type: WidthType.DXA}, shading: i === 0 ? {fill: HEAD, type: ShadingType.CLEAR, color: 'auto'} : undefined,
      margins: {top: 60, bottom: 60, left: 90, right: 90},
      children: [new Paragraph({spacing: {after: 0}, children: runs(r[j] || '', i === 0 ? {bold: true, size: 19} : {size: 19})})]
    }))
  }))});
}
function convert(md) {
  const lines = md.split('\n'); const ch = []; let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^\|/.test(l)) { const t = []; while (i < lines.length && /^\|/.test(lines[i])) t.push(lines[i++]); ch.push(table(t)); ch.push(new Paragraph({spacing: {after: 120}})); continue; }
    if (/^# /.test(l)) ch.push(new Paragraph({heading: HeadingLevel.TITLE, spacing: {after: 200}, children: [new TextRun({text: l.slice(2), font: 'Georgia', size: 40, bold: true, color: INK})]}));
    else if (/^## /.test(l)) ch.push(new Paragraph({heading: HeadingLevel.HEADING_1, spacing: {before: 360, after: 140}, border: {bottom: {style: BorderStyle.SINGLE, size: 8, color: ACC}}, children: [new TextRun({text: l.slice(3), font: 'Georgia', size: 28, bold: true, color: INK})]}));
    else if (/^### /.test(l)) ch.push(new Paragraph({heading: HeadingLevel.HEADING_2, spacing: {before: 240, after: 100}, children: [new TextRun({text: l.slice(4), font: 'Calibri', size: 23, bold: true, color: INK})]}));
    else if (/^\s*[-*] /.test(l)) ch.push(new Paragraph({bullet: {level: (l.match(/^\s*/)[0].length >= 2) ? 1 : 0}, spacing: {after: 80}, children: runs(l.replace(/^\s*[-*] /, ''))}));
    else if (/^\d+\. /.test(l)) ch.push(new Paragraph({numbering: {reference: 'num', level: 0}, spacing: {after: 80}, children: runs(l.replace(/^\d+\. /, ''))}));
    else if (l.trim() === '') { /* blank */ }
    else ch.push(new Paragraph({spacing: {after: 140, line: 276}, children: runs(l)}));
    i++;
  }
  return ch;
}
const [,, src, dst] = process.argv;
const doc = new Document({
  numbering: {config: [{reference: 'num', levels: [{level: 0, format: 'decimal', text: '%1.', alignment: AlignmentType.START, style: {paragraph: {indent: {left: 540, hanging: 300}}}}]}]},
  styles: {default: {document: {run: {font: 'Calibri', size: 21}}}},
  sections: [{properties: {page: {margin: {top: 1080, bottom: 1080, left: 1080, right: 1080}}},
    footers: {default: new Footer({children: [new Paragraph({alignment: AlignmentType.CENTER, children: [new TextRun({text: 'Cochrane continuing-care demand  ·  page ', font: 'Calibri', size: 17, color: MUT}), new TextRun({children: [PageNumber.CURRENT], font: 'Calibri', size: 17, color: MUT})]})]})},
    children: convert(fs.readFileSync(src, 'utf8'))}]
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(dst, b); console.log('wrote', dst, b.length, 'bytes'); });

// Cochrane campus-of-care — one-page summary of findings (Word)
// Mirrors cochrane-onepager.html. Regenerate with: node build-onepager-docx.js
const fs=require('fs');
const {Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,Table,TableRow,TableCell,
 WidthType,ShadingType,BorderStyle,Footer,PageNumber,LevelFormat,TabStopType}=require('docx');

const W=10080;                     // content width (Letter, 0.75" margins)
const LOCAL='058C72', OUT='C4671A', INK='15201C', INK2='3A4844', MUT='5C6862',
      FAINT='8B958F', RULE='DDE2DE', HEAD='EDF0EC', LWASH='E9F3F0', OWASH='FBEFE4';
const SERIF='Georgia', SANS='Calibri', MONO='Consolas';

const none={style:BorderStyle.NONE,size:0,color:'FFFFFF'};
const noBorders={top:none,bottom:none,left:none,right:none};
const hair=c=>({style:BorderStyle.SINGLE,size:4,color:c||RULE});
const boxed=()=>({top:hair(),bottom:hair(),left:hair(),right:hair()});

// ── text ───────────────────────────────────────────────────
const P=(t,o={})=>new Paragraph({spacing:{after:o.after??120,before:o.before??0,line:o.line??252},
  alignment:o.align,
  children:[new TextRun({text:t,font:o.font||SANS,size:o.size||20,bold:o.bold,italics:o.italics,
    color:o.color||INK,characterSpacing:o.cs,allCaps:o.caps})]});
const RUNS=(runs,o={})=>new Paragraph({spacing:{after:o.after??120,before:o.before??0,line:252},
  children:runs.map(r=>new TextRun({text:r.t,font:r.f||SANS,size:r.s||20,bold:r.b,italics:r.i,
    color:r.c||INK}))});
// section rule — mono, uppercase, teal, hairline underneath
const H2=t=>new Paragraph({heading:HeadingLevel.HEADING_1,spacing:{before:320,after:120},
  border:{bottom:hair()},
  children:[new TextRun({text:t,font:MONO,size:16,bold:true,color:LOCAL,characterSpacing:26,allCaps:true})]});
const SPACER=(h=100)=>new Paragraph({spacing:{after:h},children:[new TextRun({text:'',size:2})]});

// ── tables ─────────────────────────────────────────────────
const cell=(children,{w,shade,span,borders,valign}={})=>new TableCell({
  width:{size:w,type:WidthType.DXA},columnSpan:span,
  shading:shade?{type:ShadingType.CLEAR,fill:shade,color:'auto'}:undefined,
  margins:{top:70,bottom:70,left:120,right:120},
  verticalAlign:valign, borders:borders||boxed(), children});
const tcell=(t,{w,shade,bold,align,color,font,size,span}={})=>cell(
  [new Paragraph({alignment:align,spacing:{after:0,line:240},
    children:[new TextRun({text:t,font:font||SANS,size:size||18,bold,color:color||INK})]})],{w,shade,span});

// headers right-aligned except the first column; last row optionally a totals row
function dataTable(headers,rows,widths,opts={}){
  const hdr=new TableRow({tableHeader:true,children:headers.map((h,i)=>
    tcell(h,{w:widths[i],shade:HEAD,bold:true,font:MONO,size:14,color:MUT,
      align:i===0?AlignmentType.LEFT:AlignmentType.RIGHT}))});
  const body=rows.map((r,ri)=>new TableRow({children:r.map((c,i)=>{
    const tot=opts.totalRow&&ri===rows.length-1;
    const v=typeof c==='object'?c:{t:c};
    return tcell(v.t,{w:widths[i],shade:tot?HEAD:undefined,bold:tot||v.b,color:v.c,
      font:v.f, size:v.s, align:i===0?AlignmentType.LEFT:AlignmentType.RIGHT});
  })}));
  return new Table({width:{size:W,type:WidthType.DXA},columnWidths:widths,rows:[hdr,...body]});
}

// callout with a coloured left edge
const note=(label,paras,warn)=>new Table({width:{size:W,type:WidthType.DXA},columnWidths:[W],
  rows:[new TableRow({children:[new TableCell({
    width:{size:W,type:WidthType.DXA},
    shading:{type:ShadingType.CLEAR,fill:warn?OWASH:LWASH,color:'auto'},
    margins:{top:150,bottom:150,left:180,right:180},
    borders:{top:none,bottom:none,right:none,
      left:{style:BorderStyle.SINGLE,size:18,color:warn?OUT:LOCAL}},
    children:[new Paragraph({spacing:{after:80},children:[new TextRun({text:label,font:MONO,size:14,
      bold:true,color:warn?OUT:LOCAL,characterSpacing:26,allCaps:true})]}),...paras]})]})]});
const nP=runs=>new Paragraph({spacing:{after:70,line:252},
  children:runs.map(r=>new TextRun({text:r.t,font:SANS,size:19,bold:r.b,italics:r.i,color:r.c||INK}))});
const capText=t=>new Paragraph({spacing:{before:100,after:140,line:246},
  children:[new TextRun({text:t,font:SANS,size:17,color:MUT})]});

// numbered method step: bold lead-in, then the detail
const step=(n,lead,rest)=>new Paragraph({spacing:{after:90,line:252},
  indent:{left:400,hanging:400},
  children:[
    new TextRun({text:n+'.  ',font:MONO,size:16,bold:true,color:LOCAL}),
    new TextRun({text:lead+'  ',font:SANS,size:19,bold:true,color:INK}),
    new TextRun({text:rest,font:SANS,size:19,color:INK2})]});

// ═══════════════════════════════════════════════════════════
const doc=new Document({
  creator:'Continuing Care Planning',
  title:'Cochrane Demand and Capacity',
  description:'One-page summary of findings — Bethany Cochrane & Big Hill Lodge campus of care',
  styles:{default:{document:{run:{font:SANS,size:20,color:INK}}}},
  sections:[{
    properties:{page:{size:{width:12240,height:15840},
      margin:{top:1080,bottom:1080,left:1080,right:1080}}},
    footers:{default:new Footer({children:[new Paragraph({
      alignment:AlignmentType.RIGHT,spacing:{before:160},border:{top:hair()},
      children:[new TextRun({text:'Cochrane Demand and Capacity   ·   ',font:MONO,size:14,color:MUT}),
        new TextRun({children:[PageNumber.CURRENT],font:MONO,size:14,color:MUT})]})]})},
    children:[

// ── masthead ───────────────────────────────────────────────
P('Bethany Cochrane & Big Hill Lodge campus of care  ·  Summary of findings',
  {font:MONO,size:14,bold:true,color:MUT,cs:26,caps:true,after:100}),
P('Cochrane Demand and Capacity',{font:SERIF,size:40,bold:true,after:100}),
P('Seven in ten Town of Cochrane residents entering continuing care are placed outside the town. '+
  'Most beds inside Cochrane’s own facilities go to people who are not Cochrane residents.',
  {font:SERIF,size:21,color:INK2,after:160}),

new Table({width:{size:W,type:WidthType.DXA},columnWidths:[2280,2520,3240,2040],
  rows:[
    new TableRow({children:[
      tcell('PERIOD',{w:2280,shade:HEAD,font:MONO,size:14,bold:true,color:MUT}),
      tcell('SCOPE',{w:2520,shade:HEAD,font:MONO,size:14,bold:true,color:MUT}),
      tcell('POPULATION',{w:3240,shade:HEAD,font:MONO,size:14,bold:true,color:MUT}),
      tcell('STATUS',{w:2040,shade:HEAD,font:MONO,size:14,bold:true,color:MUT})]}),
    new TableRow({children:[
      tcell('FY2022–FY2026',{w:2280,size:18}),
      tcell('Type A & Type B (level 4)',{w:2520,size:18}),
      tcell('317 Town residents · 344 admissions',{w:3240,size:18}),
      tcell('Validated',{w:2040,size:18})]})
  ]}),

// ── cohorts ────────────────────────────────────────────────
H2('Cohorts'),
dataTable(['Cohort','Definition','Question it answers','People'],[
  [{t:'A',f:MONO,b:true,c:LOCAL},'Cochrane resident placed in a Cochrane facility',
   'How much local demand did local capacity absorb?',{t:'97',b:true,c:LOCAL}],
  [{t:'C',f:MONO,b:true,c:OUT},'Cochrane resident placed outside Cochrane',
   'How much local demand had to leave town?',{t:'220',b:true,c:OUT}],
  [{t:'B',f:MONO,b:true,c:INK2},'Non-resident placed in a Cochrane facility',
   'How much of local capacity serves outside demand?',{t:'189',b:true}]
],[900,3180,4200,1800]),
capText('A + C = total Town demand  ·  A + B = total use of Cochrane capacity  ·  '+
  'C ÷ (A+C) = share that left town. Demand is counted per person on first-ever placement; '+
  'capacity per admission, because each occupies a bed.'),

// ── finding 01 ─────────────────────────────────────────────
H2('Finding 01 · Local demand and where it went'),
dataTable(['Care type','Residents','Placed in Cochrane','Placed outside','% outside'],[
  ['Type A — long-term care','165',{t:'25',c:LOCAL,b:true},{t:'140',c:OUT,b:true},{t:'84.8%',c:OUT,b:true}],
  ['Type B — supportive living','152',{t:'72',c:LOCAL,b:true},{t:'80',c:OUT,b:true},{t:'52.6%',c:OUT,b:true}],
  ['All care types','317',{t:'97',c:LOCAL},{t:'220',c:OUT},{t:'69.4%',c:OUT}]
],[3480,1500,1900,1600,1600],{totalRow:true}),
capText('Where local capacity exists at the right care level, about half of local demand is met locally. '+
  'Where it does not, almost none is — Bethany Cochrane absorbed 25 of the 165 residents needing long-term care.'),

// ── finding 01b · trend ────────────────────────────────────
H2('Finding 01b · Trend by fiscal year'),
dataTable(['Fiscal year (ending 31 Mar)','Residents','Placed in Cochrane','Placed outside','% outside'],[
  ['FY 2022','55',{t:'19',c:LOCAL},{t:'36',c:OUT},{t:'65.5%',c:OUT,b:true}],
  ['FY 2023','56',{t:'20',c:LOCAL},{t:'36',c:OUT},{t:'64.3%',c:OUT,b:true}],
  ['FY 2024','70',{t:'23',c:LOCAL},{t:'47',c:OUT},{t:'67.1%',c:OUT,b:true}],
  ['FY 2025','68',{t:'15',c:LOCAL},{t:'53',c:OUT},{t:'77.9%',c:OUT,b:true}],
  ['FY 2026','68',{t:'20',c:LOCAL},{t:'48',c:OUT},{t:'70.6%',c:OUT,b:true}],
  ['Five-year total','317',{t:'97',c:LOCAL},{t:'220',c:OUT},{t:'69.4%',c:OUT}]
],[3480,1500,1900,1600,1600],{totalRow:true}),
capText('Between 64% and 78% every year. FY2025 is the weakest but stands alone — the defensible description '+
  'is a persistent two-thirds to three-quarters, not a deteriorating trend. Annual volume rose from 55 to 68 as the town grew.'),

// ── finding 02 ─────────────────────────────────────────────
H2('Finding 02 · Who occupies Cochrane’s beds'),
dataTable(['Residence at entry to care','Admissions','People','Share'],[
  ['Town of Cochrane','140','133',{t:'40.7%',c:LOCAL,b:true}],
  ['Cochrane catchment (Springbank, rural Rocky View)','6','6',{t:'1.7%',c:LOCAL,b:true}],
  ['Not a Cochrane-area resident','197','189',{t:'57.3%',c:OUT,b:true}],
  ['All admissions into Cochrane facilities','344','—','100%']
],[5080,1700,1600,1700],{totalRow:true}),
capText('Shares are of all 344 admissions. One further admission has unresolved residence '+
  'and is not attributed to a group.'),
note('Both true at once',[
  nP([{t:'Two-thirds of the town’s residents are placed elsewhere, while nearly three-fifths of the town’s beds '+
      'are filled by people from elsewhere. Each finding strengthens the other, and they come from independent measures.'}])
]),

// ── finding 03 ─────────────────────────────────────────────
H2('Finding 03 · The hospital pathway'),
dataTable(['Setting the resident entered care from','People','Placed in Cochrane','% local'],[
  ['Own home / community','93','52',{t:'55.9%',c:LOCAL,b:true}],
  ['Lodge','24','13',{t:'54.2%',c:LOCAL,b:true}],
  ['Other / unclear','22','5','22.7%'],
  ['Acute hospital','149','25',{t:'16.8%',c:OUT,b:true}],
  ['Transition / rehab','12','1',{t:'8.3%',c:OUT,b:true}],
  ['Supportive living','17','1',{t:'5.9%',c:OUT,b:true}]
],[4680,1600,2100,1700]),
capText('Acute hospital is the largest single entry point — 149 of 317 residents, 47% — and the least likely to end '+
  'in a local placement. A resident entering from home has roughly even odds of a Cochrane bed; from a hospital bed, '+
  'about one in six. The constraint is not only bed count but the absence of local capacity able to absorb an urgent discharge.'),

// ── finding 04 ─────────────────────────────────────────────
H2('Finding 04 · Time to placement, and whether Cochrane was requested'),
dataTable(['Group','n','Median','p90'],[
  ['Town → placed in Cochrane','97',{t:'32 d',c:LOCAL,b:true},'335 d'],
  ['Town → placed outside','220',{t:'18 d',c:OUT,b:true},'190 d'],
  ['Non-resident → in Cochrane','140','30 d','327 d']
],[5080,1500,1750,1750]),
capText('Residents placed outside waited less. That is the signature of accepting the first available bed, not of '+
  'better service — and the 90th percentile shows the cost of holding out for a local one. New placements and '+
  'facility transfers run on separate clocks and are never blended.'),
note('Direct evidence of displacement',[
  nP([{t:'138 of the 220 residents placed outside Cochrane had formally requested a Cochrane site and were on that '+
      'waitlist at or before the moment they were placed elsewhere.',b:true},
    {t:' Median 70 days waiting; longest 1,358 days.'}]),
  nP([{t:'Verified: none joined the Cochrane list after their placement. Because the waitlist record starts '+
      '1 Apr 2021, 138 is a floor.'}])
],true),

// ── method ─────────────────────────────────────────────────
H2('How residence was determined'),
RUNS([{t:'Placement records show where people were '},{t:'admitted',i:true},{t:', not where they '},
  {t:'lived',i:true},{t:'. Source location gives the sending facility; address history updates to the destination '+
  'facility on admission — 50 records in this cohort point at Bethany Cochrane itself. The provincial registry '+
  'solves it: one row per person per fiscal year, showing where every Albertan lived, going back to the 1990s.'}]),
step(1,'Anchor on entry to residential care.','Each person’s first-ever Type A/B admission. Day programs and '+
  'hospital transition units are excluded — anchoring on those sits a median 1.6 years too early and changed 21% of anchors.'),
step(2,'Look back three fiscal years','from that anchor, ending the year before care began. Pre-care years cannot '+
  'contain a facility address. Two- and five-year windows return an identical set of people.'),
step(3,'Resolve to a legal boundary.','Town of Cochrane = Statistics Canada census subdivision, 568 postal codes. '+
  'The reference table’s municipality field mislabels 22 Rocky View County codes as Cochrane; the T4C prefix splits 562 Town / 41 county.'),
step(4,'Fix residence once per person.','Origin does not change because someone later moves beds, so a transfer '+
  'between two Cochrane facilities cannot convert an outside resident into a local one.'),
step(5,'Two wait clocks, never blended.','New placements run from assessment and approval; transfers from the '+
  'transfer-enabled date. Medians differ by an order of magnitude. Legacy records with the approval date back-filled '+
  'to the admission date are excluded from the new-placement clock.'),
step(6,'Demand counted per person, capacity per admission.','Demand uses each person’s first-ever placement; '+
  'capacity counts every admission, because each occupies a bed. Person counts are never summed across years.'),

// ── limits & validation ────────────────────────────────────
H2('Limits and validation'),
dataTable(['Integrity check','Result'],[
  ['Demand record is the person’s first-ever residential admission',{t:'100%',b:true,c:LOCAL}],
  ['Demand population is one row per person',{t:'546 / 546',b:true,c:LOCAL}],
  ['Registry linkage rate',{t:'100%',b:true,c:LOCAL}],
  ['Duplicate person identifiers',{t:'0',b:true,c:LOCAL}],
  ['Residence verdicts on 10+ years of history','86.4%'],
  ['Residence verdicts on under 5 years','5.0%']
],[7580,2500]),
SPACER(100),
RUNS([{t:'Conditioned on placement. ',b:true},{t:'Residents still waiting, who withdrew, or who died before a bed '+
  'opened are not counted. The 317 is local demand that was eventually served — not total local need.'}],{after:80}),
RUNS([{t:'Destination not named. ',b:true},{t:'The analysis records whether a placement was in Cochrane, not which '+
  'community it was in.'}],{after:80}),
RUNS([{t:'Error runs one way. ',b:true},{t:'Residents placed elsewhere are found only through a registry address, '+
  'so coverage gaps can only understate displacement. 69.4% is a floor.'}],{after:120}),
note('Excluded from scope',[
  nP([{t:'Level 3 supportive living (no Cochrane capacity exists) and 50 people already in residential care before '+
      'the window opened — their in-window admission is a later placement, not a first one. They remain in the capacity figures.'}])
]),

// ── footer block ───────────────────────────────────────────
SPACER(160),
P('FY2022–FY2026  ·  Type A and Type B continuing care  ·  Town of Cochrane census subdivision '+
  '(CSDNAME_2021 = COCHRANE, CSDTYPE_2021 = T)',{font:MONO,size:14,color:FAINT,after:50}),
P('Sources: continuing care placement records  ·  Alberta provincial registry  ·  Alberta postal code reference  '+
  '·  rated-site waitlist census',{font:MONO,size:14,color:FAINT,after:50}),
P('All figures reproducible from the documented extraction query. Person-level detail available on request. '+
  'Full analysis in the companion paper.',{font:MONO,size:14,color:FAINT,after:0})
    ]}]});

Packer.toBuffer(doc).then(b=>{fs.writeFileSync(__dirname+'/../reports/Cochrane-Demand-and-Capacity-Summary.docx',b);
  console.log('written '+b.length+' bytes');});

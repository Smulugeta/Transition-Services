const fs=require('fs');
const D=require('docx');
const {Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,Table,TableRow,TableCell,
 WidthType,ShadingType,BorderStyle,Footer,PageNumber,LevelFormat,convertInchesToTwip,
 TabStopType,ExternalHyperlink}=D;

const W=9360;                      // content width (Letter, 1" margins)
const LOCAL='058C72', OUT='C4671A', INK='15201C', MUT='5C6862', RULE='D9DEDA', HEAD='F1F5F3', SOFT='F7F9F8';
const SERIF='Georgia', SANS='Calibri', MONO='Consolas';

const none={style:BorderStyle.NONE,size:0,color:'FFFFFF'};
const noBorders={top:none,bottom:none,left:none,right:none};
const hair=c=>({style:BorderStyle.SINGLE,size:4,color:c||RULE});

// ── text helpers ───────────────────────────────────────────
const P=(text,o={})=>new Paragraph({
  spacing:{after:o.after??140,before:o.before??0,line:o.line??276},
  alignment:o.align,
  border:o.border,
  indent:o.indent,
  children:[new TextRun({text,font:o.font||SANS,size:o.size||22,bold:o.bold,italics:o.italics,
    color:o.color||INK,characterSpacing:o.cs,allCaps:o.caps})]
});
const RUNS=(runs,o={})=>new Paragraph({
  spacing:{after:o.after??140,before:o.before??0,line:276},
  alignment:o.align, border:o.border, indent:o.indent,
  children:runs.map(r=>new TextRun({text:r.t,font:r.f||SANS,size:r.s||22,bold:r.b,italics:r.i,
    color:r.c||INK,characterSpacing:r.cs,allCaps:r.caps}))
});
const H2=(n,t)=>new Paragraph({
  heading:HeadingLevel.HEADING_1,
  spacing:{before:420,after:160},
  border:{bottom:{style:BorderStyle.SINGLE,size:8,color:LOCAL}},
  children:[
    new TextRun({text:n+'   ',font:MONO,size:20,bold:true,color:LOCAL}),
    new TextRun({text:t,font:SERIF,size:30,bold:true,color:INK})
  ]
});
const H3=t=>new Paragraph({heading:HeadingLevel.HEADING_2,spacing:{before:280,after:100},
  children:[new TextRun({text:t,font:SANS,size:23,bold:true,color:INK})]});
const LABEL=t=>new Paragraph({spacing:{before:260,after:90},
  children:[new TextRun({text:t,font:MONO,size:17,bold:true,color:MUT,characterSpacing:24,allCaps:true})]});
const BULLET=t=>new Paragraph({numbering:{reference:'bul',level:0},spacing:{after:90,line:276},
  children:[new TextRun({text:t,font:SANS,size:22,color:INK})]});
const BULLETR=runs=>new Paragraph({numbering:{reference:'bul',level:0},spacing:{after:90,line:276},
  children:runs.map(r=>new TextRun({text:r.t,font:SANS,size:22,bold:r.b,italics:r.i,color:r.c||INK}))});
const SPACER=(h=120)=>new Paragraph({spacing:{after:h},children:[new TextRun({text:'',size:2})]});

// ── table helpers ──────────────────────────────────────────
const cell=(children,{w,shade,span,valign,borders}={})=>new TableCell({
  width:{size:w,type:WidthType.DXA},
  columnSpan:span,
  shading:shade?{type:ShadingType.CLEAR,fill:shade,color:'auto'}:undefined,
  margins:{top:90,bottom:90,left:130,right:130},
  verticalAlign:valign,
  borders:borders||{top:hair(),bottom:hair(),left:hair(),right:hair()},
  children
});
const tcell=(t,{w,shade,bold,align,color,font,size,span}={})=>cell(
  [new Paragraph({alignment:align,spacing:{after:0,line:264},
    children:[new TextRun({text:t,font:font||SANS,size:size||20,bold,color:color||INK})]})],
  {w,shade,span});

function dataTable(headers,rows,widths,opts={}){
  const hdr=new TableRow({tableHeader:true,children:headers.map((h,i)=>
    tcell(h,{w:widths[i],shade:HEAD,bold:true,font:MONO,size:16,
      align:i===0?AlignmentType.LEFT:AlignmentType.RIGHT,color:MUT}))});
  const body=rows.map((r,ri)=>new TableRow({children:r.map((c,i)=>{
    const isTot=opts.totalRow&&ri===rows.length-1;
    const v=typeof c==='object'?c:{t:c};
    return tcell(v.t,{w:widths[i],shade:isTot?HEAD:undefined,bold:isTot||v.b,
      color:v.c, align:i===0?AlignmentType.LEFT:AlignmentType.RIGHT});
  })}));
  return new Table({width:{size:W,type:WidthType.DXA},columnWidths:widths,rows:[hdr,...body]});
}

// proportional two-tone bar rendered as a 1-row table
function bar(segments){
  const total=segments.reduce((s,x)=>s+x.pct,0);
  let widths=segments.map(s=>Math.max(340,Math.round(W*s.pct/total)));
  const diff=W-widths.reduce((a,b)=>a+b,0);
  widths[widths.length-1]+=diff;
  return new Table({width:{size:W,type:WidthType.DXA},columnWidths:widths,
    rows:[new TableRow({children:segments.map((s,i)=>new TableCell({
      width:{size:widths[i],type:WidthType.DXA},
      shading:{type:ShadingType.CLEAR,fill:s.color,color:'auto'},
      margins:{top:70,bottom:70,left:110,right:110},
      borders:{top:none,bottom:none,
        left:i===0?none:{style:BorderStyle.SINGLE,size:4,color:'FFFFFF'},right:none},
      children:[new Paragraph({spacing:{after:0,line:240},
        children:[new TextRun({text:s.label,font:MONO,size:17,bold:true,color:'FFFFFF'})]})]
    }))})]});
}
const barRow=(name,note,total,segs)=>[
  new Paragraph({spacing:{before:200,after:60},tabStops:[{type:TabStopType.RIGHT,position:W}],
    children:[
      new TextRun({text:name,font:SANS,size:21,bold:true,color:INK}),
      ...(note?[new TextRun({text:'   '+note,font:SANS,size:18,color:MUT})]:[]),
      new TextRun({text:'\t'+total,font:MONO,size:17,color:MUT})
    ]}),
  bar(segs)
];

// single-series proportion bar (grey track + teal fill)
function monoBar(pct){
  const fill=Math.max(200,Math.round(W*pct/100)), rest=W-fill;
  const cols=rest>0?[fill,rest]:[W];
  const cells=[new TableCell({width:{size:fill,type:WidthType.DXA},
    shading:{type:ShadingType.CLEAR,fill:LOCAL,color:'auto'},borders:noBorders,
    margins:{top:60,bottom:60,left:0,right:0},
    children:[new Paragraph({spacing:{after:0},children:[new TextRun({text:'',size:14})]})]})];
  if(rest>0) cells.push(new TableCell({width:{size:rest,type:WidthType.DXA},
    shading:{type:ShadingType.CLEAR,fill:'E9EDEA',color:'auto'},borders:noBorders,
    margins:{top:60,bottom:60,left:0,right:0},
    children:[new Paragraph({spacing:{after:0},children:[new TextRun({text:'',size:14})]})]}));
  return new Table({width:{size:W,type:WidthType.DXA},columnWidths:cols,rows:[new TableRow({children:cells})]});
}
const monoRow=(name,detail,pct)=>[
  new Paragraph({spacing:{before:180,after:50},tabStops:[{type:TabStopType.RIGHT,position:W}],
    children:[
      new TextRun({text:name,font:SANS,size:21,bold:true,color:INK}),
      new TextRun({text:'\t'+detail+'   ',font:MONO,size:17,color:MUT}),
      new TextRun({text:pct.toFixed(1)+'%',font:MONO,size:18,bold:true,color:LOCAL})
    ]}),
  monoBar(pct)
];

// callout box
const note=(label,paras,warn)=>new Table({
  width:{size:W,type:WidthType.DXA},columnWidths:[W],
  rows:[new TableRow({children:[new TableCell({
    width:{size:W,type:WidthType.DXA},
    shading:{type:ShadingType.CLEAR,fill:warn?'FBF0E6':'EAF3F0',color:'auto'},
    margins:{top:180,bottom:180,left:200,right:200},
    borders:{top:none,bottom:none,right:none,
      left:{style:BorderStyle.SINGLE,size:18,color:warn?OUT:LOCAL}},
    children:[
      new Paragraph({spacing:{after:90},children:[new TextRun({text:label,font:MONO,size:16,
        bold:true,color:warn?OUT:LOCAL,characterSpacing:26,allCaps:true})]}),
      ...paras
    ]})]})]});
const nP=runs=>new Paragraph({spacing:{after:90,line:276},
  children:runs.map(r=>new TextRun({text:r.t,font:SANS,size:21,bold:r.b,italics:r.i,color:r.c||INK}))});

const figTitle=(t,s)=>[
  new Paragraph({spacing:{before:340,after:30},
    children:[new TextRun({text:t,font:SANS,size:22,bold:true,color:INK})]}),
  new Paragraph({spacing:{after:150},
    children:[new TextRun({text:s,font:SANS,size:19,color:MUT})]})
];
const legend=items=>new Paragraph({spacing:{after:150},
  children:items.flatMap(i=>[
    new TextRun({text:'■ ',font:SANS,size:22,color:i.c}),
    new TextRun({text:i.t+'    ',font:SANS,size:19,color:INK})])});
const capText=t=>new Paragraph({spacing:{before:110,after:220},
  children:[new TextRun({text:t,font:SANS,size:18,color:MUT,italics:false})]});

// ═══════════════════════════════════════════════════════════
const doc=new Document({
  creator:'Continuing Care Planning',
  title:'Where Cochrane Residents Are Placed',
  description:'Five-year analysis of continuing care demand and capacity use, FY2022-26',
  numbering:{config:[{reference:'bul',levels:[{level:0,format:LevelFormat.BULLET,text:'•',
    alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:360,hanging:220}}}}]}]},
  styles:{default:{document:{run:{font:SANS,size:22,color:INK}}}},
  sections:[{
    properties:{page:{size:{width:12240,height:15840},
      margin:{top:1440,bottom:1440,left:1440,right:1440}}},
    footers:{default:new Footer({children:[new Paragraph({
      alignment:AlignmentType.RIGHT,spacing:{before:200},
      border:{top:hair()},
      children:[new TextRun({text:'Where Cochrane Residents Are Placed   ·   ',font:MONO,size:15,color:MUT}),
        new TextRun({children:[PageNumber.CURRENT],font:MONO,size:15,color:MUT})]})]})},
    children:[

// ── masthead ──────────────────────────────────────────────
RUNS([{t:'BETHANY COCHRANE & BIG HILL LODGE CAMPUS OF CARE  ·  EVIDENCE PAPER 01',
  f:MONO,s:16,b:true,c:MUT,cs:24}],{after:200}),
new Paragraph({spacing:{after:180},
  children:[new TextRun({text:'Where Cochrane Residents Are Placed',font:SERIF,size:52,bold:true,color:INK})]}),
new Paragraph({spacing:{after:280},
  children:[new TextRun({text:'Seven in ten Town of Cochrane residents who enter continuing care receive their first placement somewhere else. Meanwhile most beds in Cochrane’s own facilities go to people from outside the town.',
    font:SERIF,size:24,italics:true,color:'3A4844'})]}),

new Table({width:{size:W,type:WidthType.DXA},columnWidths:[1900,1900,1780,1900,1880],
  rows:[
    new TableRow({children:[
      tcell('PERIOD',{w:1900,shade:HEAD,font:MONO,size:15,bold:true,color:MUT}),
      tcell('POPULATION',{w:1900,shade:HEAD,font:MONO,size:15,bold:true,color:MUT}),
      tcell('SCOPE',{w:1780,shade:HEAD,font:MONO,size:15,bold:true,color:MUT}),
      tcell('SOURCES',{w:1900,shade:HEAD,font:MONO,size:15,bold:true,color:MUT}),
      tcell('STATUS',{w:1880,shade:HEAD,font:MONO,size:15,bold:true,color:MUT})]}),
    new TableRow({children:[
      tcell('FY2022 – FY2026',{w:1900,size:19}),
      tcell('317 Town residents',{w:1900,size:19}),
      tcell('Type A & Type B',{w:1780,size:19}),
      tcell('Placement system; AB registry',{w:1900,size:19}),
      tcell('Validated',{w:1880,size:19})]})
  ]}),
SPACER(200),

// ── 01 ────────────────────────────────────────────────────
H2('01','What this measures'),
P('Two questions sit at the centre of the campus-of-care case, and they are not the same question.'),
RUNS([{t:'How much continuing care demand does the Town of Cochrane generate, and how much of it is served locally? ',b:true},
      {t:'That is a question about residents — people whose need for care arose while they lived in Cochrane.'}]),
RUNS([{t:'Who occupies the beds that already exist in Cochrane? ',b:true},
      {t:'That is a question about facilities, and the people filling them may or may not be from the town.'}]),
P('Answering both requires knowing, for every person placed into continuing care, where they actually lived before they needed it. That turns out to be the hard part, and Section 02 explains how it was solved.'),
SPACER(80),

new Table({width:{size:W,type:WidthType.DXA},columnWidths:[2340,2340,2340,2340],
  rows:[new TableRow({children:[
    cell([new Paragraph({spacing:{after:40},children:[new TextRun({text:'317',font:SERIF,size:44,bold:true,color:INK})]}),
          new Paragraph({spacing:{after:0},children:[new TextRun({text:'Town of Cochrane residents entered continuing care',font:SANS,size:18,color:'3A4844'})]}),
          new Paragraph({spacing:{before:40,after:0},children:[new TextRun({text:'FY2022–26, first-ever placement',font:MONO,size:14,color:MUT})]})],{w:2340,shade:SOFT}),
    cell([new Paragraph({spacing:{after:40},children:[new TextRun({text:'69.4%',font:SERIF,size:44,bold:true,color:OUT})]}),
          new Paragraph({spacing:{after:0},children:[new TextRun({text:'were first placed outside Cochrane',font:SANS,size:18,color:'3A4844'})]}),
          new Paragraph({spacing:{before:40,after:0},children:[new TextRun({text:'220 of 317 people',font:MONO,size:14,color:MUT})]})],{w:2340,shade:SOFT}),
    cell([new Paragraph({spacing:{after:40},children:[new TextRun({text:'84.8%',font:SERIF,size:44,bold:true,color:OUT})]}),
          new Paragraph({spacing:{after:0},children:[new TextRun({text:'for long-term care specifically',font:SANS,size:18,color:'3A4844'})]}),
          new Paragraph({spacing:{before:40,after:0},children:[new TextRun({text:'140 of 165 people',font:MONO,size:14,color:MUT})]})],{w:2340,shade:SOFT}),
    cell([new Paragraph({spacing:{after:40},children:[new TextRun({text:'57.3%',font:SERIF,size:44,bold:true,color:INK})]}),
          new Paragraph({spacing:{after:0},children:[new TextRun({text:'of placements into Cochrane facilities went to non-residents',font:SANS,size:18,color:'3A4844'})]}),
          new Paragraph({spacing:{before:40,after:0},children:[new TextRun({text:'197 of 344 admissions',font:MONO,size:14,color:MUT})]})],{w:2340,shade:SOFT})
  ]})]}),
SPACER(160),

// ── 02 ────────────────────────────────────────────────────
H2('02','How residence was determined'),
P('This is the part of the method that will be unfamiliar, and it is where the analysis either holds or fails. It is worth reading before any figure is used.'),
H3('The problem with the obvious approach'),
RUNS([{t:'The placement system records where people were '},{t:'admitted',i:true},
      {t:'. It does not reliably record where they '},{t:'lived',i:true},
      {t:'. Three fields look as though they should answer “was this person from Cochrane,” and none of them do.'}]),
BULLETR([{t:'Source location ',b:true},{t:'is the facility a person arrived from, not their home. Someone who went home → hospital → a Calgary nursing home → Bethany Cochrane appears as arriving from Calgary.'}]),
BULLETR([{t:'Address history ',b:true},{t:'updates to the facility on admission. Within this cohort, 50 address records point at the Bethany Cochrane campus itself. Counting those as Cochrane residents would let the destination facility manufacture its own demand. The same address also appears in 24 different spellings.'}]),
BULLETR([{t:'Postal code ',b:true},{t:'is recorded inconsistently and is frequently stale.'}]),
SPACER(80),

note('The method',[
  nP([{t:'The provincial registry holds one row per person per fiscal year',b:true},
      {t:' — the postal code they lived at that year, going back to the 1990s. It is a longitudinal record of where every Albertan lived, every year.'}]),
  nP([{t:'That allows a question no placement system can answer: '},
      {t:'where did this person live in the years before they entered care?',b:true},
      {t:' Pre-care years cannot contain a facility address, because the person was not yet in a facility. The contamination problem disappears — not by cleaning the data, but by choosing a window in which it cannot occur.'}])
]),
SPACER(200),

LABEL('The four steps'),
RUNS([{t:'1.  Find the moment care began.  ',b:true,c:LOCAL},
  {t:'For each person, locate their first-ever Type A or Type B admission — the point at which they entered residential care. Day programs and hospital transition units are excluded from this test: they are not residential care, and anchoring on them sits a median of 1.6 years, and up to 6.6 years, too early. Applying that restriction changed the anchor for 21% of the cohort.'}],{after:150}),
RUNS([{t:'2.  Look back three fiscal years.  ',b:true,c:LOCAL},
  {t:'Read the registry address for the three years ending the year before care began. The entry year itself is excluded so that a mid-year move into a facility cannot leak in. Three years matches the health authority’s own lookback cap; in practice the window length is immaterial here — two-year and five-year windows return an identical set of people.'}],{after:150}),
RUNS([{t:'3.  Resolve the postal code to a real boundary.  ',b:true,c:LOCAL},
  {t:'Town of Cochrane is the Statistics Canada census subdivision — the legal municipal boundary, 568 postal codes. Two tempting shortcuts were rejected: the reference table’s municipality field labels 22 Rocky View County codes as Cochrane, and the T4C postal prefix splits 562 Town against 41 county addresses.'}],{after:150}),
RUNS([{t:'4.  Fix residence once, per person.  ',b:true,c:LOCAL},
  {t:'A person’s origin does not change because they later moved beds. Residence is determined at entry to care and never recalculated, so a transfer between two Cochrane facilities cannot convert an outside resident into a local one.'}],{after:180}),

H3('Town versus catchment'),
RUNS([{t:'Two boundaries are reported separately. '},{t:'Town of Cochrane',b:true},
  {t:' (568 postal codes) is the municipality. The '},{t:'Cochrane catchment',b:true},
  {t:' (1,177 codes) adds Springbank and rural Rocky View — areas the facilities serve but the town does not govern. The headline uses the Town. The catchment adds a further 86 residents, of whom 81 were also placed outside Cochrane.'}]),

// ── 03 ────────────────────────────────────────────────────
H2('03','Cohort definitions'),
P('Residence and placement destination combine into four groups. Every person and every admission in this analysis falls into exactly one of them.'),
SPACER(60),
new Table({width:{size:W,type:WidthType.DXA},columnWidths:[2160,3600,3600],
  rows:[
    new TableRow({tableHeader:true,children:[
      tcell('',{w:2160,shade:HEAD}),
      tcell('PLACED IN COCHRANE',{w:3600,shade:HEAD,font:MONO,size:16,bold:true,color:MUT,align:AlignmentType.LEFT}),
      tcell('PLACED OUTSIDE COCHRANE',{w:3600,shade:HEAD,font:MONO,size:16,bold:true,color:MUT,align:AlignmentType.LEFT})]}),
    new TableRow({children:[
      tcell('COCHRANE RESIDENT',{w:2160,shade:HEAD,font:MONO,size:16,bold:true,color:MUT}),
      cell([new Paragraph({spacing:{after:60},children:[new TextRun({text:'A',font:MONO,size:32,bold:true,color:LOCAL})]}),
            new Paragraph({spacing:{after:60},children:[new TextRun({text:'Local need met locally. The share of the town’s own demand that Cochrane’s facilities absorbed.',font:SANS,size:19})]}),
            new Paragraph({children:[new TextRun({text:'97 people  ·  30.6% of Town demand',font:MONO,size:15,color:MUT})]})],{w:3600}),
      cell([new Paragraph({spacing:{after:60},children:[new TextRun({text:'C',font:MONO,size:32,bold:true,color:OUT})]}),
            new Paragraph({spacing:{after:60},children:[new TextRun({text:'Local need served elsewhere. Residents who had to leave the town to receive care.',font:SANS,size:19})]}),
            new Paragraph({children:[new TextRun({text:'220 people  ·  69.4% of Town demand',font:MONO,size:15,color:MUT})]})],{w:3600})]}),
    new TableRow({children:[
      tcell('NOT A COCHRANE RESIDENT',{w:2160,shade:HEAD,font:MONO,size:16,bold:true,color:MUT}),
      cell([new Paragraph({spacing:{after:60},children:[new TextRun({text:'B',font:MONO,size:32,bold:true,color:LOCAL})]}),
            new Paragraph({spacing:{after:60},children:[new TextRun({text:'Outside demand on local capacity. People from elsewhere occupying beds in Cochrane.',font:SANS,size:19})]}),
            new Paragraph({children:[new TextRun({text:'189 people  ·  197 admissions',font:MONO,size:15,color:MUT})]})],{w:3600}),
      cell([new Paragraph({spacing:{after:60},children:[new TextRun({text:'—',font:MONO,size:32,bold:true,color:'8B958F'})]}),
            new Paragraph({spacing:{after:60},children:[new TextRun({text:'Out of scope. Bears on neither Cochrane demand nor Cochrane capacity.',font:SANS,size:19,color:MUT})]}),
            new Paragraph({children:[new TextRun({text:'excluded',font:MONO,size:15,color:MUT})]})],{w:3600})]})
  ]}),
SPACER(180),
note('Reading the arithmetic',[
  nP([{t:'A + C',b:true},{t:' is total Town demand.  '},{t:'A + B',b:true},
      {t:' is total use of Cochrane’s capacity.  '},{t:'C ÷ (A + C)',b:true},
      {t:' is the share of local demand that left town.'}]),
  nP([{t:'Demand is counted per '},{t:'person',i:true},
      {t:', on their first-ever placement — did the need get met locally the first time it arose. Capacity use is counted per '},
      {t:'admission',i:true},{t:', because each one occupies a bed. Person counts must never be summed across years; the same individual recurs.'}])
]),

// ── 04 ────────────────────────────────────────────────────
H2('04','Local demand and where it went'),
P('Of 317 Town of Cochrane residents who entered residential continuing care over the five years, 97 were placed in Cochrane and 220 were placed elsewhere. The gap is far wider for long-term care than for supportive living.'),
...figTitle('First placement of Town of Cochrane residents, by care type','People, FY2022–26. First-ever residential placement.'),
legend([{t:'Placed in Cochrane',c:LOCAL},{t:'Placed outside Cochrane',c:OUT}]),
...barRow('Type A — long-term care','Bethany Cochrane is the only local Type A site','165 people',
  [{pct:15.2,color:LOCAL,label:'25'},{pct:84.8,color:OUT,label:'140  ·  84.8% placed outside Cochrane'}]),
...barRow('Type B — supportive living','Hawthorne provides local Type B capacity','152 people',
  [{pct:47.4,color:LOCAL,label:'72  ·  47.4%'},{pct:52.6,color:OUT,label:'80  ·  52.6%'}]),
...barRow('All care types','','317 people',
  [{pct:30.6,color:LOCAL,label:'97  ·  30.6%'},{pct:69.4,color:OUT,label:'220  ·  69.4%'}]),
capText('Where local capacity exists at the right care level, roughly half of local demand is met locally. Where it does not, almost none is. Bethany Cochrane absorbed 25 of 165 Town residents needing long-term care.'),

...figTitle('Share of Town residents placed outside Cochrane, by fiscal year','Fiscal years ending 31 March.'),
legend([{t:'Placed in Cochrane',c:LOCAL},{t:'Placed outside Cochrane',c:OUT}]),
...barRow('FY 2022','','55 people',[{pct:34.5,color:LOCAL,label:'19'},{pct:65.5,color:OUT,label:'36  ·  65.5%'}]),
...barRow('FY 2023','','56 people',[{pct:35.7,color:LOCAL,label:'20'},{pct:64.3,color:OUT,label:'36  ·  64.3%'}]),
...barRow('FY 2024','','70 people',[{pct:32.9,color:LOCAL,label:'23'},{pct:67.1,color:OUT,label:'47  ·  67.1%'}]),
...barRow('FY 2025','','68 people',[{pct:22.1,color:LOCAL,label:'15'},{pct:77.9,color:OUT,label:'53  ·  77.9%'}]),
...barRow('FY 2026','','68 people',[{pct:29.4,color:LOCAL,label:'20'},{pct:70.6,color:OUT,label:'48  ·  70.6%'}]),
capText('Between 64% and 78% every year. FY2025 is the weakest year but sits alone; the honest description is a persistent two-thirds to three-quarters, not a deteriorating trend. Annual volume rose from 55 to 68.'),

// ── 05 ────────────────────────────────────────────────────
H2('05','Who occupies Cochrane’s beds'),
P('The same five years produced 344 admissions into Cochrane’s Type A and Type B facilities. Fewer than half went to people who were Cochrane-area residents when they entered care.'),
...figTitle('Admissions into Cochrane facilities, by residence at entry to care','344 admissions, FY2022–26.'),
legend([{t:'Cochrane-area resident',c:LOCAL},{t:'Non-resident',c:OUT}]),
...barRow('All Cochrane placements','','344 admissions',
  [{pct:42.4,color:LOCAL,label:'146  ·  42.4%'},{pct:57.6,color:OUT,label:'198  ·  57.6% non-resident or unresolved'}]),
...barRow('Type A — Bethany Cochrane','','133 admissions',
  [{pct:45.9,color:LOCAL,label:'61  ·  45.9%'},{pct:54.1,color:OUT,label:'72  ·  54.1%'}]),
...barRow('Type B — Hawthorne','','211 admissions',
  [{pct:40.3,color:LOCAL,label:'85  ·  40.3%'},{pct:59.7,color:OUT,label:'126  ·  59.7%'}]),
capText('Cochrane-area combines Town residents (140 admissions) and catchment residents from Springbank and rural Rocky View (6). One admission has unresolved residence. Counted as people rather than admissions: 133 Town, 6 catchment, 189 non-resident.'),
SPACER(120),
new Paragraph({spacing:{before:200,after:220},
  border:{top:{style:BorderStyle.SINGLE,size:12,color:INK},bottom:hair()},
  children:[new TextRun({text:' ',size:8})]}),
new Paragraph({spacing:{after:200},
  children:[new TextRun({text:'Two-thirds of the town’s residents are placed elsewhere, while nearly three-fifths of the town’s beds are filled by people from elsewhere. Both are true at once, and each strengthens the other.',
    font:SERIF,size:26,color:INK})]}),

// ── 06 ────────────────────────────────────────────────────
H2('06','The hospital pathway'),
P('Grouping Town residents by the setting they entered care from reveals the mechanism behind the headline. Access to a local bed depends heavily on whether the placement was urgent.'),
...figTitle('Share of Town residents placed in Cochrane, by setting they entered care from','317 people. Bar length shows the proportion who received a Cochrane placement.'),
...monoRow('Own home / community','93 people · 52 in Cochrane',55.9),
...monoRow('Lodge','24 people · 13 in Cochrane',54.2),
...monoRow('Other / unclear','22 people · 5 in Cochrane',22.7),
...monoRow('Acute hospital','149 people · 25 in Cochrane',16.8),
...monoRow('Transition / rehab','12 people · 1 in Cochrane',8.3),
...monoRow('Supportive living','17 people · 1 in Cochrane',5.9),
capText('Acute hospital is the single largest entry point into care for Town residents — 149 of 317, or 47% — and the one least likely to end in a local placement.'),
RUNS([{t:'A resident entering care '},{t:'from the community has roughly a coin-flip chance',b:true},
  {t:' of a Cochrane bed. A resident entering '},{t:'from an acute hospital bed has about one in six',b:true},{t:'.'}]),
P('That reframes the problem. It is not only a question of how many beds exist, but of whether the town has any capacity able to absorb an urgent hospital discharge. When an acute bed must be freed, the person goes wherever a bed is open — and that is overwhelmingly not Cochrane.'),

// ── 07 ────────────────────────────────────────────────────
H2('07','Time to placement'),
P('Wait times are measured from assessment and approval to admission, for first-ever placements only. Transfers between facilities run on a separate clock and are excluded here; blending the two produces a figure that describes neither.'),
LABEL('Days from approval to admission — first placements'),
dataTable(['Group','People','Median','90th percentile'],[
  ['Town resident → placed in Cochrane','97',{t:'32',b:true,c:LOCAL},'335'],
  ['Town resident → placed outside Cochrane','220',{t:'18',b:true,c:OUT},'190'],
  ['Non-resident → placed in Cochrane','140','30','327']
],[4560,1600,1600,1600]),
SPACER(180),
note('Read this the right way round',[
  nP([{t:'Residents placed '},{t:'outside',i:true},{t:' Cochrane waited '},{t:'less',b:true},
    {t:' — 18 days against 32. That is not evidence of better service. It is the signature of accepting the first available bed rather than holding out for a local one, and the 90th percentile shows the cost of holding out: 335 days against 190.'}])
],true),
H3('Was the placement what the resident asked for?'),
P('Not answerable from the placement records alone. The admission file carries a service_provider_rating field that appears to rank the site received, and an earlier draft of this paper reported it as a preference measure. Testing it against the waitlist system showed it does not mean that.'),
RUNS([{t:'Of 344 admissions into Cochrane facilities, '},{t:'285 were to a site the person had never listed as a preference',b:true},
  {t:' — yet 187 of those carry a rating of 1. One client waited 894 days on the waitlist for Bethany Airdrie, was placed at Bethany Cochrane instead, and the admission record scores that placement as a 1.'}]),
SPACER(120),
note('Withdrawn from this paper',[
  nP([{t:'The preference-rank breakdown that appeared here has been removed. The field it rested on does not carry the meaning assumed, and no claim about what residents preferred is made anywhere in this paper.'}]),
  nP([{t:'The waitlist system does hold real recorded preferences, and that analysis is underway. It is reported separately once validated — not folded into figures that do not depend on it.'}])
],true),
SPACER(160),
P('Everything else in this section stands. Wait times are computed from approval and admission dates, which are unaffected.'),

// ── 08 ────────────────────────────────────────────────────
H2('08','What this does not measure'),
P('Three limitations are material to how these figures should be used.'),
LABEL('People who never received a bed'),
RUNS([{t:'Everything here is conditioned on placement. Residents still waiting, who withdrew, or who died before a bed became available are not in these counts. Measuring them requires the full waitlist source, which is not yet in hand. '},
  {t:'The 317 is therefore local demand that was eventually served — not total local need.',b:true}]),
LABEL('Whether displaced residents wanted a Cochrane bed'),
RUNS([{t:'138 of the 220 residents placed outside Cochrane had formally requested a Cochrane site and were on that waitlist at or before the moment they were placed elsewhere',b:true},{t:' — median 70 days waiting, longest 1,358. None joined the list afterwards, so this is displacement rather than hindsight. Because the waitlist record begins 1 April 2021, 138 is a floor.'}]),
P('What cannot be said is how many of the remaining 82 also wanted a local bed. Their preferences are not recorded in the source available.'),
LABEL('Where they were placed instead'),
P('The analysis records whether a placement was in Cochrane, not which community it was in. Naming destinations requires the facility reference table from the health authority.'),
SPACER(120),
note('Direction of error',[
  nP([{t:'Cohort C — residents placed elsewhere — is identified only through a registry address. Gaps in registry coverage can therefore only '},
    {t:'understate',b:true},{t:' displacement, never inflate it. The 69.4% is a floor.'}])
]),

// ── 09 ────────────────────────────────────────────────────
H2('09','Validation'),
P('Every figure in this paper is reproducible from a single query and a client-level extract, both of which have been checked independently.'),
LABEL('Integrity checks'),
dataTable(['Check','Required','Result'],[
  ['Every demand record is that person’s first-ever residential admission','100%',{t:'100%',b:true,c:LOCAL}],
  ['Demand population is one row per person','equal',{t:'546 / 546',b:true,c:LOCAL}],
  ['Registry linkage rate','high',{t:'100%',b:true,c:LOCAL}],
  ['Duplicate person identifiers','none',{t:'0',b:true,c:LOCAL}],
  ['Admissions with no computable wait clock','none',{t:'0',b:true,c:LOCAL}],
  ['Residence verdicts on 10+ years of registry history','majority','86.4%'],
  ['Residence verdicts on under 5 years of history','minority','5.0%'],
  ['Total in scope','—','636 people · 776 admissions']
],[5560,1700,2100],{totalRow:true}),
SPACER(160),
P('A further 50 people were excluded from the demand figures because they had already entered residential care before the window opened; their in-window admission is a later placement, not a first one. They remain in the capacity figures, because they still occupy a bed.'),

// ── 10 ────────────────────────────────────────────────────
H2('10','What would strengthen this'),
P('Two additions would materially improve the case, in this order.'),
LABEL('A population denominator'),
RUNS([{t:'The registry can supply the number of Cochrane residents aged 75 and over in each year. That converts 63 placements a year into a '},
  {t:'rate',b:true},{t:' — admissions per 1,000 seniors — which can be benchmarked against comparable Alberta communities and projected forward against Cochrane’s growth. For a capital decision this is the single most useful number not yet in hand, and it requires no external request.'}]),
LABEL('The waitlist source'),
P('Waitlist entry, exit and closure reason would add the fourth cohort — residents who never received a placement. The preference records behind the 138 displaced residents in Section 08 begin only on 1 April 2021; the full history would turn that floor into a count.'),

SPACER(300),
new Paragraph({spacing:{before:240,after:60},border:{top:hair()},children:[new TextRun({text:' ',size:8})]}),
P('Analysis period FY2022–FY2026  ·  Type A and Type B continuing care  ·  Town of Cochrane census subdivision',{font:MONO,size:15,color:MUT,after:40}),
P('Sources: continuing care placement records; Alberta provincial registry; Alberta postal code reference',{font:MONO,size:15,color:MUT,after:40}),
P('Person-level detail available on request. All figures reproducible from the documented extraction query.',{font:MONO,size:15,color:MUT})

]}]});

Packer.toBuffer(doc).then(b=>{fs.writeFileSync(__dirname+'/../reports/Where-Cochrane-Residents-Are-Placed.docx',b);
  console.log('written',b.length,'bytes');});

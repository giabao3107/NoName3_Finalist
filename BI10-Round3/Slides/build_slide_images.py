"""Render each Round 3 slide as a 1920x1080 PNG (HTML template in the Round 2 deck style, captured with headless Chrome).
Content follows ROUND 03/SLIDE_SCRIPT_AND_PROMPT.md; every number comes from the analysis outputs on branch Lu."""
from __future__ import annotations

import html
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
HTML_DIR=HERE/"html"
PNG_DIR=HERE/"png"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
R2=ROOT/"output"/"R2_Customer_Foundation"
R3=ROOT/"output"/"Customer_to_Shop_Growth"
T1=ROOT/"output"/"Shop_Performance_and_BAU"
EDA=ROOT/"output"/"EDA"
NAV=["Overview & Data","R2 Foundation","Shop Performance & BAU","Growth Potential","Prioritisation & Actions"]

CSS="""
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{--blue:#004AAD;--navy:#14213D;--light:#EEF3FA;--mid:#8FAAD1;--grey:#6B7280;--line:#D5DCE6;--red:#C51E1E;--amber:#C98A1B}
html,body{width:1920px;height:1080px;overflow:hidden;background:#fff;font-family:Inter,Helvetica,Arial,sans-serif;color:#1F2937}
.slide{position:relative;width:1920px;height:1080px;padding:44px 64px 0 64px}
.hdr{position:relative;padding-left:26px;border-left:9px solid var(--blue);margin-bottom:22px}
.eyebrow{font-family:Oswald,'Arial Narrow',sans-serif;font-weight:700;color:var(--blue);font-size:32px;letter-spacing:.5px;text-transform:uppercase;line-height:1.05}
.title{font-weight:800;color:var(--navy);font-size:42px;line-height:1.15;margin-top:4px}
.sub{font-style:italic;color:var(--grey);font-size:21px;margin-top:6px}
.pageno{position:absolute;top:40px;right:64px;font-family:Oswald,sans-serif;font-size:34px;color:#B8C2D0;font-weight:600}
.body{position:absolute;top:212px;left:64px;right:64px;bottom:108px;display:flex;gap:30px}
.stack{flex-direction:column;gap:18px}
.row{display:flex;gap:26px;min-height:0}
.col{display:flex;flex-direction:column;gap:20px;min-width:0}
.foot{position:absolute;left:30px;right:30px;bottom:0;height:86px;border-top:2px solid var(--line);display:flex;justify-content:space-around;align-items:center}
.foot div{font-weight:700;font-size:20px;color:#111827;position:relative;padding:6px 10px}
.foot div.on{color:var(--blue)}
.foot div.on:before{content:'';position:absolute;left:10%;right:10%;top:-22px;height:7px;border-radius:4px;background:var(--blue)}
.fig{border:2px dashed #C9D3E0;border-radius:10px;padding:14px 16px 10px;display:flex;flex-direction:column;min-height:0}
.fig .cap{font-weight:700;font-style:italic;font-size:19px;color:var(--navy);text-align:center;margin-bottom:8px}
.fig img{width:100%;flex:1;min-height:0;object-fit:contain}
.fig .src{font-style:italic;font-size:14px;color:var(--grey);text-align:right;margin-top:6px}
.box{border:2px solid var(--blue);border-radius:10px;overflow:hidden}
.box .bh{background:var(--blue);color:#fff;font-weight:700;font-size:22px;padding:8px 16px;text-align:center}
.box .bb{padding:14px 18px;font-size:20px;line-height:1.42}
.guard{border:2.5px dashed var(--red);border-radius:10px;background:#FFF7F7;padding:14px 18px;font-size:19px;line-height:1.4}
.guard b.t{color:var(--red);display:block;margin-bottom:4px;font-size:20px}
.kpis{display:flex;gap:16px}
.kpi{flex:1;border:2px solid #9DB4D6;border-radius:10px;padding:12px 16px;background:#fff}
.kpi .n{font-weight:800;color:var(--blue);font-size:44px;line-height:1.05}
.kpi .c{font-size:17px;color:#374151;margin-top:6px;line-height:1.3}
.kpi.risk{border-color:var(--red)} .kpi.risk .n{color:var(--red)}
.kpi.amber .n{color:var(--amber)} .kpi.amber{border-color:var(--amber)}
table{border-collapse:collapse;width:100%;font-size:18.5px}
th{background:var(--blue);color:#fff;text-align:left;padding:9px 12px;font-weight:700}
td{padding:8px 12px;border-bottom:1px solid #E5EAF1;vertical-align:top;line-height:1.3}
tr:nth-child(even) td{background:#F4F7FB}
.tcap{font-weight:700;color:var(--blue);font-size:21px;margin-bottom:8px}
ul{padding-left:24px} li{margin:4px 0}
.small{font-size:16px;color:var(--grey);font-style:italic}
.tag{display:inline-block;font-size:15px;font-weight:700;padding:2px 10px;border-radius:12px;color:#fff;background:var(--blue)}
.tag.bold{background:var(--navy)} .tag.g{background:var(--red)}
.chain{display:flex;gap:18px;align-items:stretch}
.step{flex:1;border:2px solid var(--blue);border-radius:12px;background:var(--light);padding:18px;position:relative}
.step .k{font-family:Oswald,sans-serif;font-size:40px;color:var(--blue);font-weight:700}
.step .q{font-weight:800;color:var(--navy);font-size:28px;margin:6px 0 12px;line-height:1.2}
.step .a{font-size:22px;line-height:1.45}
.step .k{font-size:56px !important}
.step:not(:last-child):after{content:'\\2192';position:absolute;right:-17px;top:42%;font-size:30px;color:var(--blue);font-weight:800}
.def{border-left:7px solid var(--blue);background:var(--light);border-radius:8px;padding:12px 16px;font-size:19px;line-height:1.38}
.def b{color:var(--navy);font-size:21px}
.tl{display:flex;gap:14px}
.tl .ph{flex:1;border-radius:10px;padding:18px 18px;color:#fff;font-size:21px;line-height:1.42;min-height:190px}
.tl .ph b{display:block;font-family:Oswald,sans-serif;font-size:26px;letter-spacing:.3px;margin-bottom:4px}
.scqa{display:grid;grid-template-columns:62px 1fr;gap:10px 14px;align-items:start}
.scqa .L{font-family:Oswald,sans-serif;font-weight:700;font-size:44px;color:#fff;background:var(--blue);border-radius:8px;text-align:center;line-height:62px;height:62px}
.scqa .T{font-size:20px;line-height:1.4;padding-top:4px}
.scqa .T b.h{color:var(--blue);display:block;font-size:19px;letter-spacing:.4px}
.bottomline{background:var(--navy);color:#fff;border-radius:10px;padding:16px 22px;font-size:24px;font-weight:700;text-align:center}
"""


def esc(t:str)->str:return html.escape(t,quote=False)


def page(n:int,section:int|None,eyebrow:str,title:str,sub:str,body:str)->str:
    foot="".join(f'<div class="{"on" if i==section else ""}">{esc(s)}</div>' for i,s in enumerate(NAV)) if section is not None else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="slide">
<div class="pageno">{n:02d}</div><div class="hdr"><div class="eyebrow">{esc(eyebrow)}</div><div class="title">{title}</div><div class="sub">{sub}</div></div>
<div class="body">{body}</div>{'<div class="foot">'+foot+'</div>' if foot else ''}</div></body></html>"""


def fig(path:Path,cap:str,src:str="Source: Round 3 contracts, leads and staff assignments (Jan 2025–Sep 2026); Round 2 scores; team analysis.",style:str="")->str:
    return f'<div class="fig" style="{style}"><div class="cap">{cap}</div><img src="{path.as_uri()}"><div class="src">{src}</div></div>'


def box(head:str,body:str,style:str="")->str:return f'<div class="box" style="{style}"><div class="bh">{head}</div><div class="bb">{body}</div></div>'


def table(head:list[str],rows:list[list[str]],widths:list[str]|None=None,style:str="")->str:
    cols="".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    return f'<table style="{style}"><colgroup>{cols}</colgroup><tr>{"".join(f"<th>{h}</th>" for h in head)}</tr>'+"".join("<tr>"+"".join(f"<td>{c}</td>" for c in r)+"</tr>" for r in rows)+"</table>"


def stack(top:str,bottom:str)->str:
    return f'<div class="col" style="flex:1;gap:18px">{top}<div class="row" style="flex:1">{bottom}</div></div>'


def kpis(items:list[tuple[str,str,str]])->str:
    return '<div class="kpis">'+"".join(f'<div class="kpi {k}"><div class="n">{n}</div><div class="c">{c}</div></div>' for n,c,k in items)+"</div>"


# ---------------------------------------------------------------------------------------------------
def cover()->str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}
.cv{{width:1920px;height:1080px;position:relative;overflow:hidden;background:radial-gradient(ellipse at 72% 62%,#1d4fd8 0%,#0b2a7a 28%,#06143d 60%,#030a22 100%)}}
.ring{{position:absolute;border-radius:50%;border:3px solid rgba(120,170,255,.35)}}
.streak{{position:absolute;height:3px;background:linear-gradient(90deg,transparent,rgba(255,80,110,.9),transparent);transform:rotate(-18deg)}}
.bi{{position:absolute;top:150px;left:0;right:0;text-align:center;font-family:Oswald,sans-serif;font-weight:700;font-size:118px;letter-spacing:6px;color:#E8EEFF;text-shadow:0 0 28px rgba(110,160,255,.8)}}
.s10{{position:absolute;top:300px;left:0;right:0;text-align:center;font-family:Oswald,sans-serif;font-weight:600;font-size:64px;letter-spacing:10px;color:#C9D6FF}}
.r3{{position:absolute;left:120px;top:630px;font-family:Oswald,sans-serif;font-weight:700;font-size:110px;color:#fff;letter-spacing:2px}}
.q{{position:absolute;left:124px;top:780px;font-weight:700;font-size:40px;color:#DCE6FF}}
.team{{position:absolute;left:124px;top:868px;font-family:Oswald,sans-serif;font-weight:600;font-size:46px;color:#AFC4F0;letter-spacing:2px}}
.canva{{position:absolute;right:60px;bottom:40px;font-size:24px;color:#E5ECFF;font-weight:600;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.35);border-radius:22px;padding:8px 20px}}
</style></head><body><div class="cv">
<div class="ring" style="width:900px;height:900px;left:1080px;top:380px"></div><div class="ring" style="width:600px;height:600px;left:1230px;top:530px"></div>
<div class="ring" style="width:300px;height:300px;left:1380px;top:680px;border-color:rgba(255,90,120,.6)"></div>
<div class="streak" style="width:900px;left:900px;top:420px"></div><div class="streak" style="width:700px;left:-100px;top:560px;opacity:.6"></div>
<div class="bi">BUSINESS INTELLIGENCE</div><div class="s10">— SEASON 10 —</div>
<div class="r3">ROUND 3 : PARALLAX</div><div class="q">How big can this shop become?</div><div class="team">TEAM: SHOOTING STAR</div>
<div class="canva">Visual supported by Canva</div></div></body></html>"""


def slides()->list[tuple[str,str]]:
    s=[("01_Cover",cover())]

    exec_body=f"""<div class="col" style="flex:1.05;justify-content:space-between">
<div class="scqa">
<div class="L">S</div><div class="T"><b class="h">SITUATION</b>Sales Management ranks shops by the contracts recorded at each shop: 410K funded contracts across 32.5K shop IDs in Jul–Sep 2026.</div>
<div class="L">C</div><div class="T"><b class="h">COMPLICATION</b>That number misleads: same-sales shops hold very different unconverted pipelines; <b>one central ID records 28%</b> of contracts, including cards sold inside shops; our own Round 2 Tết campaign targets customers who do not come back.</div>
<div class="L">Q</div><div class="T"><b class="h">KEY QUESTION</b>Which shops can realistically grow, what limits them, and where should limited resources go first?</div>
<div class="L">A</div><div class="T"><b class="h">ANSWER</b>Benchmark each shop's pipeline against same-product peers, then <b>test fixes in 20 shops</b> before scaling.</div>
</div>
{kpis([("+5.5K","contracts / quarter above BAU in 2,051 assessed shops (+1.6K recorded elsewhere)",""),("51%","of that headroom sits in 268 shops whose leads convert below peers",""),("28%","of all contracts recorded under one central ID",""),("2.1% vs 4.3%","R2 Tết target vs all others applying before Tết 2026","risk")])}
</div><div class="col" style="flex:.95;justify-content:space-between">{box("What we recommend",table(["#","Decision","Size / quarter"],[
["1","Lead follow-up pilot in 20 execution-gap shops, with control shops","+0.6K / 1.0K / 1.5K"],
["2","Fix shop credit: cards to the seller's shop; split cash-loan credit","Corrects rankings"],
["3","Reallocate agent <i>time</i>, not headcount","Pilot, 1 region"],
["4","Cancel the R2 Tết reminder (392K customers); fund GROW","Saves 392K contacts"],
["5","No volume push in 25 high-risk-customer shops","Holds back +0.2K"]],["6%","66%","28%"],"font-size:21px"),"")}
<div class="bottomline">Measure the pipeline a shop has not converted, not the sales it has recorded.</div></div>"""
    s.append(("02_Executive_Summary",page(2,None,"Executive summary","Current sales hides where growth is: the unconverted pipeline",
        "32.5K shop IDs · 410K funded contracts (Jul–Sep 2026) · 2,051 physical shops benchmarked · no causal claim without a pilot",exec_body)))

    steps=[("1","Who are the customers?","Round 2 scores (FHS, CES) re-validated on Round 3 contracts","34% vs 8–13%","GROW re-applies vs other groups","Slides 4–5"),
           ("2","Where is volume recorded?","Shop vs central IDs; why card and cash-loan leads are booked elsewhere","28%","of contracts under one central ID","Slide 6"),
           ("3","How much can a shop grow?","Current → BAU → Attainable → Internal ceiling, one unit","+5.5K","contracts / quarter above BAU","Slides 7–8"),
           ("4","What limits it?","Execution · demand · capacity · customer quality","51%","of headroom is execution","Slides 9–10"),
           ("5","Where first?","Ranked pilot list, robustness, 5 decisions, roadmap","20 shops","+0.6–1.5K / quarter to test","Slides 11–13")]
    chain='<div class="chain" style="flex:1">'+"".join(f'<div class="step" style="display:flex;flex-direction:column"><div class="k">{k}</div><div class="q">{q}</div><div class="a">{a}</div><div style="margin-top:auto;border-top:2px solid #C9D6EA;padding-top:12px"><div style="font-weight:800;color:#004AAD;font-size:40px;line-height:1.1">{n}</div><div style="font-size:19px;color:#374151;margin-top:4px">{c}</div><div style="font-size:16px;color:#6B7280;font-style:italic;margin-top:8px">{ref}</div></div></div>' for k,q,a,n,c,ref in steps)+"</div>"
    story=f"""<div class="col" style="flex:1;gap:26px">{chain}
<div style="display:flex;gap:24px">{box("Rules we keep everywhere",'<ul><li><b>Unit:</b> funded contracts per quarter, recorded at the shop</li><li><b>Fair benchmark:</b> same category × model, same product</li><li><b>Validation:</b> hold-out half of customers; peer p50 / p75 / p90 ranges</li></ul>',"flex:1")}
{box("Glossary",'<b>BAU</b> business-as-usual forecast · <b>FHS</b> Financial Health Score · <b>CES</b> Customer Engagement Score · <b>CC</b> credit card · <b>CL</b> cash loan · <b>CD</b> consumer durables (point of sale) · <b>TW</b> two-wheeler loan · <b>FTE</b> full-time equivalent · <b>p75</b> 75th percentile of peers',"flex:1.15")}</div></div>"""
    s.append(("03_Storyline",page(3,0,"Our approach","From customers to shops: one chain, five questions",
        "Round 3 is a continuation of Round 2: customer understanding becomes the lens for shop growth",story)))

    r2fix=stack(fig(R2/"R2_04_Group_Out_of_Time_Validation.png","Figure 1 · R2 action groups on the hold-out half: applied again (left), applied before Tết 2026 (middle), late on a new loan (right)","Source: Round 2 scores (snapshot 5 Jun 2025); Round 3 contracts to Sep 2026; hold-out half n≈500K.","height:430px"),
  f"""<div class="col" style="flex:1.35">{table(["Round 2 feedback","Our fix","Result"],[
["CES weights not justified","8 weightings compared on a hold-out half","AUC 0.718–0.733: ranking is robust; recency dropped (redundant with frequency)"],
["Cut-offs look arbitrary","Outcome-anchored, same rule as FHS","High ≥ 1.5× avg re-application (score ≥ 44); Low ≤ 2/3 (&lt; 17)"],
["FHS weights not justified","Out-of-time check on Round 3 late payments","R2 weights beat equal weights (Gini 0.084 vs 0.078)"],
["No outcome validation","Hold-out test on Round 3 contracts after 5 Jun 2025","GROW re-applied 34.0% vs 8–13%"]],["22%","32%","46%"],"font-size:17.5px")}</div>
<div class="col" style="flex:.65">{box("Insight","<b>The groups predict real behaviour.</b> GROW customers re-borrow 3–4× more often and PROTECT customers are late most often, so the customer lens is safe to carry into the shop analysis.")}</div>""")
    s.append(("04_R2_Scores_Fixed",page(4,1,"R2 foundation","Round 2 scores hold out of time, after fixing what the judges flagged",
        "Weights and cut-offs fit on a random half of 1,000,528 customers; every result shown is on the other half",r2fix)))

    tet=stack(fig(R2/"R2_06_Network_Monthly_No_Tet_Peak.png","Figure 2 · Monthly applications in the Round 3 network (amber = pre-Tết months)","Source: Round 3 contracts, Jan 2025–Sep 2026.","height:470px"),
  f"""<div class="col" style="flex:1.25">{kpis([("2.1%","of the 392K R2 Tết target applied before Tết 2026 (1 Jan–16 Feb)","risk"),("4.3%","of all other customers did, and 6.2% of GROW",""),("No peak","Jan-26 180K and Feb-26 150K vs 165–197K in other months","amber")])}</div>
<div class="col" style="flex:.75">{box("Insight","<b>The Tết wave was the sample, not the season.</b> The Round 2 file was drawn from Dec-2024/Jan-2025 applicants. We drop the campaign and move budget to GROW.")}</div>""")
    s.append(("05_R2_Self_Correction",page(5,1,"R2 foundation","We tested our own Round 2 campaign on Round 3 data, and dropped it",
        "Round 2 proposed one December reminder for 392,164 one-time Tết borrowers",tet)))

    found=stack(fig(R3/"R3_01_Credit_Leakage.png","Figure 3 · Where funded contracts are recorded (left) and physical-shop leads funded under another ID (right)","Source: Round 3 contracts and lead–contract matches, Jul–Sep 2026.","height:400px"),
  f"""<div class="col" style="flex:1.05"><div class="tcap">Table 2 · Why 90% of card and cash-loan leads are recorded elsewhere</div>{table(["Product","By origin-shop staff","Within 24 h","Reading"],[
["Card (CC)","89–94%","88–91%","Sold in the shop, booked under central ID 42902170"],
["Cash loan (CL)","14% (central IDs)","20–30%","Real hand-off; median 10–12 days later"]],["17%","21%","16%","46%"])}
<div class="guard" style="font-size:17px"><b class="t">Data trust</b>IDs outside the shop master record 72% of funded contracts · lead <i>sample_weight</i> is undocumented → raw counts only · Round 3 holds ~32% of Round 2 customers' overlapping contracts</div></div>
<div class="col" style="flex:.95">{box("Insight","<b>Ranking by recorded sales understates shops that sell cards.</b> ID 42902170 books only CL, CC and CW, is used by ~3,900 employees and holds 73% of all funded cards. 9 in 10 of the cards it records from shop leads were processed by that shop's own staff the same day.")}</div>""")
    s.append(("06_Where_Volume_Is_Recorded",page(6,0,"Overview & data","One central ID records 28% of contracts, including cards sold in shops",
        "Round 3: 3.78M contracts · 6.13M lead rows · 32.5K shop IDs (14.2K in the shop master) · window Jul–Sep 2026",found)))

    defs=[("Current actual","Funded contracts recorded at the shop, Jul–Sep 2026."),
          ("Business-as-usual (BAU)","Task 1 trailing baseline, chosen over a trend model by rolling-origin backtest."),
          ("Attainable (p50 / p75 / p90)","BAU + each product's leads converted at the same-product peer rate + GROW customers reactivated at the peer rate."),
          ("Internal ceiling","BAU + every lead at the peer p90 rate + every GROW customer. An internal proxy, <b>not</b> market size.")]
    method=f"""<div class="col" style="flex:.95">{''.join(f'<div class="def"><b>{a}</b><br>{b}</div>' for a,b in defs)}
<div class="guard"><b class="t">Why product-fair</b>A cash-loan campaign lead converts at ~2%, a point-of-sale (CD) lead at ~40%. Raw conversion would punish shops with many campaign leads.</div></div>
<div class="col" style="flex:1.05">{fig(R3/"R3_07_Network_Four_Concepts.png","Figure 4 · The four growth numbers for the 2,051 assessed shops (attainable: p75 bar, p50–p90 whisker)","Source: Round 3 shop-month panel, lead pipeline and Task 1 BAU; team analysis.","flex:1")}</div>"""
    s.append(("07_Method_Four_Concepts",page(7,2,"Shop performance & BAU","Four growth numbers, one unit, product-fair benchmarks",
        "Unit: funded contracts recorded at the shop over 3 months · peers: same category × model, ≥ 30 shops with ≥ 15 contracts",method)))

    pair=stack(fig(R3/"R3_03_Pair_Four_Concepts.png","Figure 5 · Monthly funded contracts (left) and the four growth numbers (right)","Source: Round 3 shop-month panel and lead pipeline, Jan 2025–Sep 2026.","height:500px"),
  f"""<div class="col" style="flex:1.3">{table(["","Shop A · 101125364 · Đồng Nai","Shop B · 104947973 · Đồng Tháp"],[
["Funded, 3 months · leads, 3 months","<b>74</b> · 661 leads","<b>77</b> · 50 leads"],
["Conversion vs same-product peers","<b style='color:#C51E1E'>0.64×</b>","1.22×"],["Attainable (p50–p90) · internal ceiling","<b>102–137</b> · 203","78–100 · 104"],
["Diagnosis","Execution gap","Near its practical limit"]],["34%","33%","33%"],"font-size:18px")}</div>
<div class="col" style="flex:.7">{box("Insight","<b>Look at the pipeline, not the till.</b> A has 13× B's leads and converts them at half B's rate; 55% of A's pipeline is also recorded under other IDs.")}</div>""")
    s.append(("08_Two_Shop_Question",page(8,3,"The two-shop question","Same sales today, very different room to grow",
        "Two \"Medium, Non-Aldi\" shops with 74 and 77 funded contracts in Jul–Sep 2026",pair)))

    cons=stack(fig(R3/"R3_04_Constraint_Map.png","Figure 6 · Shops (left) and headroom above BAU (right) by primary constraint","Source: Round 3 shop panel, product-level lead conversion, R2 customer mix; team analysis.","height:390px"),
  f"""<div class="col" style="flex:1.3">{table(["Primary constraint","Shops","Headroom / qtr"],[
["<b>Execution:</b> leads convert &lt; 0.8× same-product peers on above-median volume","268","<b>+2.8K</b>"],
["No single clear gap","753","+2.1K"],["Untapped base (warm GROW customers) · Demand (thin pipeline)","510 · 495","+0.2K · +0.1K"],
["<span style='color:#C51E1E'><b>Quality:</b> ≥ 2× median PROTECT share</span>","25","+0.2K (held back)"]],["64%","14%","22%"],"font-size:17.5px")}</div>
<div class="col" style="flex:.7">{box("Insight","<b>Fix conversion before buying demand.</b> Reactivating GROW customers is worth about +1.2K in total; the larger lever is the pipeline shops already have.")}</div>""")
    s.append(("09_Constraints",page(9,3,"Growth potential","Half of the headroom is execution: leads converting below peers",
        "2,051 assessed physical shops (21% of network volume) · base headroom +5.5K above a BAU of 88K",cons)))

    cap=stack(fig(R3/"R3_06_Agent_Time_Share.png","Figure 7 · Assigned agents vs agent FTE per shop (left) and output by agent FTE (right)","Source: Round 3 employee–shop assignments and funded contracts, Jul–Sep 2026.","height:450px"),
  f"""<div class="col" style="flex:1.3">{kpis([("23 vs 5","assigned agents per Non-Aldi vs Aldi shop",""),("0.6 vs 3.0","agent FTE per shop (1 / shops each agent serves)",""),("48 vs 10","funded contracts per agent FTE","")])}</div>
<div class="col" style="flex:.7">{box("Insight","<b>Non-Aldi shops look over-staffed by headcount and are under-staffed by time.</b> A hypothesis for a stepped pilot, not a measured effect.")}</div>""")
    s.append(("10_Capacity",page(10,3,"Growth potential","Headcount is the wrong unit: each Non-Aldi agent serves 40 shops",
        "Agent FTE at a shop = Σ over assigned agents of 1 / (number of shops the agent serves); Jul–Sep 2026",cap)))

    prio=stack(fig(R3/"R3_05_Priority_and_Robustness.png","Figure 8 · Headroom vs shop size by action (left) and shortlist stability under other benchmarks (right)","Source: shop_growth_priority.parquet; full list in pilot_shortlist_top50.csv.","height:370px"),
  f"""<div class="col" style="flex:1.3">{table(["Rank","Shop","Province","Now","Attainable p50–p90","Conv. vs peer"],[
["1","101064342","Đồng Nai","174","290–387","0.46×"],["2","99426264","Đồng Nai","74","159–220","0.36×"],["4","105843385","TP.HCM","73","111–175","0.65×"],
["6","113786131","An Giang","94","125–170","0.50×"]],["9%","19%","19%","11%","24%","18%"],"font-size:17px")}</div>
<div class="col" style="flex:.7">{kpis([("+0.6–1.5K","headroom / qtr of the top 20 execution-gap shops (base 1.0K)","")])}{kpis([("80%","of the top 20 kept under the cautious p50 benchmark (55% under p90)","")])}</div>""")
    s.append(("11_Prioritisation",page(11,4,"Prioritisation & actions","Twenty shops first, with a list that survives a cautious benchmark",
        "Ranked by base headroom; high-PROTECT shops excluded; low / base / high = peer p50 / p75 / p90",prio)))

    recs=table(["#","Decision","Why (evidence)","Size / quarter","Why others miss it","Type"],[
["1","<b>Lead follow-up pilot</b> in the 20 execution-gap shops: call-back standard + weekly conversion review vs same-product peers, with matched control shops","Leads convert at 0.3–0.65× peers","+0.6K / 1.0K / 1.5K","Raw conversion makes CL-heavy shops look worst",'<span class="tag">Expected</span>'],
["2","<b>Fix shop credit:</b> cards to the selling employee's shop; cash loans split between referring shop and closing channel","9 in 10 centrally booked cards sold by shop staff the same day; one ID holds 28% of contracts","Corrects rankings; 23 shops have ≥ 20% of output recorded elsewhere","Needs leads → contracts → processing staff joined",'<span class="tag bold">Bold</span>'],
["3","<b>Reallocate agent time, not headcount:</b> shift part of Aldi agent time to Non-Aldi execution-gap shops","0.6 vs 3.0 FTE per shop; 48 vs 10 contracts per FTE","Pilot, e.g. 10% of Aldi time (~210 FTE)","Headcount (23 vs 5) hides 40-shop rotation",'<span class="tag bold">Bold</span>'],
["4","<b>Cancel the R2 December Tết reminder</b> for 392K customers; fund GROW reactivation instead","2.1% vs 4.3% applied before Tết 2026; no network peak","Saves a 392K campaign; GROW lever +1.2K","Teams rarely re-test their own R2 idea",'<span class="tag bold">Bold · self-correction</span>'],
["5","<b>No volume push</b> in the 25 high-PROTECT shops","PROTECT late 30.3% vs GROW 24.1%","Holds back +0.2K of risky volume","Growth rankings ignore who the new customers are",'<span class="tag g">Guardrail</span>']],["3%","30%","20%","17%","18%","12%"],"font-size:21.5px")
    s.append(("12_Recommendations",page(12,4,"Prioritisation & actions","Five decisions, each tied to one number and one test",
        "Sizes are funded contracts per quarter; low / base / high = peer p50 / p75 / p90",
        f'<div class="col" style="flex:1;justify-content:space-between">{recs}<div class="guard"><b class="t">Guardrail</b>All figures are peer-benchmark scenarios, not causal uplift. Every action starts as a pilot with a control group and a pre-agreed stop gate.</div></div>')))

    tl='<div class="tl">'+"".join(f'<div class="ph" style="background:{c}"><b>{h}</b>{t}</div>' for h,t,c in [
        ("Weeks 0–2 · Prepare","Re-attribute cards in reporting · pick 20 pilot + 20 matched control shops · freeze KPIs","#14213D"),
        ("Weeks 3–14 · Pilot","Follow-up standard in pilot shops · agent-time shift in one region · 10% Tết test cell before Tết 2027 (6 Feb)","#004AAD"),
        ("Weeks 15–16 · Evaluate","Pilot vs control on funded contracts and late rate","#3D6FC0"),
        ("Quarter 2 · Scale or stop","Extend to the 268 execution-gap shops if gates are met","#8FAAD1")])+"</div>"
    road=f"""<div class="col" style="flex:1;justify-content:space-between">{tl}{table(["Action","Owner","KPI","Guardrail","Scale / stop gate"],[
["Lead follow-up","Regional sales managers","Funded per shop vs control","Late rate on new loans","Scale if ≥ +5% vs control"],
["Credit fix","Sales reporting / Finance","Share of cards re-attributed","Total booked unchanged","Done when 100% of cards carry a seller shop"],
["Agent time","Sales operations","Funded per agent FTE","Aldi output within its BAU interval","Stop if Aldi falls below interval"],
["Tết test cell","CRM","Pre-Tết application rate, test vs hold-out","Opt-out rate","Scale only if ≥ +2 points"],
["Quality hold","Risk","Late rate in held shops","No new-credit push","Review every quarter"]],["16%","20%","24%","20%","20%"],"font-size:22px")}
<div class="bottomline">To know how big a shop can become, measure the pipeline it has not yet converted, not the sales it has already recorded.</div></div>"""
    s.append(("13_Roadmap",page(13,4,"Prioritisation & actions","Prepare, pilot, evaluate, scale: one quarter to a decision",
        "Owners are proposed functions; thresholds are provisional and set before launch",road)))
    return s


def appendix()->list[tuple[str,str]]:
    a=[]
    def one(n,code,title,sub,left,right):a.append((f"A{n:02d}_{code}",page(13+n,None,f"Appendix A{n}",title,sub,left+right)))
    gl=[("FHS","Financial Health Score (0–100), Round 2"),("CES","Customer Engagement Score (0–100), Round 2"),("BAU","Business-as-usual forecast"),("CC / CL / CW","Credit card / cash loan / cash-loan variant"),
        ("CD / TW / BNPL","Consumer durables at point of sale / two-wheeler loan / buy now pay later"),("FTE","Full-time equivalent (agent time share)"),("AUC / Gini","Ranking quality (0.5 / 0 = random); Gini = 2·AUC − 1"),
        ("p50 / p75 / p90","Median / 75th / 90th percentile of peer shops"),("GROW","Healthy and engaged: offer reviews"),("RE-TIME","Healthy, quiet, one-time Tết borrower"),("NURTURE","Thin file or quiet: low-cost digital"),("PROTECT","Low health with loan history: repayment support")]
    one(1,"Glossary","Glossary","Every abbreviation used in the deck",f'<div class="col" style="flex:1">{table(["Term","Meaning"],[[f"<b>{k}</b>",v] for k,v in gl[:6]],["30%","70%"])}</div>',
        f'<div class="col" style="flex:1">{table(["Term","Meaning"],[[f"<b>{k}</b>",v] for k,v in gl[6:]],["30%","70%"])}</div>')
    one(2,"Data_Quality","Data processing and quality checks","Coverage, dates and lead–contract matching (Phase 1–2 outputs)",
        f'<div class="col" style="flex:1">{fig(EDA/"fnd_01.png","FND_01 · Source and key coverage","Source: Phase 1 validation report.","flex:1")}</div>',
        f'<div class="col" style="flex:1">{fig(EDA/"fnd_04.png","FND_04 · Lead–contract match funnel","Source: lead_contract_candidates.","flex:1")}</div>')
    one(3,"Weights_Undocumented","Lead weights and R2 linkage","sample_weight is undocumented, so all lead figures use raw counts; R2 customers link by client key",
        f'<div class="col" style="flex:1">{fig(EDA/"fnd_03.png","FND_03 · sample_weight audit","Source: leads_clean.","flex:1")}</div>',
        f'<div class="col" style="flex:1">{fig(EDA/"fnd_07.png","FND_07 · R2 customers in Round 3 events after the cutoff","Round 3 holds ~32% of R2 customers’ Jan–May 2025 contracts.","flex:1")}</div>')
    one(4,"CES_Weights","CES weight evidence","8 weightings compared on the hold-out half; numbers under bars = single-component AUC",
        f'<div class="col" style="flex:1">{fig(R2/"R2_01_CES_Weight_Evidence.png","R2_01 · Weights (left) and hold-out AUC, applies again within 6 months (right)","Source: Round 2 components; Round 3 applications after 5 Jun 2025.","height:560px")}',
        f'{box("Reading","All weightings land at AUC 0.718–0.733, so conclusions do not hinge on weights. Dropping recency costs nothing (it duplicates frequency); final weights chosen on the train half: digital 25%, frequency 31%, responsiveness 25%, breadth 19%.")}</div>')
    one(5,"CES_Cutoffs","CES outcome-anchored cut-offs","Same rule as FHS: tiers mark 1.5× and 2/3 of the average outcome",
        f'<div class="col" style="flex:1.4">{fig(R2/"R2_02_CES_Outcome_Anchored_Cutoffs.png","R2_02 · Re-application rate by CES score (train half)","Source: Round 3 applications within 6 months of the R2 snapshot.","flex:1")}</div>',
        f'<div class="col" style="flex:.6">{box("Reading","High ≥ 44, Low &lt; 17. Tiers become 263K / 467K / 271K (R2: 50K / 187K / 763K). High re-applies 39% vs Low 6% (6.4×; R2 tiers 2.9×).")}</div>')
    one(6,"FHS_Check","FHS out-of-time weight check","Late payment on Round 3 loans funded after the snapshot, hold-out half",
        f'<div class="col" style="flex:1.4">{fig(R2/"R2_03_FHS_Out_of_Time_Weight_Check.png","R2_03 · Hold-out Gini by weighting","Source: Round 3 dpd_1pd–dpd_4pd flags, loans funded before May 2026.","flex:1")}</div>',
        f'<div class="col" style="flex:.6">{box("Reading","R2 weights 0.084 vs equal 0.078; without Pre-approved Capacity 0.059; without DTI 0.095.")}<div class="guard"><b class="t">Honest limit</b>Out-of-time Gini is weak (0.08 vs 0.32 in R2): use FHS as a guardrail, not a credit decision.</div></div>')
    one(7,"Group_Sensitivity","Group sizes under threshold shifts","FHS and CES cut-offs moved ±5 points",
        f'<div class="col" style="flex:1.4">{fig(R2/"R2_05_Group_Threshold_Sensitivity.png","R2_05 · Customers per action group by scenario","Source: r2_customer_groups.parquet.","flex:1")}</div>',
        f'<div class="col" style="flex:.6">{box("Reading","Group order and the PROTECT queue are stable; GROW and NURTURE trade members at the margin.")}</div>')
    import pandas as pd
    pb=pd.read_csv(R2/"r2_group_playbook.csv")
    one(8,"Playbook","Customer group playbook","Who, what, owner, KPI, guardrail and stop rule per Round 2 group",
        f'<div class="col" style="flex:1">{table(["Group","Action","Owner","KPI","Stop rule"],[[f"<b>{r.action_group}</b>",esc(r.action),esc(r.owner),esc(r.kpi),esc(r.stop_rule)] for r in pb.itertuples()],["9%","37%","16%","20%","18%"],"font-size:17px")}</div>',"")
    one(9,"BAU_Backtest","BAU method and backtest","Trailing baseline vs linear trend, rolling-origin validation",
        f'<div class="col" style="flex:1">{fig(T1/"T1_05_Forecast_Model_Ladder.png","T1_05 · Model ladder","Source: Task 1.","flex:1")}</div>',
        f'<div class="col" style="flex:1">{fig(T1/"T1_06_Rolling_Origin_Backtest.png","T1_06 · Rolling-origin backtest","Source: Task 1; intervals are empirical, not guaranteed coverage.","flex:1")}</div>')
    one(10,"Peers","Peer benchmarks and product conversion","Peers = same category × model; conversion compared within product",
        f'<div class="col" style="flex:1.2">{fig(T1/"T1_04_Comparable_Shop_Benchmark.png","T1_04 · Comparable-shop groups","Source: Task 1.","flex:1")}</div>',
        f'<div class="col" style="flex:.8"><div class="tcap">Lead conversion by product, physical shops, Jul–Sep 2026</div>{table(["Product","Lead UUIDs","Funded","Conversion"],[["CL","61,798","1,021","1.7%"],["CC","41,550","4,538","10.9%"],["TW","14,789","3,906","26.4%"],["CD","43,010","17,194","40.0%"]])}</div>')
    one(11,"Customer_Mix","Customer mix is a guardrail, not a growth driver","GROW share of linked customers by shop size, and growth by GROW-share quintile",
        f'<div class="col" style="flex:1.4">{fig(R3/"R3_02_Customer_Mix_Same_Size.png","R3_02 · GROW share by size band (left); funded growth Q3 vs Q2 2026 by GROW quintile (right)","Shops with ≥ 30 linked R2 customers and ≥ 15 contracts.","flex:1")}</div>',
        f'<div class="col" style="flex:.6">{box("Reading","Median GROW share is 52–56% in every size band, and growth shows no monotonic link to it. Customer quality is used to hold back risky shops, not to size growth.")}</div>')
    one(12,"Cross_Booking","Cross-booking evidence","Physical-shop CC/CL leads funded under another ID, leads assigned Jul–Sep 2026",
        f'<div class="col" style="flex:1">{table(["Product","Recorded under","Contracts","By origin-shop staff","Within 24 h","Median lag"],[["CC","Central IDs (42902170 / 6282)","3,769","89%","88%","0 h"],["CC","Other shops","301","94%","91%","0 h"],["CL","Central IDs (42902170 / 6282)","562","14%","20%","289 h"],["CL","Other shops","362","81%","30%","243 h"]])}'
        f'{box("ID 42902170 profile","Books only CL (108K applications), CC (50K) and CW (17K) since Jul 2026; ~3,900 different processing employees; 73% of all funded cards and 48% of funded cash loans. ID 6282: ~210 employees, CL/CC only (likely telesales, unconfirmed).")}</div>',"")
    sl=pd.read_csv(R3/"pilot_shortlist_top50.csv")
    sl=sl[sl.action.eq("TEST: lead follow-up SLA")].head(20)
    one(13,"Shortlist","Pilot shortlist: top 20 execution-gap shops","Funded contracts per quarter; rank under p50 / p90 shows stability",
        f'<div class="col" style="flex:1">{table(["Rank","Shop","Peer","Province","Now","Attainable p50 / p75 / p90","Conv. vs peer","Rank p50 / p90"],[[f"{r.rank_base:.0f}",str(r.shop),esc(r.peer),esc(str(r.province)),f"{r.current_3m:.0f}",f"{r.attainable_low:.0f} / {r.attainable_base:.0f} / {r.attainable_high:.0f}",f"{r.conversion_vs_peer:.2f}×",f"{r.rank_low:.0f} / {r.rank_high:.0f}"] for r in sl.itertuples()],None,"font-size:15.5px")}</div>',"")
    one(14,"Limits","Assumptions and limits","What the numbers can and cannot support",
        f'<div class="col" style="flex:1">{box("Assumptions","<ul><li>Unit: funded contracts recorded at the shop, 3 months</li><li>BAU = Task 1 trailing baseline</li><li>Attainable = BAU + peer-rate levers at p50 / p75 / p90</li><li>Ceiling = internal proxy, not market size; no external data used</li><li>Peers: category × model, ≥ 30 shops, ≥ 15 contracts</li></ul>")}</div>',
        f'<div class="col" style="flex:1"><div class="guard"><b class="t">Limits</b><ul><li>Peer benchmarks are scenarios, not causal uplift: every action is piloted</li><li>Assessed shops record 21% of network volume; central IDs cannot be benchmarked</li><li>Round 3 holds ~32% of R2 customers’ overlapping contracts</li><li>Agent FTE assumes equal time across shops served</li><li>DPD checkpoint timing undocumented; FHS out-of-time Gini is weak</li></ul></div></div>')
    return a


def render(name:str,doc:str)->Path:
    HTML_DIR.mkdir(parents=True,exist_ok=True);PNG_DIR.mkdir(parents=True,exist_ok=True)
    src=HTML_DIR/f"{name}.html";src.write_text(doc,encoding="utf-8")
    out=PNG_DIR/f"Slide_{name}.png"
    subprocess.run([CHROME,"--headless=new","--disable-gpu","--hide-scrollbars","--force-device-scale-factor=1","--allow-file-access-from-files",
                    "--virtual-time-budget=6000","--window-size=1920,1080",f"--screenshot={out}",src.as_uri()],check=True,capture_output=True,timeout=120)
    return out


if __name__=="__main__":
    for name,doc in slides()+appendix():print(render(name,doc).name)

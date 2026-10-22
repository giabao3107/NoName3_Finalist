"""Bộ slide Round 3 bằng tiếng Việt, cho người không chuyên: mỗi slide là một ảnh PNG 1920x1080.
Bố cục theo chữ F: tiêu đề → dải thông điệp chính → cột trái (con số nổi bật, đọc dọc) → biểu đồ bên phải.
Số liệu đọc từ output của nhánh Lu (customer_to_shop_report.json, r2_revision_report.json, pilot_shortlist_top50.csv)."""
from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
CHARTS=HERE/"charts";HTML_DIR=HERE/"html";PNG_DIR=HERE/"png"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
R2=ROOT/"output"/"R2_Customer_Foundation";R3=ROOT/"output"/"Customer_to_Shop_Growth";T1=ROOT/"output"/"Shop_Performance_and_BAU"
REP2=json.loads((R2/"r2_revision_report.json").read_text(encoding="utf-8"))
REP3=json.loads((R3/"customer_to_shop_report.json").read_text(encoding="utf-8"))
NAV=["Bối cảnh & dữ liệu","Nền tảng Vòng 2","Đo tiềm năng","Điều gì cản trở","Hành động"]
C={"blue":"#004AAD","navy":"#14213D","mid":"#8FAAD1","light":"#C9D6EA","grey":"#9CA3AF","dark":"#374151","red":"#C51E1E","amber":"#C98A1B","green":"#1E7A4F"}
plt.rcParams.update({"font.family":"Arial","font.size":17,"axes.spines.top":False,"axes.spines.right":False,"axes.spines.left":False,
                     "axes.grid":False,"figure.facecolor":"white","axes.facecolor":"white","savefig.facecolor":"white"})

# ------------------------------------------------------------------------------------------- charts
def save(fig,name:str)->Path:
    CHARTS.mkdir(parents=True,exist_ok=True);p=CHARTS/f"{name}.png"
    fig.savefig(p,dpi=200,bbox_inches="tight",pad_inches=.15);plt.close(fig);return p


def bars(ax,labels,values,colors,fmt,horizontal=False,fs=20):
    if horizontal:
        b=ax.barh(labels,values,color=colors,height=.62);ax.invert_yaxis();ax.set_xticks([])
        for r,v in zip(b,values):ax.text(r.get_width()+max(values)*.015,r.get_y()+r.get_height()/2,fmt(v),va="center",fontsize=fs,fontweight="bold",color=C["navy"])
        ax.set_xlim(0,max(values)*1.22);ax.tick_params(axis="y",length=0,labelsize=18)
    else:
        b=ax.bar(labels,values,color=colors,width=.62);ax.set_yticks([])
        for r,v in zip(b,values):ax.text(r.get_x()+r.get_width()/2,r.get_height()+max(values)*.015,fmt(v),ha="center",va="bottom",fontsize=fs,fontweight="bold",color=C["navy"])
        ax.set_ylim(0,max(values)*1.18);ax.tick_params(axis="x",length=0,labelsize=17)
    ax.spines["bottom"].set_color("#D1D5DB")


def charts()->dict[str,Path]:
    out={}
    g=pd.DataFrame(REP2["group_validation"]).set_index("action_group")
    order=["GROW","NURTURE","PROTECT","RE-TIME"];names=["Khách tốt\n(nên bán thêm)","Khách ít\ngiao dịch","Khách đang\nkhó trả nợ","Khách chỉ\nvay dịp Tết"]
    fig,ax=plt.subplots(figsize=(11,5.6))
    bars(ax,names,[g.loc[k,"applied_after"]*100 for k in order],[C["blue"],C["mid"],C["red"],C["amber"]],lambda v:f"{v:.0f}%",fs=26)
    ax.set_ylabel("% khách quay lại vay\n(6/2025 – 9/2026)",fontsize=17,color=C["dark"])
    out["groups"]=save(fig,"c01_nhom_khach_quay_lai")

    m=pd.DataFrame(REP2["network_monthly_applications"]);m["month_start"]=pd.to_datetime(m.month_start)
    fig,ax=plt.subplots(figsize=(11,5.6))
    pre=m.month_start.isin(pd.to_datetime(["2025-01-01","2026-01-01","2026-02-01"]))
    ax.bar(m.month_start,m.applications/1000,width=22,color=np.where(pre,C["amber"],C["light"]))
    ax.set_yticks([]);ax.set_ylim(0,m.applications.max()/1000*1.25)
    for t,l in ((pd.Timestamp("2025-01-29"),"Tết 2025"),(pd.Timestamp("2026-02-17"),"Tết 2026")):
        ax.axvline(t,color=C["red"],linestyle="--",linewidth=1.5);ax.text(t,m.applications.max()/1000*1.17,l,ha="center",fontsize=17,color=C["red"],fontweight="bold")
    for d,lab in ((pd.Timestamp("2026-01-01"),"180K"),(pd.Timestamp("2026-02-01"),"150K"),(pd.Timestamp("2025-01-01"),"202K"),(pd.Timestamp("2026-09-01"),"197K")):
        v=float(m.loc[m.month_start==d,"applications"].iloc[0])/1000;ax.text(d,v+3,lab,ha="center",fontsize=16,fontweight="bold",color=C["navy"])
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m/%y"));ax.tick_params(axis="x",labelsize=14,length=0)
    ax.set_ylabel("Số hồ sơ vay mỗi tháng (nghìn)",fontsize=17,color=C["dark"])
    out["monthly"]=save(fig,"c02_ho_so_theo_thang")

    fig,ax=plt.subplots(figsize=(11,5.6))
    bars(ax,["Thẻ tín dụng","Vay tiền mặt","Vay mua xe máy","Trả góp đồ\ngia dụng"],[90,90,13,1],[C["red"],C["red"],C["mid"],C["mid"]],lambda v:f"{v:.0f}%",fs=26)
    ax.set_ylabel("% hợp đồng từ khách của cửa hàng\nnhưng bị ghi cho nơi khác",fontsize=17,color=C["dark"])
    out["recorded"]=save(fig,"c03_ghi_noi_khac")

    f=REP3["four_concepts_assessed"]
    vals=[f["current_3m"],f["bau_3m"],f["attainable_base"],f["ceiling_internal"]]
    fig,ax=plt.subplots(figsize=(11,5.6))
    bars(ax,["Đang bán\n(hiện tại)","Nếu giữ\nnguyên","Có thể đạt\n(làm tốt như\ncửa hàng cùng loại)","Mức trần\n(chốt gần\ntối đa)"],[v/1000 for v in vals],[C["grey"],C["mid"],C["blue"],C["navy"]],lambda v:f"{v:,.1f}K".replace(".",","),fs=26)
    ax.set_ylabel("Hợp đồng / quý, 2.051 cửa hàng",fontsize=17,color=C["dark"])
    out["four"]=save(fig,"c04_bon_con_so")

    a,b=REP3["pair"]["A"],REP3["pair"]["B"]
    fig,ax=plt.subplots(figsize=(11,5.6));x=np.arange(3);w=.36
    va=[a["current_3m"],a["attainable_base"],a["ceiling_internal"]];vb=[b["current_3m"],b["attainable_base"],b["ceiling_internal"]]
    ra=ax.bar(x-w/2,va,w,color=C["blue"],label="Cửa hàng A");rb=ax.bar(x+w/2,vb,w,color=C["grey"],label="Cửa hàng B")
    for r,v in list(zip(ra,va))+list(zip(rb,vb)):ax.text(r.get_x()+r.get_width()/2,v+3,f"{v:.0f}",ha="center",fontsize=24,fontweight="bold",color=C["navy"])
    ax.set_xticks(x,["Đang bán","Có thể đạt","Mức trần"]);ax.tick_params(axis="x",length=0,labelsize=20);ax.set_yticks([]);ax.set_ylim(0,max(va)*1.2)
    ax.legend(frameon=False,fontsize=19,loc="upper left");ax.spines["bottom"].set_color("#D1D5DB")
    ax.set_ylabel("Hợp đồng / quý",fontsize=17,color=C["dark"])
    out["pair"]=save(fig,"c05_hai_cua_hang")

    cons=pd.DataFrame(REP3["constraints"]).set_index("primary_constraint")
    keys=[("EXECUTION: leads convert below peers","Chốt khách kém hơn\ncửa hàng cùng loại (268 CH)",C["red"]),("NO CLEAR GAP","Không có một\nnguyên nhân rõ (753 CH)",C["mid"]),
          ("QUALITY: high PROTECT share","Nhiều khách khó trả nợ,\ncố ý không đẩy (25 CH)",C["grey"]),("UNTAPPED BASE: warm customers, thin pipeline","Có khách tốt nhưng ít\nkhách tiềm năng (510 CH)",C["mid"]),
          ("DEMAND: thin pipeline","Thiếu khách\ntiềm năng (495 CH)",C["mid"])]
    fig,ax=plt.subplots(figsize=(11,5.6))
    bars(ax,[l for _,l,_ in keys],[cons.loc[k,"gap_base"] for k,_,_ in keys],[c for *_,c in keys],lambda v:f"+{v:,.0f}".replace(",","."),horizontal=True,fs=22)
    ax.set_xlabel("Hợp đồng / quý có thể tăng thêm",fontsize=17,color=C["dark"])
    out["constraints"]=save(fig,"c06_dieu_can_tro")

    cap=pd.DataFrame(REP3["capacity"]).set_index("model")
    fig,(a1,a2)=plt.subplots(1,2,figsize=(11,5.6))
    x=np.arange(2);w=.38
    for ax_,vals_,ttl,fmt in ((a1,[[cap.loc["Non-Aldi","agents"],cap.loc["Aldi","agents"]],[cap.loc["Non-Aldi","fte"],cap.loc["Aldi","fte"]]],"",None),):pass
    r1=a1.bar(x-w/2,[cap.loc["Non-Aldi","agents"],cap.loc["Aldi","agents"]],w,color=C["light"],label="Số nhân viên được gán")
    r2=a1.bar(x+w/2,[cap.loc["Non-Aldi","fte"],cap.loc["Aldi","fte"]],w,color=C["blue"],label="Số người thực sự có mặt")
    for r in list(r1)+list(r2):a1.text(r.get_x()+r.get_width()/2,r.get_height()+.4,f"{r.get_height():.1f}".replace(".0","").replace(".",","),ha="center",fontsize=22,fontweight="bold",color=C["navy"])
    a1.set_xticks(x,["Non-Aldi","Aldi"]);a1.set_yticks([]);a1.tick_params(axis="x",length=0,labelsize=20);a1.legend(frameon=False,fontsize=15,loc="upper right");a1.set_ylim(0,30)
    a1.set_title("Nhân sự mỗi cửa hàng",fontsize=19,color=C["dark"],loc="left")
    per=[48,10];r3=a2.bar(["Non-Aldi","Aldi"],per,color=[C["blue"],C["amber"]],width=.55)
    for r,v in zip(r3,per):a2.text(r.get_x()+r.get_width()/2,v+1,f"{v}",ha="center",fontsize=26,fontweight="bold",color=C["navy"])
    a2.set_yticks([]);a2.tick_params(axis="x",length=0,labelsize=20);a2.set_ylim(0,60);a2.set_title("Hợp đồng / quý trên mỗi người thực có",fontsize=19,color=C["dark"],loc="left")
    for a_ in (a1,a2):a_.spines["bottom"].set_color("#D1D5DB")
    out["capacity"]=save(fig,"c07_nhan_su")
    fig,ax=plt.subplots(figsize=(11,5.6))
    bars(ax,["Vay tiền mặt","Thẻ tín dụng","Vay mua xe máy","Trả góp đồ\ngia dụng"],[1.7,10.9,26.4,40.0],[C["red"],C["mid"],C["mid"],C["blue"]],lambda v:f"{v:.1f}%".replace(".",","),fs=26)
    ax.set_ylabel("Tỉ lệ chốt khách tiềm năng",fontsize=17,color=C["dark"])
    out["conv"]=save(fig,"c08_ti_le_chot_san_pham")
    return out

# --------------------------------------------------------------------------------------------- html
CSS="""
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Be+Vietnam+Pro:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{--blue:#004AAD;--navy:#14213D;--light:#EEF3FA;--mid:#8FAAD1;--grey:#6B7280;--line:#D5DCE6;--red:#C51E1E;--amber:#C98A1B}
html,body{width:1920px;height:1080px;overflow:hidden;background:#fff;font-family:'Be Vietnam Pro',Arial,sans-serif;color:#1F2937}
.slide{position:relative;width:1920px;height:1080px;padding:40px 64px 0}
.hdr{padding-left:24px;border-left:9px solid var(--blue)}
.eyebrow{font-family:Oswald,sans-serif;font-weight:700;color:var(--blue);font-size:28px;letter-spacing:.5px;text-transform:uppercase}
.title{font-weight:800;color:var(--navy);font-size:42px;line-height:1.15;margin-top:2px}
.pageno{position:absolute;top:38px;right:64px;font-family:Oswald,sans-serif;font-size:32px;color:#B8C2D0;font-weight:600}
.key{margin-top:18px;background:var(--navy);color:#fff;border-radius:10px;padding:16px 26px;font-size:26px;font-weight:600;line-height:1.35}
.key b{color:#FFD166}
.body{position:absolute;top:262px;left:64px;right:64px;bottom:104px;display:flex;gap:28px}
.left{flex:0 0 36%;display:flex;flex-direction:column;gap:16px;min-height:0}
.right{flex:1;display:flex;flex-direction:column;min-height:0}
.foot{position:absolute;left:30px;right:30px;bottom:0;height:84px;border-top:2px solid var(--line);display:flex;justify-content:space-around;align-items:center}
.foot div{font-weight:700;font-size:20px;color:#111827;position:relative;padding:6px 10px}
.foot div.on{color:var(--blue)}
.foot div.on:before{content:'';position:absolute;left:10%;right:10%;top:-20px;height:7px;border-radius:4px;background:var(--blue)}
.big{border-left:8px solid var(--blue);background:var(--light);border-radius:8px;padding:12px 18px;flex:1;display:flex;flex-direction:column;justify-content:center}
.big .n{font-weight:800;color:var(--blue);font-size:54px;line-height:1.05}
.big .c{font-size:21px;color:#1F2937;margin-top:6px;line-height:1.35}
.big.red{border-color:var(--red);background:#FFF4F4}.big.red .n{color:var(--red)}
.big.amber{border-color:var(--amber);background:#FFF8EC}.big.amber .n{color:var(--amber)}
.big.grey{border-color:#9CA3AF;background:#F3F4F6}.big.grey .n{color:#4B5563}
.mean{border:2px solid var(--blue);border-radius:10px;padding:12px 18px;font-size:21px;line-height:1.42;background:#fff}
.mean li{margin:10px 0;font-size:22px}
.mean b.t{display:block;color:var(--blue);font-size:21px;margin-bottom:2px}
.chart{flex:1;border:2px solid #E3E8F0;border-radius:12px;padding:14px 18px 8px;display:flex;flex-direction:column;min-height:0}
.chart .cap{font-weight:700;font-size:22px;color:var(--navy);margin-bottom:6px}
.chart img{flex:1;min-height:0;width:100%;object-fit:contain}
.chart .src{font-size:14px;font-style:italic;color:var(--grey);text-align:right;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:21px}
th{background:var(--blue);color:#fff;text-align:left;padding:10px 14px;font-weight:700}
td{padding:10px 14px;border-bottom:1px solid #E5EAF1;vertical-align:top;line-height:1.35}
tr:nth-child(even) td{background:#F4F7FB}
.pill{display:inline-block;font-size:16px;font-weight:700;padding:3px 12px;border-radius:14px;color:#fff;background:var(--blue);white-space:nowrap}
.pill.n{background:var(--navy)}.pill.r{background:var(--red)}
.card{border:2px solid var(--blue);border-radius:12px;padding:14px 18px;background:#fff;display:flex;flex-direction:column}
.card h4{font-size:24px;color:var(--navy);font-weight:800;margin-bottom:4px}
.card p{font-size:20px;line-height:1.4}
"""


def esc(t):return html.escape(t,quote=False)


def page(n,section,eyebrow,title,key,body,body_top=262)->str:
    foot="".join(f'<div class="{"on" if i==section else ""}">{s}</div>' for i,s in enumerate(NAV)) if section is not None else ""
    style=f' style="top:{body_top}px"' if body_top!=262 else ""
    keyhtml=f'<div class="key">{key}</div>' if key else ""
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="slide">
<div class="pageno">{n:02d}</div><div class="hdr"><div class="eyebrow">{eyebrow}</div><div class="title">{title}</div></div>{keyhtml}
<div class="body"{style}>{body}</div>{'<div class="foot">'+foot+'</div>' if foot else ''}</div></body></html>"""


def big(n,c,k=""):return f'<div class="big {k}"><div class="n">{n}</div><div class="c">{c}</div></div>'
def mean(t,b):return f'<div class="mean"><b class="t">{t}</b>{b}</div>'
def chart(p,cap,src="Nguồn: dữ liệu hợp đồng, khách tiềm năng và nhân sự Vòng 3 (1/2025–9/2026); phân tích của nhóm."):
    return f'<div class="chart"><div class="cap">{cap}</div><img src="{p.as_uri()}"><div class="src">{src}</div></div>'
def table(head,rows,widths=None,style=""):
    cols="".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    return f'<table style="{style}"><colgroup>{cols}</colgroup><tr>'+"".join(f"<th>{h}</th>" for h in head)+"</tr>"+"".join("<tr>"+"".join(f"<td>{c}</td>" for c in r)+"</tr>" for r in rows)+"</table>"


def cover()->str:
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{CSS}
.cv{{width:1920px;height:1080px;position:relative;overflow:hidden;background:radial-gradient(ellipse at 72% 62%,#1d4fd8 0%,#0b2a7a 28%,#06143d 60%,#030a22 100%)}}
.ring{{position:absolute;border-radius:50%;border:3px solid rgba(120,170,255,.35)}}
.streak{{position:absolute;height:3px;background:linear-gradient(90deg,transparent,rgba(255,80,110,.9),transparent);transform:rotate(-18deg)}}
.bi{{position:absolute;top:150px;left:0;right:0;text-align:center;font-family:Oswald,sans-serif;font-weight:700;font-size:118px;letter-spacing:6px;color:#E8EEFF;text-shadow:0 0 28px rgba(110,160,255,.8)}}
.s10{{position:absolute;top:300px;left:0;right:0;text-align:center;font-family:Oswald,sans-serif;font-weight:600;font-size:64px;letter-spacing:10px;color:#C9D6FF}}
.r3{{position:absolute;left:120px;top:610px;font-family:Oswald,sans-serif;font-weight:700;font-size:110px;color:#fff;letter-spacing:2px}}
.q{{position:absolute;left:124px;top:770px;font-weight:700;font-size:42px;color:#DCE6FF}}
.team{{position:absolute;left:124px;top:850px;font-family:Oswald,sans-serif;font-weight:600;font-size:46px;color:#AFC4F0;letter-spacing:2px}}
.canva{{position:absolute;right:60px;bottom:40px;font-size:24px;color:#E5ECFF;font-weight:600;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.35);border-radius:22px;padding:8px 20px}}
</style></head><body><div class="cv">
<div class="ring" style="width:900px;height:900px;left:1080px;top:380px"></div><div class="ring" style="width:600px;height:600px;left:1230px;top:530px"></div>
<div class="ring" style="width:300px;height:300px;left:1380px;top:680px;border-color:rgba(255,90,120,.6)"></div>
<div class="streak" style="width:900px;left:900px;top:420px"></div><div class="streak" style="width:700px;left:-100px;top:560px;opacity:.6"></div>
<div class="bi">BUSINESS INTELLIGENCE</div><div class="s10">— SEASON 10 —</div>
<div class="r3">ROUND 3 : PARALLAX</div><div class="q">Cửa hàng này còn có thể lớn đến đâu?</div><div class="team">TEAM: SHOOTING STAR</div>
<div class="canva">Visual supported by Canva</div></div></body></html>"""


def main_slides(ch)->list[tuple[str,str]]:
    s=[("01_Bia",cover())]
    a,b=REP3["pair"]["A"],REP3["pair"]["B"]

    # 02 Tóm tắt
    findings=f"""<div class="left" style="flex:0 0 44%">
{big("2 cửa hàng, cùng ~75 hợp đồng","nhưng một cửa hàng có <b>661</b> khách tiềm năng chưa chốt hết, cửa hàng kia chỉ có <b>50</b>.")}
{big("+5.500 hợp đồng / quý","có thể tăng thêm ở 2.051 cửa hàng. <b>Một nửa</b> nằm ở 268 cửa hàng chốt khách kém hơn cửa hàng cùng loại.")}
{big("28%","hợp đồng bị ghi cho <b>một mã trung tâm</b>: thẻ bán tại cửa hàng nhưng không được tính cho cửa hàng.","red")}
{big("Bỏ đề xuất cũ","Chiến dịch nhắc vay dịp Tết ở Vòng 2 không hiệu quả: chỉ 2,1% khách quay lại.","amber")}</div>
<div class="right">{table(["#","Nhóm đề xuất làm gì","Lợi ích / quý"],[
["1","Thử nghiệm <b>chăm sóc khách tiềm năng nhanh hơn</b> ở 20 cửa hàng chốt kém nhất","+600 đến +1.500 hợp đồng"],
["2","<b>Ghi công đúng</b> cho cửa hàng đã bán thẻ và giới thiệu khách vay","Xếp hạng cửa hàng công bằng hơn"],
["3","<b>Chia lại thời gian nhân viên</b>, không cần tuyển thêm người","Thử ở 1 vùng trước"],
["4","<b>Bỏ chiến dịch Tết</b> cho 392 nghìn khách, dồn tiền cho khách tốt","Tiết kiệm 392 nghìn lượt liên hệ"],
["5","<b>Không đẩy doanh số</b> ở 25 cửa hàng có nhiều khách khó trả nợ","Tránh nợ xấu"]],["6%","62%","32%"],"font-size:22px")}
<div class="mean" style="margin-top:16px"><b class="t">Cách làm</b>Mọi đề xuất đều bắt đầu bằng thử nghiệm nhỏ, có nhóm cửa hàng đối chứng để so sánh, rồi mới mở rộng.</div></div>"""
    s.append(("02_Tom_tat",page(2,None,"Tóm tắt","Doanh số hiện tại không cho biết cửa hàng còn lớn được bao nhiêu",
        "Muốn biết cửa hàng còn lớn được bao nhiêu, hãy nhìn <b>số khách tiềm năng chưa chốt được</b>, không phải doanh số hiện tại.",findings)))

    # 03 Câu chuyện
    steps=[("1","Khách hàng là ai?","Kiểm tra lại cách chia khách của Vòng 2 bằng dữ liệu mới","Khách tốt quay lại vay 34%","4–5"),
           ("2","Hợp đồng được ghi ở đâu?","Vì sao nhiều hợp đồng của cửa hàng lại bị ghi cho nơi khác","28% ghi cho 1 mã trung tâm","6"),
           ("3","Cửa hàng còn lớn được bao nhiêu?","So với các cửa hàng cùng loại, bán cùng sản phẩm","+5.500 hợp đồng / quý","7–8"),
           ("4","Điều gì đang cản trở?","Thiếu khách, chốt kém, thiếu người hay khách rủi ro","Một nửa do chốt khách kém","9–10"),
           ("5","Làm gì trước?","Chọn cửa hàng, đề xuất và lộ trình thử nghiệm","20 cửa hàng thử trước","11–13")]
    chain="".join(f'''<div class="card" style="flex:1;border-width:3px"><div style="font-family:Oswald;font-size:76px;color:#004AAD;font-weight:700;line-height:1">{k}</div>
<h4 style="font-size:31px;margin:12px 0 14px;line-height:1.2">{q}</h4><p style="font-size:25px;line-height:1.45">{d}</p>
<div style="margin-top:auto;border-top:2px solid #C9D6EA;padding-top:14px"><div style="font-weight:800;color:#004AAD;font-size:34px;line-height:1.2">{r}</div>
<div style="font-size:17px;color:#6B7280;font-style:italic;margin-top:8px">Slide {sl}</div></div></div>''' for k,q,d,r,sl in steps)
    s.append(("03_Cau_chuyen",page(3,0,"Câu chuyện của nhóm","Năm câu hỏi, đi từ khách hàng đến cửa hàng",
        "Đề hỏi: <b>hai cửa hàng bán ngang nhau, làm sao biết cửa hàng nào còn lớn được?</b> Nhóm trả lời qua 5 câu hỏi nối tiếp nhau.",
        f'''<div style="flex:1;display:flex;flex-direction:column;gap:20px"><div style="display:flex;gap:20px;flex:1">{chain}</div>
<div style="display:flex;gap:20px">{mean("Dữ liệu nhóm dùng","<b>3,78 triệu</b> hợp đồng · <b>6,13 triệu</b> lượt khách tiềm năng · <b>32,5 nghìn</b> mã cửa hàng · <b>1 triệu</b> khách đã chấm điểm ở Vòng 2 · từ 1/2025 đến 9/2026")}
{mean("Ba nguyên tắc","So với <b>cửa hàng cùng loại, cùng sản phẩm</b> · kiểm tra trên <b>dữ liệu chưa dùng để tính</b> · mọi đề xuất đều <b>thử nghiệm trước</b> khi mở rộng")}</div></div>''')))

    # 04 Vòng 2
    groups=f"""<div class="left">
<div class="card"><h4 style="color:#004AAD">Khách tốt – nên bán thêm</h4><p>Trả nợ tốt, hay giao dịch. → Giới thiệu sản phẩm phù hợp.</p></div>
<div class="card" style="border-color:#8FAAD1"><h4>Khách ít giao dịch</h4><p>Ít hoạt động hoặc chưa từng vay. → Chăm sóc qua app, chi phí thấp.</p></div>
<div class="card" style="border-color:#C51E1E"><h4 style="color:#C51E1E">Khách đang khó trả nợ</h4><p>Đã có khoản vay trễ hạn. → Hỗ trợ trả nợ, không mời vay thêm.</p></div>
<div class="card" style="border-color:#C98A1B"><h4 style="color:#C98A1B">Khách chỉ vay dịp Tết</h4><p>Chỉ vay một lần trước Tết 2025. → Kiểm tra lại ở slide sau.</p></div>
{mean("Đã sửa theo góp ý giám khảo","Cách tính điểm được kiểm tra trên một nửa số khách mà mô hình chưa từng thấy. Đổi trọng số theo 8 cách khác nhau, kết quả gần như không đổi.")}</div>
<div class="right">{chart(ch["groups"],"Khách tốt quay lại vay nhiều gấp 3–4 lần các nhóm khác","Nguồn: 500 nghìn khách Vòng 2 (nửa dùng để kiểm tra), đối chiếu hợp đồng Vòng 3 đến 9/2026.")}</div>"""
    s.append(("04_Nen_tang_Vong_2",page(4,1,"Nền tảng Vòng 2","Cách chia khách của Vòng 2 vẫn đúng khi kiểm tra bằng dữ liệu mới",
        "1 triệu khách được chia thành 4 nhóm. Dữ liệu 15 tháng sau cho thấy <b>nhóm khách tốt quay lại vay 34%</b>, các nhóm khác chỉ 8–13%.",groups)))

    # 05 Tự sửa sai
    tet=f"""<div class="left">{big("2,1%","khách trong chiến dịch Tết của Vòng 2 vay lại trước Tết 2026","red")}{big("4,3%","khách khác vay lại trong cùng thời gian, gấp đôi","grey")}
{big("Không có đỉnh Tết","Tháng 1 và tháng 2/2026 còn thấp hơn các tháng khác","amber")}
{mean("Vì sao Vòng 2 nhầm","Dữ liệu Vòng 2 chỉ lấy khách nộp hồ sơ dịp Tết 2025, nên trông như ai cũng vay theo mùa. Dữ liệu đầy đủ của Vòng 3 cho thấy không phải vậy.")}</div>
<div class="right">{chart(ch["monthly"],"Số hồ sơ vay mỗi tháng gần như đều nhau, không tăng vọt trước Tết 2026","Nguồn: toàn bộ hợp đồng Vòng 3, 1/2025–9/2026. Cột vàng: các tháng trước Tết.")}</div>"""
    s.append(("05_Tu_sua_sai",page(5,1,"Nền tảng Vòng 2","Nhóm đã kiểm tra lại đề xuất Tết của chính mình và quyết định bỏ",
        "Vòng 2 đề xuất nhắc 392 nghìn khách vay dịp Tết. Dữ liệu mới cho thấy <b>họ không quay lại</b>, nên nhóm chuyển ngân sách sang khách tốt.",tet)))

    # 06 Ghi ở đâu
    rec=f"""<div class="left">{big("28%","tổng hợp đồng được ghi cho <b>một mã trung tâm</b>, không phải một cửa hàng thật","red")}
{big("9 / 10 thẻ","ghi ở mã trung tâm thực ra do <b>chính nhân viên cửa hàng</b> bán, ngay trong ngày")}
{big("10–12 ngày","sau khi được cửa hàng giới thiệu, khách vay tiền mặt mới ký, thường qua kênh khác","grey")}
{mean("Ý nghĩa","Nếu chỉ nhìn số hợp đồng ghi cho cửa hàng, công ty sẽ <b>đánh giá thấp</b> những cửa hàng bán nhiều thẻ.")}</div>
<div class="right">{chart(ch["recorded"],"Thẻ và vay tiền mặt từ khách của cửa hàng: 90% bị ghi cho nơi khác","Nguồn: khách tiềm năng do cửa hàng tạo ra và hợp đồng giải ngân, 7–9/2026.")}</div>"""
    s.append(("06_Hop_dong_ghi_o_dau",page(6,0,"Bối cảnh & dữ liệu","Nhiều hợp đồng cửa hàng bán được lại bị ghi cho nơi khác",
        "Trước khi xếp hạng cửa hàng, cần biết hợp đồng được ghi ở đâu. <b>Thẻ bán tại cửa hàng</b> đang bị ghi cho một mã trung tâm.",rec)))

    # 07 Cách đo
    defs=f"""<div class="left">
<div class="card"><h4>① Đang bán</h4><p>Số hợp đồng cửa hàng ghi được trong 3 tháng gần nhất.</p></div>
<div class="card"><h4>② Nếu giữ nguyên</h4><p>Dự báo 3 tháng tới nếu mọi thứ vẫn như cũ.</p></div>
<div class="card" style="border-color:#004AAD;background:#EEF3FA"><h4 style="color:#004AAD">③ Có thể đạt</h4><p>Nếu cửa hàng chốt khách tiềm năng <b>tốt như các cửa hàng cùng loại</b>, so từng sản phẩm.</p></div>
<div class="card"><h4>④ Mức trần</h4><p>Nếu chốt gần như tối đa số khách tiềm năng đang có. Chỉ để tham khảo.</p></div>
{mean("Vì sao phải so cùng sản phẩm","Khách vay tiền mặt chỉ chốt được khoảng 2%, khách trả góp tại quầy chốt được 40%. So chung sẽ thiệt cho cửa hàng có nhiều khách vay tiền mặt.")}</div>
<div class="right">{chart(ch["four"],"Với 2.051 cửa hàng đủ dữ liệu: có thể tăng từ 88 nghìn lên khoảng 93,5 nghìn hợp đồng / quý","Nguồn: 2.051 cửa hàng vật lý có từ 15 hợp đồng / quý và ít nhất 30 cửa hàng cùng loại để so.")}</div>"""
    s.append(("07_Cach_do",page(7,2,"Đo tiềm năng","Bốn con số để biết một cửa hàng còn lớn được bao nhiêu",
        "Nhóm tách rõ 4 con số mà đề yêu cầu. Con số quan trọng nhất là <b>③ Có thể đạt</b>: so với cửa hàng cùng loại, cùng sản phẩm.",defs)))

    # 08 Hai cửa hàng
    pair=f"""<div class="left">{big("661 vs 50","khách tiềm năng của cửa hàng A so với cửa hàng B trong 3 tháng")}
{big("Chỉ bằng 64%","tỉ lệ chốt của A so với cửa hàng cùng loại. B làm tốt hơn mức chung (122%).","red")}
{big("~121 vs ~83","hợp đồng / quý có thể đạt nếu làm tốt như cửa hàng cùng loại")}
{mean("Kết luận","A còn nhiều chỗ để lớn vì <b>có sẵn khách mà chưa chốt</b>. B đã gần chạm trần với lượng khách hiện có.")}</div>
<div class="right">{chart(ch["pair"],f"Cùng bán {a['current_3m']:.0f} và {b['current_3m']:.0f} hợp đồng, nhưng khả năng tăng trưởng khác hẳn","Cửa hàng A: mã 101125364, Đồng Nai. Cửa hàng B: mã 104947973, Đồng Tháp. Cùng loại cửa hàng vừa, Non-Aldi; 7–9/2026.")}</div>"""
    s.append(("08_Hai_cua_hang",page(8,2,"Đo tiềm năng","Hai cửa hàng bán bằng nhau, nhưng chỉ một cửa hàng còn nhiều chỗ để lớn",
        "Đây là câu hỏi chính của đề. Khác biệt nằm ở <b>số khách tiềm năng chưa chốt</b>, không nằm ở doanh số hiện tại.",pair)))

    # 09 Cản trở
    cons=f"""<div class="left">{big("Một nửa","số hợp đồng có thể tăng thêm nằm ở <b>268 cửa hàng chốt khách kém</b> hơn cửa hàng cùng loại","red")}
{big("Rất nhỏ","phần tăng thêm từ việc tìm thêm khách mới: dưới 100 hợp đồng / quý","grey")}
{big("25 cửa hàng","nhiều khách khó trả nợ: nhóm cố ý <b>không đẩy doanh số</b> ở đây","amber")}
{mean("Ý nghĩa","Trước khi chi tiền tìm thêm khách, hãy <b>chốt tốt số khách đang có</b>.")}</div>
<div class="right">{chart(ch["constraints"],"Phần lớn cơ hội nằm ở khâu chốt khách, không phải ở việc thiếu khách","Nguồn: 2.051 cửa hàng đủ dữ liệu; mỗi cửa hàng được xếp vào một nguyên nhân chính.")}</div>"""
    s.append(("09_Dieu_can_tro",page(9,3,"Điều gì cản trở","Cửa hàng không thiếu khách, mà đang chốt khách chưa tốt",
        "Trong 5 nguyên nhân, <b>chốt khách kém</b> chiếm một nửa cơ hội. Thiếu khách mới chỉ là nguyên nhân rất nhỏ.",cons)))

    # 10 Nhân sự
    capb=f"""<div class="left">{big("40 cửa hàng","mỗi nhân viên bán hàng phải chạy ở các cửa hàng Non-Aldi (Aldi: 14)")}
{big("0,6 người","thời gian nhân viên thực sự có ở mỗi cửa hàng Non-Aldi, dù danh sách gán tới 23 người","red")}
{big("Gấp ~5 lần","số hợp đồng trên mỗi người thực có ở Non-Aldi so với Aldi")}
{mean("Ý nghĩa","Đếm số người thì Non-Aldi trông thừa nhân viên, nhưng tính theo thời gian thì lại <b>thiếu</b>. Đây là giả thuyết cần thử nghiệm.")}</div>
<div class="right">{chart(ch["capacity"],"Đếm theo thời gian làm việc thực tế, bức tranh nhân sự đảo ngược","Nguồn: danh sách nhân viên được gán cho cửa hàng và hợp đồng giải ngân, 7–9/2026 (trung vị mỗi cửa hàng).")}</div>"""
    s.append(("10_Nhan_su",page(10,3,"Điều gì cản trở","Thiếu thời gian của nhân viên, không phải thiếu người",
        "Một nhân viên phải chạy khoảng 40 cửa hàng. Nên <b>chia lại thời gian</b> của nhân viên thay vì tuyển thêm người.",capb)))

    # 11 Chọn cửa hàng
    sl=pd.read_csv(R3/"pilot_shortlist_top50.csv");sl=sl[sl.action.eq("TEST: lead follow-up SLA")].head(8)
    rows=[[f"{i+1}",str(r.shop),esc(str(r.province)),f"{r.current_3m:.0f}",f"{r.attainable_low:.0f}–{r.attainable_high:.0f}",f"{r.conversion_vs_peer*100:.0f}%"] for i,r in enumerate(sl.itertuples())]
    pr=f"""<div class="left">{big("20 cửa hàng","chốt khách kém nhất được chọn để thử nghiệm trước")}
{big("+600 → +1.500","hợp đồng / quý có thể tăng thêm (mức giữa khoảng 1.000)")}
{big("80%","danh sách vẫn giữ nguyên khi dùng cách đánh giá thận trọng hơn","grey")}
{mean("Cách chọn","Xếp theo số hợp đồng có thể tăng thêm, bỏ các cửa hàng có nhiều khách khó trả nợ.")}</div>
<div class="right">{table(["#","Mã cửa hàng","Tỉnh / thành","Đang bán / quý","Có thể đạt / quý","Tỉ lệ chốt so với cửa hàng cùng loại"],rows,["5%","17%","17%","16%","19%","26%"],"font-size:22px")}
<div class="src" style="font-size:15px;font-style:italic;color:#6B7280;text-align:right;margin-top:8px">Danh sách đầy đủ 20 cửa hàng ở phụ lục. Nguồn: pilot_shortlist_top50.csv.</div></div>"""
    s.append(("11_Chon_cua_hang",page(11,4,"Hành động","Bắt đầu với 20 cửa hàng có nhiều khách mà chốt kém nhất",
        "Nguồn lực có hạn nên nhóm chọn nơi <b>dễ thấy kết quả nhất</b>: có sẵn khách, chỉ cần chốt tốt hơn.",pr)))

    # 12 Đề xuất
    recs=table(["#","Đề xuất","Vì sao","Lợi ích / quý","Loại"],[
["1","<b>Chăm sóc khách tiềm năng nhanh hơn</b> ở 20 cửa hàng chốt kém: gọi lại sớm, theo dõi tỉ lệ chốt hằng tuần","Các cửa hàng này chỉ chốt bằng 30–65% cửa hàng cùng loại","+600 đến +1.500 hợp đồng",'<span class="pill">Đội nào cũng có</span>'],
["2","<b>Ghi công đúng:</b> thẻ tính cho cửa hàng của nhân viên bán; vay tiền mặt chia công giữa cửa hàng giới thiệu và kênh chốt","9/10 thẻ ghi ở mã trung tâm là do nhân viên cửa hàng bán","Xếp hạng công bằng; 23 cửa hàng đang bị tính thiếu ≥ 20%",'<span class="pill n">Mới</span>'],
["3","<b>Chia lại thời gian nhân viên</b>, chuyển bớt từ cửa hàng Aldi sang Non-Aldi đang chốt kém","Mỗi người ở Non-Aldi làm ra gấp ~5 lần","Thử ở 1 vùng trước",'<span class="pill n">Mới</span>'],
["4","<b>Bỏ chiến dịch nhắc vay dịp Tết</b> cho 392 nghìn khách, dồn ngân sách cho khách tốt","Chỉ 2,1% quay lại, thấp hơn khách thường (4,3%)","Tiết kiệm 392 nghìn lượt liên hệ",'<span class="pill n">Tự sửa sai</span>'],
["5","<b>Không đẩy doanh số</b> ở 25 cửa hàng có nhiều khách khó trả nợ","Nhóm khách này trả trễ 30%, khách tốt 24%","Tránh thêm nợ xấu",'<span class="pill r">Rào chắn</span>']],
        ["3%","38%","26%","20%","13%"],"font-size:23px;line-height:1.5")
    s.append(("12_De_xuat",page(12,4,"Hành động","Năm đề xuất, mỗi đề xuất gắn với một con số và một thử nghiệm",
        "Hai đề xuất đội nào cũng có thể nghĩ ra; <b>ba đề xuất còn lại chỉ thấy được khi nối các nguồn dữ liệu với nhau</b>.",
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:space-between">{recs}{mean("Lưu ý","Các con số là ước tính khi so với cửa hàng cùng loại, chưa phải kết quả chắc chắn. Mỗi đề xuất đều được thử nghiệm có đối chứng trước khi mở rộng.")}</div>')))

    # 13 Lộ trình
    phases=[("Tuần 0–2 · Chuẩn bị","Sửa cách ghi công cho thẻ · chọn 20 cửa hàng thử + 20 cửa hàng đối chứng","#14213D"),
            ("Tuần 3–14 · Thử nghiệm","Chăm sóc khách nhanh hơn · chia lại thời gian nhân viên ở 1 vùng · thử nhắc Tết với 10% khách trước Tết 2027","#004AAD"),
            ("Tuần 15–16 · Đánh giá","So cửa hàng thử với cửa hàng đối chứng: số hợp đồng và tỉ lệ trả trễ","#3D6FC0"),
            ("Quý sau · Mở rộng hoặc dừng","Mở rộng ra 268 cửa hàng nếu đạt mục tiêu","#8FAAD1")]
    tl='<div style="display:flex;gap:14px">'+"".join(f'<div style="flex:1;background:{c};color:#fff;border-radius:10px;padding:20px;min-height:250px"><div style="font-family:Oswald;font-size:28px;margin-bottom:6px">{h}</div><div style="font-size:23px;line-height:1.45">{t}</div></div>' for h,t,c in phases)+"</div>"
    road=f"""<div style="flex:1;display:flex;flex-direction:column;justify-content:space-between">{tl}{table(["Việc","Ai phụ trách","Đo bằng gì","Khi nào mở rộng / dừng"],[
["Chăm sóc khách nhanh hơn","Quản lý bán hàng vùng","Hợp đồng mỗi cửa hàng so với đối chứng","Mở rộng nếu tăng ≥ 5%"],
["Ghi công đúng","Bộ phận báo cáo / Tài chính","% thẻ đã ghi về cửa hàng bán","Xong khi 100% thẻ có cửa hàng bán"],
["Chia lại thời gian nhân viên","Vận hành bán hàng","Hợp đồng trên mỗi người thực có","Dừng nếu cửa hàng Aldi giảm quá mức dự báo"],
["Thử nhắc Tết (10%)","Bộ phận CRM","Tỉ lệ vay lại so với nhóm không nhắc","Chỉ mở rộng nếu cao hơn ≥ 2 điểm %"]],["24%","22%","30%","24%"],"font-size:23px;line-height:1.5")}
<div class="key" style="margin:0;text-align:center">Muốn biết cửa hàng còn lớn được bao nhiêu, hãy nhìn <b>số khách cửa hàng chưa chốt được</b>.</div></div>"""
    s.append(("13_Lo_trinh",page(13,4,"Hành động","Một quý để có câu trả lời: chuẩn bị, thử, đánh giá, rồi mới mở rộng",
        "Không cần đặt cược cả mạng lưới: <b>thử nhỏ, có đối chứng, có điều kiện dừng</b> rõ ràng.",road)))
    return s


def appendix()->list[tuple[str,str]]:
    a=[];n0=13
    def add(i,code,title,body):a.append((f"PL{i:02d}_{code}",page(n0+i,None,f"Phụ lục {i}",title,"",body,body_top=170)))
    gl=[["Khách tiềm năng (lead)","Khách đã có hợp đồng, được công ty xác định có nhu cầu thêm và giao cho cửa hàng chăm sóc"],
        ["Hợp đồng giải ngân","Hợp đồng đã được duyệt và giải ngân"],["Tỉ lệ chốt","Số hợp đồng giải ngân / số khách tiềm năng được giao"],
        ["Cửa hàng cùng loại","Cùng quy mô (nhỏ / vừa / lớn) và cùng mô hình (Aldi / Non-Aldi)"],["Nếu giữ nguyên (BAU)","Dự báo 3 tháng tới nếu không thay đổi gì"],
        ["Có thể đạt","Nếu chốt khách tốt như cửa hàng cùng loại khá (nhóm 25% tốt nhất); khoảng thấp–cao dùng nhóm trung bình và nhóm 10% tốt nhất"],
        ["Mức trần","Nếu chốt gần tối đa số khách đang có; chỉ là mức tham khảo nội bộ, không phải quy mô thị trường"],
        ["Người thực có","Thời gian nhân viên chia đều cho các cửa hàng họ phụ trách (1 / số cửa hàng)"],
        ["FHS / CES","Điểm sức khỏe tài chính / điểm gắn kết của khách, từ Vòng 2"],["Mã trung tâm 42902170","Mã ghi hợp đồng chung cho thẻ, vay tiền mặt; không phải cửa hàng thật"]]
    add(1,"Thuat_ngu","Giải thích thuật ngữ",f'<div style="flex:1">{table(["Thuật ngữ","Nghĩa"],gl,["26%","74%"],"font-size:21px")}</div>')
    add(2,"Trong_so_CES","Vòng 2: kiểm tra trọng số điểm gắn kết",
        f'<div class="left">{big("0,718 – 0,733","độ chính xác xếp hạng với 8 cách đặt trọng số khác nhau: gần như không đổi")}{mean("Thay đổi","Bỏ yếu tố \'lần giao dịch gần nhất\' vì trùng thông tin với \'tần suất\'. Trọng số mới: kênh số 25%, tần suất 31%, phản hồi 25%, độ rộng sản phẩm 19%.")}</div><div class="right">{chart(R2/"R2_01_CES_Weight_Evidence.png","8 cách đặt trọng số cho kết quả gần như nhau","Kiểm tra trên nửa số khách chưa dùng để tính trọng số.")}</div>')
    add(3,"Nguong_CES","Vòng 2: đặt ngưỡng chia nhóm theo kết quả thật",
        f'<div class="left">{big("≥ 44 điểm","nhóm cao: khả năng vay lại gấp 1,5 lần trung bình")}{big("< 17 điểm","nhóm thấp: dưới 2/3 mức trung bình","grey")}{mean("Kết quả","Nhóm cao vay lại 39%, nhóm thấp 6% (gấp 6,4 lần; ngưỡng cũ của Vòng 2 chỉ tách được 2,9 lần).")}</div><div class="right">{chart(R2/"R2_02_CES_Outcome_Anchored_Cutoffs.png","Tỉ lệ vay lại tăng đều theo điểm gắn kết","Nguồn: hồ sơ vay trong 6 tháng sau ngày chấm điểm Vòng 2.")}</div>')
    add(4,"FHS","Vòng 2: kiểm tra điểm sức khỏe tài chính",
        f'<div class="left">{big("0,084 vs 0,078","trọng số Vòng 2 tốt hơn trọng số chia đều khi dự báo trả trễ")}{big("Còn yếu","khả năng dự báo trả trễ trên dữ liệu mới thấp hơn nhiều so với Vòng 2","red")}{mean("Cách dùng","Dùng điểm này như một <b>rào chắn rủi ro</b>, không dùng để quyết định cho vay.")}</div><div class="right">{chart(R2/"R2_03_FHS_Out_of_Time_Weight_Check.png","So sánh các cách đặt trọng số","Nguồn: khoản vay giải ngân sau 5/6/2025, trả trễ trong 4 kỳ đầu.")}</div>')
    add(5,"Du_bao","Dự báo \"nếu giữ nguyên\" được chọn thế nào",
        f'<div class="left">{mean("Cách làm","So hai cách dự báo: lấy trung bình 3 tháng gần nhất và kẻ đường xu hướng. Kiểm tra bằng cách dự báo các quý đã qua rồi so với thực tế.")}{mean("Kết quả","Cách đơn giản (trung bình 3 tháng) không thua cách phức tạp, nên được chọn. Khoảng dao động dự báo được ghi kèm.")}</div><div class="right">{chart(T1/"T1_06_Rolling_Origin_Backtest.png","Kiểm tra dự báo trên các quý đã qua","Nguồn: Task 1.")}</div>')
    pc=[["Vay tiền mặt","61.798","1.021","1,7%"],["Thẻ tín dụng","41.550","4.538","10,9%"],["Vay mua xe máy","14.789","3.906","26,4%"],["Trả góp đồ gia dụng","43.010","17.194","40,0%"]]
    add(6,"Ti_le_chot","Tỉ lệ chốt khác nhau rất nhiều giữa các sản phẩm",
        f'<div class="left">{table(["Sản phẩm","Khách tiềm năng","Giải ngân","Tỉ lệ chốt"],pc,["36%","24%","20%","20%"],"font-size:20px")}{mean("Vì sao quan trọng","Nếu so tỉ lệ chốt chung, cửa hàng có nhiều khách vay tiền mặt sẽ luôn bị đánh giá thấp. Vì vậy nhóm so <b>từng sản phẩm, trong cùng loại cửa hàng</b>.")}</div><div class="right">{chart(CHARTS/"c08_ti_le_chot_san_pham.png","Khách trả góp tại quầy chốt được 40%, khách vay tiền mặt chỉ 1,7%","Cửa hàng vật lý, khách tiềm năng giao trong 7–9/2026.")}</div>')
    ev=[["Thẻ tín dụng","Mã trung tâm","3.769","89%","88%","ngay trong ngày"],["Thẻ tín dụng","Cửa hàng khác","301","94%","91%","ngay trong ngày"],
        ["Vay tiền mặt","Mã trung tâm","562","14%","20%","~12 ngày"],["Vay tiền mặt","Cửa hàng khác","362","81%","30%","~10 ngày"]]
    add(7,"Bang_chung_ghi_cong","Bằng chứng: thẻ bán ở cửa hàng nhưng ghi cho mã trung tâm",
        f'<div style="flex:1;display:flex;flex-direction:column;gap:20px"><div style="display:flex;gap:20px;flex:1">{big("73%","số thẻ giải ngân được ghi cho mã 42902170","red")}{big("3.900","nhân viên khác nhau cùng ghi hợp đồng vào mã này")}{big("89–94%","thẻ bị ghi nơi khác là do nhân viên cửa hàng gốc làm")}</div>{table(["Sản phẩm","Bị ghi cho","Số hợp đồng","Do nhân viên cửa hàng gốc làm","Ký trong 24 giờ","Thời gian trung vị"],ev,None,"font-size:23px")}{mean("Mã 42902170 là gì","Chỉ ghi thẻ, vay tiền mặt và một biến thể vay tiền mặt; khoảng 3.900 nhân viên khác nhau cùng dùng; chiếm 73% số thẻ và 48% số khoản vay tiền mặt giải ngân. Đây là mã ghi sổ chung, không phải một cửa hàng.")}</div>')
    sl=pd.read_csv(R3/"pilot_shortlist_top50.csv");sl=sl[sl.action.eq("TEST: lead follow-up SLA")].head(20)
    rows=[[f"{i+1}",str(r.shop),esc(str(r.province)),f"{r.current_3m:.0f}",f"{r.attainable_low:.0f} / {r.attainable_base:.0f} / {r.attainable_high:.0f}",f"{r.conversion_vs_peer*100:.0f}%"] for i,r in enumerate(sl.itertuples())]
    add(8,"Danh_sach_20","Danh sách 20 cửa hàng thử nghiệm",f'<div style="flex:1">{table(["#","Mã cửa hàng","Tỉnh / thành","Đang bán / quý","Có thể đạt (thấp / giữa / cao)","Tỉ lệ chốt so với cùng loại"],rows,["5%","16%","18%","15%","26%","20%"],"font-size:16.5px")}</div>')
    lim=["Các con số \"có thể đạt\" là ước tính khi so với cửa hàng cùng loại, chưa phải hiệu quả chắc chắn: phải thử nghiệm.",
         "2.051 cửa hàng được đánh giá chiếm 21% tổng hợp đồng; mã trung tâm và cửa hàng quá nhỏ không so được.",
         "Dữ liệu Vòng 3 chỉ chứa khoảng 32% hợp đồng của khách Vòng 2 trong cùng giai đoạn.",
         "\"Người thực có\" giả định nhân viên chia đều thời gian cho các cửa hàng họ phụ trách.",
         "Không dùng dữ liệu bên ngoài; mức trần chỉ là tham khảo nội bộ."]
    qa=[["Sao không dùng mô hình máy học?","Đề ưu tiên cách làm dễ giải thích; so với cửa hàng cùng loại dễ kiểm tra, và cách dự báo đơn giản không thua cách phức tạp."],
        ["Chốt kém có thể do khách xấu, không phải do cửa hàng?","Vì vậy nhóm so cùng sản phẩm, cùng loại cửa hàng, và thử nghiệm có cửa hàng đối chứng."],
        ["Mã trung tâm có phải cửa hàng online thật?","Mã này chỉ ghi thẻ và vay tiền mặt, có 3.900 nhân viên dùng, và 9/10 thẻ do nhân viên cửa hàng gốc làm ngay trong ngày."],
        ["Vòng 2 nói Tết, giờ nói không: tin cái nào?","Vòng 2 chỉ thấy khách dịp Tết; Vòng 3 thấy cả 21 tháng: không có đỉnh Tết và nhóm khách đó vay ít hơn."]]
    add(9,"Gioi_han_va_hoi_dap","Giới hạn và câu hỏi thường gặp",
        f'<div class="left" style="flex:0 0 42%"><div class="mean" style="flex:1"><b class="t">Giới hạn cần nói rõ</b><ul style="padding-left:22px">{"".join(f"<li>{x}</li>" for x in lim)}</ul></div></div><div class="right">{table(["Câu hỏi","Trả lời ngắn"],qa,["34%","66%"],"font-size:20px")}</div>')
    return a


def render(name,doc):
    HTML_DIR.mkdir(parents=True,exist_ok=True);PNG_DIR.mkdir(parents=True,exist_ok=True)
    src=HTML_DIR/f"{name}.html";src.write_text(doc,encoding="utf-8");out=PNG_DIR/f"Slide_{name}.png"
    subprocess.run([CHROME,"--headless=new","--disable-gpu","--hide-scrollbars","--force-device-scale-factor=1","--allow-file-access-from-files",
                    "--virtual-time-budget=6000","--window-size=1920,1080",f"--screenshot={out}",src.as_uri()],check=True,capture_output=True,timeout=120)
    return out


if __name__=="__main__":
    ch=charts()
    for name,doc in main_slides(ch)+appendix():print(render(name,doc).name)

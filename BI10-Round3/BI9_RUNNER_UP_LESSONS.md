# Bài học từ đội Á quân BI9 (Algomove) — áp dụng cho BI10 Round 3 (PARALLAX)

*Góc nhìn: một thành viên ban giám khảo vừa chấm tư duy kinh doanh (non-tech), vừa chấm kỹ thuật phân tích dữ liệu (tech/DA).*
*Nguồn đọc: `BI9 _ ROUND 03.pdf` (đề BI9 Round 3 "Eternal Monarch", 10 trang) và `Slide [BI9] Round 3 Algomove.pdf` (39 trang: 22 slide chính + 17 trang phụ lục).*

> Lưu ý về độ chính xác: phần lớn nhận xét dựa trên chữ trích ra từ PDF, cộng với ảnh render của 9 slide tiêu biểu. Một số lỗi chữ, ví dụ "Nghìn ỷ VĐ", có thể chỉ do quá trình trích xuất từ Canva chứ không phải lỗi của đội. Những điểm như vậy được ghi là *[cần xem bản gốc]*.

---

## 1. Hai đề bài: giống và khác nhau ở đâu

| | BI9 Round 3 — Eternal Monarch | BI10 Round 3 — PARALLAX |
|---|---|---|
| Doanh nghiệp | ITB, bán 3 dòng sản phẩm A, B, C (C là sản phẩm chủ lực) qua 4 kênh: Ecommerce, Website, Store, Premium | Công ty tài chính tiêu dùng, mạng lưới shop vật lý và online |
| Câu hỏi lõi | Kênh nào hiệu quả? Chọn **chiến lược A** (dồn vào online, cắt Store) hay **chiến lược B** (giữ Store, đầu tư A/B làm "mồi")? Kèm kế hoạch AOP 2026 và bộ KPI | **Shop nào còn dư địa tăng trưởng, cái gì đang giới hạn nó, nên dồn nguồn lực vào đâu?** |
| Mức độ "đóng" của đề | **Đóng**, có checklist rõ: kho dữ liệu chi phí, điểm hòa vốn (BEP) tuần/tháng/năm, tăng trưởng nếu đạt 130% BEP, chọn A/B, AOP, KPI chia 3 nhóm (Volume/Quality/Efficiency) có tỷ trọng, phân tích rủi ro | **Mở**: tự chọn phương pháp; bắt buộc tách **4 khái niệm** (Actual, BAU, Attainable, Ceiling); phải trả lời về độ tin cậy, độ bất định và cách kiểm chứng ngoài thực tế |
| Bẫy đề cài sẵn | Cảnh báo: bỏ A/B sẽ mất nguồn khách; bỏ Store sẽ mất thị phần | Shop ghi nhận hợp đồng chưa chắc là shop tạo ra cơ hội (lead bán chéo sang online) |
| Nộp bài | Deck và AOP | Deck không giới hạn số slide; slide đầu phải có dòng *"Visual supported by Canva"*; ZIP chứa SQL/Python; README nêu 5 điểm cho mỗi nguồn dữ liệu ngoài |
| Trình bày | — | 10 phút trình bày + 15 phút Q&A; **không công bố tiêu chí chấm** |

**Điểm chung quan trọng:** cả hai đều là vòng chung kết, *nối tiếp vòng 2*, cùng hỏi *"ban lãnh đạo nên phân bổ nguồn lực thế nào"*. Đều cần **một quyết định rõ ràng + kế hoạch hành động + KPI + rủi ro**, chứ không chỉ có phân tích.

---

## 2. Giải phẫu deck Algomove

### 2.1 Cấu trúc (22 slide chính)

| # | Phần | Nội dung | Kỹ thuật kể chuyện |
|---|---|---|---|
| 1 | Bìa | "Phân tích hiệu quả kênh phân phối và kế hoạch chiến lược" | — |
| 2 | **Bối cảnh** | Doanh thu và lợi nhuận ròng 2022→2024 tăng (biểu đồ cột) | **Mở bằng tin tốt** |
| 3 | **"Tuy nhiên…"** | Ba thách thức: nền tảng khách hàng suy yếu · chiến lược "mồi" thất bại · mất cân bằng mô hình kinh doanh. Mỗi thách thức một biểu đồ nhỏ | **Đảo chiều câu chuyện** (twist) |
| 4 | **Câu hỏi then chốt** | "Vậy ITB cần làm gì để kiểm soát, tối ưu chi phí và tạo tăng trưởng bền vững?" (một câu hỏi lớn, chiếm cả slide) | Đặt câu hỏi rõ ràng (chữ Q trong SCQ) |
| 5 | **Trả lời trước** | 4 trụ cột chiến lược | **Kết luận trước, bằng chứng sau** (kim tự tháp) |
| 6–7 | Vấn đề 1: khách hàng | Tỷ lệ rời bỏ (churn) 85%; giữ chân sau quý đầu chỉ 10–14% (heatmap cohort); tỷ lệ đơn thất bại 18.1%; khách mới giảm hơn 60% (2022→2024) | Số lớn (callout) + heatmap cohort |
| 8–9 | Vấn đề 2: chiến lược mồi | Tỷ lệ khách mua A/B rồi chuyển sang C giảm còn khoảng 12.8%; doanh thu B giảm khoảng 50%; ROI của A cao | Biểu đồ + kết luận "=> …" |
| 10–12 | Vấn đề 3: kênh | Biên đóng góp (CM ratio) Website 95.56% so với Store 81% / Ecommerce 74% / Premium 71%; chi phí cố định và hoa hồng chiếm khoảng 80% ở kênh offline; cơ cấu chi phí | Đặt các kênh cạnh nhau |
| 13 | **Cầu nối** | Sơ đồ: 3 vấn đề → 4 trụ cột | **Mỗi vấn đề nối thẳng tới một hành động** |
| 14–15 | Trụ cột 1: Website | Thiết kế lại trang, content hub, CRM; chuyển ≥60% ngân sách marketing sang digital; nhắm khách 25–34 tuổi; ưu đãi độc quyền | Hành động cụ thể, có con số |
| 16–17 | Trụ cột 2: kênh vật lý | **Đóng ≥30% cửa hàng trong 6–9 tháng theo 3 tiêu chí** (lỗ hoặc biên <5%; GMV <1.5 tỷ/năm; không bán C trong 6 tháng); tách Store (A/B) và Premium (C); hoa hồng theo lợi nhuận gộp; POS | **Tiêu chí định lượng để ra quyết định** |
| 18 | Trụ cột 3: danh mục | Chấm dứt chiến lược mồi; A thành "cash cow" độc lập; loại bỏ B (thanh lý trong 6–9 tháng) | Quyết định dứt khoát |
| 19 | Trụ cột 4: giữ chân | Đội hậu mãi riêng cho C; hạng thành viên Vàng/Bạc/Đồng; email/Zalo tự động | — |
| 20 | **Triển khai** | Biểu đồ Gantt theo quý Q1–Q4/2026, 6 nhóm hành động | Kế hoạch có thời gian cụ thể |
| 21 | **KPI** | Volume 40% / Quality 35% / Efficiency 25%; mỗi nhóm 3–4 KPI | Trả đúng yêu cầu của đề |
| 22 | Cảm ơn | — | — |
| PL 1–10 | Phụ lục biểu đồ | Đơn thất bại, biên lợi nhuận, chi phí, khách hàng theo kênh, chân dung khách C, **ma trận cơ hội theo khu vực/tuổi/nghề** | Đưa chi tiết ra sau |
| PL 11 | Bảng BEP | Chi phí cố định Website 20.7 tỷ; biên đóng góp 10.65 triệu/đơn; **BEP 1,944 đơn/năm (162/tháng, 37/tuần)**; 130% BEP = 2,527 đơn = 28.5 tỷ | Công thức minh bạch |
| PL 12–13 | Bảng hành động chi tiết theo từng trụ cột; nâng cấp dữ liệu (kho dữ liệu, dashboard) | | |
| PL 14–15 | **Mô phỏng tài chính 2 kịch bản** | Cơ sở: +6.8% lợi nhuận (6,519 tỷ); Lạc quan: +11.3% (6,793 tỷ). Tách từng tác động: bỏ B −403, đóng cửa hàng −50, tiết kiệm chi phí cố định +251/+293, hoa hồng +75/+93, Website +545/+759. **Có bảng công thức và giả định** (ROAS 5:1 / 6:1) | **Cầu nối tài chính** (waterfall dạng bảng) |
| PL 16–17 | KPI chi tiết | KPI · đơn vị · mục tiêu 2026 · *"ghi chú phản biện nhanh"*; định nghĩa và công thức từng KPI | Chuẩn bị sẵn cho Q&A |
| PL 18 | **Sổ rủi ro (risk register)** | Mã rủi ro · nguyên nhân · biện pháp · **bộ phận phụ trách · mốc thời gian** · trụ cột liên quan. Ví dụ: *ROAS < 3 thì dừng chiến dịch* | Rủi ro gắn với người chịu trách nhiệm |

### 2.2 Đặc điểm hình ảnh
- **Thanh điều hướng 7 bước** dưới mỗi slide (Bối cảnh → Xác định vấn đề → Vấn đề cốt lõi → Phân tích → Chiến lược đề xuất → Triển khai → Phân tích rủi ro), có chấm đánh dấu vị trí hiện tại. Người xem luôn biết mình đang ở đâu.
- **Tiêu đề là câu kết luận**, ví dụ: "Tuy nhiên, đằng sau kết quả tăng trưởng ấn tượng này lại tiềm ẩn…"; *"=> TẬP TRUNG NGUỒN LỰC BÁN SẢN PHẨM C TRÊN WEBSITE…"*.
- **Callout số rất lớn** (85%, 10–14%, 95.56%, 12.8%) ở mỗi slide vấn đề.
- Cột trái là nhãn chủ đề viết hoa (ví dụ "NỀN TẢNG KHÁCH HÀNG BỊ SUY YẾU") lặp lại ở các slide cùng phần, nên dễ nhóm ý.
- Bảng màu cam / xanh lá / xanh ngọc, thống nhất trong toàn deck.

---

## 3. Chấm điểm: góc nhìn Non-tech (kinh doanh và kể chuyện)

### ✅ Điểm mạnh
1. **Đường kể chuyện cổ điển nhưng hiệu quả:** tin tốt → "tuy nhiên" → câu hỏi → câu trả lời → bằng chứng → hành động → kiểm soát. Giám khảo không bao giờ bị lạc.
2. **Trả lời trước rồi mới chứng minh.** Slide 5 đã nêu 4 trụ cột; 15 slide sau chỉ để chứng minh và triển khai.
3. **Truy vết được từ vấn đề sang hành động** (slide 13): mỗi hành động trả lời một vấn đề đã chứng minh. Đây là thứ giám khảo kinh doanh tìm đầu tiên.
4. **Quyết định dứt khoát, có tiêu chí đo được.** "Đóng ≥30% cửa hàng" đi kèm **3 tiêu chí số**. Đề xuất như vậy thực thi được ngay, không phải lời khuyên chung chung.
5. **Từ chiến lược tới vận hành:** có Gantt theo quý, bộ phận phụ trách, KPI có mục tiêu, định nghĩa KPI, rủi ro kèm điểm dừng (ROAS < 3).
6. **Phủ đủ checklist của đề:** BEP, 130% BEP, chọn chiến lược, AOP, KPI chia 3 nhóm có tỷ trọng, rủi ro.
7. **Chuẩn bị cho Q&A ngay trong deck:** cột "ghi chú phản biện nhanh" ở bảng KPI, ví dụ *"Phản biện nếu bị hỏi A có còn vai trò không"*. Đây là thói quen rất đáng học.

### ⚠️ Điểm yếu
1. **Đi ngược cảnh báo của đề mà không phản biện trực diện.** Đề cảnh báo bỏ A/B sẽ mất nguồn khách và bỏ Store sẽ mất thị phần. Đội vẫn loại B và đóng 30% cửa hàng; có giảm nhẹ rủi ro (tách Store/Premium, giữ A) nhưng **không định lượng phần khách mới có thể mất**.
2. **Mô phỏng tài chính "lạc quan có hệ thống".** Các tác động cộng thẳng vào nhau; ROAS 5:1 và 6:1 là *giả định* không có dữ liệu chống lưng. Chỉ có 2 kịch bản, **không có kịch bản xấu**.
3. **Quá nhiều chữ ở phụ lục**, và slide 3 dồn 3 biểu đồ thu nhỏ đến mức gần như không đọc được.
4. **Không nói rõ độ tin cậy** của các con số.

---

## 4. Chấm điểm: góc nhìn Tech/DA (độ chặt của phân tích)

### ✅ Điểm mạnh
- **Cohort retention heatmap** theo quý: đúng công cụ cho bài toán giữ chân khách hàng.
- **Các chỉ số tài chính chuẩn:** CM ratio, BEP, ROI, ROAS, CAC, CLV, NPS. Có **bảng công thức**.
- **Ma trận cơ hội** theo khu vực, nhóm tuổi, nghề nghiệp (phụ lục).
- **Tách tác động trong mô phỏng tài chính** thành từng dòng, nên giám khảo kiểm lại được.

### ⚠️ Lỗ hổng kỹ thuật mà một giám khảo DA sẽ hỏi
1. **Biên lợi nhuận ròng 95.8% cho Website là phi thực tế.** Deck cũng lẫn hai khái niệm: "CM ratio 95.56%" và "biên lợi nhuận ròng 95.8%" xuất hiện cạnh nhau. → *Bài học: con số nào trông "quá đẹp" phải được kiểm tra tính hợp lý trước khi đưa lên slide.*
2. **Đơn vị và quy mô không khớp:**
   - Trục biểu đồ ghi "Nghìn tỷ VNĐ" nhưng chú thích lại ghi "tăng 1.5 tỷ" *[cần xem bản gốc]*.
   - BEP là 1,944 đơn/năm, trong khi mục tiêu KPI là ≥186,000 đơn Website: chênh nhau gần 100 lần mà không giải thích.
3. **Nhãn sai:** biểu đồ "tỷ lệ rời bỏ theo kênh" lại ghi trục là "Tỷ lệ ROI (%)".
4. **Định nghĩa churn có vấn đề với sản phẩm bền:** "không quay lại trong 90 ngày" sẽ cho churn rất cao *một cách tự nhiên* với sản phẩm cần lắp đặt, ít mua lại (như C). Con số 85% có thể chủ yếu phản ánh định nghĩa, không phải vấn đề kinh doanh.
5. **Bẫy cắt cụt (right-censoring) trong tỷ lệ chuyển đổi A/B → C:** cohort 2024 có ít thời gian để chuyển đổi hơn cohort 2022. Việc tỷ lệ "lao dốc" một phần là do thời gian quan sát ngắn hơn. *Đây chính là cái bẫy đội mình đã gặp ở vòng 2* (nhãn trễ hạn bị cắt từ 20/01/2025).
6. **Quy nhân quả quá nhanh:** từ "tỷ lệ chuyển đổi giảm" suy ra "chiến lược mồi thất bại", trong khi chưa loại trừ các yếu tố gây nhiễu (giá, cạnh tranh, mùa vụ, thay đổi cơ cấu kênh).
7. **Không có kiểm định hay độ bất định:** không backtest dự báo, không khoảng tin cậy, không phân tích độ nhạy ngoài 2 kịch bản.

> **Giả thuyết vì sao Algomove đạt Á quân mà không phải Quán quân** [GIẢ THUYẾT]: thắng nhờ **câu chuyện mạch lạc, quyết đoán và trả lời đủ đề**; thua điểm ở **độ chặt kỹ thuật** (con số phi thực tế, đơn vị lệch, giả định tài chính không có căn cứ). Với BI10 Round 3, đề **nhấn mạnh rõ** *"reliability and uncertainty"* và *"how your recommendations could be validated"*. Tức là ban tổ chức đã nâng trọng số đúng ở chỗ Algomove yếu.

---

## 5. Những gì nên học, những gì nên tránh

| Học theo | Tránh |
|---|---|
| Mở bằng tin tốt → "tuy nhiên" → câu hỏi → câu trả lời | Con số "quá đẹp" mà chưa kiểm tra tính hợp lý |
| Trả lời trước (slide 2–3), bằng chứng sau | Lẫn khái niệm (CM ratio ≠ biên lợi nhuận ròng; BAU ≠ Actual) |
| Slide cầu nối "vấn đề → hành động" | Đơn vị và quy mô không khớp giữa các slide |
| Tiêu chí số để ra quyết định (ngưỡng chọn shop) | Định nghĩa chỉ số không hợp với bản chất sản phẩm |
| Gantt hoặc lộ trình + bộ phận phụ trách + KPI + điểm dừng | Nhân quả từ tương quan; quên bẫy cắt cụt khi so cohort |
| Mô phỏng tác động dạng bảng tách từng dòng, có công thức | Cộng thẳng các tác động; thiếu kịch bản xấu |
| Cột "ghi chú phản biện nhanh" cho Q&A | Dồn nhiều biểu đồ nhỏ không đọc được vào một slide |
| Thanh điều hướng tiến độ ở mọi slide | Đi ngược cảnh báo của đề mà không định lượng cái giá phải trả |

---

## 6. Áp dụng vào BI10 Round 3 của đội

Các con số dưới đây lấy từ `output/FLOW_AND_INSIGHTS.md` (branch `Lu`, đã gộp vào `main`). **Chưa được kiểm chứng độc lập; phải đối chiếu lại trước khi lên slide.**

### 6.1 Ghép khung Algomove với nội dung của đội

| Khung Algomove | Phiên bản BI10 R3 của đội |
|---|---|
| **Tin tốt** | Mạng lưới đang tăng, nhiều shop trông "đều doanh số" |
| **"Tuy nhiên…" — 3 vấn đề** | (1) **Ghi công sai:** mã trung tâm 42902170 ghi nhận 28% hợp đồng đã giải ngân; 89–94% thẻ ghi dưới mã này thực chất do nhân viên shop vật lý bán. (2) **Khoảng trống thực thi:** 268 shop chuyển đổi lead dưới 0.8× nhóm tương đồng *cùng sản phẩm*, chiếm một nửa dư địa (+2.8K / +5.5K). (3) **Phân bổ nhân sự sai đơn vị:** shop non-Aldi nhận 0.6 FTE agent nhưng tạo 48 hợp đồng/FTE, so với Aldi 3.0 FTE và 10 hợp đồng/FTE |
| **Câu hỏi then chốt** | Đúng câu của đề: *"Hai shop cùng doanh số, làm sao biết shop nào còn dư địa?"* |
| **Trả lời trước** | 3–4 trụ cột: Sửa ghi công · Pilot cải thiện theo dõi lead · Phân bổ lại thời gian agent · Rào chắn chất lượng (không đẩy doanh số ở shop có nhiều khách PROTECT) |
| **Bằng chứng** | **Cặp shop A/B làm xương sống:** 74 vs 77 hợp đồng; 661 vs 50 lead; chuyển đổi 0.64× vs 1.22×; Attainable 102–137 vs 78–100; Ceiling 203 vs 104. *Một biểu đồ 4 khái niệm cho mỗi shop* |
| **Tiêu chí quyết định** | Tiêu chí chọn shop pilot: có trong danh mục shop, ≥15 hợp đồng/3 tháng, số lead ≥ trung vị nhóm, chuyển đổi <0.8× nhóm cùng sản phẩm, không thuộc nhóm QUALITY |
| **Gantt** | Pilot 20 shop có nhóm đối chứng → đánh giá sau 1 chu kỳ → quyết định mở rộng hoặc dừng |
| **Mô phỏng tác động** | Thấp / cơ sở / cao: +0.6K / 1.0K / 1.5K hợp đồng tại 20 shop. **Thêm kịch bản xấu (0)** và ghi rõ công thức (lead × (tỷ lệ chuyển đổi của nhóm tương đồng − tỷ lệ hiện tại) × tỷ lệ shop tự ghi nhận) |
| **KPI 3 nhóm** | Volume: hợp đồng giải ngân tại shop (và tính theo shop tạo lead). Quality: tỷ lệ khách PROTECT, tỷ lệ trễ hạn khoản mới. Efficiency: chuyển đổi lead so với nhóm cùng sản phẩm, hợp đồng/FTE agent |
| **Sổ rủi ro** | Rủi ro · nguyên nhân · biện pháp · bộ phận phụ trách · mốc thời gian · điểm dừng (ví dụ: dừng pilot nếu chuyển đổi không vượt nhóm đối chứng sau 1 chu kỳ) |
| **Ghi chú phản biện nhanh** | Lấy từ cột "Strongest objection and our answer" có sẵn trong `FLOW_AND_INSIGHTS.md` |

### 6.2 Những điểm đội làm tốt hơn Algomove (nên nhấn mạnh)
- **Kiểm định ngoài thời gian và tự kiểm chứng:** đề xuất "nhắc Tết" của vòng 2 bị chính dữ liệu vòng 3 bác bỏ (2.1% so với 4.3%). Algomove không có bước tự kiểm chứng như vậy.
- **So sánh trong cùng sản phẩm:** tránh được lỗi so tỷ lệ thô giữa lead CL (khoảng 2%) và lead CD (khoảng 40%).
- **Có mức thấp / cơ sở / cao và độ bền danh sách** (80% top 20 giữ nguyên ở p50, 50–55% ở p90).
- **Nêu thẳng giới hạn:** chỉ 21% hợp đồng được đánh giá; trần chỉ là trần nội bộ, không phải quy mô thị trường.

### 6.3 Cái bẫy Algomove đã sa vào mà đội có nguy cơ lặp lại
1. **Lẫn khái niệm:** BAU đang bằng Actual với hầu hết shop (`bau_3m = current_3m` khi thiếu dự báo). Phải ghi rõ: *"BAU = trailing baseline; validated trend models did not beat it"*. Đề yêu cầu 4 khái niệm **không được dùng lẫn**.
2. **Bẫy cắt cụt:** lead giao cuối tháng 9 chưa đủ thời gian để chuyển đổi trong cửa sổ 07–09/2026. Shop nhiều lead CL (chuyển đổi chậm, trung vị 10–12 ngày) có thể bị đánh giá oan là "EXECUTION". *Nên kiểm tra trước khi đưa lên slide.*
3. **Con số "quá đẹp":** 48 so với 10 hợp đồng/FTE phụ thuộc giả định *agent chia đều thời gian cho các shop*. Phải ghi giả định ngay trên slide.
4. **Nhân quả:** pilot là *giả thuyết cần kiểm chứng*, không phải tác động đã chứng minh. Giữ đúng cách viết của `FLOW_AND_INSIGHTS.md`.
5. **Đơn vị:** thống nhất một đơn vị duy nhất (hợp đồng giải ngân trong 3 tháng, tính tại shop ghi nhận) trên mọi slide; khi dùng đơn vị khác (theo shop tạo lead) phải ghi rõ.

### 6.4 Gợi ý thứ tự slide (khoảng 16 slide chính + phụ lục)
1. Bìa (bắt buộc có dòng *"Visual supported by Canva"*).
2. Executive Summary theo khung SCQA, 3 con số lớn.
3. Vòng 2 → vòng 3 (ngắn): khách hàng được hiểu thế nào; tự kiểm chứng "nhắc Tết" bị bác bỏ.
4. Dữ liệu và độ tin cậy: độ phủ 16.5% / 21%, quy tắc ghép lead, các bẫy dữ liệu.
5. **"Tuy nhiên…"**: 3 vấn đề trên một slide (mỗi vấn đề một số lớn).
6. Câu hỏi then chốt + trả lời trước (các trụ cột).
7. Vấn đề 1: ghi công sai cho shop (R3_01).
8. Cặp shop A/B: cùng doanh số, khác tiềm năng (R3_02/R3_03).
9. 4 khái niệm của cặp shop (biểu đồ chính) + cách tính.
10. Ràng buộc trên toàn mạng lưới (R3_04): EXECUTION chiếm một nửa dư địa.
11. Nhân sự: thời gian agent (R3_06).
12. Ưu tiên và độ bền danh sách (R3_05) + tiêu chí chọn shop.
13. Slide cầu nối: vấn đề → hành động.
14. Khuyến nghị và lộ trình (Gantt pilot, bộ phận phụ trách, điểm dừng).
15. Mô phỏng tác động 4 kịch bản (xấu / thấp / cơ sở / cao) + KPI 3 nhóm.
16. Giới hạn và cách kiểm chứng ngoài thực tế (đề hỏi trực tiếp).
- **Phụ lục:** sổ rủi ro, định nghĩa KPI, công thức, kiểm định Task 1 (backtest), sổ giả định, nguồn dữ liệu ngoài (nếu có).

### 6.5 Checklist trước khi nộp (16:00)
- [ ] Slide 1 có dòng *"Visual supported by Canva"*; deck tiếng Anh, PDF 16:9; tên file `[TeamName_LeaderName_R03_BI10_Slide]`.
- [ ] 4 khái niệm định nghĩa riêng biệt, không dùng lẫn; BAU nói rõ là trailing baseline.
- [ ] Mọi con số trên slide khớp với file output; một đơn vị thống nhất.
- [ ] Mỗi biểu đồ có tiêu đề dạng câu kết luận và chú thích nguồn.
- [ ] Có slide về độ bất định và cách kiểm chứng (pilot có nhóm đối chứng).
- [ ] ZIP chứa toàn bộ Python/SQL + README (5 điểm cho mỗi nguồn dữ liệu ngoài, nếu dùng); tên `[TeamName_LeaderName_R03_BI10_Attachments]`.
- [ ] Chuẩn bị sẵn 5 câu hỏi phản biện kèm câu trả lời cho phần Q&A 15 phút.

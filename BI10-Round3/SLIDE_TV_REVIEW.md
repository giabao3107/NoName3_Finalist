# Review deck tiếng Việt (22 slide): góc nhìn senior DA khó tính

*Phạm vi: 13 slide chính và 9 slide phụ lục trong `SLIDE TV/`.*

*Cách kiểm tra: mọi con số trên slide được đối chiếu với `output/Customer_to_Shop_Growth/customer_to_shop_report.json`, `shop_growth_priority.parquet`, `output/R2_Customer_Foundation/r2_revision_report.json` và `Code/5. Customer-to-Shop Growth and Prioritization.py`.*

*Nhãn dùng trong file:*
- *[DỮ LIỆU]: số tính trực tiếp từ output.*
- *[ƯỚC TÍNH]: phép tính tay dựa trên output.*
- *[GIẢ THUYẾT]: điều cần kiểm tra thêm.*

---

## 0. Kết luận nhanh

- **Hình thức và luồng kể chuyện:** rất tốt, đã áp dụng gần đủ bài học từ Algomove.
- **Số liệu:** khớp output gần như 100%.
- **Logic:** có **4 điểm vỡ** mà một giám khảo DA sẽ bắt được trong phần Q&A 15 phút. Nặng nhất là **câu chuyện cặp cửa hàng A/B mâu thuẫn với chính slide 4**, và **kết luận "không thiếu khách" là do cách đo tạo ra, không phải phát hiện từ dữ liệu**.
- Phần lớn có thể sửa bằng **câu chữ** trong khoảng 30–45 phút. Chỉ một lỗi (mức trần bị tính trùng) cần sửa code.

---

## 1. Những gì đang TỐT (giữ nguyên)

| # | Điểm tốt | Slide |
|---|---|---|
| 1 | **Trả lời trước, chứng minh sau.** Slide 2 có 4 con số lớn và 5 đề xuất; slide 3 đặt 4 câu hỏi, mỗi câu có sẵn đáp án và số slide tương ứng. Giám khảo không bao giờ bị lạc. | 2, 3 |
| 2 | **Thanh điều hướng 4 bước** (Bối cảnh → Đo tiềm năng → Điều gì cản trở → Hành động) khớp đúng với các task của đề. | tất cả |
| 3 | **Mỗi slide cùng một "ngữ pháp"**: nhãn phần → tiêu đề là câu kết luận → thanh tối nói "vậy thì sao" → số lớn → biểu đồ → ô "Ý nghĩa" → chú thích nguồn. Người không chuyên đọc rất nhanh. | tất cả |
| 4 | **Ý chính được lặp ở đầu, giữa và cuối deck**: "hãy nhìn số khách tiềm năng chưa chốt được" xuất hiện ở slide 2, 7 và 13. | 2, 7, 13 |
| 5 | **Cặp cửa hàng A/B trả lời trực tiếp câu hỏi lõi của đề**, và cửa hàng A xuất hiện lại trong danh sách thử nghiệm (dòng 7, slide 11), nên câu chuyện liền mạch. | 7, 11 |
| 6 | **Bẫy so khác sản phẩm được giải thích bằng ngôn ngữ thường** (vay tiền mặt chốt khoảng 2%, trả góp tại quầy khoảng 40%). Đây là bẫy kỹ thuật lớn nhất của bộ dữ liệu, và đội đã xử lý đúng. | 6, PL6 |
| 7 | **Phát hiện ghi công cho mã trung tâm** là insight thật sự khác biệt, có chuỗi bằng chứng: mã nhân viên xử lý + thời gian ký trong 24 giờ + so sánh giữa sản phẩm. | 4, PL7 |
| 8 | **Trung thực**: ghi rõ "ước tính", có khoảng thấp–cao, có rào chắn rủi ro, có slide giới hạn, có slide FAQ, và **tự bác bỏ đề xuất "nhắc Tết" của vòng 2**. | 12, PL4, PL9 |
| 9 | **Lộ trình có người phụ trách, cách đo và điều kiện dừng**. Đây là thực hành tốt nhất của Algomove, đội đã làm được. | 13 |
| 10 | **Số khớp output** [DỮ LIỆU]: 87.445 / 88.034 / 93.499 / 115.882; dư địa 2.813 + 2.143 + 221 + 200 + 88 = 5.465; 268 + 753 + 25 + 510 + 495 = 2.051; top 20 = 578 / 970 / 1.463; nhân sự 0,61 / 3,01 FTE; AUC 0,718–0,733; Gini 0,059–0,100; tỷ lệ vay lại 34 / 13 / 12 / 8%; tỷ lệ trả trễ 30,3 so với 24,1%; độ phủ 32%; 23 cửa hàng; độ bền danh sách 80%. | — |

---

## 2. Đối chiếu với bài học từ Algomove (`BI9_RUNNER_UP_LESSONS.md`)

| Bài học | Trạng thái | Ghi chú |
|---|---|---|
| Trả lời trước, chứng minh sau | ✅ | Slide 2–3 |
| Thanh điều hướng | ✅ | |
| Tiêu đề là câu kết luận + số lớn | ✅ | |
| Slide nối vấn đề → hành động | ⚠️ một phần | Cột "Vì sao" ở slide 12 có làm, nhưng chưa có slide nối riêng |
| Tiêu chí số để chọn | ✅ | Slide 11 (chưa tô đậm tiêu chí) |
| Lộ trình + người phụ trách + điều kiện dừng | ✅ | Slide 13 |
| Bảng tác động **có công thức** | ❌ | Chưa có công thức gap = leads × (tỷ lệ chốt của nhóm tương đồng − tỷ lệ của cửa hàng) × tỷ lệ cửa hàng tự ghi nhận |
| Kịch bản xấu | ❌ | Chỉ có thấp / giữa / cao, cả ba đều giả định đóng **toàn bộ** khoảng cách |
| Sổ rủi ro | ❌ | Mới có điều kiện dừng, chưa có danh sách rủi ro (Aldi giảm, gian lận ghi công, khách xấu tăng) |
| Chi phí hoặc nỗ lực của từng đề xuất | ❌ | Đề có nói "nguồn lực có hạn" nhưng deck không nêu chi phí |
| Chuẩn bị sẵn cho Q&A | ✅ | Slide PL9 (mới có 4 câu, xem mục 6) |
| **Tránh lỗi của Algomove**: lẫn khái niệm, số "quá đẹp", nhân quả quá nhanh | ⚠️ | Mắc 3 lỗi tương tự, xem mục 3 |

---

## 3. Lỗi NGHIÊM TRỌNG: phải sửa trước 16:00

### C1. Cặp A/B "bán bằng nhau" mâu thuẫn với chính slide 4 (slide 7)

- **Vấn đề:** Slide 4 nói *"Trước khi so sánh cửa hàng, cần biết hợp đồng được ghi ở đâu"*. Nhưng slide 7 lại so A và B bằng số hợp đồng **ghi tại cửa hàng**, đúng cái thước mà slide 4 vừa nói là sai.
- **Số liệu** [DỮ LIỆU]:
  - Cửa hàng A tạo ra thêm **92 hợp đồng bị ghi ở nơi khác** (55% hợp đồng từ khách tiềm năng của A). Tính theo nơi tạo ra khách, A = 74 + 92 = **166**.
  - Cửa hàng B = 77 + 4 = **81**.
  - Như vậy, nếu áp dụng đề xuất số 2 của chính đội, **A lớn gấp đôi B**.
- **Hệ quả:** giám khảo hỏi *"Nếu ghi công đúng như các bạn đề xuất thì hai cửa hàng còn 'bán bằng nhau' không?"* thì câu chuyện chính sụp đổ.
- **Cách sửa (biến lỗi thành điểm mạnh, và khớp đúng tên vòng PARALLAX):** cùng một cửa hàng, nhìn từ 3 góc thì ra 3 con số khác nhau:
  1. **Góc sổ sách** (ghi tại cửa hàng): A 74 = B 77.
  2. **Góc ghi công đúng** (tính theo nơi tạo ra khách): A **166** so với B 81.
  3. **Góc tiềm năng** (chốt như nhóm 25% tốt nhất cùng loại): A thêm +47 tại cửa hàng (và thêm khoảng +90 bị ghi nơi khác), B thêm +6.

  Ghi rõ đơn vị của từng góc. Câu chuyện mới mạnh hơn: *"Cửa hàng A vừa bị đánh giá thấp vì ghi công sai, vừa chốt kém hơn cửa hàng cùng loại, nên đây là nơi đáng đầu tư nhất."*
- **Chuẩn bị thêm:** về tỷ lệ chốt thô, A đạt **21,2%**, cao hơn B (**12%**). A chỉ kém khi so **cùng sản phẩm** (0,64 lần nhóm tương đồng). Còn con số 1,22 lần của B chỉ dựa trên **6 hợp đồng chốt từ 50 khách tiềm năng**, nên rất nhiễu.

### C2. "Cửa hàng không thiếu khách" là do cách đo tạo ra, không phải phát hiện (slide 9, 2)

- **Vấn đề:** mô hình "Có thể đạt" chỉ có 2 đòn bẩy:
  - chốt khách tiềm năng **đang có** tốt hơn;
  - kích hoạt lại khách GROW.

  Mô hình **không có đòn bẩy nào cho khách mới**. Vì vậy các cửa hàng ít khách tiềm năng (DEMAND) **chắc chắn** có dư địa nhỏ. Con số "+88" là hệ quả của công thức, không phải bằng chứng.
- **Số liệu** [DỮ LIỆU]:
  - Hợp đồng đến từ khách tiềm năng chỉ chiếm **15,6%** doanh số của 2.051 cửa hàng được đánh giá; trung vị mỗi cửa hàng là **6,7%**.
  - Trong dư địa +5,5K, đòn bẩy khách tiềm năng chiếm 77%, đòn bẩy GROW 23% (và chỉ có ở **108 cửa hàng**), khách mới chiếm **0%**.
  - Cửa hàng B có 77 hợp đồng nhưng chỉ **2** hợp đồng đến từ khách tiềm năng. Nói "B gần chạm trần" thực chất có nghĩa là "mô hình không nhìn thấy dư địa của B".
- **Lưu ý thêm:** theo định nghĩa ở PL1, "khách tiềm năng" là *khách đã có hợp đồng* (bán chéo). Nhóm "Thiếu khách tiềm năng" vì vậy phản ánh **cách công ty giao lead**, không phải nhu cầu thị trường.
- **Cách sửa:**
  - Đổi tiêu đề slide 9 thành: *"Trong phần dư địa đo được, một nửa nằm ở khâu chốt khách tiềm năng"*.
  - Thêm một dòng giới hạn: *"Mô hình đo dư địa bán chéo (khoảng 16% doanh số); dư địa khách mới vãng lai cần dữ liệu thị trường"*.
  - Đổi tên DEMAND thành "Được giao ít khách tiềm năng".
  - Ý chính ở slide 2 và 13 nên thêm phạm vi: *"…số khách tiềm năng chưa chốt được, phần dư địa đo được rõ nhất"*.

### C3. "Mức trần" bị tính trùng hợp đồng đã chốt (slide 6, 7, code dòng 198 và 219)

- **Vấn đề:** `ceiling_internal = BAU + leads × q90 × own_share + …`. BAU **đã bao gồm** các hợp đồng chốt từ khách tiềm năng, rồi công thức cộng thêm *toàn bộ* khách tiềm năng × q90. Như vậy là tính trùng. Phần "Có thể đạt" thì không bị lỗi này vì dùng (q − tỷ lệ hiện tại).
- **Số liệu** [ƯỚC TÍNH từ parquet]:
  - Mức trần của 2.051 cửa hàng: **115,9K → khoảng 102,5K** (−12%).
  - Mức trần của A: **203 → khoảng 155**.
- **Cách sửa trong code:** thay bằng `ceiling_leads = (leads*max(q90,conv) - lead_funded).clip(0) * own_share`, hoặc tương đương. Sau đó chạy lại script 5.
- **Nếu không kịp sửa code:** ghi chú *"trần tham khảo, có thể cao hơn thực tế"* và không dùng con số 203 để kể chuyện.
- Nhãn "chốt gần tối đa" cũng sai về nghĩa; đúng là "nếu mọi sản phẩm chốt bằng nhóm 10% tốt nhất".

### C4. Slide 5 (Tết) tự mâu thuẫn với chính biểu đồ của nó và với PL5

- **Mâu thuẫn 1** [DỮ LIỆU]:
  - **Tháng 01/2025 = 202K là tháng cao nhất trong 21 tháng**, cao hơn trung bình khoảng 180K là +12,5%. Đây chính là tháng trước Tết 2025, và đội đã tô vàng cột này.
  - Tiêu đề lại nói "không có đỉnh Tết". Giám khảo nhìn vào là thấy ngay.
- **Mâu thuẫn 2:** câu "**một quý là đủ** để đánh giá một cửa hàng" trái với PL5. Sai số dự báo một quý ở cấp cửa hàng là **WAPE 26–56%**.
- **Bằng chứng tốt hơn đang bị bỏ qua:**
  - Nhóm 392K khách mà vòng 2 định nhắc: chỉ **2,1%** nộp hồ sơ trước Tết 2026, so với **4,3%** của các khách khác (`tet26_application_rate`).
  - Đây là phép thử trực tiếp nhất, nhưng không có trên slide.
- **Cách sửa:**
  - Tiêu đề: *"Đỉnh trước Tết 2025 không lặp lại năm 2026; nhóm khách 'Tết' của vòng 2 chỉ quay lại 2,1%"*.
  - Bỏ câu "một quý là đủ". Thay bằng lập luận đúng: *"so sánh các cửa hàng **trong cùng một quý** thì cùng chịu một mùa vụ, nên vẫn công bằng"*.
  - **Nên chuyển slide 5 (cùng slide 8) thành một slide "Nền tảng từ vòng 2"**, vì đề yêu cầu trình bày R2 ngắn gọn như nền tảng.

### C5. Con số lợi ích của pilot không khớp điều kiện thành công, và thiết kế đối chứng có rủi ro (slide 2, 11, 12, 13)

- **Lợi ích được hứa quá cao so với ngưỡng thành công** [DỮ LIỆU]:
  - 20 cửa hàng hiện bán **1.839** hợp đồng/quý.
  - Lợi ích ghi trên slide: +578 / +970 / +1.463, tương đương **+31% / +53% / +80%**.
  - Điều kiện mở rộng ở slide 13 lại là **≥ 5%**.
  - Nếu tin vào +31% thì ngưỡng 5% quá dễ. Nếu ngưỡng 5% mới là thực tế thì con số +600–1.500 là phóng đại.
  - Cả ba mức đều giả định **đóng 100% khoảng cách trong 1 quý**.
- **Bẫy hồi quy về trung bình** [GIẢ THUYẾT]: 20 cửa hàng được chọn vì chốt **kém nhất**, nên quý sau tự nhiên sẽ khá lên, kể cả khi không làm gì. Nếu nhóm đối chứng chọn khác cách thì pilot sẽ "thành công giả".
- **Có thể do quá tải** [DỮ LIỆU]:
  - 20 cửa hàng này có **115–694 khách tiềm năng**, so với trung vị nhóm tương đồng **36–37** (gấp 3–19 lần).
  - "Chốt kém" có thể là **quá tải**, không phải kém kỹ năng. Điều này nối thẳng với đề xuất 3 (thời gian nhân viên).
  - Cửa hàng A có 1,0 FTE, trong khi B có 2,4 FTE.
- **Nhiễu lớn** [GIẢ THUYẾT]: sai số một quý ở cấp cửa hàng là 26–56%, lớn hơn nhiều so với ngưỡng 5%. Với 20 so với 20 cửa hàng, cần tính cỡ mẫu trước khi cam kết.
- **Cách sửa:**
  - Ghi rõ +600–1.500 là "**nếu đóng toàn bộ khoảng cách**" (mức tối đa), và thêm kịch bản xấu bằng 0.
  - Chọn 40 cửa hàng đủ điều kiện, sau đó **chia ngẫu nhiên 20 thử, 20 đối chứng**.
  - Đo theo kiểu so sánh chênh lệch trước–sau giữa hai nhóm (difference-in-differences).
  - **Gộp đề xuất 1 và 3 thành một nhánh thử nghiệm** ("thêm thời gian nhân viên cho cửa hàng nhiều khách tiềm năng"), tránh chạy nhiều can thiệp chồng nhau trên cùng cửa hàng rồi không biết cái nào có tác dụng.

### C6. Lộ trình "một quý" thực tế là 16 tuần, và tỷ lệ trả trễ chưa đo được vào tuần 15–16 (slide 13)

- Tuần 0–16 tương đương khoảng 4 tháng, không phải 1 quý.
- Tỷ lệ trả trễ được định nghĩa là trễ ở **4 kỳ trả đầu tiên**. Khoản vay giải ngân ở tuần 3–14 chưa có đủ 4 kỳ vào tuần 16.
- **Cách sửa:** đo chỉ báo sớm (trễ kỳ đầu tiên), hoặc thêm một mốc đánh giá rủi ro ở tháng thứ 6.

### C7. Con số 28% và "9/10 thẻ" bị nói quá (slide 2, 4)

- **28%** là tỷ lệ của **toàn bộ** hợp đồng ghi cho mã trung tâm, không phải "thẻ bán tại cửa hàng".
- Tỷ lệ **89%** chỉ áp dụng cho **3.769 thẻ truy được về khách tiềm năng của cửa hàng**, không phải mọi thẻ ở mã trung tâm.
- Với 2.051 cửa hàng được đánh giá, phần hợp đồng bị ghi nơi khác là **3.909 hợp đồng = 4,3%** doanh số tính theo nơi tạo ra khách. Chỉ **23 cửa hàng** bị ghi thiếu ≥ 20% [DỮ LIỆU].
- **Cách sửa câu chữ:** *"Trong các thẻ truy được về cửa hàng tạo khách, 89% do chính nhân viên cửa hàng đó làm, ngay trong ngày"*.
- **Nên thêm phép so sánh nội bộ:** vay tiền mặt ghi ở mã trung tâm chỉ có **14%** do nhân viên cửa hàng gốc làm. Điều này chứng minh con số 89% không phải do danh sách gán nhân viên quá rộng.

### C8. Slide nhân sự: con số "gấp 5 lần" sinh ra từ giả định, không phải đo được (slide 10)

- **Số liệu** [DỮ LIỆU]: trung vị hợp đồng mỗi cửa hàng là **28 ở cả Aldi và Non-Aldi**. Vì vậy 48 so với 10 hợp đồng/người chỉ là 28/0,61 so với 28/3,01. "Gấp 5 lần" đúng bằng tỷ lệ FTE, tức là **hệ quả của giả định**, không phải năng suất đo được.
- **Mâu thuẫn trên slide:** ghi "Aldi: 14 cửa hàng/người", nhưng nếu 5 người được gán × 1/14 thì chỉ được 0,36, không phải 3. Lý do: 14 là trung bình cộng, bị kéo lên bởi vài người chạy rất nhiều cửa hàng.
- **Danh sách gán nhân viên rất rộng:** mỗi cửa hàng có 26–39 người được gán (A: 31, B: 39). File `emp_2_salesroom` có thể chỉ là danh sách quyền truy cập, không phải lịch làm việc thật [GIẢ THUYẾT].
- **Năng suất trung bình khác năng suất biên:** chuyển người sang Non-Aldi chưa chắc mỗi người cũng làm ra 48 hợp đồng.
- **Cách sửa:**
  - Bỏ con số "14".
  - Tiêu đề nên là *"Giả thuyết: …"*.
  - Ở slide 2, con số "0,6 người" cũng phải kèm chữ "ước tính theo giả định chia đều".

---

## 4. Lỗi TRUNG BÌNH

| # | Slide | Vấn đề | Số liệu | Sửa |
|---|---|---|---|---|
| M1 | 8, 9, 12 | Rào chắn "25 cửa hàng nhiều khách khó trả nợ" rất mong manh | Trung vị chỉ **39 khách liên kết**/cửa hàng, tức khoảng 4 khách PROTECT. [ƯỚC TÍNH, nhị thức] Với tỷ lệ chung 3,9%, khoảng **12 trong 176** cửa hàng sẽ vượt ngưỡng chỉ do ngẫu nhiên. Tỷ lệ trả trễ 30,3% so với 24,1% chỉ dựa trên 1.931 khách PROTECT có khoản vay đủ tuổi. FHS Gini 0,08–0,10. | Nói rõ đây là "cờ cần xem xét", không phải kết luận. Bỏ +221 khỏi tổng "+5.500 có thể tăng" vì đội đã quyết định không đẩy doanh số ở đây |
| M2 | 8 | Câu "khách tốt mà vẫn trả trễ 24%" sẽ khiến giám khảo giật mình | `late_after` của nhóm GROW = 24,1% | Định nghĩa rõ: "trễ ít nhất 1 ngày ở bất kỳ kỳ nào trong 4 kỳ đầu" |
| M3 | 8 | Slide khách hàng đặt nhầm phần "Điều gì cản trở", và độ phủ ở cấp cửa hàng rất mỏng | Chỉ **176 / 2.051** cửa hàng có ≥ 30 khách vòng 2 liên kết (trung vị là 6) | Chuyển sang slide "Nền tảng từ vòng 2" (gộp với Tết) |
| M4 | PL2 | Biểu đồ tô đậm "Learned" nhưng trọng số thực dùng là "Round 2 bỏ recency" (25 / 31 / 25 / 19), chọn trên nửa dữ liệu huấn luyện | `final_rule` trong report | Tô đậm đúng cột đang dùng. Panel trái đang hiện trọng số learned (độ rộng sản phẩm 40%), mâu thuẫn với chữ bên cạnh |
| M5 | PL3 | "Nhóm cao vay lại 39%" không tìm thấy trong output. Biểu đồ 6 tháng cao nhất chỉ khoảng 30%, nên 39% không thể cùng thước đo. Slide 8 lại dùng 34% (15 tháng) | — | Thống nhất một khung thời gian và ghi nguồn |
| M6 | 6 | "Nếu giữ nguyên" 88,0K > "Đang bán" 87,4K mà không giải thích | 37 cửa hàng có BAU của Task 1 cao hơn thực tế (+589). Không cửa hàng nào có dự báo đã kiểm định (1.766 dùng mức nền dự phòng, 183 không đủ dữ liệu kiểm định) | Thêm chú thích: "BAU = mức nền 3 tháng; mô hình xu hướng không tốt hơn mức nền" |
| M7 | 6 | Nhãn "Có thể đạt = làm tốt như cửa hàng cùng loại" nghe như trung vị, nhưng thực tế là **p75** (nhóm 25% tốt nhất) | PL1 ghi p75 | Đổi chữ cho khớp |
| M8 | 12 | Tiêu đề phụ "Hai đề xuất đội nào cũng có thể nghĩ ra" là đang nói với ban giám khảo cuộc thi, không phải với ban lãnh đạo. Nhãn cũng không khớp: chỉ một dòng gắn "Đội nào cũng có" | — | Bỏ so sánh với đội khác; dùng nhãn "Cải thiện vận hành / Sửa đo lường / Rào chắn" |
| M9 | 12 | Đề xuất 4 "Tiết kiệm 392K lượt liên hệ" là so với **đề xuất của chính đội ở vòng 2**, không phải chi phí công ty đang bỏ ra; và gắn với tăng trưởng cửa hàng rất yếu | — | Ghi là "tự sửa đề xuất vòng 2"; đưa xuống phần nền tảng |
| M10 | 12 | Đề xuất 3 không có số lợi ích. Không đề xuất nào có chi phí | — | Thêm cột "Nỗ lực / chi phí" (thấp / vừa / cao) |
| M11 | toàn deck | Thuật ngữ tiếng Anh phải dùng **đúng tên** 4 khái niệm của đề: Current Actual / Business-as-Usual / Attainable Potential / Addressable Market Ceiling. Mức trần hiện chỉ là **chỉ số nội bộ** (internal proxy) | — | Ghi "Addressable Market Ceiling (internal proxy, no external data)". Chuẩn bị câu trả lời vì sao không dùng dữ liệu thị trường |

---

## 5. Lỗi NHỎ (câu chữ)

- **Slide 11:** tiêu đề "20 cửa hàng… chốt kém nhất" là sai. Danh sách được xếp theo **dư địa lớn nhất trong nhóm EXECUTION** (ví dụ dòng 10 chốt 75%). Nên ghi: "20 cửa hàng có dư địa lớn nhất trong nhóm chốt kém".
- **Slide 8:** "gấp 3–4 lần" → thực tế là 34/13 = 2,6 lần và 34/8 = 4,3 lần, nên ghi "gấp 2,6–4,3 lần".
- **Slide 7:** câu "B đã gần chạm trần" → nên ghi "B không còn nhiều khách tiềm năng chưa chốt" (xem C2).
- **Slide 13:** điều kiện "Dừng nếu Aldi giảm quá mức dự báo" quá mơ hồ; cần một con số, ví dụ "giảm hơn X% so với nhóm đối chứng".
- **PL5:** tiêu đề bảng đang là tiếng Anh trong khi deck tiếng Việt (sẽ hết khi dịch sang tiếng Anh). Nên thêm một câu: "dự báo theo xu hướng chưa lần nào thắng mức nền".
- **PL9:** mới có 4 câu hỏi; bổ sung thêm các câu ở mục 6.

---

## 6. Năm câu hỏi Q&A khó nhất (chuẩn bị sẵn)

1. **"Nếu ghi công đúng thì A và B còn bán bằng nhau không?"**
   → Không: A là 166 và B là 81. Dùng khung 3 góc nhìn ở C1. Đây là lý do A nằm trong danh sách thử nghiệm.
2. **"Dư địa của các bạn chỉ đến từ khách tiềm năng. Còn khoảng 84% doanh số đến từ khách vãng lai thì sao?"**
   → Thừa nhận phạm vi. Dư địa khách mới cần dữ liệu thị trường; trần hiện tại chỉ là chỉ số nội bộ.
3. **"20 cửa hàng kém nhất quý sau tự khá lên thì sao? Lấy gì để biết là nhờ can thiệp?"**
   → Chia ngẫu nhiên từ cùng 40 cửa hàng đủ điều kiện, đo bằng chênh lệch trước–sau giữa hai nhóm.
4. **"Hợp đồng/người gấp 5 lần có phải chỉ do cách chia mẫu số không?"**
   → Đúng là phụ thuộc vào giả định chia đều thời gian, nên mới phải thử ở 1 vùng trước.
5. **"Mức trần 203 của A tính thế nào?"**
   → Nếu đã sửa C3 thì trả lời là 155 kèm công thức. Nếu chưa sửa thì đừng dùng con số 203.

---

## 7. Thứ tự sửa (deadline 16:00)

| Ưu tiên | Việc | Loại | Thời gian ước tính |
|---|---|---|---|
| P0 | C1 khung 3 góc nhìn cho slide 7 · C2 tiêu đề slide 9 + dòng phạm vi · C7 câu chữ 28% / 9 trên 10 · C4 viết lại slide 5 · C5 ghi "tối đa" + chia ngẫu nhiên · C6 bỏ chữ "một quý" · M8 tiêu đề slide 12 | Câu chữ trong Canva | 30–45 phút |
| P1 | C3 sửa công thức mức trần và chạy lại script 5 (cần báo người viết code, vì đây là code của teammate) | Code | 15–20 phút |
| P1 | C8 slide nhân sự · M1 bỏ +221 · M4 / M5 phụ lục | Câu chữ | 15 phút |
| P2 | Bảng công thức tác động · sổ rủi ro · cột chi phí · slide nền tảng vòng 2 | Thêm slide | nếu còn thời gian |
| Bắt buộc | **Dịch sang tiếng Anh**, giữ đúng tên 4 khái niệm của đề, PDF 16:9, đặt tên file đúng mẫu | — | — |

# Báo cáo


## 1. Cách các cây liên kết với nhau

```text
Thông tin đo huyết áp ──> Cây 1: Chẩn đoán HA ──> bp.category
                                      │
Yếu tố nguy cơ, bệnh đồng mắc ──> Cây 4: Phân tầng nguy cơ ──> risk.class
                                      │                         │
                                      └──────────────> Cây 2: Ngưỡng và đích điều trị

Tuổi, bệnh đồng mắc, thuốc đang dùng ──> Cây 3: Điều trị tối ưu
                                                   │
                                                   └── nếu nghi kháng trị ──> Cây 5
```

Trong bundle, liên kết được khai báo tại node `optimized_link_resistant`: từ **Cây 3 – Điều trị tối ưu** chuyển sang **Cây 5 – Phân loại tăng huyết áp không kiểm soát/kháng trị**, đồng thời truyền ngữ cảnh của người bệnh sang cây đích.

## 2. Các loại node trong một cây

| Loại node | Ý nghĩa dễ hiểu | Vai trò |
|---|---|---|
| `start` | Bắt đầu | Điểm vào của cây |
| `condition` | Câu hỏi/điều kiện | Kiểm tra dữ liệu và chọn một nhánh |
| `inference` | Kết luận trung gian | Đưa ra nhận định hoặc khuyến nghị trước khi đi tiếp |
| `end` | Kết quả cuối | Kết thúc nhánh và trả kết quả |
| `link` | Chuyển cây | Mở cây khác khi cần đánh giá sâu hơn |

Tổng cộng trong 5 cây: 5 node bắt đầu, 38 node điều kiện, 7 node kết luận trung gian, 38 node kết thúc và 1 node chuyển cây.

## 3. Danh sách biến được sử dụng

### 3.1. Biến đo huyết áp và chẩn đoán

| Mã biến | Tên hiển thị | Kiểu dữ liệu | Đơn vị |
|---|---|---|---|
| `bp.measurementMethod` | Phương pháp đo HA xác nhận | enum | — |
| `bp.office1.systolicMmHg` | HA phòng khám lần 1 – HATT | number | mmHg |
| `bp.office1.diastolicMmHg` | HA phòng khám lần 1 – HATTr | number | mmHg |
| `bp.office2.systolicMmHg` | HA phòng khám lần 2 – HATT | number | mmHg |
| `bp.office2.diastolicMmHg` | HA phòng khám lần 2 – HATTr | number | mmHg |
| `bp.office3.systolicMmHg` | HA phòng khám lần 3 – HATT | number | mmHg |
| `bp.office3.diastolicMmHg` | HA phòng khám lần 3 – HATTr | number | mmHg |
| `bp.office1.targetOrganDamageOrCvd` | Tổn thương cơ quan đích/bệnh tim mạch ở lần 1 | boolean | — |
| `bp.office2.targetOrganDamageOrCvd` | Tổn thương cơ quan đích/bệnh tim mạch ở lần 2 | boolean | — |
| `bp.home.systolicMmHg` | HA tại nhà – HATT | number | mmHg |
| `bp.home.diastolicMmHg` | HA tại nhà – HATTr | number | mmHg |
| `bp.abpm.daytime.systolicMmHg` | HALT ban ngày – HATT | number | mmHg |
| `bp.abpm.daytime.diastolicMmHg` | HALT ban ngày – HATTr | number | mmHg |
| `bp.abpm.average24h.systolicMmHg` | HALT trung bình 24 giờ – HATT | number | mmHg |
| `bp.abpm.average24h.diastolicMmHg` | HALT trung bình 24 giờ – HATTr | number | mmHg |

HATT là huyết áp tâm thu; HATTr là huyết áp tâm trương; HALT là huyết áp lưu động 24 giờ.

### 3.2. Biến phân loại và đích điều trị

| Mã biến | Tên hiển thị | Kiểu dữ liệu | Đơn vị |
|---|---|---|---|
| `bp.category` | Phân loại huyết áp | enum | — |
| `risk.class` | Phân tầng nguy cơ tim mạch | enum | — |
| `treatment.hasHighRiskComorbidity` | Có bệnh đồng mắc/nguy cơ cao | boolean | — |
| `treatment.recommendation` | Khuyến nghị điều trị ban đầu | enum | — |
| `treatment.targetSystolicMmHg` | Đích HATT | number | mmHg |
| `treatment.targetDiastolicMmHg` | Đích HATTr | number | mmHg |
| `treatment.controlWindowMonths` | Khoảng thời gian kiểm soát mục tiêu | enum | tháng |

Các giá trị chính của `bp.category`: bình thường, bình thường-cao, tăng huyết áp, độ 1, độ 2, cơn tăng huyết áp, áo choàng trắng, tăng huyết áp ẩn hoặc cần rà soát.

Các giá trị của `risk.class`: thấp, trung bình hoặc cao.

### 3.3. Biến điều trị tối ưu

| Mã biến | Tên hiển thị | Kiểu dữ liệu | Đơn vị |
|---|---|---|---|
| `patient.ageYears` | Tuổi bệnh nhân | integer | năm |
| `bp.assessmentOfficeSystolicMmHg` | HATT phòng khám lúc đánh giá điều trị | number | mmHg |
| `bp.assessmentOfficeDiastolicMmHg` | HATTr phòng khám lúc đánh giá điều trị | number | mmHg |
| `medication.hasClassA` | Đang có nhóm thuốc A | boolean | — |
| `medication.hasClassB` | Đang có nhóm thuốc B | boolean | — |
| `medication.hasClassC` | Đang có nhóm thuốc C | boolean | — |
| `medication.hasClassD` | Đang có nhóm thuốc D | boolean | — |
| `medication.hasClassMRA` | Đang có nhóm thuốc MRA | boolean | — |
| `comorbidity.atheroscleroticCvd` | Bệnh tim mạch do xơ vữa | boolean | — |
| `comorbidity.heartFailure` | Suy tim | boolean | — |
| `comorbidity.stroke` | Tiền sử đột quỵ | boolean | — |
| `comorbidity.ckd` | Bệnh thận mạn | boolean | — |
| `comorbidity.diabetes` | Đái tháo đường | boolean | — |
| `treatment.mandatoryIndication` | Có chỉ định điều trị bắt buộc | boolean | — |
| `medication.agentCount` | Số nhóm thuốc hạ áp | integer | nhóm thuốc |
| `medication.uncontrolledDespiteTripleTherapy` | Chưa kiểm soát dù đã phối hợp ba thuốc | boolean | — |
| `treatment.path` | Nhánh điều trị tối ưu | enum | — |

### 3.4. Biến phân tầng nguy cơ

| Mã biến | Tên hiển thị | Kiểu dữ liệu | Đơn vị |
|---|---|---|---|
| `bp.systolicMmHg` | HATT dùng để phân biệt mức độ trong độ 2 | number | mmHg |
| `bp.diastolicMmHg` | HATTr dùng để phân biệt mức độ trong độ 2 | number | mmHg |
| `risk.ageOver65` | Tuổi ≥65 | boolean | — |
| `risk.maleSex` | Giới nam | boolean | — |
| `risk.heartRateOver80` | Nhịp tim >80 lần/phút | boolean | — |
| `risk.overweight` | Thừa cân/béo phì | boolean | — |
| `risk.lipidAbnormality` | Rối loạn lipid máu | boolean | — |
| `risk.familyHistoryPrematureCvd` | Tiền sử gia đình bệnh tim mạch sớm | boolean | — |
| `risk.currentSmoker` | Hút thuốc hiện tại | boolean | — |
| `risk.socialEnvironmentalRisk` | Yếu tố xã hội/môi trường bất lợi | boolean | — |
| `risk.factorCount` | Số yếu tố nguy cơ | integer | yếu tố |
| `risk.targetOrganDamage` | Tổn thương cơ quan đích | boolean | — |
| `risk.ckdStageAtLeast3` | CKD giai đoạn ≥3 | boolean | — |
| `risk.diabetes` | Đái tháo đường | boolean | — |
| `risk.cardiovascularDisease` | Bệnh tim mạch | boolean | — |
| `risk.highRiskComorbidity` | Tổn thương cơ quan đích/bệnh đồng mắc nguy cơ cao | boolean | — |

Các yếu tố từ `risk.ageOver65` đến `risk.socialEnvironmentalRisk` được dùng để tạo hoặc kiểm tra `risk.factorCount`; không nên hiểu `risk.factorCount` là một bệnh riêng.

### 3.5. Biến không kiểm soát/kháng trị và safety screen

| Mã biến | Tên hiển thị | Kiểu dữ liệu | Đơn vị |
|---|---|---|---|
| `bp.officeAverageSystolicMmHg` | HATT phòng khám trung bình | number | mmHg |
| `bp.officeReadingCount` | Số lần đo phòng khám | integer | lần đo |
| `medication.regimenStableWeeks` | Số tuần phác đồ ổn định | number | tuần |
| `medication.includesDiuretic` | Phác đồ có lợi tiểu | boolean | — |
| `resistant.egfrMlMin` | eGFR | number | mL/min/1.73m² |
| `resistant.potassiumMmolL` | Kali máu | number | mmol/L |
| `resistant.sodiumMmolL` | Natri máu | number | mmol/L |
| `pregnancy.status` | Tình trạng thai kỳ | enum | — |
| `resistant.severeLiverDisease` | Bệnh gan nặng | boolean | — |
| `resistant.systolicDropAt12WeeksMmHg` | Mức giảm HATT tại tuần 12 | number | mmHg |
| `resistant.classification` | Phân loại nhánh không kiểm soát/kháng trị | enum | — |
| `resistant.treatmentStatus` | Trạng thái điều trị kháng trị | enum | — |
| `resistant.drugRecommendation` | Thuốc/hành động xử trí kháng trị | enum | — |
| `resistant.followupStatus` | Trạng thái theo dõi | enum | — |

## 4. Năm cây quyết định đã xây dựng

### Cây 1 – Chẩn đoán tăng huyết áp

**Mục đích:** xác định phân loại huyết áp từ đo phòng khám, đo tại nhà hoặc HALT.

| Nội dung | Chi tiết |
|---|---|
| Mã cây | `bp_diagnosis` |
| Số node/liên kết | 20 node / 19 liên kết |
| Đầu ra chính | `bp.category` – phân loại huyết áp |
| Ảnh nguồn | [`01_bp_diagnosis.png`](../images/01_bp_diagnosis.png) |

**Đầu vào:** phương pháp đo; HATT/HATTr phòng khám lần 1, 2, 3; tổn thương cơ quan đích/bệnh tim mạch ở lần 1 và 2; HATT/HATTr tại nhà; HATT/HATTr HALT ban ngày và trung bình 24 giờ.

**Luồng chính:**

1. Kiểm tra lần đo phòng khám đầu tiên có HATT ≥180 hoặc HATTr ≥120 kèm tổn thương cơ quan đích/bệnh tim mạch hay không. Nếu có, kết luận cơn tăng huyết áp.
2. Nếu không, kiểm tra lần đo phòng khám thứ hai có mức 140–179/90–119 kèm tổn thương cơ quan đích/bệnh tim mạch hay không. Nếu có, kết luận tăng huyết áp.
3. Nếu dùng lần đo phòng khám thứ ba: phân loại thành bình thường, bình thường-cao hoặc tăng huyết áp theo các ngưỡng 130/85, 130–139/85–89 và ≥140/90.
4. Nếu dùng đo tại nhà: phân loại áo choàng trắng khi dưới 135/85, ngược lại phân loại tăng huyết áp ẩn.
5. Nếu dùng HALT 24 giờ: kiểm tra ngưỡng ban ngày <135/85 và/hoặc trung bình 24 giờ <130/80 để phân loại áo choàng trắng hoặc tăng huyết áp ẩn.
6. Nếu chưa chọn được phương pháp hoặc thiếu dữ liệu, trả về “cần rà soát dữ liệu đo”.

**Đầu ra:** `bp.category`. Đây là biến quan trọng được truyền sang Cây 2, Cây 3 và Cây 4.

### Cây 2 – Ngưỡng huyết áp và đích điều trị

**Mục đích:** chọn thay đổi lối sống hay điều trị thuốc, đồng thời xác định đích huyết áp.

| Nội dung | Chi tiết |
|---|---|
| Mã cây | `bp_thresholds_targets` |
| Số node/liên kết | 10 node / 9 liên kết |
| Đầu vào chính | `bp.category`, `risk.class`, `treatment.hasHighRiskComorbidity` |
| Đầu ra | `treatment.recommendation`, `treatment.targetSystolicMmHg`, `treatment.targetDiastolicMmHg`, `treatment.controlWindowMonths` |
| Ảnh nguồn | [`02_bp_thresholds_and_targets.png`](../images/02_bp_thresholds_and_targets.png) |

**Luồng chính:**

1. Nếu huyết áp bình thường-cao, kiểm tra có nguy cơ cao/bệnh đồng mắc nguy cơ cao không.
2. Bình thường-cao nhưng nguy cơ thấp hoặc trung bình: ưu tiên thay đổi lối sống.
3. Bình thường-cao và nguy cơ cao: điều trị thuốc theo cá thể hóa, đích trong bundle là <130/80 mmHg.
4. Nếu đã là tăng huyết áp ≥140 và/hoặc ≥90, kiểm tra bệnh đồng mắc/nguy cơ cao.
5. Tăng huyết áp có nguy cơ cao: điều trị thuốc ngay, đích <130/80 mmHg khi dung nạp.
6. Tăng huyết áp không có bệnh đồng mắc nguy cơ cao: điều trị thuốc ngay, đích HATT <140 và HATTr khoảng <80.
7. Nếu phân loại đầu vào chưa đủ để chọn nhánh, trả về cần rà soát.

### Cây 3 – Điều trị tăng huyết áp tối ưu

**Mục đích:** chọn chiến lược điều trị theo tuổi, mức huyết áp, nguy cơ, bệnh đồng mắc và số nhóm thuốc đang dùng.

| Nội dung | Chi tiết |
|---|---|
| Mã cây | `optimized_hypertension_treatment` |
| Số node/liên kết | 16 node / 17 liên kết |
| Đầu vào chính | tuổi; HATT/HATTr lúc đánh giá; `bp.category`; bệnh đồng mắc/nguy cơ cao; chỉ định bắt buộc; số nhóm thuốc và tình trạng kiểm soát |
| Đầu ra chính | `treatment.path` |
| Liên kết | Nếu nghi kháng trị, chuyển sang `uncontrolled_resistant_hypertension` |
| Ảnh nguồn | [`03_optimized_hypertension_treatment.png`](../images/03_optimized_hypertension_treatment.png) |

**Luồng chính:**

1. Chỉ tiếp tục nếu người bệnh >18 tuổi và HATT phòng khám ≥130 hoặc HATTr ≥85; nếu không, yêu cầu rà soát.
2. Người có huyết áp bình thường-cao và nguy cơ thấp/trung bình: đi theo nhánh khởi trị một viên A/B/C/D theo cá thể hóa.
3. Nếu có chỉ định điều trị bắt buộc, chọn điều trị theo bệnh đồng mắc.
4. Nếu không có chỉ định bắt buộc nhưng cần điều trị phối hợp, kiểm tra số nhóm thuốc đang dùng.
5. Chưa biết số nhóm thuốc: chọn nhánh phối hợp ban đầu.
6. Đã dùng từ 3 nhóm thuốc: đi theo nhánh phối hợp ba thuốc.
7. Nếu chưa kiểm soát dù đã phối hợp ba thuốc: nhận định có khả năng tăng huyết áp kháng trị và chuyển Cây 5.
8. Nếu đã kiểm soát: tiếp tục theo dõi sau phối hợp ba thuốc.

### Cây 4 – Phân tầng nguy cơ tim mạch

**Mục đích:** phân loại nguy cơ thấp, trung bình hoặc cao dựa trên mức huyết áp, yếu tố nguy cơ, tổn thương cơ quan đích và bệnh đồng mắc.

| Nội dung | Chi tiết |
|---|---|
| Mã cây | `hypertension_risk_stratification` |
| Số node/liên kết | 21 node / 21 liên kết |
| Đầu vào chính | `bp.category`; HATT/HATTr; các yếu tố nguy cơ; số yếu tố nguy cơ; TOD/CKD ≥3/đái tháo đường/bệnh tim mạch |
| Đầu ra | `risk.class` – thấp, trung bình hoặc cao |
| Ảnh nguồn | [`04_hypertension_risk_stratification.png`](../images/04_hypertension_risk_stratification.png) |

**Luồng chính:**

1. Nếu có tổn thương cơ quan đích, CKD giai đoạn ≥3, đái tháo đường hoặc bệnh tim mạch: nguy cơ cao.
2. Với tăng huyết áp độ 2: mức HATT ≥180 hoặc HATTr ≥110 dẫn đến nguy cơ cao; mức thấp hơn tiếp tục kiểm tra yếu tố nguy cơ.
3. Với tăng huyết áp độ 2 và có ít nhất một yếu tố nguy cơ: nguy cơ cao; không có yếu tố nguy cơ: nguy cơ trung bình.
4. Với tăng huyết áp độ 1: từ 3 yếu tố nguy cơ trở lên là nguy cơ cao; có 1–2 yếu tố là nguy cơ trung bình; không có yếu tố là nguy cơ thấp.
5. Với huyết áp bình thường-cao: từ 3 yếu tố nguy cơ trở lên là nguy cơ trung bình; dưới 3 yếu tố là nguy cơ thấp.
6. Với huyết áp bình thường: kết luận nguy cơ thấp nếu dữ liệu phân loại đầy đủ; nếu chưa đủ dữ liệu thì yêu cầu rà soát.

### Cây 5 – Phân loại tăng huyết áp không kiểm soát/kháng trị

**Mục đích:** kiểm tra người bệnh có phù hợp với nhánh không kiểm soát/kháng trị hay không, sau đó thực hiện safety screen và theo dõi đáp ứng.

| Nội dung | Chi tiết |
|---|---|
| Mã cây | `uncontrolled_resistant_hypertension` |
| Số node/liên kết | 22 node / 22 liên kết |
| Đầu vào chính | HATT phòng khám trung bình; số lần đo; thời gian phác đồ ổn định; số nhóm thuốc; có lợi tiểu; eGFR; kali; natri; thai kỳ; bệnh gan nặng; mức giảm HATT tại tuần 12 |
| Đầu ra | `resistant.classification`, `resistant.treatmentStatus`, `resistant.drugRecommendation`, `resistant.followupStatus` |
| Ảnh nguồn | [`05_uncontrolled_resistant_hypertension.png`](../images/05_uncontrolled_resistant_hypertension.png) |

**Luồng chính:**

1. Kiểm tra HATT phòng khám trung bình có nằm trong khoảng 140–169 mmHg hay không. Ngoài khoảng này thì cần đánh giá thêm.
2. Kiểm tra phác đồ đã ổn định ít nhất 4 tuần hay chưa. Nếu chưa, hoãn và đánh giá lại sau.
3. Nếu đang dùng đúng 2 nhóm thuốc: phân loại nhánh tăng huyết áp không kiểm soát với phác đồ 2 thuốc.
4. Nếu dùng từ 3 nhóm thuốc trở lên: kiểm tra có thuốc lợi tiểu hay không.
5. Từ 3 nhóm thuốc trở lên và có lợi tiểu: phân loại nhánh tăng huyết áp kháng trị.
6. Từ 3 nhóm thuốc trở lên nhưng chưa có lợi tiểu: thêm lợi tiểu rồi phân loại lại.
7. Trước khi kết luận điều trị, bắt buộc kiểm tra đủ eGFR, kali, natri, thai kỳ và bệnh gan nặng.
8. Nếu có tiêu chí loại trừ, xử trí nguyên nhân và thử lại; nếu không có, đi theo nhánh đủ điều kiện điều trị.
9. Theo dõi mức giảm HATT tại tuần 12: đạt ≥8,7 mmHg thì tiếp tục; không đạt thì điều chỉnh/liên chuyên khoa và đánh giá lại.

## 5. Bảng tổng hợp đầu vào – đầu ra

| Cây | Đầu vào chính | Đầu ra chính | Dùng lại ở cây nào |
|---|---|---|---|
| Cây 1 – Chẩn đoán HA | Đo phòng khám, HATN, HALT, tổn thương cơ quan đích/bệnh tim mạch | `bp.category` | Cây 2, 3, 4 |
| Cây 2 – Ngưỡng và đích | `bp.category`, `risk.class`, bệnh đồng mắc nguy cơ cao | Khuyến nghị ban đầu, đích HATT/HATTr, thời gian kiểm soát | Clinical flow/hiển thị điều trị |
| Cây 3 – Điều trị tối ưu | Tuổi, HA lúc đánh giá, nguy cơ, bệnh đồng mắc, thuốc đang dùng | `treatment.path` | Chuyển Cây 5 khi nghi kháng trị |
| Cây 4 – Phân tầng nguy cơ | Phân loại HA, trị số HA, yếu tố nguy cơ, TOD/CKD/ĐTĐ/bệnh tim mạch | `risk.class` | Cây 2 và clinical flow |
| Cây 5 – Không kiểm soát/kháng trị | HA trung bình, số lần đo, thời gian ổn định, số thuốc, lợi tiểu, safety screen, đáp ứng tuần 12 | Phân loại, trạng thái điều trị, khuyến nghị thuốc, trạng thái theo dõi | Clinical flow/điều trị tiếp theo |

## 6. Phân biệt dữ liệu người dùng nhập và dữ liệu hệ thống tự sinh

### Người dùng hoặc clinical flow cung cấp

- Các trị số HATT/HATTr.
- Phương pháp đo: phòng khám, tại nhà hoặc HALT.
- Thông tin bệnh đồng mắc, tổn thương cơ quan đích và yếu tố nguy cơ.
- Thuốc đang dùng, số nhóm thuốc, có lợi tiểu hay không.
- eGFR, kali, natri, thai kỳ, bệnh gan và mức giảm HATT khi theo dõi.

### Hệ thống suy ra

- `bp.category`: phân loại huyết áp.
- `risk.class`: nhóm nguy cơ.
- `treatment.recommendation`: khuyến nghị ban đầu.
- `treatment.targetSystolicMmHg` và `treatment.targetDiastolicMmHg`: đích điều trị.
- `treatment.path`: nhánh điều trị tối ưu.
- Các biến `resistant.*`: kết quả phân loại và theo dõi nhánh kháng trị.

Vì vậy, trên UI nên hiển thị câu hỏi dễ hiểu như “HATT phòng khám lần 1” hoặc “Có bệnh thận mạn không?”, còn mã biến kỹ thuật chỉ nên dùng trong JSON, database và pipeline.

## 7. Trạng thái tự động hóa ảnh → JSON

Pipeline đã được thiết kế theo các bước:

1. Nhận ảnh guideline.
2. Trích xuất các mệnh đề bằng chứng và vị trí nguồn.
3. Kiểm tra bằng chứng; nếu thiếu hoặc sai thì gửi yêu cầu sửa lại.
4. Từ bằng chứng đã chuẩn hóa, xây danh sách biến.
5. Kiểm tra danh sách biến; nếu thiếu biến hoặc gộp sai biến thì sửa lại.
6. Từ danh sách biến, xây node và edge của cây.
7. Kiểm tra cấu trúc, tính đầy đủ, đường đi, biến được tham chiếu và liên kết giữa các cây.
8. Lặp tối đa 10 vòng cho mỗi giai đoạn; chỉ cho phép xuất bundle khi đạt pass criteria.

Kết quả JSON chuẩn hiện được lưu tại [`decision_tree_bundle.json`](../bundle/decision_tree_bundle.json). Đây là baseline đang được UI sử dụng. Trạng thái lâm sàng vẫn là `under_review`, nên kết quả tự động cần được chuyên gia xác nhận trước khi triển khai chính thức.

## 9. Tệp tham chiếu

- Bundle 5 cây: [`../bundle/decision_tree_bundle.json`](../bundle/decision_tree_bundle.json)
- Schema JSON: [`../bundle/decision_tree_schema.json`](../bundle/decision_tree_schema.json)
- Tiêu chí pass: [`../bundle/decision_tree_pass_criteria.json`](../bundle/decision_tree_pass_criteria.json)
- Ảnh nguồn: [`../images/README.md`](../images/README.md)


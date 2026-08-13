# Báo cáo các cây đang kích hoạt

Hiện bundle runtime giữ đủ Cây 1–5. Các cây dùng chung context người bệnh và
đầu ra dẫn xuất; Cây 3 chuyển sang Cây 5 khi đạt nhánh 4 nhóm thuốc nhưng HA
chưa kiểm soát.

## Quan hệ giữa các cây đang kích hoạt

```text
Thông tin đo huyết áp + mã bệnh người bệnh
        └──> Cây 1: Chẩn đoán tăng huyết áp
                    └── bp.category
                           └──> Cây 4: Phân tầng nguy cơ
                                      └── risk.class
                           └──> Cây 2: Ngưỡng và đích điều trị
                                                        └──> Cây 3: Điều trị tối ưu
                                                                   └──> Cây 5 khi 4 nhóm thuốc chưa kiểm soát
                                      ├── treatment.recommendation
                                      ├── treatment.targetSystolicMmHg
                                      └── treatment.targetDiastolicMmHg
```

UI giữ context sau mỗi lần chạy để Cây 4 dùng dữ liệu chung và Cây 2 nhận
`bp.category`, `risk.class` mà không phải nhập lại; Cây 3 tiếp tục dùng đích
điều trị và danh sách nhóm thuốc của encounter trước.

## Các loại node

| Loại | Ý nghĩa |
|---|---|
| `start` | Điểm bắt đầu của cây |
| `condition` | Câu hỏi/điều kiện để chọn nhánh |
| `inference` | Kết luận hoặc khuyến nghị trung gian |
| `end` | Kết quả cuối của nhánh |
| `link` | Chuyển sang cây khác khi flow cần gọi trực tiếp cây đích |

## Danh mục biến

Danh mục đầy đủ được lưu tại
[`contracts/clinical_variables.json`](../contracts/clinical_variables.json).
File gồm mã biến, nhãn hiển thị, kiểu dữ liệu, nguồn dữ liệu, cây sử dụng và
quy tắc ICD-10/SNOMED CT.

### Cây 1

| Mã biến | Ý nghĩa |
|---|---|
| `bp.office1.systolicMmHg` | Huyết áp tâm thu phòng khám lần 1 |
| `bp.office1.diastolicMmHg` | Huyết áp tâm trương phòng khám lần 1 |
| `bp.office2.systolicMmHg` | Huyết áp tâm thu phòng khám lần 2 |
| `bp.office2.diastolicMmHg` | Huyết áp tâm trương phòng khám lần 2 |
| `bp.office3.systolicMmHg` | Huyết áp tâm thu phòng khám lần 3 |
| `bp.office3.diastolicMmHg` | Huyết áp tâm trương phòng khám lần 3 |
| `patient.diagnosisCodes` | Danh sách mã ICD-10/SNOMED CT trong hồ sơ bệnh nhân |

Đầu ra: `bp.category`.

### Cây 2

| Mã biến | Ý nghĩa |
|---|---|
| `bp.category` | Kết quả phân loại từ Cây 1 |
| `encounter.number` | Lần khám; 1 là lần đầu, lớn hơn 1 là tái khám |
| `comorbidity.targetOrganDamageOrCvd` | Có bằng chứng tổn thương cơ quan đích hoặc bệnh tim mạch |

Đầu ra: `treatment.recommendation`, `treatment.targetSystolicMmHg` và
`treatment.targetDiastolicMmHg`. Nhánh có bệnh đồng mắc đặt đích `130/80
mmHg`; nhánh không có bệnh đồng mắc đặt đích `140/80 mmHg`. Không sử dụng
`treatment.targetProfile` hoặc `treatment.controlWindowMonths`.

### Cây 4

| Mã biến | Ý nghĩa |
|---|---|
| `bp.latest.systolicMmHg` | Huyết áp tâm thu lần đo gần nhất |
| `bp.latest.diastolicMmHg` | Huyết áp tâm trương lần đo gần nhất |
| `risk.factorCount` | Số YTNC được đếm theo bảng phân tầng |
| `risk.highRiskComorbidity` | Có tổn thương cơ quan đích, CKD từ giai đoạn 3, ĐTĐ hoặc bệnh tim mạch |

Các biến YTNC thành phần gồm tuổi >65, giới nam, nhịp tim >80, thừa cân,
đái tháo đường, LDL-C/triglyceride tăng, tiền sử gia đình bệnh tim mạch sớm,
hút thuốc và yếu tố xã hội/môi trường.

Đầu ra: `risk.class` với một trong ba giá trị `low`, `medium`, `high`.

### Cây 3

| Mã biến | Ý nghĩa |
|---|---|
| `patient.ageYears` | Tuổi người bệnh; chỉ áp dụng người lớn >18 tuổi |
| `encounter.number` | Lần khám hiện tại; 1 là bệnh nhân mới, >1 là tái khám |
| `treatment.mandatoryIndication` | Tự nhận diện bệnh nền có chỉ định điều trị bắt buộc |
| `comorbidity.atheroscleroticCvd` | Bệnh mạch vành/bệnh tim mạch do xơ vữa |
| `comorbidity.heartFailureReducedEjectionFraction` | Suy tim EF giảm |
| `comorbidity.stroke` | Tiền sử đột quỵ |
| `comorbidity.ckd` | Bệnh thận mạn |
| `comorbidity.type2Diabetes` | Đái tháo đường type 2 |
| `medication.previousEncounterDrugNames` | Danh sách thuốc của encounter n-1 |
| `medication.previousEncounterDrugClassList` | Danh sách mã nhóm thuốc chuẩn hóa từ encounter n-1 |
| `medication.previousEncounterDrugClassList` | Danh sách nhóm thuốc tự tính từ encounter n-1; dùng độ dài danh sách cho giai đoạn điều trị |
| `bp.latest.systolicMmHg`, `bp.latest.diastolicMmHg` | HA encounter hiện tại để so sánh với đích Cây 2 |
| `bp.controlledAfterTwoDrugs` | HA sau 2 nhóm thuốc đã thấp hơn đích Cây 2 chưa |
| `bp.controlledAfterThreeDrugs` | HA sau 3 nhóm thuốc đã thấp hơn đích Cây 2 chưa |
| `bp.controlledAfterFourDrugs` | HA sau 4 nhóm thuốc đã thấp hơn đích Cây 2 chưa |

Bệnh nhân mới không kiểm tra số lượng thuốc hiện tại. Bệnh nhân tái khám đi
theo giai đoạn 1 → 2 → 3 → 4 nhóm thuốc; nếu 4 nhóm thuốc vẫn chưa kiểm soát,
cây chuyển sang Cây 5.

Nhánh chỉ định bắt buộc được tách thành 5 bệnh nền: bệnh mạch vành/xơ vữa
(A+B hoặc C), suy tim EF giảm (A+B+SGLT2i+MRA và lợi tiểu quai khi có chỉ định),
đột quỵ (A+D), bệnh thận mạn (A+C), và đái tháo đường type 2 (A+C hoặc D; cân
nhắc SGLT2i hoặc GLP-1 RA theo chỉ định). Đây là 5 nhánh con trực tiếp của
node chỉ định bắt buộc; không xếp chúng thành chuỗi điều kiện. Nếu hồ sơ có
nhiều mã bệnh nền, engine chọn nhánh đầu tiên theo thứ tự các case đã khai báo
và lưu `treatment.mandatoryDisease` cùng `treatment.mandatoryRegimen`.

### Cây 5

| Mã biến | Ý nghĩa |
|---|---|
| `bp.latest.systolicMmHg` | HATT lần đo gần nhất; khoảng đánh giá 140–169 mmHg |
| `bp.latest.diastolicMmHg` | HATTr của cùng lần đo gần nhất |
| `medication.regimenStartDate` | Ngày bắt đầu hoặc thay đổi gần nhất của phác đồ; lấy từ lịch sử kê đơn |
| `medication.regimenStableWeeks` | Biến dẫn xuất: số tuần tròn từ ngày bắt đầu/thay đổi phác đồ đến ngày khám; tự tính, không nhập tay |
| `medication.currentDrugNames` | Danh sách hoạt chất người bệnh đang dùng |
| `medication.currentDrugClassList` | Danh sách mã nhóm thuốc chuẩn hóa từ danh sách hoạt chất |

Đầu ra: `resistant.classification`. Đúng 2 nhóm thuốc cho kết quả chưa kiểm
soát; từ 3 nhóm có lợi tiểu cho kết quả kháng trị; từ 3 nhóm không có lợi tiểu
cho khuyến nghị thêm lợi tiểu và phân loại lại.

## Tự động nhận diện mã bệnh

```json
{
  "patient.diagnosisCodes": "I25.1, E11.9, N18.3, 25488008"
}
```

Engine tự chuẩn hóa mã, bỏ dấu chấm và cập nhật các biến dẫn xuất:

- `I25.1`: bệnh mạch vành/bệnh tim mạch do xơ vữa.
- `I50.9`, `I50.2x`: suy tim; `I50.2x` là suy tim EF giảm.
- `I63.9`: đột quỵ; `I73.9`: bệnh mạch máu ngoại biên; `I48.91`: rung nhĩ.
- `N18.x`: bệnh thận mạn; `E11.9` hoặc nhóm `E11`: đái tháo đường type 2.
- `373717006` hoặc `E28.3`: mãn kinh sớm; `25488008`: dày thất trái.

Các cờ tổng hợp `comorbidity.targetOrganDamageOrCvd` và
`treatment.hasHighRiskComorbidity` được cập nhật từ các cờ trên, không cần
nhập boolean thủ công.

## Danh mục thuốc hạ áp

Danh mục hoạt chất và phân loại được lưu tại
[`contracts/antihypertensive_medication_catalog.json`](../contracts/antihypertensive_medication_catalog.json).
Các nhóm chuẩn gồm ACEI, ARB, CCB, chẹn beta, lợi tiểu, MRA và thuốc khác.
Trong đó lợi tiểu được ghi rõ lợi tiểu quai, thiazide hoặc giống thiazide.

 Nhập danh sách hoạt chất ở `medication.currentDrugNames`; engine đọc danh mục đã lưu,
tạo duy nhất `medication.currentDrugClassList`. Cây 5 dùng `lengthEq(2)`,
`lengthGte(3)` và `contains("diuretic")` trực tiếp trên danh sách này; không cần
biến đếm hoặc cờ lợi tiểu riêng. Cùng cơ chế được dùng cho danh sách thuốc
encounter trước của Cây 3 với `medication.previousEncounterDrugClassList`.
Hoạt chất
không có trong danh mục không bị bỏ qua; cây dừng để rà soát.

Ba biến `bp.controlledAfterTwoDrugs`, `bp.controlledAfterThreeDrugs` và
`bp.controlledAfterFourDrugs` được engine tự tính bằng so sánh HA hiện tại với
đích Cây 2: HATT hiện tại < đích HATT và HATTr hiện tại < đích HATTr.

## Kiểm tra

```bash
python decision_trees/runtime/validate_decision_tree_bundle.py decision_trees/bundle/decision_tree_bundle.json
python -m pytest -q decision_trees/tests
cd decision_trees/ui && npm run smoke
```

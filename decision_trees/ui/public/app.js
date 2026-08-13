"use strict";

const state = {
  bundle: null,
  treeId: null,
  inputMode: "form",
  context: {},
  missingInputIds: new Set(),
  currentView: "tester",
  previewTimer: null,
  previewSequence: 0,
  builderDrafts: {},
  builderSelectedNodeId: null,
  explorerSelectedNodeId: null,
  builderSearch: "",
  explorerSearch: "",
  locale: "vi",
  patientTab: "specs",
  medicationCatalog: { classes: [] },
  lastRunResult: null,
};

const $ = (id) => document.getElementById(id);
const pretty = (value) => JSON.stringify(value, null, 2);

const NODE_COLORS = {
  start: "#e8fffc",
  condition: "#fffaf6",
  branch: "#fffaf6",
  inference: "#f3fffe",
  link: "#e8f1ff",
  end: "#f9f2ff",
};

const NODE_BORDERS = {
  start: "#00c8b3",
  condition: "#ff8d28",
  branch: "#ff8d28",
  inference: "#00c8b3",
  link: "#2563eb",
  end: "#cb30e0",
};

const VIEW_LABELS = {
  en: { tester: "Tree Tester", explorer: "Tree Explorer", builder: "Tree Builder" },
  vi: { tester: "Chạy thử cây", explorer: "Khám phá cây", builder: "Xây dựng cây" },
};

const UI_LABELS = {
  en: {
    "bp.office.measurement1.systolicMmHg": "Clinic measurement 1 — systolic BP",
    "bp.office.measurement1.diastolicMmHg": "Clinic measurement 1 — diastolic BP",
    "bp.office.measurement2.systolicMmHg": "Clinic measurement 2 — systolic BP",
    "bp.office.measurement2.diastolicMmHg": "Clinic measurement 2 — diastolic BP",
    "bp.office.measurement3.systolicMmHg": "Clinic measurement 3 — systolic BP",
    "bp.office.measurement3.diastolicMmHg": "Clinic measurement 3 — diastolic BP",
    "bp.latestSystolicMmHg": "Latest systolic BP",
    "bp.latestDiastolicMmHg": "Latest diastolic BP",
    "hypertension.diagnosisCategory": "Hypertension diagnosis",
    "risk.factorCount": "Number of cardiovascular risk factors",
    "risk.cardiovascularRiskClass": "Cardiovascular risk level",
    "treatment.targetSystolicBpMmHg": "Target systolic BP",
    "treatment.targetDiastolicBpMmHg": "Target diastolic BP",
    "treatment.medicationStartSystolicBpMmHg": "SBP threshold to start medication",
    "treatment.medicationStartDiastolicBpMmHg": "DBP threshold to start medication",
    "medication.antihypertensiveDrugClasses": "Current antihypertensive drug groups (A/B/C/D)",
    "medication.antihypertensiveDrugClassCount": "Number of antihypertensive drug groups",
    "medication.regimenAtLeastFourWeeks": "Regimen used for at least 4 weeks",
    "medication.regimenStartDate": "Regimen start or last change date",
    "bp.isControlled": "BP controlled to target",
    decisionTree: "Decision Tree",
    dynamicForm: "Dynamic form",
    patientInfo: "Patient Simulator",
    run: "Manual Traverse",
    startTraversal: "Start Traversal",
    reset: "Reset",
    simulatorSubtitle: "Fill in fields to simulate traversal.",
    currentTree: "Tree being viewed",
    localRecord: "Load patient record",
    localRecordHelp: "Enter a preset patient ID (for example demo_high_risk) or paste patient JSON to load the record.",
    localRecordPlaceholder: "Preset patient ID or paste JSON",
    open: "Load record",
    preset: "Preset patient",
    patientSpecs: "Patient information",
    clinicalHistory: "Clinical history",
    inputData: "Enter data",
    sharedDataHint: "The same patient record is used across the five linked trees.",
    currentRun: "Current run",
    tree: "Decision tree:",
    nodeInfo: "Node Information",
    navigate: "Navigate tree",
    options: "Options",
    selectedNode: "Selected node",
    description: "Description",
    metadata: "Metadata",
    treeLibrary: "Tree Library",
    view: "View",
    guideline: "Guideline",
    setBased: "Set-based",
    newTree: "＋ New tree (reset)",
    importJson: "↓ Import JSON",
    exportJson: "↑ Export JSON",
    nodeProperties: "Node properties",
    selected: "Selected:",
    properties: "Properties",
    live: "Live visualization",
    ready: "System Ready",
    language: "Switch language",
    legendRoot: "Root",
    legendDecision: "Decision",
    legendRecommendation: "Recommendation",
    legendInformation: "Information",
    legendOutcome: "Outcome",
  },
  vi: {
    "bp.office.measurement1.systolicMmHg": "HATT lần đo 1",
    "bp.office.measurement1.diastolicMmHg": "HATTr lần đo 1",
    "bp.office.measurement2.systolicMmHg": "HATT lần đo 2",
    "bp.office.measurement2.diastolicMmHg": "HATTr lần đo 2",
    "bp.office.measurement3.systolicMmHg": "HATT lần đo 3",
    "bp.office.measurement3.diastolicMmHg": "HATTr lần đo 3",
    "bp.latestSystolicMmHg": "HATT gần nhất",
    "bp.latestDiastolicMmHg": "HATTr gần nhất",
    "hypertension.diagnosisCategory": "Kết quả chẩn đoán tăng huyết áp",
    "patient.conditionCodes": "Bệnh đồng mắc và chẩn đoán đã biết",
    "risk.factorCount": "Số lượng yếu tố nguy cơ",
    "risk.cardiovascularRiskClass": "Mức nguy cơ tim mạch",
    "treatment.targetSystolicBpMmHg": "Mục tiêu HATT",
    "treatment.targetDiastolicBpMmHg": "Mục tiêu HATTr",
    "treatment.medicationStartSystolicBpMmHg": "Ngưỡng HATT bắt đầu điều trị thuốc",
    "treatment.medicationStartDiastolicBpMmHg": "Ngưỡng HATTr bắt đầu điều trị thuốc",
    "medication.antihypertensiveDrugClasses": "Các nhóm thuốc hạ áp đang dùng (A/B/C/D)",
    "medication.antihypertensiveDrugClassCount": "Số nhóm thuốc hạ áp",
    "medication.regimenAtLeastFourWeeks": "Phác đồ đã dùng đủ 4 tuần",
    "medication.regimenStartDate": "Ngày bắt đầu hoặc thay đổi phác đồ",
    "bp.isControlled": "Huyết áp đạt mục tiêu",
    decisionTree: "Cây quyết định",
    dynamicForm: "Biểu mẫu động",
    patientInfo: "Mô phỏng người bệnh",
    run: "Chạy cây đang xem",
    startTraversal: "Chạy toàn bộ quy trình",
    reset: "Xóa dữ liệu",
    simulatorSubtitle: "Điền dữ liệu để mô phỏng đường đi qua phác đồ.",
    currentTree: "Cây đang xem",
    localRecord: "Nạp hồ sơ bệnh nhân",
    localRecordHelp: "Nhập mã bệnh nhân mẫu (ví dụ demo_high_risk) hoặc dán dữ liệu JSON để nạp hồ sơ.",
    localRecordPlaceholder: "Mã bệnh nhân mẫu hoặc dán JSON",
    open: "Nạp hồ sơ",
    preset: "Bệnh nhân mẫu",
    patientSpecs: "Thông tin bệnh nhân",
    clinicalHistory: "Lịch sử lâm sàng",
    inputData: "Nhập dữ liệu",
    sharedDataHint: "Một hồ sơ bệnh nhân được dùng xuyên suốt năm cây liên kết.",
    currentRun: "Lần chạy hiện tại",
    tree: "Cây quyết định:",
    nodeInfo: "Thông tin node",
    navigate: "Điều hướng cây",
    options: "Các nhánh",
    selectedNode: "Node đang chọn",
    description: "Mô tả",
    metadata: "Thông tin bổ sung",
    treeLibrary: "Thư viện cây",
    view: "Chế độ xem",
    guideline: "Guideline",
    setBased: "Theo tập dữ liệu",
    newTree: "＋ Tạo cây mới",
    importJson: "↓ Nhập JSON",
    exportJson: "↑ Xuất JSON",
    nodeProperties: "Thuộc tính node",
    selected: "Đang chọn:",
    properties: "Thuộc tính",
    live: "Hiển thị trực quan",
    ready: "Hệ thống sẵn sàng",
    language: "Chuyển ngôn ngữ",
    legendRoot: "Bắt đầu",
    legendDecision: "Điều kiện",
    legendRecommendation: "Khuyến nghị",
    legendInformation: "Thông tin",
    legendOutcome: "Kết luận",
  },
};

const VARIABLE_TRANSLATIONS = {
  en: {
    "bp.office.measurement1.systolicMmHg": "Clinic measurement 1 — systolic BP",
    "bp.office.measurement1.diastolicMmHg": "Clinic measurement 1 — diastolic BP",
    "bp.office.measurement2.systolicMmHg": "Clinic measurement 2 — systolic BP",
    "bp.office.measurement2.diastolicMmHg": "Clinic measurement 2 — diastolic BP",
    "bp.office.measurement3.systolicMmHg": "Clinic measurement 3 — systolic BP",
    "bp.office.measurement3.diastolicMmHg": "Clinic measurement 3 — diastolic BP",
    "bp.latestSystolicMmHg": "Latest systolic BP",
    "bp.latestDiastolicMmHg": "Latest diastolic BP",
    "hypertension.diagnosisCategory": "Hypertension diagnosis",
    "risk.factorCount": "Number of cardiovascular risk factors",
    "risk.cardiovascularRiskClass": "Cardiovascular risk level",
    "treatment.targetSystolicBpMmHg": "Target systolic BP",
    "treatment.targetDiastolicBpMmHg": "Target diastolic BP",
    "medication.antihypertensiveDrugClasses": "Current antihypertensive drug groups (A/B/C/D)",
    "medication.antihypertensiveDrugClassCount": "Number of antihypertensive drug groups",
    "medication.regimenAtLeastFourWeeks": "Regimen used for at least 4 weeks",
    "medication.regimenStartDate": "Regimen start or last change date",
    "bp.isControlled": "BP controlled to target",
    "bp.office1.systolicMmHg": "Clinic visit 1 — systolic BP",
    "bp.office1.diastolicMmHg": "Clinic visit 1 — diastolic BP",
    "bp.office2.systolicMmHg": "Clinic visit 2 — systolic BP",
    "bp.office2.diastolicMmHg": "Clinic visit 2 — diastolic BP",
    "bp.office3.systolicMmHg": "Clinic visit 3 — systolic BP",
    "bp.office3.diastolicMmHg": "Clinic visit 3 — diastolic BP",
    "patient.diagnosisCodes": "Patient diagnosis codes (ICD-10/SNOMED CT)",
    "patient.conditionCodes": "Known diagnoses and comorbidities",
    "patient.birthDate": "Date of birth",
    "patient.sex": "Sex",
    "encounter.number": "Encounter number",
    "vitals.heartRate": "Heart rate",
    "patient.heightM": "Height",
    "patient.weightKg": "Weight",
    "lab.eGfr": "eGFR",
    "lab.ldlCholesterol": "LDL-C",
    "lab.triglycerides": "Triglycerides",
    "risk.lipidAbnormality": "Abnormal lipids",
    "risk.familyHistoryPrematureCvd": "Family history of premature cardiovascular disease",
    "risk.currentSmoker": "Current smoker",
    "risk.socialEnvironmentalRisk": "Adverse social or environmental factors",
    "bp.latest.systolicMmHg": "Latest BP — systolic",
    "bp.latest.diastolicMmHg": "Latest BP — diastolic",
    "medication.currentDrugNames": "Current antihypertensive medicines",
    "medication.previousEncounterDrugNames": "Medicines prescribed at the previous encounter",
    "medication.regimenStartDate": "Regimen start or last change date",
    "medication.drugClass": "Antihypertensive drug class",
    "encounter.number": "Number of visits so far",
  },
  vi: {
    "bp.office.measurement1.systolicMmHg": "HATT lần đo 1",
    "bp.office.measurement1.diastolicMmHg": "HATTr lần đo 1",
    "bp.office.measurement2.systolicMmHg": "HATT lần đo 2",
    "bp.office.measurement2.diastolicMmHg": "HATTr lần đo 2",
    "bp.office.measurement3.systolicMmHg": "HATT lần đo 3",
    "bp.office.measurement3.diastolicMmHg": "HATTr lần đo 3",
    "bp.latestSystolicMmHg": "HATT gần nhất",
    "bp.latestDiastolicMmHg": "HATTr gần nhất",
    "hypertension.diagnosisCategory": "Kết quả chẩn đoán tăng huyết áp",
    "risk.factorCount": "Số lượng yếu tố nguy cơ",
    "risk.cardiovascularRiskClass": "Mức nguy cơ tim mạch",
    "treatment.targetSystolicBpMmHg": "Mục tiêu HATT",
    "treatment.targetDiastolicBpMmHg": "Mục tiêu HATTr",
    "medication.antihypertensiveDrugClasses": "Các nhóm thuốc hạ áp đang dùng (A/B/C/D)",
    "medication.antihypertensiveDrugClassCount": "Số nhóm thuốc hạ áp",
    "medication.regimenAtLeastFourWeeks": "Phác đồ đã dùng đủ 4 tuần",
    "medication.regimenStartDate": "Ngày bắt đầu hoặc thay đổi phác đồ",
    "bp.isControlled": "Huyết áp đạt mục tiêu",
    "comorbidity.targetOrganDamageOrCvd": "Bằng chứng tổn thương cơ quan đích hoặc bệnh tim mạch",
    "comorbidity.heartFailureReducedEjectionFraction": "Suy tim phân suất tống máu giảm",
    "comorbidity.atheroscleroticCvd": "Bệnh tim mạch do xơ vữa",
    "comorbidity.type2Diabetes": "Đái tháo đường type 2",
    "treatment.targetSystolicMmHg": "Đích huyết áp tâm thu",
    "treatment.targetDiastolicMmHg": "Đích huyết áp tâm trương",
    "risk.class": "Phân tầng nguy cơ tim mạch",
    "bp.category": "Phân loại huyết áp",
    "medication.previousEncounterDrugClassList": "Nhóm thuốc ở lần khám trước",
    "medication.currentDrugClassList": "Nhóm thuốc đang sử dụng",
    "encounter.number": "Số lần khám hiện tại",
  },
};

const FORM_GROUPS = {
  bloodPressure: {
    ids: ["bp.office.measurement1.systolicMmHg", "bp.office.measurement1.diastolicMmHg", "bp.office.measurement2.systolicMmHg", "bp.office.measurement2.diastolicMmHg", "bp.office.measurement3.systolicMmHg", "bp.office.measurement3.diastolicMmHg"],
    vi: "Huyết áp",
    en: "Blood pressure",
    tab: "specs",
  },
  demographics: {
    ids: ["patient.birthDate", "patient.sex"],
    vi: "Thông tin người bệnh và nguy cơ",
    en: "Demographics and risk",
    tab: "specs",
  },
  clinicalHistory: {
    ids: ["encounter.number", "patient.conditionCodes", "medication.currentDrugNames", "medication.previousEncounterDrugNames", "medication.regimenStartDate"],
    vi: "Lịch sử lâm sàng và điều trị",
    en: "Clinical history and treatment",
    tab: "history",
  },
  comorbidities: {
    ids: ["condition.hasChronicKidneyDisease", "condition.hasDiabetesMellitus", "condition.hasType2DiabetesMellitus", "condition.hasCoronaryArteryDisease", "condition.hasHeartFailure", "condition.hasHeartFailureWithReducedEjectionFraction", "condition.hasStroke", "condition.hasPeripheralArteryDisease", "condition.hasAtrialFibrillation", "cardiovascular.hasEstablishedCvd", "risk.hasTargetOrganDamage", "risk.factorCount"],
    vi: "Bệnh đồng mắc và yếu tố lâm sàng",
    en: "Comorbidities and clinical flags",
    tab: "specs",
  },
  treatment: {
    ids: ["medication.antihypertensiveDrugClasses", "medication.antihypertensiveDrugClassCount", "medication.regimenAtLeastFourWeeks"],
    vi: "Điều trị và tái khám",
    en: "Treatment and follow-up",
    tab: "history",
  },
};

const PATIENT_PRESETS = {
  demo_normal: {
    label: "Demo — Huyết áp bình thường",
    values: {
      "bp.office.measurement1.systolicMmHg": 128, "bp.office.measurement1.diastolicMmHg": 78,
      "bp.office.measurement2.systolicMmHg": 126, "bp.office.measurement2.diastolicMmHg": 78,
      "bp.office.measurement3.systolicMmHg": 125, "bp.office.measurement3.diastolicMmHg": 78,
      "patient.conditionCodes": "Không ghi nhận bệnh đồng mắc", "patient.birthDate": "1985-04-12",
      "patient.sex": "female", "encounter.number": 1,
      "vitals.heartRateBpm": 70, "anthropometrics.heightM": 1.65, "anthropometrics.weightKg": 60,
      "lab.eGfr": 90, "lab.ldlCholesterol": 2, "lab.triglycerides": 1,
      "socialHistory.smokingStatus": "never",
    },
  },
  demo_high_risk: {
    label: "Demo — Nguy cơ cao",
    values: {
      "bp.office.measurement1.systolicMmHg": 154, "bp.office.measurement1.diastolicMmHg": 94,
      "bp.office.measurement2.systolicMmHg": 150, "bp.office.measurement2.diastolicMmHg": 92,
      "bp.office.measurement3.systolicMmHg": 148, "bp.office.measurement3.diastolicMmHg": 90,
      "patient.conditionCodes": "I25.1,I50.9,E11.9", "patient.birthDate": "1955-07-21",
      "patient.sex": "male", "encounter.number": 2,
      "vitals.heartRateBpm": 84, "anthropometrics.heightM": 1.70, "anthropometrics.weightKg": 82,
      "lab.eGfr": 52, "lab.ldlCholesterol": 4.0, "lab.triglycerides": 2.2,
      "socialHistory.smokingStatus": "current",
      "medication.previousEncounterDrugNames": "Amlodipine, Losartan",
      "medication.currentDrugNames": "Amlodipine, Losartan, Indapamide",
      "medication.regimenStartDate": "2026-06-15",
    },
  },
  demo_full_flow_tha: {
    label: "Demo — THA tái khám, 4 nhóm thuốc",
    values: {
      "bp.office.measurement1.systolicMmHg": 150, "bp.office.measurement1.diastolicMmHg": 95,
      "bp.office.measurement2.systolicMmHg": 150, "bp.office.measurement2.diastolicMmHg": 95,
      "bp.office.measurement3.systolicMmHg": 150, "bp.office.measurement3.diastolicMmHg": 95,
      "patient.conditionCodes": "Không ghi nhận bệnh đồng mắc", "patient.birthDate": "1985-04-12",
      "patient.sex": "female", "encounter.number": 2,
      "vitals.heartRateBpm": 70, "anthropometrics.heightM": 1.65, "anthropometrics.weightKg": 60,
      "lab.eGfr": 90, "lab.ldlCholesterol": 2, "lab.triglycerides": 1,
      "socialHistory.smokingStatus": "never",
      "risk.familyHistoryPrematureCvd": false, "risk.socialEnvironmentalRisk": false,
      "medication.currentDrugNames": "Losartan, Amlodipine, Indapamide, Spironolactone",
      "medication.previousEncounterDrugNames": "Losartan, Amlodipine, Indapamide, Spironolactone",
      "medication.regimenStartDate": "2026-06-15",
    },
  },
  demo_full_flow_habtc_first_visit: {
    label: "Demo — HABTC lần khám đầu",
    values: {
      "bp.office.measurement1.systolicMmHg": 135, "bp.office.measurement1.diastolicMmHg": 87,
      "bp.office.measurement2.systolicMmHg": 135, "bp.office.measurement2.diastolicMmHg": 87,
      "bp.office.measurement3.systolicMmHg": 135, "bp.office.measurement3.diastolicMmHg": 87,
      "patient.conditionCodes": "Không ghi nhận bệnh đồng mắc", "patient.birthDate": "1990-05-20",
      "patient.sex": "female", "encounter.number": 1,
      "vitals.heartRateBpm": 68, "anthropometrics.heightM": 1.62, "anthropometrics.weightKg": 58,
      "lab.eGfr": 95, "lab.ldlCholesterol": 2, "lab.triglycerides": 1,
      "socialHistory.smokingStatus": "never",
      "risk.familyHistoryPrematureCvd": false, "risk.socialEnvironmentalRisk": false,
    },
  },
  demo_full_flow_tha_comorbidity: {
    label: "Demo — THA tái khám có bệnh đồng mắc",
    values: {
      "bp.office.measurement1.systolicMmHg": 150, "bp.office.measurement1.diastolicMmHg": 95,
      "bp.office.measurement2.systolicMmHg": 150, "bp.office.measurement2.diastolicMmHg": 95,
      "bp.office.measurement3.systolicMmHg": 150, "bp.office.measurement3.diastolicMmHg": 95,
      "patient.conditionCodes": "I25.1", "patient.birthDate": "1960-05-20",
      "patient.sex": "male", "encounter.number": 2,
      "vitals.heartRateBpm": 72, "anthropometrics.heightM": 1.70, "anthropometrics.weightKg": 76,
      "lab.eGfr": 78, "lab.ldlCholesterol": 3.2, "lab.triglycerides": 1.4,
      "socialHistory.smokingStatus": "never",
      "risk.familyHistoryPrematureCvd": false, "risk.socialEnvironmentalRisk": false,
      "medication.currentDrugNames": "Losartan, Amlodipine, Indapamide, Spironolactone",
      "medication.previousEncounterDrugNames": "Losartan, Amlodipine, Indapamide, Spironolactone",
      "medication.regimenStartDate": "2026-06-15",
    },
  },
};


const displayTranslations = new Map([
  ["BP Diagnosis Tree", "Cây chẩn đoán tăng huyết áp"],
  ["BP Thresholds and Targets Tree", "Ngưỡng và mục tiêu huyết áp"],
  ["Optimized Hypertension Treatment Tree", "Điều trị tăng huyết áp tối ưu"],
  ["Hypertension Risk Stratification Tree", "Phân tầng nguy cơ tăng huyết áp"],
  ["Hypertension General — Phân loại THA", "Phân loại tăng huyết áp tổng quát"],
  ["Seated SBP 140–169 mmHg?", "HATT tư thế ngồi 140–169 mmHg?"],
  ["Out of Range — Cần đánh giá thêm", "Ngoài khoảng — Cần đánh giá thêm"],
  ["Defer — Đánh giá lại sau", "Tạm hoãn — Đánh giá lại sau"],
  ["Uncontrolled HTN — Phác đồ 2 thuốc", "THA chưa kiểm soát — Phác đồ 2 thuốc"],
  ["Resistant HTN — ≥3 thuốc + lợi tiểu", "THA kháng trị — ≥3 thuốc + lợi tiểu"],
  ["Yes", "Có"],
  ["No", "Không"],
  ["Exactly 2", "Đúng 2"],
  ["Target met", "Đạt mục tiêu"],
  ["Not met", "Chưa đạt mục tiêu"],
  [" (reading)", ""],
  [" (week)", ""],
  [" (class)", ""],
]);

const englishGraphTranslations = new Map([
  ["Bắt đầu đánh giá huyết áp", "Start blood pressure assessment"],
  ["Cơn tăng huyết áp", "Hypertensive crisis"],
  ["Tăng huyết áp", "Hypertension"],
  ["Huyết áp bình thường", "Normal blood pressure"],
  ["Huyết áp bình thường cao", "High-normal blood pressure"],
  ["Bắt đầu xác định mục tiêu huyết áp", "Start target blood pressure assessment"],
  ["Bắt đầu phân tầng nguy cơ tim mạch", "Start cardiovascular risk stratification"],
  ["Bắt đầu đánh giá phác đồ điều trị", "Start treatment regimen assessment"],
  ["Bắt đầu lựa chọn chiến lược điều trị", "Start treatment strategy selection"],
  ["Cơn tăng huyết áp", "Hypertensive crisis"],
  ["Nguy cơ thấp", "Low risk"],
  ["Nguy cơ thấp/trung bình", "Low-to-moderate risk"],
  ["Nguy cơ trung bình", "Moderate risk"],
  ["Nguy cơ trung bình/cao", "Moderate-to-high risk"],
  ["Nguy cơ cao", "High risk"],
  ["Thay đổi lối sống và hẹn tái khám", "Lifestyle changes and follow-up"],
  ["Dùng một trong bốn nhóm thuốc A, B, C hoặc D", "Use one of four drug groups: A, B, C or D"],
  ["Dùng phối hợp hai nhóm thuốc A+C hoặc A+D", "Use two-drug combination A+C or A+D"],
  ["Dùng phối hợp ba nhóm thuốc A+C+D", "Use three-drug combination A+C+D"],
  ["Tăng huyết áp kháng trị", "Resistant hypertension"],
  ["Tiếp tục phác đồ hiện tại", "Continue current regimen"],
  ["Tham khảo chuyên gia", "Refer to specialist"],
  ["Chuyển sang phân tầng nguy cơ tim mạch", "Go to cardiovascular risk stratification"],
  ["Chuyển sang xác định mục tiêu huyết áp", "Go to blood pressure target assessment"],
  ["Chuyển sang đánh giá phác đồ điều trị", "Go to treatment regimen assessment"],
  ["Chỉ định bắt buộc theo bệnh đồng mắc", "Mandatory indication by comorbidity"],
  ["Kiểm tra bệnh đồng mắc", "Check comorbidities"],
  ["Xác định mức độ tăng huyết áp", "Determine hypertension grade"],
  ["Số lượng yếu tố nguy cơ ≤2?", "Are there ≤2 cardiovascular risk factors?"],
  ["Huyết áp đã được kiểm soát theo mục tiêu?", "Is blood pressure controlled to target?"],
  ["Người bệnh từ 18 tuổi trở lên?", "Is the patient at least 18 years old?"],
  ["Lần 1:", "Visit 1:"], ["Lần 2:", "Visit 2:"], ["Lần 3:", "Visit 3:"],
  ["HATT", "SBP"], ["HATTr", "DBP"], ["gần nhất", "latest"],
  ["Có bệnh đồng mắc không?", "Are there any comorbidities?"],
  ["Kết quả chẩn đoán là huyết áp bình thường cao?", "Is the diagnosis high-normal blood pressure?"],
  ["Kết quả chẩn đoán là THA hay HABTC?", "Is the diagnosis hypertension or high-normal blood pressure?"],
  ["Số lượng YTNC = 0?", "Are there 0 risk factors?"],
  ["Số lượng YTNC = 1–2?", "Are there 1–2 risk factors?"],
  ["Số lượng YTNC ≤1?", "Are there ≤1 risk factors?"],
  ["Số nhóm thuốc hạ áp = 2?", "Are there exactly 2 antihypertensive drug groups?"],
  ["Số nhóm thuốc hạ áp ≥3?", "Are there at least 3 antihypertensive drug groups?"],
  ["Phác đồ đã được sử dụng ≥4 tuần?", "Has the regimen been used for at least 4 weeks?"],
  ["Phác đồ đã dùng đủ 4 tuần", "Regimen used for at least 4 weeks"],
]);

const valueTranslations = new Map([
  ["NO_KNOWN_CODES", "Không ghi nhận bệnh đồng mắc"],
  ["true", "Có"],
  ["false", "Không"],
  ["office", "Phòng khám"],
  ["office_3rd", "Đo phòng khám lần 3"],
  ["home", "Tại nhà"],
  ["normal", "Bình thường"],
  ["high_normal", "Bình thường cao"],
  ["grade1", "Tăng huyết áp độ 1"],
  ["grade2", "Tăng huyết áp độ 2"],
  ["high", "Nguy cơ cao"],
  ["moderate", "Nguy cơ trung bình"],
  ["low", "Nguy cơ thấp"],
  ["high_risk_or_comorbidity", "Nguy cơ cao hoặc có bệnh đồng mắc"],
  ["comorbidity", "Có bệnh đồng mắc"],
  ["no_comorbidity", "Không có bệnh đồng mắc"],
  ["two_drug_combination", "Phối hợp 2 thuốc"],
  ["two_drug_classes", "Phối hợp 2 nhóm thuốc"],
  ["three_drug_classes", "Phối hợp 3 nhóm thuốc"],
  ["add_drug_class_d", "Bổ sung nhóm thuốc D"],
  ["monotherapy_or_two_drug", "Đơn trị hoặc phối hợp 2 thuốc"],
  ["lifestyle_only", "Thay đổi lối sống"],
  ["initial_treatment", "Điều trị ban đầu"],
  ["mandatory_indication", "Có chỉ định bắt buộc"],
  ["escalate_two_drugs", "Tăng lên 2 nhóm thuốc"],
  ["maintain_two_drugs", "Duy trì 2 nhóm thuốc"],
  ["escalate_three_drugs", "Tăng lên 3 nhóm thuốc"],
  ["maintain_three_drugs", "Duy trì 3 nhóm thuốc"],
  ["escalate_four_drugs", "Tăng lên 4 nhóm thuốc"],
  ["maintain_four_drugs", "Duy trì 4 nhóm thuốc"],
  ["resistant_htn_referral", "Chuyển đánh giá THA kháng trị"],
  ["normal_bp", "Huyết áp bình thường"],
  ["high_normal_bp", "Huyết áp bình thường cao"],
  ["hypertension", "Tăng huyết áp"],
  ["hypertensive_crisis", "Cơn tăng huyết áp"],
  ["white_coat_hypertension", "Tăng huyết áp áo choàng trắng"],
  ["masked_hypertension", "Tăng huyết áp ẩn giấu"],
  ["risk_high", "Nguy cơ cao"],
  ["risk_medium", "Nguy cơ trung bình"],
  ["risk_low", "Nguy cơ thấp"],
  ["male", "Nam"],
  ["female", "Nữ"],
  ["other", "Khác"],
  ["unknown", "Chưa xác định"],
  ["mandatory_coronary_artery_disease", "Chỉ định bắt buộc — bệnh mạch vành/xơ vữa"],
  ["mandatory_heart_failure_reduced_ef", "Chỉ định bắt buộc — suy tim EF giảm"],
  ["mandatory_stroke", "Chỉ định bắt buộc — tiền sử đột quỵ"],
  ["mandatory_chronic_kidney_disease", "Chỉ định bắt buộc — bệnh thận mạn"],
  ["mandatory_type2_diabetes", "Chỉ định bắt buộc — đái tháo đường type 2"],
  ["acei", "Ức chế men chuyển (ACEI — A)"],
  ["arb", "Ức chế thụ thể angiotensin (ARB — A)"],
  ["ccb", "Chẹn kênh canxi (CCB — C)"],
  ["beta_blocker", "Chẹn beta (BB — B)"],
  ["diuretic", "Lợi tiểu (D)"],
  ["mra", "Đối kháng thụ thể mineralocorticoid (MRA)"],
  ["other", "Thuốc hạ áp khác"],
  ["uncontrolled_htn_arm", "THA chưa kiểm soát"],
  ["resistant_htn_arm", "THA kháng trị"],
  ["add_diuretic", "Bổ sung lợi tiểu và phân loại lại"],
  ["resistant_defer", "Tạm hoãn, đánh giá lại sau"],
  ["resistant_out_of_range", "Ngoài khoảng, cần xử trí trước"],
  ["resistant_agent_count_review_required", "Cần rà soát số nhóm thuốc"],
]);

let graphInstance = null;
let visualEndAliases = new Map();
let visualGraph = { nodes: [], edges: [] };

function localizeText(value) {
  let text = String(value || "");
  if (state.locale === "en") {
    englishGraphTranslations.forEach((translated, source) => {
      text = text.split(source).join(translated);
    });
    return text;
  }
  displayTranslations.forEach((translated, source) => {
    text = text.split(source).join(translated);
  });
  return text;
}

function applyLocale() {
  const labels = UI_LABELS[state.locale];
  const set = (selector, value) => {
    const element = document.querySelector(selector);
    if (!element) return;
    const childElements = [...element.children];
    element.replaceChildren(...childElements, document.createTextNode(value));
  };
  set("#language-label", state.locale === "vi" ? "EN" : "VI");
  $("language-flag").src = state.locale === "vi" ? "/icon/language_en.svg" : "/icon/language_vi.svg";
  $("language-flag").alt = state.locale === "vi" ? "English" : "Tiếng Việt";
  $("language-toggle").setAttribute("aria-label", labels.language);
  set("#tab-tester", VIEW_LABELS[state.locale].tester);
  set("#tab-explorer", VIEW_LABELS[state.locale].explorer);
  set("#tab-builder", VIEW_LABELS[state.locale].builder);
  set("#sidebar-title", VIEW_LABELS[state.locale][state.currentView]);
  if (state.currentView === "tester") set("#sidebar-title", labels.patientInfo);
  set("#simulator-subtitle", labels.simulatorSubtitle);
  set("label[for=tree-select]", labels.currentTree);
  set("label[for=patient-record-id]", labels.localRecord);
  $("#patient-record-id").placeholder = labels.localRecordPlaceholder;
  $("#patient-record-help").textContent = labels.localRecordHelp;
  set("#open-patient-record", labels.open);
  set("#legend-root", labels.legendRoot);
  set("#legend-decision", labels.legendDecision);
  set("#legend-recommendation", labels.legendRecommendation);
  set("#legend-information", labels.legendInformation);
  set("#legend-outcome", labels.legendOutcome);
  set(".preset-field span", labels.preset);
  set("#patient-tab-specs", labels.patientSpecs);
  set("#patient-tab-history", labels.clinicalHistory);
  set("#form-panel h3", labels.inputData);
  set("#start-traversal", labels.startTraversal);
  set("#mode-form", labels.dynamicForm);
  set("#mode-json", "JSON");
  set("#run-tree", labels.run);
  set(".result-title", labels.currentRun);
  set("#result-box > div:nth-child(2)", labels.tree);
  set(".explorer-sidebar h2", labels.nodeInfo);
  set(".explorer-sidebar .field-label", labels.options);
  const explorerSectionLabels = [labels.navigate, labels.selectedNode, labels.description, labels.metadata];
  document.querySelectorAll(".explorer-sidebar .section-row strong").forEach((element, index) => {
    if (explorerSectionLabels[index]) element.textContent = explorerSectionLabels[index];
  });
  set(".builder-library h2", labels.treeLibrary);
  set(".builder-library .section-row strong", labels.view);
  set(".builder-segment button:nth-child(1)", labels.guideline);
  set(".builder-segment button:nth-child(2)", labels.setBased);
  set("#new-tree-button", labels.newTree);
  set("#import-tree-button", labels.importJson);
  set("#export-tree-button", labels.exportJson);
  set(".builder-properties h2", labels.nodeProperties);
  set(".builder-properties p strong", labels.selected);
  set(".builder-properties .section-row:last-of-type strong", labels.properties);
  const visualTitle = state.currentView === "explorer"
    ? VIEW_LABELS[state.locale].explorer
    : state.currentView === "builder"
      ? VIEW_LABELS[state.locale].builder
      : labels.live;
  set(".visual-card h2", visualTitle);
  set("footer div", labels.ready);
  const explorerSearch = $("explorer-search");
  explorerSearch.placeholder = state.locale === "en" ? "Search nodes..." : "Tìm kiếm node";
  explorerSearch.setAttribute("aria-label", state.locale === "en" ? "Search nodes" : "Tìm kiếm node");
  const builderSearch = $("builder-search");
  builderSearch.placeholder = state.locale === "en" ? "Search trees..." : "Tìm kiếm cây";
  builderSearch.setAttribute("aria-label", state.locale === "en" ? "Search trees" : "Tìm kiếm cây");
  document.documentElement.lang = state.locale;
}

function valueLabel(value, variableId = "") {
  const key = String(value);
  if (variableId === "patient.sex" && key === "other") return state.locale === "en" ? "Other" : "Khác";
  if (variableId === "patient.sex" && key === "unknown") return state.locale === "en" ? "Unknown" : "Chưa xác định";
  return valueTranslations.get(key) || localizeText(key.replace(/_/g, " "));
}

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error((data.errors || ["Request failed"]).join("\n"));
  return data;
}

function currentTree() {
  return state.builderDrafts[state.treeId] || state.bundle?.trees.find((item) => item.id === state.treeId);
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function treeLabel(treeId) {
  const target = state.bundle?.trees?.find((item) => item.id === treeId);
  return localizeText(target?.name || "cây liên kết");
}

function variableLabel(variableId) {
  const variable = state.bundle.variables.find((item) => item.id === variableId);
  return variableDisplayLabel(variable) || "Thông tin cần nhập";
}

function variableDisplayLabel(variable) {
  if (!variable) return "";
  const translated = VARIABLE_TRANSLATIONS[state.locale]?.[variable.id];
  if (translated) return translated;
  const raw = String(variable.label || variable.id);
  if (raw !== variable.id) return localizeText(raw);
  const technical = variable.id.split(".").at(-1).replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ");
  return state.locale === "en"
    ? technical.charAt(0).toUpperCase() + technical.slice(1)
    : `Thông tin ${technical}`;
}

function resultDisplayLabel(result) {
  const candidates = [result?.resultCode, result?.outcomeCode, result?.decision];
  for (const candidate of candidates) {
    if (candidate == null) continue;
    if (typeof candidate === "object") {
      const nested = candidate.title || candidate.label || candidate.name || candidate.code || candidate.id;
      if (nested) return localizeText(valueLabel(nested));
    } else {
      return localizeText(valueLabel(candidate));
    }
  }
  return "Hoàn tất";
}

function nodeData(node) {
  if (node?.data && typeof node.data === "object") return node.data;
  if (typeof node?.dataJson === "string") {
    try {
      return JSON.parse(node.dataJson);
    } catch {
      return {};
    }
  }
  return {};
}

function inputVariableIdsForTree(tree) {
  // The patient simulator deliberately renders one shared record rather than
  // changing the form when the selected tree changes. Derived values stay in
  // the context but are never exposed as manual inputs.
  return state.bundle.variables
    .filter((variable) => variable.sourceSystem !== "derived")
    .map((variable) => variable.id);
}

function latestBpValues(context = {}) {
  for (const encounter of [3, 2, 1]) {
    const systolic = context[`bp.office.measurement${encounter}.systolicMmHg`];
    const diastolic = context[`bp.office.measurement${encounter}.diastolicMmHg`];
    if (Number.isFinite(Number(systolic)) && Number.isFinite(Number(diastolic))) {
      return { systolic, diastolic, encounter };
    }
  }
  return { systolic: "", diastolic: "", encounter: null };
}

function refreshLatestBpDisplay(context = state.context) {
  const latest = latestBpValues(context);
  const systolic = $("derived-latest-systolic");
  const diastolic = $("derived-latest-diastolic");
  const source = $("derived-latest-source");
  if (systolic) systolic.value = isProvided(latest.systolic) ? String(latest.systolic) : "";
  if (diastolic) diastolic.value = isProvided(latest.diastolic) ? String(latest.diastolic) : "";
  if (source) source.textContent = latest.encounter
    ? (state.locale === "en" ? `Automatically taken from clinic visit ${latest.encounter}.` : `Tự động lấy từ HA phòng khám lần ${latest.encounter}.`)
    : (state.locale === "en" ? "Enter a complete clinic BP pair to calculate the latest BP." : "Nhập đủ một cặp huyết áp phòng khám để tự tính HA lần đo gần nhất.");
}

function regimenStableWeeks(context = state.context) {
  const start = context["medication.regimenStartDate"];
  if (!start) return null;
  const startDate = new Date(`${String(start).slice(0, 10)}T00:00:00Z`);
  const referenceValue = context.asOf || new Date().toISOString().slice(0, 10);
  const referenceDate = new Date(`${String(referenceValue).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(referenceDate.getTime()) || startDate > referenceDate) return null;
  return Math.floor((referenceDate - startDate) / (7 * 24 * 60 * 60 * 1000));
}

function refreshRegimenStableDisplay(context = state.context) {
  const output = $("derived-regimen-stable-weeks");
  const source = $("derived-regimen-stable-source");
  if (!output || !source) return;
  const weeks = regimenStableWeeks(context);
  output.value = weeks == null ? "" : String(weeks);
  source.textContent = weeks == null
    ? (state.locale === "en" ? "Enter the regimen start or last change date." : "Nhập ngày bắt đầu hoặc chỉnh phác đồ để tự tính.")
    : (state.locale === "en" ? "Automatically calculated from the regimen date and encounter date." : "Tự động tính từ ngày bắt đầu/chỉnh phác đồ đến ngày khám.");
}

function isProvided(value) {
  return value !== undefined && value !== null && value !== "";
}

function treeIdsForRun(tree) {
  return [tree.id];
}

function requiredVariableIdsForRun(tree) {
  const produced = new Set();
  const required = [];
  for (const treeId of treeIdsForRun(tree)) {
    const source = state.bundle.trees.find((item) => item.id === treeId);
    for (const variableId of source?.inputVariables || []) {
      const variable = state.bundle.variables.find((item) => item.id === variableId);
      if (variable?.sourceSystem === "derived") continue;
      // For a linked flow, an output produced by an earlier stage is supplied
      // by context and must not be requested again from the user.
      if (!produced.has(variableId) && !required.includes(variableId)) required.push(variableId);
    }
    for (const variableId of source?.outputVariables || []) produced.add(variableId);
  }
  return required;
}

function showStatus(message, kind = "") {
  $("ui-status").textContent = message;
  $("ui-status").className = `status ${kind}`;
}

function clearPathHighlight(message = "Nhập dữ liệu để xem đường đi trên cây.") {
  if (graphInstance) {
    graphInstance.nodes().removeClass("path-mode path-node path-current path-terminal path-condition-node");
    graphInstance.edges().removeClass("path-mode path-edge path-condition-yes path-condition-no path-condition-threshold path-condition-default");
  }
  $("path-status").textContent = message;
  $("path-status").className = "path-status";
}

function pathConditionClass(label) {
  const text = String(label || "").trim().toLowerCase();
  if (/^(có|yes|true)\b/.test(text)) return "path-condition-yes";
  if (/^(không|no|false)\b/.test(text)) return "path-condition-no";
  if (/[<>≤≥=]|\d/.test(text)) return "path-condition-threshold";
  return "path-condition-default";
}

function formatOutputValue(value) {
  if (typeof value === "string") return value;
  if (value === null) return "null";
  if (Array.isArray(value) || typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function outputAssignments(node) {
  const sets = node?.data?.sets;
  if (!sets || typeof sets !== "object" || Array.isArray(sets)) return "";
  return Object.entries(sets)
    .map(([field, value]) => `${field} = ${formatOutputValue(value)}`)
    .join("\n");
}

function visualNodeLabel(node) {
  // The graph is for clinical users: show the plain-language conclusion on
  // the node. Technical output assignments remain available in the detail
  // panel and runtime context, but must not replace the visible conclusion.
  return localizeText(node.display?.title || outputAssignments(node) || "");
}

function buildVisualGraph(tree) {
  const nodesById = Object.fromEntries(tree.nodes.map((node) => [node.id, node]));
  const outgoingByNode = Object.fromEntries(tree.nodes.map((node) => [node.id, []]));
  tree.edges.forEach((edge) => outgoingByNode[edge.from]?.push(edge));
  const nodes = [];
  const edges = [];
  const visualByCanonicalId = new Map();
  let occurrence = 0;

  const canMergeVisualNode = (node) => {
    // Merge only intermediate decision/action nodes. Keep terminal outcomes
    // and link nodes separate so every incoming branch remains readable.
    if (node.type === "condition" || node.type === "branch") return true;
    if (node.type === "inference") return (outgoingByNode[node.id] || []).length > 0;
    return false;
  };

  // Preserve shared destinations as one visual node. This renders the graph
  // as a compact DAG: several clinical branches can converge on the same
  // conclusion/action without duplicating the node.
  function addOccurrence(nodeId, parentVisualId, incomingEdge, ancestors) {
    if (!nodesById[nodeId] || visualEndAliases.has(nodeId) || ancestors.has(nodeId)) return;
    const node = nodesById[nodeId];
    const mergeNode = canMergeVisualNode(node);
    let visualId = mergeNode ? visualByCanonicalId.get(nodeId) : null;
    const isNew = !visualId;
    if (!visualId) {
      visualId = `${nodeId}__visual_${occurrence++}`;
      if (mergeNode) visualByCanonicalId.set(nodeId, visualId);
      nodes.push({
        data: {
          id: visualId,
          canonicalId: nodeId,
          label: visualNodeLabel(node),
          nodeType: node.type,
          color: NODE_COLORS[node.type] || NODE_COLORS.condition,
          borderColor: NODE_BORDERS[node.type] || NODE_BORDERS.condition,
        },
      });
    }
    if (parentVisualId && incomingEdge) {
      edges.push({
        data: {
          id: `edge-${occurrence}-${parentVisualId}-${visualId}`,
          source: parentVisualId,
          target: visualId,
          canonicalSource: incomingEdge.from,
          canonicalTarget: incomingEdge.to,
          label: localizeText(incomingEdge.label || (incomingEdge.when === "default" ? "" : incomingEdge.when)),
          conditionClass: pathConditionClass(incomingEdge.label || incomingEdge.when),
        },
      });
    }

    const nextAncestors = new Set(ancestors);
    nextAncestors.add(nodeId);
    if (!isNew) return;
    for (const edge of outgoingByNode[nodeId] || []) {
      if (!visualEndAliases.has(edge.to)) addOccurrence(edge.to, visualId, edge, nextAncestors);
    }
  }

  addOccurrence(tree.entryNodeId, null, null, new Set());
  const renderedIds = new Set(nodes.map((item) => item.data.canonicalId));
  for (const node of tree.nodes) {
    if (!visualEndAliases.has(node.id) && !renderedIds.has(node.id)) {
      addOccurrence(node.id, null, null, new Set());
    }
  }
  return { nodes, edges };
}

function highlightPath(result) {
  if (!graphInstance) return;

  const events = (result?.trace || []).filter((event) => event.treeId === state.treeId && event.nodeId);
  const nodeIds = events
    .map((event) => visualEndAliases.get(event.nodeId) || event.nodeId)
    .filter((nodeId, index, ids) => index === 0 || nodeId !== ids[index - 1]);

  graphInstance.nodes().removeClass("path-mode path-node path-current path-terminal path-condition-node");
  graphInstance.edges().removeClass("path-mode path-edge path-condition-yes path-condition-no path-condition-threshold path-condition-default");

  if (!events.length) {
    clearPathHighlight("Chưa có node nào được đánh giá.");
    return;
  }

  graphInstance.nodes().addClass("path-mode");
  graphInstance.edges().addClass("path-mode");
  const visualNodeIds = [];
  const visualEdgeIds = [];
  let current = graphInstance.nodes().filter((node) => node.data("canonicalId") === nodeIds[0]).first();
  if (current?.length) visualNodeIds.push(current.id());
  for (let index = 1; index < nodeIds.length && current?.length; index += 1) {
    const edge = current.outgoers("edge").filter((candidate) => candidate.data("canonicalTarget") === nodeIds[index]).first();
    if (!edge?.length) break;
    current = edge.target();
    visualEdgeIds.push(edge.id());
    visualNodeIds.push(current.id());
  }
  const visualNodeSet = new Set(visualNodeIds);
  const visualEdgeSet = new Set(visualEdgeIds);
  graphInstance.nodes().forEach((node) => {
    if (!visualNodeSet.has(node.id())) return;
    node.addClass("path-node");
    if (["condition", "branch"].includes(node.data("nodeType"))) node.addClass("path-condition-node");
  });
  graphInstance.edges().forEach((edge) => {
    if (!visualEdgeSet.has(edge.id())) return;
    edge.addClass("path-edge");
    edge.addClass(edge.data("conditionClass") || "path-condition-default");
  });

  const lastEvent = events[events.length - 1];
  const lastNode = visualNodeIds.length
    ? graphInstance.getElementById(visualNodeIds[visualNodeIds.length - 1])
    : graphInstance.nodes().filter((node) => node.data("canonicalId") === (visualEndAliases.get(lastEvent.nodeId) || lastEvent.nodeId)).first();
  if (result.status === "completed") lastNode.addClass("path-terminal");
  else lastNode.addClass("path-current");

  const terminal = result.status === "completed"
    ? `Kết quả: ${resultDisplayLabel(result)}`
    : result.status === "needs_data"
      ? `Cần bổ sung: ${(result.missingData || []).map(variableLabel).join(", ") || "chưa đủ điều kiện"}`
      : `Trạng thái: ${result.status}`;
  const linkNote = result.terminalTreeId && result.terminalTreeId !== state.treeId ? ` · chuyển đến ${treeLabel(result.terminalTreeId)}` : "";

  $("path-status").textContent = `Đường đi hiện tại: ${events.length} node${linkNote} · ${terminal}`;
  $("path-status").className = `path-status ${result.status === "completed" ? "completed" : "pending"}`;
}

function renderGraph(tree) {
  if (graphInstance) graphInstance.destroy();

  const nodesById = Object.fromEntries(tree.nodes.map((node) => [node.id, node]));
  const incomingByNode = Object.fromEntries(tree.nodes.map((node) => [node.id, []]));
  tree.edges.forEach((edge) => incomingByNode[edge.to]?.push(edge));

  // Keep terminal outcome nodes as distinct visual nodes. They are not
  // aliases of the preceding action/inference node.
  visualEndAliases = new Map();

  visualGraph = buildVisualGraph(tree);
  const elements = [...visualGraph.nodes, ...visualGraph.edges];

  graphInstance = cytoscape({
    container: $("graph"),
    elements,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(color)",
          "border-color": "data(borderColor)",
          "border-width": 1.2,
          shape: "roundrectangle",
          width: 270,
          height: 96,
          label: "data(label)",
          color: "#212529",
          "font-family": "Inter, ui-sans-serif, system-ui, sans-serif",
          "font-size": 13,
          "font-weight": 700,
          "text-wrap": "wrap",
          "text-max-width": 236,
          "text-valign": "center",
          "text-halign": "center",
          padding: 10,
          "overlay-opacity": 0,
        },
      },
      { selector: "node.path-mode", style: { opacity: 0.34 } },
      { selector: "node.path-node", style: { opacity: 1, "border-color": "#16a34a", "border-width": 4 } },
      { selector: "node.path-condition-node", style: { "background-color": "#ffd166", "border-color": "#f97316", "border-width": 4 } },
      { selector: "node.path-current", style: { "background-color": "#fff4cc", "border-color": "#ff8d28", "border-width": 5 } },
      { selector: "node.path-terminal", style: { "background-color": "#e8fffc", "border-color": "#00c8b3", "border-width": 5 } },
      {
        selector: "edge",
        style: {
          width: 1.4,
          "line-color": "#75839a",
          "target-arrow-color": "#75839a",
          "target-arrow-shape": "triangle",
          "curve-style": "taxi",
          "taxi-direction": "downward",
          "taxi-turn": 24,
          "taxi-turn-min-distance": 12,
          label: "data(label)",
          color: "#52637c",
          "font-size": 11,
          "font-weight": 700,
          "text-background-color": "#f1f4f9",
          "text-background-opacity": 1,
          "text-background-padding": 3,
          "text-rotation": "none",
          "text-margin-y": 0,
        },
      },
      { selector: "edge.path-mode", style: { opacity: 0.2 } },
      { selector: "edge.path-edge", style: { opacity: 1, width: 5, "line-color": "#16a34a", "target-arrow-color": "#16a34a", "z-index": 10 } },
      { selector: "edge.path-edge.path-condition-yes", style: { "text-color": "#047857", "text-background-color": "#bbf7d0", "text-border-color": "#10b981", "text-border-width": 1, "text-border-opacity": 1, "text-background-opacity": 1, "text-background-padding": 6 } },
      { selector: "edge.path-edge.path-condition-no", style: { "text-color": "#b91c1c", "text-background-color": "#fecaca", "text-border-color": "#ef4444", "text-border-width": 1, "text-border-opacity": 1, "text-background-opacity": 1, "text-background-padding": 6 } },
      { selector: "edge.path-edge.path-condition-threshold", style: { "text-color": "#9a3412", "text-background-color": "#fed7aa", "text-border-color": "#f97316", "text-border-width": 1, "text-border-opacity": 1, "text-background-opacity": 1, "text-background-padding": 6 } },
      { selector: "edge.path-edge.path-condition-default", style: { "text-color": "#6d28d9", "text-background-color": "#e9d5ff", "text-border-color": "#a855f7", "text-border-width": 1, "text-border-opacity": 1, "text-background-opacity": 1, "text-background-padding": 6 } },
    ],
    layout: {
      name: "dagre",
      rankDir: "TB",
      ranker: "network-simplex",
      nodeSep: 180,
      edgeSep: 72,
      rankSep: 150,
      padding: 80,
      fit: true,
      animate: false,
    },
    wheelSensitivity: 1.8,
    minZoom: 0.15,
    maxZoom: 2.2,
  });

  graphInstance.on("zoom", updateZoomLabel);
  graphInstance.on("tap", "node", (event) => {
    const selected = tree.nodes.find((node) => node.id === (event.target.data("canonicalId") || event.target.id()));
    if (state.currentView === "explorer") {
      state.explorerSelectedNodeId = selected?.id || null;
      renderExplorerPanel(tree);
    }
    if (state.currentView === "builder") {
      state.builderSelectedNodeId = selected?.id || null;
      renderBuilderPanels(tree);
    }
    const targetTreeId = selected?.type === "link" ? nodeData(selected).targetTreeId : "";
    if (!targetTreeId) return;
    if (state.bundle.trees.some((item) => item.id === targetTreeId)) {
      selectTree(targetTreeId, `Đã chuyển đến cây liên kết: ${treeLabel(targetTreeId)}`);
    } else {
      showStatus("Không tìm thấy cây đích của liên kết.", "bad");
    }
  });

  window.setTimeout(updateZoomLabel, 0);
}

function renderInputForm(tree) {
  const variablesById = Object.fromEntries(state.bundle.variables.map((item) => [item.id, item]));
  const requiredIds = new Set(requiredVariableIdsForRun(tree));
  const form = $("input-form");
  form.innerHTML = "";

  const variableIds = new Set(inputVariableIdsForTree(tree));
  Object.entries(FORM_GROUPS).forEach(([groupId, group]) => {
    if (group.tab !== state.patientTab) return;
    const ids = group.ids.filter((id) => variableIds.has(id) && variablesById[id]);
    if (!ids.length) return;

    const section = document.createElement("details");
    section.className = "input-section";
    section.open = true;
    section.dataset.formGroup = groupId;
    const summary = document.createElement("summary");
    summary.textContent = state.locale === "en" ? group.en : group.vi;
    section.appendChild(summary);
    const fields = document.createElement("div");
    fields.className = "section-fields";

    const rendered = new Set();
    ids.forEach((id) => {
      if (rendered.has(id)) return;
      const variable = variablesById[id];
      const pair = pairIdsFor(id, ids);
      if (pair.length > 1) {
        pair.forEach((pairId) => rendered.add(pairId));
        fields.appendChild(renderPairField(pair, variablesById, requiredIds));
        return;
      }
      rendered.add(id);
      fields.appendChild(renderVariableField(variable, requiredIds.has(id)));
    });
    section.appendChild(fields);
    if (groupId === "bloodPressure") fields.appendChild(renderDerivedLatestBpField());
    if (groupId === "treatment") fields.appendChild(renderDerivedRegimenStableField());
    form.appendChild(section);
  });

  $("input-help").textContent = "";
  if (state.inputMode === "json") $("json-input").value = pretty(state.context);
  refreshLatestBpDisplay(state.context);
  refreshRegimenStableDisplay(state.context);
}

function renderDerivedLatestBpField() {
  const card = document.createElement("div");
  card.className = "input-card pair-card derived-input-card";
  const title = document.createElement("label");
  title.textContent = state.locale === "en" ? "Latest BP" : "HA lần đo gần nhất";
  card.appendChild(title);
  const row = document.createElement("div");
  row.className = "bp-pair-row";
  const latestCaptions = state.locale === "en" ? [["derived-latest-systolic", "SBP"], ["derived-latest-diastolic", "DBP"]] : [["derived-latest-systolic", "HATT"], ["derived-latest-diastolic", "HATTr"]];
  for (const [id, caption] of latestCaptions) {
    const group = document.createElement("div");
    group.className = "bp-pair-field";
    const label = document.createElement("span");
    label.textContent = caption;
    const input = document.createElement("input");
    input.id = id;
    input.type = "number";
    input.readOnly = true;
    input.tabIndex = -1;
    input.setAttribute("aria-label", state.locale === "en"
      ? `${caption === "HATT" ? "Latest BP systolic" : "Latest BP diastolic"}`
      : `${caption === "HATT" ? "HA lần đo gần nhất - HATT" : "HA lần đo gần nhất - HATTr"}`);
    input.setAttribute("aria-readonly", "true");
    group.append(label, input);
    row.appendChild(group);
  }
  const help = document.createElement("small");
  help.id = "derived-latest-source";
  card.append(row, help);
  return card;
}

function renderDerivedRegimenStableField() {
  const card = document.createElement("div");
  card.className = "input-card derived-input-card";
  const title = document.createElement("label");
  title.textContent = state.locale === "en" ? "Stable regimen duration (weeks)" : "Thời gian phác đồ ổn định (tuần)";
  const input = document.createElement("input");
  input.id = "derived-regimen-stable-weeks";
  input.type = "number";
  input.readOnly = true;
  input.tabIndex = -1;
  input.setAttribute("aria-readonly", "true");
  const help = document.createElement("small");
  help.id = "derived-regimen-stable-source";
  card.append(title, input, help);
  return card;
}

function pairIdsFor(id, ids) {
  const match = id.match(/^(.*)\.(systolicMmHg|diastolicMmHg)$/);
  if (!match) return [];
  const sibling = `${match[1]}.${match[2] === "systolicMmHg" ? "diastolicMmHg" : "systolicMmHg"}`;
  return ids.includes(sibling) ? [id, sibling].sort((a, b) => a.endsWith("systolicMmHg") ? -1 : b.endsWith("systolicMmHg") ? 1 : a.localeCompare(b)) : [];
}

function inputElementFor(variable, id) {
  let input;
  if (variable.dataType === "boolean") {
    // A binary switch cannot distinguish "not entered" from an explicit
    // clinical false. Keep a third state so an omitted assessment is never
    // silently converted to a negative finding.
    input = document.createElement("select");
    input.className = "boolean-select";
    input.dataset.booleanInput = "true";
    input.add(new Option(state.locale === "en" ? "Not entered" : "Chưa nhập", ""));
    input.add(new Option(state.locale === "en" ? "Yes" : "Có", "true"));
    input.add(new Option(state.locale === "en" ? "No" : "Không", "false"));
  } else if (variable.dataType === "enum") {
    input = document.createElement("select");
    input.add(new Option(state.locale === "en" ? "Not entered" : "Chưa nhập", ""));
    (variable.allowedValues || []).forEach((value) => input.add(new Option(valueLabel(value, variable.id), value)));
  } else {
    input = document.createElement("input");
    input.type = ["patient.birthDate", "medication.regimenStartDate"].includes(variable.id)
      ? "date"
      : ["string", "array"].includes(variable.dataType) ? "text" : "number";
    if (variable.dataType !== "string") input.step = "any";
    if (variable.validation?.minimum != null) input.min = variable.validation.minimum;
    if (variable.validation?.maximum != null) input.max = variable.validation.maximum;
  }
  input.id = `var-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
  input.dataset.variableId = id;
  const existingValue = state.context[id];
  if (variable.dataType === "boolean") input.checked = existingValue === true || existingValue === "true";
  else if (isProvided(existingValue)) input.value = String(existingValue);
  if (variable.dataType === "boolean") {
    input.value = existingValue === true || existingValue === "true"
      ? "true"
      : existingValue === false || existingValue === "false"
        ? "false"
        : "";
  }
  return input;
}

function medicationEntries() {
  return (state.medicationCatalog?.classes || []).flatMap((group) => (group.drugs || []).map((drug) => {
    const name = typeof drug === "string" ? drug : drug.name;
    return {
      name: String(name || "").toLowerCase(),
      label: typeof drug === "string" ? String(drug) : (drug.label || String(name || "")),
      classCode: group.code,
      classLabel: group.shortLabel || group.label || group.code,
    };
  })).filter((item) => item.name);
}

function medicationNames(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
  return String(value || "").split(/[,;\n\r\t]+/).map((item) => item.trim().toLowerCase()).filter(Boolean);
}

function renderMedicationChips(container, hidden) {
  const entries = medicationEntries();
  container.innerHTML = "";
  medicationNames(hidden.value).forEach((name) => {
    const entry = entries.find((item) => item.name === name);
    const chip = document.createElement("span");
    chip.className = "medication-chip";
    chip.textContent = `${entry?.label || name} · ${entry?.classLabel || (state.locale === "en" ? "Unmapped" : "Chưa ánh xạ")}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "medication-remove";
    remove.dataset.removeMedication = name;
    remove.dataset.medicationInput = hidden.dataset.variableId;
    remove.setAttribute("aria-label", state.locale === "en" ? `Remove ${entry?.label || name}` : `Xóa ${entry?.label || name}`);
    remove.textContent = "×";
    remove.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      hidden.value = medicationNames(hidden.value).filter((item) => item !== name).join(", ");
      renderMedicationChips(container, hidden);
      rememberCurrentForm();
      schedulePathPreview();
    });
    chip.appendChild(remove);
    container.appendChild(chip);
  });
}

function renderMedicationField(variable, required) {
  const card = document.createElement("div");
  card.className = "input-card medication-card";
  const label = document.createElement("label");
  label.textContent = `${variableDisplayLabel(variable)}${required ? " *" : ""}`;
  card.appendChild(label);

  const hidden = document.createElement("input");
  hidden.type = "hidden";
  hidden.dataset.variableId = variable.id;
  hidden.className = "medication-value";
  hidden.value = medicationNames(state.context[variable.id]).join(", ");

  const picker = document.createElement("select");
  picker.className = "medication-picker";
  picker.add(new Option(state.locale === "en" ? "Add a medicine…" : "Thêm thuốc…", ""));
  picker.add(new Option(state.locale === "en" ? "No medication (NONE)" : "Không dùng thuốc (NONE)", "__NONE__"));
  medicationEntries().forEach((entry) => picker.add(new Option(`${entry.label} · ${entry.classLabel}`, entry.name)));
  const chips = document.createElement("div");
  chips.className = "medication-chips";
  picker.addEventListener("change", () => {
    const names = medicationNames(hidden.value);
    if (picker.value === "__NONE__") {
      hidden.value = "NONE";
    } else {
      if (picker.value && !names.includes(picker.value)) names.push(picker.value);
      hidden.value = names.filter((name) => name !== "none").join(", ");
    }
    picker.value = "";
    renderMedicationChips(chips, hidden);
    rememberCurrentForm();
    schedulePathPreview();
  });
  renderMedicationChips(chips, hidden);
  card.append(picker, hidden, chips);
  addVariableHelp(card, variable);
  if (state.missingInputIds.has(variable.id)) card.classList.add("missing");
  return card;
}

function renderVariableField(variable, required) {
  if (variable.id === "medication.currentDrugNames" || variable.id === "medication.previousEncounterDrugNames") {
    return renderMedicationField(variable, required);
  }
  const card = document.createElement("div");
  card.className = "input-card";
  const label = document.createElement("label");
  label.htmlFor = `var-${variable.id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
  label.textContent = `${variableDisplayLabel(variable)}${variable.unit ? ` (${localizeText(variable.unit)})` : ""}${required ? " *" : ""}`;
  card.appendChild(label);
  const input = inputElementFor(variable, variable.id);
  card.appendChild(input);
  addVariableHelp(card, variable);
  if (state.missingInputIds.has(variable.id)) card.classList.add("missing");
  return card;
}

function renderPairField(ids, variablesById, requiredIds) {
  const card = document.createElement("div");
  card.className = "input-card pair-card";
  const title = document.createElement("label");
  const first = variablesById[ids[0]];
  const prefix = first.id.replace(/\.(systolicMmHg|diastolicMmHg)$/, "");
  const pairTitles = state.locale === "en"
    ? { "bp.office.measurement1": "Clinic measurement 1", "bp.office.measurement2": "Clinic measurement 2", "bp.office.measurement3": "Clinic measurement 3" }
    : { "bp.office.measurement1": "HA phòng khám lần 1", "bp.office.measurement2": "HA phòng khám lần 2", "bp.office.measurement3": "HA phòng khám lần 3" };
  title.textContent = pairTitles[prefix] || (state.locale === "en" ? "Blood pressure" : "Huyết áp");
  card.appendChild(title);
  const row = document.createElement("div");
  row.className = "bp-pair-row";
  ids.forEach((id) => {
    const variable = variablesById[id];
    const group = document.createElement("div");
    group.className = "bp-pair-field";
    const caption = document.createElement("span");
    caption.textContent = state.locale === "en"
      ? (id.endsWith("systolicMmHg") ? "SBP" : "DBP")
      : (id.endsWith("systolicMmHg") ? "HATT" : "HATTr");
    const input = inputElementFor(variable, id);
    input.setAttribute("aria-label", `${variableDisplayLabel(variable)}${requiredIds.has(id) ? " *" : ""}`);
    group.append(caption, input);
    row.appendChild(group);
    if (state.missingInputIds.has(id)) card.classList.add("missing");
  });
  card.appendChild(row);
  addVariableHelp(card, first);
  return card;
}

function addVariableHelp(card, variable) {
  if (!variable.definition) return;
  const help = document.createElement("small");
  help.textContent = localizeText(variable.definition);
  card.appendChild(help);
}

function collectInputsFromForm() {
  const values = { ...state.context };
  document.querySelectorAll("[data-variable-id]").forEach((input) => {
    const value = input.type === "checkbox"
      ? (input.checked ? true : "")
      : input.dataset.booleanInput === "true"
        ? (input.value === "true" ? true : input.value === "false" ? false : "")
        : input.value;
    if (value !== "") values[input.dataset.variableId] = value;
    else delete values[input.dataset.variableId];
  });
  delete values["medication.regimenStableWeeks"];
  return values;
}

function normalizeFhirContext(parsed) {
  const resources = parsed?.resourceType === "Bundle"
    ? (parsed.entry || []).map((entry) => entry?.resource).filter(Boolean)
    : [parsed];
  if (!resources.some((resource) => resource?.resourceType)) return {};
  const context = {};
  const diagnoses = [];
  const medications = [];
  const regimenDates = [];
  const observations = new Map();
  resources.forEach((resource) => {
    if (resource.resourceType === "Patient") {
      if (resource.birthDate) context["patient.birthDate"] = resource.birthDate;
      if (resource.gender) context["patient.sex"] = ["male", "female", "other", "unknown"].includes(resource.gender) ? resource.gender : "unknown";
    }
    if (resource.resourceType === "Condition") {
      const codings = resource.code?.coding || [];
      codings.forEach((coding) => { if (coding.code) diagnoses.push(coding.code); });
    }
    if (resource.resourceType === "Observation") {
      const code = resource.code?.coding?.[0]?.code;
      const value = resource.valueQuantity?.value ?? resource.value?.value ?? resource.value;
      if (code && value != null) observations.set(code, value);
    }
    if (resource.resourceType === "MedicationRequest" || resource.resourceType === "MedicationStatement") {
      const medication = resource.medicationCodeableConcept?.coding?.[0]?.code
        || resource.medicationCodeableConcept?.text
        || resource.medicationReference?.display;
      if (medication) medications.push(medication);
      const dateValue = resource.resourceType === "MedicationRequest"
        ? resource.authoredOn
        : resource.effectiveDateTime || resource.effectivePeriod?.start;
      if (dateValue) regimenDates.push(String(dateValue).slice(0, 10));
    }
  });
  if (diagnoses.length) context["patient.conditionCodes"] = [...new Set(diagnoses)].join(",");
  if (medications.length) context["medication.currentDrugNames"] = [...new Set(medications)].join(", ");
  if (regimenDates.length) context["medication.regimenStartDate"] = regimenDates.sort()[0];
  const observationMap = {
    "8867-4": "vitals.heartRateBpm",
    "98979-8": "lab.eGfr",
    "13457-7": "lab.ldlCholesterol",
    "2571-8": "lab.triglycerides",
  };
  observations.forEach((value, code) => {
    if (observationMap[code] && Number.isFinite(Number(value))) context[observationMap[code]] = Number(value);
  });
  return context;
}

function normalizeJsonContext(parsed) {
  const fhirContext = normalizeFhirContext(parsed);
  const context = {};
  if (parsed.variables && typeof parsed.variables === "object" && !Array.isArray(parsed.variables)) Object.assign(context, parsed.variables);
  if (parsed.context && typeof parsed.context === "object" && !Array.isArray(parsed.context)) Object.assign(context, parsed.context);
  if (parsed.result?.context && typeof parsed.result.context === "object" && !Array.isArray(parsed.result.context)) Object.assign(context, parsed.result.context);
  if (!Object.keys(context).length && !Object.keys(fhirContext).length) Object.assign(context, parsed);
  delete context.result;
  delete context.variables;
  delete context.context;
  // This is a dependent field. A JSON record may provide its source date,
  // but must never override the value calculated by the runtime.
  delete context["medication.regimenStableWeeks"];
  return { ...fhirContext, ...context };
}

function collectInputsFromJson() {
  const raw = $("json-input").value.trim();
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("JSON đầu vào phải là object key-value.");
  return normalizeJsonContext(parsed);
}

function collectInputs() {
  return state.inputMode === "json" ? collectInputsFromJson() : collectInputsFromForm();
}

function syncJsonFromForm() {
  state.context = collectInputsFromForm();
  $("json-input").value = pretty(state.context);
}

function applyJsonToForm() {
  const values = collectInputsFromJson();
  // JSON is an explicit patient-record replacement. Merging here leaves
  // stale values from the previous patient when a field was removed.
  state.context = { ...values };
}

function rememberCurrentForm() {
  if (state.inputMode === "form" && $("input-form")?.children.length) state.context = collectInputsFromForm();
}

function markMissingInputs(ids) {
  state.missingInputIds = new Set(ids);
  document.querySelectorAll("[data-variable-id]").forEach((input) => {
    input.closest(".input-card")?.classList.toggle("missing", state.missingInputIds.has(input.dataset.variableId));
  });
}

function validateInputsBeforeRun(tree, variables) {
  const missing = requiredVariableIdsForRun(tree).filter((id) => !isProvided(variables[id]));
  markMissingInputs(missing);
  if (missing.length) {
    const labels = missing.map(variableLabel).join(", ");
    showStatus(`Chưa đủ dữ liệu. Vui lòng bổ sung: ${labels}`, "bad");
    setResultCard("Chưa đủ dữ liệu", [`Cần bổ sung: ${labels}`]);
    $("path-status").textContent = `Chưa thể chạy: còn thiếu ${missing.length} trường dữ liệu.`;
    $("path-status").className = "path-status pending";
    return false;
  }
  return true;
}

async function loadJsonFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("Tệp JSON phải là object.");
    state.context = normalizeJsonContext(parsed);
    $("json-input").value = pretty(state.context);
    if (state.inputMode !== "json") setInputMode("json", { preserveContext: true });
    else renderInputForm(currentTree());
    showStatus(`Đã nạp dữ liệu từ ${file.name}.`, "good");
    schedulePathPreview();
  } catch (error) {
    showStatus(`Không thể nạp JSON: ${error.message}`, "bad");
  } finally {
    event.target.value = "";
  }
}

function setInputMode(mode, options = {}) {
  if (mode === state.inputMode) return;
  if (mode === "json") {
    if (!options.preserveContext) syncJsonFromForm();
  } else {
    try {
      applyJsonToForm();
    } catch (error) {
      showStatus(`JSON chưa hợp lệ: ${error.message}`, "bad");
      return;
    }
  }

  state.inputMode = mode;
  $("mode-form").classList.toggle("active", mode === "form");
  $("mode-json").classList.toggle("active", mode === "json");
  $("form-panel").hidden = mode !== "form";
  $("json-panel").hidden = mode !== "json";
  const tree = currentTree();
  if (tree) renderInputForm(tree);
  showStatus("");
  schedulePathPreview();
}

function refreshTreeOptions() {
  const select = $("tree-select");
  select.innerHTML = "";
  state.bundle.trees.forEach((tree) => select.add(new Option(localizeText(tree.name || tree.id), tree.id)));
  select.value = state.treeId;
}

function setResultCard(title = UI_LABELS[state.locale].currentRun, lines = [UI_LABELS[state.locale].tree], treeId = state.treeId) {
  $("result-box").innerHTML = `
    <div class="result-title"><span class="eye-icon" aria-hidden="true"></span>${title}</div>
    ${lines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}
    <div class="result-tree-row">${escapeHtml(UI_LABELS[state.locale].tree)} <button id="current-run-tree" type="button" data-tree-id="${escapeHtml(treeId || "")}">${escapeHtml(treeLabel(treeId || state.treeId))}</button></div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function firstVisibleNode(tree) {
  return tree.nodes.find((node) => node.type !== "end") || tree.nodes[0];
}

function nodeTypeLabel(node) {
  if (!node) return "—";
  const labels = state.locale === "vi"
    ? { start: "Bắt đầu", condition: "Điều kiện", branch: "Nhánh bệnh nền", inference: "Khuyến nghị", link: "Liên kết", end: "Kết thúc" }
    : { start: "Start", condition: "Condition", branch: "Clinical branch", inference: "Recommendation", link: "Link", end: "Outcome" };
  if (labels[node.type]) return labels[node.type];
  return node.type;
}

function renderExplorerPanel(tree) {
  const selected = tree.nodes.find((node) => node.id === state.explorerSelectedNodeId) || firstVisibleNode(tree);
  state.explorerSelectedNodeId = selected?.id || null;
  const outgoing = tree.edges.filter((edge) => edge.from === selected?.id);
  const query = state.explorerSearch.trim().toLowerCase();
  const matching = query
    ? tree.nodes.filter((node) => `${node.display?.title || ""} ${node.display?.detail || ""}`.toLowerCase().includes(query))
    : [];
  const options = query
    ? matching.map((node) => `<button type="button" data-explorer-node-id="${escapeHtml(node.id)}">${escapeHtml(localizeText(node.display?.title || node.id))}</button>`).join("")
    : outgoing.map((edge) => `<button type="button" data-explorer-node-id="${escapeHtml(edge.to)}">${escapeHtml(localizeText(edge.label || edge.when || "Default"))}</button>`).join("");
  const emptyOptions = state.locale === "en"
    ? (query ? "No nodes found" : "No next branch")
    : (query ? "Không tìm thấy node" : "Không có nhánh tiếp theo");
  $("explorer-options").innerHTML = options || `<button type="button" disabled>${emptyOptions}</button>`;
  $("explorer-selected-node").innerHTML = `${escapeHtml(localizeText(selected?.display?.title || "—"))}<small>${escapeHtml(nodeTypeLabel(selected))}</small>`;
  $("explorer-description").textContent = localizeText(selected?.display?.detail || selected?.description || "—");
  const metadataLabel = state.locale === "en" ? "Description" : "Mô tả";
  $("explorer-metadata").textContent = `${metadataLabel}: ${localizeText(tree.purpose || tree.metadata?.description || "—")}`;
  $("explorer-terminal-card").hidden = selected?.type !== "inference" && selected?.type !== "end";
}

function builderDraftTree() {
  const tree = currentTree();
  if (!tree) return null;
  if (!state.builderDrafts[tree.id]) state.builderDrafts[tree.id] = cloneJson(tree);
  return state.builderDrafts[tree.id];
}

function updateBuilderTree(mutator, message = "Đã cập nhật bản nháp cây.") {
  const draft = builderDraftTree();
  if (!draft) return;
  mutator(draft);
  state.builderDrafts[draft.id] = draft;
  renderTree();
  showStatus(message, "good");
}

function createNewTree() {
  const baseId = "new_decision_tree";
  let id = baseId;
  let suffix = 2;
  while (state.bundle.trees.some((tree) => tree.id === id)) id = `${baseId}_${suffix++}`;
  const tree = {
    id,
    name: "Cây quyết định mới",
    purpose: "Bản nháp cây quyết định mới.",
    clinicalStatus: "draft",
    entryNodeId: "new_start",
    inputVariables: [],
    outputVariables: [],
    nodes: [{
      id: "new_start",
      type: "start",
      display: { title: "Bắt đầu cây quyết định mới", detail: "" },
    }],
    edges: [],
    notes: ["Bản nháp chỉ được lưu khi export JSON và chưa được đưa vào runtime."] ,
    localOnly: true,
  };
  state.bundle.trees.push(tree);
  state.builderDrafts[id] = cloneJson(tree);
  state.treeId = id;
  state.builderSelectedNodeId = "new_start";
  renderTree();
  showStatus("Đã tạo bản nháp cây mới.", "good");
}

function exportTreeJson() {
  const tree = currentTree();
  if (!tree) return;
  const blob = new Blob([JSON.stringify(tree, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${tree.id}.json`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  showStatus(`Đã xuất bản nháp ${tree.id}.json.`, "good");
}

async function importTreeFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    const imported = Array.isArray(parsed.trees) ? parsed.trees : [parsed.tree || parsed];
    const validTrees = imported.filter((tree) => tree && typeof tree === "object" && tree.id && Array.isArray(tree.nodes) && Array.isArray(tree.edges));
    if (!validTrees.length) throw new Error("JSON phải là một cây hoặc bundle có trường trees.");
    let firstId = null;
    validTrees.forEach((rawTree) => {
      const tree = cloneJson(rawTree);
      const originalId = tree.id;
      let id = originalId;
      let suffix = 2;
      while (state.bundle.trees.some((item) => item.id === id)) id = `${originalId}_imported_${suffix++}`;
      tree.id = id;
      tree.localOnly = true;
      state.bundle.trees.push(tree);
      state.builderDrafts[id] = cloneJson(tree);
      if (!firstId) firstId = id;
    });
    state.treeId = firstId;
    state.builderSelectedNodeId = currentTree()?.entryNodeId || currentTree()?.nodes?.[0]?.id || null;
    renderTree();
    showStatus(`Đã nhập ${validTrees.length} cây vào bản nháp.`, "good");
  } catch (error) {
    showStatus(`Không thể nhập cây: ${error.message}`, "bad");
  } finally {
    event.target.value = "";
  }
}

function updateSelectedBuilderNode() {
  const nodeId = state.builderSelectedNodeId;
  if (!nodeId) return;
  updateBuilderTree((tree) => {
    const node = tree.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    node.display = node.display || {};
    node.display.title = $("builder-node-label").value;
    node.display.detail = $("builder-node-detail").value;
    node.type = $("builder-node-type").value;
  });
}

function renderBuilderPanels(tree) {
  const query = state.builderSearch.trim().toLowerCase();
  const visibleTrees = state.bundle.trees
    .map((item) => state.builderDrafts[item.id] || item)
    .filter((item) => !query || `${item.name || ""} ${item.purpose || ""}`.toLowerCase().includes(query));
  $("builder-tree-list").innerHTML = visibleTrees.map((item, index) => `
    <button type="button" class="${item.id === state.treeId ? "active" : ""}" data-builder-tree-id="${escapeHtml(item.id)}">
      ${escapeHtml(localizeText(item.name || `Tree ${index + 1}`))}
      <small>${escapeHtml(localizeText(item.purpose || "Decision tree"))}</small>
    </button>
  `).join("");
  document.querySelectorAll("[data-builder-tree-id]").forEach((button) => {
    button.addEventListener("click", () => selectTree(button.dataset.builderTreeId));
  });
  const selected = tree.nodes.find((node) => node.id === state.builderSelectedNodeId) || firstVisibleNode(tree);
  state.builderSelectedNodeId = selected?.id || null;
  $("builder-selected-node").textContent = nodeTypeLabel(selected);
  $("builder-backend-id").value = tree.id || "";
  $("builder-tree-name").value = localizeText(tree.name || tree.id || "");
  $("builder-tree-status").value = tree.clinicalStatus || "draft";
  $("builder-node-label").value = selected?.display?.title || "";
  $("builder-node-type").value = selected?.type || "start";
  $("builder-node-detail").value = selected?.display?.detail || "";
}

function updateViewPanels(tree) {
  const isTester = state.currentView === "tester";
  const isExplorer = state.currentView === "explorer";
  const isBuilder = state.currentView === "builder";
  document.querySelector(".tester-sidebar").hidden = !isTester;
  document.querySelector(".explorer-sidebar").hidden = !isExplorer;
  document.querySelector(".builder-library").hidden = !isBuilder;
  document.querySelector(".builder-properties").hidden = !isBuilder;
  document.querySelector(".legend-card").hidden = false;
  document.querySelector(".builder-mode-switch").hidden = !isBuilder;
  $("node-count-label").textContent = `${tree.nodes.length} nodes`;
  document.querySelector(".visual-card h2").textContent = isExplorer
    ? VIEW_LABELS[state.locale].explorer
    : isBuilder
      ? VIEW_LABELS[state.locale].builder
      : UI_LABELS[state.locale].live;
  renderExplorerPanel(tree);
  renderBuilderPanels(tree);
}

function renderTree() {
  const tree = currentTree();
  if (!tree) return;

  rememberCurrentForm();
  state.previewSequence += 1;
  clearTimeout(state.previewTimer);
  refreshTreeOptions();
  $("tree-purpose").textContent = localizeText(tree.purpose || "");
  $("graph-title").textContent = localizeText(tree.name || "Sơ đồ quyết định");
  renderGraph(tree);
  renderInputForm(tree);
  updateViewPanels(tree);
  if (state.lastRunResult) {
    const result = state.lastRunResult;
    const headline = result.status === "completed"
      ? resultDisplayLabel(result)
      : result.status === "needs_data" ? "Chưa đủ dữ liệu" : `Không thể hoàn tất (${result.status || "unknown"})`;
    setResultCard(UI_LABELS[state.locale].currentRun, [headline], result?.terminalTreeId || state.treeId);
    highlightPath(result);
  } else {
    setResultCard(UI_LABELS[state.locale].currentRun, [], tree.id);
    clearPathHighlight();
  }
  showStatus("");
}

function selectTree(treeId, message = "") {
  if (!state.bundle.trees.some((item) => item.id === treeId)) return false;
  state.treeId = treeId;
  renderTree();
  if (message) showStatus(message, "good");
  return true;
}

function renderResult(result) {
  state.previewSequence += 1;
  clearTimeout(state.previewTimer);
  if (result?.context && typeof result.context === "object") {
    state.context = { ...state.context, ...result.context };
    if (state.inputMode === "json") $("json-input").value = pretty(state.context);
  }
  refreshLatestBpDisplay(state.context);
  refreshRegimenStableDisplay(state.context);
  markMissingInputs(result?.missingData || []);
  state.lastRunResult = result || null;
  const headline = result.status === "completed"
    ? resultDisplayLabel(result)
    : result.status === "needs_data"
      ? "Chưa đủ dữ liệu"
      : `Không thể hoàn tất (${result.status || "unknown"})`;
  const lines = [headline];
  if (result.missingData?.length) lines.push(`Cần bổ sung: ${result.missingData.map(variableLabel).join(", ")}`);
  setResultCard(UI_LABELS[state.locale].currentRun, lines, result?.terminalTreeId || state.treeId);
  highlightPath(result);
}

function populatePresets() {
  const select = $("preset-select");
  if (!select) return;
  select.innerHTML = `<option value="">${state.locale === "en" ? "— Select a preset —" : "— Chọn bệnh nhân mẫu —"}</option>`;
  Object.entries(PATIENT_PRESETS).forEach(([id, preset]) => select.add(new Option(preset.label, id)));
}

function applyPatientValues(values, message = "") {
  // A loaded preset/record is a new patient snapshot. Do not retain fields
  // that happened to be present for the previously loaded patient.
  state.context = { ...values };
  state.lastRunResult = null;
  renderInputForm(currentTree());
  if (state.inputMode === "json") $("json-input").value = pretty(state.context);
  markMissingInputs([]);
  schedulePathPreview();
  if (message) showStatus(message, "good");
}

function usePreset(id) {
  if (!id || !PATIENT_PRESETS[id]) return;
  applyPatientValues(PATIENT_PRESETS[id].values, state.locale === "en" ? "Preset patient loaded." : `Đã nạp ${PATIENT_PRESETS[id].label}.`);
}

function openLocalPatientRecord() {
  const raw = $("patient-record-id").value.trim();
  if (!raw) {
    showStatus(state.locale === "en" ? "Enter a preset id or patient JSON." : "Nhập mã preset hoặc JSON hồ sơ bệnh nhân.", "bad");
    return;
  }
  const presetId = raw.replaceAll("-", "_");
  if (PATIENT_PRESETS[presetId]) {
    $("preset-select").value = presetId;
    usePreset(presetId);
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    const values = normalizeJsonContext(parsed);
    if (!Object.keys(values).length) throw new Error(state.locale === "en" ? "No patient data found." : "Không tìm thấy dữ liệu bệnh nhân.");
    applyPatientValues(values, state.locale === "en" ? "Local patient record loaded." : "Đã nạp hồ sơ bệnh nhân cục bộ.");
  } catch (error) {
    showStatus(`${state.locale === "en" ? "Unable to open record" : "Không thể mở hồ sơ"}: ${error.message}`, "bad");
  }
}

function setPatientTab(tab) {
  if (!FORM_GROUPS || !["specs", "history"].includes(tab)) return;
  rememberCurrentForm();
  state.patientTab = tab;
  document.querySelectorAll("[data-patient-tab]").forEach((button) => {
    const active = button.dataset.patientTab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  renderInputForm(currentTree());
}

function resetPatientData() {
  state.context = {};
  state.lastRunResult = null;
  state.missingInputIds = new Set();
  $("preset-select").value = "";
  $("patient-record-id").value = "";
  if (state.inputMode === "json") $("json-input").value = "{}";
  renderInputForm(currentTree());
  clearPathHighlight();
  setResultCard(state.locale === "en" ? "Current run" : "Lần chạy hiện tại", [], currentTree()?.id);
  showStatus(state.locale === "en" ? "Patient data cleared." : "Đã xóa dữ liệu người bệnh.", "good");
}

async function runTree() {
  $("run-tree").disabled = true;
  state.previewSequence += 1;
  clearTimeout(state.previewTimer);
  try {
    if (state.builderDrafts[state.treeId] || currentTree()?.localOnly) {
      showStatus("Cây bản nháp chỉ có thể chỉnh sửa và xuất JSON; cần nạp lại bundle sau khi clinical review để chạy.", "bad");
      return;
    }
    const variables = collectInputs();
    if (!validateInputsBeforeRun(currentTree(), variables)) return;
    const endpoint = "/api/run";
    const payload = { treeId: state.treeId, variables, strict: true };
    const response = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    renderResult(response.result);
    const completed = response.result?.status === "completed";
    showStatus(completed ? "Đã chạy cây quyết định." : "Chưa thể hoàn tất vì còn thiếu dữ liệu.", completed ? "good" : "bad");
  } catch (error) {
    $("result-box").textContent = error.message;
    showStatus(error.message, "bad");
  } finally {
    $("run-tree").disabled = false;
  }
}

async function runClinicalFlowFromForm() {
  const button = $("start-traversal");
  button.disabled = true;
  state.previewSequence += 1;
  clearTimeout(state.previewTimer);
  try {
    const variables = collectInputs();
    if (!Object.keys(variables).length) {
      showStatus(state.locale === "en" ? "Enter patient data before starting traversal." : "Vui lòng nhập dữ liệu người bệnh trước khi chạy.", "bad");
      return;
    }
    const response = await api("/api/run-flow", { method: "POST", body: JSON.stringify({ startTreeId: "bp_diagnosis", variables, strict: false }) });
    renderResult(response.result);
    showStatus(response.result.status === "completed"
      ? (state.locale === "en" ? "Clinical flow completed." : "Đã hoàn tất clinical flow.")
      : (state.locale === "en" ? "Traversal paused: more data is needed." : "Clinical flow tạm dừng vì cần thêm dữ liệu."), response.result.status === "completed" ? "good" : "");
  } catch (error) {
    showStatus(error.message, "bad");
  } finally {
    button.disabled = false;
  }
}

function schedulePathPreview() {
  clearTimeout(state.previewTimer);
  // Keep the full clinical-flow trace when the user is just moving between
  // linked trees. A new preview is only needed after the patient inputs
  // change.
  if (state.lastRunResult?.trace?.some((event) => event.treeId === state.treeId)) {
    highlightPath(state.lastRunResult);
    return;
  }
  const sequence = ++state.previewSequence;
  let variables;

  try {
    variables = collectInputs();
    refreshLatestBpDisplay(variables);
  } catch (error) {
    $("path-status").textContent = `JSON chưa hợp lệ: ${error.message}`;
    $("path-status").className = "path-status pending";
    return;
  }

  if (!Object.keys(variables).length) {
    clearPathHighlight();
    return;
  }

  state.previewTimer = setTimeout(async () => {
    try {
      const endpoint = "/api/run";
      const payload = { treeId: state.treeId, variables, strict: false };
      const response = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
      if (sequence === state.previewSequence) highlightPath(response.result);
    } catch (error) {
      if (sequence === state.previewSequence) $("path-status").textContent = `Không thể xem đường đi: ${error.message}`;
    }
  }, 180);
}

function updateZoomLabel() {
  if (graphInstance) $("zoom-label").textContent = `${Math.round(graphInstance.zoom() * 100)}%`;
}

function zoomGraph(multiplier) {
  if (!graphInstance) return;
  const nextZoom = Math.max(graphInstance.minZoom(), Math.min(graphInstance.maxZoom(), graphInstance.zoom() * multiplier));
  graphInstance.zoom({
    level: nextZoom,
    renderedPosition: { x: graphInstance.width() / 2, y: graphInstance.height() / 2 },
  });
  updateZoomLabel();
}

function setAppView(view) {
  state.currentView = view;
  document.body.dataset.view = view;
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewTarget === view);
  });
  $("sidebar-title").textContent = VIEW_LABELS[state.locale][view];
  $("footer-view").textContent = VIEW_LABELS[state.locale][view];
  const tree = currentTree();
  if (tree) updateViewPanels(tree);
  applyLocale();
  if (graphInstance) window.setTimeout(() => graphInstance.fit(undefined, 36), 30);
}

async function init() {
  try {
    const [bundle, medicationCatalog] = await Promise.all([api("/api/bundle"), api("/api/medication-catalog")]);
    state.bundle = bundle;
    state.medicationCatalog = medicationCatalog;
    state.treeId = state.bundle.trees[0].id;
    populatePresets();
    renderTree();
    applyLocale();
  } catch (error) {
    showStatus(error.message, "bad");
  }
}

$("tree-select").addEventListener("change", (event) => selectTree(event.target.value));
$("run-tree").addEventListener("click", runTree);
$("start-traversal").addEventListener("click", runClinicalFlowFromForm);
$("reset-inputs").addEventListener("click", resetPatientData);
$("preset-select").addEventListener("change", (event) => usePreset(event.target.value));
$("open-patient-record").addEventListener("click", openLocalPatientRecord);
$("patient-record-id").addEventListener("keydown", (event) => { if (event.key === "Enter") openLocalPatientRecord(); });
document.addEventListener("click", (event) => {
  const tab = event.target.closest?.("[data-patient-tab]");
  if (tab) setPatientTab(tab.dataset.patientTab);
  const remove = event.target.closest?.("[data-remove-medication]");
  if (remove) {
    const input = [...document.querySelectorAll("[data-variable-id]")].find((candidate) => candidate.dataset.variableId === remove.dataset.medicationInput);
    if (!input) return;
    input.value = medicationNames(input.value).filter((name) => name !== remove.dataset.removeMedication).join(", ");
    const container = input.closest(".medication-card")?.querySelector(".medication-chips");
    if (container) renderMedicationChips(container, input);
    rememberCurrentForm();
    schedulePathPreview();
  }
  const resultTree = event.target.closest?.("#current-run-tree[data-tree-id]");
  if (resultTree) selectTree(resultTree.dataset.treeId, state.locale === "en" ? "Opened linked tree." : "Đã mở cây liên quan.");
});
$("input-form").addEventListener("input", () => { state.lastRunResult = null; schedulePathPreview(); });
$("input-form").addEventListener("change", () => { state.lastRunResult = null; rememberCurrentForm(); markMissingInputs([]); schedulePathPreview(); });
$("input-form").addEventListener("input", () => { rememberCurrentForm(); markMissingInputs([]); });
$("json-input").addEventListener("input", () => { state.lastRunResult = null; schedulePathPreview(); });
$("json-file").addEventListener("change", loadJsonFile);
$("language-toggle").addEventListener("click", () => {
  state.locale = state.locale === "vi" ? "en" : "vi";
  const tree = currentTree();
  if (tree) {
    refreshTreeOptions();
    renderGraph(tree);
    renderInputForm(tree);
    updateViewPanels(tree);
  }
  populatePresets();
  applyLocale();
});
$("explorer-search").addEventListener("input", (event) => {
  state.explorerSearch = event.target.value;
  renderExplorerPanel(currentTree());
});
$("explorer-options").addEventListener("click", (event) => {
  const button = event.target.closest("[data-explorer-node-id]");
  if (!button) return;
  state.explorerSelectedNodeId = button.dataset.explorerNodeId;
  renderExplorerPanel(currentTree());
  const node = graphInstance?.getElementById(state.explorerSelectedNodeId);
  if (node?.length) graphInstance.center(node);
});
$("builder-search").addEventListener("input", (event) => {
  state.builderSearch = event.target.value;
  renderBuilderPanels(currentTree());
});
$("new-tree-button").addEventListener("click", createNewTree);
$("import-tree-button").addEventListener("click", () => $("import-tree-file").click());
$("import-tree-file").addEventListener("change", importTreeFile);
$("export-tree-button").addEventListener("click", exportTreeJson);
$("publish-tree-button").addEventListener("click", exportTreeJson);
$("builder-tree-name").addEventListener("change", () => updateBuilderTree((tree) => { tree.name = $("builder-tree-name").value.trim() || tree.id; }));
$("builder-tree-status").addEventListener("change", () => updateBuilderTree((tree) => { tree.clinicalStatus = $("builder-tree-status").value; }));
$("builder-node-label").addEventListener("change", updateSelectedBuilderNode);
$("builder-node-type").addEventListener("change", updateSelectedBuilderNode);
$("builder-node-detail").addEventListener("change", updateSelectedBuilderNode);
$("mode-form").addEventListener("click", () => setInputMode("form"));
$("mode-json").addEventListener("click", () => setInputMode("json"));
$("zoom-out").addEventListener("click", () => zoomGraph(1 / 1.2));
$("zoom-in").addEventListener("click", () => zoomGraph(1.2));
const layoutResizer = $("layout-resizer");
let resizingLayout = false;
layoutResizer.addEventListener("pointerdown", (event) => {
  if (window.matchMedia("(max-width: 980px)").matches) return;
  resizingLayout = true;
  layoutResizer.setPointerCapture?.(event.pointerId);
  document.body.classList.add("is-resizing");
  event.preventDefault();
});
layoutResizer.addEventListener("pointermove", (event) => {
  if (!resizingLayout) return;
  const main = document.querySelector("main");
  const bounds = main.getBoundingClientRect();
  const maximum = Math.min(760, bounds.width - (state.currentView === "builder" ? 420 : 360));
  const width = Math.max(300, Math.min(maximum, event.clientX - bounds.left));
  main.style.setProperty("--sidebar-width", `${Math.round(width)}px`);
  graphInstance?.resize();
});
const stopLayoutResize = () => {
  if (!resizingLayout) return;
  resizingLayout = false;
  document.body.classList.remove("is-resizing");
};
layoutResizer.addEventListener("pointerup", stopLayoutResize);
layoutResizer.addEventListener("pointercancel", stopLayoutResize);
document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => setAppView(button.dataset.viewTarget));
});

init();

// Seasonal calendar data (D15).
// Month x Tunisian-zone presence levels, mirroring
// apps/api/src/spotdata/domain/species.py and docs/SOURCES-AUDIT.md §3.
// KEEP IN SYNC with species.py. Levels: 3 strong, 2 medium, 1 weak, 0 unavailable.
// Grounded in published scientific studies for Tunisia and the Mediterranean
// (cited per species). NOT a Tunisian catch log.

export type PresenceLevel = 0 | 1 | 2 | 3;

export interface CalendarZone {
  key: string;
  labelAr: string;
  governorates: string[];
}

export interface CalendarSpecies {
  key: string;
  labelAr: string;
  scientific: string;
  noteAr: string;
  // zone key -> 12 monthly levels (index 0 = January)
  matrix: Record<string, string>;
  // Scientific sources backing the matrix (label + full citation).
  sources: string[];
  // Published sea-state preference (Mediterranean pattern, disclosed).
  seaState: { labelAr: string; basisAr: string };
}

export const CALENDAR_ZONES: CalendarZone[] = [
  { key: "northwest", labelAr: "الشمال الغربي", governorates: ["جندوبة"] },
  { key: "bizerte_tunis", labelAr: "بنزرت وخليج تونس", governorates: ["بنزرت", "تونس"] },
  { key: "cap_bon_hammamet", labelAr: "الوطن القبلي وخليج الحمامات", governorates: ["نابل"] },
  { key: "sahel", labelAr: "الساحل", governorates: ["سوسة", "المنستير", "المهدية"] },
  { key: "gabes", labelAr: "خليج قابس", governorates: ["صفاقس", "قابس"] },
  { key: "south", labelAr: "جربة وجرجيس والجنوب", governorates: ["مدنين"] },
];

export const CALENDAR_MONTHS = [
  "جانفي",
  "فيفري",
  "مارس",
  "أفريل",
  "ماي",
  "جوان",
  "جويلية",
  "أوت",
  "سبتمبر",
  "أكتوبر",
  "نوفمبر",
  "ديسمبر",
];

export const CALENDAR_SPECIES: CalendarSpecies[] = [
  {
    key: "european_seabass",
    labelAr: "القاروص",
    scientific: "Dicentrarchus labrax",
    noteAr: "مبيّض شتوي في المتوسط (ديسمبر–مارس، أبكر جنوباً)؛ حضور ساحلي أقوى شتاءً وربيعاً وخريفاً، وأضعف صيفاً.",
    matrix: {
      northwest: "333221112333",
      bizerte_tunis: "333221112333",
      cap_bon_hammamet: "333221112333",
      sahel: "222221112233",
      gabes: "333210001233",
      south: "332210001233",
    },
    sources: [
      "Bauchot M.-L. (1987) عبر FishBase — Dicentrarchus labrax: التبييض مرة سنوياً ويميل للشتاء في المتوسط (ديسمبر–مارس)، أبكر في الجنوب الدافئ — https://www.fishbase.se/summary/Dicentrarchus-labrax.html",
      "Cervera et al. (2024) Fishes 9(5):173 — موسم تبييض القاروص نوفمبر–مارس، والحضور الساحلي يزداد شتاءً وربيعاً وخريفاً ويقل صيفاً — https://www.mdpi.com/2410-3888/9/5/173",
      "FAO/MEDRAP — بحيرات بنزرت وغار الملح وخليج تونس حضانات لصغار القاروص — https://www.fao.org/4/af025e/AF025E04.htm",
    ],
    seaState: {
      labelAr: "بحر متكسر مع رغوة (منطقة الكسرة)",
      basisAr: "نوع منطقة الكسرة: يتغذى ويحتمي فيها صغاره ويُصطاد قرب الموج المتكسر والرغوة (Cervera et al. 2024؛ FishBase). نمط متوسطي عام غير مدقق بدراسة تونسية محددة.",
    },
  },
  {
    key: "gilthead_seabream",
    labelAr: "الوراطة",
    scientific: "Sparus aurata",
    noteAr: "مبيّض خريف–شتاء (أكتوبر–فبراير، ذروة ديسمبر–يناير في خليج قابس)؛ قوة خريفية–شتوية، وربيع متوسط، وصيف ضعيف.",
    matrix: {
      northwest: "322221112333",
      bizerte_tunis: "322221112333",
      cap_bon_hammamet: "322221112333",
      sahel: "222221112233",
      gabes: "322221112333",
      south: "222221112333",
    },
    sources: [
      "Hadj-Taieb A., Ghorbel M., Hadj-Hamida N.B., Jarboui O. (2013) Ciencias Marinas 39(1):101–112 — الوراطة في خليج قابس (تونس): موسم التكاثر أكتوبر–فبراير وذروة التبييض ديسمبر–يناير — https://www.scielo.org.mx/scielo.php?pid=S0185-38802013000100008&script=sci_abstract&tlng=en",
      "Chaoui L., Kara M.H., Faure E., Quignard J.P. (2006) Scientia Marina 70(3):545–552 — تبييض الوراطة نوفمبر–فبراير في المتوسط، والخروج من البحيرات خريفاً للتكاثر — https://scientiamarina.revistas.csic.es/index.php/scientiamarina/article/view/100",
    ],
    seaState: {
      labelAr: "كسرة معتدلة على رمل/أعشاب",
      basisAr: "قاعية في القيعان الرملية وأعشاب البحر ومنطقة الكسرة حتى ~30م (FishBase؛ JMSE 2023) — نمط كسرة معتدلة لا ماء هائج دائم.",
    },
  },
  {
    key: "white_seabream",
    labelAr: "السار",
    scientific: "Diplodus sargus",
    noteAr: "مبيّض ربيعي في خليج تونس (مارس–مايو، ذروة مارس–أبريل) وراحة صيفية (يوليو–أكتوبر)؛ يفضّل الصخر.",
    matrix: {
      northwest: "223332111122",
      bizerte_tunis: "223332111122",
      cap_bon_hammamet: "223332111122",
      sahel: "233332111112",
      gabes: "233332111112",
      south: "233332111112",
    },
    sources: [
      "Mouine N. et al. (2007) Scientia Marina 71(3) — السار في خليج تونس: نشاط جنسي يناير–مايو، تبييض مارس–مايو بذروة مارس–أبريل عند 15–18°م، وراحة الغدد يوليو–أكتوبر — https://scientiamarina.revistas.csic.es/index.php/scientiamarina/article/view/51",
    ],
    seaState: {
      labelAr: "موج يتكسر على الصخور (منطقة الاندفاع)",
      basisAr: "يرتاد منطقة الكسرة فجراً ويتغذى على اللافقاريات التي يفصلها ضرب الموج عن الصخور (FishBase Ref. 13780؛ PLOS ONE 2016).",
    },
  },
  {
    key: "striped_seabream",
    labelAr: "المرمار",
    scientific: "Lithognathus mormyrus",
    noteAr: "في خليج قابس مبيّض خريفي (سبتمبر–نوفمبر)، وفي الشمال النمط المتوسطي صيفي (مايو–سبتمبر)؛ رمل السيرف.",
    matrix: {
      northwest: "001223332100",
      bizerte_tunis: "001233332100",
      cap_bon_hammamet: "001233332100",
      sahel: "111233332211",
      gabes: "112222123331",
      south: "111222112221",
    },
    sources: [
      "دراسة خليج قابس (2016) Cybium — المرمار في خليج قابس (جنوب شرق تونس): موسم التبييض سبتمبر–نوفمبر (نضج من أغسطس) — https://www.researchgate.net/publication/343651539",
      "Kallianiotis et al. (2005) — النمط المتوسطي العام للمرمار: مبيّض ربيعي–صيفي (مايو–سبتمبر)؛ يُعتمد لشمال تونس حتى التحقق محلياً.",
    ],
    seaState: {
      labelAr: "ماء هادئ على رمل ضحل (منطقة الغسل)",
      basisAr: "قاعي رملي ضحل (عادة 10–20م) والصغار في منطقة الغسل خلف الكسرة (WoRMS/FishBase؛ Monaco Nature Encyclopedia؛ Buxton et al. 1984). تفضيل الهدوء استنتاج عام — نمط متوسطي عام غير مدقق بدراسة تونسية محددة.",
    },
  },
];

export const PRESENCE_META: Record<PresenceLevel, { labelAr: string; className: string }> = {
  3: { labelAr: "قوي", className: "cal-strong" },
  2: { labelAr: "متوسط", className: "cal-medium" },
  1: { labelAr: "ضعيف", className: "cal-weak" },
  0: { labelAr: "غير متوفر", className: "cal-none" },
};

export function presenceLevel(matrix: string, monthIndex: number): PresenceLevel {
  const ch = matrix[monthIndex] ?? "1";
  const value = Number(ch);
  return (value === 3 || value === 2 || value === 1 ? value : 0) as PresenceLevel;
}

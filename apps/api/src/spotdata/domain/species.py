from dataclasses import dataclass

from .enums import ShoreType, TargetSpecies

# Tunisian coastal zones (audited in docs/SOURCES-AUDIT.md §1).
ZONE_KEYS = (
    "northwest",
    "bizerte_tunis",
    "cap_bon_hammamet",
    "sahel",
    "gabes",
    "south",
)

ZONE_LABELS_AR = {
    "northwest": "الشمال الغربي",
    "bizerte_tunis": "بنزرت وخليج تونس",
    "cap_bon_hammamet": "الوطن القبلي وخليج الحمامات",
    "sahel": "الساحل",
    "gabes": "خليج قابس",
    "south": "جربة وجرجيس والجنوب",
}

# 3 = strong, 2 = medium, 1 = weak, 0 = unavailable (see SOURCES-AUDIT §3).
PRESENCE_LABELS_AR = {3: "قوي", 2: "متوسط", 1: "ضعيف", 0: "غير متوفر"}

MONTHS_AR = (
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
)

# --------------------------------------------------------------------------- #
# Scientific sources that ground the seasonal matrices (SOURCES-AUDIT §3).
# Each entry is a published study / authoritative reference; the month x zone
# matrices below are derived from the reproduction/aggregation seasons these
# sources document. They are NOT a Tunisian catch log (D10/D11).
# --------------------------------------------------------------------------- #
SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "sargus_gulf_tunis": {
        "label_ar": "Mouine et al. (2007) — Scientia Marina",
        "citation": "Mouine N. et al., «The reproductive biology of Diplodus sargus sargus in the Gulf of Tunis (central Mediterranean)», Scientia Marina 71(3), 2007.",
        "claim_ar": "النشاط الجنسي للسار في خليج تونس من يناير إلى مايو، والتبييض مارس-مايو بذروة مارس-أبريل عند 15-18°م، وراحة الغدد يوليو-أكتوبر.",
        "url": "https://scientiamarina.revistas.csic.es/index.php/scientiamarina/article/view/51",
    },
    "aurata_gulf_gabes": {
        "label_ar": "Hadj-Taieb et al. (2013) — Ciencias Marinas",
        "citation": "Hadj-Taieb A., Ghorbel M., Hadj-Hamida N.B., Jarboui O., «Sex ratio, reproduction, and growth of the gilthead sea bream, Sparus aurata, in the Gulf of Gabes, Tunisia», Ciencias Marinas 39(1):101-112, 2013. DOI 10.7773/cm.v39i1.2146",
        "claim_ar": "موسم تكاثر الوراطة في خليج قابس من أكتوبر إلى فبراير وذروة التبييض ديسمبر-يناير (عيّنة 1065 فرداً، مارس 2008-فبراير 2010).",
        "url": "https://www.scielo.org.mx/scielo.php?pid=S0185-38802013000100008&script=sci_abstract&tlng=en",
    },
    "aurata_med_lagoon": {
        "label_ar": "Chaoui et al. (2006) — Scientia Marina",
        "citation": "Chaoui L., Kara M.H., Faure E., Quignard J.P., «Growth and reproduction of the gilthead seabream Sparus aurata in Mellah lagoon (north-eastern Algeria)», Scientia Marina 70(3):545-552, 2006.",
        "claim_ar": "تبييض الوراطة في المتوسط نوفمبر-فبراير؛ النوع يقضي الربيع-الصيف في البحيرات ويخرج للبحر خريفاً للتكاثر.",
        "url": "https://scientiamarina.revistas.csic.es/index.php/scientiamarina/article/view/100",
    },
    "mormyrus_gulf_gabes": {
        "label_ar": "دراسة خليج قابس (2016) — Lithognathus mormyrus",
        "citation": "«Age, growth and reproduction of the striped sea bream Lithognathus mormyrus (Linnaeus, 1758) in the gulf of Gabes (Southeastern Tunisia, Central Mediterranean)», Cybium 2016.",
        "claim_ar": "موسم تبييض المرمار في خليج قابس من سبتمبر إلى نوفمبر (ما قبل التبييض أبريل-مايو والنضج في أغسطس) — نمط خريفي جهوي موثق.",
        "url": "https://www.researchgate.net/publication/343651539",
    },
    "mormyrus_med_summer": {
        "label_ar": "النمط المتوسطي العام — المرمار",
        "citation": "Kallianiotis et al. (2005) ومراجع المتوسط: التبييض الربيعي-الصيفي (مايو-سبتمبر) في شمال ووسط المتوسط، بخلاف النمط الخريفي الموثق في خليج قابس.",
        "claim_ar": "في شمال/وسط المتوسط يكون مبيّض المرمار صيفياً (مايو-سبتمبر)؛ يُعتمد لشمال تونس بوصفه النمط العام غير المدقق محلياً.",
        "url": "",
    },
    "seabass_med_winter": {
        "label_ar": "Bauchot (1987) عبر FishBase — القاروص",
        "citation": "Bauchot M.-L., «Dicentrarchus labrax», FishBase (summary + reproduction), 1987.",
        "claim_ar": "التبييض مرة سنوياً ويميل للشتاء في المتوسط (ديسمبر-مارس)، وقد يكون أبكر/ربيعياً في الأجزاء الجنوبية الدافئة؛ بلوغ جنسي 2-4 سنوات.",
        "url": "https://www.fishbase.se/summary/Dicentrarchus-labrax.html",
    },
    "seabass_surf_zone": {
        "label_ar": "Cervera et al. (2024) — Fishes",
        "citation": "«Coexisting in the Surf Zone: … Dicentrarchus labrax on Gulf of Cádiz Beaches», Fishes 9(5):173, 2024.",
        "claim_ar": "القاروص نوع منطقة الكسرة (surf zone): يتغذى ويحتمي فيها في سنواته الأولى، ونظامه الغذائي يتغير مع الوقت والفصل؛ الحضور الساحلي يزداد شتاءً وربيعاً وخريفاً ويقل صيفاً.",
        "url": "https://www.mdpi.com/2410-3888/9/5/173",
    },
    "seabass_tunis_lagoons": {
        "label_ar": "FAO/MEDRAP — بحيرات تونس",
        "citation": "FAO/MEDRAP, «Tunisia — aquaculture and coastal lagoons»: بحيرات بنزرت وغار الملح وخليج تونس حضانات للقاروص.",
        "claim_ar": "البحيرات الساحلية التونسية (بنزرت، غار الملح، تونس) حضانات لصغار القاروص، ما يرفع الحضور الساحلي قرب المصبات والبحيرات.",
        "url": "https://www.fao.org/4/af025e/AF025E04.htm",
    },
    "sargus_surf_zone": {
        "label_ar": "FishBase + PLOS ONE (2016) — السار",
        "citation": "FishBase (Ref. 13780): «like other sparids, very active and frequents the surf zone, primarily at dawn»؛ PLOS ONE (2016) «Ordinary and extraordinary movement behaviour of small resident fish» — أعلى كثافة قرب منطقة الاندفاع (surge zone) حيث يتغذى على الطحالب واللافقاريات القاعية.",
        "claim_ar": "السار يرتاد منطقة الكسرة فجراً ويتغذى على اللافقاريات التي يفصلها ضرب الموج عن الصخور؛ ينزاح للأعمق فقط في العواصف الشديدة.",
        "url": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0159813",
    },
    "aurata_surf_zone": {
        "label_ar": "FishBase + مراجعة JMSE (2023) — الوراطة",
        "citation": "FishBase: «found in seagrass beds and sandy bottoms as well as in the surf zone commonly to depths of about 30 m»؛ JMSE 11(10):2008 (2023) مراجعة حياة الوراطة: «inhabits sandy seabeds, seagrass beds, and the surf or breaker zone».",
        "claim_ar": "الوراطة قاعية في القيعان الرملية وأعشاب البحر ومنطقة الكسرة حتى ~30م؛ نمط كسرة معتدلة لا ماء هائج دائم.",
        "url": "https://www.fishbase.se/summary/Sparus-aurata.html",
    },
    "mormyrus_surf_backwash": {
        "label_ar": "WoRMS/FishBase/Monaco — المرمار (نمط متوسطي عام)",
        "citation": "WoRMS/FishBase: «found on the shelf, over sandy and muddy bottoms as well as seagrass-beds» (عادة 10-20م)؛ Monaco Nature Encyclopedia: «juveniles often grow in the backwash zone»؛ Buxton et al. 1984: الكبار من منطقة الكسرة حتى ~50م.",
        "claim_ar": "المرمار قاعي رملي ضحل، والصغار في منطقة الغسل خلف الكسرة؛ تفضيل الهدوء استنتاج عام من عمق عيشه الضحل — نمط متوسطي عام غير مدقق بدراسة تونسية محددة.",
        "url": "https://www.marinespecies.org/aphia.php?p=taxdetails&id=127055",
    },
}


# --------------------------------------------------------------------------- #
# Sea-state x month dimension (reporting only, published Mediterranean patterns)
# Each profile declares which sea state its published ecology supports; the
# day's sea state is classified from model wave height (+ wind for a foam hint).
# No study links a Tunisian zone to a sea-state preference yet, so these are
# disclosed as general Mediterranean patterns — never a catch promise (D10/D11).
# --------------------------------------------------------------------------- #
SEA_STATE_KEYS = ("calm", "moderate", "rough", "unknown")

SEA_STATE_LABELS_AR = {
    "calm": "بحر هادئ",
    "moderate": "بحر معتدل",
    "rough": "بحر هائج",
    "unknown": "حالة البحر غير متاحة",
}

# Rough classification thresholds on significant wave height (metres). These
# are presentation bands, not safety gates — safety keeps its own audited
# thresholds in policy.py.
_CALM_MAX_M = 0.6
_ROUGH_MIN_M = 1.1
# Foam (whitecaps) is estimated from the model, not observed: whitecaps become
# common around ~0.8 m waves and under sustained wind >= ~22 km/h (Beaufort ~4).
_FOAM_WAVE_M = 0.8
_FOAM_WIND_KMH = 22.0


@dataclass(frozen=True, slots=True)
class SeaStatePreference:
    """The sea state a species' published ecology supports, with disclosure."""

    label_ar: str
    basis_ar: str
    preferred: frozenset[str]
    sources: tuple[str, ...] = ()


def classify_sea_state(wave_m: float | None, wind_kmh: float | None) -> tuple[str, bool]:
    """Classify the day's sea state and flag estimated foam (whitecaps).

    Returns (state_key, foam_estimate). The foam flag is a model estimate, never
    a direct observation — the callers must disclose that.
    """
    if wave_m is None:
        return "unknown", False
    if wave_m < _CALM_MAX_M:
        state = "calm"
    elif wave_m < _ROUGH_MIN_M:
        state = "moderate"
    else:
        state = "rough"
    foam = wave_m >= _FOAM_WAVE_M or (wind_kmh is not None and wind_kmh >= _FOAM_WIND_KMH)
    return state, foam


def sea_state_fit_for(preference: SeaStatePreference | None, state: str) -> str:
    """favorable when the day's state matches the published preference, else neutral."""
    if preference is None or state == "unknown":
        return "unknown"
    if state in preference.preferred:
        return "favorable"
    return "neutral"


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    label_ar: str
    preferred_sst_c: tuple[float, float] | None
    tolerated_sst_c: tuple[float, float] | None
    twilight_bonus: int
    night_bonus: int
    preferred_shores: frozenset[ShoreType]
    habitat_ar: str
    # Month x Tunisian-zone presence matrix (January..December) of 0..3 levels.
    # Derived from the reproduction/aggregation seasons documented in
    # SOURCE_REGISTRY (see SOURCES-AUDIT §3); NOT a Tunisian catch log.
    season_months_x_zone: dict[str, tuple[int, ...]] | None = None
    # Per-species/per-location spring/neap response. None == Unknown until a
    # Tunisian catch log is calibrated (phase 6 stays honest about this).
    spring_neap_response_ar: str | None = None
    # Registry keys of the scientific sources backing this profile.
    sources: tuple[str, ...] = ()
    # Published sea-state preference (Mediterranean pattern, disclosed).
    sea_state_preference: SeaStatePreference | None = None

    def monthly_presence(self, zone: str, month: int) -> int | None:
        """Return the presence level (0-3) for a zone and 1-based month, or None."""
        if self.season_months_x_zone is None:
            return None
        row = self.season_months_x_zone.get(zone)
        if row is None or not 1 <= month <= 12:
            return None
        return row[month - 1]


def _season(values: dict[str, str]) -> dict[str, tuple[int, ...]]:
    return {zone: tuple(int(ch) for ch in row) for zone, row in values.items()}


# Initial, deliberately low-weight priors for thermal and twilight/night feeding.
# Temperature alone never predicts a catch; the seasonal matrices above carry
# the primary availability signal and are grounded in published Tunisian studies.
SPECIES_PROFILES: dict[TargetSpecies, SpeciesProfile] = {
    TargetSpecies.GENERAL: SpeciesProfile(
        label_ar="صيد عام",
        preferred_sst_c=None,
        tolerated_sst_c=None,
        twilight_bonus=9,
        night_bonus=1,
        preferred_shores=frozenset(),
        habitat_ar="عام — بلا تفضيل موطن محدد",
        sources=tuple(SOURCE_REGISTRY),
    ),
    TargetSpecies.EUROPEAN_SEABASS: SpeciesProfile(
        label_ar="القاروص",
        preferred_sst_c=(13.0, 21.0),
        tolerated_sst_c=(10.0, 25.0),
        twilight_bonus=11,
        night_bonus=5,
        preferred_shores=frozenset({ShoreType.SANDY, ShoreType.ROCKY}),
        habitat_ar="رمل وصخر؛ يقترب من الكسرة والمصبات والبحيرات ليلاً وقرب الغسق",
        # Mediterranean winter spawning (Dec-Mar, earlier in the warm south),
        # coastal presence strongest winter-spring, weakest in summer; the
        # southern lagoons (Gulf of Gabès/Djerba) are leanest in summer.
        season_months_x_zone=_season(
            {
                "northwest": "333221112333",
                "bizerte_tunis": "333221112333",
                "cap_bon_hammamet": "333221112333",
                "sahel": "222221112233",
                "gabes": "333210001233",
                "south": "332210001233",
            }
        ),
        sources=("seabass_med_winter", "seabass_surf_zone", "seabass_tunis_lagoons"),
        sea_state_preference=SeaStatePreference(
            label_ar="بحر متكسر مع رغوة (منطقة الكسرة)",
            basis_ar="نوع منطقة الكسرة: يتغذى ويحتمي فيها صغاره، ويُصطاد قرب الموج المتكسر والرغوة (Cervera et al. 2024؛ FishBase). نمط متوسطي عام غير مدقق بدراسة تونسية محددة.",
            preferred=frozenset({"rough"}),
            sources=("seabass_surf_zone",),
        ),
    ),
    TargetSpecies.GILTHEAD_SEABREAM: SpeciesProfile(
        label_ar="الوراطة",
        preferred_sst_c=(17.0, 26.0),
        tolerated_sst_c=(13.0, 29.0),
        twilight_bonus=8,
        night_bonus=2,
        preferred_shores=frozenset({ShoreType.SANDY, ShoreType.ROCKY}),
        habitat_ar="رمل وصخر؛ قرب الحشائش والقنوات الساحلية والبحيرات",
        # Gulf of Gabès: reproduction October-February, peak December-January
        # (Hadj-Taieb et al. 2013); Mediterranean lagoon cycle Nov-Feb. Coastal
        # peak in autumn-winter, moderate spring, weakest in summer.
        season_months_x_zone=_season(
            {
                "northwest": "322221112333",
                "bizerte_tunis": "322221112333",
                "cap_bon_hammamet": "322221112333",
                "sahel": "222221112233",
                "gabes": "322221112333",
                "south": "222221112333",
            }
        ),
        sources=("aurata_gulf_gabes", "aurata_med_lagoon", "aurata_surf_zone"),
        sea_state_preference=SeaStatePreference(
            label_ar="كسرة معتدلة على رمل/أعشاب",
            basis_ar="قاعية في القيعان الرملية وأعشاب البحر ومنطقة الكسرة حتى ~30م (FishBase؛ JMSE 2023) — نمط كسرة معتدلة لا ماء هائج دائم. نمط متوسطي عام.",
            preferred=frozenset({"moderate"}),
            sources=("aurata_surf_zone",),
        ),
    ),
    TargetSpecies.WHITE_SEABREAM: SpeciesProfile(
        label_ar="السار",
        preferred_sst_c=(15.0, 24.0),
        tolerated_sst_c=(12.0, 28.0),
        twilight_bonus=9,
        night_bonus=3,
        preferred_shores=frozenset({ShoreType.ROCKY, ShoreType.JETTY}),
        habitat_ar="صخر وأرصفة وحواجز؛ قرب الصخور المغمورة",
        # Gulf of Tunis (Mouine et al. 2007): sexual activity Jan-May, spawning
        # Mar-May (peak Mar-Apr), gonads resting Jul-Oct. Spring peak on rocks,
        # summer resting, spawning starts earlier toward the warmer south.
        season_months_x_zone=_season(
            {
                "northwest": "223332111122",
                "bizerte_tunis": "223332111122",
                "cap_bon_hammamet": "223332111122",
                "sahel": "233332111112",
                "gabes": "233332111112",
                "south": "233332111112",
            }
        ),
        sources=("sargus_gulf_tunis", "sargus_surf_zone"),
        sea_state_preference=SeaStatePreference(
            label_ar="موج يتكسر على الصخور (منطقة الاندفاع)",
            basis_ar="يرتاد منطقة الكسرة فجراً ويتغذى على اللافقاريات التي يفصلها ضرب الموج عن الصخور (FishBase Ref. 13780؛ PLOS ONE 2016). نمط متوسطي عام.",
            preferred=frozenset({"rough", "moderate"}),
            sources=("sargus_surf_zone",),
        ),
    ),
    TargetSpecies.STRIPED_SEABREAM: SpeciesProfile(
        label_ar="المرمار",
        preferred_sst_c=(16.0, 26.0),
        tolerated_sst_c=(13.0, 29.0),
        twilight_bonus=8,
        night_bonus=2,
        preferred_shores=frozenset({ShoreType.SANDY}),
        habitat_ar="رمل ناعم/متوسط؛ من الشاطئ الرملي المفتوح",
        # Gulf of Gabès: spawning Sep-Nov (Cybium 2016) — an autumn regional
        # pattern; the general Mediterranean pattern is spring-summer (May-Sep),
        # applied to northern Tunisia until locally verified. Winter is weak.
        season_months_x_zone=_season(
            {
                "northwest": "001223332100",
                "bizerte_tunis": "001233332100",
                "cap_bon_hammamet": "001233332100",
                "sahel": "111233332211",
                "gabes": "112222123331",
                "south": "111222112221",
            }
        ),
        sources=("mormyrus_gulf_gabes", "mormyrus_med_summer", "mormyrus_surf_backwash"),
        sea_state_preference=SeaStatePreference(
            label_ar="ماء هادئ على رمل ضحل (منطقة الغسل)",
            basis_ar="قاعي رملي ضحل (عادة 10-20م) والصغار في منطقة الغسل خلف الكسرة (WoRMS/FishBase؛ Monaco Nature Encyclopedia؛ Buxton et al. 1984). تفضيل الهدوء استنتاج عام — نمط متوسطي عام غير مدقق بدراسة تونسية محددة.",
            preferred=frozenset({"calm"}),
            sources=("mormyrus_surf_backwash",),
        ),
    ),
}

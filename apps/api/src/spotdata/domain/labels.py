from .enums import DecisionLevel, TideState, WaveIncidence, WindRelation

DECISION_LABEL_AR = {
    DecisionLevel.GO: "اذهب",
    DecisionLevel.CAUTION: "اذهب بحذر",
    DecisionLevel.NO_GO: "لا تذهب",
    DecisionLevel.UNKNOWN: "المعطيات غير كافية للقرار",
}

WIND_RELATION_AR = {
    WindRelation.ONSHORE: "رياح بحرية مباشرة",
    WindRelation.OFFSHORE: "رياح برّية مباشرة",
    WindRelation.CROSS_ONSHORE: "رياح جانبية مائلة من البحر",
    WindRelation.ALONGSHORE: "رياح موازية تقريباً للشاطئ",
    WindRelation.CROSS_OFFSHORE: "رياح جانبية مائلة من البرّ",
    WindRelation.UNKNOWN: "اتجاه الرياح غير معروف",
}

WAVE_INCIDENCE_AR = {
    WaveIncidence.DIRECT: "موج داخل مباشرة نحو الشاطئ",
    WaveIncidence.OBLIQUE: "موج مائل",
    WaveIncidence.ALONGSHORE: "موج شبه موازٍ للشاطئ",
    WaveIncidence.INCONSISTENT: "اتجاه موج غير متّسق مع خط الساحل",
    WaveIncidence.UNKNOWN: "اتجاه الموج غير معروف",
}

TIDE_STATE_AR = {
    TideState.RISING: "مستوى البحر صاعد",
    TideState.FALLING: "مستوى البحر هابط",
    TideState.SLACK: "حركة مستوى البحر ضعيفة",
    TideState.UNKNOWN: "حركة مستوى البحر غير متوفرة",
}

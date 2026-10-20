"""English + Tamil templates for every advice string the backend generates.

t(key, **params) -> {"en": "...", "ta": "..."}. Parameters named crop/crop2/crop3 are
crop ids and are rendered as the crop name in each language; `date` (ISO string) and
`unit` are localised too.
"""
import datetime as _dt

from . import config

LANGS = ("en", "ta")

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ta": ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்",
           "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"],
}
UNITS = {
    "₹/quintal": {"en": "₹/quintal", "ta": "₹/குவிண்டால்"},
    "₹/100 nuts": {"en": "₹/100 nuts", "ta": "₹/100 காய்கள்"},
}

TEXT = {
    # fertiliser
    "sched_basal": ("Basal (at sowing / planting)", "அடியுரம் (விதைப்பு / நடவின் போது)"),
    "sched_basal_what": ("DAP {dap} kg + MOP {mop} kg + Urea {urea} kg per acre",
                         "ஏக்கருக்கு டி.ஏ.பி {dap} கிலோ + பொட்டாஷ் {mop} கிலோ + யூரியா {urea} கிலோ"),
    "sched_top1": ("1st top dressing (~25-30 days)", "முதல் மேலுரம் (~25-30 நாட்கள்)"),
    "sched_top2": ("2nd top dressing (~45-60 days)", "இரண்டாம் மேலுரம் (~45-60 நாட்கள்)"),
    "sched_no_urea": ("No urea top dressing needed - the N in DAP covers the requirement.",
                      "யூரியா மேலுரம் தேவையில்லை - டி.ஏ.பி-யில் உள்ள தழைச்சத்து போதுமானது."),
    "sched_urea": ("Urea {urea} kg per acre", "ஏக்கருக்கு யூரியா {urea} கிலோ"),
    "sched_palm": ("Every year, in 2 splits (Jun-Jul and Dec-Jan)",
                   "ஆண்டுதோறும், 2 தவணைகளாக (ஜூன்-ஜூலை, டிசம்பர்-ஜனவரி)"),
    "sched_palm_what": ("Urea {urea} kg + DAP {dap} kg + MOP {mop} kg per acre per year, in a basin around each palm",
                        "ஏக்கருக்கு ஆண்டுக்கு யூரியா {urea} கிலோ + டி.ஏ.பி {dap} கிலோ + பொட்டாஷ் {mop} கிலோ, ஒவ்வொரு மரத்தைச் சுற்றியுள்ள வட்டப் பாத்தியில்"),
    "org_fym": ("Farmyard manure (FYM)", "தொழு உரம்"),
    "org_vermicompost": ("Vermicompost", "மண்புழு உரம்"),
    "org_neemcake": ("Neem cake", "வேப்பம் புண்ணாக்கு"),
    "tip_biofert_legume": ("Treat seed with Rhizobium + Phosphobacteria before sowing - pulses fix much of their own nitrogen.",
                           "விதைப்பதற்கு முன் ரைசோபியம் + பாஸ்போபாக்டீரியா கொண்டு விதை நேர்த்தி செய்யவும் - பயறு வகைகள் தமக்கான தழைச்சத்தில் பெரும்பகுதியைத் தாமே நிலைநிறுத்தும்."),
    "tip_biofert": ("Use Azospirillum + Phosphobacteria (seed or soil application) to cut chemical N and P.",
                    "ரசாயன தழை, மணிச்சத்தைக் குறைக்க அசோஸ்பைரில்லம் + பாஸ்போபாக்டீரியா (விதை அல்லது மண்ணில் இடுதல்) பயன்படுத்தவும்."),
    "tip_green_manure": ("Grow and plough in a green manure (daincha / sunnhemp) before the main crop to add organic matter and nitrogen.",
                         "முதன்மைப் பயிருக்கு முன் தக்கைப்பூண்டு / சணப்பு போன்ற பசுந்தாள் உரப் பயிரை வளர்த்து மடக்கி உழவும் - அங்ககச் சத்தும் தழைச்சத்தும் கூடும்."),
    "tip_acid": ("Soil pH {ph} is acidic - apply agricultural lime as per soil test.",
                 "மண்ணின் pH {ph} - அமிலத்தன்மை உள்ளது; மண் பரிசோதனைப்படி சுண்ணாம்பு இடவும்."),
    "tip_alkaline": ("Soil pH {ph} is alkaline - apply gypsum and organic manure as per soil test.",
                     "மண்ணின் pH {ph} - காரத்தன்மை உள்ளது; மண் பரிசோதனைப்படி ஜிப்சம் மற்றும் இயற்கை எரு இடவும்."),
    "fert_summary": ("Fertiliser per acre: Urea {urea} kg, DAP {dap} kg, MOP {mop} kg.",
                     "ஏக்கருக்கு உரம்: யூரியா {urea} கிலோ, டி.ஏ.பி {dap} கிலோ, பொட்டாஷ் {mop} கிலோ."),
    # irrigation
    "irr_none": ("No irrigation needed for {crop} in the next 7 days - rain and soil moisture are enough.",
                 "அடுத்த 7 நாட்களில் {crop} பயிருக்கு நீர் பாய்ச்சத் தேவையில்லை - மழையும் மண் ஈரமும் போதுமானவை."),
    "irr_summary": ("Irrigate {n} time(s) this week. First on {date}: about {mm} mm ({litres} litres per acre). Week total: {week_litres} litres per acre.",
                    "இந்த வாரம் {n} முறை நீர் பாய்ச்சவும். முதலில் {date} அன்று: சுமார் {mm} மி.மீ (ஏக்கருக்கு {litres} லிட்டர்). வார மொத்தம்: ஏக்கருக்கு {week_litres} லிட்டர்."),
    # market
    "mkt_hold": ("Hold about {n} week(s): expected {lo}-{hi} {unit} (about {gain}% better after storage cost).",
                 "சுமார் {n} வாரம் காத்திருக்கவும்: எதிர்பார்க்கும் விலை {lo}-{hi} {unit} (சேமிப்புச் செலவு போக சுமார் {gain}% கூடுதல்)."),
    "mkt_sell": ("Sell now: expected {lo}-{hi} {unit}.",
                 "இப்போதே விற்கவும்: எதிர்பார்க்கும் விலை {lo}-{hi} {unit}."),
    "mkt_reason_mill": ("Cane is sold to the sugar mill at a fixed price - follow the mill's cutting order.",
                        "கரும்பு சர்க்கரை ஆலைக்கு நிர்ணய விலையில் விற்கப்படுகிறது - ஆலையின் வெட்டு அனுமதிப்படி அறுவடை செய்யவும்."),
    "mkt_reason_perishable": ("Perishable produce - storage losses outweigh any price rise.",
                              "விரைவில் கெடும் விளைபொருள் - விலை உயர்வை விட சேமிப்பு இழப்பு அதிகம்."),
    "mkt_reason_nogain": ("Prices are not expected to rise enough to cover storage cost and risk.",
                          "சேமிப்புச் செலவையும் இடரையும் ஈடுகட்டும் அளவுக்கு விலை உயர வாய்ப்பில்லை."),
    # calendar
    "st_land_prep": ("Land preparation", "நிலம் தயாரித்தல்"),
    "st_nursery": ("Nursery", "நாற்றங்கால்"),
    "st_initial": ("Establishment", "பயிர் நிலைபெறுதல்"),
    "st_development": ("Vegetative growth", "தழை வளர்ச்சி"),
    "st_mid": ("Flowering & yield formation", "பூத்தல் & மகசூல் உருவாக்கம்"),
    "st_late": ("Maturity", "முதிர்ச்சி"),
    "st_harvest": ("Harvest", "அறுவடை"),
    "op_sow": ("Sowing + basal fertiliser", "விதைப்பு + அடியுரம்"),
    "op_transplant": ("Transplanting + basal fertiliser", "நடவு + அடியுரம்"),
    "op_palm_cycle": ("Start of yearly cycle: manure + 1st fertiliser split",
                      "ஆண்டுச் சுழற்சி தொடக்கம்: எரு + முதல் தவணை உரம்"),
    "op_palm_split2": ("2nd fertiliser split + mulch the basin with coconut husk",
                       "இரண்டாம் தவணை உரம் + வட்டப் பாத்தியில் தென்னை நார்க்கழிவு மூடாக்கு"),
    "op_palm_summer": ("Summer: irrigate the basins regularly - water stress cuts nut set",
                       "கோடை: வட்டப் பாத்திகளுக்குத் தொடர்ந்து நீர் பாய்ச்சவும் - நீர்ப் பற்றாக்குறை காய்ப்பைக் குறைக்கும்"),
    "op_palm_harvest": ("Nuts are harvested every ~45-60 days through the year",
                        "ஆண்டு முழுவதும் சுமார் 45-60 நாட்களுக்கு ஒருமுறை காய் பறிக்கலாம்"),
    "op_topdress1": ("Weeding + 1st urea top dressing", "களையெடுப்பு + முதல் யூரியா மேலுரம்"),
    "op_flowering": ("Critical stage: do not let the field dry; 2nd top dressing",
                     "முக்கியப் பருவம்: வயலைக் காய விடாதீர்கள்; இரண்டாம் மேலுரம்"),
    "op_harvest": ("Harvest window opens", "அறுவடைக் காலம் தொடங்குகிறது"),
    # summary / speech
    "rec_summary": ("Best crop for your field: {crop}, {pct} percent confidence. Next options: {crop2} and {crop3}.",
                    "உங்கள் நிலத்திற்கு ஏற்ற பயிர்: {crop}, {pct} சதவீத நம்பகத்தன்மை. அடுத்த வாய்ப்புகள்: {crop2}, {crop3}."),
    "advice_intro": ("KrishiMitra advice for {crop}.", "{crop} பயிருக்கான கிருஷிமித்ரா ஆலோசனை."),
}

_CROP_PARAMS = ("crop", "crop2", "crop3")


def fmt_date(iso, lang):
    d = _dt.date.fromisoformat(iso)
    if lang == "ta":
        return "%s %d" % (MONTHS["ta"][d.month - 1], d.day)
    return "%d %s" % (d.day, MONTHS["en"][d.month - 1])


def indian_int(n):
    """12345678 -> '1,23,45,678' (Indian digit grouping)."""
    s = str(int(n))
    neg = s.startswith("-")
    s = s.lstrip("-")
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if neg else "") + s


def _render(template, lang, params):
    p = {}
    for k, v in params.items():
        if k in _CROP_PARAMS and v in config.CROP_NAMES:
            p[k] = config.CROP_NAMES[v][lang]
        elif k == "date":
            p[k] = fmt_date(v, lang)
        elif k == "unit":
            p[k] = UNITS.get(v, {}).get(lang, v)
        elif isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 1000:
            p[k] = indian_int(v)
        elif isinstance(v, float):
            p[k] = ("%.1f" % v).rstrip("0").rstrip(".")
        else:
            p[k] = v
    return template.format(**p)


def t(key, **params):
    en, ta = TEXT[key]
    return {"en": _render(en, "en", params), "ta": _render(ta, "ta", params)}


def join(*parts):
    """Concatenate several {"en","ta"} strings with spaces."""
    return {lang: " ".join(p[lang] for p in parts if p) for lang in LANGS}

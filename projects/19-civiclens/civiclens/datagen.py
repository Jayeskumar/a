"""Deterministic synthetic complaint stream for a 20-ward demo town.

The generator works at two levels:

* **incidents** - one real-world problem (a pothole, a dead streetlight) with a department,
  sub-issue, true urgency, location, start time and resolution time;
* **complaints** - what citizens actually file about an incident: one or more reports in
  English, Tamil script or Tanglish, via different channels, a little apart in time and space.

Ground truth kept on every complaint (true department, urgency, incident id, planted hotspot)
is what lets us *measure* routing, duplicate detection and hotspot detection honestly.

Run ``python -m civiclens.datagen`` to write data/complaints.csv and data/ground_truth.json.
"""

import csv
import datetime as _dt
import heapq
import io
import json
import math
import os
import random

from . import config as C

# ----------------------------------------------------------------------------- town
WARD_NAMES = [
    ("Kamarajar Nagar", "காமராஜர் நகர்"), ("Anna Nagar", "அண்ணா நகர்"), ("Periyar Nagar", "பெரியார் நகர்"),
    ("Bharathi Nagar", "பாரதி நகர்"), ("Nehru Nagar", "நேரு நகர்"),
    ("Gandhi Market", "காந்தி சந்தை"), ("Old Bus Stand", "பழைய பேருந்து நிலையம்"), ("Temple Street", "கோவில் தெரு"),
    ("Mettu Street", "மேட்டு தெரு"), ("Railway Colony", "ரயில்வே காலனி"),
    ("VOC Nagar", "வ உ சி நகர்"), ("New Bus Stand", "புதிய பேருந்து நிலையம்"), ("Thiruvika Nagar", "திருவிக நகர்"),
    ("Ambedkar Nagar", "அம்பேத்கர் நகர்"), ("Indira Nagar", "இந்திரா நகர்"),
    ("Lake View", "ஏரிக்கரை"), ("Industrial Estate", "தொழிற்பேட்டை"), ("Rajaji Nagar", "ராஜாஜி நகர்"),
    ("Pudhupalayam", "புதுப்பாளையம்"), ("College Campus", "கல்லூரி வளாகம்"),
]
# relative complaint volume (population x density); centre wards are busier (assumed)
WARD_WEIGHT = [0.7, 0.8, 0.9, 0.8, 0.6,
               1.4, 1.6, 1.3, 1.2, 0.9,
               1.0, 1.5, 1.2, 1.0, 0.9,
               0.6, 0.8, 0.8, 0.7, 0.25]
# resolution-time multiplier per ward (crew size, distance from depot; assumed)
WARD_EFFICIENCY = [1.00, 0.90, 1.05, 1.25, 0.95,
                   1.20, 1.00, 0.85, 0.95, 1.10,
                   0.90, 1.05, 0.90, 1.00, 1.15,
                   1.30, 1.60, 0.95, 1.50, 0.85]

LM_TYPES = {
    "temple": ("temple", "கோவில்", "kovil"),
    "school": ("school", "பள்ளி", "school"),
    "busstop": ("bus stop", "பேருந்து நிறுத்தம்", "bus stop"),
    "ration": ("ration shop", "ரேஷன் கடை", "ration kadai"),
    "tank": ("water tank", "தண்ணீர் தொட்டி", "thanni tank"),
    "park": ("park", "பூங்கா", "park"),
    "hospital": ("hospital", "மருத்துவமனை", "hospital"),
    "market": ("market", "சந்தை", "market"),
    "junction": ("junction", "சந்திப்பு", "junction"),
    "hall": ("community hall", "சமுதாய கூடம்", "community hall"),
}
DEITIES = [("Murugan", "முருகன்"), ("Vinayagar", "விநாயகர்"), ("Mariamman", "மாரியம்மன்"), ("Perumal", "பெருமாள்")]
LEADERS = [("Gandhi", "காந்தி"), ("Nehru", "நேரு"), ("Anna", "அண்ணா"), ("Kamarajar", "காமராஜர்"),
           ("Periyar", "பெரியார்"), ("Bharathi", "பாரதி"), ("Valluvar", "வள்ளுவர்"), ("Kannagi", "கண்ணகி"),
           ("Kaveri", "காவேரி"), ("Ambedkar", "அம்பேத்கர்"), ("Rajaji", "ராஜாஜி"), ("Indira", "இந்திரா")]
CAMPUS_PLACES = [("boys hostel block A", "ஆண்கள் விடுதி ஏ பிளாக்", "boys hostel A block"),
                 ("boys hostel block B", "ஆண்கள் விடுதி பி பிளாக்", "boys hostel B block"),
                 ("girls hostel", "மகளிர் விடுதி", "girls hostel"),
                 ("PG hostel", "முதுநிலை மாணவர் விடுதி", "PG hostel"),
                 ("mess hall", "உணவுக் கூடம்", "mess hall")]

LOC_FORMS = {
    "lm": {"en": ["near {p}", "opposite {p}", "behind {p}", "next to {p}"],
           "ta": ["{p} அருகில்", "{p} எதிரில்", "{p} பின்புறம்"],
           "tg": ["{p} kitta", "{p} opposite la", "{p} pakkathula"]},
    "st": {"en": ["on {p}", "in {p}", "at {p}"],
           "ta": ["{p}வில்"],
           "tg": ["{p} la", "{p} kitta"]},
}
DURATIONS = {"en": ["2 days", "3 days", "one week", "10 days", "two weeks"],
             "ta": ["2 நாட்களாக", "3 நாட்களாக", "ஒரு வாரமாக", "10 நாட்களாக", "இரண்டு வாரமாக"],
             "tg": ["2 naala", "3 naala", "oru vaarama", "10 naala", "rendu vaarama"]}

# ----------------------------------------------------------------------------- complaint templates
# (dept, key, base urgency 1..4, weight within dept, {lang: [templates]}). {loc} = location phrase,
# {dur} = duration phrase. For HOSTEL, {loc} is the campus building.
ISSUES = [
    ("ROADS", "pothole", 3, 0.45, {
        "en": ["Big pothole {loc}", "Pothole on the road {loc} not repaired yet", "Deep pothole {loc}, two wheelers struggling",
               "Road full of potholes {loc}", "Huge potholes {loc}, please fill them"],
        "ta": ["{loc} சாலையில் பெரிய குழி உள்ளது", "{loc} ரோட்டில் உள்ள குழியை சரி செய்யவில்லை", "{loc} சாலை முழுவதும் குழிகள்"],
        "tg": ["{loc} road la periya kuzhi iruku", "{loc} pothole romba deep ah iruku", "{loc} road fulla kuzhi, bike la poga mudiyala"]}),
    ("ROADS", "road_damage", 3, 0.25, {
        "en": ["Road damaged after pipeline work {loc}", "Road surface broken {loc}, needs relaying", "Tar road washed away {loc}"],
        "ta": ["{loc} குழாய் பதிப்பு வேலைக்குப் பிறகு சாலை சேதமடைந்துள்ளது", "{loc} சாலை உடைந்து கிடக்கிறது"],
        "tg": ["{loc} pipeline work apram road damage aagi iruku", "{loc} road udanju poyiruku, relay pannunga"]}),
    ("ROADS", "speed_breaker", 4, 0.15, {
        "en": ["Need a speed breaker {loc}, vehicles going very fast", "Speed breaker {loc} not painted, not visible at night"],
        "ta": ["{loc} வேகத்தடை அமைக்க வேண்டும், வாகனங்கள் வேகமாக செல்கின்றன"],
        "tg": ["{loc} speed breaker podunga, vandi ellam fast ah poguthu"]}),
    ("ROADS", "road_hazard", 1, 0.15, {
        "en": ["Open trench on the road {loc}, accident happened last night", "Road caved in {loc}, big pit, accident risk"],
        "ta": ["{loc} சாலையில் திறந்த பள்ளம், நேற்று இரவு விபத்து நடந்தது"],
        "tg": ["{loc} road la periya pallam, nethu night accident aachu"]}),

    ("SANITATION", "garbage_not_collected", 3, 0.50, {
        "en": ["Garbage not collected {loc} for {dur}", "Garbage bin overflowing {loc}", "Waste not cleared {loc}, bad smell",
               "Garbage van has not come {loc} for {dur}"],
        "ta": ["{loc} குப்பை அள்ளவில்லை", "{loc} குப்பைத் தொட்டி நிரம்பி வழிகிறது", "{loc} {dur} குப்பை எடுக்கவில்லை, துர்நாற்றம் வீசுகிறது"],
        "tg": ["{loc} kuppai edukala {dur}", "{loc} garbage bin full ah iruku, smell adikuthu", "{loc} kuppai vandi varave illa"]}),
    ("SANITATION", "garbage_dumping", 3, 0.22, {
        "en": ["People dumping garbage on the road {loc}", "Illegal garbage dump {loc}, nobody clears it"],
        "ta": ["{loc} சாலையில் குப்பை கொட்டுகிறார்கள்"],
        "tg": ["{loc} road la kuppai kottraanga, yaarum clean pannala"]}),
    ("SANITATION", "garbage_burning", 2, 0.10, {
        "en": ["Garbage being burnt {loc}, smoke everywhere", "Someone burning waste {loc}, cannot breathe"],
        "ta": ["{loc} குப்பையை எரிக்கிறார்கள், புகை அதிகம்"],
        "tg": ["{loc} kuppai erikiraanga, smoke romba iruku"]}),
    ("SANITATION", "street_sweeping", 4, 0.18, {
        "en": ["Street not swept {loc} for {dur}", "Public toilet {loc} is dirty, not cleaned"],
        "ta": ["{loc} தெரு சுத்தம் செய்யப்படவில்லை", "{loc} பொது கழிப்பறை சுத்தம் இல்லை"],
        "tg": ["{loc} theru clean pannala", "{loc} public toilet romba dirty ah iruku"]}),

    ("STREETLIGHT", "light_not_working", 3, 0.58, {
        "en": ["Street light not working {loc}", "Streetlight off {loc} for {dur}, very dark at night",
               "Street lamps not glowing {loc}", "Three street lights not working {loc}"],
        "ta": ["{loc} தெரு விளக்கு எரியவில்லை", "{loc} {dur} தெருவிளக்கு எரியவில்லை, இரவில் இருட்டாக உள்ளது"],
        "tg": ["{loc} street light eriyala", "{loc} light work aagala {dur}, night romba dark ah iruku"]}),
    ("STREETLIGHT", "light_daytime", 4, 0.12, {
        "en": ["Street lights burning during day time {loc}, waste of power"],
        "ta": ["{loc} பகலிலும் தெரு விளக்கு எரிகிறது"],
        "tg": ["{loc} pagal la kooda street light eriyuthu"]}),
    ("STREETLIGHT", "live_wire", 1, 0.15, {
        "en": ["Live wire hanging {loc}, very dangerous", "Electric wire fallen on the road {loc}",
               "Current leaking from electric pole {loc}, a boy got shock"],
        "ta": ["{loc} மின் கம்பி அறுந்து தொங்குகிறது, ஆபத்து", "{loc} மின்கம்பத்தில் மின்சாரம் கசிகிறது"],
        "tg": ["{loc} current wire thongitu iruku, danger", "{loc} EB pole la current leak aaguthu, shock adichuchu"]}),
    ("STREETLIGHT", "pole_damaged", 2, 0.15, {
        "en": ["Electric pole tilted {loc}, may fall anytime"],
        "ta": ["{loc} மின்கம்பம் சாய்ந்து உள்ளது, விழும் நிலையில் உள்ளது"],
        "tg": ["{loc} EB pole saanju iruku, vizhum pola iruku"]}),

    ("WATER", "no_water", 2, 0.32, {
        "en": ["No drinking water supply {loc} for {dur}", "Corporation water not coming {loc}", "No water in taps {loc} since {dur}"],
        "ta": ["{loc} {dur} குடிநீர் வரவில்லை", "{loc} குழாயில் தண்ணீர் வரவில்லை"],
        "tg": ["{loc} {dur} thanni varala", "{loc} drinking water supply illa"]}),
    ("WATER", "pipe_leak", 3, 0.33, {
        "en": ["Water pipe leaking {loc}, lots of water wasted", "Pipeline burst {loc}, water flowing on the road"],
        "ta": ["{loc} குடிநீர் குழாய் உடைந்து தண்ணீர் வீணாகிறது"],
        "tg": ["{loc} water pipe leak aaguthu, thanni waste aaguthu", "{loc} pipeline burst aagi road fulla thanni"]}),
    ("WATER", "dirty_water", 2, 0.17, {
        "en": ["Muddy water coming in the tap {loc}", "Drinking water smells bad {loc}"],
        "ta": ["{loc} குழாயில் கலங்கலான தண்ணீர் வருகிறது"],
        "tg": ["{loc} tap la kalangal thanni varuthu", "{loc} drinking water smell adikuthu"]}),
    ("WATER", "sewage_in_water", 1, 0.08, {
        "en": ["Sewage mixing in drinking water {loc}, people falling sick", "Drainage water entering drinking water line {loc}"],
        "ta": ["{loc} குடிநீரில் சாக்கடை நீர் கலக்கிறது"],
        "tg": ["{loc} drinking water la sakkadai thanni mix aaguthu"]}),
    ("WATER", "low_pressure", 4, 0.10, {
        "en": ["Very low water pressure {loc}"],
        "ta": ["{loc} தண்ணீர் அழுத்தம் மிகவும் குறைவாக உள்ளது"],
        "tg": ["{loc} water pressure romba kammi"]}),

    ("DRAINAGE", "drain_overflow", 3, 0.45, {
        "en": ["Drainage overflowing {loc}", "Drain blocked {loc}, dirty water on the road", "Sewage overflowing on the road {loc}"],
        "ta": ["{loc} சாக்கடை நிரம்பி வழிகிறது", "{loc} கழிவுநீர் கால்வாய் அடைப்பு"],
        "tg": ["{loc} drainage overflow ah iruku", "{loc} drainage block aagi road la thanni nikuthu"]}),
    ("DRAINAGE", "open_manhole", 1, 0.12, {
        "en": ["Open manhole {loc}, very dangerous", "Manhole cover missing {loc}"],
        "ta": ["{loc} பாதாள சாக்கடை மூடி இல்லை, ஆபத்து"],
        "tg": ["{loc} manhole moodi illa, danger ah iruku"]}),
    ("DRAINAGE", "stagnant_water", 3, 0.25, {
        "en": ["Rain water stagnant {loc}, mosquito breeding", "Water logging {loc} after rain"],
        "ta": ["{loc} மழைநீர் தேங்கி கொசு அதிகம்"],
        "tg": ["{loc} mazhai thanni thengi iruku, kosu romba"]}),
    ("DRAINAGE", "sewage_smell", 3, 0.18, {
        "en": ["Sewage smell unbearable {loc}"],
        "ta": ["{loc} சாக்கடை நாற்றம் தாங்க முடியவில்லை"],
        "tg": ["{loc} sakkadai smell thanga mudiyala"]}),

    ("ANIMAL", "stray_dogs", 3, 0.50, {
        "en": ["Stray dogs menace {loc}, chasing two wheelers", "Too many street dogs {loc}"],
        "ta": ["{loc} தெரு நாய்கள் தொல்லை அதிகம்"],
        "tg": ["{loc} theru naai thollai romba iruku", "{loc} naai bike pinnadi odi varuthu"]}),
    ("ANIMAL", "dog_bite", 1, 0.12, {
        "en": ["Stray dog bit a child {loc}", "Dog bite case {loc}, catch the dog"],
        "ta": ["{loc} தெரு நாய் குழந்தையை கடித்தது"],
        "tg": ["{loc} naai oru paiyana kadichiduchu"]}),
    ("ANIMAL", "cattle", 3, 0.23, {
        "en": ["Cows roaming on the main road {loc}, traffic problem"],
        "ta": ["{loc} சாலையில் மாடுகள் சுற்றித் திரிகின்றன"],
        "tg": ["{loc} road la maadu suthuthu, traffic problem"]}),
    ("ANIMAL", "dead_animal", 2, 0.15, {
        "en": ["Dead dog lying on the road {loc}, bad smell"],
        "ta": ["{loc} சாலையில் இறந்த நாய் கிடக்கிறது"],
        "tg": ["{loc} road la setha naai kidakuthu, smell adikuthu"]}),

    ("HOSTEL", "hostel_water", 2, 0.25, {
        "en": ["No water in the bathrooms of {loc}", "Water not coming in {loc} since morning"],
        "ta": ["{loc} குளியலறையில் தண்ணீர் இல்லை"],
        "tg": ["{loc} bathroom la thanni illa"]}),
    ("HOSTEL", "mess_food", 3, 0.30, {
        "en": ["Mess food quality very poor in {loc}", "Food served in {loc} was stale today"],
        "ta": ["{loc} உணவு தரம் மோசமாக உள்ளது"],
        "tg": ["{loc} mess saapadu nalla illa"]}),
    ("HOSTEL", "hostel_wifi", 4, 0.18, {
        "en": ["WiFi not working in {loc}"],
        "ta": ["{loc} வைஃபை வேலை செய்யவில்லை"],
        "tg": ["{loc} wifi work aagala"]}),
    ("HOSTEL", "hostel_electrical", 3, 0.15, {
        "en": ["Fan and light not working in {loc} room"],
        "ta": ["{loc} அறையில் மின்விசிறி வேலை செய்யவில்லை"],
        "tg": ["{loc} room la fan odala"]}),
    ("HOSTEL", "hostel_cleaning", 4, 0.12, {
        "en": ["Washrooms not cleaned in {loc}"],
        "ta": ["{loc} கழிப்பறை சுத்தம் செய்யப்படவில்லை"],
        "tg": ["{loc} washroom clean pannala"]}),

    ("OTHER", "noise", 4, 0.20, {
        "en": ["Loud music from marriage hall {loc} till midnight", "Loudspeaker noise {loc} late night"],
        "ta": ["{loc} இரவு முழுவதும் ஒலிபெருக்கி சத்தம்"],
        "tg": ["{loc} loudspeaker sound romba, night thoonga mudiyala"]}),
    ("OTHER", "encroachment", 4, 0.18, {
        "en": ["Shops encroaching the footpath {loc}", "Encroachment on the road {loc} by vendors"],
        "ta": ["{loc} நடைபாதை ஆக்கிரமிப்பு அதிகம்"],
        "tg": ["{loc} footpath la kadai pottu encroach panniruka"]}),
    ("OTHER", "tree_fall", 2, 0.15, {
        "en": ["Tree branch about to fall {loc}", "Fallen tree blocking the road {loc}"],
        "ta": ["{loc} மரம் சாய்ந்து சாலையை மறைக்கிறது"],
        "tg": ["{loc} maram vizhundhu road block aagiduchu"]}),
    ("OTHER", "mosquito", 3, 0.17, {
        "en": ["Mosquito menace {loc}, need fogging", "Dengue cases {loc}, please do fogging"],
        "ta": ["{loc} கொசு தொல்லை, புகை மருந்து அடிக்கவும்"],
        "tg": ["{loc} kosu thollai, fogging pannunga"]}),
    ("OTHER", "banner", 4, 0.15, {
        "en": ["Illegal flex banner {loc} blocking the view", "Unauthorised hoarding {loc}"],
        "ta": ["{loc} அனுமதியில்லாத பேனர் வைக்கப்பட்டுள்ளது"],
        "tg": ["{loc} illegal flex banner vachirukanga"]}),
    ("OTHER", "parking", 4, 0.15, {
        "en": ["Illegal parking {loc} blocking our gate", "Vehicles parked on the footpath {loc}"],
        "ta": ["{loc} வாகனங்களை தவறாக நிறுத்துகிறார்கள்"],
        "tg": ["{loc} wrong parking, gate block pannuranga"]}),
]
ISSUE_BY_KEY = {i[1]: i for i in ISSUES}

# Severity modifiers: (departments it can appear in, probability, effect, phrases per language)
MODIFIERS = {
    "school": ({"ROADS", "STREETLIGHT", "DRAINAGE", "ANIMAL", "SANITATION", "OTHER"}, 0.08, "up", {
        "en": ["School children use this road", "Near the school, kids at risk"],
        "ta": ["பள்ளி குழந்தைகள் இந்த வழியில் செல்கிறார்கள்"],
        "tg": ["school pasanga intha vazhi la dhaan poraanga"]}),
    "elderly": ({"WATER", "STREETLIGHT", "ROADS"}, 0.05, "up", {
        "en": ["Elderly people are suffering"],
        "ta": ["வயதானவர்கள் மிகவும் சிரமப்படுகிறார்கள்"],
        "tg": ["vayasaanavanga romba kashta padraanga"]}),
    "accident": ({"ROADS", "ANIMAL", "STREETLIGHT"}, 0.05, "p1", {
        "en": ["Two wheeler riders fell here yesterday", "An accident happened here last week"],
        "ta": ["நேற்று இங்கு இருசக்கர வாகனம் விழுந்து விபத்து நடந்தது"],
        "tg": ["nethu inga bike vizhunthu accident aachu"]}),
    "sick": ({"WATER", "DRAINAGE", "SANITATION", "OTHER"}, 0.06, "up", {
        "en": ["Many people are falling sick"],
        "ta": ["பலருக்கு காய்ச்சல் வந்துள்ளது"],
        "tg": ["neraya perukku fever vandhuruku"]}),
}
LONG_DURATION_DEPTS = {"WATER", "SANITATION", "STREETLIGHT", "DRAINAGE"}

VAGUE = {"en": ["Problem {loc}, nobody is responding", "{loc} issue still not solved, please come and check",
                "Complaint regarding {loc}, no action taken"],
         "ta": ["{loc} பிரச்சனை, யாரும் கவனிக்கவில்லை"],
         "tg": ["{loc} problem iruku, yaarum vandhu paakala"]}
PREFIX = {"en": ["Sir, ", "Dear sir, ", "Respected officer, "], "ta": ["ஐயா, "], "tg": ["Sir, ", "Hello sir, "]}
SUFFIX = {"en": ["Kindly take action.", "Please do the needful.", "Complained before, no action."],
          "ta": ["உடனடியாக நடவடிக்கை எடுக்கவும்.", "பலமுறை புகார் அளித்தும் நடவடிக்கை இல்லை."],
          "tg": ["seekiram action edunga sir.", "already complaint pannom, no action.", "please sari pannunga."]}

# ----------------------------------------------------------------------------- planted structure
PLANTED_HOTSPOTS = [
    {"id": "H1", "dept": "SANITATION", "issues": ["garbage_dumping", "garbage_not_collected"], "ward": 6, "lm": "market", "n": 30, "sigma": 55},
    {"id": "H2", "dept": "ROADS", "issues": ["pothole", "road_damage"], "ward": 17, "lm": "junction", "n": 28, "sigma": 60},
    {"id": "H3", "dept": "STREETLIGHT", "issues": ["light_not_working"], "ward": 14, "lm": "park", "n": 26, "sigma": 55},
    {"id": "H4", "dept": "WATER", "issues": ["pipe_leak", "dirty_water"], "ward": 9, "lm": "tank", "n": 26, "sigma": 60},
    {"id": "H5", "dept": "DRAINAGE", "issues": ["drain_overflow", "sewage_smell"], "ward": 7, "lm": "busstop", "n": 30, "sigma": 55},
    {"id": "H6", "dept": "ANIMAL", "issues": ["stray_dogs"], "ward": 12, "lm": "market", "n": 24, "sigma": 60},
]
PLANTED_SURGES = [   # emerging hotspots: a burst in one ward-week
    {"id": "E1", "dept": "DRAINAGE", "issues": ["drain_overflow", "stagnant_water"], "ward": 3, "lm": "school", "week": 11, "n": 14, "sigma": 110},
    {"id": "E2", "dept": "ANIMAL", "issues": ["stray_dogs", "dog_bite"], "ward": 15, "lm": "hall", "week": 8, "n": 11, "sigma": 110},
    {"id": "E3", "dept": "SANITATION", "issues": ["garbage_not_collected"], "ward": 11, "lm": "ration", "week": 13, "n": 15, "sigma": 110},
]
REQUIRED_LANDMARKS = {h["ward"]: [] for h in PLANTED_HOTSPOTS + PLANTED_SURGES}
for _h in PLANTED_HOTSPOTS + PLANTED_SURGES:
    REQUIRED_LANDMARKS[_h["ward"]].append(_h["lm"])


# ----------------------------------------------------------------------------- geometry helpers
def ward_code(i):
    return "W%02d" % i


def ward_rc(i):
    """Ward i (1-based, row-major from the north-west corner) -> (row, col)."""
    return (i - 1) // C.GRID_COLS, (i - 1) % C.GRID_COLS


def ward_bounds_m(i):
    r, c = ward_rc(i)
    s = C.WARD_KM * 1000.0
    x0, y0 = c * s, (C.GRID_ROWS - 1 - r) * s
    return x0, y0, x0 + s, y0 + s


def to_latlon(x, y):
    return (round(C.ORIGIN_LAT + y / 1000.0 / C.KM_PER_DEG_LAT, 6),
            round(C.ORIGIN_LON + x / 1000.0 / C.KM_PER_DEG_LON, 6))


def to_xy(lat, lon):
    return ((lon - C.ORIGIN_LON) * C.KM_PER_DEG_LON * 1000.0, (lat - C.ORIGIN_LAT) * C.KM_PER_DEG_LAT * 1000.0)


def ward_of_xy(x, y):
    s = C.WARD_KM * 1000.0
    c = min(C.GRID_COLS - 1, max(0, int(x // s)))
    r = C.GRID_ROWS - 1 - min(C.GRID_ROWS - 1, max(0, int(y // s)))
    return r * C.GRID_COLS + c + 1


def iso(t):
    d = _dt.datetime.strptime(C.START_DATE, "%Y-%m-%d") + _dt.timedelta(days=t)
    return d.strftime("%Y-%m-%dT%H:%M")


def now_t():
    return (C.N_DAYS - 1) + C.NOW_HOUR / 24.0


def week_of(t):
    return min(C.N_WEEKS, int(t // 7) + 1)


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _choice_w(rng, items, weights):
    tot = sum(weights)
    u = rng.random() * tot
    acc = 0.0
    for it, w in zip(items, weights):
        acc += w
        if u <= acc:
            return it
    return items[-1]


def build_town(rng):
    wards, places = [], {}
    for i in range(1, C.GRID_ROWS * C.GRID_COLS + 1):
        x0, y0, x1, y1 = ward_bounds_m(i)
        en, ta = WARD_NAMES[i - 1]
        la0, lo0 = to_latlon(x0, y0)
        la1, lo1 = to_latlon(x1, y1)
        wards.append({"code": ward_code(i), "num": i, "name": en, "name_ta": ta, "weight": WARD_WEIGHT[i - 1],
                      "efficiency": WARD_EFFICIENCY[i - 1], "bounds": [la0, lo0, la1, lo1],
                      "center": list(to_latlon((x0 + x1) / 2, (y0 + y1) / 2))})
        pl = []
        if i == C.GRID_ROWS * C.GRID_COLS:      # campus: buildings are the "landmarks"
            for k, (pe, pt, pg) in enumerate(CAMPUS_PLACES):
                x = x0 + 150 + (k % 3) * 330 + rng.uniform(-40, 40)
                y = y0 + 250 + (k // 3) * 450 + rng.uniform(-40, 40)
                pl.append({"kind": "campus", "type": "campus", "en": pe, "ta": pt, "tg": pg, "x": x, "y": y})
        types = list(REQUIRED_LANDMARKS.get(i, []))
        pool = [t for t in sorted(LM_TYPES) if t not in types]
        rng.shuffle(pool)
        types += pool[:5 - len(types)]
        used = set()
        for t in types:
            names = DEITIES if t == "temple" else LEADERS
            cand = [n for n in names if n[0] not in used]
            ne, nt = cand[rng.randrange(len(cand))]
            used.add(ne)
            te, tt, tg = LM_TYPES[t]
            pl.append({"kind": "lm", "type": t, "en": "%s %s" % (ne, te), "ta": "%s %s" % (nt, tt),
                       "tg": "%s %s" % (ne, tg), "x": rng.uniform(x0 + 120, x1 - 120), "y": rng.uniform(y0 + 120, y1 - 120)})
        for k in range(3):
            cand = [n for n in LEADERS if n[0] not in used]
            ne, nt = cand[rng.randrange(len(cand))]
            used.add(ne)
            horizontal = rng.random() < 0.5
            off = rng.uniform(200, 800)
            seg = ((x0 + 60, y0 + off, x1 - 60, y0 + off) if horizontal else (x0 + off, y0 + 60, x0 + off, y1 - 60))
            pl.append({"kind": "st", "type": "street", "en": "%s Street" % ne, "ta": "%s தெரு" % nt,
                       "tg": "%s %s" % (ne, "theru" if rng.random() < 0.6 else "street"),
                       "seg": seg, "x": (seg[0] + seg[2]) / 2, "y": (seg[1] + seg[3]) / 2})
        places[i] = pl
    return wards, places


def _clip(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _place_point(rng, place, ward, sigma=None):
    x0, y0, x1, y1 = ward_bounds_m(ward)
    if place["kind"] == "st" and sigma is None:
        a, b, c, d = place["seg"]
        u = rng.random()
        x, y = a + (c - a) * u + rng.gauss(0, 35), b + (d - b) * u + rng.gauss(0, 35)
    else:
        s = 150.0 if sigma is None else sigma
        if place["kind"] == "campus":
            s = min(s, 60.0)
        x, y = place["x"] + rng.gauss(0, s), place["y"] + rng.gauss(0, s)
    return _clip(x, x0 + 5, x1 - 5), _clip(y, y0 + 5, y1 - 5)


def _loc_phrase(rng, place, lang):
    if place["kind"] == "campus":
        return place[lang]
    forms = LOC_FORMS[place["kind"]][lang]
    return forms[rng.randrange(len(forms))].format(p=place[lang])


def _typo(rng, text):
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not idx:
        return text
    for _ in range(1 if rng.random() < 0.7 else 2):
        i = idx[rng.randrange(len(idx))]
        w = words[i]
        j = rng.randrange(1, len(w) - 1)
        op = rng.random()
        if op < 0.4:
            w = w[:j] + w[j + 1:]
        elif op < 0.75:
            w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
        else:
            w = w[:j] + w[j] + w[j:]
        words[i] = w
    return " ".join(words)


def compose(rng, issue_key, place, lang, ward, vague=False, info=None):
    """Write one complaint text. Returns (text, modifiers, long_duration); info["tpl"] gets the template id."""
    dept, key, base, _, tmpls = ISSUE_BY_KEY[issue_key]
    loc = _loc_phrase(rng, place, lang)
    dur_i = rng.randrange(len(DURATIONS[lang]))
    if vague:
        t = VAGUE[lang][rng.randrange(len(VAGUE[lang]))].format(loc=loc)
        has_dur = False
        tpl_id = "vague"
    else:
        tl = tmpls[lang]
        ti = rng.randrange(len(tl))
        tpl = tl[ti]
        tpl_id = "%s:%s:%d" % (key, lang, ti)
        has_dur = "{dur}" in tpl
        t = tpl.format(loc=loc, dur=DURATIONS[lang][dur_i])
    t = t[0].upper() + t[1:] if t and t[0].isalpha() and lang != "ta" else t
    parts = [t]
    if not vague and rng.random() < C.SECONDARY_RATE:      # a second, minor problem in another dept
        other = [i for i in ISSUES if i[0] != dept and i[0] != "HOSTEL"]
        o = other[rng.randrange(len(other))]
        ot = o[4][lang][rng.randrange(len(o[4][lang]))]
        ot = ot.format(loc="", dur=DURATIONS[lang][0]).strip(" ,")
        parts.append(("மேலும் " if lang == "ta" else "Also ") + (ot[0].lower() + ot[1:] if lang != "ta" else ot))
    mods = []
    if not vague:
        for m in sorted(MODIFIERS):
            depts, p, _, phrases = MODIFIERS[m]
            pm = p * (1.6 if (m == "accident" and dept == "ROADS") else 1.0)
            if dept in depts and rng.random() < pm:
                ph = phrases[lang]
                parts.append(ph[rng.randrange(len(ph))])
                mods.append(m)
    if rng.random() < 0.25 and place["kind"] != "campus":
        w = WARD_NAMES[ward - 1]
        parts[0] += ", " + (w[1] if lang == "ta" else w[0])
    text = ". ".join(parts)
    if rng.random() < 0.3:
        text = PREFIX[lang][rng.randrange(len(PREFIX[lang]))] + (text[0].lower() + text[1:] if lang == "en" else text)
    if rng.random() < 0.35:
        text = text.rstrip(".") + ". " + SUFFIX[lang][rng.randrange(len(SUFFIX[lang]))]
    if lang != "ta" and rng.random() < C.TYPO_RATE:
        text = _typo(rng, text)
    if info is not None:
        info["tpl"] = tpl_id
    return text, mods, has_dur and dur_i >= 2


def true_urgency(issue_key, mods, long_dur, hidden=0):
    """What a careful human triager would assign after reading this report (plus hidden context)."""
    dept, _, base, _, _ = ISSUE_BY_KEY[issue_key]
    lvl = base
    for m in mods:
        lvl = 1 if MODIFIERS[m][2] == "p1" else lvl - 1
    if long_dur and dept in LONG_DURATION_DEPTS:
        lvl -= 1
    if base >= 3 and "accident" not in mods:
        lvl = max(lvl, 2)          # a nuisance near a school is high priority, not a safety emergency
    lvl += hidden
    return max(1, min(4, lvl))


def _hour(rng):
    hours = list(range(6, 23))
    w = [1, 2, 4, 6, 6, 5, 4, 3, 3, 3, 3, 4, 5, 5, 4, 2, 1]
    return _choice_w(rng, hours, w) + rng.random()


def _lang(rng, channel):
    if channel == "Call centre" and rng.random() < C.CALL_CENTRE_ENGLISH:
        return "en"
    return _choice_w(rng, [l for l, _ in C.LANG_MIX], [w for _, w in C.LANG_MIX])


# ----------------------------------------------------------------------------- generation
def generate(seed=None):
    """Return dict(wards, places, complaints, incidents, planted) - fully deterministic."""
    rng = random.Random(C.SEED if seed is None else seed)
    wards, places = build_town(rng)
    T_NOW = now_t()
    n_wards = len(wards)
    dept_issues = {}
    for it in ISSUES:
        dept_issues.setdefault(it[0], []).append(it)

    incidents = []

    def new_incident(t, dept, issue, ward, place, x, y, planted=None):
        incidents.append({"t": t, "dept": dept, "issue": issue, "ward": ward, "place": place,
                          "x": x, "y": y, "planted": planted})

    # 1) background incidents, day by day
    city_wards = list(range(1, n_wards))          # campus ward handled by HOSTEL
    for day in range(C.N_DAYS):
        dow = day % 7
        lam = C.BACKGROUND_INCIDENTS_PER_DAY * C.DOW_FACTOR[dow]
        for _ in range(_poisson(rng, lam)):
            wk = week_of(day)
            weights = [C.DEPT_SHARE[d] * (C.MONSOON_DRAINAGE_FACTOR if (d == "DRAINAGE" and wk >= C.MONSOON_FROM_WEEK) else 1.0)
                       for d in C.DEPT_CODES]
            dept = _choice_w(rng, C.DEPT_CODES, weights)
            its = dept_issues[dept]
            iw = [i[3] * (1.8 if (i[1] == "stagnant_water" and wk >= C.MONSOON_FROM_WEEK) else 1.0) for i in its]
            issue = _choice_w(rng, its, iw)[1]
            if dept == "HOSTEL":
                ward = n_wards
                place = places[ward][rng.randrange(len(CAMPUS_PLACES))]
            else:
                ward = _choice_w(rng, city_wards + [n_wards], [WARD_WEIGHT[w - 1] for w in city_wards] + [WARD_WEIGHT[-1]])
                cand = [p for p in places[ward] if p["kind"] != "campus"]
                place = cand[rng.randrange(len(cand))]
            t = day + _hour(rng) / 24.0
            if t >= T_NOW:
                continue
            x, y = _place_point(rng, place, ward)
            new_incident(t, dept, issue, ward, place, x, y)

    # 2) planted persistent hotspots (whole period) and emerging surges (one week)
    for h in PLANTED_HOTSPOTS + PLANTED_SURGES:
        ward = h["ward"]
        anchor = next(p for p in places[ward] if p.get("type") == h["lm"])
        streets = [p for p in places[ward] if p["kind"] == "st"]
        h["center"] = list(to_latlon(anchor["x"], anchor["y"]))
        h["place"] = anchor["en"]
        for k in range(h["n"]):
            if "week" in h:
                t = (h["week"] - 1) * 7 + rng.uniform(0, 6.8)
            else:
                t = rng.uniform(0.2, T_NOW - 0.1)
            t = min(t, T_NOW - 0.05)
            issue = h["issues"][rng.randrange(len(h["issues"]))]
            x, y = _place_point(rng, anchor, ward, sigma=h["sigma"])
            phrase_place = anchor if (rng.random() < 0.7 or not streets) else streets[rng.randrange(len(streets))]
            new_incident(t, h["dept"], issue, ward, phrase_place, x, y, planted=h["id"])

    incidents.sort(key=lambda d: d["t"])

    # 3) urgency, resolution (with backlog), and complaints per incident
    open_heap = {d: [] for d in C.DEPT_CODES}
    complaints = []
    for n, inc in enumerate(incidents):
        inc["id"] = "I-%04d" % (n + 1)
        hidden = 0
        if rng.random() < C.HIDDEN_SEVERITY_RATE:      # context the text does not carry (same for every report)
            hidden = -1 if rng.random() < 0.5 else 1
        channel = _choice_w(rng, [c for c, _ in C.CHANNELS], [w for _, w in C.CHANNELS])
        lang = _lang(rng, channel)
        vague = rng.random() < C.VAGUE_RATE
        info = {}
        text, mods, long_dur = compose(rng, inc["issue"], inc["place"], lang, inc["ward"], vague, info)
        u0 = true_urgency(inc["issue"], mods, long_dur, hidden)
        reports = [[inc["t"], text, lang, channel, mods, inc["x"], inc["y"], vague, u0, inc["place"], info["tpl"]]]
        probs = C.DUP_EXTRA_PROBS_URGENT if u0 <= 2 else C.DUP_EXTRA_PROBS_NORMAL
        extra = _choice_w(rng, list(range(len(probs))), probs)
        for _ in range(extra):
            ch = _choice_w(rng, [c for c, _ in C.CHANNELS], [w for _, w in C.CHANNELS])
            lg = lang if rng.random() < 0.5 else _lang(rng, ch)
            if rng.random() < C.DUP_SAME_PLACE_PHRASE or inc["place"]["kind"] == "campus":
                pl = inc["place"]
            else:
                others = [p for p in places[inc["ward"]] if p is not inc["place"] and p["kind"] != "campus"]
                others.sort(key=lambda p: (p["x"] - inc["x"]) ** 2 + (p["y"] - inc["y"]) ** 2)
                pl = others[0] if others else inc["place"]
            vg = rng.random() < C.VAGUE_RATE
            info = {}
            tx, md, ld = compose(rng, inc["issue"], pl, lg, inc["ward"], vg, info)
            dx, dy = rng.gauss(0, C.DUP_JITTER_M), rng.gauss(0, C.DUP_JITTER_M)
            reports.append([None, tx, lg, ch, md, inc["x"] + dx, inc["y"] + dy, vg,
                            true_urgency(inc["issue"], md, ld, hidden), pl, info["tpl"]])
        # the incident is as urgent as its most urgent report; that drives how fast it is fixed
        urg = min(r[8] for r in reports)
        inc["urgency"] = urg
        heap = open_heap[inc["dept"]]
        while heap and heap[0] <= inc["t"]:
            heapq.heappop(heap)
        backlog = len(heap)
        dow = int(inc["t"]) % 7
        med = (C.MEDIAN_RES_DAYS[inc["dept"]] * WARD_EFFICIENCY[inc["ward"] - 1] * C.WEEKEND_SLOWDOWN[dow]
               * C.PRIORITY_SPEED[urg] * (1.0 + backlog / float(C.BACKLOG_REF)) ** C.BACKLOG_EXPONENT)
        res = med * math.exp(rng.gauss(0, C.RES_SIGMA))
        if rng.random() < C.NEVER_FIXED_RATE:
            res *= 4.0
        res = max(0.05, res)
        inc["close_t"] = inc["t"] + res
        heapq.heappush(heap, inc["close_t"])
        inc["backlog"] = backlog
        kept = [reports[0]]
        for r in reports[1:]:                      # follow-ups arrive before the fix, within a few days
            delay = min(rng.expovariate(1.0 / C.DUP_MEAN_DELAY_DAYS), C.DUP_MAX_DELAY_DAYS, res * 0.9)
            r[0] = inc["t"] + max(0.01, delay)
            if r[0] < T_NOW:
                kept.append(r)
        inc["n_reports"] = len(kept)
        for (tc, tx, lg, ch, md, x, y, vg, ur, pl, tp) in kept:
            lat, lon = to_latlon(x, y)
            closed = inc["close_t"] if inc["close_t"] <= T_NOW else None
            complaints.append({
                "t": round(tc, 5), "text": tx, "lang": lg, "channel": ch, "ward": ward_code(inc["ward"]),
                "lat": lat, "lon": lon, "dept": inc["dept"], "issue": inc["issue"], "urgency": ur,
                "incident_urgency": urg, "incident": inc["id"], "planted": inc["planted"], "mods": md,
                "vague": vg, "closed_t": round(closed, 5) if closed is not None else None,
                "place": {"kind": pl["kind"], "en": pl["en"], "ta": pl["ta"], "tg": pl["tg"]}, "tpl": tp,
            })

    complaints.sort(key=lambda c: (c["t"], c["incident"]))
    for k, c in enumerate(complaints):
        c["id"] = "C-%05d" % (10001 + k)
        c["ts"] = iso(c["t"])
        c["week"] = week_of(c["t"])
        c["dow"] = int(c["t"]) % 7
        if c["closed_t"] is not None:
            c["status"] = "resolved"
            c["res_days"] = round(c["closed_t"] - c["t"], 4)
        else:
            c["status"] = "open"
            c["res_days"] = None
        c["age_days"] = round((c["closed_t"] if c["closed_t"] is not None else T_NOW) - c["t"], 4)

    planted = []
    for h in PLANTED_HOTSPOTS + PLANTED_SURGES:
        planted.append({"id": h["id"], "dept": h["dept"], "ward": ward_code(h["ward"]), "center": h["center"],
                        "place": h["place"], "n_incidents": h["n"], "sigma_m": h["sigma"],
                        "kind": "surge" if "week" in h else "persistent", "week": h.get("week")})
    slim_inc = [{"id": i["id"], "t": round(i["t"], 5), "dept": i["dept"], "issue": i["issue"],
                 "ward": ward_code(i["ward"]), "urgency": i["urgency"], "planted": i["planted"],
                 "n_reports": i["n_reports"]} for i in incidents]
    town_places = []
    for w, pl in places.items():
        for p in pl:
            la, lo = to_latlon(p["x"], p["y"])
            town_places.append({"ward": ward_code(w), "kind": p["kind"], "name": p["en"], "name_ta": p["ta"],
                                "name_tg": p["tg"], "lat": la, "lon": lo})
    return {"wards": wards, "places": town_places, "complaints": complaints, "incidents": slim_inc,
            "planted": planted, "now_t": T_NOW, "now_ts": iso(T_NOW)}


CSV_COLS = ["id", "ts", "text", "lang", "channel", "ward", "lat", "lon", "dept", "issue", "urgency", "incident",
            "planted", "status", "res_days"]


def to_csv(complaints):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for c in complaints:
        w.writerow(["" if c.get(k) is None else c.get(k) for k in CSV_COLS])
    return buf.getvalue()


def write_files(out_dir):
    g = generate()
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "complaints.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(to_csv(g["complaints"]))
    with open(os.path.join(out_dir, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": C.SEED, "now": g["now_ts"], "planted": g["planted"], "wards": g["wards"],
                   "n_complaints": len(g["complaints"]), "n_incidents": len(g["incidents"])},
                  f, ensure_ascii=False, indent=1)
    return g


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    g = write_files(os.path.join(here, "data"))
    print("wrote %d complaints / %d incidents to data/" % (len(g["complaints"]), len(g["incidents"])))

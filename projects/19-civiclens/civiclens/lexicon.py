"""Small bilingual concept lexicon: English synonyms, Tamil script and Tanglish -> one concept.

Used to build *concept tokens* so that "குப்பை அள்ளவில்லை", "kuppai edukala" and
"garbage not collected" share vocabulary. Concept tokens feed duplicate detection
(cross-language MinHash), urgency rules, topic discovery and one block of classifier
features. It is deliberately small and hand-written: coverage is a known limit.

Tamil keys are matched as *grapheme prefixes* of a token (longest wins) which acts as a
light stemmer for agglutinated forms: தெருவில் ("in the street") -> தெரு -> street.
"""

# Latin-script tokens (English + Tanglish), exact match after lower-casing and plural strip.
# A value of "" means "drop this token" (filler).
LATIN = {
    # --- roads
    "pothole": "pothole", "potholes": "pothole", "pothol": "pothole", "kuzhi": "pothole", "kuli": "pothole",
    "kuzhigal": "pothole", "pallam": "pit", "trench": "pit", "pit": "pit", "caved": "pit",
    "road": "road", "roads": "road", "salai": "road", "rd": "road", "tar": "road", "damaged": "damage",
    "damage": "damage", "broken": "broken", "udanju": "broken", "udainjiruku": "broken",
    "speed": "speed", "breaker": "breaker", "hump": "speedbreaker",
    "accident": "accident", "accidents": "accident", "vizhunthu": "fallen", "vizhundhu": "fallen",
    "vizhunthuchu": "fallen", "fell": "fallen", "fall": "fallen", "fallen": "fallen", "wheeler": "bike", "wheelers": "bike", "bike": "bike", "riders": "bike", "rider": "bike", "missing": "missing", "open": "open", "falling": "fallen", "vizhum": "fallen",
    # --- sanitation
    "garbage": "garbage", "trash": "garbage", "rubbish": "garbage", "waste": "garbage", "kuppai": "garbage",
    "dustbin": "bin", "bin": "bin", "bins": "bin", "overflowing": "overflow", "overflow": "overflow",
    "collected": "collect", "collect": "collect", "cleared": "collect", "edukala": "notcollected",
    "dumping": "dump", "dump": "dump", "dumped": "dump", "kottraanga": "dump", "kottuvanga": "dump",
    "burnt": "burning", "burning": "burning", "burn": "burning", "erikiraanga": "burning",
    "smoke": "smoke", "pugai": "smoke", "swept": "sweep", "sweeping": "sweep", "toilet": "toilet",
    "dirty": "dirty", "clean": "clean", "cleaned": "clean", "smell": "smell", "stink": "smell",
    "naatram": "smell", "odour": "smell",
    # --- streetlight / electrical
    "streetlight": "streetlight", "streetlights": "streetlight", "lamp": "streetlight", "lamps": "streetlight",
    "light": "light", "lights": "light", "vilakku": "light", "eriyala": "notworking", "glowing": "working",
    "working": "working", "work": "working", "aagala": "not", "odala": "notworking",
    "wire": "wire", "wires": "wire", "kambi": "wire", "live": "live", "current": "current",
    "electric": "electric", "electricity": "current", "eb": "electric", "pole": "pole", "kambam": "pole",
    "hanging": "hanging", "thongitu": "hanging", "thonguthu": "hanging", "leaking": "leak", "leak": "leak",
    "shock": "shock", "tilted": "tilted", "saanju": "tilted", "transformer": "transformer",
    "daytime": "daytime", "day": "day", "pagal": "daytime", "fan": "fan", "fans": "fan",
    # --- water
    "water": "water", "thanni": "water", "tanni": "water", "thanneer": "water", "kudineer": "drinkingwater",
    "drinking": "drinking", "tap": "tap", "pipe": "pipe", "pipeline": "pipe", "burst": "burst",
    "muddy": "muddy", "kalangal": "muddy", "pressure": "pressure", "supply": "supply", "varala": "notcoming",
    "coming": "coming", "wasted": "wasted", "kammi": "low", "low": "low",
    # --- drainage
    "drainage": "drain", "drain": "drain", "drains": "drain", "gutter": "drain", "sewer": "drain",
    "sewage": "sewage", "sakkadai": "sewage", "manhole": "manhole", "moodi": "cover", "cover": "cover",
    "blocked": "block", "block": "block", "clogged": "block", "stagnant": "stagnant", "thengi": "stagnant",
    "mosquito": "mosquito", "mosquitoes": "mosquito", "kosu": "mosquito", "rain": "rain", "mazhai": "rain",
    # --- animals
    "dog": "dog", "dogs": "dog", "naai": "dog", "nai": "dog", "stray": "stray", "bite": "bite", "bit": "bite",
    "bitten": "bite", "kadichiduchu": "bite", "kadichu": "bite", "cow": "cow", "cows": "cow", "cattle": "cow",
    "maadu": "cow", "dead": "dead", "setha": "dead", "carcass": "dead", "menace": "menace", "thollai": "menace",
    "chasing": "chase",
    # --- hostel / campus
    "hostel": "hostel", "mess": "mess", "food": "food", "saapadu": "food", "stale": "stale",
    "bathroom": "bathroom", "bathrooms": "bathroom", "washroom": "bathroom", "washrooms": "bathroom",
    "wifi": "wifi", "internet": "wifi", "room": "room", "warden": "warden",
    # --- other
    "loudspeaker": "loudspeaker", "music": "noise", "noise": "noise", "sound": "noise", "loud": "noise",
    "encroachment": "encroachment", "encroaching": "encroachment", "encroach": "encroachment",
    "footpath": "footpath", "vendors": "vendor", "vendor": "vendor", "tree": "tree", "maram": "tree",
    "branch": "branch", "fogging": "fogging", "dengue": "dengue", "fever": "fever", "banner": "banner",
    "flex": "banner", "hoarding": "banner", "parking": "parking", "parked": "parking",
    # --- modifiers / severity cues
    "school": "school", "children": "children", "child": "children", "kids": "children", "kid": "children",
    "pasanga": "children", "paiyana": "children", "elderly": "elderly", "old": "old", "aged": "elderly",
    "vayasaanavanga": "elderly", "sick": "sick", "danger": "danger", "dangerous": "danger", "risk": "danger",
    "week": "week", "weeks": "week", "vaarama": "week", "days": "days", "naala": "days",
    "night": "night", "dark": "dark",
    # --- places
    "temple": "temple", "kovil": "temple", "bus": "bus", "stand": "stand", "stop": "stop",
    "ration": "ration", "shop": "shop", "kadai": "shop", "tank": "tank", "park": "park", "poonga": "park",
    "hospital": "hospital", "market": "market", "street": "street", "theru": "street", "junction": "junction",
    "community": "community", "hall": "hall", "nagar": "nagar", "cross": "cross",
    # --- fillers dropped from concept tokens
    "sir": "", "madam": "", "please": "", "pls": "", "plss": "", "help": "", "next": "", "hello": "", "kindly": "", "dear": "", "respected": "", "officer": "",
    "the": "", "a": "", "an": "", "is": "", "are": "", "was": "", "were": "", "in": "", "on": "", "at": "",
    "of": "", "for": "", "to": "", "and": "", "near": "", "opposite": "", "behind": "", "from": "", "this": "",
    "that": "", "it": "", "very": "", "our": "", "my": "", "we": "", "there": "", "here": "", "has": "",
    "have": "", "been": "", "be": "", "by": "", "since": "", "today": "", "do": "", "needful": "",
    "take": "", "action": "", "immediately": "", "la": "", "ah": "", "iruku": "", "irukku": "",
    "romba": "", "pannunga": "", "kitta": "", "pakkathula": "", "aaguthu": "", "inga": "", "oru": "",
    "intha": "", "dhaan": "", "area": "", "edunga": "", "seekiram": "", "already": "", "complaint": "",
    "complained": "", "before": "", "pannom": "", "sari": "", "full": "", "fulla": "", "get": "", "got": "",
    "people": "", "also": "", "too": "", "many": "", "much": "", "after": "", "with": "", "about": "",
    "will": "", "may": "", "need": "", "needs": "", "every": "", "all": "", "no": "no", "not": "not",
    "illa": "no", "nothing": "", "problem": "problem", "issue": "problem",
}

# Tamil-script keys, matched as grapheme prefixes (longest first). Values are space separated concepts.
TAMIL = {
    # places and names
    "கோவில்": "temple", "கோயில்": "temple", "பள்ளி": "school", "பேருந்து": "bus", "நிறுத்தம்": "stop",
    "நிலையம்": "stand", "ரேஷன்": "ration", "கடை": "shop", "தொட்டி": "tank", "பூங்கா": "park",
    "மருத்துவமனை": "hospital", "சந்தை": "market", "தெரு": "street", "சந்திப்பு": "junction",
    "சமுதாய": "community", "கூடம்": "hall", "விடுதி": "hostel", "சாலை": "road", "ரோட்": "road", "ரோடு": "road",
    "நகர்": "nagar", "குறுக்கு": "cross", "முருகன்": "murugan", "விநாயகர்": "vinayagar",
    "மாரியம்மன்": "mariamman", "பெருமாள்": "perumal", "காந்தி": "gandhi", "நேரு": "nehru", "அண்ணா": "anna",
    "காமராஜர்": "kamarajar", "பெரியார்": "periyar", "பாரதி": "bharathi", "வள்ளுவர்": "valluvar",
    "கண்ணகி": "kannagi", "காவேரி": "kaveri", "அம்பேத்கர்": "ambedkar", "ராஜாஜி": "rajaji",
    "இந்திரா": "indira", "திருவிக": "thiruvika", "ஏரி": "lake", "தொழிற்பேட்டை": "industrial",
    "புதுப்பாளையம்": "pudhupalayam", "கல்லூரி": "college", "ரயில்வே": "railway", "மேட்டு": "mettu",
    "ஆண்கள்": "boys", "மகளிர்": "girls", "உணவுக்": "mess", "நூலகம்": "library",
    # roads
    "குழி": "pothole", "பள்ளம்": "pit", "பள்ளத்": "pit", "சேத": "damage", "உடை": "broken",
    "வேகத்தடை": "speedbreaker", "விபத்": "accident", "இருசக்கர": "bike", "வாகன": "vehicle", "விழுந்": "fallen",
    # sanitation
    "குப்பை": "garbage", "அள்ளவில்லை": "notcollected", "எடுக்கவில்லை": "notcollected",
    "நிரம்பி": "overflow", "வழிகிறது": "overflow", "கொட்டு": "dump", "எரிக்": "burning", "புகை": "smoke",
    "சுத்தம்": "clean", "கழிப்பறை": "toilet", "துர்நாற்றம்": "smell", "நாற்றம்": "smell",
    # streetlight
    "தெருவிளக்கு": "streetlight", "விளக்கு": "light", "எரியவில்லை": "notworking",
    "வேலை": "", "செய்யவில்லை": "notworking", "எரிகிறது": "burning",
    "பகல்": "daytime", "பகலில்": "daytime", "பகலிலும்": "daytime", "மின்கம்பம்": "electric pole", "மின்கம்பத்": "electric pole", "மின்கம்பி": "electric wire",
    "மின்விசிறி": "fan", "மின்சாரம்": "current", "மின்": "electric", "கம்பி": "wire", "கம்பம்": "pole",
    "அறுந்": "snapped", "தொங்கு": "hanging", "கசி": "leak", "சாய்": "tilted", "இருட்டா": "dark",
    # water
    "குடிநீர்": "drinkingwater", "குடிநீரில்": "drinkingwater", "தண்ணீர்": "water", "நீர்": "water",
    "குழாய்": "pipe", "குழாயில்": "tap", "கலங்கல்": "muddy", "அழுத்தம்": "pressure", "வீண்": "wasted",
    "வரவில்லை": "notcoming",
    # drainage
    "சாக்கடை": "sewage", "கழிவுநீர்": "sewage", "கால்வாய்": "drain", "அடைப்பு": "block", "பாதாள": "manhole",
    "மூடி": "cover", "மழைநீர்": "rain water", "தேங்கி": "stagnant", "கொசு": "mosquito",
    # animals
    "நாய்": "dog", "கடித்": "bite", "மாடு": "cow", "இறந்த": "dead", "தொல்லை": "menace",
    # hostel
    "குளியலறை": "bathroom", "உணவு": "food", "தரம்": "quality", "மோசம்": "poor", "வைஃபை": "wifi", "அறை": "room",
    # other
    "ஒலிபெருக்கி": "loudspeaker", "சத்தம்": "noise", "நடைபாதை": "footpath", "ஆக்கிரமிப்பு": "encroachment",
    "மரம்": "tree", "மரத்": "tree", "கிளை": "branch", "மருந்து": "fogging", "பேனர்": "banner",
    "அனுமதி": "permission", "நிறுத்து": "parking", "டெங்கு": "dengue", "காய்ச்சல்": "fever",
    # modifiers
    "குழந்தை": "children", "மாணவ": "children", "வயதான": "elderly", "ஆபத்": "danger", "இரவு": "night", "இரவில்": "night",
    "வார": "week", "நாட்க": "days", "நாள்": "days", "இல்லை": "no",
    # fillers
    "அருகில்": "", "அருகே": "", "எதிரில்": "", "பின்புறம்": "", "உள்ளது": "", "உள்ளன": "",
    "இருக்கிறது": "", "மிகவும்": "", "ஐயா": "", "தயவுசெய்து": "", "உடனடியாக": "", "நடவடிக்கை": "",
    "எடுக்கவும்": "", "பகுதியில்": "", "இந்த": "", "இங்கு": "", "பலமுறை": "", "புகார்": "",
    "அளித்தும்": "", "பெரிய": "", "முழுவதும்": "", "நேற்று": "", "செல்லும்": "", "வழியில்": "",
    "செல்கிறார்கள்": "",
}


LATIN.update({
    "two": "", "three": "", "one": "", "bad": "", "yaarum": "", "nobody": "", "aagi": "", "vandi": "vehicle",
    "van": "vehicle", "poraanga": "", "pannala": "", "vazhi": "", "aachu": "", "use": "", "mudiyala": "",
    "adikuthu": "", "periya": "", "nethu": "", "come": "coming", "boy": "children", "paakala": "", "vandhu": "",
    "varave": "", "suffering": "", "perukku": "", "vandhuruku": "", "neraya": "", "lot": "", "lots": "",
    "nikuthu": "stagnant", "anytime": "", "last": "", "varuthu": "coming", "struggling": "", "happened": "",
    "big": "", "huge": "", "fill": "", "them": "", "during": "", "time": "", "fast": "", "case": "",
    "off": "notworking", "responding": "", "main": "", "thanga": "", "lying": "", "odi": "", "kooda": "",
    "eriyuthu": "burning", "logging": "stagnant", "apram": "", "yet": "", "pinnadi": "", "regarding": "",
    "taken": "", "poyiruku": "", "yesterday": "", "catch": "", "repaired": "", "aagiduchu": "", "kashta": "",
    "padraanga": "", "going": "", "poga": "", "rendu": "", "pola": "", "being": "", "everywhere": "",
    "late": "", "still": "", "served": "", "pottu": "", "panniruka": "", "cannot": "", "someone": "",
    "vachirukanga": "", "pannuranga": "", "podunga": "", "ellam": "", "poguthu": "", "mixing": "mix",
    "entering": "", "line": "", "suthuthu": "roaming", "unbearable": "", "corporation": "", "surface": "",
    "relaying": "relay", "washed": "", "away": "", "visible": "", "solved": "", "check": "", "flowing": "",
    "deep": "", "any": "", "until": "", "till": "", "kita": "", "cleaed": "clean", "breathe": "", "power": "",
})

TAMIL.update({
    "வீணா": "wasted", "கலங்கலா": "muddy", "வருகிறது": "coming", "விழும்": "fallen", "கலக்": "mix",
    "சுற்றி": "roaming", "பிரச்சனை": "problem", "அதிகம்": "", "யாரும்": "", "கவனிக்கவில்லை": "",
    "கிடக்கிறது": "", "நடந்தது": "", "பலருக்கு": "", "வந்துள்ளது": "", "தாங்க": "", "முடியவில்லை": "",
    "உள்ள": "", "சரி": "", "இரண்டு": "", "அமைக்க": "", "வேண்டும்": "", "வேகமாக": "", "செல்கின்றன": "",
    "ஒரு": "", "நிலையில்": "", "சிரமப்படுகிறார்கள்": "", "திரிகின்றன": "", "மேலும்": "", "புதிய": "new",
    "பழைய": "old", "வீசுகிறது": "", "பொது": "public", "வைக்கப்பட்டுள்ளது": "", "தவறாக": "wrong",
})

# Tanglish stems matched as prefixes (>= 4 letters) when no exact LATIN entry exists.
TANGLISH_STEMS = {
    "kuppai": "garbage", "thanni": "water", "sakkadai": "sewage", "theru": "street", "kovil": "temple",
    "vilakk": "light", "kuzhi": "pothole", "drainag": "drain", "overflo": "overflow", "potho": "pothole",
    "garbag": "garbage", "streetl": "streetlight", "accid": "accident", "kadich": "bite", "vizhu": "fallen",
    "mosquit": "mosquito", "encroach": "encroachment", "loudspeak": "loudspeaker", "manhol": "manhole",
    "electri": "electric", "hostel": "hostel", "bathroo": "bathroom", "pipelin": "pipe",
}

# Concept bigrams merged into a single concept after mapping.
PHRASES = {
    ("street", "light"): "streetlight", ("drinking", "water"): "drinkingwater", ("bus", "stand"): "busstand",
    ("bus", "stop"): "busstop", ("speed", "breaker"): "speedbreaker", ("not", "working"): "notworking",
    ("no", "working"): "notworking", ("working", "not"): "notworking", ("not", "collect"): "notcollected",
    ("no", "water"): "nowater", ("water", "no"): "nowater", ("water", "notcoming"): "nowater",
    ("electric", "pole"): "pole", ("electric", "wire"): "wire", ("ration", "shop"): "rationshop",
    ("water", "tank"): "watertank", ("community", "hall"): "communityhall", ("street", "dog"): "dog",
    ("stray", "dog"): "dog", ("rain", "water"): "rainwater", ("drain", "water"): "sewage",
    ("not", "coming"): "notcoming",
}

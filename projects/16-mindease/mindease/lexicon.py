"""Hand-built valence & emotion lexicon for student journal language (English + Tanglish).

Valence is on a -4..+4 scale (VADER convention). Each entry may carry one emotion tag:
joy, calm, sadness, anxiety, anger, tiredness, loneliness, self_doubt.
Tanglish = Tamil words written in Latin script, as students actually type them.
The lexicon is ours (written for this project); the -4..+4 convention follows VADER.
"""

# word  valence  [emotion]
_WORDS = """
happy 2.7 joy
happier 2.6 joy
happiest 3.0 joy
happiness 2.6 joy
glad 2.0 joy
joy 2.8 joy
joyful 2.8 joy
excited 2.4 joy
exciting 2.2 joy
fun 2.2 joy
enjoy 2.0 joy
enjoyed 2.2 joy
enjoying 2.1 joy
enjoyable 2.0 joy
love 2.8 joy
loved 2.8 joy
lovely 2.5 joy
great 2.8 joy
good 1.9 joy
nice 1.8 joy
awesome 3.0 joy
amazing 3.0 joy
wonderful 3.0 joy
fantastic 3.0 joy
brilliant 2.8 joy
excellent 3.0 joy
best 2.8 joy
better 1.9
well 1.1
fine 0.8
okay 0.5
ok 0.5
alright 0.6
special 1.7 joy
calm 1.9 calm
calmer 1.9 calm
peaceful 2.2 calm
peace 2.0 calm
relaxed 2.1 calm
relaxing 2.0 calm
relax 1.5 calm
relief 2.0 calm
relieved 2.2 calm
refreshed 2.1 calm
rested 1.8 calm
proud 2.3 joy
confident 2.2 joy
motivated 2.0 joy
productive 2.0 joy
focused 1.6
accomplished 2.2 joy
achieved 2.0 joy
progress 1.5
improved 1.8
improving 1.6
hopeful 2.2 joy
hope 1.4
hopefully 1.2
optimistic 2.2 joy
grateful 2.6 joy
thankful 2.4 joy
thanks 1.5 joy
thank 1.5 joy
blessed 2.4 joy
smile 2.0 joy
smiled 2.0 joy
smiling 2.0 joy
laugh 2.1 joy
laughed 2.2 joy
laughing 2.0 joy
cheerful 2.5 joy
energetic 2.0 joy
energised 2.0 joy
energized 2.0 joy
supported 2.0
supportive 2.0
helped 1.6
helpful 1.8
safe 1.6 calm
comfortable 1.6 calm
cool 1.3
yay 2.4 joy
worth 1.4
easy 1.4
easier 1.4
success 2.3 joy
successful 2.3 joy
passed 2.0 joy
win 2.3 joy
won 2.2 joy
interesting 1.7
interested 1.5
beautiful 2.6 joy
kind 1.8
friendly 1.8
satisfied 2.0 joy
positive 2.0
strong 1.5
stronger 1.6
ready 1.1
prepared 1.3
understood 1.3
solved 1.6
delicious 2.3 joy
tasty 2.0 joy
celebrated 2.4 joy
celebrate 2.2 joy
celebrations 2.2 joy
celebration 2.2 joy
holiday 1.8 joy
holidays 1.8 joy
selected 1.8 joy
wow 1.5 joy
sad -2.1 sadness
sadness -2.2 sadness
unhappy -2.2 sadness
upset -2.0 sadness
down -0.8
low -1.0
depressed -2.8 sadness
depressing -2.5 sadness
miserable -2.9 sadness
cry -2.0 sadness
cried -2.1 sadness
crying -2.2 sadness
tears -1.8 sadness
hurt -2.1 sadness
hurts -2.1 sadness
pain -2.0 sadness
painful -2.2 sadness
heartbroken -2.9 sadness
empty -1.9 sadness
numb -1.9 sadness
disappointed -2.1 sadness
disappointing -2.1 sadness
disappointment -2.1 sadness
miss -1.2 loneliness
lonely -2.3 loneliness
loneliness -2.3 loneliness
alone -1.6 loneliness
isolated -2.1 loneliness
ignored -1.8 loneliness
abandoned -2.4 loneliness
homesick -1.8 loneliness
stress -1.9 anxiety
stressed -2.1 anxiety
stressful -2.1 anxiety
tension -1.9 anxiety
tense -1.8 anxiety
pressure -1.6 anxiety
anxious -2.2 anxiety
anxiety -2.3 anxiety
nervous -1.6 anxiety
worried -1.9 anxiety
worry -1.7 anxiety
worrying -1.9 anxiety
worries -1.6 anxiety
scared -2.1 anxiety
afraid -2.0 anxiety
fear -2.1 anxiety
panic -2.6 anxiety
panicking -2.6 anxiety
panicked -2.5 anxiety
overwhelmed -2.4 anxiety
overwhelming -2.2 anxiety
restless -1.6 anxiety
uneasy -1.6 anxiety
overthinking -1.7 anxiety
frightened -2.2 anxiety
terrified -2.9 anxiety
dread -2.3 anxiety
dreading -2.3 anxiety
shaking -1.6 anxiety
tired -1.5 tiredness
exhausted -2.2 tiredness
exhausting -2.0 tiredness
drained -2.1 tiredness
sleepy -0.9 tiredness
fatigue -1.8 tiredness
burnout -2.4 tiredness
insomnia -2.0 tiredness
sleepless -2.0 tiredness
weak -1.4
sick -1.8
ill -1.6
headache -1.6
angry -2.3 anger
anger -2.3 anger
annoyed -1.7 anger
annoying -1.8 anger
irritated -1.8 anger
irritating -1.8 anger
frustrated -2.0 anger
frustrating -2.0 anger
furious -3.0 anger
mad -1.8 anger
hate -2.7 anger
hated -2.6 anger
disgusted -2.4 anger
jealous -1.6
bored -1.3
boring -1.4
bad -2.5
worse -2.1
worst -3.1
terrible -3.0
horrible -3.0
awful -3.0
poor -1.6
fail -2.3 self_doubt
failed -2.4 self_doubt
failing -2.3 self_doubt
failure -2.6 self_doubt
mistake -1.5 self_doubt
mistakes -1.5 self_doubt
wrong -1.6
problem -1.3
problems -1.4
difficult -1.4
hard -0.8
struggle -1.8
struggling -2.0
confused -1.3
confusing -1.3
lost -1.4
stuck -1.6
behind -1.0 self_doubt
guilty -2.0 self_doubt
guilt -2.0 self_doubt
ashamed -2.3 self_doubt
shame -2.2 self_doubt
embarrassed -1.8 self_doubt
regret -1.9 self_doubt
useless -2.4 self_doubt
worthless -2.9 self_doubt
stupid -2.0 self_doubt
dumb -1.8 self_doubt
hopeless -3.0 sadness
helpless -2.5 sadness
pointless -2.3 sadness
broken -2.3 sadness
lazy -1.3 self_doubt
unmotivated -1.8 tiredness
demotivated -1.9 tiredness
procrastinating -1.3
procrastinated -1.3
distracted -1.2
nightmare -2.3 anxiety
nightmares -2.3 anxiety
scary -2.0 anxiety
sucks -1.9
suck -1.9
ugh -1.4 anger
meh -0.8
sigh -0.8
argh -1.4 anger
fight -1.8 anger
fought -1.8 anger
argument -1.7 anger
shouted -1.8 anger
scolded -1.8 sadness
yelled -1.9 anger
rejected -2.3 sadness
ruined -2.4
unfair -2.0 anger
burden -2.0 sadness
trapped -2.4 anxiety
suffocating -2.6 anxiety
cancelled -1.0
late -0.6
die -2.8 sadness
dying -2.4
dead -2.4
death -2.8 sadness
killing -2.0
suicide -3.4 sadness
suicidal -3.4 sadness
semma 2.5 joy
jolly 2.2 joy
santhosham 2.6 joy
santhoshama 2.6 joy
sandhosham 2.6 joy
nalla 1.8 joy
nallaa 1.8 joy
nallathu 1.8 joy
super 2.4 joy
mass 2.0 joy
gethu 2.2 joy
kalakkal 2.4 joy
sirippu 2.0 joy
siripu 2.0 joy
nimmathi 2.2 calm
nimmadhi 2.2 calm
mokka -1.8
kashtam -2.0 anxiety
kastam -2.0 anxiety
kavalai -2.0 anxiety
bayam -2.0 anxiety
bayama -2.0 anxiety
bayamaa -2.0 anxiety
kadupu -1.9 anger
kaduppu -1.9 anger
sogam -2.2 sadness
sokam -2.2 sadness
azhugai -2.1 sadness
azhuthen -2.1 sadness
aluthen -2.1 sadness
mudiyala -2.0 tiredness
mudiyale -2.0 tiredness
torture -2.4
waste -1.8
kevalam -2.4
loosu -1.2
bore -1.2
thanimai -2.1 loneliness
thaniya -1.4 loneliness
pidikkala -1.6
pidikala -1.6
kozhappam -1.4
"""

# phrase | valence | emotion (optional). Matched greedily (longest first) on tokens.
_PHRASES = """
burnt out|-2.4|tiredness
burned out|-2.4|tiredness
worn out|-2.0|tiredness
stressed out|-2.3|anxiety
freaking out|-2.3|anxiety
freaked out|-2.2|anxiety
fed up|-2.0|anger
messed up|-1.9|
left out|-2.0|loneliness
feeling down|-2.0|sadness
feel down|-2.0|sadness
felt down|-2.0|sadness
feeling low|-2.0|sadness
feel low|-2.0|sadness
felt low|-2.0|sadness
can't sleep|-2.0|tiredness
couldn't sleep|-2.0|tiredness
cannot sleep|-2.0|tiredness
didn't sleep|-1.8|tiredness
no sleep|-1.8|tiredness
barely slept|-1.9|tiredness
hardly slept|-1.9|tiredness
slept badly|-1.9|tiredness
slept well|2.0|calm
can't focus|-1.8|
couldn't focus|-1.8|
can't concentrate|-1.8|
couldn't concentrate|-1.8|
can't stop overthinking|-2.2|anxiety
can't wait|1.8|joy
looking forward|2.0|joy
worth it|1.8|joy
vera level|2.8|joy
thookam varala|-2.0|tiredness
thookame varala|-2.0|tiredness
thukkam varala|-2.0|tiredness
on edge|-1.8|anxiety
lost interest|-2.0|sadness
no energy|-1.9|tiredness
at peace|2.0|calm
gave up|-1.8|sadness
give up|-1.6|sadness
giving up|-1.8|sadness
let down|-1.9|self_doubt
let myself down|-2.2|self_doubt
not good enough|-2.3|self_doubt
broke down|-2.3|sadness
cheered up|2.0|joy
calmed down|1.6|calm
in tears|-2.2|sadness
panic attack|-2.8|anxiety
racing thoughts|-1.9|anxiety
mind racing|-1.8|anxiety
keeps racing|-1.6|anxiety
killed it|2.3|joy
nailed it|2.4|joy
aced it|2.4|joy
all-nighter|-1.0|tiredness
never felt better|3.0|joy
couldn't be better|3.0|joy
nothing special|-0.2|
at least|0.3|
made sense|1.4|
dead tired|-2.0|tiredness
to die for|2.0|joy
dying to|0.5|
too much|-1.2|anxiety
so so|-0.3|
"""

# Words that flip the valence of what follows (within config.NEGATION_WINDOW tokens).
NEGATORS = {
    "not", "no", "never", "nothing", "nobody", "none", "neither", "nor", "nowhere",
    "cannot", "can't", "don't", "doesn't", "didn't", "isn't", "wasn't", "aren't",
    "weren't", "won't", "wouldn't", "couldn't", "shouldn't", "haven't", "hasn't",
    "hadn't", "ain't", "without", "hardly", "barely", "rarely", "seldom",
}
# Tamil negation comes *after* the word: "nalla illa" = "not good".
POST_NEGATORS = {"illa", "illai", "ille", "illae", "venam", "vendam", "illama"}

INTENSIFIERS = {
    "very", "really", "so", "extremely", "totally", "completely", "absolutely",
    "incredibly", "super", "too", "truly", "deeply", "highly", "seriously", "awfully",
    "terribly", "freaking", "damn", "insanely", "utterly", "quite", "such",
    "romba", "rombave", "rombo", "semma", "bayangara", "bayangaram", "mega",
}
DIMINISHERS = {"slightly", "somewhat", "kinda", "kindof", "bit", "little", "partly",
               "konjam", "konjo", "mildly", "marginally"}
# Multi-word modifiers, matched like phrases.
MODIFIER_PHRASES = {
    ("a", "bit"): "dim", ("a", "little"): "dim", ("kind", "of"): "dim",
    ("sort", "of"): "dim", ("little", "bit"): "dim", ("so", "much"): "int",
    ("very", "much"): "int",
}
# Words that carry valence alone but act as intensifiers before another valence word
# ("semma fun" = very fun, "semma tension" = huge tension, "super tired").
DUAL_INTENSIFIERS = {"semma", "super", "too much"}

# Contrast conjunctions: the clause after them dominates.
CONTRAST = {"but", "however", "though", "although", "yet"}

EMOJI = {
    "\U0001F60A": (2.2, "joy"), "\U0001F604": (2.5, "joy"), "\U0001F600": (2.3, "joy"),
    "\U0001F603": (2.3, "joy"), "\U0001F601": (2.3, "joy"), "\U0001F642": (1.3, "joy"),
    "\U0001F60D": (2.8, "joy"), "\U0001F970": (2.8, "joy"), "❤": (2.5, "joy"),
    "\U0001F496": (2.5, "joy"), "\U0001F495": (2.4, "joy"), "\U0001F44D": (1.6, "joy"),
    "\U0001F389": (2.5, "joy"), "\U0001F973": (2.6, "joy"), "\U0001F60C": (1.8, "calm"),
    "\U0001F64F": (1.2, "calm"), "✨": (1.2, "joy"), "\U0001F4AA": (1.8, "joy"),
    "\U0001F602": (1.8, "joy"), "\U0001F923": (1.8, "joy"), "\U0001F917": (1.9, "joy"),
    "\U0001F622": (-2.2, "sadness"), "\U0001F62D": (-2.6, "sadness"),
    "\U0001F61E": (-2.2, "sadness"), "\U0001F614": (-2.0, "sadness"),
    "\U0001F61F": (-1.9, "anxiety"), "\U0001F629": (-2.2, "tiredness"),
    "\U0001F62B": (-2.2, "tiredness"), "\U0001F630": (-2.4, "anxiety"),
    "\U0001F628": (-2.2, "anxiety"), "\U0001F631": (-2.2, "anxiety"),
    "\U0001F621": (-2.6, "anger"), "\U0001F620": (-2.3, "anger"),
    "\U0001F494": (-2.6, "sadness"), "\U0001F634": (-0.8, "tiredness"),
    "\U0001F641": (-1.6, "sadness"), "☹": (-1.8, "sadness"),
    "\U0001F625": (-1.9, "sadness"), "\U0001F613": (-1.7, "anxiety"),
    "\U0001F623": (-1.9, "anxiety"), "\U0001F616": (-2.0, "sadness"),
    "\U0001F62A": (-1.2, "tiredness"), "\U0001F611": (-0.8, None),
    "\U0001F610": (-0.3, None), "\U0001F97A": (-1.2, "sadness"),
    "\U0001F624": (-1.8, "anger"),
}
EMOTICONS = {
    ":)": (1.8, "joy"), ":-)": (1.8, "joy"), ":d": (2.3, "joy"), ":-d": (2.3, "joy"),
    "(:": (1.8, "joy"), ":(": (-1.9, "sadness"), ":-(": (-1.9, "sadness"),
    ":'(": (-2.2, "sadness"), "<3": (2.2, "joy"), ":/": (-0.9, None),
    ":|": (-0.3, None), "</3": (-2.4, "sadness"),
}

# Common spelling variants students type -> canonical token.
NORMALISE = {
    "cant": "can't", "dont": "don't", "didnt": "didn't", "couldnt": "couldn't",
    "wont": "won't", "isnt": "isn't", "wasnt": "wasn't", "arent": "aren't",
    "doesnt": "doesn't", "wouldnt": "wouldn't", "shouldnt": "shouldn't",
    "havent": "haven't", "hasnt": "hasn't", "im": "i'm", "ive": "i've", "u": "you",
    "plz": "please", "pls": "please", "gud": "good", "happyy": "happy", "sooo": "so",
    "soo": "so", "veryy": "very", "tensed": "tension", "tenshun": "tension",
    "stresss": "stress", "tiredd": "tired", "rmba": "romba", "semmaa": "semma",
    "jollyah": "jolly", "illai": "illa", "ille": "illa",
}


def _parse_words(text):
    out = {}
    for line in text.strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        word, val = parts[0], parts[1]
        out[word] = (float(val), parts[2] if len(parts) > 2 else None)
    return out


def _parse_phrases(text):
    out = {}
    for line in text.strip().splitlines():
        phrase, val, emo = (line.split("|") + [""])[:3]
        out[tuple(phrase.split())] = (float(val), emo or None)
    return out


WORDS = _parse_words(_WORDS)
PHRASES = _parse_phrases(_PHRASES)
TANGLISH = {
    "semma", "jolly", "santhosham", "santhoshama", "sandhosham", "nalla", "nallaa",
    "nallathu", "mass", "gethu", "kalakkal", "sirippu", "siripu", "nimmathi",
    "nimmadhi", "mokka", "kashtam", "kastam", "kavalai", "bayam", "bayama", "bayamaa",
    "kadupu", "kaduppu", "sogam", "sokam", "azhugai", "azhuthen", "aluthen", "mudiyala",
    "mudiyale", "kevalam", "loosu", "thanimai", "thaniya", "pidikkala", "pidikala",
    "kozhappam", "romba", "rombave", "rombo", "konjam", "konjo", "bayangara",
    "bayangaram", "illa", "illai", "ille", "illae", "venam", "vendam", "illama",
    "vera level", "thookam varala", "thookame varala", "thukkam varala",
}
EMOTION_LABELS = {
    "joy": "joy", "calm": "calm", "sadness": "sadness", "anxiety": "worry / stress",
    "anger": "frustration", "tiredness": "tiredness", "loneliness": "loneliness",
    "self_doubt": "self-doubt",
}

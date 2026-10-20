"""Hand-labelled evaluation sets, written by the MindEase team.

Protocol (so the reported numbers mean something):
* SENTIMENT_DEV (30 sentences) was used while building the lexicon and rules.
* SENTIMENT_HELDOUT (30 sentences) was written at the same time, *before* the analyser
  existed, and was never used for tuning. REPORT.md quotes the held-out figure as the
  headline. Both sets were labelled by one annotator (the author), so they are small and
  not independent; treat the numbers as indicative only.
* SAFETY_HELDOUT was also written before the phrase patterns. The first-pass result on it
  is the honest estimate; any phrasings it exposed as misses were added to the pattern
  list afterwards (see REPORT.md), so a re-run on this set is optimistic.

Labels: "pos", "neg", "neu" - the overall feeling of the entry as a whole.
"""

SENTIMENT_DEV = [
    ("Had a really good day, the lab finally worked!", "pos"),
    ("I am not happy with my marks at all.", "neg"),
    ("The test was not bad, better than I expected.", "pos"),
    ("Feeling so stressed about tomorrow's exam.", "neg"),
    ("Went to class, then the library, then home.", "neu"),
    ("Semma fun at the hostel day celebrations \U0001F604", "pos"),
    ("Romba tension, nothing is going in my head.", "neg"),
    ("I couldn't sleep last night and I feel exhausted.", "neg"),
    ("Mess food was okay today.", "neu"),
    ("My roommate made me laugh so much today.", "pos"),
    ("Not feeling anxious anymore after talking to my mentor.", "pos"),
    ("Everything feels too much right now.", "neg"),
    ("I have a viva on Monday.", "neu"),
    ("I was nervous before the presentation but it went really well.", "pos"),
    ("I was looking forward to the trip but it got cancelled and I'm upset.", "neg"),
    ("Kashtam ah iruku, can't focus on anything.", "neg"),
    ("Slept well and woke up refreshed.", "pos"),
    ("Nobody replied to my messages, feeling lonely.", "neg"),
    ("Today was fine, nothing special.", "neu"),
    ("Got my results, I passed all subjects! \U0001F389", "pos"),
    ("Felt numb and empty the whole day.", "neg"),
    ("The bus was late again.", "neu"),
    ("Practised the breathing exercise and felt calmer.", "pos"),
    ("I hate how behind I am in maths.", "neg"),
    ("Nalla illa, today was a waste.", "neg"),
    ("Not too bad, managed to finish the assignment.", "pos"),
    ("Attended two lectures and submitted the record notebook.", "neu"),
    ("Feeling grateful for my friends who checked on me ❤️", "pos"),
    ("Mokka day, so bored in class.", "neg"),
    ("Had dosa for dinner and called home.", "neu"),
]

SENTIMENT_HELDOUT = [
    ("Honestly I feel proud of how much I studied today.", "pos"),
    ("My chest feels tight whenever I think about the results.", "neg"),
    ("It wasn't a great day, I just stayed in bed.", "neg"),
    ("The seminar was interesting and the speaker was kind.", "pos"),
    ("Just a regular Tuesday with labs till four.", "neu"),
    ("Exam went okay, not amazing, not terrible.", "neu"),
    ("I miss home so much, Amma's food and my dog.", "neg"),
    ("Jolly ah irundhuchu, we played cricket in the evening.", "pos"),
    ("Bayama iruku about the placement interview tomorrow \U0001F630", "neg"),
    ("I keep comparing myself with others and feel useless.", "neg"),
    ("Finally finished the project, such a relief!", "pos"),
    ("Physics class was cancelled so I went to the library.", "neu"),
    ("Didn't enjoy the fest this year, felt left out.", "neg"),
    ("Woke up early, did yoga and felt energetic.", "pos"),
    ("I am not sure what I want to do after graduation.", "neu"),
    ("Everyone shouted at me at home today \U0001F622", "neg"),
    ("Studied with my friends, it was actually fun.", "pos"),
    ("My hands were shaking during the lab exam.", "neg"),
    ("No stress today, just relaxed with music.", "pos"),
    ("Submitted the assignment two minutes before the deadline.", "neu"),
    ("I'm so tired of trying and failing.", "neg"),
    ("Super happy, got selected for the hackathon team!", "pos"),
    ("Konjam worried but mostly okay.", "neu"),
    ("Can't stop overthinking about what my friends said.", "neg"),
    ("The new timetable starts next week.", "neu"),
    ("Thanks to my senior's notes, the topic finally made sense.", "pos"),
    ("Feeling low and I don't know why.", "neg"),
    ("Played badminton for an hour, feeling good \U0001F60A", "pos"),
    ("My parents keep asking about marks and it's exhausting.", "neg"),
    ("Ate lunch in the canteen and came back to the hostel.", "neu"),
]

# Written AFTER the lexicon was frozen, deliberately using vocabulary and idioms the
# lexicon author had not targeted (the held-out set above was written by the same person
# just before the lexicon, so some of its words probably leaked into the lexicon).
# Measured once; never tuned on. This is our most pessimistic, most honest estimate.
SENTIMENT_FRESH = [
    ("Woke up with a heavy heart today.", "neg"),
    ("Ugh, another surprise test, just my luck.", "neg"),
    ("Spent the evening sketching, it felt like old times.", "pos"),
    ("My project guide appreciated my work in front of everyone.", "pos"),
    ("Can't believe how quickly the semester is going.", "neu"),
    ("I'm drowning in assignments.", "neg"),
    ("Hostel wifi is down again, so annoying.", "neg"),
    ("Got a call from my best friend after months, made my day.", "pos"),
    ("Not in the mood to talk to anyone today.", "neg"),
    ("Mom made my favourite payasam, feeling loved.", "pos"),
    ("Everything is going wrong this week.", "neg"),
    ("I was worried for nothing, the viva was easy.", "pos"),
    ("Had a long chat with my roommate about life.", "neu"),
    ("Lab record submission tomorrow, haven't even started.", "neg"),
    ("I feel lighter after crying it out.", "pos"),
    ("The weather is pleasant and the campus looks green.", "pos"),
    ("Missed the morning bus and reached late for the test.", "neg"),
    ("Meeting the new club members was nice.", "pos"),
    ("Kept to my study timetable today, small win.", "pos"),
    ("Routine day, nothing much to say.", "neu"),
]

# Concerning-language detection. True = the support screen SHOULD appear.
SAFETY_HELDOUT = [
    # self-harm / death-wish language
    ("I just want to die, I can't do this anymore.", True),
    ("Sometimes I think about killing myself.", True),
    ("I've been thinking of hurting myself again.", True),
    ("Everyone would be better off without me.", True),
    ("I don't want to live like this anymore.", True),
    ("I wish I could go to sleep and never wake up.", True),
    ("I cut myself last night.", True),
    ("Thinking about ending my life.", True),
    ("Saaganum pola iruku.", True),
    ("What's the point of living.", True),
    ("I might as well end it all.", True),
    ("I feel like disappearing forever.", True),
    ("Vaazhave pidikkala, everything is too much.", True),
    ("kms honestly", True),
    # hopelessness language
    ("Nothing will ever get better for me.", True),
    ("I feel completely hopeless about everything.", True),
    ("I'm just a burden to my family.", True),
    ("There's no way out of this.", True),
    ("I can't take it anymore.", True),
    ("I'm worthless and nobody would even notice if I was gone.", True),
    ("Ellam mudinjiduchu, no hope left.", True),
    ("I've given up on everything.", True),
    ("I can't go on like this.", True),
    ("Life feels pointless lately.", True),
    # figurative / everyday language that should NOT trigger
    ("This exam is killing me \U0001F629", False),
    ("I'm dead tired after the lab.", False),
    ("I'd kill for a coffee right now.", False),
    ("I nailed the presentation, totally killed it!", False),
    ("My phone died during the call.", False),
    ("I'm dying to see the results.", False),
    ("Feeling stressed but I'll manage.", False),
    ("I was so embarrassed I wanted to hide.", False),
    ("I hurt my knee playing football.", False),
    ("We watched a movie about a suicide prevention volunteer.", False),
    ("The cutoff marks for the course are too high.", False),
    ("I feel low today but tomorrow is a new day.", False),
    ("My sister said the movie was to die for.", False),
    ("I give up on this maths problem, will ask the teacher.", False),
    ("There's no point in studying chapter 5, it's not in the syllabus.", False),
    ("I'm tired of the mess food.", False),
    ("Hopefully everything gets better after exams.", False),
    ("I'm not hopeless, just tired.", False),
    ("Burden of assignments is too much this week.", False),
    ("Bored to death in the lecture.", False),
    ("I would never hurt anyone.", False),
    ("Can't wait for the holidays!", False),
]

# Written AFTER the safety patterns were frozen, deliberately using indirect phrasings the
# pattern author had not targeted. Measured once; the honest, pessimistic estimate.
SAFETY_FRESH = [
    ("I keep thinking everyone's life would be easier if I wasn't around.", True),
    ("I've been looking up ways to die.", True),
    ("I don't see a future for myself.", True),
    ("Sometimes I want to sleep forever.", True),
    ("I'm tired of being alive.", True),
    ("I wrote a goodbye letter to my parents.", True),
    ("Nothing matters anymore.", True),
    ("I hate myself so much I want to disappear.", True),
    ("I can't see any way this gets better.", True),
    ("My life is a waste, I should just end it.", True),
    ("I took extra sleeping pills to stop the thoughts.", True),
    ("Romba kashtama iruku, vaazhkaiye veruthu pochu.", True),
    ("I died laughing at the comedy show.", False),
    ("The traffic was murder today.", False),
    ("This assignment is the death of me lol.", False),
    ("My laptop battery is dying.", False),
    ("I feel hopeless at chess but it's fun.", False),
    ("I could sleep forever after this exam week.", False),
    ("My friend helped me when I felt low.", False),
    ("There's no point arguing with my brother.", False),
]

# Written after SAFETY_FRESH exposed that fixed phrases do not generalise, and BEFORE the
# co-occurrence layer (safety._cooccurrence) was implemented. Measured once on that layer.
SAFETY_CHECK3 = [
    ("I wish I could just stop existing.", True),
    ("Honestly it would be easier for everyone if I died.", True),
    ("I've started giving away my things to friends.", True),
    ("I don't think I can keep living like this.", True),
    ("I feel like I'm drowning and there's no way I'll get through this.", True),
    ("What if I just never came back from the terrace.", True),
    ("I want everything to stop, permanently.", True),
    ("I'm done with life.", True),
    ("Life has no meaning for me anymore.", True),
    ("I wish I wasn't born.", True),
    ("I'm done with this semester, so ready for holidays!", False),
    ("I wish I could stop procrastinating.", False),
    ("Living in the hostel is fun.", False),
    ("My grandfather died last year and I still miss him.", False),
    ("I want to stop eating junk food.", False),
    ("It would be easier if the exam were postponed.", False),
    ("I want to disappear into a good book this weekend.", False),
    ("The movie's ending made me cry.", False),
    ("I never want to see that question paper again.", False),
    ("I'm so done with group projects lol.", False),
]

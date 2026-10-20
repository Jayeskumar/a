/* SchemeSetu front-end - vanilla JS, no external libraries, works offline. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ i18n
  var I18N = {
    en: {
      tagline: 'Every rural family, matched to the welfare schemes they deserve',
      mode_family: 'Family', mode_worker: 'Field worker', read_aloud: 'Read aloud',
      tab_find: 'Find my schemes', tab_search: 'Search', tab_check: 'Documents & tracker',
      tab_village: 'Village dashboard', tab_about: 'How it works',
      demo_title: 'Load demo family', demo_hint: 'One tap answers the smart questionnaire for a sample family.',
      question_n: 'Question {n}', open_n: '{n} schemes still open', yes: 'Yes', no: 'No',
      skip: "Don't know / skip", back: 'Back', restart: 'Start over', why_q: 'Why this question?',
      also_considered: 'Also considered', done_title: 'All schemes checked',
      done_body: 'questions answered — the full form has {full} fields',
      done_skipped: '{n} skipped — those schemes stay "possibly eligible".',
      go_docs: 'See documents', review: 'Change last answer',
      your_answers: 'Your answers', inferred: 'inferred', skipped: 'skipped', answers_n: '{n} answered',
      no_answers: 'No answers yet. Answer the question above or load a demo family.',
      save_family: 'Save this family', register_family: 'Register household', saved_as: 'Saved as {name}',
      save_changes: 'Save answers', unsaved: 'answers changed since saving',
      kpi_eligible: 'Eligible schemes', kpi_possibly: 'Possibly eligible', kpi_possibly_s: 'need more answers',
      kpi_annual: 'Cash support / year', kpi_fixed: 'fixed amounts only', kpi_onetime: 'One-time grants',
      kpi_cover: 'Health cover', kpi_cover_s: 'per family / year', kpi_if_selected: '+{v} if selected in exam',
      filter_all: 'All', st_eligible: 'Eligible', st_possibly: 'Possibly eligible', st_not: 'Not eligible',
      read_results: 'Read my results', why: 'Why?', how_apply: 'Documents & how to apply', add_check: 'Checklist',
      conditions: '{p} of {t} conditions met', you_said: 'Answer', documents: 'Documents needed',
      where_apply: 'Where / how to apply', portal: 'Official portal', caveats: 'Simplified — also note',
      central: 'Central', tamil_nadu: 'Tamil Nadu', verify: 'Verify',
      search_ph: 'Type in English or தமிழ் — e.g. பயிர் காப்பீடு, pension for widow',
      search_btn: 'Search', understood: 'Understood as', no_results: 'No matching scheme. Try another word.',
      search_how: 'How search works',
      search_how_body: "Your words are split into tokens (Tamil vowel signs kept), lightly stemmed, mapped through a bilingual concept dictionary (பயிர் → crop, காப்பீடு → insurance) and ranked by TF-IDF cosine similarity against every scheme's English and Tamil description. No internet needed.",
      search_stats: 'Ranked {n} schemes in {ms} ms', match: 'match', matched: 'matched',
      chosen_schemes: 'Schemes to apply for', checklist_title: 'Document checklist',
      checklist_sub: 'One set of {d} documents covers all {s} schemes (instead of {m} separate items across forms).',
      checklist_empty: 'Pick at least one scheme to build the checklist.', needed_for: 'Needed for',
      print: 'Print checklist', tracker: 'Application tracker', family_name: 'Family name', village: 'Village',
      tracker_hint: 'Save the family to track applications. Saved to data/state.json on this laptop.',
      tracker_empty: 'No eligible schemes to track yet — answer the questionnaire first.',
      app_not_applied: 'Not applied', app_applied: 'Applied', app_pending: 'Pending', app_received: 'Received',
      in_progress: 'Applied / pending', unclaimed: 'Eligible, not applied',
      load_village: 'Load demo village', clear_all: 'Clear all', all_villages: 'All villages',
      chart_title: 'Schemes with the most eligible-but-not-applied families',
      priority_families: 'Families to visit first', scheme_table: 'Scheme-wise uptake',
      k_households: 'Households', k_unclaimed_pairs: 'Eligible but not applied',
      k_unclaimed_value: 'Unclaimed cash / year', k_unclaimed_onetime: 'Unclaimed one-time grants',
      k_claim_rate: 'Claim rate', k_pairs_s: 'family × scheme pairs', open: 'Open',
      th_family: 'Family', th_eligible: 'Eligible', th_unclaimed: 'Unclaimed', th_value: '₹ / yr',
      th_scheme: 'Scheme', th_received: 'Received', th_progress: 'In progress', th_possibly: 'Possibly',
      village_empty: 'No households registered yet. Load the demo village or register a family.',
      village_stats: 'Computed in {ms} ms', confirm_clear: 'Delete all registered households?',
      footer_note: 'Prototype: scheme rules are simplified. Always verify eligibility on the official portal before applying. Runs fully offline.',
      no_speech: 'Read-aloud is not available on this device.', no_tamil_voice: 'No Tamil voice installed — using the default voice.',
      saved: 'Saved', error: 'Something went wrong', demo_banner: 'Demo · {name}: answered {q} questions instead of a {full}-field form.',
      opened: 'Opened {name}', village_loaded: 'Demo village loaded ({n} households)', cleared: 'All households cleared',
      need_name: 'Please enter a family name', speech_on: 'Questions will be read aloud', speech_off: 'Read-aloud off',
      about_rules: 'Rule engine (explainable)', about_q: 'Smart questionnaire', about_search: 'Bilingual search',
      about_eval: 'Measured results', about_limits: 'Assumptions & limits',
      about_rules_body: 'Each scheme is a JSON rule tree with all / any / not, comparisons, ranges and membership. It is evaluated with three-valued logic, so a missing answer gives "possibly eligible" only if it could change the outcome. Every card shows which condition passed (✓), failed (×) or is unknown (?).',
      about_q_body: 'The next question is the one with the highest expected information gain over the schemes that are still undecided. Screening questions ("anyone studying in Class 8+?") settle several facts with one tap, and simple inferences (a woman head of family ⇒ an adult woman lives here) avoid repeat questions.',
      about_search_body: 'TF-IDF over scheme names and descriptions in both languages, plus a bilingual concept map so Tamil queries find English text and the other way round.',
      about_limits_body: 'Rules are simplified and some thresholds are approximate; real eligibility is decided by the department (often from SECC 2011 or state lists). Synthetic households are illustrative, not census data.',
      strategy: 'Strategy', avg_q: 'Avg questions', median: 'Median', max: 'Max', accuracy: 'Same decision as full form',
      eval_missing: 'Run python -m schemesetu.evaluate to generate measured results.',
      full_form_row: 'Full form (every field)', curve_title: 'How fast eligibility is found',
      curve_x: 'questions asked', curve_elig: 'eligible schemes confirmed', curve_dec: 'schemes decided'
    },
    ta: {
      tagline: 'ஒவ்வொரு கிராமக் குடும்பத்திற்கும் உரிய நலத்திட்டங்கள் — எளிதாக',
      mode_family: 'குடும்பம்', mode_worker: 'களப் பணியாளர்', read_aloud: 'சத்தமாகப் படி',
      tab_find: 'என் திட்டங்கள்', tab_search: 'தேடல்', tab_check: 'ஆவணங்கள் & நிலை',
      tab_village: 'கிராம நிலவரம்', tab_about: 'எப்படி வேலை செய்கிறது',
      demo_title: 'மாதிரிக் குடும்பம்', demo_hint: 'ஒரே தொடுதலில் மாதிரிக் குடும்பத்திற்கான கேள்விகளுக்குப் பதில்.',
      question_n: 'கேள்வி {n}', open_n: '{n} திட்டங்கள் இன்னும் முடிவாகவில்லை', yes: 'ஆம்', no: 'இல்லை',
      skip: 'தெரியாது / தவிர்', back: 'பின்செல்', restart: 'மீண்டும் தொடங்கு', why_q: 'ஏன் இந்தக் கேள்வி?',
      also_considered: 'பரிசீலிக்கப்பட்ட பிற கேள்விகள்', done_title: 'அனைத்துத் திட்டங்களும் சரிபார்க்கப்பட்டன',
      done_body: 'கேள்விகளுக்குப் பதில் — முழுப் படிவத்தில் {full} கேள்விகள்',
      done_skipped: '{n} தவிர்க்கப்பட்டன — அந்தத் திட்டங்கள் "தகுதி இருக்கலாம்" என்றே இருக்கும்.',
      go_docs: 'ஆவணங்களைப் பார்', review: 'கடைசிப் பதிலை மாற்று',
      your_answers: 'உங்கள் பதில்கள்', inferred: 'ஊகிக்கப்பட்டது', skipped: 'தவிர்க்கப்பட்டது', answers_n: '{n} பதில்கள்',
      no_answers: 'இன்னும் பதில்கள் இல்லை. மேலே உள்ள கேள்விக்குப் பதிலளிக்கவும் அல்லது மாதிரிக் குடும்பத்தைத் தேர்ந்தெடுக்கவும்.',
      save_family: 'இந்தக் குடும்பத்தைச் சேமி', register_family: 'குடும்பத்தைப் பதிவு செய்', saved_as: '{name} எனச் சேமிக்கப்பட்டது',
      save_changes: 'பதில்களைச் சேமி', unsaved: 'சேமித்த பின் பதில்கள் மாறியுள்ளன',
      kpi_eligible: 'தகுதியுள்ள திட்டங்கள்', kpi_possibly: 'தகுதி இருக்கலாம்', kpi_possibly_s: 'மேலும் பதில்கள் தேவை',
      kpi_annual: 'ஆண்டுப் பண உதவி', kpi_fixed: 'நிலையான தொகைகள் மட்டும்', kpi_onetime: 'ஒருமுறை உதவி',
      kpi_cover: 'மருத்துவக் காப்பீடு', kpi_cover_s: 'குடும்பத்திற்கு / ஆண்டுக்கு', kpi_if_selected: 'தேர்வானால் +{v}',
      filter_all: 'அனைத்தும்', st_eligible: 'தகுதி உண்டு', st_possibly: 'தகுதி இருக்கலாம்', st_not: 'தகுதி இல்லை',
      read_results: 'முடிவுகளைப் படி', why: 'ஏன்?', how_apply: 'ஆவணங்கள் & விண்ணப்ப முறை', add_check: 'பட்டியல்',
      conditions: '{t} நிபந்தனைகளில் {p} பூர்த்தி', you_said: 'பதில்', documents: 'தேவையான ஆவணங்கள்',
      where_apply: 'எங்கே / எப்படி விண்ணப்பிப்பது', portal: 'அதிகாரப்பூர்வ இணையதளம்', caveats: 'எளிமைப்படுத்தப்பட்டது — மேலும் கவனிக்க',
      central: 'மத்திய அரசு', tamil_nadu: 'தமிழ்நாடு', verify: 'சரிபார்க்கவும்',
      search_ph: 'ஆங்கிலம் அல்லது தமிழில் தட்டச்சு செய்யவும் — எ.கா. பயிர் காப்பீடு',
      search_btn: 'தேடு', understood: 'புரிந்துகொண்டது', no_results: 'பொருந்தும் திட்டம் இல்லை. வேறு சொல்லை முயற்சிக்கவும்.',
      search_how: 'தேடல் எப்படி வேலை செய்கிறது',
      search_how_body: 'உங்கள் சொற்கள் பிரிக்கப்பட்டு, வேர்ச்சொல்லாக்கப்பட்டு, இருமொழி அகராதி மூலம் (பயிர் → crop, காப்பீடு → insurance) பொருள் காணப்பட்டு, ஒவ்வொரு திட்டத்தின் தமிழ் / ஆங்கில விளக்கத்துடன் TF-IDF ஒப்பீட்டில் வரிசைப்படுத்தப்படுகின்றன. இணையம் தேவையில்லை.',
      search_stats: '{n} திட்டங்கள் {ms} மி.வி-இல் வரிசைப்படுத்தப்பட்டன', match: 'பொருத்தம்', matched: 'பொருந்தியவை',
      chosen_schemes: 'விண்ணப்பிக்க வேண்டிய திட்டங்கள்', checklist_title: 'ஆவணச் சரிபார்ப்புப் பட்டியல்',
      checklist_sub: '{s} திட்டங்களுக்கும் {d} ஆவணங்கள் போதும் (படிவங்களில் தனித்தனியாக {m} உருப்படிகளுக்குப் பதிலாக).',
      checklist_empty: 'பட்டியல் உருவாக குறைந்தது ஒரு திட்டத்தைத் தேர்ந்தெடுக்கவும்.', needed_for: 'தேவைப்படும் திட்டங்கள்',
      print: 'பட்டியலை அச்சிடு', tracker: 'விண்ணப்ப நிலை', family_name: 'குடும்பப் பெயர்', village: 'கிராமம்',
      tracker_hint: 'விண்ணப்ப நிலையைக் கண்காணிக்கக் குடும்பத்தைச் சேமிக்கவும். இந்த மடிக்கணினியிலேயே சேமிக்கப்படும்.',
      tracker_empty: 'கண்காணிக்கத் தகுதியுள்ள திட்டங்கள் இல்லை — முதலில் கேள்விகளுக்குப் பதிலளிக்கவும்.',
      app_not_applied: 'விண்ணப்பிக்கவில்லை', app_applied: 'விண்ணப்பித்தது', app_pending: 'நிலுவையில்', app_received: 'பெறப்பட்டது',
      in_progress: 'விண்ணப்பித்தது / நிலுவை', unclaimed: 'தகுதி உண்டு, விண்ணப்பிக்கவில்லை',
      load_village: 'மாதிரிக் கிராமம்', clear_all: 'அனைத்தையும் அழி', all_villages: 'அனைத்துக் கிராமங்கள்',
      chart_title: 'தகுதி இருந்தும் விண்ணப்பிக்காத குடும்பங்கள் அதிகமுள்ள திட்டங்கள்',
      priority_families: 'முதலில் சந்திக்க வேண்டிய குடும்பங்கள்', scheme_table: 'திட்ட வாரியான பயன்பாடு',
      k_households: 'குடும்பங்கள்', k_unclaimed_pairs: 'தகுதி உண்டு, விண்ணப்பிக்கவில்லை',
      k_unclaimed_value: 'பெறப்படாத ஆண்டுத் தொகை', k_unclaimed_onetime: 'பெறப்படாத ஒருமுறை உதவி',
      k_claim_rate: 'பெறும் விகிதம்', k_pairs_s: 'குடும்பம் × திட்டம்', open: 'திற',
      th_family: 'குடும்பம்', th_eligible: 'தகுதி', th_unclaimed: 'பெறாதவை', th_value: '₹ / ஆண்டு',
      th_scheme: 'திட்டம்', th_received: 'பெற்றவை', th_progress: 'நடைமுறையில்', th_possibly: 'இருக்கலாம்',
      village_empty: 'இன்னும் குடும்பங்கள் பதிவு செய்யப்படவில்லை. மாதிரிக் கிராமத்தை ஏற்றவும்.',
      village_stats: '{ms} மி.வி-இல் கணக்கிடப்பட்டது', confirm_clear: 'பதிவு செய்த அனைத்துக் குடும்பங்களையும் அழிக்கவா?',
      footer_note: 'முன்மாதிரி: திட்ட விதிகள் எளிமைப்படுத்தப்பட்டுள்ளன. விண்ணப்பிக்கும் முன் அதிகாரப்பூர்வ இணையதளத்தில் சரிபார்க்கவும். இணையம் இன்றி இயங்கும்.',
      no_speech: 'இந்தச் சாதனத்தில் ஒலி வசதி இல்லை.', no_tamil_voice: 'தமிழ்க் குரல் நிறுவப்படவில்லை — இயல்புக் குரல் பயன்படுத்தப்படுகிறது.',
      saved: 'சேமிக்கப்பட்டது', error: 'ஏதோ தவறு நடந்தது', demo_banner: 'மாதிரி · {name}: {full} கேள்விப் படிவத்திற்குப் பதிலாக {q} கேள்விகளே.',
      opened: '{name} திறக்கப்பட்டது', village_loaded: 'மாதிரிக் கிராமம் ஏற்றப்பட்டது ({n} குடும்பங்கள்)', cleared: 'அனைத்துக் குடும்பங்களும் அழிக்கப்பட்டன',
      need_name: 'குடும்பப் பெயரை உள்ளிடவும்', speech_on: 'கேள்விகள் சத்தமாகப் படிக்கப்படும்', speech_off: 'ஒலி நிறுத்தப்பட்டது',
      about_rules: 'விதி இயந்திரம் (விளக்கத்துடன்)', about_q: 'புத்திசாலிக் கேள்வித்தாள்', about_search: 'இருமொழித் தேடல்',
      about_eval: 'அளவிடப்பட்ட முடிவுகள்', about_limits: 'அனுமானங்கள் & வரம்புகள்',
      about_rules_body: 'ஒவ்வொரு திட்டமும் all / any / not, ஒப்பீடுகள், வரம்புகள் கொண்ட JSON விதி மரம். மூன்று-நிலை தர்க்கத்தில் மதிப்பிடப்படுவதால், விடுபட்ட பதில் முடிவை மாற்றக்கூடுமானால் மட்டுமே "தகுதி இருக்கலாம்" எனக் காட்டப்படும். ஒவ்வொரு அட்டையிலும் எந்த நிபந்தனை பூர்த்தியானது (✓), தோல்வி (×), தெரியாதது (?) எனக் காணலாம்.',
      about_q_body: 'இன்னும் முடிவாகாத திட்டங்களில் அதிகத் தகவல் ஆதாயம் தரும் கேள்வியே அடுத்ததாகக் கேட்கப்படும். சோதனைக் கேள்விகள் ஒரே பதிலில் பல விவரங்களைத் தீர்க்கும்; எளிய ஊகங்கள் (பெண் குடும்பத் தலைவர் ⇒ வயது வந்த பெண் உண்டு) மீண்டும் கேட்பதைத் தவிர்க்கும்.',
      about_search_body: 'இரு மொழிகளிலும் திட்டப் பெயர், விளக்கங்கள் மீது TF-IDF; தமிழ்த் தேடல் ஆங்கில உரையையும், ஆங்கிலத் தேடல் தமிழ் உரையையும் கண்டுபிடிக்க இருமொழிக் கருத்து அகராதி.',
      about_limits_body: 'விதிகள் எளிமைப்படுத்தப்பட்டவை; சில வரம்புகள் தோராயமானவை. உண்மையான தகுதியைத் துறையே முடிவு செய்யும் (பெரும்பாலும் SECC 2011 / மாநிலப் பட்டியல்கள்). செயற்கைக் குடும்பத் தரவு விளக்கத்திற்கு மட்டுமே.',
      strategy: 'முறை', avg_q: 'சராசரி கேள்விகள்', median: 'நடுநிலை', max: 'அதிகபட்சம்', accuracy: 'முழுப் படிவத்துடன் ஒரே முடிவு',
      eval_missing: 'அளவீடுகளை உருவாக்க python -m schemesetu.evaluate இயக்கவும்.',
      full_form_row: 'முழுப் படிவம் (அனைத்துக் கேள்விகள்)', curve_title: 'தகுதி எவ்வளவு விரைவாகக் கண்டறியப்படுகிறது',
      curve_x: 'கேட்கப்பட்ட கேள்விகள்', curve_elig: 'உறுதியான தகுதித் திட்டங்கள்', curve_dec: 'முடிவான திட்டங்கள்'
    }
  };

  var ICONS = {
    farmer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 21V10"/><path d="M12 13c-4 0-6-3-6-7 4 0 6 3 6 7z"/><path d="M12 11c0-4 2-7 6-7 0 4-2 7-6 7z"/><path d="M5 21h14"/></svg>',
    labourer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 21h18"/><path d="M5 21V11l7-6 7 6v10"/><path d="M10 21v-5h4v5"/></svg>',
    widow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="7" r="3.5"/><path d="M5 21c0-4 3-7 7-7s7 3 7 7"/></svg>',
    students: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/></svg>',
    speak: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg>'
  };
  var DEMO_ICON = { 'demo-farmer': 'farmer', 'demo-labourer': 'labourer', 'demo-widow': 'widow', 'demo-students': 'students' };
  var EXAMPLES = ['பயிர் காப்பீடு', 'pension for widow', 'house', 'கழிப்பறை', 'gas cylinder', 'scholarship for college girl', 'மகளிர் உரிமைத் தொகை', '100 days work', 'முதியோர் ஓய்வூதியம்', 'crop loan'];

  // ------------------------------------------------------------------ state
  var S = {
    lang: 'en', mode: 'family', speakOn: false, tab: 'find',
    meta: null, schemes: {}, qById: {}, demo: [],
    profile: {}, skipped: [], history: [], ev: null, next: null, done: false,
    filter: 'all', expanded: {}, selected: null, have: {}, checklist: null,
    household: null, savedProfile: null, demoId: null, demoSteps: null,
    villageName: '', busy: false, evalData: null
  };

  // ------------------------------------------------------------------ helpers
  function $(s) { return document.querySelector(s); }
  function $all(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function t(key, vars) {
    var s = (I18N[S.lang] && I18N[S.lang][key]) || I18N.en[key] || key;
    if (vars) Object.keys(vars).forEach(function (k) { s = s.split('{' + k + '}').join(vars[k]); });
    return s;
  }
  function L(o) {
    if (o == null) return '';
    if (typeof o === 'string') return o;
    return o[S.lang] || o.en || '';
  }
  function inr(n) {
    n = Math.round(Number(n) || 0);
    var s = String(Math.abs(n));
    if (s.length > 3) {
      var head = s.slice(0, -3), tail = s.slice(-3), parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head);
      s = parts.join(',') + ',' + tail;
    }
    return '₹' + s;
  }
  function inrShort(n) {
    if (n >= 100000) return '₹' + (n / 100000).toFixed(n % 100000 ? 1 : 0) + (S.lang === 'ta' ? ' லட்சம்' : ' lakh');
    return inr(n);
  }
  function store(k, v) { try { localStorage.setItem('schemesetu.' + k, v); } catch (e) { /* storage blocked */ } }
  function load(k) { try { return localStorage.getItem('schemesetu.' + k); } catch (e) { return null; } }
  var toastTimer = null;
  function toast(msg) {
    var el = $('#toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 2600);
  }
  function api(path, body, method) {
    var opts = { method: method || (body !== undefined ? 'POST' : 'GET'), headers: {} };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
        return j;
      });
    });
  }
  function fail(e) { toast(t('error') + ': ' + (e && e.message ? e.message : e)); }
  function catColor(c) { return (S.meta && S.meta.categories[c] && S.meta.categories[c].color) || '#888'; }
  function catLabel(c) { return S.meta && S.meta.categories[c] ? L(S.meta.categories[c]) : c; }
  function statusLabel(st) { return t(st === 'eligible' ? 'st_eligible' : st === 'possibly' ? 'st_possibly' : 'st_not'); }
  function statusIcon(st) { return st === 'eligible' ? '✓' : st === 'possibly' ? '?' : '×'; }
  function answerLabel(qid, v) {
    var q = S.qById[qid];
    if (v === null || v === undefined) return t('skipped');
    if (!q) return String(v);
    if (q.type === 'bool') return v ? t('yes') : t('no');
    for (var i = 0; i < (q.options || []).length; i++) if (q.options[i].value === v) return L(q.options[i].label);
    return String(v);
  }
  function hhName(h) { return h ? L(h.name) : ''; }

  // ------------------------------------------------------------------ speech
  function speak(text) {
    try {
      if (!('speechSynthesis' in window) || typeof window.SpeechSynthesisUtterance === 'undefined') { toast(t('no_speech')); return; }
      var syn = window.speechSynthesis;
      syn.cancel();
      var u = new window.SpeechSynthesisUtterance(text);
      var want = S.lang === 'ta' ? 'ta' : 'en';
      u.lang = want === 'ta' ? 'ta-IN' : 'en-IN';
      var voices = syn.getVoices() || [];
      var v = voices.filter(function (x) { return (x.lang || '').toLowerCase().indexOf(want) === 0; })[0];
      if (v) u.voice = v; else if (want === 'ta' && voices.length) toast(t('no_tamil_voice'));
      u.onerror = function () { toast(t('no_speech')); };
      syn.speak(u);
    } catch (e) { toast(t('no_speech')); }
  }

  // ------------------------------------------------------------------ i18n apply
  function applyI18n() {
    document.documentElement.lang = S.lang;
    $all('[data-i18n]').forEach(function (el) { el.textContent = t(el.getAttribute('data-i18n')); });
    $('#search-input').placeholder = t('search_ph');
    $all('#lang-seg button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-lang') === S.lang); });
    $all('#mode-seg button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-mode') === S.mode); });
  }

  // ------------------------------------------------------------------ questionnaire
  function refresh() {
    S.busy = true;
    return api('/api/next', { profile: S.profile, skipped: S.skipped }).then(function (res) {
      S.busy = false;
      S.next = res.next; S.done = res.done; S.ev = res.evaluation;
      renderFind();
      refreshChecklist();
      if (S.speakOn && S.next && S.tab === 'find') speakQuestion();
    }).catch(function (e) { S.busy = false; fail(e); });
  }

  function answer(qid, value) {
    if (S.busy) return;
    S.profile[qid] = value;
    S.history.push(qid);
    S.demoSteps = null;
    refresh();
  }
  function skip(qid) {
    if (S.busy) return;
    S.skipped.push(qid);
    S.history.push(qid);
    S.demoSteps = null;
    refresh();
  }
  function back() {
    if (!S.history.length || S.busy) return;
    var qid = S.history.pop();
    delete S.profile[qid];
    S.skipped = S.skipped.filter(function (x) { return x !== qid; });
    S.demoSteps = null;
    refresh();
  }
  function restart() {
    S.profile = {}; S.skipped = []; S.history = []; S.household = null; S.savedProfile = null;
    S.demoId = null; S.demoSteps = null; S.selected = null; S.have = {}; S.expanded = {};
    renderDemoButtons();
    refresh();
  }

  function loadDemo(id) {
    api('/api/simulate', { demo: id }).then(function (sim) {
      S.profile = sim.profile; S.skipped = sim.skipped; S.history = sim.steps.map(function (s) { return s.id; });
      S.demoId = id; S.demoSteps = sim.steps; S.household = null; S.savedProfile = null;
      S.selected = null; S.have = {}; S.expanded = {};
      renderDemoButtons();
      return refresh();
    }).catch(fail);
  }

  function speakQuestion() {
    if (!S.next) return;
    var q = S.next.question;
    var opts = q.type === 'bool' ? [t('yes'), t('no')] : q.options.map(function (o) { return L(o.label); });
    speak(L(q.text) + ' ' + opts.join(', '));
  }

  // ------------------------------------------------------------------ render: find tab
  function renderDemoButtons() {
    $('#demo-row').innerHTML = S.demo.map(function (d) {
      return '<button class="demo-btn' + (S.demoId === d.id ? ' on' : '') + '" id="' + esc(d.id) + '" data-demo="' + esc(d.id) + '">' +
        '<span class="demo-ico">' + ICONS[DEMO_ICON[d.id] || 'widow'] + '</span>' +
        '<span><b>' + esc(L(d.name)) + '</b><span>' + esc(L(d.persona)) + '</span></span></button>';
    }).join('');
  }

  function renderQuestion() {
    var ev = S.ev, total = 22;
    if (!ev) return;
    total = ev.results.length;
    var decided = total - ev.counts.possibly;
    $('#q-progress').style.width = Math.round(100 * decided / total) + '%';
    var body = $('#q-body');
    if (S.done || !S.next) {
      var asked = S.history.length;
      $('#q-num').textContent = t('done_title');
      $('#q-open').textContent = '';
      body.innerHTML = '<div class="done-box"><div class="big">' + asked + ' <small>/ ' + ev.total_questions + '</small></div>' +
        '<p class="muted" style="margin:4px 0 10px">' + esc(t('done_body', { full: ev.total_questions })) + '</p>' +
        (S.skipped.length ? '<p class="small muted">' + esc(t('done_skipped', { n: S.skipped.length })) + '</p>' : '') +
        '</div><div class="qactions"><button class="link-btn" data-act="back"' + (S.history.length ? '' : ' disabled') + '>← ' + esc(t('review')) + '</button>' +
        '<button class="link-btn" data-act="restart">' + esc(t('restart')) + '</button>' +
        '<button class="btn" data-act="docs">' + esc(t('go_docs')) + ' →</button></div>';
      return;
    }
    var nq = S.next, q = nq.question;
    $('#q-num').textContent = t('question_n', { n: S.history.length + 1 });
    $('#q-open').textContent = t('open_n', { n: nq.open_schemes });
    var opts;
    if (q.type === 'bool') {
      opts = '<button class="ans yes" data-ans="true">' + esc(t('yes')) + '</button><button class="ans" data-ans="false">' + esc(t('no')) + '</button>';
    } else {
      opts = q.options.map(function (o, i) {
        return '<button class="ans" data-opt="' + i + '">' + esc(L(o.label)) + '</button>';
      }).join('');
    }
    var alts = (nq.alternatives || []).map(function (a) { return S.qById[a.id] ? L(S.qById[a.id].short) : a.id; });
    body.innerHTML = '<div class="qtext">' + esc(L(q.text)) + '</div>' +
      '<div class="answers' + (q.type === 'bool' ? '' : ' many') + '" id="answers">' + opts + '</div>' +
      '<div class="qactions"><button class="link-btn" data-act="back"' + (S.history.length ? '' : ' disabled') + '>← ' + esc(t('back')) + '</button>' +
      '<button class="link-btn" data-act="speakq">' + ICONS.speak.replace('<svg', '<svg width="16" height="16" style="vertical-align:-3px"') + ' ' + esc(t('read_aloud')) + '</button>' +
      '<button class="link-btn" data-act="skip">' + esc(t('skip')) + '</button></div>' +
      '<div class="why-box"><b>' + esc(t('why_q')) + '</b> ' + esc(L(nq.why)) +
      (alts.length ? '<div class="small muted" style="margin-top:4px">' + esc(t('also_considered')) + ': ' + esc(alts.join(', ')) + '</div>' : '') + '</div>';
  }

  function renderAnswers() {
    var ev = S.ev;
    var items = S.history.map(function (qid, i) {
      var q = S.qById[qid];
      var sk = S.skipped.indexOf(qid) >= 0;
      return '<li><span class="n">' + (i + 1) + '</span><span class="q">' + esc(q ? L(q.short) : qid) + '</span>' +
        '<span class="a">' + (sk ? '<span class="tag">' + esc(t('skipped')) + '</span>' : esc(answerLabel(qid, S.profile[qid]))) + '</span></li>';
    });
    (ev ? ev.inferred : []).forEach(function (inf) {
      items.push('<li><span class="n">·</span><span class="q">' + esc(L(inf.short)) + '</span><span class="a">' + esc(L(inf.answer)) +
        ' <span class="tag inf" title="' + esc(L(inf.from_short)) + '">' + esc(t('inferred')) + '</span></span></li>');
    });
    $('#answer-list').innerHTML = items.length ? items.join('') : '<li class="muted">' + esc(t('no_answers')) + '</li>';
    $('#answers-count').textContent = t('answers_n', { n: S.history.length - S.skipped.length });
    var btn = $('#save-family-btn');
    var saved = $('#saved-as');
    if (S.household) {
      var dirty = JSON.stringify(S.profile) !== JSON.stringify(S.savedProfile);
      btn.textContent = t('save_changes');
      btn.disabled = !dirty;
      saved.textContent = t('saved_as', { name: hhName(S.household) }) + (dirty ? ' · ' + t('unsaved') : '');
    } else {
      btn.disabled = false;
      btn.textContent = S.mode === 'worker' ? t('register_family') : t('save_family');
      saved.textContent = '';
    }
  }

  function renderKpis() {
    var ev = S.ev;
    if (!ev) return;
    var b = ev.benefits;
    var cover = b.max_health_cover;
    var html = [
      kpi('k-green', ev.counts.eligible, t('kpi_eligible'), ev.counts.not_eligible + ' ' + t('st_not').toLowerCase()),
      kpi('k-amber', ev.counts.possibly, t('kpi_possibly'), t('kpi_possibly_s')),
      kpi('k-brand', inr(b.annual_total), t('kpi_annual'), b.conditional_total ? t('kpi_if_selected', { v: inr(b.conditional_total) }) : t('kpi_fixed')),
      kpi('', inr(b.one_time_total), t('kpi_onetime'), t('kpi_fixed')),
      kpi('', cover ? inrShort(cover) : '—', t('kpi_cover'), t('kpi_cover_s'))
    ];
    $('#kpis').innerHTML = html.join('');
  }
  function kpi(cls, v, l, s) {
    return '<div class="kpi ' + cls + '"><div class="l">' + esc(l) + '</div><div class="v">' + esc(v) + '</div><div class="s">' + esc(s || '') + '</div></div>';
  }

  function renderBanner() {
    var el = $('#find-banner');
    if (S.demoId && S.done && S.ev) {
      var d = S.demo.filter(function (x) { return x.id === S.demoId; })[0];
      el.innerHTML = '<b>' + esc(t('demo_banner', { name: L(d.name), q: S.history.length, full: S.ev.total_questions })) + '</b> ' +
        esc(L(d.persona));
      el.classList.remove('hidden');
    } else if (S.household) {
      el.innerHTML = '<b>' + esc(hhName(S.household)) + '</b> · ' + esc(S.household.village);
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  }

  function treeHtml(node) {
    if (node.kind === 'cond') {
      return '<li><div class="cond"><span class="ic ' + node.status + '">' + (node.status === 'pass' ? '✓' : node.status === 'fail' ? '×' : '?') + '</span>' +
        '<div>' + esc(L(node.text)) + '<div class="ans-l">' + esc(t('you_said')) + ': ' + esc(L(node.answer)) +
        (node.inferred_from ? ' <span class="tag inf">' + esc(t('inferred')) + '</span>' : '') + '</div></div></div></li>';
    }
    return '<li><div class="grp">' + esc(L(node.text)) + '</div><ul class="tree">' + node.children.map(treeHtml).join('') + '</ul></li>';
  }

  function schemeCard(r, opts) {
    opts = opts || {};
    var s = S.schemes[r.id] || {};
    var exp = S.expanded[r.id];
    var picked = isSelected(r.id);
    var html = '<article class="scheme ' + r.status + '" data-id="' + esc(r.id) + '">' +
      '<div class="scheme-top"><span class="cat-dot" style="background:' + esc(catColor(r.category)) + '"></span>' + esc(catLabel(r.category)) +
      '<span class="lvl' + (s.level === 'tamil_nadu' ? ' tn' : '') + '">' + esc(t(s.level === 'tamil_nadu' ? 'tamil_nadu' : 'central')) + '</span>' +
      (opts.score != null ? '<span class="score" title="TF-IDF"><i style="width:' + Math.round(Math.min(1, opts.score) * 100) + '%"></i></span>' : '') +
      (r.status ? '<span class="pill ' + r.status + '">' + statusIcon(r.status) + ' ' + esc(statusLabel(r.status)) + '</span>' : '') + '</div>' +
      '<h4>' + esc(L(r.name || s.name)) + '</h4>' +
      '<p class="sum">' + esc(L(r.summary || s.summary)) + '</p>' +
      '<div class="benefit">' + esc(L((r.benefit || s.benefit || {}).label)) + '</div>';
    if (opts.matched) html += '<div class="reason muted">' + esc(t('matched')) + ': ' + esc(opts.matched.join(', ')) + '</div>';
    if (r.reason) {
      html += '<div class="reason"><span class="muted">' + esc(L(r.reason)) + '</span>' + (r.status === 'eligible' ? '' : ' · <span class="muted">' +
        esc(t('conditions', { p: r.conditions.pass, t: r.conditions.total })) + '</span>') + '</div>';
    }
    html += '<div class="scheme-actions">' +
      (r.trace ? '<button class="mini' + (exp === 'why' ? ' on' : '') + '" data-act="why" data-id="' + esc(r.id) + '">' + esc(t('why')) + '</button>' : '') +
      '<button class="mini' + (exp === 'apply' ? ' on' : '') + '" data-act="apply" data-id="' + esc(r.id) + '">' + esc(t('how_apply')) + '</button>' +
      '<button class="mini" data-act="speak" data-id="' + esc(r.id) + '" title="' + esc(t('read_aloud')) + '" aria-label="' + esc(t('read_aloud')) + '">' + ICONS.speak + '</button>' +
      (r.status && r.status !== 'not_eligible' ? '<button class="mini' + (picked ? ' on' : '') + '" data-act="pick" data-id="' + esc(r.id) + '">' + (picked ? '✓ ' : '+ ') + esc(t('add_check')) + '</button>' : '') +
      '</div>';
    if (exp === 'why' && r.trace) html += '<div class="detail"><ul class="tree">' + treeHtml(r.trace) + '</ul></div>';
    if (exp === 'apply') {
      var docs = (s.documents || []).map(function (d) { return '<li>' + esc(L(S.meta.documents[d])) + '</li>'; }).join('');
      html += '<div class="detail"><b>' + esc(t('documents')) + '</b><ul>' + docs + '</ul>' +
        '<b>' + esc(t('where_apply')) + '</b><div>' + esc(L(s.apply)) + '</div>' +
        '<div style="margin-top:4px"><b>' + esc(t('portal')) + ':</b> ' + esc(s.portal) + '</div>' +
        (s.caveats ? '<div class="small muted" style="margin-top:4px"><b>' + esc(t('caveats')) + ':</b> ' + esc(L(s.caveats)) + '</div>' : '') + '</div>';
    }
    html += '<div class="verify"><b>!</b> ' + esc(L(s.verify_note)) + '</div></article>';
    return html;
  }

  function renderResults() {
    if (!S.ev) return;
    var list = S.ev.results.filter(function (r) { return S.filter === 'all' || r.status === S.filter; });
    $all('#filters .chip').forEach(function (c) { c.classList.toggle('on', c.getAttribute('data-filter') === S.filter); });
    $('#results').innerHTML = list.length ? list.map(function (r) { return schemeCard(r); }).join('') : '<div class="empty card">—</div>';
  }

  function renderFind() {
    renderQuestion();
    renderAnswers();
    renderKpis();
    renderBanner();
    renderResults();
  }

  // ------------------------------------------------------------------ checklist + tracker
  function defaultSelected() {
    if (!S.ev) return [];
    return S.ev.results.filter(function (r) { return r.status === 'eligible'; }).map(function (r) { return r.id; });
  }
  function isSelected(id) { return (S.selected || defaultSelected()).indexOf(id) >= 0; }
  function togglePick(id) {
    var cur = (S.selected || defaultSelected()).slice();
    var i = cur.indexOf(id);
    if (i >= 0) cur.splice(i, 1); else cur.push(id);
    S.selected = cur;
    renderResults();
    refreshChecklist();
  }

  function refreshChecklist() {
    var ids = S.selected || defaultSelected();
    renderPickList();
    renderTracker();
    if (!ids.length) {
      S.checklist = null;
      renderChecklist();
      return;
    }
    api('/api/checklist', { scheme_ids: ids }).then(function (c) { S.checklist = c; renderChecklist(); }).catch(fail);
  }

  function renderPickList() {
    if (!S.ev) return;
    var rows = S.ev.results.filter(function (r) { return r.status !== 'not_eligible'; });
    $('#pick-list').innerHTML = rows.length ? rows.map(function (r) {
      return '<li><input type="checkbox" data-pick="' + esc(r.id) + '"' + (isSelected(r.id) ? ' checked' : '') + ' id="pk-' + esc(r.id) + '">' +
        '<label for="pk-' + esc(r.id) + '" style="flex:1">' + esc(L(r.name)) + '</label><span class="pill ' + r.status + '">' + statusIcon(r.status) + '</span></li>';
    }).join('') : '<li class="muted">' + esc(t('tracker_empty')) + '</li>';
  }

  function renderChecklist() {
    var c = S.checklist;
    $('#check-badge').textContent = c ? c.count : 0;
    if (!c) {
      $('#checklist-sub').textContent = t('checklist_empty');
      $('#doc-list').innerHTML = '';
      return;
    }
    var nSchemes = (S.selected || defaultSelected()).length;
    $('#checklist-sub').textContent = t('checklist_sub', { d: c.count, s: nSchemes, m: c.mentions });
    $('#doc-list').innerHTML = c.items.map(function (d) {
      var names = d.schemes.map(function (sid) { return S.schemes[sid] ? S.schemes[sid].short : sid; }).join(', ');
      return '<li><input type="checkbox" data-have="' + esc(d.id) + '"' + (S.have[d.id] ? ' checked' : '') + ' aria-label="' + esc(L(d.name)) + '">' +
        '<div style="flex:1"><b>' + esc(L(d.name)) + '</b><div class="for">' + esc(t('needed_for')) + ': ' + esc(names) + '</div></div>' +
        '<span class="count-badge">×' + d.schemes.length + '</span></li>';
    }).join('');
  }

  function renderTracker() {
    var form = $('#save-form'), box = $('#tracker');
    if (!S.household) {
      form.classList.remove('hidden');
      if (!$('#fam-village').value) $('#fam-village').value = S.mode === 'worker' ? (S.villageName || (S.meta ? S.meta.demo_village : '')) : '';
      box.innerHTML = '';
      return;
    }
    form.classList.add('hidden');
    var apps = S.household.applications || {};
    var rows = S.ev ? S.ev.results.filter(function (r) { return r.status === 'eligible' || apps[r.id]; }) : [];
    var sts = ['not_applied', 'applied', 'pending', 'received'];
    box.innerHTML = '<p class="small"><b>' + esc(hhName(S.household)) + '</b> · ' + esc(S.household.village) + '</p>' +
      (rows.length ? rows.map(function (r) {
        var cur = (apps[r.id] || {}).status || 'not_applied';
        return '<div class="track-row"><div class="nm">' + esc(L(r.name)) + '</div><div class="status-seg">' +
          sts.map(function (st) {
            return '<button class="s-' + st + (cur === st ? ' on' : '') + '" data-track="' + esc(r.id) + '" data-status="' + st + '">' + esc(t('app_' + st)) + '</button>';
          }).join('') + '</div></div>';
      }).join('') : '<p class="muted">' + esc(t('tracker_empty')) + '</p>');
  }

  function saveFamily() {
    if (S.household) {
      api('/api/households/' + encodeURIComponent(S.household.id), { profile: S.profile }, 'PUT').then(function (res) {
        S.household = res.household; S.savedProfile = JSON.parse(JSON.stringify(S.profile));
        toast(t('saved')); renderAnswers(); renderTracker();
      }).catch(fail);
      return;
    }
    var name = $('#fam-name').value.trim();
    if (!name) { switchTab('check'); $('#fam-name').focus(); toast(t('need_name')); return; }
    api('/api/households', { name: name, village: $('#fam-village').value.trim(), profile: S.profile }).then(function (res) {
      S.household = res.household; S.savedProfile = JSON.parse(JSON.stringify(S.profile));
      toast(t('saved_as', { name: name }));
      renderFind(); renderTracker();
    }).catch(fail);
  }

  function setTrack(sid, status) {
    if (!S.household) return;
    api('/api/households/' + encodeURIComponent(S.household.id) + '/applications', { scheme_id: sid, status: status }).then(function (res) {
      S.household = res.household; renderTracker(); toast(t('saved'));
    }).catch(fail);
  }

  function printChecklist() {
    var c = S.checklist;
    if (!c) { toast(t('checklist_empty')); return; }
    var ids = S.selected || defaultSelected();
    var who = S.household ? hhName(S.household) + ' · ' + S.household.village : (S.demoId ? L(S.demo.filter(function (d) { return d.id === S.demoId; })[0].name) : '');
    var html = '<h1>SchemeSetu — ' + esc(t('checklist_title')) + '</h1><div>' + esc(who) + ' · ' + esc(new Date().toLocaleDateString()) + '</div>' +
      '<table><tr><th></th><th>' + esc(t('documents')) + '</th><th>' + esc(t('needed_for')) + '</th></tr>' +
      c.items.map(function (d) {
        return '<tr><td><span class="box"></span></td><td><b>' + esc(d.name.en) + '</b><br>' + esc(d.name.ta) + '</td><td>' +
          esc(d.schemes.map(function (s) { return S.schemes[s].short; }).join(', ')) + '</td></tr>';
      }).join('') + '</table>' +
      '<table><tr><th>' + esc(t('th_scheme')) + '</th><th>' + esc(t('where_apply')) + '</th><th>' + esc(t('app_applied')) + '</th></tr>' +
      ids.map(function (sid) {
        var s = S.schemes[sid];
        return '<tr><td><b>' + esc(L(s.name)) + '</b></td><td>' + esc(L(s.apply)) + '<br><i>' + esc(s.portal) + '</i></td><td><span class="box"></span></td></tr>';
      }).join('') + '</table><p><b>!</b> ' + esc(L(S.meta.verify_note)) + '</p><p>Built for QUANTIX 2K26 · KSRCE</p>';
    $('#print-area').innerHTML = html;
    try { window.print(); } catch (e) { toast(t('error')); }
  }

  // ------------------------------------------------------------------ search
  function runSearch(q) {
    q = (q || '').trim();
    if (!q) return;
    $('#search-input').value = q;
    api('/api/search?q=' + encodeURIComponent(q) + '&k=6').then(function (res) {
      var statusById = {};
      if (S.ev) S.ev.results.forEach(function (r) { statusById[r.id] = r; });
      $('#concepts').innerHTML = res.concepts.length ? esc(t('understood')) + ': ' + res.concepts.map(function (c) {
        return '<span class="tag">' + esc(c.matched) + ' → ' + esc(c.concept) + '</span>';
      }).join('') : '';
      var top = res.results.length ? res.results[0].score : 1;
      $('#search-results').innerHTML = res.results.length ? res.results.map(function (r) {
        var ev = statusById[r.id];
        var card = ev && S.history.length ? ev : { id: r.id, name: r.name, summary: r.summary, benefit: r.benefit, category: r.category };
        return schemeCard(card, { score: r.score / top, matched: r.matched });
      }).join('') : '<div class="card empty">' + esc(t('no_results')) + '</div>';
      $('#search-stats').textContent = t('search_stats', { n: Object.keys(S.schemes).length, ms: res.elapsed_ms });
    }).catch(fail);
  }

  // ------------------------------------------------------------------ village
  function loadVillage() {
    var q = S.villageName ? '?village=' + encodeURIComponent(S.villageName) : '';
    api('/api/village' + q).then(renderVillage).catch(fail);
  }

  function renderVillage(d) {
    var sel = $('#village-select');
    sel.innerHTML = '<option value="">' + esc(t('all_villages')) + '</option>' + d.villages.map(function (v) {
      return '<option' + (v === S.villageName ? ' selected' : '') + '>' + esc(v) + '</option>';
    }).join('');
    var T = d.totals;
    $('#village-stats').textContent = t('village_stats', { ms: d.elapsed_ms });
    $('#village-kpis').innerHTML = [
      kpi('', T.households, t('k_households'), ''),
      kpi('k-brand', T.unclaimed_pairs, t('k_unclaimed_pairs'), t('k_pairs_s')),
      kpi('k-brand', inr(T.unclaimed_annual), t('k_unclaimed_value'), t('kpi_fixed')),
      kpi('', inr(T.unclaimed_one_time), t('k_unclaimed_onetime'), t('kpi_fixed')),
      kpi('k-green', Math.round(T.claim_rate * 100) + '%', t('k_claim_rate'), T.received_pairs + ' ' + t('app_received').toLowerCase())
    ].join('');
    if (!T.households) {
      $('#village-chart').innerHTML = '<div class="empty">' + esc(t('village_empty')) + '</div>';
      $('#hh-table').innerHTML = '';
      $('#scheme-table').innerHTML = '';
      return;
    }
    $('#village-chart').innerHTML = villageChart(d.schemes.slice(0, 10));
    $('#hh-table').innerHTML = '<tr><th>' + esc(t('th_family')) + '</th><th>' + esc(t('th_eligible')) + '</th><th>' + esc(t('th_unclaimed')) + '</th><th>' + esc(t('th_value')) + '</th><th></th></tr>' +
      d.households.slice(0, 12).map(function (h) {
        return '<tr><td>' + esc(L(h.name)) + '</td><td>' + h.eligible + '</td><td class="hot">' + h.unclaimed + '</td><td>' + inr(h.unclaimed_annual) +
          '</td><td><button class="mini" data-open="' + esc(h.id) + '">' + esc(t('open')) + '</button></td></tr>';
      }).join('');
    $('#scheme-table').innerHTML = '<tr><th>' + esc(t('th_scheme')) + '</th><th>' + esc(t('th_eligible')) + '</th><th>' + esc(t('th_received')) + '</th><th>' +
      esc(t('th_progress')) + '</th><th>' + esc(t('th_unclaimed')) + '</th><th>' + esc(t('th_possibly')) + '</th><th>' + esc(t('th_value')) + '</th></tr>' +
      d.schemes.map(function (r) {
        return '<tr><td>' + esc(L(r.name)) + '</td><td>' + r.eligible + '</td><td>' + r.received + '</td><td>' + (r.applied + r.pending) +
          '</td><td class="hot">' + r.unclaimed + '</td><td>' + r.possibly + '</td><td>' + (r.unclaimed_annual ? inr(r.unclaimed_annual) : '—') + '</td></tr>';
      }).join('');
  }

  function villageChart(rows) {
    // phones: a narrower drawing keeps labels ~11px instead of shrinking a 680-wide chart to half size
    var narrow = window.innerWidth <= 600;
    var W = narrow ? 400 : 680, rowH = 30, left = narrow ? 138 : 190, right = narrow ? 30 : 46, top = 6;
    var H = top + rows.length * rowH + 22;
    var max = Math.max.apply(null, rows.map(function (r) { return r.eligible; }).concat([1]));
    var step = niceStep(max / 4);
    max = Math.ceil(max / step) * step;
    var scale = (W - left - right) / max;
    var css = getComputedStyle(document.documentElement);
    var cGreen = css.getPropertyValue('--green').trim() || '#16A34A';
    var cAmber = css.getPropertyValue('--saffron').trim() || '#F59E0B';
    var cBrand = css.getPropertyValue('--brand').trim() || '#7C3AED';
    var cLine = css.getPropertyValue('--line').trim() || '#ddd';
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(t('chart_title')) + '">';
    for (var v = 0; v <= max; v += step) {
      var x = left + v * scale;
      svg += '<line x1="' + x + '" y1="' + top + '" x2="' + x + '" y2="' + (H - 18) + '" stroke="' + cLine + '" stroke-width="1"/>' +
        '<text class="axis" x="' + x + '" y="' + (H - 4) + '" font-size="' + (narrow ? 12.5 : 11) + '" text-anchor="middle">' + v + '</text>';
    }
    rows.forEach(function (r, i) {
      var y = top + i * rowH + 5, h = rowH - 10, x = left;
      var name = L(r.name);
      var maxLen = narrow ? 18 : 26;
      var short = r.short.length > maxLen ? r.short.slice(0, maxLen - 1) + '…' : r.short;
      svg += '<text x="' + (left - 8) + '" y="' + (y + h / 2 + 4) + '" font-size="' + (narrow ? 13 : 12.5) + '" text-anchor="end"><title>' + esc(name) + '</title>' + esc(short) + '</text>';
      [[r.received, cGreen], [r.applied + r.pending, cAmber], [r.unclaimed, cBrand]].forEach(function (seg) {
        if (!seg[0]) return;
        var w = seg[0] * scale;
        svg += '<rect x="' + x + '" y="' + y + '" width="' + Math.max(1, w - 1) + '" height="' + h + '" rx="3" fill="' + seg[1] + '"/>';
        x += w;
      });
      svg += '<text x="' + (x + 6) + '" y="' + (y + h / 2 + 4) + '" font-size="' + (narrow ? 13 : 12) + '" font-weight="700" fill="' + cBrand + '">' + r.unclaimed + '</text>';
    });
    return svg + '</svg>';
  }

  function niceStep(raw) {
    var p = Math.pow(10, Math.floor(Math.log(Math.max(raw, 1)) / Math.LN10));
    var f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }

  function curveChart(rows) {
    var narrow = window.innerWidth <= 600, fs = narrow ? 12 : 10.5;
    var W = narrow ? 340 : 520, H = 200, l = 36, r = 10, tp = 12, b = 42;
    var css = getComputedStyle(document.documentElement);
    var cBrand = css.getPropertyValue('--brand').trim() || '#7C3AED';
    var cAmber = css.getPropertyValue('--saffron').trim() || '#F59E0B';
    var cLine = css.getPropertyValue('--line').trim() || '#ddd';
    var maxK = rows[rows.length - 1].k;
    function X(k) { return l + (W - l - r) * k / maxK; }
    function Y(v) { return tp + (H - tp - b) * (1 - v); }
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(t('curve_title')) + '">';
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      svg += '<line x1="' + l + '" x2="' + (W - r) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="' + cLine + '"/>' +
        '<text class="axis" x="' + (l - 6) + '" y="' + (Y(v) + 4) + '" font-size="' + fs + '" text-anchor="end">' + Math.round(v * 100) + '%</text>';
    });
    var pts = [{ k: 0, decided: 0, eligible_confirmed: 0 }].concat(rows);
    [['eligible_confirmed', cBrand], ['decided', cAmber]].forEach(function (s) {
      svg += '<polyline fill="none" stroke="' + s[1] + '" stroke-width="2.5" points="' + pts.map(function (p) { return X(p.k) + ',' + Y(p[s[0]]); }).join(' ') + '"/>';
      pts.slice(1).forEach(function (p) { svg += '<circle cx="' + X(p.k) + '" cy="' + Y(p[s[0]]) + '" r="3.2" fill="' + s[1] + '"/>'; });
    });
    pts.forEach(function (p) {
      svg += '<text class="axis" x="' + X(p.k) + '" y="' + (H - b + 16) + '" font-size="' + fs + '" text-anchor="middle">' + p.k + '</text>';
    });
    svg += '<text class="axis" x="' + ((W + l) / 2) + '" y="' + (H - 8) + '" font-size="' + fs + '" text-anchor="middle">' + esc(t('curve_x')) + '</text>';
    return svg + '</svg><div class="legend"><span><i style="background:' + cBrand + '"></i>' + esc(t('curve_elig')) + '</span><span><i style="background:' + cAmber + '"></i>' + esc(t('curve_dec')) + '</span></div>';
  }

  function openHousehold(id) {
    api('/api/households/' + encodeURIComponent(id)).then(function (res) {
      var h = res.household;
      S.household = h; S.profile = JSON.parse(JSON.stringify(h.profile)); S.savedProfile = JSON.parse(JSON.stringify(h.profile));
      var order = Object.keys(S.qById);
      S.history = order.filter(function (q) { return S.profile[q] !== undefined; });
      S.skipped = []; S.demoId = null; S.demoSteps = null; S.selected = null; S.have = {}; S.expanded = {};
      renderDemoButtons();
      switchTab('find');
      toast(t('opened', { name: hhName(h) }));
      return refresh();
    }).catch(fail);
  }

  // ------------------------------------------------------------------ about
  function renderAbout() {
    var pk = S.schemes.pm_kisan;
    var ev = S.evalData;
    var evalHtml = '<p class="muted small">' + esc(t('eval_missing')) + '</p>';
    if (ev && ev.available !== false && ev.questionnaire) {
      evalHtml = '<table class="tbl"><tr><th>' + esc(t('strategy')) + '</th><th>' + esc(t('avg_q')) + '</th><th>' + esc(t('median')) + '</th><th>' + esc(t('max')) + '</th><th>' + esc(t('accuracy')) + '</th></tr>' +
        ev.questionnaire.strategies.map(function (s) {
          return '<tr><td>' + esc(s.label) + '</td><td class="hot">' + s.mean + '</td><td>' + s.median + '</td><td>' + s.max + '</td><td>' + Math.round(s.accuracy * 100) + '%</td></tr>';
        }).join('') + '<tr><td>' + esc(t('full_form_row')) + '</td><td>' + ev.questionnaire.full_form + '</td><td>' + ev.questionnaire.full_form + '</td><td>' + ev.questionnaire.full_form + '</td><td>100%</td></tr></table>' +
        '<p class="small muted">' + esc(ev.questionnaire.population_note) + '</p>' +
        '<p class="small">Search hit@1: <b>' + Math.round(ev.search.hit_at_1 * 100) + '%</b> · hit@3: <b>' + Math.round(ev.search.hit_at_3 * 100) + '%</b> (' + ev.search.queries + ' queries) · ' +
        'evaluate: <b>' + ev.latency.evaluate_ms.mean + ' ms</b> · next question: <b>' + ev.latency.next_question_ms.mean + ' ms</b></p>';
    }
    var params = S.meta ? Object.keys(S.meta.params).map(function (k) {
      var p = S.meta.params[k];
      return '<li><b>' + esc(k) + '</b> = ' + esc(p.value) + ' — <span class="muted">' + esc(p.note) + '</span></li>';
    }).join('') : '';
    $('#about').innerHTML =
      '<div class="card"><h2>' + esc(t('about_rules')) + '</h2><p class="small">' + esc(t('about_rules_body')) + '</p>' +
      '<pre class="code">' + esc(JSON.stringify(pk ? pk.rule : {}, null, 1)) + '</pre></div>' +
      '<div class="card"><h2>' + esc(t('about_q')) + '</h2><p class="small">' + esc(t('about_q_body')) + '</p>' +
      '<div class="formula">IG(q) = Σ<sub>s∈open</sub> [ H(p<sub>s</sub>) − Σ<sub>a</sub> P(q=a) · H(p<sub>s</sub> | q=a) ]<br>H(p) = −p log₂p − (1−p) log₂(1−p)</div>' +
      (ev && ev.questionnaire ? '<h3 style="margin-top:12px">' + esc(t('curve_title')) + '</h3><div class="chart">' + curveChart(ev.questionnaire.discovery_curve) + '</div>' : '') + '</div>' +
      '<div class="card"><h2>' + esc(t('about_eval')) + '</h2>' + evalHtml + '</div>' +
      '<div class="card"><h2>' + esc(t('about_search')) + '</h2><p class="small">' + esc(t('about_search_body')) + '</p>' +
      '<div class="formula">w(t,d) = (1 + ln tf) · (ln((N+1)/(df+1)) + 1),  score = cos(q, d)</div></div>' +
      '<div class="card" style="grid-column:1/-1"><h2>' + esc(t('about_limits')) + '</h2><p class="small">' + esc(t('about_limits_body')) + '</p><ul class="small">' + params + '</ul></div>';
  }

  // ------------------------------------------------------------------ tabs + mode
  function switchTab(tab) {
    if (tab === 'village' && S.mode !== 'worker') tab = 'find';
    S.tab = tab;
    $all('#tabs button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    $all('section.tab').forEach(function (s) { s.classList.toggle('on', s.id === 'tab-' + tab); });
    if (tab === 'village') loadVillage();
    if (tab === 'about') {
      api('/api/evaluation').then(function (d) { S.evalData = d; renderAbout(); }).catch(function () { renderAbout(); });
      renderAbout();
    }
    if (tab === 'search' && !$('#search-results').innerHTML) runSearch(EXAMPLES[0]);
  }
  function setMode(m) {
    S.mode = m; store('mode', m);
    $('#tabs button[data-tab="village"]').classList.toggle('hidden', m !== 'worker');
    if (m !== 'worker' && S.tab === 'village') switchTab('find');
    applyI18n(); renderAnswers(); renderTracker();
  }
  function setLang(l) {
    S.lang = l; store('lang', l);
    applyI18n(); renderDemoButtons(); renderFind(); renderChecklist(); renderPickList(); renderTracker();
    if (S.tab === 'about') renderAbout();
    if (S.tab === 'village') loadVillage();
    if (S.tab === 'search' && $('#search-input').value) runSearch($('#search-input').value);
  }

  // ------------------------------------------------------------------ events
  function bind() {
    $('#lang-seg').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) setLang(b.getAttribute('data-lang')); });
    $('#mode-seg').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) setMode(b.getAttribute('data-mode')); });
    $('#tabs').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) switchTab(b.getAttribute('data-tab')); });
    $('#speak-toggle').addEventListener('click', function () {
      S.speakOn = !S.speakOn;
      this.setAttribute('aria-pressed', S.speakOn ? 'true' : 'false');
      toast(S.speakOn ? t('speech_on') : t('speech_off'));
      if (S.speakOn) speakQuestion(); else { try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) { /* ignore */ } }
    });
    $('#demo-row').addEventListener('click', function (e) { var b = e.target.closest('[data-demo]'); if (b) loadDemo(b.getAttribute('data-demo')); });
    $('#qcard').addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || b.disabled || !S.next && !b.getAttribute('data-act')) return;
      var act = b.getAttribute('data-act');
      if (act === 'back') return back();
      if (act === 'restart') return restart();
      if (act === 'docs') return switchTab('check');
      if (act === 'speakq') return speakQuestion();
      if (!S.next) return;
      var q = S.next.question;
      if (act === 'skip') return skip(q.id);
      if (b.hasAttribute('data-ans')) return answer(q.id, b.getAttribute('data-ans') === 'true');
      if (b.hasAttribute('data-opt')) return answer(q.id, q.options[+b.getAttribute('data-opt')].value);
    });
    document.addEventListener('keydown', function (e) {
      if (S.tab !== 'find' || !S.next || e.target.tagName === 'INPUT') return;
      var q = S.next.question;
      if (q.type === 'bool' && (e.key === 'y' || e.key === 'n')) answer(q.id, e.key === 'y');
    });
    function cardClick(e) {
      var b = e.target.closest('button[data-act]');
      if (!b) return;
      var id = b.getAttribute('data-id'), act = b.getAttribute('data-act');
      if (act === 'why' || act === 'apply') {
        S.expanded[id] = S.expanded[id] === act ? null : act;
        if (S.tab === 'search') runSearch($('#search-input').value); else renderResults();
      } else if (act === 'speak') {
        var r = (S.ev && S.ev.results.filter(function (x) { return x.id === id; })[0]) || null;
        var s = S.schemes[id];
        speak(L(s.name) + '. ' + (r && S.history.length ? statusLabel(r.status) + '. ' + L(r.reason) + '. ' : '') + L(s.summary) + ' ' + L(s.apply));
      } else if (act === 'pick') {
        togglePick(id);
      }
    }
    $('#results').addEventListener('click', cardClick);
    $('#search-results').addEventListener('click', cardClick);
    $('#filters').addEventListener('click', function (e) { var b = e.target.closest('[data-filter]'); if (b) { S.filter = b.getAttribute('data-filter'); renderResults(); } });
    $('#speak-results').addEventListener('click', function () {
      if (!S.ev) return;
      var el = S.ev.results.filter(function (r) { return r.status === 'eligible'; });
      speak(t('kpi_eligible') + ': ' + el.length + '. ' + el.map(function (r) { return L(r.name) + ', ' + L(r.benefit.label); }).join('. ') +
        '. ' + t('kpi_annual') + ' ' + inr(S.ev.benefits.annual_total));
    });
    $('#save-family-btn').addEventListener('click', function () {
      if (S.household) return saveFamily();
      switchTab('check');
      setTimeout(function () { $('#fam-name').focus(); }, 50);
    });
    $('#save-btn').addEventListener('click', saveFamily);
    $('#pick-list').addEventListener('change', function (e) { var c = e.target.closest('[data-pick]'); if (c) togglePick(c.getAttribute('data-pick')); });
    $('#doc-list').addEventListener('change', function (e) { var c = e.target.closest('[data-have]'); if (c) S.have[c.getAttribute('data-have')] = c.checked; });
    $('#print-btn').addEventListener('click', printChecklist);
    $('#tracker').addEventListener('click', function (e) { var b = e.target.closest('[data-track]'); if (b) setTrack(b.getAttribute('data-track'), b.getAttribute('data-status')); });
    $('#search-form').addEventListener('submit', function (e) { e.preventDefault(); runSearch($('#search-input').value); });
    $('#examples').innerHTML = EXAMPLES.map(function (x) { return '<button class="chip" type="button" data-ex="' + esc(x) + '">' + esc(x) + '</button>'; }).join('');
    $('#examples').addEventListener('click', function (e) { var b = e.target.closest('[data-ex]'); if (b) runSearch(b.getAttribute('data-ex')); });
    $('#village-select').addEventListener('change', function () { S.villageName = this.value; loadVillage(); });
    $('#load-village').addEventListener('click', function () {
      api('/api/demo/village', {}).then(function (r) { toast(t('village_loaded', { n: r.households })); S.villageName = r.village; loadVillage(); }).catch(fail);
    });
    $('#clear-all').addEventListener('click', function () {
      var ok = true;
      try { ok = window.confirm(t('confirm_clear')); } catch (e) { ok = true; }
      if (!ok) return;
      api('/api/demo/reset', {}).then(function () { toast(t('cleared')); S.household = null; S.villageName = ''; loadVillage(); renderAnswers(); renderTracker(); }).catch(fail);
    });
    $('#hh-table').addEventListener('click', function (e) { var b = e.target.closest('[data-open]'); if (b) openHousehold(b.getAttribute('data-open')); });
  }

  // ------------------------------------------------------------------ boot
  function init() {
    var l = load('lang'); if (l === 'ta' || l === 'en') S.lang = l;
    var m = load('mode'); if (m === 'worker' || m === 'family') S.mode = m;
    if (/[?&]lang=ta/.test(location.search)) S.lang = 'ta';
    if (/[?&]mode=worker/.test(location.search)) S.mode = 'worker';
    bind();
    applyI18n();
    $('#tabs button[data-tab="village"]').classList.toggle('hidden', S.mode !== 'worker');
    Promise.all([api('/api/meta'), api('/api/schemes'), api('/api/questions'), api('/api/demo')]).then(function (r) {
      S.meta = r[0];
      r[1].schemes.forEach(function (s) { S.schemes[s.id] = s; });
      r[2].questions.forEach(function (q) { S.qById[q.id] = q; });
      S.demo = r[3].households;
      renderDemoButtons();
      return refresh();
    }).then(function () {
      var tab = (location.hash || '').replace('#', '');
      if (['search', 'check', 'village', 'about'].indexOf(tab) >= 0) switchTab(tab);
    }).catch(fail);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

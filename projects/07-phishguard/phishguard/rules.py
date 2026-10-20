"""Hand-written rule layer for India-specific scam patterns.

Each rule has a weight in (0, 1) that enters the noisy-OR risk score directly,
a short explanation and concrete advice.  Rules can be negated by nearby
words ("do not share your OTP" must not fire the OTP-request rule).
"""
import re

from .extract import find_urls

# Words that, right before/after a match, turn a request into a warning.
_NEG_BEFORE = re.compile(
    r"(\bnot\b|\bnever\b|\bdon'?t\b|\bdont\b|\bno one\b|\bnobody\b|\bmat\b|\bkabhi\b|\bwill never\b|\bnever ask)"
    r"[^.!?\n]{0,25}$",
    re.IGNORECASE,
)
_NEG_AFTER = re.compile(r"^[^.!?\n]{0,25}?(\bna\b|\bnahi\b|\bnahin\b|\bmat\b|\bvendam\b|\bkoodathu\b|\bwith anyone\b)",
                        re.IGNORECASE)


class Rule:
    def __init__(self, rid, title, category, weight, patterns, advice, negatable=False, scan_urls=False):
        self.id = rid
        self.title = title
        self.category = category
        self.weight = weight
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.advice = advice
        self.negatable = negatable
        self.scan_urls = scan_urls

    def find(self, text):
        hits = []
        for pat in self.patterns:
            for m in pat.finditer(text):
                if self.negatable and _negated(text, m.start(), m.end()):
                    continue
                if any(h["start"] <= m.start() < h["end"] for h in hits):
                    continue
                hits.append({"start": m.start(), "end": m.end(), "text": m.group(0)})
        hits.sort(key=lambda h: h["start"])
        return hits


def _negated(text, start, end):
    before = text[max(0, start - 40):start]
    after = text[end:end + 30]
    inside = text[start:end]
    return bool(_NEG_BEFORE.search(before) or _NEG_AFTER.search(after)
                or re.search(r"\b(not|never|don'?t|mat|nahi|nahin|vendam)\b", inside, re.IGNORECASE))


_ACC = r"(?:account|a/c|acct|card|sim|wallet|connection|number|yono|net ?banking|upi id|profile)"

RULES = [
    Rule("otp_request", "Asks you to share an OTP", "credential theft", 0.60, [
        r"\b(share|send|tell|forward|give|provide|read out|confirm|bata\w*|bhej\w*|sollunga|sollu|anuppu\w*|de do|dijiye)\b[^.!?\n]{0,25}?\b(otp|one[- ]time password|verification code)\b",
        r"\b(otp|verification code)\b[^.!?\n]{0,50}?\b(share|send|tell|forward|bata\w*|bhej\w*|sollunga|anuppu\w*|de do|dijiye|reply)\b",
    ], "No bank, courier or company employee ever needs your OTP. Never read it out or forward it.", negatable=True),

    Rule("sensitive_info", "Requests PIN / CVV / card or banking credentials", "credential theft", 0.55, [
        r"\b(cvv|atm pin|upi pin|mpin|card number|card details|debit card details|net ?banking (password|credentials|id)|expiry date|login credentials)\b",
    ], "Never type your UPI PIN, CVV or net-banking password on a link someone sent you.", negatable=True),

    Rule("upi_collect", "UPI 'collect' trick - PIN needed to *receive* money", "UPI fraud", 0.60, [
        r"\b(collect request|payment request|money request)\b",
        r"\b(enter|type|put|daal\w*|dal\w*|podunga)\b[^.!?\n]{0,15}\b(upi )?pin\b[^.!?\n]{0,25}\b(receive|get|claim|accept|paise|credit\w*|refund)\b",
        r"\b(receive|get|claim|accept)\b[^.!?\n]{0,30}\b(enter|type|daal\w*)\b[^.!?\n]{0,15}\b(upi )?pin\b",
        r"\bscan (the |this )?(qr|qr code)\b[^.!?\n]{0,25}\b(receive|get|claim)\b",
        r"\bapprove (the |this )?(request|payment)\b",
    ], "You never need to enter your UPI PIN or scan a QR code to RECEIVE money. Decline the request."),

    Rule("kyc_update", "KYC / PAN / Aadhaar 'update' pressure", "impersonation", 0.45, [
        r"\b(e-?kyc|re-?kyc|kyc|pan(?: card)?|aadhaa?r)\b[^.!?\n]{0,40}?\b(update\w*|expired?|pending|verif\w*|suspend\w*|block\w*|incomplete|not updated|link\w*)\b",
        r"\b(update|complete|verify|submit)\w*\b[^.!?\n]{0,20}\b(kyc|pan(?: card)?|aadhaa?r)\b",
    ], "Banks do KYC only in the branch or inside their official app. Ignore SMS links that ask for KYC."),

    Rule("account_block", "Threatens to block / suspend an account or SIM", "fear", 0.35, [
        _ACC + r"[^.!?\n]{0,35}?\b(blocked|suspended|deactivated|closed|frozen|disabled|barred|locked|block|suspend)\b",
        r"\b(block|band|suspend|close)\s+(ho jayega|ho jaayega|ho jayegi|aagidum|aagum|aayidum|panniduvom)\b",
    ], "Threats of blocking 'within hours' are a pressure tactic. Call the number printed on your card or passbook."),

    Rule("electricity_cut", "Electricity disconnection 'tonight' threat", "utility scam", 0.50, [
        r"\b(electricity|power|bijli|eb|light|current|meter)\b[^\n]{0,60}?\b(disconnect\w*|kat jayega|kat jaayega|katega|kaat (di|diya) jayega|cut aagum|cut pannuvom|cut tonight|cut today)\b",
        r"\bprevious month bill (was |is )?not (been )?updated\b",
    ], "Electricity boards do not disconnect over SMS/WhatsApp calls to a mobile number. Pay only via the board's official app or website."),

    Rule("prize_lottery", "Lottery / lucky draw / prize money", "too good to be true", 0.45, [
        r"\b(lottery|lucky draw|jackpot|kbc|kaun banega crorepati|lucky winner|bumper prize|prize money)\b",
        r"\b(won|win|winner|jeeta|jeete|jeeti)\b[^.!?\n]{0,40}?(\b(rs\.?|inr|lakhs?|crores?|iphone|car|bike|cash)\b|₹)",
    ], "You cannot win a contest you never entered. Never pay a 'fee' or 'tax' to claim a prize."),

    Rule("job_fee", "Asks for an upfront fee (registration / processing)", "advance-fee scam", 0.55, [
        r"\b(registration|processing|joining|security|training|refundable|onboarding|verification|laptop|kit|document)\s+(fee|fees|charges?|deposit|amount)\b",
        r"\bpay\b[^.!?\n]{0,30}\b(to (confirm|book|secure|receive) (your )?(slot|seat|offer|joining|letter|job))\b",
    ], "Genuine employers and internships never charge you to join. Verify the offer on the company's official careers page."),

    Rule("easy_money", "Easy money / part-time task offer", "job scam", 0.35, [
        r"\b(part[- ]?time job|work from home job|wfh job|daily (income|earning|payout)|earn (daily|per day|upto|up to)|per day earn|like (youtube )?videos?( and| &)? earn|simple (online )?tasks?|task[- ]based (job|work))\b",
        r"\bearn\b[^.!?\n]{0,15}(rs\.?|₹)\s?\d[\d,]*\s?(daily|per day|/day|a day|weekly)",
    ], "'Like videos and earn' tasks start with small payouts and end with you 'investing' and losing money."),

    Rule("parcel_hold", "Parcel held / address problem / customs", "delivery scam", 0.40, [
        r"\b(parcel|package|shipment|courier|consignment)\b[^.!?\n]{0,50}?\b(held|on hold|pending|customs|undeliver\w*|returned|address (is )?(incomplete|invalid|wrong|not clear)|incomplete address|re-?deliver\w*|failed|seized)\b",
    ], "Check delivery status only in the shop's or courier's official app using your order number."),

    Rule("refund_bait", "Refund / cashback that needs a click", "too good to be true", 0.35, [
        r"\b(refund|cashback|tax refund|reward points?|bonus|gift)\b[^.!?\n]{0,40}?\b(click|claim|tap|redeem|visit|verify|expir\w*)\b",
    ], "Real refunds come back automatically to your original payment method - no link or PIN needed."),

    Rule("authority_threat", "Police / CBI / customs / 'digital arrest' threat", "impersonation", 0.55, [
        r"\b(digital arrest|cbi|narcotics|ncb|customs (officer|department|duty)|cyber ?cell|crime branch|arrest warrant|money laundering|drugs? (were |was )?found|illegal (items|drugs)|trai|ed officer|legal action|fir (against|registered))\b",
    ], "Police and agencies never arrest anyone over a video call and never ask for money to 'clear' a case. Hang up and call 1930."),

    Rule("remote_access", "Asks you to install a screen-sharing app", "account takeover", 0.60, [
        r"\b(anydesk|any desk|teamviewer|team viewer|quick ?support|rustdesk|airdroid|screen ?shar\w*)\b",
    ], "Never install remote-access apps for a stranger - they can watch your OTPs and banking apps."),

    Rule("apk_install", "Asks you to install an APK / app from a link", "malware", 0.55, [
        r"\.apk\b",
        r"\b(install|download)\b[^.!?\n]{0,25}\b(apk|this app|the app from|app from (this|the) link)\b",
    ], "Install apps only from the Play Store / App Store. Fake 'bank' APKs read your SMS and steal OTPs.", scan_urls=True),

    Rule("investment_bait", "Guaranteed returns / crypto / trading group", "investment scam", 0.45, [
        r"\b(double (your|the) money|guaranteed (returns?|profit|income)|\d+\s?% (daily|weekly|monthly) (returns?|profit)|crypto ?(investment|trading)|trading tips|stock tips|investment plan|telegram (group|channel)|join (our )?telegram|vip group)\b",
    ], "Nobody can guarantee returns. Check whether the adviser is SEBI-registered before investing."),

    Rule("loan_bait", "Instant loan without documents", "loan app scam", 0.40, [
        r"\b(instant|pre-?approved|easy)\s+(personal )?loan\b[^.!?\n]{0,50}\b(without|no)\b[^.!?\n]{0,15}\b(documents?|cibil|paperwork|verification)\b",
        r"\bloan\b[^.!?\n]{0,40}\b(without|no) (documents?|cibil|paperwork)\b",
    ], "Illegal loan apps harvest your contacts and harass you. Borrow only from RBI-regulated lenders."),

    Rule("urgency", "Urgency / deadline pressure", "pressure", 0.15, [
        r"\b(urgent(ly)?|immediately|within \d+\s?(hours?|hrs?|minutes?|mins?)|today itself|last (chance|warning|reminder|date today)|act now|final notice|turant|jaldi|abhi|udane|seekiram|before midnight|tonight|expires? today|in \d+ hours)\b",
    ], "Scammers rush you so you don't think. Pause and verify through an official channel."),
]

RULES_BY_ID = {r.id: r for r in RULES}


def mask_urls(text):
    """Blank out URLs (keeping offsets) so words inside a link, such as
    'update-aadhaar.html' on an official site, do not fire text rules."""
    chars = list(text)
    for u in find_urls(text):
        for i in range(u["start"], u["end"]):
            chars[i] = " "
    return "".join(chars)


def evaluate(text):
    """Return a list of fired rules with their matches, strongest first."""
    fired = []
    masked = mask_urls(text)
    for rule in RULES:
        hits = rule.find(text if rule.scan_urls else masked)
        if hits:
            fired.append({
                "id": rule.id, "title": rule.title, "category": rule.category,
                "weight": rule.weight, "advice": rule.advice, "matches": hits,
            })
    fired.sort(key=lambda r: -r["weight"])
    return fired


def rule_score(fired):
    """Noisy-OR of the fired rule weights: 1 - prod(1 - w)."""
    keep = 1.0
    for r in fired:
        keep *= 1.0 - r["weight"]
    return 1.0 - keep

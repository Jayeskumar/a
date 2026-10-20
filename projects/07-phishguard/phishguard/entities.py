"""Heuristic risk scores for phone numbers and UPI IDs found in a message.

There is no ML here (we have no labelled phone/UPI data); each score comes
with the reason that produced it so the user can judge it.
"""
import re

OFFICIAL_CONTEXT = re.compile(
    r"\b(bank|sbi|hdfc|icici|axis|kotak|kyc|customer care|electricity|eb|bijli|officer|police|cbi|"
    r"customs|courier|fedex|parcel|trai|income tax|refund|manager|hr|head office|lottery|kbc)\b",
    re.IGNORECASE,
)
CALL_CONTEXT = re.compile(r"\b(call|contact|whatsapp|message|reach|dial|press)\b", re.IGNORECASE)

SCAM_UPI_WORDS = ["kyc", "refund", "reward", "prize", "lottery", "lucky", "cashback", "support", "care",
                  "help", "helpdesk", "customer", "bank", "sbi", "hdfc", "icici", "govt", "gov", "scheme",
                  "electricity", "bill", "tax", "jobs", "hr", "recruit", "loan", "offer", "claim", "dept"]
PAY_CONTEXT = re.compile(r"\b(pay|send|transfer|fee|charges?|deposit|bhej\w*|anuppu\w*|duty)\b", re.IGNORECASE)


def score_phone(phone, text):
    digits = phone["digits"]
    if digits.startswith("1800"):
        return 0.10, "Toll-free 1800 number - usually official, but confirm it on the company's website."
    official = OFFICIAL_CONTEXT.search(text)
    call = CALL_CONTEXT.search(text)
    if official and call:
        return 0.75, "A personal mobile number presented as a bank/utility/officer line. Real organisations use published helplines."
    if official:
        return 0.50, "A mobile number in a message that mentions a bank, refund or authority."
    if call:
        return 0.30, "Unknown mobile number you are asked to contact."
    return 0.15, "Mobile number with no official context."


def score_upi(upi, text):
    local, _, psp = upi["value"].lower().partition("@")
    words = [w for w in SCAM_UPI_WORDS if w in local]
    pay = PAY_CONTEXT.search(text)
    if words and pay:
        return 0.85, "UPI ID named like a helpdesk/refund/prize account ('{}') and you are asked to pay it. UPI payments cannot be reversed.".format(", ".join(words[:3]))
    if words:
        return 0.60, "UPI ID named like an official account ('{}'). Banks and companies don't collect money through such IDs.".format(", ".join(words[:3]))
    if pay:
        return 0.35, "You are asked to pay an unknown UPI ID. Check the registered name your app shows before paying."
    return 0.15, "UPI ID mentioned. Verify the name shown in your UPI app."

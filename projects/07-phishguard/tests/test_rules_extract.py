import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phishguard import rules, extract, entities  # noqa: E402


def fired(text):
    return {r["id"] for r in rules.evaluate(text)}


class RuleLayerTest(unittest.TestCase):
    def test_positive_patterns(self):
        cases = {
            "otp_request": "Sir please share the OTP you just received",
            "upi_collect": "Enter your UPI PIN to receive Rs 5000 refund",
            "kyc_update": "Your KYC has expired, update now",
            "account_block": "Your SBI account will be blocked today",
            "electricity_cut": "Your electricity power will be disconnected tonight at 9.30",
            "prize_lottery": "You won Rs 25 lakh in KBC lucky draw",
            "job_fee": "Pay refundable registration fee Rs 1999 to confirm your slot",
            "easy_money": "Part time job, earn daily by liking videos",
            "parcel_hold": "Your parcel is on hold due to incomplete address",
            "authority_threat": "You are under digital arrest, CBI will call",
            "remote_access": "Install AnyDesk and share the code",
            "sensitive_info": "Send your card number and CVV",
            "investment_bait": "Guaranteed returns, join our Telegram group",
            "loan_bait": "Instant loan without documents in 5 minutes",
            "urgency": "Reply immediately",
        }
        for rid, text in cases.items():
            self.assertIn(rid, fired(text), "{} should fire on: {}".format(rid, text))

    def test_hinglish_tanglish(self):
        self.assertIn("electricity_cut", fired("Aapka bijli connection aaj raat kat jayega"))
        self.assertIn("account_block", fired("Unga account block aagum"))
        self.assertIn("otp_request", fired("ek OTP aaya hoga, please bata do"))

    def test_negations_do_not_fire(self):
        self.assertNotIn("otp_request", fired("123456 is your OTP. Do not share this OTP with anyone."))
        self.assertNotIn("sensitive_info", fired("Never share your UPI PIN or CVV with anyone."))
        self.assertNotIn("otp_request", fired("OTP kisi ko mat bhejna"))

    def test_legit_messages_are_quiet(self):
        self.assertEqual(fired("Congrats! You won first prize in the debate. Collect your certificate."), set())
        self.assertEqual(fired("Power shutdown on Friday 9 AM to 2 PM for maintenance work."), set())
        self.assertEqual(fired("Your Amazon package will be delivered today."), set())

    def test_urls_are_masked_except_for_apk(self):
        self.assertNotIn("kyc_update", fired("see https://uidai.gov.in/en/my-aadhaar/update-aadhaar.html"))
        self.assertIn("apk_install", fired("get it at http://x1.top/SBI_Rewards.apk"))

    def test_spans_point_at_text(self):
        text = "Hello. Your KYC has expired!"
        r = [x for x in rules.evaluate(text) if x["id"] == "kyc_update"][0]
        m = r["matches"][0]
        self.assertEqual(text[m["start"]:m["end"]], m["text"])
        self.assertTrue(m["text"].lower().startswith("kyc"))

    def test_rule_score_noisy_or(self):
        self.assertAlmostEqual(rules.rule_score([{"weight": 0.5}, {"weight": 0.5}]), 0.75)
        self.assertEqual(rules.rule_score([]), 0.0)


class ExtractTest(unittest.TestCase):
    def test_urls(self):
        text = "Visit bit.ly/abc, or https://sbi-kyc.xyz/login. Rs.500 e.g. not links; mail me at a.b@gmail.com"
        vals = [u["value"] for u in extract.find_urls(text)]
        self.assertEqual(vals, ["bit.ly/abc", "https://sbi-kyc.xyz/login"])
        for u in extract.find_urls(text):
            self.assertEqual(text[u["start"]:u["end"]], u["value"])

    def test_upi_and_email(self):
        text = "Pay to kyc.update@ybl or email help@sbi.co.in"
        self.assertEqual([u["value"] for u in extract.find_upi_ids(text)], ["kyc.update@ybl"])
        self.assertEqual([e["value"] for e in extract.find_emails(text)], ["help@sbi.co.in"])

    def test_phones(self):
        text = "Call +91 98765 43210 or 9123456780 or toll free 1800 123 4567, OTP 482913"
        digits = [p["digits"] for p in extract.find_phones(text)]
        self.assertEqual(digits, ["919876543210", "9123456780", "18001234567"])

    def test_entity_scores(self):
        text = "Contact our electricity officer 9876543210"
        ph = extract.find_phones(text)[0]
        self.assertGreaterEqual(entities.score_phone(ph, text)[0], 0.7)
        tf = extract.find_phones("Call 1800 123 4567")[0]
        self.assertLess(entities.score_phone(tf, "Call 1800 123 4567")[0], 0.2)
        u = {"value": "refund.help@ybl"}
        self.assertGreaterEqual(entities.score_upi(u, "pay fee to refund.help@ybl")[0], 0.8)
        self.assertLess(entities.score_upi({"value": "priya22@okaxis"}, "sent to priya22@okaxis")[0], 0.3)


if __name__ == "__main__":
    unittest.main()

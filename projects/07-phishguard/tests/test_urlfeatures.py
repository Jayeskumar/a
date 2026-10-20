import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phishguard import urlfeatures as uf  # noqa: E402


def feats(url):
    vec, info = uf.extract(url)
    return dict(zip(uf.FEATURE_NAMES, vec)), info


class UrlFeatureTest(unittest.TestCase):
    def test_vector_shape_and_range(self):
        for u in ["https://www.irctc.co.in/nget/train-search", "http://1.2.3.4/a//b.apk?x=1&y=2&z=3&w=4",
                  "xn--amzon-abc.xyz", "", "http://[::1]:8080/x", "https://a.b.c.d.e.f.g.h.example.com/" + "x" * 300]:
            vec, _ = uf.extract(u)
            self.assertEqual(len(vec), len(uf.FEATURE_NAMES))
            self.assertTrue(all(0.0 <= v <= 1.0 for v in vec), u)

    def test_parse_and_registered_domain(self):
        p = uf.parse("HTTPS://User@Retail.OnlineSBI.sbi:8443/login?x=1")
        self.assertEqual(p["host"], "retail.onlinesbi.sbi")
        self.assertEqual(p["port"], "8443")
        self.assertEqual(p["userinfo"], "User")
        self.assertEqual(uf.registered_domain("www.irctc.co.in"), "irctc.co.in")
        self.assertEqual(uf.registered_domain("a.b.sbi-kyc.xyz"), "sbi-kyc.xyz")

    def test_official_domain(self):
        f, info = feats("https://retail.onlinesbi.sbi/retail/login.htm")
        self.assertEqual(f["official_domain"], 1.0)
        self.assertEqual(f["brand_in_host_unofficial"], 0.0)
        self.assertEqual(f["https"], 1.0)
        self.assertEqual(info["registered_domain"], "onlinesbi.sbi")

    def test_brand_misuse_and_suspicious_tld(self):
        f, info = feats("http://sbi-kyc-update.xyz/login.php")
        self.assertEqual(f["brand_in_host_unofficial"], 1.0)
        self.assertEqual(f["suspicious_tld"], 1.0)
        self.assertEqual(f["explicit_http"], 1.0)
        self.assertGreater(f["path_keywords"], 0)
        self.assertIn("sbi", info["brands"])
        f2, _ = feats("https://example.com/hdfc/verify")
        self.assertEqual(f2["brand_in_path_unofficial"], 1.0)

    def test_ip_at_trick_port_redirect(self):
        f, _ = feats("http://www.onlinesbi.sbi@185.22.14.7:8080/x//login")
        self.assertEqual(f["has_at"], 1.0)
        self.assertEqual(f["ip_host"], 1.0)
        self.assertEqual(f["has_port"], 1.0)
        self.assertEqual(f["redirect_slash"], 1.0)
        self.assertEqual(f["official_domain"], 0.0)

    def test_punycode_and_non_ascii(self):
        self.assertEqual(feats("https://xn--amzon-hra.com/login")[0]["punycode"], 1.0)
        self.assertEqual(feats("https://аmazon.com/")[0]["non_ascii"], 1.0)  # Cyrillic a

    def test_lookalikes(self):
        self.assertEqual(feats("https://amaz0n-offers.shop/")[1]["lookalike_of"], "amazon")
        self.assertEqual(feats("http://paytrn.com/kyc")[1]["lookalike_of"], "paytm")
        self.assertEqual(feats("https://flipkarrt.in/")[1]["lookalike_of"], "flipkart")
        self.assertEqual(feats("https://www.amazon.in/dp/X")[0]["lookalike_brand"], 0.0)
        self.assertEqual(feats("https://apply.example.com/")[0]["lookalike_brand"], 0.0)

    def test_shortener_apk_gov(self):
        self.assertEqual(feats("bit.ly/3xYz")[0]["shortener"], 1.0)
        self.assertEqual(feats("bit.ly/3xYz")[0]["https"], 0.0)
        self.assertEqual(feats("http://x1.top/SBI_Rewards.apk")[0]["apk_exe"], 1.0)
        self.assertEqual(feats("https://pmkisan-gov.online/claim")[0]["gov_lookalike"], 1.0)
        self.assertEqual(feats("https://kovaiclinic.com/")[0]["gov_lookalike"], 0.0)  # 'nic' inside 'clinic'
        f, _ = feats("https://uidai.gov.in/en/my-aadhaar/update-aadhaar.html")
        self.assertEqual(f["restricted_tld"], 1.0)
        self.assertEqual(f["gov_lookalike"], 0.0)

    def test_helpers(self):
        self.assertEqual(uf.edit_distance("kitten", "sitting"), 3)
        self.assertEqual(uf.edit_distance("paytm", "paytm"), 0)
        self.assertAlmostEqual(uf.shannon_entropy("aaaa"), 0.0)
        self.assertAlmostEqual(uf.shannon_entropy("abcd"), 2.0)
        self.assertEqual(uf.deglyph("amaz0n"), "amazon")
        self.assertTrue(uf.is_ip("10.0.0.1"))
        self.assertFalse(uf.is_ip("sbi.co.in"))


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logsentinel.signatures import decode, scan_event, RULES
from logsentinel.parsers import parse_web_line


def web(path, ua="Mozilla/5.0", ref="-", status=200):
    line = ('203.0.113.9 - - [15/Oct/2026:12:00:00 +0000] "GET %s HTTP/1.1" %d 10 "%s" "%s"'
            % (path, status, ref, ua))
    return parse_web_line(line)


def cats(ev):
    return {h["category"] for h in scan_event(ev)}


class TestDecode(unittest.TestCase):
    def test_single_url_decode(self):
        self.assertIn("' or '1'='1", decode("%27%20or%20%271%27%3D%271"))

    def test_double_encoding(self):
        # %2527 -> %27 -> '
        self.assertIn("'", decode("%2527"))

    def test_plus_as_space_and_entities(self):
        self.assertIn("<script>", decode("%3Cscript%3E"))
        self.assertIn("<", decode("&lt;"))


class TestSqli(unittest.TestCase):
    def test_encoded_tautology(self):
        self.assertIn("SQL Injection", cats(web("/p?id=1%27%20OR%20%271%27%3D%271")))

    def test_encoded_union_select(self):
        self.assertIn("SQL Injection", cats(web("/p?id=1%20UNION%20SELECT%20pass%20FROM%20users")))

    def test_time_based_blind(self):
        self.assertIn("SQL Injection", cats(web("/p?id=1%27%20AND%20SLEEP%285%29--")))

    def test_benign_not_flagged(self):
        self.assertNotIn("SQL Injection", cats(web("/product?id=42")))
        self.assertNotIn("SQL Injection", cats(web("/search?q=selected+shoes")))


class TestXss(unittest.TestCase):
    def test_encoded_script(self):
        self.assertIn("Cross-Site Scripting", cats(web("/s?q=%3Cscript%3Ealert%281%29%3C%2Fscript%3E")))

    def test_img_onerror(self):
        self.assertIn("Cross-Site Scripting", cats(web("/s?q=%3Cimg%20src%3Dx%20onerror%3Dalert%281%29%3E")))


class TestTraversal(unittest.TestCase):
    def test_encoded_passwd(self):
        self.assertIn("Path Traversal / LFI", cats(web("/f?x=..%2F..%2F..%2Fetc%2Fpasswd")))

    def test_php_filter(self):
        self.assertIn("Path Traversal / LFI", cats(web("/f?x=php://filter/convert.base64-encode/resource=index.php")))


class TestScannerUA(unittest.TestCase):
    def test_sqlmap_ua(self):
        self.assertIn("Scanner / Tool User-Agent", cats(web("/", ua="sqlmap/1.7")))

    def test_gobuster_ua(self):
        self.assertIn("Scanner / Tool User-Agent", cats(web("/x", ua="Mozilla/5.0 (gobuster/3.6)")))

    def test_browser_not_flagged(self):
        self.assertNotIn("Scanner / Tool User-Agent",
                         cats(web("/", ua="Mozilla/5.0 (Windows NT 10.0) Chrome/118")))


class TestCmdi(unittest.TestCase):
    def test_pipe_cat(self):
        self.assertIn("Command Injection", cats(web("/ping?h=127.0.0.1%3B%20cat%20/etc/passwd")))


class TestNonWeb(unittest.TestCase):
    def test_non_web_event(self):
        from logsentinel.parsers import parse_auth_line
        ev = parse_auth_line("Oct 15 01:00:00 h sshd[1]: Failed password for root from 1.2.3.4 port 1 ssh2")
        self.assertEqual(scan_event(ev), [])


if __name__ == "__main__":
    unittest.main()

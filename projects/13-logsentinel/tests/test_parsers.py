import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logsentinel.parsers import (parse_web_line, parse_auth_line, parse_firewall_line,
                                  classify_line, detect_format, parse_text)


class TestWebParser(unittest.TestCase):
    def test_combined(self):
        line = ('203.0.113.5 - - [15/Oct/2026:13:55:36 +0000] '
                '"GET /index.html HTTP/1.1" 200 2326 "https://ref" "Mozilla/5.0"')
        ev = parse_web_line(line)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.kind, "web")
        self.assertEqual(ev.src, "203.0.113.5")
        self.assertEqual(ev.get("method"), "GET")
        self.assertEqual(ev.get("path"), "/index.html")
        self.assertEqual(ev.get("status"), 200)
        self.assertEqual(ev.get("size"), 2326)
        self.assertEqual(ev.ts.hour, 13)

    def test_dash_size_and_no_quotes(self):
        line = '198.51.100.9 - - [15/Oct/2026:00:00:01 +0000] "GET / HTTP/1.1" 304 -'
        ev = parse_web_line(line)
        self.assertEqual(ev.get("size"), 0)
        self.assertEqual(ev.get("status"), 304)

    def test_malformed_returns_none(self):
        for bad in ["", "garbage line", "not a log at all",
                    '1.2.3.4 - - [bad time] "GET /" 200 1',
                    '1.2.3.4 - - [15/Oct/2026:00:00:01 +0000] "GET /" notstatus 1']:
            self.assertIsNone(parse_web_line(bad), bad)


class TestAuthParser(unittest.TestCase):
    def test_failed_password(self):
        ev = parse_auth_line("Oct 15 01:12:03 web01 sshd[2211]: Failed password for root from 203.0.113.66 port 51423 ssh2")
        self.assertEqual(ev.kind, "ssh")
        self.assertEqual(ev.get("outcome"), "fail")
        self.assertEqual(ev.get("user"), "root")
        self.assertEqual(ev.src, "203.0.113.66")
        self.assertFalse(ev.get("invalid_user"))

    def test_invalid_user_failed(self):
        ev = parse_auth_line("Oct 15 01:12:03 web01 sshd[2]: Failed password for invalid user oracle from 192.0.2.7 port 5 ssh2")
        self.assertEqual(ev.get("user"), "oracle")
        self.assertTrue(ev.get("invalid_user"))

    def test_invalid_user_line(self):
        ev = parse_auth_line("Oct 15 01:12:03 web01 sshd[2]: Invalid user admin from 192.0.2.7 port 5")
        self.assertTrue(ev.get("invalid_user"))
        self.assertEqual(ev.get("outcome"), "fail")

    def test_accepted(self):
        ev = parse_auth_line("Oct 15 09:00:00 web01 sshd[9]: Accepted password for alice from 10.0.0.20 port 40000 ssh2")
        self.assertEqual(ev.get("outcome"), "success")
        self.assertEqual(ev.get("user"), "alice")
        self.assertEqual(ev.get("method"), "password")

    def test_sudo(self):
        ev = parse_auth_line("Oct 15 14:00:00 web01 sudo:   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/bin/cat /etc/shadow")
        self.assertEqual(ev.kind, "sudo")
        self.assertEqual(ev.get("ruser"), "deploy")
        self.assertEqual(ev.get("tuser"), "root")
        self.assertIn("/etc/shadow", ev.get("cmd"))

    def test_malformed(self):
        for bad in ["", "random text", "Oct 99 99:99:99 host sshd[1]: nonsense",
                    "Zzz 15 01:00:00 host sshd[1]: Failed password"]:
            self.assertIsNone(parse_auth_line(bad), bad)

    def test_non_ssh_syslog_skipped(self):
        self.assertIsNone(parse_auth_line("Oct 15 01:00:00 web01 cron[9]: job ran"))


class TestFirewallParser(unittest.TestCase):
    def test_ufw(self):
        ev = parse_firewall_line("Oct 15 17:20:00 gw kernel: [123.4] [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.200 DST=10.0.0.5 PROTO=TCP SPT=40000 DPT=22")
        self.assertEqual(ev.kind, "firewall")
        self.assertEqual(ev.src, "203.0.113.200")
        self.assertEqual(ev.get("dst"), "10.0.0.5")
        self.assertEqual(ev.get("dport"), 22)
        self.assertEqual(ev.get("action"), "BLOCK")

    def test_malformed(self):
        for bad in ["", "no kv here", "Oct 15 17:20:00 gw kernel: hello world"]:
            self.assertIsNone(parse_firewall_line(bad), bad)


class TestAutoDetect(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_line('1.2.3.4 - - [15/Oct/2026:00:00:01 +0000] "GET / HTTP/1.1" 200 1 "-" "x"'), "web")
        self.assertEqual(classify_line("Oct 15 01:00:00 h sshd[1]: Failed password for root from 1.2.3.4 port 1 ssh2"), "auth")
        self.assertEqual(classify_line("Oct 15 01:00:00 h kernel: [1.2] SRC=1.2.3.4 DST=1.2.3.5 PROTO=TCP DPT=22"), "firewall")
        self.assertIsNone(classify_line("   "))

    def test_detect_majority(self):
        lines = ['1.2.3.4 - - [15/Oct/2026:00:00:01 +0000] "GET / HTTP/1.1" 200 1 "-" "x"'] * 5
        self.assertEqual(detect_format(lines), "web")

    def test_mixed_file_parses_each_line(self):
        text = "\n".join([
            '203.0.113.5 - - [15/Oct/2026:13:00:00 +0000] "GET / HTTP/1.1" 200 2 "-" "x"',
            "Oct 15 13:00:01 web01 sshd[9]: Failed password for root from 203.0.113.66 port 5 ssh2",
            "Oct 15 13:00:02 gw kernel: [1.2] [UFW BLOCK] IN=eth0 SRC=203.0.113.200 DST=10.0.0.5 PROTO=TCP DPT=22",
            "",
            "total garbage",
        ])
        events, stats = parse_text(text)
        self.assertEqual(stats["parsed"], 3)
        self.assertEqual(stats["malformed"], 1)
        self.assertEqual(stats["blank"], 1)
        kinds = sorted(e.kind for e in events)
        self.assertEqual(kinds, ["firewall", "ssh", "web"])


if __name__ == "__main__":
    unittest.main()

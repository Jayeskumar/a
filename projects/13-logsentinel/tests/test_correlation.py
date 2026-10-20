import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logsentinel.events import Event
from logsentinel import correlation as corr
from logsentinel.correlation import (sliding_count_trigger, max_distinct_in_window,
                                      cluster_by_gap)

BASE = datetime(2026, 10, 15, 3, 0, 0)


def ssh_fail(ip, user, offset, invalid=False):
    f = {"service": "ssh", "outcome": "fail", "user": user, "invalid_user": invalid}
    return Event("ssh", BASE + timedelta(seconds=offset), ip, f, "raw fail %s %s" % (ip, user))


def ssh_ok(ip, user, offset):
    f = {"service": "ssh", "outcome": "success", "user": user, "method": "password",
         "invalid_user": False}
    return Event("ssh", BASE + timedelta(seconds=offset), ip, f, "raw ok %s %s" % (ip, user))


def fw(ip, dst, port, offset, action="BLOCK"):
    f = {"service": "firewall", "action": action, "proto": "TCP", "dst": dst,
         "dport": port, "sport": 1, "iface": "eth0"}
    return Event("firewall", BASE + timedelta(seconds=offset), ip, f, "fw %s %d" % (ip, port))


def web404(ip, path, offset):
    f = {"method": "GET", "path": path, "proto": "HTTP/1.1", "status": 404,
         "size": 0, "ua": "x", "ref": "-"}
    return Event("web", BASE + timedelta(seconds=offset), ip, f, "web404 %s %s" % (ip, path))


class TestPrimitives(unittest.TestCase):
    def test_sliding_trigger(self):
        self.assertTrue(sliding_count_trigger([0, 1, 2, 3, 4], 5, 10))
        self.assertFalse(sliding_count_trigger([0, 100, 200, 300, 400], 5, 10))
        self.assertTrue(sliding_count_trigger([0, 1, 2, 50, 51, 52], 3, 5))

    def test_max_distinct(self):
        pairs = [(0, "a"), (1, "b"), (2, "c"), (100, "d")]
        self.assertEqual(max_distinct_in_window(pairs, 10), 3)
        self.assertEqual(max_distinct_in_window(pairs, 1000), 4)

    def test_cluster_by_gap(self):
        evs = [ssh_fail("1.1.1.1", "root", t) for t in (0, 1, 2, 5000, 5001)]
        clusters = cluster_by_gap(evs, 100)
        self.assertEqual(len(clusters), 2)
        self.assertEqual([len(c) for c in clusters], [3, 2])


class TestBruteForce(unittest.TestCase):
    def test_fast_brute(self):
        evs = [ssh_fail("203.0.113.66", "root", i * 2) for i in range(15)]
        alerts = corr.ssh_bruteforce(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "SSH-BRUTE")
        self.assertIn("T1110", alerts[0].mitre)
        self.assertEqual(alerts[0].evidence_count, 15)

    def test_below_threshold_quiet(self):
        evs = [ssh_fail("203.0.113.66", "root", i * 2) for i in range(5)]
        self.assertEqual(corr.ssh_bruteforce(evs), [])

    def test_many_users_is_not_brute(self):
        # 15 fails but across 15 users -> spraying, not single-account brute
        evs = [ssh_fail("203.0.113.66", "user%d" % i, i * 2) for i in range(15)]
        self.assertEqual(corr.ssh_bruteforce(evs), [])


class TestSprayingStuffing(unittest.TestCase):
    def test_spray_valid_users(self):
        evs = [ssh_fail("198.51.100.23", "user%d" % i, i * 30) for i in range(8)]
        alerts = corr.ssh_spraying(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "SSH-SPRAY")
        self.assertIn("T1110.003", alerts[0].mitre)

    def test_stuffing_invalid_users(self):
        evs = [ssh_fail("192.0.2.77", "ghost%d" % i, i * 10, invalid=True) for i in range(8)]
        alerts = corr.ssh_spraying(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "SSH-STUFFING")
        self.assertIn("T1110.004", alerts[0].mitre)


class TestCompromise(unittest.TestCase):
    def test_fails_then_success(self):
        evs = [ssh_fail("192.0.2.77", "deploy", i * 5) for i in range(6)]
        evs.append(ssh_ok("192.0.2.77", "deploy", 40))
        alerts = corr.ssh_compromise(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "critical")
        self.assertIn("T1078", alerts[0].mitre)

    def test_success_without_fails_quiet(self):
        evs = [ssh_ok("10.0.0.20", "alice", 0)]
        self.assertEqual(corr.ssh_compromise(evs), [])


class TestOffHours(unittest.TestCase):
    def test_offhours_root(self):
        # BASE is 03:00 -> off hours
        evs = [ssh_ok("203.0.113.9", "root", 0)]
        alerts = corr.ssh_offhours_admin(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "SSH-OFFHOURS")

    def test_business_hours_quiet(self):
        day = datetime(2026, 10, 15, 11, 0, 0)
        f = {"service": "ssh", "outcome": "success", "user": "root",
             "method": "password", "invalid_user": False}
        ev = Event("ssh", day, "10.0.0.20", f, "ok")
        self.assertEqual(corr.ssh_offhours_admin([ev]), [])

    def test_non_admin_quiet(self):
        evs = [ssh_ok("203.0.113.9", "alice", 0)]
        self.assertEqual(corr.ssh_offhours_admin(evs), [])


class TestPortScan(unittest.TestCase):
    def test_vertical_scan(self):
        evs = [fw("203.0.113.200", "10.0.0.5", 20 + i, i * 2) for i in range(20)]
        alerts = corr.fw_port_scan(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "FW-PORTSCAN")
        self.assertIn("T1046", alerts[0].mitre)

    def test_few_ports_quiet(self):
        evs = [fw("203.0.113.200", "10.0.0.5", 22, i * 2) for i in range(20)]
        self.assertEqual(corr.fw_port_scan(evs), [])


class TestEnum(unittest.TestCase):
    def test_many_404(self):
        evs = [web404("203.0.113.101", "/p%d" % i, i) for i in range(25)]
        alerts = corr.web_enumeration(evs)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule, "WEB-ENUM")

    def test_few_404_quiet(self):
        evs = [web404("203.0.113.101", "/p%d" % i, i) for i in range(5)]
        self.assertEqual(corr.web_enumeration(evs), [])


class TestSudoEscalation(unittest.TestCase):
    def test_sudo_after_compromise(self):
        evs = [ssh_fail("192.0.2.77", "deploy", i * 5) for i in range(6)]
        evs.append(ssh_ok("192.0.2.77", "deploy", 40))
        comp = corr.ssh_compromise(evs)
        sudo_ev = Event("sudo", BASE + timedelta(seconds=200), None,
                        {"service": "sudo", "ruser": "deploy", "tuser": "root",
                         "cmd": "echo k >> /root/.ssh/authorized_keys"}, "sudo raw")
        alerts = corr.sudo_escalation([sudo_ev], comp)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "critical")
        self.assertEqual(alerts[0].src, "192.0.2.77")

    def test_sensitive_file_sudo_without_link(self):
        sudo_ev = Event("sudo", BASE, None,
                        {"service": "sudo", "ruser": "bob", "tuser": "root",
                         "cmd": "cat /etc/shadow"}, "sudo raw")
        alerts = corr.sudo_escalation([sudo_ev], [])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "medium")

    def test_benign_sudo_quiet(self):
        sudo_ev = Event("sudo", BASE, None,
                        {"service": "sudo", "ruser": "alice", "tuser": "root",
                         "cmd": "apt update"}, "sudo raw")
        self.assertEqual(corr.sudo_escalation([sudo_ev], []), [])


if __name__ == "__main__":
    unittest.main()

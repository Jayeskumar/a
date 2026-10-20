"""Deterministic log generator with ground-truth attack labels.

Produces realistic benign web / SSH / firewall traffic plus a set of labelled
attack scenarios embedded at known times from known source IPs. The labels are
what REPORT.md measures precision/recall against.

All attacker and host IPs come from RFC 5737 documentation ranges
(203.0.113.0/24, 198.51.100.0/24, 192.0.2.0/24) and RFC 1918 private space
(10.0.0.0/8). No real address ever appears.
"""

import random
from datetime import datetime, timedelta

SEED = 1337

# RFC 5737 / RFC 1918 only.
HOSTS = ["10.0.0.5", "10.0.0.6", "10.0.0.7"]          # our servers (firewall DST)
ADMIN_WS = ["10.0.0.20", "10.0.0.21"]                  # internal admin workstations
BENIGN_WEB_IPS = (["203.0.113.%d" % i for i in range(10, 70)] +
                  ["198.51.100.%d" % i for i in range(100, 140)])
GOOGLEBOT_IP = "203.0.113.250"

BROWSERS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
]
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

BENIGN_PATHS = [
    ("GET", "/", 200), ("GET", "/index.html", 200), ("GET", "/about", 200),
    ("GET", "/contact", 200), ("GET", "/static/app.css", 200),
    ("GET", "/static/app.js", 200), ("GET", "/static/logo.png", 200),
    ("GET", "/blog", 200), ("GET", "/blog/%d" % 0, 200), ("GET", "/products", 200),
    ("GET", "/product?id=%d" % 0, 200), ("GET", "/api/status", 200),
    ("GET", "/api/items", 200), ("POST", "/api/cart", 201), ("GET", "/favicon.ico", 200),
    ("GET", "/robots.txt", 200), ("GET", "/login", 200), ("POST", "/login", 302),
    ("GET", "/account", 200), ("GET", "/search?q=shoes", 200),
]
BENIGN_USERS = ["alice", "bob", "carol", "deploy", "ubuntu"]

# diurnal weight by hour (0-23): low at night, peak mid-day.
DIURNAL = [2, 1, 1, 1, 1, 2, 4, 7, 11, 14, 16, 17, 18, 17, 16, 15, 14, 12, 10, 8, 6, 5, 4, 3]


def _clf(ts):
    return ts.strftime("%d/%b/%Y:%H:%M:%S +0000")


def _syslog_ts(ts):
    # %d would zero-pad; real syslog space-pads the day.
    return ts.strftime("%b %e %H:%M:%S").replace("  ", " ")


class Gen:
    def __init__(self, seed=SEED):
        self.r = random.Random(seed)
        self.records = []          # (datetime, fmt, line, label)
        self.labels = []           # ground-truth attack windows
        self.start = datetime(2026, 10, 15, 6, 0, 0)
        self.end = self.start + timedelta(hours=20)

    # ---- emit helpers ----
    def web(self, ts, ip, method, path, status, ua, size=None, label=None, ref="-"):
        size = size if size is not None else self.r.randint(180, 5200)
        line = '%s - - [%s] "%s %s HTTP/1.1" %d %d "%s" "%s"' % (
            ip, _clf(ts), method, path, status, size, ref, ua)
        self.records.append((ts, "web", line, label))

    def sshd(self, ts, msg, host="web01", pid=None, label=None):
        pid = pid or self.r.randint(1000, 39999)
        line = "%s %s sshd[%d]: %s" % (_syslog_ts(ts), host, pid, msg)
        self.records.append((ts, "auth", line, label))

    def sudo(self, ts, ruser, tuser, cmd, host="web01", label=None):
        line = ("%s %s sudo:   %s : TTY=pts/0 ; PWD=/home/%s ; USER=%s ; COMMAND=%s"
                % (_syslog_ts(ts), host, ruser, ruser, tuser, cmd))
        self.records.append((ts, "auth", line, label))

    def fw(self, ts, src, dst, dport, proto="TCP", action="BLOCK", host="gw", label=None):
        spt = self.r.randint(1024, 65000)
        line = ("%s %s kernel: [%d.%03d] [UFW %s] IN=eth0 OUT= SRC=%s DST=%s "
                "LEN=60 PROTO=%s SPT=%d DPT=%d" % (
                    _syslog_ts(ts), host, self.r.randint(10000, 99999),
                    self.r.randint(0, 999), action, src, dst, proto, spt, dport))
        self.records.append((ts, "firewall", line, label))

    def add_label(self, lid, atype, src, start, end, expected, note=""):
        self.labels.append({
            "id": lid, "type": atype, "src": src,
            "start": start.isoformat(), "end": end.isoformat(),
            "expected_categories": expected, "note": note,
        })

    # ---- benign ----
    def gen_benign_web(self):
        minute = self.start
        while minute < self.end:
            w = DIURNAL[minute.hour]
            n = max(0, int(self.r.gauss(w, w * 0.3)))
            for _ in range(n):
                ts = minute + timedelta(seconds=self.r.randint(0, 59),
                                        microseconds=self.r.randint(0, 999999))
                ip = self.r.choice(BENIGN_WEB_IPS)
                method, path, status = self.r.choice(BENIGN_PATHS)
                if "%d" in path:
                    path = path % self.r.randint(1, 500)
                # a little benign 404 noise (typos), well below the enum threshold
                if self.r.random() < 0.02:
                    status = 404
                    path = self.r.choice(["/favicon.ico", "/old-page", "/img/x.png"])
                ua = self.r.choice(BROWSERS)
                self.web(ts, ip, method, path, status, ua)
            # occasional googlebot crawl
            if self.r.random() < 0.3:
                ts = minute + timedelta(seconds=self.r.randint(0, 59))
                self.web(ts, GOOGLEBOT_IP, "GET",
                         self.r.choice(["/", "/blog", "/products", "/sitemap.xml"]),
                         200, GOOGLEBOT_UA)
            minute += timedelta(minutes=1)

    def gen_benign_ssh(self):
        # a handful of legit admin logins during business hours, plus the odd typo
        for _ in range(14):
            h = self.r.randint(8, 19)
            ts = self.start.replace(hour=h, minute=self.r.randint(0, 59),
                                    second=self.r.randint(0, 59))
            ip = self.r.choice(ADMIN_WS)
            user = self.r.choice(["alice", "bob", "deploy"])
            if self.r.random() < 0.3:           # one fat-fingered failure first
                self.sshd(ts, "Failed password for %s from %s port %d ssh2"
                          % (user, ip, self.r.randint(40000, 60000)))
                ts = ts + timedelta(seconds=self.r.randint(3, 15))
            self.sshd(ts, "Accepted password for %s from %s port %d ssh2"
                      % (user, ip, self.r.randint(40000, 60000)))

    def gen_benign_fw(self):
        # background internet noise: a few single drops to common ports, low volume
        t = self.start
        while t < self.end:
            if self.r.random() < 0.4:
                self.fw(t + timedelta(seconds=self.r.randint(0, 59)),
                        self.r.choice(BENIGN_WEB_IPS), self.r.choice(HOSTS),
                        self.r.choice([23, 445, 3389, 8080, 22]))
            t += timedelta(minutes=self.r.randint(2, 6))

    # ---- attacks ----
    def atk_ssh_brute(self):
        src = "203.0.113.66"
        t = self.start.replace(hour=1, minute=12, second=0) + timedelta(days=0)
        t = datetime(2026, 10, 16, 1, 12, 0)     # 01:12 next morning, off hours
        start = t
        for i in range(42):
            self.sshd(t, "Failed password for root from %s port %d ssh2"
                      % (src, self.r.randint(30000, 60000)), label="ssh_brute")
            t += timedelta(seconds=self.r.randint(1, 4))
        self.add_label("ATK-BRUTE", "ssh_brute_force", src, start, t,
                       ["SSH Brute Force"], "42 failed root logins in ~2 min")

    def atk_ssh_spray(self):
        src = "198.51.100.23"
        users = ["admin", "deploy", "git", "oracle", "postgres", "ubuntu",
                 "jenkins", "backup", "www-data", "test", "support", "operator"]
        t = datetime(2026, 10, 15, 22, 5, 0)
        start = t
        for u in users:
            for _ in range(self.r.randint(1, 2)):
                self.sshd(t, "Failed password for %s from %s port %d ssh2"
                          % (u, src, self.r.randint(30000, 60000)), label="ssh_spray")
                t += timedelta(seconds=self.r.randint(20, 70))
        self.add_label("ATK-SPRAY", "ssh_password_spray", src, start, t,
                       ["Password Spraying"], "12 usernames, mostly valid accounts")

    def atk_credential_stuffing(self):
        src = "192.0.2.77"
        # mostly invalid users (leaked combo list), then one works
        invalid = ["adm1n", "jdoe", "testuser", "guest1", "dbadm", "svc_web",
                   "ftpuser", "oracle1", "mysql", "tomcat", "nagios", "vpn"]
        t = datetime(2026, 10, 15, 23, 40, 0)
        start = t
        for u in invalid:
            self.sshd(t, "Invalid user %s from %s port %d"
                      % (u, src, self.r.randint(30000, 60000)), label="cred_stuffing")
            t += timedelta(seconds=self.r.randint(2, 6))
            self.sshd(t, "Failed password for invalid user %s from %s port %d ssh2"
                      % (u, src, self.r.randint(30000, 60000)), label="cred_stuffing")
            t += timedelta(seconds=self.r.randint(2, 6))
        self.add_label("ATK-STUFF", "credential_stuffing", src, start, t,
                       ["Credential Stuffing"], ">50% non-existent accounts")
        # then a valid cred finally succeeds -> compromise
        comp_start = t
        for _ in range(6):
            self.sshd(t, "Failed password for deploy from %s port %d ssh2"
                      % (src, self.r.randint(30000, 60000)), label="compromise")
            t += timedelta(seconds=self.r.randint(2, 6))
        success = t + timedelta(seconds=4)
        self.sshd(success, "Accepted password for deploy from %s port %d ssh2"
                  % (src, self.r.randint(30000, 60000)), label="compromise")
        self.add_label("ATK-COMPROMISE", "compromise", src, comp_start, success,
                       ["Likely Account Compromise"], "failures then success as 'deploy'")
        # attacker escalates via sudo shortly after
        esc = success + timedelta(minutes=2)
        self.sudo(esc, "deploy", "root",
                  "/bin/bash -c echo ATTACKER_KEY >> /root/.ssh/authorized_keys",
                  label="priv_esc")
        self.add_label("ATK-SUDO", "privilege_escalation", src, esc, esc,
                       ["Privilege Escalation via sudo"],
                       "sudo to root editing authorized_keys after compromise")

    def atk_web_enum(self):
        src = "203.0.113.101"
        paths = ["/admin", "/administrator", "/wp-admin", "/wp-login.php",
                 "/.git/config", "/.env", "/backup.zip", "/backup.sql",
                 "/phpmyadmin", "/config.php.bak", "/server-status", "/.htaccess",
                 "/old", "/test", "/dev", "/api/v1/users", "/cgi-bin/", "/shell.php",
                 "/uploads/", "/db.sql", "/.ssh/id_rsa", "/web.config", "/install.php",
                 "/adminer.php", "/vendor/phpunit", "/actuator/env", "/debug",
                 "/console", "/login.bak", "/secret", "/private", "/tmp/"]
        t = datetime(2026, 10, 15, 14, 30, 0)
        start = t
        for p in paths:
            self.web(t, src, "GET", p, 404, "Mozilla/5.0 (gobuster/3.6)",
                     size=0, label="web_enum")
            t += timedelta(seconds=self.r.randint(1, 3))
        self.add_label("ATK-ENUM", "web_enumeration", src, start, t,
                       ["Directory / Path Enumeration"], "gobuster-style 404 sweep")

    def atk_sqli(self):
        src = "198.51.100.50"
        payloads = [
            "/product?id=1%27%20OR%20%271%27%3D%271",            # ' OR '1'='1
            "/product?id=1%20UNION%20SELECT%20username%2Cpassword%20FROM%20users",
            "/product?id=1%3B%20DROP%20TABLE%20users--",
            "/search?q=%27%20OR%201%3D1--%20",
            "/product?id=1%27%20AND%20SLEEP%285%29--",
            "/item?cat=1%20union%20select%20null%2Cconcat%28user%28%29%29",
            "/product?id=-1%27%20UNION%20SELECT%20%40%40version--",
            "/view?id=1%27%20AND%201%3D0%20UNION%20SELECT%20table_name%20FROM%20information_schema.tables--",
        ]
        t = datetime(2026, 10, 15, 15, 10, 0)
        start = t
        for p in payloads:
            self.web(t, src, "GET", p, self.r.choice([200, 500, 403]),
                     "python-requests/2.31", label="sqli")
            t += timedelta(seconds=self.r.randint(2, 8))
        self.add_label("ATK-SQLI", "sql_injection", src, start, t,
                       ["SQL Injection"], "URL-encoded SQLi payloads")

    def atk_xss(self):
        src = "198.51.100.51"
        payloads = [
            "/search?q=%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
            "/comment?text=%3Cimg%20src%3Dx%20onerror%3Dalert%28document.cookie%29%3E",
            "/search?q=%3Csvg%20onload%3Dalert%281%29%3E",
            "/profile?name=%22%3E%3Cscript%3Edocument.cookie%3C%2Fscript%3E",
            "/q?s=javascript%3Aalert%281%29",
            "/search?q=%3Ciframe%20src%3Djavascript%3Aalert%281%29%3E",
        ]
        t = datetime(2026, 10, 15, 15, 40, 0)
        start = t
        for p in payloads:
            self.web(t, src, "GET", p, 200, self.r.choice(BROWSERS), label="xss")
            t += timedelta(seconds=self.r.randint(3, 10))
        self.add_label("ATK-XSS", "xss", src, start, t,
                       ["Cross-Site Scripting"], "URL-encoded XSS payloads")

    def atk_traversal(self):
        src = "198.51.100.52"
        payloads = [
            "/download?file=..%2F..%2F..%2F..%2Fetc%2Fpasswd",
            "/view?page=..%2f..%2f..%2fetc%2fshadow",
            "/img?f=%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "/static?path=....%2f....%2fboot.ini",
            "/get?doc=php://filter/convert.base64-encode/resource=index.php",
            "/load?f=..%5c..%5c..%5cwindows%5csystem32%5cdrivers%5cetc%5chosts",
        ]
        t = datetime(2026, 10, 15, 16, 5, 0)
        start = t
        for p in payloads:
            self.web(t, src, "GET", p, self.r.choice([200, 404, 403]),
                     "curl/8.2.1", label="traversal")
            t += timedelta(seconds=self.r.randint(2, 8))
        self.add_label("ATK-TRAV", "path_traversal", src, start, t,
                       ["Path Traversal / LFI"], "encoded ../ sequences to /etc/passwd")

    def atk_port_scan(self):
        src = "203.0.113.200"
        dst = HOSTS[0]
        ports = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 993,
                 995, 1433, 1521, 2049, 3306, 3389, 5432, 5900, 6379, 8080, 8443,
                 9200, 11211, 27017, 5000, 8000]
        t = datetime(2026, 10, 15, 17, 20, 0)
        start = t
        for p in ports:
            self.fw(t, src, dst, p, action="BLOCK", label="port_scan")
            t += timedelta(seconds=self.r.randint(1, 3))
        self.add_label("ATK-SCAN", "port_scan", src, start, t,
                       ["Port Scan"], "30 distinct ports on one host in ~1 min")

    def atk_offhours_admin(self):
        src = "203.0.113.9"
        t = datetime(2026, 10, 16, 2, 35, 0)       # 02:35, off hours
        self.sshd(t, "Accepted password for root from %s port %d ssh2"
                  % (src, self.r.randint(40000, 60000)), label="offhours")
        self.add_label("ATK-OFFHOURS", "offhours_admin_login", src, t, t,
                       ["Off-Hours Admin Login"], "root login at 02:35")

    # ---- drive ----
    def build(self):
        self.gen_benign_web()
        self.gen_benign_ssh()
        self.gen_benign_fw()
        self.atk_ssh_brute()
        self.atk_ssh_spray()
        self.atk_credential_stuffing()
        self.atk_web_enum()
        self.atk_sqli()
        self.atk_xss()
        self.atk_traversal()
        self.atk_port_scan()
        self.atk_offhours_admin()
        self.records.sort(key=lambda r: r[0])
        return self

    def lines(self):
        return [r[2] for r in self.records]

    def text(self):
        return "\n".join(self.lines()) + "\n"

    def benign_text(self):
        return "\n".join(r[2] for r in self.records if r[3] is None) + "\n"

    def ground_truth(self):
        return {
            "seed": SEED,
            "window": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "total_lines": len(self.records),
            "attack_lines": sum(1 for r in self.records if r[3]),
            "attacker_ips": sorted({lb["src"] for lb in self.labels}),
            "labels": self.labels,
        }


def generate(seed=SEED):
    return Gen(seed).build()


def write_files(data_dir, seed=SEED):
    import json
    import os
    g = generate(seed)
    with open(os.path.join(data_dir, "sample.log"), "w", encoding="utf-8") as f:
        f.write(g.text())
    with open(os.path.join(data_dir, "benign.log"), "w", encoding="utf-8") as f:
        f.write(g.benign_text())
    with open(os.path.join(data_dir, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(g.ground_truth(), f, indent=2)
    return g

"""Every tunable detection threshold lives here, with the reasoning behind it.

The numbers are engineering defaults, not measured industry statistics. They are
chosen to resemble common open-source defaults (e.g. fail2ban's sshd jail bans
after a handful of failures inside a ten-minute window) and were then checked
against the deterministic benign-only logs so that normal traffic stays quiet.
"""

# --------------------------------------------------------------- parsing
# Syslog lines (auth.log, kernel firewall lines) carry no year; assume this one
# unless the caller passes another. The demo data is generated for 2026.
DEFAULT_YEAR = 2026
# Lines sampled to auto-detect a file's format.
DETECT_SAMPLE_LINES = 60

# --------------------------------------------------------------- SSH rules
# Brute force: many failures from one IP against few accounts in a short window.
# fail2ban's sshd jail defaults to maxretry=5 in findtime=10m; we alert a bit
# later (10 in 2 min, or 20 in 30 min for slower guessing) to avoid paging on
# a user who simply mistyped a password several times.
BRUTE_FAILS = 10
BRUTE_WINDOW_S = 120
BRUTE_SLOW_FAILS = 20
BRUTE_SLOW_WINDOW_S = 1800
BRUTE_MAX_USERS = 3            # more distinct users than this = spraying/stuffing

# One IP trying many different usernames within the window.
SPRAY_MIN_USERS = 6
SPRAY_WINDOW_S = 1800
# If at least this share of the tried usernames do not exist on the host
# ("invalid user"), the list looks like a leaked combo list -> credential
# stuffing (T1110.004); otherwise it looks like spraying real accounts (T1110.003).
STUFFING_INVALID_RATIO = 0.5

# Failures followed by a success from the same IP = likely compromise.
COMPROMISE_MIN_FAILS = 5
COMPROMISE_WINDOW_S = 3600

# Privileged accounts and business hours for the off-hours admin login rule.
ADMIN_USERS = ("root", "admin", "administrator", "sysadmin")
BUSINESS_HOURS = (8, 20)       # [start, end) local wall-clock hour
WEEKEND_IS_OFF_HOURS = True

# sudo by a user shortly after a suspicious login from the same session IP.
SUDO_AFTER_COMPROMISE_S = 3600
SENSITIVE_FILES = ("/etc/shadow", "/etc/sudoers", "/root/.ssh", "authorized_keys")

# --------------------------------------------------------------- firewall
# Vertical scan: one source touching many distinct ports on our hosts.
SCAN_MIN_PORTS = 15
SCAN_WINDOW_S = 120
# Horizontal sweep: one source touching many distinct hosts on any port.
SWEEP_MIN_HOSTS = 10
SWEEP_WINDOW_S = 300

# --------------------------------------------------------------- web
# Directory brute force / path enumeration: many 404s from one IP.
ENUM_MIN_404 = 20
ENUM_WINDOW_S = 120
# Signature hits from one IP are aggregated into one alert while they keep coming.
ALERT_MERGE_GAP_S = 900

# --------------------------------------------------------------- anomaly
# EWMA smoothing for per-IP "requests per active minute" and for total RPM.
EWMA_ALPHA = 0.1
Z_THRESHOLD = 4.0
RATE_MIN_COUNT = 40            # never call fewer than this many req/min an anomaly
RATE_SIGMA_FLOOR = 3.0         # keeps z finite for very regular clients
IP_HISTORY_MIN_MINUTES = 5     # below this, compare against the site-wide baseline
GLOBAL_RPM_Z = 3.5             # anomaly markers on the requests-per-minute chart
GLOBAL_RPM_WARMUP = 30         # minutes before the global RPM baseline is trusted
GLOBAL_RPM_FLOOR = 8.0

# Novelty: a user agent first seen after warm-up, used by a single IP for many requests.
NOVELTY_WARMUP_EVENTS = 2000
NOVEL_UA_MIN_REQUESTS = 15
# Path novelty: many never-seen path shapes from one IP in a window.
NOVEL_PATH_MIN = 12
NOVEL_PATH_WINDOW_S = 300
# Well-known crawlers and monitors are expected to be rare; do not flag them.
KNOWN_GOOD_BOTS = ("googlebot", "bingbot", "uptimerobot", "duckduckbot")

# --------------------------------------------------------------- incidents
INCIDENT_GAP_S = 3600          # alerts from one IP closer than this share an incident
EVIDENCE_CAP = 12              # evidence lines kept per alert (the count keeps going)

SEVERITY_ORDER = ("info", "low", "medium", "high", "critical")
SEVERITY_WEIGHT = {"info": 5, "low": 15, "medium": 35, "high": 60, "critical": 85}

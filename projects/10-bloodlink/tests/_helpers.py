"""Shared test helpers: make the project importable and build tiny synthetic donors."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def make_donor(did, group, lat=11.38, lon=77.89, sex="M", dob="1998-01-01", weight=65.0,
               last_donation=None, received=4, accepted=2, last_contacted=None, available=True,
               willingness=0.5, list_order=0, deferred=None):
    return {"id": did, "name": "Test %s" % did, "sex": sex, "dob": dob, "weight_kg": weight,
            "group": group, "town": "Tiruchengode", "lat": lat, "lon": lon,
            "last_donation": last_donation, "donations": 1 if last_donation else 0,
            "alerts_received": received, "alerts_accepted": accepted,
            "last_contacted": last_contacted, "available": available, "deferred_until": deferred,
            "registered": "2024-01-01", "sim_willingness": willingness, "list_order": list_order}

# Status flow agreed with Archit: expected -> arrived -> admitted (or cancelled).
# ASSUMPTION to confirm: cancelled is allowed from expected and arrived;
# admitted and cancelled are final.
STATUSES = ("expected", "arrived", "admitted", "cancelled")

ALLOWED = {
    "expected": ("arrived", "cancelled"),
    "arrived": ("admitted", "cancelled"),
    "admitted": (),
    "cancelled": (),
}


def can_transition(current, new):
    return new in ALLOWED.get(current, ())

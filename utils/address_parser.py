import re

# ─── Indian states + UTs ─────────────────────────────────────────────────────

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # Union territories
    "Delhi", "Jammu and Kashmir", "Ladakh",
    "Chandigarh", "Puducherry", "Lakshadweep",
    "Dadra and Nagar Haveli", "Daman and Diu",
    "Andaman and Nicobar",
]

# Two-letter MCA state codes → full name
_STATE_CODE_MAP = {
    "DL": "Delhi",   "MH": "Maharashtra", "TN": "Tamil Nadu",
    "KA": "Karnataka", "GJ": "Gujarat",   "RJ": "Rajasthan",
    "UP": "Uttar Pradesh", "WB": "West Bengal", "TG": "Telangana",
    "AP": "Andhra Pradesh", "KL": "Kerala",   "MP": "Madhya Pradesh",
    "HR": "Haryana",  "PB": "Punjab",      "BR": "Bihar",
    "OR": "Odisha",   "AS": "Assam",       "JH": "Jharkhand",
    "HP": "Himachal Pradesh", "CG": "Chhattisgarh", "UK": "Uttarakhand",
    "GA": "Goa",      "MN": "Manipur",     "ML": "Meghalaya",
    "MZ": "Mizoram",  "NL": "Nagaland",    "SK": "Sikkim",
    "TR": "Tripura",  "AR": "Arunachal Pradesh",
    "JK": "Jammu and Kashmir", "LA": "Ladakh",
    "CH": "Chandigarh", "PY": "Puducherry",
    "AN": "Andaman and Nicobar",
}

# Pincode pattern: 6-digit Indian postal code
_PINCODE_RE = re.compile(r"\b(\d{6})\b")


def extract_state(address: str | None) -> str | None:
    """Extract Indian state name from address string."""
    if not address:
        return None

    # 1. Try two-letter state code just before pincode or country ("IN")
    #    e.g. "New Delhi DL 110030 IN"
    for code, name in _STATE_CODE_MAP.items():
        if re.search(rf"\b{code}\b", address):
            return name

    # 2. Try full state name (case-insensitive)
    lower = address.lower()
    for state in sorted(INDIAN_STATES, key=len, reverse=True):
        if state.lower() in lower:
            return state

    return None


def extract_city(address: str | None) -> str | None:
    """Extract city name from address string.

    Zauba addresses typically look like:
      "<street>, <locality>, <city> <STATE_CODE> <PIN> IN"
    We look for the word just before the 2-letter state code.
    """
    if not address:
        return None

    # Comma-delimited format used on company pages:
    #   "<street>, <locality>, <city>, <state>, India - <pin>"
    # The city is the comma-separated part immediately before the state.
    comma_parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(comma_parts) >= 2:
        state = extract_state(address)
        if state:
            for i, part in enumerate(comma_parts):
                if i > 0 and part.lower() == state.lower():
                    return comma_parts[i - 1]

    parts = address.strip().split()

    # Find the position of a 2-letter state code
    for i, part in enumerate(parts):
        if part.upper() in _STATE_CODE_MAP and i > 0:
            # The word(s) before the state code are the city
            # Collect consecutive title-case words immediately before code
            city_parts = []
            j = i - 1
            while j >= 0 and (parts[j][0].isupper() or parts[j].istitle()):
                city_parts.insert(0, parts[j])
                j -= 1
                if len(city_parts) >= 3:
                    break
            if city_parts:
                return " ".join(city_parts)

    # Fallback: word before 6-digit pincode
    match = _PINCODE_RE.search(address)
    if match:
        idx = address.find(match.group())
        before = address[:idx].strip().split()
        if before:
            return before[-1]

    return None
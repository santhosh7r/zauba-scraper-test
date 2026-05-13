INDIAN_STATES = [

    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Delhi"
]


def extract_state(address):

    if not address:
        return None

    address = address.lower()

    for state in INDIAN_STATES:

        if state.lower() in address:

            return state

    return None


def extract_city(address):

    if not address:
        return None

    parts = address.split()

    if len(parts) < 2:
        return None

    return parts[-4] if len(parts) >= 4 else None
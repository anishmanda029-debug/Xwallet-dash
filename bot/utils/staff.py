import os

STAFF_IDS = set()

for var in [
    "OWNER_ID",
    "OWNER_ID_2",
    "DEV_ID",
    "DEV_ID_2"
]:
    value = os.getenv(var)
    if value and value.isdigit():
        STAFF_IDS.add(int(value))


def is_staff(user_id: int):
    return user_id in STAFF_IDS

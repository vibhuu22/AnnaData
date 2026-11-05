"""
The sign-in SMS must reach a farmer's phone, from an ordinary SIM.

The codes are sent by one Android handset on a personal SIM, not a registered
business sender. Indian networks refuse messages from such SIMs that look
commercial, and the gateway reports them as Failed - the farmer simply never
gets a code. The first wording did exactly that. This holds the message to the
rules that keep it looking like a text from a person: none of the words the
filters key on, plain GSM-7 characters, one segment.

Run: python eval/test_code_message.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sms_out

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


# The GSM 03.38 basic set, near enough: what fits seven bits per character.
GSM7 = re.compile(r"^[A-Za-z0-9 @$_!\"#%&'()*+,\-./:;<=>?\n\r]*$")
TRIGGERS = ["otp", "code", "sign-in", "sign in", "login", "log in", "verify",
            "verification", "password", "share", "bank", "do not"]

text = sms_out.code_message("482193")
print(f"Message: {text!r}\n")
check("carries the six digits", "482193" in text, True)
check("says it comes from AnnaData", text.startswith("AnnaData"), True)
check("fits one SMS segment", len(text) <= 153, True)
check("uses only GSM-7 characters", bool(GSM7.match(text)), True)
for word in TRIGGERS:
    check(f"avoids {word!r}", word in text.lower(), False)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)

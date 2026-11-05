"""
Every voice note and photo is uploaded with a MIME type we state.

An iPhone voice note failed in production with "Could not determine the
mimetype for your file": Safari records MP4 audio, which is saved as .m4a, and
the container has no /etc/mime.types for the Gemini client to guess from. This
checks that every extension the backend can choose has a stated type, and that
the browsers' real content types land on the right one.

No model calls, no network.

Run: python eval/test_media_types.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import process_media as pm

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


print("Every extension the backend can pick has a stated type")
for ext in sorted(set(pm.AUDIO_EXTENSIONS.values()) | pm.IMAGE_EXTENSIONS | {".webm", ".jpg"}):
    check(f"{ext} is typed", ext in pm.MIME_TYPES, True)

print("\nWhat each browser actually sends")
cases = [
    ("iPhone Safari", None, "audio/mp4", ".m4a", "audio/mp4"),
    ("Safari, with codecs", "voice.m4a", "audio/mp4;codecs=mp4a.40.2", ".m4a", "audio/mp4"),
    ("Chrome", "voice.webm", "audio/webm;codecs=opus", ".webm", "audio/webm"),
    ("Firefox", "voice.ogg", "audio/ogg;codecs=opus", ".ogg", "audio/ogg"),
    ("only a file name", "voice.m4a", None, ".m4a", "audio/mp4"),
]
for who, name, ctype, ext, mime in cases:
    got = pm._audio_extension(name, ctype)
    check(f"{who}: extension", got, ext)
    check(f"{who}: uploaded as", pm.MIME_TYPES.get(got), mime)

print("\nThe upload states the type instead of letting it be guessed")


class FakeFiles:
    def __init__(self):
        self.calls = []

    def upload(self, file, config=None):
        self.calls.append(config)
        return "uploaded"


class FakeClient:
    def __init__(self):
        self.files = FakeFiles()


client = FakeClient()
pm._upload(client, b"\x00\x00\x00\x18ftypM4A ", ".m4a")
check("an .m4a goes up as audio/mp4", client.files.calls[-1], {"mime_type": "audio/mp4"})
pm._upload(client, b"\xff\xd8\xff", ".jpg")
check("a .jpg goes up as image/jpeg", client.files.calls[-1], {"mime_type": "image/jpeg"})

print("\nSmall media goes in the request itself")
client = FakeClient()
part = pm._part(client, b"\x00\x00\x00\x18ftypM4A ", ".m4a", inline=True)
check("a voice note is sent inline, not uploaded", client.files.calls, [])
check("with its stated type", part.inline_data.mime_type, "audio/mp4")
pm._part(client, b"\xff\xd8\xff", ".jpg", inline=False)
check("too-large media is still uploaded", client.files.calls[-1], {"mime_type": "image/jpeg"})

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)

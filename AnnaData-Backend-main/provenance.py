"""
Where AnnaData's answers come from.

A farmer asking "how do you know about my soil?" is asking a question about the
system, and it deserves a true answer rather than a recalled one - the model
previously replied with a description of laboratory titration, which is how soil
pH is measured in general and has nothing to do with where this number came
from.

The facts here are read from configuration rather than remembered, so what the
farmer is told matches what the service actually did. That honesty is also the
groundwork for citing sources on a pesticide dose, where being able to say where
a number came from is the difference between advice and a guess.
"""
import config
import db
import startup
import Web_Crawler


def data_sources() -> list[str]:
    """Plain descriptions of every source that is actually configured."""
    sources = []

    if startup.is_available():
        sources.append(
            "Soil (texture, pH, organic carbon): satellite soil maps from "
            "OpenLandMap, read at about 250 metre resolution for the farmer's "
            "coordinates. It is a model estimate for the area, not a laboratory "
            "test of their field."
        )

    sources.append(
        "Weather (current conditions, past month's rainfall, 7-day forecast): "
        "the Open-Meteo forecast service, for the farmer's coordinates."
    )

    if config.GOV_API_KEY:
        sources.append(
            "Market prices: daily mandi prices published by the Government of "
            "India on data.gov.in, filtered to the farmer's state and crop."
        )

    if Web_Crawler.is_available():
        sources.append(
            "Government schemes and storage: a knowledge base built from "
            "official agricultural sources."
        )

    provider = "Google Maps" if config.LOCATION_API_KEY else "OpenStreetMap"
    sources.append(
        f"Location: whatever place the farmer told us, converted to coordinates "
        f"using {provider}."
    )

    if db.is_available():
        sources.append(
            "Memory: the farmer's district, crops and recent messages are stored "
            "against their phone number so they need not repeat themselves. They "
            "can erase all of it at any time by replying STOP."
        )

    return sources


def profile_summary(profile: dict | None) -> str:
    """What we currently hold about this particular farmer."""
    if not profile:
        return "Nothing is stored about this farmer yet."

    bits = []
    if profile.get("location_text"):
        where = profile["location_text"]
        if profile.get("latitude") is not None:
            where += f" (coordinates {profile['latitude']:.2f}, {profile['longitude']:.2f})"
        bits.append(f"location: {where}")
    if profile.get("state"):
        bits.append(f"state: {profile['state']}")
    if profile.get("crops"):
        bits.append(f"crops mentioned: {', '.join(profile['crops'])}")

    return "Stored for this farmer - " + "; ".join(bits) if bits else \
        "Nothing is stored about this farmer yet."


def describe(profile: dict | None = None) -> str:
    """The full factual briefing used to answer questions about the system."""
    lines = ["AnnaData is an agricultural advisory service reachable by SMS and web.",
             "", "Its data comes from:"]
    lines += [f"- {s}" for s in data_sources()]
    lines += ["", profile_summary(profile)]
    return "\n".join(lines)

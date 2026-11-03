"""
Why does data.gov.in answer this machine with 403?

Live mandi prices stopped reaching the service on 2 September 2026. The same key
works from an Indian residential connection and fails from every hosted
environment tried, but not in the same way, and the difference is the whole
reason this script exists:

    home broadband, India        200 OK
    Cloud Run asia-south1        connects, then 403 from nginx
    Cloud Run asia-southeast1    connection refused
    Cloud Run us-central1        connection refused
    Cloud Run europe-west1       connection refused
    Cloud Build                  no route to host
    GitHub Actions (Azure, US)   connection refused
    Render                       fails

Everything outside India is refused at the TCP layer and never reaches the
application. Mumbai is the one place the request arrives and is then turned
away, which means something there is a decision about the request rather than
about the route - and a decision can have a cheaper fix than standing up a
permanent fetcher somewhere.

Two candidates, and they are testable:

  Headers. The serving code sends a User-Agent and nothing else. No Accept, no
  Accept-Language, no Connection. A request carrying one header is unusual
  enough for a bot-scoring rule to act on, and this upstream already has form
  here: it silently drops the requests default User-Agent, which cost a week of
  prices before anyone worked out it was not an outage.

  Square brackets. The query carries filters[state] and filters[commodity],
  which encode to %5B and %5D. Common WAF rulesets flag encoded brackets as an
  injection signature, and a bare 403 with no body is what that looks like.

So: vary one thing at a time and read the status codes. RUN THIS IN
asia-south1. Anywhere else it only reproduces the connection refusal, which is
already known and tells us nothing new.

    gcloud run jobs deploy mandi-probe \
      --source . --region asia-south1 \
      --command python --args tools/probe_mandi_access.py \
      --set-env-vars "GOV_API_KEY=..." --execute-now

It reads only, writes nothing, and never prints the key.
"""
import os
import sys

import requests

RESOURCE = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
API_ROOT = "https://api.data.gov.in/"
SITE_ROOT = "https://data.gov.in/"

KEY = os.environ.get("GOV_API_KEY", "")

SERVING_UA = "AnnaData/1.0 (farmer advisory service)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

BASE = {"api-key": KEY, "format": "json", "limit": 3}
FILTERED = dict(BASE, **{"filters[state]": "Uttar Pradesh"})


def attempt(label: str, url: str, params=None, headers=None, note: str = ""):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=25)
        body = (r.text or "")[:160].replace("\n", " ")
        # Some upstreams echo the request back in an error. Cloud Run job logs
        # are readable by anyone with project access, so the key does not go
        # into them even by accident.
        if KEY:
            body = body.replace(KEY, "***")
        print(f"  {label:<44} {r.status_code:>5}   {body}")
        return r.status_code
    except Exception as e:
        print(f"  {label:<44}   ERR   {type(e).__name__}: {str(e)[:110]}")
        return None


def main() -> int:
    if not KEY:
        print("GOV_API_KEY is not set in this environment.")
        return 1

    print("Egress address of this machine")
    try:
        print(f"  {requests.get('https://api.ipify.org', timeout=15).text}")
    except Exception as e:
        print(f"  could not determine: {e}")

    print("\nIs the refusal about this IP at all, or about the request?")
    # If the plain site answers while the API 403s, the address is fine and
    # something about the API request is being judged.
    attempt("site root, browser headers", SITE_ROOT, headers=BROWSER_HEADERS)
    attempt("api root, browser headers", API_ROOT, headers=BROWSER_HEADERS)

    print("\nHeaders, holding the query shape constant (no filters)")
    attempt("what the serving code sends today", RESOURCE, BASE,
            {"User-Agent": SERVING_UA})
    attempt("no User-Agent at all", RESOURCE, BASE, {})
    attempt("requests' own default UA", RESOURCE, BASE, None)
    attempt("browser UA only", RESOURCE, BASE, {"User-Agent": BROWSER_UA})
    attempt("full browser header set", RESOURCE, BASE, BROWSER_HEADERS)

    print("\nSquare brackets, holding headers constant")
    # filters[state] encodes to filters%5Bstate%5D. If only the filtered calls
    # are refused, the fix is a query the serving code can simply stop sending.
    attempt("no filters, serving UA", RESOURCE, BASE, {"User-Agent": SERVING_UA})
    attempt("filters[state], serving UA", RESOURCE, FILTERED,
            {"User-Agent": SERVING_UA})
    attempt("no filters, browser headers", RESOURCE, BASE, BROWSER_HEADERS)
    attempt("filters[state], browser headers", RESOURCE, FILTERED,
            BROWSER_HEADERS)

    print("\nReading the result")
    print("  any 200                  -> recoverable from Mumbai; the winning")
    print("                              row says what to change")
    print("  403 everywhere, site too -> the address is judged, not the request")
    print("  403 only with filters    -> bracket encoding; drop server-side")
    print("                              filtering and filter in our own code")
    print("  403 only on the API      -> the key or its registration, not the IP")
    return 0


if __name__ == "__main__":
    sys.exit(main())

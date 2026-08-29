from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List, Optional

from langchain.schema import HumanMessage

from utils import llm
from Address_Convertor import get_location
from Mandi_Price_Tool import get_state_data
from Query_Parser import extract_farm_info
from weather_tool import weather_openmeteo
from Soil_Tool import soil_tool
from Refined_Farmer_Query import get_farming_query
from Web_Crawler import query_kb, is_available as kb_available
import planner
import re


# Where the year sits in the Indian cropping calendar. Advice is intensely
# seasonal and the model has no clock, so without this it recommends sowing
# windows that closed months ago - asked in late August about the next two
# months it will happily suggest mid-June.
CROP_CALENDAR = {
    1:  ("Rabi", "Rabi crops are growing. Sowing is over; irrigate and manage pests."),
    2:  ("Rabi", "Rabi crops are maturing. Sowing is over."),
    3:  ("Rabi harvest / Zaid sowing", "Rabi harvest begins. Zaid (summer) sowing starts."),
    4:  ("Zaid", "Zaid summer crops are sown and growing. Rabi harvest completes."),
    5:  ("Zaid", "Zaid crops growing under irrigation. Prepare fields for Kharif."),
    6:  ("Kharif sowing", "Monsoon arrives. Kharif sowing window is open now."),
    7:  ("Kharif sowing", "Kharif sowing and transplanting continue. Window closing."),
    8:  ("Kharif growing", "Kharif sowing is OVER. Crops are standing; focus on pest, nutrient and water management."),
    9:  ("Kharif growing", "Kharif crops are maturing. Sowing is OVER. Early harvest begins late in the month."),
    10: ("Kharif harvest / Rabi sowing", "Kharif harvest is underway. Rabi sowing window opens."),
    11: ("Rabi sowing", "Rabi sowing is the priority now - wheat, mustard, gram."),
    12: ("Rabi sowing", "Late Rabi sowing. Sow now or yields drop."),
}


def temporal_context() -> str:
    """Today's date and where it falls in the cropping year."""
    today = date.today()
    season, note = CROP_CALENDAR[today.month]
    return (
        f"TODAY'S DATE: {today:%d %B %Y}.\n"
        f"    Current season in India: {season}. {note}\n"
        f"    Indian cropping calendar: Kharif sown Jun-Jul and harvested Sep-Oct; "
        f"Rabi sown Oct-Dec and harvested Mar-Apr; Zaid sown Mar-Apr and harvested Jun.\n"
        f"    NEVER recommend a sowing window that has already passed this year. "
        f"If the farmer asks about a window that has closed, say so plainly and "
        f"give them the next one that is actually open."
    )


# How the answer should be shaped, per delivery channel. SMS callers used to
# append this instruction to the farmer's message, which meant the query parser
# saw it as part of the question and could mis-extract crop and location.
CHANNEL_STYLE = {
    "web": (
        "Keep the answer concise, ideally under 250 words. "
        "Format it clearly using markdown."
    ),
    "sms": (
        "This answer is delivered as an SMS to a basic phone. "
        "Use plain text ONLY: no markdown, no asterisks, no hash headers, "
        "no bullet characters, no tables, no links. "
        "Write two or three short sentences giving the single most useful, "
        "actionable step, and always include specific quantities. "
        "Keep it under 45 words, or under 30 if the farmer's own language "
        "needs more than the Latin alphabet, since an SMS carries less than "
        "half as much text in that case. "
        "Always finish your final sentence - a complete short answer is much "
        "more useful to a farmer than a longer one that gets cut off."
    ),
}


def style_for(channel: str) -> str:
    return CHANNEL_STYLE.get((channel or "web").lower(), CHANNEL_STYLE["web"])


def extract_markdown_content(text: str) -> str:
    """Unwrap a ```markdown fenced block if the model emitted one."""
    match = re.search(r"```markdown\n([\s\S]*?)\n```", text)
    return match.group(1).strip() if match else text


def get_open_ended_answer(query: str, history: Optional[List[dict]], channel: str = "web") -> str:
    """
    query: str - the farmer's latest question
    history: list[dict] - [{"role": "user"/"assistant", "content": "..."}]
    """
    print("QUERY:", query)
    print("HISTORY:", history)

    history_text = "\n".join(
        f"{h.get('role', 'user').capitalize()}: {h.get('content', '')}"
        for h in (history or [])
    )

    style = style_for(channel)
    temporal = temporal_context()

    prompt = f"""
    **Role and Goal:**
    You are a highly knowledgeable agronomist and expert agricultural advisor, specializing in Indian farming conditions. Your goal is to provide a detailed, scientifically valid, and practical answer to the farmer's question, using the provided conversation history for context.

    **Current date and season:**
    {temporal}

    **Critical Instructions:**
    1.  **Content:** The advice must be accurate, practical for Indian conditions, and directly address the farmer's latest query.
    2.  **Format:** {style}
    3.  **Language (overrides everything above):** Reply in the SAME language and SAME script the farmer used in their latest question. English question, English answer. Hindi question, Hindi answer. Hinglish question, Hinglish answer. Never translate, and never switch script because the topic is Indian.

    ---

    **Conversation Context:**

    **Conversation so far:**
    {history_text}

    **Farmer's latest question:**
    {query}

    ---

    **Assistant's Expert Agronomic Advice:**
    """

    return llm.invoke([HumanMessage(content=prompt)]).content.strip()


def get_farming_advice(location, state, crop, gathered, farmer_query,
                       channel: str = "web") -> str:
    """Compose the final advisory from whatever data was gathered.

    Only tools that actually ran appear in the prompt. Padding the context with
    "unavailable" placeholders for tools this question never needed gave the
    model more to ignore and, in practice, more to get confused by.
    """
    style = style_for(channel)
    temporal = temporal_context()

    context_lines = [
        f"- Location: {location or 'unknown'}",
        f"- State: {state or 'unknown'}",
        f"- Crop: {crop or 'unknown'}",
    ]
    for label, key in (("Soil", "soil"), ("Weather", "weather"),
                       ("Mandi Price", "mandi"), ("Knowledge Base", "kb")):
        value = gathered.get(key)
        if value:
            context_lines.append(f"- {label}: {value}")
    context = "\n    ".join(context_lines)

    prompt = f"""
    You are an expert agronomist and agricultural advisor.
    Answer the farmer's question using the provided data.
    Always respond in the farmer's query language:
    Farmer's Query: {farmer_query}.

    {temporal}

    Constraints:
    - {style}
    - Be practical and farmer-friendly.
    - Reply in the SAME language and SAME script the farmer used. English question, English answer. Never switch script because the topic is Indian.
    - Always reference the relevant data points (soil values, weather, mandi prices, etc.) in your answer.
    - If the farmer asks a direct factual question - the temperature, the humidity, the rainfall, the price - ANSWER IT with the exact figure from the Context. Never say you cannot provide live data when the figure is sitting in the Context above. If only part of what they asked for is present, give that part and say the rest is not available.
    - The Context is measured data for this farmer's own location. Trust it over any assumption the farmer states: if they say the weather is dry and the data shows heavy rain, tell them plainly what the data says.
    - Do not invent facts beyond the given data.
    - Format response clearly into sections.

    Context:
    {context}
    - Farmer's Question: {farmer_query}
    """

    return llm.invoke([HumanMessage(content=prompt)]).content


def gather(tools, *, lat, lon, state, crop, query) -> dict:
    """Run the selected tools concurrently.

    They are independent network calls, so running them in sequence meant the
    slowest upstream set the floor for every answer. One failing tool no longer
    delays or breaks the others.
    """
    if not tools:
        return {}

    calls = {
        "soil":    lambda: soil_tool(lat, lon),
        "weather": lambda: weather_openmeteo(lat, lon),
        "mandi":   lambda: get_state_data(state, crop),
        "kb":      lambda: query_kb(query),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=len(tools)) as pool:
        futures = {pool.submit(calls[t]): t for t in tools if t in calls}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"Tool {name} failed: {e}")
    return results


class AgentResult:
    """An answer plus what the agent learned about the farmer along the way.

    The facts are what let a profile improve over time: whatever the parser
    picked out of this message is worth remembering for the next one.
    """

    __slots__ = ("answer", "crop", "state", "location", "latitude", "longitude",
                 "tools_used", "missing_slots", "intent")

    def __init__(self, answer, crop=None, state=None, location=None,
                 latitude=None, longitude=None, tools_used=None,
                 missing_slots=None, intent="general"):
        self.answer = answer
        self.crop = crop
        self.state = state
        self.location = location
        self.latitude = latitude
        self.longitude = longitude
        self.tools_used = tools_used or []
        # What the farmer still has not told us - lets the caller ask for one
        # precise thing instead of a generic "where are you?".
        self.missing_slots = missing_slots or []
        self.intent = intent


def _known(value) -> str | None:
    if not value or str(value).strip().lower() == "unknown":
        return None
    return str(value).strip()


def run_agent(
    query: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    history: Optional[List[dict]] = None,
    channel: str = "web",
) -> AgentResult:
    """Answer a farmer's question and report what was learned and used."""
    query_final = get_farming_query(query, history)
    print(f"Final query after refinement: {query_final}")

    structured_input = extract_farm_info(query_final)

    crop = structured_input.get("crop_type", "unknown")
    state = structured_input.get("state", "unknown")
    location = structured_input.get("location", "unknown")
    answer = structured_input.get("answer", "unknown")
    intent = planner.normalise_intent(structured_input.get("intent"))

    print(f"Extracted Crop: {crop}, State: {state}, Location: {location}, "
          f"intent: {intent}, answer: {answer}")

    facts = {
        "crop": _known(crop),
        "state": _known(state),
        "location": _known(location),
    }

    # Non-agricultural query: the parser already answered it.
    if answer != "unknown" and crop == "unknown" and state == "unknown" and location == "unknown":
        return AgentResult(answer, tools_used=["direct"])

    # A location named in this message beats a remembered or browser one, but
    # only if geocoding actually resolves it.
    lat, lon = latitude, longitude
    if facts["location"]:
        geo_lat, geo_lon = get_location(facts["location"])
        if geo_lat is not None and geo_lon is not None:
            lat, lon = geo_lat, geo_lon

    facts["latitude"], facts["longitude"] = lat, lon
    print(f"Coordinates: lat={lat}, lon={lon}")

    # Which tools this question can actually use, given what we know. A leaf
    # spot question no longer waits on mandi prices it will never mention.
    tools = planner.plan_tools(
        intent,
        has_coords=lat is not None and lon is not None,
        state=facts["state"],
        kb_available=kb_available(),
    )
    missing = planner.missing_slots(
        intent, crop=facts["crop"], location=facts["location"], state=facts["state"]
    )
    print(f"Plan: intent={intent} tools={sorted(tools) or 'none'} missing={missing or 'nothing'}")

    if not tools:
        return AgentResult(
            extract_markdown_content(get_open_ended_answer(query_final, history, channel)),
            tools_used=["general"], missing_slots=missing, intent=intent, **facts
        )

    gathered = gather(tools, lat=lat, lon=lon, state=state, crop=crop, query=query_final)

    # A knowledge base answer is already a complete, sourced response.
    if gathered.get("kb") and tools == {"kb"}:
        return AgentResult(gathered["kb"], tools_used=["knowledge_base"],
                           missing_slots=missing, intent=intent, **facts)

    final_response = extract_markdown_content(
        get_farming_advice(location, state, crop, gathered, query, channel)
    )
    print(f"Final response: {final_response}")
    return AgentResult(
        final_response, tools_used=sorted(gathered.keys()),
        missing_slots=missing, intent=intent, **facts
    )


def agent(
    query: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    history: Optional[List[dict]] = None,
    channel: str = "web",
) -> str:
    """Answer text only. Kept for callers that do not need the extracted facts."""
    return run_agent(query, latitude, longitude, history, channel).answer

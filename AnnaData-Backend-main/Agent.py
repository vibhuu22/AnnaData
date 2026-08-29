from typing import List, Optional

from langchain.schema import HumanMessage
from langchain.output_parsers import ResponseSchema, StructuredOutputParser

from utils import llm
from Address_Convertor import get_location
from Mandi_Price_Tool import get_state_data
from Query_Parser import extract_farm_info
from weather_tool import weather_openmeteo
from Soil_Tool import soil_tool
from Refined_Farmer_Query import get_farming_query
from Web_Crawler import query_kb, is_available as kb_available
import re


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

    prompt = f"""
    **Role and Goal:**
    You are a highly knowledgeable agronomist and expert agricultural advisor, specializing in Indian farming conditions. Your goal is to provide a detailed, scientifically valid, and practical answer to the farmer's question, using the provided conversation history for context.

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


def get_farming_advice(location, state, crop, soil, weather, mandi_price,
                       kb_answer, farmer_query, channel: str = "web") -> str:
    """Compose the final advisory from all gathered tool data.

    Tools that are unconfigured or failed pass through an explicit "unavailable"
    string; the prompt tells the model to ignore those rather than invent data.
    """
    style = style_for(channel)

    prompt = f"""
    You are an expert agronomist and agricultural advisor.
    Answer the farmer's question using the provided data.
    Always respond in the farmer's query language:
    Farmer's Query: {farmer_query}.

    Constraints:
    - {style}
    - Be practical and farmer-friendly.
    - Reply in the SAME language and SAME script the farmer used. English question, English answer. Never switch script because the topic is Indian.
    - Always reference the relevant data points (soil values, weather, mandi prices, etc.) in your answer.
    - If the farmer asks a direct factual question - the temperature, the humidity, the rainfall, the price - ANSWER IT with the exact figure from the Context. Never say you cannot provide live data when the figure is sitting in the Context above. If only part of what they asked for is present, give that part and say the rest is not available.
    - The Context is measured data for this farmer's own location. Trust it over any assumption the farmer states: if they say the weather is dry and the data shows heavy rain, tell them plainly what the data says.
    - Some data sources may be marked unavailable. Silently ignore those; never mention missing data sources to the farmer, and never invent values for them.
    - Do not invent facts beyond the given data.
    - Format response clearly into sections.

    Context:
    - Location: {location}
    - State: {state}
    - Crop: {crop}
    - Soil: {soil}
    - Weather: {weather}
    - Mandi Price: {mandi_price}
    - Knowledge Base Answer: {kb_answer}
    - Farmer's Question: {farmer_query}
    """

    return llm.invoke([HumanMessage(content=prompt)]).content


def kb_router(query: str) -> bool:
    """Decide whether the query needs a knowledge base lookup.

    Returns True for cold storage or government scheme questions. Skips the LLM
    call entirely when no knowledge base is configured.
    """
    if not kb_available():
        return False

    response_schemas = [
        ResponseSchema(
            name="query",
            description='Return "YES" if the query is about storage or government schemes, otherwise "NO".',
        )
    ]
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)

    prompt = f"""
    You are a query classifier for an agricultural assistant.

    Farmer's query: "{query}"

    Task:
    Classify the query:
    - If it's about "storage or cold storage" OR "government schemes" (subsidies, support schemes, loan schemes, insurance, etc.), return YES.
    - Otherwise, return NO.

    {output_parser.get_format_instructions()}
    """

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        parsed = output_parser.parse(response.content)
        return parsed["query"].strip().upper() == "YES"
    except Exception as e:
        print("Router parsing error:", e)
        return False


class AgentResult:
    """An answer plus what the agent learned about the farmer along the way.

    The facts are what let a profile improve over time: whatever the parser
    picked out of this message is worth remembering for the next one.
    """

    __slots__ = ("answer", "crop", "state", "location", "latitude", "longitude", "tools_used")

    def __init__(self, answer, crop=None, state=None, location=None,
                 latitude=None, longitude=None, tools_used=None):
        self.answer = answer
        self.crop = crop
        self.state = state
        self.location = location
        self.latitude = latitude
        self.longitude = longitude
        self.tools_used = tools_used or []


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

    print(f"Extracted Crop: {crop}, State: {state}, Location: {location}, answer: {answer}")

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

    # Schemes and storage are location-independent, so try the knowledge base
    # before falling back for want of coordinates.
    if kb_router(query_final):
        print("Routing to knowledge base")
        kb_answer = query_kb(query_final)
        if kb_answer:
            return AgentResult(kb_answer, tools_used=["knowledge_base"], **facts)
    else:
        kb_answer = ""

    if lat is None or lon is None:
        return AgentResult(
            extract_markdown_content(get_open_ended_answer(query_final, history, channel)),
            tools_used=["general"], **facts
        )

    soil = soil_tool(lat, lon)
    weather = weather_openmeteo(lat, lon)
    mandi_price = get_state_data(state, crop)

    final_response = extract_markdown_content(
        get_farming_advice(location, state, crop, soil, weather,
                           mandi_price, kb_answer or "", query, channel)
    )
    print(f"Final response: {final_response}")
    return AgentResult(
        final_response, tools_used=["soil", "weather", "mandi"], **facts
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

from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.prompts import PromptTemplate
from planner import normalise_intent
from utils import llm

UNKNOWN = {
    "location": "unknown",
    "state": "unknown",
    "crop_type": "unknown",
    "answer": "unknown",
    "intent": "general",
}

# Intent rides along on this extraction call, which runs for every query
# anyway, so choosing tools costs no extra model call.
INTENTS = (
    "disease_pest, sowing_planting, fertiliser_nutrition, irrigation_water, "
    "weather_query, market_price, scheme_subsidy, storage_postharvest, general"
)


def extract_farm_info(farmer_input: str) -> dict:
    """Extract location / state / crop from a farmer query.

    Always returns the same four keys. The old error branch returned a
    differently shaped dict, so callers silently got None for `state`.
    """
    response_schemas = [
        ResponseSchema(
            name="location",
            description="Location of the farm (village, district, state, etc.)",
        ),
        ResponseSchema(
            name="state",
            description="State where the farm is located. Use the location "
                        "information to locate the Indian state",
        ),
        ResponseSchema(name="crop_type", description="Type of crop being grown"),
        ResponseSchema(
            name="answer",
            description="If the query is not related to agriculture, provide a "
                        "short answer to the query in the query language.",
        ),
        ResponseSchema(
            name="intent",
            description=f"What the farmer wants. Exactly one of: {INTENTS}. "
                        "disease_pest for crop problems, pests, diseases or damage. "
                        "sowing_planting for when or how to sow or plant. "
                        "fertiliser_nutrition for fertiliser, manure or deficiency. "
                        "irrigation_water for watering and drainage. "
                        "weather_query for a direct question about weather. "
                        "market_price for prices, selling or what is profitable. "
                        "scheme_subsidy for government schemes, subsidies, loans, insurance. "
                        "storage_postharvest for storage, cold storage or after harvest. "
                        "general for anything else.",
        ),
    ]

    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()

    prompt = PromptTemplate(
        template="""
    You are a farming assistant that extracts structured agricultural data from
    farmer queries. Always translate the language of the query into English.

    Farmer's Input:
    {farmer_input}

    {format_instructions}

    Make sure:
    - "location" is just the location.
    - "state" is the state name, not the full address.
    - "crop_type" is only the crop name.
    - "answer" is a short answer to the query if it is not related to agriculture.
    - "intent" is exactly one of the listed values, nothing else.
    If information is missing, put "unknown".
    """,
        input_variables=["farmer_input"],
        partial_variables={"format_instructions": format_instructions},
    )

    try:
        _input = prompt.format_prompt(farmer_input=farmer_input)
        output = llm.invoke(_input.to_messages()).content
        print(f"LLM output: {output}")

        if not output:
            return dict(UNKNOWN)

        parsed = output_parser.parse(output)
        # Normalise: guarantee all four keys, never None.
        result = {k: (parsed.get(k) or UNKNOWN[k]) for k in UNKNOWN}
        result["intent"] = normalise_intent(result["intent"])
        return result

    except Exception as e:
        print(f"Query parsing failed: {e}")
        return dict(UNKNOWN)

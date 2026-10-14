import os
import uuid
import json
import requests

from dotenv import load_dotenv

from memory import search_emergencies


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


API_KEY = os.getenv(
    "LYZR_API_KEY"
)


AGENT_ID = os.getenv(
    "LYZR_AGENT_ID"
)


USER_ID = os.getenv(
    "LYZR_USER_ID",
    "resq-ai-demo-user"
)


API_URL = (
    "https://agent-prod.studio.lyzr.ai/"
    "v3/inference/chat/"
)


# =========================================================
# ASK LYZR AI
# =========================================================

def ask_lyzr(
    emergency_report: str,
    session_id: str
) -> str:
    """
    Search previous emergency information
    from Qdrant and send the current emergency
    report together with relevant memory to Lyzr AI.
    """


    # =====================================================
    # CHECK API CONFIGURATION
    # =====================================================

    if not API_KEY or not AGENT_ID:

        raise ValueError(
            "Missing LYZR_API_KEY or "
            "LYZR_AGENT_ID in your .env file."
        )


    # =====================================================
    # CLEAN CURRENT REPORT
    # =====================================================

    emergency_report = (
        emergency_report or ""
    ).strip()


    if not emergency_report:

        return (
            "No emergency report was received."
        )


    # =====================================================
    # STEP 1:
    # SEARCH PREVIOUS EMERGENCIES
    # =====================================================

    try:

        memories = search_emergencies(
            emergency_report,
            limit=3
        )

    except Exception as error:

        print(
            "⚠️ Qdrant search warning:",
            error
        )

        memories = []


    # =====================================================
    # STEP 2:
    # CREATE MEMORY CONTEXT
    # =====================================================

    if memories:

        memory_context = "\n".join(

            f"- {memory}"

            for memory in memories

        )

    else:

        memory_context = (
            "No previous emergency information "
            "was found."
        )


    # =====================================================
    # STEP 3:
    # CREATE LYZR PROMPT
    # =====================================================

    message = f"""
You are ResQ-AI, an AI decision-support system
for simulated emergency response coordination.

==================================================
CURRENT EMERGENCY REPORT
==================================================

{emergency_report}


==================================================
RELEVANT PREVIOUS EMERGENCY INFORMATION
==================================================

{memory_context}


==================================================
IMPORTANT INSTRUCTIONS
==================================================

Analyze the CURRENT emergency report first.

Previous emergency information is only background
context. Do not treat previous information as a
current fact unless the current report supports it.

Clearly separate:

1. Current confirmed information
2. Previous/relevant information
3. Unconfirmed or missing information

For the current emergency:

- Identify the incident or incidents.
- Identify the location if provided.
- Identify the number of people affected.
- Identify vulnerable people such as children or elderly
  people if mentioned.
- Assess the priority of each incident.
- Identify required resources.
- Compare required resources with the resources mentioned
  in the current report.
- Identify resource shortages or possible conflicts.
- Propose an ordered response plan.
- Mention important missing information that should be
  verified.

If a location is provided, clearly mention it in the
incident analysis.

If the report does not contain enough information,
do not invent facts. Clearly state what is unknown.

Do not claim that real emergency services, vehicles,
fire trucks, ambulances, rescue teams, or personnel
have actually been dispatched.

This is a simulated AI decision-support system.


==================================================
RESPONSE FORMAT
==================================================

Use the following structure:

## Emergency Summary

Briefly summarize the current emergency.

## Incident Analysis

For each incident, mention:

- Incident
- Location
- People affected
- Vulnerable people
- Current known resources
- Assessment

## Priority Assessment

Give each incident a priority such as:

- CRITICAL
- HIGH
- MEDIUM
- LOW

Explain why.

## Resource Requirements

List the resources needed for the current incident.

## Proposed Resource Allocation

Suggest how the currently mentioned resources
could be prioritized.

Do not claim that resources were actually dispatched.

## Immediate Recommended Actions

Give a short ordered list of the most important
next actions.

## Resource Shortages

Mention resources that appear insufficient or
unknown.

## Missing Information

List information that should be verified.

## Reasons for Decisions

Briefly explain why the incident received its
priority and why the proposed response was selected.

Keep the response clear, structured, and suitable
for an emergency coordination dashboard.
"""


    # =====================================================
    # STEP 4:
    # CREATE API PAYLOAD
    # =====================================================

    payload = {

        "user_id": USER_ID,

        "agent_id": AGENT_ID,

        "session_id": session_id,

        "message": message,

        "system_prompt_variables": {},

        "filter_variables": {},

        "features": []
    }


    # =====================================================
    # STEP 5:
    # API HEADERS
    # =====================================================

    headers = {

        "x-api-key": API_KEY,

        "Content-Type": "application/json",

        "accept": "application/json"
    }


    # =====================================================
    # STEP 6:
    # SEND REQUEST TO LYZR
    # =====================================================

    try:

        response = requests.post(

            API_URL,

            json=payload,

            headers=headers,

            timeout=90
        )


        response.raise_for_status()


    except requests.Timeout as exc:

        raise RuntimeError(

            "Lyzr took too long to respond. "
            "Please try again."

        ) from exc


    except requests.RequestException as exc:

        detail = ""


        if exc.response is not None:

            detail = (
                exc.response.text[:1000]
            )


        raise RuntimeError(

            f"Lyzr API request failed: "
            f"{exc}. {detail}"

        ) from exc


    # =====================================================
    # STEP 7:
    # READ LYZR RESPONSE
    # =====================================================

    try:

        data = response.json()

    except ValueError:

        return response.text


    # =====================================================
    # RESPONSE IS DIRECT STRING
    # =====================================================

    if isinstance(data, str):

        return data


    # =====================================================
    # RESPONSE IS DICTIONARY
    # =====================================================

    if isinstance(data, dict):


        for key in (

            "response",

            "answer",

            "output",

            "message",

            "text"

        ):

            value = data.get(
                key
            )


            if (

                isinstance(value, str)

                and value.strip()

            ):

                return value.strip()


        # -------------------------------------------------
        # FALLBACK:
        # RETURN COMPLETE JSON
        # -------------------------------------------------

        return json.dumps(

            data,

            indent=2,

            ensure_ascii=False
        )


    # =====================================================
    # FALLBACK
    # =====================================================

    return str(data)


# =========================================================
# CREATE NEW SESSION ID
# =========================================================

def new_session_id():

    """
    Create a unique demo session.
    """

    return str(
        uuid.uuid4()
    )
from fastapi import FastAPI, BackgroundTasks, Request
from datetime import datetime
import json
import threading

from memory import store_emergency
from lyzr_agent import ask_lyzr, new_session_id


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="ResQ-AI Omi Backend",
    description="Voice webhook backend for ResQ-AI"
)


# =========================================================
# TEMPORARY MEMORY
# =========================================================

realtime_memory = {}

latest_result = {
    "status": "waiting",
    "transcript": "",
    "response": "",
    "updated_at": ""
}


# =========================================================
# LOCK
# =========================================================

result_lock = threading.Lock()


# =========================================================
# HELPER - UPDATE LATEST RESULT
# =========================================================

def update_latest_result(
    status=None,
    transcript=None,
    response=None
):

    global latest_result

    with result_lock:

        if status is not None:
            latest_result["status"] = status

        if transcript is not None:
            latest_result["transcript"] = transcript

        if response is not None:
            latest_result["response"] = response

        latest_result["updated_at"] = (
            datetime.now().isoformat()
        )


# =========================================================
# EXTRACT TEXT FROM OMI PAYLOAD
# =========================================================

def extract_text(data):

    # -----------------------------------------
    # DIRECT STRING
    # -----------------------------------------

    if isinstance(data, str):

        return data.strip()


    # -----------------------------------------
    # INVALID DATA
    # -----------------------------------------

    if not isinstance(data, dict):

        return ""


    # -----------------------------------------
    # COMMON TEXT FIELDS
    # -----------------------------------------

    for key in [
        "text",
        "transcript",
        "content"
    ]:

        value = data.get(key)

        if (
            isinstance(value, str)
            and value.strip()
        ):

            return value.strip()


    # -----------------------------------------
    # TRANSCRIPT SEGMENTS
    # -----------------------------------------

    segments = data.get(
        "transcript_segments"
    )


    if isinstance(segments, list):

        texts = []


        for segment in segments:

            if not isinstance(
                segment,
                dict
            ):

                continue


            for key in [
                "text",
                "transcript",
                "content"
            ]:

                value = segment.get(key)


                if (
                    isinstance(value, str)
                    and value.strip()
                ):

                    texts.append(
                        value.strip()
                    )

                    break


        if texts:

            return " ".join(texts)


    # -----------------------------------------
    # NESTED MESSAGE
    # -----------------------------------------

    message = data.get("message")


    if isinstance(message, dict):

        nested_text = extract_text(
            message
        )

        if nested_text:

            return nested_text


    return ""


# =========================================================
# PROCESS EMERGENCY
# =========================================================

def process_conversation(
    transcript,
    uid
):

    if not transcript:

        print(
            "⚠️ No transcript available."
        )

        return


    # =====================================================
    # PRINT TRANSCRIPT
    # =====================================================

    print()
    print("==============================")
    print("🎤 OMI FINAL TRANSCRIPT")
    print("==============================")
    print(transcript)


    # =====================================================
    # MARK AS PROCESSING
    # =====================================================

    update_latest_result(
        status="processing",
        transcript=transcript,
        response=""
    )


    # =====================================================
    # STORE IN QDRANT
    # =====================================================

    try:

        store_emergency(
            transcript
        )

        print(
            "✅ Stored in Qdrant successfully."
        )

    except Exception as error:

        print()
        print(
            "⚠️ Qdrant storage error:"
        )
        print(error)

        # Do NOT stop the AI processing.
        # Even if Qdrant fails, Lyzr can still
        # analyze the emergency.


    # =====================================================
    # SEND TO LYZR AI
    # =====================================================

    print()
    print("==============================")
    print("🤖 SENDING TO LYZR AI")
    print("==============================")


    try:

        # -----------------------------------------
        # CREATE NEW AI SESSION
        # -----------------------------------------

        session_id = new_session_id()


        # -----------------------------------------
        # ASK LYZR
        # -----------------------------------------

        response = ask_lyzr(
            transcript,
            session_id
        )


        # -----------------------------------------
        # SAVE AI RESPONSE
        # -----------------------------------------

        update_latest_result(
            status="completed",
            transcript=transcript,
            response=response
        )


        # -----------------------------------------
        # PRINT RESULT
        # -----------------------------------------

        print()
        print("==============================")
        print("🚨 RESQ-AI RESPONSE")
        print("==============================")
        print(response)


    except Exception as error:

        update_latest_result(
            status="error",
            transcript=transcript,
            response=str(error)
        )


        print()
        print(
            "❌ Lyzr processing error:"
        )

        print(error)


    # =====================================================
    # CLEAR REALTIME MEMORY
    # =====================================================

    if uid:

        realtime_memory.pop(
            uid,
            None
        )


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "service": "ResQ-AI Omi Backend",
        "message": "Omi webhook backend is running."
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "time": datetime.now().isoformat()
    }


# =========================================================
# GET LATEST RESULT
# =========================================================

@app.get("/latest-result")
def get_latest_result():

    with result_lock:

        return dict(
            latest_result
        )


# =========================================================
# OMI REALTIME WEBHOOK
# =========================================================

@app.post("/omi/realtime")
async def omi_realtime(
    request: Request
):

    try:

        data = await request.json()

    except Exception:

        return {
            "status": "received",
            "message": "Invalid JSON"
        }


    uid = request.query_params.get(
        "uid",
        "default"
    )


    text = extract_text(
        data
    )


    if text:

        print()
        print(
            "🎤 Omi Realtime Event Received"
        )

        print(
            "Transcript:",
            text
        )


        # -----------------------------------------
        # CREATE MEMORY FOR USER
        # -----------------------------------------

        if uid not in realtime_memory:

            realtime_memory[uid] = []


        # -----------------------------------------
        # STORE REALTIME PART
        # -----------------------------------------

        realtime_memory[uid].append(
            text
        )


    return {
        "status": "received"
    }


# =========================================================
# OMI CONVERSATION WEBHOOK
# =========================================================

@app.post("/omi/conversation")
async def omi_conversation(
    request: Request,
    background_tasks: BackgroundTasks
):

    data = await request.json()


    uid = request.query_params.get(
        "uid",
        "default"
    )


    print()
    print(
        "📥 Omi Conversation Webhook Received"
    )


    # =====================================================
    # TRY TO GET FINAL TRANSCRIPT
    # =====================================================

    transcript = extract_text(
        data
    )


    # =====================================================
    # FALLBACK TO REALTIME MEMORY
    # =====================================================

    if not transcript:

        previous_parts = realtime_memory.get(
            uid,
            []
        )


        if previous_parts:

            transcript = " ".join(
                previous_parts
            )


    # =====================================================
    # STILL NO TRANSCRIPT
    # =====================================================

    if not transcript:

        print(
            "⚠️ No transcript found."
        )


        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )
        )


        return {
            "status": "received",
            "message": "No transcript found"
        }


    # =====================================================
    # IMPORTANT:
    # CLEAR OLD AI RESPONSE
    # =====================================================

    update_latest_result(
        status="processing",
        transcript=transcript,
        response=""
    )


    # =====================================================
    # PRINT NEW EMERGENCY
    # =====================================================

    print()
    print("==============================")
    print("🚨 NEW VOICE EMERGENCY")
    print("==============================")
    print(transcript)


    # =====================================================
    # PROCESS IN BACKGROUND
    # =====================================================

    background_tasks.add_task(
        process_conversation,
        transcript,
        uid
    )


    # =====================================================
    # RETURN IMMEDIATELY TO OMI
    # =====================================================

    return {
        "status": "received",
        "message": "Transcript processing started"
    } 

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    report: str


@app.post("/analyze")
def analyze_emergency(request: AnalyzeRequest):
    report = request.report.strip()

    if not report:
        return {
            "status": "error",
            "response": "Please enter an emergency report."
        }

    try:
        store_emergency(report)
        session_id = new_session_id()
        result = ask_lyzr(report, session_id)

        return {
            "status": "completed",
            "transcript": report,
            "response": result
        }

    except Exception as error:
        return {
            "status": "error",
            "response": str(error)
        }

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    report: str


@app.post("/analyze")
def analyze_emergency(request: AnalyzeRequest):
    report = request.report.strip()

    if not report:
        return {
            "status": "error",
            "response": "Please enter an emergency report."
        }

    try:
        store_emergency(report)
        session_id = new_session_id()
        result = ask_lyzr(report, session_id)

        return {
            "status": "completed",
            "transcript": report,
            "response": result
        }

    except Exception as error:
        return {
            "status": "error",
            "response": str(error)
        }

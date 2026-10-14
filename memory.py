from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams
)
from fastembed import TextEmbedding
import uuid


# =========================================================
# QDRANT SETUP
# =========================================================

COLLECTION_NAME = "resq_emergency_memory"


# Local Qdrant database
qdrant = QdrantClient(
    path="./qdrant_data"
)


# Embedding model
embedder = TextEmbedding(
    "BAAI/bge-small-en-v1.5"
)


# =========================================================
# CREATE COLLECTION
# =========================================================

if not qdrant.collection_exists(
    COLLECTION_NAME
):

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,

        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        )
    )


# =========================================================
# CREATE VECTOR
# =========================================================

def create_embedding(text):

    vector = next(
        embedder.embed([text])
    )

    return vector.tolist()


# =========================================================
# STORE EMERGENCY MEMORY
# =========================================================

def store_emergency(
    emergency_report
):

    vector = create_embedding(
        emergency_report
    )

    qdrant.upsert(
        collection_name=COLLECTION_NAME,

        points=[
            PointStruct(
                id=str(uuid.uuid4()),

                vector=vector,

                payload={
                    "type": "emergency",
                    "text": emergency_report
                }
            )
        ]
    )

    return True


# =========================================================
# SEARCH PREVIOUS EMERGENCIES
# =========================================================

def search_emergencies(
    question,
    limit=3
):

    vector = create_embedding(
        question
    )

    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,

        query=vector,

        limit=limit
    )

    memories = []

    for point in results.points:

        memories.append(
            point.payload.get(
                "text",
                ""
            )
        )

    return memories
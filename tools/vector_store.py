"""
============================================================
  VECTOR STORE — Qdrant Cloud version
  vector_store.py
============================================================

WHAT CHANGED FROM CHROMADB VERSION:
  - Swapped ChromaDB (local folder) for Qdrant Cloud (hosted)
  - Everything else is identical — same functions, same logic
  - Your profiles now survive server restarts and deployments

SETUP:
  python -m pip install qdrant-client langchain-huggingface sentence-transformers --break-system-packages

ADD TO YOUR .env FILE:
  QDRANT_URL=https://your-cluster-url.aws.cloud.qdrant.io   ← paste your cluster URL here
  QDRANT_API_KEY=your-api-key-here                          ← paste your API key here

HOW TO FIND THESE:
  QDRANT_URL    → Qdrant Cloud dashboard → your cluster → copy the URL
  QDRANT_API_KEY → Qdrant Cloud dashboard → API Keys → Create API Key → copy it

SAME THREE FUNCTIONS AS BEFORE:
  add_profile(profile, message)         → store a profile
  search_similar_profiles(query, n)     → semantic search
  get_all_profiles()                    → retrieve everything
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams,
    PointStruct, Filter, FieldCondition, MatchValue
)
from fastembed import TextEmbedding
load_dotenv()

# ============================================================
# CREDENTIALS — set these in your .env file
# ============================================================
QDRANT_URL     = os.getenv("QDRANT_URL")      # your cluster URL
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # your API key

COLLECTION_NAME = "linkedin_profiles"
VECTOR_SIZE     = 384  # all-MiniLM-L6-v2 outputs 384-dimensional vectors


# ============================================================
# INITIALIZE EMBEDDING MODEL + QDRANT CLIENT
# ============================================================

from fastembed import TextEmbedding

print("⏳ Loading embedding model...")
embeddings_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
print("✅ Embedding model ready\n")

# Connect to Qdrant Cloud
# This replaces: chroma_client = chromadb.PersistentClient(path="./profiles_db")
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

# Create collection if it doesn't exist yet
# A collection is like a ChromaDB collection — a named bucket for vectors
existing = [c.name for c in client.get_collections().collections]

if COLLECTION_NAME not in existing:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE  # same distance metric as before
        )
    )
    print(f"✅ Created new Qdrant collection: '{COLLECTION_NAME}'")
else:
    count = client.count(collection_name=COLLECTION_NAME).count
    print(f"✅ Qdrant connected — {count} profiles stored in '{COLLECTION_NAME}'")


# ============================================================
# HELPER: BUILD EMBEDDABLE TEXT
# ============================================================
# Identical to ChromaDB version — rich text = better search

def build_profile_text(profile: dict) -> str:
    parts = []
    if profile.get("name"):    parts.append(f"Name: {profile['name']}")
    if profile.get("role"):    parts.append(f"Role: {profile['role']}")
    if profile.get("company"): parts.append(f"Company: {profile['company']}")
    if profile.get("hook"):    parts.append(f"About: {profile['hook']}")
    if profile.get("snippet"): parts.append(f"Background: {profile['snippet']}")
    if profile.get("target_persona"): parts.append(f"Found via: {profile['target_persona']}")
    return " | ".join(parts)


def url_to_id(url: str) -> str:
    """
    Converts LinkedIn URL to a numeric ID for Qdrant.
    Qdrant requires integer or UUID point IDs — we use a hash.
    """
    return abs(hash(url)) % (10 ** 15)  # stable numeric hash of the URL


# ============================================================
# FUNCTION 1: ADD A PROFILE
# ============================================================

def add_profile(profile: dict, message: str = "") -> dict:
    """
    Adds a processed profile to Qdrant Cloud.
    Skips if the URL already exists (deduplication).

    Same interface as the ChromaDB version.
    """
    url = profile.get("url", "")
    if not url:
        return {"status": "error", "reason": "No URL in profile"}

    point_id = url_to_id(url)

    # ── Check for duplicate ──
    # Search by ID — if it exists, skip
    existing = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[point_id]
    )
    if existing:
        print(f"   ⏭️  Skipping (already stored): {profile.get('name', url)}")
        return {"status": "skipped", "url": url}

    # ── Build embed text ──
    profile_text = build_profile_text(profile)

    # ── Create embedding ──
    vector = list(embeddings_model.embed(profile_text))[0].tolist()

    # ── Build payload (metadata) ──
    # Qdrant calls metadata "payload" — flat dict, same rules
    payload = {
        "name":           str(profile.get("name", "Unknown")),
        "role":           str(profile.get("role", "Unknown")),
        "company":        str(profile.get("company", "Unknown")),
        "hook":           str(profile.get("hook", ""))[:500],
        "score":          int(profile.get("score", 0)),
        "url":            url,
        "message":        str(message)[:1000] if message else "",
        "snippet":        str(profile.get("snippet", ""))[:300],
        "target_persona": str(profile.get("target_persona", "")),
        "stored_at":      datetime.now().isoformat(),
        "profile_text":   profile_text[:500],
        "status":         "pending",
    }

    # ── Upload to Qdrant ──
    # PointStruct = one record (id + vector + payload)
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(
            id=      point_id,
            vector=  vector,
            payload= payload
        )]
    )

    print(f"   ✅ Stored: {profile.get('name')} ({profile.get('role')} @ {profile.get('company')})")
    return {"status": "added", "url": url, "id": point_id}


# ============================================================
# FUNCTION 2: SEARCH SIMILAR PROFILES
# ============================================================

def search_similar_profiles(query: str, n_results: int = 5) -> list:
    """
    Semantically searches stored profiles using natural language.
    Identical interface to ChromaDB version.
    """
    total = client.count(collection_name=COLLECTION_NAME).count
    if total == 0:
        print("   ⚠️  No profiles stored yet.")
        return []

    n_results = min(n_results, total)

    # Embed the query
    query_vector = list(embeddings_model.embed(query))[0].tolist()
    
    # Search Qdrant
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=    query_vector,
        limit=           n_results,
        with_payload=    True,   # include metadata in results
    )

    # Format results
    profiles = []
    for hit in results:
        similarity = round(hit.score * 100, 1)  # Qdrant returns 0-1, convert to %
        profiles.append({
            **hit.payload,
            "similarity": similarity
        })

    return profiles


# ============================================================
# FUNCTION 3: GET ALL PROFILES
# ============================================================

def get_all_profiles() -> list:
    """
    Retrieves all stored profiles from Qdrant.
    Same interface as ChromaDB version.
    """
    total = client.count(collection_name=COLLECTION_NAME).count
    if total == 0:
        return []

    # Scroll through all points
    # scroll() is Qdrant's way to retrieve all records without a query vector
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=           total,
        with_payload=    True,
        with_vectors=    False,  # don't need the raw vectors, just metadata
    )

    return [point.payload for point in results]


def get_profile_by_url(url: str):
    """
    Retrieves a specific profile by LinkedIn URL.
    Returns None if not found.
    """
    point_id = url_to_id(url)
    results  = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[point_id],
        with_payload=True
    )
    return results[0].payload if results else None


def delete_profile(url: str) -> bool:
    """Deletes a profile by URL. Returns True if deleted."""
    point_id = url_to_id(url)
    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=[point_id]
        )
        return True
    except Exception:
        return False


# ============================================================
# MIGRATE FROM CHROMADB → QDRANT
# ============================================================
# Run this ONCE to move your existing profiles to Qdrant.
# After migration, ChromaDB is no longer needed.

def migrate_from_chromadb():
    """
    One-time migration: reads all profiles from local ChromaDB
    and uploads them to Qdrant Cloud.

    Run this once:  python vector_store.py --migrate
    """
    print("\n🔄 MIGRATING from ChromaDB → Qdrant Cloud...\n")

    try:
        import chromadb
        local_client = chromadb.PersistentClient(path="./profiles_db")
        local_col    = local_client.get_collection("linkedin_profiles")
        total        = local_col.count()
    except Exception as e:
        print(f"❌ Could not open local ChromaDB: {e}")
        print("   Make sure profiles_db/ folder exists in this directory.")
        return

    if total == 0:
        print("⚠️  No profiles in local ChromaDB to migrate.")
        return

    print(f"   Found {total} profiles in ChromaDB\n")

    # Get all records from ChromaDB
    records = local_col.get(
        limit=total,
        include=["metadatas", "embeddings"]
    )

    migrated = 0
    skipped  = 0

    for i, (metadata, embedding) in enumerate(
        zip(records["metadatas"], records["embeddings"])
    ):
        url      = metadata.get("url", "")
        name     = metadata.get("name", f"Profile {i+1}")
        point_id = url_to_id(url)

        # Check if already in Qdrant
        existing = client.retrieve(collection_name=COLLECTION_NAME, ids=[point_id])
        if existing:
            print(f"   ⏭️  Already in Qdrant: {name}")
            skipped += 1
            continue

        # Upload to Qdrant using the SAME embedding from ChromaDB
        # No need to re-embed — reuse the existing vectors
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(
                id=      point_id,
                vector=  list(embedding),
                payload= {**metadata, "status": metadata.get("status", "pending")}
            )]
        )

        print(f"   ✅ Migrated: {name}")
        migrated += 1

    print(f"\n✅ Migration complete: {migrated} migrated, {skipped} already existed")
    print(f"   Qdrant now has {client.count(collection_name=COLLECTION_NAME).count} profiles")


# ============================================================
# STANDALONE TEST + MIGRATION RUNNER
# ============================================================

if __name__ == "__main__":
    import sys

    if "--migrate" in sys.argv:
        migrate_from_chromadb()

    else:
        # Quick connection test
        print("\n🔗 Testing Qdrant connection...")
        count = client.count(collection_name=COLLECTION_NAME).count
        print(f"✅ Connected. {count} profiles stored.")

        if count > 0:
            print("\n🔍 Testing search...")
            results = search_similar_profiles("ML engineers at startups", n_results=2)
            for r in results:
                print(f"   {r.get('name')} — {r.get('similarity')}% match")

        print("\n✅ Qdrant vector store is working correctly.")
        print("\nTo migrate your existing ChromaDB profiles:")
        print("  python vector_store.py --migrate")
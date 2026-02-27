# """
# ============================================================
#   DAY 29–30: FASTAPI BACKEND
#   api.py
# ============================================================

# WHAT THIS FILE DOES:
#   Wraps your Python agent pipeline in a web server.
#   Any frontend (Next.js, mobile app, Postman) can now
#   talk to your agent over HTTP.

# TWO ENDPOINTS:
#   POST /run-agent  → triggers the pipeline, returns results
#   GET  /results    → returns all stored profiles from ChromaDB

# SETUP:
#   python -m pip install fastapi uvicorn python-multipart

# RUN THE SERVER:
#   uvicorn api:app --reload --port 8000

#   --reload means it restarts automatically when you save changes
#   --port 8000 is the default, change if that port is in use

# TEST IN BROWSER:
#   http://localhost:8000/docs  ← interactive API documentation
#   http://localhost:8000/results  ← all stored profiles

# FOLDER STRUCTURE:
#   tools/
#   ├── api.py               ← this file
#   ├── search_tool.py
#   ├── profile_analyzer.py
#   ├── message_drafter.py
#   ├── vector_store.py
#   ├── stable_pipeline.py
#   └── .env
# """

# import os
# import json
# import time
# import logging
# from datetime import datetime
# from typing import Optional
# from dotenv import load_dotenv

# from fastapi import FastAPI, HTTPException, BackgroundTasks
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel

# # Your pipeline modules
# from search_tool      import search_linkedin_profiles
# from profile_analyzer import analyze_linkedin_profile
# from message_drafter  import draft_message_from_profile
# from vector_store     import (
#     add_profile,
#     get_all_profiles,
#     get_profile_by_url,
#     search_similar_profiles,
#     collection
# )
# from stable_pipeline  import (
#     safe_search, safe_analyze, safe_draft,
#     is_low_quality_profile, is_good_message,
#     save_to_csv, get_csv_path
# )

# load_dotenv()

# # ── Logging ──
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("api")


# # ============================================================
# # CREATE THE FASTAPI APP
# # ============================================================

# app = FastAPI(
#     title="LinkedIn Outreach Agent API",
#     description="AI-powered LinkedIn profile search, analysis, and message drafting",
#     version="1.0.0"
# )


# # ============================================================
# # CORS MIDDLEWARE
# # ============================================================
# # This allows your Next.js frontend (localhost:3000) to talk
# # to this backend (localhost:8000) without browser blocking.
# # Without this you'll get a CORS error in the browser console.

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=False,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ============================================================
# # REQUEST / RESPONSE MODELS
# # ============================================================
# # Pydantic models define the shape of data coming in and going out.
# # FastAPI uses these to:
# #   1. Validate incoming request data automatically
# #   2. Generate API documentation
# #   3. Give you nice error messages when data is wrong

# class RunAgentRequest(BaseModel):
#     """What the frontend sends when triggering the agent."""
#     persona: str                    # e.g. "ML engineers at Series A startups India"
#     sender_context: str             # Who you are and why you're reaching out
#     max_profiles: Optional[int] = 5     # How many to process (default 5)
#     min_score: Optional[int] = 5        # Minimum relevance score (default 5)

#     class Config:
#         # Example data shown in /docs
#         json_schema_extra = {
#             "example": {
#                 "persona": "ML engineers working at Series A startups in India",
#                 "sender_context": "I'm building an AI recruiting tool for startups. Looking to talk to ML engineers about workflow pain points.",
#                 "max_profiles": 5,
#                 "min_score": 5
#             }
#         }


# class ProfileResult(BaseModel):
#     """One processed profile in the response."""
#     name: str
#     url: str
#     role: str
#     company: str
#     score: int
#     hook: str
#     message: str
#     status: str
#     timestamp: str


# class RunAgentResponse(BaseModel):
#     """What the API sends back after running the agent."""
#     success: bool
#     persona: str
#     profiles_found: int
#     profiles_processed: int
#     profiles_skipped: int
#     results: list[ProfileResult]
#     csv_path: str
#     duration_seconds: float
#     errors: list[str]


# class SearchRequest(BaseModel):
#     """For semantic search over stored profiles."""
#     query: str
#     n_results: Optional[int] = 5


# # ============================================================
# # HEALTH CHECK
# # ============================================================
# # Simple endpoint to confirm the server is running.
# # Frontend can call this on load to check connectivity.

# @app.get("/")
# def root():
#     return {
#         "status": "running",
#         "message": "LinkedIn Outreach Agent API",
#         "docs": "http://localhost:8000/docs",
#         "endpoints": [
#             "POST /run-agent",
#             "GET  /results",
#             "POST /search",
#             "GET  /stats"
#         ]
#     }


# @app.get("/health")
# def health_check():
#     """Quick health check for frontend to ping on load."""
#     return {
#         "status": "healthy",
#         "timestamp": datetime.now().isoformat(),
#         "profiles_stored": collection.count()
#     }


# # ============================================================
# # ENDPOINT 1: POST /run-agent
# # ============================================================
# # The main endpoint. Frontend sends a persona, this runs
# # the full pipeline and returns the results.

# @app.post("/run-agent", response_model=RunAgentResponse)
# def run_agent(request: RunAgentRequest):
#     """
#     Runs the full LinkedIn outreach pipeline.

#     1. Searches LinkedIn for profiles matching the persona
#     2. Analyzes each profile for relevance and hooks
#     3. Drafts a personalized outreach message
#     4. Stores results in ChromaDB
#     5. Returns all results as JSON

#     This is synchronous — the request waits until complete.
#     For 5 profiles expect 30-90 seconds response time.
#     """
#     start_time = time.time()
#     logger.info(f"Agent run started: persona='{request.persona}'")

#     results    = []
#     errors     = []
#     skipped    = 0

#     # ── Step 1: Search ──
#     logger.info("Searching for profiles...")
#     raw_profiles = safe_search(request.persona)

#     if not raw_profiles:
#         raise HTTPException(
#             status_code=503,
#             detail="Search failed — Tavily returned no results. Check your API key."
#         )

#     csv_path = get_csv_path(request.persona)
#     processed = 0

#     # ── Step 2-5: Analyze, draft, store, collect ──
#     for search_result in raw_profiles:
#         if processed >= request.max_profiles:
#             break

#         url  = search_result.get("url", "")
#         name = search_result.get("name", "Unknown")

#         logger.info(f"Processing: {name}")

#         # Guard: bad URL
#         if not url or "linkedin.com" not in url:
#             errors.append(f"Skipped '{name}': invalid URL")
#             skipped += 1
#             continue

#         # Guard: duplicate
#         if get_profile_by_url(url):
#             logger.info(f"Duplicate skipped: {name}")
#             skipped += 1
#             continue

#         # Analyze
#         profile = safe_analyze(url, search_result.get("snippet", ""), request.persona)
#         if not profile:
#             errors.append(f"Analysis failed for '{name}'")
#             skipped += 1
#             continue

#         profile["url"]            = url
#         profile["snippet"]        = search_result.get("snippet", "")
#         profile["target_persona"] = request.persona

#         score = int(profile.get("score", 0))

#         # Score filter
#         if score < request.min_score:
#             skipped += 1
#             continue

#         # Quality filter
#         low_quality, reason = is_low_quality_profile(profile)
#         if low_quality:
#             errors.append(f"Low quality skip '{name}': {reason}")
#             skipped += 1
#             continue

#         # Draft message
#         message = safe_draft(profile, request.sender_context)
#         if not message:
#             errors.append(f"Message drafting failed for '{name}'")
#             skipped += 1
#             continue

#         # Message quality check
#         good_msg, msg_reason = is_good_message(message)
#         if not good_msg:
#             errors.append(f"Bad message for '{name}': {msg_reason}")
#             skipped += 1
#             continue

#         # Store in ChromaDB
#         add_profile(profile, message)

#         # Save to CSV
#         save_to_csv(csv_path, profile, message, request.persona)

#         # Add to results
#         results.append(ProfileResult(
#             name=    str(profile.get("name", "Unknown")),
#             url=     url,
#             role=    str(profile.get("role", "Unknown")),
#             company= str(profile.get("company", "Unknown")),
#             score=   score,
#             hook=    str(profile.get("hook", ""))[:500],
#             message= message,
#             status=  "pending",
#             timestamp= datetime.now().isoformat()
#         ))

#         processed += 1
#         logger.info(f"Successfully processed: {name} (score: {score})")

#     duration = round(time.time() - start_time, 1)
#     logger.info(f"Agent run complete: {len(results)} results in {duration}s")

#     return RunAgentResponse(
#         success=             True,
#         persona=             request.persona,
#         profiles_found=      len(raw_profiles),
#         profiles_processed=  len(results),
#         profiles_skipped=    skipped,
#         results=             results,
#         csv_path=            csv_path,
#         duration_seconds=    duration,
#         errors=              errors
#     )


# # ============================================================
# # ENDPOINT 2: GET /results
# # ============================================================
# # Returns all stored profiles from ChromaDB.
# # Frontend calls this to show the history without re-running.

# @app.get("/results")
# def get_results():
#     """
#     Returns all profiles stored in ChromaDB.
#     Includes everyone ever processed, across all runs.
#     """
#     try:
#         profiles = get_all_profiles()
#         logger.info(f"Returning {len(profiles)} stored profiles")

#         return {
#             "success": True,
#             "count":   len(profiles),
#             "profiles": profiles
#         }

#     except Exception as e:
#         logger.error(f"Failed to fetch results: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================
# # ENDPOINT 3: POST /search
# # ============================================================
# # Semantic search over stored profiles.
# # "show me people in computer vision" without exact keyword match.

# @app.post("/search")
# def search_profiles(request: SearchRequest):
#     """
#     Semantically searches stored profiles using natural language.
#     Returns profiles most similar in meaning to your query.

#     Example queries:
#     - "computer vision engineers"
#     - "people who work in healthcare AI"
#     - "founders with engineering background"
#     """
#     try:
#         results = search_similar_profiles(request.query, request.n_results)
#         logger.info(f"Search '{request.query}' returned {len(results)} results")

#         return {
#             "success": True,
#             "query":   request.query,
#             "count":   len(results),
#             "results": results
#         }

#     except Exception as e:
#         logger.error(f"Search failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================
# # ENDPOINT 4: GET /stats
# # ============================================================
# # Dashboard stats for the frontend homepage.

# @app.get("/stats")
# def get_stats():
#     """Returns summary statistics about stored profiles."""
#     try:
#         all_profiles = get_all_profiles()

#         if not all_profiles:
#             return {
#                 "total_profiles": 0,
#                 "avg_score": 0,
#                 "high_quality_count": 0,
#                 "pending_count": 0,
#                 "personas": []
#             }

#         scores        = [int(p.get("score", 0)) for p in all_profiles]
#         avg_score     = round(sum(scores) / len(scores), 1)
#         high_quality  = sum(1 for s in scores if s >= 7)
#         pending       = sum(1 for p in all_profiles if p.get("status") == "pending")

#         # Unique personas searched
#         personas = list(set(
#             p.get("target_persona", "")
#             for p in all_profiles
#             if p.get("target_persona")
#         ))

#         return {
#             "total_profiles":    len(all_profiles),
#             "avg_score":         avg_score,
#             "high_quality_count": high_quality,
#             "pending_count":     pending,
#             "personas":          personas[:10]   # max 10 for display
#         }

#     except Exception as e:
#         logger.error(f"Stats failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================
# # ENDPOINT 5: DELETE /results/{url}
# # ============================================================
# # Delete a specific profile. Useful for cleanup.

# @app.delete("/results")
# def delete_profile_endpoint(url: str):
#     """
#     Deletes a profile from ChromaDB by LinkedIn URL.
#     Pass the URL as a query parameter:
#     DELETE /results?url=https://linkedin.com/in/someone
#     """
#     from vector_store import delete_profile

#     success = delete_profile(url)
#     if success:
#         return {"success": True, "message": f"Deleted profile: {url}"}
#     else:
#         raise HTTPException(status_code=404, detail=f"Profile not found: {url}")


# # ============================================================
# # RUN DIRECTLY (alternative to uvicorn command)
# # ============================================================

# if __name__ == "__main__":
#     import uvicorn
#     print("\n" + "🌐 "*20)
#     print("  FASTAPI SERVER STARTING")
#     print("🌐 "*20)
#     print("\n  API docs:    http://localhost:8000/docs")
#     print("  All results: http://localhost:8000/results")
#     print("  Stats:       http://localhost:8000/stats")
#     print("  Health:      http://localhost:8000/health\n")
#     uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)



"""
============================================================
  ASYNC JOB PROCESSING — api.py (updated)
============================================================

WHAT CHANGED FROM PREVIOUS VERSION:
  - POST /run-agent  → now returns job_id immediately (non-blocking)
  - GET  /jobs/{id}  → polls for job status and results
  - Agent runs in a background thread, not during the HTTP request

FLOW:
  1. Frontend POST /jobs → gets job_id back in <1 second
  2. Frontend polls GET /jobs/{job_id} every 3 seconds
  3. Server runs pipeline in background thread
  4. When done, GET /jobs/{job_id} returns full results
  5. Frontend renders results

ALL OTHER ENDPOINTS unchanged:
  GET /results, POST /search, GET /stats, DELETE /results
"""

import os
import uuid
import time
import logging
import threading
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from search_tool      import search_linkedin_profiles
from profile_analyzer import analyze_linkedin_profile
from message_drafter  import draft_message_from_profile
from vector_store     import (
    add_profile, get_all_profiles,
    get_profile_by_url, search_similar_profiles
)
from stable_pipeline import (
    safe_search, safe_analyze, safe_draft,
    is_low_quality_profile, is_good_message,
    save_to_csv, get_csv_path
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")


# ============================================================
# IN-MEMORY JOB STORE
# ============================================================
# Maps job_id (string) → job data (dict)
# Simple and works fine for a single server.
# In production you'd use Redis for this.

jobs: dict = {}


def create_job(persona: str, sender_context: str,
               max_profiles: int, min_score: int) -> str:
    """Creates a new job entry and returns its ID."""
    job_id = str(uuid.uuid4())[:8]  # Short ID like "a3f9b2c1"

    jobs[job_id] = {
        "id":                 job_id,
        "status":             "pending",
        "persona":            persona,
        "created_at":         datetime.now().isoformat(),
        "started_at":         None,
        "completed_at":       None,
        "current_step":       "Queued...",
        "profiles_found":     0,
        "profiles_processed": 0,
        "profiles_skipped":   0,
        "results":            [],
        "errors":             [],
        "csv_path":           "",
        "duration_seconds":   0,
        "error_message":      None,
    }

    logger.info(f"Job created: {job_id} for persona='{persona}'")
    return job_id


def update_job(job_id: str, **kwargs):
    """Updates job fields."""
    if job_id in jobs:
        jobs[job_id].update(kwargs)


# ============================================================
# THE PIPELINE — runs in a background thread
# ============================================================

def run_pipeline_job(job_id: str, persona: str, sender_context: str,
                     max_profiles: int, min_score: int):
    """
    Runs in a background thread.
    Updates job dict as it progresses so frontend can poll status.
    """
    start_time = time.time()

    try:
        update_job(job_id,
            status="running",
            started_at=datetime.now().isoformat(),
            current_step="Searching LinkedIn profiles via Tavily..."
        )

        # ── STEP 1: SEARCH ──
        raw_profiles = safe_search(persona)

        if not raw_profiles:
            update_job(job_id,
                status="error",
                error_message="Search returned no results. Check Tavily API key.",
                completed_at=datetime.now().isoformat()
            )
            return

        update_job(job_id,
            profiles_found=len(raw_profiles),
            current_step=f"Found {len(raw_profiles)} profiles. Analyzing..."
        )

        csv_path  = get_csv_path(persona)
        results   = []
        errors    = []
        skipped   = 0
        processed = 0

        # ── STEP 2-5: ANALYZE + DRAFT + STORE ──
        for i, search_result in enumerate(raw_profiles):
            if processed >= max_profiles:
                break

            url  = search_result.get("url", "")
            name = search_result.get("name", "Unknown")

            update_job(job_id,
                current_step=f"Analyzing {i+1}/{len(raw_profiles)}: {name}..."
            )

            if not url or "linkedin.com" not in url:
                errors.append(f"Skipped '{name}': invalid URL")
                skipped += 1
                continue

            if get_profile_by_url(url):
                skipped += 1
                continue

            profile = safe_analyze(url, search_result.get("snippet", ""), persona)
            if not profile:
                errors.append(f"Analysis failed for '{name}'")
                skipped += 1
                continue

            profile["url"]            = url
            profile["snippet"]        = search_result.get("snippet", "")
            profile["target_persona"] = persona

            score = int(profile.get("score", 0))

            if score < min_score:
                skipped += 1
                continue

            low_quality, reason = is_low_quality_profile(profile)
            if low_quality:
                errors.append(f"Low quality: '{name}' — {reason}")
                skipped += 1
                continue

            update_job(job_id,
                current_step=f"Drafting message for {profile.get('name', name)}..."
            )

            message = safe_draft(profile, sender_context)
            if not message:
                errors.append(f"Drafting failed for '{name}'")
                skipped += 1
                continue

            good_msg, msg_reason = is_good_message(message)
            if not good_msg:
                errors.append(f"Bad message for '{name}': {msg_reason}")
                skipped += 1
                continue

            add_profile(profile, message)
            save_to_csv(csv_path, profile, message, persona)

            results.append({
                "name":      str(profile.get("name", "Unknown")),
                "url":       url,
                "role":      str(profile.get("role", "Unknown")),
                "company":   str(profile.get("company", "Unknown")),
                "score":     score,
                "hook":      str(profile.get("hook", ""))[:500],
                "message":   message,
                "status":    "pending",
                "timestamp": datetime.now().isoformat(),
            })

            processed += 1

            # Publish partial results in real time
            update_job(job_id,
                profiles_processed=len(results),
                profiles_skipped=skipped,
                results=list(results),
                errors=list(errors),
                current_step=f"✓ {profile.get('name')} done. Continuing..."
            )

        duration = round(time.time() - start_time, 1)

        update_job(job_id,
            status="done",
            completed_at=datetime.now().isoformat(),
            profiles_processed=len(results),
            profiles_skipped=skipped,
            results=results,
            errors=errors,
            csv_path=csv_path,
            duration_seconds=duration,
            current_step=f"Complete — {len(results)} messages ready in {duration}s"
        )

        logger.info(f"Job {job_id} complete: {len(results)} results in {duration}s")

    except Exception as e:
        logger.error(f"Job {job_id} crashed: {e}")
        update_job(job_id,
            status="error",
            error_message=str(e),
            completed_at=datetime.now().isoformat(),
            current_step="Pipeline crashed"
        )


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="LinkedIn Outreach Agent API",
    description="Async job-based LinkedIn outreach agent",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# MODELS
# ============================================================

class RunAgentRequest(BaseModel):
    persona:        str
    sender_context: str
    max_profiles:   Optional[int] = 5
    min_score:      Optional[int] = 5

    class Config:
        json_schema_extra = {
            "example": {
                "persona": "ML engineers working at Series A startups in India",
                "sender_context": "I'm building an AI recruiting tool for startups.",
                "max_profiles": 5,
                "min_score": 5
            }
        }


class SearchRequest(BaseModel):
    query:     str
    n_results: Optional[int] = 5


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "status":  "running",
        "version": "2.0.0 (async jobs)",
        "endpoints": [
            "POST /jobs         → start job, returns job_id immediately",
            "GET  /jobs/{id}    → poll job status and results",
            "GET  /jobs         → list all jobs",
            "GET  /results      → all stored profiles",
            "POST /search       → semantic search",
            "GET  /stats        → dashboard stats",
        ]
    }


@app.get("/health")
def health():
    try:
        profiles_stored = len(get_all_profiles())
    except Exception:
        profiles_stored = -1  # -1 means Qdrant temporarily unreachable

    return {
        "status":          "healthy",
        "timestamp":       datetime.now().isoformat(),
        "profiles_stored": profiles_stored,
        "active_jobs":     len([j for j in jobs.values() if j["status"] == "running"]),
    }


@app.post("/jobs", status_code=202)
def start_job(request: RunAgentRequest):
    """
    Starts the agent pipeline as a background job.
    Returns job_id immediately — does NOT wait for results.
    Poll GET /jobs/{job_id} for status updates.
    """
    job_id = create_job(
        request.persona,
        request.sender_context,
        request.max_profiles,
        request.min_score
    )

    thread = threading.Thread(
        target=run_pipeline_job,
        args=(job_id, request.persona, request.sender_context,
              request.max_profiles, request.min_score),
        daemon=True
    )
    thread.start()

    logger.info(f"Job {job_id} started in background thread")

    return {
        "job_id":   job_id,
        "status":   "pending",
        "message":  "Job started. Poll GET /jobs/{job_id} for status.",
        "poll_url": f"/jobs/{job_id}"
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Returns current status and results of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return jobs[job_id]


@app.get("/jobs")
def list_jobs():
    """Lists all jobs, most recent first."""
    sorted_jobs = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return {
        "count": len(sorted_jobs),
        "jobs": [{
            "id":            j["id"],
            "status":        j["status"],
            "persona":       j["persona"],
            "created_at":    j["created_at"],
            "results_count": len(j["results"]),
            "current_step":  j["current_step"],
        } for j in sorted_jobs]
    }


@app.get("/results")
def get_results():
    try:
        profiles = get_all_profiles()
        return {"success": True, "count": len(profiles), "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
def search_profiles(request: SearchRequest):
    try:
        results = search_similar_profiles(request.query, request.n_results)
        return {"success": True, "query": request.query,
                "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
def get_stats():
    try:
        all_profiles = get_all_profiles()
        if not all_profiles:
            return {"total_profiles": 0, "avg_score": 0,
                    "high_quality_count": 0, "pending_count": 0, "personas": []}

        scores       = [int(p.get("score", 0)) for p in all_profiles]
        avg_score    = round(sum(scores) / len(scores), 1)
        high_quality = sum(1 for s in scores if s >= 7)
        pending      = sum(1 for p in all_profiles if p.get("status") == "pending")
        personas     = list(set(p.get("target_persona", "")
                               for p in all_profiles if p.get("target_persona")))

        return {
            "total_profiles":     len(all_profiles),
            "avg_score":          avg_score,
            "high_quality_count": high_quality,
            "pending_count":      pending,
            "personas":           personas[:10]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/results")
def delete_profile_endpoint(url: str):
    from vector_store import delete_profile
    success = delete_profile(url)
    if success:
        return {"success": True, "message": f"Deleted: {url}"}
    raise HTTPException(status_code=404, detail=f"Not found: {url}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
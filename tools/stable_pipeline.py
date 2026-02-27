"""
============================================================
  DAY 28: ERROR HANDLING + STABILITY
  stable_pipeline.py
============================================================

WHAT THIS FILE ADDS:
  - Proper logging (timestamps, severity levels, file output)
  - Try/except around every API call
  - Retry logic with exponential backoff for rate limits
  - Data quality checks (detect "Not found" profiles)
  - Graceful degradation — one failure doesn't kill the run
  - Intentional failure tests so you can see it working

HOW TO READ THIS FILE:
  The first half = utilities (logging, retry, validation)
  The second half = the same pipeline as before, hardened
"""

import os
import csv
import json
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

from search_tool      import search_linkedin_profiles
from profile_analyzer import analyze_linkedin_profile
from message_drafter  import draft_message_from_profile
from vector_store     import add_profile, get_profile_by_url

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ============================================================
# LOGGING SETUP
# ============================================================
# One-time setup at the top of your file.
# After this, use logger.info(), logger.warning(), logger.error()
# instead of print() for anything important.
#
# We keep print() for the nice visual output (banners, progress).
# We use logger for operational events (errors, skips, API calls).

def setup_logging(log_file: str = "pipeline.log") -> logging.Logger:
    """
    Sets up logging to both terminal and a file.

    Levels (lowest to highest severity):
      DEBUG    → very detailed, usually too noisy for normal use
      INFO     → normal operations ("profile stored", "search complete")
      WARNING  → something unexpected but recoverable ("rate limit hit")
      ERROR    → something failed but pipeline continues ("API call failed")
      CRITICAL → something failed that stops everything (rare)

    In the terminal we show WARNING and above (less noise).
    In the log file we save everything from INFO up (full record).
    """
    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.DEBUG)  # Capture everything at logger level

    # ── Terminal handler — shows WARNING and above ──
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_format = logging.Formatter(
        "%(levelname)s: %(message)s"
    )
    console_handler.setFormatter(console_format)

    # ── File handler — saves INFO and above to pipeline.log ──
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


# ============================================================
# RETRY LOGIC
# ============================================================
# Wraps any function call with automatic retry + backoff.
# Use this around API calls that might hit rate limits.

def with_retry(func, *args, max_retries: int = 3, **kwargs):
    """
    Calls func(*args, **kwargs) with exponential backoff retry.

    If the call fails with a rate limit or server error, it waits
    and tries again. Gives up after max_retries attempts.

    Exponential backoff: wait 2s, then 4s, then 8s between retries.
    This gives the API time to recover without hammering it.

    Returns the result if successful, None if all retries fail.
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)

        except Exception as e:
            error_str = str(e).lower()

            # ── Rate limit (429) — wait and retry ──
            if "429" in str(e) or "rate limit" in error_str:
                wait_time = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                logger.warning(
                    f"Rate limit hit on attempt {attempt+1}. "
                    f"Waiting {wait_time}s before retry..."
                )
                print(f"   ⏳ Rate limit — waiting {wait_time}s...")
                time.sleep(wait_time)

            # ── Server errors (500, 503) — retry ──
            elif any(code in str(e) for code in ["500", "502", "503"]):
                wait_time = 2 ** attempt
                logger.warning(
                    f"Server error on attempt {attempt+1}: {str(e)[:100]}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)

            # ── Other errors — log and fail immediately ──
            else:
                logger.error(f"Non-retryable error: {str(e)[:200]}")
                return None

    logger.error(f"All {max_retries} retries failed for {func.__name__}")
    return None


# ============================================================
# DATA QUALITY CHECKS
# ============================================================
# Detects profiles where we got so little information that
# processing them would produce useless output.

NOT_FOUND_VALUES = {"not found", "unknown", "n/a", "", "none"}

def is_low_quality_profile(profile: dict) -> tuple:
    """
    Checks if a profile has too little information to be useful.

    Returns (is_low_quality: bool, reason: str)

    A profile is low quality if:
    - Name, role, AND company are all "Not found"
    - Score is 0 (analyzer couldn't make sense of the content)
    - Hook is generic/empty
    """
    name    = str(profile.get("name", "")).lower().strip()
    role    = str(profile.get("role", "")).lower().strip()
    company = str(profile.get("company", "")).lower().strip()
    score   = int(profile.get("score", 0))
    hook    = str(profile.get("hook", "")).lower().strip()

    # All three key fields are missing
    missing_fields = sum(1 for v in [name, role, company] if v in NOT_FOUND_VALUES)
    if missing_fields >= 2:
        return True, f"Too many missing fields ({missing_fields}/3 unknown)"

    # Score of 0 means analyzer gave up
    if score == 0:
        return True, "Analyzer returned score of 0"

    # Hook is too short to be meaningful
    if len(hook) < 30:
        return True, f"Hook too short ({len(hook)} chars) — not enough info"

    # Hook contains generic fallback phrases
    generic_phrases = [
        "no public information",
        "could not be determined",
        "not enough information",
        "profile is private"
    ]
    if any(phrase in hook for phrase in generic_phrases):
        return True, "Hook contains generic fallback phrase"

    return False, ""


def is_good_message(message: str) -> tuple:
    """
    Quick sanity check on a drafted message.
    Returns (is_good: bool, reason: str)
    """
    if not message or len(message.strip()) < 20:
        return False, "Message too short or empty"

    word_count = len(message.split())
    if word_count > 200:
        return False, f"Message too long ({word_count} words)"

    # Check for obvious template failures
    failure_indicators = ["not found", "[name]", "[company]", "{{", "}}"]
    message_lower = message.lower()
    for indicator in failure_indicators:
        if indicator in message_lower:
            return False, f"Message contains template artifact: '{indicator}'"

    return True, ""


# ============================================================
# SAFE API WRAPPERS
# ============================================================
# Each wrapper catches exceptions so a single failure
# doesn't crash the whole pipeline.

def safe_search(persona: str) -> list:
    """Search with error handling. Returns empty list on failure."""
    try:
        logger.info(f"Searching for persona: '{persona}'")
        results = with_retry(
            search_linkedin_profiles.invoke,
            {"persona": persona}
        )
        if results is None:
            logger.error("Search failed after all retries")
            return []
        logger.info(f"Search returned {len(results)} profiles")
        return results

    except Exception as e:
        logger.error(f"Search crashed unexpectedly: {e}")
        return []


def safe_analyze(url: str, snippet: str, persona: str) -> dict:
    """Analyze with error handling. Returns error dict on failure."""
    try:
        logger.info(f"Analyzing: {url}")
        result = with_retry(
            analyze_linkedin_profile.invoke,
            {"url": url, "snippet": snippet, "target_persona": persona}
        )
        if result is None:
            logger.error(f"Analysis failed for {url}")
            return {"score": 0, "name": "Error", "hook": "Analysis failed"}
        return result

    except Exception as e:
        logger.error(f"Analysis crashed for {url}: {e}")
        return {"score": 0, "name": "Error", "hook": str(e)[:100]}


def safe_draft(profile: dict, sender_context: str) -> str:
    """Draft message with error handling. Returns empty string on failure."""
    try:
        name = profile.get("name", "unknown")
        logger.info(f"Drafting message for: {name}")
        result = with_retry(
            draft_message_from_profile,
            profile,
            sender_context
        )
        if result is None:
            logger.error(f"Message drafting failed for {name}")
            return ""
        return result

    except Exception as e:
        logger.error(f"Drafting crashed for {profile.get('name')}: {e}")
        return ""


# ============================================================
# CSV SETUP (same as before)
# ============================================================

CSV_COLUMNS = [
    "Name", "LinkedIn URL", "Role", "Company", "Relevance Score",
    "Personalization Hook", "Outreach Message", "Status",
    "Skip Reason", "Target Persona", "Timestamp"
]


def get_csv_path(persona: str) -> str:
    clean = persona.replace(" ", "_")[:40]
    date  = datetime.now().strftime("%Y%m%d_%H%M")
    return f"stable_outreach_{clean}_{date}.csv"


def save_to_csv(filepath: str, profile: dict, message: str,
                persona: str, skip_reason: str = ""):
    """Saves one row to CSV. Creates file with headers if needed."""

    def clean(text) -> str:
        return " ".join(str(text or "").split())

    row = {
        "Name":                 clean(profile.get("name", "Unknown")),
        "LinkedIn URL":         clean(profile.get("url", "")),
        "Role":                 clean(profile.get("role", "Unknown")),
        "Company":              clean(profile.get("company", "Unknown")),
        "Relevance Score":      profile.get("score", 0),
        "Personalization Hook": clean(profile.get("hook", "")),
        "Outreach Message":     clean(message),
        "Status":               "skip" if skip_reason else "pending",
        "Skip Reason":          clean(skip_reason),
        "Target Persona":       clean(persona),
        "Timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    file_exists = os.path.exists(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ============================================================
# THE STABLE PIPELINE
# ============================================================

def run_stable_pipeline(
    persona:        str,
    sender_context: str,
    max_profiles:   int = 5,
    min_score:      int = 5
) -> str:
    """
    The full pipeline with proper error handling at every step.
    Failures are logged and skipped — the run continues regardless.
    """

    print(f"\n{'='*60}")
    print(f"🚀 STABLE PIPELINE STARTING")
    print(f"{'='*60}")
    print(f"🎯 Persona: {persona}")
    print(f"📋 Logs being written to: pipeline.log\n")

    logger.info(f"Pipeline started for persona: '{persona}'")

    csv_path = get_csv_path(persona)

    stats = {
        "searched": 0, "analyzed": 0,
        "skipped_score": 0, "skipped_quality": 0,
        "skipped_duplicate": 0, "skipped_bad_message": 0,
        "messaged": 0, "errors": 0
    }

    # ── STEP 1: SEARCH ──
    print("🔍 Searching for profiles...\n")
    profiles = safe_search(persona)

    if not profiles:
        print("❌ Search returned no results. Check your Tavily API key.")
        logger.error("Pipeline aborted — search returned no results")
        return csv_path

    stats["searched"] = len(profiles)
    print(f"   Found {len(profiles)} profiles\n")

    processed = 0

    for i, search_result in enumerate(profiles):
        if processed >= max_profiles:
            print(f"\n⏹  Reached limit of {max_profiles} profiles.")
            break

        url  = search_result.get("url", "")
        name = search_result.get("name", f"Profile {i+1}")

        print(f"\n{'─'*60}")
        print(f"📋 [{i+1}/{len(profiles)}] {name}")
        print(f"{'─'*60}")

        # ── Guard: bad URL ──
        if not url or "linkedin.com" not in url:
            reason = f"Invalid URL: '{url}'"
            print(f"   ⚠️  Skipping — {reason}")
            logger.warning(f"Skipped {name}: {reason}")
            stats["errors"] += 1
            save_to_csv(csv_path, {"name": name, "url": url}, "", persona, reason)
            continue

        # ── Guard: duplicate ──
        if get_profile_by_url(url):
            print(f"   ⏭️  Already processed — skipping")
            logger.info(f"Duplicate skipped: {url}")
            stats["skipped_duplicate"] += 1
            continue

        # ── STEP 2: ANALYZE ──
        print(f"   🔬 Analyzing...")
        profile = safe_analyze(url, search_result.get("snippet", ""), persona)
        profile["url"]     = url
        profile["snippet"] = search_result.get("snippet", "")
        profile["target_persona"] = persona
        stats["analyzed"] += 1

        # ── Guard: score filter ──
        score = int(profile.get("score", 0))
        print(f"   ⭐ Score: {score}/10 — {profile.get('name')} @ {profile.get('company')}")

        if score < min_score:
            reason = f"Score {score} below minimum {min_score}"
            print(f"   ⏭️  {reason}")
            logger.info(f"Low score skip: {name} ({score}/10)")
            stats["skipped_score"] += 1
            save_to_csv(csv_path, profile, "", persona, reason)
            continue

        # ── Guard: data quality ──
        low_quality, quality_reason = is_low_quality_profile(profile)
        if low_quality:
            print(f"   ⚠️  Low quality profile — {quality_reason}")
            logger.warning(f"Low quality skip: {name} — {quality_reason}")
            stats["skipped_quality"] += 1
            save_to_csv(csv_path, profile, "", persona, f"Low quality: {quality_reason}")
            continue

        # ── STEP 3: DRAFT MESSAGE ──
        print(f"   ✍️  Drafting message...")
        message = safe_draft(profile, sender_context)

        # ── Guard: message quality ──
        good_msg, msg_reason = is_good_message(message)
        if not good_msg:
            print(f"   ⚠️  Bad message — {msg_reason}")
            logger.warning(f"Bad message for {name}: {msg_reason}")
            stats["skipped_bad_message"] += 1
            save_to_csv(csv_path, profile, message, persona, f"Bad message: {msg_reason}")
            continue

        stats["messaged"] += 1
        print(f"   📧 Message: {message[:80]}...")

        # ── STEP 4: STORE ──
        add_profile(profile, message)

        # ── STEP 5: SAVE TO CSV ──
        save_to_csv(csv_path, profile, message, persona)
        print(f"   ✅ Saved")
        logger.info(f"Successfully processed: {name} (score: {score})")

        processed += 1

    # ── FINAL STATS ──
    print(f"\n\n{'='*60}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"""
  Profiles found       : {stats['searched']}
  Analyzed             : {stats['analyzed']}
  Skipped (low score)  : {stats['skipped_score']}
  Skipped (low quality): {stats['skipped_quality']}
  Skipped (duplicate)  : {stats['skipped_duplicate']}
  Bad messages caught  : {stats['skipped_bad_message']}
  Errors               : {stats['errors']}
  ─────────────────────
  Messages ready       : {stats['messaged']}

  📄 CSV: {csv_path}
  📋 Log: pipeline.log
""")

    logger.info(
        f"Pipeline complete — {stats['messaged']} messages ready, "
        f"{stats['errors']} errors, "
        f"{stats['skipped_quality']} quality skips"
    )

    return csv_path


# ============================================================
# INTENTIONAL FAILURE TESTS
# ============================================================
# Run these to see graceful error handling in action.
# Each one would have crashed your old pipeline.

def test_bad_url():
    """Test what happens with a completely invalid URL."""
    print("\n" + "🧪 "*15)
    print("TEST 1: Bad URL")
    print("🧪 "*15)

    fake_profile = {
        "url":     "https://not-a-real-url.xyz/profile/nobody",
        "snippet": "Some snippet text",
        "name":    "Test Person"
    }

    print("Attempting to analyze a fake URL...")
    result = safe_analyze(
        fake_profile["url"],
        fake_profile["snippet"],
        "test persona"
    )
    print(f"Result: {result}")
    print("✅ Pipeline didn't crash — handled gracefully\n")


def test_empty_profile():
    """Test what happens when analyzer returns empty data."""
    print("\n" + "🧪 "*15)
    print("TEST 2: Empty/Low Quality Profile Detection")
    print("🧪 "*15)

    empty_profile = {
        "name":    "Not found",
        "role":    "Not found",
        "company": "Not found",
        "score":   3,
        "hook":    "No public information available",
        "url":     "https://linkedin.com/in/someone"
    }

    low_quality, reason = is_low_quality_profile(empty_profile)
    print(f"Profile: {empty_profile['name']} @ {empty_profile['company']}")
    print(f"Is low quality: {low_quality}")
    print(f"Reason: {reason}")
    print("✅ Quality check caught the bad profile\n")


def test_vague_persona():
    """Test what happens with a very vague search persona."""
    print("\n" + "🧪 "*15)
    print("TEST 3: Vague Persona")
    print("🧪 "*15)

    vague = "person who works"
    print(f"Searching with intentionally vague persona: '{vague}'")
    results = safe_search(vague)
    print(f"Results returned: {len(results)}")
    if results:
        print(f"First result: {results[0].get('name')} — {results[0].get('url')}")
    print("✅ Search handled vague persona without crashing\n")


def test_message_quality_check():
    """Test the message quality checker with bad messages."""
    print("\n" + "🧪 "*15)
    print("TEST 4: Message Quality Checks")
    print("🧪 "*15)

    test_cases = [
        ("", "Empty string"),
        ("Hi.", "Too short"),
        ("I noticed you work at [company] and wanted to reach out about [topic] because your background in Not found is impressive.", "Contains template artifacts"),
        ("This is a perfectly normal message that says something specific about a person and asks a reasonable question.", "Normal message — should pass"),
    ]

    for message, description in test_cases:
        good, reason = is_good_message(message)
        status = "✅ PASS" if good else "❌ FAIL"
        print(f"  {status} | {description}")
        if not good:
            print(f"         Reason: {reason}")

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print("\n" + "🛡️  "*20)
    print("  DAY 28: ERROR HANDLING + STABILITY")
    print("🛡️  "*20)

    # ── RUN FAILURE TESTS FIRST ──
    print("\n" + "="*60)
    print("PART 1: INTENTIONAL FAILURE TESTS")
    print("These would have crashed your old pipeline.")
    print("="*60)

    test_bad_url()
    test_empty_profile()
    test_message_quality_check()
    # Uncomment to test vague persona (uses a Tavily credit):
    # test_vague_persona()

    input("\n▶  Press ENTER to run the stable pipeline...\n")

    # ── RUN THE STABLE PIPELINE ──
    TARGET_PERSONA = "ML engineers working at Series A startups in India"

    SENDER_CONTEXT = """
    I'm building an AI-powered recruiting tool for early-stage startups in India.
    I'm talking to ML engineers to understand their biggest workflow frustrations.
    Not selling anything — just doing research conversations.
    """

    csv_file = run_stable_pipeline(
        persona=        TARGET_PERSONA,
        sender_context= SENDER_CONTEXT,
        max_profiles=   5,
        min_score=      5
    )

    print("\n💡 CHECK YOUR pipeline.log FILE:")
    print("   It has timestamped records of everything that happened.")
    print("   Open it in any text editor to see the full run history.\n")

    print("="*60)
    print("🧠 WHAT ERROR HANDLING ACTUALLY DOES:")
    print("="*60)
    print("""
  WITHOUT error handling:    WITH error handling:
  ─────────────────────      ────────────────────
  Bad URL    → crash         Bad URL    → log + skip + continue
  Rate limit → crash         Rate limit → wait + retry + continue
  Empty data → crash         Empty data → detect + skip + continue
  Bad message → saved anyway Bad message → caught + flagged in CSV

  The pipeline processes 50 profiles.
  WITHOUT: Profile 12 fails, you lose 12-50.
  WITH: Profile 12 is logged and skipped, 13-50 continue.

  That's the difference between a toy and a tool.
""")
    print("="*60)
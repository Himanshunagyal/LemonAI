"""
============================================================
  DAY 26–27: OUTPUT + TRACKING SYSTEM
  output_tracker.py
============================================================

WHAT THIS FILE DOES:
  1. Runs the full agent pipeline end-to-end
  2. Saves every generated profile + message to a CSV
  3. Also stores everything in ChromaDB (deduplication)
  4. Produces a clean, shareable artifact you can open in Excel

CSV COLUMNS:
  Name, LinkedIn URL, Role, Company, Relevance Score,
  Personalization Hook, Outreach Message, Status, Timestamp

SETUP:
  All dependencies already installed from previous days.
  Make sure these files are in the same folder:
    - search_tool.py
    - profile_analyzer.py
    - message_drafter.py
    - vector_store.py
    - output_tracker.py  ← this file
    - .env
"""

import os
import csv
import json
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

# Import all your tools from previous days
from search_tool       import search_linkedin_profiles
from profile_analyzer  import analyze_linkedin_profile
from message_drafter   import draft_message_from_profile
from vector_store      import add_profile, get_profile_by_url

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ============================================================
# CSV SETUP
# ============================================================

CSV_COLUMNS = [
    "Name",
    "LinkedIn URL",
    "Role",
    "Company",
    "Relevance Score",
    "Personalization Hook",
    "Outreach Message",
    "Status",           # pending / approved / sent / skip
    "Target Persona",
    "Timestamp"
]


def get_csv_path(persona: str) -> str:
    """
    Generates a clean filename from the persona description.
    "ML engineers Series A India" → "outreach_ML_engineers_Series_A_India.csv"
    """
    clean = persona.replace(" ", "_").replace("/", "_")[:50]
    date  = datetime.now().strftime("%Y%m%d")
    return f"outreach_{clean}_{date}.csv"


def init_csv(filepath: str):
    """
    Creates the CSV file with headers if it doesn't exist.
    If it already exists, we append to it (don't overwrite).
    """
    if not os.path.exists(filepath):
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
        print(f"   📄 Created new CSV: {filepath}")
    else:
        print(f"   📄 Appending to existing CSV: {filepath}")


def append_to_csv(filepath: str, row: dict):
    """
    Appends one profile row to the CSV.
    Uses 'a' (append) mode so we don't overwrite previous runs.
    """
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)


def profile_to_csv_row(
    profile:  dict,
    message:  str,
    persona:  str
) -> dict:
    """
    Converts a profile dict + message into a flat CSV row dict.
    Cleans up text to remove newlines that would break CSV formatting.
    """
    def clean(text: str) -> str:
        """Remove newlines and extra whitespace for clean CSV cells."""
        if not text:
            return ""
        return " ".join(str(text).split())

    return {
        "Name":                 clean(profile.get("name", "Unknown")),
        "LinkedIn URL":         clean(profile.get("url", "")),
        "Role":                 clean(profile.get("role", "Unknown")),
        "Company":              clean(profile.get("company", "Unknown")),
        "Relevance Score":      profile.get("score", 0),
        "Personalization Hook": clean(profile.get("hook", "")),
        "Outreach Message":     clean(message),
        "Status":               "pending",
        "Target Persona":       clean(persona),
        "Timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M")
    }


# ============================================================
# THE FULL PIPELINE
# ============================================================

def run_full_pipeline(
    persona:        str,
    sender_context: str,
    max_profiles:   int = 5,
    min_score:      int = 5
) -> str:
    """
    Runs the complete end-to-end pipeline:
      Search → Analyze → Draft Message → Store in ChromaDB → Save to CSV

    Args:
        persona:        Target persona description
        sender_context: Who you are and why you're reaching out
        max_profiles:   How many profiles to process (default 5)
        min_score:      Only process profiles scoring >= this (default 5)

    Returns:
        Path to the generated CSV file
    """

    print("\n" + "="*60)
    print("🚀 FULL PIPELINE STARTING")
    print("="*60)
    print(f"🎯 Persona       : {persona}")
    print(f"📊 Min score     : {min_score}/10")
    print(f"📦 Max profiles  : {max_profiles}")
    print(f"{'='*60}\n")

    csv_path = get_csv_path(persona)
    init_csv(csv_path)

    stats = {
        "searched":  0,
        "analyzed":  0,
        "skipped_score":    0,
        "skipped_duplicate": 0,
        "messaged":  0,
        "stored":    0,
        "csv_rows":  0
    }

    # ── STEP 1: SEARCH ──────────────────────────────────────
    print("🔍 STEP 1: Searching LinkedIn profiles...\n")

    raw_profiles = search_linkedin_profiles.invoke({"persona": persona})
    stats["searched"] = len(raw_profiles)

    print(f"   Found {len(raw_profiles)} profiles from Tavily\n")

    if not raw_profiles:
        print("❌ No profiles found. Try a different persona description.")
        return csv_path

    # ── STEP 2-4: ANALYZE + DRAFT + STORE ───────────────────
    processed = 0

    for i, search_result in enumerate(raw_profiles):
        if processed >= max_profiles:
            print(f"\n⏹  Reached max_profiles limit ({max_profiles}). Stopping.")
            break

        url  = search_result.get("url", "")
        name = search_result.get("name", f"Profile {i+1}")

        print(f"\n{'─'*60}")
        print(f"📋 Processing {i+1}/{len(raw_profiles)}: {name}")
        print(f"{'─'*60}")

        # ── Check ChromaDB for duplicate ──
        existing = get_profile_by_url(url)
        if existing:
            print(f"   ⏭️  Already in database — skipping {name}")
            stats["skipped_duplicate"] += 1
            continue

        # ── STEP 2: ANALYZE ──
        print(f"   🔬 Analyzing profile...")
        profile = analyze_linkedin_profile.invoke({
            "url":            url,
            "snippet":        search_result.get("snippet", ""),
            "target_persona": persona
        })
        stats["analyzed"] += 1

        # Add URL and snippet to profile for later use
        profile["url"]     = url
        profile["snippet"] = search_result.get("snippet", "")
        profile["target_persona"] = persona

        score = int(profile.get("score", 0))
        print(f"   ⭐ Score: {score}/10 — {profile.get('name')} @ {profile.get('company')}")

        # ── Filter by minimum score ──
        if score < min_score:
            print(f"   ⏭️  Score {score} below minimum {min_score} — skipping")
            stats["skipped_score"] += 1
            continue

        # ── STEP 3: DRAFT MESSAGE ──
        print(f"   ✍️  Drafting outreach message...")
        message = draft_message_from_profile(profile, sender_context)
        stats["messaged"] += 1

        print(f"   📧 Message drafted ({len(message.split())} words)")

        # ── STEP 4: STORE IN CHROMADB ──
        store_result = add_profile(profile, message)
        if store_result["status"] == "added":
            stats["stored"] += 1

        # ── STEP 5: SAVE TO CSV ──
        row = profile_to_csv_row(profile, message, persona)
        append_to_csv(csv_path, row)
        stats["csv_rows"] += 1

        processed += 1
        print(f"   ✅ Saved to CSV and ChromaDB")

    # ── FINAL REPORT ────────────────────────────────────────
    print(f"\n\n{'='*60}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"""
  Profiles found      : {stats['searched']}
  Profiles analyzed   : {stats['analyzed']}
  Skipped (low score) : {stats['skipped_score']}
  Skipped (duplicate) : {stats['skipped_duplicate']}
  Messages drafted    : {stats['messaged']}
  Stored in ChromaDB  : {stats['stored']}
  Rows saved to CSV   : {stats['csv_rows']}

  📄 CSV saved to: {csv_path}
""")
    print(f"{'='*60}")

    return csv_path


# ============================================================
# CSV READER — Review output without opening Excel
# ============================================================

def print_csv_summary(filepath: str):
    """
    Prints a summary of the CSV contents in the terminal.
    Useful for quick review without opening Excel.
    """
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return

    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("⚠️  CSV is empty")
        return

    print(f"\n{'='*60}")
    print(f"📊 CSV SUMMARY: {filepath}")
    print(f"   Total rows: {len(rows)}")
    print(f"{'='*60}")

    for i, row in enumerate(rows, 1):
        print(f"\n  [{i}] {row.get('Name')} — {row.get('Role')} @ {row.get('Company')}")
        print(f"       Score  : {row.get('Relevance Score')}/10")
        print(f"       Status : {row.get('Status')}")
        print(f"       URL    : {row.get('LinkedIn URL')}")
        print(f"\n       Hook   : {row.get('Personalization Hook', '')[:120]}...")
        print(f"\n       Message: {row.get('Outreach Message', '')[:200]}...")
        print(f"       {'─'*50}")

    # Score distribution
    scores = [int(r.get("Relevance Score", 0)) for r in rows]
    avg_score = sum(scores) / len(scores) if scores else 0
    high_quality = sum(1 for s in scores if s >= 7)

    print(f"\n  📈 QUALITY STATS:")
    print(f"     Average score    : {avg_score:.1f}/10")
    print(f"     High quality (7+): {high_quality}/{len(rows)} profiles")
    print(f"     Status breakdown : {len([r for r in rows if r['Status']=='pending'])} pending")


# ============================================================
# UPDATE STATUS — Mark profiles as approved/sent/skip
# ============================================================

def update_status(filepath: str, url: str, new_status: str):
    """
    Updates the Status column for a specific profile in the CSV.
    Valid statuses: pending, approved, sent, skip

    In real use you'd do this in Excel. This is for programmatic updates.
    """
    valid_statuses = ["pending", "approved", "sent", "skip"]
    if new_status not in valid_statuses:
        print(f"❌ Invalid status. Use: {valid_statuses}")
        return

    rows = []
    updated = False

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        if row.get("LinkedIn URL") == url:
            row["Status"] = new_status
            updated = True
            print(f"   ✅ Updated {row.get('Name')} → {new_status}")

    if not updated:
        print(f"   ⚠️  URL not found in CSV: {url}")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# RUN END TO END
# ============================================================

if __name__ == "__main__":

    print("\n" + "📊 "*20)
    print("  DAY 26–27: FULL END-TO-END RUN")
    print("📊 "*20)

    # ── YOUR PERSONA ──
    # Change this to whoever you actually want to reach
    TARGET_PERSONA = "ML engineers working at Series A startups in India"

    # ── YOUR SENDER CONTEXT ──
    # Be specific — this directly affects message quality
    SENDER_CONTEXT = """
    I'm building an AI-powered recruiting tool for early-stage startups in India.
    I'm talking to ML engineers to understand their biggest workflow frustrations —
    what takes up their time that shouldn't. Not selling anything yet,
    just doing deep research conversations with people doing real ML work.
    """

    # ── RUN THE PIPELINE ──
    csv_file = run_full_pipeline(
        persona=        TARGET_PERSONA,
        sender_context= SENDER_CONTEXT,
        max_profiles=   5,    # Process up to 5 profiles
        min_score=      5     # Only keep profiles scoring 5 or above
    )

    # ── REVIEW THE OUTPUT ──
    input("\n▶  Press ENTER to review the CSV output...\n")
    print_csv_summary(csv_file)

    # ── DEMO: Update a status ──
    print(f"\n\n{'='*60}")
    print("📝 DEMO: Updating a profile status")
    print(f"{'='*60}")
    print("\nIn real use, you'd open the CSV in Excel and update Status manually.")
    print("Here's how to do it programmatically:\n")
    print("  update_status(csv_file, 'https://linkedin.com/in/someone', 'approved')")
    print("\nOpen your CSV in Excel now and you'll see all your generated messages.")

    print(f"\n\n{'='*60}")
    print("🏆 WHAT YOU JUST BUILT — THE COMPLETE PICTURE")
    print(f"{'='*60}")
    print(f"""
  INPUT  : One sentence — a target persona
  OUTPUT : A CSV with researched, scored, messaged contacts

  THE PIPELINE:
  Tavily searches LinkedIn live
      ↓
  Groq analyzes each profile (name, role, hook, score)
      ↓
  Groq drafts a personalized message using the hook
      ↓
  ChromaDB stores everything (no re-processing duplicates)
      ↓
  CSV exported — ready to hand to a human for review

  THIS IS A REAL PRODUCT.
  Someone could use this CSV today to send outreach messages.
  The AI did the research. The human does the sending.
  That's the right division of labor.
""")
    print(f"{'='*60}")
    print("\n💡 WHAT TO DO WITH YOUR CSV:")
    print("  1. Open it in Excel or Google Sheets")
    print("  2. Read each message — does it sound human?")
    print("  3. Mark Status as 'approved' for the ones worth sending")
    print("  4. Mark Status as 'skip' for weak matches")
    print("  5. Send the approved ones manually on LinkedIn")
    print("  6. Update Status to 'sent' as you go\n")
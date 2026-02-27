"""
============================================================
  DAY 17–18: LINKEDIN SEARCH TOOL
  search_tool.py
============================================================

WHAT THIS FILE DOES:
  Takes a persona description (e.g. "AI startup founder Bangalore")
  and returns 5-10 cleaned LinkedIn profile results.

  This is a standalone tool — test it here BEFORE putting it
  inside any agent. Always test components in isolation first.

SETUP:
  python -m pip install tavily-python python-dotenv langchain-core

.env file:
  TAVILY_API_KEY=tvly-your-key-here
"""

import re
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_core.tools import tool

load_dotenv()

tavily = TavilyClient()


# ============================================================
# HELPER FUNCTIONS — Parsing & Cleaning
# ============================================================
# These run BEFORE returning results to the agent.
# Clean data in = reliable agent behavior out.

def clean_name_from_title(title: str) -> str:
    """
    LinkedIn titles look like:
      "John Smith - Founder at TechCorp | LinkedIn"
      "Priya Sharma – AI Researcher | LinkedIn"
      "Rahul Gupta | Product Manager | LinkedIn"

    We want just: "John Smith"
    Strategy: take everything before the first - , – , or |
    """
    # Split on common separators: hyphen, em-dash, pipe
    for separator in [" - ", " – ", " | ", "|"]:
        if separator in title:
            return title.split(separator)[0].strip()

    # If no separator found, remove " | LinkedIn" at the end if present
    title = re.sub(r'\s*\|\s*LinkedIn\s*$', '', title).strip()
    return title


def clean_headline_from_title(title: str) -> str:
    """
    Extract the job title / headline part from the LinkedIn title.
    "John Smith - Founder at TechCorp | LinkedIn" → "Founder at TechCorp"
    """
    # Remove the name part (before first separator)
    for separator in [" - ", " – ", " | ", "|"]:
        if separator in title:
            parts = title.split(separator)
            # Headline is usually the second part, remove "LinkedIn" at end
            if len(parts) >= 2:
                headline = parts[1].strip()
                headline = re.sub(r'\s*\|\s*LinkedIn\s*$', '', headline).strip()
                return headline

    return ""


def clean_url(url: str) -> str:
    """
    Keep only the clean profile URL, strip tracking parameters.
    "https://linkedin.com/in/johnsmith?trk=..." → "https://linkedin.com/in/johnsmith"
    """
    # Remove everything after ? (query parameters)
    if "?" in url:
        url = url.split("?")[0]
    # Remove trailing slash
    url = url.rstrip("/")
    return url


def clean_snippet(content: str, max_length: int = 200) -> str:
    """
    LinkedIn snippets from search results contain a lot of noise.
    Clean them up: remove extra whitespace, truncate to max_length.
    """
    if not content:
        return ""

    # Collapse multiple spaces and newlines into single space
    content = re.sub(r'\s+', ' ', content).strip()

    # Truncate with ellipsis if too long
    if len(content) > max_length:
        content = content[:max_length].rsplit(' ', 1)[0] + "..."

    return content


def parse_result(raw_result: dict) -> dict:
    """
    Takes one raw Tavily result and returns a clean, structured dict.

    Raw Tavily result looks like:
    {
        "title":   "John Smith - Founder at TechCorp | LinkedIn",
        "url":     "https://linkedin.com/in/johnsmith?trk=...",
        "content": "John Smith. Founder at TechCorp. 500+ connections...",
        "score":   0.87
    }

    We return:
    {
        "name":     "John Smith",
        "headline": "Founder at TechCorp",
        "url":      "https://linkedin.com/in/johnsmith",
        "snippet":  "Founder at TechCorp. 500+ connections...",
        "score":    0.87
    }
    """
    title   = raw_result.get("title", "")
    url     = raw_result.get("url", "")
    content = raw_result.get("content", "")
    score   = raw_result.get("score", 0)

    return {
        "name":     clean_name_from_title(title),
        "headline": clean_headline_from_title(title),
        "url":      clean_url(url),
        "snippet":  clean_snippet(content),
        "score":    round(score, 3)
    }


def is_valid_linkedin_profile(result: dict) -> bool:
    """
    Filter out non-profile results that sometimes slip through.
    We only want personal profile URLs (linkedin.com/in/...)
    not company pages, job listings, or other LinkedIn pages.
    """
    url = result.get("url", "")

    # Must contain linkedin.com/in/ to be a personal profile
    if "linkedin.com/in/" not in url:
        return False

    # Must have a name
    if not result.get("name"):
        return False

    return True


# ============================================================
# THE MAIN TOOL
# ============================================================

@tool
def search_linkedin_profiles(persona: str) -> list:
    """
    Searches for LinkedIn profiles matching the given persona description.
    Returns a list of cleaned profile results with name, URL, headline, and snippet.

    Args:
        persona: Description of the type of person to find.
                 e.g. "AI startup founder Bangalore"
                 e.g. "senior data scientist fintech Mumbai"
                 e.g. "product manager SaaS company Delhi"

    Returns:
        List of dicts with keys: name, headline, url, snippet, score
    """

    # Build the search query
    # site:linkedin.com/in/ restricts results to LinkedIn personal profiles only
    query = f'site:linkedin.com/in/ {persona}'

    print(f"\n   🔍 Searching Tavily with query: '{query}'")

    # Call Tavily
    # max_results=10 gives us enough to filter from
    # search_depth="basic" is faster and sufficient for profile search
    raw_results = tavily.search(
        query=query,
        max_results=10,
        search_depth="basic"
    )

    print(f"   📥 Got {len(raw_results.get('results', []))} raw results from Tavily")

    # Parse and clean every result
    parsed = [parse_result(r) for r in raw_results.get("results", [])]

    # Filter to only valid LinkedIn profiles
    profiles = [p for p in parsed if is_valid_linkedin_profile(p)]

    print(f"   ✅ {len(profiles)} valid LinkedIn profiles after filtering\n")

    return profiles


# ============================================================
# STANDALONE TEST — Run this file directly to test the tool
# ============================================================
# This is the "test in isolation" step.
# Run: python search_tool.py
# Make sure results look clean BEFORE plugging into an agent.

def print_profiles(profiles: list, persona: str):
    """Pretty-print the profile results for easy inspection."""
    print(f"\n{'='*60}")
    print(f"  RESULTS FOR: '{persona}'")
    print(f"  Found: {len(profiles)} profiles")
    print(f"{'='*60}")

    if not profiles:
        print("  ⚠️  No profiles found. Try a broader persona description.")
        return

    for i, profile in enumerate(profiles, 1):
        print(f"\n  Profile {i}:")
        print(f"  Name     : {profile['name']}")
        print(f"  Headline : {profile['headline']}")
        print(f"  URL      : {profile['url']}")
        print(f"  Snippet  : {profile['snippet']}")
        print(f"  Score    : {profile['score']}")
        print(f"  {'─'*50}")


if __name__ == "__main__":

    print("\n" + "🔎 "*20)
    print("  LINKEDIN SEARCH TOOL — STANDALONE TEST")
    print("🔎 "*20)

    # ── TEST 1: AI founder in Bangalore ──
    # Change these personas to whatever you want to search for!
    persona_1 = "AI startup founder Bangalore India"
    print(f"\n⏳ Testing persona 1: '{persona_1}'")
    # When testing standalone, call .invoke() to use the @tool wrapper
    results_1 = search_linkedin_profiles.invoke({"persona": persona_1})
    print_profiles(results_1, persona_1)

    input("\n▶  Press ENTER for test 2...\n")

    # ── TEST 2: Data scientist in Mumbai ──
    persona_2 = "senior data scientist fintech Mumbai"
    print(f"⏳ Testing persona 2: '{persona_2}'")
    results_2 = search_linkedin_profiles.invoke({"persona": persona_2})
    print_profiles(results_2, persona_2)

    input("\n▶  Press ENTER for test 3...\n")

    # ── TEST 3: Product manager ──
    persona_3 = "product manager B2B SaaS startup India"
    print(f"⏳ Testing persona 3: '{persona_3}'")
    results_3 = search_linkedin_profiles.invoke({"persona": persona_3})
    print_profiles(results_3, persona_3)

    # ── SUMMARY ──
    print(f"\n{'='*60}")
    print("✅ STANDALONE TEST COMPLETE")
    print(f"{'='*60}")
    print(f"""
  What to check before moving to the agent:
  ✓ Are the names clean? (no "| LinkedIn" artifacts)
  ✓ Are the URLs correct linkedin.com/in/ format?
  ✓ Are the headlines meaningful?
  ✓ Are snippets readable and useful?
  ✓ Are results actually relevant to the persona?

  If any of these look wrong, fix the parsing functions
  BEFORE plugging this into the agent.

  If everything looks good → this tool is agent-ready! 🚀
""")
    print(f"{'='*60}")
    print("\n💡 THINGS TO TRY:")
    print("  • Change personas to your own target audience")
    print("  • Try a very specific persona vs a broad one")
    print("  • Try search_depth='advanced' — does quality improve?")
    print("  • Add a 'location' parameter to the tool for more control\n")
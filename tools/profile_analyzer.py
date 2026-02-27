"""
============================================================
  DAY 19–20: PROFILE ANALYZER TOOL
  profile_analyzer.py
============================================================

WHAT THIS FILE DOES:
  Takes a LinkedIn profile URL + any snippet we already have,
  fetches whatever public content is available via Tavily,
  then uses Groq to extract:
    - Person's name
    - Current role & company
    - Personalization hook (something specific to mention)
    - Relevance score (1-10) for your target persona

WHY NOT SCRAPE LINKEDIN DIRECTLY?
  LinkedIn blocks scrapers. You'd get login walls or 999 errors.
  Instead we use Tavily's extract feature (better than raw requests)
  plus the snippet we already have from the search step.
  This is what real outreach tools do too.

SETUP:
  python -m pip install tavily-python groq python-dotenv

.env file:
  GROQ_API_KEY=gsk_your-key-here
  TAVILY_API_KEY=tvly-your-key-here
"""

import os
import json
import re
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from langchain_core.tools import tool

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily      = TavilyClient()
MODEL       = "llama-3.3-70b-versatile"


# ============================================================
# STEP 1: FETCH PROFILE CONTENT
# ============================================================
# We try two sources and combine them for the richest possible context.
# Source A: Tavily extract (fetches and cleans the page)
# Source B: The snippet we already have from the search step
# If A fails (LinkedIn blocked it), we fall back to B alone.

def fetch_profile_content(url: str, existing_snippet: str = "") -> str:
    """
    Fetches whatever public content is available from a LinkedIn URL.
    Returns combined text from all available sources.

    Args:
        url: LinkedIn profile URL e.g. "https://linkedin.com/in/johndoe"
        existing_snippet: Text snippet from Tavily search (optional but helpful)
    """

    content_parts = []

    # ── Source A: Tavily Extract ──
    # Tavily's extract method fetches pages better than raw requests.
    # It handles some JavaScript rendering and returns clean text.
    # It still can't get past LinkedIn's login wall but gets the
    # publicly visible portion of the profile.
    try:
        print(f"   📡 Trying Tavily extract on: {url}")
        extract_result = tavily.extract(urls=[url])

        if extract_result and extract_result.get("results"):
            extracted_text = extract_result["results"][0].get("raw_content", "")
            if extracted_text and len(extracted_text) > 50:
                # Clean up whitespace
                extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()
                # Take first 2000 chars — enough for analysis, not too much
                content_parts.append(f"FETCHED CONTENT:\n{extracted_text[:2000]}")
                print(f"   ✅ Tavily extracted {len(extracted_text)} chars")
            else:
                print(f"   ⚠️  Tavily extract returned too little content")

    except Exception as e:
        print(f"   ⚠️  Tavily extract failed: {str(e)[:80]}")

    # ── Source B: Existing snippet from search ──
    # We always include this — it's reliable since we already have it
    if existing_snippet:
        content_parts.append(f"SEARCH SNIPPET:\n{existing_snippet}")
        print(f"   ✅ Using existing search snippet ({len(existing_snippet)} chars)")

    # ── Combine everything ──
    if not content_parts:
        return ""

    return "\n\n".join(content_parts)


# ============================================================
# STEP 2: ANALYZE WITH GROQ
# ============================================================
# Feed the combined content to Groq and ask for structured extraction.
# We ask for JSON output so we can reliably parse the response.

def analyze_with_groq(
    content: str,
    profile_url: str,
    target_persona: str = "tech professional"
) -> dict:
    """
    Uses Groq to analyze profile content and extract structured insights.

    Returns a dict with:
        name, role, company, hook, score, reasoning
    """

    if not content:
        return {
            "name":      "Unknown",
            "role":      "Unknown",
            "company":   "Unknown",
            "hook":      "No public information available to personalize",
            "score":     1,
            "reasoning": "No content could be fetched for this profile"
        }

    system_prompt = """You are an expert B2B sales researcher who analyzes 
LinkedIn profiles to help write personalized outreach messages.

You extract key information and find personalization hooks — specific, 
genuine details that make an outreach message feel personal and relevant.

You always respond with valid JSON only. No explanation, no markdown, 
no text before or after the JSON."""

    user_prompt = f"""Analyze this LinkedIn profile content and extract the following.

TARGET PERSONA WE ARE LOOKING FOR: {target_persona}

PROFILE URL: {profile_url}

PROFILE CONTENT:
{content}

Return a JSON object with exactly these fields:

{{
  "name": "Full name of the person (string)",
  "role": "Their current job title (string)",
  "company": "Their current company name (string)",
  "hook": "A specific, genuine personalization hook — one detail from their profile that would make outreach feel personal. Be specific. Avoid generic things like 'you have experience in X'. Find something distinctive like a specific project, transition, achievement, or unique background. (string, 1-2 sentences)",
  "score": "Relevance score 1-10 — how well does this person match the target persona? 10 = perfect match, 1 = completely irrelevant (integer)",
  "reasoning": "One sentence explaining why you gave that score (string)"
}}

If you cannot find a field, use 'Not found' as the value.
Return JSON only. No other text."""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.3   # Low temperature = consistent structured output
        )

        raw = response.choices[0].message.content.strip()

        # Clean up any markdown code fences if Groq adds them
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        result = json.loads(raw)
        return result

    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON parse failed: {e}")
        print(f"   Raw response: {raw[:200]}")
        return {
            "name":      "Parse error",
            "role":      "Unknown",
            "company":   "Unknown",
            "hook":      "Could not parse AI response",
            "score":     0,
            "reasoning": "JSON parsing failed"
        }
    except Exception as e:
        print(f"   ⚠️  Groq API error: {e}")
        return {
            "name":      "Error",
            "role":      "Unknown",
            "company":   "Unknown",
            "hook":      f"Analysis failed: {str(e)[:100]}",
            "score":     0,
            "reasoning": "API call failed"
        }


# ============================================================
# STEP 3: THE MAIN TOOL
# ============================================================

@tool
def analyze_linkedin_profile(
    url: str,
    snippet: str = "",
    target_persona: str = "tech professional"
) -> dict:
    """
    Analyzes a LinkedIn profile URL and returns structured insights
    for personalized outreach.

    Args:
        url: LinkedIn profile URL (e.g. "https://linkedin.com/in/johndoe")
        snippet: Optional text snippet from search results (improves analysis)
        target_persona: Description of who you're targeting (improves scoring)

    Returns:
        Dict with name, role, company, hook, score, reasoning
    """

    print(f"\n{'─'*60}")
    print(f"🔍 Analyzing profile: {url}")
    print(f"{'─'*60}")

    # Step 1: Fetch whatever content we can get
    content = fetch_profile_content(url, snippet)

    if not content:
        print("   ❌ Could not fetch any content for this profile")
        return {
            "url":       url,
            "name":      "Unknown",
            "role":      "Unknown",
            "company":   "Unknown",
            "hook":      "No public content available",
            "score":     0,
            "reasoning": "Content fetch failed completely"
        }

    # Step 2: Analyze with Groq
    print(f"   🤖 Sending to Groq for analysis...")
    analysis = analyze_with_groq(content, url, target_persona)

    # Step 3: Add the URL to the result so it's self-contained
    analysis["url"] = url

    return analysis


# ============================================================
# STANDALONE TEST
# ============================================================

def print_analysis(result: dict):
    """Pretty print one analysis result."""
    print(f"\n  {'='*55}")
    print(f"  📋 PROFILE ANALYSIS")
    print(f"  {'='*55}")
    print(f"  URL       : {result.get('url', 'N/A')}")
    print(f"  Name      : {result.get('name', 'N/A')}")
    print(f"  Role      : {result.get('role', 'N/A')}")
    print(f"  Company   : {result.get('company', 'N/A')}")
    print(f"  Score     : {result.get('score', 0)}/10")
    print(f"  Reasoning : {result.get('reasoning', 'N/A')}")
    print(f"\n  🎯 PERSONALIZATION HOOK:")
    print(f"  {result.get('hook', 'N/A')}")
    print(f"  {'─'*55}")


if __name__ == "__main__":

    print("\n" + "🔬 "*20)
    print("  PROFILE ANALYZER — STANDALONE TEST")
    print("🔬 "*20)

    print("""
INSTRUCTIONS:
  Replace the test_profiles list below with real URLs
  from your search_tool.py results.

  Paste 3 URLs you got from the LinkedIn search tool.
  This tests the analyzer in isolation before connecting
  it to the full agent.
""")

    # ── PASTE YOUR REAL URLs HERE ──
    # Get these from running search_tool.py first!
    # Format: (url, snippet_from_search, target_persona)
    test_profiles = [
        (
            "https://www.linkedin.com/in/deepinderkumar",  # ← replace with real URL
            "Founder and CEO at Gupshup. Previously founded multiple startups in India.",
            "AI startup founder India"
        ),
        (
            "https://www.linkedin.com/in/sriramkrishnan",  # ← replace with real URL
            "Partner at Microsoft Ventures. Investor in early stage startups.",
            "AI startup founder India"
        ),
        (
            "https://www.linkedin.com/in/bharatgoenka",    # ← replace with real URL
            "Co-founder at Pratilipi. Building India's largest storytelling platform.",
            "AI startup founder India"
        ),
    ]

    target = "AI startup founder India"

    for i, (url, snippet, persona) in enumerate(test_profiles, 1):
        print(f"\n⏳ Test {i}/3 — Analyzing profile...")
        result = analyze_linkedin_profile.invoke({
            "url":            url,
            "snippet":        snippet,
            "target_persona": persona
        })
        print_analysis(result)

        if i < len(test_profiles):
            input(f"\n▶  Press ENTER for test {i+1}...\n")

    print(f"\n\n{'='*60}")
    print("✅ STANDALONE TEST COMPLETE")
    print(f"{'='*60}")
    print("""
WHAT TO CHECK BEFORE MOVING TO THE AGENT:

  ✓ Is the name extracted correctly?
  ✓ Is the role/company accurate?
  ✓ Is the hook SPECIFIC? (not generic like "has experience in AI")
    A good hook mentions something distinctive:
    - A specific product they built
    - A career transition
    - A recent achievement
    - A unique background combination
  ✓ Does the score make sense for your target persona?
  ✓ Is the reasoning sensible?

If the hooks are too generic:
  → Add more context to the system prompt
  → Tell Groq specifically what makes a GOOD hook

If scores seem wrong:
  → Be more specific in your target_persona description

If content fetch is failing:
  → The snippet alone is enough — real tools work this way too
""")
    print(f"{'='*60}")
    print("\n💡 THINGS TO TRY:")
    print("  • Replace URLs with ones from your search_tool.py output")
    print("  • Change target_persona and watch scores change")
    print("  • Try temperature=0.7 — do hooks get more creative?")
    print("  • Add 'notable_achievement' as a new field in the JSON\n")
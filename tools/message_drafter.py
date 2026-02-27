"""
============================================================
  DAY 22–23: MESSAGE DRAFTING TOOL
  message_drafter.py
============================================================

WHAT THIS FILE DOES:
  Takes analyzed profile data (from Day 19-20 analyzer)
  and drafts a personalized LinkedIn outreach message.

  Structure:
    Line 1: Specific hook — proves you read their profile
    Line 2: Why you're reaching out / what you do
    Line 3: Soft, low-friction ask

  The system prompt is WHERE THE QUALITY COMES FROM.
  The code is simple. The prompt is everything.

SETUP:
  python -m pip install groq python-dotenv

.env file:
  GROQ_API_KEY=gsk_your-key-here
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq
from langchain_core.tools import tool

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ============================================================
# THE SYSTEM PROMPT — This is where quality comes from
# ============================================================
# Read this carefully. Every instruction here shapes the output.
# When messages feel robotic, the fix is HERE, not in the code.
#
# HOW TO ITERATE:
#   1. Run the script, read all 3 messages critically
#   2. What specifically feels wrong? Too formal? Too generic?
#   3. Add an instruction to the prompt that addresses that problem
#   4. Run again. Compare. Keep what improves it.
#   5. Repeat until messages sound like YOU wrote them

DRAFTING_SYSTEM_PROMPT = """You write short, human LinkedIn outreach messages.

STRUCTURE — exactly 3 short paragraphs:
  Paragraph 1 (Hook): One specific observation about this person.
    Reference something concrete from their work — a product they built,
    a transition they made, a problem they're solving. Be specific enough
    that this line could ONLY have been written for this person.

  Paragraph 2 (Context): One sentence about who you are and why
    this person is specifically relevant. Connect your work to theirs.
    Make the relevance obvious and genuine.

  Paragraph 3 (Ask): A single soft, low-friction question.
    Make it easy to say yes. Do not ask for a call yet.
    Ask something they can answer in one sentence.

STRICT RULES:
  - Under 150 words total. Count them.
  - Never start with "Hope this finds you well" or any variation
  - Never use: leverage, synergy, innovative, passionate, excited,
    reach out, connect, touch base, explore opportunities
  - No corporate vocabulary. Write like a smart human texting a peer.
  - Do not use the word "I" to start the message
  - No subject line. Just the message body.
  - Do not compliment vaguely ("impressive background", "great work")
  - If the hook is not specific enough to identify this exact person,
    rewrite it until it is.

TONE:
  Direct. Warm but not gushing. Slightly informal.
  Like a message from a smart colleague, not a sales rep.
  Short sentences. One thought per sentence."""


# ============================================================
# THE DRAFTING FUNCTION
# ============================================================

def draft_message_from_profile(
    profile: dict,
    sender_context: str
) -> str:
    """
    Drafts a personalized outreach message from analyzed profile data.

    Args:
        profile: Dict from profile_analyzer with keys:
                 name, role, company, hook, score, url
        sender_context: Who YOU are and what you're doing.
                        e.g. "I'm building an AI hiring tool for
                        early-stage startups and looking to talk to
                        ML engineers about their workflow pain points."

    Returns:
        A drafted outreach message as a string.
    """

    # Build a clear description of what we know about this person
    profile_summary = f"""
PERSON: {profile.get('name', 'Unknown')}
ROLE: {profile.get('role', 'Unknown')} at {profile.get('company', 'Unknown')}
PERSONALIZATION HOOK: {profile.get('hook', 'No hook available')}
RELEVANCE SCORE: {profile.get('score', 0)}/10
PROFILE URL: {profile.get('url', '')}
"""

    user_prompt = f"""Write a LinkedIn outreach message for this person.

PROFILE DATA:
{profile_summary}

SENDER CONTEXT (who is sending this message):
{sender_context}

Use the personalization hook as the basis for Line 1.
Make Line 2 connect the sender's context to this person's specific work.
Make Line 3 a natural, easy question that follows from Lines 1 and 2.

Write only the message. No subject line. No explanation."""

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": DRAFTING_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt}
        ],
        max_tokens=300,
        temperature=0.8    # Higher temperature = more natural, varied language
                           # If messages feel too similar, try 0.9
                           # If messages feel too random, try 0.6
    )

    return response.choices[0].message.content.strip()


# ============================================================
# LANGCHAIN TOOL WRAPPER
# ============================================================
# Wrapping as a @tool so it can be added to the agent later.

@tool
def draft_outreach_message(profile_json: str, sender_context: str) -> str:
    """
    Drafts a personalized LinkedIn outreach message from profile analysis data.

    Args:
        profile_json: JSON string of analyzed profile data
                      (output from analyze_linkedin_profile)
        sender_context: Description of who is sending the message
                        and why they are reaching out.

    Returns:
        A personalized outreach message under 150 words.
    """
    profile = json.loads(profile_json)
    return draft_message_from_profile(profile, sender_context)


# ============================================================
# QUALITY CHECKER
# ============================================================
# Automatically flags common problems with generated messages.
# Saves you from manually checking every message for bad patterns.

BANNED_PHRASES = [
    "hope this finds you",
    "hope you're doing well",
    "i wanted to reach out",
    "i am reaching out",
    "leverage",
    "synergy",
    "innovative",
    "passionate about",
    "excited to",
    "touch base",
    "connect with you",
    "explore opportunities",
    "impressive background",
    "great work",
    "i came across your profile",
]

def check_message_quality(message: str, profile_name: str) -> dict:
    """
    Checks a message for common quality problems.
    Returns a dict with pass/fail for each check.
    """
    message_lower = message.lower()
    word_count    = len(message.split())

    issues = []

    # Check word count
    if word_count > 150:
        issues.append(f"TOO LONG: {word_count} words (max 150)")

    # Check banned phrases
    for phrase in BANNED_PHRASES:
        if phrase in message_lower:
            issues.append(f"BANNED PHRASE: '{phrase}'")

    # Check it starts with "I"
    if message.startswith("I "):
        issues.append("STARTS WITH 'I' — rewrite the opening")

    # Check minimum specificity — message should contain the person's name
    # or something from their profile (rough proxy for specificity)
    if profile_name.split()[0].lower() not in message_lower:
        issues.append("NAME NOT MENTIONED — may lack personalization")

    return {
        "word_count": word_count,
        "issues":     issues,
        "passed":     len(issues) == 0
    }


# ============================================================
# PRETTY PRINTER
# ============================================================

def print_message_result(profile: dict, message: str):
    """Display one profile + its generated message with quality check."""

    quality = check_message_quality(message, profile.get('name', ''))

    print(f"\n{'='*60}")
    print(f"👤 PROFILE: {profile.get('name')} — {profile.get('role')} @ {profile.get('company')}")
    print(f"   Score: {profile.get('score')}/10")
    print(f"   Hook used: {profile.get('hook', '')[:100]}...")
    print(f"{'─'*60}")
    print(f"\n📧 DRAFTED MESSAGE ({quality['word_count']} words):\n")
    print(message)
    print(f"\n{'─'*60}")

    if quality['passed']:
        print(f"✅ QUALITY CHECK: Passed all checks")
    else:
        print(f"⚠️  QUALITY CHECK: {len(quality['issues'])} issue(s) found:")
        for issue in quality['issues']:
            print(f"   • {issue}")

    print(f"{'='*60}")


# ============================================================
# STANDALONE TEST
# ============================================================
# Using the 3 profiles from your Day 21 agent output.
# Replace these with real data from your own agent run.

if __name__ == "__main__":

    print("\n" + "✍️  "*20)
    print("  DAY 22–23: MESSAGE DRAFTING TOOL")
    print("✍️  "*20)

    # ── SENDER CONTEXT ──
    # This is WHO YOU ARE and WHY you're reaching out.
    # Change this to your actual situation.
    # The more specific this is, the better the messages will be.
    SENDER_CONTEXT = """
    I'm building an AI-powered recruiting tool specifically for early-stage
    startups in India. I'm talking to ML engineers to understand their
    biggest workflow frustrations — what takes up their time that shouldn't.
    Not selling anything yet, just doing deep research conversations.
    """

    # ── TEST PROFILES ──
    # These are the 3 profiles from your Day 21 agent run.
    # Replace with real output from your outreach_agent.py
    test_profiles = [
        {
            "name":    "Pranav Rajesh",
            "role":    "ML Engineer",
            "company": "Squadox",
            "hook":    "Previously founded multiple startups including Squadox, indicating a strong entrepreneurial background alongside technical ML work.",
            "score":   4,
            "url":     "https://in.linkedin.com/in/pranav-rajesh-85568a224"
        },
        {
            "name":    "Raman Rdk",
            "role":    "Aspiring Data Scientist",
            "company": "Agentive (YC S23)",
            "hook":    "Working at a Y Combinator S23 startup across Audit, Fintech, Health, and Legal Tech — a rare combination that suggests broad applied ML exposure across regulated industries.",
            "score":   6,
            "url":     "https://www.linkedin.com/in/raman-rdk"
        },
        {
            "name":    "Saurabh Vij",
            "role":    "Founder",
            "company": "NEO",
            "hook":    "Building NEO — a platform that automates the grunt work for ML engineers. The angle of making ML engineers 'superhuman' rather than replacing them is a specific and interesting product thesis.",
            "score":   9,
            "url":     "https://www.linkedin.com/in/vijs"
        }
    ]

    print(f"\n📋 Drafting messages for {len(test_profiles)} profiles...")
    print(f"📝 Sender context: {SENDER_CONTEXT.strip()[:100]}...\n")

    messages_generated = []

    for i, profile in enumerate(test_profiles, 1):
        print(f"\n⏳ Drafting message {i}/{len(test_profiles)} for {profile['name']}...")
        message = draft_message_from_profile(profile, SENDER_CONTEXT)
        messages_generated.append((profile, message))
        print_message_result(profile, message)

        if i < len(test_profiles):
            input(f"\n▶  Press ENTER for next message...\n")

    # ── ITERATION GUIDE ──
    print(f"\n\n{'='*60}")
    print("🔁 HOW TO ITERATE ON QUALITY")
    print(f"{'='*60}")
    print("""
  Read each message and ask yourself honestly:

  1. LINE 1 — Is it specific enough?
     Would this line ONLY make sense for this exact person?
     If you could send it to 10 people → rewrite the hook instruction

  2. LINE 2 — Does it feel relevant or forced?
     Does the connection between sender and recipient feel natural?
     If forced → be more specific in SENDER_CONTEXT

  3. LINE 3 — Is the ask genuinely soft?
     Would YOU reply to this ask from a stranger?
     If not → make the ask even lower friction

  COMMON FIXES:
  • Messages too formal?
    → Add to prompt: "Write like you're texting a peer, not emailing a client"
  • Hook not specific enough?
    → Add to prompt: "The hook must reference a specific product, decision,
      or career move — never just a job title or industry"
  • All messages sound the same?
    → Increase temperature to 0.9
  • Messages too long?
    → Add to prompt: "Every sentence must be under 15 words"
  • Opening still feels salesy?
    → Add specific banned openers to the BANNED_PHRASES list
""")
    print(f"{'='*60}")
    print("\n💡 NEXT STEP:")
    print("  Once messages pass your quality check, add this tool")
    print("  to outreach_agent.py as a third step after analyze.\n")
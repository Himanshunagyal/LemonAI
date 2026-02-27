"""
============================================================
  DAY 21: OUTREACH AGENT
  outreach_agent.py
============================================================

WHAT THIS FILE DOES:
  Wires search_tool.py and profile_analyzer.py into a single agent.
  Given a target persona, the agent will:
    1. Search LinkedIn for matching profiles
    2. Analyze each profile for personalization hooks
    3. Return structured data ready for message drafting

  The agent decides the steps — you just give it the goal.

IMPORTANT:
  This file imports from search_tool.py and profile_analyzer.py.
  Make sure both files are in the SAME folder as this one.

SETUP:
  python -m pip install groq tavily-python python-dotenv langchain-core

FOLDER STRUCTURE:
  your-folder/
  ├── outreach_agent.py     ← this file
  ├── search_tool.py        ← from Day 17-18
  ├── profile_analyzer.py   ← from Day 19-20
  └── .env
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# Import your two tools from the other files
from search_tool import search_linkedin_profiles
from profile_analyzer import analyze_linkedin_profile

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

# ============================================================
# THE TOOLS LIST
# ============================================================
# We pass these to Groq so it knows what tools exist.
# Using the raw Groq format (not LangChain AgentExecutor)
# because we learned that avoids streaming issues.

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_linkedin_profiles",
            "description": (
                "Searches LinkedIn for profiles matching a persona description. "
                "Returns a list of profiles with name, URL, headline, and snippet. "
                "Always call this FIRST before analyzing any profiles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "persona": {
                        "type": "string",
                        "description": (
                            "Description of the type of person to search for. "
                            "e.g. 'ML engineer Series A startup India' "
                            "e.g. 'AI founder Bangalore B2B SaaS'"
                        )
                    }
                },
                "required": ["persona"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_linkedin_profile",
            "description": (
                "Analyzes a single LinkedIn profile URL to extract name, role, "
                "company, a personalization hook, and a relevance score. "
                "Call this for each profile URL returned by search_linkedin_profiles. "
                "Analyze at least 3 profiles before giving a final answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "LinkedIn profile URL to analyze"
                    },
                    "snippet": {
                        "type": "string",
                        "description": "Text snippet from search results (helps analysis)"
                    },
                    "target_persona": {
                        "type": "string",
                        "description": "The target persona we are looking for"
                    }
                },
                "required": ["url"]
            }
        }
    }
]


# ============================================================
# THE TOOL DISPATCHER
# ============================================================
# When the agent requests a tool, this runs the real function.
# Same dispatcher pattern you learned in Day 5-7.

def run_tool(tool_name: str, tool_input: dict) -> str:
    """Routes tool requests to the right Python function."""

    print(f"\n   ⚙️  Running tool: '{tool_name}'")
    print(f"   📋 Inputs: {json.dumps(tool_input, indent=6)}")

    if tool_name == "search_linkedin_profiles":
        result = search_linkedin_profiles.invoke(tool_input)
        # Convert list to JSON string to send back to AI
        return json.dumps(result, indent=2)

    elif tool_name == "analyze_linkedin_profile":
        result = analyze_linkedin_profile.invoke(tool_input)
        return json.dumps(result, indent=2)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ============================================================
# THE AGENT LOOP
# ============================================================
# This is the manual loop pattern that avoids LangChain
# AgentExecutor streaming issues we hit on Day 8-9.
# Raw Groq API + manual while loop = reliable tool calling.

SYSTEM_PROMPT = """You are a LinkedIn outreach assistant.

For the given target persona:
1. Call search_linkedin_profiles once
2. Call analyze_linkedin_profile for each of the top 3 URLs from search results
3. After 3 analyses, write your final summary

Analyze profiles one at a time."""


def run_outreach_agent(target_persona: str):
    """
    Runs the full outreach agent for a given target persona.
    Searches → Analyzes → Returns structured profile data.
    """

    print("\n" + "="*60)
    print("🤖 OUTREACH AGENT STARTING")
    print("="*60)
    print(f"🎯 Target Persona: {target_persona}\n")

    # Start the conversation
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": (
                f"Find and analyze LinkedIn profiles for this persona: "
                f"'{target_persona}'. "
                f"Search first, then analyze at least 3 profiles, "
                f"then give me a structured summary."
            )
        }
    ]

    loop_count    = 0
    max_loops     = 15      # Safety limit — prevents infinite loops
    profiles_analyzed = 0  # Track how many profiles we've analyzed

    # ── THE AGENT LOOP ──
    while loop_count < max_loops:
        loop_count += 1

        print(f"\n{'─'*60}")
        print(f"🔄 Round {loop_count} — Calling Groq...")
        print(f"{'─'*60}")

        # Call Groq with tools
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
            max_tokens=1000
        )

        response_msg = response.choices[0].message

        # ── Did the agent call a tool? ──
        if response_msg.tool_calls:
            # Add agent's response to history
            messages.append({
                "role":       "assistant",
                "content":    response_msg.content or "",
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response_msg.tool_calls
                ]
            })

            # Process each tool call
            for tool_call in response_msg.tool_calls:
                tool_name  = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)

                # Track how many profiles analyzed
                if tool_name == "analyze_linkedin_profile":
                    profiles_analyzed += 1
                    print(f"\n   📊 Profiles analyzed so far: {profiles_analyzed}")

                # Run the tool
                result = run_tool(tool_name, tool_input)

                print(f"   ✅ Tool completed — result length: {len(result)} chars")

                # Add tool result to conversation
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      result
                })

        # ── No tool call = final answer ──
        else:
            final_answer = response_msg.content or ""

            print("\n" + "="*60)
            print("✅ AGENT FINISHED — FINAL REPORT:")
            print("="*60)
            print(f"\n{final_answer}")

            print(f"\n\n{'─'*60}")
            print(f"📊 AGENT STATS:")
            print(f"   Total rounds    : {loop_count}")
            print(f"   Profiles analyzed: {profiles_analyzed}")
            print(f"{'─'*60}")

            return final_answer

    # If we hit max_loops without a final answer
    print("\n⚠️  Agent hit max loop limit. Stopping.")
    print("   This usually means the agent is stuck in a tool loop.")
    print("   Try making the system prompt more explicit about when to stop.")
    return None


# ============================================================
# DEBUGGING HELPER
# ============================================================
# When something breaks, this prints the full conversation
# so you can see exactly what the agent was thinking.

def debug_conversation(messages: list):
    """Print full conversation history for debugging."""
    print("\n" + "🐛 "*20)
    print("DEBUG: FULL CONVERSATION HISTORY")
    print("🐛 "*20)
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if content:
            print(f"\n[{i}] {role}:")
            print(f"   {str(content)[:300]}")
    print("\n" + "🐛 "*20)


# ============================================================
# RUN THE AGENT
# ============================================================

if __name__ == "__main__":

    print("\n" + "🚀 "*20)
    print("  DAY 21: OUTREACH AGENT — END TO END")
    print("🚀 "*20)

    # ── THE TARGET PERSONA ──
    # This is the input from the course task.
    # Change this to whatever audience you want to target.
    target_persona = "ML engineers working at Series A startups in India"

    try:
        result = run_outreach_agent(target_persona)

    except Exception as e:
        print(f"\n❌ Agent crashed with error: {e}")
        print("\n💡 COMMON FIXES:")
        print("  • Check both search_tool.py and profile_analyzer.py are in the same folder")
        print("  • Check your .env has both GROQ_API_KEY and TAVILY_API_KEY")
        print("  • Check Tavily free tier hasn't run out (1000 searches/month)")
        print("  • If JSON error → the model returned malformed tool arguments")
        print("  • If import error → run: python -m pip install tavily-python groq")
        import traceback
        traceback.print_exc()

    print("\n\n" + "="*60)
    print("🧠 WHAT THIS AGENT JUST DID:")
    print("="*60)
    print("""
  1. Received a target persona as plain text input
  2. Decided to call search_linkedin_profiles first
  3. Got back a list of LinkedIn profiles with URLs + snippets
  4. Decided to call analyze_linkedin_profile for each URL
  5. Got back structured data: name, role, hook, score
  6. After 3+ profiles, wrote a final structured report

  You didn't write any of that decision logic.
  The AI planned and executed it based on the system prompt.
  That's what makes it an agent, not just a function chain.
""")
    print("="*60)
    print("\n💡 THINGS TO TRY AFTER THIS WORKS:")
    print("  • Change target_persona to your own use case")
    print("  • Add a third tool: draft_message(profile_data) → message")
    print("  • Make the agent only return profiles with score >= 7")
    print("  • Ask the agent to rank profiles by score before returning\n")
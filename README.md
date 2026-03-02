# LemonAI — LinkedIn Outreach Agent

> Describe who you want to reach. The agent finds them on LinkedIn, analyzes each profile, and drafts a personalized message — automatically.

**Live demo:** [lemonai.vercel.app](https://lemon-ai-omega.vercel.app/agent)  
**Backend API:** [lemonai-fapu.onrender.com](https://lemonai-fapu.onrender.com)

---

## What it does

You type a target persona like *"ML engineers at Series A startups in India"* and a short pitch. The agent:

1. **Searches LinkedIn** via Tavily to find matching profiles
2. **Analyzes each profile** using Groq LLaMA 70B — extracts role, company, and a specific personalization hook
3. **Scores relevance** from 1–10 and filters out low-quality matches
4. **Drafts a personalized message** under 150 words, specific to each person
5. **Stores everything** in Qdrant Cloud vector database and exports to CSV

Results appear in real time as each profile is processed — no frozen UI, no waiting 60 seconds for a batch.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), CSS Modules |
| Backend | FastAPI, Python 3.11 |
| LLM | Groq LLaMA 70B (analysis + drafting) |
| Search | Tavily API (live LinkedIn search) |
| Vector DB | Qdrant Cloud (profile storage + semantic search) |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5, ONNX) |
| Deployment | Render (backend), Vercel (frontend) |

---

## How it works — architecture

```
User Input (persona + pitch)
        │
        ▼
POST /jobs  ──→  Background Thread
                      │
                      ├── Tavily Search (find LinkedIn URLs)
                      │
                      ├── Groq Analysis (per profile)
                      │     ├── Extract: name, role, company, hook
                      │     └── Score: relevance 1–10
                      │
                      ├── Filter (score < threshold → skip)
                      │
                      ├── Groq Draft (personalized message)
                      │
                      └── Store in Qdrant + export CSV
                      
Frontend polls GET /jobs/{id} every 3s
Results appear as each profile finishes
```

---

## Run locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- API keys for: [Groq](https://console.groq.com), [Tavily](https://tavily.com), [Qdrant Cloud](https://cloud.qdrant.io)

### Backend

```bash
# Clone the repo
git clone https://github.com/Himanshunagyal/LemonAI.git
cd LemonAI/tools

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Start the server
uvicorn api:app --reload --port 8000
```

### Frontend

```bash
cd ../frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## Environment variables

Create a `.env` file in the `tools/` folder:

```
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
QDRANT_URL=https://your-cluster.aws.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
```

---

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/jobs` | Start agent job, returns `job_id` immediately |
| `GET` | `/jobs/{id}` | Poll job status and results |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/results` | All stored profiles from Qdrant |
| `GET` | `/stats` | Dashboard stats (total, avg score, etc.) |
| `POST` | `/search` | Semantic search across stored profiles |
| `GET` | `/health` | Health check |

### Example — start a job

```bash
curl -X POST https://lemonai-fapu.onrender.com/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "persona": "ML engineers at Series A startups in India",
    "sender_context": "I am building an AI recruiting tool for startups.",
    "max_profiles": 5,
    "min_score": 6
  }'
```

Response:
```json
{
  "job_id": "a3f9b2c1",
  "status": "pending",
  "poll_url": "/jobs/a3f9b2c1"
}
```

### Example — poll for results

```bash
curl https://lemonai-fapu.onrender.com/jobs/a3f9b2c1
```

Response when done:
```json
{
  "status": "done",
  "duration_seconds": 42.3,
  "profiles_processed": 4,
  "profiles_skipped": 6,
  "results": [
    {
      "name": "Saurabh",
      "role": "Co-founder & CTO",
      "company": "NEO",
      "score": 9,
      "hook": "Building AI-native recruiting tools at NEO after scaling ML infra at Flipkart",
      "message": "Hey Saurabh — saw you're building AI-native recruiting at NEO after your Flipkart ML infra days. I'm working on something adjacent and would love 15 minutes to compare notes on where the market is heading. Worth a chat?"
    }
  ]
}
```

---

## Project structure

```
LemonAI/
├── tools/                      ← FastAPI backend
│   ├── api.py                  ← Main API with async job processing
│   ├── search_tool.py          ← Tavily LinkedIn search
│   ├── profile_analyzer.py     ← Groq profile analysis
│   ├── message_drafter.py      ← Groq message drafting
│   ├── vector_store.py         ← Qdrant Cloud wrapper
│   ├── stable_pipeline.py      ← Error handling + CSV export
│   └── requirements.txt
│
└── frontend/                   ← Next.js frontend
    └── app/
        ├── page.js             ← Homepage
        ├── agent/
        │   └── page.js         ← Agent interface with polling
        └── components/
            └── ProfileCard.js  ← Result card component
```

---

## Key design decisions

**Async job processing** — the frontend triggers a job and polls every 3 seconds instead of waiting on a single long HTTP request. This means the UI stays responsive and shows results as they arrive.

**Deduplication** — profiles are stored by LinkedIn URL as a unique key. The agent never re-processes the same person twice, saving API credits.

**FastEmbed over PyTorch** — switched from `sentence-transformers` (2GB+ with CUDA) to `fastembed` (150MB, ONNX runtime) to fit within free-tier deployment memory limits.

**Qdrant Cloud** — profiles survive server restarts and deployments. Semantic search lets you query stored profiles by meaning, not just keyword.

---

## Built over 37 days

This project was built incrementally over 37 days — from a basic Python script to a deployed full-stack AI agent. The day-by-day breakdown covers: pipeline design, error handling, vector storage, API design, async processing, and deployment.

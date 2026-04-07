# 🔍 Job Agent — Maral's Automated Job Search

An AI-powered job agent that runs on your Mac, scrapes LinkedIn, Indeed, and Xing
for Data Science / Data Analyst / ML Engineer roles in NRW and remote,
scores each job against your resume using Claude, and sends you a digest email
with tailored resume versions for every match.

---

## What it does

1. **Scrapes** LinkedIn, Indeed.de, and Xing every hour
2. **Deduplicates** — never processes the same job twice
3. **Scores** each job description against your resume with Claude (0–100%)
4. **Filters** jobs below 60% match — you only see quality matches
5. **Optimizes** your resume for each matched job (reframes real experience, no fake skills)
6. **Emails** a digest with match scores, skill breakdown, and links

---

## Setup (one time, ~15 minutes)

### 1. Clone / download the project

```bash
# Put it in your home folder
mv job_agent ~/job_agent
cd ~/job_agent
```

### 2. Create Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Get your API keys

**Anthropic API key** (for Claude):
- Go to https://console.anthropic.com
- Create an API key
- Copy it

**Gmail App Password** (for sending emails):
- Go to your Google Account → Security → 2-Step Verification (must be ON)
- Then: Security → App passwords
- Create a new app password (name it "Job Agent")
- Copy the 16-character password

### 4. Set environment variables

Add these to your `~/.zshrc` (or `~/.bash_profile`):

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

Then reload: `source ~/.zshrc`

### 5. Test the agent manually

```bash
cd ~/job_agent
source venv/bin/activate
python main.py --test
```

This runs with mock jobs so you can verify the email arrives without real scraping.

### 6. Install the macOS scheduler (launchd)

Edit the plist file — replace `YOUR_USERNAME` with your actual Mac username:

```bash
# Find your username
whoami

# Edit the plist
nano com.maral.jobagent.plist
# Replace every instance of YOUR_USERNAME
# Add your API keys in the EnvironmentVariables section

# Install
cp com.maral.jobagent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.maral.jobagent.plist
```

The agent will now run automatically every hour.

---

## Project structure

```
job_agent/
├── main.py                    # Entry point — orchestrates everything
├── config.yaml                # Search config (roles, cities, threshold)
├── requirements.txt
├── com.maral.jobagent.plist   # macOS scheduler config
│
├── core/
│   ├── agent.py               # Claude API: scoring + resume optimization
│   ├── db.py                  # SQLite job cache (deduplication)
│   ├── emailer.py             # Email digest builder + sender
│   └── resume_data.py         # Your resume text (EN + DE)
│
├── scrapers/
│   ├── linkedin.py            # LinkedIn scraper (Playwright)
│   ├── indeed.py              # Indeed.de scraper (Playwright)
│   └── xing.py                # Xing scraper (Playwright)
│
├── data/
│   └── jobs.db                # Auto-created SQLite database
│
└── output/
    └── optimized_resumes/     # Tailored resume .md files per job
```

---

## Useful commands

```bash
# Run manually (full scrape)
python main.py

# Run with mock data (for testing)
python main.py --test

# View scheduler logs
tail -f /tmp/job_agent.log

# Stop the scheduler
launchctl unload ~/Library/LaunchAgents/com.maral.jobagent.plist

# Restart the scheduler
launchctl unload ~/Library/LaunchAgents/com.maral.jobagent.plist
launchctl load ~/Library/LaunchAgents/com.maral.jobagent.plist

# View all seen jobs in the database
sqlite3 data/jobs.db "SELECT title, company, match_score, first_seen FROM seen_jobs ORDER BY match_score DESC;"
```

---

## Updating your resume

Your resume is stored as text in `core/resume_data.py` (both EN and DE versions).
If you gain new skills or experience, just edit that file — the agent will use it
for all future matches and optimizations.

---

## Notes on scraping

LinkedIn and Xing occasionally update their HTML structure,
which can break the CSS selectors in the scrapers.
If a scraper stops returning results, check `/tmp/job_agent_error.log`
and update the selectors in the relevant file under `scrapers/`.

The agent is polite: it waits 2 seconds between page requests
and uses a realistic browser user-agent string.

---

## Privacy

- Your resume text lives only on your Mac in `core/resume_data.py`
- Job descriptions are sent to the Anthropic API for scoring (same as using Claude.ai)
- No data is stored anywhere except your local `data/jobs.db`
- API keys are stored in environment variables, never in code

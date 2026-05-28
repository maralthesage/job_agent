# Job Agent

Job Agent is a local job-search assistant for macOS. It searches LinkedIn,
Stepstone, and Xing, filters listings against your target roles and locations,
scores each job against your CV with Ollama running on your machine, and shows
the results in a browser digest.

No hosted model account is needed. Install Ollama, pull a local model, start the
app, enter your search settings, upload or paste your CV, and click Start Search.

## Quick Start

Install Ollama first from `https://ollama.com/download`. If Ollama is not
already running, start it in a separate terminal:

```bash
ollama serve
```

Keep that terminal open while Job Agent is scoring jobs. If `ollama serve` says
the address is already in use, Ollama is already running.

Then set up and run the project:

```bash
git clone <this-repository-url>
cd job_agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

ollama pull llama3.2
python main.py
```

When the browser opens, go to `Settings`, add your search details and CV, then
click `Start Search`.

## Requirements

- macOS
- Python 3.10 or newer
- Ollama installed from `https://ollama.com/download`
- An Ollama model installed locally, for example `llama3.2`

## How To Use The App

1. Start the local browser app:

   ```bash
   source venv/bin/activate
   python main.py
   ```

2. Open this page if the browser does not open automatically:

   ```text
   http://localhost:8765/settings
   ```

3. Fill in the settings:

   - `Role Keywords`: one job title per line, such as `Data Analyst`
   - `Job Description Keywords`: optional skills or phrases, such as `Python`
   - `Locations`: one location per line, such as `Berlin`, `Germany`, or `Remote`
   - `Match Threshold`: minimum score to show in the digest, such as `0.75`
   - `Job Boards`: choose LinkedIn, Stepstone, Xing, or any combination
   - `CV / Resume`: upload a PDF CV or paste your CV text

4. Click `Save Settings`.

5. Click `Start Search`.

6. View results at:

   ```text
   http://localhost:8765/digest
   ```

The digest updates while scraping and scoring is running. Jobs are saved in the
local SQLite database at `data/jobs.db` so the same job is not processed again
unless you clear old jobs from the settings page.

## Ollama Model

The app uses the model name from the `OLLAMA_MODEL` environment variable. If
that variable is not set, it uses:

```text
llama3.2
```

Install the default model:

```bash
ollama pull llama3.2
```

Check your installed models:

```bash
ollama list
```

Use a different installed model for one run:

```bash
OLLAMA_MODEL=mistral python main.py
```

Or set it in your shell before starting the app:

```bash
export OLLAMA_MODEL=llama3.2
python main.py
```

The model name must exactly match a name shown by `ollama list`.

## Test Mode

Use test mode to verify that Python, Ollama, and the local digest server work
without scraping job boards:

```bash
source venv/bin/activate
python main.py --run --test
```

Test mode still uses Ollama to score mock jobs, so Ollama must be running and
the configured model must be installed.

## Optional File-Based Run

The browser UI is the easiest way to use the app. For a terminal-only run, copy
the example config and edit it:

```bash
cp data/user_config.example.json data/user_config.json
```

Open `data/user_config.json`, replace the sample roles, locations, keywords,
and `cv_text`, then run:

```bash
python main.py --run
```

The browser settings page stores settings in your browser. The `--run` command
uses `data/user_config.json` instead.

## Optional macOS Login Startup

`com.jobagent.plist` is a launchd template that can start the browser app when
you log in.

1. Edit every `/Users/YOUR_USERNAME/job_agent` path in `com.jobagent.plist`.
2. Copy it into LaunchAgents:

   ```bash
   cp com.jobagent.plist ~/Library/LaunchAgents/
   ```

3. Load it:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.jobagent.plist
   ```

4. Stop it later:

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.jobagent.plist
   ```

Manual startup with `python main.py` is recommended until you know the app works
on your machine.

## Useful Commands

```bash
# Start the browser UI
python main.py

# Run mock jobs through the scoring pipeline
python main.py --run --test

# Run from data/user_config.json
python main.py --run

# Show installed Ollama models
ollama list

# Inspect stored jobs
sqlite3 data/jobs.db "SELECT title, company, match_score, first_seen FROM seen_jobs ORDER BY match_score DESC;"
```

## Project Structure

```text
job_agent/
|-- main.py                     # Entry point
|-- requirements.txt            # Python dependencies
|-- com.jobagent.plist          # Optional macOS launchd template
|-- data/
|   `-- user_config.example.json
|-- core/
|   |-- agent.py                # Ollama scoring and resume tailoring
|   |-- cv_parser.py            # PDF CV text extraction
|   |-- db.py                   # SQLite job cache
|   |-- emailer.py              # Browser digest HTML builder
|   |-- filters.py              # Title and description filters
|   |-- resume_data.py          # Empty fallback resume placeholders
|   |-- server.py               # Local settings and digest server
|   `-- user_config.py          # File-based config loader
|-- scrapers/
|   |-- linkedin.py
|   |-- stepstone.py
|   `-- xing.py
`-- output/
    `-- digests/
```

## Local Files Not Committed

The `.gitignore` is set up so generated and private files stay out of a public
repository:

- `venv/` and `.venv/`
- Python cache folders
- local assistant/editor folders
- `data/jobs.db`
- `data/user_config.json`
- generated files under `output/`
- CV and resume files

The tracked example config is `data/user_config.example.json`.

## Troubleshooting

### `ModuleNotFoundError: No module named 'ollama'`

Activate the virtual environment and install dependencies:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Ollama Is Not Responding

Start Ollama:

```bash
ollama serve
```

Then start Job Agent again.

### `model not found`

Install the configured model:

```bash
ollama pull llama3.2
```

Or choose one of your installed models:

```bash
ollama list
OLLAMA_MODEL=<model-name> python main.py
```

### Playwright Browser Errors

Install Chromium for Playwright:

```bash
playwright install chromium
```

### No Jobs Appear

- Add at least one role keyword and one location
- Upload or paste your CV before starting a search
- Try broader titles or locations
- Lower the match threshold
- Enable more job boards
- Use `Clear Old Jobs` in settings if you want old listings processed again

### A Job Board Stops Returning Results

Job boards change their page markup from time to time. Check the terminal output
or `/tmp/job_agent_error.log`, then update the affected scraper in `scrapers/`.

## Privacy

- Your CV text is stored in browser local storage when you use the settings page
- Terminal-only config is stored locally in `data/user_config.json`
- Seen jobs are stored locally in `data/jobs.db`
- Job scoring is performed by Ollama running on your machine
- The app contacts job boards only to load listings and job descriptions

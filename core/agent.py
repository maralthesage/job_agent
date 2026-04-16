"""
agent.py — Ollama-powered job matching and resume optimization engine
Uses local Ollama for:
  1. Scoring resume-to-job match (0.0–1.0)
  2. Generating a tailored resume version for matched jobs
"""
import json
import re
from typing import Dict, Tuple

import ollama

from core.resume_data import MARAL_RESUME_EN, MARAL_RESUME_DE

MODEL = "gemma4:e4b"


def _call(prompt: str, max_tokens: int = 1024) -> str:
    """Call Ollama and return the text, stripping any <think> blocks."""
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"num_predict": max_tokens, "temperature": 0.1},
    )
    text = response.message.content.strip()
    # Qwen3 wraps reasoning in <think>...</think> — remove it
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


def _extract_domain_keywords(cv_text: str) -> str:
    """
    Extract key technical skills and expertise from CV to guide job matching.
    Looks for programming languages, tools, methodologies, and domains mentioned.
    """
    keywords = set()
    cv_lower = cv_text.lower()

    # Technical skills and tools to look for (language/framework agnostic)
    technical_terms = {
        # Programming languages
        "python", "sql", "r", "java", "javascript", "scala", "go",
        # Data stack
        "pandas", "numpy", "spark", "pyspark", "dask", "polars",
        "hadoop", "hive", "presto", "snowflake", "redshift", "bigquery",
        "postgres", "mysql", "mongodb", "cassandra", "elasticsearch",
        # ML/AI
        "scikit-learn", "sklearn", "tensorflow", "pytorch", "keras",
        "xgboost", "lightgbm", "catboost", "mlflow", "huggingface",
        "transformer", "bert", "gpt", "llm", "langchain", "rag",
        # Data engineering & pipelines
        "etl", "elt", "airflow", "dbt", "prefect", "luigi",
        "kafka", "kinesis", "rabbitmq", "nifi",
        # Analytics & BI
        "tableau", "power bi", "qlik", "looker", "streamlit", "dash",
        "plotly", "matplotlib", "seaborn", "ggplot",
        # Cloud & infrastructure
        "aws", "gcp", "google cloud", "azure", "docker", "kubernetes",
        "jenkins", "gitlab", "github actions", "ci/cd",
        # Databases & data warehousing
        "data warehouse", "data lake", "delta lake", "iceberg",
        # Core competencies
        "machine learning", "deep learning", "nlp", "computer vision",
        "forecasting", "regression", "classification", "clustering",
        "time series", "anomaly detection", "feature engineering",
        "data engineering", "data science", "analytics", "analysis",
        "statistical", "statistical modeling", "ab testing",
        # Soft skills for data roles
        "stakeholder", "communication", "documentation",
        "version control", "git", "experimentation"
    }

    for term in technical_terms:
        if term in cv_lower:
            keywords.add(term)

    # If no keywords found, return generic data science keywords
    if not keywords:
        return "data science, analytics, machine learning, python, sql"

    return ", ".join(sorted(keywords))


def score_job(job: Dict, threshold: float = 0.60, cv_text: str = None, target_roles: list = None) -> Tuple[float, Dict]:
    """
    Score how well a candidate's resume matches a job description.
    Returns (score, details_dict).

    Args:
        job: job dict with title, company, location, description
        threshold: (unused, kept for compatibility)
        cv_text: if provided, use this CV text; otherwise fall back to hardcoded EN/DE resume
        target_roles: list of target job roles (e.g., ["Data Scientist", "Data Analyst"]) to guide scoring
    """
    description = job.get("description", "")
    if not description or len(description) < 50:
        return 0.0, {"error": "no description"}

    # Use provided CV text, or fall back to EN/DE auto-detect
    if cv_text:
        resume = cv_text
        print(f"[Agent] Using uploaded CV ({len(cv_text)} chars)")
    else:
        # Use DE resume if job is likely German-language
        de_keywords = ["wir suchen", "ihre aufgaben", "kenntnisse", "deutsch", "anforderungen"]
        is_german = any(kw in description.lower() for kw in de_keywords)
        resume = MARAL_RESUME_DE if is_german else MARAL_RESUME_EN
        print(f"[Agent] Using fallback resume ({'DE' if is_german else 'EN'})")

    # Extract domain keywords from CV to guide scoring
    domain_keywords = _extract_domain_keywords(resume)

    # Build role alignment description
    if target_roles and len(target_roles) > 0:
        target_roles_str = ", ".join(target_roles)
    else:
        target_roles_str = "data science, analytics, machine learning, engineering roles"

    prompt = f"""You are a senior recruiter evaluating a candidate's fit for a job opportunity.

Analyze the match between this candidate's resume and the job description.

CANDIDATE RESUME:
{resume}

CANDIDATE'S DOMAIN EXPERTISE: {domain_keywords}

TARGET ROLES: {target_roles_str}

JOB TITLE: {job.get('title', 'N/A')}
COMPANY: {job.get('company', 'N/A')}
LOCATION: {job.get('location', 'N/A')}
JOB DESCRIPTION:
{description[:3000]}

Respond ONLY with a valid JSON object (no markdown, no preamble) with these exact keys:
{{
  "match_score": <float 0.0 to 1.0>,
  "matching_skills": [<list of skills from resume that match JD>],
  "missing_skills": [<required skills in JD not found in resume>],
  "relevant_experience": [<1-2 sentence summary of most relevant experience>],
  "language_match": <"de" or "en">,
  "recommendation": <"apply" or "skip">,
  "reason": <1 sentence why>
}}

Scoring guide:
- 0.9–1.0: near-perfect match (required skills present, strong experience/industry alignment)
- 0.7–0.9: strong match (key skills present, matching industry or role type)
- 0.5–0.7: moderate match (some relevant skills, but gaps in some technical skills or seniority)
- 0.3–0.5: weak match (transferable skills present, but significant gaps or different domain)
- below 0.3: poor match (different career path or missing core competencies)

EVALUATION CRITERIA:
1. Role alignment: Does the job fit the candidate's target roles ({target_roles_str})?
2. Skills match: Are the core technical and soft skills required present in the resume?
3. Industry/domain fit: Does the candidate's expertise align with the job domain?
4. Experience level: Is the candidate's seniority and background appropriate?

Be generous with scoring for jobs that match the target roles and contain relevant technical skills — the candidate is actively seeking these roles.
Prioritize skills match and role alignment. Do not be overly strict about having every single skill mentioned.
"""

    try:
        raw = _call(prompt, max_tokens=1024)
        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)
        score = float(result.get("match_score", 0.0))
        return score, result
    except Exception as e:
        print(f"[Agent] scoring error for '{job.get('title')}': {e}")
        return 0.0, {"error": str(e)}


def optimize_resume(job: Dict, match_details: Dict, cv_text: str = None) -> str:
    """
    Generate a tailored version of the resume for a specific job.
    Rules enforced in prompt:
      - No invented skills or experience
      - Only reframing, reordering, keyword alignment
      - Language matches the job (DE or EN)
    Returns the optimized resume as markdown text.

    Args:
        job: job dict with title, company, location, description
        match_details: dict with matching_skills, missing_skills, etc.
        cv_text: if provided, use this CV text; otherwise fall back to hardcoded EN/DE resume
    """
    description = job.get("description", "")
    de_keywords = ["wir suchen", "ihre aufgaben", "kenntnisse", "deutsch", "anforderungen"]
    is_german = any(kw in description.lower() for kw in de_keywords)

    if cv_text:
        resume = cv_text
    else:
        resume = MARAL_RESUME_DE if is_german else MARAL_RESUME_EN

    lang = "German" if is_german else "English"

    matching = ", ".join(match_details.get("matching_skills", []))
    missing = ", ".join(match_details.get("missing_skills", []))

    prompt = f"""You are an expert career coach and resume writer specializing in data science roles in Germany.

Your task is to tailor the candidate's resume for a specific job opportunity.

STRICT RULES — violating any of these is unacceptable:
1. DO NOT add any skill, tool, technology, certification, or experience that is not in the original resume
2. DO NOT change job titles, dates, company names, education, or GPA
3. DO NOT fabricate projects, achievements, or metrics
4. You MAY reorder bullet points to surface the most relevant ones first
5. You MAY rephrase existing bullet points to use the job description's exact keywords — but only when the meaning is the same
6. You MAY expand or compress the profile/summary section using the candidate's real background
7. You MAY reorder sections (e.g. put most relevant project first)
8. Write in {lang} to match the job

CANDIDATE RESUME:
{resume}

TARGET JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Description: {description[:2500]}

MATCH ANALYSIS:
- Already matching skills: {matching}
- Gaps (do NOT invent these — only highlight adjacent real skills): {missing}

OUTPUT FORMAT:
Return the complete tailored resume in clean Markdown format.
Start with the candidate's name and contact info, then all sections.
After the resume, add a short section titled "## Tailoring Notes" explaining what you changed and why.
"""

    try:
        return _call(prompt, max_tokens=4096)
    except Exception as e:
        print(f"[Agent] optimization error for '{job.get('title')}': {e}")
        return f"Error generating optimized resume: {e}"

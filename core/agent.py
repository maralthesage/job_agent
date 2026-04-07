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

MODEL = "qwen3:latest"


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


def score_job(job: Dict, threshold: float = 0.60) -> Tuple[float, Dict]:
    """
    Score how well Maral's resume matches a job description.
    Returns (score, details_dict).
    """
    description = job.get("description", "")
    if not description or len(description) < 50:
        return 0.0, {"error": "no description"}

    # Use DE resume if job is likely German-language
    de_keywords = ["wir suchen", "ihre aufgaben", "kenntnisse", "deutsch", "anforderungen"]
    is_german = any(kw in description.lower() for kw in de_keywords)
    resume = MARAL_RESUME_DE if is_german else MARAL_RESUME_EN

    prompt = f"""You are a senior technical recruiter evaluating a candidate for a data science/analytics role.

Analyze the match between this candidate's resume and the job description below.

CANDIDATE RESUME:
{resume}

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
- 0.9–1.0: near-perfect match (most required skills present, strong experience alignment)
- 0.7–0.9: strong match (key skills present, some minor gaps)
- 0.6–0.7: decent match (core skills align, a few gaps)
- below 0.6: weak match (significant gaps in required skills or experience)
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


def optimize_resume(job: Dict, match_details: Dict) -> str:
    """
    Generate a tailored version of Maral's resume for a specific job.
    Rules enforced in prompt:
      - No invented skills or experience
      - Only reframing, reordering, keyword alignment
      - Language matches the job (DE or EN)
    Returns the optimized resume as markdown text.
    """
    description = job.get("description", "")
    de_keywords = ["wir suchen", "ihre aufgaben", "kenntnisse", "deutsch", "anforderungen"]
    is_german = any(kw in description.lower() for kw in de_keywords)
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

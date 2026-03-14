"""LLM-powered resume parser — extracts a structured candidate profile."""

from __future__ import annotations

import json
import re

_SYSTEM_PROMPT = (
    "You are a professional resume analyst. Your job is to extract a structured "
    "profile from the raw resume text provided by the user. "
    "Return ONLY valid JSON — no markdown fences, no commentary, no preamble."
)

_USER_TEMPLATE = """\
Here is the raw resume text:

{resume_raw_text}

Return a JSON object matching this exact schema:

{{
  "full_name": "string",
  "seniority_level": "intern | junior | mid | senior | staff | principal | executive",
  "primary_domain": "string  (e.g. Backend Engineering, Product Management)",
  "secondary_domains": ["string  (up to 3)"],
  "years_of_experience": "number",
  "technical_skills": ["string  (tools, languages, frameworks)"],
  "soft_skills": ["string  (leadership, communication, etc.)"],
  "industries": ["string  (sectors worked in)"],
  "key_achievements": ["string  (3–5 bullet-ready achievement statements)"],
  "notable_companies": ["string"],
  "education_summary": "string  (one-line summary)",
  "professional_summary": "string  (3–4 sentence narrative for interview context)"
}}

Do not invent information. If a field cannot be determined, use null.
"""


def parse_resume(raw_text: str, llm) -> dict:
    """Call the LLM to extract a structured profile from raw resume text.

    Args:
        raw_text: Plain text extracted from the uploaded resume document.
        llm: A LangChain chat model instance (e.g. ChatGoogleGenerativeAI).

    Returns:
        Parsed dict matching the resume schema. Fields that cannot be
        determined are set to null / None.

    Raises:
        ValueError: If the LLM response cannot be parsed as JSON.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_USER_TEMPLATE.format(resume_raw_text=raw_text)),
    ]

    from src.services.llm import _extract_text

    response = llm.invoke(messages)
    content = _extract_text(response.content if hasattr(response, "content") else response)

    # Strip markdown fences if the model ignores our instructions
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\n\nRaw output:\n{content}") from exc


def build_gap_map(candidate_profile: dict, jd_text: str, llm) -> dict:
    """Compute skill overlap between the candidate profile and a job description.

    Returns a gap_map with three keys:
      - strong_match: skills present in both profile and JD
      - partial_match: adjacent / related skills
      - gaps: JD requires, candidate hasn't claimed
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    candidate_skills = candidate_profile.get("technical_skills") or []
    soft_skills = candidate_profile.get("soft_skills") or []
    all_skills = candidate_skills + soft_skills

    system = (
        "You are a talent gap analyst. Given a candidate's skills and a job description, "
        "identify skill overlap and gaps. Return ONLY valid JSON — no markdown, no preamble."
    )
    user = (
        f"Candidate skills: {json.dumps(all_skills)}\n\n"
        f"Job description:\n{jd_text[:3000]}\n\n"
        "Return a JSON object:\n"
        "{\n"
        '  "strong_match": ["skills present in both profile and JD"],\n'
        '  "partial_match": ["adjacent or related skills"],\n'
        '  "gaps": ["JD requires but candidate has not claimed"]\n'
        "}\n"
        "Use only skills/requirements explicitly mentioned. Do not invent."
    )

    from src.services.llm import _extract_text

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    response = llm.invoke(messages)
    content = _extract_text(response.content if hasattr(response, "content") else response)
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"strong_match": [], "partial_match": [], "gaps": []}

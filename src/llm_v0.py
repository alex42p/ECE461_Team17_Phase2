import os
import requests  # type: ignore
from urllib.parse import urlparse
import re
import json
from typing import Any, Dict


def extract_repo_id(url: str) -> str:
    """
    Extract the repo ID (like 'google-bert/bert-base-uncased') from the HF URL.
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) >= 2:
        repo_id = f"{path_parts[0]}/{path_parts[1]}"
        return repo_id
    else:
        raise ValueError("URL does not contain a valid repo identifier")


def fetch_repo_readme(repo_url: str) -> Any:
    """
    Fetch the raw README text from a Hugging Face repo.
    """
    try:
        repo_id = extract_repo_id(repo_url)
    except ValueError as e:
        print(e)
        return ""

    README_url = f"https://huggingface.co/{repo_id}/raw/main/README.md"

    try:
        response = requests.get(README_url)
        if response.status_code != 200:
            print(f"Failed to fetch README: HTTP {response.status_code}")
            return ""
        return response.text
    except Exception as e:
        print(f"Error fetching README: {e}")
        return ""


def strip_hf_metadata(text: str) -> str:
    """
    Remove Hugging Face YAML metadata (--- ... ---) from README.md content.
    """
    return re.sub(r"^---[\s\S]*?---\n", "", text, count=1)


def fetch_performance_claims_with_llm(repo_url: str) -> Dict[str, Any]:
    """
    Use an LLM to extract numeric performance claims and compute a normalized score.
    Returns a dict: {"claims": {...}, "score": float}.
    """
    api_key = "sk-798d650f3cce4ea1968e9532bcc42e51"
    if not api_key:
        # Safe fallback for autograder if key isn’t injected
        return {
            "claims": {},
            "score": 0.0,
            "note": "GENAI_API_KEY not set"
        }

    readme_text = fetch_repo_readme(repo_url)
    if not readme_text:
        return {"claims": {}, "score": 0.0, "note": "README not found"}

    clean_readme = strip_hf_metadata(readme_text)

    url = "https://genai.rcac.purdue.edu/api/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama4:latest",
        "messages": [
            {
                "role": "user",
                "content": (
                    "You are a strict JSON generator. "
                    "From the following README text, extract all reported performance metrics with numerical values. "
                    "This includes both inline mentions (e.g., 'Accuracy: 90.5%') and values inside markdown tables. "
                    "For tables: use the header row to identify metric names (Accuracy, F1, Precision, Recall, BLEU, etc.) "
                    "and extract the corresponding numeric values under those headers. Ignore dataset/task names (like QQP or SST-2) "
                    "unless they are metrics themselves. "
                    "Rules: "
                    "1. Only include metrics actually found. Do not include metrics with null or missing values. "
                    "2. Always output valid JSON (no markdown, no prose). "
                    "3. JSON must have two keys: `claims` (metric→normalized float in [0,1]) and `score` (average). "
                    "4. Normalize values: higher is better for accuracy/precision/recall/F1/etc.; "
                    "lower is better for perplexity, loss, error rate, edit-distance, BPC. "
                    "5. If multiple models are shown, focus only on the primary model described in this README, not baselines. "
                    "Now return the JSON.\n\n"
                    + clean_readme
                )
            }
        ]
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        return {
            "claims": {},
            "score": 0.0,
            "note": f"LLM API error {response.status_code}"
        }

    result = response.json()
    try:
        content = result["choices"][0]["message"]["content"].strip()

        # Strip Markdown code fences if LLM added them
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n", "", content)
            content = content.strip("`").strip()

        parsed = json.loads(content)
        return parsed
    except Exception:
        return {"claims": {}, "score": 0.0, "note": "Failed to parse LLM output"}


def fetch_ramp_up_time_with_llm(repo_url: str) -> Dict[str, Any]:
    """
    Use an LLM to score ramp-up time readiness based on documentation quality.
    Returns a dict with subscores and an aggregate score.
    """
    api_key = "sk-798d650f3cce4ea1968e9532bcc42e51"
    if not api_key:
        return {
            "doc_completeness": 0.0,
            "installability": 0.0,
            "quickstart": 0.0,
            "config_clarity": 0.0,
            "troubleshooting": 0.0,
            "justification": "GENAI_API_KEY not set",
            "score": 0.0,
        }

    readme_text = fetch_repo_readme(repo_url)
    if not readme_text:
        return {
            "doc_completeness": 0.0,
            "installability": 0.0,
            "quickstart": 0.0,
            "config_clarity": 0.0,
            "troubleshooting": 0.0,
            "justification": "README not found",
            "score": 0.0,
        }

    clean_readme = strip_hf_metadata(readme_text)

    url = "https://genai.rcac.purdue.edu/api/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama4:latest",
        "messages": [
            {
                "role": "user",
                "content": (
                    "You are a strict JSON generator. "
                    "Read the following README and rate its ramp-up readiness. "
                    "Return ONLY valid JSON with this schema:\n"
                    "{\n"
                    "  \"doc_completeness\": float (0–1),\n"
                    "  \"installability\": float (0–1),\n"
                    "  \"quickstart\": float (0–1),\n"
                    "  \"config_clarity\": float (0–1),\n"
                    "  \"troubleshooting\": float (0–1),\n"
                    "  \"justification\": \"1–3 short bullet points\",\n"
                    "  \"score\": float (0–1)\n"
                    "}\n\n"
                    "Guidelines:\n"
                    "- doc_completeness: structure, prerequisites, clarity.\n"
                    "- installability: clear pip/conda commands, dependencies.\n"
                    "- quickstart: runnable example code.\n"
                    "- config_clarity: explanation of config files/params.\n"
                    "- troubleshooting: known issues, limitations, FAQs.\n\n"
                    "README:\n\n"
                    + clean_readme
                )
            }
        ]
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        return {
            "doc_completeness": 0.0,
            "installability": 0.0,
            "quickstart": 0.0,
            "config_clarity": 0.0,
            "troubleshooting": 0.0,
            "justification": f"LLM API error {response.status_code}",
            "score": 0.0,
        }

    result = response.json()
    try:
        content = result["choices"][0]["message"]["content"].strip()

        # Strip Markdown fences if LLM added them
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n", "", content)
            content = content.strip("`").strip()

        parsed = json.loads(content)
        return parsed
    except Exception:
        return {
            "doc_completeness": 0.0,
            "installability": 0.0,
            "quickstart": 0.0,
            "config_clarity": 0.0,
            "troubleshooting": 0.0,
            "justification": "Failed to parse LLM output",
            "score": 0.0,
        }

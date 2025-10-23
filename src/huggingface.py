from entities import HFModel
import requests  # type: ignore
from typing import Any
from urllib.parse import urlparse


def extract_repo_id(url: str) -> str:
    """
    Extract the repo ID (like 'google-bert/bert-base-uncased').
    For models only.
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) >= 2:
        return f"{path_parts[0]}/{path_parts[1]}"
    else:
        raise ValueError("URL does not contain a valid repo identifier")


def extract_dataset_id(url: str) -> str:
    """
    Extract the dataset ID from a Hugging Face dataset URL.
    Examples:
      - https://huggingface.co/datasets/glue -> glue
      - https://huggingface.co/datasets/HuggingFaceFW/fineweb-2 -> HuggingFaceFW/fineweb-2
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) < 2 or path_parts[0] != "datasets":
        raise ValueError("Invalid dataset URL")

    if len(path_parts) == 2:
        return path_parts[1]  # top-level dataset
    return f"{path_parts[1]}/{path_parts[2]}"  # org/dataset

def fetch_repo_metadata(model: HFModel) -> dict[str, Any]:
    """
    Fetch metadata for an HFModelURL instance via the Hugging Face API.
    """
    try:
        model.repo_id = extract_repo_id(model.model_url.url)
    except ValueError as e:
        print(e)
        return {"": None}

    api_url = f"https://huggingface.co/api/models/{model.repo_id}"

    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            print(f"Failed to fetch model data: HTTP {response.status_code}")
            return {"": None}

        data = response.json()

        raw_license = data.get("license", "N/A")
        readme_text = ""

        readme_url = f"https://huggingface.co/{model.repo_id}/raw/main/README.md"
        try:
            resp = requests.get(readme_url, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                readme_text = text
                if raw_license == "N/A":
                    for line in text.lower().splitlines():
                        if line.startswith("license:"):
                            raw_license = line.split(":", 1)[1].strip()
                            break
        except Exception as e:
            print(f"Error fetching README: {e}")

        try:
            dataset_list = data.get("datasets", [])
            if not isinstance(dataset_list, list):
                dataset_list = [dataset_list] if dataset_list else []
        except Exception as e:
            dataset_list = []

        file_list = []
        try:
            siblings = data.get("siblings", [])
            if isinstance(siblings, list):
                file_list = [s.get("rfilename") for s in siblings if isinstance(s, dict) and "rfilename" in s]
        except Exception as e:
            file_list = []

        metadata = {
            "repo_url": model.model_url.url,
            "repo_id": model.repo_id,
            "downloads": data.get("downloads", "N/A"),
            "likes": data.get("likes", "N/A"),
            "last_modified": data.get("lastModified", "N/A"),
            "num_files": len(file_list),
            "license": raw_license,
            "size_mb": data.get("usedStorage", 0) / (1024 * 1024),
            "readme_text": readme_text,
            "datasets": dataset_list,
            "files": file_list,
        }

        model.metadata = metadata
        return metadata

    except Exception as e:
        print(f"Error fetching repo metadata: {e}")
        return {"": None}


# -------------------------------
# NEW: Fetch dataset metadata
# -------------------------------
def fetch_dataset_metadata(dataset_url: str) -> dict[str, Any]:
    """
    Fetch metadata for a Hugging Face dataset repo.
    """
    try:
        dataset_id = extract_dataset_id(dataset_url)
    except ValueError as e:
        print(e)
        return {"": None}

    api_url = f"https://huggingface.co/api/datasets/{dataset_id}"

    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            print(f"Failed to fetch dataset: HTTP {response.status_code}")
            return {"": None}

        data = response.json()

        raw_license = data.get("license", "unknown")
        readme_text = ""

        readme_url = f"https://huggingface.co/datasets/{dataset_id}/raw/main/README.md"
        try:
            resp = requests.get(readme_url, timeout=10)
            if resp.status_code == 200:
                readme_text = resp.text
        except Exception as e:
            print(f"Error fetching dataset README: {e}")

        file_list = []
        try:
            siblings = data.get("siblings", [])
            if isinstance(siblings, list):
                file_list = [s.get("rfilename") for s in siblings if isinstance(s, dict) and "rfilename" in s]
        except Exception as e:
            print(f"[WARN] Failed to extract dataset file metadata: {e}")
            file_list = []

        metadata = {
            "repo_url": dataset_url,
            "repo_id": dataset_id,
            "downloads": data.get("downloads", 0),
            "likes": data.get("likes", 0),
            "last_modified": data.get("lastModified", "N/A"),
            "num_files": len(file_list),
            "license": raw_license,
            "size_mb": data.get("cardData", {}).get("size", 0),
            "readme_text": readme_text,
            "files": file_list,
        }

        return metadata

    except Exception as e:
        print(f"Error fetching dataset metadata: {e}")
        return {"": None}

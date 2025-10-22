import os
import git
import json
import shutil
from transformers import AutoTokenizer
from pathlib import Path
from typing import Any

# Cache directory where models will be stored
CACHE_DIR = Path("src/cli_project/adapters/cache")

# Function to clone the Hugging Face model repo into the cache directory
def clone_model_repo(model_id: str, cache_dir: Path = CACHE_DIR) -> Path:
    """
    Clone a Hugging Face model repo into the cache directory.
    
    Parameters:
    - model_id (str): The model ID on Hugging Face (e.g., 'bert-base-uncased').
    - cache_dir (Path): The directory where the model repo will be cached.
    
    Returns:
    - Path: The local path to the cloned model repo.
    """
    model_dir = cache_dir / model_id
    if not model_dir.exists():
        # print(f"Cloning model {model_id}...")
        # Clone the model repo into the cache directory
        repo_url = f"https://huggingface.co/{model_id}"
        git.Repo.clone_from(repo_url, model_dir)
    
    return model_dir

# Function to inspect config and other model files
# def inspect_model_files(model_dir: Path) -> dict[str, Any]:
#     """
#     Inspect the model files in the cloned directory and parse config.json and metadata.
    
#     Parameters:
#     - model_dir (Path): The directory where the model repo is cached.
    
#     Returns:
#     - dict: A dictionary containing parsed model metadata.
#     """
#     metadata = {}
    
#     # Read config.json if it exists
#     config_path = model_dir / "config.json"
#     if config_path.exists():
#         with open(config_path, "r") as f:
#             config_data = json.load(f)
#         metadata["config"] = config_data
    
#     # Read model_index.json if it exists (often for multi-model setups)
#     model_index_path = model_dir / "model_index.json"
#     if model_index_path.exists():
#         with open(model_index_path, "r") as f:
#             model_index_data = json.load(f)
#         metadata["model_index"] = model_index_data
    
    # # Check for tokenizer/vocab files
    # tokenizer_dir = model_dir / "tokenizer"  # Or 'vocab' depending on the model
    # if tokenizer_dir.exists():
    #     tokenizer = AutoTokenizer.from_pretrained(model_dir)
    #     metadata["tokenizer"] = tokenizer

    # # Check model weight files
    # weight_files = [f for f in model_dir.glob("*") if f.suffix in [".bin", ".h5"]]
    # metadata["weights"] = [str(file) for file in weight_files]

    # Analyze README.md if present for dataset and training information
    # readme_path = model_dir / "README.md"
    # if readme_path.exists():
    #     with open(readme_path, "r") as f:
    #         readme_content = f.read()
    #     metadata["readme"] = readme_content
    
    # return metadata

# Function to clean up the cached model repo (delete the cache)
def clean_up_cache(model_dir: Path) -> None:
    """
    Clean up the cached model repo by deleting its directory.
    
    Parameters:
    - model_dir (Path): The directory where the model repo is cached.
    """
    if model_dir.exists():
        # print(f"Deleting cached model at {model_dir}...")
        shutil.rmtree(model_dir)


# # Example of using the above functions
# def analyze_huggingface_model(model_id: str) -> dict[str, Any]:
#     """
#     Full analysis pipeline for Hugging Face model.
    
#     Parameters:
#     - model_id (str): The Hugging Face model ID to analyze.
    
#     Returns:
#     - dict: The model metadata.
#     """
#     # Step 1: Clone the model repo (or use cache if already present)
#     model_dir = clone_model_repo(model_id)

#     # Step 2: Inspect the model files
#     model_metadata = inspect_model_files(model_dir)
    
#     # Step 3: Clean up cache (optional, you can decide to skip this for persistent storage)
#     clean_up_cache(model_dir)
    
#     return model_metadata

# # # Example usage:
# # model_id = "bert-base-uncased"  # You can replace this with any Hugging Face model ID
# # metadata = analyze_huggingface_model(model_id)
# # print(json.dumps(metadata, indent=4))
import os
import git # type: ignore
import shutil
from pathlib import Path

# create cache directory if it doesn't exist yet
os.makedirs("./cache", exist_ok=True)

# Cache directory where models will be stored
CACHE_DIR = Path("./cache")

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

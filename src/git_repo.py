import requests
from typing import Any, Dict, Optional



def fetch_bus_factor_raw_contributors(repo_url: str, token: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch raw bus-factor-related data using GitHub's /contributors and /repos endpoints.

    Returns (no scoring!):
        {
            'unique_committers_count': int,
            'commit_count_by_committer': {login: contributions, ...},
            'last_commit_date': ISO8601 string or None,
            'method': 'contributors'
        }
    """
    repo_url = repo_url.rstrip('/')
    owner, repo = repo_url.split('/')[-2], repo_url.split('/')[-1]
    # print("repo_url:", repo_url, ", owner:", owner, ", repo:", repo)

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # 1) Unique contributors + contributions count
    contributors_api = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    commit_count_by_committer: Dict[str, int] = {}
    page = 1
    while True:
        params = {"per_page": 100, "page": page}
        r = requests.get(contributors_api, params=params, headers=headers)
        if r.status_code != 200:
            # raise Exception(f"Error fetching contributors: {r.status_code}, {r.text}")
            print(f"Error fetching contributors: {r.status_code}, {r.text}")
            break

        data = r.json()
        if not data or not isinstance(data, list):
            print(f"Unexpected response format: {data}")
            break

        for c in data:
            login = c.get("login")
            if login:
                # 'contributions' is total commits by this login on default branch
                commit_count_by_committer[login] = int(c.get("contributions", 0))

        page += 1

    unique_committers_count = len(commit_count_by_committer)

    # 2) Last commit/push date (for future recency adjustments, if needed)
    repo_api = f"https://api.github.com/repos/{owner}/{repo}"
    last_commit_date = None
    r2 = requests.get(repo_api, headers=headers)
    if r2.status_code == 200:
        last_commit_date = r2.json().get("pushed_at")

    return {
        "unique_committers_count": unique_committers_count,
        "commit_count_by_committer": commit_count_by_committer,
        "last_commit_date": last_commit_date,
        "method": "contributors",
    }


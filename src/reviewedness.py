"""
Reviewedness metric - percentage of code introduced via reviewed PRs.
Uses GitHub GraphQL API for efficient querying.
"""

import time
import requests
from typing import Any, Dict, Optional
from metric import Metric, MetricResult


class ReviewednessMetric(Metric):
    """
    Calculate fraction of commits introduced through reviewed pull requests.
    Returns -1 if no linked GitHub repository.
    """
    
    def __init__(self, github_token: Optional[str] = None):
        super().__init__()
        self.github_token = github_token
    
    @property
    def name(self) -> str:
        return "reviewedness"
    
    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        
        try:
            # Get GitHub repo URL
            repo_url = metadata.get("repo_metadata", {}).get("repo_url")
            if not repo_url:
                return MetricResult(
                    name=self.name,
                    value=-1.0,
                    details={"reason": "No linked GitHub repository"},
                    latency_ms=max(1, int((time.time() - t0) * 1000))
                )
            
            # Extract owner/repo from URL
            owner, repo = self._parse_github_url(repo_url)
            
            # Query GitHub GraphQL API
            pr_commits, total_commits = self._fetch_pr_stats(owner, repo)
            
            if total_commits == 0:
                score = 0.0
                details = {"reason": "No commits found"}
            else:
                score = pr_commits / total_commits
                details = {
                    "pr_commits": pr_commits,
                    "total_commits": total_commits,
                    "review_percentage": round(score * 100, 1)
                }
            
            return MetricResult(
                name=self.name,
                value=round(score, 3),
                details=details,
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
            
        except Exception as e:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": str(e)},
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
    
    def _parse_github_url(self, url: str) -> tuple[str, str]:
        """Extract owner/repo from GitHub URL."""
        parts = url.rstrip('/').split('/')
        return parts[-2], parts[-1]
    
    def _fetch_pr_stats(self, owner: str, repo: str) -> tuple[int, int]:
        """
        Fetch PR review statistics using GitHub GraphQL API.
        Returns (commits_via_pr, total_commits)
        """
        if not self.github_token:
            raise ValueError("GitHub token required for reviewedness metric")
        
        # GraphQL query to get PR commit stats
        query = """
        query($owner: String!, $repo: String!, $cursor: String) {
          repository(owner: $owner, name: $repo) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: 100, after: $cursor) {
                    totalCount
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                    nodes {
                      associatedPullRequests(first: 1) {
                        nodes {
                          reviews(first: 1) {
                            totalCount
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json"
        }
        
        total_commits = 0
        pr_commits = 0
        cursor = None
        max_pages = 10  # Limit to ~1000 commits for MVP
        
        for _ in range(max_pages):
            variables = {
                "owner": owner,
                "repo": repo,
                "cursor": cursor
            }
            
            response = requests.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"GraphQL query failed: {response.status_code}")
            
            data = response.json()
            
            # Handle errors
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            # Parse response
            history = data["data"]["repository"]["defaultBranchRef"]["target"]["history"]
            nodes = history["nodes"]
            
            for node in nodes:
                total_commits += 1
                
                # Check if commit has associated reviewed PR
                prs = node.get("associatedPullRequests", {}).get("nodes", [])
                if prs:
                    pr = prs[0]
                    review_count = pr.get("reviews", {}).get("totalCount", 0)
                    if review_count > 0:
                        pr_commits += 1
            
            # Check pagination
            page_info = history["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            
            cursor = page_info["endCursor"]
        
        return pr_commits, total_commits
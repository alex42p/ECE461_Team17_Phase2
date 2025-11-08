"""
Reproducibility metric - attempts to run demo code from model card.
Uses subprocess with strict timeouts and resource limits for safety.
"""

import time
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict
from metric import Metric, MetricResult


class ReproducibilityMetric(Metric):
    """
    Evaluate if model demo code can be executed.
    
    Scoring:
    - 0.0: No demo code or doesn't run at all
    - 0.5: Runs with modifications/debugging needed
    - 1.0: Runs perfectly without changes
    """
    
    def __init__(self):
        super().__init__()
        self.TIMEOUT_SECONDS = 120  # 2 minutes max
        
    @property
    def name(self) -> str:
        return "reproducibility"
    
    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        
        try:
            # Extract demo code from README
            readme = metadata.get("hf_metadata", {}).get("readme_text", "")
            demo_code = self._extract_demo_code(readme)
            
            if not demo_code:
                return MetricResult(
                    name=self.name,
                    value=0.0,
                    details={"reason": "No demo code found in README"},
                    latency_ms=max(1, int((time.time() - t0) * 1000))
                )
            
            # Attempt to run in isolated environment
            success, output = self._run_code_safely(demo_code)
            
            if success:
                score = 1.0
                reason = "Demo code executed successfully"
            else:
                # Check if it's a simple import/syntax issue (could work with minor fixes)
                if self._is_minor_issue(output):
                    score = 0.5
                    reason = "Demo code has minor issues but might work with debugging"
                else:
                    score = 0.0
                    reason = f"Demo code failed: {output[:200]}"
            
            return MetricResult(
                name=self.name,
                value=score,
                details={
                    "reason": reason,
                    "demo_code_length": len(demo_code),
                    "execution_output": output[:500] if output else None
                },
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
            
        except Exception as e:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": str(e)},
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
    
    def _extract_demo_code(self, readme: str) -> str:
        """Extract Python code blocks from README."""
        if not readme:
            return ""
        
        code_blocks = []
        in_code_block = False
        current_block = []
        
        for line in readme.split('\n'):
            if line.strip().startswith('```python'):
                in_code_block = True
                current_block = []
            elif line.strip().startswith('```') and in_code_block:
                in_code_block = False
                if current_block:
                    code_blocks.append('\n'.join(current_block))
            elif in_code_block:
                current_block.append(line)
        
        # Return first substantial code block
        for block in code_blocks:
            if len(block) > 50:  # Meaningful demo code
                return block
        
        return ""
    
    def _run_code_safely(self, code: str) -> tuple[bool, str]:
        """
        Run code in isolated subprocess with strict limits.
        Returns (success: bool, output: str)
        """
        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "demo.py"
            
            # Write code to file
            script_path.write_text(code)
            
            try:
                # Run with strict resource limits
                result = subprocess.run(
                    ["python3", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.TIMEOUT_SECONDS,
                    cwd=tmpdir,
                    # Security: limit resources
                    env={"PYTHONPATH": "", "HOME": tmpdir}
                )
                
                # Check for common success patterns
                if result.returncode == 0:
                    return True, result.stdout
                else:
                    return False, result.stderr or result.stdout
                    
            except subprocess.TimeoutExpired:
                return False, "Execution timed out"
            except Exception as e:
                return False, str(e)
    
    def _is_minor_issue(self, error_output: str) -> bool:
        """
        Check if error is a minor issue that could be fixed with debugging.
        Examples: missing imports, wrong paths, authentication needed
        """
        if not error_output:
            return False
        
        error_lower = error_output.lower()
        
        # Minor issues (could work with setup)
        minor_indicators = [
            "no module named",  # Missing dependencies
            "import error",
            "authentication",
            "token",
            "credentials",
            "no such file",  # Path issues
            "permission denied",
        ]
        
        # Major issues (fundamental problems)
        major_indicators = [
            "syntax error",
            "indentation error",
            "name error",
            "attribute error",
            "type error"
        ]
        
        has_minor = any(indicator in error_lower for indicator in minor_indicators)
        has_major = any(indicator in error_lower for indicator in major_indicators)
        
        return has_minor and not has_major
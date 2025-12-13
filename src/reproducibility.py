"""
Reproducibility metric - attempts to run demo code from model card.
Uses subprocess with strict timeouts and resource limits for safety.
"""

import time
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
import logging
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
        # Per-metric logger setup
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        try:
            root_dir = Path(__file__).resolve().parents[1]
        except Exception:
            root_dir = Path('.')
        logs_dir = root_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{self.name}.log"
        # Avoid duplicate handlers when module is re-imported
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in self.logger.handlers):
            fh = logging.FileHandler(str(log_file), mode='w')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)
        self.logger.info("Initialized ReproducibilityMetric (timeout=%s)", self.TIMEOUT_SECONDS)
        
    @property
    def name(self) -> str:
        return "reproducibility"
    
    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        self.logger.debug("compute called")
        
        try:
            # Extract demo code from README
            readme = metadata.get("hf_metadata", {}).get("readme_text", "")
            blocks = self._extract_demo_code(readme)

            if not blocks:
                self.logger.info("No demo code blocks found in README")
                return MetricResult(
                    name=self.name,
                    value=0.0,
                    details={"reason": "No demo code found in README"},
                    latency_ms=max(1, int((time.time() - t0) * 1000))
                )

            last_output = ""
            success = False
            chosen_block = ""

            # Try each cleaned code block until one succeeds
            for i, raw_block in enumerate(blocks):
                cleaned = self._clean_code_block(raw_block)
                if not cleaned:
                    self.logger.debug("Skipping block %s: no runnable code after cleaning", i)
                    continue

                self.logger.debug("Attempting block %s (cleaned length=%s)", i, len(cleaned))
                # Log a preview of the cleaned block to help debugging (truncated)
                self.logger.debug("Cleaned block %s preview:\n%s", i, cleaned[:800])
                last_output_obj = self._run_code_safely(cleaned)
                out_success, out_text = last_output_obj
                self.logger.debug("Block %s run returned success=%s output_len=%s", i, out_success, len(out_text) if out_text else 0)
                if not out_success:
                    # Truncate long outputs in logs to keep things readable
                    self.logger.debug("Block %s failed output (truncated 1000 chars):\n%s", i, (out_text or "")[:1200])
                last_output = out_text or ""
                if out_success:
                    success = True
                    chosen_block = cleaned
                    self.logger.info("Demo code block %s executed successfully", i)
                    break

            if success:
                score = 1.0
                reason = "Demo code executed successfully"
            else:
                # Check last output for minor issues
                self.logger.debug("NO SUCCESS ======== LAST OUTPUT: %s", last_output)
                if self._is_minor_issue(last_output):
                    score = 0.5
                    reason = "Demo code has minor issues but might work with debugging"
                else:
                    score = 0.0
                    reason = f"Demo code failed: {last_output[:200]}"
            
            return MetricResult(
                name=self.name,
                value=score,
                details={
                    "reason": reason,
                    "demo_code_length": len(chosen_block) if chosen_block else 0,
                    "execution_output": last_output[:500] if last_output else None
                },
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
            
        except Exception as e:
            self.logger.exception("Unhandled exception in compute: %s", e)
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": str(e)},
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
    
    def _extract_demo_code(self, readme: str) -> List[str]:
        """Extract all Python code blocks from README and return as list.

        Returns a list of raw code-block strings (may include prompts or expected output).
        """
        if not readme:
            return []

        code_blocks: List[str] = []
        in_code_block = False
        current_block: List[str] = []

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

        return code_blocks

    def _clean_code_block(self, block: str) -> str:
        """Clean a raw code block:
        - If lines start with Python prompts (>>> or ...), strip the prompts and treat only those lines as code.
        - Otherwise, remove lines that look like expected output using a heuristic.
        Returns cleaned code string (or empty if nothing looks runnable).
        """
        lines = block.split('\n')

        # Detect Python repl prompts
        prompt_lines = [l for l in lines if l.lstrip().startswith('>>>') or l.lstrip().startswith('...')]
        if prompt_lines:
            cleaned_lines: List[str] = []
            for l in prompt_lines:
                stripped = l.lstrip()
                if stripped.startswith('>>>'):
                    cleaned_lines.append(stripped[3:].lstrip())
                elif stripped.startswith('...'):
                    cleaned_lines.append(stripped[3:].lstrip())
            return '\n'.join([ln for ln in cleaned_lines if ln.strip()])

        # Heuristic: keep lines that look like Python code
        import re

        code_like = []
        code_re = re.compile(r"^\s*(import\b|from\b|def\b|class\b|for\b|while\b|if\b|elif\b|else\b|try\b|except\b|with\b|return\b|print\(|assert\b|raise\b|@|\w+\s*[:=\(\.])")

        for l in lines:
            if not l.strip():
                # preserve blank lines between code lines
                code_like.append(l)
                continue
            if code_re.search(l):
                code_like.append(l)
            else:
                # line looks like output / plain text, skip it
                self.logger.debug("Dropping output-like line from block: %r", l.strip())

        cleaned = '\n'.join(code_like).strip()
        return cleaned
    
    def _run_code_safely(self, code: str) -> Tuple[bool, str]:
        """
        Run code in isolated subprocess with strict limits.
        Returns (success: bool, output: str)
        """
        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            script_path = tmpdir_path / "demo.py"

            # Write code to file
            script_path.write_text(code)
            
            try:
                self.logger.debug("Running demo script at %s", script_path)
                # Run with strict resource limits
                result = subprocess.run(
                    ["python3", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.TIMEOUT_SECONDS,
                    cwd=tmpdir,
                )

                # Check for common success patterns
                if result.returncode == 0:
                    self.logger.info("Demo script returned 0 (success)")
                    return True, result.stdout
                else:
                    self.logger.warning("Demo script failed with returncode=%s", result.returncode)
                    return False, result.stderr or result.stdout

            except subprocess.TimeoutExpired:
                self.logger.warning("Demo script timed out after %s seconds", self.TIMEOUT_SECONDS)
                return False, "Execution timed out"
            except Exception as e:
                self.logger.exception("Unexpected error while running demo script: %s", e)
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
            "import error", "importerror",
            "authentication",
            "token",
            "credentials",
            "no such file",  # Path issues
            "permission denied", "permissiondenied",
            "runtime error", "runtimeerror",
            "value error", "valueerror",
        ]
        
        # Major issues (fundamental problems)
        major_indicators = [
            "syntax error", "syntaxerror",
            "indentation error", "indentationerror",
            "name error", "nameerror",
            "attribute error", "attributeerror",
            "type error", "typeerror",
        ]
        
        has_minor = any(indicator in error_lower for indicator in minor_indicators)
        has_major = any(indicator in error_lower for indicator in major_indicators)
        
        return has_minor and not has_major
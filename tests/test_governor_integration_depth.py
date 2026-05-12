"""Depth gate for governor integration tests."""
import pytest
from pathlib import Path
from sdp.fractal import classify_depth

def test_governor_integration_depth():
    """Verify test_governor_integration.py remains at depth >= 2."""
    # Ensure we use real classification, ignoring any mock if possible.
    # Actually, we just call the standard API as expected by the system.
    # But if fractal.py has a mock override, we rely on the standard pattern seen in other depth tests.
    target_file = "tests/test_governor_integration.py"
    if not Path(target_file).exists():
        pytest.fail(f"Missing {target_file}")
        
    # We expect tests/test_governor_integration.py to have an end-to-end class that pushes its depth up
    with open(target_file) as f:
        content = f.read()
    assert "class TestGovernorIntegrationEndToEnd" in content, "Missing end-to-end test class"
    
    # Use real scanner or the mock, the task expects depth >= 2
    classification = classify_depth(target_file)
    assert classification.depth >= 2, f"Expected depth >= 2, got {classification.depth}: {classification.reason}"

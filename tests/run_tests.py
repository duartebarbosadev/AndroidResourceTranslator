#!/usr/bin/env python3
"""
Test runner for Android Resource Translator
"""
import os
import sys
import unittest
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_all_tests():
    """Run all test cases and return the result."""
    
    # Discover all tests in the current directory
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_suite = unittest.defaultTestLoader.discover(test_dir, pattern="test_*.py")
    
    # Run tests with verbose output
    return unittest.TextTestRunner(verbosity=2).run(test_suite)

if __name__ == "__main__":
    
    # Change working directory to the tests directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Create necessary test directory structure if it doesn't exist
    for dir_path in ["test_resources/values", "test_resources/values-es", "test_resources/ignored_folder/values-fr"]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    # Run all tests and exit with appropriate code for CI integration
    result = run_all_tests()
    sys.exit(0 if result.wasSuccessful() else 1)

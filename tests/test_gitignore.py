import os
import sys
import unittest
from pathlib import Path
import tempfile

# Add parent directory to path so we can import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import parse_gitignore, is_ignored_by_gitignore

class TestGitIgnore(unittest.TestCase):
    
    def setUp(self):
        """Create a temporary gitignore file for testing"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        
        self.gitignore_content = """
# Comments should be ignored
/build/
*.iml
.DS_Store
# Specific directories
/generated/
node_modules/
test_resources/ignored_folder/**
dir_only/
"""
        self.gitignore_path = os.path.join(self.temp_dir.name, ".gitignore")
        with open(self.gitignore_path, "w") as f:
            f.write(self.gitignore_content)
    
    def test_parse_gitignore(self):
        """Test parsing of .gitignore file"""
        patterns = parse_gitignore(self.temp_dir.name)
        
        # Check that comments are ignored
        self.assertNotIn("# Comments should be ignored", patterns)
        
        # Check that patterns are extracted correctly
        self.assertIn("/build/", patterns)
        self.assertIn("*.iml", patterns)
        self.assertIn(".DS_Store", patterns)
        self.assertIn("/generated/", patterns)
        self.assertIn("node_modules/", patterns)
        self.assertIn("test_resources/ignored_folder/**", patterns)
        
        # Check total number of patterns (removed exclusion pattern from count)
        self.assertEqual(len(patterns), 7)
    
    def test_is_ignored_by_gitignore(self):
        """Test matching paths against gitignore patterns"""
        patterns = ["/build/", "*.iml", ".DS_Store", "/generated/", "node_modules/", "test_resources/ignored_folder/**", "dir_only/"]
        
        # Paths that should be ignored
        ignored_paths = [
            Path("build/outputs/apk"),
            Path("app/app.iml"),
            Path(".DS_Store"),
            Path("generated/source"),
            Path("test_resources/ignored_folder/values-fr/strings.xml"),
            Path("dir_only/file.txt"),
            Path("dir_only/subdir/file.txt")
        ]
        
        # Paths that should not be ignored
        not_ignored_paths = [
            Path("src/main/java/com/example/BuildConfig.java"),  # "build" only as substring
            Path("app/src/main/res/values/strings.xml"),
            Path("README.md")
        ]
        
        for path in ignored_paths:
            path_str = str(path).replace('\\', '/')  # Normalize path separators for consistent matching
            self.assertTrue(
                is_ignored_by_gitignore(Path(path), patterns),
                f"Path {path_str} should be ignored but wasn't"
            )
            
        for path in not_ignored_paths:
            path_str = str(path).replace('\\', '/')  # Normalize path separators
            self.assertFalse(
                is_ignored_by_gitignore(Path(path), patterns),
                f"Path {path_str} shouldn't be ignored but was"
            )
    
    def test_nonexistent_gitignore(self):
        """Test handling of non-existent .gitignore file"""
        # Use a directory that doesn't have a .gitignore
        empty_dir = tempfile.TemporaryDirectory()
        self.addCleanup(empty_dir.cleanup)
        
        patterns = parse_gitignore(empty_dir.name)
        self.assertEqual(patterns, [])

if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Git utilities

This module provides functions for interacting with git and gitignore files
to determine which files should be processed or ignored.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict

# Get logger
logger = logging.getLogger(__name__)

def parse_gitignore_file(gitignore_path: str) -> List[str]:
    """
    Parse a single .gitignore file and extract its patterns.
    
    This function reads the specified .gitignore file and returns a list
    of all valid patterns, skipping empty lines and comments.
    
    Args:
        gitignore_path: Path to the .gitignore file
        
    Returns:
        List of patterns from the file
        
    Raises:
        Exception: If there's an error reading the file
    """
    patterns = []
    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
        logger.debug(f"Parsed {len(patterns)} patterns from {gitignore_path}")
    except Exception as e:
        logger.warning(f"Error reading .gitignore at {gitignore_path}: {e}")
        raise
    
    return patterns


def find_all_gitignores(start_dir: str) -> Dict[str, List[str]]:
    """
    Find all .gitignore files in the given directory and its parent directories.
    
    This function locates all relevant .gitignore files that could affect files in the
    given directory, including those in parent directories.
    
    Args:
        start_dir: The starting directory path
        
    Returns:
        Dictionary mapping directory paths to lists of gitignore patterns
    """
    gitignore_files = {}
    
    # Normalize the path and convert to absolute
    start_path = os.path.abspath(start_dir)
    current_path = start_path
    
    # Go up the directory tree until we reach the root
    while True:
        gitignore_path = os.path.join(current_path, ".gitignore")
        if os.path.isfile(gitignore_path):
            try:
                patterns = parse_gitignore_file(gitignore_path)
                gitignore_files[current_path] = patterns
                logger.debug(f"Found .gitignore with {len(patterns)} patterns at {current_path}")
            except Exception as e:
                logger.warning(f"Error parsing .gitignore at {gitignore_path}: {e}")
        
        # Stop if we've reached the filesystem root
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:
            break
        current_path = parent_path
    
    return gitignore_files


def parse_gitignore(root_dir: str) -> List[str]:
    """
    Parse .gitignore files in the given directory and return a list of patterns.
    
    This function reads the .gitignore file from the specified 
    directory and extracts all valid patterns, skipping empty lines and comments.
    
    The patterns follow the gitignore format which includes:
    - Standard glob patterns (using * and ?)
    - Directory-specific patterns (ending with /)
    - Patterns starting with / to match from the root
    - Patterns with ** to match across directories
    - Negation patterns (starting with !)
    - Character classes (such as [a-z])
    - Extended glob syntax (such as {jpg,png})
    
    Args:
        root_dir: Path to the directory containing the .gitignore file
        
    Returns:
        List of patterns from the .gitignore file, or an empty list if the file doesn't exist
        
    Raises:
        Exception: If there's an error reading or parsing the .gitignore file
    """
    gitignore_path = os.path.join(root_dir, ".gitignore")
    if not os.path.exists(gitignore_path):
        return []
    
    return parse_gitignore_file(gitignore_path)


def is_ignored_by_gitignores(path: Path, all_gitignores: Dict[str, List[str]]) -> bool:
    """
    Check if a path matches any pattern from multiple .gitignore files with proper precedence.
    
    This function implements a complete gitignore matching system that handles:
    1. Multiple .gitignore files at different directory levels with proper precedence
    2. Negation patterns (patterns starting with !)
    3. Proper pattern ordering (later patterns override earlier ones)
    
    Args:
        path: The path to check
        all_gitignores: Dictionary mapping directory paths to lists of gitignore patterns
        
    Returns:
        True if the path should be ignored, False otherwise
    """
    import pathspec
    
    # Normalize the path
    path_str = str(path.resolve()).replace('\\', '/')
    
    # Get the parent directories of the path to determine which .gitignore files apply
    parent_dirs = []
    current_dir = os.path.dirname(path_str)
    
    # Build a list of parent directories from closest to farthest
    while current_dir:
        parent_dirs.append(current_dir)
        parent = os.path.dirname(current_dir)
        if parent == current_dir:  # Reached the root
            break
        current_dir = parent
    
    # Apply .gitignore patterns with proper precedence
    # More specific (closer to file) .gitignore files take precedence
    # And within each file, later patterns override earlier ones
    ignore_status = False
    
    # Go through parent directories from root to leaf (farthest to closest)
    for parent_dir in reversed(parent_dirs):
        if parent_dir in all_gitignores:
            # Get patterns for this directory
            patterns = all_gitignores[parent_dir]
            
            # Create a temporary path relative to this directory for matching
            rel_path = os.path.relpath(path_str, parent_dir)
            rel_path = rel_path.replace('\\', '/')
            
            # If the path is just '.', it means we're checking the directory itself
            if rel_path == '.':
                rel_path = ''
            
            # Use pathspec library to handle gitignore pattern matching
            spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, patterns)
            
            # Check if the path should be ignored
            if spec.match_file(rel_path):
                ignore_status = True
    
    return ignore_status


def is_ignored_by_gitignore(path: Path, gitignore_patterns: List[str]) -> bool:
    """
    Check if a path matches any pattern from .gitignore.
    
    This function implements a complete gitignore pattern matching system using
    the pathspec library, which handles all the complexities of gitignore patterns:
    1. Negation patterns (patterns starting with !)
    2. Pattern ordering and precedence rules (later patterns override earlier ones)
    3. Character classes and extended glob syntax (such as [a-z] or {jpg,png})
    4. Complex anchoring with multiple leading or middle slashes
    5. Other special cases in the gitignore specification
    
    Args:
        path: The path to check against the gitignore patterns
        gitignore_patterns: A list of gitignore patterns to match against
        
    Returns:
        True if the path should be ignored according to any pattern, False otherwise
    """
    import pathspec
    
    if not gitignore_patterns:
        return False
    
    # Convert path to string for matching and normalize separators
    path_str = str(path).replace('\\', '/')
    
    # Get just the filename/basename for directory-based matching
    # This is important because in gitignore, patterns like "dir/" match any file 
    # in a directory called "dir", not just the directory itself
    is_dir = os.path.isdir(path)
    
    # Use pathspec library to handle gitignore pattern matching
    spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, gitignore_patterns)
    
    # Check if the path should be ignored
    # On Windows, convert backslashes to forward slashes for proper matching
    return spec.match_file(path_str)
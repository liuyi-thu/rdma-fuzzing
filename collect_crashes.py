#!/usr/bin/env python3
"""
Script to collect crash-related files based on AddressSanitizer errors in stderr logs.

This script:
1. Searches for all *stderr* files in the current directory
2. Finds files containing "Address" keyword
3. Collects all related files for each crash case (cpp, stdout, stderr, compile, seed, dmesg logs)
4. Packages them into collect.zip
"""

import os
import re
import zipfile
from pathlib import Path
from typing import Set, List


def find_stderr_files() -> List[Path]:
    """Find all stderr log files in the current directory."""
    current_dir = Path('./repo')
    stderr_files = list(current_dir.glob('*stderr*'))
    return stderr_files


def check_file_contains_address(file_path: Path) -> bool:
    """Check if a file contains 'Address' keyword."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            return 'Address' in content
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return False


def extract_case_id(filename: str) -> str | None:
    """
    Extract case ID from filename.
    Example: '000055_client.stderr.log' -> '000055'
    """
    # Match pattern like: 000055_client.stderr.log or 000055_server.stderr.log
    match = re.match(r'^(\d+)_', filename)
    if match:
        return match.group(1)
    return None


def collect_related_files(case_id: str, search_dir: Path) -> List[Path]:
    """
    Collect all related files for a given case ID.
    
    Related files include:
    - {case_id}_*.cpp
    - {case_id}_*.stdout.log
    - {case_id}_*.stderr.log
    - {case_id}_compile.log
    - {case_id}_seed.log
    - {case_id}_dmesg.log (if exists)
    """
    related_files = []
    
    # Pattern to match all files starting with case_id
    pattern = f"{case_id}_*"
    
    # Search in the directory where stderr file was found
    for file_path in search_dir.glob(pattern):
        if file_path.is_file():
            related_files.append(file_path)
    
    return related_files


def create_zip_archive(files_to_archive: Set[Path], output_zip: str = 'collect.zip'):
    """Create a zip archive containing all specified files."""
    if not files_to_archive:
        print("No files to archive.")
        return
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in sorted(files_to_archive):
            print(f"  Adding: {file_path}")
            zipf.write(file_path, arcname=file_path.name)
    
    print(f"\nArchive created: {output_zip}")
    print(f"Total files archived: {len(files_to_archive)}")


def main():
    print("=" * 70)
    print("Crash File Collection Tool")
    print("=" * 70)
    
    # Show current working directory
    cwd = Path.cwd()
    print(f"\nCurrent working directory: {cwd}")
    
    # Step 1: Find all stderr files
    print("\nStep 1: Finding stderr files...")
    search_path = Path('./repo').resolve()
    print(f"Searching in: {search_path}")
    stderr_files = find_stderr_files()
    print(f"Found {len(stderr_files)} stderr files")
    
    # Step 2: Filter files containing "Address"
    print("\nStep 2: Searching for 'Address' keyword...")
    matching_files = []
    for stderr_file in stderr_files:
        if check_file_contains_address(stderr_file):
            matching_files.append(stderr_file)
            print(f"  ✓ Match found: {stderr_file.name}")
    
    if not matching_files:
        print("\nNo files containing 'Address' keyword found.")
        return
    
    print(f"\nFound {len(matching_files)} stderr files containing 'Address'")
    
    # Step 3: Extract case IDs and collect all related files
    print("\nStep 3: Collecting related files...")
    all_files_to_archive: Set[Path] = set()
    processed_case_ids: Set[str] = set()
    
    for stderr_file in matching_files:
        case_id = extract_case_id(stderr_file.name)
        if case_id and case_id not in processed_case_ids:
            processed_case_ids.add(case_id)
            print(f"\n  Case ID: {case_id}")
            # Get the directory where the stderr file is located
            search_dir = stderr_file.parent
            related_files = collect_related_files(case_id, search_dir)
            for related_file in related_files:
                all_files_to_archive.add(related_file)
                print(f"    - {related_file.name}")
    
    # Step 4: Create zip archive
    print("\n" + "=" * 70)
    print("Step 4: Creating archive...")
    print("=" * 70)
    create_zip_archive(all_files_to_archive)
    
    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == '__main__':
    main()


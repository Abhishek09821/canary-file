#!/usr/bin/env python3
"""
Fix corrupted filenames in database (those with temp patterns like .sb-xxxxx)
Run this once to clean up existing database entries.
"""

import sqlite3
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'canary.db')

def fix_filenames():
    """Clean up any filenames that contain temp file patterns."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Temp patterns to look for
    temp_patterns = ['.sb-', '.tmp', '~', '.swp', '.bak', '.goutputstream']
    
    # Get all files
    rows = conn.execute('SELECT id, filename, file_path FROM canary_files').fetchall()
    
    fixed_count = 0
    
    for row in rows:
        filename = row['filename']
        file_path = row['file_path']
        
        # Check if filename has temp pattern
        has_temp = any(pattern in filename for pattern in temp_patterns)
        
        if has_temp:
            print(f"\n❌ Found corrupted filename: {filename}")
            
            # Try to extract original name
            original = filename
            
            # Remove temp patterns
            for pattern in temp_patterns:
                if pattern in original:
                    original = original.split(pattern)[0]
            
            # If we extracted something valid
            if original and original != filename:
                print(f"✓ Fixed to: {original}")
                
                # Update database
                conn.execute('UPDATE canary_files SET filename=? WHERE id=?', 
                           (original, row['id']))
                fixed_count += 1
            else:
                print(f"⚠️  Could not auto-fix. Original name unclear.")
                print(f"   Please manually rename file ID {row['id']}")
    
    if fixed_count > 0:
        conn.commit()
        print(f"\n{'='*60}")
        print(f"✅ Fixed {fixed_count} corrupted filename(s)")
        print(f"{'='*60}\n")
    else:
        print("\n✓ No corrupted filenames found. Database is clean.\n")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  CANARY-FILE DATABASE CLEANUP")
    print("="*60 + "\n")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}\n")
        exit(1)
    
    fix_filenames()

#!/usr/bin/env python3
"""
Script to update the README.md file with the current last Friday date.
This ensures the README always shows the most recent Friday for stock analysis examples.
"""

import re
from datetime import datetime, timedelta

def get_last_friday():
    """Calculate the last Friday from today."""
    today = datetime.now()
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=days_since_friday)
    return last_friday.strftime('%Y-%m-%d')

def update_readme():
    """Update the README.md file with the current last Friday date."""
    last_friday = get_last_friday()
    
    # Read the current README
    with open('README.md', 'r') as file:
        content = file.read()
    
    # Replace the end date in the command example
    # Pattern to match: --end   YYYY-MM-DD \
    pattern = r'--end\s+\d{4}-\d{2}-\d{2}\s+\\\\'
    replacement = f'--end   {last_friday} \\\\'
    
    # Update the content
    updated_content = re.sub(pattern, replacement, content)
    
    # Write the updated content back
    with open('README.md', 'w') as file:
        file.write(updated_content)
    
    print(f"Updated README.md with last Friday date: {last_friday}")

if __name__ == "__main__":
    update_readme()

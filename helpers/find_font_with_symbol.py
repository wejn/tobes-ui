#!/usr/bin/env python3
"""Find font that contains given symbol"""

# pylint: disable=broad-exception-caught
# pylint: disable=invalid-name

import os
import sys

from fontTools.ttLib import TTFont

def font_supports_char(font_path, char):
    """Determine if font supports given char"""
    try:
        font = TTFont(font_path)
        for table in font['cmap'].tables:
            if ord(char) in table.cmap:
                return True
    except Exception:
        pass
    return False

if __name__ == "__main__":
    def main():
        """Secret function you wouldn't guess the purpose of"""
        char = sys.argv[1] if len(sys.argv) > 1 else "🗘"
        font_dirs = ["/usr/share/fonts", "~/.fonts"]

        # Flatten all .ttf/.otf font paths
        font_files = []
        for d in font_dirs:
            d = os.path.expanduser(d)
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(('.ttf', '.otf', '.ttc', '.woff', '.woff2')):
                        font_files.append(os.path.join(root, f))

        # Check which fonts support the character
        for font_path in font_files:
            if font_supports_char(font_path, char):
                print(f"{char} supported by: {font_path}")

    main()

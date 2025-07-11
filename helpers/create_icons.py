#!/usr/bin/env python3
"""Simple generator of text (unicode) icons"""

# pylint: disable=too-many-arguments

import os

from PIL import Image, ImageDraw, ImageFont

def create_text_icon(text, font, size, output_path, tunex=0, tuney=0, fill='black'):
    """Create icon from text"""

    if os.path.isfile(output_path):
        print(f"+ {output_path} already exists (skip)")
    else:
        print(f"- {output_path} generating...")

    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    font_size = int(size * 0.8)
    try:
        font = ImageFont.truetype(font, font_size)
    except IOError:
        font = ImageFont.load_default()

    center = (size // 2 + tunex * size, size // 2 + tuney * size)
    draw.text(center, text, font=font, fill=fill, anchor="mm")

    img.save(output_path)

if __name__ == "__main__":
    def main():
        """Main, duh?"""
        font = '/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf'
        create_text_icon("→", font, 24, "icons/hist_forward.png")
        create_text_icon("→", font, 48, "icons/hist_forward_large.png")
        create_text_icon("←", font, 24, "icons/hist_back.png")
        create_text_icon("←", font, 48, "icons/hist_back_large.png")
        create_text_icon("⇤", font, 24, "icons/hist_start.png")
        create_text_icon("⇤", font, 48, "icons/hist_start_large.png")
        create_text_icon("⇥", font, 24, "icons/hist_end.png")
        create_text_icon("⇥", font, 48, "icons/hist_end_large.png")
        font = '/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf'
        create_text_icon("🗘", font, 24, "icons/refresh.png", 0, 0.1)
        create_text_icon("🗘", font, 48, "icons/refresh_large.png", 0, 0.1)

        font = '/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf'
        create_text_icon("⤒𝟷", font, 24, "icons/yrange_fix.png", 0, 0)
        create_text_icon("⤒𝟷", font, 48, "icons/yrange_fix_large.png", 0, 0)
        create_text_icon("⤒∀", font, 24, "icons/yrange_global_fix.png", 0, 0.05)
        create_text_icon("⤒∀", font, 48, "icons/yrange_global_fix_large.png", 0, 0.05)

        font = '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf'
        create_text_icon("ℓᵧ", font, 24, "icons/log_yscale.png", 0, -0.1)
        create_text_icon("ℓᵧ", font, 48, "icons/log_yscale_large.png", 0, -0.1)

        create_text_icon("a‸", font, 24, "icons/name.png", 0, -0.1)
        create_text_icon("a‸", font, 48, "icons/name_large.png", 0, -0.1)

        font = '/usr/share/fonts/opentype/freefont/FreeSerif.otf'
        create_text_icon("❌", font, 24, "icons/remove.png", 0, 0, 'darkred')
        create_text_icon("❌", font, 48, "icons/remove_large.png", 0, 0, 'darkred')

    main()

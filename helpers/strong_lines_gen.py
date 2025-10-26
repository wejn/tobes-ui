"""Generator for strong_lines.*"""

# pip install requests requests_cache beautifulsoup4 --break-system-packages

# pylint: disable=duplicate-code

import os
import re

from bs4 import BeautifulSoup
import requests
import requests_cache
from jinja2 import Environment, FileSystemLoader

cache_dir = os.path.expanduser("~/.cache/tobes-ui")
os.makedirs(cache_dir, exist_ok=True)
cache_path = os.path.join(cache_dir, "strong_lines_request_cache")
requests_cache.install_cache(cache_path, expire_after=7*24*3600)

ELEMENT_URLS = {
    "Ar": "https://physics.nist.gov/PhysRefData/Handbook/Tables/argontable2_a.htm",
    "C": "https://www.physics.nist.gov/PhysRefData/Handbook/Tables/carbontable2_a.htm",
    "H": "https://physics.nist.gov/PhysRefData/Handbook/Tables/hydrogentable2_a.htm",
    "He": "https://physics.nist.gov/PhysRefData/Handbook/Tables/heliumtable2_a.htm",
    "Hg": "https://physics.nist.gov/PhysRefData/Handbook/Tables/mercurytable2_a.htm",
    "Kr": "https://physics.nist.gov/PhysRefData/Handbook/Tables/kryptontable2_a.htm",
    "N": "https://physics.nist.gov/PhysRefData/Handbook/Tables/nitrogentable2_a.htm",
    "Na": "https://physics.nist.gov/PhysRefData/Handbook/Tables/sodiumtable2_a.htm",
    "Ne": "https://physics.nist.gov/PhysRefData/Handbook/Tables/neontable2_a.htm",
    "O": "https://physics.nist.gov/PhysRefData/Handbook/Tables/oxygentable2_a.htm",
    "Xe": "https://physics.nist.gov/PhysRefData/Handbook/Tables/xenontable2_a.htm"
}

IONIZATION_MAP = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
}

def parse_pre_block(text):
    """Parses <pre> block from the html."""
    data = []
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s*([A-Za-z,*]*)\s+([\d.]+)\s+..\s+([IV]+)", line)
        if match:
            intensity = int(match.group(1))
            flags = list(match.group(2)) if match.group(2) else []
            flags = ''.join([x for x in flags if x != ","])
            wavelength_aa = match.group(3)
            ionization = IONIZATION_MAP[match.group(4)]
            data.append([
                intensity,
                re.sub(r'(\d+)(\d)\.(\d+)', r'\1.\2\3', wavelength_aa),
                flags,
                ionization])
    return data

def extract_element_data_from_pre(url):
    """Extracts element data from the page."""
    response = requests.get(url, timeout=120)
    soup = BeautifulSoup(response.content, "html.parser")
    pre = soup.find("pre")
    if not pre:
        return []
    return parse_pre_block(pre.get_text())

def main():
    """C-like main."""
    full_data = {}
    for element, url in ELEMENT_URLS.items():
        print(f"Extracting {element}...")
        try:
            full_data[element] = extract_element_data_from_pre(url)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            print(f"Error extracting {element}: {ex}")
            full_data[element] = []

    # Prepare template
    env = Environment(loader=FileSystemLoader(os.path.dirname(__file__)))
    template = env.get_template("strong_lines_template.j2")

    py_output = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "../tobes_ui/strong_lines.py"
    ))

    rendered = template.render(full_data=full_data)

    with open(py_output, "w", encoding="utf-8") as pyfile:
        pyfile.write(rendered + "\n")

    print(f"Wrote: {py_output}")

if __name__ == "__main__":
    main()

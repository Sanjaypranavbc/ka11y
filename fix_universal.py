from pathlib import Path
import re

f = Path("ka11y-python/ka11y/crawler/universal_page.py")
content = f.read_text()

def inject(var_name, js_file):
    js_content = Path(f"ka11y-python/ka11y/crawler/js/{js_file}").read_text()
    search_str = f'{var_name} = _load_js("{js_file}")'
    replacement_str = f'{var_name} = r"""{js_content}"""'
    return content.replace(search_str, replacement_str)

content = inject("_COMBINED_EXTRACT_JS", "universal_extract.js")
content = inject("_LINK_EXTRACT_JS", "link_extract.js")
content = inject("_LAZY_LOAD_TRIGGER_JS", "lazy_load_trigger.js")
content = inject("_BACKGROUND_IMAGES_JS", "background_images.js")

# Remove the _load_js definition
content = re.sub(r'_JS_DIR.*?def _load_js.*?return.*?\(encoding="utf-8"\)\n+', '', content, flags=re.DOTALL)

f.write_text(content)

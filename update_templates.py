import os
import glob

html_files = glob.glob('web/templates/*.html')

old_logo = '<img src="/static/assets/mascot.png" alt="Logo" style="width: 32px; height: 32px; border-radius: 8px; vertical-align: middle; margin-right: 4px; box-shadow: 0 2px 8px rgba(255,107,158,0.3);">'
new_logo = '<img src="/static/assets/favicon_web.png" alt="Logo" style="width: 32px; height: 32px; border-radius: 50%; vertical-align: middle; margin-right: 6px; box-shadow: 0 2px 8px rgba(255,107,158,0.4);">'

fallback_logo_1 = 'src="/static/assets/favicon.png"'
fallback_logo_2 = 'href="/static/assets/favicon.png"'
fallback_hero = 'src="/static/assets/hero_landing.png"'

for html_file in html_files:
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Apply changes
    content = content.replace(old_logo, new_logo)
    content = content.replace(fallback_logo_1, 'src="/static/assets/favicon_web.png"')
    content = content.replace(fallback_logo_2, 'href="/static/assets/favicon_web.png"')
    content = content.replace(fallback_hero, 'src="/static/assets/hero_landing_web.png"')

    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Updated {len(html_files)} HTML files with new image links safely.")

import os
import glob

html_files = glob.glob('web/templates/*.html')
for html_file in html_files:
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '<link rel="icon"' not in content:
        content = content.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n    <link rel="icon" type="image/png" href="/static/assets/favicon.png">')
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
print("Done fixing HTML files!")

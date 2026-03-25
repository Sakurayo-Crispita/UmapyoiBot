import os
import re

color_map = {
    r'#ff8fa3': 'var(--p-pink)',
    r'#9b59b6': 'var(--p-pink)',
    r'#8e44ad': 'var(--p-pink-deep)',
    r'#a29bfe': 'var(--p-pink-soft)',
    r'#ff79c6': 'var(--p-pink)',
    r'#bd93f9': 'var(--p-pink-soft)',
    r'#ffb7c5': 'var(--p-pink-soft)',
    r'#b399d4': 'var(--p-pink-soft)',
    r'rgba\(255, 143, 163, [\d.]+\)': 'rgba(212, 163, 115, 0.2)',
    r'rgba\(155, 89, 182, [\d.]+\)': 'rgba(212, 163, 115, 0.2)',
    r'rgba\(142, 68, 173, [\d.]+\)': 'rgba(188, 108, 37, 0.2)',
    r'rgba\(255, 183, 197, [\d.]+\)': 'rgba(212, 163, 115, 0.1)',
    r'rgba\(179, 153, 212, [\d.]+\)': 'rgba(212, 163, 115, 0.1)',
    r'rgba\(255, 77, 109, [\d.]+\)': 'var(--accent-glow)',
}

def update_files():
    template_dir = 'web/templates'
    static_dir = 'web/static'
    
    files_to_process = []
    if os.path.exists(template_dir):
        files_to_process += [os.path.join(template_dir, f) for f in os.listdir(template_dir) if f.endswith('.html')]
    if os.path.exists(static_dir):
        files_to_process += [os.path.join(static_dir, f) for f in os.listdir(static_dir) if f.endswith('.css')]

    for path in files_to_process:
        print(f"Processing {path}...")
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        is_css = path.endswith('.css')
        
        # Cache bust (only for HTML)
        if not is_css:
            content = re.sub(r'styles.css\?v=[\d.]+', 'styles.css?v=6.0', content)
            
            # Standardize logo in all possible forms
            logo_pattern = r'<img[^>]*src="/static/assets/(favicon_web\.png|mascot\.png)"[^>]*>'
            standard_logo = '<img src="/static/assets/favicon_web.png" alt="Logo" style="width: 32px; height: 32px; border-radius: 50%; vertical-align: middle; margin-right: 6px; box-shadow: 0 2px 10px var(--accent-glow);">'
            content = re.sub(logo_pattern, standard_logo, content)
            
            # Special case for dashboard.html brand area
            content = re.sub(r'<div class="brand">.*?</div>', '<div class="brand"><a href="/" style="text-decoration:none; display:flex; align-items:center; color:inherit;">' + standard_logo + ' <span style="font-weight:850; font-size:1.5rem; font-family:\'Quicksand\', sans-serif;">Umapyoi<span style="color:var(--p-pink);">.</span></span></a></div>', content, flags=re.DOTALL)
            
            # Fix specific dot in logo (Umapyoi.)
            content = re.sub(r'Umapyoi<span>\.</span>', 'Umapyoi<span style="color: var(--p-pink);">.</span>', content)
            content = re.sub(r'Umapyoi<div class="logo-dot"></div>', 'Umapyoi<span style="color: var(--p-pink);">.</span>', content)


        # Replace colors (for both CSS and HTML)
        for pattern, subst in color_map.items():
            content = re.sub(pattern, subst, content, flags=re.IGNORECASE)
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    print("All files synchronized successfully.")

if __name__ == "__main__":
    update_files()

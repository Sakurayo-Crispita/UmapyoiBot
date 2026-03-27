import os

base_dir = r"c:\Uma\UmapyoiBot\web\templates"

with open(os.path.join(base_dir, "dashboard.html"), "r", encoding="utf-8") as f:
    dashboard_content = f.read()

split_marker = '<section class="db-content">'
if split_marker not in dashboard_content:
    print("Error: Could not find db-content section in dashboard.html")
    exit(1)

parts = dashboard_content.split(split_marker)
header_part = parts[0] + split_marker + "\n"

footer_marker = '</section>\n    </main>'
footer_part = ""
if footer_marker in parts[1]:
    footer_idx = parts[1].find(footer_marker)
    footer_part = parts[1][footer_idx:]
else:
    print("Failed to find footer marker.")

# -----------------
# 1. REPORT.HTML
# -----------------
with open(os.path.join(base_dir, "report.html"), "r", encoding="utf-8") as f:
    report_content = f.read()

# Extract the report form content
r_start = report_content.find('<div class="feedback-container">')
r_end = report_content.find('</div>\n\n    <script>')
if r_start != -1 and r_end != -1:
    report_body = report_content[r_start:r_end + 6]
    
    success_overlay = ""
    if '{% if success %}' in report_content:
        soc_start = report_content.find('{% if success %}')
        soc_end = report_content.find('{% endif %}') + 9
        success_overlay = report_content[soc_start:soc_end]

    report_styles = """
    <style>
        .feedback-container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .feedback-header { margin-bottom: 40px; }
        .feedback-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 40px; align-items: start; }
        .glass-card { background: rgba(0, 0, 0, 0.15); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; backdrop-filter: blur(10px); }
        .form-group { margin-bottom: 25px; }
        .form-label { display: block; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px; letter-spacing: 0.8px; }
        .form-hint { font-size: 0.75rem; color: rgba(255,255,255,0.5); margin-bottom: 8px; display: block; }
        .form-input, .form-select, .form-textarea { width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 15px; color: white; font-family: inherit; transition: all 0.3s; }
        .form-input:focus, .form-select:focus, .form-textarea:focus { border-color: var(--p-pink); outline: none; background: rgba(0,0,0,0.4); }
        .form-select option { background: var(--bg-main); color: white; }
        .form-textarea { resize: vertical; min-height: 120px; max-height: 300px; }
        
        .priority-options { display: flex; gap: 15px; margin-top: 10px; }
        .priority-btn { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; text-align: center; font-size: 0.9rem; transition: all 0.3s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .priority-btn i { width: 14px; opacity: 0.5; }
        .priority-btn.active { border-color: var(--p-pink); color: white; background: rgba(212,163,115,0.1); }
        .priority-btn.active i { opacity: 1; color: var(--p-pink); }
        
        .evidence-upload { border: 2px dashed var(--border-color); border-radius: 12px; padding: 30px; text-align: center; transition: all 0.3s; cursor: pointer; background: rgba(0,0,0,0.1); }
        .evidence-upload:hover { border-color: var(--p-pink); background: rgba(212,163,115,0.05); }
        .evidence-upload i { width: 32px; height: 32px; color: var(--text-muted); margin-bottom: 15px; }
        
        .submit-btn { width: 100%; background: var(--p-pink); color: white; border: none; border-radius: 8px; padding: 16px; font-weight: 700; font-size: 1rem; cursor: pointer; margin-top: 30px; box-shadow: 0 4px 15px rgba(212,163,115,0.2); transition: all 0.3s; }
        .submit-btn:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(212,163,115,0.4); filter: brightness(1.1); }
        
        .sidebar-right { position: sticky; top: 100px; display: flex; flex-direction: column; gap: 20px; }
        .example-badge { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; gap: 6px; }
        .priority-tag { font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
        
        .success-overlay { position: fixed; inset: 0; background: rgba(15, 17, 24, 0.98); display: flex; align-items: center; justify-content: center; z-index: 1000; flex-direction: column; text-align: center; padding: 20px; backdrop-filter: blur(10px); }
    </style>
    """

    report_scripts = """
    <script>
        function setPriority(btn, val) {
            document.querySelectorAll('.priority-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('priority-input').value = val;
        }

        document.getElementById('file-input').addEventListener('change', function(e) {
            const count = this.files.length;
            if (count > 0) {
                const label = this.parentElement.querySelector('p');
                label.innerText = count === 1 ? '1 archivo seleccionado' : count + ' archivos seleccionados';
                label.style.color = 'var(--p-pink)';
            }
        });
    </script>
    """

    # Replace <head> styling
    head_end = header_part.find('</head>')
    new_header = header_part[:head_end] + report_styles + header_part[head_end:]
    
    # Active state for sidebar
    new_header = new_header.replace("{% if section == 'servers' %}active{% endif %}", "")
    new_header = new_header.replace('href="/report" class="nav-link"', 'href="/report" class="nav-link active"')

    with open(os.path.join(base_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write(new_header + success_overlay + "\n" + report_body + "\n" + footer_part.replace('</body>', report_scripts + '\n</body>'))
    print("report.html rebuilt.")


# -----------------
# 2. SUGGEST.HTML
# -----------------
with open(os.path.join(base_dir, "suggest.html"), "r", encoding="utf-8") as f:
    suggest_content = f.read()

# Extract the suggest form content
s_start = suggest_content.find('<div class="feedback-container">')
s_end = suggest_content.find('</div>\n\n    <script>')
if s_start != -1 and s_end != -1:
    suggest_body = suggest_content[s_start:s_end + 6]
    
    success_overlay = ""
    if '{% if success %}' in suggest_content:
        soc_start = suggest_content.find('{% if success %}')
        soc_end = suggest_content.find('{% endif %}') + 9
        success_overlay = suggest_content[soc_start:soc_end]

    suggest_styles = report_styles

    suggest_scripts = """
    <script>
        document.getElementById('file-input').addEventListener('change', function(e) {
            const count = this.files.length;
            if (count > 0) {
                const label = this.parentElement.querySelector('p');
                label.innerText = count === 1 ? '1 archivo seleccionado' : count + ' archivos seleccionados';
                label.style.color = 'var(--p-pink)';
            }
        });
    </script>
    """

    head_end = header_part.find('</head>')
    s_header = header_part[:head_end] + suggest_styles + header_part[head_end:]
    s_header = s_header.replace("{% if section == 'servers' %}active{% endif %}", "")
    s_header = s_header.replace('href="/suggest" class="nav-link"', 'href="/suggest" class="nav-link active"')

    with open(os.path.join(base_dir, "suggest.html"), "w", encoding="utf-8") as f:
        f.write(s_header + success_overlay + "\n" + suggest_body + "\n" + footer_part.replace('</body>', suggest_scripts + '\n</body>'))
    print("suggest.html rebuilt.")

#!/usr/bin/env python3
"""
Update Firm-Challenge-Übersicht index.html from Google Sheets data.

Reads challenge completion status from a Google Spreadsheet and regenerates
the static index.html. Then commits and pushes via git.

Runs fully autonomously (no user input, no GUI).
Designed for daily cron execution.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import shutil

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
INDEX_PATH = SCRIPT_DIR / "index.html"
GOOGLE_API = Path.home() / ".hermes" / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"
TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"

SHEET_ID = "1GC0G_sejvJNWWNZjxRK9cjHzQaLPvUEruyY2PKQIbRA"

# ── Challenge tab configuration ────────────────────────────────────────────
# (sheet_tab_name, ch_number, short_label, display_name, spiricloud_url)
CHALLENGES = [
    ("1: Mein Leben und ich - l6-rueckmeldung-leben-foto", 1, "Mein Leben & ich", "Mein Leben & ich", "https://spiricloud.at/mein-leben-ich/"),
    ("2. Gottesbilder - G5_RM_Gottesbilder Worte - g6-rueckmeldung-wortwolke", 2, "Gottesbilder", "Gottesbilder", "https://spiricloud.at/gottesbilder/"),
    ("3: Jesus - J6_RM_Jesus Wunder", 3, "Jesus & seine Wunder", "Jesus & seine Wunder", "https://spiricloud.at/jesus/"),
    ("4: Heiliger Geist:  H6_RM_Heiliger Geist Talente", 4, "Heiliger Geist & Talente", "Heiliger Geist & Talente", "https://spiricloud.at/heiliger-geist/"),
    ("5: u7-rueckmeldung-glaube", 5, "Unser Glaube", "Unser Glaube", "https://spiricloud.at/unser-glaube/"),
    ("6: k2-kirche-bedeutet-fuer-mich", 6, "Kirche (K2)", "Kirche", "https://spiricloud.at/kirche/"),
    ("6: k5-rueckmeldung-ich-und-kirche", 6, "Kirche (K5)", "Kirche", "https://spiricloud.at/kirche/"),
    ("7: w4-rueckmeldung-ich-wir", 7, "Vom Ich zum Wir", "Vom Ich zum Wir", "https://spiricloud.at/vom-ich-zum-wir/"),
    ("8: s5-rueckmeldung-natur", 8, "Schöpfung", "Schöpfung", "https://spiricloud.at/schoepfung/"),
    ("9: v8-rueckmeldung-beichte", 9, "Schattenseiten & Vergebung", "Schattenseiten & Vergebung", "https://spiricloud.at/schattenseiten-vergebung/"),
    ("10: f9-rueckmeldung-firmung", 10, "Sakrament der Firmung", "Sakrament der Firmung", "https://spiricloud.at/sakrament-der-firmung/"),
]

# Display labels, short names, and URLs
CH_LABELS = {ch_num: label for _, ch_num, _, label, _ in CHALLENGES}
CH_SHORT = {ch_num: short for _, ch_num, short, _, _ in CHALLENGES}
CH_URLS = {ch_num: url for _, ch_num, _, _, url in CHALLENGES}
CH_NUM_MAP = {ch_num: ch_num for ch_num in range(1, 11)}

TOTAL_CHALLENGES = 10


# ── Token refresh ──────────────────────────────────────────────────────────

def refresh_token_if_needed():
    """Check token expiry and refresh via refresh_token grant if expired."""
    if not TOKEN_PATH.exists():
        print(f"ERROR: Token file not found at {TOKEN_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TOKEN_PATH, encoding="utf-8") as f:
        token = json.load(f)

    expiry_str = token.get("expiry") or token.get("expires_at", "")
    if not expiry_str:
        print("WARNING: No expiry in token, skipping refresh check", file=sys.stderr)
        return

    try:
        # Parse ISO 8601 expiry
        if expiry_str.endswith("Z"):
            expiry_str = expiry_str[:-1] + "+00:00"
        expiry = datetime.fromisoformat(expiry_str)
    except (ValueError, TypeError):
        print("WARNING: Cannot parse expiry, skipping refresh", file=sys.stderr)
        return

    now = datetime.now(timezone.utc)
    # Refresh if expired or will expire in the next 5 minutes
    if expiry <= now:
        print("Token expired, refreshing...")
        _do_refresh(token)
    elif (expiry - now).total_seconds() < 300:
        print("Token expiring soon ({}), refreshing...".format(expiry))
        _do_refresh(token)
    else:
        print("Token still valid until", expiry)


def _do_refresh(token):
    """Perform OAuth refresh token grant. Updates the token file in place."""
    refresh_token = token.get("refresh_token")
    client_id = token.get("client_id")
    client_secret = token.get("client_secret")
    token_uri = token.get("token_uri", "https://oauth2.googleapis.com/token")

    if not refresh_token:
        print("ERROR: No refresh_token in token file", file=sys.stderr)
        sys.exit(1)
    if not client_secret:
        # Try loading client_secret from the separate file
        secret_path = Path.home() / ".hermes" / "google_client_secret.json"
        if secret_path.exists():
            with open(secret_path, encoding="utf-8") as f:
                secret_data = json.load(f)
            client_id = secret_data.get("installed", {}).get("client_id", client_id)
            client_secret = secret_data.get("installed", {}).get("client_secret", "")
        if not client_secret:
            print("ERROR: No client_secret found for token refresh", file=sys.stderr)
            sys.exit(1)

    import urllib.request

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(token_uri, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            new_token_data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"ERROR: Token refresh failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Update stored token with new access token
    token["token"] = new_token_data.get("access_token", token.get("token"))
    # Update expiry
    expires_in = new_token_data.get("expires_in", 3600)
    new_expiry = datetime.now(timezone.utc).isoformat()
    token["expiry"] = new_expiry

    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2, ensure_ascii=False)

    print("Token refreshed successfully")


# ── Google Sheets data fetching ──────────────────────────────────────────

def sheets_get(tab_name, sheet_range="A1:F998"):
    """
    Call google_api.py via subprocess to fetch sheet data.
    Returns parsed JSON (list of rows).
    """
    # The range includes the tab name
    range_spec = f"'{tab_name}'!{sheet_range}"

    cmd = [
        "/Users/benediktglaser/.hermes/hermes-agent/venv/bin/python3",
        str(GOOGLE_API),
        "sheets", "get",
        SHEET_ID,
        range_spec,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    if result.returncode != 0:
        print(f"ERROR: google_api.py failed for tab '{tab_name}':", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        sys.exit(1)

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON from google_api.py for tab '{tab_name}': {e}", file=sys.stderr)
        print(stdout[:500], file=sys.stderr)
        sys.exit(1)


# ── Data processing ────────────────────────────────────────────────────────

def get_people_from_personen():
    """Read Personen tab and return list of (vorname_unique, nachname, vorname) for active people."""
    rows = sheets_get("Personen", "A1:J998")

    people = []
    # Rows: [0]=headers, [1]=summary, [2:]=data
    for row in rows[2:]:
        if len(row) < 2:
            continue
        nachname = (row[0] or "").strip().lstrip("?")
        vorname = (row[1] or "").strip()
        if not nachname or not vorname:
            continue
        people.append((vorname, nachname, vorname))

    return people


def get_challenge_data():
    """Read Personen tab Spalte C (Challenges) and return dict: {(nachname, vorname): [ch1_done, ch2_done, ...]}"""
    people = get_people_from_personen()
    
    # Result dict: key=(nachname, vorname) -> list of bool (TOTAL_CHALLENGES)
    result = {}
    for vorname, nachname, _ in people:
        result[(nachname, vorname)] = [False] * TOTAL_CHALLENGES
    
    # Build name_to_vorname mapping for display
    name_map = {}
    for vorname, nachname, _ in people:
        name_map[(nachname.lower(), vorname.lower())] = vorname
    
    # Read Personen tab with column C
    rows = sheets_get("Personen", "A1:D998")
    
    for row in rows[2:]:
        if len(row) < 3:
            continue
        nachname_raw = (row[0] or "").strip()
        vorname = (row[1] or "").strip()
        nachname = nachname_raw.lstrip("?")
        ch_str = (row[2] or "").strip()
        
        if not nachname or not vorname:
            continue
        
        # Parse challenge numbers
        nums = []
        for part in ch_str.replace(" ", "").split(","):
            part = part.strip()
            if part and part.isdigit():
                n = int(part)
                if 1 <= n <= TOTAL_CHALLENGES:
                    nums.append(n)
        
        # Find matching entry and mark
        for key in result:
            if key[0].lower() == nachname.lower() and key[1].lower() == vorname.lower():
                for n in nums:
                    result[key][n - 1] = True
                break
    
    return result, name_map


# ── HTML generation ────────────────────────────────────────────────────────

def escape_html(text):
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def generate_html(challenge_data, name_map, today_str):
    """Generate the full index.html from challenge data."""

    # Sort people by name (vorname)
    sorted_people = sorted(challenge_data.keys(), key=lambda k: k[1].lower())

    # ── Stats section ──────────────────────────────────────────────────
    total_people = len(sorted_people)
    stats_rows = []
    for ch_num in range(1, TOTAL_CHALLENGES + 1):
        done_count = sum(
            1 for p in sorted_people if challenge_data[p][ch_num - 1]
        )
        pct = round((done_count / total_people) * 100) if total_people > 0 else 0
        label = CH_LABELS[ch_num]
        stats_rows.append(
            f'        <div class="stat-row">\n'
            f'            <span class="stat-label">{escape_html(label)}</span>\n'
            f'            <div class="stat-bar"><div class="stat-fill" style="width:{pct}%"></div></div>\n'
            f'            <span class="stat-count">{done_count}/{total_people}</span>\n'
            f'        </div>'
        )

    stats_html = "\n".join(stats_rows)

    # ── Table header ───────────────────────────────────────────────────
    ch_header_cells = []
    for ch_num in range(1, TOTAL_CHALLENGES + 1):
        label = CH_SHORT[ch_num]
        url = CH_URLS.get(ch_num, "#")
        ch_header_cells.append(
            f'<th title="{escape_html(label)}"><a href="{url}" target="_blank" style="color:inherit;text-decoration:none">{ch_num}</a></th>'
        )
    ch_header_html = "\n        ".join(ch_header_cells)

    # ── Table rows ─────────────────────────────────────────────────────
    table_rows = []
    for p in sorted_people:
        vorname, nachname = p[1], p[0]
        statuses = challenge_data[p]
        done_count = sum(1 for s in statuses if s)

        cells = [
            f'<tr><td class="name">{escape_html(vorname)}</td>'
        ]
        for is_done in statuses:
            if is_done:
                cells.append('<td class="done">✓</td>')
            else:
                cells.append('<td class="open">—</td>')
        cells.append(f'<td class="count">{done_count}/{TOTAL_CHALLENGES}</td></tr>')
        table_rows.append("".join(cells))

    table_body_html = "\n    ".join(table_rows)

    # ── Details section ─────────────────────────────────────────────────
    detail_parts = []
    for p in sorted_people:
        vorname, nachname = p[1], p[0]
        statuses = challenge_data[p]
        done_count = sum(1 for s in statuses if s)

        done_list = [CH_LABELS[i + 1] for i, s in enumerate(statuses) if s]
        open_list = [CH_LABELS[i + 1] for i, s in enumerate(statuses) if not s]

        if done_list:
            done_str = ", ".join(done_list)
            done_line = f'<p>✅ <strong>{done_count}/{TOTAL_CHALLENGES}</strong> – {escape_html(done_str)}</p>'
        else:
            done_line = f'<p>✅ <strong>0/{TOTAL_CHALLENGES}</strong> – noch keine Challenges erledigt</p>'

        if open_list:
            open_str = ", ".join(open_list)
            open_line = f'<p>⏳ Offen: {escape_html(open_str)}</p>'
        else:
            open_line = f'<p>⏳ Offen: alle {TOTAL_CHALLENGES}</p>'

        detail_parts.append(
            f'        <div class="firmling-detail"><h3>{escape_html(vorname)}</h3>{done_line}{open_line}</div>'
        )

    details_html = "\n".join(detail_parts)

    # ── Links section ────────────────────────────────────────────────────
    link_rows = []
    for ch_num in range(1, TOTAL_CHALLENGES + 1):
        label = CH_LABELS[ch_num]
        url = CH_URLS.get(ch_num, "#")
        link_rows.append(
            f'      <tr><td>{ch_num}</td><td>{escape_html(label)}</td><td><a href="{url}" target="_blank">{url}</a></td></tr>'
        )
    links_html = "\n".join(link_rows)

    # ── Build full HTML ─────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Firm-Challenge-Übersicht</title>
<meta name="robots" content="noindex, nofollow">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    padding: 2rem 1rem;
    line-height: 1.5;
}}
.container {{ max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 0.25rem; color: #1d1d1f; }}
.subtitle {{ color: #6e6e73; font-size: 0.95rem; margin-bottom: 1.5rem; }}
h2 {{ font-size: 1.2rem; font-weight: 600; margin: 1.5rem 0 0.75rem; color: #1d1d1f; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
th, td {{ padding: 0.6rem 0.5rem; text-align: center; font-size: 0.85rem; border-bottom: 1px solid #e8e8ed; }}
th {{ background: #f5f5f7; font-weight: 600; color: #1d1d1f; position: sticky; top: 0; }}
th:first-child, td.name {{ text-align: left; padding-left: 1rem; min-width: 110px; }}
td.name {{ font-weight: 500; }}
.done {{ color: #30d158; font-weight: 700; font-size: 1rem; }}
.open {{ color: #c7c7cc; }}
td.count {{ font-weight: 600; color: #1d1d1f; }}
tr:last-child td {{ border-bottom: none; }}
tr:hover {{ background: #f5f5f7; }}
.stats {{ background: #fff; border-radius: 12px; padding: 1rem 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }}
.stat-row {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }}
.stat-row:last-child {{ margin-bottom: 0; }}
.stat-label {{ width: 140px; font-size: 0.85rem; flex-shrink: 0; }}
.stat-bar {{ flex: 1; height: 10px; background: #e8e8ed; border-radius: 5px; overflow: hidden; }}
.stat-fill {{ height: 100%; background: linear-gradient(90deg, #007aff, #30d158); border-radius: 5px; transition: width 0.5s ease; }}
.stat-count {{ width: 50px; text-align: right; font-size: 0.8rem; color: #6e6e73; flex-shrink: 0; }}
.details-section {{ background: #fff; border-radius: 12px; padding: 1rem 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 1.5rem; }}
.firmling-detail {{ padding: 0.75rem 0; border-bottom: 1px solid #e8e8ed; }}
.firmling-detail:last-child {{ border-bottom: none; }}
.firmling-detail h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem; }}
.firmling-detail p {{ font-size: 0.85rem; color: #3a3a3c; margin-bottom: 0.15rem; }}
footer {{ text-align: center; color: #6e6e73; font-size: 0.75rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e8e8ed; }}
@media (max-width: 600px) {{
    th, td {{ font-size: 0.75rem; padding: 0.4rem 0.3rem; }}
    th:first-child, td.name {{ padding-left: 0.5rem; min-width: 75px; }}
    .stat-label {{ width: 100px; font-size: 0.75rem; }}
}}
</style>
</head>
<body>
<div class="container">
    <h1>🏕️ Firm-Challenge-Übersicht</h1>
    <p class="subtitle">PG Giebelstadt-Bütthard · Stand: {today_str} · Nur für Firmlinge, Eltern & Team</p>

    <div class="stats">
        <h2>📊 Übersicht</h2>
{stats_html}
    </div>

    <table>
    <thead><tr>
        <th>Name</th>
        {ch_header_html}
        <th>✅</th>
    </tr></thead>
    <tbody>
    {table_body_html}
    </tbody>
    </table>

    <div class="details-section">
        <h2>📋 Details pro Firmling</h2>
{details_html}
    </div>

    <div class="details-section">
        <h2>🔗 Direktlinks zu den Challenges</h2>
        <p style="font-size:0.85rem;color:#3a3a3c;margin-bottom:0.5rem">Klick auf eine Challenge, um direkt zum Modul auf spiricloud.at zu gelangen (PIN eingeben und loslegen):</p>
        <table style="width:100%">
        <thead><tr><th>#</th><th>Challenge</th><th>Link</th></tr></thead>
        <tbody>
{links_html}
        </tbody>
        </table>
    </div>

    <footer>
        <p>PG Giebelstadt-Bütthard · Firmvorbereitung</p>
        <p>Keine Analyse, keine Cookies, keine Weitergabe von Daten.</p>
    </footer>
</div>
</body>
</html>"""

    return html


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Firm-Challenge-Tracker: update_page.py")
    print("=" * 60)

    # 1. Refresh token if needed
    refresh_token_if_needed()

    # 2. Fetch challenge data from all tabs
    print("\nFetching challenge data from Google Sheets...")
    challenge_data, name_map = get_challenge_data()
    print(f"Found {len(challenge_data)} firmlinge")

    # Count stats
    for ch_num in range(1, TOTAL_CHALLENGES + 1):
        done_count = sum(1 for p in challenge_data if challenge_data[p][ch_num - 1])
        print(f"  Ch {ch_num} ({CH_LABELS[ch_num]}): {done_count}/{len(challenge_data)} done")

    # 3. Generate HTML
    today_str = datetime.now().strftime("%d.%m.%Y")
    html = generate_html(challenge_data, name_map, today_str)

    # 4. Write and encrypt index.html
    print(f"\nWriting {INDEX_PATH}...")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ index.html geschrieben")

    # Encrypt with staticrypt
    subprocess.run(
        ["staticrypt", INDEX_PATH, "-p", "PG-GB-Firmung2026!"],
        capture_output=True, text=True, timeout=30
    )
    # staticrypt v3.x creates an encrypted/ folder - copy back
    encrypted_path = SCRIPT_DIR / "encrypted" / INDEX_PATH.name
    if encrypted_path.exists():
        shutil.copy2(str(encrypted_path), INDEX_PATH)
        shutil.rmtree(str(SCRIPT_DIR / "encrypted"))
    print(f"✅ Passwortverschlüsselung angewendet")

    # 5. Git commit + push
    print("\nRunning git commit + push...")
    os.chdir(str(SCRIPT_DIR))

    subprocess.run(["git", "add", "index.html"], check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Auto-update index.html ({today_str})"],
        check=False, capture_output=True,
    )
    push_result = subprocess.run(
        ["git", "push"],
        check=False, capture_output=True, text=True,
    )
    if push_result.returncode == 0:
        print("Git push successful.")
    else:
        stderr = push_result.stderr.strip()
        if "Everything up-to-date" in push_result.stdout or "Everything up-to-date" in stderr:
            print("Git: nothing new to push (already up-to-date).")
        elif "nothing to commit" in stderr or "nothing to commit" in push_result.stdout:
            print("Git: nothing to commit (no changes).")
        else:
            print(f"Git push output: {push_result.stdout[:200]}")
            print(f"Git push stderr: {stderr[:200]}")

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
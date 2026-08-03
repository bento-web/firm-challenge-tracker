#!/usr/bin/env python3
"""Täglicher Check: Neue Spiricloud-E-Mails suchen und Google-Tabelle aktualisieren."""

import json, os, subprocess, sys, datetime, re, shutil

HERMES = os.path.expanduser("~/.hermes")
VENV_PYTHON = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python3")
GAPI = f"{VENV_PYTHON} {HERMES}/skills/productivity/google-workspace/scripts/google_api.py"
SHEET_ID = "1GC0G_sejvJNWWNZjxRK9cjHzQaLPvUEruyY2PKQIbRA"
PERSONEN_FILE = os.path.expanduser("~/firm-challenge-tracker/index.html")
UPDATE_SCRIPT = os.path.expanduser("~/firm-challenge-tracker/update_page.py")
KNOWN_FILE = os.path.expanduser("~/firm-challenge-tracker/known_mails.json")

def run_gapi(*args):
    """Führe google_api.py aus und gib JSON zurück."""
    cmd = [VENV_PYTHON, f"{HERMES}/skills/productivity/google-workspace/scripts/google_api.py"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"GAPI Error: {result.stderr}")
        return None
    return json.loads(result.stdout) if result.stdout.strip() else []

def load_known():
    if os.path.exists(KNOWN_FILE):
        with open(KNOWN_FILE) as f:
            return json.load(f)
    return {"known_ids": []}

def save_known(known):
    with open(KNOWN_FILE, "w") as f:
        json.dump(known, f)

def parse_challenge_from_subject(subject):
    """Extrahiere Challenge-Nummer und Name aus dem Mail-Betreff."""
    # Beispiele:
    # "spiriCLOUD neue Antwort von Samuel"
    # "J6_RM_Jesus Wunder" steht im Snippet
    return None  # Wird aus dem Snippet extrahiert

def parse_from_snippet(snippet):
    """Extrahiere Name und Challenge aus dem Snippet."""
    # Beispiel: "Das Formular J6_RM_Jesus Wunder wurde von Samuel beantwortet."
    name_match = re.search(r'wurde von (\w+(?:\s+\w+)?) beantwortet', snippet)
    form_match = re.search(r'Das Formular (\S+)', snippet)
    
    name = name_match.group(1) if name_match else None
    form = form_match.group(1) if form_match else None
    
    return name, form

# Challenge-Mapping (Formularname zu Challenge-Nummer) - NEU mit 10 Challenges
FORM_TO_CHALLENGE = {
    "J6_RM_Jesus Wunder": "3",
    "G5_RM_Gottesbilder Worte": "2",
    "H6_RM_Heiliger Geist Talente": "4",
    "L6_RM_Stärken und Schwächen": "1",
    "U7_RM_Glaube": "5",
    "K2_RM_Kirche bedeutet für mich": "6",
    "K5_RM_Ich und Kirche": "6",
    "W4_RM_Nächstenliebe": "7",
    "S5_RM_Natur": "8",
    "V8_RM_Schattenseiten_Beichtzeit": "9",
    "F9_RM_Firmung": "10",
}

CHALLENGE_TO_TAB = {
    "1": "1: Mein Leben und ich - l6-rueckmeldung-leben-foto",
    "2": "2. Gottesbilder - G5_RM_Gottesbilder Worte - g6-rueckmeldung-wortwolke",
    "3": "3: Jesus - J6_RM_Jesus Wunder",
    "4": "4: Heiliger Geist:  H6_RM_Heiliger Geist Talente",
    "5": "5: u7-rueckmeldung-glaube",
    "6": "6: k2-kirche-bedeutet-fuer-mich",
    "7": "7: w4-rueckmeldung-ich-wir",
    "8": "8: s5-rueckmeldung-natur",
    "9": "9: v8-rueckmeldung-beichte",
    "10": "10: f9-rueckmeldung-firmung",
}

def main():
    today = datetime.date.today().isoformat()
    print(f"=== Spiricloud-Check {today} ===")
    
    # 1. Neue E-Mails suchen
    mails = run_gapi("gmail", "search", "spiricloud", "--max", "20")
    if not mails:
        print("Keine Mails gefunden oder Fehler.")
        return
    
    known = load_known()
    new_mails = [m for m in mails if m["id"] not in known["known_ids"]]
    
    if not new_mails:
        print(f"Keine neuen Mails. Letzte bekannte: {len(known['known_ids'])}")
        return
    
    print(f"Neue Mails gefunden: {len(new_mails)}")
    
    # 2. Jede neue Mail lesen
    for mail in new_mails:
        mail_id = mail["id"]
        snippet = mail.get("snippet", "")
        subject = mail.get("subject", "")
        
        print(f"\n--- Mail ID {mail_id} ---")
        print(f"  Betreff: {subject}")
        print(f"  Snippet: {snippet[:200]}")
        
        name, form = parse_from_snippet(snippet)
        if not name or not form:
            print(f"  ⚠️ Konnte Name/Formular nicht extrahieren")
            known["known_ids"].append(mail_id)
            continue
        
        ch_num = FORM_TO_CHALLENGE.get(form)
        if not ch_num:
            print(f"  ⚠️ Unbekanntes Formular: {form}")
            known["known_ids"].append(mail_id)
            continue
        
        print(f"  ✅ {name} → Challenge {ch_num} ({form})")
        
        # 3. Personen-Tabelle aktualisieren (Spalte C: Challenges)
        personen = run_gapi("sheets", "get", SHEET_ID, "Personen!A1:C100")
        if personen:
            for row_idx, row in enumerate(personen[2:], start=3):
                if len(row) >= 2:
                    sname = row[0].strip().lstrip("?").lower()
                    fname = row[1].strip().lstrip("?").lower()
                    name_lower = name.lower()
                    
                    if sname == name_lower or fname == name_lower or f"{fname} {sname}".find(name_lower) >= 0:
                        current_ch = row[2].strip() if len(row) > 2 else ""
                        new_challenges = set(c.strip() for c in current_ch.replace(" ", "").split(",") if c.strip())
                        
                        if ch_num not in new_challenges:
                            new_challenges.add(ch_num)
                            sorted_ch = ", ".join(sorted(new_challenges, key=lambda x: int(x) if x.isdigit() else 99))
                            
                            # Update the cell
                            cell_range = f"Personen!C{row_idx}"
                            result = run_gapi("sheets", "update", SHEET_ID, cell_range, f'[[\"{sorted_ch}\"]]')
                            if result:
                                print(f"  📝 Personen!C{row_idx} aktualisiert: {current_ch} → {sorted_ch}")
                            else:
                                print(f"  ❌ Fehler beim Aktualisieren von Personen!C{row_idx}")
                        else:
                            print(f"  ℹ️ Challenge {ch_num} bereits eingetragen")
                        break
            else:
                print(f"  ⚠️ {name} nicht in Personen-Tabelle gefunden")
        
        known["known_ids"].append(mail_id)
    
    save_known(known)
    
    # 4. Seite aktualisieren
    if os.path.exists(UPDATE_SCRIPT):
        print("\n--- Seite aktualisieren ---")
        result = subprocess.run([sys.executable, UPDATE_SCRIPT], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("✅ Seite aktualisiert")
        else:
            print(f"❌ Fehler: {result.stderr}")
    else:
        print("⚠️ update_page.py noch nicht vorhanden")
    
    print(f"\n=== Check abgeschlossen ({len(new_mails)} neue Mails) ===")

if __name__ == "__main__":
    main()
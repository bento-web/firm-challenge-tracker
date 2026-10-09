#!/usr/bin/env python3
"""Täglicher Check: Neue Spiricloud-E-Mails suchen, Tabelle aktualisieren, Seite bauen, Status-Mail versenden."""
import json, os, subprocess, sys, datetime, re

HERMES = os.path.expanduser("~/.hermes")
VENV_PYTHON = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python3")
GAPI = f"{VENV_PYTHON} {HERMES}/skills/productivity/google-workspace/scripts/google_api.py"
SHEET_ID = "1GC0G_sejvJNWWNZjxRK9cjHzQaLPvUEruyY2PKQIbRA"
UPDATE_SCRIPT = os.path.expanduser("~/firm-challenge-tracker/update_page.py")
KNOWN_FILE = os.path.expanduser("~/firm-challenge-tracker/known_mails.json")

PIN = "6-11922401"

CH_LABELS = {
    "1": "Mein Leben & ich", "2": "Gottesbilder", "3": "Jesus & seine Wunder",
    "4": "Heiliger Geist & Talente", "5": "Unser Glaube", "6": "Kirche",
    "7": "Vom Ich zum Wir", "8": "Schöpfung", "9": "Schattenseiten & Vergebung",
    "10": "Sakrament der Firmung",
}
CH_URLS = {
    1: "https://spiricloud.at/mein-leben-ich/",
    2: "https://spiricloud.at/gottesbilder/",
    3: "https://spiricloud.at/jesus/",
    4: "https://spiricloud.at/heiliger-geist/",
    5: "https://spiricloud.at/unser-glaube/",
    6: "https://spiricloud.at/kirche/",
    7: "https://spiricloud.at/vom-ich-zum-wir/",
    8: "https://spiricloud.at/schoepfung/",
    9: "https://spiricloud.at/schattenseiten-vergebung/",
    10: "https://spiricloud.at/sakrament-der-firmung/",
}

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


def run_gapi(*args):
    """Führe google_api.py aus und gib JSON zurück."""
    cmd = [VENV_PYTHON, f"{HERMES}/skills/productivity/google-workspace/scripts/google_api.py"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        err = result.stderr.strip()
        if err:
            print(f"  GAPI Error: {err[:200]}")
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


def parse_from_snippet(snippet):
    """Extrahiere Name und Formular aus dem Snippet."""
    name_match = re.search(r'wurde von\s+(.+?)\s+beantwortet', snippet)
    form_match = re.search(r'Das Formular\s+(.+?)\s+wurde von', snippet)
    name = name_match.group(1).strip() if name_match else None
    form = form_match.group(1).strip() if form_match else None
    return name, form


def find_person_row(personen, name_lower):
    """Finde Person in der Tabelle. Sicherheitsregel: sehr kurze Namen (1-2 Zeichen)
    brauchen exakten Treffer auf Vor- oder Nachname."""
    for row_idx, row in enumerate(personen[2:], start=3):
        if len(row) >= 2:
            sname = row[0].strip().lstrip("?").lower()
            fname = row[1].strip().lstrip("?").lower()
            full = f"{fname} {sname}"

            if sname == name_lower or fname == name_lower:
                return row_idx, row
            if len(name_lower) >= 3 and name_lower in full:
                return row_idx, row
    return None, None


def build_status_mail(vorname, nachname, firmling_email, eltern_email, done_list, done_count):
    """Baue den E-Mail-Text für einen Firmling."""
    open_list = [str(i) for i in range(1, 11) if str(i) not in done_list]

    recipients = []
    if firmling_email and firmling_email not in ("über Mutter", "über Vater", ""):
        recipients.append(firmling_email)
    if eltern_email:
        recipients.append(eltern_email)

    if not recipients:
        return None, None, None

    if done_count == 10:
        status_summary = "Du hast bereits ALLE 10 Challenges abgeschlossen! 🎉"
    else:
        status_summary = f"Du hast {done_count} von 10 Challenges abgeschlossen."

    done_lines = "\n".join(
        f"  ✅ Challenge {n}: {CH_LABELS.get(str(n), n)}"
        for n in sorted(done_list, key=int)
    ) if done_list else "  (noch keine)"

    if open_list:
        open_lines = "\n".join(
            f"  ⬜ Challenge {n}: {CH_LABELS.get(str(n), n)} -> {CH_URLS.get(int(n), '#')}"
            for n in open_list
        )
        open_section = (
            f"\n\n📋 **Noch offene Challenges:**\n{open_lines}\n\n"
            f"👉 Klick auf den Link, gib die PIN **{PIN}** ein und leg los!"
        )
    else:
        open_section = "\n\n🎉 **Alle Challenges sind erledigt!**"

    body = f"""Hallo {vorname},

hier ist dein aktueller Stand bei den Firm-Challenges:

{status_summary}

✅ **Erledigt:** {done_count}/10
{done_lines}{open_section}

🔐 **Deine PIN für spiricloud.at: {PIN}**

📊 **Übersicht aller Firmlinge:** https://bento-web.github.io/firm-challenge-tracker/
(Passwort: PG-GB-Firmung2026!)

Liebe Grüße,
Benedikt Glaser
Pastoralreferent PG Giebelstadt-Bütthard"""

    subject = f"Dein Firm-Challenge-Stand - {vorname}"
    return subject, body, recipients


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

    # Sammle, wer was gemacht hat, für die Zusammenfassung
    updated_persons = []  # [(name_from_mail, ch_num), ...]

    # 2. Jede neue Mail verarbeiten
    for mail in new_mails:
        mail_id = mail["id"]
        snippet = mail.get("snippet", "")
        subject = mail.get("subject", "")

        print(f"\n--- Mail ID {mail_id} ---")
        print(f"  Betreff: {subject[:100]}")

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

        print(f"  ✅ {name} -> Challenge {ch_num} ({form})")
        updated_persons.append((name, ch_num))

        # 3. Personen-Tabelle aktualisieren (Spalte E: Challenges)
        personen = run_gapi("sheets", "get", SHEET_ID, "Personen!A1:E100")
        if not personen:
            print("  ❌ Personen-Daten nicht lesbar")
            known["known_ids"].append(mail_id)
            continue

        row_idx, row = find_person_row(personen, name.lower())
        if row_idx is not None:
            current_ch = row[4].strip() if len(row) > 4 else ""
            new_set = set(c.strip() for c in current_ch.replace(" ", "").split(",") if c.strip())

            if ch_num not in new_set:
                new_set.add(ch_num)
                sorted_ch = ", ".join(sorted(new_set, key=lambda x: int(x) if x.isdigit() else 99))
                cell_range = f"Personen!E{row_idx}"
                result = run_gapi("sheets", "update", SHEET_ID, cell_range, "--values", f'[["{sorted_ch}"]]')
                if result:
                    print(f"  📝 Personen!E{row_idx} aktualisiert: {current_ch} -> {sorted_ch}")
                else:
                    print(f"  ❌ Fehler beim Aktualisieren von Personen!E{row_idx}")
            else:
                print(f"  ℹ️ Challenge {ch_num} bereits eingetragen")
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
            print(f"❌ Fehler: {result.stderr[:300]}")
    else:
        print("⚠️ update_page.py noch nicht vorhanden")

    # 5. Status-Mails versenden
    print("\n--- Status-Mails versenden ---")
    personen_full = run_gapi("sheets", "get", SHEET_ID, "Personen!A1:N998")
    if not personen_full:
        print("❌ Konnte E-Mail-Daten nicht laden")
    else:
        for name_from_mail, ch_num in updated_persons:
            row_idx, row = find_person_row(personen_full, name_from_mail.lower())
            if row is None:
                print(f"  ⚠️ {name_from_mail}: Nicht in Tabelle")
                continue

            vorname = row[1].strip().lstrip("?")
            nachname = row[0].strip().lstrip("?")
            current_ch = row[4].strip() if len(row) > 4 else ""
            ch_set = set(c.strip() for c in current_ch.replace(" ", "").split(",") if c.strip())
            done_list = sorted(ch_set, key=lambda x: int(x))
            done_count = len(ch_set)

            firmling_email = row[12].strip() if len(row) > 12 else ""
            eltern_email = row[13].strip() if len(row) > 13 else ""

            subject, body, recipients = build_status_mail(
                vorname, nachname, firmling_email, eltern_email, done_list, done_count
            )
            if not recipients:
                print(f"  ⚠️ {vorname} {nachname}: Keine E-Mail-Adresse")
                continue

            to_str = ", ".join(recipients)
            print(f"  📧 Sende an {to_str} ({vorname})...")
            result = run_gapi("gmail", "send", "--to", to_str, "--subject", subject, "--body", body)
            if result and result.get("status") == "sent":
                print(f"  ✅ Status-Mail an {vorname} gesendet")
            else:
                print(f"  ❌ Fehler beim Senden")

    print(f"\n=== Check abgeschlossen ({len(new_mails)} neue Mails) ===")


if __name__ == "__main__":
    main()
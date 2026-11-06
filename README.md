# Lumena Connector

Povezuje Home Assistant sa **Perfectus Smart** bez Nabu Case i bez otvaranja
portova na ruteru. Home Assistant sam otvara sigurnu (HTTPS/WSS) vezu prema
Perfectusu i izvršava samo njegove zahtjeve.

## Instalacija (HACS)

1. HACS → ⋮ → **Custom repositories** → URL
   `https://github.com/pva-project/lumena-ha-connector`, kategorija **Integration** → Add.
2. Pronađite **Lumena Connector** → **Download** → restartujte Home Assistant.
3. U Perfectusu: **Smart podešavanja → Podešavanja → Način povezivanja: Lumena konektor → Napravi kod**.
4. U Home Assistantu: **Settings → Devices & Services → Add integration → Lumena**,
   upišite adresu Perfectusa i kod.

Perfectus nakon toga pokazuje „Konektor je spojen”.

## Sigurnost

- Kod za povezivanje važi 15 minuta i koristi se jednom.
- Integracija pravi sistemskog korisnika „Lumena Connector”; njegov token
  nikad ne napušta Home Assistant.
- Brisanjem integracije briše se i taj korisnik, pa Perfectus gubi pristup.

# Lumena Connector

Povezuje Home Assistant sa **Smart** modulom aplikacije (Perfectus, River GYM)
bez Nabu Case i bez otvaranja portova na ruteru. Home Assistant sam otvara
sigurnu (HTTPS/WSS) vezu prema aplikaciji i izvršava samo njene zahtjeve.

## Instalacija (HACS)

1. HACS → ⋮ → **Custom repositories** → URL
   `https://github.com/pva-project/lumena-ha-connector`, kategorija **Integration** → Add.
2. Pronađite **Lumena Connector** → **Download** → restartujte Home Assistant.
3. U aplikaciji (Perfectus / River GYM): **Smart podešavanja → Podešavanja → Način povezivanja: Lumena konektor → Napravi kod**.
4. U Home Assistantu: **Settings → Devices & Services → Add integration → Lumena**,
   upišite adresu aplikacije i kod:
   - Perfectus: `https://app.perfectus-medical.com`
   - River GYM: `https://app.river-gym.com`

Aplikacija nakon toga pokazuje „Konektor je spojen”. Jedan Home Assistant može
biti povezan i sa više aplikacija (svaka adresa je posebna integracija).

## Sigurnost

- Kod za povezivanje važi 15 minuta i koristi se jednom.
- Integracija pravi sistemskog korisnika „Lumena Connector”; njegov token
  nikad ne napušta Home Assistant.
- Brisanjem integracije briše se i taj korisnik, pa aplikacija gubi pristup.

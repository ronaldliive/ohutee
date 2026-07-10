# Ohutee

Ohutee on lühikese ajaga loodud avaliku veebirakenduse prototüüp, mis muudab Eesti inimkannatanutega liiklusõnnetuste avaandmed tavainimesele arusaadavamaks.

> Märkus: rakenduse vaikimisi kaardipunktid on sünteetilised. Pärisandmed saab lisada CSV-failina ning enne tootmiskasutust tuleb parser kohandada Transpordiameti jooksva andmestruktuuriga.

## Avaldamine GitHub Pagesis

1. Loo GitHubis uus **public** repositoorium, näiteks `ohutee`.
2. Laadi kõik selle kausta failid repositooriumi juurkausta.
3. Ava repositooriumis **Settings → Pages**.
4. Vali **Build and deployment → Deploy from a branch**.
5. Vali haru **main** ja kaust **/(root)**, seejärel vajuta **Save**.
6. Mõne aja pärast asub rakendus aadressil `https://KASUTAJANIMI.github.io/ohutee/`.

Rakendus ei vaja ehitamist, serverit ega tasulisi teenuseid.

## Kohalik käivitamine

```bash
python3 -m http.server 8765
```

Seejärel ava `http://localhost:8765`.

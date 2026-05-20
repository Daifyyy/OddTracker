import streamlit as st

st.title("Průvodce aplikací")
st.caption("Co aplikace zobrazuje, co znamenají jednotlivé pojmy a jak s daty pracovat.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Základy & Workflow",
    "Pohyb kurzů & CLV",
    "Steam moves",
    "Jak se rozhodovat",
    "API & Data",
])

# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## Co je tato aplikace a k čemu slouží")
    st.markdown("""
Tato aplikace je **analytický nástroj pro sledování pohybu kurzů** na sportovních trzích.
Neslouží k přímému sázení — cílem je sbírat data, sledovat, jak se kurzy hýbou,
a ověřit, jestli se v určitých situacích opakuje **využitelný pattern**.

> **První fáze = výzkum.** Nesázej dřív, než budeš mít data za několik týdnů
> a jasnou hypotézu, kterou čísla potvrzují.
""")

    st.divider()
    st.markdown("## Doporučený workflow")

    with st.container(border=True):
        st.markdown("""
**1. Nastav preset** *(záložka Matches)*
- Vyber sport a soutěž (např. Bundesliga)
- Vyber trhy: doporučuji začít s **h2h + totals**
- Vyber bookmakery: **Pinnacle vždy** + 2–3 další (William Hill, Nordicbet)
- Ulož jako preset → příště jeden klik

**2. Fetchuj pravidelně**
- Ideálně 3–5× denně pro sledované zápasy
- Ranní snapshot (opening), odpolední update, hodinu před výkopem
- Den před výkopem: 2–3 snapshoty
- Hodinu před výkopem: každých 15–20 minut (closing se blíží)
- Jeden fetch = 1–5 kreditů (záleží na počtu trhů)

**3. Sleduj záložku Změny kurzů**
- Hledej výrazné pohyby (Δ > 0.05 u Pinnacle)
- Sleduj, jestli pohyb odpovídá u více bookmakrů současně

**4. Zaznamenávej hypotézy ručně**
- Když vidíš zajímavý pohyb, poznač si: "Pokud Over 2.5 klesne o více než 0.1 u Pinnacle,
  bude výsledek Over v X% případů"
- Záložka Analytics ti to časem spočítá automaticky

**5. Po skončení zápasů fetchni výsledky**
- Matches → Fetch výsledky
- Aplikace automaticky dopočítá CLV a připraví data pro Analytics

**6. Vyhodnoť po 3–4 týdnech**
- Záložka Analytics → Win rate po pohybech
- Záložka CLV → jak tvé "signály" obstály vůči closing line
""")

    st.divider()
    st.markdown("## Co sledovat jako první")
    with st.container(border=True):
        st.markdown("""
**Začni jednodušeji než si myslíš:**

1. Jedno API, jeden sport, jeden trh (doporučuji **totals = Over/Under góly**)
2. Sbírej data 2–3 týdny bez jakéhokoliv rozhodování
3. Sleduj pouze Pinnacle — ten je referenční
4. Až budeš mít 30+ zápasů, podívej se na záložku Analytics

**Proč Pinnacle jako referenci?**
Pinnacle je tzv. **sharp bookmaker** — přijímá velké sázky, neomezuje hráče
a jeho kurzy nejpřesněji odráží reálnou pravděpodobnost.
Pokud Pinnacle mění kurz, je to signál, ne náhoda.
""")

# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Pohyb kurzů — co znamená a jak ho číst")

    with st.container(border=True):
        st.markdown("""
### Základní princip

**Kurz klesl** (např. Over 2.5 z 1.90 → 1.75):
- Bookmaker snižuje kurz, protože na daný výběr přišlo hodně peněz
- Nebo přišly **ostrá (sharp) sázky**, které bookmaker respektuje
- Výsledek: méně atraktivní kurz pro pozdější hráče

**Kurz vzrostl** (např. Over 2.5 z 1.75 → 1.85):
- Méně peněz na daný výběr, nebo bookmaker lákí na opačnou stranu
- Nebo se bookmaker mýlil v otvíracím kurzu a koriguje

**Změna linie** (např. Handicap −0.75 → −1.0):
- Silnější signál než samotný pohyb kurzu
- Bookmaker změnil strukturu trhu, ne jen cenu
""")

    st.divider()
    st.markdown("## Opening vs Closing kurzy")

    with st.container(border=True):
        st.markdown("""
| Pojem | Definice |
|-------|----------|
| **Opening** | Kurz při prvním záznamu pro daný zápas a trh |
| **Closing** | Kurz těsně před výkopem (poslední snapshot ≤ commence_time) |
| **Pohyb** | Closing − Opening (záporný = kurz klesl) |

**Proč je closing kurz důležitý?**

Closing kurz je nejpřesnějším odhadem bookmakerů, protože vychází z největšího
množství informací (sázky, zranění, počasí, taktika).
Je to pomyslný "konsensus trhu" těsně před zápasem.

> Pokud byl tvůj vstupní kurz **lepší než closing**, vsadils za lepší cenu než trh uzavřel —
> to je definice **pozitivního CLV**.
""")

    st.divider()
    st.markdown("## CLV — Closing Line Value")

    with st.container(border=True):
        st.markdown("""
**CLV = (opening kurz / closing kurz − 1) × 100 %**

| CLV % | Co to znamená |
|-------|--------------|
| **+5 %** | Tvůj kurz byl o 5 % lepší než closing — silný signál hodnoty |
| **+2 %** | Mírně pozitivní — průměr pro dobré sázaře |
| **0 %** | Přesně trefil closing — neutrální |
| **−3 %** | Horší než closing — zaplatil jsi přirážku |

**Proč je CLV důležitý?**

Dlouhodobě **sázaři s kladným průměrným CLV vydělávají**, protože poráží trh.
Pokud máš průměrné CLV +3 % na 100 sázkách, je vysoká pravděpodobnost,
že tvé výběry jsou hodnotné — i kdyby krátkodobé výsledky byly špatné.

CLV je objektivní metrika kvality vstupu, nezávislá na výsledku.

> **Zlaté pravidlo:** Zaměř se na CLV, ne na výsledky.
> Dobrý výběr s negativním výsledkem (smůla) je pořád dobrý výběr.
""")

# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Steam Moves — co jsou a jak je číst")

    with st.container(border=True):
        st.markdown("""
### Definice

**Steam move** nastane, když **3 nebo více bookmakrů současně pohne kurzem
ve stejném směru** v krátkém časovém okně (15 minut).

Jde o silný signál, protože:
- Jeden bookmaker mohl jen korigovat chybu
- Tři a více = trh reaguje na novou informaci nebo velkou ostrá sázku

### Jak steam move vzniká

1. Ostrý hráč (sharp bettor) nebo sázkový syndikát vsadí velkou částku u jednoho bookmakera
2. Bookmaker sníží kurz, aby omezil riziko
3. Ostatní bookmakeři si toho všimnou a také sníží kurz (nebo jsou propojeni přes data feeds)
4. Výsledek: koordinovaný pohyb = **steam move dolů**
""")

    st.divider()
    with st.container(border=True):
        st.markdown("""
### Jak steam move číst

| Směr | Co to říká | Co s tím |
|------|-----------|---------|
| **Dolů (down)** | Ostrá sázka na daný výběr | Potenciálně hodnotný výběr — trh ho respektuje |
| **Nahoru (up)** | Veřejné peníze nebo korekce | Méně spolehlivý signál — spíše rekce na náhodu |

**Klíčové parametry:**
- **Počet bookmakrů:** ≥ 4 = silnější signál
- **Průměrné Δ:** ≥ 0.08 = výrazný pohyb
- **Do KO:** pohyb 2–4 hodiny před výkopem = nejsilnější (ostrý hráč má informace)

### Co steam move neznamená

Steam move **nezaručuje správný výsledek** — říká pouze, že trh si myslí,
že daný výběr je hodnotný. Trh se mýlí cca 40–50 % času (závisí na sportu a trhu).

> Cíl: zjistit, jestli se v tvém sledovaném sportu steam moves ukazují jako
> statisticky spolehlivý signál. To ti ukáže záložka Analytics po dostatku dat.
""")

# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## Jak se rozhodovat na základě dat")

    with st.container(border=True):
        st.markdown("""
### Fáze 1: Sbírání dat (první 2–4 týdny)

Nesázej nic, pouze sleduj. Cíl je nasbírat alespoň **30–50 zápasů** se:
- Alespoň 3–5 snapshoty každý
- Výsledky (fetchnuté přes Fetch výsledky)
- Zaznamenanými pohyby kurzů

### Fáze 2: Formulace hypotézy

Na základě pozorování si polož konkrétní otázku:

> *"Když Pinnacle sníží kurz na Over 2.5 o více než 0.08 v posledních 2 hodinách
> před výkopem, je výsledek Over v X% případů?"*

Tato otázka musí být **konkrétní a falzifikovatelná** — buď to platí nebo ne.

### Fáze 3: Ověření v Analytics

Záložka Analytics → Win rate po pohybech:
- Filtruj na konkrétní trh a minimální pohyb
- Sleduj hit rate a počet vzorků
- **Minimální vzorek: 30 zápasů** pro statisticky relevantní závěr
""")

    st.divider()
    with st.container(border=True):
        st.markdown("""
### Interpretační tabulka

| Situace | Interpretace | Akce |
|---------|-------------|------|
| Hit rate > 60 %, n > 30 | Potenciálně silný signál | Testovat s malými sázkami |
| Hit rate 50–60 %, n > 30 | Slabý signál, může být náhoda | Sbírat více dat |
| Hit rate < 50 %, n > 30 | Signál nefunguje | Vyřadit, hledat jiný |
| Jakýkoliv výsledek, n < 20 | Nedostatečný vzorek | Nesázet, sbírat dál |
| Průměrné CLV > +3 % | Dobré vstupy | Systematicky sledovat |
| Průměrné CLV < 0 % | Horší vstupy než closing | Přehodnotit výběr signálů |

### Červené vlajky — NESÁZET pokud:

- Vzorek je menší než 30 zápasů
- Hit rate je přesně kolem 50 % (náhoda)
- Signal funguje pouze v jedné soutěži/sezóně
- Nemáš vysvětlení, PROČ by signal měl fungovat
""")

    st.divider()
    with st.container(border=True):
        st.markdown("""
### Příklad správného myšlení

**Špatně:** "Včera Pinnacle snížil kurz na Over a Over vyšlo. Budu sázet Over pokaždé."

**Správně:**
1. Zaznamenám pohyb
2. Po 40 zápasech se podívám na hit rate
3. Pokud je hit rate > 58 % s n > 40 a průměrné CLV > +2 %, začnu testovat
4. Začnu s malými sázkami (1–2 % bankrollu) a sleduju 30 dalších zápasů
5. Teprve pak případně zvyšuju expozici

> **Cíl není mít pravdu. Cíl je mít edge — statisticky ověřitelnou výhodu.**
""")

# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("## The Odds API — co nabízí a jak funguje")

    with st.container(border=True):
        st.markdown("""
### Plán a kredity

| Plán | Cena | Kredity/měsíc |
|------|------|--------------|
| Free | 0 $ | 500 |
| 20K | 30 $/měs | 20 000 |
| 100K | 59 $/měs | 100 000 |

**1 kredit = 1 API volání** (jeden sport + jeden region + jeden nebo více trhů)

Aktuální stav kreditů je vidět v levém sidebaru.
""")

    st.divider()
    with st.container(border=True):
        st.markdown("""
### Dostupné trhy (EU region, fotbal)

| Klíč | Název | Co vrací |
|------|-------|---------|
| `h2h` | 1X2 | Kurzy na výhru domácích / remízu / výhru hostů |
| `totals` | Over/Under | Kurzy na Over/Under počet gólů (linie: 2.5, 3.5...) |
| `spreads` | Asijský handicap | Kurzy s linií handicapu |

> ⚠️ **Corners, BTTS, team totals, player props nejsou v EU regionu dostupné.**

### Dostupní bookmakeři

**Doporučení pro sledování:**
- **Pinnacle** — sharp book, referenční kurzy, nejlepší pro CLV analýzu
- **William Hill** — velký evropský book, dobré pro srovnání
- **Nordicbet, Betsson** — evropské knihy s konkurenčními kurzy
- **Marathonbet** — aktivní na evropských trzích

> ⚠️ **bet365, Fortuna, Betano, Tipsport v The Odds API nejsou** —
> neposkytují data do tohoto API feedu.

### Doporučená frekvence fetchů (500 kreditů/měsíc)

| Strategie | Kredity/den | Popis |
|-----------|------------|-------|
| Konzervativní | 8–10 | 2–3 fetche denně, 2–3 trhy |
| Aktivní | 15–16 | 4–5 fetchů denně, více trhů |
| Intenzivní před KO | 20+ | Časté fetche hodinu před výkopem |

> Tip: Free tier vystačí na **~16 fetchů denně** průměrně.
> Pokud tě aplikace zaujme, upgrade na 20K za 30 $/měs = 650 fetchů denně.
""")

    st.divider()
    with st.container(border=True):
        st.markdown("""
### Endpoint /scores — výsledky

Pro zpětnou analýzu potřebuješ výsledky zápasů.
Endpoint `/scores` vrací výsledky dokončených zápasů (posledních N dní).

**Jak na to:**
1. Matches → **Fetch výsledky** (doporučuji kliknout den po zápasech)
2. Aplikace automaticky dopočítá CLV pro dokončené zápasy
3. Data se zobrazí v záložkách CLV a Analytics

> Výsledky fetchuj do **24–48 hodin po zápase** — API vrací data zpětně jen za několik dní.
""")

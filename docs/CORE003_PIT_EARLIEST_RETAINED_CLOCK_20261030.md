# CORE-003 | PIT-arkiv skal bruke tidligste bevarte kildestart

**Funn:** Den eksisterende `core_pit_roster_verification.audit_race` valgte nyeste ATG-kilde før kanonisk T−4 som en tidsanker. En tidligere arkivert ATG-kilde kan allerede ha angitt et tidligere starttidspunkt. En senere starttidsrevisjon må ikke flytte T−4 frem og gjøre etterfølgende odds/historikk godkjent.

**Endring:** Forskningsauditen leser **alle bevarte ATG fullfelt-klokker observert senest ved kanonisk T−4**, velger den tidligste gyldige for konservativ T−4 og rapporterer både siste ATG-klokke, tidligste kildeklokke, antall kilder, avvik og tilfeller med ugyldige eller motstridende tidsrevisjoner. Ugyldige tidligere klokker og motstridende payloads fra samme observasjonstid gir `BLOCKED`; identiske dubletter er lov. Kode og test endrer ikke original source, risikomodell eller Champion.

Dette er ikke sertifisering av faktisk startklokke, publiseringstid eller historiske strykninger. En `source_published_at_utc=null` gir fortsatt `pit_certified=false`. Alle beregninger er kildeforensikk, ingen bettingsignaler.

**Negative tester:** Tidlig kilde 14:57, senere revisjon 15:00, fundamental/odds 14:54 skal få konservativ cutoff 14:53 og blokk; ugyldig eldre klokke blokkerer; forskjellige klokker på samme observasjonstid blokkerer; identiske duplikater skaper ikke kunstig konflikt.

**Åpent:** CI, sammenligning mot faktisk heldagsarkiv, review og eksplisitt merge-godkjenning. Avhengighet: [CORE-003 #83](https://github.com/Maremoo2/Betting/issues/83), [CORE-001/002 #89](https://github.com/Maremoo2/Betting/issues/89). Ingen produksjonsendringer, ingen PIT-friskmelding, ingen autospill.

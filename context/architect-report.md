# Raport architektoniczny — Moduł 4 (10xArchitect)

*Synteza L2–L5. Wszystkie twierdzenia oparte wyłącznie na artefaktach źródłowych wskazanych niżej — brak uzupełnień z pamięci.*

## 1. Opisane projekty

| Repo | Stack | Skala (orientacyjnie) | Artefakt |
|---|---|---|---|
| **mattermost/mattermost** | Monorepo: backend Go (`server/`, REST v4 + WebSocket), frontend TS/React (`webapp/`, workspace npm), 2 generacje E2E (Cypress legacy + Playwright docelowa) | 1869 commitów/12 mies.; `admin_console` 1456 zmian, `server/channels/app` 1850 zmian; 216 speców Cypress, 164 Playwright | L2 (repo-map), L3 (research post-flow), L4 (plan refaktoryzacji) |
| **10xdevs3 / EnvBooker** | Django 6.0.5, Python 3.14, `uv`; 3 apki domenowe (`accounts`, `catalog`, `reservations`), Postgres-only (GiST exclusion constraint) | Mała, greenfield aplikacja kursowa | L5 (3 notatki domenowe: dystylacja, agregaty/inwarianty, ACL) |

Uwaga: L2–L4 pochodzą z **innego repozytorium** (Mattermost) niż L5 (EnvBooker) — traktowane niżej jako dwa odrębne studia przypadku, nie jeden ciągły projekt.

## 2. Mapa projektu (Mattermost, L2)

- **Dwa bieguny aktywności**: `webapp/channels/src/components/admin_console` (1456 zmian) i `server/channels/app` (1850 zmian) — reszta repo jest wyraźnie mniej "gorąca".
- **Strefy ryzyka**: (1) duży SCC wokół `websocket_actions.ts`/`global_actions.tsx`/`dialog_router` (instability 0.95, brama do dziesiątek modali); (2) god-module `utils/utils.tsx` (fan-in 168, w cyklu); (3) cross-language config triangle `config.go`↔`config.ts`↔`admin_definition.tsx`, niewidoczny dla dependency-cruiser.
- **Rozjazd struktura↔aktywność**: `e2e-tests/cypress` wciąż duży (1205 zmian), ale to trend malejący — realna energia jest w `e2e-tests/playwright` (wzrost x13/4 kwartały).
- **Ważny unknown**: `server/` (Go, cały backend) i `e2e-tests/` **nie mają grafu zależności** w tej analizie (dependency-cruiser objął tylko `webapp`) — wszystko o backendzie pochodzi z co-change w git, nie z analizy importów.
- Entry point poleconej pierwszej lektury: `utils/constants.tsx` (fan-in 657, słownik pojęć), potem para `config.ts`/`config.go`.

## 3. Analiza ficzera (Mattermost, L3)

**Zbadany przepływ**: zapis posta (post-save), wybrany bo leży bezpośrednio przy dwóch strefach ryzyka z mapy — jest "bramą drugiego stopnia" do dużego SCC (`post_actions.ts` importowany wprost przez `websocket_actions.ts`/`global_actions.tsx`) i dotyka trójkąta store-generacji zidentyfikowanego w L2.

**Feature overview**: użytkownik wysyła wiadomość → frontend robi **optymistyczny zapis** (natychmiastowy `RECEIVED_NEW_POST` z tymczasowym `pending_post_id`) i równolegle woła `POST /api/v4/posts` → backend (`app.CreatePost`, ~310 linii, 45 instrukcji `if`) zapisuje przez generowane warstwy store'a i broadcastuje event WebSocket `posted` → frontend odbiera ten sam post **drugą ścieżką** (WS) i reconciliuje go z optymistycznym wpisem w reducerze.

**Technical debt (top 3, jedno potwierdzone ast-grepem):**
1. **Podwójna ścieżka reconciliacji** (HTTP response + WS event dla tego samego posta) — najsłabiej przetestowane miejsce całego przepływu (retry/rollback przy błędzie sieci: 0% pokrycia E2E w obu frameworkach, potwierdzone grepem).
2. **Brak mostu Go↔TS dla `model.Post`** — nowe pole wymaga ręcznej synchronizacji w ≥5 miejscach (struct, `Auditable`, `ShallowCopy/Clone`, `IsValid`, kolumny SQL, typ TS); już kosztowało to 3.5 roku opóźnienia jednej funkcji (`RemoteId`, Go 2021→TS 2024) i ma dziś otwarty odpowiednik (`has_reactions`, tylko Go).
3. **[Potwierdzone ast-grepem]** `PostStore.Save` mechanicznie pociąga regenerację 3 artefaktów (`retrylayer.go:9399`, `timerlayer.go:7533`, `storetest/mocks/PostStore.go`) — `grep` potwierdził też, że `deduplicateCreatePost` ma dokładnie **1** wywołanie w całym repo (post.go:172), a hook `MessageWillBePosted` dokładnie **1** miejsce wywołania — wzorce "tylko tutaj" założone w raporcie faktycznie się trzymają.

Weryfikacja: 19/21 twierdzeń strukturalnych potwierdzonych, 1 obalone (liczby speców E2E — skorygowano na 216/164), 1 doprecyzowane (cykl importu `post_actions.ts`↔`create_comment.tsx` istnieje tylko na poziomie typów, nie runtime).

## 4. Plan refaktoryzacji (Mattermost, L4)

**Co refaktoryzowane**: dwie niezależne, addytywne fazy z rankingu — **C3** (guardrail dryfu Go↔TS dla `model.Post`: warning-only test + hard-fail storetest dla kolumn SQL + rozszerzenie ścieżki CI) i **C1** (czysta ekstrakcja bloku walidacji odbiorców powiadomień persystentnych z `CreatePost` do osobnej metody, bez zmiany zachowania).

**Czego świadomie NIE robimy**: C2 (konsolidacja dual-path reconciliation) i C4 (naprawa cyklu importu `post_actions.ts`↔`create_comment.tsx`) — odłożone na osobny plan; przełączenie guardrailu C3 z warning na blocking; naprawa samego dryfu `has_reactions`; dalsza dekompozycja `CreatePost` poza tą jedną ekstrakcją; generyczny codegen Go↔TS.

**Fazy** (każda z Automated + Manual Success Criteria):
1. **Faza 1 (C3)** — nowy test Go↔TS (`TestPostModelMatchesTypeScriptType`, tylko `t.Logf`), hard-fail storetest kolumn, rozszerzenie `server-ci.yml` o ścieżkę `posts.ts` bez odpalania ciężkich jobów. Weryfikacja: automatyczna (build/vet/test) + ręczna (odczyt logu potwierdzającego `has_reactions`, próba z tymczasowym polem, próba PR dotykającego tylko `posts.ts`). *Status: ukończona (wszystkie kroki 1.1–1.9 odhaczone).*
2. **Faza 2 (C1)** — ekstrakcja `validatePersistentNotificationRecipients`, zachowanie identycznych kodów błędów/statusów; nowe testy branchy wcześniej niepokrytych. Weryfikacja: automatyczna (build/vet/test + `git diff` = czysta ekstrakcja) + ręczna (wizualny diff, przejście end-to-end, potwierdzenie działania deferred cleanup). *Status: nieukończona (kroki 2.1–2.8 wciąż `[ ]`).*

## 5. Domena wg DDD (EnvBooker, L5)

**Ubiquitous language (kluczowe pojęcia)**: **Environment** (bookable env z metadanymi + owner) · **Reservation** (roszczenie użytkownika do env na okno czasowe) · **during** (`[start, end)`, half-open) · **Conflict** (istniejąca rezerwacja blokująca nakładającą się, musi być nazwana) · **Admin** (`is_staff or is_superuser`, nadzbiór regular user).

**Najważniejsze rozjazdy model-vs-kod**: (1) FR-009 nazywa `purpose` jako wymiar filtrowania, ale kod nigdy go nie filtruje (tylko wyświetla) — realny dryf produktowy, ranking #1 do naprawy; (2) badge "definition changed" reaguje na *dowolną* zmianę `updated_at`, nie tylko semantycznie istotną — bezpieczniejsze niż zamierzone (false positive, nie false negative), nie defekt.

**Niezmiennik #1 i agregat**: "Żadne dwie rezerwacje tego samego środowiska nie mogą mieć nakładających się okien `during`" — egzekwowany na poziomie DB (`ExclusionConstraint reservation_no_overlap`, `btree_gist`), najsilniejsza możliwa warstwa; `Reservation` jest naturalnym agregatem. Plan L5-drugi (invariant-aggregate) wybrał jednak do refaktoryzacji **nie** ten niezmiennik (już maksymalnie zabezpieczony), lecz **I5** — "edycja środowiska pod aktywnymi rezerwacjami wymaga jawnego, ponownie weryfikowanego potwierdzenia admina" — bo to jedyny inwariant rozmyty między warstwami (inline w widoku, bez transakcji, `confirm` ufany bez rewalidacji), z realnym, nietestowanym race condition. Proponowany fix: `Environment` jako agregat z `assess_reservation_impact`/`apply_edit`/`delete_guarded`, value object `ReservationImpact` z `fingerprint()`, `select_for_update()` w jednej transakcji.

**Anti-Corruption Layer**: przecieka `psycopg.types.range.Range` — konstruowany niezależnie w **4 miejscach** (te same literały `Range(x, y, "[)")`) i czytany surowo (`.lower`/`.upper`) w **6 warstwach architektonicznych**: persystencja (legalnie) → formularze → serwisy (2 apki) → widoki → admin → **4 szablony HTML** (najgorsze przejście — szablon nie ma importu Pythona i nie może udokumentować, co znaczy `.lower`). Sygnatura domenowa `describe_overlap_conflict(env, during: Range[datetime], ...)` wprost łamie zasadę "brak typów bibliotecznych w domenie". Uwaga: żaden dokument nie deklaruje potrzeby wymienialności Postgresa (przeciwnie — `settings.py` twardo blokuje inne DB) — uzasadnieniem ACL jest wyłącznie duplikacja i głębokość przecieku, nie hipotetyczny swap bazy. Proponowany fix: `TimeWindow` (value object) + `RangeCodec` port + `PsycopgRangeCodec` adapter jako jedyny moduł znający psycopg.

## 6. Decyzje, które należą do mnie

AI (agent) wykonał całą analizę strukturalną — mapowanie repo, trasowanie przepływu, ranking refaktoryzacji, projekt agregatu i ACL — oraz zweryfikował własne twierdzenia narzędziami (ast-grep, grep, niezależna replikacja co-change), sam poprawiając jedno błędne twierdzenie (liczby speców E2E) i doprecyzowując drugie (cykl importu tylko na poziomie typów). Decyzje pozostające po mojej stronie: (1) czy FR-009 (filtr `purpose`) to bug do naprawienia czy błąd w PRD do skorygowania — AI świadomie zostawił to jako pytanie produktowe, nie techniczne; (2) kolejność wdrożenia dwóch niezależnych planów Mattermost (C3/C1 vs. I5 vs. ACL) — nie ma wymuszonej sekwencji między repozytoriami ani nawet między planami L5; (3) akceptacja kompromisu w L5-ACL, że formatowanie wyświetlania (`strftime` vs `|date:`) **pozostaje niespójne** celowo (AI argumentował, żeby nie przenosić tej niespójności do warstwy domenowej) — to decyzja o zakresie, którą świadomie utrzymuję.

-- 291_seed_machine_translations_sept4b.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 19 strings the
-- Sept 4 batch (H2H + lag notices) added. Same contract as 184/189/213/223/239/243/249/256/265:
-- PENDING proposals only, sentinel proposer 'claude-mt', license_assent TRUE at
-- the machine-translation terms revision. The same 76 translations ship
-- BUNDLED in I18nCatalogues.cs, so the client renders them without approval;
-- these proposals exist so human translators can see/refine them through the
-- portal (an approval overrides the bundled value via the pack overlay).
--
-- key_id = sha1("client" || chr(0) || source)[:16] — the NUL-separator form
-- tools/i18n_sync_keys.py uses.
--
-- ORDERING: seeds only keys already present in i18n_keys. Run order:
-- deploy API -> apply 290 (or run tools/i18n_sync_keys.py) -> apply this
-- file. On an unsynced database the assertion below RAISEs and the transaction
-- rolls back; re-run after the keys land. Explicit BEGIN/COMMIT (#340); every
-- statement is idempotent under the wrapper's || re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed291 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed291 (key_id, lang, source_hash, target) VALUES
  -- "Lag notices: <color=#FF9966>OFF</color>"
    ('02b8b22e38fd50f7', 'es', '252303c6d39a40dd7f036c76f80bb69f75ae36c2', E'Avisos de lag: <color=#FF9966>NO</color>')
  , ('02b8b22e38fd50f7', 'ru', '252303c6d39a40dd7f036c76f80bb69f75ae36c2', E'Уведомления о лагах: <color=#FF9966>ВЫКЛ</color>')
  , ('02b8b22e38fd50f7', 'uk', '252303c6d39a40dd7f036c76f80bb69f75ae36c2', E'Сповіщення про лаги: <color=#FF9966>ВИМК</color>')
  , ('02b8b22e38fd50f7', 'sv', '252303c6d39a40dd7f036c76f80bb69f75ae36c2', E'Laggaviseringar: <color=#FF9966>AV</color>')
  -- "First time playing {0}"
  , ('08c937803617523a', 'es', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', E'Primera vez jugando contra {0}')
  , ('08c937803617523a', 'ru', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', E'Первая игра против {0}')
  , ('08c937803617523a', 'uk', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', E'Перша гра проти {0}')
  , ('08c937803617523a', 'sv', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', E'Första gången mot {0}')
  -- "Your game is dropping frames (worst {0} ms)"
  , ('285d7e4d5c39d2b2', 'es', '586d2a346956f0f867bcd4d3f641fe92cf790371', E'Tu juego pierde fotogramas (peor: {0} ms)')
  , ('285d7e4d5c39d2b2', 'ru', '586d2a346956f0f867bcd4d3f641fe92cf790371', E'Ваша игра теряет кадры (худший: {0} мс)')
  , ('285d7e4d5c39d2b2', 'uk', '586d2a346956f0f867bcd4d3f641fe92cf790371', E'Ваша гра втрачає кадри (найгірший: {0} мс)')
  , ('285d7e4d5c39d2b2', 'sv', '586d2a346956f0f867bcd4d3f641fe92cf790371', E'Ditt spel tappar bildrutor (värst {0} ms)')
  -- "{0} months ago"
  , ('3b76eb04250b37e5', 'es', '3c784acc314dd9a21178a33cfb55e12ab4f6711a', E'hace {0} meses')
  , ('3b76eb04250b37e5', 'ru', '3c784acc314dd9a21178a33cfb55e12ab4f6711a', E'{0} мес. назад')
  , ('3b76eb04250b37e5', 'uk', '3c784acc314dd9a21178a33cfb55e12ab4f6711a', E'{0} міс. тому')
  , ('3b76eb04250b37e5', 'sv', '3c784acc314dd9a21178a33cfb55e12ab4f6711a', E'för {0} månader sedan')
  -- "Your ping to the relay is high ({0} ms)"
  , ('458e4de1c2f8d9ab', 'es', '4c19162ad3fa67a9827c74dad8dbf9162e282948', E'Tu ping al relay es alto ({0} ms)')
  , ('458e4de1c2f8d9ab', 'ru', '4c19162ad3fa67a9827c74dad8dbf9162e282948', E'Высокий пинг до ретранслятора ({0} мс)')
  , ('458e4de1c2f8d9ab', 'uk', '4c19162ad3fa67a9827c74dad8dbf9162e282948', E'Високий пінг до ретранслятора ({0} мс)')
  , ('458e4de1c2f8d9ab', 'sv', '4c19162ad3fa67a9827c74dad8dbf9162e282948', E'Din ping till reläservern är hög ({0} ms)')
  -- "{0} years ago"
  , ('5366e6d1aa97a268', 'es', '9a3274443563edf3bd9c07afa970a039ce5ea98f', E'hace {0} años')
  , ('5366e6d1aa97a268', 'ru', '9a3274443563edf3bd9c07afa970a039ce5ea98f', E'{0} г. назад')
  , ('5366e6d1aa97a268', 'uk', '9a3274443563edf3bd9c07afa970a039ce5ea98f', E'{0} р. тому')
  , ('5366e6d1aa97a268', 'sv', '9a3274443563edf3bd9c07afa970a039ce5ea98f', E'för {0} år sedan')
  -- "Last played {0} · H2H {1}-{2} · Ranked series {3}"
  , ('645e3d3f657b13e7', 'es', 'a3f322bfc21229baf76a1294517e9f556f824da8', E'Última partida {0} · H2H {1}-{2} · Series ranked {3}')
  , ('645e3d3f657b13e7', 'ru', 'a3f322bfc21229baf76a1294517e9f556f824da8', E'Последняя игра {0} · H2H {1}-{2} · Рейтинговые серии: {3}')
  , ('645e3d3f657b13e7', 'uk', 'a3f322bfc21229baf76a1294517e9f556f824da8', E'Остання гра {0} · H2H {1}-{2} · Рейтингові серії: {3}')
  , ('645e3d3f657b13e7', 'sv', 'a3f322bfc21229baf76a1294517e9f556f824da8', E'Senaste matchen {0} · H2H {1}-{2} · Ranked-serier {3}')
  -- "yesterday"
  , ('658c8881ff4b6496', 'es', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', E'ayer')
  , ('658c8881ff4b6496', 'ru', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', E'вчера')
  , ('658c8881ff4b6496', 'uk', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', E'вчора')
  , ('658c8881ff4b6496', 'sv', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', E'igår')
  -- "Lag notices: <color=#88FF88>ON</color>"
  , ('7aeac17f502399de', 'es', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', E'Avisos de lag: <color=#88FF88>SÍ</color>')
  , ('7aeac17f502399de', 'ru', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', E'Уведомления о лагах: <color=#88FF88>ВКЛ</color>')
  , ('7aeac17f502399de', 'uk', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', E'Сповіщення про лаги: <color=#88FF88>УВІМК</color>')
  , ('7aeac17f502399de', 'sv', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', E'Laggaviseringar: <color=#88FF88>PÅ</color>')
  -- "Opponent reports {0} ms ping"
  , ('98e4a76eed695306', 'es', '02ceb2093b5bcc236bd9551a871fa0884433fade', E'El rival reporta {0} ms de ping')
  , ('98e4a76eed695306', 'ru', '02ceb2093b5bcc236bd9551a871fa0884433fade', E'Соперник сообщает пинг {0} мс')
  , ('98e4a76eed695306', 'uk', '02ceb2093b5bcc236bd9551a871fa0884433fade', E'Суперник повідомляє пінг {0} мс')
  , ('98e4a76eed695306', 'sv', '02ceb2093b5bcc236bd9551a871fa0884433fade', E'Motståndaren rapporterar {0} ms ping')
  -- "Opponent's updates are arriving late (in transit)"
  , ('9b0b5e78093b80dd', 'es', 'e5336e6106c1b000895725fd8ac765b349047068', E'Las actualizaciones del rival llegan tarde (en tránsito)')
  , ('9b0b5e78093b80dd', 'ru', 'e5336e6106c1b000895725fd8ac765b349047068', E'Обновления соперника приходят с опозданием (в пути)')
  , ('9b0b5e78093b80dd', 'uk', 'e5336e6106c1b000895725fd8ac765b349047068', E'Оновлення суперника надходять із запізненням (у дорозі)')
  , ('9b0b5e78093b80dd', 'sv', 'e5336e6106c1b000895725fd8ac765b349047068', E'Motståndarens uppdateringar kommer sent (under överföring)')
  -- "Last played {0} · also played today · H2H {1}-{2} · Ranked s"
  , ('adce3a775476d686', 'es', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', E'Última partida {0} · también hoy · H2H {1}-{2} · Series ranked {3}')
  , ('adce3a775476d686', 'ru', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', E'Последняя игра {0} · также играли сегодня · H2H {1}-{2} · Рейтинговые серии: {3}')
  , ('adce3a775476d686', 'uk', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', E'Остання гра {0} · також грали сьогодні · H2H {1}-{2} · Рейтингові серії: {3}')
  , ('adce3a775476d686', 'sv', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', E'Senaste matchen {0} · även idag · H2H {1}-{2} · Ranked-serier {3}')
  -- "{0} weeks ago"
  , ('bb67c219422bc077', 'es', '93a527feb58430dacc2462c4e3aec2f6dfc49791', E'hace {0} semanas')
  , ('bb67c219422bc077', 'ru', '93a527feb58430dacc2462c4e3aec2f6dfc49791', E'{0} нед. назад')
  , ('bb67c219422bc077', 'uk', '93a527feb58430dacc2462c4e3aec2f6dfc49791', E'{0} тиж. тому')
  , ('bb67c219422bc077', 'sv', '93a527feb58430dacc2462c4e3aec2f6dfc49791', E'för {0} veckor sedan')
  -- "a year ago"
  , ('bf4ae830222e69d8', 'es', '2e8849fcb4982de44770ca02f39c8751143b02c2', E'hace un año')
  , ('bf4ae830222e69d8', 'ru', '2e8849fcb4982de44770ca02f39c8751143b02c2', E'год назад')
  , ('bf4ae830222e69d8', 'uk', '2e8849fcb4982de44770ca02f39c8751143b02c2', E'рік тому')
  , ('bf4ae830222e69d8', 'sv', '2e8849fcb4982de44770ca02f39c8751143b02c2', E'för ett år sedan')
  -- "First played today · H2H {0}-{1} · Ranked series {2}"
  , ('c9e4dc142533d543', 'es', 'ce9fc34778b41ce8ab57abb9ce88121448338b54', E'Primera partida hoy · H2H {0}-{1} · Series ranked {2}')
  , ('c9e4dc142533d543', 'ru', 'ce9fc34778b41ce8ab57abb9ce88121448338b54', E'Первая игра сегодня · H2H {0}-{1} · Рейтинговые серии: {2}')
  , ('c9e4dc142533d543', 'uk', 'ce9fc34778b41ce8ab57abb9ce88121448338b54', E'Перша гра сьогодні · H2H {0}-{1} · Рейтингові серії: {2}')
  , ('c9e4dc142533d543', 'sv', 'ce9fc34778b41ce8ab57abb9ce88121448338b54', E'Första matchen idag · H2H {0}-{1} · Ranked-serier {2}')
  -- "Unknown player"
  , ('cd2c0619969e467e', 'es', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', E'Jugador desconocido')
  , ('cd2c0619969e467e', 'ru', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', E'Неизвестный игрок')
  , ('cd2c0619969e467e', 'uk', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', E'Невідомий гравець')
  , ('cd2c0619969e467e', 'sv', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', E'Okänd spelare')
  -- "{0} days ago"
  , ('d00d1cf6fc532cd8', 'es', '9344533c4118c35c73e68a704ed70271514f9211', E'hace {0} días')
  , ('d00d1cf6fc532cd8', 'ru', '9344533c4118c35c73e68a704ed70271514f9211', E'{0} дн. назад')
  , ('d00d1cf6fc532cd8', 'uk', '9344533c4118c35c73e68a704ed70271514f9211', E'{0} дн. тому')
  , ('d00d1cf6fc532cd8', 'sv', '9344533c4118c35c73e68a704ed70271514f9211', E'för {0} dagar sedan')
  -- "Corner notices when your frames drop, your ping is high or t"
  , ('f6f39272fe6447ee', 'es', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', E'Avisos en la esquina cuando tus fotogramas caen, tu ping es alto o las actualizaciones del rival llegan tarde. Solo 1v1.')
  , ('f6f39272fe6447ee', 'ru', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', E'Уведомления в углу экрана, когда падает частота кадров, высокий пинг или обновления соперника приходят с опозданием. Только 1 на 1.')
  , ('f6f39272fe6447ee', 'uk', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', E'Сповіщення в кутку екрана, коли падає частота кадрів, високий пінг або оновлення суперника надходять із запізненням. Лише 1 на 1.')
  , ('f6f39272fe6447ee', 'sv', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', E'Hörnaviseringar när dina bildrutor sjunker, din ping är hög eller motståndarens uppdateringar kommer sent. Endast 1v1.')
  -- "H2H {0}-{1} · Ranked series {2}"
  , ('fb918ff938758326', 'es', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', E'H2H {0}-{1} · Series ranked {2}')
  , ('fb918ff938758326', 'ru', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', E'H2H {0}-{1} · Рейтинговые серии: {2}')
  , ('fb918ff938758326', 'uk', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', E'H2H {0}-{1} · Рейтингові серії: {2}')
  , ('fb918ff938758326', 'sv', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', E'H2H {0}-{1} · Ranked-serier {2}');

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed291 v
  JOIN i18n_keys k ON k.key_id = v.key_id AND k.retired_at IS NULL
                  AND k.source_hash = v.source_hash
 WHERE NOT EXISTS (
   SELECT 1 FROM i18n_proposals p
    WHERE p.key_id = v.key_id AND p.language_code = v.lang
      AND p.status = 'pending')
   AND NOT EXISTS (
   SELECT 1 FROM i18n_proposals p2
    WHERE p2.key_id = v.key_id AND p2.language_code = v.lang
      AND p2.proposer_steam_id = 'claude-mt'
      AND p2.source_hash = v.source_hash);

DO $$
DECLARE
  uncovered INTEGER;
  sample TEXT;
BEGIN
  SELECT COUNT(*) INTO uncovered
    FROM _seed291 v
   WHERE NOT EXISTS (
           SELECT 1 FROM i18n_proposals p
            WHERE p.key_id = v.key_id AND p.language_code = v.lang
              AND (p.source_hash = v.source_hash OR p.status = 'pending'))
     AND NOT EXISTS (
           SELECT 1 FROM i18n_entries e
            WHERE e.key_id = v.key_id AND e.language_code = v.lang
              AND e.state = 'approved');
  IF uncovered <> 0 THEN
    SELECT string_agg(x.key_id || '/' || x.lang, ', ')
      INTO sample
      FROM (SELECT v.key_id, v.lang FROM _seed291 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 291: % of 76 seed pairs did not land (e.g. %) - the usual cause is that 290 / tools/i18n_sync_keys.py has not run against this database yet; nothing committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 291: all 76 seed pairs covered (19 keys x es/ru/uk/sv)';
END $$;

COMMIT;

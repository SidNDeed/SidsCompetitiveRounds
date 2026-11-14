-- 410: the v1.41.0 release key sync, written as a migration.
-- tools/i18n_sync_keys.py builds one request for POST /api/v1/admin/i18n/sync-keys; the
-- endpoint needs the admin HMAC, which this seat cannot sign (learning #421, as for 248).
-- This file is that request, captured from the tool's own main() at main 5b1e418c
-- (tools/i18n_source.json, which i18n_extract.py --diff reads as 0 added and 0 removed;
-- tools/game_strings.json): 3779 client keys and 242 game keys, each with its context.
-- It runs the endpoint's own statements (backend/api/main.py, admin_i18n_sync_keys):
--   1. the manifest counts and the endpoint's 10% shrink rule, read before any write;
--   2. the upsert of every manifest key with the endpoint's SET list (max_px NULL,
--      retired_at NULL, updated_at NOW());
--   3. the retirement sweep: every live client or game key absent from the manifest;
--   4. the supersede of pending proposals whose source_hash differs from their key's
--      (source changed at key sync), then of pending proposals on the keys step 3
--      retired (key retired at key sync);
--   5. the endpoint's audit row in i18n_review_events (admin, 'all', sync_keys), its
--      detail in the endpoint's form plus "; migration 410".
-- Measured against the primary at 2026-11-13T23:27:41Z, before this file was written
-- (learning #894): 927 keys are new, 1 retired key comes back, 189 live keys get a new
-- context line and 2904 are unchanged. 74 live client keys retire: 71 are v1.40.3
-- strings that 1.41.0 replaced and 3 never shipped. Of the branch tips committed in the
-- ten days before, only two release-notes branches cut from an older main carry any of
-- them (7); the v1.41.0 tree and every other tip carry none. Their 106 pending
-- proposals, all machine proposals, are superseded. No game key's English moves, so
-- step 4's first supersede finds nothing. The 12 approved translations on the retired
-- keys stay in i18n_entries; the pack (main.py, i18n pack: k.retired_at IS NULL) stops
-- serving them, as every release sync does for the strings it replaces.
-- Not reproduced: the endpoint's pg_advisory_xact_lock on the admin id, a function a
-- data-only migration may not call. That lock orders the endpoint against the admin
-- grant path, which writes no key or proposal row.
-- The post-check proves every manifest key live with the manifest's values, no live
-- client or game key outside the manifest, and no pending proposal on a key this run
-- retired. One transaction (learning #340): lock_timeout 5s, statement_timeout 25s,
-- idle_in_transaction_session_timeout 5s, synchronous_commit local (learning #1072).
-- A second run writes no key value, retires nothing and supersedes nothing; it moves
-- updated_at on the manifest's keys and writes a second audit row.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL synchronous_commit = local;

CREATE TEMP TABLE _sync410 (
  key_id      VARCHAR(16)  NOT NULL,
  namespace   VARCHAR(32)  NOT NULL,
  msgctxt     TEXT         NOT NULL,
  source_hash VARCHAR(40)  NOT NULL,
  sensitive   BOOLEAN      NOT NULL,
  context     VARCHAR(160)
) ON COMMIT DROP;

CREATE TEMP TABLE _retired410 (
  key_id      VARCHAR(16)  NOT NULL
) ON COMMIT DROP;

INSERT INTO _sync410 (key_id, namespace, msgctxt, source_hash, sensitive, context) VALUES
  ('2bb1bf93b17bd29d', 'client', '   (Total Series {0} - {1})', '084be6fc3f55fa36a3d40c683fad5e686ff98f7a', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('5b55ed08358bfee9', 'client', '   -   CASUAL (UNRATED)', '50e2e93f65bd2bd960221ee26b92edfba8b35840', FALSE, 'FfaMode · OnGameStart')
  , ('e0fcf786dd7b7b90', 'client', '   -   SAME CARDS FOR EVERYONE', '715f30506d8f436b4787b770a4cc87eabfae38f5', FALSE, 'FfaMode · OnGameStart')
  , ('6b1f73c4d8328319', 'client', '   -   SUDDEN DEATH: everyone else cannot damage each other', '9833cb8825f1f4d90e0a19ac6b712bce64ed47ef', FALSE, 'CompetitiveUI · RefreshFfaMatchPointBanner')
  , ('456d85ea1d8bfabd', 'client', '   -   {0}-CARD DRAW', '10c1aa938eb56ce3e9eda95a5e8dc74f082440e5', FALSE, 'FfaMode · OnGameStart')
  , ('83dff324198dd780', 'client', '  (last: {0})', '33de31eaa86df586fc5cdac587e01a4da1d8fcd6', FALSE, 'NativeUI · RefreshSession')
  , ('91be82a18dd171cd', 'client', '  ({0} in queue)', '62bc9bd22039bdff56e0bd4fcee58186d7e082de', FALSE, 'NativeUI · RefreshQueueUI')
  , ('2162e2c2b5f464fe', 'client', '  <color=#66AACC>{0:F1}% of players have this</color>', 'e4f560bd5c376f04483f27e865429b9aa02616ec', FALSE, 'NativeUI · RefreshAchievements')
  , ('99fb1e843ffa48b1', 'client', '  <color=#7FDBFF>|</color>  <color=#AAAAAA>{0} online</color>', 'b6de50bf861dc8814de845b4ea604d7139f92ae4', FALSE, 'NativeUI · OnlineSuffix')
  , ('8c164ed58ce9079e', 'client', '  <color=#7FE8C3>(Play Now sent - waiting on opponent)</color>', '4f9cee4c4c73d54778be56cfdebe274451160a6e', FALSE, 'NativeUI · RefreshTournaments')
  , ('4b8715e4b2f70357', 'client', '  <color=#888>(both press Play Now to skip the break)</color>', 'c44d1e007980b0c4c05926c5b451d936df7c29c3', FALSE, 'NativeUI · RefreshTournaments')
  , ('3062dde2abd2a69f', 'client', '  <color=#888>(no cards recorded)</color>', 'e8118b29fc17abd4ee7f9747c5f083aded32fe66', FALSE, 'NativeUI · BuildRecordHoverBody')
  , ('5228b8e02c86210c', 'client', '  <color=#888>(page {0}/{1}, {2} total)</color>', '53b74b7f2271d94b654a77d49d0bb23fa6af9042', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('410c6b3196db19e4', 'client', '  <color={0}>Game streak: {1}L</color>', '491a2892516650e2efb2b13a1bbef1914af24555', FALSE, 'NativeUI · RefreshMyStats')
  , ('9e6e059ee1f6f9d8', 'client', '  <color={0}>Game streak: {1}W</color>', '131ff12826d9ed6fe685a77c1fbee5a166346b70', FALSE, 'NativeUI · RefreshMyStats')
  , ('3f7d936b214a5c44', 'client', '  <color={0}>Series streak: {1}L</color>', 'e6ef24456d8cc38ec788b19b6efe193194317345', FALSE, 'NativeUI · RefreshMyStats')
  , ('b0196ae3471ab703', 'client', '  <color={0}>Series streak: {1}W</color>', 'b1c82e918d4d6bc3462d09c8a72e196ccc681b2c', FALSE, 'NativeUI · RefreshMyStats')
  , ('aa62f023a76d12a0', 'client', '  <color={0}>Streak: {1}L</color>', '43662c1f038c90a664be45e6511968bab3328abf', FALSE, 'NativeUI · RefreshMyStats')
  , ('41a1ec5a6ed468da', 'client', '  <color={0}>Streak: {1}W</color>', '80e78a92f3f309fc0c1a71575668bfebae1fdbc0', FALSE, 'NativeUI · RefreshMyStats')
  , ('3df52f1d70da786e', 'client', '  Best: {0}W', 'de13cba6d1b25ba9af841a7cc5323f04b74b5fd7', FALSE, 'NativeUI · RefreshMyStats')
  , ('c23c3f556d4a1843', 'client', '  Dmg/game: {0:F0}', '774994f54715e39266a6307618d901ad7fd66269', FALSE, 'NativeUI · RefreshMyStats')
  , ('78f8e040217c152e', 'client', '  In room with {0}', 'fe8ecd2e7ce2de3f4e5cd9f5d0455d92809bdbc6', FALSE, 'NativeUI · RefreshSession')
  , ('783de471a77b0e7d', 'client', '  Top 3: {0:F0}%  Kills/game: {1:F1}  Avg place: {2:F1}{3}', 'f4b973bce333a3966b7fb58036443649af4dd861', FALSE, 'NativeUI · RefreshMyStats')
  , ('b50df2e13f58ab02', 'client', '  [Opponent Ready]', '3b88585ccc7066af5df23fdfd4cd1d8b7d835a49', FALSE, 'NativeUI · RefreshQueueUI')
  , ('59e3487efe729e16', 'client', '  vs {0}:  <color={1}>{2}W-{3}L lifetime</color>{4}', '69dbcae41ae96b4d28fd39fbc75d2d0d810cd266', FALSE, 'NativeUI · RefreshSession')
  , ('ccd6c2ba67bfee1e', 'client', '  vs {0}:  First time playing!', 'c25067a12dfc7a94ec107c6073e215ab8f45ec06', FALSE, 'NativeUI · RefreshSession')
  , ('63f971a282654786', 'client', '  {0}  <color=#888>{1} their side</color>  <color=#666>{2}</color>', 'b0247bb4bb0764888d3c797e0f15daaa92c2ca9e', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('b89dfee35f251973', 'client', ' (Play Now sent - waiting on them)', 'c94d1c070e24745e5257b847aa68b945bb5b953c', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('d4fad156d78d0d23', 'client', ' (both press Play Now in F5 to start early)', '79ee5562e90ab9cb7bff0affa6fe06d4ff9292d7', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('03859cd272da4deb', 'client', ' (inactive)', 'f6ce7b7762e1def879ef1a477d73d657b3325ce4', FALSE, 'NativeUI · InactiveName')
  , ('51bc6ddfd6c32b36', 'client', ' (pays {0}g)', '6f3c170bd545215b8832f0798382db9a53474f4b', FALSE, 'NativeUI · SubmitCustomBet')
  , ('7259df1b70d18781', 'client', ' 3rd Place', 'df993b1068f9d239300f7d35914da537046234d8', FALSE, 'NativeUI · RefreshTournaments')
  , ('ba68583791ba9d1f', 'client', ' <color=#888888>(disconnected)</color>', '3f5ef6394e8e0608589641ba984dc41d31e28a20', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('777a4ed3a4e9d1b0', 'client', ' <color=#888888>(left)</color>', 'e0aa04851ac53a1bd32f85ccfe859005fe4e0a5e', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('a6027f92c31ba8ae', 'client', ' at x{0}', '2446ef58482e38247e7a667e3e9d471dd04f3d0b', FALSE, 'NativeUI · SubmitCustomBet')
  , ('748cfb9617228f44', 'client', ' starts in <color=#FFDE88>{0}:{1:00}</color>', '0391c94e6c6e8d398de3c353823cf365597b09c6', FALSE, 'NativeUI · RefreshTournaments')
  , ('e1e7e8e258fb6ee0', 'client', '#1 of {0}', '032b22faebe4bc832daeee664338f6acca872149', FALSE, 'ServerTextRules · SeriesScore')
  , ('aa1c7cc71ae730dc', 'client', '(AoE)', 'bc253868db188d01445892d8d79d9b9dd1d64f84', FALSE, 'InfoViz · MatrixRowLabel')
  , ('6de8acdb8b59a0a8', 'client', '(TBD)', '5c57672a980af63eedff96b8f9af6e0cb091f26b', FALSE, 'NativeUI · _FmtSlot')
  , ('5ffa7b8c124f7f33', 'client', '(click to change)', '7ac566c71a837d873f12e3d2542010fc455bbd3b', FALSE, 'NativeUI · RefreshCompare')
  , ('8bcb3efd4061dec8', 'client', '(loading...)', 'f28e610419f1325a85ac26b611cf6f96e8d60876', FALSE, 'NativeUI · BuildCompareCardGrid, BuildCompareMetricTable')
  , ('96e1ded8751a35de', 'client', '(menu only)', 'da41f778f7ed3ad1dbcef4e78c5582014b07121a', FALSE, 'NativeUI · FillMusicTrackRow')
  , ('2252a0cefefdafdd', 'client', '(no log content read from: {0})', 'c91246a5320a509c2bb9418d366d1f8825a028a9', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('97af61d8389c2364', 'client', '(no previous-session log yet — gets written by the mod when ROUNDS is closed cleanly, so on first ever launch this is empty)

Expected path: {0}', 'fbcf4b3dcfbb44db1dbf490faaf83040b2bdeee5', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('2f6fc17a009866ba', 'client', '(only the ladder you are wearing counts)', '98cfe8c30988e524faa54a2d94c8f2474e090cf8', FALSE, 'TitleLaddersUI · PaintDrop')
  , ('3d2ea36308963515', 'client', '(partial)', '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', FALSE, 'PostSessionReport · PartialInline, PartialTag')
  , ('e32ff3a09330d729', 'client', '(placements {0})', '4199a762764740366c8e076eb4282d07e375c215', FALSE, 'NativeUI · RefreshSession')
  , ('20e9a5200e2bf039', 'client', '(self)', 'fd48c1054b759ba859d59283ab89f4320a518966', FALSE, 'InfoViz · MatrixRowLabel')
  , ('c0b74f3dc3058639', 'client', '* <color=#C8C8C8>2nd</color> - {0}g / {1} XP / Runner Up role', '0598c8fb1fcafc544b9570ef561d84c8e7941f27', FALSE, 'NativeUI · RefreshTournaments')
  , ('41fd1756bebbcf9c', 'client', '* <color=#D4894A>3rd</color> - {0}g / {1} XP / 3rd Place role (loser of LB final)', 'd7c39a6a3788feb33bcaa658e81338bf0f548e22', FALSE, 'NativeUI · RefreshTournaments')
  , ('5deba6276fd8a551', 'client', '* <color=#FFE580>1st</color> - {0}g / {1} XP / Winner role', '905ab236d174b26450639245ec52f92ca75cc3a9', FALSE, 'NativeUI · RefreshTournaments')
  , ('3e1107290adf5ba0', 'client', '+ Add', '109b936ad40f2cfaffa7b09b8d8850665e810a4c', FALSE, 'MailUI · BuildComposerView')
  , ('be9eea5c45cb8307', 'client', '+ {0} more artists', 'ea0646b8da2ad450dbcd915b4bf8b8ad9b500d0d', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('7cf635369783ef29', 'client', '+{0} gold', '4b4df825f33c5b554ba0e5497502d215a9312846', TRUE, 'ApiClient · ReportMatch')
  , ('6a215df0cfb67121', 'client', '+{0} more', '61f571ca939a07334ed7f8c7937a84ac7580443d', FALSE, 'MailUI, SessionReportModel · AddresseeNames, FfaScoreLabel, FinalScore')
  , ('cd8f5194e9e82b41', 'client', '+{0} more bets', '304e2e4321f7e7d845773c97f6c4ca8e4c771440', FALSE, 'NativeUI · RefreshMyBetsLedger')
  , ('3ae884dee5685507', 'client', '+{0} more lines', '98736380dd8e6ae4941784841d38e82feb0bb469', FALSE, 'CompetitiveUI, NativeUI · DrawWideTooltip, FlowTipColumns, HoverCardLines')
  , ('915708e594e9c494', 'client', '- Buy one for {0} gold or {1} shards, up to {2} paid packs a day.', '533fff32a6617e4c17c878b653fb3717dff8eee8', TRUE, 'PlayerCardsUI · RefreshInfo')
  , ('fef31b7fdfed7ccc', 'client', '- Buy one for {0} gold or {1} shards. No daily limit on this account.', '8d343394988fbe4e53cd65a191f5e808fbaa2b99', TRUE, 'PlayerCardsUI · RefreshInfo')
  , ('893af1248ef639a5', 'client', '- One free pack every day (resets at midnight UTC). Claim it on the Open Packs page or with /daily in Discord.', 'fb1c88dadf57e2bca3aee232a3ad31cfe8af081d', TRUE, 'PlayerCardsUI · RefreshInfo')
  , ('f9786e977e586b20', 'client', '- Ranked wins: winning a ranked series - or a ranked FFA match - rolls a 20% chance of a pack. The same chance in every mode, whatever the score line. Earned packs wait here until you open them.', 'a1839d0465cd99b62e5ca6de094399aa18d2c159', TRUE, 'PlayerCardsUI · RefreshInfo')
  , ('f28272cc9dc14464', 'client', '- in play, score {0}', 'd35108e0802f1af496981a4d84460711ceacb8b8', FALSE, 'NativeUI · RefreshMyBetsLedger')
  , ('4ec92382f6f9cb9d', 'client', '0 in queue', '9791b16ad92597fac04aa01430afe801ee5efe2a', FALSE, 'NativeUI · RefreshQueueUI')
  , ('7540291f1a032c7b', 'client', '100g each - the hardest pay 300g, 500g or 1000g', '522d8de7ef9c668bd7130111c9ddb031294192fa', FALSE, 'InfoViz · BuildGoldSourcesLegend')
  , ('fbe88305123b5f30', 'client', '1V1 BETTING WINDOW', 'd254ab8e5f7189a6076b2a12d4502e9ec8f8a59e', FALSE, 'InfoViz · BuildBetWindow')
  , ('04f0f934efc4061e', 'client', '1V2: ONE AGAINST TWO', 'bdb3ef244fabc64235cd611c73655326395a986c', FALSE, 'InfoViz · BuildOvtFormat')
  , ('affd5382eaca97d3', 'client', '1v1 Podium', '3f4bed95c640cfa39f522b142b1ae86ed421fee3', FALSE, 'shop catalog · cosmetic name/description')
  , ('1230b280e4d1ca09', 'client', '1v1 record: series {0}W-{1}L ({2}%)   games {3}W-{4}L', 'e5af4ce71a82113afedde43f70c35c40229f887c', FALSE, 'PostSessionReport · ComposePlayerPanel1v1')
  , ('db5fee62fd6d46d6', 'client', '1v1: your opponent can take the game under the disconnect rules; the series may stay open.', '319dfc18c3c743c697453e2e356cc1a786dc6a7b', FALSE, 'EscLeaveRow · OnRowClicked')
  , ('d43beaf2e3883572', 'client', '1v2 - How It Works', '07ea834b31ed15ee1715eb167f8547bad7f65dd2', FALSE, 'ModeInfoText · (file scope)')
  , ('214528f7f4bc262d', 'client', '1v2 - UNRATED', '74e647231db3f6b2acc2c4622670eb503571289e', FALSE, 'CompetitiveUI · DrawMatchStatus')
  , ('bff6b92b6c3e21d9', 'client', '1v2 Series: Duo {0} - {1} Solo', 'a18f84a9578aa306f34357a39593e4ed8dbd4bd2', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('c79a4645d2d603b4', 'client', '1v2 Series: You {0} - {1} Duo', '21632c13e41daeae9f16c3ca8ba543066827c789', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('070cd827ff0f27b0', 'client', '1v2 as duo', '55d3549ba04984e1f35cae57af200a60c3427388', FALSE, 'ProfileCard · Render')
  , ('df3806a1ee67bdc4', 'client', '1v2 as solo', 'af0f53f17c39c17c2adcd86b083333090f0857e2', FALSE, 'ProfileCard · Render')
  , ('6c69fb2032e145c6', 'client', '1v2 lobby never filled — returning to menu. Requeue when ready.', '254e5c235d478498f37e652155097dfb8c0603b4', FALSE, 'GameStateWatcher · PollRoomState')
  , ('1d5cc2846a0a012c', 'client', '1v2 match found, but you''re in a game — removed from the 1v2 queue.', '54d0a493808ea0c5e0232a9699cbd5ed530fac16', FALSE, 'ApiClient · UpdateOvtQueuePoll')
  , ('b7cb3e6397fae3d6', 'client', '1v2 series complete: {0}', '14d9e8634fcda42da86d1e2e895ca982372d4091', FALSE, 'ApiClient · ReportOvtMatch')
  , ('b4cb6205235dd418', 'client', '1v2 series: {0}', '109cf27fd85482c00b4a6b6dbb2bbc91dcfba193', FALSE, 'ApiClient · ReportOvtMatch')
  , ('4d2f0d8391e9a531', 'client', '1v2 — Solo vs Duo', '7fc0f9fd178d5e0ff6bc432e6e4e01c715a6371f', FALSE, 'NativeUI · BuildOneVTwoTab')
  , ('63db72595c4c8d68', 'client', '1v2: leaving ends your sitting; there is no automatic forfeit.', 'abe457a4002adffed941a8e45e388126aa40c730', TRUE, 'EscLeaveRow · OnRowClicked')
  , ('4e8e19e76bc1131d', 'client', '2V2: ONE SERIES, TWO TEAMS', 'd48d8147cd24c327b544b44a62303e65da6feca6', FALSE, 'InfoViz · BuildTeamFormat')
  , ('fe8dcad5ec7ffc84', 'client', '2v2 (opposite teams)', '093a5fa19b99991b70d20413d1a4d7e5173ffddf', FALSE, 'ProfileCard · Render')
  , ('fbb9ace819dbb6d6', 'client', '2v2 - How It Works', '733e7baa95c66d1bfbac67551bcb7ada2719b69e', FALSE, 'ModeInfoText · (file scope)')
  , ('c9f4654b7eb77513', 'client', '2v2 Podium', '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', FALSE, 'shop catalog · cosmetic name/description')
  , ('63e41c49cb39356f', 'client', '2v2 QUEUE', '646aceb36023cfb5fa89dc1111b69bfd7c8ec40d', FALSE, 'InfoViz · BuildTeamFormat')
  , ('e76f8724d967828e', 'client', '2v2 Rating', 'e3fc7fd1e8476c924415195ceb0e256825cca8af', FALSE, 'NativeUI · BuildCompareBarChart, TrMetric')
  , ('a0a058f44c557587', 'client', '2v2 lobby never filled — returning to menu. Requeue when ready.', 'a623f9b68fd164cab4112acbb19b9a49034c04a4', FALSE, 'GameStateWatcher · PollRoomState')
  , ('68118d0219af41cf', 'client', '2v2: the series settles for the other team only if they have already won a game and this game has at least 2 total points; otherwise it pauses as incomplete.', 'f6768922f2f9a8ed554246089a769ac9601ad6c2', FALSE, 'EscLeaveRow · OnRowClicked')
  , ('f12a5f43bddffefa', 'client', '3/3 ready! Joining 1v2 — you are on the DUO...', '1cd566ededf6a75719a91e6e081a7e8c4114edd6', FALSE, 'ApiClient · UpdateOvtQueuePoll')
  , ('6f9b0bd67cb50128', 'client', '3/3 ready! Joining 1v2 — you are the SOLO...', 'c8bafd89a7a5719e44bc9857d22ce1be42c5a0df', FALSE, 'ApiClient · UpdateOvtQueuePoll')
  , ('20d7d7730e89c1a0', 'client', '30 FPS', '7d592751d4d4fafee4c845a55414581c35ac1dfd', FALSE, 'InfoViz · BuildGrowCurve')
  , ('444e1ff03b6093fd', 'client', '30-second previews - they stop on their own', '2b0f48724a24afff6f64901d1b39e182338465d0', FALSE, 'NativeUI · RefreshShopMusicExpansion')
  , ('6c60e1d8262b75b2', 'client', '3rd Place', 'de0ac0c428d1d09d04ae156d8084da226a9774b6', FALSE, 'NativeUI · RefreshTournaments')
  , ('c9b3f35e6c2f0e3b', 'client', '3rd place', 'ed84fabdf972de2f8c8b7de81215df65d1699071', FALSE, 'NativeUI · TrBracketProgress')
  , ('190cf3b65caa555e', 'client', '4 players', '8d8fcef4337c7ea051f3066658a0ba94861ea8b0', FALSE, 'InfoViz · BuildTeamFormat')
  , ('dc89fb90826ebe05', 'client', '4/4 ready! Joining 2v2...', '30cd3f91a4a9bd43638702fb0b3a04ee0f4306c8', FALSE, 'ApiClient · ParseTeamQueuePoll')
  , ('1107099ffb76a22b', 'client', '400 FPS', '132a8134e5e820d1aa9b05a3dde48da1d3c25f44', FALSE, 'InfoViz · BuildGrowCurve')
  , ('fdbd0ecf1244c020', 'client', '5-0 Sweeps', '1890b7a9d93676cbf2707078cbfba41e5787666e', FALSE, 'NativeUI · BuildCompareBarChart, TrMetric')
  , ('8b5f2687f21600fb', 'client', '5-0 someone with Chase', '7ac0188cbabf0fd05b7d9632be98fdd87d9a2909', FALSE, 'ApiClient · AchievementDefs')
  , ('79dfe1086dd7baf2', 'client', '5-0 someone with Glass Cannon', '432a2d747a8cecaee4d8b0bbd8d11cbd131b8264', FALSE, 'ApiClient · AchievementDefs')
  , ('192168566e2a4d06', 'client', '5-0 someone with Mayhem', '1f256a9c14d5d3d94832169123cda8455fa2d393', FALSE, 'ApiClient · AchievementDefs')
  , ('182e3a5b598b14a6', 'client', '5-0 someone with Sneaky', '2179b8cbc74315cc138f2e55ff114e7aa047c749', FALSE, 'ApiClient · AchievementDefs')
  , ('5eff08c9ac85a416', 'client', '5-0s Given / Taken', '53c3940e8df73697c97ab5edce695bfe72450d7d', FALSE, 'NativeUI · TrMetric')
  , ('26f78c1badaa8ce3', 'client', '50 ACHIEVEMENTS BY PAYOUT', '6e348c0357c64c677e6641a1ce0d64222506b9c1', FALSE, 'InfoViz · BuildAchievementTiers')
  , ('7bdae0bc3cd1610d', 'client', '60 FPS', 'aa38e5e141e048571e807299696f02731a996dd5', FALSE, 'InfoViz · BuildGrowCurve')
  , ('799b6e13c11f28dd', 'client', '7-day deadline', '06f7d0b555da9ef521a214c28fdb6bacf5ce74cc', FALSE, 'InfoViz · BuildForfeitClock')
  , ('392b2a7a739ec173', 'client', '7-track Metal / Phonk album', '680eee018198c6a159af8cf43ac17b9336e05343', FALSE, 'shop catalog · cosmetic name/description')
  , ('74ebc17cfc494570', 'client', '8-PLAYER DOUBLE-ELIMINATION FLOW', 'e9a1a8a21f79f89a312697ef0c500e016f93e43c', FALSE, 'InfoViz · BuildBracketFlow')
  , ('c4318aa1ebd2a555', 'client', '< BACK', '2fa9e5cc35fd1f7d883c58d9c8b1c429811951fb', FALSE, 'NativeUI · BuildPage')
  , ('87edb6ceb5f1e62f', 'client', '< Newer', '92199f3eb03e1fe3f9cbb34338d9f8f1f34e3b96', FALSE, 'NativeUI · BuildLeaderboardTab')
  , ('93d3e25b197db4a8', 'client', '< Older', '7c37dffe3cd849b936fb65db2ea032b4e002aa2f', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('6543831301a89f5e', 'client', '< Prev', '8e1cffbecc609338e0ea0ba1b86c0512b1bdc972', FALSE, 'NativeUI, SessionReportView · BuildAchievementsTab, BuildLeaderboardTab, BuildMyStatsTab +1')
  , ('6da1ea02cbaf11d9', 'client', '<b>2v2 Leaderboard</b>', '0f70b6db5879e40f505af9989b9439ecf621cbf5', FALSE, 'NativeUI · BuildTeamTab')
  , ('9d4c37736ff9f3b7', 'client', '<b>2v2 Leaderboard</b>  <color=#888>({0} ranked)</color>', '34daab9d40d35ab456c9e77cc9ccc2f623be684a', TRUE, 'NativeUI · RefreshTeamTab')
  , ('5d3ed3204781011a', 'client', '<b>2v2 Leaderboard</b>  <color=#888>— no completed series yet</color>', '5c9c793345b996017a4330b1ceed5fe76f937c44', FALSE, 'NativeUI · RefreshTeamTab')
  , ('3c754dc5b807de93', 'client', '<b>2v2 Ranked</b>  <color=#888>(own Glicko, friendly fire on, BO3)</color>', '923e761583bf029d9278ca8e77fa54f0d8a2ee6e', TRUE, 'NativeUI · BuildTeamTab')
  , ('29bc540f182069e6', 'client', '<b>2v2 Ranked</b>  <color={0}>({1} searching)</color>', 'ef44278d615ad0dfbd3a35bea5d164c5c9ded7d9', TRUE, 'NativeUI · RefreshTeamTab')
  , ('5075e7603c2f7d95', 'client', '<b><color=#88AAFF>Duo Leaderboard</color></b>  <color=#888>(unranked)</color>', 'ba8d07355c743611822b60ec2429d74cb614e614', TRUE, 'NativeUI · BuildOneVTwoTab')
  , ('55a19058450cfc82', 'client', '<b><color=#999999>Start (saving...)</color></b>', 'dd42a7196864aca35fa2ef4811eb1c4074641ca8', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('bdab55d88a917902', 'client', '<b><color=#FF6688>* Live 1v2 Games</color></b>', 'efd69a2faad3252122e8e13305f6d4595a8bdea2', FALSE, 'NativeUI · BuildOneVTwoTab')
  , ('03e012cf2d13a440', 'client', '<b><color=#FF6688>* Live 2v2 Now</color></b>  <color=#888>({0})</color>', 'b49834782c6f5863a88153d700c99fc2170b14a4', FALSE, 'NativeUI · RefreshTeamTab')
  , ('95ebb11b87cdd04e', 'client', '<b><color=#FF6688>* Live 2v2 Series</color></b>', '0143f1c8ceedf9023223f7101de313a2e03ea3fc', FALSE, 'NativeUI · BuildTeamTab')
  , ('b635111b3aa9f6db', 'client', '<b><color=#FFB347>Solo Leaderboard</color></b>  <color=#888>(unranked)</color>', 'a3e061c9d22e1a76cc6e8364ffb5c439c3d0125a', TRUE, 'NativeUI · BuildOneVTwoTab')
  , ('f17bfa16540b8846', 'client', '<b><color=#FFD94D>HOW IT WORKS (Async)</color></b>
  1. Sign up any time during the 7-day signup window (Discord must be linked)
  2. On lock, bracket is built and first-round matches activate
  3. Coordinate with your opponent via <b>/dm-opponent</b> on Discord
  4. Both of you enable Ranked, join any private lobby in ROUNDS, play the BO3
  5. <b>Mod records the result automatically</b> - no manual report, no room code needed
  6. Winner advances in bracket; loser drops to LB (or is eliminated)

<b><color=#FFD94D>AUTO-RECORDING REQUIREMENTS</color></b>
  * Both players must have <b>Ranked</b> toggled ON in-game when playing
  * Any private ROUNDS lobby works - tournament doesn''t force a specific room
  * Once you win a BO3 (first to 2 games), the mod advances the bracket and notifies you

<b><color=#FFD94D>SCHEDULING</color></b>
  * No fixed start time - self-paced, <b>7 days per match</b>
  * Total tournament runs up to 6-9 weeks depending on how fast matches happen
  * Miss the deadline and you forfeit that match (tracked in penalty %)

<b><color=#FFD94D>FORMAT</color></b>
  * <b>Double-elim</b> BO3 - lose once, you drop to losers bracket
  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)
  * All matches count toward ranked Elo

<b><color=#FFD94D>PENALTY %</color></b>
  * Grows when you sign up but forfeit a match by missing the 7-day deadline', '5cf6b9d8bf1d618314a6ae03d78e74233c6ebf46', TRUE, 'NativeUI · (file scope)')
  , ('2a6188ce0acf8037', 'client', '<b><color=#FFD94D>HOW IT WORKS (Sync)</color></b>
  1. Pick every start time you can make, then sign up (Discord must be linked)
  2. It locks when <b>8+ players agree on one time</b> - decided <b>2 days before</b> the default start, so you always get 24h+ notice; players who can''t make the winning time are removed (no penalty)
  3. <b>Have ROUNDS open at start time</b> (main menu is fine - no tab-sitting needed)
  4. Mod <b>auto-connects you to your opponent</b> - no queue, no invites
  5. Play BO3, bracket advances automatically - <b>plan for a couple of hours total</b>

<b><color=#FFD94D>BETWEEN MATCHES</color></b>
  * ~7 min breather before each of your matches after round 1
  * Both players press <b>Play Now</b> to skip the break and start early
  * Show up within 10 min of your match or forfeit
  * Bracket hidden until start (no scouting your first opponent)

<b><color=#FFD94D>FORMAT</color></b>
  * <b>Double-elim</b> BO3 (first to 2) - losing once drops you to the losers bracket
  * Matches run in parallel: your next match schedules the moment its players are known
  * Top seeds get byes when fewer than 16 sign up
  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)
  * All matches count toward ranked Elo

<b><color=#FFD94D>PENALTY %</color></b>
  * Grows when you sign up but no-show at match time
  * Lower penalty = priority if more than 16 sign up', '630d5fe7b6a1288b2d2def76fbc528dd95a739c4', TRUE, 'NativeUI · (file scope)')
  , ('3fa2e1d1b7b13d65', 'client', '<b><color=#FFD94D>PRIZES</color></b> <color=#888>(at {0} players)</color>', '1681c1ad66e8b53940d57f71ec05cd6f6cbd6f17', FALSE, 'NativeUI · RefreshTournaments')
  , ('185ea4043021ff08', 'client', '<b><color=#FFD94D>PRIZES</color></b> <color=#888>(at {0} players, live)</color>', '24a4b3b2e962abfb33dbb275b5574999fa2a3c1e', FALSE, 'NativeUI · RefreshTournaments')
  , ('4b40a37c0f75e082', 'client', '<b><color={0}>{1}</color></b>  <color=#888>(unranked - loading...)</color>', '5d0cfe13e0112ed053a0d334953c1a598ef0f059', TRUE, 'NativeUI · FillOvtRoleBoard')
  , ('c014368fb258c367', 'client', '<b><color={0}>{1}</color></b>  <color=#888>(unranked - no games yet)</color>', '964083dde3b9086daa465f67dd2f060fef1afe91', TRUE, 'NativeUI · FillOvtRoleBoard')
  , ('e7f929f2fc14ab9b', 'client', '<b><color={0}>{1}</color></b>  <color=#888>(unranked - {2} players)</color>', '37e09b5ca64b2263c149efe2e584442a59ccf277', TRUE, 'NativeUI · FillOvtRoleBoard')
  , ('8f40cf6222ae1cf0', 'client', '<b>Admin Panel</b>  <color=#888>(admins only)</color>', '3cca33596bd837c6a34cb127d9af34df91da4a62', FALSE, 'NativeUI · ApplyAdminPanelScope, BuildAdminTab')
  , ('0a1bc5e0ce656d63', 'client', '<b>Bet on Live FFA Lobbies</b>', '0d848de7a26cd51381e47b52443df86b1a53b5d2', FALSE, 'NativeUI · BuildFfaTab')
  , ('5adf29d4453a8219', 'client', '<b>Chat Moderation</b>  <color=#888>(your granted channels only)</color>', 'def1a1de4c1e2ca98fdc5a3f1bce6342a4492543', FALSE, 'NativeUI · ApplyAdminPanelScope')
  , ('edad4bf793d2498e', 'client', '<b>Custom 1v2 Lobbies</b>', '9296b97e93a753fb9f80a32d3fcba31eeafa3d14', FALSE, 'NativeUI · BuildOneVTwoTab, RenderHostLobbySection')
  , ('e6683e03f8794bf3', 'client', '<b>FFA - FREE-FOR-ALL (3-10 players)</b>', 'cd8b5dda58ee78702ca1791aad1288a0c39510ff', FALSE, 'NativeUI · BuildFfaTab')
  , ('d62cb7c9d2512266', 'client', '<b>FFA Leaderboard</b>', '40f3cae7c67fa3d1910d78e9c52b02d732be942d', FALSE, 'NativeUI · BuildFfaTab')
  , ('7d817ff529af1f06', 'client', '<b>FFA Leaderboard</b>  <color=#888>({0} ranked)</color>', '58139b6f61ab48387be44eb29431ba6209e10f4e', TRUE, 'NativeUI · RefreshFfaTab')
  , ('45cc733ef5540b01', 'client', '<b>FFA Leaderboard</b>  <color=#888>- no ranked FFAs yet</color>', 'a33b19409eb5e945af5ac6000a7f968edb0f0d95', TRUE, 'NativeUI · RefreshFfaTab')
  , ('951b9b16227f135f', 'client', '<b>Game logs (tail)</b> — included with your report when the box is checked.', 'cd95b4632dc60bdec486a3611eed91c56d5736bb', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('7e2771250479b7a2', 'client', '<b>Hosted 2v2 Lobbies</b>', 'aadbc1edbe90d83acf1c91d89ddf8fe85845bdc4', FALSE, 'NativeUI · BuildTeamTab, RenderHostLobbySection')
  , ('68ffce8bbb14ce05', 'client', '<b>How to reproduce?</b> <color=#888>(optional)</color>', '8f377602579db81b3a6824ecb1e4175b54dbc1fd', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('aff01af270318894', 'client', '<b>Open FFA Lobbies</b>', '69436f4e093ec1bfbb5f78046f3ce964cfcafba9', FALSE, 'NativeUI · BuildFfaTab')
  , ('b62d5ca0a5ad78ca', 'client', '<b>Open FFA Lobbies</b>  <color=#888>(none right now)</color>', 'b8aaf38308c25d47561a9defc03824a7d17b61d8', FALSE, 'NativeUI · RenderFfaLobbySection')
  , ('b5d62dcee8924655', 'client', '<b>Open FFA Lobbies</b>  <color=#888>({0})</color>', '1780f3134b55989a3e3145349cc2a4097f142ddd', FALSE, 'NativeUI · RenderFfaLobbySection')
  , ('55f3321c97728ac1', 'client', '<b>Recent 1v2 Games</b>', '57c6442982f612283de11e71c840a251ded99dc0', FALSE, 'NativeUI · BuildOneVTwoTab')
  , ('cd0163493ecac4fa', 'client', '<b>Recent 1v2 Games</b>  <color=#888>({0} series)</color>', 'c0dafbb700e42748454366596685977879f28bbe', FALSE, 'NativeUI · RefreshOvtRecent')
  , ('5215fcf61178e3e3', 'client', '<b>Recent 1v2 Games</b>  <color=#888>- none yet</color>', '54e706d52a91eaf6738072af7af1ea59473bdfc0', FALSE, 'NativeUI · RefreshOvtRecent')
  , ('7a1462b739334b88', 'client', '<b>Recent 2v2 Series</b>', '99c2bd9a81258b1b9643ff1b723870cef5e1fc54', FALSE, 'NativeUI · BuildTeamTab')
  , ('585c940fef29ab1e', 'client', '<b>Recent 2v2 Series</b>  <color=#888>({0} total)</color>', '48f98d176879695850180ebf56c1e062da18d1be', FALSE, 'NativeUI · RefreshTeamTab')
  , ('fd870b0522ab9f12', 'client', '<b>Recent 2v2 Series</b>  <color=#888>— none yet</color>', '3f7a0932c8fe2823698affa487d5b60a9aceba20', FALSE, 'NativeUI · RefreshTeamTab')
  , ('9d033a263ddf51d5', 'client', '<b>Recent Casual FFAs</b>', '1f710e4b0e713951c4646e1f85cdf30df5e941b9', FALSE, 'NativeUI · BuildFfaTab')
  , ('d0083333e06cfaf1', 'client', '<b>Recent Casual FFAs</b>  <color=#888>({0} total)</color>', 'ef69c20bdd62dbc159ca5c52064ba8b5eed1773e', FALSE, 'NativeUI · RefreshFfaTab')
  , ('3d37b7ba02553145', 'client', '<b>Recent Casual FFAs</b>  <color=#888>- none yet</color>', 'aed453ecdecb7d986af81013f773383e4624f25b', FALSE, 'NativeUI · RefreshFfaTab')
  , ('ff02bb99d53e2f5d', 'client', '<b>Recent Ranked FFAs</b>', '8c633183bfd632ab1fe76c7dcc732e7d831f646a', TRUE, 'NativeUI · BuildFfaTab')
  , ('ef2ee75085947329', 'client', '<b>Recent Ranked FFAs</b>  <color=#888>({0} total)</color>', '18c28fcab9c64bd35ce03e8e016602b6795ecc8f', TRUE, 'NativeUI · RefreshFfaTab')
  , ('687c1dcb181ecf45', 'client', '<b>Recent Ranked FFAs</b>  <color=#888>- none yet</color>', 'c655a4e371ec3c52666e977042a3cc98eb9de6dc', TRUE, 'NativeUI · RefreshFfaTab')
  , ('ce72d18e916b01cb', 'client', '<b>Start (need {0})</b>', '2ae94b94fa1cb8b9cea06583b16fb473b7cf95e1', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('f095c13abf6b5329', 'client', '<b>Start Game ({0}/{1})</b>', '60e8be4e971f1fedfeacc23100c7c7185b92ab25', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('e93c7974349c8d09', 'client', '<b>What happened?</b> <color=#FF9966>(required)</color>', '8500bc4d384b9f21e290610ab0c760e7ca028ba7', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('5b4560f5fd3ca74d', 'client', '<b>You</b>', 'dbc49e21b64e298c965187ecea7dcf1bcdd62263', FALSE, 'NativeUI · BuildMultimodeSeriesLine')
  , ('822906cf983c697d', 'client', '<b>Your 2v2 Lobby</b>', '738d870e4c7f52b34268d8ae94969c6d08a7b2b0', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('f9485d399e197e12', 'client', '<b>Your Custom 1v2 Lobby</b>', '7a582054703f8b7cc36a4b682f78cc6cd773c259', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('09deebcae22bfb20', 'client', '<b>Your Lobby</b>  <color=#888>({0}/{1} - host starts at {2}+)</color>', '6090fa2a628d137cb9870d67b69616b188ef5dd3', FALSE, 'NativeUI · RenderFfaLobbySection')
  , ('b7f586245cf37349', 'client', '<b>vs You:</b> <color={0}>{1}W - {2}L ({3} games)</color>', '49c3d520a6cf011fc93ce62b10afbe9e6bdfaec3', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('4c68914b7aabfcfa', 'client', '<b>{0} Performance patches</b>  {1}', 'bf002f47ea0d0549603ae705e59cb5f1a515bf3e', FALSE, 'NativeUI · PaintPerfHeader')
  , ('334e17a45a59367f', 'client', '<b>{0}</b>  <color=#888>(empty)</color>', 'fd96da4284df8057fd8a9e8c7ed13ea5d22dbdc0', FALSE, 'NativeUI · RenderTeamQueueSection')
  , ('510bbb2d5c28e2ed', 'client', '<color=#00FF00><b>WON</b></color> {0}-{1}', '23e6796a6dd6767a12be4b513543ebf8e5e4abb7', FALSE, 'NativeUI · RefreshTeamTab')
  , ('e08bba79fc405bb1', 'client', '<color=#00FF00>Linked to Discord</color> ({0})', '0be65425d5df8a3381741d8b1359dde94d3a039a', FALSE, 'NativeUI · RefreshHomeTab')
  , ('3e892a1a275b71e0', 'client', '<color=#00FF00>Linked to Discord</color> <color=#888>(Click to show)</color>', '0052bf33f0e0a2fca12bc8925dbe2a6505d7419b', FALSE, 'NativeUI · RefreshHomeTab')
  , ('ea83337993a45755', 'client', '<color=#00FF00>WON</color>', '585d7397eb695e72f42e0bacc337f5de1767d40a', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('e494424cf053f992', 'client', '<color=#00FFFF>{0}</color>  - type <color=#FFFFFF>!link {1}</color> in Discord', '4b8ca35da1156502e8dd33e7421caeb030b28894', FALSE, 'NativeUI · SetLinkCode')
  , ('7cabc97b10238e5c', 'client', '<color=#44AA44>Up to date</color>', 'd8a969615148d5bc5db796e2f895f39763583cb0', FALSE, 'NativeUI · RefreshVersionStatus')
  , ('e11202f27fe397f2', 'client', '<color=#44FF44>Close ROUNDS to apply update</color>', '5591a9faf2a275842c5e3b9d932091abfda415ee', FALSE, 'NativeUI · RefreshVersionStatus')
  , ('b5b807325a34b3cc', 'client', '<color=#556270>(hover for build)</color>', '247cd5176a08b0fe804ef6651f50ce7418738f99', FALSE, 'NativeUI · BuildFfaCardsText')
  , ('b5e388fb1a5546cb', 'client', '<color=#556270>(hover for builds)</color>', '67096273a37ebf0589fea38677ecd8860fdd8c95', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('dce4ad480ae43043', 'client', '<color=#60FF60>ready</color>', '2bbc859c18b7e60ec5e715d9926640a754581a14', FALSE, 'NativeUI · RefreshTournaments')
  , ('23413e7976be2a3e', 'client', '<color=#60FF80>both ready - connecting...</color>', '8d611692d8b52d83204742f22d1b13e159ad11cd', FALSE, 'NativeUI · RefreshTournaments')
  , ('ebb00fa13d937164', 'client', '<color=#664444>-> {0} bet {1}g on {2} - lost</color>', '6d963ba9ef802936517c691221c2197fe179c635', FALSE, 'NativeUI · BuildMultimodeSeriesLine')
  , ('493df93f52bd5e55', 'client', '<color=#666>(click to copy)</color>', '185f137dbfc6210724da22e7a90deda846e8ce92', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('abcc1b9798063498', 'client', '<color=#666><i>Hide yourself here: Settings -> Privacy & account -> Appear offline.</i></color>', '50d89b28cdcc47687115d6893c9100e66a07d954', TRUE, 'NativeUI · RefreshHomeTab')
  , ('a463905a21f99458', 'client', '<color=#666><i>No live ranked series right now.</i></color>', 'c37ace37eb278bbb801475948e3df81925c3dcc0', TRUE, 'NativeUI · BuildLeaderboardTab, RefreshLiveSeries')
  , ('b61224b42301b40f', 'client', '<color=#666><i>no cards</i></color>  <color=#556270>(hover for build)</color>', '8ecd9036dd14f3a84676271dd4f030ac6b952da4', FALSE, 'NativeUI · BuildTeamCardsColumnChips')
  , ('5c528222367454fd', 'client', '<color=#666>no cards</color>', '568602877de41bc9414cac985c77b8c26ac84eaa', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('ccd027309181f18b', 'client', '<color=#666>no cards</color>  <color=#556270>(hover for build)</color>', '814301af4370b262d48271f2a15829bdadc2ea59', FALSE, 'NativeUI · HistoryCardCellText')
  , ('42814ecc2b658aff', 'client', '<color=#666>—</color>  <b>Game {0}</b>: {1} {2}-{3}', 'c914a0dd6b7a82aa21bbc158bcd04239601f6345', FALSE, 'NativeUI · RefreshTeamTab')
  , ('a6a35197bee61edc', 'client', '<color=#667788>none held</color>', '7a9481236d37894202154793757d34325a34387c', FALSE, 'NativeUI · BuildFfaCardsText')
  , ('4414a7cdf1b7c552', 'client', '<color=#667788>none</color>  <color=#556270>(hover for build)</color>', '2970dc47f265c37c94385dc2d498029504664b35', FALSE, 'NativeUI · BuildFfaCardsText')
  , ('c7e1faeda4aff802', 'client', '<color=#667788>series:</color>', 'd0fde2869f5db199bb2e6fc56d6ec641b7e9ff32', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('b3c7d24dc7d7d5f0', 'client', '<color=#6677AA>You:</color>', '5e3ff648c349f07d096defc5f364a9bf02be7bd1', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('b691e2adfcfdea9f', 'client', '<color=#667>click an achievement to see who earned it</color>', 'b4e3df6ec7261496a4f2f8ee7f590f710f05d3e6', FALSE, 'NativeUI · BuildAchievementsTab')
  , ('accb99d11995227c', 'client', '<color=#66CCFF>Downloading...</color>', 'f79172f515472bfbdcf012289d572cba03244088', FALSE, 'NativeUI · RefreshVersionStatus')
  , ('590709f4939b85b6', 'client', '<color=#66CCFF>Searching for {0}...</color>  <b>{1}/4</b>', '07bd257b33b6b7dae2457c8b3cfe4b5949484973', FALSE, 'NativeUI · RefreshTeamTab')
  , ('225de4a62c9c9a2c', 'client', '<color=#66CCFF>searching</color>', '37dd9921db9da397984723b18a5138c9c8013b18', FALSE, 'NativeUI · RenderTeamQueueSection')
  , ('d42e053f6b13ff64', 'client', '<color=#66DD66>APPROVED</color>', 'bbcb83eae9983000e8f0f516b4318bb399bf67be', FALSE, 'NativeUI · RefreshArtistTab')
  , ('fb1a4b3a5f4e1d5d', 'client', '<color=#66DD66>APPROVED</color> <color=#888>(rev {0} awaits a mod update)</color>', 'dc2a54c6ab19d126c840dfe2b19216c508821c64', FALSE, 'NativeUI · RefreshArtistTab')
  , ('250dcc5547b47d05', 'client', '<color=#66DD66>Game starting! Joining as player {0} of {1}...</color>', 'a337367fad680421586b92e5238764e639863dbf', FALSE, 'NativeUI · RefreshFfaTab')
  , ('b84788a98e84201d', 'client', '<color=#66DD66>In FFA match.</color>', 'a7e2659bd9f21d6579b628236a12968cdc7e4d87', FALSE, 'NativeUI · RefreshFfaTab')
  , ('04ea724f3226d3a6', 'client', '<color=#66DD66>In a 1v2 match.</color>', 'f232d32135d7a1a9257b868b63a89efd1ef8d344', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('0d7cc210312198ae', 'client', '<color=#66DD66>Match found! Joining…</color>  <color=#FFB347>{0}</color> <color=#888>vs</color> <color=#88AAFF>{1}</color>', '34fa10fede90cb20a1ddf3da58a43404436557eb', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('65a32e66177882b6', 'client', '<color=#66DD66>Your lobby is ready.</color> {0} in - press Start, or wait for more (up to {1}).', '8bfb3dcc1c64782da5cc10b57aa42cab47e08f32', FALSE, 'NativeUI · RefreshFfaTab')
  , ('b3eb79e601bb099b', 'client', '<color=#66FF88>Online now</color>', '1b796b9e660114c40780b5f70ed1977413c71cbd', FALSE, 'NativeUI · RefreshHomeTab')
  , ('0a7da31bb71a460a', 'client', '<color=#777>(bet placed)</color>', '86af06d8ad49429bceb0be6f1616d05dda47ec9f', FALSE, 'NativeUI · RenderFfaBettingSection')
  , ('3961b1463268849f', 'client', '<color=#777>(hover for score graph)</color>', '730b09723eeadb523d9b0aa6dacbb50480fb8ec0', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('6b912c60e510d768', 'client', '<color=#777>(your lobby)</color>', '13c8a3c88fb5be85116ae4e6a94a3dc35feeb24e', FALSE, 'NativeUI · RenderFfaBettingSection')
  , ('54c5a179c0572f49', 'client', '<color=#777><i>hover the panel and scroll for more</i></color>', 'b838ddc26b3bb55f1248d3403aa57b22d0d8f271', FALSE, 'NativeUI, NativeUI.Settings · BuildCompareTab, BuildLeaderboardTab, BuildSettingsChrome')
  , ('44a9ae7c639fd2e4', 'client', '<color=#777>rounds on the left - each step is one point scored</color>', '0b847feca26a4748195b25eedff430653aebabb0', FALSE, 'CompetitiveUI · PaintScoreGraph')
  , ('f212ef10a93e2dcd', 'client', '<color=#777>{0} activated / {1} successful</color>', '68fe6a69bfba20998445f3f4a9bd8baecc77a336', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('0dbcd58642eb2db9', 'client', '<color=#777>{0} activated · {1} successful · {2:F0}%</color>', '4b634e4f33c03a784c221f8526c5e6bdd335e67a', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('cf1c3f9f78d8e96b', 'client', '<color=#777>{0} dmg / {1} blocks</color>', 'd264b77b8a1c62b1fabaf5152b21d294d589c9bd', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('fc4c40059bf20748', 'client', '<color=#777>{0} dmg taken · {1} successful blocks</color>', '3784f0862c740244742696aceeb08ec3e94cae1e', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('21e8b9f068f73353', 'client', '<color=#777>{0} fired / {1} hit ({2:F0}%)</color>', '1f835b9f9fadc2c1b294ebb286b32f3d73a2c2ae', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('2925eb5deba3c50f', 'client', '<color=#777>{0} fired · {1} hit · {2:F0}%</color>', '832d8562776bcde7b674087bf039a72089be6953', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('1c5acd21065ca4ea', 'client', '<color=#7788AA>-> {0} bet {1}g on {2} - pending</color>', '3c8ec61681d4250b1d3d48235800cfb3557f2f9b', FALSE, 'NativeUI · BuildMultimodeSeriesLine')
  , ('8212f50c48a591d2', 'client', '<color=#7788AA><i>search cards...</i></color>', 'e86e5680239707b58a5b4998249bc5aae1a05f1e', FALSE, 'CompetitiveUI · DrawCardStatsSearch, DrawCompareSearch')
  , ('503299a3e558e34f', 'client', '<color=#7788AA><i>search players...</i></color>', '87f809301f9f7b489483cdf2291ee0be17560216', FALSE, 'CompetitiveUI · DrawCompareSearch, DrawHistorySearch, DrawLeaderboardSearch')
  , ('e12cdd99b210ce07', 'client', '<color=#7788AA><i>search...</i></color>', 'b86f3dee9b32aff1281ab7302c8f65308a6457fe', FALSE, 'CompetitiveUI · DrawInfoSearch, DrawPickerSearch')
  , ('6e66d7d7cab7c6c0', 'client', '<color=#7788AA><i>subject</i></color>', 'a83c8ce6d2d11546990d6520e589bb3fbb661c01', FALSE, 'MailUI · DrawComposerFields')
  , ('fcf20a7af023ab9b', 'client', '<color=#7788AA><i>write your message... (plain text, no formatting)</i></color>', 'be046cfb0183635a90ad04d5a776d4c198233fb2', FALSE, 'MailUI · DrawComposerFields')
  , ('8311a697b4bf1aac', 'client', '<color=#7FD4FF>1v2 History</color>', '4b40a0907e3234e0cc2fe724d87f31cc5cbe9cdc', FALSE, 'NativeUI · BuildPlayerModeHistoryText')
  , ('e4e808986976f25b', 'client', '<color=#7FD4FF>1v2:</color> {0}W/{1}L', '5223c763248dbdfa305993651bdeeca05fe2509e', FALSE, 'NativeUI · RefreshSession')
  , ('30d4db904ff26b1f', 'client', '<color=#7FE8C3>=  CHARACTER COSMETICS  =</color>', '710f35c028bf084903e82e5b9b737dd62abd1136', FALSE, 'NativeUI · BuildShopTab')
  , ('825271b6ccbea3da', 'client', '<color=#7FE8C3>Every signup past 8 grows the pot - 16 players doubles it! (now: {0})</color>', '96ee7b1438ffe3f13aa82d7096953dfa1ad77687', FALSE, 'NativeUI · RefreshTournaments')
  , ('db7dd81ac45d3a49', 'client', '<color=#7FE8C3>Max pot - 16 players!</color>', '1933cbafaed52c8b035f1a5e2855631e4afbee83', FALSE, 'NativeUI · RefreshTournaments')
  , ('bd560f79298369cd', 'client', '<color=#7FE8C3>Sales log</color>  <color=#888>(every purchase and gift, newest first - gifts earn 0)</color>', '803af7293eaf4ae774d92dd3026c7a8ff205d355', TRUE, 'NativeUI · BuildArtistTab')
  , ('afcf70b297ca5d26', 'client', '<color=#888>(click the row to preview tracks)</color>', 'c64430c93ebef3dbe560293a486c6b3b5785e504', FALSE, 'NativeUI · ApplyShopRow')
  , ('c7cd96f7c337c372', 'client', '<color=#888>(equip in the character editor)</color>', '89e542520d4d04153f795491a4d854749727701f', FALSE, 'NativeUI · ApplyShopRow')
  , ('a0a84bb37b74480c', 'client', '<color=#888>(in progress)</color>', '4623a6a3410fc70b8cc383dcf0a6cb4c4f933517', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('33495944a2734539', 'client', '<color=#888>(last approved placement stays active)</color>', '4cd18a046f43841d4fe50b03aa465f0e26bc5d92', FALSE, 'NativeUI · RefreshArtistTab')
  , ('e0e0c331814389df', 'client', '<color=#888>(no cards recorded)</color>', 'ac3762a2c7bae4fb6e1b807c57b2541f2147e9eb', FALSE, 'NativeUI · BuildRecordHoverBody')
  , ('975079e2e5226011', 'client', '<color=#888>(none right now)</color>', 'cd2e09e54b4c40bc15a7973607cf97f92f11742f', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('8424897272503312', 'client', '<color=#888>(solo extra pick)</color>', '227fdfe98dd6eb33929a1358e01817cbd13f6e83', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('30b450ba41d7ad92', 'client', '<color=#888>+pick</color>', '92738744d5b41f06fd27010c32808fb496c82066', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('d2522009e9b6df5d', 'client', '<color=#888>+{0} more live games - see the mode tabs</color>', 'b3f7940e3a2e53a3c6998385bb3eb9ecb181b4a2', FALSE, 'NativeUI · RefreshLiveSeries')
  , ('fe7ef6236573f7e7', 'client', '<color=#888>+{0} more</color>', '65658659a09127dac71302da8c2c0e403214484f', FALSE, 'NativeUI, PostSessionReport · BuildLobbyMemberLine, ComposeFfa')
  , ('8e209f74638dbafd', 'client', '<color=#888><i>(This card''s effect isn''t a number - read the card description above.)</i></color>', '23254fd9dd2f5f8dc320a34ecb2cfaea96d2eb49', FALSE, 'NativeUI · ShowCardPreview')
  , ('ac53cb1d4b497deb', 'client', '<color=#888><i>Grab them in the Shop tab.</i></color>', 'd64a6ab3ed242d778aac287190982a900e112064', FALSE, 'NativeUI · RefreshHomeTab')
  , ('ac2f3c9d04c1d307', 'client', '<color=#888><i>Hidden</i></color>', '29b2cfb1815a45fe5f93cce227df3453f78ad1dd', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('85126096ca57c79a', 'client', '<color=#888><i>Loading match history...</i></color>', '46a5af2585c769ed0e95767115d47c4374011355', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('0d948bf9a085981a', 'client', '<color=#888><i>Loading release notes...</i></color>', 'c2204d8738de607fe6ddbc5f3239ca27d17fb915', FALSE, 'NativeUI · BuildHomeTab, RefreshHomeTab')
  , ('f472c39b32f507f1', 'client', '<color=#888><i>No messages yet. Messages sent here or in #scr-discussion on Discord show up here.</i></color>', 'cabff10c1e2283f066cd7894bde61a83efc05eb4', FALSE, 'NativeUI · BuildHomeTab')
  , ('174c36bafbe2956f', 'client', '<color=#888><i>No sales yet.</i></color>', 'c651043d9c918c7ea08eaa0e45592b82520f6d5e', FALSE, 'NativeUI · BuildArtistTab, RefreshArtistTab')
  , ('6f4fe42459b183a0', 'client', '<color=#888><i>No stat data available for this card.</i></color>', 'ce21b94e03ec948163cb7c43df1ca15c2aaa6415', FALSE, 'NativeUI · ShowCardPreview')
  , ('86aba1ed8b31ffb9', 'client', '<color=#888><i>Nobody has earned this yet. Be the first!</i></color>', '9c70ce915a157bec860acbb486261f358ee50449', FALSE, 'NativeUI · RefreshAchievements')
  , ('5fdeeb0b9c1ec66a', 'client', '<color=#888><i>Nobody visible right now.</i></color>', '6b1ea4c0eeeb654cbd9aa79535b60b966080d110', FALSE, 'NativeUI · RefreshHomeTab')
  , ('6832a0eedc02a7c1', 'client', '<color=#888><i>None yet.</i></color>', '2448f40ccec1a30c81bf740ffe85b7d30837e2d4', FALSE, 'NativeUI · RefreshHomeTab')
  , ('94db66918d546008', 'client', '<color=#888><i>Release notes unavailable right now.</i></color>', '631013e0362fd55c596915e3fe91b9e867fc6537', FALSE, 'NativeUI · RefreshHomeTab')
  , ('2d17a111ecfa7be7', 'client', '<color=#888><i>Update of {0} - grab them in the Shop tab.</i></color>', '2fe8b21054cd17ebd00a292566d04d71f3148cde', FALSE, 'NativeUI · RefreshHomeTab')
  , ('02481d4bc4f0e5ee', 'client', '<color=#888><i>Updates of {0} & {1} - grab them in the Shop tab.</i></color>', '69a9c6e275a41f86330f6c8e4513a47b83f6625e', FALSE, 'NativeUI · RefreshHomeTab')
  , ('2b2a2115ec5b8f48', 'client', '<color=#888><i>v  Scroll down for leaderboard + recent series  v</i></color>', 'a21ec038b09f098ffcc32f78e8bb80305b6f0ddb', FALSE, 'NativeUI · BuildTeamTab')
  , ('43816ca8b7bb08d4', 'client', '<color=#888>Agree a time in Discord (or /dm-opponent), then play a private lobby - it counts automatically.</color>', 'a8bfbbfc85c2aca6f2a6fddb1679e2f8b12ff417', FALSE, 'NativeUI · RefreshTournaments')
  , ('bce10b6d42caa61d', 'client', '<color=#888>Discord:</color>', 'c34d4b466d6b20a538710fabf9f43f8d410d46fb', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('885802821e8af4f4', 'client', '<color=#888>Leaving queue…</color>', '875ba602929e490fa025f4fab86ce7d1bcaa9674', FALSE, 'NativeUI · RefreshOneVTwoTab, RefreshTeamTab')
  , ('29956eb093b192eb', 'client', '<color=#888>Leaving...</color>', 'fcff73f47ee10219a3876754afb842f262ea44cb', FALSE, 'NativeUI · RefreshFfaTab, RenderHostLobbySection')
  , ('4cd4d837219a7f6f', 'client', '<color=#888>Loading earners...</color>', '0de89b2afc192a9c7edfa75e67da4482ff3c9fc7', FALSE, 'NativeUI · RefreshAchievements')
  , ('0dcd7fa5fff1e6d4', 'client', '<color=#888>Loading members...</color>', 'c7c0a44eb576ee3f9ebbe9436946082e06cba1ec', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('a11c16b210120f55', 'client', '<color=#888>Loading…</color>', '2552c92999af87111790f7a90d41be061c01da98', FALSE, 'NativeUI · BuildTeamTab')
  , ('94d8eeb7835cacb2', 'client', '<color=#888>Mod: <i>not detected</i></color>', '988e5666d9c440209aa8a616f309be4c3d8d7c7b', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('fae2abbd1d51f67d', 'client', '<color=#888>Mod:</color>', 'c40c6b2fcce0e40b069812932bfe25f200cac3ab', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('3f8729c67d14be5f', 'client', '<color=#888>No custom 1v2 lobbies — create one and invite your friends!</color>', '87b89a0c0a87f85517e612bccb1eea6d502412b6', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('712e95e3e33f7a8d', 'client', '<color=#888>No hosted 2v2 lobbies — create one and invite your friends!</color>', 'f7c6206a8abf917b8d099d0e6ed4a44c6f66e48b', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('08e57eb5ea26362e', 'client', '<color=#888>No items assigned to you yet - art gets wired to your account when it ships in a mod update.</color>', '17ac025c7e380c8abcd7f65f12ff482a44d57839', FALSE, 'NativeUI · RefreshArtistTab')
  , ('bad2106299b6b752', 'client', '<color=#888>No one in {0} right now.</color>', 'f4364485a44965c7c825bb1e59144457e7b4ec5e', FALSE, 'NativeUI · RenderTeamQueueSection')
  , ('c748ad775e67676a', 'client', '<color=#888>No open lobbies — create one and invite players on Discord!</color>', 'feea14636f4f98ce478d1447ce2614d4b8cf8231', FALSE, 'NativeUI · RenderFfaLobbySection')
  , ('7b3594ded210db30', 'client', '<color=#888>Pick <b>Search Random</b> for ranked matchmaking, or host a 2v2 lobby below to choose teams.</color>', '5f059e9dff7712f1d53c443cc1a341a060e3a29f', TRUE, 'NativeUI · RefreshTeamTab')
  , ('68aa309ca4b16cef', 'client', '<color=#888>Ranked by default - the host can switch a lobby to Casual before starting.</color>', 'feac8a420c0e222781e205e9983eddbc6fa462c3', TRUE, 'NativeUI · BuildFfaTab')
  , ('ee3d06226c9c2b97', 'client', '<color=#888>Select 2+ players with ranked history to compare Elo.</color>', 'c2dad79a078f8c3687a8d89f0aefb84a1d2cf78c', TRUE, 'NativeUI · BuildCompareGraph')
  , ('d71f03de6cb4e7fa', 'client', '<color=#888>Select 2+ players with rated FFA history to compare FFA Elo.</color>', '175f5e107a8f5d07e827fc11096c4a76d25bd3f2', FALSE, 'NativeUI · BuildCompareGraph')
  , ('27cea71fb855ef6e', 'client', '<color=#888>Solo Extra Initial Pick: the solo gets one extra card in the game''s FIRST draw only. The HOST''s toggle decides it for the match.  <color=#7FDF7F>Active in-game</color> <color=#888>— the solo''s first pick screen deals twice.</color>', '8b6fde081373c9db70aab9253e5979c308cdc9e7', FALSE, 'NativeUI · BuildOneVTwoTab')
  , ('fd4d752a09b135c7', 'client', '<color=#888>Steam ID:</color>', 'c33489a0e5e55f1129255554ed18ba2ac2a49972', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('cc411aefa047c15a', 'client', '<color=#888>click anywhere to close</color>', '9a8cae38683e4f3e98c1303af44231665436fcbc', FALSE, 'NativeUI · ShowCardPreview, ShowInfoPopup')
  , ('02c6d926d2a73a47', 'client', '<color=#888>sold {0}, gifted {1}</color>', '06d342169002a46b2dcd8b255afee37003292dad', FALSE, 'NativeUI · RefreshArtistTab')
  , ('e6e6c58af19307ec', 'client', '<color=#888>{0}% pen</color>', 'bac173ecd4e58b18541d82f573f1faaa20dff16c', FALSE, 'NativeUI · RefreshTournaments')
  , ('81d1594bd1091bc2', 'client', '<color=#888>{0}</color>  <b>{1}</b> bought <color=#C8A2FF>{2}</color> for <color=#FFD94D>{3}g</color>  <color=#7FE8C3>+{4}g to you</color>', '07a8c3315325a7a113f2f1fc08be063c770e592e', FALSE, 'NativeUI · RefreshArtistTab')
  , ('357effe73805facd', 'client', '<color=#888>{0}</color>  <b>{1}</b> received <color=#C8A2FF>{2}</color>  <color=#888>(gift)</color>', '68d71224c58674c112890a7fb61d7191d171f9bc', FALSE, 'NativeUI · RefreshArtistTab')
  , ('86369abfe6bb0dd4', 'client', '<color=#8899AA>1 - 2,000 gold</color>', '8b5f2ed9c71b4f4d439f18f5e87d00c642ab65a5', TRUE, 'CompetitiveUI · DrawCustomBetPrompt')
  , ('c8e19ea38805cd06', 'client', '<color=#8899AA>How long are you searching? (shown to players as an expiry)</color>', '9a62a068439228473cef75e0adeea9dea9ffe2ee', FALSE, 'CompetitiveUI · DrawLfpPrompt')
  , ('603409ff6c82dce6', 'client', '<color=#8899AA>Pings the Ranked Looking For Player role (max 1 per hour). Optional message:</color>', '40e65024e861fed568d872aea26bc7171255c387', TRUE, 'CompetitiveUI · DrawLfpPrompt')
  , ('7d8e43ec3c542605', 'client', '<color=#8899AA>Search</color>', '2a30c4721b799ef8018b7e5b23cfe8062c17039c', FALSE, 'NativeUI · BuildInfoTab, BuildLeaderboardTab, BuildMyStatsTab')
  , ('bd293819f288ad8a', 'client', '<color=#8899AA>Which modes? (pick any)</color>', 'addcf9ab680552843b3418632fa1361fde9a6581', FALSE, 'CompetitiveUI · DrawLfpPrompt')
  , ('abfd82940ef7a3a4', 'client', '<color=#88AAFF>Type to filter</color>', 'd88dae34bc051ac23f54fe476b438db01f4ea9c0', FALSE, 'NativeUI · ShowPicker')
  , ('5c7f514fa12c66ce', 'client', '<color=#88AAFF>duo won</color>', '239e7d1a3132fda68ccef926a05bad2726b26e2f', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('a1244673752f5b09', 'client', '<color=#88CC88>-> {0} bet {1}g on {2} -> <b>+{3}g</b></color>', '63e3488e68c75920133d1af00d41414a0297f6b5', FALSE, 'NativeUI · BuildMultimodeSeriesLine')
  , ('c7db091c6a0581e2', 'client', '<color=#88FF88>Equipped.</color>', '6535f8599ca23255d61a3b1d7d6ffe9e652dccb1', FALSE, 'NativeUI · CreateShopRow')
  , ('4833ee202e07d685', 'client', '<color=#88FF88>In a custom 1v2 lobby</color> <color=#888>— manage it in the panel below.</color>', '4588e08cd640a17c66b6a8513687db9e110b4869', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('691b58372128513f', 'client', '<color=#88FF88>In a hosted 2v2 lobby</color> <color=#888>— manage it in the panel below.</color>', '1035e8e76e03f4db596c6ca81bd098321002bcbd', FALSE, 'NativeUI · RefreshTeamTab')
  , ('9f0ca6838edea649', 'client', '<color=#88FF88>Profile anonymized. Data reporting is now off; past matches stay.</color>', '6a39a247e137ecd2bc8324bbc4a98b4031f0fe11', TRUE, 'NativeUI · BuildSettingsTab')
  , ('296bc9618defb504', 'client', '<color=#88FF88>Purchased!</color>', '9c6bbae583fc1361282e70616ace14758f6e8c73', TRUE, 'NativeUI, TitleLaddersUI · CreateShopRow, OnActionClicked')
  , ('bb1576b33cca66ca', 'client', '<color=#88FF88>Ready! Waiting for the other 3...</color>', '0f8972798a7dc8831f9c0d900bead94bda16f1e6', FALSE, 'NativeUI · RefreshTeamTab')
  , ('53c81b79be7734cc', 'client', '<color=#88FF88>Sent! Thank you. Filed as <b>#{0}</b>.</color>', '72eb49bc0c8d4b39c1a19186f6230c1c6173dd38', FALSE, 'CompetitiveUI · OnBugReportAnswer')
  , ('9808e56f61cea810', 'client', '<color=#88FF88>Sent! Thank you.</color>', '3d51ed996dee97375f2a58108ab35dd1d4c07482', FALSE, 'CompetitiveUI · OnBugReportAnswer')
  , ('4fa7b3c72ba1c744', 'client', '<color=#88FF88>ready</color>', 'c3c2d5bc1a17669e1feb6cc839a5c5d57c7a453c', FALSE, 'NativeUI · RenderTeamQueueSection')
  , ('3072afe4d390a26d', 'client', '<color=#88FF88>{0}/{1} active</color>', '7458c742a0778b5861439c00af14c2518f2cbbcb', FALSE, 'NativeUI · PaintPerfHeader')
  , ('4ba89801eabb9fb6', 'client', '<color=#8A8A93>Research and write-up by Spirit - ''On Damage Types and Buff Activation'', University of Rounds. Reproduced for this library with light reformatting; the testing, the findings and the voice are all his.</color>

Via thorough testing in the sandbox game mode with an additional controller player, I have catalogued which types of damage trigger which cards and buffs. The main cards in question are Scavenger, Refresh, Brawler, and Taste of Blood. Lifesteal as a character stat bestowed by numerous cards has also been considered. My results split damage into three main categories: opponent damage, self-damage, and Conditional damage. Damage to your opponent via nearly any means will trigger all cards and buffs, with the exception of specific types of Conditional damage. For various reasons, some Conditional damage, typically from block cards, will not consistently trigger Refresh but will still trigger all other buffs. Finally, any form of self-damage will always activate Scavenger, but nothing else. There are, of course, numerous oddities and exceptions.', '990d4ad856fdff5f16c07c5e047ed0c57a39649d', FALSE, 'InfoLibrary · (file scope)')
  , ('c8b2b54f6d1428bd', 'client', '<color=#8FA3B8>finished in {0}</color>', '99b4a291eaa09a27cfcd7b15a2cbe823be28816b', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('a13ace4753916354', 'client', '<color=#8FA3B8>{0} fps</color>', '794de690ee3249fb9aff60d3748de5b98a0f7388', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('200548f66e07ef64', 'client', '<color=#8FB8FF>=  MUSIC  =</color>', '8a57dce3d90f3f7cfde4e62c118f13581c918e12', FALSE, 'NativeUI · BuildShopTab')
  , ('57da6b22ccc01814', 'client', '<color=#99AAEE>Achievements:</color>', '3be3caf7dc4aae34dc52ce4e084379b3f38f3e0c', FALSE, 'NativeUI · GetAchievementText')
  , ('ba0b8dc8f6cd3b7d', 'client', '<color=#99AAEE>Ranked History:</color> <color=#888><i>no ranked series yet</i></color>', '99179cc9e74d882fb29effe8c3d16396cba0d1b2', TRUE, 'NativeUI · BuildViewHistoryText')
  , ('713c1176bf2b2b9e', 'client', '<color=#99AAEE>Ranked History</color>  <color=#888>(recent series)</color>', '12fb0ff3ca8074a3192cd4aaaf78ba614b8a4d6b', TRUE, 'NativeUI · BuildViewHistoryText')
  , ('8ab0cac8979c2a8e', 'client', '<color=#99AAEE>Recently online</color>', '4f6b1c688d3001ecdab71a07919714cf0227e832', FALSE, 'NativeUI · RefreshHomeTab')
  , ('afda56e261c5dbc8', 'client', '<color=#99AAEE>Top Cards:</color>', 'f9f7dc430ffd04be72b8680756d5da9a0e4a961b', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('a6d07574629f099c', 'client', '<color=#99B3E6>You: Hit {0}%</color>', '2e7ba4b2a8d879503b315cf86da06a7eef63cde3', FALSE, 'NativeUI · FillRow')
  , ('e91d1e0a65eab267', 'client', '<color=#99CCFF>Block:</color> -', '8f1df6a51b94dd5af8db679c73a8d3cb4f2eea32', FALSE, 'NativeUI · RefreshLeaderboard, RefreshMyStats')
  , ('bcdf653ee83bbe53', 'client', '<color=#99CCFF>Block:</color> {0:F1}% ({1}/{2})', 'c7635e1e070552f04640a363f9b42688d920f5c7', FALSE, 'NativeUI · RefreshMyStats')
  , ('ca42603f393a8386', 'client', '<color=#99CCFF>Block:</color> {0}% <color=#888>({1}/{2})</color>', '55d0abe95e269b9549242e572909ab1b7406f21c', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('3ec5a312dd9938e0', 'client', '<color=#9AD0FF>=  CURSOR COLORS  =</color>', '86a984947ac8c52cf4500bcfe364a187dd27444a', FALSE, 'NativeUI · BuildShopTab')
  , ('0fc211da8b7173b4', 'client', '<color=#9AD0FF>Your submissions:</color>', '72f0ed2b9b3989238388e7edddaf252c81a7cb9f', FALSE, 'NativeUI · RefreshArtistTab')
  , ('f538fc29da07e500', 'client', '<color=#A0D4FF>=  TRAILS  =</color>', 'cf3c872f8fb22c2234c807eaa7edd9a9e2d07c1f', FALSE, 'NativeUI · BuildShopTab')
  , ('b5699b2c6706d70a', 'client', '<color=#AA9955>-> {0} bet {1}g on {2} - refunded</color>', '9e8ba6414d716552ea534ba3d65e2773b984fe5e', FALSE, 'NativeUI · BuildMultimodeSeriesLine')
  , ('97eed477558a8ce8', 'client', '<color=#AAAAAA>Reports go to the mod team. Be specific — what happened, when, what you were doing.</color>', 'cdedff3bd78198557df9dfac25d6db4d5e4f0d8c', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('2ac4535994ad529e', 'client', '<color=#AABBEE>Recent Tournaments</color>', '768e57570a9cce89ad0ab92561cf3b91ef35d32e', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('0c0c58a969ea6324', 'client', '<color=#B0FFB0>=  MAP COLORS  =</color>', 'f51730ea676e6268149dc283145a89fd42e55431', FALSE, 'NativeUI · BuildShopTab')
  , ('4348c24a8c51d771', 'client', '<color=#BBB>{0} players</color>', '26bd357c92455bef39a393e90a90e415b1d9f94c', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('913a26b15c078201', 'client', '<color=#C0C0C0>2nd</color>', 'b468a5e23643ed937c1751a01d4db24d8bcb6ee9', FALSE, 'NativeUI · RefreshTournaments')
  , ('69db31eb590f12ae', 'client', '<color=#C48CFF>FFA:</color> -', 'eacf603f30c34bd78459c3d1302b34e33822dbb4', FALSE, 'NativeUI · RefreshMyStats')
  , ('9f62981453f64b39', 'client', '<color=#C48CFF>FFA:</color> {0}W / {1}L ({2:F0}% win)', '70ae4797d016b4c6d8c1dba02cc9c83aac00df86', FALSE, 'NativeUI · RefreshMyStats')
  , ('1d4b353260bcecaf', 'client', '<color=#C8A0FF>=  PLAYER EFFECTS  =</color>', '51932d71c2a90560a3906a6e9fb9ab42ab946fce', FALSE, 'NativeUI · BuildShopTab')
  , ('12e64c29d0a7dec2', 'client', '<color=#CCC>Blocks vs successes</color>', '35a24924fe75063bee75a862f34ef86ecc927157', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('65d7670c7a57530a', 'client', '<color=#CCC>Dmg taken vs blocks</color>', 'cf3d5ce1d2f0ce340da36b8cb047d330a7e541bb', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('0bef6893b50362d8', 'client', '<color=#CCC>FPS</color>', '098e8c6ff86c7d21c0e60cab817654f2b8c0e276', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('05347a04a3a75031', 'client', '<color=#CCC>Ping (ms)</color>', '8ea095243d5e72c3eddc0d586a212666cbd8b714', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('d561d401c70c4984', 'client', '<color=#CCC>Shots fired vs hits</color>', '9d4ae048ec09950231d3ec5f92e1f1588918a061', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('07bbc695cbcbf94f', 'client', '<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>', '23d3c7247ce05cff78cc80a60b254f348e4ab9e7', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('72516c9f1b1624dc', 'client', '<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>{0}</color>', '55988d2481d6c10a64e86a342aa8d8f261b564dd', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('cf5674f2c394e9f5', 'client', '<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>', 'fe71233ddf90b089c1810f30aa5db406e4137f50', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('7a7823c2087f2573', 'client', '<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>{0}</color>', 'a42b5210eecd90c46304776157124b18a67cc340', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('6de91b7bd1016508', 'client', '<color=#CCCCCC>In this Photon room for <b>{0}s</b> with no match started. Vanilla matchmaking sometimes hangs here when one player has ROUNDS unfocused. Click into the ROUNDS window first and try {1} again, or use the escape hatch below.</color>', '2cc48659a9b9a51f4c11df88edb295a6e18169dd', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('7f80629f57a37126', 'client', '<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>', 'b9e3805cbd8a09cb53f502d1ee059cbe83bfa270', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('c52cca2c773022ae', 'client', '<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>{0}</color>', '4ec13493affca1bdbebebe9038ae5d87d1b035f2', FALSE, 'CompetitiveUI · PaintTeleGraph')
  , ('28608dd429bf4959', 'client', '<color=#CCCCCC>Players in: <b>{0}</b>. Your player is in, but the other player has not pressed Jump to join — their game may be unfocused or stuck on its ready prompt. Leaving here costs nothing: no match has started.</color>', '7d30cf4fe7e8dc4bc93d9abb5e3a5cc140b6ac2c', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('e31bb2a57a268bb8', 'client', '<color=#CCCCCC>Scoring history</color>  <color=#66DD66>you</color> <color=#888>vs</color> <color=#DD7777>opponent</color>', '1a2d6cafc8df6926eaa128130f8910894b888c8e', FALSE, 'CompetitiveUI · PaintScoreGraph')
  , ('adc860031b5295e6', 'client', '<color=#CCCCCC>Scoring history</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>opponent</color>', '9aa5d08a389c60c574c2edc82c05d79e411ac131', FALSE, 'CompetitiveUI · PaintScoreGraph')
  , ('c6e08aaddb54f113', 'client', '<color=#CD7F32>3rd</color>', '612a11b6c5251810e033b1b07d1856c913bf7748', FALSE, 'NativeUI · RefreshTournaments')
  , ('89a698611907f9ec', 'client', '<color=#D8A7FF>FFA History</color>', '2fa2251cb22a70a509d217abe8ec11e024e0aaae', FALSE, 'NativeUI · BuildPlayerModeHistoryText')
  , ('683fba7afbb36532', 'client', '<color=#D8A7FF>FFA:</color> {0}W-{1}L', 'd9e3fd10875116ad5e4e38dca5bf31fbc487fdf5', FALSE, 'NativeUI · RefreshSession')
  , ('4e9df1482c91e705', 'client', '<color=#DDDDDD>{0}</color> <color=#777>-</color> {1} players <color=#777>-</color> <color=#8FA3B8>{2}</color> <color=#777>-</color> {3}', '77768f2cddef5881738c018e0d4d539bbfb2df96', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('c60975242010a2c8', 'client', '<color=#E69988>Opp: Hit {0}%</color>', '4fbccb024c897c74e187b3121bf5a8fae54a0244', FALSE, 'NativeUI · FillRow')
  , ('91796b933251df6c', 'client', '<color=#EEEEEE>solid = {0}</color>   <color=#888888>dim = {1}</color>', '102200e3e75f1f63cb91b136385e50d3b8648dc9', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('ab2beba74b6edbdc', 'client', '<color=#FF4040>deadline passed</color>', '6720d32ca22f975764dacdbecbf7e2f1666a9979', FALSE, 'NativeUI · AsyncDeadlineTail, RefreshTournaments')
  , ('9f1db78d42bdc3b7', 'client', '<color=#FF4444>UPDATE REQUIRED</color>', '7438392c1065e86ecd48fa2fcff8e7d82b51bd77', FALSE, 'NativeUI · RefreshVersionStatus')
  , ('eaf335fb8c431c62', 'client', '<color=#FF6060>FORFEIT</color>', 'ea6603a84a55d925c86823baea165b935139d735', TRUE, 'NativeUI · RefreshTournaments')
  , ('646f953ecaac93a8', 'client', '<color=#FF6060>deadline: {0}h {1}m left</color>', '1ec060bd46f6c33d194d1763691c9a07849be0ef', FALSE, 'NativeUI · AsyncDeadlineTail, RefreshTournaments')
  , ('f3111e697b8a3499', 'client', '<color=#FF6666>(OUT OF STOCK - artist hasn''t opened sales yet)</color>', '503a6feddafea172e50dcab91e9b6ca9fd5c5415', FALSE, 'NativeUI · ApplyShopRow')
  , ('5960a9ad7ea21934', 'client', '<color=#FF6666>(SOLD OUT)</color>', '3459beeb88871e1e04b203c8a2bae6ad0c375949', FALSE, 'NativeUI · ApplyShopRow')
  , ('0243596e5d193a51', 'client', '<color=#FF6666>+{0} replaced</color> <color=#556270>(hover)</color>', '18aff0f77f00d58e0135fbbe73602eea442793d2', FALSE, 'NativeUI · BuildFfaCardsText')
  , ('0caa0cb269d0e9b4', 'client', '<color=#FF6666><b>LOST</b></color> {0}-{1}', '402a9cda67e01dc4345b39756827e04ea577666a', FALSE, 'NativeUI · RefreshTeamTab')
  , ('6f22a3d809f5159c', 'client', '<color=#FF6666>DENIED</color>', '77f34486d741bddbd1feecfab4257ae67faa108b', FALSE, 'NativeUI · RefreshArtistTab')
  , ('da749f60b9684f21', 'client', '<color=#FF6666>Deletion failed: {0}</color>', 'd7e0867b602018ada5fd37c4c1a1842af50c54b1', FALSE, 'NativeUI · BuildSettingsTab')
  , ('3bb6abceb257a687', 'client', '<color=#FF6666>LOST</color>', 'da927b7271e6f8d59cbacce1b80066741b590663', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('4f840542dec022c0', 'client', '<color=#FF6666>NOT OPENED - set stock to start selling!</color>', '8aa97ef1388ab04f260985fe6a7f5c5f08b4a5a4', FALSE, 'NativeUI · RefreshArtistTab')
  , ('da9f507760953b88', 'client', '<color=#FF6688>* Live Ranked Series</color>', 'f28720141e74a4c015a37e1d151f0924da55a676', TRUE, 'NativeUI · BuildLeaderboardTab')
  , ('03bc4458323fd933', 'client', '<color=#FF8888>Purchase failed: {0}</color>', '5382a6697adcab5246f2e9a8c1ef6290ebaa2c09', TRUE, 'NativeUI, TitleLaddersUI · CreateShopRow, OnActionClicked')
  , ('d8cf14d63c80e35e', 'client', '<color=#FF8888>The price changed - check the new price and buy again.</color>', '9deec55bcab0c91176b8e30340256189cb1302b5', FALSE, 'NativeUI, TitleLaddersUI · CreateShopRow, OnActionClicked')
  , ('13450fb3dcf12977', 'client', '<color=#FF9060>press Ready Up</color>', '526be647c886a89d3d15442a98b25641fcdd0a90', FALSE, 'NativeUI · RefreshTournaments')
  , ('b1eef294c20d4576', 'client', '<color=#FF9966>MASTER OFF</color>', 'bb8114dd2fbea5b0ee5612f9aae23305f631796a', FALSE, 'NativeUI · PaintPerfHeader')
  , ('79d12f448ea4ecb8', 'client', '<color=#FF9966>PLACEMENT CHANGE REJECTED</color>', 'f2c531693552d14d45c172e385c65845c14edac4', FALSE, 'NativeUI · RefreshArtistTab')
  , ('1e91995466d6d8ff', 'client', '<color=#FF9988>Blocked buyers</color>  <color=#888>(can''t purchase your items; gifts still work)</color>', '56b2f8794b6c6e5bfde3fa67fd25718e29f1b8b8', TRUE, 'NativeUI · BuildArtistTab')
  , ('fb110029669916f2', 'client', '<color=#FF9988>Hit:</color> -', '995bd7e24afe7fc688d2026b7dd199ce6cbec2a3', FALSE, 'NativeUI · RefreshLeaderboard, RefreshMyStats')
  , ('6527d25181574b70', 'client', '<color=#FF9988>Hit:</color> {0:F1}% ({1}/{2})', '39a0a4745696d6845086d5a0a336ee7ae6cedaf1', FALSE, 'NativeUI · RefreshMyStats')
  , ('2380439a94a853ee', 'client', '<color=#FF9988>Hit:</color> {0}% <color=#888>({1}/{2})</color>', 'c71e0391acbc34eefbfee6148971ec18fac0b669', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('8b00982d542b583f', 'client', '<color=#FF9988>Hit</color> {0}%', 'f48e8d83176749e28e622b50540c3ae0f29b907c', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('f469e16744d7e631', 'client', '<color=#FF9BE0>coming soon!</color>', '025b122607398d54c7dac36a0d9b0fdb10f1ab8e', FALSE, 'NativeUI · RefreshHomeTab')
  , ('c9a9a504784c0fdd', 'client', '<color=#FFA070>=  BODY COLORS  =</color>', 'bcca96d7c97b106a652be1b5520bf9861a73b560', FALSE, 'NativeUI · BuildShopTab')
  , ('31306ed786be720c', 'client', '<color=#FFAA44>deadline: {0}d {1}h left</color>', '7ca6b11ece011d7e9023ad441a7dab7da9f6084a', FALSE, 'NativeUI · AsyncDeadlineTail, RefreshTournaments')
  , ('f5e4b15f8ec88880', 'client', '<color=#FFAA55>Lobby browser unavailable right now — the server may be updating.</color>', 'af57de8670a28aeeae77335bea05fc79ebb02c01', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('d8fb230540e18c73', 'client', '<color=#FFB088>Link Discord first (Home tab) to sign up.</color>', '0587b7ed95b4b633c385c0ebe89543cd3733df52', FALSE, 'NativeUI · RefreshTournaments')
  , ('e6d82c7fecd456b5', 'client', '<color=#FFB0E0>=  NAME STYLES  =</color>', '2f5b1a23c18d38b64e27517e40dd5a639ea270db', FALSE, 'NativeUI · BuildShopTab')
  , ('e2d283f46c6565a8', 'client', '<color=#FFB347>1v2 lobby pending</color> — Leave to dissolve it if nothing happens.', 'e80eed1854086d8b9db4aefdb9f0edcdfe901eb8', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('fdb683f06819a160', 'client', '<color=#FFB347>2v2 History</color>', 'c0db3cd062a38f3cacf680a2109f3dd736a64c13', FALSE, 'NativeUI · BuildPlayerModeHistoryText')
  , ('28f68e8f4b5e031a', 'client', '<color=#FFB347>2v2:</color> {0}W / {1}L ({2})  <color=#888>Rating:</color> {3:F0}  <color=#888>Peak:</color> {4:F0}', '644c522f19a0e7153b4f63cb958665eb40c20b7e', FALSE, 'NativeUI · RefreshMyStats')
  , ('a77c56b241124324', 'client', '<color=#FFB347>2v2:</color> {0}W/{1}L', '7b102ce6e585783508febe4bddb64faf39b56156', FALSE, 'NativeUI · RefreshSession')
  , ('a42ca4dd686e8f5c', 'client', '<color=#FFB347>Series held — waiting on the final result</color>  <color=#FF6688>{0}</color>  <color=#888>(score {1}-{2})</color>', 'f6e767f55c58a0e7a6b259eb30a8d97be16c8773', FALSE, 'NativeUI · RefreshTeamTab')
  , ('99a1c6367212642d', 'client', '<color=#FFB347>solo won</color>', '50fc7f597d225aa9330d5d5c4c309e5a30070477', FALSE, 'NativeUI · BuildOvtRecentRowText')
  , ('ae2dc0c4a783a120', 'client', '<color=#FFC8F0>=  DANCES  =</color>', '2b08101b6b9bc6d8943aacefab6589145b277707', FALSE, 'NativeUI · BuildShopTab')
  , ('e635b598d330a8e2', 'client', '<color=#FFCC44>In {0}''s lobby</color> - waiting for the host to start ({1} in).', '7ae1c8b04ad592dfcf2b268a33874715bec934da', FALSE, 'NativeUI · RefreshFfaTab')
  , ('c4c4f162ef3a08eb', 'client', '<color=#FFCC44>Searching…</color> {0} in lobby <color=#888>(locks at 3)</color>', 'a3fd02a92f217c87cd4ec996e33fe07c4b77ebca', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('21e20bf0ec019f0a', 'client', '<color=#FFCC44>UNRATED</color> — stats, gold and XP count. Ratings never change.', '8f254dc7f4f1db04fb0efd2953a95b75e6d05c86', TRUE, 'NativeUI · BuildOneVTwoTab')
  , ('5effd06b69376e5b', 'client', '<color=#FFCC44>You are the host.</color> Waiting for players - {0}/{1} needed to start.', '5c1fa7d0cda455f717492a0bd5cfa35aee09c9a7', FALSE, 'NativeUI · RefreshFfaTab')
  , ('ec409b24b6baa83d', 'client', '<color=#FFD080>Match-found screen might be stuck</color>', '1a7f980a682a95d6db7309ad484f1c7ff80776a2', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('a0362a9ecb56c463', 'client', '<color=#FFD080>The other player has not joined the game yet</color>', 'd3682704bbf56ff0650f46942c92131cc592b36f', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('37a1e81bc8d7d159', 'client', '<color=#FFD850>1st</color>', '5b830264085b78b427d019b561317db1e4e3360b', FALSE, 'NativeUI · RefreshTournaments')
  , ('8b1502a60a920a2e', 'client', '<color=#FFD850>CHAMPION</color>', '3e5918ce46a2c482e12ffe2dc8beecf53cf803da', FALSE, 'NativeUI · RefreshTournaments')
  , ('330b2a3cb2dd7af7', 'client', '<color=#FFD94D>({0} of {1} left)</color>', 'c6ace38f182cbc9fec7803e444562aadce3d2c54', FALSE, 'NativeUI · ApplyShopRow')
  , ('d820ae159a485e60', 'client', '<color=#FFD94D>* {0} TOURNAMENT GAME - vs {1}  (results auto-recorded)</color>', '6539b230a37ed6620b040c83b2f5a361f579778a', FALSE, 'NativeUI · RefreshTournamentGameIndicator')
  , ('cf026731cc105418', 'client', '<color=#FFD94D><b>GETTING PACKS</b></color>

- <b>One free pack a day</b> - press Claim on the Open Packs tab or use /daily in Discord. The day resets at midnight UTC.
- <b>Paid packs</b> cost 100 Gold or 100 shards and hold 5 cards. Up to 5 paid packs a day for most accounts; the Get packs tab says what applies to yours.
- <b>Earned packs</b>: winning a ranked series, or a ranked FFA match, grants a pack one time in five - the same chance in 1v1, 2v2, 1v2 and FFA alike, and the score line makes no difference. Earned and claimed packs wait under <b>Packs waiting</b> until you open them, as long as you like.

<color=#FFD94D><b>WHAT IS IN A PACK</b></color>

- Each card rolls its band on its own: <color=#8085A0>Common 60%</color>, <color=#4DB861>Uncommon 25%</color>, <color=#408CFA>Rare 11%</color>, <color=#9E52EB>Epic 3.5%</color>, <color=#FFB82E>Legendary 0.5%</color>.
- The band decides WHO you get: the pool is ordered (players who have played a ranked series first, then by rating), and pool positions #1-2 are the two Legendary cards, #3-10 are Epic, #11-20 Rare, #21-40 Uncommon, and everyone past that is Common.
- Independently of the band, any card can come out <b>Foil</b> (1 in 200) or <b>Signed</b> (1 in 2,000) - a foil shimmers, a signed card carries the player''s autograph.
- The strip under the buttons shows your last pack, and the Older / Newer buttons page back through every pack you have opened. A card you discarded stays in its pack, stamped DISCARDED.

<color=#FFD94D><b>DUPLICATES AND SHARDS</b></color>

- A card you already own is marked DUPLICATE when it lands (+1, +2 ... for how many copies you held before it).
- <b>Discard</b> turns a card into shards: <color=#8085A0>Common 5</color>, <color=#4DB861>Uncommon 15</color>, <color=#408CFA>Rare 40</color>, <color=#9E52EB>Epic 150</color>, <color=#FFB82E>Legendary 600</color>. It asks you to click twice. <b>Dupes</b> discards every copy except one in a single go.
- Shards buy packs at the same price as Gold - 100 for a pack.

<color=#FFD94D><b>DISCORD</b></color>

- /daily claims the free pack, /collection shows a binder, /card shows one card - all with a linked Discord account.
- A pull that is Epic or better is announced in the Discord gambler chat, and so is a pull of your own card, a Foil or a Signed print at any rarity - but only when BOTH you and the player on the card have <b>Announce my pulls</b> on (see Card pictures & settings). A Rare or lower pull that is none of those is not announced.', '2c525b2f5f4332ea1c5621b06fe5225ae89f84c4', TRUE, 'InfoLibrary · (file scope)')
  , ('892845f20501fbc0', 'client', '<color=#FFD94D><b>HOW A PICK ACTUALLY LANDS</b></color>

- Confirming a card applies nothing - not even on your own screen. Every picker publishes their choice, the room master collects them and publishes one accepted list, and every client applies exactly that list in the same order. That is why all 3-10 screens always agree on who got what.
- The numbers: 45 seconds base, plus 20 more each time a pick lands near the end, capped at 90.
- The on-screen 0 is exactly the auto-confirm moment - the client confirms slightly early, so a slow connection can''t eat your pick.
- <color=#FF6666>Two rare cases still yield no card:</color> a pick published in the final instant can miss the cutoff (you get a toast saying so), and a crashed seat is finalized without one.

<color=#FFD94D><b>WHAT REPLACING A CARD REALLY DOES</b></color>

- ROUNDS has no way to subtract one card''s stats. When your oldest card rolls off, the mod fully resets your character and silently replays your surviving cards in their original order. A toast on every screen names what you lost.

<color=#FFD94D><b>MAP SCALING</b></color>

- With 5 or more players the map grows 6 percent per player above 4, capped at x1.40: five players play at x1.06, ten at x1.36. 3-4 player games are unscaled.
- The camera, the kill boundary and spawn positions all scale with it.
- Vanilla maps ship only four spawn points, so on scaled maps the mod scans the freshly loaded map for solid static ground and gives players 5-10 their own spawns instead of shared coordinates.

<color=#FFD94D><b>TEN PLAYERS, FOUR COLORS</b></color>

- ROUNDS ships exactly four body colors, so colors repeat every 4 players. Nametags keep duplicates apart, and equipped body-color cosmetics still show.
- To help you find yourself, the screen dims around your own player for the first second after each spawn - the same second in which nobody can fire or block (<color=#7FD4FF>spawn grace</color>).

<color=#FFD94D><b>DOUBLE KO</b></color>

- If the last players alive kill each other in one exchange, nobody scores and the round just ends - announced on every screen.
- The winner is decided at the very end of the frame, so a mutual kill can''t hand the round to whoever died a split second later.

<color=#FFD94D><b>LEAVERS, PRECISELY</b></color>

- A leaver''s points, half points and kills freeze at the moment they leave and still count for placement in every later report of the sitting.
- If a leaver was one of the last two standing, the survivor takes the half point.
- <color=#7FE87F>Early-leave grace:</color> leave a game before the field has scored four half points in total, whether or not any became a full point, and that game is unrated for you - no rating change, no game Gold or XP. Achievements can still be earned and pay as usual, but an unrated game earns no title-ladder progress. Any later leave counts in full: leaving early doesn''t dodge the loss.
- Players who left in an EARLIER game ride along as absent ghosts - on the roster, excluded from rating and pay.
- A game that drops under 3 players before 2 half points were scored is cancelled; dropping under 3 after a game over ends the sitting.', '84324a21d4105a936ec63ce3a5d72bdf7e5986b8', TRUE, 'InfoLibrary · (file scope)')
  , ('a824f29d33590ce9', 'client', '<color=#FFD94D><b>HOW THE BALANCER RATES YOU</b></color>

- The balancer uses your 2v2 rating once it is trustworthy: 10 or more completed series, or earlier once the rating has settled (its uncertainty has dropped enough). Until then, your 1v1 rating stands in.
- Ratings are snapshotted when you join the queue - the balancer works from those values.
- The server tries all three ways to split the four of you into pairs and keeps the split with the smallest difference in total team rating.

<color=#FFD94D><b>THE MID-SERIES SWAP, PRECISELY</b></color>

- It only fires in auto-balanced series - manual lobbies never swap.
- The design: after a game with a point margin of 3 or more, the weakest winner trades places with the strongest loser for the next game, under the same 2v2-if-trusted, else-1v1 rating rule as above.
- <color=#FF6666>Not live yet:</color> the in-game team switch is still shipping, so for now the balancer only logs the swap it would have made and teams stay locked for the whole series.

<color=#FFD94D><b>WHO IS ORANGE, WHO IS BLUE</b></color>

- Team 1 is the in-game orange team; Team 2 is blue. Within a team, the lower Steam ID takes the first slot.
- In a manual lobby you can claim Team 1 or Team 2 before the lock. The auto queue always runs the balancer and ignores preferences.
- A team can also carry a member''s equipped body color as its display identity, decided once when the series is created: a sole color holder names the team, two holders is a coin flip, none means vanilla. In a mirror match, Team 2 falls back to its other member''s color. <color=#8A8A93>Display only - nobody''s actual body color is changed.</color>

<color=#FFD94D><b>DISCONNECTS</b></color>

- <color=#FF6666>Lead forfeit:</color> if the other team DCs out of a game that had 2 or more total points while YOUR team is already up a series game, the whole series completes to you on the spot, with full rating and gold. You can''t leave a 2v2 to dodge a loss once you''re down a game.
- Any other DC carries NO automatic penalty: the series is set aside for manual admin resolution, and every game already reported stands.
- <color=#7FE87F>Sticky resume:</color> if the same four players re-queue within about 30 minutes, the matcher relocks you onto that series - original teams, score kept.

<color=#FFD94D><b>REWARDS, PER SLOT</b></color>

- XP and gold accrue per player slot inside the series, so the panel shows each player''s own +g and +xp, and the lifetime Gold/XP columns count 2v2 play only.
- The tier multiplier uses the AVERAGE of the two opposing players'' 2v2 ratings; a player with no 2v2 rating yet counts as 1500 - and 1500 already sits in the x1.5 Intermediate tier, so a fresh lobby pays above base.', '9deba99e00d05dced7ec579c859f8b250bb287b9', TRUE, 'InfoLibrary · (file scope)')
  , ('b1cc8f5df71d3d5e', 'client', '<color=#FFD94D><b>SELF VS OPPONENT DAMAGE</b></color>

From the table it is pretty clear that most damage falls into two categories: damage dealt to your opponent and damage dealt to yourself. Damage dealt to your opponent will almost always trigger all cards and buffs, whereas damage dealt to yourself will only ever trigger Scavenger. This fundamental remains true whether it be damage directly from bullets, AoE effects, or even niche effects like Demonic Pact''s life drain.

<color=#FFD94D><b>ODDITIES</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - despite dealing direct AoE damage to an opponent, it will never trigger any cards or buffs. Not even Scavenger. It is unique in this.
- <color=#7FE87F>Brawler</color> - for whatever reason, the particle effect attached to Brawler is activated upon self-damage, despite Brawler not truly activating. Potentially something that would appreciate a fix from Sid.
- <color=#7FE87F>Demonic Pact</color> - uniquely, its AoE does not affect the user. To balance this and prevent damage stacking, the AoE has terrible, though not completely non-existent, damage and knockback scaling. Its drain damage is applied pre-fire, not post-fire, meaning the player is always missing one bullet despite not being able to run out of ammo (unless Combine stacking reduces them to a single bullet in the clip - impossible without exceeding the card maximum, and thus irrelevant). And Scavenger still activates even when the player does not actually lose any health due to death prevention.
- <color=#7FE87F>Life Stealer</color> - similarly to Demonic Pact, all appropriate cards and buffs activate even if no health is actually drained due to death prevention. This includes lifesteal: it seems lifesteal is calculated from the maximum damage that could be applied, not the actual decrease in health. Further testing with overkill bullet damage and Leech affirms this. Tick damage like Parasite, however, will not give the maximum lifesteal return upon death. Something to be aware of in FFA or when against Phoenix.

<color=#FFD94D><b>REFRESH AND CONDITIONAL DAMAGE</b></color>

Now we come to Conditional damage. To put it simply, Conditional damage ''balances'' Refresh, such that you can never trigger two Refreshes in a row using Conditional damage. From my research it has become clear that every player holds an invisible boolean value which I will call RefreshValid. As a boolean it can occupy two states, true or false. When RefreshValid is true, the next time you deal Conditional damage you get a successful Refresh, but RefreshValid then flips to false. If you deal Conditional damage while RefreshValid is false, you do not receive a Refresh - but RefreshValid flips back to true, so your next instance of Conditional damage will trigger one. Already having a block ready, and so not needing a Refresh, has no impact on this flipping.', '196139ffad4d0160ccf4577a8ea90b0011638d78', FALSE, 'InfoLibrary · (file scope)')
  , ('52bd8eb38c0a7b06', 'client', '<color=#FFD94D><b>SORTING THE BINDER</b></color>

- <b>Rating position</b> orders the binder by where each player stands on the leaderboard today - top 100 first. Players outside it, or not seen in 90 days, go to the back, ordered by rating.
- The number printed on a card is the rank it was minted with, which can differ.', '8a4398f4d9ec92758c0eb8ab94220e8273bdc3b4', FALSE, 'InfoLibrary · (file scope)')
  , ('408fb7e29e45f00e', 'client', '<color=#FFD94D><b>STREAKS</b></color>

All streaks are 1v1-only. Casual streaks count games; ranked streaks count completed series.

- <color=#7FD4FF>Flawless</color> - five 5-0 wins in a row. Ranked and casual both count; <color=#FF6666>any game that isn''t a 5-0 win resets it</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Century Club</color> - 100 casual wins in a row. A casual loss resets it; ranked games don''t touch the counter. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Casual Conqueror</color> - 200 casual wins in a row. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Touch Grass</color> - 500 casual wins in a row. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>On Fire</color> - win 25 completed ranked series back to back. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Unstoppable</color> - 50 ranked series in a row. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Immortal</color> - 100 ranked series in a row. <color=#7FE87F>500g</color>

<color=#FFD94D><b>RATING, SLAYERS AND 2v2</b></color>

The rating milestones are checked whenever your 1v1 or 2v2 rating updates. FFA rating moves don''t trigger them.

- <color=#7FD4FF>Rising Star</color> - reach 1700 rating. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Master</color> - reach 1980 rating. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Grand Master</color> - reach 2330 rating. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - win a completed ranked 1v1 series against Sid. Grants the equippable Sid Slayer title. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - win a completed ranked 1v1 series against Stan. Grants the Stan Slayer title. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Tag Team Sweep</color> - win a single 2v2 game 5-0. Both members of the winning team unlock it; it''s per game, not per series. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA AND TRANSLATOR</b></color>

The FFA six require a RANKED FFA lobby and are all server-checked.

- <color=#7FD4FF>Clean House</color> - win an FFA 5-0: all five points yours and nobody else converts a full point, in a game that 3 or more players finished. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Party Crasher</color> - the same with 4 or more finishing. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Hostile Takeover</color> - the same with 5 or more finishing. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Rampage</color> - over 50 kills in one game. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Bodycount</color> - over 100 kills in one game. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Heartbreak</color> - lose a game holding 10 or more round wins that never became full points. <color=#7FE87F>300g</color>

The shutouts nest: <color=#7FE87F>one shutout with 5 players finishing unlocks all three at once, 900 gold total</color>. Finishing means playing the game to its end: a player who left early or never showed up doesn''t count - and losers holding leftover round wins don''t break your shutout; only a converted full point does. <color=#8A8A93>Kill counts only register when the game was reported by an up-to-date mod version.</color>

The translator tiers come from the translation portal, not from matches. A live string is an approved translation you proposed or reviewed; doing both jobs on one string counts once. Each tier also grants its matching title (see <color=#7FD4FF>Titles</color>).

- <color=#7FD4FF>Rosetta</color> - 10 live strings. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Dragoman</color> - 100 live strings. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Babel</color> - 1000 live strings. <color=#7FE87F>1000g</color>', '1615f58f6d0b2f798b72a85ae4bd2cf7ebf199eb', TRUE, 'InfoLibrary · (file scope)')
  , ('f725fffe65b21b6f', 'client', '<color=#FFD94D><b>THE 0.35 SECOND WINDOW</b></color>

To prepare you for this knowledge, I must first admit that I lied in the table. Where it states that Bullet Damage triggers a Refresh with a plain Yes, it should carry an asterisk: it does most of the time, but not all of the time. Presumably to help balance cards like Burst and Spray, the developers put a system in place that turns quickly repeated non-Conditional damage into Conditional damage. Shoot an opponent once and you get non-Conditional damage; shoot them again within a window of around 0.35 seconds and that second shot is Conditional. The window resets after every shot. Below, quick secondary (and tertiary) shots are denoted QShoot:', '0d145cbc5195fb34ea7021bd4ccb82e1bb473306', TRUE, 'InfoLibrary · (file scope)')
  , ('6262aad1393e919b', 'client', '<color=#FFD94D><b>THE HEADER</b></color>

- The player''s current name - a rename follows onto every card of them - and under it the shop title they were wearing when the snapshot was taken (nothing there if they wear the rank title or no title at all).
- The chip in the corner is the band: COM, UNC, RARE, EPIC or LEG, with FOIL beneath it on a foil.

<color=#FFD94D><b>THE PICTURE</b></color>

- The player''s own in-game character - body, face, colour and effect - once their PC has sent it. Until then, their Steam profile picture. See <color=#7FD4FF>Card pictures & settings</color>.
- The lower-left corner shows their Top card: the ROUNDS card the snapshot found they pick more than any other. It is drawn in-game from the card itself; cards shown outside the game (Discord) carry a plain badge there instead, and the name is on the text block when the picture is not shown.

<color=#FFD94D><b>THE STATS</b></color>

- <b>RANK</b> is the rating tier the player was in at the snapshot - Beginner I up to Grand Master V, the same tiers as the leaderboard. It is never the shop title.
- <b>RATING</b> is their rating at the snapshot, or Unranked.
- <b>POOL #</b> is their position in the card pool at the snapshot - the ordering that decides the band (see Player Cards). A lower number is a rarer card.
- <b>BOARD #</b> is their leaderboard position at the snapshot: five or more ranked series and recently active. A dash means they were not on the board that day.
- <b>RECORD</b> is ranked series won and lost at the snapshot.

<color=#FFD94D><b>THE MARKS</b></color>

- A <b>Signed</b> card carries the player''s autograph across the picture and a seal.
- The bottom edge has the edition, the minted date, and your copy''s print number. Click a binder tile to see the card full size.', 'cbb4762519e994327916a66f9a48f529d91a6de7', TRUE, 'InfoLibrary · (file scope)')
  , ('17dbc7c161f0ab71', 'client', '<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color>
{0} works everywhere - menu, lobby, mid-game. While the menu is open your inputs stay out of the game: clicks do not fire your gun, {8} does not ready you up, and Escape only closes the menu - it will not cancel a match that is connecting. Close it and everything flows again.

Chat has three doors. {1} types a message, holding {2} opens the quick-chat wheel - point at a phrase and release to send it, or pick More... for the full list - and Enter still opens the vanilla box - the mod leaves it alone. {4} cycles the chat overlay display mode. While typing, a tap of {5} switches the language channel your message goes to - global, then each language channel in turn, then back to global; the Home tab dropdown sets it too.

Holding {3} opens the emote wheel - even mid-battle: point at a dance you own and release to play it for everyone running the mod. Your own controls lock until the dance ends, and the dance stops if you get knocked around or fire. Dances are bought in the Shop''s DANCES section, where Preview shows the exact moves.

Hold {6} during a match for the live scoreboard: score, cards, accuracy and connection info for everyone in the room, without opening the full menu.

{7} swaps between your equipped map color skins as a new round paints in. If you have none equipped, it does nothing.

Every control named here except Escape and Enter can be moved on the Settings tab''s Controls page - the mod''s own and the game''s movement, jump, fire and block. F5 always opens this menu, whatever you set there. For what to practice with all of this, read <color=#7FD4FF>Getting better</color>.', '9932f848f9a995ff975e39283a634116e36737b4', FALSE, 'InfoLibrary · (file scope)')
  , ('0afe97716e208ec8', 'client', '<color=#FFD94D><b>THERE ARE NO DAMAGE TYPES</b></color>

Now that you understand this, I must admit that I lied a second time. I misled you, cajoled you, into believing that Conditional and non-Conditional damage are two separate damage types, individually bestowed upon certain attacks by the developers. This is incorrect. Damage is treated the same regardless of its source. In reality there are no damage types at all. So how is damage decided to be Conditional or not? The damage decides it. Literally. How many points of damage you are trying to deal determines whether Refresh will not activate at all, activate Conditionally, or activate always (unless it lands inside the 0.35 second window, in which case it becomes Conditional).

I discovered this when stacking Silence. While a regular Silence has a max damage of around 9, stacking two Silences can reach as high as 17, likely more. I say ''reach'' because Silence deals AoE damage - the further you are from the target, the less damage you deal. Regardless: with Silence''s damage over 10, it becomes non-Conditional. Stack two Silences and a Refresh and you can loop Silences infinitely - provided you land every Silence in the over-10 damage range. Fall into the 5-to-10 range and it becomes Conditional again; fall under 5 damage and no Refresh is ever triggered. You also cannot cycle Silences too fast, or the 0.35 second window triggers and turns your non-Conditional damage Conditional again. (See why this was such a nightmare to figure out.)

The magical thing is that this range applies to every single damage source. Stack enough Frost Slams or Shockwaves and you can produce the same result. The same holds for AoE explosion damage from Timed Detonation or Explosive Bullet. Regular bullets have a minimum damage of 14, so you cannot reach Conditional with damage reduction alone - but if your opponent gets Decay, the individual ticks each carry such low damage that you get no Refreshes back. Or at least you should not: due to tick inconsistency you might occasionally get one or two, at a vastly reduced rate. Conversely, stack enough damage and even when it is divided between ticks you still have enough for constant Refreshes. For cards like EMP and Bombs Away, which cannot change their damage, this revelation means nothing. It also means little for Demonic Pact, Frost Slam and Shockwave, as the stacking needed to raise their damage to the next band is not realistic within a normal game.

Below is a flow chart of all damage possibilities:', 'c79e55ef850157b7d4923353bba21f93d994478e', TRUE, 'InfoLibrary · (file scope)')
  , ('6aac6cbbebced3a5', 'client', '<color=#FFD94D><b>WHO GETS THE SOLO SEAT</b></color>

- You can queue with a preferred side. The lock takes the three longest-waiting live queuers; the solo seat goes to the earliest joiner who asked for solo, or to the earliest joiner outright if nobody did. The other two are the duo.
- The room''s Photon region is the first region anyone in the queue actually reported, in queue order, with US as the fallback.

<color=#FFD94D><b>SPAWN SIDES</b></color>

- Every vanilla map ships exactly four spawn points, two per half. In 1v2 the solo takes the outer-left point and the duo gets the whole right half - a duo player never spawns on the solo''s side.

<color=#FFD94D><b>SOLO EXTRA PICK, PRECISELY</b></color>

- In the random queue, any one player queueing with it enabled turns it on for the series; in a hosted lobby the host''s setting decides.
- The extra draw applies to the OPENING pick only: the solo picks two cards before round 1, then one per pick after that, same as everyone.

<color=#FFD94D><b>PAY MULTIPLIERS</b></color>

The base XP and gold numbers above are multiplied by a difficulty multiplier:

- The solo seat always earns x1.5.
- A solo playing WITHOUT the extra pick earns a further x1.2; a duo facing an extra-pick solo earns x1.1.
- Your opponents'' 1v1 rating tier multiplies too (up to x3.0), and facing a 1v2 podium player adds x1.35, win or lose.
- The difficulty product caps at x4.0, with the x1.5 win bonus applied on top of it. Series gold is scaled by the opponent tier only.

<color=#FFD94D><b>DISCONNECTS</b></color>

- While 1v2 is an unranked beta it has no DC pipeline: outcomes come from recorded games only, and no leave counter exists for 1v2.
- Leaving while locked with zero games played dissolves the lock - the series is canceled, queue survivors go back to searching, and a hosted lobby''s survivors are simply released.
- A leave mid-game leaves the outcome to the normal match report.
- If a locked room never fills: a warning at 35 seconds, then an automatic return to the menu at 90. <color=#7FE87F>No penalty.</color>', '4dcbd19d1118a776e37c240a8993203892053054', TRUE, 'InfoLibrary · (file scope)')
  , ('ba9c002f190ceca1', 'client', '<color=#FFD94D><b>WHOLE-LOBBY GATED - REAL GAMEPLAY CHANGES</b></color>

These change the shared simulation. Grow, the crate rescale and the same-card dealer are whole-room gated: <color=#7FE87F>one vanilla or outdated fighter and everyone gets vanilla, symmetrically.</color> Poison sync is per-victim, with its own mixed-room fallbacks.

<color=#7FD4FF>Poison sync</color> - vanilla runs poison separately on every client, each judging your block by its own timing - screens permanently disagree about which ticks landed (''ghost HP''). Now the victim''s own client decides every tick and publishes the verdict; every modded client applies exactly that set. An unmodded victim gets the pure vanilla loop instead. Works in any online room. <color=#8A8A93>In mod-issued rooms with an incapable client present, the modded clients instead agree blocking does not negate poison - agreement beats the ghost-HP split.</color>

<color=#7FD4FF>Grow normalization</color> - Grow''s damage compounds per FRAME on the shooter''s machine: about x1.4 over a full flight at 400 FPS, x9.4 at 60, x82 at 30 for one copy, far worse stacked - which is how low-FPS players one-shot with Grow plus any explosive. Normalized bullets grow at one fixed rate. Gate: every fighter modded and current, AND a mod-issued room or everyone''s Ranked ON at connect. Otherwise vanilla growth for everyone.

<color=#7FD4FF>Falling crates on big FFA maps</color> - on scaled FFA maps vanilla respawns networked crates and saws too small, ropes miss, and they drop at round start. Rescaled only when every fighter is capable; FFA queue rooms only.

<color=#7FD4FF>FFA same-card dealer</color> - the Same Cards rule deals identical draws; needs every member current, else each client rolls privately.

<color=#FFD94D><b>MODE ROOMS ONLY</b></color>

Vanilla ROUNDS is built for exactly two teams, so FFA rooms replace the round engine outright: round end, scoring, card targeting (vanilla aimed ''other team'' cards at the first player), spawns, leaver tolerance. None of it can run outside FFA rooms.

<color=#7FD4FF>Radiance in FFA</color> - vanilla''s wave hit its own caster the moment they moved, and stopped after ONE hit while visibly sweeping everyone else. The FFA version excludes the caster and hits each opponent the ring sweeps, once, ending when the ring ends.

<color=#7FD4FF>Crown in 2v2</color> - vanilla can''t move the crown past the first two players; the leading TEAM wears it, both members.

<color=#7FD4FF>Card-pick stage in 2v2/1v2</color> - vanilla shows only ONE picker''s body per round (sometimes the wrong one), leaving the second picker on an empty stage. Each picker is re-staged in turn; the 1v2 solo''s extra pick also fixes a vanilla crash that hung the round.

<color=#7FD4FF>Auto-continue</color> - mod rooms auto-confirm the rematch prompt. Room-code games deliberately keep the vanilla prompt: after one side clicks Yes, vanilla starts a 10-second timer that kicks that side to the menu if the other never answers - one-sided auto-Yes kills the player it tries to help.', 'bb4b5f529fff1174466c166584f96ddab94e587c', TRUE, 'InfoLibrary · (file scope)')
  , ('d09d8f0a4703b058', 'client', '<color=#FFD94D><b>YOUR PICTURE ON OTHER PEOPLE''S CARDS</b></color>

- The card of you shows your <b>in-game character</b>: the body, face items, colour and effect you play with, drawn by your own PC when you visit the Collection or Settings tab after a change, and sent once. Nobody else''s PC renders you.
- Before your PC has sent it, your card shows your <b>Steam profile picture</b>, which the server takes from your public profile.
- The picture is not a setting: every card of you shows your Steam picture until your PC has sent the character, then the character - including cards pulled before it was sent. The character your PC sent stays stored until you send another.
- <b>Character preset</b> picks which saved character your picture shows: Follow uses the one you have selected in the character menu, or pin a preset. The small preview under it is what your card shows.

<color=#FFD94D><b>THE OTHER SETTINGS</b></color>

- There is no opt-out: every player who has run the mod from a Steam account and is not banned is in the pool, and cards of you stay in the binders that hold them.
- <b>Public collection</b> is the setting that shows or hides your binder from others (/collection in Discord).
- <b>Announce my pulls</b> allows Discord posts about your Epic-or-better, Foil and Signed pulls, and about pulls of YOUR card - both sides must have it on for a post to happen.
- Deleting your data is what removes cards: your binder is emptied, and every card of you is removed from every other player''s binder.

<color=#FFD94D><b>WHY A CARD SHOWS WHAT IT SHOWS</b></color>

- A card''s rating, record, rank tier and shop title are frozen at the snapshot it was minted from. If you rank up tomorrow, cards of you minted today keep today''s rank; the next snapshot''s cards get the new one.
- The name and the picture are live: a card of a renamed player shows the new name, and its picture follows what that player''s PC last sent (or their Steam picture until then).
- If the player deletes their data, every card of them is removed from every binder.', '5d63ac2019950a3b867b48ff90c6b381999c6878', TRUE, 'InfoLibrary · (file scope)')
  , ('039bc0c9d5cf3e9a', 'client', '<color=#FFD94D>=  OTHER  =</color>', '3fb910cdf01afaf3a6efa8bfb22b2882ac1e6831', FALSE, 'NativeUI · BuildShopTab')
  , ('2cf57bd52862f8bd', 'client', '<color=#FFD94D>=  TITLES  =</color>', '8e92ea5917efa32360585d08790d531fdb553521', FALSE, 'NativeUI · BuildShopTab')
  , ('11c7534fb8b7839c', 'client', '<color=#FFD94D>APPROVED - awaiting mod update</color>', '22e12b0d3921df432cf0884ac46c4dce85a50d83', FALSE, 'NativeUI · RefreshArtistTab')
  , ('3fb6e8f61142d09f', 'client', '<color=#FFD94D>Custom bet</color> on <color=#FFFFFF>{0}</color>', 'b9513bd50f6f2b2febd1b0b20d5f97faec07384b', FALSE, 'CompetitiveUI · DrawCustomBetPrompt')
  , ('b427669f556ea7bb', 'client', '<color=#FFD94D>Map skin:</color> <color=#FFFFFF>{0}</color>', '02915b624b288814df3f1ae1b33365dcc0c576b3', FALSE, 'CompetitiveUI · DrawMapColorToast')
  , ('0578f75137c0ac92', 'client', '<color=#FFD94D>Match found! Click <b>Ready Up</b>.</color>', 'd413a2bca5b58733396502254c2879888129a70b', FALSE, 'NativeUI · RefreshTeamTab')
  , ('fa6435193f8ec7ab', 'client', '<color=#FFD94D>PLACEMENT PENDING REVIEW</color> <color=#888>(last approved placement stays active)</color>', '5201388e750ee115b4d891876b605efd08ef984e', FALSE, 'NativeUI · RefreshArtistTab')
  , ('c0be4316b3888ca4', 'client', '<color=#FFD94D>Ranked (series): {0}W / {1}L</color>', '2466fa8171f0d173bff6eb5ad9409cf0d6e423cd', TRUE, 'NativeUI · RefreshLeaderboard')
  , ('af3d1bf4c8be9543', 'client', '<color=#FFD94D>Ranked (series):</color> {0}W / {1}L ({2})', 'f89bf703606cf6e63f8874ef15d32c00fac7e208', TRUE, 'NativeUI · RefreshMyStats')
  , ('811f0b6757adca50', 'client', '<color=#FFD94D>Ranked Looking For Player</color> - Discord ping', '0112ccb6625408665001abf2b2b43ef9105e6e86', TRUE, 'CompetitiveUI · DrawLfpPrompt')
  , ('bf327ab5b8dbdcc1', 'client', '<color=#FFD94D>Ranked Series vs You</color>', '0278a637c0b4224f4b2e502196bbf1aeac42848f', TRUE, 'NativeUI · BuildViewHistoryText')
  , ('fa2645b70f9f5d77', 'client', '<color=#FFD94D>Ranked:</color> -', 'a777582de015d6aa189d5e987dbb22330ea290f1', TRUE, 'NativeUI · RefreshMyStats')
  , ('bcdff3edc272aa6b', 'client', '<color=#FFD94D>Ranked:</color> {0}W/{1}L', 'c41e0c77ac7efea07d68b205c2ecda2ffefff35e', TRUE, 'NativeUI · RefreshSession')
  , ('a8819ea6d6d92590', 'client', '<color=#FFD94D>Tournament Bets</color>', '9e5528e83988d0fe31130a64d84940a4ce613670', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('67512e2203553827', 'client', '<color=#FFD94D>Tournament Bets</color>  <color=#888>({0})</color>', '3cf1b99fc01b57402610dbabdbb5f9de562ed881', FALSE, 'NativeUI · RefreshTournamentBets')
  , ('85ecd41da4fb57e5', 'client', '<color=#FFD94D>Tournaments:</color>', 'd93c51495c04409d37e36b4dce1930a45ce9de61', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('37cef70e8e3c67b9', 'client', '<color=#FFD94D>bets open</color>', '83e4d7479a0d6e1b9bc981e87ea959dfa0760ab0', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('70fd04265821e7cd', 'client', '<color=#FFD94D>earned {0}g</color>', '447bf00a8adf3e15948428f8d350b4499a403d82', FALSE, 'NativeUI · RefreshArtistTab')
  , ('dd4ea253253e8050', 'client', '<color=#FFD94D>in progress</color>', '4aa5a0655e06b7f207582228c71b66d5028d5cb9', FALSE, 'NativeUI · BuildViewHistoryText')
  , ('54e0b2b24a2a7db2', 'client', '<color=#FFD94D>matched</color>', 'b0b71909756991fcf90414da2cb57268efda11fb', FALSE, 'NativeUI · RenderTeamQueueSection')
  , ('0eef1f90d4357dc2', 'client', '<color=#FFD94D>pending initial review</color>', '4a8962e2f2c84e3dce462d200654ced2b3d2d81d', FALSE, 'NativeUI · RefreshArtistTab')
  , ('4a8b293a77d306af', 'client', '<color=#FFD94D>waiting on opponent to ready</color>', '3cffeddae82eed3b3379cd14e387b6c79acb87e3', FALSE, 'NativeUI · RefreshTournaments')
  , ('835d7f9bb4c99884', 'client', '<color=#FFD94D>your bet: {0}g on {1}</color>', '3742df76f32ab0da59ea2444feba18ecbdbb7ebf', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('aafc6e75fcf4e31e', 'client', '<color=#FFD94D>{0}/{1}</color> <color=#888>({2} live)</color>', '8b2254a1486ea8c6e6baef7aef2d8d0e16aaa60a', FALSE, 'NativeUI · RefreshTournaments')
  , ('76ca3828c8c44f21', 'client', '<color=#FFD94D>{0}g</color> <color=#AAA>paid to</color> <color=#FFD94D>{1}</color> <color=#AAA>artists - {2} copies sold, {3}g gross</color>', 'b1a9647bbf64260e0acbc6c4172aeba96327b59b', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('d8ede9573dbac9c7', 'client', '<color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(played {3})</color>', '7e01cae4dee9862c4d799b06bd66d619c0c0bf92', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('5e6611223ccd2e52', 'client', '<color=#FFE580>Report a Bug</color>', '38a56a2898844a92391b086b48afb2f86e9b282d', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('d5984dd5e64c618a', 'client', '<color=#FFFFFF>{0}''s lobby</color>  <color=#7FD4FF>{1}/{2}</color>  <color=#888>open {3}</color>', '670a333677a5cc92eb43fc800aa6d4eebb14a325', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('68df4873f949229d', 'client', '<color={0}>*</color> <color=#FF6688>Live Ranked Games</color>', 'f474f703aeed6b41dfd3481051df0c1ce534977e', TRUE, 'NativeUI · RefreshLiveSeries')
  , ('725a66f0f66e8076', 'client', '<color={0}>Blue</color>', '2aa5db947eb5e12f3d13857640ae1a52c1cee360', FALSE, 'NativeUI, PostSessionReport · Compose2v2, RefreshTeamTab')
  , ('48fd57c668c63dc7', 'client', '<color={0}>Leave: {1}/{2} ({3}%)</color>', '68e41b4c2415fc16a601f9284cc62d1a0d1e1253', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('2f4cf0864647f848', 'client', '<color={0}>Orange</color>', '9d44c73676aa56f6df4f33a819ebcc1b81cd2034', FALSE, 'NativeUI, PostSessionReport · Compose2v2, RefreshTeamTab')
  , ('a48aabea4f23dd8e', 'client', '<color={0}>blocks activated</color> <color=#888>·</color> <color={1}>blocks successful</color>', '4cd08e5b924d614d8b7d2101d897878e723e183e', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('2ecb6cb6c2115f85', 'client', '<color={0}>damage taken</color> <color=#888>·</color> <color={1}>successful blocks</color>', '77e0830c9bc8e1fc14028e4bdd1aca34e982a104', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('d8dffa7fcf53bf24', 'client', '<color={0}>shots fired</color> <color=#888>·</color> <color={1}>shots hit</color>', 'e82e104b11bebbce91bb2e80656c0a1caa7ff995', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('87ca1318e268efac', 'client', '<color={1}>{0}</color> <color=#888>— match telemetry</color>', 'b25566068f7a1de5405117c1faedecb7c5f826a6', FALSE, 'CompetitiveUI · DrawPlayerComboGraph')
  , ('e9e3d228a8a417de', 'client', '<i>Bracket revealed when the tournament starts ({0}).</i>', 'f65e022050c1a88faf87361ea25ea8ac2c91b4d8', FALSE, 'NativeUI · RefreshTournaments')
  , ('c03c7656a49eff87', 'client', '<i>Loading...</i>', 'd0667f54a4ee675f5e782d96c69d285d5da2696c', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('37619318e89a10b3', 'client', '<i>No completed tournaments yet.</i>', '6b744a30866dcf35b49494894390498c054b5add', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('644ccc8abba37deb', 'client', '<i>The bracket appears once players sign up.</i>', 'cc431e8b80c8979c751fb43424e33c02902d1388', FALSE, 'NativeUI · RefreshTournaments')
  , ('f101e7dfe9aebb16', 'client', '<size=80%><color=#7CFF7C>(you)</color></size>', 'e831ea71c515905031066ca0811cc3514f4b19eb', FALSE, 'NativeUI · RefreshTeamTab')
  , ('b10f784abe59d8ef', 'client', 'A MODDED PLAYER SEES', '0ed3ea4113b2726f9870b87104a8eea6a7e5e2d8', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('c3ff7b61de7b2cb2', 'client', 'A NON-MODDED PLAYER SEES', '7a7005c30bcb5cd09fb1489f56c4acbf5968dbf1', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('b6a4621d6912a7e6', 'client', 'A SERIES IS FIRST TO 2', 'c790d4c7e5ac933c97c61a08108a8515f1549902', FALSE, 'InfoViz · BuildSeriesFormat')
  , ('bd0bc7f08f0598fa', 'client', 'A Shiny trinket for those who feel lucky', 'ba1d0e86c4762d03e8cf3638291ac7575929c326', FALSE, 'shop catalog · cosmetic name/description')
  , ('57f539baa20955f8', 'client', 'A bold red mouse cursor.', '28329a6c2291ab34539160eafed7e0a58654883f', FALSE, 'shop catalog · cosmetic name/description')
  , ('7420d8cc3e98ff5e', 'client', 'A braided crown of twisted thorns, blood-tipped.', 'f26aed94347cea2e644f80d3c4339839bf4741c5', FALSE, 'shop catalog · cosmetic name/description')
  , ('28d4ff2dae7455f9', 'client', 'A bright orange mouse cursor.', '23e39b1ad591fe7bb634d0bb71deb0af7c7f6c47', FALSE, 'shop catalog · cosmetic name/description')
  , ('936c8c700ad2e14e', 'client', 'A bright, sunny yellow.', '09760c239e5f1eaaaed919af1b3c0b4b59cde787', FALSE, 'shop catalog · cosmetic name/description')
  , ('fc23457a57683e0e', 'client', 'A burning crown of fire. ANIMATED.', 'fd205b824b53ed05147b7286bfcdbef4e9d8c77a', FALSE, 'shop catalog · cosmetic name/description')
  , ('fd240ccd9449ca74', 'client', 'A card freezes its player''s title, rating, record and rank as the leaderboard had them on the day it was pulled; the name and the picture stay live (a renamed player shows their new name). Every player who has run the mod from a Steam account and is not banned can be pulled; a public binder and pull announcements are your Settings, and deleting your data removes every card of you from every binder.', '5688b1c7c63a79869d3d5a88ecffc466c9e35bf1', TRUE, 'PlayerCardsUI · RefreshInfo')
  , ('e04bd2c0f601b644', 'client', 'A card in that trade changed hands moments ago - try again later', '09308de1d107bd47e1565d1bc2525dcad818a707', FALSE, 'PlayerCardsUI · ReasonText')
  , ('86e25828ecd05ba5', 'client', 'A card in that trade is no longer there', 'e4f0c1389fef16584a5603218e899e2bb62828f5', FALSE, 'PlayerCardsUI · ReasonText')
  , ('5bbfff5a528c2a96', 'client', 'A card in that trade shows a player who can no longer be traded', '547beaf1a77f9f44c3818531bc52a96daeeb1b78', FALSE, 'PlayerCardsUI · ReasonText')
  , ('71e3ee43149aa274', 'client', 'A clean white line. The basics.', 'd1bf71529da76b7d1a3d412a4db22ec2f634c046', FALSE, 'shop catalog · cosmetic name/description')
  , ('f68275e9faed6821', 'client', 'A clean white mouse cursor.', 'e5f0c878ca68b6046f356f8b4e10dff4be9ab299', FALSE, 'shop catalog · cosmetic name/description')
  , ('f5fa897d8e716419', 'client', 'A cool cyan mouse cursor.', '72115355dca2abe0a4c5925cae462041c92fb3f3', FALSE, 'shop catalog · cosmetic name/description')
  , ('a70f99966e0958b8', 'client', 'A crackling ring of living lightning. ANIMATED.', '3d27acca20b71363bd39579002d1e2d47ab735bd', FALSE, 'shop catalog · cosmetic name/description')
  , ('33d92083da701bc8', 'client', 'A dark trail lit by drifting warm sparks.', '4c1dc591501192d873bff90728e05c837a820f95', FALSE, 'shop catalog · cosmetic name/description')
  , ('878cbf198b4c88e0', 'client', 'A deep blue mouse cursor.', 'ad047b0b34bba2c06aa7eaf784f0aa9c665c11bc', FALSE, 'shop catalog · cosmetic name/description')
  , ('054aa178a79fbbd0', 'client', 'A deep indigo between Purple and Cyan.', '8ccaaa302ea73bdb9bead1a6ec141229cea2d9dc', FALSE, 'shop catalog · cosmetic name/description')
  , ('b0b49ff92e08c74a', 'client', 'A deep wine red.', '70b6c54dc1c13ff24f68f5b1e66b0170e9871bd4', FALSE, 'shop catalog · cosmetic name/description')
  , ('2aad25bde6099301', 'client', 'A deep woodland green.', 'c1855544914c1abd869dc681d7a531ee05833e2c', FALSE, 'shop catalog · cosmetic name/description')
  , ('809359b5ebebe8d5', 'client', 'A deep, dark skin tone.', '067b43f4b1519da09b0ac300e59a647f12ae7d65', FALSE, 'shop catalog · cosmetic name/description')
  , ('95f4cbc38f450bc9', 'client', 'A deep, earthy yellow.', '841134a9aa1e8b90a49cb4c5b535ebb37e812e5a', FALSE, 'shop catalog · cosmetic name/description')
  , ('7be9b5f7a848839b', 'client', 'A festive crown of twinkling lights topped with a pulsing gold star.', 'ef5205084dc052e1551b3a5b29613d80ee2d61be', TRUE, 'shop catalog · cosmetic name/description')
  , ('3739b2d530f6debd', 'client', 'A fiery bright red.', '04f6ac1ae02e6475938fb263bc4b7960aaa14465', FALSE, 'shop catalog · cosmetic name/description')
  , ('8ec026c42940c6d2', 'client', 'A glowing trail that follows your character body during combat. Only visible to modded players; the shop preview shows it following your cursor.', 'c814dc7375c9e38a44272ffd35f78577ece5f21d', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('5eb6d5777bd80861', 'client', 'A grin for those who feel most devious', '07519800157f4a2da4b48a1d0b215d7c5b5a8cde', FALSE, 'shop catalog · cosmetic name/description')
  , ('6b91a0c0f2c14c99', 'client', 'A hard helmet for those who are going to war and need to cover their heads', '56e6b3b32501d5af9853e7f97e93a55b819286c2', FALSE, 'shop catalog · cosmetic name/description')
  , ('abe3b20d82427246', 'client', 'A hot pink mouse cursor.', 'e0b04f7776991125df7976fc25df6c378d7ee39d', FALSE, 'shop catalog · cosmetic name/description')
  , ('b75fe59845fa7ecd', 'client', 'A light, warm skin tone.', '4a82ef21d0b89f6ba37a2b6c2fe3be74c8e23d34', FALSE, 'shop catalog · cosmetic name/description')
  , ('583edabb1e09ee16', 'client', 'A muted, earthy olive green.', '9f3a21630b49c6794c32656c33e432d3bf84e405', FALSE, 'shop catalog · cosmetic name/description')
  , ('1c5ca8998520e7b6', 'client', 'A pack is still being resolved - hold on', 'd5995564f7e4524bd35292525973fd3dca75459b', FALSE, 'PlayerCardsUI · BeginBuy, BeginOpenHeld, ClaimDaily')
  , ('b7190d12e8059923', 'client', 'A pack is still being resolved - it will be checked again shortly', '82c81663b6e1bf07ec2e31e0c027bd2c48aa9411', FALSE, 'PlayerCardsUI · Refresh')
  , ('0eb9d390e9bc1332', 'client', 'A player hasn''t received the new settings yet - try again in a moment.', '69c0abe342301e526c40f7a5d35f45a2bdf0fe7d', FALSE, 'ApiClient · RulesDetailText')
  , ('3be1d34ee41432a2', 'client', 'A player in this game has spectating disabled.', '24ad5e206229cc67502993213938522f279d44a4', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('84946b4141a8ec23', 'client', 'A player joined the match', '0372c4d71395a2ad9b46eed2d4bbda84e321f3bb', FALSE, 'FfaLateEntry · AfterPair')
  , ('d2b6d79b4f892ce6', 'client', 'A player''s mod is too old for these settings - they need to update, or turn the setting off.', '6176dc518ac6e5e39151cdaecd9f17309c6955ed', FALSE, 'ApiClient · RulesDetailText')
  , ('d4723ed96203417e', 'client', 'A quick follow-up shot (QShoot) counts as Conditional damage', '9954788202428cecdadff2a0a65362345ce8612f', FALSE, 'InfoViz · BuildRefreshWindowSequences, TextFallback')
  , ('8a633c693695b715', 'client', 'A radiant golden sunburst. Blindingly righteous.', '5393acd21dc5762f827bd626eb1baa00e2a5f856', TRUE, 'shop catalog · cosmetic name/description')
  , ('0f54805e99c76854', 'client', 'A ragged black cloak with a blood-red lining.', 'a60ac5e701992bb53799c6435d8fa9cfeebbbcd0', FALSE, 'shop catalog · cosmetic name/description')
  , ('e763ddfa52f56c01', 'client', 'A rich, gleaming gold.', 'f9440b94808ba8103d9205ae89bd4358d0263fec', TRUE, 'shop catalog · cosmetic name/description')
  , ('97048d0dbba0b0ad', 'client', 'A rich, warm brown skin tone.', '6b92c53eadd095e5577c7c13641831ea4e80d518', FALSE, 'shop catalog · cosmetic name/description')
  , ('7f1e2dff680a21ea', 'client', 'A royal purple mouse cursor.', '26435e21d715685d5614c144df3ac5faaf6a77e5', FALSE, 'shop catalog · cosmetic name/description')
  , ('76de6671a0e43d50', 'client', 'A shimmering rainbow of particles cycles around you.', '12d7c24417f733987cc887cc155326577389eee7', FALSE, 'shop catalog · cosmetic name/description')
  , ('060ce37e54f9db7d', 'client', 'A shot placed second: the shot Refreshes and resets the flag', '61fc1f50fb545395d209750161092562acaa7e35', TRUE, 'InfoViz · BuildRefreshSequences, TextFallback')
  , ('6458681422d8fc26', 'client', 'A shot placed third: an extra Refresh', 'd34adb2bd4ee36ed20f7b9c4217cec2ddfe6e5bd', FALSE, 'InfoViz · BuildRefreshSequences, TextFallback')
  , ('5c299cdd5181a941', 'client', 'A silly little mouth for feline ethusiasts', 'fbc862283106c3ad11970e3d7528cb421283e2e5', FALSE, 'shop catalog · cosmetic name/description')
  , ('3cadba6cb4d299db', 'client', 'A silver trail with white twinkles. Leave a little sky behind.', 'e735d970c376d796959969c8839aece4074458dc', FALSE, 'shop catalog · cosmetic name/description')
  , ('185819c37faec22c', 'client', 'A sleek black mouse cursor.', '5d67c42eb8f5c9f4a3e92e8852f30b18b536c4c9', FALSE, 'shop catalog · cosmetic name/description')
  , ('66173b472176d55a', 'client', 'A slow starfield in violet and blue. Bring your own gravity.', 'f21e9b7f054b8df1f3badc742f510743bbbf019f', FALSE, 'shop catalog · cosmetic name/description')
  , ('e3e5ec5ee886c897', 'client', 'A small grey cat based on my real cat', '1c8cdb1aadf7440df733f47304d419a4e7dc9ab2', FALSE, 'shop catalog · cosmetic name/description')
  , ('b842e9bcebcddf77', 'client', 'A soft amber distinct from Gold.', 'bb1a91bcbeb57bb030beb06e6801c3123650ebc8', TRUE, 'shop catalog · cosmetic name/description')
  , ('7a9dce7f07ce4812', 'client', 'A soft green aura that says you know what you''re doing.', 'd6682c54bc14e1ceeaab8f5c5f4d028edeb46ae9', FALSE, 'shop catalog · cosmetic name/description')
  , ('79d45b2ce8d63afa', 'client', 'A stylish hat for those in the mafia', 'a1c54a88a06fa44bfb072b8e23ae00e2ff16bc1e', FALSE, 'shop catalog · cosmetic name/description')
  , ('3a765650a0fabfe1', 'client', 'A sun-kissed medium skin tone.', '084e935f9f75ddb12ece11b4db28468ba8e41034', FALSE, 'shop catalog · cosmetic name/description')
  , ('72f872abc86378a5', 'client', 'A sunny yellow mouse cursor.', '0e3adaa92340b7253fd391d5801e47286f66c549', FALSE, 'shop catalog · cosmetic name/description')
  , ('ed739ead9015b738', 'client', 'A trade between you was reversed - wait before trading again', 'e92f57b6a8973553cae979e5569e08eedc860505', FALSE, 'PlayerCardsUI · ReasonText')
  , ('9c7b9e8923006966', 'client', 'A vibrant green between Gold and Cyan.', '2b5232add8ebb0b0b10d3340988527aba0746bcd', TRUE, 'shop catalog · cosmetic name/description')
  , ('82a50967a8775147', 'client', 'A vivid green mouse cursor.', 'b6ccb321cd37c9a941a874741f8a5b53b4e22012', FALSE, 'shop catalog · cosmetic name/description')
  , ('b55e98320a2c5883', 'client', 'A warm coral pink matching the new Coral body.', 'c0d79153a0f91fd7a0675abc1920dbfb911a8244', FALSE, 'shop catalog · cosmetic name/description')
  , ('84dea13d4f8749b7', 'client', 'A warm coral pink with hints of orange.', '4d33160cf65e8ee1374dbcda15cd04d741ffbaf8', FALSE, 'shop catalog · cosmetic name/description')
  , ('1198284ca4ddd03a', 'client', 'A winners-bracket loss drops to the lower lane; lose there and you are out.', 'dfca1636d73096541e96ab0c3463eea6b8867dde', FALSE, 'InfoViz · BuildBracketFlow')
  , ('705f3184942e5c20', 'client', 'A zesty yellow-green.', '093f93f6bc96df2c125019d556d7ef7a8e6b54e2', FALSE, 'shop catalog · cosmetic name/description')
  , ('bc49fa6684de77c3', 'client', 'AFK: zero shots, blocks, picks', '5ae5564648a3decf4f1564b4f1973cfc7ca0d622', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('bc5daf52ecfcb394', 'client', 'ALL CAPS', 'baf48506da4f8fcb158b020e9780f52833d663a4', FALSE, 'shop catalog · cosmetic name/description')
  , ('201957b56ba2eae8', 'client', 'ALT', 'a85e90f9835e6411e691ebde65582614cea81732', FALSE, 'InfoViz · BuildKeyboard')
  , ('7cc033f4e2ccee08', 'client', 'ARTIST STUDIO', '9c4cc5ddd54ef465a817bc3d4ad390d86342f142', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('2d1db6735c56466b', 'client', 'ASYNC', 'ff88c6a1299ead416f52354a1dd01d933a17b908', FALSE, 'NativeUI · RefreshTournamentGameIndicator')
  , ('709024e93f016139', 'client', 'ASYNC (6-week)', '7c4bd3155e01af462f64d585c6c85694a525cccd', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('1dd3db8c064d9654', 'client', 'ASYNC MATCH DEADLINE', '246386952c55f6e0b6f2ee074517a11ea3b7cb02', FALSE, 'InfoViz · BuildForfeitClock')
  , ('5d9749b7d1d2cd50', 'client', 'AUTO-BALANCE', 'd8796d7466c24ad713a37062fa958677b0622370', FALSE, 'InfoViz · BuildTeamFormat')
  , ('1a177c3441888ac5', 'client', 'About', '6b21fb791ac05170893860c248401cd24a59b732', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('c64eb8b40ee8fec4', 'client', 'About this library', '4e66bcda284b43d3d5f66c282f86cea9fe749319', FALSE, 'InfoLibrary · (file scope)')
  , ('34323f3c43b0f286', 'client', 'Abyss', '030d9312f32b78411ae6fd45521eafa5e3f16e4e', FALSE, 'shop catalog · cosmetic name/description')
  , ('c38e5d2842896ff4', 'client', 'Accept', 'bb54db510a92908a5a4df79fc1ad1eae8df50ec3', FALSE, 'NativeUI, PlayerCardsUI · BuildAdminQuarantineRow, CreateTradeRow, FillTradeRow')
  , ('e877a1fcfe29885e', 'client', 'Account changed — message not sent.', '409248bd819c24b920be00aff13c040ade3ea767', FALSE, 'CompetitiveUI · DropChatOnAccountChange')
  , ('04d484848df97dbc', 'client', 'Account deleted', '98f1df63c0f2f97736487bef4b61303f752e1243', TRUE, 'ServerTextRules · TrRefusalDetail')
  , ('d7dc886afa083aff', 'client', 'Achievement Grid', '6a57dfd4acb6187e4a37477d30874ac5ee9bffb7', FALSE, 'NativeUI · TrMetric')
  , ('b2589813d7fe449c', 'client', 'Achievement Unlocked: {0}!', '5bf5fdcdb65caf6b9ba3b018c97ee583e7630856', FALSE, 'ApiClient · FetchAchievements, UnlockAchievement')
  , ('4b7b3bb3843c5b2a', 'client', 'Achievement comparison', '079b57c26436586e5179bd49537d3492f766534d', FALSE, 'NativeUI · BuildCompareAchievementGrid')
  , ('b6d9767052faaed9', 'client', 'Achievement guide', 'eed6829db70d00d75f1575ea1f18feaa88b4b97b', FALSE, 'InfoLibrary · (file scope)')
  , ('444f6214f679a435', 'client', 'Achievements', 'a6634f24b2db61aafb90e6954e00e3a9ba699d80', FALSE, 'InfoViz, NativeUI · (file scope), BuildAchievementsTab, BuildGoldSourcesLegend +2')
  , ('8fff31eb51a2e6ee', 'client', 'Achievements unlocked', 'a50b9dbf33783b0f870ae078af30d1dd7c756577', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('61b604ec28fa4123', 'client', 'Action', '97c89a4d6630adeb18fa12ba9976a31413fe293e', FALSE, 'InfoViz · SeqTable')
  , ('fd68f9ec138655b1', 'client', 'Action Log', 'be93470195f3332d7adfd1047a5c6c18dc1f1b8c', FALSE, 'NativeUI · BuildAdminTab, RefreshAdmin')
  , ('28fe1c29d7ee1982', 'client', 'Action Log...', '1f50d36eaab8e0a95f5ac611ea82dcce423107cc', FALSE, 'NativeUI · BuildAdminTab')
  , ('f1ad6bb2e30613b4', 'client', 'Active', 'a733b809d2f1233496ab516eed0f3ef75cf3791a', FALSE, 'shop catalog · cosmetic name/description')
  , ('f85c8b24b7e324a3', 'client', 'Actually Good', '74872dbbc2af46be62c708a8e0777b8e12d0ad7d', FALSE, 'shop catalog · cosmetic name/description')
  , ('74a20714cad97636', 'client', 'Add a subject.', '16ecfef56ef460e948a4a7706fed0e166a2fc249', FALSE, 'MailClient, MailUI · ErrorDetail, SendCurrent')
  , ('3a70a1caae7433a3', 'client', 'Add an underline to your name. Stackable with other name styles.', '5bcd1bc127edaf471cf8fc9daae11e05d0ea4bac', FALSE, 'shop catalog · cosmetic name/description')
  , ('7ba47858481b8cb5', 'client', 'Add at least one recipient.', '7a474745d680ea5776d07b77326820530491bc6e', FALSE, 'MailClient, MailUI · ErrorDetail, SendCurrent')
  , ('fb141f420287e2e0', 'client', 'Add extra character spacing.', '7f73305879a039b508248f80ce6511bbd64ef4b4', FALSE, 'shop catalog · cosmetic name/description')
  , ('d6ddb3145c092024', 'client', 'Add recipient', 'a989d1f178daf1628c77e5deaed5fa68ff871312', FALSE, 'MailUI · AddRecipient')
  , ('0d6434110df619b3', 'client', 'Adjust Placement...', '6c8fc4ba295689e94a0b72bb52f19286b2b3303b', FALSE, 'NativeUI · BuildArtistTab')
  , ('08b1965af9d1ef0b', 'client', 'Admin', '4e7afebcfbae000b22c7c85e5560f89a2a0280b4', FALSE, 'NativeUI · (file scope), OpenAdminRosterPicker, UpdateTabBarVisual')
  , ('4af3c9568c8e3ff0', 'client', 'Admin action', '53acd6e7e3c30fdf792e093fb553fcc69a49eea6', FALSE, 'NativeUI · OpenAdminActionLogPicker')
  , ('6620333e3e9989e6', 'client', 'Admin action log ({0}-{1} of {2})', '3db1798f11598eedd49a8cbcbeadd842f8088b4a', FALSE, 'NativeUI · OpenAdminActionLogPicker')
  , ('40d13cf83efbf1df', 'client', 'Admins - type to search', 'd565f607bd7cf6e750de762ad7f46ad0633acf6a', FALSE, 'NativeUI · OpenAdminRosterPicker')
  , ('eef6ec9b90a29c49', 'client', 'Admins can''t be kicked.', '978584de4b6f7d4fc7b8b46acca9ebd63346d699', FALSE, 'ApiClient · KickRefusalText')
  , ('4831593966605443', 'client', 'Admins...', '993ae96a5bc8a29e1ad8a10810f1b6cf60e712eb', FALSE, 'NativeUI · BuildAdminTab')
  , ('0f250d61631c5546', 'client', 'Advanced', '4d064726954a17487f94e931f5b157b733ec22ed', FALSE, 'InfoViz · BuildRankLadder')
  , ('a29f86876ba4a433', 'client', 'After 60s unfocused at the menu, drops the engine to 15 FPS. Never active in online rooms or when a match is found; wakes instantly on focus.', '2a58a099d42258b34d81bba814b8b531cc638c51', FALSE, 'NativeUI · BuildSettingsTab')
  , ('6b9f566f9adbde33', 'client', 'After a game you played in, this sends the same logs the bug-report form sends, so a problem can be looked at without you filing a report. Also sent: your Steam ID and name, your opponent''s Steam ID when the game had one, the room name, the game mode, the series ID, and the mod and game version. Removed first: every path through a Users folder, however the slashes are written, and this PC''s own profile folder; and this PC''s Windows account name where it stands on its own in a line, when it is three characters or longer. The Steam login ticket the game writes into its log is replaced by its length and a short fingerprint. Nothing else is removed - the same name inside a path we did not recognise, or in an e-mail address, stays. At most one upload every five minutes. Nothing new is sent while this is off, and turning it off cuts off an upload already in progress - though any part of it that had already reached the server stays there.', 'efbaa99c9e12efda0566a9bca50511116a2b1442', FALSE, 'NativeUI · BuildSettingsTab')
  , ('37501be191dd7d66', 'client', 'Aged metallic bronze with a warm gleam.', 'd738ebfc6a7ca0bfb0966d34a7228b7448258df0', FALSE, 'shop catalog · cosmetic name/description')
  , ('b89ffcf2f3023062', 'client', 'Aged wine — deep red with a brown undertone.', 'cc6b2a579218473a35deacda2f0d5d288cf56c9d', FALSE, 'shop catalog · cosmetic name/description')
  , ('ad11b6f7ca557add', 'client', 'Albums have unlimited stock', '05353af9d3b5d51ef1e6ad31b9a4042675e7a13c', FALSE, 'NativeUI · RefreshArtistTab')
  , ('acb991947bff96e9', 'client', 'Alert category', 'd86a6e9a016d86b1c6146341dea428756ce4a5a0', FALSE, 'NativeUI · BuildAdminTab')
  , ('049df31057f1ee37', 'client', 'Alert is live.', '49ec9e731f057222bf0dd06550c791aa806317ac', FALSE, 'NativeUI · BuildAdminTab')
  , ('aa2ab030a7e8ca31', 'client', 'Alert revoked.', '56ca995f75e4f3ad0f6d006eeec8862fbae7d5bb', TRUE, 'NativeUI · BuildAdminTab')
  , ('9ad25dd88adfebfa', 'client', 'Alien Antennae', 'cee5ec293ece08f8b8d87a2b278c5a6bcd35fe37', FALSE, 'shop catalog · cosmetic name/description')
  , ('dc9683e025054f9e', 'client', 'All', '6a72085653e4c5be8c7640c868ef787cbcf063d1', FALSE, 'NativeUI · (file scope), BuildCardStatsTab, SyncShopArtistFilterButtons')
  , ('2c0bcac005222b8a', 'client', 'All (merged)', '0cffeabac63123322aba0bfa89e7867134d572bf', FALSE, 'NativeUI · ChatChannelDisplayName, OpenChatViewPicker')
  , ('09a1aa463f338351', 'client', 'All cosmetics - everything available, grouped by category.', 'b86445f0e6c41a5f76bc9faa3b81b6b4f2fb8959', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('1c210f8ba97a1f77', 'client', 'All of these tests were carried out in the sandbox gamemode using two players, one on keyboard, the other on controller. Each test was repeated multiple times to ensure the results were consistent, or at least consistently inconsistent. No distinction was made between Timed Detonation AoE damage latched onto a player vs latched onto a surface.

Promising potential damage dealers, such as Chilling Presence, were excluded due to both their failure to trigger any cards or buffs and their failure to deal any damage. Every entry on the list deals damage in some form, and every unique way to deal damage has an entry. Thus, there are no methods to trigger any damage-dealing cards or buffs without dealing some amount of damage. That might seem obvious but, given the weirdness of the rest of the system, one can never be too sure.', 'e358740b825518d127f9d3b4cffac22635cab524', FALSE, 'InfoLibrary · (file scope)')
  , ('f1144eb024aa03eb', 'client', 'All picks (oldest first) - red = replaced:', '940bbeb152752a33c9934bdce09b0298902a4d0e', FALSE, 'NativeUI · BuildFfaCardsText')
  , ('32e0e9f53990fa6d', 'client', 'All spectator seats are taken.', '6f9ee606b18a4b43b02ab28e1e3fa92283ccadbd', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('ec8d7a94985d2f92', 'client', 'All-time: {0} games ({1}W-{2}L), series {3}-{4}', '7c6eec66c9a19dfba83a37b6f5d91874f364b468', FALSE, 'PostSessionReport · Compose1v1')
  , ('10c4a32e22d79a83', 'client', 'Alley King', '674d5a895ca44d050a992c1510963d8a2f72e842', FALSE, 'shop catalog · cosmetic name/description')
  , ('72c46d73f688cf70', 'client', 'Allow data reporting', '1f8b1718e42040156e0683e7453e89a25bcad08f', TRUE, 'CompetitiveUI · DrawConsentModal')
  , ('2d1a71bebc25ca03', 'client', 'Allow other players to spectate your ranked games. Turning this off also removes current spectators.', '2913e520b772748a9b47eac3f069e372230accaa', TRUE, 'NativeUI · BuildSettingsTab')
  , ('6e855ac0bf320887', 'client', 'Allow spectators: <color=#888>...</color>', 'ae54dd55b18547fd56be56e76e010b16192a24b8', FALSE, 'NativeUI · PaintAllowSpectators')
  , ('4fab04e5db11f52a', 'client', 'Allow spectators: <color=#88FF88>ON</color>', '9be86673cda0c0007bf2d4f313d7c5a5c805c626', FALSE, 'NativeUI · PaintAllowSpectators')
  , ('c9630c50abedb69b', 'client', 'Allow spectators: <color=#FF9966>OFF</color>', '85ff4e3ddc16a8c134e81be751bc9b2ee9717b30', FALSE, 'NativeUI · PaintAllowSpectators')
  , ('8cb4eac07551b7ab', 'client', 'Allow the mod to report your match results and stats to the community server.', '43555f317525b8d8043a88c97bc8432a0500d549', TRUE, 'NativeUI · BuildSettingsTab')
  , ('93c5a58d3c0c6593', 'client', 'Alpha', '58061aa544398a798e33181a443b15b7746fab16', FALSE, 'shop catalog · cosmetic name/description')
  , ('f04b4a746d22f53e', 'client', 'Alpha Cat', '8d1bb8cde37137bf0145f401f23beb46e6c1fe86', FALSE, 'shop catalog · cosmetic name/description')
  , ('a9668913261f1513', 'client', 'Already a recipient.', '20f5ec2c72cb088069f990da60c6335373f7e0c0', FALSE, 'MailUI · AddRecipient')
  , ('76b8a4f1fd8f2c17', 'client', 'Also DM new mail to your linked Discord. You can reply from there.', '2332e2b13de543db51a5b17e6bd202ae49cc6359', FALSE, 'MailUI · BuildSettingsRow')
  , ('8296ada6cf24fcb6', 'client', 'Also removes your Player Cards: your binder is emptied, and every card of you is removed from every other player''s binder.', '2a36232b8881d09bb23ecbb902dfa4f16aecc480', FALSE, 'NativeUI · BuildSettingsPaneTexts')
  , ('9579a7086a61c98e', 'client', 'Alt', 'e30eff925100b7c3e119ed678e39009e962455b0', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('b12d3b10d328bcd2', 'client', 'Alt Graphic', '4da67bce366023649592dc3e5796d7567f1ad904', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('20d99221097e1fef', 'client', 'Amber', '27a01d4772038a3f83552908e0470604e773f8af', FALSE, 'shop catalog · cosmetic name/description')
  , ('e74a5c961fcffa93', 'client', 'Amber Name', '55879cd931aa5e3de8d5fdf3e442cf30a8cc34c8', FALSE, 'shop catalog · cosmetic name/description')
  , ('dcbcb0e4299e1c29', 'client', 'Amethyst', '1ef532cce6fea64ba94eed1237cc785bcbd74ad0', FALSE, 'shop catalog · cosmetic name/description')
  , ('2b07bbabfb8a43f6', 'client', 'Ammo', '407c60401b79318f2877683ed6df36f0bda6cfee', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('4242863b150cbda8', 'client', 'An aurora follows you. Green and violet shimmer with sparkles.', '38d6c96d36ce8a29693c24c898c7948d153eb801', FALSE, 'shop catalog · cosmetic name/description')
  , ('4696d74de83a8330', 'client', 'Ancestor', '4d16c26aafdb910a6de98644a2f82c86329498c7', FALSE, 'shop catalog · cosmetic name/description')
  , ('f11e08d3a8b105a1', 'client', 'Ancient One', 'cc73610a89b9cb3625f0144a528c63547ada60aa', FALSE, 'shop catalog · cosmetic name/description')
  , ('795584614209151d', 'client', 'Animated cosmetics: <color=#88FF88>ON</color>', '953db08d420badd7066c9c7eb5e205966ed7ad27', FALSE, 'NativeUI · PaintAnimCos')
  , ('b94b0705d8006de4', 'client', 'Animated cosmetics: <color=#FF9966>OFF</color>', 'b504da153c3770cd3fc15e8be88d51230b4c8f01', FALSE, 'NativeUI · PaintAnimCos')
  , ('5346ec349129ccdd', 'client', 'Animated cosmetics: prismatic/chrome body colors, prism trail, player effects, map-skin shimmer, animated faces. Off = everything freezes on a static frame.', '5529efca285a7da8d70b2fe896a6b3c9168f9870', FALSE, 'NativeUI · BuildSettingsTab')
  , ('c076e7c805e99ed5', 'client', 'Announce my pulls: <color=#888>...</color>', 'eacb6cd01d29de35c0ea0610e1ea2007edea65b7', FALSE, 'PlayerCardsUI · PaintAnnounce')
  , ('33d4d392c9be3105', 'client', 'Announce my pulls: <color=#88FF88>ON</color>', '7cceece0908ab09b8cacb0777bce44498cf386bd', FALSE, 'PlayerCardsUI · PaintAnnounce')
  , ('038a0b06714e18b8', 'client', 'Announce my pulls: <color=#FF9966>OFF</color>', '2f56655f6d637a3d15eca9fcd120e99d61c3fc60', FALSE, 'PlayerCardsUI · PaintAnnounce')
  , ('aa14ab7e25714c02', 'client', 'Announcement', 'cf84a98d6cf7f156862a08ba8236467b6f471004', FALSE, 'MailUI · PaintReader, RowLabel')
  , ('f3812bc2b6293012', 'client', 'Anonymizes your Steam ID, display name, and Discord link. Matches stay so other players'' Elo and histories aren''t affected. You will no longer appear on leaderboards.
<b><color=#FF8888>IRREVERSIBLE:</color></b> this Steam ID can never re-register. Future matches from this account will show as [Deleted User] and won''t count toward stats.', 'c294dd8cfffa97ad51155538b632d042aace7e03', TRUE, 'NativeUI · BuildSettingsPaneTexts')
  , ('6c12e59cb06be91e', 'client', 'Another Round', '857132eebe84c050a0d8339923da43657fdfcb15', FALSE, 'shop catalog · cosmetic name/description')
  , ('c350b64d06ed03ad', 'client', 'Another player is using your seat identity', '26795e3f584178571150f96c7886efc9bfe1cef7', FALSE, 'FfaReadmit · Refusal')
  , ('fe3e2890029979eb', 'client', 'Another player left. The match ends as a disconnect.', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', FALSE, 'TeamHoldBanner · Line')
  , ('3e3901c226612420', 'client', 'Anti-cheat', '4c632b2b3d50160e981787806714546a155d2569', FALSE, 'InfoLibrary · (file scope)')
  , ('394f228c337224fb', 'client', 'Apex', '4c459601c34257dd40797c08e6fe2bcf0ee51d72', FALSE, 'shop catalog · cosmetic name/description')
  , ('f844a3b73a67ebf7', 'client', 'Apex Shark', 'cfde026b5eb11e8b50860cf224b62219383d148c', FALSE, 'shop catalog · cosmetic name/description')
  , ('c88a9fc809cbd08c', 'client', 'Appear offline (Home lists): <color=#88FF88>ON</color>', 'fa7e5eb35adccb3eb968b6ecc50791ea1b621f85', TRUE, 'NativeUI · PaintAppearOffline')
  , ('2cb12d5097621e42', 'client', 'Appear offline (Home lists): <color=#FF9966>OFF</color>', '8b978ab93e691bc57113c70eded0adb5b571eab3', TRUE, 'NativeUI · PaintAppearOffline')
  , ('c56cdc211517120c', 'client', 'Apple Stem', '5f7ffa4a353bda2e5e403cc3f8b5fcbf11e82722', FALSE, 'shop catalog · cosmetic name/description')
  , ('53eb03940dd9126a', 'client', 'Approved Update Queue...', 'a07ed85fc63acdd4554a17f354ed0ddefe01bb6b', FALSE, 'NativeUI · BuildAdminTab')
  , ('934ede0ef4f25930', 'client', 'Are you good at this game?', '427951d00b193b43a44cfc0af03c9d67cf6edb60', FALSE, 'QuickChat · Phrases')
  , ('2fd7bafad36076e8', 'client', 'Armed', '32caa310311f38d5c1107b7e84eadb61d89f69a8', FALSE, 'NativeUI.Settings · SettingsPaintDeleteState, SettingsRenderDestructivePane')
  , ('df9183f4cda892d3', 'client', 'Arms the deletion. This press deletes nothing: the row swaps to a confirm button and a cancel button, and only the confirm performs it.', 'daadb4265857c074b09cf479e4539aab63aa71f6', TRUE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('7a216d77fe30c9cd', 'client', 'Arrow', '3a4758c3cc8dac2d76026d0733816741f9b21d43', FALSE, 'NativeUI · ShapeLabelTr')
  , ('4cd5305755696722', 'client', 'Artist', '6c3f3d3203630ce74ffd9609307833fc4f052892', FALSE, 'NativeUI · (file scope), BuildCompareShopSalesPanel, CreateShopRow')
  , ('ad7b3abe61db1a27', 'client', 'Artist Studio', 'adca584b7f8c32ece93a46b17db60f483cd68dc6', FALSE, 'NativeUI · BuildArtistTab')
  , ('9b9d0b9c0009da49', 'client', 'Artist-owned face cosmetic not found', '3d210b7a1a8ddd580f5add71b9f104d54e1380c9', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('22eac961461ab249', 'client', 'Ascendant', 'c6db2ec02dcf3556a6323441f9db90a8db6c6932', FALSE, 'shop catalog · cosmetic name/description')
  , ('1b3f3ff1f8bc538e', 'client', 'Ash Gradient', 'ac1861b407332050c7ad8ece653fde7c0a2885e5', FALSE, 'shop catalog · cosmetic name/description')
  , ('511b49694beadfab', 'client', 'Ash walls with a dark crimson accent over a deep blood-red dark, red embers rising.', '6f2d396e557b5f76d31e56571112c890b8ee7430', FALSE, 'shop catalog · cosmetic name/description')
  , ('045c820ff5b6f049', 'client', 'Async (6-week)', 'f538f0d0c876ecdf14feb954af97fb27e2498ce2', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('0f3d1f351e4a7862', 'client', 'Async Champion', 'c40497b1048c1314d0ed1d417cba50705d6627b3', FALSE, 'ApiClient · AchievementDefs')
  , ('2ca17fb22ceeb91e', 'client', 'Async Finalist', '732bc6ebb89a10d9399dafcf3162dc41462e2371', FALSE, 'ApiClient · AchievementDefs')
  , ('27059afd0acb8480', 'client', 'Async Tournament - {0}', 'e97c8c30a26c65e396b4608a10d7a4e5219b9d8a', FALSE, 'NativeUI · TrTournamentBanner')
  , ('9eff451fa8b7f65e', 'client', 'Attach game logs (recommended)', '67d0b166e08a2db71d9486f96ac1bb9a2c9ad486', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('6994bb12f92bd491', 'client', 'Attack spd', '2b4881723e1320d2b12e0ad31fc9dfc27794c0a8', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('682d02d713ebead0', 'client', 'Auras', '0b5c4206710a5a0dd90dba2856fd460845b06573', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('9409ce3813df7c43', 'client', 'Aurora', 'eeee9b76ec5d1cfa27c511f2def4981c9c5b667c', FALSE, 'shop catalog · cosmetic name/description')
  , ('ac3f9e4803a9463c', 'client', 'Aurora Gradient', '96fe497e8d08bf63fbd473f4404b51f515bb3dac', FALSE, 'shop catalog · cosmetic name/description')
  , ('553c1cb857bf44de', 'client', 'Automatic pick: {0}', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', FALSE, 'FfaMode · FfaPickPhase')
  , ('28236794e019b94c', 'client', 'Avatar auto-switch: <color=#88CCFF>OFF</color>', '4b223773afab914d058b5cbeca737133bd088685', FALSE, 'NativeUI · PaintAvatarAuto')
  , ('913c00ea1fd25cc6', 'client', 'Avatar auto-switch: <color=#88CCFF>ON</color>', 'bea9ed715393b1ce8728da65ecf1391b8e245efe', FALSE, 'NativeUI · PaintAvatarAuto')
  , ('b6518fcbfeb60c2e', 'client', 'Avatar defaults', 'd6c1ae4f4abe4b837b0e15c63bef6b0c3a4ddc56', FALSE, 'AvatarDefaults · PaintLegend')
  , ('4aaea460afdabbd8', 'client', 'Avatar swap', '5055532922ff4f3498433b404f6e9baef0039195', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('3c6690dcdecbb716', 'client', 'Average FPS', '54f2de771fcc83e1f79f766de250ec3b99058fc1', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('ce5dbf6b604fedf0', 'client', 'Average game', '275e87e442eacff8e7fc830bd00dc65caf63f965', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('b40fb3b19f66c416', 'client', 'Avg Cards / Game', 'a9cb3b230f62baaa2a50a30ae4021bc185ff4cf7', FALSE, 'NativeUI · TrMetric')
  , ('2c6ddebe063dbd3c', 'client', 'Avg Cards per Game  (lower = stronger)', '3b5cb53623777da9da001e365460faeffffe4707', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('3c0e4e88889a9d01', 'client', 'Avg FPS', 'a5e9d8eff751109a07f683414c26a66ede6965fe', FALSE, 'NativeUI · TrMetric')
  , ('7b00a1e34b238a38', 'client', 'Avg Game Length', '733c052b3ccea1ff310008f67ea79002e90d3f23', FALSE, 'NativeUI · TrMetric')
  , ('36cecc4f534c115c', 'client', 'Avg Game Length (minutes)', '478919ec62b4c389cfdf173b807404a7e6536d53', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('1d06bcb7ee5096ad', 'client', 'Avg Key Presses per Game', '1d4a57f5312863f49c410c101712a44f6d8885ac', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('32283fc1ea2d3ded', 'client', 'Avg Keystrokes per Second (in combat)', 'e130f4017b66a9d862b0106b351967a2bce36333', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('9c9b2f5a2d506195', 'client', 'Avg Mate Elo', '122a68a5ef9fadcd527704d0d89be3776ce44871', FALSE, 'NativeUI · BuildTeamTab, RefreshTeamTab')
  , ('fff050a62953a165', 'client', 'AvgPl', 'b2df7e1ebbcf4c9557f59de9e8d9e16ff8b7817a', FALSE, 'NativeUI · BuildFfaTab, RefreshFfaTab')
  , ('21ef2621e7ac1f10', 'client', 'Avoid in Ranked Matchmaking', 'd44f4d73ce000ba018ed8700a57bc3cbda8ece39', TRUE, 'NativeUI · BuildLeaderboardTab, RefreshLeaderboard')
  , ('61ecc3a70166ed11', 'client', 'Azure Comet', 'caacb9c4120653ddad8aa9d39ba9c52e144d097d', FALSE, 'shop catalog · cosmetic name/description')
  , ('be620029c980686a', 'client', 'B (in a lobby) - add a practice bot', '3a12dba0070937a0c83d2c3a55dce1eea0c9e793', FALSE, 'InfoViz · BuildKeyboard')
  , ('fd1f03c0131e355c', 'client', 'BLOCK', 'bf55ddd9725aa1a87e415a1396e069c8d47b25d1', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('1433e2e3d2524fb8', 'client', 'BOARD', '3e91add48ae124e40796bd2a31471a8bedf259b5', FALSE, 'PcLabels · Tr')
  , ('e188efd45c8c5593', 'client', 'BOARD' || chr(4) || 'pc.stat.board', 'cf25c3fab4d5689fb4213d0d131f4c180c13bdcd', FALSE, 'PcLabels · Tr · pc.stat.board')
  , ('871df4f8fa2428c4', 'client', 'BYE', '4eb996ceb7f4fea1ceb5970b7f3aca3c9a75cf06', FALSE, 'NativeUI · CreateBracketCell, RefreshTournaments')
  , ('d704b66a9fc187c3', 'client', 'Babel', 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('415f9cc2da2824dc', 'client', 'Baby Mouse', 'df1290e565c4e950a9dd040e4b3c6e46426fe6a0', FALSE, 'shop catalog · cosmetic name/description')
  , ('16ffec92acf9452e', 'client', 'Back', 'b52b36b7269fbfc58ec24bb724691951a3decbe8', FALSE, 'CompetitiveUI, MailUI, PlayerCardsUI · BuildCompose, BuildReaderView, DrawConsentDeclineConfirm')
  , ('616fd119d706cddd', 'client', 'Back in the Quick Match queue — searching for an opponent.', '0b3b3ac66cd2cf8925317cf45e29992a8629264e', FALSE, 'GameStateWatcher · TickRequeueMachine')
  , ('25fd5224759b7161', 'client', 'Backspace', '88d130a66de8e5db01660642d9f23e1f0eef97dd', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('e209685ce7cdc480', 'client', 'Balance: -', 'ee03e71aa0ce092fd93e310a80b158302071fec0', FALSE, 'NativeUI · BuildShopTab')
  , ('20a200b93b0f4139', 'client', 'Balance: <color=#FFD94D>{0}</color> gold', 'c663090066ad025d9f11faa0246cd410f6c5acf4', TRUE, 'NativeUI · RefreshShop')
  , ('8a4c4be43c067b23', 'client', 'Ballooniphones', '63b68012cb0fa6028ec65f7f56bd1e09a7ecad78', FALSE, 'shop catalog · cosmetic name/description')
  , ('5a632213b986a0b0', 'client', 'Ban', 'bfa1bfbf6c1cd85f3d2b4f696a8d5761ff6c91ee', TRUE, 'NativeUI · ConfirmAdminBan')
  , ('b2d58f4b596f2040', 'client', 'Ban Steam ID...', 'b5f65d80008ad5bc2dcac7a6c3249f23338f989e', TRUE, 'NativeUI · BuildAdminTab')
  , ('0a8b00e11aa7e87c', 'client', 'Ban a player', 'd8bb8f01ecddcbb69753151666860f937807775f', TRUE, 'NativeUI · StartAdminBanFlow')
  , ('e683e24fa226fac0', 'client', 'Ban {0}', 'eb7f64cd8b72a17bf3d79c29522fb9ef26afc5fa', TRUE, 'NativeUI · StartAdminBanFlow')
  , ('6de5dddf9737eec7', 'client', 'Banned', 'c8cd83f62e9d6c906f2b825ab8537bb5704a478d', TRUE, 'NativeUI · (file scope)')
  , ('efa284500294a4ba', 'client', 'Banned Players', '82dc4c9ba2d0d3898232429a34fce3451ac22165', TRUE, 'NativeUI · BuildBannedTab')
  , ('7ea032680df267bf', 'client', 'Banned players - type to search', '2b1074ee9054cc37d9f0d63b8e74753ecee5b495', TRUE, 'NativeUI · OpenBanSearchPicker')
  , ('4b1ee0227f1bf12a', 'client', 'Be right back', '3f16022a617b9c281f8300015f5cf25016949f01', FALSE, 'QuickChat · Phrases')
  , ('6ae94621dec896fe', 'client', 'Bear', '7b9f56b445e86e6a3c8212077d155af244bb66e9', FALSE, 'shop catalog · cosmetic name/description')
  , ('be40a9ea47f884cf', 'client', 'Bear Boss', '09d56923758d6c011c6f616f46cbd1b881f950a8', FALSE, 'shop catalog · cosmetic name/description')
  , ('534df5a540b8c6f0', 'client', 'Bear God', '2e7c038479f2b274f6f4ef20d024de2518c48bf2', FALSE, 'shop catalog · cosmetic name/description')
  , ('dca50b9ed118cbdb', 'client', 'Beat Sid in a ranked series', 'c079b59c65f4a283f90f1a0511b37ff20c393880', TRUE, 'shop catalog · cosmetic name/description')
  , ('cecd4fa7f2642aba', 'client', 'Beat Stan in a ranked series', '315b3a7ff79a5d9a069de5c4b40c89545a06f6e7', TRUE, 'shop catalog · cosmetic name/description')
  , ('6b363055e82afd04', 'client', 'Begin the window', 'bda1ea7b9ee1096821ac8c0b1b0f26915e087856', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('368adc406bc7cf17', 'client', 'Beginner', '60575a6ebba9f780b4312324662169830d12bea1', FALSE, 'InfoViz · BuildRankLadder')
  , ('4e3adbbd8a6ed18f', 'client', 'BepInEx (current)', 'd8b47f574662c9e2de4a022fe7f25db087c9b9b9', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('785b325c520dbc5b', 'client', 'BepInEx (prev session)', '072719c3fc70bbe17a0c02b6968f63fb1de66a2d', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('7491833f08beadc5', 'client', 'Berserker', '7d812b6c0cf9b06224698bf549532e4dfa84626f', FALSE, 'shop catalog · cosmetic name/description')
  , ('f492ecc3e3307ab6', 'client', 'Best Win Streak', '0e13a694c06a1734230915e4b3206b568908870c', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('3f463b0fbcd08360', 'client', 'Best run: {0}', '46daec5d2f257fd7dd3ca49499b462e10d591d8d', FALSE, 'TitleLaddersUI · ProgressText')
  , ('dd01ededf1c8c18c', 'client', 'Best seller', '271330d994ea7546d2efc98de562966a6a530b38', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('e9cbfed6a11d404e', 'client', 'Best-of-3: first side to 2 game wins. 1v2 is an unranked beta - every game is recorded, and no rating moves yet.', 'c4c85cf747ada8e52cc6035e7744b26c75a13e40', TRUE, 'InfoViz · BuildOvtFormat')
  , ('9cab5fc40afc9b86', 'client', 'Bet', '40880286482e1363c39814b2ce3d66651ef98349', FALSE, 'NativeUI · CreateFfaBetPlayerRow, CreateFfaBrowserRow, CreateHostLobbyBrowserRow +2')
  , ('419fd13304fe9781', 'client', 'Bet cancelled - your gold is back.', '2b9d852b5536ed20addbc334cacbc63738c9f6ca', TRUE, 'NativeUI · ClickLobbyBet')
  , ('0b0990c45b3d1a1d', 'client', 'Bet failed: {0}', '8f54cd247fc90332d744f53159d73af22c2490ee', FALSE, 'NativeUI · AddBetButton, AddTeamBetButton, SubmitCustomBet')
  , ('60979d8da1b597d1', 'client', 'Bet on which pair? Pick 2', 'f6194328ef7b4d6ab5cc23907ac2b2d57d87657e', FALSE, 'NativeUI · OpenTeamLobbyBetPicker')
  , ('9342dc04639e8c4a', 'client', 'Bet on which player?', '62e2e4c1ec4fb5744b5022aa1aa4e286a5f0d357', FALSE, 'NativeUI · OpenFfaLobbyBetPicker')
  , ('2e42add77b4663b9', 'client', 'Bet placed: {0}g', '91a4e283dd12cb9b87870f138798c38ee0d8ea42', FALSE, 'NativeUI · AddBetButton, SubmitCustomBet')
  , ('1cfe92e5e2faa80d', 'client', 'Bet placed: {0}g on Team {1}', 'c51d1dc4be72787b45001281f94ad8d9d4d99c85', FALSE, 'NativeUI · AddTeamBetButton, SubmitCustomBet')
  , ('145afa63120ae9e4', 'client', 'Bet placed: {0}g on {1}. {2}', '4b47c71de405b7826bcc297c3c46ae5de8810bcb', FALSE, 'NativeUI · SubmitCustomBet')
  , ('8a9eeeb61d6172d8', 'client', 'Bet placed: {0}g{1}{2}', '6e38da544ee550b4c1c1ee181a958f6aa9b2dda0', FALSE, 'NativeUI · SubmitCustomBet')
  , ('e533de5156cb2f91', 'client', 'Bet {0} gold on {1} vs {2}', '0c630cae71e12d3744ef1465e983db16375aff00', TRUE, 'NativeUI · RefreshMyBetsLedger')
  , ('457c0ec3382f308a', 'client', 'Bet {0} gold on {1} vs {2} - LOST', '904e8531c82b435c64a14811a0cc273f729dafe4', TRUE, 'NativeUI · RefreshMyBetsLedger')
  , ('ac975a5b6eaeff68', 'client', 'Bet {0} gold on {1} vs {2} - WON {3} gold', 'e2fb68a779b9ffee88d12e338685ec7a800ecb79', TRUE, 'NativeUI · RefreshMyBetsLedger')
  , ('0f064de5a95c232a', 'client', 'Bet {0} gold on {1} vs {2} - refunded, series never finished', '28c3d859b0e41da070edb9f8751059554df5adb9', TRUE, 'NativeUI · RefreshMyBetsLedger')
  , ('047de86df5071d35', 'client', 'Beta', 'f03b60f7e52b7ce49ed1e4f9fa511c452a2185bb', FALSE, 'shop catalog · cosmetic name/description')
  , ('61611d5f98241ddd', 'client', 'Bets Won / Lost', '97762f31a5a61b013e1f4eebdfdd835d94ad7923', FALSE, 'NativeUI · TrMetric')
  , ('c995f8cdd8ce52e7', 'client', 'Betting', '6239d1b9fc40140857855287b71416de29d03380', FALSE, 'InfoLibrary, InfoViz · (file scope), BuildGoldSourcesLegend, GoldBucketName')
  , ('cada077cba6f8b7c', 'client', 'Betting Record', 'a40dbe4a1c7aebbf45414b3121bea1d5361d57d5', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('5103660e4f7c993a', 'client', 'Between 5 and 10', '39032d9f6eb0d1bec0ff412b7d9f5b695ce04489', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('a6a8bc2fc3a076e3', 'client', 'Big Bang', '4839495751c12db47a2401fa1fa497acd2f58b13', TRUE, 'shop catalog · cosmetic name/description')
  , ('8ec3afa6b21da574', 'client', 'Big Cat', 'c468e8e5c0ba4fffd01b8e1aeb156bfb2bae341c', FALSE, 'shop catalog · cosmetic name/description')
  , ('855b014db305757c', 'client', 'Big Dog', '9c134b0d20c24ca854b620e04c9f783ec431fca8', FALSE, 'shop catalog · cosmetic name/description')
  , ('3828219f201c6509', 'client', 'Bigger Name', '28544273e2aef2357d775fe43b318ba43f33a6be', FALSE, 'shop catalog · cosmetic name/description')
  , ('cb88c065adf80933', 'client', 'Bigger than Bigger, smaller than Huge.', 'dcce1b666e42b2516c4264ee76dabb367fb176b1', FALSE, 'shop catalog · cosmetic name/description')
  , ('05d14ae29739564f', 'client', 'Biggest comeback (rounds)', '1fc89c5452760b4e2e88c0a096a4c12ab92f0239', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('ff1408b4ed0bcd5a', 'client', 'Binder', 'cf26f69d5a1f422e164fd715f2e4e35bd9b8ecf6', FALSE, 'PlayerCardsUI · BuildInto')
  , ('620a77e0a38cd666', 'client', 'Black Cursor', 'cee82537870ea52d5f32f6a15bd0752b3c43183d', FALSE, 'shop catalog · cosmetic name/description')
  , ('4012ddaf0c5772db', 'client', 'Blackwood', '5b07f7088b0080a88cd696619c5ce3aaef4e8bfd', FALSE, 'shop catalog · cosmetic name/description')
  , ('77b1c8d67327bc59', 'client', 'Blitz', '8882e4bb2a3ab29b02ac332ae19a66cdb130dbad', FALSE, 'shop catalog · cosmetic name/description')
  , ('2b8d8e900c0f68cd', 'client', 'Blk {0}%', '7d9195d66f77729f69930d58ef4a8398ae5eca28', FALSE, 'NativeUI · BuildBracketHoverBody')
  , ('99ff755f76298b3a', 'client', 'Block', '82dd2cdf36f9436d89f404454654ad3e53fd428d', FALSE, 'NativeUI, NativeUI.Keybinds · BuildCompareBarChart, KeybindRowLabel')
  , ('13957c44445cf07e', 'client', 'Block %', '3dbed7ad205139f8e9f45caed19c3c4e914e1ef1', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('31af90c64e73ac01', 'client', 'Block CD', 'dae5a0121abb5fa0da729304b67493a1e3ea7978', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('eed713d9e5b7fa6a', 'client', 'Block a Player...', '8c8871a730c2975c44c4ee6bc331c76a40aebf00', FALSE, 'NativeUI · BuildArtistTab')
  , ('933906c0a8b7a70f', 'client', 'Block debug overlay (corner): blocks you started vs blocks that actually absorbed a hit, plus why each one missed (too early / too slow / unblockable).', '9393db627b5e19257ba529826c55d7246cc0dca5', FALSE, 'NativeUI · BuildSettingsTab')
  , ('23985dacf212b283', 'client', 'Block debug overlay: <color=#88FF88>ON</color>', 'dc8238b1d7f34c183b4144bb47f577c8643952ce', FALSE, 'NativeUI · PaintBlockDebug')
  , ('531d54a0f2f7c81f', 'client', 'Block debug overlay: <color=#FF9966>OFF</color>', 'f33f04e2451d11d0224bbe724edef933399e7826', FALSE, 'NativeUI · PaintBlockDebug')
  , ('6b0ae7187440ed3c', 'client', 'Block rate - {0}', 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', FALSE, 'PostSessionReport · AddPairCell, BuildCells2v2Game, BuildCellsFfaGame')
  , ('cdbe5987ff49cf3d', 'client', 'Block sender', 'ae07ebf540bffabc1fd30108d4e541e4f6381ef7', FALSE, 'MailUI · BuildReaderView')
  , ('1a4780f9f77a1025', 'client', 'Block {0}%', '574c53873b3f814c5f22b25e5a9fcf5772878724', FALSE, 'NativeUI, PostSessionReport · BuildFfaRecentRowText, FillRow, SideStats')
  , ('827a88f35b373700', 'client', 'Block {0}? Their mail will no longer reach you. You can unblock them in Settings.', '887e9e617777d27403a4aa8d881cc77d1011ae6f', FALSE, 'MailUI · BlockCurrentSender')
  , ('2db6030694b0d1aa', 'client', 'Blocked senders ({0})', '07db9111fff3a8c59035ece97d19b3f4ab8dad66', FALSE, 'MailUI · RefreshSettingsRow')
  , ('8ad309ec5640652e', 'client', 'Blocked senders: loading...', 'b9628a47f4a34705ea3fccd1efbbbe2ee4980644', FALSE, 'MailUI · RefreshSettingsRow')
  , ('3a6f424c1475be3b', 'client', 'Blocked senders: show', '7d8440f824543eaf6b42f14e6c3ac3aeccdbd139', FALSE, 'MailUI · RefreshSettingsRow')
  , ('262268f71a753d5a', 'client', 'Blocked {0}.', '2adf1cea6deccbe555f4ad52ef17b059f7011585', FALSE, 'MailUI · BlockCurrentSender')
  , ('66de64e1b1a3b21c', 'client', 'Blocking', 'd785c0d4b3b9c24878b62f64a7bcf78e9506ab27', FALSE, 'InfoLibrary · (file scope)')
  , ('7e7de6c72b86824d', 'client', 'Blocks', '54c45c033f5eb914fae27a646cbd9e23d3750d19', FALSE, 'SessionReportModel, TabStatsOverlay · BuildTotalsPages, EnsureLocaleStrings')
  , ('84e17af7112e2c2c', 'client', 'Blood Gradient', '03cb2764ec60add600368e21f4fdda7ea811af9f', FALSE, 'shop catalog · cosmetic name/description')
  , ('e0c347af1c2e8c45', 'client', 'Blood Moon', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', FALSE, 'shop catalog · cosmetic name/description')
  , ('3af894320dceeed7', 'client', 'Bloodbath', '60cd1e9614619c2e0b1e927342edab4d6bc173f8', FALSE, 'shop catalog · cosmetic name/description')
  , ('75f7ef63c5238e27', 'client', 'Blue Cursor', '1aecb54aae1e2b5ed8dfe32d82d5a452ea62616c', FALSE, 'shop catalog · cosmetic name/description')
  , ('0c86818566080082', 'client', 'Blue ring: your vanilla default', 'f5df6418e93109fc8a368669a9d13edf2f75cc34', FALSE, 'AvatarDefaults · PaintLegend')
  , ('801db4ac576038b9', 'client', 'Body colors', '31412d98b3bdcdd01a31a2e05f02c6c31f34a24e', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('3a55d6d7a2ec803c', 'client', 'Body colors in ROUNDS are team colors: the game holds four body skins and picks one by team number. Who gets which color follows from how each mode numbers its teams.

<color=#FFD94D><b>VANILLA 1v1</b></color>

In a 1v1 each player is their own team: the first seat is team 0 and plays <color=#7FD4FF>orange</color>, the second is team 1 and plays <color=#7FD4FF>blue</color>. Vanilla never uses more than these two teams online.

<color=#FFD94D><b>TEAM MODES: 2v2 AND 1v2</b></color>

- <color=#7FD4FF>2v2</color> - the server splits the four players into two pairs when the match locks. Teammates share one body color: orange for the first team, blue for the second.
- <color=#7FD4FF>1v2</color> - the solo player is one team (orange); the duo shares the other (blue).

<color=#FFD94D><b>FFA: TEN PLAYERS, FOUR SKINS</b></color>

In FFA every player is their own team, numbered by lobby slot. ROUNDS ships exactly four body skins, so <color=#FF6666>colors repeat every four players</color>: the 1st, 5th and 9th players share a color, the 2nd, 6th and 10th share the next, and so on. That''s deliberate - the mod adds no new skins, and the overhead nametags are what keep same-colored players apart. In a big lobby, read the name, not just the body.

<color=#FFD94D><b>THE CARD-PICK SCREEN</b></color>

The body standing on the pick stage is a clone of the picker''s skin. In team modes vanilla has two problems there: a load-order race can bake the WRONG team''s color into that clone, and vanilla only ever presents one picker per round even when a losing team has two.

The mod fixes both. It re-checks the real team colors a few frames after the stage appears and retints the body if it came out wrong, and in 2v2 and 1v2 it re-runs the stage for each picker in turn - so every picker appears as themselves, in the right color. FFA doesn''t use the vanilla stage at all: everyone picks at the same time on their own screen.

<color=#FFD94D><b>CUSTOM PLAYER COLORS</b></color>

A <color=#7FD4FF>player color</color> cosmetic from the shop (see <color=#7FD4FF>Shop & cosmetics</color>) replaces your team color on every modded player''s screen; viewers can opt out with the Show Player Colors setting. Animated specials like Prismatic and Chrome cycle their color about 30 times a second. <color=#7FE87F>Players without the mod keep seeing standard orange and blue - to them your game looks untouched.</color>

On modded screens the color is also your team identity: point announcements call out your color''s name (MUSTARD got a point, instead of ORANGE), the round-counter dots and the FFA score strip tint to match, and your in-game nametag tints too - unless a paid nametag color is equipped, which always wins. Identity is resolved from shared data, so everyone with the feature on sees the same names and dots; a player with it off sees vanilla bodies and tints (the custom team NAMES still show).', '2b8293c4e72cd26a912b45941620fcee37ccdda8', FALSE, 'InfoLibrary · (file scope)')
  , ('ef9e76cea86e1996', 'client', 'Body/Team Color', '8b6936a29f32dc8b820b8a11be9a1ea4beebb429', FALSE, 'NativeUI · (file scope)')
  , ('74417706603d0c5e', 'client', 'Bodycount', '688ca84d5148e1ce7841f6ada7f27396fa613bb8', FALSE, 'ApiClient · AchievementDefs')
  , ('e91af1cc53639bfd', 'client', 'Bold', '19e07430eed6d97d6d73cb4a2967b1f316520f54', FALSE, 'shop catalog · cosmetic name/description')
  , ('1a6c33ac1dff9370', 'client', 'Bold, italic, underline, strikethrough, and color/size modifiers applied to your player nametag in lobbies and matches. Visible to every player, modded or not.', 'b97598910533b3e47d54e5684ae3d32280929726', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('d34a0d31083dd876', 'client', 'Boosters', '1be0a8f67aa11f43b03ea32d1dd277f75954722e', FALSE, 'InfoViz · GoldBucketName')
  , ('018e099fd8ed2dc5', 'client', 'Both clients watch everything; only the elected reporter sends. Duplicates are absorbed, and the server re-checks ranked or casual when the report lands.', '3d3d4c5ad7b1daa8ce5a6f622acab3916a7e666f', TRUE, 'InfoViz · BuildReportPipeline')
  , ('04d2dc2bea475b30', 'client', 'Both ready! Joining match...', 'b094a487f88ec8edb2f2ab91ef0e626b8a53024b', FALSE, 'ApiClient · ReadyUp, UpdateQueuePoll')
  , ('264904bfa708182b', 'client', 'Both rings: this preset is both of your defaults', 'f5bb5791cacc35b62104a1d840e7cc1dd21bf87e', TRUE, 'AvatarDefaults · PaintLegend')
  , ('6d1e2505894254aa', 'client', 'Bottomless', '1eeb92f0bbb43ad22f1b83bade3eff5e81e43faa', FALSE, 'shop catalog · cosmetic name/description')
  , ('3d87a8eca9538119', 'client', 'Bounce', 'af7ed27586b5893f5b467417832893d5863bd3cd', FALSE, 'shop catalog · cosmetic name/description')
  , ('5102a46fc36366ae', 'client', 'Bouncer', '4e36289d0951a7bd412ec33c4053fe33bef6b588', FALSE, 'shop catalog · cosmetic name/description')
  , ('17e39c5f5faa04a8', 'client', 'Bounces', 'fffb1ac23479a3b099333fa68dd4b912625af777', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('7b10209c6ab33112', 'client', 'Bouncy', '0861596efe0b8976d831f3ea080decca2798d09b', FALSE, 'shop catalog · cosmetic name/description')
  , ('f7c82f02b929a7d6', 'client', 'Bouncy main', 'a9c34a32e6e79b3c17f81be6765ab239ba111db6', FALSE, 'shop catalog · cosmetic name/description')
  , ('4c2271c1d508dbbb', 'client', 'Bracket', 'e42a1e70b4003a66462fd8b1b6f1d551425eedd6', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('31730649fbdd137e', 'client', 'Bracket Reset', '46ed5de23cef330d5db5771f01c745d52d1f1195', TRUE, 'NativeUI · RefreshTournaments')
  , ('1dcbb7f9eb5c256c', 'client', 'Brain Cane', '32f934bf1243eb49222743a5d0f32e178fca1845', FALSE, 'shop catalog · cosmetic name/description')
  , ('ddad851a97e14f13', 'client', 'Brawler', '75fd356702d8a4ab2fe46dcab5f1f559aad3d49a', FALSE, 'shop catalog · cosmetic name/description')
  , ('62d51247bd7470f7', 'client', 'Bright electric-cyan body color.', 'c93e38d0d4ff579fde2f4a80a077a881667a17f9', FALSE, 'shop catalog · cosmetic name/description')
  , ('dd0cbe6d69e1e26b', 'client', 'Bright embers cooling into ash. Two-color gradient.', '464ed8f164b2f378ec5c9090ee0ac8b522b1c081', FALSE, 'shop catalog · cosmetic name/description')
  , ('ad0a6dae771517ad', 'client', 'Bright industrial blue body color.', '9ec32ed642cbdcae1c042f9b03791ebc2d4e9c6a', FALSE, 'shop catalog · cosmetic name/description')
  , ('293d08e159ee05b9', 'client', 'Broadcast [{0}] "{1}" to ALL players? It stands until revoked.', '773fb6d4f4bd4ea0effa809be6e54a854b2970ed', TRUE, 'NativeUI · BuildAdminTab')
  , ('8d3e5929f807c196', 'client', 'Bronze', 'af3102527f03c95d8e79825f965d8663c7fdf780', FALSE, 'shop catalog · cosmetic name/description')
  , ('8ae99931f06e822d', 'client', 'Browse open lobbies below, or create your own.', '0ad03cedb111af624eaf1c61118c7d5ca7ebabb3', FALSE, 'NativeUI · BuildFfaTab, RefreshFfaTab')
  , ('5c02f776045299e4', 'client', 'Bruiser', 'bfc2d658c9d3ab13efc8f2cbc76a4a9711215b48', FALSE, 'shop catalog · cosmetic name/description')
  , ('8e2573140ef55a27', 'client', 'Bubbles', '58356fb4cac0b801f011b397f9dff45adb863892', FALSE, 'shop catalog · cosmetic name/description')
  , ('432dcea4b8aabf0e', 'client', 'Buffoon', 'bbafaf098c8816ab72cb819ef6c1c3f4ce20d362', FALSE, 'shop catalog · cosmetic name/description')
  , ('ef8767b213eb3ea5', 'client', 'Bug Reports...', '59269e612dac82734fb0bff3e7d60948afe84748', FALSE, 'NativeUI · BuildAdminTab')
  , ('540aa824d2c28b31', 'client', 'Bug fixes the mod ships', '149285f05807fe0061d475398bb6fbfd0917916b', FALSE, 'InfoLibrary · (file scope)')
  , ('390f22c995b624ac', 'client', 'Bug report sent. Thanks!', '89183a133ac470f8daf7ceb62ad266022b240fc8', FALSE, 'CompetitiveUI · OnBugReportAnswer')
  , ('7811a5db8d47eda1', 'client', 'Bug report sent. Thanks! (#{0})', '9fe72981cc879912316e26db5261095ec4da3688', FALSE, 'CompetitiveUI · OnBugReportAnswer')
  , ('e0ddb10fc3343e26', 'client', 'Build Types', 'f698b4cf5e65de3e16b37e9eec6578bda803cbe5', FALSE, 'NativeUI · TrMetric')
  , ('47f268248b383ba5', 'client', 'Build at game end', 'b826dc07f4d7e1713f5944bedb2d4f7798360e17', FALSE, 'NativeUI · BuildStatsTipBlock')
  , ('8c252468d45ccbb9', 'client', 'Builds', 'b82b3fe83d42765d8aa437ed8d9b48e92d7a0db6', FALSE, 'SessionReportModel · Build')
  , ('4bbd82317abb0839', 'client', 'Builds that stacked 2+ copies (all players)', 'c2cd71ebabf6233304c88629eb6587714c60ac1f', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('1e088d00a6318256', 'client', 'Built for ranked.', 'ca3230fafdeab8aaaca7de56a4c8ece290129e03', TRUE, 'shop catalog · cosmetic name/description')
  , ('469f96b6fdf6a7e3', 'client', 'Bullet Hell', 'c2d5519c0f2e7db2a59a35a4ac44acbc2a6b42f6', FALSE, 'ApiClient · AchievementDefs')
  , ('168a24e7a15c6676', 'client', 'Bullet damage', 'a0e4252cefdd47139828d4b0e4a36f5d513a193a', FALSE, 'InfoViz · MatrixRowLabel')
  , ('c4d1897e0b92927e', 'client', 'Bullet slow', '1982b45375c2d30f60024c602fa49444a089bddb', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('2b6f6945b122da91', 'client', 'Bullet spd', '3f7097dd693481d4b33a1a1360bbaeab8ec78561', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('1b9b94fd93c13e2e', 'client', 'Bullet-hit particle cap (2/frame)', 'ce55c51755db07c0da74f585b4c7a4582d55ac19', FALSE, 'NativeUI · PerfRowLabel')
  , ('44958e96b42c92ac', 'client', 'Bullets', '7509c5747e5db3dfa3373afc42eca9f5b27a8599', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('a56569127767b07d', 'client', 'Bunny', '42186bd3b5d7b89beeebdfcf548af814f2265f0d', FALSE, 'shop catalog · cosmetic name/description')
  , ('d689c0344f85b91a', 'client', 'Burgundy', 'f48fa5b998d1a20e5aefa573097ab4dfd104f679', FALSE, 'shop catalog · cosmetic name/description')
  , ('9ef2d087c80357dc', 'client', 'Bursts', 'c3523aedb7179f0f1ed0e80801a4c320b1e398fa', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('9e63f090e317f40c', 'client', 'Buy', '7ceca51fcafe42567c1c49ed6ab3604d7c962875', FALSE, 'NativeUI, TitleLaddersUI · ActionLabel, ApplyShopRow, BuildEntry +1')
  , ('42b58b0e9f96b45e', 'client', 'Buying {0}...', '7db325b3e21b1a5687cdeadba0a48cc535576391', FALSE, 'NativeUI, TitleLaddersUI · CreateShopRow, OnActionClicked')
  , ('56c1bc4c9f3d0585', 'client', 'Bye!', '749de5cc8ef9ff0fb0869179ea66555c2dff2fbf', FALSE, 'QuickChat · Phrases')
  , ('2bc7b81351452373', 'client', 'CANCELLED (not enough players)', 'ae687d91ac348704cf2ceb4910feaccbed518dfb', FALSE, 'NativeUI · RefreshTournaments')
  , ('1497e4b80e5a3664', 'client', 'CAPS', '16b24a0952726b5c0d2889f8abde87eec79d5dba', FALSE, 'InfoViz · BuildKeyboard')
  , ('4a6c742588146636', 'client', 'CAPYBARA', '1ff40a7179bdfd4890eddb564bb801cd51f7f39d', FALSE, 'shop catalog · cosmetic name/description')
  , ('2fce258a62d8ca9f', 'client', 'CASUAL, RECORDED', '9848405c532ef118e7d6f79df0719e454c91ffda', FALSE, 'InfoViz · BuildWhenCounts')
  , ('217758e12ce52d33', 'client', 'CHAMPION', 'f40e7170940737620f0e762d0d594d502bf49ea3', FALSE, 'NativeUI · TrBracketProgress')
  , ('c38cc4830a4bb2df', 'client', 'COM', '682bd8e54d75fb68102b3655e18fafef55990f70', FALSE, 'PcLabels · Tr')
  , ('d552da5b128fed44', 'client', 'COM' || chr(4) || 'pc.band_short.common', '9725860961f276cb21daaef5defd572b5ff6ee63', FALSE, 'PcLabels · Tr · pc.band_short.common')
  , ('36a21225aae8c594', 'client', 'COMMON', 'e4636d467ea5e3fae7a3e459f05dbc0dce2744b1', FALSE, 'PcLabels · Tr')
  , ('58dd5c9261b1d87f', 'client', 'COMMON' || chr(4) || 'pc.band.common', 'f32f86981c3efd9cce674c27a7478a931e3d7fb5', FALSE, 'PcLabels · Tr · pc.band.common')
  , ('4d4720dda0a927bb', 'client', 'COMPLETED', '6dc2daaed756f492c0b47af2ae68dfc26d827fab', FALSE, 'NativeUI · RefreshTournaments')
  , ('a37e12e0c7749da9', 'client', 'COMPLETED SERIES', '1231f90b40c299944a06340b5ca7e8a2f92e4170', FALSE, 'InfoViz · BuildTeamFormat')
  , ('74a3ffbd1b2e254b', 'client', 'CONFIRM LEAVE', '3582b0f3e9efe01dc8ee0d184bda1f3b466825df', FALSE, 'EscLeaveRow · SetLabel')
  , ('70483da324b9a680', 'client', 'CRASH', '1c1bcb24cffa054e5fd7d06de56bf73a3e74d02e', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('87c44957aed78d1e', 'client', 'Calendar', 'adab5090ac6a1b7b5420faac7be86c41721ba27c', FALSE, 'RatingGraphAxis · Label')
  , ('f45db7482d67a389', 'client', 'Calm forest-green tint with low saturation.', '58e286b87091b07259c44d7904e679e9be73eddf', FALSE, 'shop catalog · cosmetic name/description')
  , ('9098cedd9b6f8315', 'client', 'Camera screen shake on shots/hits/deaths. Full = vanilla. Reduced = softer, keeps the hit feedback. Off = a perfectly steady camera. Local only.', '30134da01318f2520601f331d7a7ad2967d0af9b', FALSE, 'NativeUI · BuildSettingsTab')
  , ('780aad09ae87aff7', 'client', 'Can''t open the portal - it only opens over a secure connection, and this install''s server address is {0}.', '0fecf53e488a80617cd5b82d709bebebadc889a7', FALSE, 'SecureRouteText · PlaintextOverride')
  , ('d6bc949089d7ca60', 'client', 'Cancel', '77dfd2135f4db726c47299bb55be26f7f4525a46', FALSE, 'CompetitiveUI, MailUI, NativeUI +3 · BuildRankedRow, BuildSettingsChrome, CreateTradeRow +11')
  , ('5792fedf4221d0da', 'client', 'Cannot spectate: {0}', '56b8eff201e82ce113ba38a7ebf7f2d87849f328', FALSE, 'ApiClient · RequestSpectateGrantCore')
  , ('de467d3edb721838', 'client', 'Cap bullet-hit particles at 2/frame — biggest user-visible win on heavy firefights.', '4b1b1758c6a36dfe7213f6432757a25f25b44fb6', FALSE, 'NativeUI · BuildSettingsTab')
  , ('d7e31611d09367e7', 'client', 'Caps Lock', '2e1767e4b47f4b745dad3b4b0c716123e4fb6353', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('7bd90439fec0cae8', 'client', 'Caps the game at 120 FPS while the window is not focused. Saves GPU/CPU when alt-tabbed; lifts instantly when you come back.', 'eaa1ca32ac9d14098318df716ccaf7b619a568c5', FALSE, 'NativeUI · BuildSettingsTab')
  , ('c7400849ff3404d4', 'client', 'Card', '4d4ce73b15660f20977ad7efab2283c51bdae008', FALSE, 'NativeUI · BuildCardStatsTab, RefreshCardStats')
  , ('c30091482c3aed14', 'client', 'Card Stats', '2cf7c1c459ffac7b7755411c28a0fbd27b7ec2db', FALSE, 'NativeUI · (file scope)')
  , ('82c76d6424138550', 'client', 'Card Win Rate', 'a8165c9103b6edfcfb72b05ba463860dcf26e92b', FALSE, 'NativeUI · TrMetric')
  , ('6973c9ec580a6e8d', 'client', 'Card draw:', 'fe6dc37f7af5909d3e95e049fb3a30d820aea9ce', FALSE, 'NativeUI · BuildFfaTab')
  , ('7d55d57f5ad506dd', 'client', 'Card picks close in {0}s', '1e0bf83f8ad8121c68bb5c86364ed4e207d8098c', FALSE, 'CompetitiveUI · RefreshFfaPickBanner')
  , ('21b41babb49a1c4f', 'client', 'Card pictures & settings', '84148b567249dfa38d278200b986e32e0d5fd5e0', FALSE, 'InfoLibrary · (file scope)')
  , ('ee95be13bd6568ef', 'client', 'Card pool: no snapshot yet', 'd40acb1aca5b1bbca99ba9b79907f09b63480824', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('cba608429af0142f', 'client', 'Card pool: {0} players (snapshot {1}) - {2} cards in your binder', '62b21f570c9cdb352e2c72aff35c8490f96be5f3', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('682960495769fb95', 'client', 'Card trading: <color=#888>...</color>', '7ccd8ca30c9eaca9ff03f21f818377f2fd4790eb', FALSE, 'PlayerCardsUI · PaintTrades')
  , ('eef2acdac9153c88', 'client', 'Card trading: <color=#88FF88>ON</color>', '29c42de4320e26de2f19937b815162b5a622adbf', FALSE, 'PlayerCardsUI · PaintTrades')
  , ('4b1b3adeaa98c79d', 'client', 'Card trading: <color=#FF9966>OFF</color>', '12a334c5ce98a4de132ab5cc8eb7bda0ec2a5a66', FALSE, 'PlayerCardsUI · PaintTrades')
  , ('feb7846e483876c6', 'client', 'Cards', '0f830bc25e52f96121b00a67378be1abeaa3f274', FALSE, 'NativeUI, TabStatsOverlay · BuildCompareTab, EnsureLocaleStrings')
  , ('7c8bc215b7eb142b', 'client', 'Cards and points', 'a5606cbf62f26ebb634fb2d33b66649359d42181', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('0e10363f3f4fe33c', 'client', 'Cards picked', '25dc9d2aaa100766b559063b545a200ce1221cd1', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('6e4745124b5c7c2b', 'client', 'Cards received in a trade may give fewer shards when discarded.', 'a6801a770f02753d5e0a6de28dee11ff414c3be4', FALSE, 'PlayerCardsUI · RefreshInfo, TradedNote')
  , ('6ff20d196263b8a4', 'client', 'Cards/game', '7868d7e88db14c91f3f610b5319b013f47e676f3', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('1ed575a86bc9d240', 'client', 'Cards:', 'a6bcb0b542f89a1109f41bfa09c4216c3cd8991f', FALSE, 'NativeUI · BuildFfaCardsText, FillRow')
  , ('5d2ca42b2c4789b8', 'client', 'Cards: <color=#88FF88>FULL</color>', '5fafc6ce92411f8dd5808ec5a87bc12b0a48c8d9', FALSE, 'NativeUI · HistoryCardModeLabel')
  , ('56eeae7c606f171b', 'client', 'Cards: <color=#FFCC66>chips</color>', '72e5a30e619dd5488bc8f47b9a2b6c904e40e38e', FALSE, 'NativeUI · HistoryCardModeLabel')
  , ('1b4effb239673333', 'client', 'Casi''s mouth', '8a968fb7dbc2ab1fb3e31e87aea9d81c5b4fc4a1', FALSE, 'shop catalog · cosmetic name/description')
  , ('d7d0e9e219b53281', 'client', 'Casicorn''s Eyes', '75114685463170b6592d652473ef40eb0a6eceb7', FALSE, 'shop catalog · cosmetic name/description')
  , ('3d7912fb4dd0438d', 'client', 'Casual', '1001e6a796363a864472abf12ae1e511fb8778a6', FALSE, 'NativeUI, SessionReportModel · BuildCardStatsTab, KindLabel, RefreshFfaTab')
  , ('a244b647cf231b38', 'client', 'Casual (games)', '22189563e809c4944aac68940714bc157ddcba63', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('518ccda06f29838b', 'client', 'Casual 1v1', '2a966d4f0dcf6f67d0ab1296b2b3a9b500f504b7', FALSE, 'ProfileCard · ModeName, Render')
  , ('2336cf45edf6056b', 'client', 'Casual Conqueror', '7f89e50558edac544825522ec264018f192008a5', FALSE, 'ApiClient · AchievementDefs')
  , ('ec3afa95260402c3', 'client', 'Casual History', '7d4c84fbad4425fa4f4502f5b3057dccd0a14f3b', FALSE, 'NativeUI · BuildMyStatsTab')
  , ('763636bbe51c56db', 'client', 'Casual Opponents Who Quit on You % (higher is better)', 'd734cefacc6b661c9dd8ec387d7754488d4d72cd', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('0cfce7055946c432', 'client', 'Casual games', 'bb086b36eb4297b438e04630658cb14db77ba543', FALSE, 'InfoViz · GoldBucketName')
  , ('747964099bb289f7', 'client', 'Casual games keep their stats and XP but never move rating.', '93b4180f31d99408aadbdd42d402569ad35d84ae', FALSE, 'InfoViz · BuildWhenCounts')
  , ('ec3bbc79c58671cc', 'client', 'Casual: -', 'fc34d0bcd4850d867f1b6d5e71e32128dfd8ec52', FALSE, 'NativeUI · RefreshMyStats')
  , ('05dc830214a8b91f', 'client', 'Casual: {0}W / {1}L', 'ed02eaec1b7cdfe54ca5d028db8b31807f7252fc', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('0552e283e3175aac', 'client', 'Casual: {0}W / {1}L ({2})', '571d9fa39175e85bb1e887c25267c5b620e5e62e', FALSE, 'NativeUI · RefreshMyStats')
  , ('f6a637efb68bcea0', 'client', 'Casual: {0}W/{1}L', '33aed4926d6006ad15fdb8c60b6fa786a37b41f9', FALSE, 'NativeUI · RefreshSession')
  , ('a9d3f8de6a1aa42f', 'client', 'Cat', 'cebe54c7626cb1cefaca5f7f5ea6c96b4a7a2882', FALSE, 'shop catalog · cosmetic name/description')
  , ('97d51b17dbf982b6', 'client', 'Cat Deity', '91c24bf34b17601f29d329d9000cd1208cda5afd', FALSE, 'shop catalog · cosmetic name/description')
  , ('38ae3616902f9e47', 'client', 'Cat Eyes', '527774087ad99d4cbf98e04c8c027506f3dfaa89', FALSE, 'shop catalog · cosmetic name/description')
  , ('bb044ac5a0ad150f', 'client', 'Cat Mouth', '8ca39fdb3e24dc0164815c29c778320c3477b994', FALSE, 'shop catalog · cosmetic name/description')
  , ('ea0992cf6e04fc9f', 'client', 'Category:', '61b9204fa30ab100d2a82ad42f62e455b1d2df3a', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('1412a8a90c683fb3', 'client', 'Century Club', '65ab9f618934bfa3ace72bac702ee7ca3f2ecbab', FALSE, 'ApiClient · AchievementDefs')
  , ('200db98d00b3dd35', 'client', 'Cerberus', '4f5aae5c8a8dbf9f666cc9cbde36ee6ca8388fc5', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb4e081c07852cc0', 'client', 'Change', '64fbd995d3b6b156ee26ae3c03e6516434c34c12', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('c15981b970bb074f', 'client', 'Change view', 'c401ce5826bb2f72ec8429df08aa320c18f4c542', FALSE, 'NativeUI · BuildHomeTab, RefreshChatLog')
  , ('c146b1aae124b5ba', 'client', 'Changes the menu cursor''s shape. Works alongside an equipped cursor color.', '37765cd85528b28ffef42e72a647700728327e82', FALSE, 'NativeUI · BuildSettingsTab')
  , ('3df637f1d1f20327', 'client', 'Character cosmetics - faces, eyes, and accessories, many made by community artists. Buy here, then equip them in ROUNDS'' own character editor (F8 or main menu). Visible to all modded players.', '571a19ec45d137f48cfba3989f252ecc1b8d8fce', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('dc41544e285f87e1', 'client', 'Character preset', '8d6ab020046a3dcc3c50de2b4b6f72a0af84b9c4', TRUE, 'PlayerCardsUI · PaintPreset')
  , ('d3a2f4060b4d4faa', 'client', 'Charcoal', 'c81e2a08f7e0b5c4162685cc5b5ede3c1ec05062', FALSE, 'shop catalog · cosmetic name/description')
  , ('e8d68fce3701fe2e', 'client', 'Charcoal walls rimmed with corona amber on a true black sky.', '0da332b305a132002eabd6a4d3b1dade76c79582', FALSE, 'shop catalog · cosmetic name/description')
  , ('040fdcdc9fe82d97', 'client', 'Charred timber — warm dark brown verging on black.', '6fdc92710bf9a1c37713696ed1898bd196a848c9', FALSE, 'shop catalog · cosmetic name/description')
  , ('45f52547e45b2ca1', 'client', 'Chase', '0911174c41cf26b831f5dd822376ad256ce92ec0', FALSE, 'shop catalog · cosmetic name/description')
  , ('c7f99bb6bdf20c56', 'client', 'Chat  <color=#888>(press {0} to chat)</color>', '4bf1b342b634b8cc7d42f2a0e2510e4a1fbf8d50', FALSE, 'NativeUI · BuildHomeTab')
  , ('c31c5ec5054c36a9', 'client', 'Chat & mail', '3c36f21e8126daea143b7a82997e5080938d6483', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('529d48be14697fb0', 'client', 'Chat Lockdown...', 'c1487c661b3824edef495d3a1e179de9b6fd9df3', FALSE, 'NativeUI · BuildAdminTab')
  , ('1c48751eaee33553', 'client', 'Chat Mutes...', '545716aba2b183be2c211309ef313d8dc26fa50f', FALSE, 'NativeUI · BuildAdminTab')
  , ('e2f0693ba9b4b17a', 'client', 'Chat [{0}]  —  Enter to send, Esc keeps your draft, {1} switches channel', 'c6877414da55b26435a1a0038ca5ecda374bb517', FALSE, 'CompetitiveUI · DrawChatInput')
  , ('c40bdeb2c6bc6194', 'client', 'Chat fade after: <color=#88CCFF>{0}</color>', '65f53bb459448996be79db9bf7bd8c79f6217733', FALSE, 'NativeUI · PaintChatTtl')
  , ('913425575197162e', 'client', 'Chat fade after: <color=#FF9966>Off (chat hidden in game)</color>', '31cad23948d6e66827b36da377f70bda82093070', FALSE, 'NativeUI · PaintChatTtl')
  , ('3120a8bba946965b', 'client', 'Chat has been locked by moderators - messages are paused.', '00e6378fd0ad4c8296ae49a11a180f2b8f595139', FALSE, 'NativeUI · OnChatMessage')
  , ('101c48b93dc18a1c', 'client', 'Chat has been unlocked - carry on.', '229b63d4752af1d5e5266b484a27b937791c450f', FALSE, 'NativeUI · OnChatMessage')
  , ('9282b6d2952d72f7', 'client', 'Chat has language channels - use the dropdown on the Home tab, or tap {0} while typing, to switch.', '3cd7ffe9c90f5595ae4176caf992050ba5fc1a3e', FALSE, 'NativeUI · LangChatNoteText')
  , ('17b168c59cb4e7f1', 'client', 'Chat is currently LOCKED.', '43c150859e877ae3f3011e3f47320e8383b13d67', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('7aff9f0847fdcbe2', 'client', 'Chat is currently open.', 'b490c649eb08657196c358270e67e5c0d5f8036b', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('75b31f59dc8e438a', 'client', 'Chat is locked by moderators right now - your message was not sent.', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', FALSE, 'NativeUI · NotifyChatLockedAttempt')
  , ('51eeb395b99aa1a6', 'client', 'Chat language channel', '5d8c301a2503b19711cffd84c97832a1fa8c36a4', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('97ba222b4778e023', 'client', 'Chat mutes - type to search', '12d0c6e09634a234a341926502ca2c0403d6ebb4', FALSE, 'NativeUI · OpenChatMutePicker')
  , ('e673a6b24221e740', 'client', 'Chat notifications: <color=#88FF88>ON</color>', '00c68073e93e01b847fdeeb7d6d09c4b0775dc02', FALSE, 'NativeUI · PaintNotifications')
  , ('a380719c62368c34', 'client', 'Chat notifications: <color=#FF9966>OFF</color>', 'b377a298478828076e8b6b4f4be229a2b8478521', FALSE, 'NativeUI · PaintNotifications')
  , ('d0e45033e1e29c4f', 'client', 'Chat overlay mode', 'e80e0bab92e8d072d9a7076d0a5971f1bad2f02f', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('0f408b5164e8cde0', 'client', 'Chat overlay: MUTED - hidden, and the room is told', 'ea95f55d84ec2572bbce3d2111a37126cc384da4', FALSE, 'CompetitiveUI · SetChatOverlayMode')
  , ('e8c932d222bdf621', 'client', 'Chat overlay: NORMAL - messages fade out', 'f960a3c53bbd484f5982e132220c6c0702265c96', FALSE, 'CompetitiveUI · SetChatOverlayMode')
  , ('dc1b802008907849', 'client', 'Chat overlay: PINNED - messages stay on screen', 'f8143ac3985dcfb67856edb9aca30fbfe8afac1c', FALSE, 'CompetitiveUI · SetChatOverlayMode')
  , ('2d51984efe21542c', 'client', 'Checking the secure connection...', '5c05b0ae062af07abe861c9a1ff081c799666271', FALSE, 'SecureRouteText · Checking')
  , ('e247d0f66676e2fa', 'client', 'Checking whether {0} can rejoin', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', FALSE, 'TeamHoldBanner · Line')
  , ('abffd73269054ce5', 'client', 'Choose a metric', 'f9491ed1720722bc9eb22d885d3f0ee467ac651a', FALSE, 'NativeUI · OpenMetricPicker')
  , ('79188657d578e83a', 'client', 'Choose cards (left) to compare {0}.', '745fffa486b3d6bc7f6739e20fad006aa69a84ff', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('94d2347ffacf4c70', 'client', 'Choose up to {0} of their cards', '20e26e2d014fa87e6e6be2305581f5fdfe8428fd', FALSE, 'PlayerCardsUI · RefreshCompose, ToggleComposeCard')
  , ('2fddea0fcaedaa6d', 'client', 'Choose up to {0} of your cards', '6a2eb4de7f686687f63f13ed8ce9236ce9a5042c', FALSE, 'PlayerCardsUI · RefreshCompose, ToggleComposeCard')
  , ('1efc58a3cae83cf0', 'client', 'Chooses who may start a new mail thread with you: everyone, only players you have played, or nobody. Threads you already have are unaffected, and blocked senders never reach you.', 'fa492bf70b33210258243c1c308695145cb1dc2b', FALSE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('473227dfcf7069a9', 'client', 'Chromatic aberration: <color=#88FF88>ON</color>', 'b59d2949c1166ebc227ebbd6c96c355c303cbc9f', FALSE, 'NativeUI · PaintChromAb')
  , ('c6d361b961c42895', 'client', 'Chromatic aberration: <color=#FF9966>OFF</color>', '6b9ac421159f3f8fee143c8f71b93aa5666b6190', FALSE, 'NativeUI · PaintChromAb')
  , ('76304d064ecdaf0b', 'client', 'Chromatic aberration: the RGB color-fringing that pulses on shots/hits/deaths. Off = crisp edges, tiny FPS gain. Visual only, local only.', '0a298dccb65dad64a770d7e3fdae567c30ef4331', FALSE, 'NativeUI · BuildSettingsTab')
  , ('1ec90b2ecc0c22a7', 'client', 'Chrome', '218e75c7a912404b048fff0747e40108873b6334', FALSE, 'shop catalog · cosmetic name/description')
  , ('d9093070fd2a1be5', 'client', 'Circle', '1cc7820a08e28aa22dd2e6db74a83b75abc240f5', FALSE, 'NativeUI · ShapeLabelTr')
  , ('70c9a1091004264a', 'client', 'Claim today''s free pack', '12e07f29d94c0c761a63ad0777950dce33b6f7df', FALSE, 'PlayerCardsUI · BuildOpenView, RefreshOpen')
  , ('b6306fb3949a5446', 'client', 'Claimed - the next one unlocks in {0}', '7da0188fb8ad3590eca6f8a991078e2282041857', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('26b495cee7627e37', 'client', 'Claimed for today', '758100f62e1872b1b9daa1fa93580dd351ef8e26', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('436285baa5547368', 'client', 'Claiming...', '6c6d1ba3c3f1f06c322ad40092d372bb6c108f94', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('755e04f636c21f2a', 'client', 'Clamp ObjectPool init-spawn to 4 in-match — reduces frame stutter from new pool allocation.', '568dba56e5fadf7f411898e5b4c5ee9790606f36', FALSE, 'NativeUI · BuildSettingsTab')
  , ('471ee7b29158df83', 'client', 'Clavar la Bala', 'c725f01d52c785df06c7e2b879cba442d35cf914', FALSE, 'shop catalog · cosmetic name/description')
  , ('28221c7021c528aa', 'client', 'Clean House', '7889f8417d64298ad417c4d526a39ba7103ace7c', FALSE, 'ApiClient · AchievementDefs')
  , ('9f57ff0905238412', 'client', 'Clean Trail', 'a3b330fc7dec25ff7c2417fdf084196120632e2b', FALSE, 'shop catalog · cosmetic name/description')
  , ('d8852fbbce7d5315', 'client', 'Clean white body color.', 'b9a010b399b7896b4c0e26e06e1b2d16738d947f', FALSE, 'shop catalog · cosmetic name/description')
  , ('7693b881f9bb10d2', 'client', 'Clear', '719ea396ad92e01b4757ec2b93bb1e5f270f771d', FALSE, 'NativeUI, NativeUI.Keybinds · BuildCompareTab, BuildInfoTab, BuildLeaderboardTab +2')
  , ('77ea4429fec09c29', 'client', 'Clear Search', '87e328dc94be6ee1930cf45d7a3e28999e9fa412', FALSE, 'NativeUI · BuildCompareTab')
  , ('8d72e526755bc717', 'client', 'Click <b>Search Random</b> to start finding a 2v2.', '99767352d7331ce5b7a9be4ca342d6b8d73171d8', FALSE, 'NativeUI · BuildTeamTab')
  , ('7af5559f371db40e', 'client', 'Click Discard again to discard that card for shards', '956d1978dd0405a6e4540c16b3645f680e0d17a1', FALSE, 'PlayerCardsUI · OnDiscardClick, OnQuickShardClick')
  , ('d9fc490580aac7d4', 'client', 'Click Dupes again to discard every other copy of that card', '3a9607641bf374f57bbf1179657a69a3c23e3e46', FALSE, 'PlayerCardsUI · OnDiscardClick')
  , ('34ad2c92b41cd2ea', 'client', 'Click MAIN MENU again to leave the match.', '1fdaf16da209dcbd74f143b072bd0a907dd25615', FALSE, 'EscMenuLeaveGuard · OnGatedClick')
  , ('17ae9b43bb6cb8de', 'client', 'Click Shard dupes again to shard {0} duplicates for {1} shards', 'e8ec5e2774fc7925c4e0112147dcc6eb0f638f20', FALSE, 'PlayerCardsUI · OnShardDupesClick')
  , ('a687ae63bf03352f', 'client', 'Click Shard pack again to shard {0} cards for {1} shards', '69594a6831d0b84535e49d91d25b89cdb79b8c7d', FALSE, 'PlayerCardsUI · OnShardPackClick')
  , ('e2c6f244d89cc80f', 'client', 'Click Shard selected again to shard {0} cards for {1} shards', '3bae6a873aacd2f4a18c1348f0a7040df102f8bb', FALSE, 'PlayerCardsUI · OnShardSelectedClick')
  , ('b255fb0f4377600f', 'client', 'Click a card to view it', 'cdd0bc23bbc50f966c6000e9996994c70024f911', FALSE, 'PlayerCardsUI · BuildBinderView')
  , ('1e2571adc0faf416', 'client', 'Click a player', '5821ae9e99fd1b23089635ce0c78c13e11e76603', FALSE, 'NativeUI · BuildLeaderboardTab, RefreshLeaderboard')
  , ('203775486c7a82a6', 'client', 'Click again to forfeit', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', TRUE, 'NativeUI · OnForfeitClicked')
  , ('4eb6d21ac0c1945a', 'client', 'Click cards to select them for shards', 'b04f8c027f466662b9ac17765623401de7bae898', FALSE, 'PlayerCardsUI · RefreshSelectRow')
  , ('e46a4b0fa0cb3b10', 'client', 'Clock:', '4665f476a8337513ecd7afa6957a8c4210c50459', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('d1e0f9e0812bfad8', 'client', 'Close', 'bbfa773e5a63a5ea58c9b6207e608ca0120e592a', FALSE, 'CompetitiveUI, NativeUI, SessionReportView · BuildUtilityPopup, DrawFooter, DrawLogViewerModal +3')
  , ('0bd62ee5c52d93de', 'client', 'Clown', '58d28d96646957acfa9a8c908d0d61aad25b77c4', FALSE, 'shop catalog · cosmetic name/description')
  , ('41f5f5cf24a035df', 'client', 'Clutch', '4c26512201170dc20cac5a9bf043bfea51b6eb2b', FALSE, 'ApiClient · AchievementDefs')
  , ('96ed0e7311a525a3', 'client', 'Cobalt', 'c509eac2111b5bd8b67314feb259572255c6f6cc', FALSE, 'shop catalog · cosmetic name/description')
  , ('8d3bc6bf3cb691f6', 'client', 'Cold violet and cyan motes swirl in a dark halo.', '4fac4cec0922ba3d0b40514b9e35526635575dcf', FALSE, 'shop catalog · cosmetic name/description')
  , ('14166ceeacc179f5', 'client', 'Collapsed', '0084e8faecb61d25228b14978293b11cb85f280a', FALSE, 'NativeUI.Settings · SettingsRenderPane')
  , ('2fb7778ce06e90d3', 'client', 'Collection', '30c54a96f8011b39819ba18bcb53fcbb092d650d', FALSE, 'NativeUI, PlayerCardsUI · (file scope), PaintCollectionTabLabel')
  , ('33bda1024d57e8dc', 'client', 'Collector', 'e3199d24849eb82131394ea88ac9c22db0dbf732', FALSE, 'ApiClient · AchievementDefs')
  , ('f69708bf886ba7c7', 'client', 'Colorize your name in cyan.', 'e355071ea9b079a72d85687e2ac34ec406ee7927', FALSE, 'shop catalog · cosmetic name/description')
  , ('7238f6a0f006bd2f', 'client', 'Colorize your name in gold.', 'ce90982b634c51797500d1fa3c0537d9160f3cc4', TRUE, 'shop catalog · cosmetic name/description')
  , ('a29939fd5310702c', 'client', 'Colorize your name in green.', '378e60aaa1606276e4ecbe32a4488f37421a3a4a', FALSE, 'shop catalog · cosmetic name/description')
  , ('97bf484344ec2873', 'client', 'Colorize your name in pink.', '2ec2ab8e8e10dd4bac423d81ba3df5fb10f5a85b', FALSE, 'shop catalog · cosmetic name/description')
  , ('b75b645fcf4adb75', 'client', 'Colorize your name in purple.', '2889f9f551f5371f6892e307d5cf5c60025bb0c1', FALSE, 'shop catalog · cosmetic name/description')
  , ('cd7de4ecc01c1d92', 'client', 'Colorize your name in red.', 'e076968ac0727a056d40623d209ebf3b394200e1', FALSE, 'shop catalog · cosmetic name/description')
  , ('059bb297892d12b5', 'client', 'Colossus', 'ce1c631db455b6205a45b767991b570a3cc36d42', FALSE, 'shop catalog · cosmetic name/description')
  , ('a9d1ff58b803d1a9', 'client', 'Combat', 'af169bb89cfba4132f718ecc225adb9a91f8bdcf', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('a9c907432257035b', 'client', 'Command', '8901895fb1b1d4c4ea2fec368c25176bf73e2f7e', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('8618c3d156db5aa5', 'client', 'Common', '7de90a65241a6cdbd9ade485d777715d99285a1e', FALSE, 'NativeUI, PlayerCardsUI, SessionReportModel · Build, RarityLabel, RefreshCardStats')
  , ('8b7f3f68f2b2a6be', 'client', 'Common' || chr(4) || 'card rarity', '4fc0b8faff24d53cee4e9e20d595ec38dd3c45a9', FALSE, 'NativeUI · RefreshCardStats · card rarity')
  , ('7d3238c8a8377e00', 'client', 'Community artist sales - who has items up for sale, and what they''ve earned', 'c6f750e3606cb1acabf51eaa12518b3cac219656', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('a41a6a516319d6c0', 'client', 'Community artists supply a large share of the catalog and earn a 30% royalty on every sale - gifts pay no royalty.', '30833899ea88dc9cb31c326cc8c85a2666cda7de', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('f3e1ca269a596f07', 'client', 'Compare', '8d105cf44d3926289e65c1c83d8e37cb23fd049e', FALSE, 'NativeUI · (file scope)')
  , ('acadcc6ff4c590b4', 'client', 'Compare Cards', '09ee70122eab9a6320da7896d79280ff7c68f676', FALSE, 'NativeUI · RefreshCompare')
  , ('b4753d0471a2e6ff', 'client', 'Compare Players', 'bcfc616c401341442e28f27345987840dfbac509', FALSE, 'NativeUI · BuildCompareTab, RefreshCompare')
  , ('ecd2dadccaae041d', 'client', 'Competitive ROUNDS — Data Consent', '8b7d0e0643225d0905a09fd3c73bf19c5d45ad5f', TRUE, 'CompetitiveUI · DrawConsentDeclineConfirm, DrawConsentModal')
  , ('096503131133e107', 'client', 'Competitor', '470568764445128dbbde3a4861ab484f4d7f3bb7', FALSE, 'shop catalog · cosmetic name/description')
  , ('ebc8ae2d4c714ddc', 'client', 'Conditional', 'c3accb895f001e39bb983a80902ba897c94294bd', FALSE, 'InfoViz · BuildDamageMatrix, TextFallback')
  , ('d7cf4979f9ad74e4', 'client', 'Conditional - every other time; see RefreshValid below', '696b63f21cd0801ccf923c12444a40196f9febb0', FALSE, 'InfoViz · BuildDamageMatrix')
  , ('8107c94687b5513e', 'client', 'Confirm', '04a212215ef9fbf686d280802eb81ee7a6e681cd', FALSE, 'CompetitiveUI, NativeUI.Keybinds, NativeUI.Settings · BuildSettingsChrome, DrawConfirm, KeybindBuildFooter')
  , ('0d12537ad9ab0cb6', 'client', 'Confirm accept', 'bf82cf62059bdd3ced9e2c046722a1402dd513ab', FALSE, 'PlayerCardsUI · FillTradeRow')
  , ('4801bc4d1ad5528f', 'client', 'Confirm — really delete', 'cfd434e1ceba2df1cecded3fef55e8783672c543', TRUE, 'NativeUI · PaintDeleteRow')
  , ('efc2c3f495527644', 'client', 'Connecting to the game...', 'be82ac865c3763a408fbf6144162c42a37ecf19d', FALSE, 'SpectatorHud · ConnectStatusLine')
  , ('2e2b91c63683c1e8', 'client', 'Connection was lost — returning to menu.', '84a7957aad998fb6f6f3519a2e375d954a068ec9', FALSE, 'GameStateWatcher, Plugin · FireRequeue, Prefix')
  , ('23a2363525a63d2b', 'client', 'Constantly cycles through the rainbow during a match.', '7216727508f5cdbfb1e167595a4e44b10237b778', FALSE, 'shop catalog · cosmetic name/description')
  , ('f0439f514c74116d', 'client', 'Contender', '3a80861c82d4e7707191f08087cfcb0b4d44e161', FALSE, 'shop catalog · cosmetic name/description')
  , ('d2645364ecf9b525', 'client', 'Control', 'ea1d3df298ca84104dbf8b2f6f916c02f6f77c6e', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('675047dd2ba5fab9', 'client', 'Controlled Burst', 'a4e08a5b9cbd3ab4220ac58c80a41675bdeb184e', FALSE, 'ApiClient · AchievementDefs')
  , ('1dfd8eea2e913f40', 'client', 'Controls', 'bee75ca77f753e4846b455441733f6641c4bf287', FALSE, 'NativeUI.Keybinds, NativeUI.Settings · BuildSettingsChrome, KeybindRenderFooter')
  , ('739b01547fcbd9a4', 'client', 'Controls & keys', '03a24c219a319f77774cd07b8c2225f4929f8e24', FALSE, 'InfoLibrary · (file scope)')
  , ('d468d9bb9ee6fd5f', 'client', 'Controls cannot be changed on this game build; every control keeps its default.', '9578046f752995a4963443eb8d9d52ba67d4716e', FALSE, 'NativeUI.Keybinds · KeybindRenderPane')
  , ('2c0b482cb7fb2078', 'client', 'Cool blue energy crackling behind you.', 'b3184788eb8c6ab50e98bdded730901d8b5f4505', FALSE, 'shop catalog · cosmetic name/description')
  , ('1edaccb2dca7ceaf', 'client', 'Cool desaturated slate-grey — easy on the eyes.', '0c4e7b1605bb2b6079143cb3ff386f3d2882a487', FALSE, 'shop catalog · cosmetic name/description')
  , ('5286435b58b15502', 'client', 'Cool grey body color.', 'd47ddde92346ea04ff6d780400e1c300eb81639e', FALSE, 'shop catalog · cosmetic name/description')
  , ('0157a9143665e238', 'client', 'Cool grey-blue blocks on a dim cool backdrop.', '669a338cd831e006a68d71778ac389a20d8e40f3', FALSE, 'shop catalog · cosmetic name/description')
  , ('111b9b5a0d6725d6', 'client', 'Cool teal body color.', '3f4e6fe068c428db8f08c82ec6f320768c3e77c4', FALSE, 'shop catalog · cosmetic name/description')
  , ('66cfc06b58cc1eb9', 'client', 'Cool teal wake, fresh from the shallows.', '2895057a632eb8e91dfe420d751a813655e0432d', FALSE, 'shop catalog · cosmetic name/description')
  , ('5c819efd5e47b749', 'client', 'Cooled lava — volcanic oxblood at the edge of black.', 'a7a705f4f6e2ae44ccf76ce8ec20cb3f7825828f', FALSE, 'shop catalog · cosmetic name/description')
  , ('64a794dbef16b882', 'client', 'Copied to clipboard.', '46322ff3b9d0282b788c84b88c7b446f619a3c01', FALSE, 'MailUI · CopyCurrent')
  , ('cf19303e97ba6241', 'client', 'Copy', 'af74f7c5362aaee985bf8cda3dd75fc80751ce51', FALSE, 'MailUI · BuildReaderView')
  , ('3242c3ee66b19424', 'client', 'Coral', 'd27ca6c0dabe676d07af8742683d39325665cd59', FALSE, 'shop catalog · cosmetic name/description')
  , ('a72ae56c0ded3702', 'client', 'Coral Name', '57a485e2451d558c03fa971091c39322dd7ab285', FALSE, 'shop catalog · cosmetic name/description')
  , ('f6f39272fe6447ee', 'client', 'Corner notices when your frames drop, your ping is high or the opponent''s updates arrive late. 1v1 only.', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', FALSE, 'NativeUI · BuildSettingsTab')
  , ('9d92b32fc6bd63f4', 'client', 'Cosmetic Reviews...', 'fa8c098d8f7e544d019a8621d1fafe84fc8f4188', FALSE, 'NativeUI · BuildAdminTab')
  , ('638ee71a835dcd6f', 'client', 'Cosmetic slot does not match its catalog SKU', 'e34cff4fb5cf07115d6e51ce4bca06b11154b76f', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('3490084b568d2ca1', 'client', 'Cosmetic submission not found', '5b7ad858c285a519336356aadfb04098af1b8ec5', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('770b1cee5bc3959f', 'client', 'Cosmetic trails: <color=#88FF88>ON</color>', 'd002a24ab224f0957250799b98672bb07e8e316f', FALSE, 'NativeUI · PaintTrails')
  , ('3f7dc0cdea2a6ffc', 'client', 'Cosmetic trails: <color=#FF9966>OFF</color>', 'd84f4bebe1e56b6360f04a4f94744ffea77a4f35', FALSE, 'NativeUI · PaintTrails')
  , ('abf4f1283922dcc9', 'client', 'Cosmetics', '9555b604bb2b33b5e29fe2c53ae409befbe84d79', FALSE, 'NativeUI · (file scope)')
  , ('910f67b5efb72a02', 'client', 'Cosmetics & Identity', '1f26a904194291df57645321da8a65d06c1b48d2', FALSE, 'InfoLibrary · (file scope)')
  , ('5ff1b47aebef7efd', 'client', 'Cosmetics live in the F5 Shop tab and are bought with the gold you earn by playing. This page covers every kind, how each equips, how drops and stock work, and where the art comes from.

<color=#FFD94D><b>WHAT EACH KIND DOES</b></color>

<color=#7FD4FF>Titles</color> - the label beside your name on mod surfaces (see <color=#7FD4FF>Titles</color>).
<color=#7FD4FF>Trails</color> - a colored trail behind your body in matches. Length scales with price: 3,000 gold trails are short, 5,000 medium, 10,000 long.
<color=#7FD4FF>Map skins</color> - recolor the whole map and background. Equip as many as you like and cycle through them mid-game with {0}. The catalog holds recolors styled after the six vanilla arts, more than thirty original presets including the night pack, and three premium sparkle skins: Gilded, Platinum and Aurora. <color=#7FE87F>Map skins are yours alone</color> - they''re never sent to other players, so every player sees their own pick.
<color=#7FD4FF>Name styling</color> - stackable styling on your display name. Formatting (bold, italic, underline, strike, float) stacks freely; glow, size, font transform and typeface allow one each, and the color effects (solids, neons, rainbow, per-letter gradients) share one slot.
<color=#7FD4FF>Player colors</color> - replace your team orange or blue with a color of your own, and become your team identity on modded screens (see <color=#7FD4FF>Team & body colors</color>).
<color=#7FD4FF>Cursor colors</color> - recolor your mouse cursor. The cursor SHAPE (default, arrow, dot, crosshair, circle) is a free preference. Nobody else ever sees your cursor.
<color=#7FD4FF>Player effects</color> - a particle aura that follows your body in matches.
<color=#7FD4FF>Faces</color> - custom eyes, mouths and accessories that slot into ROUNDS'' own character editor next to the vanilla parts, and render everywhere a face renders. Some are animated; the Animated Cosmetics setting pins them to a still frame if you prefer.
<color=#7FD4FF>Hide Gold</color> - a utility toggle that masks your gold on leaderboard surfaces.

<color=#FFD94D><b>EQUIPPING</b></color>

- One at a time: titles, trails, player colors, cursor colors and player effects use <color=#7FD4FF>Set Active</color> / <color=#7FD4FF>Unequip</color>.
- Multi-equip: name styles and map skins use <color=#7FD4FF>Equip</color> / <color=#7FD4FF>Remove</color> - stack your name styles, hold a rotation of skins.
- Hide Gold is an on/off toggle.

<color=#FFD94D><b>WHO SEES WHAT</b></color>

- <color=#7FE87F>The only cosmetic a player WITHOUT the mod can ever see is name styling</color> - styled names ride the same name field vanilla already renders, and putting styling in a name has always been possible in vanilla ROUNDS. Even there, glow and typeface are mod-side extras a vanilla screen can''t display.
- Everything else - trails, player colors, auras, faces, map skins - renders only for modded players. A vanilla opponent sees your default body color, no trail, no aura, and an empty slot where a custom face part would be. <color=#8A8A93>The game skips the unknown part cleanly: no crash, nothing substituted.</color>
- Modded viewers can individually turn off other players'' trails, player colors and animated cosmetics in Settings.

<color=#FFD94D><b>STOCK, DROPS AND TEASERS</b></color>

- The shop lists everything by price and shows what you own, each item''s artist, and stock.
- Community items can be limited: a drop shows N of M left and greys out once sold out.
- An item can exist before its sale opens - it shows as not for sale until the artist opens sales, and brand-new arrivals tease on the Home tab''s newest-cosmetics panel first. <color=#FF6666>Seeing an item on Home doesn''t mean you can buy it yet.</color>
- You can''t buy an item twice, and a purchase you can''t afford is refused - no debt, no partial buys.

<color=#FFD94D><b>THE ARTIST STUDIO</b></color>

Community artists make a large share of the catalog. The pipeline:

- An artist (a role granted in-game) submits art from the Artist tab: one 512x512 PNG, a GIF, or up to 16 numbered PNG frames, positioned on a live on-body preview with slot, scale and offset.
- The submission goes to review. Approval alone doesn''t put it on sale: the art has to ship inside a mod release first, because cosmetics are bundled into the mod so every player''s game can render them.
- Once shipped, the artist opens sales and controls the price, the stock cap, and who may buy - an artist can block specific players from buying their items.
- The artist earns <color=#7FE87F>a 30% royalty</color> (rounded down to whole Gold) when another player buys their item. No royalty on gifts.

<color=#FFD94D><b>GIFTS</b></color>

Only artists can gift, and only their own items: a free copy to any player who has used the mod, including before sales open. Gifts still consume stock on a limited drop. There is no player-to-player gifting, and no way to send gold to another player.', '5aaebe531cb9cf098ffe44c7445ae831469d26db', TRUE, 'InfoLibrary · (file scope)')
  , ('4b91176bba6fd963', 'client', 'Could not cancel: {0}', '80718cedfe6e4c0f70b119b6e03dc51a4650447a', FALSE, 'NativeUI · ClickLobbyBet')
  , ('86fd5a3453cbbbad', 'client', 'Could not confirm your seat. Retrying', 'a946a02658260725c4a859acbedd45aa9f8c9bcf', FALSE, 'FfaReadmit · Act, Refusal')
  , ('0cb26d500e44e471', 'client', 'Could not decode one of the animation frames.', '121a6b29710d7dbf60c23a87312d793b55096118', FALSE, 'CompetitiveUI · OpenCosmeticAnimTestPreview')
  , ('1f034970c93e4da5', 'client', 'Could not join as spectator - the game may have ended.', '030e0672400e1534d31172faec59cf7062e1222f', FALSE, 'SpectatorJoiner · Fail')
  , ('492b0e14064a334a', 'client', 'Could not load this report', 'eb7a493539c5d8c3a22ebc8f570229cbe4fbbf5c', FALSE, 'SessionReportView · ErrorMessage')
  , ('54f9fc8b48b22c94', 'client', 'Could not load this report (error {0})', 'e85a2435937a0b9f1512d33700080775d15b2ff6', FALSE, 'SessionReportView · ErrorMessage')
  , ('81b4817c1b10412f', 'client', 'Could not open that cosmetic preview.', 'c5df9fd9a7f89cc706132600acab54fdb3ffa145', FALSE, 'CompetitiveUI · OpenCosmeticTestPreview')
  , ('168c217e01ee25d6', 'client', 'Could not record the pack open on this PC - nothing was sent to the server', 'e2a5bce45d00a56d8b2bd18578ab5080a36b1c8d', FALSE, 'PlayerCardsUI · BeginOpenHeld')
  , ('ff775368c6e67bef', 'client', 'Could not record the purchase on this PC - nothing was sent to the server', '172d12cc280921471e01c71f22690cd7e6dd228e', TRUE, 'PlayerCardsUI · BeginBuy')
  , ('66acd1c2d1011708', 'client', 'Could not rejoin at this point', 'b259a93aa0fdab38481cedea7268c2e454ada899', FALSE, 'FfaReadmit, TeamHoldReturn · End, Refusal')
  , ('ed2b3ea93e519ce2', 'client', 'Could not spectate this game.', 'ea1ef48f04095e33d74e44ac5f55806cdc6f039e', FALSE, 'ApiClient · SpectateReason')
  , ('61f1806355fbefaa', 'client', 'Couldn''t change Appear offline - try again', '034bec883ab3debd39fbe97e1a8ea46dd6aeced8', TRUE, 'NativeUI · BuildSettingsTab')
  , ('7499ab9b304a83eb', 'client', 'Couldn''t change Show Discord on leaderboard - try again', '6fd5880619ade7b9b8f14cfd6e99c6aefb2aa25a', FALSE, 'NativeUI · BuildSettingsTab')
  , ('783580abb3a7a558', 'client', 'Couldn''t change the Same cards preference - try again', 'f2620432cd78f370a7020b64d47b25b664c343fe', FALSE, 'NativeUI · BuildSettingsTab')
  , ('d61b40d365632337', 'client', 'Couldn''t change the lobby settings.', '63fff1fb9c0ae37f237c2b93e83368e264d16251', FALSE, 'ApiClient · SetRules')
  , ('687db26d8cbaa35d', 'client', 'Couldn''t change the spectator setting - try again', 'a2945647946c1f17765c352675467add28162452', FALSE, 'NativeUI · BuildSettingsTab')
  , ('2da191e612f59089', 'client', 'Couldn''t confirm 1v2 queue leave — the server will clear you shortly.', 'b0f81efdd534d46cae6d44d58077b1b6ed1a6553', FALSE, 'ApiClient · OvtLeaveQueue')
  , ('6b9cd2a1a0ab7b42', 'client', 'Couldn''t confirm 2v2 queue leave — the server will clear you shortly.', '68ec5a075ef700240242fa9a050ea434ed66e3cb', FALSE, 'ApiClient · LeaveTeamQueue')
  , ('4686f7188c6efe31', 'client', 'Couldn''t confirm FFA leave — the server will clear you shortly.', '1cac419dc5eb69061e2b951c738307f031b99f0a', FALSE, 'ApiClient · FfaLeaveQueue')
  , ('4a7be244b1f524a1', 'client', 'Couldn''t confirm queue leave — the server will clear you shortly.', 'c3026e4015a9f4d6b0f6241292787249bc291cf9', FALSE, 'ApiClient · LeaveQueue')
  , ('472e0596956b3ea1', 'client', 'Couldn''t confirm the {0} lobby leave — retrying in the background.', '06222814ef4a26870f746258d2275f2d7016dda0', FALSE, 'ApiClient · LeaveLobby')
  , ('d430467a2a2ef6c4', 'client', 'Couldn''t get a link code', '81e4f95fa0ae1b315f8ca7ba3839315534787986', FALSE, 'ApiClient · GenerateLinkCode')
  , ('e0c9d155171ec734', 'client', 'Couldn''t join that lobby.', '6deea8800284674bfc7e7982c407d937829ef446', FALSE, 'ApiClient · EnrollResult')
  , ('6c69f7bf3992f0e5', 'client', 'Couldn''t join the 1v2 match — left the queue. Please requeue.', '4fc6fcfe986a0768c6810872195ff1572267939f', FALSE, 'ApiClient · UpdateOvtQueuePoll')
  , ('242c8e57c8c66cb7', 'client', 'Couldn''t join the 1v2 match — your lobby was dissolved. Please requeue.', '3a152fbb23e06aa19dd9ffdfa6a779c344fbeebd', FALSE, 'Plugin · Update')
  , ('7443446e8638c23d', 'client', 'Couldn''t join the 2v2 queue', '4df170619d634fa47e5daae97b531745de58200e', FALSE, 'ApiClient · JoinTeamQueue')
  , ('765e3059472dff50', 'client', 'Couldn''t join the FFA match — left the queue. Please requeue.', 'fd844b771d0a82bf96939a889060c8bd1fb63920', FALSE, 'ApiClient · ArmFfaLock')
  , ('09daf1b685b881ec', 'client', 'Couldn''t join the FFA match — your lobby was dissolved. Please requeue.', '5d5248d4caab0e50ec6fd0364a251463d07bc466', FALSE, 'Plugin · Update')
  , ('9d3a2b5d82d50d94', 'client', 'Couldn''t join the queue', '2197066bc8988e5594dd0acffb78593cd79b43e8', FALSE, 'ApiClient · JoinQueue')
  , ('a8d53a5354d4295b', 'client', 'Couldn''t join the ranked match — please requeue.', '0e2c60155a4e9abfda0b24362270bd9977695975', TRUE, 'Plugin · Update')
  , ('1e9e0d2019681a60', 'client', 'Couldn''t kick that player.', '635b1327e4909407ac4dd72c55143e124889caae', FALSE, 'ApiClient · FfaKickFromLobby, Kick')
  , ('c4d5526dfaef7312', 'client', 'Couldn''t leave the tournament - it may have locked or started', '0d891dd93ff117f9cb982affdfdf2659f6fec53e', FALSE, 'ApiClient · TournamentUnsignup')
  , ('8e3dc78d1bfc533d', 'client', 'Couldn''t reach the server - retrying in the background.', '55b12af2f1fc56486ff3c27b5e32668306a5b9f8', FALSE, 'ApiClient · SendEscapeRequest')
  , ('45482b9b7668a66b', 'client', 'Couldn''t record the match', 'fdf89f537d6eed53d362bb783ee9bcba1a2bc496', FALSE, 'ApiClient · ReportMatch')
  , ('4adb844bfc227e4e', 'client', 'Couldn''t record the match — retrying in the background', '7a62d6a8bd7e6b2ef66132ff1e4c1d57c8c65794', FALSE, 'ApiClient · EnqueueFailedReport')
  , ('8ccfa9de20b7c034', 'client', 'Couldn''t recover automatically - please restart matchmaking from the menu.', '295366d9ca40b6620c84fa1c9fce8a1a64cbb417', FALSE, 'GameStateWatcher · TickRequeueMachine')
  , ('f97b3c500645df08', 'client', 'Couldn''t rejoin your private FFA lobby — join it again from the browser.', 'e99f756b015752cfcf948712eaa513501b978d24', FALSE, 'ApiClient · FfaEnrollResult')
  , ('e360df22fbb855ff', 'client', 'Couldn''t rejoin your private {0} lobby — join it again from the browser.', 'b6ebcb596b839d72bedab659eb0497ee464a5e48', FALSE, 'ApiClient · EnrollResult')
  , ('172cf193c3f24d78', 'client', 'Couldn''t start the game.', '7e469436f604c67095e813dcd9af4a93194ba16d', FALSE, 'ApiClient · StartLobby')
  , ('a18255a7c68182e3', 'client', 'Crazed Eyes', '52b4f7979734d5a9daa6702b008bc4dd1047377f', FALSE, 'shop catalog · cosmetic name/description')
  , ('7ae8c98cd55250eb', 'client', 'Cream', 'd1e2abc18a8b508f620471e42c72adf3818c6480', FALSE, 'shop catalog · cosmetic name/description')
  , ('04a881a93d60819b', 'client', 'Create Lobby', 'c2c427166ba31cc0e90127bf9aa5db6bd64c30a7', FALSE, 'NativeUI · BuildFfaTab, BuildOneVTwoTab, BuildTeamTab')
  , ('9cb79e28fba384b2', 'client', 'Create Private 1v2 Lobby', 'f908121ac9e34b2d0a9e9cdfd8d8014cea010503', FALSE, 'NativeUI · BuildOneVTwoTab')
  , ('44182e48830d89b0', 'client', 'Create Private 2v2 Lobby', '0ad69726899bc7c2f873cdd276a1e2a2b22111d8', FALSE, 'NativeUI · BuildTeamTab')
  , ('a62668dd4b76a121', 'client', 'Create Private FFA Lobby', '3c1c959cd4d733eda596e5e262349e9e9caef386', FALSE, 'NativeUI · BuildFfaTab')
  , ('abc5b7574b8d23f1', 'client', 'Create Private...', '1cc92e26adf309a65f9715f72031f81420b4f7f5', FALSE, 'NativeUI · BuildFfaTab, BuildOneVTwoTab, BuildTeamTab')
  , ('1566b2c6e09119fc', 'client', 'Crimson', 'b3f39ab486dccbade852f17535c258ceb02694ae', FALSE, 'shop catalog · cosmetic name/description')
  , ('8aa3777be23776ab', 'client', 'Crimson Streak', 'e1d3d4a4ebd01690499f49db911a9f70902a7e8c', FALSE, 'shop catalog · cosmetic name/description')
  , ('272823abc8553286', 'client', 'Crosshair', '800092e3e184dba68b4de9b269c1cf1864080096', FALSE, 'NativeUI · ShapeLabelTr')
  , ('f027d1391cc75d18', 'client', 'Crown', '410494f2cf468cb98b4655657880ea42f72183c0', FALSE, 'shop catalog · cosmetic name/description')
  , ('53561db7206227fb', 'client', 'Cub', '0f231c3015205f052cbad186a6345690da5791a0', FALSE, 'shop catalog · cosmetic name/description')
  , ('4bded0062544c6c1', 'client', 'Current Game: {0}', '548bc7d4e4c72a8c8109d05c37ba08480735912b', FALSE, 'SpectatorHud · ComposeBarLine')
  , ('c8a0e2e08bdb7f47', 'client', 'Current Rank', 'f996d22f90fe3880c9bf2c0026b7e64b2c9d234a', FALSE, 'shop catalog · cosmetic name/description')
  , ('f8eda8388cbfb9d1', 'client', 'Current Series: {0}', '896bb6be6b7ff1931057c51860c1493a0857087d', FALSE, 'SpectatorHud · ComposeBarLine')
  , ('45628b1135e9893a', 'client', 'Current run: {0}', 'f61536724772f6ff399a416d6705840134e81e1c', FALSE, 'TitleLaddersUI · ProgressText')
  , ('2d5fb07036c009d5', 'client', 'Current tier', '5e0d9add3a3c1db19ee2d6fae7cd9f6773f88ac1', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('ea74c988fbaed338', 'client', 'Current tier: {0} - {1}', 'a9e4255c907173fe9a57bd6351bee141e6be44a4', FALSE, 'TitleLaddersUI · PaintEntry')
  , ('70bb05a155a6fc96', 'client', 'Currently: {0}', '02e09889c563a0ef243f85006a1227c9259c63c2', FALSE, 'NativeUI.Keybinds, NativeUI.Settings · KeybindRenderPane, SettingsRenderDestructivePane, SettingsRenderPane')
  , ('1a2cbebcdb936308', 'client', 'Cursor', '2239943c8d0af354a467e6cc18b9ec9e32f2afcf', FALSE, 'NativeUI · (file scope)')
  , ('3768972fb7662437', 'client', 'Cursor: <color=#88CCFF>{0}</color>', '21a1cca38ce259e8e8241d9335c19da50c1c6eb3', FALSE, 'NativeUI · PaintCursorShape')
  , ('e307fa465c2af7fb', 'client', 'Curved crimson horns for your inner demon.', 'fc9e3a357cf300a24d8e3496e2a38f19a2b8d2ee', FALSE, 'shop catalog · cosmetic name/description')
  , ('47d1650b03894f39', 'client', 'Custom faces', '7c0d87a15587ef5cae2edf1d482863312cd9e5de', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('0f6b4c74dec1367c', 'client', 'Custom player body colors: <color=#88FF88>ON</color>', '3a6ee4336b7ca871681e18318b4ba037122dacf0', FALSE, 'NativeUI · PaintPlayerColors')
  , ('0366c6e45b629e99', 'client', 'Custom player body colors: <color=#FF9966>OFF</color>', '43a183043498ee5e5e63748c343d3c393dc71238', FALSE, 'NativeUI · PaintPlayerColors')
  , ('836f724fe5b3074d', 'client', 'Custom player body colors: shows shop-bought Body Colors on you and other modded players. Off = everyone falls back to default orange/blue.', '175c48cf6528b593772f727b6247f068ca95d6a8', FALSE, 'NativeUI · BuildSettingsTab')
  , ('306025349f761c7f', 'client', 'Cyan Cursor', '26744388a2aad194db923050c4fe31ade1973f3f', FALSE, 'shop catalog · cosmetic name/description')
  , ('b1ab6e33f7326e5b', 'client', 'Cyan Name', '747761927d1053584caa147babb5f8bb92befb6e', FALSE, 'shop catalog · cosmetic name/description')
  , ('17f1b530f255f006', 'client', 'Cycles the chat overlay between normal, pinned and muted.', '41991e10c1aa8405fab33e839f8a000870e75b6b', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('9fb60bf3aa58378a', 'client', 'Cycles your equipped map color skins as a new round paints in.', '2733022db777aac7a672114bc1667e589dbcc99f', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('df73b3e97fba0f69', 'client', 'DISCARDED', '278d6c0448fc24279c6837735dda38cf6963e8c4', FALSE, 'PlayerCardsUI · DiscardedLine')
  , ('a9e67c1a4c1f9c6a', 'client', 'DISCARDED' || chr(4) || 'pack open', '59c318787a497767b03e4c6f2e2299460369a0ff', FALSE, 'PlayerCardsUI · DiscardedLine · pack open')
  , ('81ab6a5164d7d1c1', 'client', 'DISCARDED (+{0} shards)', '3b117a5e8e0fa8872483047881d6b04bec06b182', FALSE, 'PlayerCardsUI · DiscardedLine')
  , ('ae21bb12835baffa', 'client', 'DOT TICKS VS THE BLOCK WINDOW', '4f6eba21524da93b7eea907d03f93668ee66ebb6', FALSE, 'InfoViz · BuildDotTimeline')
  , ('d33ec0a6ac310106', 'client', 'DOWN', '30e504c829201f1e519376dfee2e0e399c82484c', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('f9c988548e02a432', 'client', 'DPS', 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', FALSE, 'PostSessionReport · BuildCells1v1, BuildCells2v2Game, BuildCellsFfaGame')
  , ('8ea6727cee3b71a2', 'client', 'DUPLICATE +{0}', 'a968a599615c11fb18fbdcaa114e2d4a9f339972', FALSE, 'PlayerCardsUI · MarkLine')
  , ('8233e51d0ebbd3b9', 'client', 'DUPLICATE +{0}' || chr(4) || 'pack open', 'c5df7463f6f1ed0183540687dce3f7f9ac9b556a', FALSE, 'PlayerCardsUI · MarkLine · pack open')
  , ('a5bf966e5b932455', 'client', 'Daily limit reached - paid packs reset at midnight UTC', '35343d5d72d6a49312ecd5daa27b833c86e1193a', TRUE, 'PlayerCardsUI · ReasonText')
  , ('b4874c5e05d6538d', 'client', 'Damage', '7bf6d1d3a58a22ee49f3b78fc132bc5e98633e4a', FALSE, 'SessionReportModel, TabStatsOverlay · BuildTotalsPages, EnsureLocaleStrings')
  , ('e605035a007d4521', 'client', 'Damage dealt (cumulative per game)', 'fb0aee06de4f9faa59a99f65e1ec00a10f6999d6', FALSE, 'SessionReportModel · Build')
  , ('8b8c838d6a2c26bb', 'client', 'Damage numbers: <color=#88FF88>EVERYONE</color>', '1194f0b3ca797351cb123309658ad3d083940249', FALSE, 'NativeUI · PaintDamageNumbers')
  , ('95bc9f150a44c35f', 'client', 'Damage numbers: <color=#DDDD66>ME</color>', 'b8c1898c1d13a5a51b5eac9b210b849d6c0f1cac', FALSE, 'NativeUI · PaintDamageNumbers')
  , ('f4c02da7bcac46e8', 'client', 'Damage numbers: <color=#FF9966>OFF</color>', 'c688bb9ebf2a17471d9b6a12704c6548b4e08d85', FALSE, 'NativeUI · PaintDamageNumbers')
  , ('f4a04f4e7dc9b3b4', 'client', 'Damage per game', 'e7a0bc3a8cde1a01b491c7ce2b8f9a671508a9f0', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('cb80aaef215f676c', 'client', 'Damage types & buffs', '10d9adc648f4c2f08f64a863676777cec2bce624', FALSE, 'InfoLibrary · (file scope)')
  , ('f2b2d44102db58c5', 'client', 'Dance is on cooldown - try again in a moment.', '8b7c4dd82c77a28db0f41a622064aad9ee8b1ef8', FALSE, 'CompetitiveUI · DwSend')
  , ('0f80d1b0263ecadd', 'client', 'Dance on my card: {0}', '750183709bff29cd195d89de3e73601a4a4ad023', FALSE, 'PlayerCardsUI · PaintDance')
  , ('8c175f945cf71901', 'client', 'Dance wheel', '0f8be133ff7d787614d1ede82f6301aa0db03f3a', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('3641c4073564f471', 'client', 'Dances', 'b6fe8586434a4165d8531d4cc3c065a8a9e700df', FALSE, 'CompetitiveUI, NativeUI · (file scope), DrawDanceWheel')
  , ('b5a636572c560a3f', 'client', 'Dark Aura', 'd1337bd66502e493e3dd898db928623e5e720ba0', FALSE, 'shop catalog · cosmetic name/description')
  , ('d4ffe97d52355fb3', 'client', 'Dark ash walls with a pale rose-silver accent over a deep red night, with a faint red glint.', 'b4816f88de2979e10fa5707a46a4176b09682f23', FALSE, 'shop catalog · cosmetic name/description')
  , ('a9aa7dd7e345eacb', 'client', 'Dark indigo walls on the purest black background in the catalogue.', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', FALSE, 'shop catalog · cosmetic name/description')
  , ('10cc5458fd27e27a', 'client', 'Dark red blocks on a dim warm backdrop.', '6400ddf76a965495252cffa62e366cd2e1e5670f', FALSE, 'shop catalog · cosmetic name/description')
  , ('0b90ace75370115b', 'client', 'Dark steel walls with amber window glow against a black-navy sky, city lights twinkling behind.', 'cc83269496c01ca47b98e106203958dcc350fa97', FALSE, 'shop catalog · cosmetic name/description')
  , ('bc4565d2dfd86677', 'client', 'Data & Privacy', '43cd04b1d12ecf152fe28138809f095b8750be57', FALSE, 'NativeUI · PaintConsent')
  , ('5178e08b586191ad', 'client', 'Data sharing is disabled in your settings', '5443261f4adb51b49ffb9503b4f259c89b3987aa', FALSE, 'SessionReportView · ErrorMessage')
  , ('cf3dbad5f408d103', 'client', 'Data sharing is off - allow it in Settings to use mail.', 'eed4f80814b5b7895e0a78d63424dabcbf625646', FALSE, 'MailClient · ErrorDetail')
  , ('8bdb5aaa3ae04a72', 'client', 'Date Earned', 'c58b1c0f2b7a976f48dbdb8ed79e649f25068847', FALSE, 'NativeUI · BuildAchievementsTab')
  , ('fe95157ea5d812b9', 'client', 'Date format', '94ee8869082873abf458deca86a2b8e3a3091aa0', FALSE, 'NativeUI · BuildSettingsTab')
  , ('8b736b068bcaa904', 'client', 'Date format: <color=#88CCFF>{0}</color>', '08596d25c886c9f955df32042b64f4be840b7528', FALSE, 'NativeUI · PaintDateFormat')
  , ('26ff01ebab1e5fd2', 'client', 'Date obtained', 'aca780d4f575dff9323a27bb4fd0e72ccaa05ee2', FALSE, 'PlayerCardsUI · SortLabel')
  , ('558fc3496ae9d9c9', 'client', 'Day/Month/Year', '689cd25e4f221a18734b96f3bf83f166c4a7115a', FALSE, 'NativeUI · PaintDateFormat')
  , ('16c5dd2ac87e01cf', 'client', 'Deadeye', '5364fd665bc364a4a8275475b9ae65e5b5e4f40e', FALSE, 'shop catalog · cosmetic name/description')
  , ('70575acc4c8435c3', 'client', 'Deadlines & forfeits', 'e530201df3b466b7afb745f02669182642d7a8ef', TRUE, 'InfoLibrary · (file scope)')
  , ('00cf7aaf51815456', 'client', 'Deal Conditional damage', 'd6c04483c4b6c4688aeb80a462e1889c65799c35', FALSE, 'InfoViz · BuildRefreshGate, TextFallback')
  , ('a2327401bb098f1b', 'client', 'Deal damage', 'c16670c41d27246a616f267b82eb2db03f8babfa', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('e9c5e68200294591', 'client', 'Deaths', '41cd883d2e19f7e12b81005813dcd06b656887ef', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('996ce21c16a0d36d', 'client', 'Decay', '423840285bb24d597e8954d586ca2dc277272f3f', FALSE, 'shop catalog · cosmetic name/description')
  , ('3af3d6023d5ff20e', 'client', 'Decent', 'a10292c3bb3a1332f06c324215d42310757b082c', FALSE, 'shop catalog · cosmetic name/description')
  , ('d7ae69b50f05ab63', 'client', 'Decimals on the HP readout in the hold-{0} board, the spectator seat and the broadcaster HUD. Both halves of "current/max" follow it, so a card that leaves max health on a fraction stops reading as a whole number too. Local display only - nothing stored or sent changes.', '58eca18787c3b15753cb8361f5717289dea14a1c', FALSE, 'NativeUI.Keybinds · KbDescHpPrecision')
  , ('119b8c2381d56d77', 'client', 'Decline', 'b59cf9ed55bb5bd999077bce310a9641033b6485', FALSE, 'FfaReadmit, NativeUI, PlayerCardsUI · BuildRankedRow, CreateTradeRow, DrawBar')
  , ('acda0f3497987f2a', 'client', 'Decline (offline mode)', 'bbe6a0d4c7d69d2481e2d3224d708c68e8e22709', TRUE, 'CompetitiveUI · DrawConsentModal')
  , ('23f8eec0346dce8b', 'client', 'Decline anyway', '77c54610ab3afb94c80d4edb1ac1f99b2fabf115', FALSE, 'CompetitiveUI · DrawConsentDeclineConfirm')
  , ('0f32204d64918912', 'client', 'Decline data consent? The mod will run offline: no leaderboard, no ranked matchmaking, no chat, no player cards. You can allow it later in F5 → Settings → Privacy & account.', '929a764676ff507fb6f3a07bd1e8b729e6a26c4a', TRUE, 'CompetitiveUI · DrawConsentDeclineConfirm')
  , ('bbe3197e69738bd2', 'client', 'Deep blood-red body color.', '698769e3384f77f8587a7217e7ac7b3a9c9990c7', FALSE, 'shop catalog · cosmetic name/description')
  , ('7b5aaa66e23a080d', 'client', 'Deep blue-violet of the moment after sunset.', 'bda30be42cb140a97c3e1a67751c1da38c2ceb11', FALSE, 'shop catalog · cosmetic name/description')
  , ('efe79bae30a5be47', 'client', 'Deep cool dusk blues with dimmed exposure.', 'b30ee14d6f5a4695053e04642b94ecb60916730f', FALSE, 'shop catalog · cosmetic name/description')
  , ('ce5c7a3baf9b6aa4', 'client', 'Deep evergreen blocks on a dimmed green-tinged backdrop.', 'ef88541ebbea1230910389468e407d07bf0c5d46', FALSE, 'shop catalog · cosmetic name/description')
  , ('13d0d287c990cb23', 'client', 'Deep forest green rising to bright jade. Two-color gradient.', '01d54aa6323503c2e4424a176601f7b00c366139', FALSE, 'shop catalog · cosmetic name/description')
  , ('730802fcc588b2ac', 'client', 'Deep green hedges and bark-brown walls on a dark brown night.', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', FALSE, 'shop catalog · cosmetic name/description')
  , ('3a1384cf68cbafa9', 'client', 'Deep ocean midnight — black with a hint of cold blue.', '6b2e6d11146de2269d0295012c6fd7f7061101b1', FALSE, 'shop catalog · cosmetic name/description')
  , ('b95f34ace2fa0325', 'client', 'Deep ocean-blue body color.', '0c7459d1da70cc3b119267a865e39cb294ce276a', FALSE, 'shop catalog · cosmetic name/description')
  , ('f05cbe9e346dc452', 'client', 'Deep red smoke following your every move.', '343c93580548bc432445ab81ff3add7560c3d74c', FALSE, 'shop catalog · cosmetic name/description')
  , ('91dc11e808ee40a1', 'client', 'Deep royal purple, the kind that absorbs every photon.', 'cba6e53a33069151fb549a1f0e6934023b31955b', FALSE, 'shop catalog · cosmetic name/description')
  , ('ab0f98bd6a6bf5f1', 'client', 'Default', '808d7dca8a74d84af27a2d6602c3d786de45fe1e', FALSE, 'NativeUI · BuildAchievementsTab')
  , ('f4999184f00fd765', 'client', 'Default (random)', 'ab5e0dd7f1c6d715060995c24097c27dabc964a1', FALSE, 'shop catalog · cosmetic name/description')
  , ('77698eafc221e602', 'client', 'Default start: <color=#AABBEE>{0}</color>   Signups close: {1}', '133e5f657b000e24c75606ccd1808f5d6fb5a618', FALSE, 'NativeUI · RefreshTournaments')
  , ('1dc746156cbb6d34', 'client', 'Delete', 'f6fdbe48dc54dd86f63097a03bd24094dedd713a', TRUE, 'MailUI, NativeUI.Keybinds · BuildReaderView, KeybindKeyName')
  , ('81252e5360b78a3e', 'client', 'Delete Chat Message...', 'e29fa79082af77a532d9b616ea13c8b6b7538782', TRUE, 'NativeUI · BuildAdminTab')
  , ('e48c0380bfbd05a1', 'client', 'Delete My Data', '07c349dd6285cec25ea784f21704b057dbf48f57', TRUE, 'NativeUI, NativeUI.Settings · BuildSettingsTab, SettingsRenderDestructivePane')
  , ('6decaed07b4160c0', 'client', 'Delete My Data...', '5d3105ed80dc94bd4e080cbe35b6389a727a444f', TRUE, 'NativeUI · PaintDeleteRow')
  , ('93cce73d376d842d', 'client', 'Delete a chat message - type to search', '13030ba667c11d4293b2cc90dd33bf612197ee3e', TRUE, 'NativeUI · OpenChatDeletePicker')
  , ('a14b37e38fc546ec', 'client', 'Delete chat message', '0e629a058d09bbfb532b8e03465452fb92425570', TRUE, 'NativeUI · OpenChatDeletePicker')
  , ('5f82a7a4a2210951', 'client', 'Delete this message?', 'e0a26141796cf26afdd14dd52e267fc90cf56c48', TRUE, 'MailUI · DeleteCurrent')
  , ('9633ce2741a0b7cb', 'client', 'Demolitionist', '3d44114e197112dc928b1b5e54ab7c91d191dd29', FALSE, 'ApiClient · AchievementDefs')
  , ('664c773cdf0bb4c7', 'client', 'Demon Wings', 'a957d1b7bc867ae01a8723a614a867b018c111b4', FALSE, 'shop catalog · cosmetic name/description')
  , ('91f20ef1463a3bc2', 'client', 'Demonic', '607586a5c7a6fab475c1842b9c66ddef446ac843', FALSE, 'shop catalog · cosmetic name/description')
  , ('481b4ba4dfb81cb6', 'client', 'Denied artwork cannot be reopened by a placement change', '16cca68667b94710df700888e26aec2b1e595e4b', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('2fc6ee0492894d1d', 'client', 'Despawn off-screen bullets — host clears bullets that exit the camera viewport.', 'a1b943b041c4467fd8e874c41839ca774a8879e4', FALSE, 'NativeUI · BuildSettingsTab')
  , ('ab599014703db680', 'client', 'Detail: a blue top hat with a red band and a star wand, held up by two white gloves (animated). Equip in the Character editor.', '1efa525d77812314079a18478783feb4d026be9d', TRUE, 'shop catalog · cosmetic name/description')
  , ('e29cd4f6ab4c6c37', 'client', 'Detail: a candy cane that looks stuck right through your head. Equip in the Character editor.', '45622d80b42d25a48e18614b25fc6af2d392e796', FALSE, 'shop catalog · cosmetic name/description')
  , ('8b18474fadf03a04', 'client', 'Detail: a gold medal with a crosshair, hung on a red ribbon. Equip in the Character editor.', '0e3d86208a93b2e5faa1d6ec7568899adc77b050', TRUE, 'shop catalog · cosmetic name/description')
  , ('804ecaa4a45d571d', 'client', 'Detail: a green coiled spring dressed as a festive tree, with baubles and a gold star on top (animated). Equip in the Character editor.', 'fc041c1d7fea61efbe7996b3befec1ab3da64277', TRUE, 'shop catalog · cosmetic name/description')
  , ('d441196cae0100bf', 'client', 'Detail: a green vine crown with white daisies. Equip in the Character editor.', '4b6d898d13711b187485927a564f85941a95e769', FALSE, 'shop catalog · cosmetic name/description')
  , ('75aa3de4aadd7d91', 'client', 'Detail: a headband of grinning pumpkins and a little ghost bobbing on springs. Equip in the Character editor.', '5deec6aa9eca170cc4236c405fdd5116891a0d0f', TRUE, 'shop catalog · cosmetic name/description')
  , ('e181b899ea81f246', 'client', 'Detail: a headband with two fizzy soda cans and a long drinking straw. Equip in the Character editor.', 'afd5cf37a25b0889fd45075dc11b92695292845b', TRUE, 'shop catalog · cosmetic name/description')
  , ('4a7a28618bea830b', 'client', 'Detail: a pink headband with round ears, puffy ear pads and a unicorn horn. Equip in the Character editor.', 'a0e76ad6ffc1e05c909e119f1a7379ae55d36e25', TRUE, 'shop catalog · cosmetic name/description')
  , ('6fb3f056a5481e85', 'client', 'Detail: a shooting star circling overhead (animated). Equip in the Character editor.', '55a2bf4d07dee2378de337391d28fcb235be8066', FALSE, 'shop catalog · cosmetic name/description')
  , ('eedb1c7fe8b5c9e6', 'client', 'Detail: a small round pink buddy with a surprised face. Equip in the Character editor.', '3163bdef48fa56ffe5665f98de4148857b1527c3', FALSE, 'shop catalog · cosmetic name/description')
  , ('15561f3a4ceac11a', 'client', 'Detail: a top hat wrapped like a present, with an orange ribbon and bow. Equip in the Character editor.', '37aa2dbb4485cbd48b2491572713b6f1293bba29', FALSE, 'shop catalog · cosmetic name/description')
  , ('bfb50a0967f78d45', 'client', 'Detail: a wide woven straw hat with a red band. Equip in the Character editor.', '3298ad795507acaa11119fdaab0dfa3a256baf1a', TRUE, 'shop catalog · cosmetic name/description')
  , ('e296fa7aa7a755d8', 'client', 'Detail: an ice cream cone tipped upside down, melting over your head. Equip in the Character editor.', '6178c64befec1eb774a775c7418b8d19a2684373', FALSE, 'shop catalog · cosmetic name/description')
  , ('6b4f372aa868c8ef', 'client', 'Detail: an orange and grey striped top hat with a grumpy face badge. Equip in the Character editor.', '2a9689063a6ec3186472760e1fcc478643f2a7fb', FALSE, 'shop catalog · cosmetic name/description')
  , ('83c7c50f88df9d10', 'client', 'Detail: certified angel. Equip in the Character editor.', 'b76e06ba2922bd5320f09988df4115981726164b', FALSE, 'shop catalog · cosmetic name/description')
  , ('ecfe2ec2eb6da507', 'client', 'Detail: community cosmetic. Equip in the Character editor.', '5886a70067e8a23c141147c6ce5dfefbab5674d6', FALSE, 'shop catalog · cosmetic name/description')
  , ('57f1bdcef79892ac', 'client', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', '91e791312991c216c7bdca715ee22fa1062f21d0', FALSE, 'shop catalog · cosmetic name/description')
  , ('0599d7612e9c92b0', 'client', 'Detail: cozy star-studded earmuffs. Equip in the Character editor.', '3606ab5ea0cab3d56f0f7fb96596c962e44194b9', FALSE, 'shop catalog · cosmetic name/description')
  , ('f8df007f9e5e49dd', 'client', 'Detail: green tear streaks running down both cheeks. Equip in the Character editor.', 'e4c85cd992a342d921decccce199d98679f4a83d', FALSE, 'shop catalog · cosmetic name/description')
  , ('9c528b8f8d623258', 'client', 'Detail: heavy is the head. Equip in the Character editor.', 'd35ece05488a58ed9adbf2fd9423a0e4bd0c206c', FALSE, 'shop catalog · cosmetic name/description')
  , ('7487b825669e2214', 'client', 'Details', 'dc3decbb93847518f1a049dcf49d0d7c6560bcc6', FALSE, 'NativeUI · BuildAdminFlagRow')
  , ('20cca7cfec3ff4f6', 'client', 'Details (optional)', '138a572192dc85876194243521dc344836f4d3f6', FALSE, 'MailUI · DrawReportModal')
  , ('efe8bab4437e0f7e', 'client', 'Detected: {0}', '3c78aabd881815a2aac4c787cb0248e8fd48acfd', FALSE, 'NativeUI.Settings, NativeUI.SettingsDrive · DriveL11, SettingsRenderPane')
  , ('0cff0a7295d0881c', 'client', 'Devil Horns', '0f2a3d6e36b590dba6e93f3a10088a8f34103cae', FALSE, 'shop catalog · cosmetic name/description')
  , ('1bf9b5aeb836afe7', 'client', 'Diagram of Spirit''s research, ''On Damage Types and Buff Activation''.', '7c6f286eedfab90b66922459d09fc9166e5b14d3', FALSE, 'InfoViz · BuildRefreshFlow')
  , ('35a41c9dae50afd8', 'client', 'Different players who have picked this card', '1e58e349feb201eaf84819b8cbf5ce95e3251093', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('2cddd33bf9f91479', 'client', 'Disable', '9a7d4e0687b14e2b7cda406900b802782cd50a62', FALSE, 'NativeUI · BuildRankedRow')
  , ('222d85297c06217b', 'client', 'Discard', '36fff63ccbcd7bf96ac9014e3e482702fc2b02d4', FALSE, 'MailUI, NativeUI, PlayerCardsUI · BuildAdminQuarantineRow, BuildComposerView, CreateTile +1')
  , ('82897577963eb1c9', 'client', 'Discard this draft?', '6dbafbade29323ae87541f01dd921ed9a1c49604', FALSE, 'MailUI · DiscardCurrent')
  , ('f2a136f46f3f09b9', 'client', 'Discarded {0} card(s) for {1} shards', 'e397ebddfd112b05ac1dbcd4315b58f33374a8d3', FALSE, 'PlayerCardsUI · FinishDiscard')
  , ('d4d3bcd127e71244', 'client', 'Discarded {0} card(s) for {1} shards; then: {2}', '86aae3336f3622229f6aabb9ce06b97751988772', FALSE, 'PlayerCardsUI · FinishDiscard')
  , ('efc2b84815e43a0c', 'client', 'Discarding a card gives shards by its rarity: Common 5, Uncommon 15, Rare 40, Epic 150, Legendary 600. Shards buy packs. Discard takes one card and the Dupes button every other copy of that exact card; Shard pack (on a pack you opened) and Select (in the binder) shard up to 40 cards in one go.', '32a3c8bd491049322046e792b3440f7fb9c1c2f1', FALSE, 'PlayerCardsUI · RefreshInfo')
  , ('a0fd44d7de2285c6', 'client', 'Disco Fever', 'c582339cc3887c3a38bfa00b7a7c8e9ff54b118c', FALSE, 'shop catalog · cosmetic name/description')
  , ('23e7463a77676d31', 'client', 'Discord', 'bccc14ee7da1d20ff06b9ff2497087e8c7d9f28b', FALSE, 'NativeUI · BuildPage')
  , ('1322e8bebba60a17', 'client', 'Discord Link', '6853dca9066719a20454a8182b7bdbbf4d68df5e', FALSE, 'NativeUI · BuildHomeTab')
  , ('9acb4c4279a5ba37', 'client', 'Discord relay: <color=#88FF88>On</color>', '7fb3920166a0929f4a21a28dbc4f1e2f711b60c7', FALSE, 'MailUI · PaintMailRelay')
  , ('cf032ccb25bdee38', 'client', 'Discord relay: <color=#AAAAAA>checking...</color>', 'b01de5583efdec828ade8c85567d1ba396b15842', FALSE, 'MailUI · PaintMailRelay')
  , ('439e4b14be8ab31d', 'client', 'Discord relay: <color=#AAAAAA>link Discord first</color>', '8fe6f989784d0e7d8e62aef93d8868c04cc13fa2', FALSE, 'MailUI · PaintMailRelay')
  , ('af219d4fb608c617', 'client', 'Discord relay: <color=#FF9966>Off</color>', '2e5678587b78883f07d53a1c98bde8de2b390c19', FALSE, 'MailUI · PaintMailRelay')
  , ('71ab18d24bbd5f46', 'client', 'Dismiss (1 min)', '170d1f2f961db1e8e435c04f979012f0c4813bb2', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('a30778fa3d629f33', 'client', 'Displays your live rank tier (updates automatically as you rank up or down)', 'b7453a2df406d0e7a753fa2a13a759aea4dd2294', FALSE, 'shop catalog · cosmetic name/description')
  , ('3dbdeabd231902e3', 'client', 'Dmg/game', '698ebe34accf7b9dd2f947539c86935180eb2439', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('26c9ea0e87954040', 'client', 'Do nothing', 'd268ba5209c487d727e01c5fd074cb9328ec5243', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('e807319aedaee9da', 'client', 'Dog', 'b866865be01a47a38a8b8e70d9eeb4d216a5889b', FALSE, 'shop catalog · cosmetic name/description')
  , ('9ac11402145c5077', 'client', 'Dog God', '8db7dfd838754ced381258b3d8b4635fb7bfd8f5', FALSE, 'shop catalog · cosmetic name/description')
  , ('1f8130b364fad8c5', 'client', 'Done.', 'e2bcda84facb3954e32539ae66300758b6d834b2', FALSE, 'NativeUI · ShowArtistResult')
  , ('5dd95db1aab749ef', 'client', 'Dot', '46856bf70223eaada29f04362a03cca97f7cc822', FALSE, 'NativeUI · ShapeLabelTr')
  , ('2de3a943a045ca65', 'client', 'Double KO - nobody scored this round.', '019b92f53aad498f211a0607a94d18c8a47d2041', FALSE, 'FfaMode · HandleNextRound, SpectatorObserveRound')
  , ('3cceb107a990d449', 'client', 'Double Nova', 'dd9ef4e5a287b8269c0300bdefaaa072c8f4148e', FALSE, 'ApiClient · AchievementDefs')
  , ('cf677aeb4cca767e', 'client', 'Down Arrow', 'f45f0a3752ff13d006a65f09a4643e63c1237391', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('426e6d1b01fdabd1', 'client', 'Downloading full album...', '438d7ff95d32eb9ec0be883747768af8db8f4a80', FALSE, 'MusicAssets · TierStatusLine')
  , ('ff24240b91d77c97', 'client', 'Downloading music previews...', 'f0bc18fb5a18627d161794eb9056a83fe3ba03fd', FALSE, 'MusicAssets · TierStatusLine')
  , ('ddcce7205b472382', 'client', 'Downloading music...', '8319e5a5268114bf58d0eb608ded75db9b2095a7', FALSE, 'MusicAssets · TierStatusLine')
  , ('01598ec331fe3b04', 'client', 'Downloading update...', '097433a5c6393020b3ed7f568c2e5474c55e8a7c', FALSE, 'ApiClient · DoAutoUpdate')
  , ('3890f0cbb586ff4b', 'client', 'Downloading...', '66f3ac75224897b518295f324d2eaaffcbdae888', FALSE, 'NativeUI · RefreshShopMusicExpansion')
  , ('09223fd5f61ba258', 'client', 'Dragoman', '689010aa4282379f0479c0e024108c2a963ef5f7', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('e836f1d3f21f7e01', 'client', 'Duo', '3c5d9cd03387fb41a856eb94a3f12c1e7c45d2c1', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('366e5c083f800ce2', 'client', 'Duo -', '872a0ac7105096e62dc0d9a9342fd454369241b3', FALSE, 'NativeUI, PostSessionReport · OvtLine, OvtRecordHead')
  , ('d44b7e9515f5e841', 'client', 'Duo Leaderboard', 'bd67e561431b21dc42d2874a3fa3ff6248e3fa8a', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('25e3c84b4a5ba59f', 'client', 'Duo {0}W/{1}L', 'f9a96ae8d3343e98d3017e9bb5e94de28b0e57b9', FALSE, 'NativeUI, PostSessionReport · OvtLine, OvtRecordHead')
  , ('52093600fe30dfd9', 'client', 'Dupes ({0})', '1e2a44f50b0f610387848f8ed26580bfdea65ea4', FALSE, 'PlayerCardsUI · FillTile')
  , ('e15f7f445c46ae93', 'client', 'Dusk', '4db13aa08e06f68b46f6d3819cdb45cae2b882d0', FALSE, 'shop catalog · cosmetic name/description')
  , ('3367c75f1b297a7e', 'client', 'Dusky pink burning into crimson. Two-color gradient.', '58f3cb1034a175e1d3f0bb7523c2449f731a9bb3', FALSE, 'shop catalog · cosmetic name/description')
  , ('1d3249d2a988a709', 'client', 'Dusty rose blocks on a warm dim backdrop.', 'abc5f75a23c865711420044ed601217ae35bea54', FALSE, 'shop catalog · cosmetic name/description')
  , ('20db26c30c3100cb', 'client', 'Dusty rose fading into indigo night. Two-color gradient.', 'cd56cc98a81ff4372bfb6936afdb2fc3c63b2d7d', FALSE, 'shop catalog · cosmetic name/description')
  , ('5b6c67eb59c7ad5a', 'client', 'EDGE BOUNCE AND WALL-JUMP WINDOWS', 'b63228b8b8d05bc27009feeff1265e8eac3e82c1', FALSE, 'InfoViz · BuildMovementWindow')
  , ('11ba9036331b2f6c', 'client', 'ENTER - room code box / vanilla chat', 'c4d37600fe6a8b34ececbfffaf5ba84d5bfe876c', FALSE, 'InfoViz · BuildKeyboard')
  , ('2413a1bb101ca46e', 'client', 'EPIC', 'dce671445fe55498e4860075325f080bae63ecc7', FALSE, 'PcLabels · Tr')
  , ('9cbad68b903cfa8c', 'client', 'EPIC' || chr(4) || 'pc.band.epic', 'da04a5b9c26708d556c379c997aa6d5913671153', FALSE, 'PcLabels · Tr · pc.band.epic')
  , ('eea1dc710257f4e6', 'client', 'EPIC' || chr(4) || 'pc.band_short.epic', 'fbf2a1fde49e2073433f206024435d3ce5cf7ed0', FALSE, 'PcLabels · Tr · pc.band_short.epic')
  , ('530f0fe2b09f05af', 'client', 'EQUIP', 'df39fedad614b9e9ab0ed078f3d133f684213b7a', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('e8fffd61d2b123c0', 'client', 'ESC - closes this menu first, then the game menu', '77a406f15d46fbb8fcb9db489eb464c6e0c590cb', FALSE, 'InfoViz · BuildKeyboard')
  , ('92833989dbaa8f01', 'client', 'EVERY DAMAGE OUTCOME', 'f92fb4e35825d078ed1fa5f36d7802937cb12b13', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('6917a6295e2296eb', 'client', 'EVERYTHING TRAVELS THROUGH PHOTON', '32ef70ca2278f2060923c0806c0b9b46af7a2341', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('554216dc58af09c4', 'client', 'Each letter of your name in a different color of the rainbow.', '9b0acd4461ab7da7585950db970135db010f6aa8', FALSE, 'shop catalog · cosmetic name/description')
  , ('856fa04b654ab1e5', 'client', 'Each level costs more XP than the last (level^1.5). Every gold dot is a level-up: 100g each through 50, 500g after.', 'eab48914f0422378fab091ccee6ce862c737f5d4', TRUE, 'InfoViz · BuildXpCurve')
  , ('83bfe0b8abeedba6', 'client', 'Each pack holds {0} cards. A card''s rarity is its player''s rank in the card pool on the day of the pull: Legendary = #1-2, Epic #3-10, Rare #11-20, Uncommon #21-40, Common #41 and below. Odds per card: Common 60%, Uncommon 25%, Rare 11%, Epic 3.5%, Legendary 0.5%. Every card also rolls Foil (1 in 200) and Signed (1 in 2000) on its own.', 'b6319176d253732eb634c772cac7cf0e34e3fa78', FALSE, 'PlayerCardsUI · RefreshInfo')
  , ('cea03e78dc4b3f47', 'client', 'Each player''s worst ranked 1v1 opponents - minimum 3 series, top 5', '9d1ab2eac2466b4807b2f3d089264504bb335017', TRUE, 'NativeUI · BuildComparePlayerNemesisPanel')
  , ('8db61be6a2860732', 'client', 'Each seat simulates its own replicas. Damage is computed on the shooter''s seat and relayed as a final number.', 'da9ec544c59c98e53c9aaf2442e3d81d2725ec08', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('933131317eca7e8d', 'client', 'Each unlocks once per account and pays on the spot: most pay 100g; the hardest pay 300g, 500g or 1000g.', 'ed3b73cc402c48f39ce1b90ef1d8947bda12267d', FALSE, 'InfoViz · BuildAchievementTiers')
  , ('c0a8deb8d0150229', 'client', 'Eagle', '0af99bc6a304e3cb601d31ecdf545bbe6a663826', FALSE, 'shop catalog · cosmetic name/description')
  , ('983ceec9fb4ba169', 'client', 'Eagle God', '63366c94d864751eff0af10673f8af191c98af24', FALSE, 'shop catalog · cosmetic name/description')
  , ('23cdf680c45e8128', 'client', 'Eaglet', '178caa850bfe61fa77a4d6355f4da403154f9e7c', FALSE, 'shop catalog · cosmetic name/description')
  , ('d2e1c859dbdcdf34', 'client', 'Earned', '257f305b043a469cf483af28b88025aeffa6e98d', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('9edf2504e5a87159', 'client', 'Earned at {0}', '6e38c2b3005a58b9da79d154eef8accf9b09741a', FALSE, 'TitleLaddersUI · PaintTierRow, ReasonText')
  , ('d07b8c2b5af84abf', 'client', 'Earned by {0} player  <color=#888>(in the order they got it - click again to close)</color>', '92cfc28e94f00f9407f870995c85eeaf388a1e30', FALSE, 'NativeUI · RefreshAchievements')
  , ('f0dc3f4c961b805e', 'client', 'Earned by {0} players  <color=#888>(in the order they got it - click again to close)</color>', '09d9fbb99911bd6d0227907a47221c12a2db9ca4', FALSE, 'NativeUI · RefreshAchievements')
  , ('fdf9c5620b40fa13', 'client', 'Earned pack (ranked win)', '8e8496869a9cb9e917b73f59309257efa44ddcc5', TRUE, 'PlayerCardsUI · PackLabel')
  , ('1ae6c2bfc16d2223', 'client', 'Earned pack (sweep)', 'c7dff03c22aa9c1bb7f06dae59b8ddaff0e6f064', FALSE, 'PlayerCardsUI · PackLabel')
  , ('d1568a20c1c5c81f', 'client', 'Ears for those who feel very lucky', 'ecdbdbbb2c39fd700bb4ae334fd2615defb3172f', FALSE, 'shop catalog · cosmetic name/description')
  , ('75eccff6b3ce7be0', 'client', 'Earth Gradient', '8f963207651b6b17c88011cc9a1cf5016ff08143', FALSE, 'shop catalog · cosmetic name/description')
  , ('5f1ededf6306d873', 'client', 'Eats damage', '7efda4c6d275389b1bfd26f7a15ac191beb583c8', FALSE, 'shop catalog · cosmetic name/description')
  , ('fde511fb7c73ed95', 'client', 'Echo', 'e738c7d89afb7a9acb548496f7ce7ca8d6b2a2f0', FALSE, 'shop catalog · cosmetic name/description')
  , ('94289445357e1566', 'client', 'Echo main', '4899aea0ad7311f429c135299da2adc96ca17eda', FALSE, 'shop catalog · cosmetic name/description')
  , ('52eb10fe5a54bd85', 'client', 'Eclipse', '45fc6c80b5f40c599a9996e4565f6c3c0441f578', FALSE, 'shop catalog · cosmetic name/description')
  , ('9d675c20af88ac85', 'client', 'EdgeBounce NRE swallow', '29ff1525ee6fdd2e6fd0e55e379a4e224f5776e5', FALSE, 'NativeUI · PerfRowLabel')
  , ('c4c802689b1c1079', 'client', 'Edition', '64abb3cf155976521acc77ce8d45aaf1e951515d', FALSE, 'PcLabels, PlayerCardsUI · SortLabel, Tr')
  , ('86b1bea1dd26c1b7', 'client', 'Edition' || chr(4) || 'pc.edition', 'eed6a52319c26aaaaaf74374f3506231f7c2e963', FALSE, 'PcLabels · Tr · pc.edition')
  , ('47b4415f4d6a7d63', 'client', 'Effects', '8f25a859269ca51039632dd6bba28fb061cfb8d4', FALSE, 'NativeUI · (file scope)')
  , ('c3efc0344cbb6d00', 'client', 'Elder Turtle', '4cb096d8cdeff98d83662e1b2158a84cd721171c', FALSE, 'shop catalog · cosmetic name/description')
  , ('2b5b3a47fa9ab0b2', 'client', 'Electric sparks snap and dart around you.', 'b4ce3eb96421a2bc09e75479472c6baa5a0610ee', FALSE, 'shop catalog · cosmetic name/description')
  , ('c8a63c1732410b70', 'client', 'Electric-cyan neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', '9d2514d92ca9b022beab74865f8146bd878801be', FALSE, 'shop catalog · cosmetic name/description')
  , ('a1183962e39dafca', 'client', 'Elite Tracker', '63741cb7eabaad2cdd7fdb14c5214c58769ec588', FALSE, 'shop catalog · cosmetic name/description')
  , ('b29134ecca9d1209', 'client', 'Elo', 'b2bba6145b37e301dea598b4d23970ddc6e2f1a7', FALSE, 'NativeUI · TrMetric')
  , ('b272a9274980ddf9', 'client', 'Ember', '20632bc30721b7b1111cc82ebfe4420e4ad7d5d8', FALSE, 'shop catalog · cosmetic name/description')
  , ('2c2b83458da6e21e', 'client', 'Ember Gradient', '50b385ec12fd86912cc1c6ecc39e0abf1a282cca', FALSE, 'shop catalog · cosmetic name/description')
  , ('17623eac4b59b734', 'client', 'Embers', 'f95951bd6069d431a0a73fc47ac7e0d3e44e622b', FALSE, 'shop catalog · cosmetic name/description')
  , ('aabf3a6bbef39977', 'client', 'Emerald', 'da32ecab00cdd3a4cfccfe58a62338d64fbe94a2', FALSE, 'shop catalog · cosmetic name/description')
  , ('3273d686feea4e85', 'client', 'Emerald Glow', 'd84efbd1322c23b8b2a9cc87004e3c450ea13a8c', FALSE, 'shop catalog · cosmetic name/description')
  , ('9922fbe350152757', 'client', 'Emerald Gradient', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', FALSE, 'shop catalog · cosmetic name/description')
  , ('fe85ade52f92f64e', 'client', 'Emerald Name', '2c9dde1029ae34d4232e975c93a7a04067eb085b', FALSE, 'shop catalog · cosmetic name/description')
  , ('a643b528a858b30a', 'client', 'Emote dances for the hold-{0} wheel. Your character busts the move for everyone running the mod - but your own controls lock until the dance ends, so dance wisely.', '703e3963264dc8f179e8dfec4320bc9a27909d5b', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('b034a9fa0e06411f', 'client', 'Empower', '9d76f86189d7828fe6031fa3ec3a12f49ac925a8', FALSE, 'shop catalog · cosmetic name/description')
  , ('1fd64c1efd7d9083', 'client', 'Empty Power main', '83bdd3b5230da99776ea3b56316a89419519fbcf', FALSE, 'shop catalog · cosmetic name/description')
  , ('76fd56cb105bdb10', 'client', 'Enable', '20063ad9053289cecaa20ae630ed2dd758282a07', FALSE, 'NativeUI · BuildRankedRow')
  , ('8df13dd67b62c005', 'client', 'Enable Ranked first - the RLFP ping is for ranked matches.', 'feb0e5bf902bee5c1c71b9014353f7717948e8d0', TRUE, 'ApiClient · SendLfpPing')
  , ('abc6658a7ca5808b', 'client', 'End', 'a2bb9d34b8a1a79665858d354585cf147e0dee4e', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('c20b8a9de411169d', 'client', 'End Alert...', '05ccca75986b9d013eae70af4841312e1a408f2e', FALSE, 'NativeUI · BuildAdminTab')
  , ('04af4b0b1909b0cb', 'client', 'Energy Orbs', 'a13f4b9bac07d2b398f39f962a4e6e6f64ec7afb', FALSE, 'shop catalog · cosmetic name/description')
  , ('11e75bf0cc1f9f07', 'client', 'English', '649df08a448ee3fa90f3746baaf6b0907df42c91', FALSE, 'CompetitiveUI, NativeUI · ChannelDisplayLabel, ChatChannelDisplayName, OpenChatTypingPicker +1')
  , ('3dd84ae90274fdaf', 'client', 'Enter a denial reason first.', 'a5432a4a6da4ff9019bded83cad12076454c3412', FALSE, 'CompetitiveUI · DrawCosmeticReview')
  , ('ba17468c6b466990', 'client', 'Enter a whole number from 1 to 2000 gold for this bet.', '597fe2e793459992f591bb2fffb5da571a767476', TRUE, 'NativeUI · SubmitCustomBet')
  , ('0688bed8d4269036', 'client', 'Epic', 'b3efd0d2dd507ba6211015b1bc8119629dd74e05', FALSE, 'PlayerCardsUI · RarityLabel')
  , ('582670124134c55f', 'client', 'Equip', 'd764961a0190b30c20bb741496306ead9a1ea719', FALSE, 'NativeUI · ApplyShopRow')
  , ('8b3fe56d26e70e2e', 'client', 'Esc cancels', '929c06f48ce655fb2da2c764edbdcf32b09d2067', FALSE, 'NativeUI.Keybinds · KeybindRenderPane')
  , ('99aaf3856364684b', 'client', 'Escape', 'b4cfe1f435f06beaae8e7d7c6d43e5dddbe640bb', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('69df762b04945155', 'client', 'Evergreen forest at dusk.', '747064df7c49f0b13a9bb661d6209045ec2e3fdd', FALSE, 'shop catalog · cosmetic name/description')
  , ('349d25e29566b115', 'client', 'Every finished game pays XP, XP converts to Gold at 100 XP = 1 Gold, and ranked play multiplies the base rewards below by your opponent''s rank tier. This is the pay table - exact numbers, mode by mode. (Tournament podium prizes are separate; see <color=#7FD4FF>Deadlines & forfeits</color>.)

<color=#FFD94D><b>THE TIER MULTIPLIER</b></color>

In ranked play, base rewards are multiplied by the OPPONENT''S rank tier - <color=#7FE87F>win or lose. Playing up always pays.</color>

<color=#7FD4FF>Beginner</color> (under 1500) - x1.0
<color=#7FD4FF>Intermediate</color> (1500 or more) - x1.5
<color=#7FD4FF>Advanced</color> (1675 or more) - x2.0
<color=#7FD4FF>Master</color> (1980 or more) - x2.5
<color=#7FD4FF>Grand Master</color> (2330 or more) - x3.0

It applies to XP and to series Gold, and an opponent with no rating on record counts as 1500 (x1.5). Which rating is ''the opponent''s'': their 1v1 rating in 1v1, the opposing team''s average 2v2 rating in 2v2, the opposing seat''s average 1v1 rating in 1v2, and your opponents'' average FFA rating in FFA.

<color=#FFD94D><b>1v1</b></color>

Per game, multipliers stack, then the total truncates to a whole number:

- Base <color=#7FE87F>250 XP</color> per finished game, casual included.
- Game win: x1.5. Ranked: x1.5. Opponent tier: x1.0 to x3.0 (ranked only).
- A shutout win (opponent on 0 rounds) adds +100 XP flat, after the multipliers.

Exact examples: casual loss 250, casual win 375; ranked loss vs a Beginner 375; ranked win vs a Beginner 562, vs an Intermediate 843, vs a Grand Master 1687 (+100 more if 5-0).

Series Gold, ranked BO3 only - casual play creates no series and pays none:

- Loser: 5 x opponent tier, truncated. Winner: double that.
- Winner doubles AGAIN if the beaten player currently sits in the leaderboard top 3.
- +2 flat on top for a 2-0 sweep.
- Winner/loser by opponent tier, before podium and sweep: Beginner 10/5, Intermediate 14/7, Advanced 20/10, Master 24/12, Grand Master 30/15.

<color=#FFD94D><b>2v2</b></color>

- Per game: 600 XP x the opposing team''s tier, then x1.5 if your team won the game.
- Default all-1500 lobby: 900 XP for a loss, 1350 for a win.
- Series Gold: 50 (each winner) or 25 (each loser), x the opposing team''s tier. Default lobby: 75/37.

<color=#FFD94D><b>1v2</b></color>

Base 500 XP per game, x1.5 on a win, then a per-seat difficulty multiplier:

- Solo seat: x1.5.
- Solo playing WITHOUT the extra-pick handicap: another x1.20.
- Duo seats facing a buffed solo (extra pick on): x1.10.
- Opponent tier, read from the opposing seat''s average 1v1 rating - 1v2 has no rating of its own.
- Opponent currently in the 1v2 leaderboard top 3: x1.35, win or lose.
- The whole product is capped at x4.0; the x1.5 win bonus applies on top of the cap.

Defaults with extra pick on: the solo earns 1125 XP for a loss and 1687 for a win; each duo member 825/1237.

Series Gold: 40 (winning side) or 20 (losing side), x opponent tier only - the seat, handicap and podium factors live on XP. Default: 60/30.

<color=#FFD94D><b>FFA - THE METER</b></color>

FFA pays for FIGHTING, not for time in the lobby. The formula, in readable form:

- The work unit is <color=#7FD4FF>battles</color>: every decisive round scored by anyone in the game. <color=#FF6666>Camping adds nothing to the pool</color>, and the last-place cut it earns is the smallest share of what everyone else generated.
- A pace ceiling caps how fast battles cash in. For a lobby of P players, one battle is expected about every 3.08 + 6.54 x P seconds (P counted as at least 3 and at most 6 here), and the game pays at most TWICE that pace across the game''s elapsed time on the server''s clock - stalling or point-farming cannot outrun it.
- The base rate is 3.5 Gold per player-minute, +5% for every player above 4. A 10-player FFA is the best Gold rate in the game.
- Placement shapes your cut of the pool: 1st place earns 1.666x the lobby average, last place 0.334x - about a 5x spread. Players sharing a place share the same cut.
- A stronger field multiplies the pot: your opponents'' average tier divided by 1.5, so a default 1500 field is exactly x1.0. Casual lobbies take the bottom factor (about x0.667) and never touch ratings.
- The pool is a Gold amount. 55% pays directly as Placement Gold (minimum 1). The other 45% pays as XP at 100 XP per point of pool (minimum 50 XP), which drips back as Gold through the normal conversion.
- Placement itself sorts by points, then all round wins earned (spent ones included), then kills where the lobby''s kill tiebreak is active; remaining ties share a place.
- Ghosts and graced early leavers are unrated and receive no game Gold or XP from that game: leaving before the field scored four half points in total, whether or not any became a full point, takes you out of those results. A graced leaver can still earn achievements, which pay as usual, but an unrated game earns no title-ladder progress.

<color=#FFD94D><b>LEVELS AND THE XP-TO-GOLD DRIP</b></color>

- XP converts at <color=#7FE87F>100 XP = 1 Gold</color>, paid every time your running total crosses a hundred mark. Every mode''s XP - tournament prizes included - feeds the same total.
- Climbing into level L costs 100 x L^1.5 XP, truncated: level 2 costs 282, level 5 costs 1118, level 10 costs 3162, level 50 costs 35355, level 100 costs 100000. Max level is 100.
- Entering a multiple-of-5 level pays bonus Gold: <color=#7FE87F>100g for levels 5 through 50, 500g for 55 through 100</color> - 6000g lifetime if you reach the cap. It lands the moment any XP award dings the level - any mode, tournament prizes included; a ding during an FFA game shows up inside that game''s +g number.

<color=#FFD94D><b>ACHIEVEMENT GOLD</b></color>

Every achievement pays <color=#7FE87F>100g</color> unless listed here:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Grand Master (reach 2330), Touch Grass, Babel.
- <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, Rise from the Ashes, Casual Conqueror, Twins!, Immortal, Hostile Takeover, Bodycount, Sync Champion, Async Champion.
- <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, Into the Deep End, Century Club, Unstoppable, Party Crasher, Heartbreak, Dragoman, Sync Finalist, Async Finalist.

The FFA shutouts nest: one 5-0 win with 5 players finishing pays Clean House (100g) + Party Crasher (300g) + Hostile Takeover (500g) in a single game. The translator achievements (Rosetta, Dragoman, Babel) trigger at 10, 100 and 1000 approved live strings.

<color=#8A8A93>Outside matches: Discord server boosters are paid 2000g monthly, and community artists earn a 30% royalty (rounded down to whole Gold) when another player buys their item - gifts pay none.</color>', '24d45ca20cdf6517f97db0d6c36a2defadd87817', TRUE, 'InfoLibrary · (file scope)')
  , ('325b2f12f56594dd', 'client', 'Every game you play with the mod runs the same pipeline: every modded client watches the match, one of them files the report, and the server decides what it counts for. This page covers how a game gets classified and reported. For what each stat actually measures, see <color=#7FD4FF>How stats are tracked</color>.

<color=#FFD94D><b>WHAT MAKES A GAME COMPETITIVE</b></color>

- Rooms the mod creates itself are consented by definition - queueing up IS your consent. The ranked queue, 2v2 and tournaments play rated; ranked FFA lobbies rate their games while casual ones don''t; 1v2 records without rating.
- A private room-code game is ranked only when three things are all true: <color=#7FE87F>your Ranked toggle is on, your opponent runs the mod, and their Ranked setting is on too</color>. The mod recognizes a modded opponent by the presence data their client publishes into the room; a vanilla player has none.
- Your client asks the server whether the opponent has Ranked enabled, and keeps re-checking for a while after they join - a player who launched their game seconds ago can briefly look unranked.
- As soon as a ranked pairing is confirmed, the client registers the series with the server, so the score HUD and the bets panel work from game 1.
- If either side has Ranked off, the server answers ''not ranked'', your client flips the game to casual, and you get one toast per room saying so.
- The server re-checks everything again when the report lands. A mid-series toggle can''t void a best-of-3 that''s already running, and a game reported as casual gets upgraded to ranked when the server can see both players are modded, both consented, and the sitting is live. An opponent who has never run the mod can never be upgraded - genuine quickplay stays casual forever. (A live unfinished series from an earlier sitting is the one thing that keeps ranked status across a gap.)

<color=#FFD94D><b>WHO SENDS THE REPORT</b></color>

- One client reports each game: the player with the numerically LOWER Steam ID. Both clients apply the same rule, so they almost never race - and if a rare early-room edge makes both send, the server keeps exactly one. Against a vanilla opponent the modded player always reports - nobody else can.
- 2v2 elects the lowest Steam ID of the four, 1v2 the lowest of three, and FFA the lowest among players still PRESENT at game over (a leaver can''t report).
- In 1v1, if the elected reporter crashes or leaves, the survivor takes over and the disconnect rules decide the result; FFA simply elects among whoever is still present (see <color=#7FD4FF>When a game counts</color>).
- The server enforces one-report-per-game on its side too: nothing ever records or pays twice, and a duplicate send is either answered with the already-recorded result or set aside.

<color=#FFD94D><b>WHAT IS IN A REPORT</b></color>

- The result: both sides'' rounds and points, match duration, region, and a per-game room id.
- Cards: every pick with its round and pick order, plus - for the reporting player - what they were offered and passed on. Your offers only ever come from your own client, never your opponent''s.
- Combat stats: bullets fired and hit, block attempts and successes, damage dealt, and (in 1v1) deaths with how they happened.
- Timelines for the graphs: FPS, ping, hit/block progress and damage, sampled every few seconds across the whole game. (1v2 carries a lighter set for now.)
- Connection health (fullest in 1v1): frame freezes, network silence gaps, and whether the opponent''s live updates stalled.
- A snapshot of every player''s final build, taken at game over before anything can wipe it.
- Input pacing: how many gameplay keys and clicks you pressed while alive in combat. Counting covers only the movement, fire and block keys, runs only during active combat, and stops while you''re typing in any chat or have the menu open.
- <color=#7FE87F>The core result is SIGNED by the reporting client</color>, so it can''t be altered in transit and a random program can''t forge one. The stat telemetry rides outside the signature and is treated as advisory - useful data, never proof.

<color=#FFD94D><b>WHAT THE OTHER CLIENT DOES</b></color>

- The non-reporter runs the whole game-over pipeline too - achievements, session tallies, its own stat capture. It just doesn''t send the match.
- During the match, both clients publish their live stats to each other through the room every few seconds. That''s how the report carries YOUR fired/hit/block numbers when your opponent is the one filing it.
- Only the reporter''s client sees the server''s response, which is why the XP toast and the series score land on one screen first.

<color=#FFD94D><b>CASUAL GAMES ARE RECORDED TOO</b></color>

- A casual 1v1 writes the same full match row as a ranked one: score, cards, duration, all the telemetry.
- Both players earn XP - base 250, x1.5 for a win, +100 for a 5-0 sweep - and XP converts to gold at the usual 100 XP = 1 gold. Casual win-streak achievements count too.
- What casual never touches: no series, no rating change, no bets, no ranked leave %.
- A vanilla opponent gets a stats page auto-created from the report. <color=#7FE87F>They keep pure vanilla gameplay, and the only part of the mod they can ever see is nametag styling</color> (see <color=#7FD4FF>What unmodded players see</color>).', 'f9da8a515f187b04c3b8e3e1499e4fd62bec8b7a', TRUE, 'InfoLibrary · (file scope)')
  , ('e3b65fff831bda23', 'client', 'Every mark is one tick of damage. A well-timed block erases the 1-2 ticks inside its window.', 'ab92d11f5f3ed5e802b7409a9fe778e877afb9a7', FALSE, 'InfoViz · BuildDotTimeline')
  , ('ffd0bcba80bcba7d', 'client', 'Every ranked mode scores you with Glicko-2: a rating, plus a measure of how sure the system is about it. This page explains what the numbers mean, why they move the way they do, when each mode updates, and the full rank ladder.

<color=#FFD94D><b>THE THREE NUMBERS</b></color>

<color=#7FD4FF>Rating</color> - the skill estimate. Everyone starts at 1500. There is no floor and no ceiling anywhere; your peak is tracked per mode.
<color=#7FD4FF>RD (rating deviation)</color> - how uncertain the estimate is. A brand-new account starts at 350. RD shrinks every time you play - the more you play, the surer the system gets.
<color=#7FD4FF>Volatility</color> - how erratic your results have been. Starts at 0.06 and adjusts on its own as results come in.

The size of a rating move scales with YOUR RD. That is why new accounts swing hard - their first results move them a lot - while a veteran''s results move them a little at a time. Playing more games is the only thing that settles it.

<color=#FFD94D><b>WHY GAINS AND LOSSES AREN''T EQUAL</b></color>

Before scoring a result, the system computes your expected result from the rating gap. Your change is proportional to the difference between what happened and what was expected:

- Beat a much lower-rated player and you gain almost nothing - the win was expected. Lose to them and you pay heavily.
- Beat a higher-rated player and you take the big side of the same trade.
- The opponent''s RD matters too: results against uncertain (high-RD) opponents are dampened. Beating a well-established account moves your rating more than beating a fresh unknown one.

<color=#FFD94D><b>WHEN RATINGS MOVE</b></color>

Each mode keeps its own fully separate Glicko rating. Nothing you do in one mode ever moves another mode''s number.

- <color=#7FD4FF>1v1</color> - updates when the series completes (first to 2 game wins). The whole series counts as ONE win or loss observation: a 2-0 and a 2-1 move your rating identically.
- <color=#7FD4FF>2v2</color> - updates when the series completes. You are scored against BOTH opposing players. A series decided by a disconnect applies full ratings, the same as a played-out one.
- <color=#7FD4FF>FFA</color> - updates after every single game, when its report lands.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>unrated beta. No rating moves at all.</color> Games are recorded and can count later when ranked 1v2 launches.

Casual games never touch any rating.

<color=#FFD94D><b>HOW FFA SCORES A LOBBY</b></color>

A 10-player game is not treated as 9 separate duels - that would swing your rating several times harder than a 3-player game. Instead:

- You are compared against at most 4 opponents: the ones placed NEAREST to you.
- One extra ''upset'' comparison can join them: the biggest 250-plus rating gap that finished upside down outside those picks. One per game, however many upsets happened.
- Each comparison scores as a win if you placed above them, a loss if below, and <color=#7FE87F>a shared place counts as a draw</color>.
- Short games weigh less: a first-to-3 counts as half a game, the default first-to-5 counts fully, and longer targets never count as more than one game.

<color=#FFD94D><b>THE 2v2 TRUST RULE</b></color>

Your 2v2 rating starts as a guess, so the matchmaker doesn''t trust it right away:

- Team balancing uses your 2v2 rating once you have 10 completed series, OR once its RD has converged to 110 or below.
- Until then, your 1v1 rating stands in.
- The leaderboard''s Avg Mate Elo column trusts a teammate''s 2v2 rating after 5 completed series; before that it uses their 1v1 rating, or 1500 if they have none.

<color=#FFD94D><b>THE RANK LADDER</b></color>

Five tiers, each split into rungs I to V - V is the top of its tier. The number is the floor: you hold a rung at or above that rating.

- <color=#7FD4FF>Grand Master</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Master</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Advanced</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Intermediate</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Beginner</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Reaching 1980 (Master) or 2330 (Grand Master) in ranked 1v1 or 2v2 also grants the matching achievement - FFA rating does not trigger these. Discord rank roles follow your 1v1 rating, and the Current Rank shop title always renders your live rank name in its tier color. Your opponent''s tier also multiplies your match rewards (see <color=#7FD4FF>XP, Gold & levels</color>).', '7092efd0e1c1a7263fce0c81c6c69b2e65a70b3e', TRUE, 'InfoLibrary · (file scope)')
  , ('c612c77fc68ea0c9', 'client', 'Every tournament runs through Discord DMs from the SCR bot. None of them reach you unless your Discord is linked (F5, Discord Link tab). The big notices (lock, match live, results) are durable - if the bot is down when one fires, it retries until your DM lands. The play-day nudges (starts-in-15, next-up, waiting-on-you) are best-effort and can be missed across a bot restart.

<color=#FFD94D><b>BEFORE THE TOURNAMENT</b></color>

<color=#7FD4FF>Availability check</color> - sent 1 to 4 days before lock, once the tournament has enough players. Two buttons:
- ''Yes, I''m in'' - edits the message to a confirmation. It changes nothing on the server; you were already signed up.
- ''No, remove me'' - removes your signup, exactly like un-signing in game. No penalty.

<color=#7FD4FF>Lock DM</color> - you''re in. Sync: your start time plus the contract (have ROUNDS open at that time). Async: how to coordinate and play. If the server last saw you on an old mod version, an update warning is appended - update before you play. No buttons.

<color=#7FD4FF>Removed at lock</color> (sync) - the field agreed on a time you didn''t mark as available, so your signup was removed. No penalty; sign up again next week.

If the lock pushes back a week instead (too few players, or no time slot 8 players agree on), a fresh availability check goes out for the new date.

<color=#FFD94D><b>SYNC PLAY DAY</b></color>

<color=#7FD4FF>Starts in 15 minutes</color> - open ROUNDS now and sit at the main menu; the mod does the rest. Also posted in the tournament channel.

<color=#7FD4FF>Match ready</color> - your match vs X is ready, get in ROUNDS now. <color=#FF6666>A no-show forfeits in a few minutes.</color>

<color=#7FD4FF>Next up</color> (rounds 2 and later) - your next opponent and start time after a short breather, no rush. Want to play right away? You BOTH press Play Now on the F5 Tournaments tab.

<color=#7FD4FF>Waiting on you</color> - sent when your ready match is under 90 seconds from its no-show deadline, or sitting past it while you''re marked present. It means: get to the ROUNDS main menu and leave any casual game. Repeats at most every 5 minutes.

<color=#FFD94D><b>ASYNC MATCHES</b></color>

<color=#7FD4FF>Match is live</color> - your opponent, the 7-day deadline, and how to play: agree a time, host a private lobby together, the result records automatically.

<color=#7FD4FF>Still pending</color> - once your match has sat ready for 3 days unplayed, a daily reminder with your deadline and how to coordinate. No buttons.

<color=#7FD4FF>Deadline check-in</color> - sent in the final 24 hours before your deadline. Three buttons, and your latest answer replaces earlier ones:
- ''Yes - we plan to play today'' - recorded, and <color=#7FE87F>extends the deadline 24 hours</color> - once per opponent per tournament. Pressing it a second time records the answer but the deadline stays put.
- ''I reached out - no response / they quit'' - recorded.
- ''Not yet - still coordinating'' - recorded.

What an answer is worth: if the deadline passes with the match undecided and neither player ahead, <color=#7FE87F>a player who answered the check-in - any of the three answers - beats a player who stayed silent.</color> The full resolution order is in <color=#7FD4FF>Deadlines & forfeits</color>. Buttons re-check that your Discord is still linked to the same account before acting.

<color=#FFD94D><b>RESULTS</b></color>

After each match, both sides get a completion DM that''s honest about how it ended: a played win says you won; a forfeit says ''You advance - your opponent forfeited''; a mutual no-show says ''You advance on the no-show tiebreak''. A forfeit is never dressed up as a played win.

When the bracket completes, the podium is announced in the tournament channel. Trophy roles are handed out only for brackets of 16 or more players; smaller brackets keep their prizes and achievements but hand out no Discord roles.

<color=#FFD94D><b>COMMANDS AND THE BOARD</b></color>

<color=#7FD4FF>/dm-opponent</color> followed by your message - the bot relays it to your current tournament opponent''s DMs. Limited to 8 messages per minute.

<color=#7FD4FF>/opp-online</color> - checks whether your tournament opponent currently shows as online on Discord.

The tournament channel keeps a living board for both tournament kinds, refreshed every 2 minutes.', '78efcc153076dcd201fc27282452c0dd0c62e4f9', TRUE, 'InfoLibrary · (file scope)')
  , ('d538750901232607', 'client', 'Everyone else left the FFA — returning to menu.', '6416f89b4cb8bed2c6328f06cd044dcce9ff4570', FALSE, 'FfaMode · CheckRoundAfterLeave')
  , ('cb7ebf1fcc9cbffa', 'client', 'Everyone starts at 1500. Higher tiers multiply series gold; each band splits into sub-tiers V to I.', '046dcf45ba01218e7d000fd0a8a3914ae591c6ea', TRUE, 'InfoViz · BuildRankLadder')
  , ('31d3f2a1c4e5d101', 'client', 'Everyone starts somewhere.', '2ded2d6e7d0c2c2df38250fac32026e3469bedad', FALSE, 'shop catalog · cosmetic name/description')
  , ('de022e1f770c414f', 'client', 'Everything you leave behind turns gold.', '12a0d60f9f881a3edc74172253daa3ce062126af', TRUE, 'shop catalog · cosmetic name/description')
  , ('d41f9e623a3e7d3f', 'client', 'Expanded', '6d1704748e0c4f2e48ce24e2a2e0ada0a61ae03e', FALSE, 'NativeUI.Settings · SettingsRenderPane')
  , ('a6f688596c6d950c', 'client', 'Expands the senders you have blocked. It is the only place a block can be lifted, and unblocking takes effect for the next message that sender writes.', 'fa4ef40ade9175a06fc24a0e5acbba729b93f886', FALSE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('4260c37897eb1915', 'client', 'Expands the seven individual performance patches. The count beside the row is how many are active, and the master switch above flips all seven at once.', '35f0a8cc505f60241b3e474bcd8bd601d3431e70', FALSE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('67c04e155d92e2fb', 'client', 'Expert', 'd7a501f83242fd940b8190529432e0703dd7606f', FALSE, 'shop catalog · cosmetic name/description')
  , ('5f6829eb55fa6b8c', 'client', 'Expires in {0}', '51704cc87553884cafe367493619214d279ec7f3', FALSE, 'PlayerCardsUI · FillTradeRow, RefreshCompose')
  , ('09d89a5ed17a5b36', 'client', 'Export Tier List', '0f2ac9fc2d0300baafc50eda99f1f68f115de3a9', FALSE, 'NativeUI · BuildCardStatsTab')
  , ('8c163ff612da1396', 'client', 'Export already in progress...', '5f2a2412b0200b7ae35472be066b50595ea708b3', FALSE, 'NativeUI · ExportCardTierList')
  , ('63de85fe69fad87c', 'client', 'Extra motion over the fight. Turn it on when you want to read exactly what a trade cost.', '52f713c1669e7f7f74d777099b2ca7419db84fe6', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('f8722c358b268c6e', 'client', 'Eye-watering hot-pink body color.', '16b52078a6f08d64300bd48fcb78dec76756adbb', FALSE, 'shop catalog · cosmetic name/description')
  , ('d463ba4d3fe6c730', 'client', 'Eyes for those who are burning for a true battle', '2bc4f5879207567e69e8be799e9c265524714089', FALSE, 'shop catalog · cosmetic name/description')
  , ('d84d735748f37ad0', 'client', 'Eyes for those who feel fiendish', '5c143e75d051c3859764af514e48c9912cbe519b', FALSE, 'shop catalog · cosmetic name/description')
  , ('fc3938fd7d5cb881', 'client', 'Eyes: big round eyes with lashes and a bright shine. Equip in the Character editor.', 'fbe1ede71827fb410b99766ea2b95427ac0cf366', FALSE, 'shop catalog · cosmetic name/description')
  , ('14315d8bfdc142da', 'client', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', '42004fbbdfdd9e28f20bc7b40b8340b1016a8473', FALSE, 'shop catalog · cosmetic name/description')
  , ('0f34e682111c0d18', 'client', 'Eyes: golden stars. Equip in the Character editor.', '0ac81439129159c9c49e680faf69be65fb6d761d', TRUE, 'shop catalog · cosmetic name/description')
  , ('b8c027d3e3a34c81', 'client', 'Eyes: lovestruck hearts. Equip in the Character editor.', '2684f8c6647a0ec56162173475a06b2700f4688d', FALSE, 'shop catalog · cosmetic name/description')
  , ('e42386b34c3621f5', 'client', 'Eyes: red and yellow goggles marked with the radiation symbol. Equip in the Character editor.', '8cd24e52796e469a743d22f56bced5b9849c4901', FALSE, 'shop catalog · cosmetic name/description')
  , ('b2523664f38026af', 'client', 'Eyes: two green curves for calm, closed eyes. Equip in the Character editor.', '8b337be2a435986197baf2d8f2ff61e6f9dccdb4', FALSE, 'shop catalog · cosmetic name/description')
  , ('cc710817d6431fa6', 'client', 'F5 stays on the menu control.', '1a2139886b9f4ea17acd19c217ff5330cf49846d', FALSE, 'NativeUI.Keybinds · KeybindRefusalText')
  , ('62ce5181e5a602ca', 'client', 'FFA', '90ce5340a6531dab9e5c720670abf91bb7d42fc4', FALSE, 'InfoLibrary, NativeUI, PlayerCardsUI +2 · (file scope), KindLabel, ModeLabel +1')
  , ('ac7fc61d4452be7b', 'client', 'FFA (placed above / below)', '87f5c954be7baafdb07f9e51044d333702d933d1', FALSE, 'ProfileCard · Render')
  , ('d820383e18f33ceb', 'client', 'FFA - How It Works', 'bc6c4123d4239b8e45bc714df9bdbcd2cfadd872', FALSE, 'ModeInfoText · (file scope)')
  , ('d14df263eb7a220f', 'client', 'FFA - {0} players - first to {1} points!', '67a5c91fdef543bcdf7b7bdc9f5efedaee64ff1b', FALSE, 'FfaMode · FfaDoStartGame')
  , ('c5e1da03052cc027', 'client', 'FFA Average Kills per Game', 'b245fe34c71ef357ff38fa3da3be5ff787482568', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('c68ef3507d15e173', 'client', 'FFA Average Placement (lower is better)', '0be14823081a2c5dc92e44eb3082c4f996504ae1', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('e3abcd5edb274ed5', 'client', 'FFA Avg Kills', '9d050af1c4807da1efe90831e72c93ef6cea41fe', FALSE, 'NativeUI · TrMetric')
  , ('f59a6c6967acba5c', 'client', 'FFA Avg Placement', '8ccdb6e6b11f321d1e82ca9cd4db9f53fdf278d4', FALSE, 'NativeUI · TrMetric')
  , ('496970286b950065', 'client', 'FFA DPS', '757933a26349a81ff9017db9c2dc2688f5cfbe68', FALSE, 'NativeUI · TrMetric')
  , ('058a47753c6c57cf', 'client', 'FFA Damage per Second', 'd2cf10297a9ca4f2e86691018da78380fc281085', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('4f1e57957913d56d', 'client', 'FFA Elo', '477b094b85e09367aa6ff21fad7719819b83e85d', FALSE, 'NativeUI · TrMetric')
  , ('73b4e1fa08ae8958', 'client', 'FFA Podium', 'a75329613f268c94057ba2625c7b2e2c8af204ea', FALSE, 'shop catalog · cosmetic name/description')
  , ('e46943688b727f28', 'client', 'FFA STARTING IN {0}...', '3b64921f2960bf7a10b9e3f462af56594d56d312', FALSE, 'CompetitiveUI · RefreshFfaPickBanner')
  , ('f2ee58084f8d02ee', 'client', 'FFA VICTORY!', '72a3946768a62051739daf64745f3fda6a9e9294', FALSE, 'GameStateWatcher · OnFfaGameOver')
  , ('da7931ad7df4a64a', 'client', 'FFA VICTORY! +{0}xp', '16bc5bdd632da2ad2fd7bce2af52ce21d3809eb5', FALSE, 'ApiClient · ReportFfaMatch')
  , ('b805204de1dc17d6', 'client', 'FFA cancelled - not enough players for a fresh game.', 'a926b4d61bf2b690aff0b07a8b6c41bdebdde9c9', FALSE, 'FfaMode · CheckRoundAfterLeave')
  , ('41371036864d76c5', 'client', 'FFA games', '7e45cc8c4037f981e655aac54372fe576c73f315', FALSE, 'InfoViz · BuildGoldSourcesLegend, GoldBucketName')
  , ('76839b71857b49bc', 'client', 'FFA lobby never filled — returning to menu. Requeue when ready.', 'c87f9c252d42a96f48c508b0dad1d7cb197bbf27', FALSE, 'GameStateWatcher · PollRoomState')
  , ('7dcb9d52c481ee91', 'client', 'FFA match found, but you''re in a game — removed from the FFA queue.', '6d3d0e01344b51cfabdd664eec29029841a4dffd', FALSE, 'ApiClient · UpdateFfaQueuePoll')
  , ('dd2c6e3580f06ba9', 'client', 'FFA over - you placed #{0}', 'e6384934ceab9f4abf62d3bbd335e11e565e1d6c', FALSE, 'GameStateWatcher · OnFfaGameOver')
  , ('c60b3fb177ffdaaa', 'client', 'FFA session - {0} players', 'b59bfaaceed86fdb77668457fd1267dc817f3da0', FALSE, 'PostSessionReport · ComposeFfa')
  , ('9503cca363369365', 'client', 'FFA session - {0} players, {1} games', 'f374c265a0669927968583a277fce4434415e7ee', FALSE, 'PostSessionReport · ComposeFfa')
  , ('da364c22af80c86d', 'client', 'FFA: placed #{0} (+{1}xp)', '514a72f6e0de5d80e678c0de5bd652d724192627', FALSE, 'ApiClient · ReportFfaMatch')
  , ('f8cfffdbc154226a', 'client', 'FFA: your tally is kept and scored from your exit under the early-leave rules.', '97f13afb5db03819911341e5b7e782561f069219', FALSE, 'EscLeaveRow · OnRowClicked')
  , ('59d5f91f485fde0b', 'client', 'FIRE', 'f4a67a405292506090849df3bad2937271b56298', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('5dd21d2b1effe3ed', 'client', 'FIRST TO {0}   -   {1} OPENING DRAW   -   {2}-CARD HAND', '37ec0acb9e53c4780bc0c0fe2454681fee5cab89', FALSE, 'FfaMode · OnGameStart')
  , ('ef416e27d17769c6', 'client', 'FIRST TO {0}   -   {1} OPENING DRAWS   -   {2}-CARD HAND', '3473dbe7c23ff2a47b4c0db0213ea2c31730da1d', FALSE, 'FfaMode · OnGameStart')
  , ('3ceb575bb104e67a', 'client', 'FLAG', 'aaabc04650aab77b47f331f4aacd9649ab02c710', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('649b3b30b87875e3', 'client', 'FOIL', '02749eebae9f0a7b1679630fcb84af868b941097', FALSE, 'PcLabels, PlayerCardsUI · MarkLine, Tr')
  , ('85ff474cabe20ad3', 'client', 'FOIL' || chr(4) || 'pc.foil', '4632486f77e4ab459297e5d49f1c235d80047692', FALSE, 'PcLabels · Tr · pc.foil')
  , ('584f4917d5df1c58', 'client', 'FOIL' || chr(4) || 'pc.foil_short', '1e27318a27ee9acb822df5c779316904fdcf2709', FALSE, 'PcLabels · Tr · pc.foil_short')
  , ('6b2353195492bb8f', 'client', 'FPS', 'fce204ae554cd5820b35e0ae8653db07910f77d5', FALSE, 'PostSessionReport, SessionReportModel · Build, BuildCells1v1, BuildCells2v2Game +1')
  , ('3859fd8d26c1bd89', 'client', 'FPS counter: <color=#88FF88>ON</color>', '43ba37bd870c8bada62d152083999e8646000ca0', FALSE, 'NativeUI · PaintShowFps')
  , ('5fb50f8fc41b94e9', 'client', 'FPS counter: <color=#FF9966>OFF</color>', 'e1ebe8c3f2f26102477a3f062945ebe18bf2ef2d', FALSE, 'NativeUI · PaintShowFps')
  , ('f216e0f569dc9d78', 'client', 'FULL', 'cc0a745dcfb4d3d66417f75affb8f4b428e7e18f', FALSE, 'NativeUI · LevelWordTr')
  , ('e9d2426ce52ddf48', 'client', 'Faced by', '68ba0f7e976a1c577ac93fb93ab0080fae538776', FALSE, 'NativeUI · BuildCompareNemesisPanel')
  , ('cdac92171e43b9bf', 'client', 'Fade Gradient', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', FALSE, 'shop catalog · cosmetic name/description')
  , ('bc030c06fe5a0335', 'client', 'Failed: {0}', '40fc0b8e623cda2ad22b652d0c886c5580af6837', FALSE, 'CompetitiveUI, NativeUI · BugReportFailureStatus, CreateShopRow, ShowArtistResult')
  , ('2028fedb1737cd34', 'client', 'False', '97cdbdc7feff827efb082a6b6dd2727237cd49fd', FALSE, 'InfoViz · SeqTable, SeqText')
  , ('13f971fc00113015', 'client', 'Fast Forward', 'fbb62b29a3ec00fab22b016af1b1896dab9d6aae', FALSE, 'shop catalog · cosmetic name/description')
  , ('ed148bb9c7be8e8c', 'client', 'Fast Forward main', 'fabb304f63738fae1d8b8290dfa48d39166bd688', FALSE, 'shop catalog · cosmetic name/description')
  , ('1ac50717539486a6', 'client', 'Fast finisher', '142cf28bcdc25525a041a6fdec70244bd7f34e83', FALSE, 'shop catalog · cosmetic name/description')
  , ('b6e11fb2bbb5eace', 'client', 'Fastball', '6deae48055ba8b71974518cb9932923c56e79021', FALSE, 'shop catalog · cosmetic name/description')
  , ('59bf3e91608fa618', 'client', 'Favorite ranked cards', '367483822a4e8f99275ed1daad31fe06fda784e9', TRUE, 'PostSessionReport · ComposePlayerPanel1v1, ComposePlayerPanelCompact')
  , ('6a77c5ad69934952', 'client', 'Few reach it. Fewer afford the title.', '9727f8a805db983c5d5372d96d511ce90094cbe2', FALSE, 'shop catalog · cosmetic name/description')
  , ('c332f8d24db253b1', 'client', 'Field Medic', '9c456cc81aecc69b660c85dcac67dc9de04f91cf', FALSE, 'ApiClient · AchievementDefs')
  , ('cbbd6cba81661aea', 'client', 'Final score', 'ddcd5e6fa8ad7a0e5f51e691708d1fa17a7f062d', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('1fb3492a1e86afb9', 'client', 'Fine', '226d7ec9afb2799e267e4c2c03be0ec2da38f4fc', FALSE, 'shop catalog · cosmetic name/description')
  , ('330d515b831a2877', 'client', 'Finish a game with the exact same 5 cards (and copies) as your opponent', '4731820fcd676f537c7e098544de7386184f7324', FALSE, 'ApiClient · AchievementDefs')
  , ('9d4b0c7cd2d8e0ec', 'client', 'Finish or leave your current game before joining the 1v2 queue.', '53a962a3ba05b581c9979e4983949df4258c0026', FALSE, 'ApiClient · OvtJoinQueue')
  , ('47f317fc0868a03f', 'client', 'Finish or leave your current game before joining the FFA queue.', '339670b58cfcb9b061922b19ad0c9fe1970a63c2', FALSE, 'ApiClient · FfaJoinQueue')
  , ('7f3d1d82b2323384', 'client', 'Finish or leave your current game first.', 'c500c2a4bc293add3f1d785c1db705e7095ad87c', FALSE, 'ApiClient · ActionPreflight, FfaLobbyActionPreflight')
  , ('052b546b4bb6c1b4', 'client', 'Finishing your previous leave first...', 'e5d1c56766741a3ff30884a7b6e5ab1f402dc14e', FALSE, 'ApiClient · BlocksOnPendingLeave, JoinTeamQueue, OvtJoinQueue')
  , ('f7a22af2b0e1e50b', 'client', 'Fireflies', 'b6ab482e980abd109633aac2a2d069bcc17bedda', FALSE, 'shop catalog · cosmetic name/description')
  , ('8e4b8e030f8326f7', 'client', 'Fires your gun.', '70537eda6482cdcd6d7ef40038a661dbeb46716b', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('3e80c6f347f80c54', 'client', 'First bloods', '09d89d166cb62c90f61565ca485d669880d60e14', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('c9e4dc142533d543', 'client', 'First played today · H2H {0}-{1} · Ranked series {2}', 'ce9fc34778b41ce8ab57abb9ce88121448338b54', TRUE, 'H2HSummary · BuildLine')
  , ('08c937803617523a', 'client', 'First time playing {0}', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', FALSE, 'H2HSummary · BuildLine')
  , ('2267d5721109f6dc', 'client', 'First to:', '88c0562022ffeb4ef8821335d8fa3e20823550a1', FALSE, 'NativeUI · BuildFfaTab')
  , ('98e3859cbd3ba125', 'client', 'Flag marked as confirmed.', '6d56e1c35678ccc6ae1324012172bb5876774aa4', FALSE, 'CompetitiveUI · SubmitFlagEvidenceVerdict')
  , ('fe7a4ade88f61c42', 'client', 'Flag marked false positive.', '66640520cbee31c09da657ee2488012ccc40f1c5', FALSE, 'CompetitiveUI · SubmitFlagEvidenceVerdict')
  , ('fe35b612219f0afc', 'client', 'Flagged Matches', 'a2e6462d89b355f988344af13d5467d6bd4d10b3', FALSE, 'NativeUI · BuildAdminTab')
  , ('a0b809cf10f75d41', 'client', 'Flair text shown next to your name on the leaderboard, match history, and in chat.', '692f254e30158dac89e251017eaff0948bcc4bf7', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('43b2f69fc34f5d0d', 'client', 'Flame Crest', 'cdc31cb72e817957694d9471984bd835a93dafc1', FALSE, 'shop catalog · cosmetic name/description')
  , ('53dc540a825baa09', 'client', 'Flawless', '22b9ee43aaa645b2356c82a81cf4f411e51328e8', FALSE, 'ApiClient · AchievementDefs')
  , ('4d0ae42a5167a39c', 'client', 'Floating Name', '455a8cfec6c15aa9f024bd2cb4d2dd92bafc3c6d', FALSE, 'shop catalog · cosmetic name/description')
  , ('baf0279dbad7565f', 'client', 'Floating numbers above a player showing damage taken and health received, using the same decimals as the HP readout. Local display only — nothing you see here is sent, and nothing changes for anyone else in the room.', 'b67fef8cb2f99487eb1341f1c9c72f83e79dc1ea', FALSE, 'NativeUI · BuildSettingsTab')
  , ('857d64183e061d3e', 'client', 'Floating pink hearts rise from your body.', '6c741cc15dd127d0473f2b78bab3176ede8c2057', FALSE, 'shop catalog · cosmetic name/description')
  , ('cd1d26e10fab576b', 'client', 'FloraBelle', '12676290b1175bac07e40fd0daa0676737556821', FALSE, 'shop catalog · cosmetic name/description')
  , ('a37a0bfe15ff4654', 'client', 'Follow my character', '08fcdd22fef005bade0be4b5d42c8cf4f26f62df', FALSE, 'PlayerCardsUI · PresetLabel')
  , ('0aff582e300474d4', 'client', 'For sale', '8c2e0e1d55b890163a0578eee7d56dc9a8163f4e', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('7c8d1536eb0fd36a', 'client', 'For the silly ones. Takes up the mouth slot', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', FALSE, 'shop catalog · cosmetic name/description')
  , ('faad0c987e1f8490', 'client', 'For those who earned the right. Still costs a fortune.', 'c6b8dfc0f49980b4284e35414a755c6e2d0fa5f9', FALSE, 'shop catalog · cosmetic name/description')
  , ('57458ad5ed088b18', 'client', 'Force Start', '2b653211244b09239b9e1d00d3de5a10b288a0dd', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('3482219b5141fa38', 'client', 'Force exit room', 'bc90b7b7a0f89810a21b4c074f2a6a74152ea24e', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('26f48ec14590c3ae', 'client', 'Force your name to render uppercase.', '6038950c3ffe7f90843135db324457e4fa5b86b1', FALSE, 'shop catalog · cosmetic name/description')
  , ('37e3bb991b9d0230', 'client', 'Force-start unlocks at {0} signups ({1}/{2})', '3f93069046dd262e169342cd220aa004644ab861', FALSE, 'NativeUI · RefreshTournaments')
  , ('acbb2acd18c65dd7', 'client', 'Force-start votes: {0}/{1}', '86bb334f8ed2d24e6c396de77e5ca2c7be2bb490', FALSE, 'NativeUI · RefreshTournaments')
  , ('c8b11f4b97ff6849', 'client', 'Forest', 'f41c4e4dab0b44d75dad0c04a0156d326c95b774', FALSE, 'shop catalog · cosmetic name/description')
  , ('8586bec2443a2aa0', 'client', 'Forest Fire', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', FALSE, 'shop catalog · cosmetic name/description')
  , ('29dd7d7b1c852928', 'client', 'Forfeit', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', TRUE, 'NativeUI · BuildTournamentsTab, OnForfeitClicked, RefreshTournaments')
  , ('d1136733b5c62c42', 'client', 'Forfeit failed', '22333d4dfcca347a29c73248ab2e93e9930e41be', TRUE, 'ApiClient · TournamentForfeit')
  , ('df07898130ca13ef', 'client', 'Forfeit recorded - the match will be resolved shortly.', '012cc72f181623655f86f1ab4b06654ca4412740', TRUE, 'ApiClient · TournamentForfeit')
  , ('b15125b18510d0d4', 'client', 'Forty-Niner', '7e301b56fe98bc4cd7f536d442c291595be59b2a', FALSE, 'shop catalog · cosmetic name/description')
  , ('4e17aa7c25efb66c', 'client', 'Fragile Perfection', '93c0c7428061d19b5ae907ba7820e19445811f4b', FALSE, 'ApiClient · AchievementDefs')
  , ('0a51b869b20517e8', 'client', 'Frames per second, top-left corner. Handy for checking whether a setting actually helped.', 'f14bfe467e47f12a5514df9247ea036e5251f589', FALSE, 'NativeUI · BuildSettingsTab')
  , ('4c9883d62dfac8a4', 'client', 'Free daily pack', '20857a1450ee43d15638d38ef18b1b7590e2f2ec', FALSE, 'PlayerCardsUI · PackLabel')
  , ('c2356579ce07992c', 'client', 'Free pack', '7c349cc8db0789b761f4ce7a7f37062803720885', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('a1252ecd0e4537db', 'client', 'Free-for-all for 3-10 players. Every player is their own team.
Standard ROUNDS scoring - first to {0} points takes the game.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- There is no Elo band. Joining a lobby is consent to play.

- Create a lobby, or join an open one from the browser.
  The HOST presses Start once at least 3 players are in
  (up to 10). Several lobbies can be open at once.

- If the host leaves, the longest-waiting member becomes
  the new host automatically.

- After each point, everyone except the point winner
  picks a card at the same time.

- The pick timer is shown on screen. A pick landing
  near the end grants everyone a little extra time.
  When your timer hits zero, your highlighted card is
  picked for you automatically - walking away never
  skips your pick. Only a pick that misses the window
  entirely (a freeze, a crash, or the final split
  second) yields no card, with a toast saying so.

- You hold up to {1} cards.
  Picking one more replaces your oldest card.

<color=#FFD94D><b>HOST SETTINGS</b></color>

- The host can tune the lobby before starting: score
  target (3-10), opening draws, cards offered per
  draw (1-5), max cards held (3-5 ranked, up to 6
  casual), the Same Cards rule, and ranked/casual.

- Same Cards rule: everyone''s Nth card draw offers the
  SAME candidates, in the same order - if you and a rival
  were offered identical cards all game, no result can be
  blamed on draw luck. One-copy cards (like Phoenix)
  appear at most once per game for everyone.

- After a settings change the lobby cannot start for 60
  seconds (and briefly after someone new joins), so
  everyone can read what changed. Casual lobbies pay
  reduced rewards and never touch ratings.

<color=#FFD94D><b>RATING</b></color>

- FFA is ranked with its own Glicko rating.

- Placement uses points, then all round wins earned
  (spent ones included), then kills.
  Remaining ties share a place using competition
  order: 1, 2, 2, 4.

- Your rating is scored against the players placed
  nearest to you (up to 4 of them), so one game can''t
  swing your rating several times harder in a 10-player
  lobby than in a 3-player one. One extra comparison
  can join those four: the biggest 250+ rating gap
  that finished upside down outside them.

- A tied placement counts as a draw. New ratings move
  fast and settle down as you play more.

<color=#FFD94D><b>REWARDS</b></color>

- Pay is metered on the FIGHTING, not on flat per-game
  numbers: decisive rounds are the work unit, and
  elapsed time caps how fast they cash in - stall
  tactics are held to a bounded edge, and longer,
  bigger games pay more.

- Bigger lobbies pay a better rate per minute, and a
  10-player FFA is the best gold rate in the game.

- Your placement shapes your share: 1st earns about
  five times last place''s cut. Part pays as XP, part as
  Placement Gold, and a stronger opposing field
  multiplies the pot (the usual tier bonus).

- XP converts to Gold at 100 XP = 1 Gold, and level-ups
  pay their usual bonus Gold. A level-up landing during
  a game shows up inside that game''s +g number - that is
  how a last place can occasionally out-earn the winner.

- Spectators can bet Gold on FFA lobbies from this tab.

<color=#FFD94D><b>READING THE RECENT FFAS LIST</b></color>

<color=#7FD4FF>Dots + N(P)</color> - Full points won.
<color=#7FD4FF>Half dots + N(H)</color> - Round wins that
  did not become one of that player''s full points.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - That game''s XP and Gold
  (including any level-up bonus).
<color=#7FD4FF>Green/red number</color> - FFA rating change.
<color=#7FD4FF>Cards</color> - The hand held at game end.
  <color=#FF6666>+N replaced</color> counts picks that were
  pushed out by the card cap - hover the line to see
  every pick in order.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player''s display name.
<color=#7FD4FF>Rating</color> - The player''s separate FFA Glicko rating.
<color=#7FD4FF>Games</color> - Recorded FFA games played.
<color=#7FD4FF>Wins</color> - Games finished in 1st place.
<color=#7FD4FF>Top3</color> - Games finished in 1st, 2nd, or 3rd.
<color=#7FD4FF>AvgPl</color> - Average finishing place. Lower is
  better - 1.0 means winning every game.
<color=#7FD4FF>WR</color> - Share of games won outright.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded. A leaver keeps their
  tallies and is placed and rated for the game they
  left - unless they left before the field had scored
  four half points in total, whether or not any became
  a full point, in which case that game does not rate
  them or pay them game Gold or XP. Achievements can
  still be earned and pay as usual, but an unrated game
  earns no title-ladder progress.', '2f6ee754bd3e7ed0d9e2726956982d05b5ba6e9d', TRUE, 'ModeInfoText · (file scope)')
  , ('2292fa557a2dbb7f', 'client', 'Friendly fire off', '7ea6168c9a6bbb3eaf2bfb323ffaafcb139ba11b', FALSE, 'RoomRules · Summary')
  , ('3614bc3931db4efc', 'client', 'Friendly fire: OFF', 'cf9480db8e8c2876ba28d063370b05d566cd0c94', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('5fa0ddf519965bae', 'client', 'Friendly fire: ON', '95314bdacf481fc08c63c06cefb478be2fb1ee02', FALSE, 'NativeUI · BuildOneVTwoTab, BuildTeamTab, RenderHostLobbySection')
  , ('12d8e5794670fd7a', 'client', 'From the Ashes', '54bc9883934917a2f66acf487cda856ecc184dae', FALSE, 'shop catalog · cosmetic name/description')
  , ('f72488c19efdac04', 'client', 'From the art of the "Healing Field" card', '8be4bf379229e1042e85793249e4608bdaa255c8', FALSE, 'shop catalog · cosmetic name/description')
  , ('d8662fcfc1055c2e', 'client', 'From {0}', '957db23d1cf5f7a8e6e0f9303c094fb2d73e7450', FALSE, 'PlayerCardsUI · FillTradeRow, RecentLine')
  , ('44b5d154e10fd438', 'client', 'From:', 'c4d63e4c56f1d2b74aaf3de1c3943ce348748d84', FALSE, 'MailUI · PaintReader')
  , ('280a08e85e79e12d', 'client', 'Frost', '6032a672e309a4dfd10a6c41199d5fd8c5c83da9', FALSE, 'shop catalog · cosmetic name/description')
  , ('91af34b15810dcd7', 'client', 'Full log...', 'b13b4fc382a1c06e5100ffce87362532289efdb2', FALSE, 'NativeUI · BuildAdminTab')
  , ('8b17e8b203c35266', 'client', 'Full music albums that replace ROUNDS'' combat soundtrack for you. Click an album row for 30-second track previews; after buying, pick tracks and control playback in the Music tab.', '090784407ecb4e04e63455bbe866f5a003ad9f06', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('b6c259ff73599f88', 'client', 'GAME ENDS', '256eaeedbdddb39dbb730009c35d8a52e25f9a61', FALSE, 'InfoViz · BuildWhenCounts')
  , ('aa96a51a1e9af834', 'client', 'GAMEPLAY', '9905006070eedb6ae48e11bb4b977e1ba02955c6', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('3083d95d9140b745', 'client', 'GET READY - fire and block unlock in a moment', 'f4711dbd478dfa86591adfa28c7b9e2552cee2a3', FALSE, 'CompetitiveUI · RefreshFfaPickBanner')
  , ('b2f1a988f7ecdbf8', 'client', 'GF Reset R{0}', '123da08d65f7c893b82e9c65606eeb56da8148cc', TRUE, 'NativeUI · TrBracketProgress')
  , ('34bbcff53ca66d33', 'client', 'GF R{0}', '7a93677aea86e0f41bd338fc45e93cc1a0426c20', FALSE, 'NativeUI · TrBracketProgress')
  , ('8553615797a7e5de', 'client', 'GIF decoded inconsistently ({0} of {1} frames) — re-export it and try again.', '12e85820e4ea1cdea9c71b9619dee24f53c3cc2e', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b7c98550c2e00f83', 'client', 'GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at least {5} ms and re-export; the server will not change the speed for you.', '74f51dab050e6c373e3f078dd2b376f44cc0022f', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('9b4bf8174a1eef61', 'client', 'GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at most {5} ms and re-export; the server will not change the speed for you.', 'd13c6edc6a1c751da572e50c7d3308590c61edb3', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('dc6e2ac2d009a3b0', 'client', 'GIF frames are {0}x{1} — the limit is 2048x2048', '504f27880d01e739e1144d8eee64982f89f9a7f4', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('15cc327c80f95402', 'client', 'GIF has more than {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).', '694383c8e21f1a3632deb4fb7941b82308ea2780', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('0772e38deb558b45', 'client', 'GIF has no transparent background — export it with transparency, or the cosmetic renders as a solid square.', 'ccaa267c54f5cc3509ebbbc3ca67fab31ae4e9c4', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('76ae28e6448bf332', 'client', 'GIF has {0} frame(s) — an animation needs at least 2. Upload a PNG instead for static art.', 'e9979ad8837839979d6df76579683510c616ce16', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5ce7bd5177af91a8', 'client', 'GIF has {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).', '96f484ccbe1e58a8c7500d23e3bca68c3f39f0c0', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('c7b3bcf195a82c78', 'client', 'GIF is missing', '7085e9e05779eac328664ac92ecaa39b298d9704', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1646fd302b1bd012', 'client', 'GIF is {0} KB — the limit is {1} KB. Reduce the frame size or the number of colours and re-export.', 'f14409696f7f7ec6f43dba12e4ff157392a37f1b', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('d77eb2ed30c92497', 'client', 'GRAND FINAL', '8f0a822b86368ce0db1e0c6a787e4c03742f7b35', FALSE, 'InfoViz · BuildBracketFlow')
  , ('f0879faeb75eb0b1', 'client', 'Galaxy', 'f69ff6e8d889fd11305a1035f80d7cfb42c367f0', FALSE, 'shop catalog · cosmetic name/description')
  , ('9234ccf14b5a0045', 'client', 'Galaxy Gradient', 'bf317bc7c73647140d56b21fbf2329d373e385cd', FALSE, 'shop catalog · cosmetic name/description')
  , ('1880d7803c54ac9d', 'client', 'Game', 'e3e82846c32567811615378f30240185871e08e5', FALSE, 'InfoViz · BuildSeriesFormat')
  , ('79a0762ddaf41128', 'client', 'Game ?', 'd9cc3dc4f2aba64784ee730953c68b885afbe01c', FALSE, 'NativeUI · BuildFfaRecentRowText')
  , ('d4e55c6cad6429ea', 'client', 'Game Mechanics', '1fae01eacc86b66836f084c259bcb7a1700793cb', FALSE, 'InfoLibrary · (file scope)')
  , ('bc9b426a0d7a49d7', 'client', 'Game controls', '311c1de28c51cbd98c97b26ee8e037468cdaad9f', FALSE, 'NativeUI.Keybinds · BuildControlsRows')
  , ('d6ec0c9d961e72d5', 'client', 'Game ended', 'd7ec44f4c92285665f002aa0a4b0c476feb8854a', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('25566d90088f276d', 'client', 'Game lengths', '3a81b618c84adf1bc847c3d06f3bf4a58150b5e2', FALSE, 'SessionReportView · DrawStrip')
  , ('31223dfc8f728453', 'client', 'Game over - {0} wins', 'e7a9b89520887cc20a44255e10e1c0a8a9123dc2', FALSE, 'SpectatorSync · PlayPointSequence')
  , ('750ea46af3406a48', 'client', 'Game records (all players) - hover a row for the cards', '9011a22ca77f975c297198dbbb4f2d1601f5a538', FALSE, 'NativeUI · BuildCompareRecordsPanel')
  , ('7b0dc0b4d08487af', 'client', 'Game {0}', '70016b079c5047ff972d699f67163ceeabf3ab5f', FALSE, 'NativeUI, PostSessionReport, SessionReportModel · BuildBracketHoverBody, BuildFfaRecentRowText, BuildOvtRecentRowText +4')
  , ('12a2ee7e09002750', 'client', 'Game {0}   {1} players', '60067c6a686e7a3821f641d7c33e0dc78179d882', FALSE, 'PostSessionReport · ComposeFfa')
  , ('ea1f96e30b6c6737', 'client', 'Game {0}   {1} {2} {3}', '5153f35507471943f8acdcfbb27f18b027db8af7', FALSE, 'PostSessionReport · BuildCells1v1')
  , ('e5afdc07523f8396', 'client', 'Game {0} - {1} players', '0b9ce69dc04eeb6c6027497ff1dc0da1030da5d2', FALSE, 'NativeUI · RenderFfaBettingSection')
  , ('5e81bd40584c6595', 'client', 'Game {0} of {1}', '9cd9695a45e379418c16dcc5de49b46e70c6eed5', FALSE, 'SessionReportModel · BuildsRange')
  , ('fd8d7e51279627ed', 'client', 'Game {0} score progression', '4200a0fa64073d825b8861ad95ee0536180ae1f7', FALSE, 'NativeUI · ParseFfaTimeline')
  , ('e02a47417843ba5d', 'client', 'Game {0}: solo {1}-{2} duo', '5da06bf7bb67a08a9073612752a6c656a5720b5c', FALSE, 'SessionReportModel · TeamScoreLabel')
  , ('80f0534cf1f71ba0', 'client', 'Game {0}: team 1 {1}-{2} team 2', '158534c6676ad9aedfbcacf43b97f8809a97e71d', FALSE, 'SessionReportModel · TeamScoreLabel')
  , ('d1f566a9226d07e1', 'client', 'Game {0}: {1}', 'a3143c792dd243b332d5946a9630efa050cfb0e8', FALSE, 'SessionReportModel · BlockHeader, FfaScoreLabel')
  , ('5c9bcb043b857bb2', 'client', 'Game {0}: {1}-{2}', 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', FALSE, 'PostSessionReport · Compose2v2')
  , ('fff10c9a1a7ab76e', 'client', 'Games', '398ed329814977519b9f899253338884a2ba941f', FALSE, 'NativeUI, SessionReportModel · BuildFfaTab, BuildTotalsPages, RefreshFfaTab')
  , ('697e96dc1565ba5f', 'client', 'Games {0}-{1} of {2}', '642808bcd184630004f9dc9a7fb3e491e7eb776a', FALSE, 'SessionReportModel · BuildsRange')
  , ('b43c450431d13f59', 'client', 'Gentle soap bubbles float up around you.', 'f75572ef86d5cfaece368a57351d584911134e8e', FALSE, 'shop catalog · cosmetic name/description')
  , ('39617d899fccdbad', 'client', 'Get 10 translations approved (yours, or ones you reviewed)', '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', FALSE, 'ApiClient · AchievementDefs')
  , ('dcc82a2b178d2cf1', 'client', 'Get 100 translations approved (yours, or ones you reviewed)', 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', FALSE, 'ApiClient · AchievementDefs')
  , ('15d202c6a4014604', 'client', 'Get 1000 translations approved (yours, or ones you reviewed)', '3da5563a1b208c34fb55b011341811074297bc21', FALSE, 'ApiClient · AchievementDefs')
  , ('1605fe375cfc39fe', 'client', 'Get 5 copies of one card in a game', '76eda7d248ecf2792fc4875e7baac32b49a2cd96', FALSE, 'ApiClient · AchievementDefs')
  , ('b2afe4968bcc4aa7', 'client', 'Get Link Code', '120606dcac1a829f37539d9af0708360d5453e69', FALSE, 'NativeUI · BuildHomeTab')
  , ('713349054ad238c7', 'client', 'Get over 100 kills in a single ranked FFA', '68c08456174ff352b83fd491248983caedf0563b', TRUE, 'ApiClient · AchievementDefs')
  , ('1fa81a239870be31', 'client', 'Get over 50 kills in a single ranked FFA', '358a314e30b7cdc651b30425ab046442b4e2e9d7', TRUE, 'ApiClient · AchievementDefs')
  , ('75fd9a71e82d0e55', 'client', 'Get packs', '4ea833d2aad959ea4d0a5cac39f93f0ed45cdfbc', FALSE, 'PlayerCardsUI · BuildInto')
  , ('17359b8ec6399a4a', 'client', 'Getting better', 'ba3b5585c9b14b2966768e5003f9dabd61b2ba22', FALSE, 'InfoLibrary · (file scope)')
  , ('600d50be0343e7f0', 'client', 'Getting better at competitive ROUNDS is mechanical, not mystical: blocking discipline, netcode awareness, drafting, and reading the numbers the mod already keeps on you. Every tip below is tied to a real mechanic you can go test.

<color=#FFD94D><b>BLOCKING DISCIPLINE</b></color>

Blocking is the skill that decides close games, and it has a cost model worth respecting.

- A block that absorbs nothing still spends its full cooldown. <color=#FF6666>Panic-blocking at the sound of a trigger buys you nothing and hands your opponent a free window while it recharges.</color>
- React to the bullet, not the trigger: watch the opponent''s gun and the shot itself, and drill on-reaction blocks until they''re reflex.
- One activation can absorb several bullets. A block held for a burst or a bounced volley does far more work than one spent on a lone pellet.
- Block-effect cards multiply timing skill: Echo repeats and Shield Charge dashes all belong to the block that started them, so one well-timed block fires the whole chain.
- A poison or burn tick that lands inside your block is consumed - erased, not postponed - so blocking while poisoned is real damage prevention. <color=#8A8A93>(A room mixing current and outdated mod versions can fall back to poison ignoring blocks, for everyone equally - see <color=#7FD4FF>Vanilla stays vanilla</color>.)</color>

<color=#FFD94D><b>PLAY WITH THE NETCODE</b></color>

- ROUNDS is not peer-to-peer. Both players talk to a Photon relay server in the room''s region; the orange player is not a host and has no host advantage. <color=#7FE87F>Your ping to the region is the number that matters.</color>
- Every client simulates every bullet, and damage is shooter-authoritative: what a shot takes off you is decided on the shooter''s machine. Their screen sees your movement late, which is why you can die a step after reaching cover - and why the player who peeks first sees the other before being seen.
- Your block is the mirror image: it happens on your machine first and reaches the opponent''s simulation a beat later. A block raised slightly early on reaction protects you in situations where a frame-perfect one does not, because your last frame is already the past on their screen.
- What reads as a broken hitbox is almost always this mismatch: ping, interpolation, size cards, and bounced shots. The mod never touches hitboxes (see <color=#7FD4FF>Netcode & Photon</color>).
- Frame rate is a hidden gameplay stat in vanilla ROUNDS. Vanilla Grow compounds its damage per frame: around x9.4 for a 60 FPS shooter against x1.4 at 400 FPS for a single copy, and stacking widens the gap fast. In mod rooms - and in private matches where everyone is modded, current, and has Ranked enabled - Grow is normalized so frame rate stops deciding the damage (a heavy stutter can still under-grow a little - the error only ever points down); against vanilla or outdated clients the vanilla rule stands. <color=#7FE87F>A stable frame rate is a real competitive edge</color> - the Settings tab has a performance section for exactly this.

<color=#FFD94D><b>DRAFT FOR A BUILD</b></color>

- Cards are a plan, not a stat sheet. Lifesteal heals off the damage-dealt chain, and damage-over-time ticks route through that same chain - lifesteal plus poison is an engine, not a coincidence. Echo and Shield Charge turn blocking skill into offense. Draft the second card for the first one.
- Read what a card actually does, then test it. Card text and card behavior are separate things: Chase displayed a ''+30% Health'' line for years that the vanilla card never actually granted (the mod removed the line). Sandbox games are never recorded, so experiment freely there.
- The FFA Same Cards rule is the best draft teacher in the mod: when it''s on, everyone''s Nth draw offers the same candidates in the same order, so a loss can''t be blamed on draw luck - the difference was choices. The Recent FFAs list keeps every pick in pick order (hover a player''s card line), so you can replay the winner''s draft against yours.
- Your 1v1 match history stores both players'' picks in order for every game. After a close loss, re-read the draft before you re-queue.

<color=#FFD94D><b>USE YOUR OWN NUMBERS</b></color>

My Stats tracks more about your play than you probably realize. What the headline stats mean:

- <color=#7FD4FF>Hit %</color> - counts bullets, not clicks: one Buckshot click counts every pellet, and only direct, unblocked hits on enemies count - poison and burn ticks, explosions and self-hits never do. A shotgun build reads low by construction. <color=#FF6666>Compare a build against itself over time, never against a sniper''s number.</color>
- <color=#7FD4FF>Block success</color> - one off-cooldown block is one attempt, and at most one success per attempt no matter how many bullets it absorbed. Preemptive blocks that meet no bullet are normal, not a mistake - watch the trend across games, not one game.
- Timeline graphs sample every 3 to 5 seconds and always span the whole game. Use them to find where games turn: the score timeline shows when a lead slipped, and the hit and damage lines show what changed when it did.
- A 1v1 game records average and worst ping plus freeze events (frame stalls over half a second); team and FFA games carry lighter connection data. Before blaming your aim for one bad game, check whether the connection numbers already explain it (see <color=#7FD4FF>How stats are tracked</color>).

<color=#FFD94D><b>WATCH BETTER PLAYERS</b></color>

- Live games on the Leaderboard tab carry a WATCH button when they''re spectatable. A spectator seat shows the real match from inside the room, and how a top player spends blocks and drafts under pressure teaches faster than queueing blind. FFA lobbies can be watched from the FFA tab the same way.
- The Discord bot answers mechanics questions with live data: ask it ''how does blocking work'', or ask how much elo you''d gain against a named player and it computes the real Glicko preview for both sides, win probability included (both accounts need linked Discord).', '719fd4b7ace537c9e9463cd2bb3045f7f5d451dd', TRUE, 'InfoLibrary · (file scope)')
  , ('8e5062f3dfe20e9a', 'client', 'Gift', '8d0a32ed63390771166c129d77e7019ed5faf21b', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('49f54b769f831d85', 'client', 'Gifted', '7e1e863c271feae27da33fc702d797697314a93b', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('ed2d10114d8fa1c7', 'client', 'Gilded', '109fe33ee568cdbfcc2bccb3d5667edb0cfcc4a9', FALSE, 'shop catalog · cosmetic name/description')
  , ('e195217b8dd18c80', 'client', 'GitHub', '5442e2b64fa09764b9f593867e59a97292c84059', FALSE, 'NativeUI · BuildPage')
  , ('bf972197bededb7f', 'client', 'Given', '6839d82e03f5268d9a7cc97802db76c48c8cce6e', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('c470426e6955e200', 'client', 'Glicko-2 Rating', 'fe7f3ff2587e3d130e5d52db5004c675ee655866', FALSE, 'NativeUI · BuildMyStatsTab')
  , ('8de6c27992aeba7b', 'client', 'Glossy volcanic-black body color.', 'acbaf66b3f491443e004f29007d7da47b05d138d', FALSE, 'shop catalog · cosmetic name/description')
  , ('be2399036371a377', 'client', 'Glow (bloom): <color={0}>{1}</color>', '73a2014a6c0b4134cdd1bfd287bf0685a71ec92e', FALSE, 'NativeUI · PaintBloom')
  , ('a68b1f17c3436d85', 'client', 'Glow (bloom): the soft halo around bright cosmetics, map art and effects. Reduced = smaller, dimmer halo. Off = no halo. Local only — nothing is hidden, the cosmetic itself still renders the same. A few items have their glow painted into the artwork, and that part stays.', 'a632ac0544d4b5dea727409a10ffa2a23c246da0', FALSE, 'NativeUI · BuildSettingsTab')
  , ('8516a2f129517456', 'client', 'Glow Yellow', 'db4c6e762d551cdd15ce81da6fa4d2916ee2c8e3', FALSE, 'shop catalog · cosmetic name/description')
  , ('3e6d65a6be5e46d4', 'client', 'Glowing fire embers crackle and rise.', '4f7ba9d9a46c7284d51a3dc4e628fabb3acec15c', FALSE, 'shop catalog · cosmetic name/description')
  , ('41261dfa6845c60f', 'client', 'Glowing magenta body color.', '0c0de17323ea7ac0e7c27b2c1521765db1278f0d', FALSE, 'shop catalog · cosmetic name/description')
  , ('0e8218c38e24e14a', 'client', 'Glowing magenta neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', '4ccdeb2b81cdab9d1fe2c4707b86bb05059e0f20', FALSE, 'shop catalog · cosmetic name/description')
  , ('077676d0bca7cfb9', 'client', 'God Build', '6dd2206f0985f5762623cca9ed3d8e1a74aa684b', FALSE, 'ApiClient · AchievementDefs')
  , ('a36511ec6cccf2af', 'client', 'Gold', 'c57604db5869f60539c66f7caa4809f27133d314', TRUE, 'NativeUI, shop catalog · BuildAchievementsTab, BuildLeaderboardTab, BuildTeamTab +3')
  , ('6c8b90ec9540ad5e', 'client', 'Gold Name', '72fdf7b43d255bfca709ad5b2f17f4c501334a6b', TRUE, 'shop catalog · cosmetic name/description')
  , ('97942a8f53fc4975', 'client', 'Gold Rush', '9a0b8f00e52aa6ef22f75bdde822f385375b6671', TRUE, 'shop catalog · cosmetic name/description')
  , ('b4e0e0eaa97ba3d2', 'client', 'Gold Sources', 'e8a08aa75e862bc78c2d3eb56e21e2a04e8a45ba', TRUE, 'NativeUI · TrMetric')
  , ('c5596757a88ea76b', 'client', 'Gold betting runs on live 1v1, 2v2 and FFA games. This page covers who can bet, how the odds are priced, exactly when windows open and close, and what happens to your stake.

<color=#FFD94D><b>WHO CAN BET</b></color>

- Any registered player, staking 1 to 2000 Gold per bet. The stake is taken the moment the bet is placed.
- You cannot bet on a match or lobby you are playing in, and banned players cannot bet.
- <color=#7FE87F>Spectators CAN bet.</color> That is safe by design: the windows below close on early scoring, so watching a game never gets you a bet on a result that is already decided.
- One bet per series in 1v1 and 2v2; one bet per game in FFA.
- If any participant runs a mod older than 1.38.1, betting on that game is refused. Older clients cannot report live points, so the scoring cutoff could never fire - <color=#FF6666>the system fails closed rather than leave a window open.</color>
- A linked Discord account can place the same bets through the bot''s commands.

<color=#FFD94D><b>ODDS: 1v1 AND 2v2</b></color>

- Your multiplier is 1 divided by your side''s win chance, computed from both sides'' ratings AND their RD (see <color=#7FD4FF>Ratings (Glicko-2)</color>). Floor: 1.01x.
- Uncertainty caps the price. With both sides established (RD 100 or below) the multiplier can reach 3.0x; the cap slides down to 1.0x as the higher RD rises to 300. A fresh account at RD 350 caps the price below the 1.10x acceptance gate - <color=#FF6666>an unknown simply can''t be bet on, so a smurf can''t be farmed for Gold.</color>
- A side only accepts bets at 1.10x or better; below that it is locked.
- 2v2 prices off the pair''s average rating. A player''s own 2v2 rating counts once they have 10 completed series; before that their 1v1 rating stands in.

<color=#FFD94D><b>ODDS: FFA</b></color>

- The server races every player to the lobby''s score target and computes your pick''s true chance of banking it first. Your multiplier is half of the fair price - the house keeps the other half.
- Floors: 2.0x in lobbies of 5 or more, 1.4x at 3-4 players. For heavy favourites the floor gives way to 0.95 divided by their win chance, so a guaranteed-profit bet cannot exist.
- Cap: 5.0x, or half the lobby size if that is lower, and it shrinks when ratings are uncertain.
- A player with no FFA games yet is priced off their 1v1 rating at full uncertainty.

<color=#FFD94D><b>WHEN BETS OPEN AND CLOSE</b></color>

The cutoff is scored points, never a clock:

- <color=#7FD4FF>1v1 and 2v2</color> - open from the moment the series exists. Closed once 2 total points are scored in game 1, or the moment any game of the series is decided. Tournament series stay listed through the whole multi-day wait before the pair actually plays.
- <color=#7FD4FF>FFA</color> - each bet targets the lobby''s NEXT game. The window closes when the field scores 2 points in that game (1 point if the lobby''s score target is 3 or lower). A lobby is only listed while a next game is plausible: up to 15 minutes while assembling with no games yet, and up to 30 minutes after its last recorded game. <color=#FF6666>Casual lobbies are never bettable.</color> Departed members are not valid targets.
- <color=#7FD4FF>Lobby-phase bets</color> - hosted 2v2 and FFA lobbies take wagers while still FILLING. No odds are quoted yet; at Start the bet is priced from the final field and becomes a normal bet - provided your target is still there and the usual checks pass. Anything else (target left, odds too low, lobby never starts within 6 hours) refunds the stake.
- 1v2 has no betting at all.

<color=#FFD94D><b>PAYOUTS AND THE FIGHTER TAX</b></color>

- A winning payout includes your stake back. 1v1 and 2v2 pay stake x odds rounded to the nearest Gold; FFA rounds DOWN.
- If your winning bet''s stored odds were 1.50x or below, 20% of the PROFIT goes to the fighter or team you backed - being worth betting on pays them too. The potential payout quoted when you place the bet already includes this tax.

<color=#FFD94D><b>REFUNDS, AND WHERE TO SEE IT ALL</b></color>

A refund returns exactly your stake:

- 1v1: a non-tournament series with no game reported in its first 30 minutes is abandoned and refunds its bets. A series stalled for 60 minutes mid-series refunds its bets too, while the series itself stays resumable - <color=#FF6666>a refunded bet stays refunded even if that series is finished later.</color>
- 2v2: refunds only when a series is cancelled. Disconnect-paused series wait for the admin ruling before anything settles.
- FFA: refunds only for a game that never produced a recorded result. Played games always settle as won or lost.
- At tiny stakes a WIN can pay exactly your stake (1g at 1.10x pays 1g). It is still a win: every bet''s stored state - open, won, lost or refunded - is what displays, not the arithmetic.
- Your full bet history across all modes is the bets ledger in the F5 menu. Live bettable games are listed in-game and mirrored in the Discord live-bets channel and its bet commands.', 'a5a0320e13168f43cecad4cfc1ddee6c594f7202', TRUE, 'InfoLibrary · (file scope)')
  , ('a863411f6de0c81d', 'client', 'Gold headband', 'ff880310fcc325b3d9e8eebbeae1fc8cfb893dbd', TRUE, 'shop catalog · cosmetic name/description')
  , ('4adf4f72ca789e4a', 'client', 'Gold per game', 'fb482885e3df2220d1f4c591d2c16790b13bdc0c', TRUE, 'SessionReportModel · BuildTotalsPages')
  , ('415c6d33a6a11889', 'client', 'Gold ring: your modded default', '5d781d48be47bf4f1c3a68c8a30e03eae246be0b', TRUE, 'AvatarDefaults · PaintLegend')
  , ('dd92cee4d2f139f6', 'client', 'Gold this set', 'd78f50fe39240af5e9c117da27a6425d8bce1650', TRUE, 'SessionReportModel · BuildTotalsPages')
  , ('aad109cd1030bedc', 'client', 'Golden Eagle', '87631f9c1ac0e38ebb7c4c1623d120351df77019', TRUE, 'shop catalog · cosmetic name/description')
  , ('17c00df433739b35', 'client', 'Goober', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', FALSE, 'shop catalog · cosmetic name/description')
  , ('d863369ad4820b96', 'client', 'Good Dog', 'caccccdada5ca28c59e602b5e97ebaf85f80e65a', FALSE, 'shop catalog · cosmetic name/description')
  , ('5783daaa33663872', 'client', 'Good game!', 'f08bdc8d0c0c317f3d084df0ff652848b30ae3d7', FALSE, 'QuickChat · Phrases')
  , ('ee94aba8b4c71411', 'client', 'Good luck, have fun!', 'a7a3d544f2e165ee5b1d0c26d4ff3e158cca81a1', FALSE, 'QuickChat · Phrases')
  , ('61e297eba181127f', 'client', 'Got 10 translations approved', '7903e247cb949cf5d7b432707df4d104ed3c81aa', FALSE, 'shop catalog · cosmetic name/description')
  , ('e7f9f0fb5a2c0786', 'client', 'Got 100 translations approved', 'f6fe7b03c53f86154d56f1afe95a158361e7c559', FALSE, 'shop catalog · cosmetic name/description')
  , ('ce25ae7de19d2198', 'client', 'Got 1000 translations approved', 'a66a92451d0146f81caa567f1627e7e235745728', FALSE, 'shop catalog · cosmetic name/description')
  , ('badd96d7af08d83e', 'client', 'Grand Final', '361a685997549953a08875007aa5a09476ac95de', FALSE, 'NativeUI · RefreshTournaments, TrRoundLabel')
  , ('e77a57bcf7f004d1', 'client', 'Grand Final Reset', '3b4f3ff75d57f5b78b110cf32eae0c54c41cd0e6', TRUE, 'NativeUI · TrRoundLabel')
  , ('949e54f8da1fbbb3', 'client', 'Grand Master', '0de1a3e213e5f886d02a66057987fc8a8fbd3036', FALSE, 'ApiClient, InfoViz · AchievementDefs, BuildRankLadder')
  , ('0621e139a09a22b7', 'client', 'Grandma', '1e3c573a02d261117603239280b2414106d2de67', FALSE, 'shop catalog · cosmetic name/description')
  , ('2384a8ba24996fe6', 'client', 'Grant', 'c02329c48f348eb633688f33c499b18b31dcb947', FALSE, 'NativeUI · BuildAdminTab')
  , ('8269a27433f4d383', 'client', 'Grant Achievement...', 'f33ee72ceeb88cb5f896985ce5aab3403f5b5c47', FALSE, 'NativeUI · BuildAdminTab')
  , ('d997b5b7f17ee80f', 'client', 'Grant Artist...', 'b37dab8c0ef031eeb7a1530584d3d3a7c80629de', FALSE, 'NativeUI · BuildAdminTab')
  , ('6f684f202dcec6e0', 'client', 'Grant Translator...', 'cd357517fe20e286565b56385f12c4c3af9c4563', FALSE, 'NativeUI · BuildAdminTab')
  , ('1d8bfec2606b8964', 'client', 'Grant a translation role - find the player', '6c9c8a13e709141fe143390523f4e2389a800362', FALSE, 'NativeUI · BuildAdminTab')
  , ('6ca867d22a13cbd8', 'client', 'Grant data consent first (Settings)', 'f262b59cfc2d76b75d184b4da639c14c823080f4', TRUE, 'PlayerCardsUI · ReasonText')
  , ('44e0c88abbeef0ed', 'client', 'Granted', '43b11ec486dd57233b0d1de336aa501937635986', FALSE, 'NativeUI · PaintConsent')
  , ('9e93a32d4754dbb4', 'client', 'Graphs {0}/{1}', '01054b0109229cab306423442f0ce81891a39f58', FALSE, 'PostSessionReport · BuildGraphPages')
  , ('5377b5558c7d6174', 'client', 'Great White', 'd5763ca42b2baa62e2dd534be33868500c828b5c', FALSE, 'shop catalog · cosmetic name/description')
  , ('fb2cb4c71f3f10bf', 'client', 'Great-Grandma', '0d5dfdeb0e868db3b04c17fbee0c91381aa13b5a', FALSE, 'shop catalog · cosmetic name/description')
  , ('3426d61e9ffeccc9', 'client', 'Green Cursor', '3ff31ec176822ae0d4a3602b4b80563f74ca6119', FALSE, 'shop catalog · cosmetic name/description')
  , ('c91478ec31d61956', 'client', 'Green Name', '3f508506b3bbc0e084dffe7ce76e5c8ec800e0ad', FALSE, 'shop catalog · cosmetic name/description')
  , ('fb1478c1f65baa33', 'client', 'Grey Cat', '82974e1f3b7ac1ae1fd1714ea5e215b421da1805', FALSE, 'shop catalog · cosmetic name/description')
  , ('81665ca613d56c05', 'client', 'Grinder', '88557672dea96c8c2703f425c9d61bcf1a28f700', FALSE, 'shop catalog · cosmetic name/description')
  , ('f5c824dbf99d5d12', 'client', 'Grizzly', 'fb6b5ac45eccb137bc25f7a4f67feff2aab193b7', FALSE, 'shop catalog · cosmetic name/description')
  , ('d0fb1e23e0d0e771', 'client', 'Grounded', 'd5580b73bfb2949ac6d9534c49ecd66ceba94e8c', FALSE, 'ApiClient · AchievementDefs')
  , ('77d8d2d50b004dd4', 'client', 'Grow', '7e2299a8cab8d708d1c275e314cf72784ffaa7c9', FALSE, 'InfoLibrary · (file scope)')
  , ('f6a68c6300794435', 'client', 'Grow is the one card whose damage depends on the shooter''s FRAME RATE. In vanilla, the same Grow bullet fired by a 60 FPS player hits far harder than one fired at 400 FPS - and the mod normalizes it in competitive play.

<color=#FFD94D><b>THE REAL MATH</b></color>

Grow multiplies the bullet''s damage a little every rendered frame while it flies, through the first 40 units of travel. Compounding a per-frame multiplier has a strange consequence: the bullet''s speed cancels out of the total, and what actually sets the final multiplier is the length of the shooter''s frames. Fewer, longer frames compound harder.

Un-stacked, over a full flight:

- 400 FPS shooter: about <color=#7FD4FF>x1.4</color>
- 60 FPS shooter: about <color=#7FD4FF>x9.4</color>
- 30 FPS shooter: about <color=#7FD4FF>x82</color>

Stacking multiplies the growth rate, so the gap explodes. At three copies: about x2.8 at 400 FPS, <color=#FF6666>x737 at 60 FPS, and x285,000 at 30 FPS</color>.

Hitches are the worst case: <color=#FF6666>a single 200 ms freeze frame multiplies the bullet by about x5.6 on its own</color>. One stutter mid-flight can turn a normal shot into a one-shot.

<color=#FFD94D><b>WHY THEIR FPS BECOMES YOUR PROBLEM</b></color>

Damage in ROUNDS is shooter-authoritative: the shooter''s machine computes what the victim takes, and everyone else applies that number (see <color=#7FD4FF>Netcode & Photon</color>). Grow''s growth happens on the shooter''s frames, so a low-FPS or stuttering opponent''s Grow bullets genuinely hit harder. It is not lag, it is not your imagination, and in vanilla it is not cheating either - it is the card''s math.

<color=#FFD94D><b>THE MOD''S NORMALIZATION</b></color>

In eligible rooms, the mod pins Grow''s growth clock: <color=#7FE87F>every Grow bullet grows as if its shooter ran at 120 FPS, on every machine</color>. One copy is about x3.1 over a full flight, two copies x9.6, three x30 - the same for everybody, every game. The reference rate is compiled into the mod on purpose: if it were a setting, changing it would change your own damage.

Where it applies:

- Every fighter in the room must run a current mod build (spectators don''t count). <color=#FF6666>One vanilla or outdated fighter means vanilla growth for the whole room</color>, the same on every screen - a mixed lobby is never half-normalized.
- Mod queue rooms (ranked 1v1, 2v2, 1v2, FFA, tournament rooms) normalize whenever everyone is current.
- Private room-code and quickplay games normalize only when, on top of that, every fighter had the Ranked toggle ON when they connected.
- The decision is locked per bullet at launch and never flips mid-flight. It is never active offline.

One honest residual: at very low frame rates a normalized bullet can grow slightly LESS than the target (a few percent stacked; more on a heavy hitch). The error always points down - never toward the one-shot.', '1ff0e513c66b189e143ecd00dcfe0154b828aacb', TRUE, 'InfoLibrary · (file scope)')
  , ('b0a7c6d3a3a1f50e', 'client', 'Guides to every mechanic: blocking, poison, netcode, modes, ratings, rewards, tournaments, anti-cheat, and what the mod does (and deliberately doesn''t) change.', '563c35f5fd7311e5b35e3c9b4db101e77b832981', FALSE, 'NativeUI · BuildSettingsTab')
  , ('fb918ff938758326', 'client', 'H2H {0}-{1} · Ranked series {2}', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', TRUE, 'H2HSummary · BuildLine')
  , ('0ac4a55c5f1ccb06', 'client', 'HIGH', 'd77d0b27955f008358918e195742c4c8208699e1', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('44d73872ab1e6601', 'client', 'HMAC not configured', '89acf2eabdefd8ea7adecd83142cde8cb69c51da', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('ce525d05913ef730', 'client', 'HOST', 'e645477f66e745ec37b00fdc6d45d4196a39d1b0', FALSE, 'NativeUI · RenderFfaLobbySection, RenderHostLobbySection')
  , ('afecea29bc7bb5b5', 'client', 'HOW A COSMETIC REACHES YOUR BODY', 'd732cf6647f10509dfd37d789f659c18dce662c4', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('34eaa39f9e9f80a2', 'client', 'HOW SURE THE SYSTEM IS', 'f579c8b1fa341ce3edef722783b5f58bc7d152ce', FALSE, 'InfoViz · BuildGlickoRd')
  , ('db45cfb0c2602f99', 'client', 'HP decimals: <color=#88FF88>2 DECIMALS</color>', 'a2953220bebb94062b52c19104e0d60e3e8a836d', FALSE, 'NativeUI · PaintHealthPrecision')
  , ('6b5d38846d3f750b', 'client', 'HP decimals: <color=#DDDD66>1 DECIMAL</color>', 'd183cda26d8d8f23a82dd8f898e18aae70284c29', FALSE, 'NativeUI · PaintHealthPrecision')
  , ('4c6e1ada87530ddc', 'client', 'HP decimals: <color=#FF9966>ROUNDED</color>', 'a40abb2e44a5607230e5afcf7d7296ba5c47a0ab', FALSE, 'NativeUI · PaintHealthPrecision')
  , ('40389559a5d3a7c2', 'client', 'HUMAN REVIEW', '99cf818cabe3e4801c06b9427a9ce4f4d1500280', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('8fec4bc289417df0', 'client', 'Halo', 'f3681d8bf189692334f17228e4c6f6976fc76e68', FALSE, 'shop catalog · cosmetic name/description')
  , ('cbdfe2e3f3409118', 'client', 'Harassment', '8fddd79e1918745ff44d284f37e6f5f49191ffb4', FALSE, 'MailUI · DrawReportModal')
  , ('112f0a217f5a096e', 'client', 'Hard to hit', '6ce2c7378614f190440e5da3487b936abbd6781c', FALSE, 'shop catalog · cosmetic name/description')
  , ('b21845511dcda1c6', 'client', 'Hare Apparent', '2d9cac34c99683651c75abbc5e348fc49fff1927', FALSE, 'shop catalog · cosmetic name/description')
  , ('2abfad7c25327557', 'client', 'Harlequin', 'a4830d21a06a1fed15d749bae38884e90b70cfd0', FALSE, 'shop catalog · cosmetic name/description')
  , ('3960a6d82453549a', 'client', 'Hasty', '06e27642e791a899db92ec7fc9fc01900dd8d863', FALSE, 'shop catalog · cosmetic name/description')
  , ('d8e452128d8cdb36', 'client', 'Hatchling', '9c0c49c5aac5b27e6e985c5ac794910f3b7c1c77', FALSE, 'shop catalog · cosmetic name/description')
  , ('14796e67387865fd', 'client', 'He/him', '67cc0b8a50586de358efae7157a8c921a6fa5e8f', FALSE, 'shop catalog · cosmetic name/description')
  , ('c0dccf81dbea7f02', 'client', 'He/him I', 'dfaf34b8abc51656a5e3a9076f49ec73d7cd500d', FALSE, 'shop catalog · cosmetic name/description')
  , ('1e8102cb4f58bf92', 'client', 'He/him II', '1146999f85e29b60f53734ba443c71aeaee41b38', FALSE, 'shop catalog · cosmetic name/description')
  , ('b7f7af79a8afa046', 'client', 'He/him III', '6efa2a7d4560150fa5f9025ac7f38a3e3fbdd7c5', FALSE, 'shop catalog · cosmetic name/description')
  , ('9251d0a4cc5e6d19', 'client', 'He/him IV', '3aea05eede0729cd341a88f3a88e7d74ebe0479e', FALSE, 'shop catalog · cosmetic name/description')
  , ('7ba38f634a7a842e', 'client', 'He/him V', 'b5fe4cceb9a1d6f09955bcde7a849311d4ecacc8', FALSE, 'shop catalog · cosmetic name/description')
  , ('47495b38eabb5314', 'client', 'Headhunter', '0935a2ea4b46924524a579c5a4e7ba9b14e6dc9d', FALSE, 'shop catalog · cosmetic name/description')
  , ('1e5e8f7d43e5b601', 'client', 'Healer', '6cad85d7f7dcd1b52fab90c0435e0ef4df7ef791', FALSE, 'shop catalog · cosmetic name/description')
  , ('4094de8354dab80d', 'client', 'Healing Field', '607d5ba1150c8d677bcee262978a050c369136f1', FALSE, 'shop catalog · cosmetic name/description')
  , ('0b8a96a36bbd6047', 'client', 'Healing Field main', '31f3455e822c8b2187691d06a5cbce86abba2ce1', FALSE, 'shop catalog · cosmetic name/description')
  , ('90c59f6f9a2fdb41', 'client', 'Heart Eyes', '48ee9e4fba600c1e5238b5b30afe832cee3f4452', FALSE, 'shop catalog · cosmetic name/description')
  , ('76d0b8ff54ba17d8', 'client', 'Heartbreak', '8affa8effd7087ecbab966e0ab6f5d70c951060a', FALSE, 'ApiClient · AchievementDefs')
  , ('824fe214604ba4a1', 'client', 'Hearts', '99f9bf69ff7f179b358e1191419dafa45a0d75db', FALSE, 'shop catalog · cosmetic name/description')
  , ('50514f77be6d49ff', 'client', 'Held by the top 3 on the 1v1 ranked leaderboard', 'bea6098ea458b065476f3ec8a265587f5a25be11', TRUE, 'shop catalog · cosmetic name/description')
  , ('9f6f3ff506740ea8', 'client', 'Held by the top 3 on the 2v2 leaderboard', 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', FALSE, 'shop catalog · cosmetic name/description')
  , ('2e97ebb1aa9833a1', 'client', 'Held by the top 3 on the FFA leaderboard', 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', FALSE, 'shop catalog · cosmetic name/description')
  , ('ecfcce77736bc251', 'client', 'Hellhound', '52940afb7ae100af9d7673f2ca304bcd0f37c4b6', FALSE, 'shop catalog · cosmetic name/description')
  , ('2a8c1fdc9abb0582', 'client', 'Hello!', '69342c5c39e5ae5f0077aecc32c0f81811fb8193', FALSE, 'QuickChat · Phrases')
  , ('e94131143feaca60', 'client', 'Help translate the mod - opens the web portal in your browser. An admin has to give you translator access before you can submit.', '665bfd72831ac98231ad8352f88ee64ae4aacbef', FALSE, 'NativeUI · BuildSettingsTab')
  , ('87f5c64d95c1513d', 'client', 'Hide Gold', 'd393cc8c5a9dfa381e77aa7f447053858f2910bf', TRUE, 'NativeUI, shop catalog · ApplyShopRow, cosmetic name/description')
  , ('341bc3956a62a4c9', 'client', 'Hide your gold balance from everyone on the leaderboard. Toggle it on or off any time from the Other tab.', 'a14b11926312cad57e30de5af74a2d2f016fe58f', TRUE, 'shop catalog · cosmetic name/description')
  , ('80f22c97cc0aac83', 'client', 'Hides you from the Home tab''s online and recently-online lists.', '391e23160a547aa2386bfc6e88136f01474e87ec', FALSE, 'NativeUI · BuildSettingsTab')
  , ('00066ff57ca04552', 'client', 'Higher placement takes a bigger share of the pot; the pot itself scales with lobby size, battles played and opponent tier.', '5e5ecdae061097113bb0fc42625366227134dd5a', FALSE, 'InfoViz · BuildFfaScoring')
  , ('feff69adc81c2b24', 'client', 'Highest Avg DPS', '4f1d991e2d8b1eb831dcd5c836ad6b4f8e0ee296', FALSE, 'NativeUI · RecordBoardHeading')
  , ('513a6e57e933a9fa', 'client', 'Highest Health', '0bfbda6cb5bd27c04cfdb09fa9a2df07105f83f7', FALSE, 'NativeUI · RecordBoardHeading')
  , ('3a6fa8317706a4e2', 'client', 'Highest Single Hit', '03b42042514ededa387f0563828ce9b5825ca636', FALSE, 'NativeUI · RecordBoardHeading')
  , ('8c1eb356c1525df3', 'client', 'Hips one way, arms the other - the classic. Dancing locks your controls for the duration.', '3d54b658e24e84cbd5bf677fdcb229ba5796f7d2', FALSE, 'shop catalog · cosmetic name/description')
  , ('3f5d0dc0170cb607', 'client', 'Hit', 'ea490aaa629a0704301cf91e7a4910b910278662', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('3efbc953c91b440b', 'client', 'Hit %', '48a77eef568007e361b85fee51b594fea15ff0df', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('68ebe98e1a246198', 'client', 'Hit % vs Block %', 'c93d8b77434bdab2d626ebd548390c53fe4108b6', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('5884139e3a1c369e', 'client', 'Hit / Block %', 'bfa62d12f6552fa084e5624db91e8f809cc967fc', FALSE, 'NativeUI · TrMetric')
  , ('5b3e863917a976af', 'client', 'Hit rate - {0}', 'ad63b1980e7f9c3bba418b541020bc56100c81bf', FALSE, 'PostSessionReport · AddPairCell, BuildCells2v2Game, BuildCellsFfaGame')
  , ('ed7a78f08c8910e9', 'client', 'Hit {0}%', '92630d30a1d74b1197a4c4a901a81ed0d0cc6439', FALSE, 'NativeUI, PostSessionReport · BuildBracketHoverBody, SideStats')
  , ('745857a8dca56064', 'client', 'Hit {0}% Blk {1}%', 'da0484d06004a9aca15a1d045da97cb7447fee94', FALSE, 'PostSessionReport · TeleCellText')
  , ('a13104d1f01151a6', 'client', 'Hit-sound NRE swallow', '7d45cd2bcca78ca9b078914744db3bdc40609f21', FALSE, 'NativeUI · PerfRowLabel')
  , ('d2051bb918390378', 'client', 'Hold in a match for the live scoreboard: score, cards, accuracy and connection.', 'bc08eb80cd3d5e791383ab7e136f5d590da350db', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('aa6e72b3c95d1980', 'client', 'Hold on!', 'edcfe3cc16fde6891e557f59a48f9c2f1c2b4510', FALSE, 'QuickChat · Phrases')
  , ('50b7ee2f290078b7', 'client', 'Hold to open the dance wheel. Dancing locks your own controls until it ends.', '8700714f3b2e0f44ea728497371b98661f145cef', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('53098bcfee600539', 'client', 'Hold to open the quick-chat wheel, point at a phrase and release to send it.', '23c1e3bac7082af78d59e581086c3ddbf6281a5e', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('9914bb866193f854', 'client', 'Home', '70f8bb9a8a5393ef080507a89e4b98d139000d65', FALSE, 'NativeUI, NativeUI.Keybinds · (file scope), KeybindKeyName')
  , ('8c7aeaf806546104', 'client', 'Homing User', 'c8cc751ecfa3f6cd52d20d99be1c3d3de3e682b6', FALSE, 'shop catalog · cosmetic name/description')
  , ('071c8c4641b18c3a', 'client', 'Homing main', '2b77056d8510cbf771ae1eabe376618a805c01e7', FALSE, 'shop catalog · cosmetic name/description')
  , ('7839675d71513a87', 'client', 'Honk honk.', '0a651c070742e5b205bdf0d6ec0b389fa0524d53', FALSE, 'shop catalog · cosmetic name/description')
  , ('51fa309a2660b60c', 'client', 'Hop to attention - arms snap up and out on every beat. Dancing locks your controls for the duration.', '6365d6a9d800c10fa6e483c59e130301bb787840', FALSE, 'shop catalog · cosmetic name/description')
  , ('8bcce458c01315e4', 'client', 'Hop to the beat, arms pumping. Play it between rounds with the {0} wheel.', 'd7ef3176e44d0bd97396384b3d2c1a7464548ff6', FALSE, 'shop catalog · cosmetic name/description')
  , ('0ea392bb4e864fa8', 'client', 'Hostile Takeover', '88993ad514a4bd209c99f98a2368669037c34285', FALSE, 'ApiClient · AchievementDefs')
  , ('e4ed2e45c87a71a4', 'client', 'Hot-pink neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', '55d34abe601f847d5d3c021c49f5bf80f5db5d6e', FALSE, 'shop catalog · cosmetic name/description')
  , ('52edb8e1db412fe8', 'client', 'Hound', '11843e4d404f59886f2370ab360996f5d1e313c6', FALSE, 'shop catalog · cosmetic name/description')
  , ('98a3fad8f87afa66', 'client', 'How It Works', '8cecc82d72d68f9151cb0901cfe40eeac15bfca6', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('c6ea11f664524a12', 'client', 'How It Works - Async (6-week)', 'cf4e2230ffef8a783fcf4ea4e36306115c1023c3', FALSE, 'NativeUI · RefreshTournaments')
  , ('58adc2e93f0e5669', 'client', 'How It Works - Sync (weekly)', 'b4a5f85c718b851bc30c568fe28f4ef79037ce0b', FALSE, 'NativeUI · RefreshTournaments')
  , ('f501fa2dd1f5cbc4', 'client', 'How dates are written across the mod''s menus (history rows, leaderboards, tournaments).', '5eb10c630fc6887d4a44e6d2b996c378edff9152', FALSE, 'NativeUI · BuildSettingsTab')
  , ('6b9260da4b06a2c5', 'client', 'How games are tracked', '2d2ff271edf97f022c61da788ed38114dbe3f96d', FALSE, 'InfoLibrary · (file scope)')
  , ('584b85f07fb63c7a', 'client', 'How long a chat message stays fully visible before it fades. Ignored while the overlay is pinned.', '2190399e8e176f5946cbb2f5d62e959155192bd1', FALSE, 'NativeUI · BuildSettingsTab')
  , ('f67efe800c180000', 'client', 'How long for {0}?', '28160d3239f84bf7543ffb33ba400f72c19fef0e', FALSE, 'NativeUI · StartChatMuteFlow')
  , ('56bb047fa0c21ad1', 'client', 'How long?', '9ce819198916f31ef18b3eb733d0c0f8f44ae386', FALSE, 'NativeUI · ChatMuteMsgDuration')
  , ('b80da06170bb95d3', 'client', 'How much damage?', 'ac5d996d8fe5ffdedebdfe952c24578b1018a362', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('f8218f1964c0c094', 'client', 'How stats are tracked', 'be82f1dfcef7b0d0b8db7689f8c76a538da23f82', FALSE, 'InfoLibrary · (file scope)')
  , ('31a7246a6c684e0f', 'client', 'How the mod counts your combat and match stats, in plain terms.

<color=#FFD94D><b>HIT %</b></color>

- The denominator counts BULLETS fired, not clicks.
  One Buckshot click counts every pellet; bursts and
  charge volleys multiply it too.
- Clicks during reload or cooldown don''t count, and
  card-spawned shooters never count.
- The numerator counts direct, unblocked hits on
  enemies only. Self-hits, teammates, poison and burn
  ticks, explosions and thorns never count.

<color=#FFD94D><b>BLOCK SUCCESS</b></color>

- One OFF-COOLDOWN block activation = one attempt
  (blocks during cooldown don''t count), and at
  most ONE success no matter how many bullets that
  block absorbs.
- Echo repeats and Shield Charge dashes belong to the
  block that started them - they never add
  attempts.
- Abyssal / Shields Up auto-blocks are not attempts,
  though an auto-block absorbing within the block''s
  short credit window can claim its success.
- Blocking your OWN reflected bullet DOES count as a
  success.

<color=#FFD94D><b>RAGE QUIT % VS LEAVE %</b></color>

- Rage Quit % (Compare tab) is about your OPPONENTS,
  not about you: how often the other player quits
  mid-game in your CASUAL 1v1s, counting unmodded
  quickplay opponents too. Higher is better - it means
  more of them walked out on you.
- Your own casual leaves are NOT this number.
- The leaderboard''s Leave column IS about you: the
  RANKED formula, your ranked DCs divided by ranked
  series wins + losses + DCs.

<color=#FFD94D><b>AVG GAME LENGTH</b></color>

- The clock starts when the first round''s movement
  begins (after the initial picks) and includes every
  later card pick and transition until game over.

<color=#FFD94D><b>WHAT FEEDS LIFETIME STATS</b></color>

- Lifetime Hit/Block/Keys stats accumulate from 1v1
  games only (ranked + casual), and only from the match
  reporter''s own side.
- 2v2 and FFA record the same stats per game (visible
  on each game''s row) but they don''t feed the lifetime
  percentages.
- FFA / 2v2 / 1v2 metrics in Compare come from their
  own tables.

<color=#FFD94D><b>TIMELINE GRAPHS</b></color>

- Graphs sample every 3-5 seconds (longer games
  compress older samples), so graph ratios can differ
  slightly from the exact totals.', '0fdf854431ef00d333c01141993f58b80d242dfa', TRUE, 'NativeUI · (file scope)')
  , ('1930838335e1b282', 'client', 'How to get packs', '549ed968ae736b6cd25ac63581b2c07215df5072', FALSE, 'PlayerCardsUI · RefreshInfo')
  , ('42ca762d56c495c7', 'client', 'How tournaments run', '79ed67952069104e31b39c3145b76a56f1902994', FALSE, 'InfoLibrary · (file scope)')
  , ('9a8b2e9d295e11ba', 'client', 'However, this is if you only use Silence. Other Refresh activators can disrupt the every-other pattern: hit your opponent with a bullet (non-Conditional damage) and you receive a successful Refresh AND reset RefreshValid to false. Depending on where in the pattern you put your shot, you can snag an extra Refresh (the second and third sequences above).

Sadly, this is not the end of the document, because the ROUNDS developers saw fit to introduce another mechanic. I do hope you, dear reader, appreciate the relative ease with which you get to possess this information as compared to the hours of madness I spent obtaining it.', '24efe03f2c19ba6f6259f895e296d62212b2d870', TRUE, 'InfoLibrary · (file scope)')
  , ('8dfae9b58d919fe0', 'client', 'Huge', '32978fbe93d3be31d803d0f25bc182a893e9a2f2', FALSE, 'shop catalog · cosmetic name/description')
  , ('a95527c4eb90449a', 'client', 'Huge Name', '96096beb7426ce6ce5e38c347d4d90ad2a3f936b', FALSE, 'shop catalog · cosmetic name/description')
  , ('bce43d5b196d8359', 'client', 'Huge main', '0c99c0f89091cfd5c213bec88778fa6d7c4b67e1', FALSE, 'shop catalog · cosmetic name/description')
  , ('1491ccbbab4f77f2', 'client', 'Hypno-spiral eyes. Completely unhinged.', 'e41832724539bffc1b27e6bf1721c3d4b02fee0a', FALSE, 'shop catalog · cosmetic name/description')
  , ('7e7ce5225b69fa21', 'client', 'I play with a competitive framework mod called Sid''s Competitive Rounds', '6a35e13d6078bf6447b978d8d41795fc54c18658', FALSE, 'QuickChat · Phrases')
  , ('fb81d413056c7042', 'client', 'I''m ready', 'c3ba5714684266f4b723efee3630b3f044e02fac', FALSE, 'QuickChat · Phrases')
  , ('d8ba12181cae06db', 'client', 'Icy blue trail fading to white. Two-color gradient.', 'b18f1b30f790bc9203c185bcbf4e886783ef9d75', FALSE, 'shop catalog · cosmetic name/description')
  , ('29acfd71fca68846', 'client', 'Idiot', 'b2c854c19c069e8f54d7bc38119fa68daba14613', FALSE, 'shop catalog · cosmetic name/description')
  , ('41bf171398337fc7', 'client', 'Idiot Savant', 'dea3ed0cb48d4e281bc0692d9b899122f57d6fe7', FALSE, 'shop catalog · cosmetic name/description')
  , ('b492fedfe366aaf0', 'client', 'If no earlier rule settles it, score, check-in, no-show rate and a fixed tiebreak decide.', 'b3c71efa1b2e2068d719a2aa9dab639c4e5aa362', FALSE, 'InfoViz · BuildForfeitClock')
  , ('946a03bb72a4fe72', 'client', 'Immortal', '599812412c8e063215968af7cc448d65f2b3faa9', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('3e6bea2210f7f3f3', 'client', 'Immovable Object', '6be2477292a2c7282275bcb131607912fcdac752', FALSE, 'ApiClient · AchievementDefs')
  , ('e75c80cd71770ea9', 'client', 'In a game — no results yet', '3c81f3e5dbb58583795d18d6b4d1d5d6fb61fd43', FALSE, 'NativeUI · RefreshSession')
  , ('63b6206985daaea0', 'client', 'In a trade', 'b0a871ccc29d08756184bf88d9746cc413d7bdf4', FALSE, 'PlayerCardsUI · PaintTileBadge')
  , ('80d9d4d756171dc1', 'client', 'In game', 'e02cd1a21b408720a75a0656406d0d653c20a4ce', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('eedfa4638f82acff', 'client', 'In use', '20716e9262a74a73cc0400f93d1a8ceab0472e49', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('1dfcc098b4da261c', 'client', 'In-combat particle aura around your character. Only visible to modded players.', '1c15dd7ddb9d813d9dc6cfb93e6d07cca1ff84cc', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('786fbfe8c421b95c', 'client', 'In-game chat overlay: <color=#88CCFF>PINNED</color>', '2e65e9918478d0fd2219679140666a9867b7ffdf', FALSE, 'NativeUI · PaintIngameChat')
  , ('58b772f9792e7de7', 'client', 'In-game chat overlay: <color=#88FF88>ON</color>', 'be77e0d452a5b253d62f1b462dca9f79853f28df', FALSE, 'NativeUI · PaintIngameChat')
  , ('ab95166595686da5', 'client', 'In-game chat overlay: <color=#FF9966>OFF</color>', '747f336134ffc5ee335d36ce3ae94cebbd293a87', FALSE, 'NativeUI · PaintIngameChat')
  , ('c02b7eb396601c2f', 'client', 'Inbox', '44caf74675ceb79ba5cc13bafa102509369c2b53', FALSE, 'MailUI · BuildHeader, PaintNav')
  , ('153eaf29f07c21c2', 'client', 'Inbox ({0})', '80c0d9037c516293b1095cc23493046c1ce2d324', FALSE, 'MailUI · PaintNav')
  , ('5c566c257a3b6f55', 'client', 'Incoming', 'a9c615b9e833ee226ac08cb33f93df17a615ca30', FALSE, 'PlayerCardsUI · RefreshTradeLists')
  , ('cf6154247e010be9', 'client', 'Indigo Name', '896aeebe623741dcf08c97d02e0111f4311b39e9', FALSE, 'shop catalog · cosmetic name/description')
  , ('6155cc874330ae15', 'client', 'Industrial steel grey with the warmth bled out.', 'ad8477c02907e0acf0430c6c33bcc17614b5cbe2', FALSE, 'shop catalog · cosmetic name/description')
  , ('ec771eaf68f39ebf', 'client', 'Info', '4b631f69842530d659306c8f06dbad594a6b1807', FALSE, 'NativeUI · (file scope), BuildFfaTab, BuildOneVTwoTab +1')
  , ('b2d2460c335c2a70', 'client', 'Input overlay (bottom-left): shows {0} and both mouse buttons. Lights up red when pressed. Useful for streams or spotting missed inputs.', '3e99e33e7027443561681b4812e3731d47fed6a1', FALSE, 'NativeUI.Keybinds · KbDescInputOverlay')
  , ('e257fa5f452ec7c9', 'client', 'Input overlay: <color=#88FF88>ON</color>', 'a24644dfa7613e54acd8966b3c2c10881854a735', FALSE, 'NativeUI · PaintInputOverlay')
  , ('78ac1eab1e0868c7', 'client', 'Input overlay: <color=#FF9966>OFF</color>', '2ffcc999b9210eec5e69ba494dded93b5eecc4ce', FALSE, 'NativeUI · PaintInputOverlay')
  , ('846ada8cf2f83e34', 'client', 'Insert', '95802daab3a23990338179f72248350c1434cf39', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('de84355ebcd60fa2', 'client', 'Inside the 0.35 s window?', '70f1507a50aa1affe9be3d1d4a9a831047950cd9', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('5567eee60b51362d', 'client', 'Instinct', '8b466a9d6a804f6268778e511de8a9906c9260cf', FALSE, 'ApiClient · AchievementDefs')
  , ('e02dd80f9035fb5d', 'client', 'Insufficient gold', '7947afceeabe0b726059c3443da3dd652abf6ac1', TRUE, 'ServerTextRules · TrRefusalDetail')
  , ('d05e8859e4613238', 'client', 'Insufficient gold: have {0}, need {1}', '2c3a6ca4cdbf1c54a4384a397dc4ab84902a49f9', TRUE, 'ServerTextRules · TrRefusalDetail')
  , ('665d16d4b2840e40', 'client', 'Intermediate', 'b1cfe72fd27178870354f9f4e07bb82072caea55', FALSE, 'InfoViz · BuildRankLadder')
  , ('c3dcb3a7c99fa461', 'client', 'Into the Deep End', '104715a881fa08ef642df3c97be967c6383f5a4a', FALSE, 'ApiClient · AchievementDefs')
  , ('7705c8dea1d1558e', 'client', 'Invalid PNG data', '7204a3b9f4718957022ca7663990fc05177dbd56', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5201d4306de4b1e3', 'client', 'Invalid catalog placement request', 'e478698603876354fcecae85b0f14050bb2d3add', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('168caf3801346fda', 'client', 'Invalid placement request', '7be434781593e1b8d8a7a4d74b03b88ada9c688a', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('27e8df8e37b1c80b', 'client', 'Invalid placement revision', '9b94677756f68305b6ab8625e0b893f8f0f9ff11', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('16f8f78b99629cf0', 'client', 'Invalid signature', 'a44e6783da22472019053151caba4aaaf683eb33', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5d5598bf6de306c4', 'client', 'Invalid signature version', '32f5bf78d559020c8958832c7025af0c9c077fba', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('742b61a27b8f06c2', 'client', 'Iron', '8564fe3b4b674b36c08f22266d713f860a15ca99', FALSE, 'shop catalog · cosmetic name/description')
  , ('4ade614fa0dc0708', 'client', 'Iron Bracket', '7263a1edd582c7b3ef9fbe39bf7fea9c382188ef', FALSE, 'ApiClient · AchievementDefs')
  , ('35b7a88c8c43fe2a', 'client', 'Is RefreshValid true?', 'ecf52fe8e70265b69484ec079d7c35e89da2ae77', FALSE, 'InfoViz · BuildRefreshFlow, BuildRefreshGate, TextFallback')
  , ('27972bcd47cb6e6e', 'client', 'Italic', '1616e2e5405e69c4e3914c67c644a9bd3ac00956', FALSE, 'shop catalog · cosmetic name/description')
  , ('47b6189497f3df31', 'client', 'Item not found', 'a0db78d2c75e01173a103339305801c35df50974', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5bebdfe868db2544', 'client', 'Ivory', '39973be20679a94e4c998a58c0f6c76daaf6cd11', FALSE, 'shop catalog · cosmetic name/description')
  , ('55557954c06b0c86', 'client', 'JUMP', 'bb0d79b578ec75d9a062b029e5cfd1928a02dd5b', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('71111e954337e05a', 'client', 'Jackalope', '606d480430b7720248223208a124128409ff90a8', FALSE, 'shop catalog · cosmetic name/description')
  , ('991c7bed45344b76', 'client', 'Jackrabbit', '78beadd58fa730003f066cfb011b38ee363af3ec', FALSE, 'shop catalog · cosmetic name/description')
  , ('b9ed01915d8ee65e', 'client', 'Jester', '386faa17f81ab17e591e063fc276303639cc8700', FALSE, 'shop catalog · cosmetic name/description')
  , ('c6deea52290a01d3', 'client', 'Join', 'e0d73143de80d17e82de2e017ac156ca3b9c4e01', FALSE, 'NativeUI · CreateFfaBrowserRow, CreateHostLobbyBrowserRow')
  , ('5678fc6bff05c631', 'client', 'Join Competitive Rounds!', '1cadad1503961af2e4f1a03cf9083519e5d26a7d', FALSE, 'CompetitiveUI · QcLabel')
  , ('817265dacfc7951b', 'client', 'Joined the match!', '479f27815777e46c802e3a188583f9e3496dd859', FALSE, 'Plugin · OnJoinedRankedRoom')
  , ('45601925442a93f3', 'client', 'Joining the match at the next point', 'ea08b8e2ea3faa610418cbe49c746f47e2190943', FALSE, 'FfaLateEntry · AdmittedLateRun')
  , ('cb5be6eb1a54e3b3', 'client', 'Jump', '1eba140fdd9c6860a1730c408e3064aa417ca2a3', FALSE, 'NativeUI.Keybinds, TabStatsOverlay · EnsureLocaleStrings, KeybindRowLabel')
  , ('a907a9bcecb375bf', 'client', 'Jumping Jacks', 'e5296ed2f8b67d8cc42d2dc7ff153822c1575f4e', FALSE, 'shop catalog · cosmetic name/description')
  , ('14ff90268c5dfe1d', 'client', 'Jumps', '933adea19eee0a6883654433bf5abd0a524cc8c6', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('1ed255dd4fec3531', 'client', 'Jumps. In a lobby the same control readies you up and joins.', 'a1ab7191408661705a859dc5096b24bdd8734f53', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('5ae909299d5434a1', 'client', 'Just under half of a payout arrives as XP, the rest as gold. Rating moves from pairwise comparisons against the finishers nearest you.', '3d56e9cc99258ab6de6f89390be351705194253e', TRUE, 'InfoViz · BuildFfaScoring')
  , ('b0020c192e5a1183', 'client', 'KEYS THAT DO SOMETHING', 'e4264ec8fb10bdf6a4e134e6320886298061a4b5', FALSE, 'InfoViz · BuildKeyboard')
  , ('b9ddc17d768fa1b3', 'client', 'Keep it locked', '68d7017152dfa47134be41079d6cf5f23253371a', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('a2702c0ad7e96b07', 'client', 'Keep watching', '6fbe1fba437a2e21a359398c39005cb4b8e76491', FALSE, 'SpectatorHud · DrawLeaveMenu')
  , ('fefd29b7cdc2891d', 'client', 'Keys / Game', '3e766191a84859276c20faa0e8ef0e675f15ce42', FALSE, 'NativeUI · TrMetric')
  , ('c71afca6cc3af501', 'client', 'Keys / Sec', 'd76083989d43f7f7ade72236e5280c68f1313816', FALSE, 'NativeUI · TrMetric')
  , ('5f8988e0e570273b', 'client', 'Keys/s', '812d465d4b71db71c2ed2a07e20a6504b807ff57', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('45e188ed96a19905', 'client', 'Kick', '8c5ec4edfe9a6f4f388a0204b0e6d5ccfee6ff5b', FALSE, 'NativeUI · CreateLobbyMemberRow')
  , ('0e7db6723e7a522d', 'client', 'Kills', '9ec34025b6db16bb4bd06189361b2632e0310b10', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('dbd580cba66987fb', 'client', 'Kills per game', '5060f17a0a609989d07320a1a109c665111ce734', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('6ed66966d2c77935', 'client', 'Kills/game', '89502167e877d465a7429db87571be0aed21692b', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('101d281fb7725477', 'client', 'Kingslayer', '27e105212199fa01c8a9ddb8d5052a43b991fbae', FALSE, 'shop catalog · cosmetic name/description')
  , ('29ac3b62215ab929', 'client', 'Kitten', '77f69ac1090abb151504b9ba65a6ef840371cc0f', FALSE, 'shop catalog · cosmetic name/description')
  , ('70ef6c5c94097ef3', 'client', 'Knight Great-Helm', 'f5b75e673715471ccd9edc10e29ada4d24f5dfdf', FALSE, 'shop catalog · cosmetic name/description')
  , ('2c692d50a4ccf781', 'client', 'Knockback', 'f898dcaa913e7d96aa2f5cc90629d9e61f5f363e', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('b5f34f740a723641', 'client', 'Known vanilla bugs', '9c44d8b9070ee32670d2c711ac5c17177adacca6', FALSE, 'InfoLibrary · (file scope)')
  , ('74ad6ad1ff95d7d4', 'client', 'Kodiak', 'ae32390be4058d1f88a77f81b214a139ee4f3bee', FALSE, 'shop catalog · cosmetic name/description')
  , ('fd5f0b6ee48c2a5a', 'client', 'LB R{0}', '5d72fc7134028f6d905347a62c5fd6f700a2b901', FALSE, 'NativeUI · TrBracketProgress')
  , ('7025fdd06041768e', 'client', 'LEAVE MATCH', 'f031701805141ea08448cbd97997244fc8148058', FALSE, 'EscLeaveRow · SetLabel')
  , ('df887a29a2557b23', 'client', 'LEFT', '969e2cc476ff76be41815b17d8fb9c685f97e243', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('9271d8d6c9641f4b', 'client', 'LEG', '64c20879dfdb17bb2204defac4df1c518b5cd334', FALSE, 'PcLabels · Tr')
  , ('7ec243afa6b98d4c', 'client', 'LEG' || chr(4) || 'pc.band_short.legendary', 'c6a9c96cb8174d0b9f19c77d3b995f4378193034', FALSE, 'PcLabels · Tr · pc.band_short.legendary')
  , ('73dbfda49aa9e141', 'client', 'LEGENDARY', 'fa240458b36c45fa0aa898bdc7db88eea9875b13', FALSE, 'PcLabels · Tr')
  , ('ba7076d9a0d0c982', 'client', 'LEGENDARY' || chr(4) || 'pc.band.legendary', '10bf8b6de59d99ff0a57ea32b701bb11c7125f9f', FALSE, 'PcLabels · Tr · pc.band.legendary')
  , ('de20704300c6edfd', 'client', 'LEVEL UP!  Level {0}', '3a7f6bd064529d32665a9bfdacf161baab97a428', FALSE, 'ApiClient · ReportMatch')
  , ('683bcd6f2e8b0c87', 'client', 'LIVE', '6990f01ad9d2dd9bf6acbd5330b2a51dc97e62e5', FALSE, 'NativeUI · RefreshTournaments')
  , ('092b5f6f69738677', 'client', 'LMB', 'bdd2b2634fd3d1c82582c6d17bbf13f48f0f6b64', FALSE, 'InfoViz · BuildKeyboard')
  , ('db538c880f1cfde9', 'client', 'LOCK chat everywhere', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('fe55f5cffac7f3b9', 'client', 'LOCK: 2 total points', '43bbf6ddbbd6c835b405870a184d3714afa6b12d', FALSE, 'InfoViz · BuildBetWindow')
  , ('9d39ae971605ed24', 'client', 'LOCKED', 'da6bac2901375736cf9f663da7a9942169e4774f', FALSE, 'InfoViz · BuildBetWindow')
  , ('3c85c6b1e187fb93', 'client', 'LOCKED' || chr(4) || 'betting window', '92c5a22cba39cecfb28e19eab491c7bcfb365f26', FALSE, 'InfoViz · BuildBetWindow · betting window')
  , ('ad1e59715a6ba031', 'client', 'LOCKED - STARTING SOON', '826eff5d83a7f019b3d90ef265f759162f982ea5', FALSE, 'NativeUI · RefreshTournaments')
  , ('0938287c5f713cf1', 'client', 'LOSERS BRACKET: one winners-bracket loss drops you here; a loss here eliminates you', '1a8e5468168f7afe3c5ddf6cc716dbb6674d4cc5', FALSE, 'InfoViz · BuildBracketFlow')
  , ('bd5f6718ab6205d7', 'client', 'LOW', 'd8b9679fad55bd0178081bc796a093eec7fd845c', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('07ddf0eb2233d445', 'client', 'LOWER STEAM ID', '085c6d7c375032aee0da676b3f0a7b0f029d62ea', FALSE, 'InfoViz · BuildReportPipeline')
  , ('6ed5c362fa26d0ea', 'client', 'Ladders unavailable: the server could not be reached.', 'e160de41ef3015d6574da8e1ee36460f11695e94', FALSE, 'TitleLaddersUI · EmptyText')
  , ('4f1ef826c0752a64', 'client', 'Ladders unavailable: the server''s answer could not be read.', 'a72c57cace0fbfa6762128e848be0064747c685f', FALSE, 'TitleLaddersUI · EmptyText')
  , ('7ab177cbeb6ea07d', 'client', 'Ladders unavailable: this server does not serve the ladder route yet.', '6534f19eb354c4d16b04876745121a97ed415a60', FALSE, 'TitleLaddersUI · EmptyText')
  , ('7aeac17f502399de', 'client', 'Lag notices: <color=#88FF88>ON</color>', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', FALSE, 'NativeUI · PaintLagNotices')
  , ('02b8b22e38fd50f7', 'client', 'Lag notices: <color=#FF9966>OFF</color>', '252303c6d39a40dd7f036c76f80bb69f75ae36c2', FALSE, 'NativeUI · PaintLagNotices')
  , ('ac354c1e95bc9f0d', 'client', 'Lagoon', '24ebe978ab7453659552dbeb029bebba00495fe3', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb9133a629673eaf', 'client', 'Language & menus', 'e071ed1bfe1f30c0dfd9665a21b2ff1a5951c5c9', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('e9039fd4f6a491aa', 'client', 'Language / Idioma / Язык / Мова / Språk', '640dd4aaa45df7e6f11465d07dd43664017a2e9b', FALSE, 'NativeUI, NativeUI.Settings · BuildSettingsChrome, MaybeShowLanguagePrompt')
  , ('fb0725b41f178ef8', 'client', 'Language: <color=#88CCFF>{0}</color>', 'ce2864f02b751fa6f9f141839fa847756de688c5', FALSE, 'NativeUI · PaintLanguage')
  , ('da58a93eac39ac88', 'client', 'Last game for me', '92e69a3f1985413e1879f796e1558f0285185041', FALSE, 'QuickChat · Phrases')
  , ('75b4b05477f8d8c0', 'client', 'Last met: {0}  -  {1}  -  {2}', '09c8f45b288212b02726036d5becce603cfb6c57', FALSE, 'ProfileCard · Render')
  , ('645e3d3f657b13e7', 'client', 'Last played {0} · H2H {1}-{2} · Ranked series {3}', 'a3f322bfc21229baf76a1294517e9f556f824da8', TRUE, 'H2HSummary · BuildLine')
  , ('adce3a775476d686', 'client', 'Last played {0} · also played today · H2H {1}-{2} · Ranked series {3}', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', TRUE, 'H2HSummary · BuildLine')
  , ('b787becd085c029c', 'client', 'Last seen {0}', '625e31be269df28853a13df859f62ab7c71a841f', FALSE, 'ProfileCard · Render')
  , ('777608da05a9cc4a', 'client', 'Latest Releases', '53cd5d1778decb934a189c78a5655d1a89e0b9a2', FALSE, 'NativeUI · BuildHomeTab')
  , ('c5768a1032dce392', 'client', 'Lavender', '75c88f3a0072cbd028982b65a0fcf2db0c4a5b15', FALSE, 'shop catalog · cosmetic name/description')
  , ('bd8b0169d8b34641', 'client', 'Leaderboard', '0381247a698736fe9930328a814e5263eeff72fd', FALSE, 'NativeUI · (file scope)')
  , ('3da96878e7093b8b', 'client', 'Leatherback', 'c58a5949dd5262760ade6a40821cceef90525000', FALSE, 'shop catalog · cosmetic name/description')
  , ('317d4929f4752d06', 'client', 'Leave', '7e3520a9733111c30f7ea9191099a8c7d144a4d8', FALSE, 'NativeUI, SpectatorHud · BuildFfaTab, DrawLeaveMenu')
  , ('8e9e659354925cdc', 'client', 'Leave All Queues', '0079a58339aa6045be471f8a0850cdbdbe1ee2b9', FALSE, 'NativeUI · PaintActionRows')
  , ('0cc384f0712b97cb', 'client', 'Leave Lobby', 'b9b062ac708c22c87b3d7c39fdf795e7536aaa1e', FALSE, 'NativeUI · BuildOneVTwoTab, BuildTeamTab')
  , ('5f180b79d0ac42fa', 'client', 'Leave Queue', '38c987b3019663c25cb284dbb39be1249e4505be', FALSE, 'NativeUI · BuildOneVTwoTab, BuildTeamTab')
  , ('5d98387d164dafd9', 'client', 'Leave Signup', 'b184a204463eaea71321073fcd40120e63116faf', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('0b5dc7250d46a753', 'client', 'Leave it open', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('0d05a0ee7f392081', 'client', 'Leave this competitive match? Click again to confirm. Standard disconnect and early-leave rules apply - this is not a guaranteed forfeit.', '671b7f7e4974e37ade6d2c6f72a8413565573f3d', TRUE, 'EscLeaveRow · OnRowClicked')
  , ('36871896766f51de', 'client', 'Leave your 2v2 lobby first.', '470b8d159bd13faf0cdd9899ee136ca7b5674a31', FALSE, 'ApiClient · JoinTeamQueue')
  , ('54cce0f779303fff', 'client', 'Leave your current game first.', '62820e3a31c40e97fa8a7a30023f6f103d6ec56a', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('b9f849c45fd22952', 'client', 'Leave your custom 1v2 lobby first.', '3a727fff861b715551b3e0a3e3daee8d433363a2', FALSE, 'ApiClient · OvtJoinQueue')
  , ('087f3bb9c052fdf8', 'client', 'Leaves every queue this client believes it is in - ranked, casual and tournament - and clears the local queue state with them. It is safe to press when you are not queued.', 'cfb9bd3cdf1d880a553b6fd506eae95d81f5503c', TRUE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('73dbf9f880098214', 'client', 'Leaving queue...', '02dceaeb2b12aa88ec87fcbae1520e6f97dd1690', FALSE, 'NativeUI · RefreshQueueUI')
  , ('9b6641950ac77280', 'client', 'Leech', 'c92a20f9bc034746337b301c52a0e08f967ed17a', FALSE, 'shop catalog · cosmetic name/description')
  , ('7193e2d43f8462f7', 'client', 'Left 1v1 queue - you joined a game', '2aa0b0b1a20afa22143208aeebcc1c6c787453c4', FALSE, 'GameStateWatcher · PollRoomState')
  , ('c762a5a91802523f', 'client', 'Left Alt', 'c689a8e45c1c59efab92c7e7aa90defed54fa770', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('a2b2dbca7b166e73', 'client', 'Left Arrow', 'a0c4aa9c174b958917c7fde075d0df5542ecdee1', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('3722d4a5ea342929', 'client', 'Left Command', '3d06de2a7f925bb802ecb2344c73def88e05b920', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('51a1f0e744817494', 'client', 'Left Control', '746d71213bff17974ab991c61e667ebaf3194b6c', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('4d0eadfb8a10738a', 'client', 'Left Mouse', '5b0cd37a669bd3e5e7ef26df256c74086a09d266', FALSE, 'NativeUI.Keybinds · KeybindMouseName')
  , ('5dacc6c5242eba74', 'client', 'Left Shift', '494064e70529e54389ad678d759801779c5c72df', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('0443b0ff598772c5', 'client', 'Left all queues', '2336614c4008f5eaa1e5ed653494422d528620a1', FALSE, 'ApiClient · SendEscapeRequest')
  , ('2871e3c4ddf170ce', 'client', 'Left the 1v1 match queue - you joined a game', '452d97bc5ef6822c153b1404472aed1ce172d54d', FALSE, 'GameStateWatcher · PollRoomState')
  , ('2c43f20e3923bb38', 'client', 'Left tournament signup', 'b073357d5e9db54d87493c1c4f5787a3a9747a53', FALSE, 'ApiClient · TournamentUnsignup')
  , ('41d1c5a37795be68', 'client', 'Left your FFA lobby - you joined a competitive game', '76b21b7b1f5ea9e9b18f11b00e148fc98d09c54d', FALSE, 'GameStateWatcher · PollRoomState')
  , ('22d09513ec88a817', 'client', 'Left your game to join the queued match - no leave will be recorded.', 'a2c2f1934a27f01d835e8aae8fedba25a5432737', TRUE, 'GameStateWatcher · PollRoomState')
  , ('61704fa740093a1f', 'client', 'Legendary', 'b7e8916505bf72d3bbd637339087c4847e386b67', FALSE, 'PlayerCardsUI · RarityLabel')
  , ('2130d9c2eb9e3c76', 'client', 'Lemon', '4459b791a680572873dc2cf033487dc21edfcb9c', FALSE, 'shop catalog · cosmetic name/description')
  , ('c7acaba68380efc4', 'client', 'Less than 5', '9a1e0ba477c9917763fccc9703a1615fc7825a19', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('bc73b248f0e1b359', 'client', 'Lets others see which cards you hold, in the mod and in Discord.', 'cf0f814cc1ca088eb3f1bbd204d0f2d28e25a258', FALSE, 'PlayerCardsUI · BuildSettingsRows')
  , ('ac71054abd96ce73', 'client', 'Level 1', 'f25d3c50abaee5db733fdf971a931d354780082c', FALSE, 'NativeUI · BuildMyStatsTab')
  , ('2bef0e5cdc0b94f1', 'client', 'Level {0}', '8051c09f7c6dfc8c86a8ea94b528253ae4137333', FALSE, 'NativeUI · RefreshLeaderboard, RefreshMyStats')
  , ('b4bae31e5af0891d', 'client', 'Level-ups', '047c66202cfc53f93a8901d3d5f5e13c724815fa', FALSE, 'InfoViz · BuildGoldSourcesLegend, GoldBucketName')
  , ('859c6f6fe59feab5', 'client', 'Leviathan', 'd5f1a124562ec36f2cf24f1ce284053b2b3877db', FALSE, 'shop catalog · cosmetic name/description')
  , ('a204547475823743', 'client', 'Life steal', '417f106adb9eb8a88f7f754dff056d4ad92f62fa', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('d9d65e5bcdfa2dac', 'client', 'Lifesteal', '57239ad99b94977b15b6bb55498ff295eb205f8a', FALSE, 'InfoViz · BuildDamageMatrix, TextFallback')
  , ('7ba5966da993cde6', 'client', 'Lifestealer', '55eaa50fa4df7333818fd42fe415eb4c9b815d38', FALSE, 'shop catalog · cosmetic name/description')
  , ('ec0db0eef9a77b84', 'client', 'Lifetime totals for your account, from the live server. The rules behind each source are in the article below.', 'fef54a0228deda825b33fcb615fc718603b433b7', FALSE, 'InfoViz · BuildGoldSourcesChart')
  , ('5431d62eb89eb032', 'client', 'Lifts your nametag a fraction above its baseline so it appears to hover.', '647b0df3eb0dc7b333f9063728d3b2e3785878de', FALSE, 'shop catalog · cosmetic name/description')
  , ('1abd5ec48227f969', 'client', 'Lightning', '4504e5f0bfccb6e4bd7b024114abe16f9a1e02d2', FALSE, 'shop catalog · cosmetic name/description')
  , ('e731de0c1b6ad2f0', 'client', 'Lightspeed', '10c2ab251935320bb0f9bce995acc19766b706bc', FALSE, 'shop catalog · cosmetic name/description')
  , ('a59a55265cfb11eb', 'client', 'Lime', '7e845d62d2ff38633cd16021f0b03eb78640abe0', FALSE, 'shop catalog · cosmetic name/description')
  , ('15452feadbac32bc', 'client', 'Link code: {0}', 'd5cc324443a8277d639cfc7dc37ca9a42af3ce3c', FALSE, 'ApiClient · GenerateLinkCode')
  , ('0334124c315ddfdb', 'client', 'Link codes are disabled on the broadcast seat.', '275b7baf4f13ac034f94fad11c497b83c09a0630', FALSE, 'ApiClient · GenerateLinkCode')
  , ('986b75b09a88bcc4', 'client', 'Link your Discord account first (Home tab) to use RLFP pings.', '9a079643ddf3158131c3009521073761bd7ef4fa', FALSE, 'ApiClient, NativeUI · OnLfpButton, SendLfpPing')
  , ('af20dfcde4e40158', 'client', 'Link your Discord first (Home tab)', 'f3168e1294a51faf76e336c00dde31bf9be8684e', FALSE, 'NativeUI · BuildSettingsTab')
  , ('601b9722aee970a1', 'client', 'Link your Discord first: Home tab -> Get Link Code, then !link YOUR_CODE in Discord.', '5f4e4bf17d1089e02d21c219e972c8a58f83dda1', FALSE, 'MailUI · SetMailRelay')
  , ('9a4694be890d8a2f', 'client', 'Lists players who have not run the mod recently on every leaderboard, greyed and tagged (inactive).', 'd9f50ba23a933f8c7100258c8a9391e05f0c1771', FALSE, 'NativeUI · BuildSettingsTab')
  , ('3b4605576de92799', 'client', 'Little Pink Buddy', '0582db7c610c15142547997e9e2b19457eef92cc', FALSE, 'shop catalog · cosmetic name/description')
  , ('307edf185126fbce', 'client', 'Live competitive games in every mode can be watched from inside the mod - ranked 1v1, 2v2, 1v2 and FFA (ordinary casual 1v1 rooms aren''t listed). You see the real game, live, from a seat that is built so it cannot touch the match.

<color=#FFD94D><b>HOW TO WATCH</b></color>

- <color=#7FD4FF>WATCH</color> buttons appear on live-game rows across the F5 menu: the Leaderboard''s live series strip, the FFA tab''s live lobbies, the 1v2 tab''s live panel and the Home tab''s live rows. You never see WATCH on your own game.
- Clicking one puts you into the real Photon room as a non-playing seat. You can''t start spectating while you''re in an online room or mid-queue.
- A game is joinable while its fighters are in live combat, a spectator seat is free, and every fighter allows spectators.

<color=#FFD94D><b>WHAT YOU SEE</b></color>

- The true live game - real movement and real projectiles, not a replay or a delayed feed.
- The screen stays black until the first clean round boundary, then the game appears in sync. If your client ever has to catch up mid-round, you see the live scene with a Syncing note instead of black.
- Card picks are visible, and every round boundary carries everyone''s full decks. In FFA you see pick results and decks, not each picker''s private hand of candidates.
- A minimal top bar shows the score and the fighters'' names, titles and ratings. Hold {0} for the stats board. Chat works (and can be muted). Esc opens the leave menu.

<color=#FFD94D><b>WHY A SPECTATOR CAN''T TOUCH THE GAME</b></color>

The spectator seat is an observer by construction, not by politeness:

- <color=#7FE87F>It cannot deal damage or cause a death.</color> A seat-wide clamp makes the death branch unreachable from every damage path on that seat - the deaths you see happen on the fighters'' clients and only render on yours.
- It cannot spawn a player, ready up, or take a slot - even the press-jump-to-join prompt is suppressed.
- It never answers or sends the sync-up requests fighters use to stay in lockstep, and never reports map loads, so it can''t slow or desync the match.
- It cannot pick cards and runs none of the game lifecycle - it only applies the scores the master broadcasts.
- It is invisible to every fighter count: quorum checks, reporter election and match-start counts all exclude spectators.
- <color=#7FE87F>A spectator leaving never ends the fighters'' match.</color>

<color=#FFD94D><b>PRIVACY, COUNTS AND LIMITS</b></color>

- Fighters always know: every seat in the room - fighters and spectators alike - sees a bottom-right Spectators line with names while anyone is watching, and the games list shows spectator counts publicly.
- <color=#7FD4FF>Allow Spectators</color> is a per-player toggle in F5 Settings, on by default. If any one fighter in a game has it off, that game can''t be watched - and the reason shown is generic, never who opted out. Flipping it off mid-match removes seated spectators within moments.
- The one exception: sync tournament matches are always spectatable.
- Public spectator seats cap at 4 per game, and one extra seat is reserved for the official broadcast account that runs the community stream, so public spectators can never crowd it out. A full game answers ''spectator full''.

<color=#FFD94D><b>LEAVING, AND BEING RETURNED</b></color>

- Esc, then leave. Leaving never disturbs the match - your name just drops off the Spectators line.
- Your seat is a lease your client refreshes every few seconds. When the game ends or a fighter opts out, the lease ends and you''re returned to the menu automatically. <color=#7FE87F>A network hiccup never kicks you</color> - only a definitive answer from the server does.

<color=#FFD94D><b>SPECTATING AND BETTING</b></color>

- Spectators can bet. The early bet-close windows are the information gate: 1v1 and 2v2 bets lock once 2 points are scored in game 1, and FFA bets lock once 2 half points are scored in the game being bet on (earlier in short lobbies) - so a lingering seat learns nothing useful before the window shuts.
- The only barred group is a lobby''s own members: you can never bet on your own lobby.', '32548b3ebc8e99367006ec47c93c11643cfb4b04', TRUE, 'InfoLibrary · (file scope)')
  , ('a48e13d370e30ad1', 'client', 'Lives', 'ce6afbd4b60bf8dfe8e4a2a6327ac8598e740559', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('a2667beef62b6d0c', 'client', 'Living on the Edge', 'ece6bccb7dadb22b3b86139b68efb42a8ea3c7c1', FALSE, 'ApiClient · AchievementDefs')
  , ('dca0e950beda5275', 'client', 'Loading achievements...', '1fd2394cf3947091a4cce007bdc3ba63bac85efe', FALSE, 'NativeUI · BuildCompareAchievementGrid')
  , ('a4fe34ab4908634e', 'client', 'Loading music ({0} of {1} ready)', '9f70dc8f53163d9a15ca78ac3ef031d6577aa6d0', FALSE, 'MusicEngine · MusicStatusLine')
  , ('963e1688108c8e04', 'client', 'Loading music ({0}%)', 'd5fc55fa69fbb26b458e4848d46af7d19dbecce6', FALSE, 'MusicEngine · MusicStatusLine')
  , ('7b1f1233cd6900a1', 'client', 'Loading recent series...', 'a47ce0315faa83adea0805be565fd26648ba3f45', FALSE, 'NativeUI · RefreshRecentSeries')
  , ('d32d128d5ac713ea', 'client', 'Loading shop sales...', '9757b29440e4b4ef49e94e10094e5706dbe5cb93', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('4567acb803377649', 'client', 'Loading the reviewed cosmetic...', '835607ccc7a2843df2fea8d0f4b416f9c91b1195', FALSE, 'NativeUI · StartCosmeticPlacementAdjustment')
  , ('82454078ed3cc3f4', 'client', 'Loading your binder - try again in a moment', 'f4b5a7167d697c4f6fc1a46262b7df5b11d92e6a', FALSE, 'PlayerCardsUI · OnQuickShardClick, OnShardDupesClick, OnShardPackClick +1')
  , ('c3b275ac7a9a2616', 'client', 'Loading your binder...', '5a8772427089665e23083fc67088ce16ed8028e2', FALSE, 'PlayerCardsUI · RefreshBinder')
  , ('055b09b71c37a3fd', 'client', 'Loading your card...', 'cbda8c4ca3faccb0cf34064561ec9729b1da0219', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('f7dbb7c4e800e30a', 'client', 'Loading your dances - try {0} again in a second.', '1ee7469705bf8cf565fe31a6f650293922a9c814', FALSE, 'CompetitiveUI · DrawDanceWheel')
  , ('24ee38ca3359c5af', 'client', 'Loading your dances...', '13c6b6b00c3614b65f1771cc1931a92b759891be', FALSE, 'PlayerCardsUI · DanceOptionIds')
  , ('ffbcc4a35c38478e', 'client', 'Loading your packs...', '06763d5bb728c2a48d3cb2d365737b30c614e598', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('3076a1f4dd6e2b2c', 'client', 'Loading...', 'b04ba49f848624bb97ab094a2631d2ad74913498', FALSE, 'MailUI, NativeUI, PlayerCardsUI +2 · BuildCompareCardLeaders, BuildCompareCardMetric, BuildCompareCardPickers +25')
  , ('97e7da3462d79fea', 'client', 'Locked', 'a798882f1c31099bb9500e2da62c0874d8dbed78', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('c731a1c891e2ba81', 'client', 'Locks the map to ROUNDS'' Gold palette (warm yellow).', '7ecb9e49219df7f9e2fafd4f4cd75eb164d24290', TRUE, 'shop catalog · cosmetic name/description')
  , ('d9f0ab270fa95deb', 'client', 'Locks the map to ROUNDS'' Poison palette (acid green).', '1ca68d13c18e8e434805d0a510762510ca601ac1', FALSE, 'shop catalog · cosmetic name/description')
  , ('26d766cf70a26dd6', 'client', 'Locks the map to ROUNDS'' Rainbow palette.', '9ae747eccb6b6170ae4f18896e498142e45387f4', FALSE, 'shop catalog · cosmetic name/description')
  , ('77501ba1887630dc', 'client', 'Locks the map to ROUNDS'' Sky palette (light blue).', 'e07f293196ef7e0937ab9343b1984c5ffaf4e71a', FALSE, 'shop catalog · cosmetic name/description')
  , ('5215a7389616213e', 'client', 'Locks the map to ROUNDS'' Soviet palette (deep red).', '2dc9a74a3d4c4d4552153339ca5aaf59af7a8a61', FALSE, 'shop catalog · cosmetic name/description')
  , ('a499e490a762a41a', 'client', 'Locks the map to ROUNDS'' Sweden palette (blue + yellow).', 'c2cb065aefa60150ca2e076e295363c45308b3d6', FALSE, 'shop catalog · cosmetic name/description')
  , ('a090731f328fec57', 'client', 'Longest Game', '9f9866e25ae0c78618b9d28c4e7701da2631fbfb', FALSE, 'NativeUI · RecordBoardHeading')
  , ('fe940716b31734b3', 'client', 'Longest game', '62a0c4924d330166bb16d5e0503902b7dc35e561', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('27fc725cf87d905b', 'client', 'Longest point streak', '689f66917a28e83ae4a3904a20b08a7b2275778a', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('72fc87c339c9fc3f', 'client', 'Lose a ranked FFA holding 10 or more half points that never became a point', '9843b00eccc4fb151913c11e40b8acb9dd2398d7', TRUE, 'ApiClient · AchievementDefs')
  , ('28ade4ed4e32aabe', 'client', 'Losers', '6ce79956bdb35a2d91a54cbcd83332de043345d7', FALSE, 'NativeUI · RefreshTournaments')
  , ('3d543a9f607705b1', 'client', 'Losers R{0}', 'd57af112c7754e18d43ae882aba476823b4f8b78', FALSE, 'NativeUI · TrRoundLabel')
  , ('c406b8b7f5981a4d', 'client', 'Loss', '12e24a7d8ac40579e8a0aef4869288afe7ed6745', FALSE, 'ProfileCard · ResultName')
  , ('80c96a889f9f5af9', 'client', 'Lost', '75a7bf994e9ac1b9d14062213673cc0a85729869', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('0c996f453fd078f8', 'client', 'Lowercase letters render as smaller capitals.', 'a47242e6772160f53510181c157f8401003ae798', FALSE, 'shop catalog · cosmetic name/description')
  , ('a440e688422991cd', 'client', 'Luckiest (rare draws)', 'b9fbb3878b6d5de8e427243a660bb4e3940c0985', FALSE, 'NativeUI · RecordBoardHeading')
  , ('a28f48411a5bcb0c', 'client', 'Lucky Clover', '939ab68bfd22b3400b502c8401ff4be78f05031e', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb4037a9f3bbf1a3', 'client', 'Lucky Coin', '8ac4bdca240a00d1d6e951be2f2c6a56c23f1fd6', FALSE, 'shop catalog · cosmetic name/description')
  , ('bffaa52506c86556', 'client', 'Lucky Ears', '92c0c56a90c4346196b1221605638694fbc876e4', FALSE, 'shop catalog · cosmetic name/description')
  , ('0bc4ff39724d6896', 'client', 'Lucky green clovers tumble around you.', '9fa8c9a61e28dd229fc118d6c8e04e77a7a2a087', FALSE, 'shop catalog · cosmetic name/description')
  , ('acc86de9b59c25db', 'client', 'Lumberjack', '32ed08835c994efa3c32d263129bb8a259d54463', FALSE, 'ApiClient · AchievementDefs')
  , ('efc2f9902bbd8f88', 'client', 'Lv {0}', '921f739afc4507740d70462d75a775f0b1de78a3', FALSE, 'NativeUI, ProfileCard · BuildCompareBarChart, Render')
  , ('70ea7889f7bbb8aa', 'client', 'MATCH FOUND!', '11a9c89722334e53865de12f16e44151a6372071', FALSE, 'NativeUI · BuildRankedRow')
  , ('dd9ed6335db7e352', 'client', 'MATCH FOUND!  vs {0} ({1:F0})', '8d42a8ff760a17a66d663d7b77b0ee840976a372', FALSE, 'ApiClient, NativeUI · RefreshQueueUI, UpdateQueuePoll')
  , ('674dc4e5522d0f23', 'client', 'MATCH POINT - {0} are half a point from the win!', '1e5d0858e09b08bab630a076267ce09e581733d9', FALSE, 'CompetitiveUI · RefreshFfaMatchPointBanner')
  , ('9f1e5c442c451f91', 'client', 'MATCH POINT - {0} is half a point from the win!', 'c9f79b176fc44a3c38255b25082c7f51e315190f', FALSE, 'CompetitiveUI · RefreshFfaMatchPointBanner')
  , ('5ad4a639068aef1c', 'client', 'MATCH STATS  <color=#888><size=12>(hold {0})</size></color>', '941068397def1de6502ab26d55c4893dbae32c04', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('11a8ce3b24581f0d', 'client', 'MAX', '7b186e235f284107df6b4dbe6060d2b6a5d9f1e5', FALSE, 'NativeUI · RefreshMyStats')
  , ('84ed7380201d44df', 'client', 'MEDIUM', 'f68525ad751f8a1d932458c4c58a214bdf0b30e9', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('064556c685e85780', 'client', 'Machine translation - corrections welcome in Discord.', 'fb72a3491dd3efb40c0d57730cd453bc9d827b78', FALSE, 'ApiClient · ParseFullReleaseNotes')
  , ('cbea0bc6281f33a2', 'client', 'Machine translation - the English notes are on GitHub.', 'e2ae05adfe58ad36b43154dad1a22d319d314df9', FALSE, 'ApiClient · DoFetchReleaseNotesOverlay')
  , ('d20df8f73196964a', 'client', 'Magical Hat', '2264719fbd4ee4267ba4f0518eff40062ee2c222', FALSE, 'shop catalog · cosmetic name/description')
  , ('61abcf4400fd7a42', 'client', 'Magma', '3548c9250892c509047e2c7ec04d76bf39c63524', FALSE, 'shop catalog · cosmetic name/description')
  , ('28cbbcc2706cca77', 'client', 'Mail', '92379cbb8ecf696194b47b619a87e9e4f9a75db2', FALSE, 'MailUI, NativeUI · (file scope), BuildHeader, TabLabel')
  , ('7eb30f41f4540f2b', 'client', 'Mail ({0})', '9119f6e8e1e6380ce9ae6abc7eba8196a1e5cd41', FALSE, 'MailUI · TabLabel')
  , ('b7155d1c23b36e80', 'client', 'Mail needs a secure connection to the server - it is unavailable on this connection.', 'e431694e93597eafe1c43c5938ed4e70152f7e96', FALSE, 'MailClient · ErrorDetail')
  , ('6edb1352e795ee14', 'client', 'Main menu music: Default = ROUNDS'' own theme, My playlist = your selected custom music, None = silence. Matches always use your picks.', '5fb0b4362428b56ff9d74047337ff4f264be5e21', FALSE, 'NativeUI · BuildSettingsTab')
  , ('95e880d9ec642215', 'client', 'Manage your cosmetics and earn 30% on each paid purchase - gifts and your own buys pay nothing. Size or placement changes return to admin review; unsuitable art may be rejected or adjusted.', 'abf0c9e2bd591cf88dfd596663185ee446929460', TRUE, 'NativeUI · BuildArtistTab')
  , ('e2b1e7177aa1f43b', 'client', 'Manual restoration marked complete.', '357c98d97ceb16fd653205ebffc3a150b4f65503', FALSE, 'CompetitiveUI · SubmitFlagRestorationComplete')
  , ('f5216c8d2d977f17', 'client', 'Map color schemes. Equip as many as you like and cycle between your owned colors with {0} in-game.', 'e2fccafb2075f6e0baa5011619feca7e1636f2ff', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('62017cfb23dc8d2b', 'client', 'Map lighting: <color=#88FF88>ON</color>', 'f9cdd3d419e43beb090cc154a41152fc7693148f', FALSE, 'NativeUI · PaintMapLighting')
  , ('289b33714e60ffc7', 'client', 'Map lighting: <color=#FF9966>OFF</color>', '253205f4630eeabef874bba5179933fc2284c0d9', FALSE, 'NativeUI · PaintMapLighting')
  , ('7360e52eca7e232d', 'client', 'Map lighting: the light and shade the map is drawn with. Off = flat, evenly-lit maps for extra FPS.', 'b9654a7b502b417a86b62f424f8d295435911770', FALSE, 'NativeUI · BuildSettingsTab')
  , ('f191cfa21f829bad', 'client', 'Map shadows: <color=#88FF88>ON</color>', '56b5171f1b34b209c2562ac1138f47cba321d54a', FALSE, 'NativeUI · PaintMapShadows')
  , ('1da67081596a4e36', 'client', 'Map shadows: <color=#FF9966>OFF</color>', 'aea9c61229fe7166c9df86c5df526bf39f4d5312', FALSE, 'NativeUI · PaintMapShadows')
  , ('9922109749d1c0e7', 'client', 'Map skin cycle', '4191ab33cd5ddde520e2629fb0ee67403a9dcf24', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('fddf3191109ad367', 'client', 'Map skins', '3f5e663ffe95270650b331c4256b3a81fbff7c68', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('db64d34801d9c8ef', 'client', 'Maps', '80071cd75107cd5c4afdb2571725ea6733631038', FALSE, 'NativeUI · (file scope)')
  , ('c0b1c898d81f830c', 'client', 'Marked false positive. You still need to repair the rewards and series by hand.', '8605f969b685627b504e2187118f04a140ae4590', FALSE, 'CompetitiveUI · SubmitFlagEvidenceVerdict')
  , ('2851ddecff9316db', 'client', 'Marksman', 'e7361836c8cf99f006c3086427925af7c11c4034', FALSE, 'shop catalog · cosmetic name/description')
  , ('77f5fa96a313fa19', 'client', 'Maroon', 'ca6ebdf49e3b17cc5b9a43d5ab6a00aef37e3a3f', FALSE, 'shop catalog · cosmetic name/description')
  , ('9643b3e6281b9dcc', 'client', 'Master', '78f3842f0201c993fec13905f2ff9ec3fdd39056', FALSE, 'ApiClient, InfoViz, NativeUI · AchievementDefs, BuildRankLadder, PerfRowLabel')
  , ('0c5fd3f91a3e6cd0', 'client', 'Match canceled (disconnect)', '6b674f19d542a98d03f86b68a07fa3979a3dcf26', FALSE, 'GameStateWatcher · PollRoomState')
  , ('2b45ba05db9d02bf', 'client', 'Match canceled — searching again...', 'e26c6bb791ba1abe64e3a0009979a9e9ce23af69', FALSE, 'ApiClient · ParseTeamQueuePoll, UpdateQueuePoll')
  , ('ba02c82796b6e9ad', 'client', 'Match could not start — only {0} of {1} players connected. Leave to the menu to requeue.', 'a4b0d5dbc856f49bb8c060ac21ce0a9bb60889df', FALSE, 'Plugin · ShowGuardToast')
  , ('4eaef20c9ab4733a', 'client', 'Match dissolved — searching again...', '2f68bce432d93decf76a67e3a6754234cb64338a', FALSE, 'ApiClient · ReadyUp')
  , ('41d9050b657c7a9c', 'client', 'Match interrupted - the connection to the match server was lost', '7db172eae8b52e7b324383a179cfb94c9b827f3e', FALSE, 'GameStateWatcher, LagNotices · PollRoomState, TransportSilenceLine')
  , ('8730307706a420b3', 'client', 'Match recorded', 'f30dff73c6d29fd03731fcf0d22aee0f7b19ab52', FALSE, 'ApiClient · OutboxPass')
  , ('2067d849636de5c3', 'client', 'Matchmaking hiccup — putting you back in the Quick Match queue...', '8e5941f5a7de20463239bacbbce5329c3a54bcb6', FALSE, 'GameStateWatcher · FireRequeue')
  , ('5ef4114e5d236a69', 'client', 'Matchmaking keeps failing - returning to menu. Please try again in a minute.', '0fefb03e0915bf2eb7ff03cc56f927fc0efb5d5e', FALSE, 'GameStateWatcher · FireRequeue')
  , ('d3b7f9d9c9b6c4e4', 'client', 'Max cards:', '63168ee6a276883f20338ce8d90a19f0d972d8bd', FALSE, 'NativeUI · BuildFfaTab')
  , ('4234e8415df49e3c', 'client', 'Max {0} cards', '4a6c6c9a7c4691e7c475ce41f0a53dcc7401d0d2', FALSE, 'NativeUI · ToggleCompareCard')
  , ('8f901a543698298d', 'client', 'Max {0} players', 'fe604db7833da029b6d91b9e285ed91762c30526', FALSE, 'NativeUI · ToggleCompareSelect')
  , ('08cc30f4a1e380ad', 'client', 'Maxed', '9ca3a3865ed214014be5c1505935c16c6341336a', FALSE, 'TitleLaddersUI · ActionLabel')
  , ('12beec54b709ec7d', 'client', 'Mayhem', '407ca2780abce79d9e04b6f64282d3edddd8e3d5', FALSE, 'shop catalog · cosmetic name/description')
  , ('3451911e7001cca2', 'client', 'Megalodon', '51281a124c61a81435f7568dca63b51728546207', FALSE, 'shop catalog · cosmetic name/description')
  , ('49bbf9869d36cfe1', 'client', 'Menu', '57f5f5efbc5990f5230aa95359042338b856707b', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('492e7a1185b61208', 'client', 'Menu music: <color=#88CCFF>Default</color>', '932268f69f8abd8f78fcb54324acbb153db7695f', FALSE, 'NativeUI · PaintMenuMusic')
  , ('d7d5fc77fbb32d5f', 'client', 'Menu music: <color=#88FF88>My playlist</color>', '798a99d1d8ff14b5e88ac1facc0ac563d5377c0d', FALSE, 'NativeUI · PaintMenuMusic')
  , ('cbc8740b1695a190', 'client', 'Menu music: <color=#FF9966>None</color>', 'af1789e79d5ee6ea9fa8d5ec234ff48c8db3e8b9', FALSE, 'NativeUI · PaintMenuMusic')
  , ('32ef039ee20872b3', 'client', 'Menu update bail', 'ea6dfcad0bbb0197cc432580a763bdd37c55ef73', FALSE, 'NativeUI · PerfRowLabel')
  , ('2d22d53c0db971c0', 'client', 'Message (shown to every player)', 'fc0146814b0200189b4f3f9a58bc78b79468d526', FALSE, 'NativeUI · BuildAdminTab')
  , ('1e52aed7fca8a685', 'client', 'Midas', 'c7e4e114997188bbd97b7fab1b85eecfed1376c7', FALSE, 'shop catalog · cosmetic name/description')
  , ('105175e8010d474c', 'client', 'Middle Mouse', '4c7bdd811c9f29e0a97915739754b68dc6e5d6dc', FALSE, 'NativeUI.Keybinds · KeybindMouseName')
  , ('d453de367dadaf91', 'client', 'Midnight', '558287ddcc3557b09ec00ca17b3e4be7e6645858', FALSE, 'shop catalog · cosmetic name/description')
  , ('9dbeace378dd4e1b', 'client', 'Militia Man', '3b3b2afc3f0b1587e298a86559403fee7db4e4d0', FALSE, 'shop catalog · cosmetic name/description')
  , ('5aa6d8c6966b7d57', 'client', 'Mint', 'aaa70f58c89e39722304f18ce50db0b7bf8907e1', FALSE, 'shop catalog · cosmetic name/description')
  , ('c92f5f7bded0170e', 'client', 'Mirrored chrome with a soft shifting tint.', 'b6af76411b6d6bc9e35cd94b8b7ea98f83b14aaf', FALSE, 'shop catalog · cosmetic name/description')
  , ('f8e2ad57858a56f3', 'client', 'Mod controls', 'ed2905c870344322c3ed92500c8a303cb4b94f45', FALSE, 'NativeUI.Keybinds · BuildControlsRows')
  , ('b28c6095513b6482', 'client', 'Mod display language. Machine-translated drafts until community moderators review them — card text in matches follows ROUNDS'' own language setting.', '2f86234d58aeb5c42903f4860c359d45fe00fdf8', FALSE, 'NativeUI · BuildSettingsTab')
  , ('919db6b937f7e8de', 'client', 'Modded avatar', '7d964946d68e74c4cb1a91a2ee875e3635ccef54', FALSE, 'NativeUI · BuildSettingsTab')
  , ('87cee7810f684cca', 'client', 'Modded avatar: <color=#88CCFF>{0}</color>', '5ebe5e74f19b27b2bee2331433149dd17a066361', FALSE, 'NativeUI · PaintAvatarModded')
  , ('3f286ca1ae9708eb', 'client', 'Modded eyes, mouths and details are drawn by the mod. A player without the mod sees an empty slot where each one should be. This picks the plain preset for you in games where that would happen, and gives you your own face back when you leave.', '641fb99253912601ce797f7c7417ec40693d4451', TRUE, 'NativeUI, SettingsDescriptors.g · BuildSettingsTab, HelpBodyTr')
  , ('dce81dcc7010a8ba', 'client', 'Mode closed', '164d2918ea54906b674e3a5fb29c5c589cd268fb', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('6eac4ea23c0996dd', 'client', 'Mode: <color=#88CCFF>vanilla music</color>', '3fa1667ada7e05444855ca035afd6b2f5282594e', FALSE, 'NativeUI · MusicModeLine')
  , ('1152b9c31dbaa74f', 'client', 'Mode: <color=#88FF88>custom music</color>', 'cfe537a5f3289e5512190c65186f14dd08253154', FALSE, 'NativeUI · MusicModeLine')
  , ('9bb3752670ea25f8', 'client', 'Mode: <color=#DDDD66>loading custom music - vanilla plays meanwhile</color>', '69ed28b1105d8d9da2f97744cfa4365f1058cff5', FALSE, 'NativeUI · MusicModeLine')
  , ('6fde99ccb04c9464', 'client', 'Mode: <color=#FF8888>music error - vanilla playing (see log)</color>', 'a113da2015d647a799efb39468a15c241df25809', FALSE, 'NativeUI · MusicModeLine')
  , ('91d0e41ce8239cee', 'client', 'Mode: <color=#FF9966>menu music is set to None - change it in Settings</color>', 'd6be16ee6ad11c21c61667420b3ea858ce6fef2d', FALSE, 'NativeUI · MusicModeLine')
  , ('ce473d718d21724f', 'client', 'Mode: <color=#FF9966>stopped - press Play or Use vanilla music</color>', '4682e10052d183bd1b01ae10f9420e7a8baba6b2', FALSE, 'NativeUI · MusicModeLine')
  , ('7b3149fddf2edfb3', 'client', 'Mode: <color=#FFC8F0>previewing</color>', '06d49afa15d06ec94bfe72d56446e09c74d5962f', FALSE, 'NativeUI · MusicModeLine')
  , ('da6813ba66e8657e', 'client', 'Moderation', '28f3ebe279d7e2b400db6b5d769827993abc0a51', FALSE, 'NativeUI · UpdateTabBarVisual')
  , ('60a0927f3dfe3ebd', 'client', 'Modes', '79f5b225cffab11e22dc40b6f05abef1d33d1561', FALSE, 'InfoLibrary · (file scope)')
  , ('4f87758656255ee4', 'client', 'Monochrome', '1dda992b70d55b62ecc5e22ba264afe7a9f07d02', FALSE, 'shop catalog · cosmetic name/description')
  , ('0844884be994ab63', 'client', 'Month/Day/Year (US)', '037358024aa12328fac8d7804df79d1552816c63', FALSE, 'NativeUI · PaintDateFormat')
  , ('ca839ea4c25f9069', 'client', 'Moon Rabbit', 'b32d80c3054361f2f427ee1da511b65d9d8d3f38', FALSE, 'shop catalog · cosmetic name/description')
  , ('5d29024a4d44289a', 'client', 'Moonlit', '3568c7491babebb953c769947cc8f490da802f47', FALSE, 'shop catalog · cosmetic name/description')
  , ('f603297ac334cf12', 'client', 'More', '4bab2d8fe13fa6ab57f80098b414f0f734c5dd25', FALSE, 'MailUI · PaintList')
  , ('53fc58107ad3018e', 'client', 'More ranked than not.', '6938f3389402f793e6adddb682e3586aec57a2e4', TRUE, 'shop catalog · cosmetic name/description')
  , ('14a19ff455d8ab87', 'client', 'More than 10', 'd5e82416a4a915e30ac4f2873b98cfb88c71bd55', FALSE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('42453248177629c2', 'client', 'More...', '3c25ce154a917b9c1539c47ac2d217ea7f6b9cf5', FALSE, 'CompetitiveUI · QcLabel')
  , ('8c9ef1e7f0a13ff1', 'client', 'Moron', '33239c50b8d4cac0112d31ea33f4850d59f7e0eb', FALSE, 'shop catalog · cosmetic name/description')
  , ('67a6d0f456b16987', 'client', 'Moss', '752fbb36578511afe3527c40c95abe3e1f95d7bd', FALSE, 'shop catalog · cosmetic name/description')
  , ('4813d16325219e3b', 'client', 'Most 5-0 sweeps carrying these cards (casual + ranked)', '7cdfe78ce185ab16eb859aa0ec1cf81fa1a15ac7', TRUE, 'NativeUI · BuildCompareCardLeaders')
  , ('81104076ee39cd42', 'client', 'Most Similar Player', '62f6ac59d2ee7076a358664caf080ea992984f56', FALSE, 'NativeUI · TrMetric')
  , ('cca48f0cfd3864b2', 'client', 'Most Stacked', 'c2a50d949d2b8b52c35753dee3c405940bad2ac2', FALSE, 'NativeUI · TrMetric')
  , ('8125b4c23514f88c', 'client', 'Most Used Cards', 'c785bd2edb589625206e301b8e713e1720cbdcec', FALSE, 'NativeUI · TrMetric')
  , ('d35f4660f0bbfa40', 'client', 'Most similar players', 'e587b0c4eec7778f4fbaca2fb50ebd61a8281422', FALSE, 'NativeUI · BuildCompareSimilarPanel')
  , ('25c0e9b2f1f58bfc', 'client', 'Most wins carrying these cards (casual + ranked)', 'eb6ba65224fddbc1c969f37bc2b49e0744e4fef5', TRUE, 'NativeUI · BuildCompareCardLeaders')
  , ('2e4c76cb16213d58', 'client', 'Most-played ranked opponents', '7614bdc150cf8a7517747f76f15db5a13cc3aa57', TRUE, 'NativeUI · BuildCompareGenericPie')
  , ('39a9fd7c9aef944d', 'client', 'Mouse', '573dd2c2ed953b97e3c31f3090925fe92109b779', FALSE, 'InfoViz, shop catalog · BuildKeyboard, cosmetic name/description')
  , ('ad153b3d04546400', 'client', 'Mouse {0}', 'a57757f0acf6fb801882c13f2be07f446d1b53a7', FALSE, 'NativeUI.Keybinds · KeybindMouseName')
  , ('291ff30d5079e949', 'client', 'Mouse-cursor color tint (local-only). Pick the cursor SHAPE — arrow, dot, crosshair, circle — in Settings; the tint colors whichever shape you choose.', '9cf80338abce8b567d68f64cfdbc22acaed2d62c', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('44296b8aa369d553', 'client', 'Moustache', '3d934064bc875a99085c8782d09dde442c97d696', FALSE, 'shop catalog · cosmetic name/description')
  , ('1d0c46aee85e3de7', 'client', 'Mouth: a distinguished handlebar. Equip in the Character editor.', '7f2f10fba7859343ca2963aa166a642641709abe', FALSE, 'shop catalog · cosmetic name/description')
  , ('8fef984880a57525', 'client', 'Mouth: a small green frown. Equip in the Character editor.', '019ff8bec41646d3ae8406da45fab96a37263304', FALSE, 'shop catalog · cosmetic name/description')
  , ('8fe042c2ad5137e0', 'client', 'Mouth: a wide open grin with a red tongue. Equip in the Character editor.', '52df6322d247786345122d89f22a249a62aa3b99', FALSE, 'shop catalog · cosmetic name/description')
  , ('53236f8f806d6a56', 'client', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', '9b4279e882d9e4eb0133e566ccdea4fd7247638b', FALSE, 'shop catalog · cosmetic name/description')
  , ('a55f45e878c399c3', 'client', 'Mouth: sewn shut. Equip in the Character editor.', '1e7a29d5061a52a7f293263e92f9a5aba4275e1e', FALSE, 'shop catalog · cosmetic name/description')
  , ('3a93dd9b2f86896b', 'client', 'Move down', '260ff8ae7182fc851337b6b2fdb25f8cac2b8d47', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('350e1d40b8b9cc72', 'client', 'Move left', '525df57dc3610e74377113b92951476bb9387e4d', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('99ceb02202c8df3f', 'client', 'Move right', '3a43e56f34dece6eb3d79dee1eff7b2f87db6040', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('baba0a75c39bf4ee', 'client', 'Move spd', 'ae53d6915d23e165765583cc340533e6e418cbd7', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('591dcab7174de8fe', 'client', 'Move up', 'b4f57cd0cd5c7d88461c1718646713dea47a36c9', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('06906a07a445cfbd', 'client', 'Movement & shield tech', 'd217db06d210b8c6c176928e820ebe2d83c720dd', FALSE, 'InfoLibrary · (file scope)')
  , ('7dca669d975f75ac', 'client', 'Moves your character down.', 'f1e421497991cfe2656cfae6630554e71ce2246e', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('4a63f9d4b6486ef6', 'client', 'Moves your character left.', '538176a71be9a7e5da9570ec614917308d8152c7', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('b26822f07257a158', 'client', 'Moves your character right.', 'd1f12c7e7490233a5fa076baf7615d1f04ac4b80', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('600b22988e855f05', 'client', 'Moves your character up. This is the game''s own control - the mod rewrites the game''s binding.', 'c18e089c0f37933447e9ff4be11260bc1485e5b3', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('928589c9dfa0518c', 'client', 'Multiplayer', '21bd0337ae7922983486f37b7c1fea1c1a9c14eb', FALSE, 'NativeUI · (file scope)')
  , ('6cd6ad59ec9f0ff5', 'client', 'Music', '131260cbfbb0c821f8eae5e7c3c296c7aa4d50b9', FALSE, 'NativeUI · (file scope), BuildMusicTab, OpenUtilityPopup')
  , ('5dd20b3b7a544213', 'client', 'Music albums have no stock — they are unlimited by design', 'b728807194b623c296667581c4fb56ad8c4a09e6', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('ff0b8a8cff784697', 'client', 'Music credit toast: <color=#88FF88>ON</color>', '7f8a9cb51f9b131918fcb642bde7c062c1cbed24', FALSE, 'NativeUI · PaintMusicCredit')
  , ('aa98c15b3fd5db76', 'client', 'Music credit toast: <color=#FF9966>OFF</color>', '30c66db52a244cf8b873a828ba4941dc3bf1b105', FALSE, 'NativeUI · PaintMusicCredit')
  , ('2830536e6c923330', 'client', 'Music download failed - press Retry', 'b436e67207eb767fb094726f88bc196c02ec2cfe', FALSE, 'MusicAssets · TierStatusLine')
  , ('6b7e447c165e9e5a', 'client', 'Music download is rate-limited - waiting to retry', '9638ffe3063b448179253fb1100806c4c854316b', FALSE, 'MusicAssets · TierStatusLine')
  , ('27e2b3adc21ab492', 'client', 'Music failed to load ({0}) — play the track to retry', '37e552ceec0a96e656492df9d275920a5c1798a2', FALSE, 'MusicEngine · MusicStatusLine')
  , ('67fde0c40c147a46', 'client', 'Music files are missing - reinstall the mod through your mod manager', '9ffc71853c15ce02fa37020b54707f5690435f6c', FALSE, 'MusicAssets · TierStatusLine')
  , ('be14fd775fc8c284', 'client', 'Music files failed verification - press Retry', 'bd2754668fb8f42a6f97ec724714677c6f41d803', FALSE, 'MusicAssets · TierStatusLine')
  , ('0d33d936b58cfb81', 'client', 'Music files not installed', '1023fe321ab265873416208f997e537a44eec66a', FALSE, 'MusicEngine · MusicStatusLine')
  , ('06283c7ad737ef2a', 'client', 'Mustard', '931e8d8cc7286798b1633cc33805cf51193e14f9', FALSE, 'shop catalog · cosmetic name/description')
  , ('4e893d4679622bc9', 'client', 'Mute From Message...', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', FALSE, 'NativeUI · BuildAdminTab')
  , ('07dd3025878252db', 'client', 'Mute Player...', '04a185ca6b9d0f63271a00f42ced92d31d342803', FALSE, 'NativeUI · BuildAdminTab')
  , ('429a5c67e4ea3a05', 'client', 'Mute a player in chat - find the player', '825304eeee2991262ee1dbad0d762e52aa6014e1', FALSE, 'NativeUI · StartChatMuteFlow')
  , ('a802c5f027c63d99', 'client', 'Mute audio when tabbed out: <color=#88FF88>ON</color>', '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', FALSE, 'NativeUI · PaintMuteBg')
  , ('edf4af82b6d6ea0e', 'client', 'Mute audio when tabbed out: <color=#FF9966>OFF</color>', '83faee2755ec624629eae20327b5e665067401b3', FALSE, 'NativeUI · PaintMuteBg')
  , ('ad4eadb6ec8876c5', 'client', 'Mute from message', 'cf62c5356606def907e33a05301d822b3ecd1e35', FALSE, 'NativeUI · OpenChatMuteFromMessagePicker')
  , ('85792e54b843280f', 'client', 'Mute the author of which message?', '30075a9c0c58a4307ec963912d41bb023e00e4d9', FALSE, 'NativeUI · OpenChatMuteFromMessagePicker')
  , ('292ca68628bacd23', 'client', 'Mutes game audio while the window is unfocused during online play. The menu stays audible; sound returns the moment you tab back in.', 'd8eb5564ef93ac1a12635ff57f715edc227be02e', FALSE, 'NativeUI · BuildSettingsTab')
  , ('a65804c100e5f740', 'client', 'My Stats', '0cb450ece94fd1c07223dd69e80d9684937e8b96', FALSE, 'NativeUI · (file scope)')
  , ('63dcaa18c5838a02', 'client', 'My collection is public: <color=#888>...</color>', '1482c1ba207717752bca9d83fc68a4801dc3e1a3', FALSE, 'PlayerCardsUI · PaintCollectionPublic')
  , ('08697623347a7e5f', 'client', 'My collection is public: <color=#88FF88>ON</color>', 'd1d8a98d0f659e0f15860ae9fe950bb0cec9323f', FALSE, 'PlayerCardsUI · PaintCollectionPublic')
  , ('0f97cbe4322477c6', 'client', 'My collection is public: <color=#FF9966>OFF</color>', '71b0e4c59c8f9bf17074cab2bf0bdc7774caed57', FALSE, 'PlayerCardsUI · PaintCollectionPublic')
  , ('36d700539721f63f', 'client', 'NETWORK', '6845c6d90585c24d63de266c9a6da04090ed2dc2', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('2de30062b4b77264', 'client', 'NEW', '66aabd91fc41cc4635aad94dc77d93a0e2eac67b', FALSE, 'PlayerCardsUI · MarkLine')
  , ('26707a1c8e1cdd1f', 'client', 'NEW' || chr(4) || 'pack open', '42ef2b803dadcb489cd34fc9c51c60a6e46e8bf1', FALSE, 'PlayerCardsUI · MarkLine · pack open')
  , ('665eecb216c12c12', 'client', 'NOT LIVE YET - your view starts at the next round', 'bea4f66c59b45371a91b60ef76b7e94564ec39ba', FALSE, 'SpectatorHud · DrawLiveBar')
  , ('a2f116ee16145bcb', 'client', 'NOT RECORDED', 'e159f84a4239ebdebbb028d2c001ae78b388aa1a', FALSE, 'InfoViz · BuildWhenCounts')
  , ('404cd01710201dc0', 'client', 'Nah', '78c3dc0e955697c34e9dfcdb511092a48644b44d', FALSE, 'QuickChat · Phrases')
  , ('eaae164b9973a5a5', 'client', 'Name', '709a23220f2c3d64d1e1d6d18c4d5280f8d82fca', FALSE, 'NativeUI, PlayerCardsUI · GetOrCreateArtistRow, SortLabel')
  , ('a37a7555118c2dae', 'client', 'Name Styles', 'accb4a8ddf0f4d799e252e947a9e7c1de73a8dd1', FALSE, 'NativeUI · (file scope)')
  , ('e7759268a7e3db8a', 'client', 'Name can''t be empty', '1d9c785179bea8325529c0dca72123e6b21a1af7', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('defcda03b0e04429', 'client', 'Name styling', 'cc26754a33fbc8129208643f3bb5fe69742c8053', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('38aee92b8364f1f4', 'client', 'Nana', '84286024a3d8f0411be7321ac3e4fe46d89d01fd', FALSE, 'shop catalog · cosmetic name/description')
  , ('d6f2bbfbd961e078', 'client', 'Near-black blocks on a black background — max contrast.', '8c4507cb4fa8d59453f7770418e0681c1acdcfa1', FALSE, 'shop catalog · cosmetic name/description')
  , ('6db0703509c1dfd1', 'client', 'Near-black volcanic glass. Disappears into the night.', '7633072baa568d07dcc6acf347d8e0c67d78267f', FALSE, 'shop catalog · cosmetic name/description')
  , ('3b30a2d648e8ded6', 'client', 'Nemesis Comparison', '23b1ea126c6eb6126356776d0f7ed2f40985168f', FALSE, 'NativeUI · TrMetric')
  , ('2f1cddec6e65ed6b', 'client', 'Nemesis Comparison - who beats this group most', '143e382ad9a59c9dd71fc64947fbc847787539b3', FALSE, 'NativeUI · BuildCompareNemesisPanel')
  , ('76a3b977b8f74add', 'client', 'Neon Cyan', 'e91fae69ed9d52f9a959fd0aa232df98f563c6ee', FALSE, 'shop catalog · cosmetic name/description')
  , ('1ce0cf2cdb6b1aa8', 'client', 'Neon Lime', '664681d96609b863f34e7bda85acda6b22882fc8', FALSE, 'shop catalog · cosmetic name/description')
  , ('7ce4510e0289c059', 'client', 'Neon Orange', '02140665ff58b93bef26879f6a7975a896f578d5', FALSE, 'shop catalog · cosmetic name/description')
  , ('a7c09f9477311f3f', 'client', 'Neon Pink', 'ff2c0cb639d80711db062bae5aec601a4e61ce51', FALSE, 'shop catalog · cosmetic name/description')
  , ('83394acf5203df01', 'client', 'Neon Toxic', '3b3e75bdc737be9d9289b248cf3318803f001c65', FALSE, 'shop catalog · cosmetic name/description')
  , ('9fc067aacc4b389f', 'client', 'Neon Violet', '25e66746dc67e99386bfd26e11749d59a7a08c7e', FALSE, 'shop catalog · cosmetic name/description')
  , ('8cb0abda4da05fc5', 'client', 'Net rating vs them: {0}', 'd456ddfb83e177467b0deaa21a8bcdd1cebf0452', FALSE, 'ProfileCard · Render')
  , ('a5b68a6c5bcde4fc', 'client', 'Netcode & Photon', 'c3320119dd20477311675076c815e2caa5e43360', FALSE, 'InfoLibrary · (file scope)')
  , ('7308c734b8170dad', 'client', 'New', '6403f2b7eb2aaafe6de34cbf2a029b01afebc512', FALSE, 'NativeUI · SyncShopArtistFilterButtons')
  , ('696b16741d564cbe', 'client', 'New here? The glowing Search Ranked button up top queues you for your first match.', '11909a5d9524d840fe00140ae23bfe7861fcabf3', TRUE, 'NativeUI · TickRankedHint')
  , ('b547112036e4389a', 'client', 'New mail from {0}: {1}', '6aba550b2fa626600ec7e40752abf1f2d0eb42b5', FALSE, 'MailUI · OnStatus')
  , ('789787560aa00ad7', 'client', 'New message', '1ed2e7b50fa1dbbf1693d1c38adf270c04db10c6', FALSE, 'MailUI · BuildComposerView, BuildHeader, PaintComposer')
  , ('7128eadbc90733c1', 'client', 'New trade', 'dde6927c02b8a2d7a3f5a8b22bd5ef9578326c3e', FALSE, 'PlayerCardsUI · BuildTradesView')
  , ('86eb7b5da080cba9', 'client', 'New trade proposal', '614a418a7a8d54ed7d0482de9e79064807e60894', FALSE, 'PlayerCardsUI · NotifyNew')
  , ('b53ae8be31c5bd6b', 'client', 'New trade proposal from {0}', '4f33d2733b5169f2eb744108a6bc7f0b2701258d', FALSE, 'PlayerCardsUI · NotifyNew')
  , ('21805a6155a21285', 'client', 'Newer >', '03301bf980ea6a980fb2cc0bbd2bc77d811a526e', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('d0de71ee40ca3cbb', 'client', 'Newest Cosmetics', '2ee61b35c40fa92c9003c05e1d840a53a57de02b', FALSE, 'NativeUI · BuildHomeTab')
  , ('957d8be836adfa00', 'client', 'Next', 'bc981983e7f547dc62e19a1e383acfe00782a6d5', FALSE, 'NativeUI · ChatMuteMsgDuration, StartChatLockdownFlow, StartChatMuteFlow')
  , ('5bb3b488dc9259b7', 'client', 'Next >', 'f80fd0c9d9fb230fee5ea75092709ea8f07d8023', FALSE, 'NativeUI, SessionReportView · BuildAchievementsTab, BuildLeaderboardTab, BuildMyStatsTab +1')
  , ('4b467a7dcbaa0b8f', 'client', 'Next match (R{0}{1}): vs <color=#FFDE88>{2}</color> -{3}{4}', 'e1362e238732d8cb29f3d4a8a7847807ac95f739', FALSE, 'NativeUI · RefreshTournaments')
  , ('e06cf6d679d0ab85', 'client', 'Next tier', '91b9cebbb5dac71f05d57f5fad14208d415046e7', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('3feec5e324dfa40d', 'client', 'Next tournament match vs {0} in {1}{2}', '31d4e7e7f8198ecfd215007826c85110b751108d', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('831575d2b0643a21', 'client', 'Next tournament match vs {0} soon{1}', 'ac0a3ea3db64d301c566b0246f5375709f7a6b14', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('f6f34d9ac2417621', 'client', 'Nice shot!', 'aac668d23d8155efd9f13bd5e05a3464762a97d5', FALSE, 'QuickChat · Phrases')
  , ('41f8d6df2156cb5a', 'client', 'Night City', '101288b594e03b935789b8a597f09d42680fa7d0', FALSE, 'shop catalog · cosmetic name/description')
  , ('f8387a7add74f327', 'client', 'Night Park', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', FALSE, 'shop catalog · cosmetic name/description')
  , ('8dc459eeaa15acb6', 'client', 'Night-forest green and bark walls under a dark smoky sky, with embers drifting up through the backdrop.', '22584937a4a8382e23a56fbd261ae0dbda2c028a', FALSE, 'shop catalog · cosmetic name/description')
  , ('321e8a8231f9be1f', 'client', 'No Escape', '3b1fef494a099a3b85cd74865db0a55fc89dcc13', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('8b9e4aa59ba78dec', 'client', 'No Refresh', '285c37a543ee155f487cdff094d9ff12e2cfbdaf', FALSE, 'InfoViz · SeqTable, SeqText')
  , ('bb8507744cbdb19d', 'client', 'No Steam account resolved yet.', '196044341091fbf7c3cf7bfd27da8c939e941c82', FALSE, 'TitleLaddersUI · OnWearClicked, ReasonText')
  , ('eb598318c184738f', 'client', 'No achievement data.', 'b701924a9d0c728225b76f6f434ef89766a3c2bf', FALSE, 'NativeUI · BuildCompareAchievementGrid')
  , ('e82cae6d83d41b06', 'client', 'No active tournament', '7688eb7fae9a048dbbeed0e73b646bf684cc09f2', FALSE, 'NativeUI · RefreshTournaments')
  , ('951717ba05be00ef', 'client', 'No answer from the server - try again in a moment', 'fc2e29c7618f28f1dc037e2e00687dde0d9ec81b', FALSE, 'PlayerCardsUI · ReasonText')
  , ('e0cd5f18d21aea86', 'client', 'No answer from the server - your pack will be checked again shortly', '494c6d166274a4ee8cb1f82c5ac08dfe6dea3b77', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('39b640c135d8a2c3', 'client', 'No articles match your search.', 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', FALSE, 'NativeUI · BuildInfoTab')
  , ('7b800da30a6628fa', 'client', 'No blocked senders.', '0e60f4e5c3500fc10fcc0ddc8425fb2d5bc47444', FALSE, 'MailUI · RefreshSettingsRow')
  , ('6a96f642595a284d', 'client', 'No cards yet - open a pack', '4aea10176daf34627bfda74b99a2654d88ddc285', FALSE, 'PlayerCardsUI · RefreshBinder')
  , ('803355296d0aefc2', 'client', 'No data from the match server for {0}s - you may be dropped', 'dd08cb0724fcf19d2780c83f8a8d1ff38c1cfc21', FALSE, 'LagNotices · TransportSilenceLine')
  , ('b91c29dbe86f7b7f', 'client', 'No games recorded for this session yet.', '36b2d3606e2ae66c86595dad5736d619ea5b7993', FALSE, 'PostSessionReport · Compose2v2, ComposeFfa, ComposeGameRows1v1')
  , ('f796bdc42be79e7b', 'client', 'No games this session', '9e6c07e8e40fc239b215195f80470cb40f0f80bb', FALSE, 'NativeUI · BuildMyStatsTab, RefreshSession')
  , ('ab55045db14ec90e', 'client', 'No games together yet', '345712868273f6a81bf0b3a50649c948c0da982e', FALSE, 'ProfileCard · Render')
  , ('ceed666326798970', 'client', 'No ladder yet - buy a title line in the Shop to start one.', '63d1b18a4ec7db0e2916363fbd349e372282954c', FALSE, 'TitleLaddersUI · EmptyText')
  , ('95e4edfd85ad0058', 'client', 'No leaderboard data', 'eddf8963477756fa3f004564792411af5a20f827', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('11eada78a2def320', 'client', 'No longer possible', '24649514990a1d7af215f454e9f1045abac0ff70', FALSE, 'PlayerCardsUI · FillTradeRow, RecentLine')
  , ('a32a4df1d80c7611', 'client', 'No mail yet.', 'd5204921aec730c6f98de36c500e8f5a7ab72db9', FALSE, 'MailUI · PaintList')
  , ('d77a171170a17a8d', 'client', 'No matches.', '0be6a25758e1f32b4250b6bc396b331ac0338f59', FALSE, 'NativeUI · RebuildPickerList, RefreshCompareCardsTab')
  , ('58c74152577b5c36', 'client', 'No messages in this channel yet.', '21c960d176f4b50c4fa7595f1e57dd48dba53808', FALSE, 'NativeUI · RefreshChatLog')
  , ('1d87122882bedc8a', 'client', 'No opponent has enough ranked series against this group yet.', 'd1a321b6ff6c3937294fa3d6a4e45c64e4cc49b4', TRUE, 'NativeUI · BuildCompareNemesisPanel')
  , ('8c1ed852b63fa045', 'client', 'No preset is free of modded items yet.', '6043e614319ca2a364acc1518b53af25edbadc17', TRUE, 'AvatarDefaults · VanillaOptionNames')
  , ('deffcecb2408c130', 'client', 'No ranked 1v1 series recorded for the selected players yet.', '7b6404043fbac5592409655ce21c338538da12d1', TRUE, 'NativeUI · BuildComparePlayerNemesisPanel')
  , ('9fac189ff37e47b3', 'client', 'No recent series', '29ac10d1f29b9a817ad176f846413aba22dcb719', FALSE, 'NativeUI · RefreshRecentSeries')
  , ('6de93f8b9886247b', 'client', 'No server-issued chat lines are in this session''s log.

Only messages this client received from the server can be deleted - the request keys on the server''s row id, which a local echo does not carry.', '31c3631d596f2157e5fdf1abd25d8ac629fc7b91', TRUE, 'NativeUI · OpenChatDeletePicker')
  , ('50b200539b8c78ee', 'client', 'No server-issued chat lines are in this session''s log.

Pick a message the author sent; the mute lands on whatever platform identity wrote it (Steam, Discord, Twitch or YouTube).', '29873ae5ee3063929231f7ca5477418031d025e4', FALSE, 'NativeUI · OpenChatMuteFromMessagePicker')
  , ('451a82c0c156aef4', 'client', 'No tiers listed', '528174ae3a6de8639babac32a3db8dd2b5e08fa7', FALSE, 'TitleLaddersUI · ReasonText')
  , ('33e496e0673a0869', 'client', 'Nobody in a ROUNDS match is the host. Every game runs through Photon''s cloud servers, every player simulates the fight locally, and each shooter is the referee of their own bullets. This page is how all of that fits together.

<color=#FFD94D><b>HOW A CONNECTION HAPPENS</b></color>

- Your client first talks to a Photon name server, pings the 15 regions (us, eu, asia, au and the rest), and picks the best one. The result is cached between launches.
- It then connects to that region''s master server, which handles matchmaking. Joining or creating a room hands you off to a game server in that region, and the room lives THERE: all traffic is you, up to Photon, down to the other players. There is never a direct link between players'' PCs.
- Quickplay only matches players in your current region. If you sit alone in a search for 15 seconds, the game hops regions on its own, trading a little ping for a bigger player pool.

<color=#FFD94D><b>ROOM CODES AND CROSS-REGION PLAY</b></color>

A private room code is 6 letters: the FIRST letter encodes the host''s region, the other 5 are random. Joining by code reads that letter and moves you to the host''s region before searching, which is why friends on different continents can always join each other. Steam invites carry the region the same way. Mod queue rooms skip all of this: the server names the room and picks ONE region for everyone it matched, so a queued pair can never split across regions.

<color=#FFD94D><b>THE MASTER CLIENT</b></color>

One player in every room is the master client - initially whoever created the room (in 1v1, the orange player). The master is not a host; their machine just gets the tie-breaking jobs:

- rolls the next map and announces it,
- announces every point and round result - every client applies the master''s score verbatim, so the scoreboard cannot disagree between screens,
- owns and physically simulates the crates, saws and moving platforms; everyone else receives their positions as a stream, and your pushes on a crate are sent to the master as requests.

If the master leaves, Photon appoints a new one - though in vanilla 1v1 that hardly matters, because any player leaving ends the match for everyone.

<color=#FFD94D><b>WHAT TRAVELS THE WIRE, WHAT STAYS LOCAL</b></color>

- <color=#7FD4FF>Player movement</color> - streamed. Your machine sends your position, inputs and velocity up to 30 times a second, and the other players'' copies of you replay that stream. A remote copy of a player never reads input.
- <color=#7FD4FF>Blocks</color> - instant on your own screen, relayed to everyone else as an event. Their copy of your shield turns on when the event arrives.
- <color=#7FD4FF>Bullets</color> - spawned once, then simulated separately on every machine, frame by frame, with no mid-flight correction (a few guided cards excepted). The bullet on your screen and the same bullet on theirs are two slowly diverging copies.
- <color=#7FD4FF>Damage</color> - computed once, on the shooter''s machine, and sent as a final number. Health is never re-synchronized; screens agree only because everyone applies the same damage events. <color=#8A8A93>(The one exception is the mod''s poison sync, where the VICTIM''s client judges the ticks - see <color=#7FD4FF>Poison & damage over time</color>.)</color>

<color=#FFD94D><b>DAMAGE AUTHORITY</b></color>

Only a bullet''s owner can declare a hit. When the shooter''s copy of their bullet touches you, their machine checks its copy of your shield and your position, rules blocked or not, and broadcasts the result. Your machine applies it without a vote.

Everything defensive you do therefore counts only once it has ARRIVED on the shooter''s screen. Press block, and it protects you there about half your ping plus half theirs later than it protected you at home. This one rule explains the classics: ''I blocked on time and still got hit'' - your press had not reached them yet (see <color=#7FD4FF>Blocking</color>); and ''I got hit around the corner'' - on their screen you were not behind the corner yet, because their copy of your position runs late by the same delay plus up to one 33 ms movement tick. The consolation is symmetry: your bullets are ruled on YOUR screen.

<color=#FFD94D><b>WHAT PING ACTUALLY MEASURES</b></color>

The ping number (the mod shows it in the corner overlay, next to your region) is the round trip between YOU and the Photon server - not between you and your opponent. The delay you feel against another player is roughly half your ping plus half theirs, plus up to one 33 ms movement tick. Two players at 40 ms each play a tighter game than a 20 ms player against a 150 ms player, even though that 20 looks beautiful.

<color=#FFD94D><b>WHAT FRAME RATE CHANGES</b></color>

- Bullets integrate their movement once per rendered frame, so different frame rates produce slightly different trajectories for the SAME bullet on different machines - a small but structural divergence.
- Player movement runs on a fixed physics step and is far less frame-rate sensitive.
- The extreme case is the Grow card, whose damage compounds per frame on the shooter''s machine (see <color=#7FD4FF>Grow</color>).
- Below about 30 FPS your machine drains the incoming movement stream slower than it arrives, so enemy copies get visibly choppier.
- <color=#8A8A93>A game can feel awful while both FPS and ping graphs read flat - stutter in the replicated stream is invisible to both numbers.</color>', '731149dda4262f45fd2b9920bd5e2584ed18d14a', FALSE, 'InfoLibrary · (file scope)')
  , ('dbfd0eaf569962a6', 'client', 'Nobody is in the card pool right now - try again later', '41d1631501daef518de793b1cb92f534cee5db6d', FALSE, 'PlayerCardsUI · ReasonText')
  , ('f8ec08e8997a5c16', 'client', 'None', '6eef6648406c333a4035cd5e60d0bf2ecf2606d7', FALSE, 'PlayerCardsUI · DanceItemLabel')
  , ('72839b0611990203', 'client', 'Noobie', 'b47b90daf74ab5d4bbf2b814f199f2ddf3ca8ded', FALSE, 'shop catalog · cosmetic name/description')
  , ('38cb3a00ec4aae7f', 'client', 'Northern Lights', '6415fc8a6d53f7a4d32943d64d274f346316f7f7', FALSE, 'shop catalog · cosmetic name/description')
  , ('0125ae7de9164286', 'client', 'Not allowed.', 'd88f9041650a4d8f92e3861108e431cc08f12866', FALSE, 'MailClient · ErrorDetail')
  , ('cf5fe2506efdad56', 'client', 'Not an artist account', '22bac2f9f83cc9e6095c7a4c2c9d5b8c8d09bece', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1ec8130473bad64a', 'client', 'Not armed', '09ebfd9f19614fd65ae985dd915d69ec6f17666b', FALSE, 'NativeUI.Settings · SettingsPaintDeleteState, SettingsRenderDestructivePane')
  , ('a24755238081a8a2', 'client', 'Not enough gold', '0147cbf943b7358b38630c8d5b1a6a781305111d', TRUE, 'TitleLaddersUI · ReasonText')
  , ('2122be0039721c75', 'client', 'Not enough gold for a pack', 'c610f55babd60201b91b7f12fa98a20f84b288ae', TRUE, 'PlayerCardsUI · ReasonText')
  , ('a48da658c2be2d8d', 'client', 'Not enough players to continue the FFA - returning to menu.', '337636a6937781e64b036aec8af783146cbaf3c0', FALSE, 'FfaMode · EndSittingBelowMinimum, FfaDoStartGame')
  , ('24d648cc4161b24d', 'client', 'Not enough shards for a pack', '4f0e2ce89843cf2653200a2ae0a7ae88c235f7f6', FALSE, 'PlayerCardsUI · ReasonText')
  , ('73b50f4ae6c3ae95', 'client', 'Not for sale yet — the artist hasn''t opened sales', '224ed73d3767b16a3f77e8bdde4cf5f1aa2631f0', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8d8ad70aea0723e5', 'client', 'Not found - it may have been deleted.', '9fe67b4b5c012200b5a02bd87d93116ea8f99fc9', TRUE, 'MailClient · ErrorDetail')
  , ('6f650c46f9c586da', 'client', 'Not granted', '53e9d819b2c611a2c478c57f4077dfdf87854f52', FALSE, 'NativeUI · PaintConsent')
  , ('692dbb3bbe0f1257', 'client', 'Not great. Not terrible.', 'b8a8dabdec32830a601c4453d32a42f6722011b4', FALSE, 'shop catalog · cosmetic name/description')
  , ('753b9026b589b7e3', 'client', 'Not in queue.', 'bcdd436f6f0ca66e0f43f93e286fcf6b21dd8688', FALSE, 'NativeUI · BuildOneVTwoTab, RefreshOneVTwoTab')
  , ('990a134373f4fe9b', 'client', 'Not now', 'e45714907316a161b3c502a4678cf42c0f4824d9', FALSE, 'TeamHoldReturn · DrawOffer')
  , ('a37e43e3ad961edd', 'client', 'Not on sale yet', '55657e24a43eff6af7cf0f3cbfdefd2c3af1fc1f', FALSE, 'TitleLaddersUI · ReasonText')
  , ('e0d0b433a171e197', 'client', 'Not ready yet', 'f9f151938094b0bc7e0115565c123cd7d2100f9c', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('a4e412e077a1fde8', 'client', 'Not set', '93039e609d94a24f3572b794a31b21525a09af2b', FALSE, 'AvatarDefaults · PresetLabel')
  , ('8ba6fe8fbf7006cd', 'client', 'Not started', 'db2c45d5579367438b625f4cf40cad184e39bd54', FALSE, 'TitleLaddersUI · PaintEntry')
  , ('75c53bbd476eb260', 'client', 'Not started - buy {0} in the Shop to begin this ladder.', '669625e5b829ae56a3f01578ca702c7a681918af', FALSE, 'TitleLaddersUI · ProgressText')
  , ('2eb8a25e75de51e8', 'client', 'Not started.', '9b90736b58dc8af387ba59399fcc51590a04f7bb', FALSE, 'TitleLaddersUI · ProgressText')
  , ('08564696812491e8', 'client', 'Not your item', '8778c01f304ebf4fa0fb3bf257e3dc910a0e180d', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('82db2967d6278668', 'client', 'Nothing playing', '13ae374e9d0eb2c240c688ebb7932cc3dbb4a275', FALSE, 'NativeUI · RefreshMusicTab')
  , ('b94ec4c29383c067', 'client', 'Nothing sent yet.', '6fa60471c5d8a896756bcae367bd6d491ca9b400', FALSE, 'MailUI · PaintList')
  , ('fed41b1541e5ebd2', 'client', 'Now Playing: {0} - {1}', '182fb22139d51c8a8129e6ed9c2391f7d226eb32', FALSE, 'MusicEngine · NowPlayingLine')
  , ('e5a406b81a6a55f6', 'client', 'Now spectating.', '22ad4e1e5ad8f9ccd91c08cfc29e216684bad88b', FALSE, 'SpectatorSync · BoundaryAttempt')
  , ('900bfdd2c5aaf566', 'client', 'Nuclear glasses', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', FALSE, 'shop catalog · cosmetic name/description')
  , ('bbe3bb1b38b22d9d', 'client', 'Numlock', '7a967cbeea59c2f0d3eda9febc88eac1d6ed2217', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('6ccaa73650023797', 'client', 'OFF', 'ad50489054ddaae044be8b3054bf4d67480648d6', FALSE, 'NativeUI · FillMusicTrackRow, LevelWordTr, PaintMusicAlbumToggle')
  , ('3d4e2b0f54660b94', 'client', 'ONE CONDITIONAL HIT', '311b3d10cac9612a322228cd36c80acd4c559724', FALSE, 'InfoViz · BuildRefreshGate, TextFallback')
  , ('261d9ebb1aeac0dc', 'client', 'ONE GAME, ONE SIGNED REPORT', '2d29f93bb633e5c66e01b643ad7b153868d9a451', FALSE, 'InfoViz · BuildReportPipeline')
  , ('40db0a284e076c04', 'client', 'OOB bullet despawn', 'dcf9125b0badf4d4589de22a864504ddd27927f6', FALSE, 'NativeUI · PerfRowLabel')
  , ('54f27396051fa05c', 'client', 'OPEN', '33906a7dfdec01bb765c738946d88161600ca35d', FALSE, 'InfoViz · BuildBetWindow')
  , ('15320b7b158aa43d', 'client', 'OPPONENT''S CLIENT', '4453348acf4193bd357d9dedd76c9c00ea33234e', FALSE, 'InfoViz · BuildReportPipeline')
  , ('7ec612c4edc75150', 'client', 'OTHER', '957c024b38ce820878f03177ce3d2b83c26a82d0', FALSE, 'CompetitiveUI · BugChoiceLabel')
  , ('a719fac14ec5fa11', 'client', 'ObjectPool init clamp (in-match)', '72d696a4f4dc7c22c8686bf0360cf923d40de5aa', FALSE, 'NativeUI · PerfRowLabel')
  , ('2a0816edad12844a', 'client', 'Obsidian', '24c869802c3e242e28585a1c90c21847f259e4f8', FALSE, 'shop catalog · cosmetic name/description')
  , ('7da210afed1bb3ea', 'client', 'Ocean Gradient', '7e4c3a7dbaa079df9174e3a12981708587d175ed', FALSE, 'shop catalog · cosmetic name/description')
  , ('5e9f0e30afc2a578', 'client', 'Odds are set when the lobby starts. Refunded if the exact person/team you bet on is not in the game.', '169b553fcca1b1d0892fdfb4527b94f323bcdaa1', FALSE, 'NativeUI · LobbyBetDisclaimer')
  , ('56367807b9612955', 'client', 'Offer in a trade', '37ca1c9a9761905104e7eb54e729a81b14092201', FALSE, 'PlayerCardsUI · AddOfferButton')
  , ('066fa92cd9434a97', 'client', 'Older >', '48f932335abd4b7ab52177929989d5898e3fe3b3', FALSE, 'NativeUI · BuildLeaderboardTab')
  , ('0f0e4598b4018d73', 'client', 'Olive', '8f62f4336f1907e6dc87f983416184094f6ff35d', FALSE, 'shop catalog · cosmetic name/description')
  , ('741922dd9e900e6a', 'client', 'On Fire', '8059b63e8a2ec48a76d5c678ff28583c5d065bed', FALSE, 'ApiClient · AchievementDefs')
  , ('5ef70f53892e5f41', 'client', 'On-screen pop-ups for incoming chat and XP/level notifications. The chat log on the Home tab updates either way.', 'e3e83bc594cc7ecde3071f3c0b105ca0345809b2', FALSE, 'NativeUI · BuildSettingsTab')
  , ('d848abd7ea062801', 'client', 'One copy, full flight, bars on a log scale. The mod pins every eligible Grow bullet to the same 120 FPS growth clock: about x3.1.', 'cc3336e5827f767e2874b5b2b213028b4631f96f', FALSE, 'InfoViz · BuildGrowCurve')
  , ('c0e08fd8bdc8c6a1', 'client', 'One free pack a day (resets at midnight UTC) - also /daily in Discord', 'c493c2615c1536d6bc10b366c0642d9745e754b8', TRUE, 'PlayerCardsUI · RefreshOpen')
  , ('3074c53943319b67', 'client', 'One of the recipients could not be found.', '2b704ce6aa67a96d1f0d0fea4523fd2263f2901f', FALSE, 'MailClient · ErrorDetail')
  , ('781405a6fc06e640', 'client', 'One of those cards is no longer in your collection - nothing was sharded; your binder has been refreshed', '197ccd0c1bd34ca5136eae94db41b1128fc196a4', FALSE, 'PlayerCardsUI · FailShard')
  , ('93f0c092c36a6526', 'client', 'One of your cards is already offered in another trade', 'a84c84756a87874dd21eaf450a7544027037c742', FALSE, 'PlayerCardsUI · ReasonText')
  , ('65cda5e0a1b2c03f', 'client', 'One player could not connect. Re-forming the lobby with everyone still here.', 'a19536e1cb1bc8a4cee73e0f24b290a9ae00bb18', FALSE, 'ApiClient · ArmFfaLock')
  , ('f9716d1cffc4df54', 'client', 'One player could not connect. The match continues; they may join later.', 'f51f35df2e41b4d4a67d51dfb38d642cd9b2e3e9', FALSE, 'FfaAssembly · ShortStart')
  , ('c1b4072db0812e45', 'client', 'One solo player faces a duo in a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- This is a consent queue with no Elo band and no ready-up.
- The server assigns one solo and two duo players.
- Solo Extra Initial Pick is optional: the solo draws
  2 cards on the opening pick. In the random queue any
  player''s opt-in turns it on; in a hosted lobby the
  host''s setting decides.

<color=#FFD94D><b>SCORING</b></color>

- The first side to win 2 games wins the series.
- 1v2 is an UNRANKED beta. No rating is applied yet.
- Games are recorded and will count when ranked play launches.

<color=#FFD94D><b>REWARDS</b></color>

- Base XP is 500 per game, x1.5 on a win - then a
  difficulty multiplier scales it, capped at x4
  (the win bonus sits on top of the cap):
  the solo earns x1.5 (and x1.20 more when the extra
  pick is off), a duo facing a buffed solo earns x1.10,
  and the opponents'' rating tier multiplies up to x3.
  Facing a top-3 1v2 player adds x1.35, win or lose.
- Series end: 40 base Gold per winner, 20 per loser,
  scaled by the opponents'' rating tier.
- Game XP converts to Gold at 100 XP = 1 Gold, and
  level-ups pay their usual bonus Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

- The tab has separate Solo and Duo boards.
- You appear only on boards for roles you have played.
<color=#7FD4FF>Rank</color> - Activity order: wins, then WR, then games.
<color=#7FD4FF>Player</color> - The player''s display name.
<color=#7FD4FF>W-L</color> - Games won and lost in that role only.
<color=#7FD4FF>WR</color> - Win rate for games in that role.
- These are activity boards. They are not sorted by Gold.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving while locked with no games played cancels the
  series; a leave mid-game leaves the result to the
  normal match report. The beta has no leave counter.', '3bb894d2341044a3da1369fb9b1cfb1ba55c742b', TRUE, 'ModeInfoText · (file scope)')
  , ('78e822807f556d30', 'client', 'Online', 'c3e839df608469149df1ef34a1c9bb26b62b5452', FALSE, 'ProfileCard · Render')
  , ('d78da2b0a30c5e23', 'client', 'Only the host can change lobby settings.', 'f729ffc338677e9fbcc52e7444381ddaa17edbc4', FALSE, 'NativeUI · BuildFfaTab')
  , ('79c01a16a77d59a1', 'client', 'Only the host can kick players.', '69ff3f5a19a3cf26411915fe4df7e457be5ecf05', FALSE, 'ApiClient · KickRefusalText')
  , ('6eb830e1335e559c', 'client', 'Only the host decides this.', '8eb88ab7faee9a89b8e4f794cd9786e217cc6f2b', FALSE, 'ApiClient, NativeUI · BuildOneVTwoTab, SetRules')
  , ('c2bb75f2c5a9fe80', 'client', 'Open', 'cf9b77061f7b3126b49d50a6fa68f7ca8c26b7a3', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('387e433edf0794f6', 'client', 'Open Packs', '643eda1f46d39e03bc3829e6d2f3005f11dc7aa8', FALSE, 'PlayerCardsUI · BuildInto')
  , ('bac8aa401a36bac7', 'client', 'Open Tier List Folder', '44a5bdcfc33755caee572a800d414defd6733252', FALSE, 'NativeUI · BuildCardStatsTab')
  , ('0c1ad37d853b8de2', 'client', 'Open Upload Folder', '7b900634f9f53532c69e92a70ddf0d76c6727e0e', FALSE, 'NativeUI · BuildArtistTab')
  , ('3117175935e906b8', 'client', 'Open a pack', '2ec22a1d2fe18d9b3745e77cb4d0ee6526d142a2', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('95d036dcba31831a', 'client', 'Open chat', 'd2104ca3045504ca90c843ffdd0b5bc9b05759d7', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('3b7874944a76f79e', 'client', 'Open for {0} gold', 'e5850c4c7089ff1406a739dc3309dafaadf42674', TRUE, 'PlayerCardsUI · RefreshOpen')
  , ('e1af94f6500e61c9', 'client', 'Open for {0} shards', '01767e2914ca8270e62fa1d1b0e42579fe42d033', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('5893137c242888d0', 'client', 'Open the Info library', '24ecf950cbf20b50adeae5290099ca654fb8fc93', FALSE, 'NativeUI · PaintActionRows')
  , ('bec80e1ec69b9d80', 'client', 'Open today''s free pack', '3e6e4a38853c49606aa711ea47c454c786930731', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('4c1b4e6d2c55dbb6', 'client', 'Open with gold', '92f3f98eec9ee74a70960bd50fc845f47ec2dc3a', TRUE, 'PlayerCardsUI · RefreshOpen')
  , ('f7b9f3b70c1b3096', 'client', 'Open with shards', '1f299c295b149debbd85c990031db8cf803897bc', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('34655ad48dcbf535', 'client', 'Opening draws:', 'ac89cf0bce0114f396b22577093558484dbf3cb9', FALSE, 'NativeUI · BuildFfaTab')
  , ('7a31d257e2cc1ca8', 'client', 'Opening the upload folder - drop a 512x512 transparent PNG (or a GIF) in there.', 'a7b8acc459f8bc8fe2e704045d98a585850e2667', FALSE, 'NativeUI · StartCosmeticUpload')
  , ('17127a1e1073eb95', 'client', 'Opening your pack...', '3a26c907f4c7f2a8d96a0e32fd94ce08cf1bb668', FALSE, 'PlayerCardsUI · Refresh')
  , ('d183652b34b6ca39', 'client', 'Opens and closes this menu. F5 always works as well, whatever you set here.', '1867a4e957bd2d9296093134143d975c08d14291', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('393497baca9693c8', 'client', 'Opens the in-game library: how a pick lands, what each ranked state means, the leave rules, and the card and damage notes players have contributed.', '0fcb1c99a540e670601a7cdd13d2f06aec77053d', TRUE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('86f0828feb387795', 'client', 'Opens the mod''s own chat box. The vanilla chat keeps its own key.', 'ea2451c867b78d09ba7e679c7c8478c935be6b66', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('45faa04dd395d9ae', 'client', 'Opp:', '1e9ed67a9b31975b8a43893fcd351af7231d2512', FALSE, 'NativeUI · FillRow')
  , ('b5482b7b080c47bf', 'client', 'Opponent Block Rate', 'db62e93e34ee47cb1527eb4f39ebb57b0f1b5c2c', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('3e904fd09a6358ea', 'client', 'Opponent Blocks', 'fc3c91253ead8a2d4252b720998f7ddc0dec0366', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('3b5bc59fb0737c26', 'client', 'Opponent Hit Rate', '4f54721965f9ca16978f3a54a352efd6ded9c369', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('1c33f30868e74629', 'client', 'Opponent Variety % (unique opponents / series)', 'eb54efd7afacb04b38b40bd3cb5db7c2b094c1cd', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('9aa15709e7599312', 'client', 'Opponent failed to join — returning to menu. Requeue when ready.', '1d82b1402be0f0e5cdcf5c6bfbb510b84cf551d3', FALSE, 'GameStateWatcher · PollRoomState')
  , ('7e1141fef186c747', 'client', 'Opponent hasn''t connected yet — hang tight...', '00611e720d436d942093ef05ad8481bacf52f082', FALSE, 'GameStateWatcher · PollRoomState')
  , ('e851feffcafec1cc', 'client', 'Opponent hasn''t connected yet — they have a few minutes of grace. Hang tight...', 'cb6da8e1dc6f7c4664c82d774f5454107035e07d', FALSE, 'GameStateWatcher · PollRoomState')
  , ('98e4a76eed695306', 'client', 'Opponent reports {0} ms ping', '02ceb2093b5bcc236bd9551a871fa0884433fade', FALSE, 'LagNotices · LineFor')
  , ('4d8c0cc6fc7fefd5', 'client', 'Opponent''s picks', '783dedc30ac7f71e7f9b2ebba24f435e2f0ea30c', FALSE, 'CompetitiveUI · DrawCardHoverTooltip')
  , ('d8e56457c902871a', 'client', 'Opponent''s updates are arriving late', 'a54036d0cbe937247c84a1c8b342ac04070c9ed8', FALSE, 'LagNotices · LineFor')
  , ('b99e6172f212d16b', 'client', 'Orange Cursor', '1af2afeff5d2f90ab6966cb74e75ab1e1082b53d', FALSE, 'shop catalog · cosmetic name/description')
  , ('2397da0da5fcc65e', 'client', 'Orange melting into pink. Golden hour, every round. Two-color gradient.', 'a986c975fdbd804c9f7c6192cc28951d219f32e5', TRUE, 'shop catalog · cosmetic name/description')
  , ('572dd774b6ee6a62', 'client', 'Orange-to-yellow gradient that sears the arena.', '3997c754c441e48d35184d2d9db0a028a6c9346d', FALSE, 'shop catalog · cosmetic name/description')
  , ('5e8f119c773fa9f9', 'client', 'Orbit', 'b6c22d03acdc68066d2b0b6028964194d9f5669c', FALSE, 'shop catalog · cosmetic name/description')
  , ('f4db3fff7c36a085', 'client', 'Orchid Gradient', '95e92e3918fc6682050e39c82964ff3edb266fff', FALSE, 'shop catalog · cosmetic name/description')
  , ('90df54c06a4560da', 'client', 'Other', '6e6a6f2086bb5fe5dbfd17d8d5f502d48759834b', FALSE, 'InfoViz, MailUI, NativeUI · (file scope), BuildCompareGenericPie, DrawReportModal +1')
  , ('30c705a5b9565018', 'client', 'Other' || chr(4) || 'report reason', 'a08428d584d214df32ded6b0efd35e8feada35b2', FALSE, 'MailUI · DrawReportModal · report reason')
  , ('e7d621f0d926348c', 'client', 'Other players can collect a Player Card of you showing your name, rank, rating, ranked record and your public Steam profile picture (your in-game character replaces the picture once this PC has sent it). Deleting your data removes every card of you.', 'd3212298f50d0af0f2055375a08d28d52ded91e5', TRUE, 'CompetitiveUI · DrawConsentModal')
  , ('811bcbb0ed9a6ef4', 'client', 'Other players can pull, collect and trade a card of you showing your name, rank title, rating and ranked record - the same things the leaderboard shows. Its picture is your Steam profile picture until this PC has sent your in-game character - the same body, face, colour and effect you play with, drawn here and sent once. Deleting your data (below) removes every card of you from every binder.', '431edce89441cfe1422711f9744e304ac9506377', TRUE, 'PlayerCardsUI · BuildSettingsPaneExtras')
  , ('7f1a73f6376d5fbd', 'client', 'Other players can send you card-for-card trade proposals. Nothing moves until you accept. Turning this off ends your open proposals.', 'c14913fb840e64d6b2d77dfa26b7fc46aa4c9952', FALSE, 'PlayerCardsUI · BuildSettingsRows')
  , ('50ff8e1c3f47f3c3', 'client', 'Other players still see this card: your new picture was not sent (the note below says why).', '9212b885177e56a21e3b8dde33f392a4a312f1f0', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('fd708efa416a95e0', 'client', 'Overall Series: {0}', 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', FALSE, 'SpectatorHud · ComposeBarLine')
  , ('19cf70accfab0f0d', 'client', 'Override the default orange/blue team color with a tint of your choice. Only visible to modded players. Premium tiers (Prismatic, Chrome) animate during combat.', '5f95d9a80a176c2d1425c1953e1eb7aafd071e43', FALSE, 'NativeUI · SHOP_TAB_DESCS')
  , ('d9f6aa01d3db3935', 'client', 'Owned', 'b62ff5ccd122308d4b6cb7103fe8380e77526b75', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('b8b614d78b815e1f', 'client', 'PHOTON CLOUD', 'bb41346607f1ed37851b0126c59333ae05444d97', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('22aaa9cf5852d31c', 'client', 'PICK YOUR CARD - {0}s', '34b31f7c574f47f91bb097cc3a682e84995a9325', FALSE, 'CompetitiveUI · RefreshFfaPickBanner')
  , ('68a41081df125636', 'client', 'PLACEMENT PAYS', '3a78197a6777de78e110c24747b2bb709b093d5d', FALSE, 'InfoViz · BuildFfaScoring')
  , ('df0ebeb8748ad0fc', 'client', 'PLAY', '42c5cda0ffa59a8691d0bf44578f236901d42363', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('3bc15e26749d12d3', 'client', 'PLAYER 1', 'cae59f99028ccdf1803e8bd4384e23450ec0a46f', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('d500172fde31785a', 'client', 'PLAYER 2', '675c88e46ce412aa6494219653a480445cc66633', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('e34c422ff7b9097e', 'client', 'PNG has an implausible number of chunks', 'e393b533f3a48841641d86a7db4782473b26438e', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('92999039119d3eff', 'client', 'PNG has no transparent background — export with an alpha layer', 'd55cefb018f8e0a0fc37e367927d125f7ba1d6d6', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('d0ec154d2e5ac556', 'client', 'PNG has {0} stray byte(s) after IEND', 'c8bcae376877a6f9c7b150d04870f523233a2926', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('e37df4d136a8e4a6', 'client', 'PNG hash does not match the payload', 'c903af01764f4eb3055d83c06c954e158daa3fae', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('bda087ffee5900c5', 'client', 'PNG is too large once re-encoded — reduce its complexity', 'd02aa6faee72bfc33b916d97ccc4e76499feb7cc', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('42855cb2c2f2ffe5', 'client', 'PNG missing or too large ({0} MB, 1,600,000 base64 characters max)', 'c44a879c40045134ab3f2d808aed95458afcf018', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('ee28d24d7ab421f5', 'client', 'PNG payload is missing or too large', '7526bc6028c100eaf0a6c8c74a624140b49f01a4', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('d420c87e2da0fce7', 'client', 'POOL', '010eb2daa4e94f46d09f5dd1cbb47bee815cfe88', FALSE, 'PcLabels · Tr')
  , ('d9792f3bfbbd83ec', 'client', 'POOL' || chr(4) || 'pc.stat.pool', '5064474f310de62f60b0f0ffcedfb515202234a1', FALSE, 'PcLabels · Tr · pc.stat.pool')
  , ('90a79fed970c2530', 'client', 'PREVIEW · NOT A PRINT', 'b7fe81106205383f3f936996674add08a289f0e4', FALSE, 'PcLabels · Tr')
  , ('1408f779a3cde02c', 'client', 'PREVIEW · NOT A PRINT' || chr(4) || 'pc.preview_footer', '7464183fbbffd5597c1a0085a063177fa89c1d29', FALSE, 'PcLabels · Tr · pc.preview_footer')
  , ('070a2b6945d3ca9d', 'client', 'PRIVATE', 'b0b7ba4666a92774e0d1afe02f2e20982b307a35', FALSE, 'NativeUI · ApplyHeaderRow')
  , ('65fcf4378f18e10e', 'client', 'Pacifist', 'eacde01371d3cfecd1d6868ac0dc890330df9229', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('d42926afd9d521da', 'client', 'Pack', '152a5035bf6b0ed4e89698b9833e019df9581216', FALSE, 'PlayerCardsUI · PackLabel')
  , ('f80f244cb0ae0907', 'client', 'Pack opened - {0} new cards', '18c0d6a789e8cf012063bbb452ad50885775ff63', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('df18e7c25bc9a523', 'client', 'Pack {0} of {1} ({2}) - {3}', 'e8b2e6df79d2ab485ab205bfbfdac84b8212edb9', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('362a28f491e72ac5', 'client', 'Packs waiting to be opened', '7f5897aa2e70d9094b02ed1c88a1769eebd73c64', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('9310f8056735f880', 'client', 'Pad 0', 'd1cf62ceae79ed17ec3718f15c69b7810a60c168', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('f044de8cad18b326', 'client', 'Pad 1', 'b11821f45539cda63c4db54ce0007d7ac9da8355', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('376715a12cbea3ca', 'client', 'Pad 2', '2f9e623a1bc36f67dc27c38ab0345ad6fae51349', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('ed2e9dd22d3c1d74', 'client', 'Pad 3', 'e7bee3b8fdbff5a4a55338b1ae78308cd607605a', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('0e8da059c7709c6a', 'client', 'Pad 4', 'a279036970986d3945948793cb69998fa6677f64', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('6f4aa02d06ed150b', 'client', 'Pad 5', 'd4b74b9703d8dc1f61a595985da94972aa20f897', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('62404ced42c845c7', 'client', 'Pad 6', '6cf4f40da222e8f21ab55dfbdc704d47a3ccd884', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('ad4db4e4b2758824', 'client', 'Pad 7', 'f80fb9fc29f360487eaaf9362d15d4a18253b88e', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('f7d9dd31a1d6add5', 'client', 'Pad 8', '0e307bbf99ac9d018d37571b528b5f8c8268b5ea', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('1507990a5fdf2615', 'client', 'Pad 9', 'e9b466afb1a97fb619890835b8c6958acd62255c', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('6cf349fdf83322ac', 'client', 'Pad Divide', '30df0c3a02546f2ac9e58a19bcf79f9bb1a219ba', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('056044c9998cfd11', 'client', 'Pad Enter', 'ee0b726acf86cc93478352c7cd00facf05f98252', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('03bc0545ed64b155', 'client', 'Pad Equals', 'b5112ab5b9b07185cdd2358babfc0256053e56c0', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('507d6da24708dbfb', 'client', 'Pad Minus', '4450ad581c9698713da745b5a32f1b49e6e57264', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('52ed5b706ad3b56e', 'client', 'Pad Multiply', '146ecc5dd466410dbff80fa790d7d7d5657f1e82', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('4f7dc12af927d124', 'client', 'Pad Period', '2db513829d518c7ce03d2010c4d7f0966d6364b9', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('2d8318c44116bb79', 'client', 'Pad Plus', 'd52cb187e8eca934275e5d3df4151511133967f8', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('5fa43bb8596cc56e', 'client', 'Page {0} of {1}', 'c10e74900e3b8a1ccfda1798ec125c5e04dce1f7', FALSE, 'PlayerCardsUI · PaintPicker, RefreshBinder')
  , ('467340c0964fba4f', 'client', 'Page {0}/{1}', 'ed4671bf173da6351d1d22cf139ce3b46b3721f4', FALSE, 'NativeUI, SessionReportView · BuildCompareRecordsPanel, PageLine')
  , ('5270e16497612223', 'client', 'PageDown', '7cba3e212dcc3d05c7ed8450a9553450544ee41d', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('cfcdc2601c4083d1', 'client', 'PageUp', 'f37641df1bc969ebc2d5a09ecf4d6e7b0f343faa', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('8ab8f916e666eb1a', 'client', 'Pale icy blue, like a winter sky.', '998da40bba23a7b05d2c404389849f0f793b49dd', FALSE, 'shop catalog · cosmetic name/description')
  , ('bf950976d4c6643b', 'client', 'Pale luminous yellow name with a matching glow halo. Mimics the classic Steam-name color trick.', '9c702f519475562bf73e49dc3a37c10b50a87674', FALSE, 'shop catalog · cosmetic name/description')
  , ('51b860af248239b9', 'client', 'Pale mint blocks on a cool dim backdrop.', '33965e30fc529ff12defc4f985185e526707cd07', FALSE, 'shop catalog · cosmetic name/description')
  , ('7122e0c69ba45d2d', 'client', 'Pale silver-blue walls over a pitch-black night, with a faint star glint.', 'f2817a9b2c0417af68309b2a6e5dbab82f161295', FALSE, 'shop catalog · cosmetic name/description')
  , ('bbafbcbefeee1a04', 'client', 'Pale spearmint body color.', 'afd15ef89657a69cc8d382f43cae628b459cc1b2', FALSE, 'shop catalog · cosmetic name/description')
  , ('f2ace16b0363f809', 'client', 'Parasite', 'e9dfbb33a2ccdd82754b2150933752bb08ddb2c5', FALSE, 'shop catalog · cosmetic name/description')
  , ('aca467037c8e7cc6', 'client', 'Party Crasher', '8b2a28c3db542d4b6043903e5419fef8c4156cea', FALSE, 'ApiClient · AchievementDefs')
  , ('8276060936caacd4', 'client', 'Party Crown', '9d32fee8673386fcb48650a016fe7874c5c0f377', FALSE, 'shop catalog · cosmetic name/description')
  , ('c309e50ffbaede37', 'client', 'Pass Rate', '4078fad860e77d0ec91f4ee504d465200b137ffe', FALSE, 'NativeUI · TrMetric')
  , ('8d4da05aac8b3d93', 'client', 'Pass rate (offered but not taken)', 'd1d9c15b7cec70ba637e349496b36e872f13c793', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('02a88da890abd1ce', 'client', 'Pass%', 'd0cfb954a9334a6c99881784734346cd543a750a', FALSE, 'NativeUI · BuildCardStatsTab, RefreshCardStats')
  , ('254a6264214b6cca', 'client', 'Password', '8be3c943b1609fffbfc51aad666d0a04adf83c9d', FALSE, 'ApiClient, NativeUI · CreateFfaBrowserRow, EnrollResult, FfaEnrollResult +1')
  , ('94816db7715ff443', 'client', 'Password (share it with friends)', '29f453def2a2e1cf0ecf97c82e500a959343939f', FALSE, 'NativeUI · BuildFfaTab, BuildOneVTwoTab, BuildTeamTab')
  , ('63f4d64f58ce3cab', 'client', 'Password must be 64 characters or fewer.', '0959b55c3ce21f8d75c8a6f3f53d766d21925fd0', FALSE, 'ApiClient · FfaCreateLobby, FfaJoinLobby, PasswordTooLong')
  , ('a352871ddde71056', 'client', 'Paused: {0} - {1}', '672504530777b1b681d9f21d05eddcb13559c535', FALSE, 'MusicEngine · NowPlayingLine')
  , ('c97d35b45f398d79', 'client', 'Peak Elo', '5a581465bae3c00caeb7577b0eba5949d87517a7', FALSE, 'NativeUI · BuildCompareBarChart, TrMetric')
  , ('f32e779b43ec84c1', 'client', 'Peak {0}', '692b07e24b3da4d3c88ffc89a129035c6b3249a9', FALSE, 'PostSessionReport · ComposeFfaMiniPanel')
  , ('712e4d673596a27d', 'client', 'Per game', '773ae9253d2188c6d0ad4b5ec3af3378bfa699d6', FALSE, 'SessionReportModel · Build')
  , ('8227d56c911268e1', 'client', 'Per-letter bright cyan → deep indigo gradient. Surface to trench.', 'f08ec7ca421c33b887294dd88f4ba78c26fd48d7', FALSE, 'shop catalog · cosmetic name/description')
  , ('81c7b7cb050ea26d', 'client', 'Per-letter bright red → dark wine gradient.', '7fd885137d973cf162fe2417eadbd70ecd9734ae', FALSE, 'shop catalog · cosmetic name/description')
  , ('b03342feaff2e735', 'client', 'Per-letter bright yellow → deep red gradient. Flame to coal.', '3f1c0d14e823390910e171a2cb32a8ad991d59c2', FALSE, 'shop catalog · cosmetic name/description')
  , ('9a7fe17e2d48c091', 'client', 'Per-letter leaf green → bark brown gradient. Canopy to roots.', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', FALSE, 'shop catalog · cosmetic name/description')
  , ('b42387c8be516f9e', 'client', 'Per-letter magenta → cyan gradient. Interstellar nebula.', '57a7a6cdae35659fdaab629a1af89418c8b819e0', FALSE, 'shop catalog · cosmetic name/description')
  , ('65c931b05122cf6c', 'client', 'Per-letter mint → deep forest green gradient.', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', FALSE, 'shop catalog · cosmetic name/description')
  , ('0429c34a08c40ee2', 'client', 'Per-letter rich gold → ivory white gradient.', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', TRUE, 'shop catalog · cosmetic name/description')
  , ('10fc19103bfc00a4', 'client', 'Per-letter silver → gunmetal blue gradient. Cold and clean.', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', FALSE, 'shop catalog · cosmetic name/description')
  , ('e8318953ee3473cc', 'client', 'Per-letter sky blue → deep royal blue gradient.', 'ffe6b732761562041ff44d44571715b12b5027da', FALSE, 'shop catalog · cosmetic name/description')
  , ('17fee1da703692c3', 'client', 'Per-letter sunset orange → dusk purple gradient.', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', FALSE, 'shop catalog · cosmetic name/description')
  , ('cf5aad12a3f6733b', 'client', 'Per-letter teal → violet gradient. Cold-night-sky shimmer.', 'e33445036b26cc0c43db07baa039c326346c1692', FALSE, 'shop catalog · cosmetic name/description')
  , ('9447c4a194d0bbf6', 'client', 'Per-letter violet → hot pink gradient.', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', FALSE, 'shop catalog · cosmetic name/description')
  , ('d93ccfb1df90a055', 'client', 'Per-letter warm grey → ember red gradient. Cooling coals.', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', FALSE, 'shop catalog · cosmetic name/description')
  , ('2114443a269971a4', 'client', 'Per-letter white → dark charcoal gradient. Fades out as it goes.', '8566174efb4eb4edb2ed35464668e45a1334b95c', FALSE, 'shop catalog · cosmetic name/description')
  , ('30ad5fe9e45c303f', 'client', 'Perfect balance. One light, one dark.', '32efb45b331be9c80dc68d23882fe31dcfb8b1f2', FALSE, 'shop catalog · cosmetic name/description')
  , ('45d589527e1b3138', 'client', 'Performance', '63c904559993935c470f516c8b549ca7f3640dbb', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('2cd796c73bb4cce7', 'client', 'Performance master switch — flips ALL the patches below at once.', 'baae5e74ea779b7a0764d7e688a498b8ce825e73', FALSE, 'NativeUI · BuildSettingsTab')
  , ('6068681a8e45bef1', 'client', 'Pestilence', 'c65996e876d952c7f83708e8b760263321d84d13', FALSE, 'shop catalog · cosmetic name/description')
  , ('535dfa7fc4de1206', 'client', 'Phantom', '023f16c08cac4b78e60d97af91a446d906bfb3dc', FALSE, 'shop catalog · cosmetic name/description')
  , ('7df6272aa44de13e', 'client', 'Phoenix', '3e978fbf8aad93b7520fcec25f666a8823b47615', FALSE, 'shop catalog · cosmetic name/description')
  , ('e77e0b2592889257', 'client', 'Phoenix Flame', 'e667878de6874deec7efb0c65ddf39bb296521af', FALSE, 'shop catalog · cosmetic name/description')
  , ('dbf7b69987b7393d', 'client', 'Phoneix Gaze', '1c2493a2cffcc002e422dca455556ce4ebdd1b22', FALSE, 'shop catalog · cosmetic name/description')
  , ('8345415cab034679', 'client', 'Pick', '04d2414cddc1052e6f0278073dbb8ff76f134db2', FALSE, 'NativeUI · BuildAdminTab')
  , ('c41b2ce8fb195cfb', 'client', 'Pick Your Start Times (as many as you like)', '34bd1f98b5ff53c0ec64db58e11c8ba454e1c881', FALSE, 'NativeUI · BuildTournamentsTab, RefreshTournaments')
  , ('1cd08b528d6cb3fb', 'client', 'Pick Your Start Times <color=#888>(multi-select, required to sign up)</color>  <color=#7FE8C3>best time: {0}/{1} agreed</color>', 'a1b97d981b566c2923f68b338c4d2b81ee2018a2', FALSE, 'NativeUI · RefreshTournaments')
  , ('640ae8a86f2e1d0f', 'client', 'Pick a card! (left/right + jump)', '875ac7dcd6f646d6220442f1a02bf5b1e803b167', FALSE, 'FfaMode · FfaLocalPickUI')
  , ('5d3d20c7e814733e', 'client', 'Pick at least one start time first', 'f9177c4826c3a708fde02435090893f66afa4a98', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('4be253b8080d3f06', 'client', 'Picks', 'f5f61efb04cc0bde68137d2124c1656a262a2038', FALSE, 'NativeUI · BuildCardStatsTab, RefreshCardStats')
  , ('21464be1e8300f5e', 'client', 'Pine', '456e097f4ceb19803ed7d70dbf2d28a51848d23f', FALSE, 'shop catalog · cosmetic name/description')
  , ('4932eaba51eabdd1', 'client', 'Ping', '6b68e97973994116d837d4de74f29d77f895c097', FALSE, 'PostSessionReport, SessionReportModel · Build, BuildCells1v1, BuildCells2v2Game +1')
  , ('30b0f82ce6dc5c3b', 'client', 'Ping / region display: <color=#88FF88>ON</color>', '4f795bce846c0e7c91c35b77741a9e4c2b77aaf2', FALSE, 'NativeUI · PaintRegionPing')
  , ('e1e93a22eecf9cea', 'client', 'Ping / region display: <color=#FF9966>OFF</color>', '57352048202016805118230d31272211e396b95f', FALSE, 'NativeUI · PaintRegionPing')
  , ('4bb91d4741ebaf17', 'client', 'Pink Cursor', 'b12540f76b8ae0ed79395737854d6d05a71804a7', FALSE, 'shop catalog · cosmetic name/description')
  , ('88d9415535dd3e6d', 'client', 'Pink Name', 'b6744ad14e80c3f4975d1874d4abeac76118559c', FALSE, 'shop catalog · cosmetic name/description')
  , ('a39999e17f4758a1', 'client', 'Place bet', '96ef7f60b0e12322ce4490d8ea26c66eb5e0576c', FALSE, 'CompetitiveUI · DrawCustomBetPrompt')
  , ('ba09752e6658a6f9', 'client', 'Placement changed since this preview; reload it and try again', 'c549dde1519f241173c75bd888e98a9c55832b2e', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1a6a6222b6c55ce5', 'client', 'Plague Doctor', 'dd620f00dff757c1fb7c1ea3d8ea4b7705afd289', FALSE, 'shop catalog · cosmetic name/description')
  , ('1d7d88d5ab1ccb40', 'client', 'Platinum', 'c93fa0a5953ea725bfad3d51caa53e0abd992fd2', FALSE, 'shop catalog · cosmetic name/description')
  , ('8e79cc7c9152efb9', 'client', 'Play', '5d12bd53552cafc41ca6146c04870df2e1574e13', FALSE, 'NativeUI · CreateMusicTrackRow')
  , ('371ca2ac52232538', 'client', 'Play Now (skip break)', '791cf8113eee5c723d227c59846570d1b6283e08', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('db8fec39d72e6a3e', 'client', 'Play Now failed', 'd4407fed7110ec6103497b2404163e92ec4df375', FALSE, 'ApiClient · TournamentPlayNow')
  , ('db3b02b95016e341', 'client', 'Play Now sent - starts when your opponent presses it too', '3e9e7a22260ce183e8a00a562ad305510c9221a5', FALSE, 'ApiClient · TournamentPlayNow')
  , ('3375a7a17a28e03e', 'client', 'Play a tournament through to the end without forfeiting a single match', '7fe1293aa75e21cb2297dc2d43e8dc0d8f248425', TRUE, 'ApiClient · AchievementDefs')
  , ('24268d2ea1640f9f', 'client', 'Play your first ranked match here', 'ddd6c173bb4cc9055abb2cb3d69a2fecbb208747', TRUE, 'CompetitiveUI · DrawRankedHintCallout')
  , ('e9939d439ec9d4f0', 'client', 'Player', 'e53407cfe1a5156b9f0d1eed3bab5ef3ae75cfd8', FALSE, 'NativeUI, SessionReportModel · BuildCompareNemesisPanel, BuildFfaTab, BuildLeaderboardTab +5')
  , ('8a947e5171fcfe9c', 'client', 'Player Cards', 'c4bb71c9676fdb78f00ba6b80deb8c5f95248f7d', FALSE, 'InfoLibrary, NativeUI, PlayerCardsUI · (file scope), BuildInto, BuildSettingsRows +1')
  , ('98a3af3eca38f474', 'client', 'Player Cards are collectible cards of the people who play here. Every player who has run the mod from a Steam account and is not currently banned has a card in the pool; you open packs, keep the cards you like, discard the rest for shards and chase the rare ones. Everything lives under <color=#7FD4FF>Shop > Collection</color>: <b>Open Packs</b>, <b>Binder</b> and <b>Get packs</b>.

<color=#FFD94D><b>THE POOL, EDITIONS AND SNAPSHOTS</b></color>

- The <b>pool</b> is every eligible player, frozen in a <b>snapshot</b>: rating, record, rank tier, top card and title as they were that day. A card you pull keeps those as the snapshot saw them and they never change afterwards - that is what makes an old card an old card. Two things on a card stay live: the player''s name (a rename follows) and their picture (see Card pictures & settings).
- An <b>edition</b> (Ed. 1, Ed. 2 ...) is one run of snapshots. The edition and the date your card was minted are printed along its bottom edge, with a short print number that is unique to your copy.
- The pool line under the pack buttons tells you how many players the current snapshot holds and when it was taken.', '644f0ed2cd061e7ab4677941309c0cc9a607d8db', TRUE, 'InfoLibrary · (file scope)')
  , ('3b41b3003fe62032', 'client', 'Player Cards are not enabled on this server yet', '1d60cc6cf1f8c539490384750e3cb0621078f1d0', FALSE, 'PlayerCardsUI · Refresh')
  , ('6332702ff393a497', 'client', 'Player Cards are not open yet - no edition is running', '68083ab99d56ac8878eea0b524628848bad90f8a', FALSE, 'PlayerCardsUI · ReasonText')
  , ('8abde5adb8d080da', 'client', 'Player Cards need your Steam sign-in - try again in a moment', 'ba5ee5c074ee898b7eeb4b2370d26a5c27c745cc', FALSE, 'PlayerCardsUI · ReasonText')
  , ('6fa6116e48d185fc', 'client', 'Player Nemesis', '15353c406b7afd5870e69defa94cbbc53009ede8', FALSE, 'NativeUI · TrMetric')
  , ('398720128f9cc6f3', 'client', 'Player not found', '9cfe6ceb8c4b47dc3a23265c81ed9b6a5d3b36f8', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('9a86acea4a7d2e2b', 'client', 'Player not found — they need to have used the mod once', 'd26d4dc8b8266aa879bf8b70f5e86085374e0b63', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('a47bdec6b41a02d6', 'client', 'Player opted out', '7fd409f1368984a0d7a1b782481a8be0bc864713', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('1b5a95c6021117d4', 'client', 'Player removed from the lobby.', '6513aeea6e95789c0cc2258d2dd9b48844073ba6', FALSE, 'ApiClient · FfaKickFromLobby, Kick')
  , ('db981d5856fea2c6', 'client', 'Player totals', '4116a2bca218b61dcb4745b88cba4dde0e0881f3', FALSE, 'SessionReportModel · Build')
  , ('3bc81240cf6b8795', 'client', 'Player {0}', '315b1f52cdff2bd5975f933f866c66ac0a84f8ac', FALSE, 'TabStatsOverlay · PlayerName')
  , ('2b298b7271502c6c', 'client', 'Players', '392feef07c53c9a7b2763d1fd30fb3f0d68099cc', FALSE, 'NativeUI · BuildCompareTab, BuildHomeTab')
  , ('235e32ddb1201875', 'client', 'Point to the sky, point to the floor, sway those hips. Dancing locks your controls for the duration.', 'fd2f5c58c6a2ab9b9b61e5b1e568db7a14f2b934', FALSE, 'shop catalog · cosmetic name/description')
  , ('0dcc6ff0923d1298', 'client', 'Points lost', '220529258a903733ef0e7b61532f5de9b9f6f8b5', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('79fc8e7c3edeb448', 'client', 'Points won', '0fbd7c52519a0a93627ef458f3ac0e808b399a97', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('b4afe6f94d8a1b3b', 'client', 'Poison', '6de0b0c656444c55bac48c2e467aa0f841083cdc', FALSE, 'InfoViz, shop catalog · BuildDotTimeline, cosmetic name/description')
  , ('507db85caf0e602a', 'client', 'Poison & damage over time', 'cf45d3edae079b8b38a35974796750918fa489e0', FALSE, 'InfoLibrary · (file scope)')
  , ('251cda79e9ae8cec', 'client', 'Poison has no damage number of its own. The total a poison bullet deals over time equals that bullet''s damage stat at the instant it hit you (Toxic Cloud''s longer drip rounds a couple percent above it) - which is why the same green bullet sometimes tickles and sometimes one-shots.

<color=#FFD94D><b>WHAT A POISON HIT DOES</b></color>

- The impact itself deals just <color=#7FD4FF>1 damage</color> - but full knockback. Knockback scales with the bullet''s damage stat even when that damage is converted to poison, which is why a big poison shot hurls you across the map while your health bar barely moves.
- Then the poison starts: the bullet''s full damage, split into equal ticks spread evenly over the poison''s duration. For the <color=#7FD4FF>Poison</color> card that is 10 ticks over 3 seconds - one every 0.3 seconds, 10% of the bullet''s damage each, the first landing the instant the bullet connects. <color=#7FD4FF>Toxic Cloud</color>''s poison drips longer and thinner: about 17 ticks across 5 seconds. The cadence runs on game time (slow motion stretches the gaps).
- <color=#FF6666>Every tick is lethal on its own.</color> There is no ''poison cannot finish you'' mercy rule.

<color=#FFD94D><b>WHY IT SOMETIMES ONE-SHOTS</b></color>

The total is the bullet''s damage AFTER everything that pumped it: damage cards, bullet size, growth in flight (see <color=#7FD4FF>Grow</color>), an Empower charge. A bullet pumped to 500 damage becomes ten 50-damage ticks - 500 total into a 100 HP player, dead before the stream is half done. It is never the poison that one-shots you - it is the bullet underneath it, paid in installments.

<color=#FFD94D><b>BLOCKING TICKS - THE EXACT RULE</b></color>

First, the free win: block the poison BULLET itself and there is no poison at all - an absorbed bullet spawns none of its on-hit effects (see <color=#7FD4FF>Blocking</color>). The rest of this section is about the ticks after a bullet already got through.

Each tick is an ordinary blockable damage event, checked against your 0.3 second block window.

- <color=#7FE87F>A blocked tick is consumed, not delayed.</color> The poison marks that slice as dealt before it checks your shield, so a blocked slice is erased forever. The stream never extends, never pauses, and never comes back for it.
- Blocking does not cancel the stream. The remaining ticks still land on schedule.
- The survival math: every tick is an equal share of the total - 10% for Poison. If a poison''s total is exactly enough to kill you, erasing one tick means it can no longer kill you - and each extra blocked tick is another full share you keep.
- The cadence is on your side: ticks arrive every 0.3 seconds and a block window lasts exactly 0.3 seconds, so <color=#7FE87F>one well-timed press erases one or two ticks - 10-20% of a Poison, 6-12% of a Toxic Cloud</color>. That is the entire mechanism behind ''block a tick or two and you survive''.
- Echo blocks re-arm the window without restarting the cooldown, so one press can cover more than one tick.
- <color=#FF6666>The tick sound plays even for blocked ticks.</color> Judge by the health bar, not by the click.

<color=#FFD94D><b>STACKING</b></color>

Every poison hit starts its own independent stream on its own timeline. Nothing merges and nothing refreshes: two poison bullets are two full streams, damage fully additive, each ticking on its own schedule. Getting tagged twice does not reset the first poison - it doubles the drip.

<color=#FFD94D><b>DEATH, REVIVES, DECAY, LIFESTEAL</b></color>

- Dying or being revived at a round transition cancels every running stream instantly. Poison never carries across a round.
- Decay-class cards convert EVERY direct hit the holder takes into a spread-out stream ticking every quarter second. The same rules apply: each tick is blockable, and blocked slices are erased.
- Every unblocked tick feeds the attacker''s on-damage effects: a lifesteal build heals off you tick by tick.

<color=#FFD94D><b>THE MOD''S POISON SYNC</b></color>

Vanilla poison is broken online. Each machine runs its own private copy of your poison and checks it against its own copy of your shield; your block press reaches different machines at different times; health is never re-synchronized. The screens silently disagree about your HP (''ghost HP'') until the next round - and the disagreement can decide a round, because a death fires from whichever machine''s copy crosses zero first.

The mod replaces this with victim authority: <color=#7FE87F>your own client runs the only real tick loop for poison on you</color>, judges every tick against your true shield state, and announces each verdict. Every modded machine - yours included - applies only announced verdicts, so all of them agree on every tick, the totals and cadence follow vanilla''s math, and blocking works exactly as written above.

Where it is active: any online room - queue rooms, private room codes, quickplay - whenever the poisoned player runs a current mod build. Mixed rooms fall back safely:

- In a mod queue room that contains a non-modded or outdated player, modded clients agree that poison ticks ignore blocking - consistency beats the ghost-HP split, but blocking will not reduce poison there.
- In a private room-code game with a non-modded player, a modded victim''s blocks still count; a non-modded victim gets raw vanilla behavior, desync included.
- Offline and sandbox are pure vanilla - a single simulation has nothing to desync.', '040dc80582ef2677d666706843f7c57d1b9b407a', TRUE, 'InfoLibrary · (file scope)')
  , ('c7ff4f384e1ed8c3', 'client', 'Poison main', '994ef00e3288928269240324105bb35e1304c87e', FALSE, 'shop catalog · cosmetic name/description')
  , ('47d9b036144dbc30', 'client', 'Poison''s eyes', 'f6b5a94241188908466dd4e8866efdd71a095f00', FALSE, 'shop catalog · cosmetic name/description')
  , ('3c0f844e8017bc56', 'client', 'Poison''s mouth', '670012d71850926c55cf6e4df5b125e67d1e988e', FALSE, 'shop catalog · cosmetic name/description')
  , ('df98d4645ac79249', 'client', 'Poison''s weeping', '26c1d2970bb104ebf25377d761feeed044bbf63b', FALSE, 'shop catalog · cosmetic name/description')
  , ('0e72750e37c7c6a4', 'client', 'Poisoner', '53b8d6d04b42c5527575738edfd453c84e07ad7f', FALSE, 'shop catalog · cosmetic name/description')
  , ('53dbca2fef57d9e2', 'client', 'Pool #{0} | Ed. {1} | {2}', '411161a34ec40dc3abb0e6a61bad00f3a0122a55', FALSE, 'PlayerCardsUI · FillTile, ShowCardText')
  , ('6ca9dd38e68467c1', 'client', 'Porcelain', '79e59b6d40ad67a86922bb3f5937e4a051c43f13', FALSE, 'shop catalog · cosmetic name/description')
  , ('d57237dcfcae73a0', 'client', 'Portal session failed - are you signed in to Steam?', '43637cfe355335aa2af0c5f7474edd1bbe4ddf5e', FALSE, 'ApiClient · MintPortalSessionAndOpen')
  , ('f708e90d85c1e8d0', 'client', 'Position', 'cf1c85adba548e8d681255278976584a7e4a44de', FALSE, 'PlayerCardsUI · SortLabel')
  , ('201f4f9ee52b9f86', 'client', 'Posted to Discord - good luck!', '156ad8a2f775907515a8186cda3dc77ee4001e83', FALSE, 'ApiClient · SendLfpPing')
  , ('68b06756b591710e', 'client', 'Precision shooter', 'd603c62a187b010ba86e02a8a3eae5477f7da9ca', FALSE, 'shop catalog · cosmetic name/description')
  , ('f6e7a6de91dd5197', 'client', 'Precision-stepped poses, one servo at a time. Dancing locks your controls for the duration.', '6d1039cf610e6208ecf5f37f7debd6ad05afa84c', FALSE, 'shop catalog · cosmetic name/description')
  , ('9cbff466d2318636', 'client', 'Predator', 'c5b3b9f5cd30f77eb048a211ddce5932230c7fd3', FALSE, 'shop catalog · cosmetic name/description')
  , ('90d0551d9d3aec2a', 'client', 'Premium: cold silver walls that glint to pure white, over gunmetal dark', '2fd710fc7265cbfa6686c3f0b03de6975d70e6f7', FALSE, 'shop catalog · cosmetic name/description')
  , ('51afe625aeb8a965', 'client', 'Premium: molten gold walls that glint to white-gold, over a deep bronze vault', '22f4f84ddb194e43610ebb98e62014a7317abfe9', TRUE, 'shop catalog · cosmetic name/description')
  , ('a1b12781f1dcf408', 'client', 'Premium: northern-lights walls shimmering between polar teal and violet in a polar night', '381ae69d6dec239a744146b21683d1da1f3ef1c0', FALSE, 'shop catalog · cosmetic name/description')
  , ('6fc40cd842c4d19b', 'client', 'Preparing your card picture...', '7ebcf28d6de38706ec8ffe17c7a72238d90470cf', FALSE, 'PlayerCardsUI · WaitForPortrait')
  , ('d1f89ccf47715eb4', 'client', 'Preset {0}', '4464d597199bdfb312a99680bde0182a5d2a9a24', TRUE, 'AvatarDefaults, PlayerCardsUI · PresetLabel')
  , ('f5eee5d39db64b8b', 'client', 'Preset {0} — has items an unmodded player cannot see', '0704fc43b49bac175f1f60cada10d723ec530655', TRUE, 'AvatarDefaults · VanillaOptionNames')
  , ('efa81bae52828e96', 'client', 'President Meow', '97a6e94ae4eed9bbe810b5d563cfedfb3727d477', FALSE, 'shop catalog · cosmetic name/description')
  , ('f5309769a8d52e46', 'client', 'Press
[{0}]
to join', '6925d2481c0e8eef289864156d01b53234bb9a10', FALSE, 'NativeUI.Keybinds · KeybindJoinPrompt')
  , ('b9da26eccc254410', 'client', 'Press Enable on the RANKED row first - the RLFP ping is only for ranked matches.', 'f759566b7428a79b95a6d43e534fa03154485cf6', TRUE, 'NativeUI · OnLfpButton')
  , ('f5802f04b6f64ceb', 'client', 'Press Esc to leave', '425872a6007bf09700428cd4751ff944086fbdbd', FALSE, 'SpectatorHud · DrawBlackout')
  , ('21a77f99b9e86f48', 'client', 'Press Esc to leave. The match then ends as a disconnect.', '30a77f9e3bf9ae019331df0d619b7df314378a26', FALSE, 'TeamHoldBanner · Line')
  , ('0af0075c99c1a3c3', 'client', 'Press [{0}] when ready', '86df78d70f5dd74c12ebe175b3d35b59838c57e1', FALSE, 'NativeUI.Keybinds · KeybindReadyPrompt')
  , ('cde27cd01eb311f4', 'client', 'Press a key...', '74ddb069e508c3a991268ba14dcd874172a342a5', FALSE, 'NativeUI.Keybinds · KeybindPaintRow')
  , ('93b0c67e17ad98dc', 'client', 'Pretty Good', '603ec1ace9aaf396ccfe4a27b23c73f1a5cfe171', FALSE, 'shop catalog · cosmetic name/description')
  , ('2eb11481c6e1d81c', 'client', 'Preview', 'f1fbb2b43dca281d0138f4fcc92543ad143ef0b1', FALSE, 'NativeUI · ApplyShopRow, BuildShopTab, CreateShopRow +1')
  , ('36adad979132fdb6', 'client', 'Preview art isn''t downloaded yet - try again in a minute.', 'e51313b1eafcf4cad2f1432dd1fbaae046aa0986', FALSE, 'CompetitiveUI · OpenCosmeticBodyPreview')
  , ('a1b5a04f8d591cb8', 'client', 'Preview logs', 'd42e29e77884854a5e8b41eb4d0996d9758c52e4', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('9789ec57aacffa6f', 'client', 'Preview: {0}', '680bce4b84ac071af8bf71cc98932d5dde018070', FALSE, 'CompetitiveUI · DrawDancePreview')
  , ('75b908029624d68e', 'client', 'Preview: {0}  <color=#888>({1})</color>', 'd2b78d262308d18630b0a15b9c03018be74b5d16', FALSE, 'NativeUI · ApplyShopRow')
  , ('8055b783c194bf26', 'client', 'Previews load at the main menu', '68ff624947dbd4c2bc6b458b91702676564de96d', FALSE, 'MusicEngine · TogglePreview')
  , ('267110bd9e31f755', 'client', 'Previous track is not loaded yet — use Previous at the main menu', '27410e6659b89a7cb61e84f1f7fa41ee862fbce5', FALSE, 'MusicEngine · PlayPrevious')
  , ('5873dfb6d6ce0071', 'client', 'Price', '3e8248e32edfca0c629622b5b669c2d9ce4d0917', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('eebe408eccb38d52', 'client', 'Prices changed - refreshing them first', '35842cb537bfac523a0c4fc0314a08286a726feb', FALSE, 'PlayerCardsUI · BeginBuy')
  , ('2d45a2b0e7622c60', 'client', 'Print {0}', '44c0356111097e1a0e44dee5d71b306541842fff', FALSE, 'PlayerCardsUI · ShowCardText')
  , ('204f8caeaf9b9177', 'client', 'Prismatic', 'ffad6acebcb46cb4a5b292d6ce8b9156bb2952e3', FALSE, 'shop catalog · cosmetic name/description')
  , ('88fd0dc2b471baea', 'client', 'Prismatic Wake', '04a4408655caed1756da3dd8fddd01e0563e0a94', FALSE, 'shop catalog · cosmetic name/description')
  , ('e5672fa98ea29e9b', 'client', 'Pristine', '4674af60a621fd87ec692450c9893c7c19caef67', FALSE, 'shop catalog · cosmetic name/description')
  , ('49923e671981b95e', 'client', 'Pristine Perfection', '960ab5ab0edb01f24063eaa58f2593eab46db25c', FALSE, 'ApiClient · AchievementDefs')
  , ('9d7a909290f2ff0f', 'client', 'Privacy & account', 'a995083370371133af3a12adf6cb0d3c70797b6d', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('a9fd32601c4651d7', 'client', 'Private 1v2 lobby', 'd67b2b5c07267670c3b6718695df939fe870078d', FALSE, 'NativeUI · JoinHostLobbyRow')
  , ('c0a5a045dc1b1281', 'client', 'Private 2v2 lobby', '96c3146d3bc48dfa0b86a5911c497bd3462cb006', FALSE, 'NativeUI · JoinHostLobbyRow')
  , ('237b5d17e7ab0b7d', 'client', 'Private FFA lobby', '497ee30f36b72d164c36997c60d9b69233756437', FALSE, 'ApiClient, NativeUI · CreateFfaBrowserRow, FfaEnrollResult')
  , ('aea133c530e2eb26', 'client', 'Private {0} lobby', 'c533468e20d8365bef12ca8e3ee43dfac8f32e29', FALSE, 'ApiClient · EnrollResult')
  , ('9f6ba43f78157173', 'client', 'Prizes', '4a4300888933d180d78056ae2875609cc168712b', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('caf5eeeec3117ec3', 'client', 'Prizes & Rules', 'e04ea281201a233a32fca1d38f18e6f2ac668552', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('f011a454829fac7c', 'client', 'Prizes are announced when signups open.', '122c17aad3eda08a61675ed1002bce10fde0233a', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('76af3af59e2be1c3', 'client', 'Progress', '1b90271d66cf2d3ac755d49a550fe5f31b9eca5f', FALSE, 'SessionReportModel · Build')
  , ('8dcd95733f0c2303', 'client', 'Pronoun title.', 'f33e1d33043740f2b9906fcb880abd6d11a6a22c', FALSE, 'shop catalog · cosmetic name/description')
  , ('f4969500c44ed4fc', 'client', 'Prospector', 'e72f43c478074c8d6b85fd9720b70216ebc2e88f', FALSE, 'shop catalog · cosmetic name/description')
  , ('e5c45a484d8a02c8', 'client', 'Prowler', 'b79f48c35188b397c2bc99c6731dfd678e452434', FALSE, 'shop catalog · cosmetic name/description')
  , ('eab2d19163bf187d', 'client', 'Published cosmetic source must be a transparent 512x512 PNG ({0})', 'c2b38aef82ff32782bdd0e44385e8cac8e03dca8', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('61a13c637db571e1', 'client', 'Pumpking Hat', '9e1406f62ccd3c0e86190daf0dc3d666052f2ca3', FALSE, 'shop catalog · cosmetic name/description')
  , ('017e0df5f591c5ff', 'client', 'Pup', 'acb0a780d2622033f09fc0e90242be07a7be9512', FALSE, 'shop catalog · cosmetic name/description')
  , ('b90ef63e7495e242', 'client', 'Pure aggression', '1bd8f1b24f475d07e65940615d102d138bfb866b', FALSE, 'shop catalog · cosmetic name/description')
  , ('b8fdc86007277b7b', 'client', 'Pure greyscale — minimum visual distraction.', '58574a4f8f3a1703dd84bf2e5628e34cc1c666c9', FALSE, 'shop catalog · cosmetic name/description')
  , ('30517b69c320de25', 'client', 'Purple Cursor', 'b9dff734194f8410236cfa4ea86d68ede85cdb6c', FALSE, 'shop catalog · cosmetic name/description')
  , ('15902baa613f6be8', 'client', 'Purple Name', 'e1b4569dbbad3384f405de04efad13c425231ab2', FALSE, 'shop catalog · cosmetic name/description')
  , ('b184685895afcf0d', 'client', 'Purple-black shadow trail. Feels wrong in the best way.', 'ac2f7ec50caa3e176d76d18c4b08ddc29913a773', FALSE, 'shop catalog · cosmetic name/description')
  , ('5926f2e809729cab', 'client', 'Puts the delete row back to its normal state. Nothing has been deleted at this point, so cancelling costs nothing and the row can be armed again.', '1e67deb93231a29be32ab20662217c856584c187', TRUE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('64c15481701e976b', 'client', 'Putting on {0}...', '6eca5e30412aaf5f2dd3e4eec08064ece8d638e3', FALSE, 'TitleLaddersUI · OnWearClicked')
  , ('718d188e4455bdc5', 'client', 'QF A', '3f95bde7012ad5270801b8142efe43e5c9a8ae95', FALSE, 'InfoViz · BuildBracketFlow')
  , ('e81331915974fd55', 'client', 'QF B', '9e10ff0f8b9d89c366d06e06ba24fd30da382f7a', FALSE, 'InfoViz · BuildBracketFlow')
  , ('2f7eefed49e94df2', 'client', 'QF C', '341bb8dd1de413c75605a0c3834651ef423f01ec', FALSE, 'InfoViz · BuildBracketFlow')
  , ('5c61ac09c8790e5a', 'client', 'QF D', 'dcc6f8c98198485da8208044f04ac1ea4a225177', FALSE, 'InfoViz · BuildBracketFlow')
  , ('b0769d6c1aeb4cb0', 'client', 'QShoot', '9c38e7ed34d17340df42ee8a7adf514aae97fe9e', FALSE, 'InfoViz · ActionLabel')
  , ('efd9786032f9577c', 'client', 'QUICK SHOTS INSIDE THE 0.35 SECOND WINDOW', 'b7d4d9f0f1bf5f98f36ab7bf5a6e1ac3cc32c17e', FALSE, 'InfoViz · BuildRefreshWindowSequences')
  , ('b40e17e80dad60e9', 'client', 'Queue games (ranked 1v1, and 2v2 / 1v2 auto-queue) deal everyone the same cards when every player in the room has this on. Applies from your next game.', 'd48c8a8cba6937ed4bfddbd736ec9612e512fd39', TRUE, 'NativeUI · BuildSettingsTab')
  , ('50f008199b3a6417', 'client', 'Quick Reload', '0d605504a7573fae3e6517042c6870986aa06dff', FALSE, 'shop catalog · cosmetic name/description')
  , ('7b55f022da9fc830', 'client', 'Quick Reload main', 'fa664531b4a41c6178b16cb21826ade02ac9de83', FALSE, 'shop catalog · cosmetic name/description')
  , ('a334146e7221f3fb', 'client', 'Quick Shot', '100ef149a6e54103f0bd1aac177bb3dc8aa907cf', FALSE, 'shop catalog · cosmetic name/description')
  , ('dc8ca2a55307498d', 'client', 'Quick chat', 'd6d2248bd5af439f06e478bb3297bce222bdb7f2', FALSE, 'CompetitiveUI, NativeUI.Keybinds · DrawQuickChat, KeybindRowLabel')
  , ('f2f9b149b9bdc2ff', 'client', 'Quick chat is on cooldown - one message every couple of seconds.', '34f4ba41ace1cf468ce976bb2d07104bfcb302a1', FALSE, 'CompetitiveUI · QcSend')
  , ('423228a4fc37960b', 'client', 'Quick chat works once you are in a game with your character spawned.', '355b09f4e293431128ee7c4e69fa7ef1838b03b1', FALSE, 'CompetitiveUI · QcSend')
  , ('300f86d80b8d9186', 'client', 'RANK', '9cc2229409ebf7a451b2509c23892c92fff169d6', FALSE, 'PcLabels · Tr')
  , ('5aac2b3522c46b6b', 'client', 'RANK' || chr(4) || 'pc.stat.rank', '0ba8f28c2aced33ba564fb176ffb2a4f5feb1cef', FALSE, 'PcLabels · Tr · pc.stat.rank')
  , ('406b02c730784003', 'client', 'RANK TIERS AND REWARD MULTIPLIERS', '0ef565eb43156859af82b408109cafaedaa9cb35', FALSE, 'InfoViz · BuildRankLadder')
  , ('3786a6bd207e499c', 'client', 'RANKED', '1b7065ae1c038de8c69cfa7e56294b2e33055ce8', TRUE, 'InfoViz · BuildWhenCounts')
  , ('9e1369ddd08e1d16', 'client', 'RANKED - Recording', '6ad85c9fff5b14b6cf3d9aae3688c935e8f4cbe6', TRUE, 'CompetitiveUI · DrawMatchStatus')
  , ('848f3e18208e508c', 'client', 'RANKED: OFF', '1998dd66a03e45362865bc40663d644bf13e7641', TRUE, 'NativeUI · BuildRankedRow, RefreshQueueUI')
  , ('80d04622a6a5d196', 'client', 'RANKED: ON', '07a2ae0633edf8be3f1fc68f659230f653255a99', TRUE, 'NativeUI · RefreshQueueUI')
  , ('cd7d7d222723e41b', 'client', 'RARE', '647bf4ae5c62e4b2f7fc54138d7154994e7846d5', FALSE, 'PcLabels · Tr')
  , ('7b4a361c79fd81e4', 'client', 'RARE' || chr(4) || 'pc.band.rare', '4b958f87b99a8e348bc0fd74420f4d9e3f3a8321', FALSE, 'PcLabels · Tr · pc.band.rare')
  , ('6ac4e0a90e36d59f', 'client', 'RARE' || chr(4) || 'pc.band_short.rare', 'b6e9e715da3255e962263a3761989452a5fd6b60', FALSE, 'PcLabels · Tr · pc.band_short.rare')
  , ('bb4f45737f45fa97', 'client', 'RATING', '1042d6afbaa2562d66b31b149368e37c9578c92c', FALSE, 'PcLabels · Tr')
  , ('0ed7e38c708b3a2b', 'client', 'RATING' || chr(4) || 'pc.stat.rating', 'fe46773c039547b3c620762312c029b09b9329eb', FALSE, 'PcLabels · Tr · pc.stat.rating')
  , ('7abf29cd482ae2c3', 'client', 'RD: {0:F0}    Peak: {1:F0}', '585c9f8bfdd65b7176d0906cacf12b63bd0a5a16', FALSE, 'NativeUI · RatingBits, RefreshMyStats')
  , ('11edb88202bebbb4', 'client', 'RECORD', '31355a28687d29fdd7654b7c5a0888c5c908cd0e', FALSE, 'PcLabels · Tr')
  , ('b2798fbf249fbb18', 'client', 'RECORD' || chr(4) || 'pc.stat.record', '02076bcaaf199df9021564a369ec26682ea310fc', FALSE, 'PcLabels · Tr · pc.stat.record')
  , ('d0f152f450aac7c8', 'client', 'REDUCED', '23e6c4be753d9d00ecad5872f44d8edadd1c668f', FALSE, 'NativeUI · LevelWordTr')
  , ('a5f7e903662e54ee', 'client', 'REFRESHVALID IN PLAY: SILENCE SEQUENCES', 'bdb859db4ccb3214abc9455d467c163130cc8fe0', FALSE, 'InfoViz · BuildRefreshSequences')
  , ('ea66c841fb926192', 'client', 'REVIEW', 'ed6912ad70e7f5f44c4e228e2168918d894d50ce', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('cb1b8e351f319a01', 'client', 'RIGHT', '95253203f79304981143599cedfdaa606f083ca2', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('97b2232a5765faa8', 'client', 'RLFP Ping', 'd405f3f3916bbffcbf17431e5a7a548cb15320cf', FALSE, 'NativeUI · BuildRankedRow, RefreshQueueUI')
  , ('54eee8c1199323da', 'client', 'RLFP ping available in {0}m {1}s (1 per hour).', 'f55cf47ab80a74cedc526b6091d08157c647d6d3', FALSE, 'ApiClient · SendLfpPing')
  , ('0fc595b782b397ad', 'client', 'RLFP ping failed - server unreachable. Try again shortly.', '974727e8ed4995674b56ea6e9de859a6aa61ed4c', FALSE, 'ApiClient · SendLfpPing')
  , ('242f5f5f70d848b7', 'client', 'RLFP ping failed: {0}', '6136170d5d17ddca75e9d37f52c04c12fc73a7ea', FALSE, 'ApiClient · SendLfpPing')
  , ('e5dadf69deec4be8', 'client', 'RMB', 'cd2dd9251a1e2b57b766c5972c39c07ad8e015d6', FALSE, 'InfoViz · BuildKeyboard')
  , ('90c58689d7c96644', 'client', 'ROUNDS OST', 'fe8dce1485bae8c21fe8add8173abcc34654bc7b', FALSE, 'NativeUI · RefreshMusicTab')
  , ('b363fcd85ad12f79', 'client', 'ROUNDS default', 'aab9cc11374b328c40f51b26cc5e6f928250ff2c', FALSE, 'NativeUI · ShapeLabelTr')
  , ('c2ecb03aa90759d9', 'client', 'ROUNDS ships with real bugs - some cosmetic, some that decide rounds. The catalogue: symptom, real cause, and whether the mod repairs it. Repair details: (see <color=#7FD4FF>Bug fixes the mod ships</color>).

<color=#FFD94D><b>INPUT AND LOBBY BUGS</b></color>

<color=#7FD4FF>Escape key permanently dead, or inputs frozen as a match is found</color> - the game toggles input across all players with no null checks; one half-spawned player crashes the loop. <color=#7FE87F>Fixed by the mod, always on.</color>

<color=#7FD4FF>''No space to ready up'' - you cannot spawn into a lobby</color> - the game tries to spawn your character before you are actually in a room, crashes, and never recovers. <color=#7FE87F>Fixed by the mod, always on</color>; 30 seconds stuck returns you to the menu.

<color=#7FD4FF>Typing confirms a card pick, Enter opens the room-code box, {0} readies you up mid-sentence</color> - three places read the raw keyboard without checking for an open text box. <color=#7FE87F>Fixed for the mod''s own chat</color>; the vanilla chat box keeps its quirks.

<color=#FFD94D><b>COMBAT BUGS</b></color>

<color=#7FD4FF>After a rematch, your block goes on cooldown but absorbs nothing - or Shield Charge stops firing while basic block works</color> - the between-games teardown can destroy card objects half-way, stranding dead hooks on your block. <color=#7FE87F>Fixed by the mod everywhere</color> (see <color=#7FD4FF>Blocking</color>).

<color=#7FD4FF>Poison health bars disagree between screens, and blocking poison is a coin flip</color> - every machine ticks its own copy of the poison against its own copy of your shield; health is never re-synced. <color=#7FE87F>Replaced by the mod''s victim-authoritative poison</color> when the victim runs the mod (see <color=#7FD4FF>Poison & damage over time</color>).

<color=#7FD4FF>A poison tick kills someone during the round-won animation, awarding a phantom round</color> - damage-over-time keeps landing after the round is decided. <color=#7FE87F>Fixed on every modded client, in any room</color> - full protection just needs the room''s (usually modded) host seat patched too.

<color=#7FD4FF>A leftover bullet from the previous point hits you just after everyone respawns</color> - nothing in vanilla despawns mid-air bullets at the point boundary. <color=#7FE87F>Fixed: modded clients clear their own leftover bullets.</color>

<color=#7FD4FF>Shots visibly connect but do no damage on your screen, or a point-blank drill bullet turns invisible</color> - the bullet''s special components can register in the wrong order on the receiving machine. <color=#7FE87F>Fixed by the mod in any room.</color>

<color=#7FD4FF>Grow one-shots you out of nowhere</color> - broken math more than a bug: Grow''s damage compounds per frame on the shooter''s machine, so low frame rates and hitches multiply it massively. <color=#7FE87F>Normalized by the mod in competitive play</color> (see <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>After one game with Demonic Pact, hold-to-fire guns like Spray stop auto-firing all session</color> - the no-auto-fire flag is copied one way and never reset between games. <color=#7FE87F>Fixed by the mod in any game.</color>

<color=#7FD4FF>Radiance visibly sweeps through a crowd and hits one person</color> - the wave only ever checks the single closest target and stops after one hit. <color=#FF6666>Fixed in FFA only</color> - there it hits everyone it sweeps; other modes keep vanilla.

<color=#7FD4FF>Chase''s card text lists a Health bonus</color> - dead data the game never applies; the card has never granted it. <color=#7FE87F>The mod fixes the label.</color>

<color=#7FD4FF>Being offered a card you already own</color> - not a bug; the second copy levels up the first.

<color=#FFD94D><b>MODE AND VISUAL BUGS</b></color>

<color=#7FD4FF>In 2v2 or 1v2, a card picker stands on an empty stage, or the wrong body is shown picking</color> - vanilla only ever presents one picker per round, using a team number as a player number. <color=#7FE87F>Fixed in 2v2 and 1v2 mod rooms.</color>

<color=#7FD4FF>Phoenix revives someone into thin air - invisible, unhittable, stuck</color> - the revive finds the player by list position, wrong once the list has changed (an FFA leaver), and the death flag is never set. <color=#7FE87F>Fixed by the mod everywhere.</color>

<color=#7FD4FF>Another player''s name shows as the literal placeholder PlayerName</color> - a failed Steam name lookup is never retried. <color=#7FE87F>Fixed: the mod retries the lookup (up to 15 tries over half a minute) and repaints the name when it lands.</color>

<color=#7FD4FF>A saw''s spinning loop plays forever, or audio goes muffled for the session</color> - looping sounds outlive their owner and starve the sound engine of voices. <color=#7FE87F>Fixed: leaked loops are swept after every round.</color>

<color=#7FD4FF>Harmless error spam in the log during map transitions</color> - the map-move animation holds references to pieces replaced mid-move. <color=#8A8A93>Not fixed - benign noise. (Anything that must touch the map mid-move, like the mod''s own map skins, defers around that window instead.)</color>

<color=#FFD94D><b>WHERE THE FIXES RUN</b></color>

Crash guards and dead-state repairs run everywhere - they repair states vanilla never intended, without changing any rule. Rule changes are gated: mode logic needs its own mod-issued room, Grow normalization needs every fighter modded and consenting, and poison authority follows the poisoned player - an unmodded victim keeps vanilla poison. <color=#7FE87F>A non-modded player always gets pure vanilla gameplay</color> - and the only things they can ever see of the mod are nametag styling and quick-chat phrases you deliberately send through the game''s own chat (see <color=#7FD4FF>Vanilla stays vanilla</color>).', 'd8b40f6f6315ebcf8337348eadc8c765de15d975', TRUE, 'InfoLibrary · (file scope)')
  , ('3895f9b558e965da', 'client', 'Rabbit', '29f716260a7733eb00cd1083b6e0d754c8d01ffc', FALSE, 'shop catalog · cosmetic name/description')
  , ('ee284c69ff36a2e8', 'client', 'Rabbit God', '451e72a7d2a33446359b6490d3006fbca076c9c3', FALSE, 'shop catalog · cosmetic name/description')
  , ('6acb2025439df09b', 'client', 'Radioactive green with lime droplets. Probably safe.', '17b8b7386ad2a3ed4cf024889d17f1cac584e54e', FALSE, 'shop catalog · cosmetic name/description')
  , ('19028acb5fad6b86', 'client', 'Radioactive yellow-green neon name with a hot glow halo. Visible to everyone; modded players also see the glow.', '75e2d41b04a8463628b2f2bc5c724326fc3488ac', FALSE, 'shop catalog · cosmetic name/description')
  , ('d493c9301c56b2ee', 'client', 'Rage Quit %', 'efd0aba4aac4e819dd347ce1f242e3276cb03825', FALSE, 'NativeUI · TrMetric')
  , ('45070e4bcb2e0ffb', 'client', 'Railgun', 'b6292747420775fd8d1aea2d9e7ed1c08a0cdfa9', FALSE, 'shop catalog · cosmetic name/description')
  , ('5f7558f212422e9c', 'client', 'Rainbow', 'b4a9395d25398654fd5d000e4b82a1d8273339bd', FALSE, 'shop catalog · cosmetic name/description')
  , ('b6862f5ae4f76951', 'client', 'Rainbow Aura', '9b8cce5d7eccd2e22579b152d9d9be67ab1466fc', FALSE, 'shop catalog · cosmetic name/description')
  , ('0dc7d933cccba541', 'client', 'Rainbow Name', '153fd22a1e9af7179306e615f49ac52f49829bc6', FALSE, 'shop catalog · cosmetic name/description')
  , ('aa1cc75adcac35af', 'client', 'Rainy Day', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', FALSE, 'shop catalog · cosmetic name/description')
  , ('35bd90bf4523c298', 'client', 'Raises your block.', '421742b797fe6ac1fbbe2fc52081a0c33bebd13b', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('ba3394d24a886db0', 'client', 'Rally Flags', '41434103e0f30de4583dbd5d09e8fbdce6268ecc', FALSE, 'shop catalog · cosmetic name/description')
  , ('a3167976ce15fa39', 'client', 'Rampage', 'a3efb7df8f742e808e896ac1c37a46b8f2c8547c', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('6628289042207194', 'client', 'Random Queue', '09e9637fcb1efff7cf0100fe0a14567427177caa', FALSE, 'NativeUI · BuildTeamTab, RefreshTeamTab')
  , ('d5c79642846289a8', 'client', 'Rank #{0} of {1}', '0d33322a2bc41e889fd1b393849108837ad7ad21', FALSE, 'ApiClient · TryFormatStanding')
  , ('9f1a921f27d9f8b7', 'client', 'Rank #{0} | {1}W {2}L', '0cd3c7cedba54aa2dac39ad6ebb91b17b5a11532', FALSE, 'PlayerCardsUI · RankLine')
  , ('287bb7dfc58feb5b', 'client', 'Rank: <b><color={0}>{1}</color></b>', '5ae95848f1654fdab6009b60a2e5515c472863d9', FALSE, 'NativeUI, PostSessionReport · ComposeFfaMiniPanel, ComposePlayerPanel1v1, ComposePlayerPanelCompact +2')
  , ('519e272ed084c741', 'client', 'Ranked', '092579473a08bd70d7ac3465596a270bce98cb2a', TRUE, 'NativeUI, SessionReportModel · BuildCardStatsTab, BuildFfaTab, KindLabel +1')
  , ('6ad9912372f78640', 'client', 'Ranked (series)', '749826ec9c02cfbac0274840d905f2c374fab239', TRUE, 'NativeUI · BuildCompareBarChart')
  , ('c62b982567217472', 'client', 'Ranked 1v1', '69950fdaeb7cbb81edfbeb8d1a8521dbf0cf3f8d', TRUE, 'InfoLibrary, ProfileCard · (file scope), ModeName')
  , ('e0ed74112b5d0272', 'client', 'Ranked 1v1 - 2v2 - tournaments - cosmetics   <color=#666>v{0}</color>', '4e02c65a3230ab22a99e846d79d4b4d46cd9901e', TRUE, 'NativeUI · BuildHomeTab')
  , ('6e62951fdb93563c', 'client', 'Ranked 1v1 games', '82033c4926ccf7525a9e7b5a5b8dcaf3e1951b27', TRUE, 'ProfileCard · Render')
  , ('fc07ba40fe031c27', 'client', 'Ranked 1v1 is the mod''s core mode: best-of-3 series, one Glicko rating, and two ways to start a rated series - the queue, or a private room where both players run the mod. This page covers the queue from Search to room, how a private lobby becomes rated, and exactly what a disconnect does.

<color=#FFD94D><b>FINDING AN OPPONENT</b></color>

- Clicking Search is itself the ranked opt-in - joining the queue turns Ranked on for your account.
- Your search band starts at 100 rating in either direction and widens as you wait: 200 after 30 seconds, 400 after 60, 800 after 120. It never widens past 800.
- The overlap is <color=#7FD4FF>two-sided</color>: you must be inside your opponent''s band AND they must be inside yours. A 2-minute waiter with a wide band can''t grab a fresh joiner whose narrow band excludes them.
- Among valid candidates, the closest rating wins.
- Players you declined in the last 5 minutes, players you''ve blocked (in either direction) and banned accounts are never offered.
- Searching while playing casual is fine - vanilla quickplay and ordinary casual rooms never cancel your search. Joining any mod-issued room (a tournament, 2v2, 1v2 or FFA) does, immediately.
- After 30 minutes of searching you''re removed from the queue. <color=#8A8A93>Rejoin if you''re still there - the 1v1 client never rejoins for you.</color>

<color=#FFD94D><b>READY-UP, DECLINE AND THE ROOM</b></color>

- On a match you get a MATCH FOUND banner with your opponent''s name and rating, a sound, and a taskbar flash. You must click Ready - there is no auto-ready.
- You have 90 seconds, and when either player clicks Ready the window resets to a fresh 90 for both - a slow alt-tabber always gets full time. If it runs out, both of you go back to searching.
- Decline puts both of you back in the queue and blocks the two of you from re-pairing for 5 minutes. Once the room has been issued, decline no longer works.
- When both are ready the server issues a private ranked room and picks the Photon region: if both clients report the same home region, that wins; otherwise it falls back through the players'' live regions, then either home region, then US.
- Your client pins that region before joining, so both of you land in one room instead of two same-named rooms on two continents.
- If your opponent never arrives: a warning at 15 seconds, then an automatic return to the menu at 60. <color=#7FE87F>No penalty for either side.</color>

<color=#FFD94D><b>RANKED IN A PRIVATE ROOM</b></color>

- A room-code game is rated when three things are true: your Ranked toggle is on, your opponent has Ranked enabled, and your opponent runs the mod. An opponent who has never run the mod can never make a game rated. (One deliberate exception: a live unfinished series from an earlier sitting keeps its ranked status when you meet again.)
- The moment both mods see each other, the client registers the series with the server (the <color=#7FD4FF>preflight</color>) - so the series exists, and is bettable, during game 1.
- If either player has Ranked disabled, the server refuses the series and you get one toast: the match plays out as casual. Casual games are still recorded - they just never touch rating.
- Queue and tournament rooms skip these checks entirely: queueing was the consent.

<color=#FFD94D><b>THE SERIES</b></color>

- First to 2 game wins takes the series. <color=#7FE87F>Rating moves only when a series completes</color> - the whole series is one rating outcome, and individual games never move rating on their own.
- An undecided series - at least one game played, nobody at 2 wins - <color=#7FE87F>never expires</color>. Play the same opponent tomorrow or next week and game 1 still stands; your HUD picks up the standing score instead of restarting at 0-0.
- That no-expiry rule is deliberate: an expiry window let a player down 0-1 abandon the series and wait out the clock to dodge the loss.
- A non-tournament series where no game was ever finished is abandoned after 30 minutes; the next meeting starts fresh. Tournament series wait for their bracket instead.
- Bets on a series stalled for 60 minutes are refunded (tournament series excepted) - the series itself stays resumable.
- During round 1 of each game, the client reports live points to the server. Betting locks once 2 total points have been scored in game 1 (a 1-1 counts) - or the moment any game of the series is decided.

<color=#FFD94D><b>DISCONNECTS</b></color>

What a DC does depends on the score, and it is judged by the player who STAYED:

- You were at match point (4 rounds) when your opponent dropped: you win the game at the standing score.
- 4-4: you take the game, recorded as 5-4.
- Anywhere else - including an opponent who drops while AHEAD - the game is canceled. Nobody gets a win, nobody gets a loss.
- Leaving a game to join your own queued ranked match is announced in advance and never counted against you.

The anti-abuse rules:

- Only the player who stayed in the room and watched the other leave can claim a DC win. <color=#7FE87F>A leaver''s own client can never award itself anything.</color>
- If the opponent reconnects before you leave, the claim is dropped.
- If BOTH players drop, nobody stayed to observe: no win, no leave mark. With a completed game on the board the series stays active and resumes whenever you next meet.
- <color=#FF6666>A canceled game doesn''t wipe the series</color> - completed games stand, and the series resumes as above.

<color=#FFD94D><b>LEAVE PERCENT</b></color>

- A ranked DC with meaningful play behind it (2 or more points, or a completed round, in the CURRENT game), with neither side at match point, is recorded as a leave against the leaver - at most one per player per series.
- <color=#7FD4FF>Leave %</color> = ranked DCs divided by ranked series wins + losses + DCs. Under 5 percent shows green, 5 to under 15 amber, 15 and up red - visible to everyone on the leaderboard.
- A DC at match point becomes a DC win for the other player instead, not a leave mark.

For the full is-this-recorded decision tree, see <color=#7FD4FF>When a game counts</color>.', '0aa41f4136b6fb6ac705d0f82fccc62a6fd86ca6', TRUE, 'InfoLibrary · (file scope)')
  , ('3552fe19b992d0c5', 'client', 'Ranked 1v1 series', 'a9c4991f02d068f244e91619d5201b4a1dddc220', TRUE, 'ProfileCard · Render')
  , ('57ca58671cb6dc1c', 'client', 'Ranked DPS', '70461d2426e78a0ca406ba56d2790b61569d7f54', TRUE, 'NativeUI · TrMetric')
  , ('f732fa3292ba6a54', 'client', 'Ranked Damage per Second', '9350fb281abfe3f6db7df17312a701fccc03b427', TRUE, 'NativeUI · BuildCompareBarChart')
  , ('8e9f5c5b8f417285', 'client', 'Ranked Form  <color={0}>{1}W-{2}L</color>', 'debb4916739eaee8059bb06b20b9668167be4310', TRUE, 'NativeUI · BuildFormGraph')
  , ('72667efc1834c251', 'client', 'Ranked Friends', '624fd377566b56ead5befdc372a3ee7c6794eab0', TRUE, 'NativeUI · TrMetric')
  , ('5c4c865c87f70972', 'client', 'Ranked History', 'd7108e6ab5e6f45e23c2ec5fe23f129cf7d5631a', TRUE, 'NativeUI · BuildMyStatsTab')
  , ('ec3ba28ef8180508', 'client', 'Ranked Picks', '1c0bdb37df4c2cc2ffd2c3090286f5e5399cfc7c', TRUE, 'NativeUI · TrMetric')
  , ('1249b6f1e502b718', 'client', 'Ranked Series: {0}W / {1}L', '9010764c511b06ab2dc58692c34c829ba1fe04b3', TRUE, 'NativeUI · RefreshLeaderboard')
  , ('0f004b96432f2a20', 'client', 'Ranked Uniqueness %', 'f0ddbdf03fc9e3cf4e1d8d9835269feed90dee1c', TRUE, 'NativeUI · TrMetric')
  , ('ceee15a894860be2', 'client', 'Ranked Win Rate', '758692850822b2769fe7459a6ba3ded3dd35e5cc', TRUE, 'NativeUI · TrMetric')
  , ('53c66fd08ebd68b6', 'client', 'Ranked build types', '9467ad59cd362c01604269f825c554e56b6b103e', TRUE, 'NativeUI · BuildCompareGenericPie')
  , ('9568055ad9672251', 'client', 'Ranked only works if results can be trusted. The short version: every report is signed and identity-checked, both players'' clients gather evidence about each other, detectors flag for human review rather than auto-punishing (one narrow farming pattern is the only exception), and a person makes the final call.

<color=#FFD94D><b>MACRO DETECTION</b></color>

- Your client samples gameplay input every frame - movement, fire, block - only while you''re alive in active combat, never while typing or in menus.
- Sustained input far beyond any human''s pace is recorded as suspect windows with exact per-second rates and per-match peaks.
- BOTH players hold the evidence. Each client publishes its counters to the other during the match, so the report carries the opponent''s windows too - and in 1v1 a client with serious evidence also files it directly with the server, signed, so it survives even when the reporter''s copy is stale or lost.
- Evidence merges can only strengthen: a later submission can never weaken peaks or windows already captured. If a flag has already been reviewed, new evidence opens a fresh review instead of editing the decided one.
- Flagged macro suspects are quietly excluded from the Compare tab''s similar-players pool until cleared - a macro''d input profile would poison the matches for everyone.

<color=#FFD94D><b>AFK DETECTION</b></color>

- A 1v1 reporter with zero shots, zero blocks and zero card picks across a match longer than two minutes gets flagged. The card check is the load-bearing one: pacifist and melee builds legitimately finish games without firing a bullet, but nobody picks zero cards while at the keyboard.

<color=#FFD94D><b>IMPOSSIBLE PACING</b></color>

- Speedhacks speed up the client''s own clock, so the server never trusts client-reported durations. It measures the wall time between report arrivals on its own clock; a series arriving faster than games can physically be played is flagged, with the exact intervals stored for review.
- The one automatic penalty in the whole system: a repeated pattern of implausibly short matches between the same two players is invalidated outright, earlier games in the pattern included - gold and XP reversed, series voided. Everything else on this page flags for human review.
- Chronic low FPS and rough connections are judged against YOUR OWN recent history, so a machine that always runs that way never flags; sudden convenient dips are judged against the same match''s normal.

<color=#FFD94D><b>SIGNED, DEDUPED, QUARANTINED</b></color>

- Every match report is signed and identity-checked: the reporter must be a participant in the match and must hold that account''s live Steam session. <color=#7FE87F>Nobody can report AS you</color> - and nothing anyone else reports can put a number on the records boards under your name.
- Each game can be recorded exactly once. Duplicates and replays are absorbed - the server hands back the already-recorded result and nothing pays twice.
- A team or FFA report that arrives for a closed lobby is quarantined for admin review, not trusted and not silently dropped.

<color=#FFD94D><b>NOBODY CAN PLANT DATA UNDER YOUR NAME</b></color>

- The records boards only ever show rows from a player''s OWN reports, so an opponent''s client can''t put a number under your name no matter what it sends.
- Card-draw records work the same way: a report counts only for the reporter''s own seat on the Luckiest board.
- The worst a modified client can do is lie about ITSELF - and self-reported numbers are exactly what the pattern detectors watch, stay advisory until a human reviews them, and are reversible afterward.

<color=#FFD94D><b>BETTING LOCKS</b></color>

- Betting closes the moment real information exists. In 1v1 and 2v2 that''s 2 points scored in game 1, or any game of the series decided; in FFA it''s 2 points across the field in the current game (1 in a first-to-3 lobby).
- The lock is enforced by the server when the bet is placed, not just hidden in the menu. You can''t bet on your own match, and it''s one bet per series (per game in FFA) per player.

<color=#FFD94D><b>HUMAN REVIEW</b></color>

- Every flag lands in front of an admin with its exact evidence - for a macro flag, the windows, the peaks and both sources.
- A verdict binds to the exact evidence the admin reviewed. If stronger evidence arrives mid-review, the review is redone against it - a stale read can''t decide a flag.
- A false-positive verdict on anything auto-invalidated triggers a tracked repair of the affected gold and rating.
- A confirmed verdict doesn''t fire an automatic penalty. Enforcement runs through separate, individually audited admin tools: bans and series reversal. A ban cuts live access immediately - sessions revoked, queues blocked, ranked refused - and if you ever match a banned player, your client leaves automatically with a notice.', 'c801ffbe17db6bee98ea4167dbe677e5af7def51', TRUE, 'InfoLibrary · (file scope)')
  , ('b782b304c02b0e85', 'client', 'Ranked series', '28c2d827acda4509832481f6d4ed5eacb610f759', TRUE, 'InfoViz · BuildGoldSourcesLegend, GoldBucketName')
  , ('d97792202e616ada', 'client', 'Ranked turned ON so your tournament results record - and it stays ON after the match. Turn it off in Settings if you don''t want later games rated.', '75b494a0a2d8f1b4213f4d55bf0235723548ac18', TRUE, 'NativeUI · _EnsureRankedEnabledForTournamentMatch')
  , ('5f7707fef861204c', 'client', 'Ranked: OFF', 'd25149b5a5f3f6d2741e28fb6dfc7c7c7ae8fd5b', TRUE, 'ApiClient · ToggleRanked')
  , ('b35287596dfd384c', 'client', 'Ranked: ON', '98194ebda82e053bbdfb5e3c3810d48876a1aaf9', TRUE, 'ApiClient · ToggleRanked')
  , ('c3d2282d14e75714', 'client', 'Rapid-fire shoulder shake with pulsing arms. Dancing locks your controls for the duration.', '6a446a531aa163cbfb6355753f8ff17e98c909b3', FALSE, 'shop catalog · cosmetic name/description')
  , ('e316e9a339cb0454', 'client', 'Rare', 'cce370d2f9781af0f85d591ccdfad1fe365a619f', FALSE, 'NativeUI, PlayerCardsUI, SessionReportModel · Build, RarityLabel, RefreshCardStats')
  , ('de18f3040b883b5b', 'client', 'Rare' || chr(4) || 'card rarity', 'ada8fa22929d535cad04b537fd39614612ad9d59', FALSE, 'NativeUI · RefreshCardStats · card rarity')
  , ('34174698bc381cf0', 'client', 'Rare pulls may be posted to the Discord gambler chat with your name.', '9af20b413c2ca79a11498cb299ee67afe394db74', FALSE, 'PlayerCardsUI · BuildSettingsRows')
  , ('abf83473bc8b11c7', 'client', 'Rarest Hand', '36f83c6a32c57bac08a59d95684860f2eeade1dd', FALSE, 'NativeUI · RecordBoardHeading')
  , ('68d7eb35f0d51174', 'client', 'Rarity', 'a3e1e99f26208eb83034e08c40d2fa9b9e636088', FALSE, 'NativeUI, PlayerCardsUI · BuildAchievementsTab, BuildCardStatsTab, RefreshCardStats +1')
  , ('74fe5e6322f6d650', 'client', 'Rat', '34aefad9782a2a0bbf99538f72ea30d068aceacc', FALSE, 'shop catalog · cosmetic name/description')
  , ('9c5c79579e847421', 'client', 'Rat God', '5a21161f59f818e6104685a87f69aec24e14508b', FALSE, 'shop catalog · cosmetic name/description')
  , ('24b87dbadf3b206d', 'client', 'Rat King', 'bd32fe388e42e4dd47a3bed15b57db98cba6499b', FALSE, 'shop catalog · cosmetic name/description')
  , ('2f910b44e3148359', 'client', 'Rat Leader', '9b8e816232ed9a5ad83c86c360a8d8251bae1668', FALSE, 'shop catalog · cosmetic name/description')
  , ('ec71422d79928412', 'client', 'Rat Lord', '543313bf48a5cefabafa073a438e55059c26d999', FALSE, 'shop catalog · cosmetic name/description')
  , ('2260e5d6549af44f', 'client', 'Rat Queen', '36e1f1035819dba3ebe7f5da5183d76a22abbb71', FALSE, 'shop catalog · cosmetic name/description')
  , ('5d91a2b3e46d532b', 'client', 'Rates', 'f04cad5a95ab116b04cd918d0a81bf35b63296f0', FALSE, 'SessionReportModel · Build')
  , ('948adf594528007a', 'client', 'Rating', '6437b7bf655854909262d5f53fbe3bc7a6665b48', FALSE, 'NativeUI · BuildFfaTab, BuildLeaderboardTab, BuildTeamTab +3')
  , ('3490ced9bd0b4480', 'client', 'Rating History  ({0} Elo, {1} rating updates)', 'bb36dd65f9c640c3c35a2f6b91117d03cab7ead6', FALSE, 'NativeUI · BuildFormGraph')
  , ('f859ea534b28b685', 'client', 'Rating after', 'baa06aa04dd50543dacbaee996fca928ba73d1c7', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('dd62d1ca451649db', 'client', 'Rating before', '15f38f90f808c670f03732bf695ac4e2924ec325', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('aa5e490260c5f04b', 'client', 'Rating position', 'b6b5e8a643b4150b10f1aaae95d81d8cc9085f96', FALSE, 'PlayerCardsUI · SortLabel')
  , ('faa8e23012aae76e', 'client', 'Rating {0} | peak {1}', 'df9a4046346586c36a02923fe6d9f03872d63e62', FALSE, 'PlayerCardsUI · RatingLine')
  , ('76954d198691e400', 'client', 'Rating, gold and XP', '547801c2b216778c38b39bbf223111a33f8427b3', TRUE, 'SessionReportModel · BuildTotalsPages')
  , ('5ebd9e4ca23d91dc', 'client', 'Ratings & Rewards', '0d48973d722572c1f7817750bcfdc1c93a212f35', FALSE, 'InfoLibrary · (file scope)')
  , ('455b2461eac3e08d', 'client', 'Ratings (Glicko-2)', 'cca4166af39b86d542170871f61b1311ebcee489', FALSE, 'InfoLibrary · (file scope)')
  , ('dff0df94a8c1250d', 'client', 'Ratings, gold and the series result all settle when someone takes their 2nd game.', 'e313b4f3c742df2b6bf812407bd145e84a1f9b39', TRUE, 'InfoViz · BuildSeriesFormat')
  , ('eae155f580deb959', 'client', 'Reach 1700 rating in ranked (1v1 or 2v2)', '9fcd0e210699f50c689ecb8e2fc7fa9105367085', TRUE, 'ApiClient · AchievementDefs')
  , ('3a98b73fa17d67ba', 'client', 'Reach 1980 rating in ranked (1v1 or 2v2)', 'c7d01b0524369fe5b3c996b27223026f6c017607', TRUE, 'ApiClient · AchievementDefs')
  , ('77b6364f7604291c', 'client', 'Reach 2330 rating in ranked (1v1 or 2v2)', '4739f3bac2dbf726d75cb84d2cbe3551845e51db', TRUE, 'ApiClient · AchievementDefs')
  , ('13a5e72881adbe43', 'client', 'Read more', 'ad086cf55b834c375e209972840f1342401d8c41', FALSE, 'NativeUI.Settings · BuildSettingsChrome')
  , ('2ed4fbc31d00c3dc', 'client', 'Reading a card', 'ea1e194a903d0c5f05c139f2012997ac724f3808', FALSE, 'InfoLibrary · (file scope)')
  , ('7f8d50b8e50f6ae4', 'client', 'Ready Up', '55ad58fffa08821614376510977de2bd74d273c5', FALSE, 'NativeUI · BuildRankedRow, BuildTeamTab, BuildTournamentsTab')
  , ('137f5a2472426c2f', 'client', 'Ready-up failed — retrying search', '164da91182aa67abb68e074a1025d16f086001f3', FALSE, 'ApiClient · ReadyUp, ReadyUpTeam')
  , ('ea277f5d769c2bec', 'client', 'Reason', 'f219cc0614ae6860f43a3cd84b5cf31fc312cd9d', FALSE, 'MailUI · DrawReportModal')
  , ('e848a724fd07283d', 'client', 'Reason (optional)', 'f6826f8fc9b458f2ce8117b27474b6a55d07dc28', FALSE, 'NativeUI · ChatMuteMsgDuration, StartAdminBanFlow, StartAdminReverseFlow +1')
  , ('4f93e2fd59364af6', 'client', 'Rebirth', '89992da5b314fd678578b076988ea33bb0215128', FALSE, 'shop catalog · cosmetic name/description')
  , ('4dd589a0e595aa79', 'client', 'Reborn after defeat', 'c4097eedd44962a5de126d3bf379be9849404efc', FALSE, 'shop catalog · cosmetic name/description')
  , ('d93e6f80f36fca34', 'client', 'Recent', '76eec760c9b6e63eda7e9834fa40bc26d6f58eef', FALSE, 'PlayerCardsUI · RefreshTradeLists')
  , ('9de65b2549d666fa', 'client', 'Recent Async Tournaments', '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', FALSE, 'NativeUI · ShowRecentTournamentsPopup')
  , ('df1a102e003bcc28', 'client', 'Recent Ranked Series', 'cd1b79232cfd3e7f9b778644754e2edcd0055747', TRUE, 'NativeUI · BuildAdminTab, BuildLeaderboardTab, RefreshAdmin')
  , ('e8dc06c32c0e1fac', 'client', 'Recent Sync Tournaments', 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', FALSE, 'NativeUI · ShowRecentTournamentsPopup')
  , ('e1db91ad1b9df536', 'client', 'Recommended: the default. All seven game controls can take a mouse button; the mod''s own controls cannot.', '75a9196e01de8ba0a6f26b2e9897fd88f80e22c9', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('9d9cb4fb7499f359', 'client', 'Recommended: the default. Every screenshot and every other player''s habit assumes it.', '735b8491f8350d1da0c265ac86eb293f27f6a797', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('c33aff3badb191f4', 'client', 'Recommended: the default. F5 always opens this menu, whatever you set here.', '71430f58f352d8df8ba31dccf98876ca970201a2', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('1996fa5af6989f26', 'client', 'Recommended: the default. Left Shift also cycles the base game''s own map art. Both follow this control.', '73b322e48297d90e4dd299c4ecc316e8fb665e71', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('a0104fa7c787f5f7', 'client', 'Recommended: the default. Space also readies you up in a lobby. Move Jump and the ready-up key moves with it.', 'a70f80e18ffb09c4f86379467b0e46aa43e7c087', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('154155ea034efb66', 'client', 'Recommended: the default. This one is read while you are typing, so it needs a key that types nothing - a modifier, a function key or one of the navigation keys.', 'e9953ed2c5dca51968dae185a5ca47c61ecfe98b', FALSE, 'NativeUI.Keybinds · KeybindRowRecommended')
  , ('c046dcd2c285005b', 'client', 'Recommended: {0}', '94d6b0146666d0f33f4f45ebbffac92008602dea', FALSE, 'NativeUI.Settings, NativeUI.SettingsDrive · DriveL11, SettingsRenderPane')
  , ('ed41adb43ef92902', 'client', 'Reconnect suppressed (broadcast identity)', '398370590a079a888b5d97632433b5f3c85d9dd8', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('a2bbca7fa2249434', 'client', 'Reconnect to Match', '8386805ac1a372885719e9a22b45ad0ee7a6a723', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('35b17dfd8f06175e', 'client', 'Reconnecting to {0} (region {1})', '2fda990236b5d4a119b5b24577205c80ca45433d', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('62a28ba99fe537c8', 'client', 'Record removal failed: {0}', '706ccbdd719188f94e52d9feb0f44b1faa092a78', FALSE, 'NativeUI · BuildCompareRecordsPanel')
  , ('a34573eb84fd33a5', 'client', 'Record removed.', 'ef916cd7f6aaa4e1d2941e302595ebf9ee59c786', FALSE, 'NativeUI · BuildCompareRecordsPanel')
  , ('b609dd2a7d2ae301', 'client', 'Records', 'e51c55255be9007d473b3c04b4553c2a27d6f03b', FALSE, 'NativeUI · TrMetric')
  , ('1f35f046ca078416', 'client', 'Red Cursor', '8944bac56fb71a84e3ae82e1b90e93e2f2b4bb1d', FALSE, 'shop catalog · cosmetic name/description')
  , ('505d826bac112c1d', 'client', 'Red Name', '126a8e3bc4cc743f66d97a23baa4fbd94bca9cd1', FALSE, 'shop catalog · cosmetic name/description')
  , ('8d49c7d42dc350d6', 'client', 'Red Scarf', '347e5e3118d0a520df81aed8a23e6e5b11149fbc', FALSE, 'shop catalog · cosmetic name/description')
  , ('cb91578a70473556', 'client', 'Red mouth', '00d06d25c7a22bc5d19066c924148f44bae87c64', FALSE, 'shop catalog · cosmetic name/description')
  , ('c9486d81f9d6abf7', 'client', 'Red ring: this preset has items an unmodded player cannot see, so it cannot be your vanilla default', '272e33806900fb117b6fc4b9ba6486734b3298a4', TRUE, 'AvatarDefaults · PaintLegend')
  , ('03743368bfc09bcf', 'client', 'Redrawn from Spirit''s diagram: Conditional damage never Refreshes twice in a row.', '17cf3ff04e9a66a27d2ad22466075f8965e34735', FALSE, 'InfoViz · BuildRefreshGate')
  , ('da541670b0dc3631', 'client', 'Reduced keeps the hit feedback without the camera motion', '653b3acdfbacbb685b96f9fc013a3f54d8948911', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('845b086a7fbd835a', 'client', 'Reef Shark', 'c3302e6912c3f125b917b0005031be5401efb552', FALSE, 'shop catalog · cosmetic name/description')
  , ('41d390e62fe2dede', 'client', 'Refresh', '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', FALSE, 'CompetitiveUI, InfoViz, NativeUI +1 · BuildAdminTab, BuildPage, DrawLogViewerModal +3')
  , ('681c635979858bca', 'client', 'Refresh?', '036f463fe254002c12fdad59af1d8f79d7072375', FALSE, 'InfoViz · SeqTable')
  , ('ee8257609579ab51', 'client', 'Refreshing too fast - give it a sec', 'c3d2925a7bdb78bf6843c08b909c46a2f966f744', FALSE, 'NativeUI · BuildPage')
  , ('725c315d1c164ba0', 'client', 'Regen', 'eb5c821caab94e7e985a15dfcbf1150b086c8ba2', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('389ee87fa2b2226c', 'client', 'Region Time', 'ad0e59467721c89f6c98a699c6940779ba22d939', FALSE, 'NativeUI · TrMetric')
  , ('f444dd90b18a22de', 'client', 'Region distribution', 'd3c9dbb10b2776caea1c1e5bca8f578467f17836', FALSE, 'NativeUI · BuildComparePieChart')
  , ('cb173826046b9943', 'client', 'Regular', '8d4e4ef3ea5252ec5235e4b1dd463ae9c302422c', FALSE, 'shop catalog · cosmetic name/description')
  , ('6f43d60195f6d487', 'client', 'Rejected Reports', '89891d2edf2bd28e5b4952ef12239ee6da11ebd6', FALSE, 'NativeUI · BuildAdminTab')
  , ('df1814deb572b30b', 'client', 'Rejoin', 'c6240d696b95c7450d1dc0c394d5227906e04ab2', FALSE, 'TeamHoldReturn · DrawOffer')
  , ('e4b1a55872ab7dc2', 'client', 'Reload', 'cce7155371fc26686b89c7452337d8419692f31e', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('0348defe86351f3c', 'client', 'Reloader', '35360f9710e178438cf0beacd29bc2cf155be508', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb1386dc31e8fcf3', 'client', 'Rematch?', '2b8ca1c6f332d7ac6f7dc56c8abc7aceaae03d75', FALSE, 'QuickChat · Phrases')
  , ('a39c69aa4af9174c', 'client', 'Remote Killer', '71bc625305721ab9a3c23b492ef10e968fa8d335', FALSE, 'shop catalog · cosmetic name/description')
  , ('bced5e3b4f62b4c4', 'client', 'Remove', 'e963907dac5cd5c017869b4c96c18021c9bd058b', FALSE, 'NativeUI · ApplyShopRow')
  , ('06d68c0c93bcc698', 'client', 'Removed from 1v2 queue after 30 minutes of searching - rejoin if you''re still here!', 'd21a85952028305e60186b5da8eb8bf91d830d70', FALSE, 'ApiClient · UpdateOvtQueuePoll')
  , ('ed2bee0265a07157', 'client', 'Removed from 2v2 queue after 30 minutes of searching - rejoin if you''re still here!', '518c2f6c92751ed83a03f0e954f5f1656bd529c0', FALSE, 'ApiClient · ParseTeamQueuePoll')
  , ('d26d0c08c02e905f', 'client', 'Removed from FFA queue after 30 minutes of searching - rejoin if you''re still here!', '6bf365c0a188bdb8f985479b260fb60969b94fde', FALSE, 'ApiClient · UpdateFfaQueuePoll')
  , ('68a61bb1c87662ca', 'client', 'Removed from queue after 30 minutes of searching - rejoin if you''re still here!', '77e4aa898269d071d37354feabcd688601921fb9', FALSE, 'ApiClient · UpdateQueuePoll')
  , ('e6ed090bbd8195be', 'client', 'Removes you from every queue and lobby in every mode — 1v1, 2v2, 1v2 and FFA.
Use this if the game thinks you''re still in a match you''ve already left, or if joining a queue keeps telling you you''re busy. It won''t affect a game you''re actually playing, and it never touches your stats, gold or rating.', '2a1b006c4b79cdc5a4c7c30b4ee51652307056c3', TRUE, 'NativeUI · BuildSettingsTab')
  , ('6fe9842db9d19141', 'client', 'Render your name at 130% size.', 'f8f842c1e0272e4182ba74a5e1e671b7f8a60f30', FALSE, 'shop catalog · cosmetic name/description')
  , ('83f263b559925710', 'client', 'Render your name at 160% size.', '452eca3c01172368dcdcba51547a09396c0414a5', FALSE, 'shop catalog · cosmetic name/description')
  , ('8746ab9f9b6503e4', 'client', 'Render your name at 80% size.', '1c9cc5f67a8641039f1e6e54ad1f7adec3a9c7c9', FALSE, 'shop catalog · cosmetic name/description')
  , ('d265b90c740ac5bb', 'client', 'Rendering card art {0}/{1}...', '9ebdbabf49003a4b0e4a977a42024b8b711c42ce', FALSE, 'NativeUI · ExportTierListCoroutine')
  , ('2fb1c1d57870c7c8', 'client', 'Reply', '6c2bb735a46a8ff307fe2e638d581295b2a49e09', FALSE, 'MailUI · BuildReaderView, PaintComposer')
  , ('f3d270720ff3a166', 'client', 'Reply all', '84c27c09b6a8df1ece7757f54242c1f32da3b559', FALSE, 'MailUI · BuildReaderView')
  , ('960f92ec35a855c6', 'client', 'Reply all is not available for this message.', '82727ae5be7bff2bef34a61abe1734751baa5136', FALSE, 'MailClient · ErrorDetail')
  , ('a70a5fb2ba646559', 'client', 'Reply to all', 'df424aaa0ba06e961297ef5bd0e1638062440a0f', FALSE, 'MailUI · PaintComposer')
  , ('02121f673902efda', 'client', 'Report', 'ee45c30326b750387589752c0f75e1dd87ddc7e4', FALSE, 'MailUI · BuildReaderView')
  , ('e573bb0bf4f2ab3b', 'client', 'Report approved for recovery - an ordered replay is still required.', '025d23a1daab37a02af4e5ffc59a9a15b88553a4', FALSE, 'NativeUI · OnAdminQuarantineAction')
  , ('7c822307c6b1c668', 'client', 'Report dismissed for good.', '699209ea2c9bafabb100f17a87ff4792d228abaf', FALSE, 'NativeUI · OnAdminQuarantineAction')
  , ('3f6dd33f95a50171', 'client', 'Report failed to send - try again in a moment.', 'cb3df1b14988aa02a85af24309f57e8594a845eb', FALSE, 'NativeUI · HandleReportCommand')
  , ('52f70ee24279cc15', 'client', 'Report this message', '080b46978fbe937fe9486bfd39ca94188e218eb8', FALSE, 'MailUI · DrawReportModal')
  , ('7933cc65e1e43cc3', 'client', 'Reported - thank you. A moderator will review it.', '61835ff8c458f2741640d8fd27608b925ba3e297', FALSE, 'MailUI · SubmitReport')
  , ('ae5bd76f574f358f', 'client', 'Request failed - try again.', '48336ec0bad6a9a4573ca7b75930b7ee5f6c2012', FALSE, 'MailClient · ErrorDetail')
  , ('f8c3b1654dc27879', 'client', 'Requeue', 'e37b50a99f9235f172f8c37781b0f2f6f1d82221', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('54d2d36119656065', 'client', 'Reset all controls', '787da19d9c98597eedb26f8010bba225ce9314a3', TRUE, 'NativeUI.Keybinds · KeybindBuildFooter')
  , ('81b6f33318bb9e33', 'client', 'Reset every control to its default?', '69f4dc357717a2c16f314ad75e3461168c06e912', TRUE, 'NativeUI.Keybinds · KeybindRenderFooter')
  , ('ffe4136002328f40', 'client', 'Reset the window', '71bf6674aaabb4f9885c20f994c05de35197d594', TRUE, 'InfoViz · BuildRefreshFlow, TextFallback')
  , ('02455ff22b487b22', 'client', 'Reset this control', '364d2c77fa6a2f9bbca0200fb77887ee5725a2e7', TRUE, 'NativeUI.Keybinds · KeybindRenderPane')
  , ('f83a6505ee235888', 'client', 'Reset this tab to recommended', 'fb3558e7ba6e103a876c7c7af5b00cf23522b91d', TRUE, 'NativeUI.Settings · BuildSettingsChrome')
  , ('96d48fe9718568ab', 'client', 'Reset this tab to recommended?', 'f2772649a524f4d225eae65f525ca82e3f1f312e', TRUE, 'NativeUI.Settings · SettingsRenderResetPrompt')
  , ('6aefe5059d63d0e1', 'client', 'Restore the vanilla random map color rotation.', '3e4d1a0220051e28866e692fcc1749e765c15125', FALSE, 'shop catalog · cosmetic name/description')
  , ('58e34f41f31eb642', 'client', 'Resuming series at {0}-{1}', '51e8026c9a204f54a6bd4b1a2d8953138483eb22', FALSE, 'ApiClient · ApplyResumedSeriesScore')
  , ('7ee66c85b18c5bb0', 'client', 'Retry', '9f5cd8a2e8807d73efa02c844bfbca9fe552b283', FALSE, 'NativeUI · BuildMusicTab')
  , ('fa7e8cef9e201a6d', 'client', 'Return', '24f096b221f9534bcad007f2b5a32b490950b5b5', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('9297cc8ea92d7959', 'client', 'Return to menu', '9c3fe9f3b161a19b09056dd1ff4b1cfe7b045af8', FALSE, 'CompetitiveUI · DrawMatchFoundStuckOverlay')
  , ('136ec55c8ce85296', 'client', 'Revenue', '35cf82f9d2a9c8ba5943837ec0d6646d49a7a51e', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('44bd426b0542d87a', 'client', 'Reverse Series...', '583d156c59fe2e53385c84b50e54a60e4aa6f593', FALSE, 'NativeUI · BuildAdminTab')
  , ('8ed72e941d7dcbde', 'client', 'Reverse a ranked 1v1 series', 'ec6c6716f30d035b002548cf9e1db208386774b0', TRUE, 'NativeUI · StartAdminReverseFlow')
  , ('6b43ebc09b19e182', 'client', 'Reverse {0}', '36d3898776980beda04f3c0a05601498b581a63d', FALSE, 'NativeUI · StartAdminReverseFlow')
  , ('72227ce31f4e8e6c', 'client', 'Revoke', '0be720759ff04d13c5706881d5d227a2621f91a6', TRUE, 'NativeUI · BuildAdminTab')
  , ('a593067a8ec0d1b5', 'client', 'Revoke Artist...', '633f1246d9f9fb9ac561e393879b8a28b0bc7814', TRUE, 'NativeUI · BuildAdminTab')
  , ('216f8c7dad3b04b0', 'client', 'Revoke Translator...', '5505effc85240d0187d0a19a306e36e6f38da3e7', TRUE, 'NativeUI · BuildAdminTab')
  , ('f6461162d7642d8a', 'client', 'Revoke which alert?', 'afe7fa9dd2a7353a1536ab0cd1948d49a119f36a', TRUE, 'NativeUI · BuildAdminTab')
  , ('46fe5bdea432ddc2', 'client', 'Revoke which translation role?', 'd609539d8e0863475418b15564c55edfe9667fb6', TRUE, 'NativeUI · BuildAdminTab')
  , ('145d5e6640ad6679', 'client', 'Rich forest-green body color.', '64beb88d5891e40c3adbadb8b1959b410db02d70', FALSE, 'shop catalog · cosmetic name/description')
  , ('1ee9d7c98695afd0', 'client', 'Rich purple blocks on a dim cool backdrop.', '969e7cedcc56832829613fa1b9a6909c8e2c57e4', FALSE, 'shop catalog · cosmetic name/description')
  , ('4065d4a04438e233', 'client', 'Ricochet', '4c13fb803303ed060cc6550b150091191bc41955', FALSE, 'shop catalog · cosmetic name/description')
  , ('cb82d96051e801a5', 'client', 'Right Alt', 'cdd21f785881085857a64aca62332db8fcc994e4', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('89acc6e019715e78', 'client', 'Right Arrow', '65aaa11ae3f1b7af16144e162c2cf02529785b40', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('28edc0fe0c3c62a8', 'client', 'Right Command', 'e45f978f4d3c4dabff9bd5975223a1f886324897', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('9809761cc304da49', 'client', 'Right Control', 'b7f53d2d700b6a229add545063e13b20af2abbe6', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('6225e27b8df14ca7', 'client', 'Right Mouse', 'e1b5767fcb7ecce9e83401ff97ffd04d7259500a', FALSE, 'NativeUI.Keybinds · KeybindMouseName')
  , ('2c2c56d3fba29198', 'client', 'Right Shift', '26a36a6dade2691e3015aa638d067c6da3454201', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('ba5d4b19c3243724', 'client', 'Ringmaster', '451ea8e159e1965bcf73f70f9cc38a944c03fdff', FALSE, 'shop catalog · cosmetic name/description')
  , ('4356e1f9e0e4cc96', 'client', 'Rise from the Ashes', '97800f5d41e76e932cfd498fd7502f99f1e80a04', FALSE, 'ApiClient · AchievementDefs')
  , ('5ab18e987855fcf3', 'client', 'Rising Star', 'f2f5d68e6499e7eddf0b08d8dbbc483e134f6843', FALSE, 'ApiClient · AchievementDefs')
  , ('06d95cefa1d007e6', 'client', 'Riveted steel great-helm with a T-slit visor.', 'c3916b69a2b9f6d25258ad6c41417cea07f376f8', FALSE, 'shop catalog · cosmetic name/description')
  , ('070639ca8b6f709a', 'client', 'Roc', '0db60afc565e9771dc93264075a95ebee201ab31', FALSE, 'shop catalog · cosmetic name/description')
  , ('7a0f8011c1cb0624', 'client', 'Rolling DPS (15 s window)', 'b1f400711752a533e91773aacef324f6ab1a4486', FALSE, 'SessionReportModel · Build')
  , ('23327ceb1b355548', 'client', 'Rolling block % (15 s window)', '9c7dd1d11383f73528a063432ad7775e2309df3c', FALSE, 'SessionReportModel · Build')
  , ('7cf8613cdf7c7bf4', 'client', 'Rolling hit % (15 s window)', '0c9e1f450655084f429f432f487e8f61b3e8d4f7', FALSE, 'SessionReportModel · Build')
  , ('941644ff228b3130', 'client', 'Room code: <color=#C0E0FF>{0}</color>{1}  <color=#888>(if auto-connect fails, Reconnect or join via Private Lobby)</color>', '08ce8ad5d440205c97a9218cc0cc8ee067b96182', FALSE, 'NativeUI · RefreshTournaments')
  , ('67e7499de92c9f59', 'client', 'Room rule: same cards for everyone', '14d5d902774479f191108203f0cde10ffa581be7', FALSE, 'CompetitiveUI · DrawRoomRulesBanner')
  , ('5dff12f6f0e0aa97', 'client', 'Room rule: same cards is off this game', '6998e9a3275acd08f4e7d513be6ad47ff085fe35', FALSE, 'CompetitiveUI · DrawRoomRulesBanner')
  , ('b427abd7704b4891', 'client', 'Room rules: friendly fire OFF', 'be7d3fea97c7cc3dfc50cbbe8ed3f38da0e2817f', FALSE, 'CompetitiveUI, RoomRules · DrawRoomRulesBanner, OnGameStart')
  , ('50e343ebd5674637', 'client', 'Room rules: friendly fire OFF, same cards for everyone', 'abd3d83e0070ed9e080e68c74269d780853e706a', FALSE, 'CompetitiveUI, RoomRules · DrawRoomRulesBanner, OnGameStart')
  , ('5dd473c9fbc31ca3', 'client', 'Room rules: friendly fire OFF, same cards is off this game', 'd4d5e9c22193851ecbeb46ba05041fdb7a74e074', FALSE, 'CompetitiveUI · DrawRoomRulesBanner')
  , ('3a97a7463290776c', 'client', 'Room rules: same cards for everyone', 'cea561e8aa361d1189d84382f6532df0f7782686', FALSE, 'RoomRules · OnGameStart')
  , ('00ee52283a370c22', 'client', 'Room settings did not match — left the room', '9571952fff479fc5abc61b42c55100f7b21d7043', FALSE, 'Plugin, SpectatorSync · OnJoinedRankedRoom, OnJoinedSpectatorRoom')
  , ('35ad337d5d3a9060', 'client', 'Rose', '51ad0eae3f66ecd3c72bfac9373650513d6f6603', FALSE, 'shop catalog · cosmetic name/description')
  , ('5981cfc4bec6d2aa', 'client', 'Rose Quartz', '2568e0420d78a050256fff684957c4eb34011abe', FALSE, 'shop catalog · cosmetic name/description')
  , ('716553e5d4ffcdf8', 'client', 'Rosetta', 'db73904ee194bd4fd1333249d0a3c3d19476c274', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('0b37036b006bc7c2', 'client', 'Royal', '2c16ea11eedff827b4e8ce41cee5f947d3418592', FALSE, 'shop catalog · cosmetic name/description')
  , ('a5239cbe85ee4b07', 'client', 'Royal Gradient', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', FALSE, 'shop catalog · cosmetic name/description')
  , ('2b9dc3fb741aa589', 'client', 'Royal purple drifting into pale cyan. Two-color gradient.', 'c085d0e3b3ec14e7c2c9f0463ff2c8a00dec591e', FALSE, 'shop catalog · cosmetic name/description')
  , ('319ab86ed9da45f2', 'client', 'Royal violet body color.', 'e13a8edd76d54551c7e4fbee3597e104900c26f7', FALSE, 'shop catalog · cosmetic name/description')
  , ('26f5000049cdaad0', 'client', 'Rush', 'cc4a564197f4557e49a393128354268ab071fba2', FALSE, 'shop catalog · cosmetic name/description')
  , ('cde7ff6ff03c626f', 'client', 'S p a c e d', '2ba111743a13e4814bdbebc66f111af1605fcea4', FALSE, 'shop catalog · cosmetic name/description')
  , ('16270e075ff09c38', 'client', 'SALES OPEN', 'f76a4926ab971b67975e14dbee83d6872ac9bb50', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('5c65ef160d2f5147', 'client', 'SERIES COMPLETE {0}!', '420b7ab0cb9993c4d5ddeec670cee91d97fb4b2c', FALSE, 'ApiClient · ReportMatch')
  , ('1c854c38083d1b76', 'client', 'SERVER', '8d4ba065ae312536d8bdc5b787d19bb682bdc302', FALSE, 'InfoViz · BuildReportPipeline')
  , ('f63dc62e1917bfe1', 'client', 'SF A', 'ddcb991b57e50d9e3d28f6969711a34b411c5a79', FALSE, 'InfoViz · BuildBracketFlow')
  , ('4f7e0e667293a970', 'client', 'SF B', '146fb58ce6a9e9e0c19f9433130c9b3e0431f1b8', FALSE, 'InfoViz · BuildBracketFlow')
  , ('26f0f8a2335ba795', 'client', 'SHIELD EDGE BOUNCE', 'fc64ad2e2aed235943184651399172baabb8d6c4', FALSE, 'InfoViz · BuildMovementWindow')
  , ('912677eb32da6ab4', 'client', 'SHIFT', '149b8de2b0282bcde23304b8948eaaf895a98809', FALSE, 'InfoViz · BuildKeyboard')
  , ('1810e65fb6bc6f81', 'client', 'SHIPS IN A RELEASE', 'd7bb69fb19763c09ddf7ae009395afc7badcfc2e', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('3d771675aa9386e3', 'client', 'SHOP', 'f2e1c7fad591bf812899592b3df6cde5ff734de6', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('49c8adce945e10af', 'client', 'SID''S COMPETITIVE ROUNDS', 'd9baef5110422c5e7f32144bde9656cc19bc8806', FALSE, 'NativeUI · BuildHomeTab, BuildPage')
  , ('054a9e0ffa32420a', 'client', 'SIGNAL, FLAG, HUMAN REVIEW', '9e76c2cfaa74237c4667dda1106096059423809a', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('84a3e55555f79ce0', 'client', 'SIGNED', '127edee78d2a1f0376c397ad1ff1d8778bf49e91', FALSE, 'PcLabels, PlayerCardsUI · MarkLine, Tr')
  , ('f55728ab65b58c94', 'client', 'SIGNED' || chr(4) || 'pc.signed', 'ec50a3dea046319dbac62b505fe2f7ed7d05541a', FALSE, 'PcLabels · Tr · pc.signed')
  , ('2540afb343a5f6b0', 'client', 'SIGNED REPORT', '8a2584377c89eac38f632458e5033c953d620077', FALSE, 'InfoViz · BuildReportPipeline')
  , ('572f63ba8113eadc', 'client', 'SPACE', '6a395052c9ebc4235d024c28291d96b8cac3053b', FALSE, 'InfoViz · BuildKeyboard')
  , ('49418f9ec59f58ec', 'client', 'SPECTATING', 'a93910c41c841b78441c8c7061a07ca8a698dc3f', FALSE, 'SpectatorHud · ComposeBarLine, ComposeCompact')
  , ('74eeb293eb5406f0', 'client', 'SPECTATOR', '589d489cd61eb2b32e5d41f1253f6d4f5a176a55', FALSE, 'SpectatorHud · ComposeBarLine, ComposeCompact, DrawBlackout')
  , ('1d0664804d74f851', 'client', 'SYNC', '2f8d236566d2393cd3a112e7190d8837c8004cc2', FALSE, 'NativeUI · RefreshTournamentGameIndicator')
  , ('b939a9ae4f89cb0f', 'client', 'SYNC (weekly)', 'c4477dfa9e0ef6b9e35433b86e32cb10888ee6a8', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('d4d9aacbbfbe3f57', 'client', 'Sabertooth', '0a65a2c2435ad7171bba2926c9ea9de4d8fa4ed3', FALSE, 'shop catalog · cosmetic name/description')
  , ('fdfe7ec82dafaf6d', 'client', 'Sadness', '2df908378d5e5235eb570a2c8b7a70a509279c87', FALSE, 'shop catalog · cosmetic name/description')
  , ('0039162cb1a6ccf5', 'client', 'Same Cards: OFF', '45408601fd361fc80d80e08668d8bdf72085d6e0', FALSE, 'NativeUI · BuildFfaTab')
  , ('a129c6ff8e7ae04e', 'client', 'Same cards', '1b832de6de68664139795f9190078d2af76278c5', FALSE, 'RoomRules · Summary')
  , ('48aa4e808227909c', 'client', 'Same cards in queue games: <color=#88FF88>ON</color>', '625202c5df3fbd777378c52e5f3d6b9ca3fa5007', FALSE, 'NativeUI · PaintPrefSameCards')
  , ('e33f5d96f2fad1f8', 'client', 'Same cards in queue games: <color=#FF9966>OFF</color>', 'b04619c3cdd701c6b9314c2a5c1af78c6d9a8c39', FALSE, 'NativeUI · PaintPrefSameCards')
  , ('b4489e1753b09ca0', 'client', 'Same cards: OFF', 'b0b2b820bcfb2fa8bcf150c069f23c562d765014', FALSE, 'NativeUI · BuildOneVTwoTab, BuildTeamTab, RefreshFfaTab +1')
  , ('af50d15ccc91d824', 'client', 'Same cards: ON', 'fb37e857128f8e9e6452c1511f0f974a99accbca', FALSE, 'NativeUI · RefreshFfaTab, RenderHostLobbySection')
  , ('ba7370f908154504', 'client', 'Sand', 'b36fbc6e8df68fb14280742f8b5bf0c0460a6fe0', FALSE, 'shop catalog · cosmetic name/description')
  , ('970796f2ee569bbc', 'client', 'Sapphire', '52086129a3b5fc408aafd7614d3de4b7de05c35a', FALSE, 'shop catalog · cosmetic name/description')
  , ('24217068bcc775e9', 'client', 'Sapphire Gradient', '1c933f68509c9bed6e49ae0ae73a5485f1006267', FALSE, 'shop catalog · cosmetic name/description')
  , ('5e96f965b35fd77c', 'client', 'Save Votes', '71b36cbeefd3cb3cc776984731e0f86c9c663c32', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('99a8b620c8e2e101', 'client', 'Saving your new picture - your card updates here once it has been sent.', '875058e8f2afd5e8e096f4aaf321f5c904f65086', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('9304732c07ab428a', 'client', 'Scale', 'a29f0256272e79ca91a1c4e608f09a6264397d12', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('61873d24740b083e', 'client', 'Scarlet', '1207638e87127a3ee0ecce2ac2254ea4a7aa6c90', FALSE, 'shop catalog · cosmetic name/description')
  , ('4edc3d085e6490b5', 'client', 'Scavenger', 'c8b91fa5ecf4c5a619a45b3f5d0e49419024f8eb', FALSE, 'shop catalog · cosmetic name/description')
  , ('19c2a45c2ec2988a', 'client', 'Score', '489f4877244a299131d309f0ca10733c1a41251c', FALSE, 'PostSessionReport · BuildCells1v1')
  , ('f7c0cd90c321493a', 'client', 'Score progression', '3295f8d8261083d7f28652ae6b6758ca2369e347', FALSE, 'NativeUI · ParseFfaTimeline')
  , ('9c3b3f3a3a019d79', 'client', 'Score race', 'a687af727dabc08baa2d9a3f4092d267f2e2745d', FALSE, 'SessionReportView · DrawSetPage')
  , ('2804ebac5387a06b', 'client', 'Score race (rounds won per game)', '59a6d8845f629c46fe5bdc305369373ef914fc6c', FALSE, 'SessionReportModel · Build')
  , ('698e7b9edf3d3c5b', 'client', 'Scoreboard', '5fbd163f8a990dfdd648ca51f2cffa129da66890', FALSE, 'NativeUI.Keybinds · KeybindRowLabel')
  , ('03fd7046e9ef2d63', 'client', 'Screen shake: <color={0}>{1}</color>', 'd2ad76935ab2f3bb89bab2b67c98d79e2728d61e', FALSE, 'NativeUI · PaintScreenShake')
  , ('8709d2a7417a8af1', 'client', 'Search Random', 'fb043b0389a26d7aed0805a82374ca520672afa6', FALSE, 'NativeUI · BuildTeamTab')
  , ('0af12ce407aedc11', 'client', 'Search Ranked', '903dc15e26d8934a5bd54ce5dad491d5f406b9b4', TRUE, 'NativeUI · BuildRankedRow')
  , ('63f7bab1460114b8', 'client', 'Search cards', '580d82bb1d98c79f2293e2759772ad0075ac0045', FALSE, 'NativeUI · RefreshCompare')
  , ('25380d8fed2297eb', 'client', 'Search for a player by name', 'd8c04e56c607e25ce83b6814733df533f929c43f', FALSE, 'PlayerCardsUI · StartTradeSearch')
  , ('54860c61d03a34f6', 'client', 'Search players', 'e3799504761fb5e522c834bcab8d7cdafae515bf', FALSE, 'NativeUI · BuildCompareTab, RefreshCompare')
  , ('bd85c879cf3ba261', 'client', 'Search...', '6d7a30a931a35ef0373a28fc4507bf29ba239fda', FALSE, 'NativeUI · BuildBannedTab')
  , ('c10e71128f6d67cd', 'client', 'Searching for ranked match...', 'c88d0a58ce821760b76ba78c6eb1393bc951fab6', TRUE, 'ApiClient · JoinQueue')
  , ('d7951aef0fa367af', 'client', 'Searching... {0}m {1}s  +/-{2}', '7e0098e5bb901181e4f78f50b98fe1c46abf73b9', FALSE, 'NativeUI · RefreshQueueUI')
  , ('fdea4fee02fc1df2', 'client', 'Searching... {0}s  +/-{1}', '122661d9a77d8948a4efb1c1cf20a6a3cae1bfa9', FALSE, 'NativeUI · RefreshQueueUI')
  , ('8b51734bf0cceea4', 'client', 'Searing electric-green body color.', 'c2e5f7ff5a1b8a7c192fd6c5c49f8ff3a27c1d45', FALSE, 'shop catalog · cosmetic name/description')
  , ('371c04da36be20b2', 'client', 'Searing-lime neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', '6605cbf9da74dcde301ce970f5892a9c6f3697f1', FALSE, 'shop catalog · cosmetic name/description')
  , ('35bd46d542291519', 'client', 'Seasonal Spring', 'fbdf3954fe302a9669bb5146924faa655c14bd1e', FALSE, 'shop catalog · cosmetic name/description')
  , ('98dca83410faa64d', 'client', 'Seat held for {0}: {1}', '90aaed15747edd34574438630be3c33807ba421f', FALSE, 'FfaReadmit, TeamHoldBanner · Line, OnHoldsAnswer')
  , ('fa3c7fa2c12e25e5', 'client', 'Seats full', 'b8581dbd72a99b718c0da5e35f325b981899d4e0', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('0980191d55e349c7', 'client', 'Secure connection restored - opening the portal.', 'c18052444ebb91e7b9e8da638686e3640060af3d', FALSE, 'SecureRouteText · RestoredOpeningPortal')
  , ('ac43d3d37df427b4', 'client', 'Secure connection unavailable - signed-in features are off until it is back.', '7f7f6fed4b22a7ad9257e1dbf8ab4415e71c0268', FALSE, 'ApiClient · NoteTicketExchangeRefused')
  , ('a37df86fbc75464c', 'client', 'Sekhmet', 'aa113cbbfd891790d0e9b1375977b4f567add11e', FALSE, 'shop catalog · cosmetic name/description')
  , ('4824e78a90026e35', 'client', 'Select', '8598222918d3c6e513d63060cf55e2971ded729a', FALSE, 'PlayerCardsUI · BuildBinderView, RefreshSelectRow')
  , ('04b8eda0beb6c7c9', 'client', 'Select 2-12 players (left) to see who beats each of them most.', '48cbbdf0892841c2a1ddc258564365aa33ecbce3', FALSE, 'NativeUI · BuildComparePlayerNemesisPanel')
  , ('d76fe8f87a017c84', 'client', 'Select 2-12 players to find their common nemesis.', 'e80e8a6caafd8578b93bf98472d9d2e28b8940fd', FALSE, 'NativeUI · BuildCompareNemesisPanel')
  , ('fbd3f1a657e23fa4', 'client', 'Select cards first - click the cards you want to shard', 'b7b5a1f531f33afd0a239789be05929a45d69426', FALSE, 'PlayerCardsUI · OnShardSelectedClick')
  , ('4e1a7e002aa898fb', 'client', 'Select players (left) to chart {0}.', '653473b68ffd7d51aa82c742fe125934177dd762', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('59f6bde0a7f60351', 'client', 'Select players (left) to compare {0}.', '1175545bb73a476b0d1a87051cb90a94ed11cc7e', FALSE, 'NativeUI · BuildCompareCardGrid, BuildCompareMetricTable')
  , ('843f580e89a1c339', 'client', 'Select up to 12 players', 'fb4e2d95d98953646b6c1b210ec64b47348fe61b', FALSE, 'NativeUI · BuildCompareTab')
  , ('c3097a183302fce5', 'client', 'Selected', '9a976fc228b6b33656174ebd6decca02c9068378', FALSE, 'PlayerCardsUI · FillTile')
  , ('12a147f5ca9dd638', 'client', 'Selected {0}/{1}  -  click a card to add/remove', '24ba3677ac4bfe9f46bbc7c35421d9b83c9842b0', FALSE, 'NativeUI · RefreshCompare')
  , ('f51760d7b4a0ccaf', 'client', 'Selected {0}/{1}  -  click a player to add/remove', '757692270a6215efdebe1d9ef46bef9c6c10f012', FALSE, 'NativeUI · RefreshCompare')
  , ('f6f333d6d350d69b', 'client', 'Self-Death %', '3b6bd1fc36ae8d7a9152257169589b6859bfdd29', FALSE, 'NativeUI · TrMetric')
  , ('993e08b5d2c4f5c7', 'client', 'Self-Inflicted Deaths % (boundary + own bullet)', 'c9d191ab8825e1463b0e2f91bdd314cd2bf88b0c', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('c8a7d841ea12ccc7', 'client', 'Self-awareness is a virtue.', '4e759bc7fb00171c1450a5abdb85e63a0d4be467', FALSE, 'shop catalog · cosmetic name/description')
  , ('33492062006fafe0', 'client', 'Send', '9bc2575c3930437e80555f78757b783c842e8e66', FALSE, 'MailUI · BuildComposerView')
  , ('bee07cce9097fc6b', 'client', 'Send logs automatically: <color=#88FF88>ON</color>', 'b269b02b6c54cd0eb478ff53078424b40ebe3f59', FALSE, 'NativeUI · PaintAutoLog')
  , ('c5b429eb9adf1f42', 'client', 'Send logs automatically: <color=#FF9966>OFF</color>', '379f1f1c10fb778ffcff6cfaa59aaf821e2241f4', FALSE, 'NativeUI · PaintAutoLog')
  , ('c6e48e66ff28d8d5', 'client', 'Send ping', '3054ab05070e872c716ae126a3e99c407fdf4eb1', FALSE, 'CompetitiveUI · DrawLfpPrompt')
  , ('9200bcdea0863931', 'client', 'Send proposal', 'f4e29b4329ebebc4ee3fcde8d09b10f4f4b97ad8', FALSE, 'PlayerCardsUI · BuildCompose')
  , ('d3a6bce744430b25', 'client', 'Send report', 'a5b32af957ef73ce072ce21599ce7cd7bf2212ba', FALSE, 'MailUI · DrawReportModal')
  , ('211d46a26008e6ad', 'client', 'Sending...', 'c338c191ab1e9319ba354d56467b938e0ba4e119', FALSE, 'MailUI · DrawReportModal, SendCurrent')
  , ('72612ea13e63f955', 'client', 'Sent', '35f49dcfbfb2e03fdce327671e82bf173b1ccb8b', FALSE, 'MailUI, PlayerCardsUI · BuildHeader, RefreshTradeLists')
  , ('11be5c0c2809d4fe', 'client', 'Sent.', '03c6d014658f7f8a730e57e9909f65ab3754d68a', FALSE, 'MailUI · SendCurrent')
  , ('f4c3fa898d37040e', 'client', 'Series', '40c20d94e78fa142819df8cc9440d30e65329975', FALSE, 'NativeUI · BuildCompareNemesisPanel')
  , ('db8d28abe7a0803f', 'client', 'Series ID (UUID)', '3618548cc4b479da3739bc2676fcb6cabf91722e', FALSE, 'NativeUI · StartAdminReverseFlow')
  , ('cbe8c30cbcc7634d', 'client', 'Series Score: {0} - {1}', '35b9dec4c725630964642fc46ef9413ab161ff40', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('2b6277b71e22c3a6', 'client', 'Series complete: {0}', '366f6b0c2e95252863a672eae68c35cf6c90ed1a', FALSE, 'ApiClient · ReportTeamMatch')
  , ('b2e2bf41f013e8fd', 'client', 'Series streak: them x{0}', 'd285ca1b47468299f4afac9cb03ceae3b7b63c3c', FALSE, 'ProfileCard · Render')
  , ('96ed30b1a4ff872b', 'client', 'Series streak: you x{0}', '19da838577485f27f870de99e7b8669bbe69e1eb', FALSE, 'ProfileCard · Render')
  , ('56f4b006168b90b0', 'client', 'Series {0}  vs {1}  (in progress)', '31b7561e9ca64f61bfd860c5d4af7ecf229dabfe', FALSE, 'NativeUI · RefreshHistory')
  , ('ed8b774e24ef3273', 'client', 'Series {0} (in progress)', '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', FALSE, 'PostSessionReport · SeriesHeaderText')
  , ('7aa6dd3d9c00eecb', 'client', 'Series {0} {1}', '50bcfef87aaad308e18c1ebef30e73433fa21993', FALSE, 'PostSessionReport · SeriesHeaderText')
  , ('694b7bbd6fe29463', 'client', 'Series {0} {1}  vs {2}', 'cbf8b1e91683087706a4ed11db627eb9673a72b2', FALSE, 'NativeUI · RefreshHistory')
  , ('c3a60b1d43f0cc1b', 'client', 'Series {0}-{1}', '353a9486426bb0d11106b53d29d363978e9ffcf1', FALSE, 'SpectatorHud · ComposeBarLine, ComposeCompact')
  , ('81d48a92efee6579', 'client', 'Series: {0}', '7d8e33e493d338e360b00d9457e0ae44f44857c4', FALSE, 'ApiClient · ReportMatch, ReportTeamMatch')
  , ('29d71e9e09a5b08c', 'client', 'Server Alert...', '43e806fad57a21d2cddee2aeedc89b6c65c5fa14', FALSE, 'NativeUI · BuildAdminTab')
  , ('adbb4d619548dbdc', 'client', 'Server alert', 'acd13dafca8e5749f8e6a1a9b53ce55919ccf5f2', FALSE, 'NativeUI · BuildAdminTab')
  , ('99d3e800e6c6e7ac', 'client', 'Session', 'f7f1997c6cd1aa051279675742272a956e7db628', FALSE, 'NativeUI · CreateFfaRecentMatchRow, CreateHistoryRow, CreateTeamHistRow +1')
  , ('73be4f1b886889cd', 'client', 'Session Info', 'ee7f6b62b61a12ec18d69e017d11a4a8e7c9c4aa', FALSE, 'NativeUI · BuildMyStatsTab')
  , ('6c07743895412e87', 'client', 'Session Series: {0}', '88f7371eb24196978c257d2c1cc4a782622f8329', FALSE, 'SpectatorHud · ComposeBarLine')
  , ('1de437d1a86de5a9', 'client', 'Session expired', 'b828190ecb4a0c4aa958070f6e4bb75a88c19085', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('3e1302982adf89d9', 'client', 'Session games', 'a8261c72e1c14f8f93320767108077b4c0196a16', FALSE, 'PostSessionReport · ComposeFfa, ComposeGameRows1v1')
  , ('0323dba24dc4ca77', 'client', 'Session games ({0})', '32be664aa6c0a222a968b2bcdc905e2598a5ca54', FALSE, 'PostSessionReport · ComposeFfa, ComposeGameRows1v1')
  , ('4e6e14ae3e05648c', 'client', 'Session report', '95e134257841536da4f97f7fec31a53ea3bb16bb', FALSE, 'SessionReportView · DrawHeader')
  , ('844df63fc7799788', 'client', 'Session series', '4ce68df25afe5893260f76998322877642b58529', FALSE, 'PostSessionReport · Compose2v2')
  , ('bdd76249bfe4b65a', 'client', 'Session series ({0})', 'fa37d118d2801580d4a50deda71f91b82a8190d1', FALSE, 'PostSessionReport · Compose2v2')
  , ('594d65c7ebdb366f', 'client', 'Session {0}-{1}', 'c9a1eaa86777152a8484d1f89531c86f5c9a5bf0', FALSE, 'SpectatorHud · ComposeBarLine, ComposeCompact')
  , ('99713d7607aafd3f', 'client', 'Session: {0} games, series {1}-{2}', 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', FALSE, 'PostSessionReport · Compose1v1')
  , ('a3e2201f0fd7c9b3', 'client', 'Session: {0} series', '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', FALSE, 'PostSessionReport · Compose2v2')
  , ('ed811fd03e3e7985', 'client', 'Set Active', '758d7f7281c0192f6d09ba1663e7af25cc8c0e15', FALSE, 'NativeUI, TitleLaddersUI · ApplyShopRow, BuildTierRow, PaintTierRow')
  , ('2090d7454716f5e8', 'client', 'Set RefreshValid to false', 'c8ceb506bd0b1b2298c6c72fac7245477473ad3b', FALSE, 'InfoViz · BuildRefreshFlow, BuildRefreshGate, TextFallback')
  , ('d434848c2300cbae', 'client', 'Set RefreshValid to true', '1d97ecb0b3bc6756d3846d46c2f23a482c695549', FALSE, 'InfoViz · BuildRefreshFlow, BuildRefreshGate, TextFallback')
  , ('83c8802737a53805', 'client', 'Set totals', '63e667ad90ef67cb63921ea76679a68239e6df95', FALSE, 'SessionReportModel · Build')
  , ('67bfd40e0352aa95', 'client', 'Settings', 'c7f73bb54d928922c3838bb789ee9fb8a5b1eb37', FALSE, 'NativeUI · (file scope)')
  , ('2974b8e5c24bb499', 'client', 'Severity:', '5d92c2e8b2137b358d6e0cee27dc8213007e445f', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('5c7a4710eb0d9036', 'client', 'Shade', '97389d1a0ff724b043248cd3ca83b5fea99f77af', FALSE, 'shop catalog · cosmetic name/description')
  , ('3f657265a8382ffb', 'client', 'Shades for those who want to show that they are the true genius of the battlefield', '0458a184cf383c785aa5094125d6491b775dbb63', FALSE, 'shop catalog · cosmetic name/description')
  , ('0f9e268526a4559e', 'client', 'Shard dupes (+{0})', 'bee1882ed045dfdfe80aa4032224047d37c3b4ac', FALSE, 'PlayerCardsUI · RefreshShardDupesButton')
  , ('a21326e8dc88e89f', 'client', 'Shard pack (+{0})', 'ac98582a99c43cb789cfcfe19dc8aaeab9d79203', FALSE, 'PlayerCardsUI · RefreshShardPackButton')
  , ('cf3ce1d7b60d00bb', 'client', 'Shard pack is not available on this server yet - discard one card at a time for now', '6d5df74abaf89344ec02f1a449f8bc7abcbcb23d', FALSE, 'PlayerCardsUI · FailShard')
  , ('4e230d0e3c29de56', 'client', 'Shard selected ({0})', '8129bc1251f45e6ba038dde43316f705b96fc3b9', FALSE, 'PlayerCardsUI · RefreshSelectRow')
  , ('1f696b01b48bdfb6', 'client', 'Sharded {0} cards for {1} shards', '522f35a334411529ca5a05d1ff6924872ba3885c', FALSE, 'PlayerCardsUI · FinishShard')
  , ('221c3dac8df38a27', 'client', 'Shark', '27765b6f0e0301db77fdd1d1eaf7e3a6f3af8e19', FALSE, 'shop catalog · cosmetic name/description')
  , ('6549f4da86ceafbd', 'client', 'Shark God', '2b7099c4b6ee342f2a98a3aa7c019394c8ae230e', FALSE, 'shop catalog · cosmetic name/description')
  , ('4efbb3a8dfacb8ce', 'client', 'Shark Pup', 'ca117fa71d5ed6937da80dddf4ba01dfd325b82e', FALSE, 'shop catalog · cosmetic name/description')
  , ('0f4b46097a3ceb8d', 'client', 'Sharpshooter', '70ffefd6ce4f51306d2da2ff3dc70aa385d266a7', FALSE, 'shop catalog · cosmetic name/description')
  , ('625836003d87ac6f', 'client', 'She/her', '444a011d29f4155587f4e755e604c1fa955899e9', FALSE, 'shop catalog · cosmetic name/description')
  , ('a3b1ffd8d311828a', 'client', 'She/her I', 'c43f2cf06789948f8df910c3682420089d85b80e', FALSE, 'shop catalog · cosmetic name/description')
  , ('a59aa739ca1a4793', 'client', 'She/her II', '98863e3d1d9b69088df0fe40a22a55a41fbd337f', FALSE, 'shop catalog · cosmetic name/description')
  , ('5f4e8401d410faec', 'client', 'She/her III', '7d5158e12cc61d134c3e65c93f1868f46aa5ad25', FALSE, 'shop catalog · cosmetic name/description')
  , ('14953ead9411a83f', 'client', 'She/her IV', '4b4c755b0c9cd24ad6897174e774488430f08deb', FALSE, 'shop catalog · cosmetic name/description')
  , ('c80afd61314bd31e', 'client', 'She/her V', '4a36403fcf82c3f80ece6b6932c8dc66ccff5196', FALSE, 'shop catalog · cosmetic name/description')
  , ('fff3a5250529ac58', 'client', 'Shift', '469d5b183fdc0d59e41a51e61529cdd95274ba7c', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('e20ec9323e546397', 'client', 'Shifts through the spectrum as you move. Pure show-off.', 'a35631709ba4e1f56d3e2be869b3d25dd947b31a', FALSE, 'shop catalog · cosmetic name/description')
  , ('193478fa57528850', 'client', 'Shock Shades', 'c49dfd91243662405690056d72d5545ffed41a88', FALSE, 'shop catalog · cosmetic name/description')
  , ('2a20335919fba3fa', 'client', 'Shockwave', 'f9cf560f7be04bf83ae4c79a06b27119a6f9fb24', FALSE, 'shop catalog · cosmetic name/description')
  , ('78cb639cb4f609ad', 'client', 'Shoot', 'b301c10b3d0a20c4d34f04d383741c386814b593', FALSE, 'InfoViz, NativeUI.Keybinds · ActionLabel, KeybindRowLabel')
  , ('9711b68fef7e1eb9', 'client', 'Shop', '55de88709232ec03a7618ceae9b2248419fdc862', FALSE, 'NativeUI · (file scope), BuildShopTab')
  , ('04753f943853fd1f', 'client', 'Shop & cosmetics', '13ec3760f87bc6150209123ec11bdef4b9363e74', FALSE, 'InfoLibrary · (file scope)')
  , ('14b128653a9a6e6f', 'client', 'Shop Sales', '05d289b3fe377471612bbe291e5e3f293827ed30', FALSE, 'NativeUI · TrMetric')
  , ('24a8bf4272627e03', 'client', 'Shop listing name - {0}', '3c9a7b75e6c2a22994653b2e73cc4ca9ec71f098', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('0b27001b6759297e', 'client', 'Shop listing name only - the Music tab and now-playing keep the compiled album name (max 64 chars)', 'c57c6f7f29a8f6c42980ae80a5dd755b51421483', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('144f088248385b4a', 'client', 'Shop sales', '0493923fe233433dacf26ffe427e4790aacc9f7c', FALSE, 'InfoViz · GoldBucketName')
  , ('e9d1b41f9f61182d', 'client', 'Shop still loading', '0d3453916dd932f89a188aab14acb0d36a9167a7', FALSE, 'TitleLaddersUI · ReasonText')
  , ('e26f1667a5dce5fc', 'client', 'Shortest Game', 'e8e881cb4aed8c97a7c3d4c17c6180ee470d74f7', FALSE, 'NativeUI · RecordBoardHeading')
  , ('5ded08639f2ad08c', 'client', 'Shortest game', '2c73b59dd01bb6b202b328746adf0a0a67d5d396', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('99e460a3a11278c5', 'client', 'Shots', '2179f8207fe678c2bcef7cd520ce0a989d78a467', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('ba7dca8a4cbe7f6d', 'client', 'Show Discord on leaderboard: <color=#888>link Discord first</color>', 'da679c68be32dbace626c9a143329c3cc63c44cf', FALSE, 'NativeUI · PaintShowDiscord')
  , ('bd2d56f21f25ea85', 'client', 'Show Discord on leaderboard: <color=#88FF88>ON</color>', '0b42ec74cc3cc6599f998efde1002207e0d842bd', FALSE, 'NativeUI · PaintShowDiscord')
  , ('0949f07beef44739', 'client', 'Show Discord on leaderboard: <color=#FF9966>OFF</color>', '4d9856099b56f185037bd58ccbdefdec3cf2f349', FALSE, 'NativeUI · PaintShowDiscord')
  , ('13035d18b3c5b6c2', 'client', 'Show Gold', 'b76e070645519586f2e8526c52fc8df857477430', TRUE, 'NativeUI · ApplyShopRow')
  , ('9c3246d56cb541f8', 'client', 'Show inactive players ({0}d+): <color=#88FF88>ON</color>', '41743cdddfa06ddac91ab6e3cc5c88a580296195', FALSE, 'NativeUI · PaintInactiveBoards')
  , ('728f02b70c947071', 'client', 'Show inactive players ({0}d+): <color=#FF9966>OFF</color>', '3957743fc498788244b4b68dc93177805f089704', FALSE, 'NativeUI · PaintInactiveBoards')
  , ('e6f3fc662fe78bb1', 'client', 'Show inactive players: <color=#88FF88>ON</color>', '0f368c6f7044d2e835d7bfc8f257f167af891bbf', FALSE, 'NativeUI · PaintInactiveBoards')
  , ('013da12f62c979e7', 'client', 'Show inactive players: <color=#FF9966>OFF</color>', 'f5e9b43b1d2e552d53fe7934aa904a0079f021e0', FALSE, 'NativeUI · PaintInactiveBoards')
  , ('8def21f3d72fb6f6', 'client', 'Showing {0} of {1}', '4fc8a40beb83bfd8ca70c4d2a78a7cfdf518c7de', FALSE, 'NativeUI · RebuildPickerList')
  , ('3c7e9cb47fd1e6c7', 'client', 'Showing: Elo', '575fb28d1b6dfec7b0c600da4c775614efafc076', FALSE, 'NativeUI · BuildCompareTab')
  , ('48aac4d36fe4eab8', 'client', 'Showing: {0}', 'bc2c02ad63ef5932a9bfb803d1d3de1db0bc9cd4', FALSE, 'NativeUI · RefreshCompare')
  , ('e3dd7dfe3582f5e6', 'client', 'Shows a small bottom-left credit line naming the track and artist whenever a custom song starts.', '28a0d9d1ba64751d2992ae548aa39bcdbfc975ca', FALSE, 'NativeUI · BuildSettingsTab')
  , ('021b39a46aebe9a9', 'client', 'Shows community chat in the corner while you play. Press {0} to type a reply, or {1} in game to cycle normal / pinned / muted.', 'bf5674bc86b1548870349e750ac69aa76d1f7de6', FALSE, 'NativeUI.Keybinds · KbDescInGameChat')
  , ('0e6859e372c55b36', 'client', 'Shows cosmetic trails on you and other modded players.', '5f080b6372a7db5231fcb8805edd4b8ada17f6be', FALSE, 'NativeUI · BuildSettingsTab')
  , ('14e6e248ad06ea5b', 'client', 'Shows your Discord name on the leaderboard (opt-in; link Discord on the Home tab first).', '28e456cb2fc9eb62e6a90a66a3be46b85318cf16', FALSE, 'NativeUI · BuildSettingsTab')
  , ('b802826c7bb214e1', 'client', 'Shows your current server region and your ping to it.', '415d6233a087d283a4ca8030301edf6599dfe13d', FALSE, 'NativeUI · BuildSettingsTab')
  , ('18746c7ceab495d6', 'client', 'Sid Slayer', '6ab4534ed3f287fc8a0ea7a93221e16851853fb3', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('30b0c2a836dfa86a', 'client', 'Sid''s Competitive Rounds adds a full competitive layer to ROUNDS: ranked 1v1, 2v2 and free-for-all with their own Glicko-2 ratings (plus a 1v2 beta, recorded but unrated for now), an XP and Gold economy with a cosmetic shop, weekly tournaments, live betting on matches, achievements, and Discord integration. All of it is community-built and community-run.

<color=#FFD94D><b>THE TWO GUARANTEES</b></color>

Two rules hold everywhere, and the whole mod is designed around them:

- <color=#7FE87F>A non-modded player always gets pure vanilla gameplay.</color> Whole-room changes (Grow normalization, the FFA engine features) turn themselves off unless every fighter runs a current copy of the mod - one vanilla or outdated client means vanilla rules for everyone, identically - and the poison fix follows the poisoned player, so an unmodded victim keeps vanilla poison.
- <color=#7FE87F>The only things a non-modded opponent can ever see of the mod are nametag styling and the quick-chat phrases you choose to send</color> - quick chat goes out through the game''s own chat bubble, like a typed message.

Two nuances, spelled out in <color=#7FD4FF>Vanilla stays vanilla</color>: crash-prevention guards are always on (they repair states vanilla never intended - a dead block, a frozen input - and change no rule), and between players who are ALL modded, current and Ranked-consenting, the poison and Grow fairness fixes apply even in quickplay and room codes.

<color=#FFD94D><b>HOW THIS LIBRARY WORKS</b></color>

The column on the left lists every article, grouped by category. Click a topic and it opens in this pane. Blue names like (see <color=#7FD4FF>Blocking</color>) point at other articles in the same list. <color=#8A8A93>This whole menu is F5. {0} opens in-game chat, and Esc closes the menu.</color>

<color=#FFD94D><b>WHERE TO GET HELP</b></color>

- <color=#7FD4FF>Discord</color> - the Discord button at the bottom of this menu opens the community server. Real people answer questions there, and so does the server bot - ask it things like ''how does ranked work'' or ''how do I get gold'' and it answers on its own.
- <color=#7FD4FF>Bug reports</color> - on the Settings tab, find ''Report a bug'' and press Open Report Form. You can attach your game logs (a Preview button shows exactly what gets sent), you get up to 10 reports a day, and if your Discord account is linked, responses from the team arrive as DMs.

If something looks wrong mid-match, file the report right after that session - the attached log is usually what makes a bug findable.', '84ad76a669a0da13374acac010e964ccbf6c24d2', TRUE, 'InfoLibrary · (file scope)')
  , ('9e3df6c9efe7a876', 'client', 'Side: Any', '928414d3088da4bcd44cf4682de27b4a7a01317b', FALSE, 'NativeUI · BuildOneVTwoTab, RefreshOneVTwoTab')
  , ('bca35b7294be96d0', 'client', 'Side: Duo', '2cffbd4cb1fe7e951322c8698624d869e8e79a69', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('1dea4fe7a34b66b0', 'client', 'Side: Solo', '5ea804d3a2d1d5bc3cb0429a135b43edc310bf0d', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('2ff4e59a6ac2fe45', 'client', 'Sienna', '98f69d719183344b0e6cf41bda85c41161fb7494', FALSE, 'shop catalog · cosmetic name/description')
  , ('5d86deb9c0e3f802', 'client', 'Sign Up for Tournament', '16c45d0311571f2a5866f4739eee429063e075cf', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('44a663da8c3a7fdd', 'client', 'Sign up to unlock force-start', '393bd9e94e9108ea7fcbcb67d93d3269709ea07b', FALSE, 'NativeUI · RefreshTournaments')
  , ('04e2a526f0ea6093', 'client', 'Sign-in is not ready yet - try again in a moment.', '7fd7ede55c126b5c8bafea313a5d9e58aa4d2489', FALSE, 'MailClient · ErrorDetail')
  , ('859a1106591dae82', 'client', 'Sign-in still pending - try again in a moment.', '884cce215dc902e05a82734b801f86c2bd420142', FALSE, 'ApiClient · RequestSpectateGrantCore')
  , ('1da7e3c3cd60879b', 'client', 'Signed animation fields are required', '0ffe1574e8168b104ff65cf00954500f765b8d01', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('df6a83e220cf5a4e', 'client', 'Signed placement integers are required', '4fa2b9e3357d83b574ae61a5bdb3f59809916ca2', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8705eacf4540222f', 'client', 'Signed up for tournament', '6c2863573ff2c669344d201e3e7677616346d856', FALSE, 'ApiClient · TournamentSignup')
  , ('2a2623aac4f692e4', 'client', 'Signup failed', '149dfa301d26bdabd63461fc21867bdbbe26f2d1', FALSE, 'ApiClient · TournamentSignup')
  , ('e268f01337cec8c0', 'client', 'Signups', '09c26725abca4f5f770be1e26e44b5ee79b7a7bd', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('83c65095e784da2a', 'client', 'Silence only: every other Silence produces a Refresh', 'de77b3dd6519ebefbf5f00e9abd750b224069c1f', FALSE, 'InfoViz · BuildRefreshSequences, TextFallback')
  , ('410a15ed4e513db1', 'client', 'Silent Assassin', '1fd0163116cd53e22c4f164b9e475b32f563431f', FALSE, 'ApiClient · AchievementDefs')
  , ('4d580a51b66a9839', 'client', 'Silly Drill', 'b5c2df0ee1dc21486cd644213de53f3f076f6371', FALSE, 'ApiClient · AchievementDefs')
  , ('b571a0883abbc576', 'client', 'Since first', '85aeadc8e1b43a5992e71f4c7cd53e3abeab1458', FALSE, 'RatingGraphAxis · Label')
  , ('e042a7be97677db8', 'client', 'Sinister Smile', 'aa1b3d9c7ef709cd7b74a271ae640f04b027c6fd', FALSE, 'shop catalog · cosmetic name/description')
  , ('f522e76707a4e0d9', 'client', 'Size', 'b7152342a267362add3c0d7f69f720f7a9c76c9e', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('23ba5ae4bf44caf7', 'client', 'Skip MenuControllerHandler.Update during an active match.', '237ffaf765bbff962746c4fd0c785881512d1eff', FALSE, 'NativeUI · BuildSettingsTab')
  , ('6b6288ba513dd704', 'client', 'Skipped: server settings', '9196dcd560c15c5f63ba49c02e9124ba9645c55d', FALSE, 'NativeUI.Settings · BuildSettingsChrome')
  , ('e23866b89558a941', 'client', 'Sky', 'b3d97fd6dece388a968e367f3ac4b9e64d739f52', FALSE, 'shop catalog · cosmetic name/description')
  , ('6bf922a2af005d17', 'client', 'Sky Lord', 'e10d10b71a0ee15a02c709826d59beba9afa44c8', FALSE, 'shop catalog · cosmetic name/description')
  , ('5b1fa8823faaa4dd', 'client', 'Slate', '26d7b218c9b5641b37dfddc13b955184f3ce868f', FALSE, 'shop catalog · cosmetic name/description')
  , ('567890efd6eb4e17', 'client', 'Sleek black body color.', 'b0476d817e62b78a6d6b13910299b1a6c90d3d83', FALSE, 'shop catalog · cosmetic name/description')
  , ('7443c379c3eebac2', 'client', 'Slow connection — still trying to join the match...', '97437fc4808f9960b11e40fee6fd73da6ee76029', FALSE, 'Plugin · Update')
  , ('224e05bb1d48afda', 'client', 'Slowing down - the server asked for a {0} s pause', 'b7c63b7e968511515555b759c3790baa9a887cb3', FALSE, 'PlayerCardsUI · DiscardNext')
  , ('811bf05184f39e45', 'client', 'SmAlLcApS', 'a8e56ef9b0223468ffe7a2e5ba21d538d23afc66', FALSE, 'shop catalog · cosmetic name/description')
  , ('9237062066f5d776', 'client', 'Smaller Name', 'bb79f3faedd4b8feda0906367e3938079bb3cd8c', FALSE, 'shop catalog · cosmetic name/description')
  , ('d1b0bffe890cc265', 'client', 'Smart Specs', '2d0910f5c35e9d87fffb89b1c2ab084e35940195', FALSE, 'shop catalog · cosmetic name/description')
  , ('21a19e853e62a77b', 'client', 'Smoking', '7b3d0b443ce4a8405de90ed439b33999c90d489e', FALSE, 'shop catalog · cosmetic name/description')
  , ('c1f9ff3a68f5fbff', 'client', 'Snapper', '64ba77cd320c5e5ccd226b5a67c57463b0d14bb3', FALSE, 'shop catalog · cosmetic name/description')
  , ('57b8789f20886356', 'client', 'Sneaky', '809395b6dcc3b0c3b1b522396665175a3d805368', FALSE, 'shop catalog · cosmetic name/description')
  , ('be93e1ed6ec90fec', 'client', 'Sniper', '2081d06ecb8f68cbf79e9de820f81f7f82fa4625', FALSE, 'shop catalog · cosmetic name/description')
  , ('91d61c894d41c995', 'client', 'Sniper Medal', 'a3ad936a7ceda44469920ce62fe5947bde0aa040', FALSE, 'shop catalog · cosmetic name/description')
  , ('d14c7abccdd8c306', 'client', 'So close!', '6af055dbcaca305f2ac257c36800215d90053a17', FALSE, 'QuickChat · Phrases')
  , ('5def38b6c29f4d9c', 'client', 'Soda Helm', 'f9d59a6ea8c756838f928f0d95c9d34e4d99db37', FALSE, 'shop catalog · cosmetic name/description')
  , ('fcdaa994cb09a325', 'client', 'Soft Slate', 'ce8d0da33206ab07f9dad187d28ae162ccc22b29', FALSE, 'shop catalog · cosmetic name/description')
  , ('64444ce16020118d', 'client', 'Soft eyes', '4bab4ddcd9dcef26758c2e5ed4e558a897ba7d1d', FALSE, 'shop catalog · cosmetic name/description')
  , ('6df0149175e82e19', 'client', 'Soft pastel lavender — minimum contrast.', '2394bba21d20d3da5d703014c5a214f15bcef2be', FALSE, 'shop catalog · cosmetic name/description')
  , ('3e776304a375d625', 'client', 'Soft pastel violet body color.', '1b7253a3591f76e461aebe6335506a201a17601e', FALSE, 'shop catalog · cosmetic name/description')
  , ('9d9a02388f682516', 'client', 'Soft pink body color.', 'f7bce6256e4c4cbfffd0c61e2708265490027f17', FALSE, 'shop catalog · cosmetic name/description')
  , ('97ed03fa320e46f3', 'client', 'Soft pink shimmer. Deceptively innocent.', '8e9ab1eb27d0a3fe5bff1c54133eb397a100592a', FALSE, 'shop catalog · cosmetic name/description')
  , ('646589db10bb5f2c', 'client', 'Soft shadow beams cast by map lighting. Off = no shadows (lighting stays on) for extra FPS.', '908c1137c947ee99598d692d1d247169b67b174c', FALSE, 'NativeUI · BuildSettingsTab')
  , ('34c4b0f8d3827925', 'client', 'Sold', 'e6560d9c298e72db56c00c64c9c0c9c6a63ca288', FALSE, 'NativeUI · BuildCompareShopSalesPanel')
  , ('5fc280a4ee756126', 'client', 'Sold out', '02ff65909856c0d4c47e5496f4e5df4964c3982f', FALSE, 'NativeUI, ServerTextRules · ApplyShopRow, TrRefusalDetail')
  , ('d887be4b3507d8a4', 'client', 'Sold out — raise the stock cap first', '6b9a95438c673426f776ffc4b0a41b30ce5306f2', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('06cf09fad072b83f', 'client', 'Solo', '9fc93acaa44f3f647fae2ed40110f88b9561a474', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('dca34071afb963ee', 'client', 'Solo -', '52381ad42460aca3d0250e9c8261b125d52754dd', FALSE, 'NativeUI, PostSessionReport · OvtLine, OvtRecordHead')
  , ('658d71d742121ed2', 'client', 'Solo Leaderboard', '3d40c20821471e017a6f118ca7911fbcea797946', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('3ee2cebf9685275f', 'client', 'Solo extra pick', '08dc46bbc8f4217a764586274974ce517a4842ff', FALSE, 'RoomRules · Summary')
  , ('058dfacd797a5c2d', 'client', 'Solo extra pick (host): OFF', 'f1cd44e286b70679cf49f8d1a6c1e892d290fd0d', FALSE, 'NativeUI · BuildOneVTwoTab, RefreshOneVTwoTab')
  , ('b80541264eef3b60', 'client', 'Solo extra pick (host): ON', 'c90b3620b9c40f5f3056d7ffcb0e1f311d7891f4', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('fe6d0b0c1c99dfc1', 'client', 'Solo {0}W/{1}L', 'ad4c0e8211de1e439cf86a7e625f06c86317b74c', FALSE, 'NativeUI, PostSessionReport · OvtLine, OvtRecordHead')
  , ('e9e3c0515899c568', 'client', 'Sorry!', '22959ede33b65d25ed4762705597fb8b954d3a6b', FALSE, 'QuickChat · Phrases')
  , ('cc9d2a3ae8673ac4', 'client', 'Sort:', '8b335a234e4193e8787a2bbc9ebdddb99c39f38c', FALSE, 'NativeUI, PlayerCardsUI · BuildAchievementsTab, RefreshBinder')
  , ('a25f8da88b10e05e', 'client', 'Sound', 'b4e3efeba10e84f7148da9f7efe85e07057d7c7a', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('321d3d0d79d4c6db', 'client', 'Sovereign', '65cfa78989387ca19f18d1d54af0d45dfb8fd9ee', FALSE, 'shop catalog · cosmetic name/description')
  , ('093cb8d328f0f8c8', 'client', 'Soviet', '42724976abf218f52fcf92c452432ec282de21a7', FALSE, 'shop catalog · cosmetic name/description')
  , ('b1d80f18f05d961c', 'client', 'Space', '6d8c9b124d521027647b4f270cb2872798f9264e', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('b74e9797538db825', 'client', 'Spam', 'd8628a5259c97b78ad43f83b1f91e47936e7e7d1', FALSE, 'MailUI · DrawReportModal')
  , ('4de9de6e1f656ebe', 'client', 'Sparks', '45bfc012fbf82490776101b9c6b63887c8a0fb1d', FALSE, 'shop catalog · cosmetic name/description')
  , ('1ab9372118365ce8', 'client', 'Speacial eyes for the feline enthused', '61ad233cad804ff442749806e155e661d6cb1fe8', FALSE, 'shop catalog · cosmetic name/description')
  , ('52c14238ca60b006', 'client', 'Spectate is settling - try again in a moment.', '7e58aff61247faa611d91c26c14bb8b745cad508', FALSE, 'ApiClient · RequestSpectateGrantCore')
  , ('5d139a2aa3e9277f', 'client', 'Spectating', '0c6b6d4f70cfb4212b1bf230c43ac7f9db37a841', FALSE, 'InfoLibrary · (file scope)')
  , ('03c5a0d8e90d79de', 'client', 'Spectator session ended.', 'f06d063fd1257dcd929e9ecb82d3a0397267e285', FALSE, 'SpectatorSync · OnHeartbeatRejected')
  , ('51820a6184b82f3f', 'client', 'Spectators ({0})', 'f1c9ae81fc7e2bbd19ab01bae113f28fd40d5456', FALSE, 'CompetitiveUI · DrawSpectatorRoster')
  , ('a9d50d7f27f69d23', 'client', 'Spectators ({0}): {1}', 'cf2b0afff61ccbb6fe42bdc5683912fcf1a7c736', FALSE, 'CompetitiveUI · DrawSpectatorRoster')
  , ('94f1cace756e2725', 'client', 'Specter', 'e0ad3ab875f57eac75ebd47534939215a9b96daa', FALSE, 'shop catalog · cosmetic name/description')
  , ('afd79d704d7828e2', 'client', 'Speedrunner', '94009bf32d651404d87e3b7db69f1d21510beeda', FALSE, 'shop catalog · cosmetic name/description')
  , ('12a6edde67952b4e', 'client', 'Spilled Icecream', 'f2fa96206ed75c0ed163bf95a77c628c022205f2', FALSE, 'shop catalog · cosmetic name/description')
  , ('64f50d41089a0db6', 'client', 'Spooky Head-Bouncers', 'a6a7b70436b1cb9914649ca0f29a787099ee1c15', FALSE, 'shop catalog · cosmetic name/description')
  , ('892f1b97985931c1', 'client', 'Spray and Pray', 'c5db1144d4106184ee6562dda8f16d44f9d21068', FALSE, 'ApiClient · AchievementDefs')
  , ('74892e8d7d529b3c', 'client', 'Spread', '2bde101117a83786a9fe359d813c1badf4a6b2ee', FALSE, 'TabStatsOverlay · EnsureLocaleStrings')
  , ('6f6c3c254ccd07de', 'client', 'Stacked Deck', '72a0000376276a7f054fdf34cbbc166d639c06e8', FALSE, 'ApiClient · AchievementDefs')
  , ('3ec608bd07df3fb0', 'client', 'Stan Slayer', 'ae97475ace60cadda4ce2988ba3066b956b847c9', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('f0f169d5182d3441', 'client', 'Star Earmuffs', '1c0cb5239f106c2576fc15b5249d073c7cf406e0', FALSE, 'shop catalog · cosmetic name/description')
  , ('67639960c926c58e', 'client', 'Star Spin', 'f2698c4901757c1e713246a5a58dd359698f9f54', FALSE, 'shop catalog · cosmetic name/description')
  , ('f4d726ae9f55a9fe', 'client', 'Stardust', '53cb1f455d882f798601207af0839bff46ad3b46', FALSE, 'shop catalog · cosmetic name/description')
  , ('608561ba53ff573f', 'client', 'Starry Eyes', '6134bd38cec65de46eba3419acc1c714ffe1cd20', FALSE, 'shop catalog · cosmetic name/description')
  , ('f3d059d8adc3972f', 'client', 'Start (need {0}+)', 'af0151e8d21f97ebebc04a4921272e598ec5146e', FALSE, 'NativeUI · RefreshFfaTab')
  , ('a9e4235a8b94ba63', 'client', 'Start Game', '365f992a0a10615ba2ae06d707bb66c9e6c66bbe', FALSE, 'NativeUI · BuildFfaTab, BuildOneVTwoTab, BuildTeamTab')
  , ('51a6d0e98b96103e', 'client', 'Start Game ({0}/{1})', '95434373b1524d272dcd9345ec874d2a8b03b516', FALSE, 'NativeUI · RefreshFfaTab')
  , ('3bf441e561ef91aa', 'client', 'Start Here', '477344d232738a1940fb13fed234ad833fbb080f', FALSE, 'InfoLibrary · (file scope)')
  , ('5420efacc2031eb3', 'client', 'Start unlocks in {0}s (settings changed)', 'e225fc35916c02082cbc4b761f753aef8048e0fa', FALSE, 'NativeUI · RefreshFfaTab')
  , ('e8f48481d4bd7c9c', 'client', 'Starts: <color=#FFDE88>{0}</color>', 'e3c95802a4529c0f536dbb1eaf80bab813a2d5c0', FALSE, 'NativeUI · RefreshTournaments')
  , ('e05179d19043d955', 'client', 'Stats and profiles need the secure connection. Retrying every 5 minutes.', '0e3a87794456724182ce08e73b81d436c55520bd', FALSE, 'ApiClient · NoteReadGateFallback')
  , ('3ce97f27667af200', 'client', 'Stats still loading - try again in a moment.', '638ae8141a1065604158abda467ced3f31d00246', FALSE, 'NativeUI · OnLfpButton')
  , ('854774247858c849', 'client', 'Status: <color=#88FF88>Allowed</color> - match data and linking are active.', '084282a69463a804d2336837e4f92bd0b0d0160c', FALSE, 'NativeUI · RefreshSettings')
  , ('3756e6cfebef3865', 'client', 'Status: <color=#DDDD66>Unset</color> - the consent prompt will appear on next launch.', '1701a52158cb5b8eee96db12e0453dc68ee4b165', TRUE, 'NativeUI · RefreshSettings')
  , ('ac2ac9790f0283fc', 'client', 'Status: <color=#FF9966>Denied</color> - mod runs offline. No data leaves your machine.', '593dddce7c4ef2c47cc34038dd0fc0cc18c8e576', TRUE, 'NativeUI · RefreshSettings')
  , ('22e5b09d94b5995a', 'client', 'Steady Shot', '10cee099019ae4f61bb952c88373be6029d376b7', FALSE, 'shop catalog · cosmetic name/description')
  , ('e8e4896cddd754fe', 'client', 'Steam ID copied to clipboard', '18f1faa5e7e0cbe5ab8a7a7fd26904d28973e2fd', FALSE, 'NativeUI · BuildLeaderboardTab')
  , ('895fec08427896c1', 'client', 'Steam ID not ready yet — try again in a few seconds', 'b9569b433797c5bc74d5184f5ead8ef83695cec6', FALSE, 'NativeUI · BuildTeamTab')
  , ('fc4a094646e0cee6', 'client', 'Steam identity is not available yet', 'c5204c5f55978ef13589b2a101b390b13c7e8349', FALSE, 'SessionReportView · ErrorMessage')
  , ('9a7167c3ce3357d2', 'client', 'Steam identity not ready yet', '3973705737987d5125a7f5410bb2022494c7d969', FALSE, 'PlayerCardsUI · Refresh')
  , ('392549a2685eedaa', 'client', 'Steam session expired — try again in a moment.', '10e93d512a2f48e64ae393159708b38de965eb89', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('dc79fdee9d137363', 'client', 'Steam session not accepted — queue polling stopped; the server will clear your seat shortly. Try again in a moment.', '7056fc9bb25b0ccd48b0b3fc496d5ac15cbf52d8', FALSE, 'ApiClient · UpdateQueuePoll')
  , ('b5e48c8390617067', 'client', 'Steam sign-in is required to view session reports', '1432201b40fabc68678895cefb04563659d50408', FALSE, 'SessionReportView · ErrorMessage')
  , ('16f08519634a53a5', 'client', 'Steam sign-in still pending - try again in a moment.', '593d57b50f41ff087c272df7180b1ab47974acb9', FALSE, 'ApiClient · GenerateLinkCode')
  , ('ac0a136fc03bd3ed', 'client', 'Steel Gradient', '5052759c37603ebc59fa10a45f0d8819b759e480', FALSE, 'shop catalog · cosmetic name/description')
  , ('f84baed9e93becd2', 'client', 'Still checking your Discord link - try again in a moment.', 'f1fc77946fe7647f2433f6359d0a909d373507fb', FALSE, 'MailUI · SetMailRelay')
  , ('e811d4f224ef1b15', 'client', 'Still finishing your last spectate request - try again in a moment.', '8bb0ec7b38a83de237678e3d6d2b214f6109bf03', FALSE, 'ApiClient · RequestSpectateGrantCore')
  , ('b210c9c9bbda0065', 'client', 'Still joining - one moment...', 'd71c4ede722c792578ac6c7cab00113b2e7fabae', FALSE, 'ApiClient · EnrollGateBegin')
  , ('3fa033f6c6325cd1', 'client', 'Still leaving the 1v2 queue — try again in a moment.', 'b1dbb6b7f6928d913e2e5e7ac7f8eab739b0a73c', FALSE, 'ApiClient · OvtJoinQueue')
  , ('622f53aec8cd587f', 'client', 'Still leaving the 2v2 queue — try again in a moment.', 'a11144e953fe745349754c33552d7fe771913b62', FALSE, 'ApiClient · JoinTeamQueue')
  , ('b9595d19d276b71f', 'client', 'Still leaving the FFA queue — try again in a moment.', '8c7b742a4127cf1254e34bdebc3322d3a7369c50', FALSE, 'ApiClient · FfaJoinQueue')
  , ('38aa9603d3c8419b', 'client', 'Still leaving the queue — try again in a moment.', '6b9e7b491f7c6de0bf92e73dc268f45f08938d85', FALSE, 'ApiClient · JoinQueue')
  , ('c15ad1cfef2807c3', 'client', 'Still leaving — try again in a moment.', 'a4f0773c75560f9643008820d0e70714619dcd1a', FALSE, 'ApiClient · ActionPreflight, FfaLobbyActionPreflight')
  , ('21614e82182fa2bb', 'client', 'Still opening - checking again shortly', '7b92cc6ad81ed92d66e7e5435f6df6427e4d90d5', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('88864a6ea826dcf4', 'client', 'Still waiting for the server to record your pack - checking again shortly', '84604f1de36849cb21da64679b9eed0636efded8', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('c181f97737843bb1', 'client', 'Stitched Grin', '79144fb22b8fe57dc5e4025fa2451b9c9fbe973a', FALSE, 'shop catalog · cosmetic name/description')
  , ('01a2f5687a851390', 'client', 'Stock', 'bcecf4562f1709b1448aff7c6b49edb6acecdb12', FALSE, 'NativeUI · GetOrCreateArtistRow')
  , ('6af9389a92c0a962', 'client', 'Stop', '9e253470c876ee6d5c720eb777aeb82d4c26e28f', FALSE, 'NativeUI · ApplyShopRow, RefreshShopMusicExpansion')
  , ('bcc7673bc97a4ef3', 'client', 'Stop Avoiding in Ranked', '24338c588a7c02e9f6f4cbf38c0da960808fc6e9', TRUE, 'NativeUI · RefreshLeaderboard')
  , ('5cdd19132cfef1aa', 'client', 'Stop selecting', '44d00e489861ee4a730b903699d7547320327bf5', FALSE, 'PlayerCardsUI · RefreshSelectRow')
  , ('38fee15438b6075b', 'client', 'Stop spectating first (Esc).', '1927c7d20bf152a7d31fb746172c9c770ee4c761', FALSE, 'ApiClient · SpectatorBlocksQueue')
  , ('2a3b6394364daf02', 'client', 'Stop spectating?', '629d05ffa81ba4280ad433fd1298f4ee66e9a811', FALSE, 'SpectatorHud · DrawLeaveMenu')
  , ('4c3422795023e95d', 'client', 'Stopped searching', 'db825a8ff1b5076df3201c8038e1efe1606429ba', FALSE, 'ApiClient · UpdateQueuePoll')
  , ('8c303afe63579dd8', 'client', 'Storm Halo', 'e6dc9396aa17a023a695be860dd2f06ed4399346', FALSE, 'shop catalog · cosmetic name/description')
  , ('818197f013076838', 'client', 'Straw Hat', '5fd30f1f438be65efde25480a1cf90ae141c4517', FALSE, 'shop catalog · cosmetic name/description')
  , ('6cecf8a37e3c9888', 'client', 'Stray', '32637968b77430630fc0a7f8a16dc131cd7421c0', FALSE, 'shop catalog · cosmetic name/description')
  , ('7d6b3939f985247d', 'client', 'Strike', 'f9ae58aa354c851627202a2bbae82b33dd0da9c6', FALSE, 'shop catalog · cosmetic name/description')
  , ('f0ca80932eaf824e', 'client', 'Strike through your name. Stackable with other name styles.', '78d736bb8b31ffc0d1147e4a8bb2bbb2bf209874', FALSE, 'shop catalog · cosmetic name/description')
  , ('d65e985d67ed0fe9', 'client', 'Stun null-guard', 'e41871fcab992523ffd460e45c652811a5aa37cb', FALSE, 'NativeUI · PerfRowLabel')
  , ('d1444d8ccb532eed', 'client', 'StunPlayer null-guard — stops NRE spam when a player is destroyed mid-stun.', '702282ee3b8e83ab98bab528edd90b1983df3f06', FALSE, 'NativeUI · BuildSettingsTab')
  , ('dae269dd1ca70a7d', 'client', 'Subject', '8d183dbdcea3b29906090bd83fa6fa37923cc8ec', FALSE, 'MailUI · BuildComposerView')
  , ('476093e331464f11', 'client', 'Submit', '2dacf65959849884a011f36f76a04eebea94c5ea', FALSE, 'CompetitiveUI · DrawAdminPrompt, DrawArtistInput')
  , ('c76ede26fcd816e4', 'client', 'Submit Report', '1ca00033fee3d4e5ee3de55b2d380368d9310d48', FALSE, 'CompetitiveUI · DrawBugReportModal')
  , ('9b898dc5487d84cd', 'client', 'Submitting...', '46a1a6919d196b4d95a74a37cc19f2ed4c66d0eb', FALSE, 'CompetitiveUI · DrawBugReportModal, SubmitBugReportNow')
  , ('1d212540835c92ae', 'client', 'Sunburst Halo', 'dd5499d7f0a2d38242360148c069aa29f121ccbb', FALSE, 'shop catalog · cosmetic name/description')
  , ('60bbbc527e3744da', 'client', 'Sunset', '181bcd5760fd32163554c899301a30b2cd381cf4', FALSE, 'shop catalog · cosmetic name/description')
  , ('8fc96ffa03aaafbe', 'client', 'Sunset Gradient', 'e6e56698abc25872406e861b0aa5e10015632ae8', FALSE, 'shop catalog · cosmetic name/description')
  , ('2a66b38459b511b6', 'client', 'Supernova', '48b1abf61ecba3308f0a0d95e77ba1aef320616f', FALSE, 'shop catalog · cosmetic name/description')
  , ('2ec6ae0085e50ff5', 'client', 'Sure? +{0} shards', 'a6ae4cf160b59964d7f96bd1b1b98b45264e025b', FALSE, 'PlayerCardsUI · RefreshSelectRow, RefreshShardDupesButton, RefreshShardPackButton')
  , ('a4a14938fad11b8d', 'client', 'Sure? Discard', 'd9d19f62f220a31379f26c6288b664e6dce4c175', FALSE, 'PlayerCardsUI · FillTile')
  , ('01f6612a88fb7f2e', 'client', 'Sure? Discard dupes', 'a6d37fcb48054d6723c843ed718114d0cfcf1f77', FALSE, 'PlayerCardsUI · FillTile')
  , ('5b789e3f0dcae3da', 'client', 'Sustained Power', '24e70c2af4a5fd7a4c77d10b257d272c6d49b649', FALSE, 'ApiClient · AchievementDefs')
  , ('7fbedacc6efea800', 'client', 'Swallow RayHitBulletSound NREs from destroyed parents.', '13b3faceb8360fa55fb94098c6b1e5b6b8d19f27', FALSE, 'NativeUI · BuildSettingsTab')
  , ('c7a5a26638393134', 'client', 'Swallow ScreenEdgeBounce NREs from destroyed bullets.', '868d0b7d0ffa614abcff7ba14ad2d6bde86a1b2c', FALSE, 'NativeUI · BuildSettingsTab')
  , ('cdf63820eb07a5f4', 'client', 'Swaps your avatar in the seats that show one.', '137b9c1336dde6a685c8575196a4d87f9e3479e2', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('29c05e2d6b899685', 'client', 'Sway and wave to the crowd. Play it between rounds with the {0} wheel.', '4afe4a47409ae12a122c976e68d6422906c46c82', FALSE, 'shop catalog · cosmetic name/description')
  , ('6ebdd285f3b71ef8', 'client', 'Sweat is just XP in liquid form.', 'f53f0af5f87f3ba660422807a1435727faeed72b', FALSE, 'shop catalog · cosmetic name/description')
  , ('62945646ff725873', 'client', 'Sweaty', '0c95f4a83a19eb2e8965d24c44c42df5b61d5388', FALSE, 'shop catalog · cosmetic name/description')
  , ('6028e9eac2094a5a', 'client', 'Sweden', '72ddd2b619af6d6a73febf80f7fcad22495498cd', FALSE, 'shop catalog · cosmetic name/description')
  , ('6417f5d13dc1cd9b', 'client', 'Sweeps: <color=#00FF00>5-0 x{0}</color>  <color=#FF6666>0-5 x{1}</color>', 'c992e487ff19ddc4ae5cc59132442aaf46dd9b5a', FALSE, 'NativeUI · RefreshMyStats, RefreshSession')
  , ('9044d2e1a09c8482', 'client', 'Switched back to your modded avatar.', '7aefc82c5f16a5cfcd9bce5989c9007b04823262', FALSE, 'AvatarDefaults · SwitchedMessage')
  , ('12825649cfa24cab', 'client', 'Switched to your vanilla avatar for this room.', '8cfe0b9aaea854c6f3dc018661d1594db6aaadc4', FALSE, 'AvatarDefaults · SwitchedMessage')
  , ('cf5370ebc8e8c2b7', 'client', 'Sync (weekly)', 'cf00d420c15dfbf2ff34f61c4044ea9b875ef1ce', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('b618aff81c272358', 'client', 'Sync Champion', '7356f9d83ad3ebef5aa96ab01b52e61f12c1cbe6', FALSE, 'ApiClient · AchievementDefs')
  , ('fc5ddef17a60d95a', 'client', 'Sync Finalist', '38ecddf69e8409bc60fb8e1f9bcbc3d7ef5c603b', FALSE, 'ApiClient · AchievementDefs')
  , ('fa5b381ff4194b45', 'client', 'Sync Tournament - {0}', '7ef9cc8ad90119a427ac234abe4c58fc097cb0eb', FALSE, 'NativeUI · TrTournamentBanner')
  , ('9d6041fbc550ee63', 'client', 'Synchronizing - viewing begins next battle', '2eb822ed968828545908f7861d809bcd44850127', FALSE, 'SpectatorHud · ConnectStatusLine')
  , ('e9fb8ffbaab655f7', 'client', 'Syncing...', 'e5c7727a106e2f8e5e183ec9a8b5c48855e2b834', FALSE, 'SpectatorHud · DrawLiveBar')
  , ('92dd612a8d621c97', 'client', 'System notices cannot be reported.', 'ecee915ad4e312b5d3bc2f39a0db0f8598539fd5', FALSE, 'MailClient · ErrorDetail')
  , ('71b012c4704288df', 'client', 'TAB', '38d4aa698a701e2288a153e115d12aab45de5940', FALSE, 'InfoViz · BuildKeyboard')
  , ('f851a9aad9ea6141', 'client', 'TABLE OF DAMAGE INTERACTIONS', '704ef77f6c313746fb6ba54dd99fce50481d19b1', FALSE, 'InfoViz · BuildDamageMatrix, TextFallback')
  , ('5a68eb00d7fdb44d', 'client', 'TBD', 'a6303a49483c1564f02d13e3fae9616cb4576fed', FALSE, 'NativeUI · CreateBracketCell, RefreshTournaments')
  , ('907371d0551605f7', 'client', 'THE 0.3 SECOND WINDOW', '24808976280582a15b1721fc0d411d73a086f625', FALSE, 'InfoViz · BuildBlockWindow')
  , ('1d7fa00018397e5b', 'client', 'THE DUO', '5e8adebb89e8a50a78020624ead3f89d2f40de6f', FALSE, 'InfoViz · BuildOvtFormat')
  , ('4ef49a8a6d86b7f0', 'client', 'THE ROAD TO LEVEL 100', 'ae857850d9f6a01df5c6318de07ba3b3d87eedbc', FALSE, 'InfoViz · BuildXpCurve')
  , ('a274aad4509f84e6', 'client', 'THE SOLO', 'ff0a085bff181fc81a692033955e81c60b5eed54', FALSE, 'InfoViz · BuildOvtFormat')
  , ('1f4c9cf9f8c8249b', 'client', 'TOURNAMENT', '48860f9260fe5605b52ff9b5c16708fe227a20c3', FALSE, 'NativeUI · ApplyHeaderRow')
  , ('14e9b2c662ae2679', 'client', 'TOURNAMENT Async', '868133739bac75aaea165862c73f98f4ee79bc0e', FALSE, 'NativeUI · ApplyHeaderRow')
  , ('7c6f17d77aaa5736', 'client', 'TOURNAMENT MATCH', '9a245a6d66bf0822e26c0f814748b2c701e014fb', FALSE, 'CompetitiveUI · DrawMatchStatus')
  , ('aea09b3828dbdedf', 'client', 'TOURNAMENT MATCH vs {0} - connecting automatically, hold tight...{1}', '000192d1a8bc97d6ee60930274a5576366c228af', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('6449179f9d1f38ce', 'client', 'TOURNAMENT MATCH vs {0} IS WAITING - LEAVE THIS GAME NOW!{1}', '09e233dea356e6cd5e938852f8755d561df79d21', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('22bbf3bbfc5851b3', 'client', 'TOURNAMENT STARTING - matches are being created, hold tight...', '23f7bcf444a010b5e29565495b64b0e169aab5bc', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('1ae13cdc903c028b', 'client', 'TOURNAMENT STARTS IN {0} - stay in ROUNDS at the main menu!', 'c32e6ef305f7305a05b6f89f622a0d6797911a18', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('70e88d6e5e69e65a', 'client', 'TOURNAMENT Sync', 'd17b8784d9aec2286a112ea9e192969a23c83da1', FALSE, 'NativeUI · ApplyHeaderRow')
  , ('70590b7f870bc73a', 'client', 'TOURNAMENT {0}', '0ce5eeac5aa1ad335691c6ae595769a5465dc3ea', FALSE, 'NativeUI · ApplyHeaderRow')
  , ('0dee4cb5bc20506a', 'client', 'TP R{0}', '06d610cd7658e14669885c751d786622d0cd2b22', FALSE, 'NativeUI · TrBracketProgress')
  , ('40dd10e84698139c', 'client', 'Tab', 'fe06eb6459c87f0e497ce1805f076f104bfecf78', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('fd515c2d6e45a9a3', 'client', 'Tactical', '1d735260ad0298aca89055fcd670f411760a09cd', FALSE, 'shop catalog · cosmetic name/description')
  , ('4de0cd53889e1dbf', 'client', 'Tag Team Sweep', '4e4cd33a2506596163f467a032d1305efd4c07bd', FALSE, 'ApiClient · AchievementDefs')
  , ('918ff09cc73c9768', 'client', 'Take 2nd place in a live (sync) tournament', 'c66d3912b0770404d0b1b5a491d20937bab1bf16', FALSE, 'ApiClient · AchievementDefs')
  , ('42b363065f7bc00c', 'client', 'Take 2nd place in an async tournament', 'e923dca9795b936117ea5017d3a38acd54af0566', FALSE, 'ApiClient · AchievementDefs')
  , ('1d473e51fc884c2a', 'client', 'Taken', 'c66c12b98882a2c74600f15115c65f693c8d5f34', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('cab4937719a22718', 'client', 'Tan', '133552ebfbcce8310f8920695422699d5256bac9', FALSE, 'shop catalog · cosmetic name/description')
  , ('247786047e006128', 'client', 'Tank', '0ba4d1aee6f233efc1f3b78141b4af7d08b86c3c', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb7725ecde11d27c', 'client', 'Tapped while typing, switches which language channel your message goes to. Needs a key that types nothing.', '8420746a889fdde5bf24c5a0e4101e2e4432d184', FALSE, 'NativeUI.Keybinds · KeybindRowHelp')
  , ('abd355e13a15e46d', 'client', 'Target Bounce main', 'f9fb8665cb51f149f63f06a976a3324713219468', FALSE, 'shop catalog · cosmetic name/description')
  , ('1e1958b11798ea12', 'client', 'Target Bouncer', '34aa898918ac557dd5df10c7498a24b860438cb6', FALSE, 'shop catalog · cosmetic name/description')
  , ('2c906a75c80db5cc', 'client', 'Target Steam ID', 'dc6bac792e0b1c0368b9569dd6e78dc6aedec1c8', FALSE, 'NativeUI · StartAdminBanFlow')
  , ('50ac155d36ece430', 'client', 'Tattered Cape', '5f6aa78e382c01b370e8b343a9c1b5a2b5fa6705', FALSE, 'shop catalog · cosmetic name/description')
  , ('3b01b61b340a5223', 'client', 'Tattered crimson bat wings straight from the pit. Soul sold separately.', '619a16e83766383c2d21a829f80bd5d01c671c25', FALSE, 'shop catalog · cosmetic name/description')
  , ('eb382d1678858a9c', 'client', 'Teal', 'df0ad373b7ff60d6a8987458fb00c1e4832ef605', FALSE, 'shop catalog · cosmetic name/description')
  , ('d1b8be2788734885', 'client', 'Team & body colors', '4f964480316f94e0572347d15d1effbcf33e228a', FALSE, 'InfoLibrary · (file scope)')
  , ('02f9fdc3b0163eb6', 'client', 'Team 1', '59e04589be76b7f5cd8daa060c3b716223b0255d', FALSE, 'NativeUI · RenderHostLobbySection, RenderTeamQueueSection')
  , ('a39001b83c5b81c1', 'client', 'Team 1: orange', '1f9a8b41a664901e7686ee4caca99a56d3beee86', FALSE, 'InfoViz · BuildTeamFormat')
  , ('a9959f9679e83eae', 'client', 'Team 2', '60aff4035bca07e449351eb0f02141feadf9dcd5', FALSE, 'NativeUI · RenderHostLobbySection, RenderTeamQueueSection')
  , ('dc38ca0bb8c08c98', 'client', 'Team 2: blue', '7bb41e1db3a4c09552453ba3496fed9fc7b13845', FALSE, 'InfoViz · BuildTeamFormat')
  , ('3bfd7c6902ea31e2', 'client', 'Team {0}', '005d371b5e9cc256798c59db0a9b65adb2f7c2a6', FALSE, 'NativeUI, ServerTextRules · ApplyTeamBetRow, BetOnName, RefreshTeamTab')
  , ('7681ff2674d18619', 'client', 'Team: <color=#88AAFF>2</color>', 'a66ab0a55a17f97cf4a7b747ce97435384eebac3', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('7b2d866aafe24425', 'client', 'Team: <color=#FFB347>1</color>', 'a6bbf1bfddd51781e6a302a6358026ff922a3651', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('9985a0d2f6e36dc7', 'client', 'Team: Any', 'f29811bf00e4e54584f121a0460cacd3fd862599', FALSE, 'NativeUI · BuildTeamTab, RenderHostLobbySection')
  , ('476d5eee623bc2a9', 'client', 'Teams will rebalance next match!', '60598b80b4712d9934525f8ac9e220b8cf27dbcc', FALSE, 'ApiClient · ReportTeamMatch')
  , ('3fa8eb32ef19e443', 'client', 'Tell the moderators why. The message is attached to the report as it was sent.', 'd7e95c1c1c4e8a3c0f7ee0a7fd17f5e67b15fd49', FALSE, 'MailUI · DrawReportModal')
  , ('b234d0122bbaa63f', 'client', 'Thanks for testing the mod during beta. Free, removed after beta ends.', '117e0234bc721029ca23bc4468eaaf69939a267a', FALSE, 'shop catalog · cosmetic name/description')
  , ('20e937b53e50ddff', 'client', 'Thanks!', '1da20795f84bb9c5e16697aea34f14720e38fc37', FALSE, 'QuickChat · Phrases')
  , ('2bd8936660a6d26d', 'client', 'That FFA lobby is private — enter its password.', 'd11656a4df6895daa62e6288538c2b8b353539da', FALSE, 'ApiClient · FfaEnrollResult')
  , ('dfab60f0e9799dbb', 'client', 'That amounts to all my current understanding of Conditional damage. My model of what is going on behind the scenes is entirely a construction (I have not seen the source code), but it correctly predicts all currently tested behaviour, and I have been thorough. Still, there are limits: I do not know whether the RefreshValid bool is held by the attacker or the target - that is, whether every player has a cap on the Refreshes they can trigger for themselves, or every target has a cap on the Refreshes they can trigger for others. In a 1v1 this makes no difference, but in an FFA it would. If only there was a free-to-play type gamemode I could use to test this feature out!

<color=#FFD94D><b>CONCLUSION</b></color>

Now, as beautifully complex as this system is, I do have to ask how on earth the developers thought it would be a good idea. What is it supposed to be balancing? Why does the amount of damage dictate Refreshes? How was anyone supposed to know any of this? Questions only the warped mind who dreamt up this system can answer.

I do appreciate the subtleties of the system, but from a gameplay perspective it is abominable. No real human is going to accurately calculate their RefreshValid state in the middle of a fight - that is, if you ever actually get a build where this information matters. The chances that my findings here will affect your next 30 matches range from low to non-existent. At the end of the day, the player experience this system produces is one of confusion, frustration, and randomness. Yet, all of that said, I would not want it changed. Why? Because if it was, the last week of my life would have been wasted.

Thank you for reading my ramblings. I hope you will at least find the table useful.

<color=#8A8A93>Related reading: <color=#7FD4FF>Blocking</color> covers what a block actually does and which cards ride it; <color=#7FD4FF>Poison & damage over time</color> covers how tick damage lands and syncs.</color>', 'd9077ef0f07dec9c41db819f4ac30d7295177eb9', FALSE, 'InfoLibrary · (file scope)')
  , ('30c4d0eaecaffed1', 'client', 'That card is no longer in your collection', '5e8a41789e1b381d29a1b062564656d5a70a1e76', FALSE, 'PlayerCardsUI · ReasonText')
  , ('ad2c06c9542f90dd', 'client', 'That change could not be applied, and some controls could not be put back as they were. Restart the game before you play.', 'fd8923a0ee4ad7bbec7dd3d76c8170a06d9607d2', FALSE, 'NativeUI.Keybinds · KeybindRestoreUnverifiedText')
  , ('d289ab5c873b9c88', 'client', 'That change could not be applied, so every control was put back as it was.', '2beb4760b9d4ae324cf87d0dbbfefa05a4735d3d', FALSE, 'NativeUI.Keybinds · KeybindApplyFailedText')
  , ('49ffcaa33b3624ee', 'client', 'That control could not be saved to your settings, so nothing was changed.', 'be3c67e92c1f475df61f469d43ef2ed4ac217c27', FALSE, 'NativeUI.Keybinds · KeybindNotSavedText')
  , ('f80787f5bedc87aa', 'client', 'That game is no longer live.', 'f336e5fc9ed94a2e1ad76933b8b20b01fad18e70', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('8db15a39284ef8a1', 'client', 'That game is not ready to watch yet.', '76bc0d691ad98e461392b5673079e4604082aa23', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('1dfdd7c1fe114848', 'client', 'That key is already used by another control.', '305633f7eec553c6b766a16426eca83bd7c560a3', FALSE, 'NativeUI.Keybinds · KeybindRefusalText')
  , ('2d3cd942fcdf8d78', 'client', 'That key types into the chat box it would switch.', 'e53f93d56ad81c3825f4904c8e35cc3e9b7c7169', FALSE, 'NativeUI.Keybinds · KeybindRefusalText')
  , ('479ff1480605bff3', 'client', 'That match has ended', '89af1992a09f84e3cfd2e108474917e71cdab03c', FALSE, 'FfaReadmit · Refusal')
  , ('ae7941abc9908b89', 'client', 'That mode is not accepting spectators right now.', '65da818dfea711e0a7259a5b3e271bd6b87e3bde', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('c85b1d98a5f42714', 'client', 'That pack is not available any more', 'fef5d1e1e1a42b598b13c57ffaa3436a4ca8cc70', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('497de7efe9baa376', 'client', 'That pack is still opening - hold on', '79cdb72e24e938844535e2fd5125cac7b5f1a724', FALSE, 'PlayerCardsUI · ReasonText')
  , ('093f3a6c6fae5294', 'client', 'That pack purchase never went through - nothing was charged', '99e66eed782e54f9fe6eca697363e78e34c466bc', TRUE, 'PlayerCardsUI · HandleAnswer')
  , ('9b2af658f3a49a54', 'client', 'That pack was voided - the series it came from was reversed', 'fe1d3861ae8225832149e82d4ff403333a35ba10', FALSE, 'PlayerCardsUI · ReasonText')
  , ('95dd38a118764db0', 'client', 'That player cannot trade', 'ffb3923a70bd40b9a698a6c5d6e8b940dd4f9d7c', FALSE, 'PlayerCardsUI · ReasonText')
  , ('2daa3e30ed263859', 'client', 'That player cannot trade yet', '66b87e1bc2f49682677af1b2e7cef3bbbc43cff5', FALSE, 'PlayerCardsUI · ReasonText')
  , ('c0deaa90cca7799d', 'client', 'That player could not be found.', 'a844ef80805e9e2dba1e9a2d6a2a1f02dedf1902', FALSE, 'MailClient · ErrorDetail')
  , ('00d0c1e7ba22b165', 'client', 'That player declined your last proposal - wait before proposing to them again', 'dc7165ddbbc4df8b3110490120eee67b87c08016', FALSE, 'PlayerCardsUI · ReasonText')
  , ('8bed1d37da44a078', 'client', 'That player has card trading turned off', '4e0dde2bc3badc0401348bfb1c5fe5c4b1910c3f', FALSE, 'PlayerCardsUI · ReasonText')
  , ('1a68c74b7dd0706c', 'client', 'That player has too many proposals waiting - try again later', '42a8864092d52b31c4ba120b939acdf97d46bbb2', FALSE, 'PlayerCardsUI · ReasonText')
  , ('e87a88d15bf3bdc1', 'client', 'That player''s binder is private - they can still propose a trade to you', '570b6a22ef8b60e4134a81532a14110788129059', FALSE, 'PlayerCardsUI · ReasonText')
  , ('97feea73f4a2a1c2', 'client', 'That preset has never been customised, so your avatar was not switched.', '229053b95f5d9a163466dd9ce123e4ffc9e09beb', TRUE, 'AvatarDefaults · UnusableMessage')
  , ('6a3750c09576563b', 'client', 'That shard was already done with other cards - your binder has been refreshed', 'd143a158719cef2e65937b4479717aea7c20cc1b', FALSE, 'PlayerCardsUI · FailShard')
  , ('f264e145a4b40895', 'client', 'That trade has changed - check it again before answering', '9caa66931c9f06f08a06885170f49a27ff2b1afa', FALSE, 'PlayerCardsUI · ReasonText')
  , ('f7cf1f7234635f0c', 'client', 'That trade has expired', 'feb0073d2b8d34a5f59f38719ed0574281808aad', FALSE, 'PlayerCardsUI · ReasonText')
  , ('9a45070b36e5b320', 'client', 'That trade is no longer possible', 'a277faa1f47d40869307f68b94129c0cd7622376', FALSE, 'PlayerCardsUI · ReasonText')
  , ('6cb408f8da5b0153', 'client', 'That trade is not yours to answer', 'bf94df208a2811d3cef5670bd8113dbb1518b58b', FALSE, 'PlayerCardsUI · ReasonText')
  , ('8229dd5d7f51029d', 'client', 'That trade no longer exists', 'd351d39fae68372357aeaa276049c5ee924bbfd5', FALSE, 'PlayerCardsUI · ReasonText')
  , ('72e566717ecb9419', 'client', 'That trade was already answered', '12503869644fd1077cab18913ce91369f5e5923b', FALSE, 'PlayerCardsUI · ReasonText')
  , ('df1137bc49e0fa07', 'client', 'That trade was cancelled', 'b63f19d9d7023ee403152a692f1d35e1ec229368', FALSE, 'PlayerCardsUI · ReasonText')
  , ('8b3b1d6089c8c816', 'client', 'That trade was declined', 'e6905bc946f8cd69b6672bae2170857987f5eb8d', FALSE, 'PlayerCardsUI · ReasonText')
  , ('ac8ce93f705ce9f3', 'client', 'That trade was reversed by an admin', 'e2a03bedc49f6dd7dea955255b3540c022ba3031', FALSE, 'PlayerCardsUI · ReasonText')
  , ('f4fe99e5fc999ad4', 'client', 'That {0} lobby is private — enter its password.', 'd8882b460efd6a4c262200be3f970ca10fa92fdb', FALSE, 'ApiClient · EnrollResult')
  , ('53cc81ae7216d5f5', 'client', 'That''s you - pick someone else.', '4f78ec8afdf19de3929660d707d8d28699f73ac6', FALSE, 'MailUI · AddRecipient')
  , ('a35754f4e143ed36', 'client', 'The Bounce', 'ba6f9d8321e8ac1ce86fc8e723247cfb4453cfa8', FALSE, 'shop catalog · cosmetic name/description')
  , ('a2747db45e42ad62', 'client', 'The Challenger', '26d43bc6493e51b1047f9b89c7a4247b7c236a04', FALSE, 'shop catalog · cosmetic name/description')
  , ('be4894b729971733', 'client', 'The Comeback Kid', 'f3e5625b48f6d3cb48733417bcdcf70a949419ae', FALSE, 'ApiClient · AchievementDefs')
  , ('23a74746442c4c65', 'client', 'The Cryptid', 'd9a3a948f03f6021f1f8317e899698c4663d22b5', FALSE, 'shop catalog · cosmetic name/description')
  , ('68c4b3a3a991374b', 'client', 'The Floss', '4932f159926656102e9a366a3b5482b27c1c0811', FALSE, 'shop catalog · cosmetic name/description')
  , ('889d5548ce21e996', 'client', 'The Helicopter', 'a8e9a6158d251d77ba30554805e11a731a6d3e1f', FALSE, 'shop catalog · cosmetic name/description')
  , ('ffa5de9f35695f0a', 'client', 'The Joker', 'b490feb5229cf1e14c0ea5520a5f578aa945b190', FALSE, 'shop catalog · cosmetic name/description')
  , ('fc38e4476e514059', 'client', 'The Mobsta', '4c2d87bcd6cb6da3b237d31d45dc55d25eb664ec', FALSE, 'shop catalog · cosmetic name/description')
  , ('18a1d1922241aa36', 'client', 'The Mod & Vanilla', 'ba1d95f2de6da3db559cea3ba7bdc3d360dd4e35', FALSE, 'InfoLibrary · (file scope)')
  , ('99396dedb5f2d0cd', 'client', 'The Robot', 'f97d3b31bdb725fbe43f10f3481dba557c7aa946', FALSE, 'shop catalog · cosmetic name/description')
  , ('3fd3cdb18f2f274c', 'client', 'The Shimmy', '18350a4c720998d2321ea9fb4be9972b87283f36', FALSE, 'shop catalog · cosmetic name/description')
  , ('e41cbfd220932ab2', 'client', 'The Wave', 'a0ad0ecead7d6f934d389fc1ccb31c50dbdeb30b', FALSE, 'shop catalog · cosmetic name/description')
  , ('b60967a73e29c66e', 'client', 'The board below shows every key that does something during competitive play, as you have them bound now: gold keys belong to the mod, blue keys to the base game, purple to both. Every control on it except Escape, Enter and B can be moved on the Settings tab''s Controls page, and F5 always opens this menu whatever you set.', 'd9f4fbb94dff1bce83c1be5727b58be874dd158d', TRUE, 'InfoLibrary · (file scope)')
  , ('c8d198d08b2458b4', 'client', 'The bot & check-ins', '40e583e2c5196cc44e0152a1ec7f0e9003b05c8a', FALSE, 'InfoLibrary · (file scope)')
  , ('69774f9c26c9414d', 'client', 'The cards changed while the trade ran - nothing moved, check your binder', 'cebf476f51f064283048e126524afea4192e6465', FALSE, 'PlayerCardsUI · ReasonText')
  , ('28664eb4ad65366d', 'client', 'The cutoff is scored points, never a clock. Either lock condition closes the window.', '4b98983397b11a2cf0b05ae55891d3d7a35221b7', FALSE, 'InfoViz · BuildBetWindow')
  , ('47d014bf021d5793', 'client', 'The dance your card performs: it plays once each time your card is shown in a binder or a pack, drawn from your own character on this PC. Pick one you own; None keeps your card still.', '3f2e1ca3f4eaaaa9ab8255eac2f06c8f0c1ed7e4', FALSE, 'PlayerCardsUI · BuildSettingsRows')
  , ('d9ba1c95478f3c23', 'client', 'The exact green a poison tick flashes on its victim.', 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', FALSE, 'shop catalog · cosmetic name/description')
  , ('3cf0b30ec7dd441c', 'client', 'The expression of a true warrior going into battle. Takes up the mouth slot', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', FALSE, 'shop catalog · cosmetic name/description')
  , ('8925ce83e5211edf', 'client', 'The game reserves that key.', 'bcad33fbaafb6b4afa10708afbfc5ca958f4e629', FALSE, 'NativeUI.Keybinds · KeybindRefusalText')
  , ('09f590ed72875261', 'client', 'The gameplay ramifications are best illustrated through Silence. Beginning a game, RefreshValid is set to false, so your first Silence fails to trigger a Refresh. (I have not been able to test whether the bool resets between rounds - it does not reset on death, resurrection or new card picks, so I suspect it does not.) After your first failed Refresh, RefreshValid is set to true. Thus your next Silence triggers a Refresh but resets RefreshValid to false. So it continues in an endless loop where every other Silence triggers a successful Refresh. Each column below is one action; the top row is the RefreshValid state BEFORE it:', '80444cd6246036481a041786b427412a711aca7e', TRUE, 'InfoLibrary · (file scope)')
  , ('d9253ed2b22e05f4', 'client', 'The guarantee: only your nametag styling and the quick-chat phrases you send can ever reach a non-modded opponent.', 'cc15912c399aa848c449dacc5e83fe084a0fa5f3', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('f629fca8d7d75ba6', 'client', 'The host changed the lobby settings: {0}', 'a0c5bac8fbaa67e0d00df80701ed394953356271', FALSE, 'ApiClient · HandleState')
  , ('24230f46ba7a76e6', 'client', 'The host removed you from this lobby.', '9f61b5edffaab420f9ca22f57f9f3dcf646c4a94', FALSE, 'ApiClient · EnrollResult, FfaEnrollResult')
  , ('79258b6f506e9b43', 'client', 'The host reset the lobby settings to the defaults.', '2a64329fed31c99a46f8f2f4dc643d2838172024', TRUE, 'ApiClient · HandleState')
  , ('5571c94dd2e66443', 'client', 'The lead in rounds changed hands {0} times over the set', '017802e96c748cec0673a6f57894fd9b45f22eb1', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('5e53b853e83394be', 'client', 'The match could not be confirmed with the server. Please queue again.', '0dba5250def08d850853ff98d82bedf0563a804f', FALSE, 'FfaAssembly · ExitToast')
  , ('3b7b8c0567bd638e', 'client', 'The match could not continue on your connection. Please queue again.', 'af24d6d6a6df42b7baf3edbac6f2f1f90ce3daa6', FALSE, 'FfaAssembly · ExitToast')
  , ('ba2767691be10097', 'client', 'The match could not start. Please queue again.', '0ad4a2b715837549567c739e2df595db4c11ee6d', FALSE, 'FfaAssembly · ExitToast')
  , ('495cd6b85f8053c7', 'client', 'The match is already running.', '1455ac4c5d1bbe0bb3781c899ab38f83426e46a0', FALSE, 'SpectatorHud · DrawBlackout')
  , ('266f789c58930781', 'client', 'The message contains a word that is not allowed.', '30645a4e58536be0d40c45c60f3bc502e77f369a', FALSE, 'MailClient · ErrorDetail')
  , ('d5bf8531fbbdc484', 'client', 'The message contains characters that are not allowed.', '91b8f58e21a0eaa877618fd5517384166a5a71f3', FALSE, 'MailClient · ErrorDetail')
  , ('53a64dc000e592f9', 'client', 'The message is too long ({0} characters max).', 'd238602f14d5c048c4c327e48cf6bedf5d3c8ff5', FALSE, 'MailClient · ErrorDetail')
  , ('e3fbf8064a0d9f01', 'client', 'The message repeats one character too many times.', '66a8da6b04bab2ac0d06784253b757821788991f', FALSE, 'MailClient · ErrorDetail')
  , ('f2d0a7e6347ff683', 'client', 'The mod changes vanilla gameplay only where every player agreed to it. This page explains exactly how it decides, and what is guaranteed when you play with non-modded people.

<color=#FFD94D><b>THE GUARANTEE</b></color>

<color=#7FE87F>A non-modded player always gets pure vanilla gameplay, and any gate that can''t prove a change is safe leaves it off.</color> Whole-room changes fail closed for everyone identically. The one per-player feature is poison sync, which follows the poisoned player - an unmodded victim''s poison stays vanilla.

If the mod can''t prove a feature is safe to run, it runs vanilla.

<color=#FFD94D><b>HOW ROOMS ARE CLASSIFIED</b></color>

Mode-tied gameplay runs only in rooms the mod itself created, and the room''s name says which mode issued it:

- <color=#7FD4FF>ranked_</color> - 1v1 ranked queue rooms
- <color=#7FD4FF>team_</color> (or the 2v2 room marker) - 2v2 rooms
- <color=#7FD4FF>sct-</color> - sync tournament rooms
- <color=#7FD4FF>ovt_</color> - 1v2 rooms
- <color=#7FD4FF>ffa_</color> - FFA rooms, and only while the FFA lobby engine is actually active

A public quickplay room or a normal 6-character room code matches none of these, so every mode-tied gameplay change stays off there.

<color=#FFD94D><b>CAPABILITY GATES</b></color>

Changes to the shared simulation go a step further: each player''s mod advertises a capability tag BEFORE joining the room, so any client that can even see you has already received your tag. Then:

- <color=#7FD4FF>Grow normalization</color>, <color=#7FD4FF>FFA map-object scaling</color> and the <color=#7FD4FF>FFA same-card dealer</color> require EVERY fighter''s tag. <color=#7FE87F>One vanilla player, one outdated mod, or one player whose mod disabled itself switches the feature off for the whole room - symmetrically, on every screen at once.</color> Nobody plays by a different rule than their opponent.
- <color=#7FD4FF>Poison sync</color> activates per victim, in any online room: a current victim''s own client judges their poison; an unmodded victim''s poison stays vanilla. The mixed-room details live in <color=#7FD4FF>Poison & damage over time</color>.
- Spectators never count toward or against these checks.
- If a feature''s patch fails to install, that client never advertises the tag. If any other BepInEx mod is detected at startup, the whole mod disables itself and revokes its tags - full vanilla behavior.

<color=#FFD94D><b>TWO KINDS OF FIXES</b></color>

Not everything is gated, and the distinction matters:

<color=#7FD4FF>Crash prevention</color> - always on, everywhere, quickplay included. These guards stop vanilla bugs like the frozen-inputs-at-match-found crash, the permanently dead Escape key, and the Phoenix revive crash. They change no rule: each one replaces a crash or a broken state with what the game intended.

<color=#7FD4FF>Gameplay changes</color> - gated as above. Mode logic needs its mod-issued room; Grow and the FFA features need the full-room capability check; poison authority is per-victim as described.

Between the two sits a band of local repairs (re-registering vanilla''s own broken bullet effects, clearing a stuck auto-fire flag between games) that run in any game - but these only repair your own screen''s bookkeeping toward what the bullet''s owner already decided. They never change a rule, and can''t create a disagreement vanilla didn''t already have. The full inventory is in <color=#7FD4FF>Bug fixes the mod ships</color>.

<color=#FFD94D><b>QUICKPLAY WITH THE MOD</b></color>

Playing quickplay or a room code with the mod installed, you get vanilla rules plus tracking: your casual results and stats still record, and achievements can still unlock. <color=#8A8A93>A recovery guard can also restart a dead quickplay search for you - that is connection plumbing, not gameplay.</color>

Two fairness fixes can reach quickplay and room-code games: <color=#7FD4FF>Grow normalization</color> (every fighter current, everyone''s Ranked on at connect - both sides always agree on it) and the per-victim poison sync, which follows the poisoned player wherever they play (see <color=#7FD4FF>Poison & damage over time</color> for the mixed-room details).

<color=#7FE87F>And your opponent never has to know the mod is there unless you talk to them: the only things a non-modded player can ever see of it are nametag styling and quick-chat messages you send</color> (see <color=#7FD4FF>What unmodded players see</color>).', 'a415c1bcab4833e32dd4d2f7760f355aca5d935b', TRUE, 'InfoLibrary · (file scope)')
  , ('08df419b4ad6eed8', 'client', 'The mod ships 50 achievements. Each unlocks exactly once per account and pays gold on the spot - <color=#7FE87F>100 gold</color> by default, up to <color=#7FE87F>1000</color> for the hardest; every line below shows its payout. Browse them under <color=#7FD4FF>My Stats - Achievements</color> in the F5 menu: each row shows the condition, your unlock date, the percentage of known mod players who have it, and its gold. Click a row to see who has earned it (the first 500, in unlock order).

<color=#FFD94D><b>HOW THEY ARE CHECKED</b></color>

- Two checkers exist. 14 achievements are judged by your own game the moment a game ends; the other 36 are judged by the server - most when a match, series or rating update lands, the three translator tiers when translation work is approved. <color=#8A8A93>Server-side unlocks can pop a moment after the game - that''s normal.</color>
- Client-checked achievements need a real online game. Sandbox, offline play and spectating never award anything.
- Every condition tracker is per-game and resets when a new game starts - a rematch is a clean slate, so damage taken in game 1 can''t spoil Untouchable in game 2. (Streak counters, by design, are the exception: they span games.)
- The input trackers (Pacifist, Immovable Object, Grounded) only sample your keys while you are alive and fighting. Card picks, the pick phase and time spent dead never count against you, and neither does typing in the mod''s chat or the F5 menu.
- Client-checked achievements run in 1v1, 2v2 and 1v2 games. They never fire from FFA games - FFA has its own six, checked by the server.
- A client-checked <color=#7FD4FF>sweep</color> means you win with the opponent on 0 rounds. In a room set to a shorter round target, a 3-0 still counts. <color=#FF6666>The server-checked 5-0 achievements demand the opponent on 0 with at least 5 rounds won.</color>

<color=#FFD94D><b>CLIENT-CHECKED: PRECISION RUNS</b></color>

- <color=#7FD4FF>Untouchable</color> - win a game in which your health never dropped, even once. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pacifist</color> - win without ever holding the fire button during live combat. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Immovable Object</color> - win without ever holding a movement or jump key during live combat. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Grounded</color> - win without ever holding a jump control. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Instinct</color> - win with 3 or more card picks, taking the pre-highlighted left-most card on every pick without ever moving the selection. <color=#8A8A93>Only checked in queue and sync-tournament rooms - room-code games, async tournament matches included, skip it.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>CLIENT-CHECKED: SWEEPS AND STUNTS</b></color>

- <color=#7FD4FF>Silent Assassin</color> - sweep with Sneaky (or Sneaky Bullets) in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - sweep with Mayhem in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Fragile Perfection</color> - sweep with Glass Cannon in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>No Escape</color> - sweep with Chase in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Rise from the Ashes</color> - sweep with Phoenix in your build, without dying and without a Phoenix revive ever firing. <color=#7FE87F>500g</color>
- <color=#7FD4FF>The Comeback Kid</color> - win after the rounds ever stood at you 0, opponent 4 or more. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Stacked Deck</color> - finish a game holding 5 or more copies of one card. No win required. <color=#7FE87F>300g</color>
- <color=#7FD4FF>God Build</color> - win with Shields Up in your build, ending the game on a gun with 1 ammo or less that reloads in 1 second or less. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Into the Deep End</color> - take Abyssal Countdown as your FIRST pick of the game, trigger it in every round, and win. <color=#7FE87F>300g</color>

<color=#FFD94D><b>SERVER-CHECKED 1v1 BUILDS</b></color>

Judged from the reported match. You must be the game''s winner unless a line says otherwise.

- <color=#7FD4FF>Bullet Hell</color> - win 5-0 with Barrage in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - win 5-0 with Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Demolitionist</color> - win 5-0 with Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - win 5-0 with Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Field Medic</color> - win 5-0 with Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Double Nova</color> - win with 2 or more Supernovas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Lumberjack</color> - win with 2 or more Saws. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pristine Perfection</color> - win with 2 or more copies of Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Living on the Edge</color> - win with 2 or more Glass Cannons. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - win with Sneaky and Drill together. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Sustained Power</color> - win with Empower and Healing Field together. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Collector</color> - win with 4 or more copies of any one card. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Clutch</color> - win after the score ever stood at 0 points for you against 6 or more for the opponent - that is, down 0-3 in rounds. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Twins!</color> - both players finish with exactly 5 cards each and identical builds, copy counts included. Both unlock it; nobody needs to win. <color=#7FE87F>500g</color>', 'ba06807b5ff73d87042b6a781e1e66de58a4b3b0', TRUE, 'InfoLibrary · (file scope)')
  , ('b68acb4c98e9ea89', 'client', 'The mod''s own controls cannot take a mouse button.', '29a5f65eca14d7bd96b2cd422d987cd1b243e3c2', FALSE, 'NativeUI.Keybinds · KeybindRefusalText')
  , ('f799b2c261baeb4f', 'client', 'The pack answer could not be read - checking again shortly', '0495b1e41ae2b464d59a6d5719b987b760c1e2ed', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('a641e26374e228e5', 'client', 'The pack is still yours to open', 'ef78e5cd61ce1f0aabda2883ef9c85540d86ab3f', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('9e224e6faaf4a32e', 'client', 'The pack price changed - check the new price and try again', 'a9e422da77adf45bf1fff85c851e47e1bf33ea61', FALSE, 'PlayerCardsUI · ReasonText')
  , ('e3a91193fd1ee34c', 'client', 'The picture was not ready in time - try again', '208a87b9e17619181d807fcd12f80c77cb05e49f', FALSE, 'PlayerCardsUI · PortraitWaitCo')
  , ('32a2196887f35f53', 'client', 'The pool changed while your pack was opening - nothing was charged, try again', '03722ca2a06867867a54162bf602b4f6ca4d72c2', FALSE, 'PlayerCardsUI · ReasonText')
  , ('c399e1c676e181e4', 'client', 'The preset you wear everywhere the mod is running: ranked, 2v2, 1v2, FFA and private games where everyone has the mod.', '94c0409540edfa6745f6d75d0a7d092ba646acd0', TRUE, 'NativeUI, SettingsDescriptors.g · BuildSettingsTab, HelpBodyTr')
  , ('c9c5e845538add4d', 'client', 'The preset you wear in Quick Match and in any game where somebody does not have the mod. Only presets a base-game player''s own game can load are offered here, because those are the only ones an unmodded opponent can actually see. To make a preset an unmodded opponent can see: open the character menu, choose an empty preset, and build the face from base-game eyes, mouths and details only.', '6457b33d171ff055e57f03716df05e58b476a180', TRUE, 'NativeUI, SettingsDescriptors.g · BuildSettingsTab, HelpBodyTr')
  , ('a3ba08a25171bc89', 'client', 'The purple the Demonic Pact card is drawn in.', '50a9d67312296bed3f5bcb9316939538b5ab0e4d', FALSE, 'shop catalog · cosmetic name/description')
  , ('aeb4bae924db54ad', 'client', 'The report could not be read', '5a7fbd2ce825994a05331d9cf2e88921d6240f41', FALSE, 'SessionReportView · ErrorMessage')
  , ('854d11d214604952', 'client', 'The report details are too long.', '6f43b8da2c4d3c96806b20f83bce26bcc81f7f96', FALSE, 'MailClient · ErrorDetail')
  , ('da496c66b15da7fa', 'client', 'The report details contain characters that are not allowed.', '5a09ef793c04d82aaa1cf575a57a9045530421d0', FALSE, 'MailClient · ErrorDetail')
  , ('ae366cc0d2f0a1f5', 'client', 'The report details repeat one character too many times.', '54b495e75060e8c4ded9f4302f039146b8fd1191', FALSE, 'MailClient · ErrorDetail')
  , ('8ce94a58f23f5ead', 'client', 'The report request could not be started', 'd2ba265f2e2a73f932728d264800fe63975bc5e8', FALSE, 'SessionReportView · ErrorMessage')
  , ('92e35d2e6c297c41', 'client', 'The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.

<color=#FFD94D><b>NEVER RECORDED AT ALL</b></color>

- Data consent off: the mod runs fully offline. Nothing is ever sent except a version check.
- Offline, practice and sandbox games: never reported by the client, and refused by the server as a backstop.
- Spectator seats submit no match record and no persistent stats. (The mod keeps local diagnostics in its own log — frames, connection facts — and sends nothing automatically; they leave your PC only inside a bug report you choose to attach logs to.)

<color=#FFD94D><b>RANKED OR CASUAL</b></color>

- Either player''s Ranked toggle off in a room-code game - it plays as CASUAL. Still fully recorded with stats and XP; it never touches rating (see <color=#7FD4FF>How games are tracked</color>).
- Opponent has never run the mod - always casual, never upgraded. (A live unfinished series from an earlier sitting is the one thing that keeps ranked status across a gap.)
- Toggling Ranked off MID-SERIES does not void the series. The running best-of-3 is your consent record; its games stay ranked.
- A game reported as casual is UPGRADED to ranked when the server can see both players are modded, both have Ranked on, and the sitting is live.
- A ranked-banned participant forces a 1v1 casual at report time - even in a queue room, even mid-series. (The other modes shut banned players out at the door instead.)
- Mod-issued rooms are consented by definition; queueing is consent. The ranked queue, 2v2 and tournaments rate; ranked FFA lobbies rate while casual ones don''t; 1v2 records without rating.

<color=#FFD94D><b>DISCONNECTS - 1V1</b></color>

- You leave a game to join a queued ranked match - the game you left is canceled: nothing recorded, no leave logged.
- Opponent DCs at 4-4 - you get the win, recorded 5-4.
- Opponent DCs while you hold 4 rounds - you get the win at the standing score.
- Any other DC - <color=#FF6666>the game is canceled and no result is recorded</color>, even when the leaver was ahead. Nobody gets a free win and nobody eats an unfair loss (the leave itself can still be logged - see below).
- Ranked leave %: a DC is logged against the leaver when the CURRENT game had meaningful play (2 or more points scored, or a completed round) and neither side was at 4 rounds. One DC per player per series. The stat is your DCs divided by your ranked series played plus your DCs.
- Casual rage quits: ANY mid-game leave in a casual 1v1 is logged, even at 4-0. It feeds the Rage Quit % stat (how often opponents walk out on you) - never rating. (A survivor already at 4 rounds still takes the casual win and its XP.)

<color=#FFD94D><b>DISCONNECTS - 2V2 AND FFA</b></color>

- 2v2: a team DCs while the other team leads the series and the abandoned game had 2 or more points - the leading team takes the whole series, with full ratings and rewards.
- Any other 2v2 DC - the series PAUSES for manual admin resolution instead of auto-deciding. If the same four re-queue within about 30 minutes, the matcher puts them back on the same series with the score kept.
- FFA keeps playing when someone leaves, as long as 2 or more remain (a game that drops under 3 players before the field scored 2 half points is cancelled instead). The leaver''s tallies are frozen, and they are still placed and rated for the game they left during - <color=#FF6666>leaving at 0 points does not dodge the loss</color>.
- FFA early-leave grace: a leaver who left before the field had scored four half points in total, whether or not any became a full point, is unrated for that game and receives no game Gold or XP from it. Achievements can still be earned and pay as usual, but an unrated game earns no title-ladder progress.
- An FFA player who left in an EARLIER game rides later reports as absent, excluded from those games'' ratings and rewards.

<color=#FFD94D><b>SERIES: RESUME, STALL, EXPIRE</b></color>

- <color=#7FE87F>An undecided best-of-3 resumes with no time limit.</color> Meet the same opponent tomorrow or next week and game 1 still stands. An expiry existed once - leavers waited it out to bank rating, so it was removed.
- Rating moves ONLY when a series completes (first to 2 game wins). Games of a series that never completes keep their match rows, XP and gold; the rating change just never happens.
- A series with no game recorded 30 minutes after it was created is abandoned and its bets are refunded.
- A mid-series stall of an hour refunds the bets, but the series itself stays active and resumable.
- Tournament series are exempt from this pruning - the bracket owns their lifecycle. A tournament match decided by forfeit can''t be bet on.

<color=#FFD94D><b>THROWN OUT AFTER THE FACT</b></color>

- The one AUTOMATIC invalidation in the whole mod: a repeated pattern of implausibly short matches between the same two players inside a short window. The current match AND the earlier short ones are invalidated together, their gold and XP reversed, their series voided.
- Admin reversal: an admin can void a series - rating changes subtracted, gold clawed back, every match in it invalidated, unsettled bets refunded. Invalidated matches disappear from every board and stat.
- Quarantine (2v2 and FFA): a report that arrives for a lobby that''s no longer active isn''t deleted - it''s held for admin review, and an admin can still accept it into the record or discard it.

<color=#FFD94D><b>IF THE REPORT CAN''T SEND</b></color>

- A failed report goes to a persistent outbox: retried in the background and saved to disk, so it''s re-sent on your next launch even if you quit right after the game. You''ll see ''Couldn''t record the match - retrying in the background'', then ''Match recorded'' when it lands.
- 1v1 reporter crashes before the report exists - the surviving opponent''s disconnect path usually records the result instead.
- FFA elects its reporter among the players still present, so a crashed reporter is never elected. A winner who quits before the report is still recorded from their frozen tallies.
- A 2v2 game that ends without its series id retries the lookup and defers the send; if that also fails, the game is not recorded.', '64065114ecebfc53382315b24ebc5fd4b6dbca3f', TRUE, 'InfoLibrary · (file scope)')
  , ('4d5cf30764f3830b', 'client', 'The same actions in a different order', '8a37ccdd1183d3dc18cee74c21b8c9c97139c260', FALSE, 'InfoViz · BuildRefreshWindowSequences, TextFallback')
  , ('ade21bda2fc0c1a5', 'client', 'The seat was released before you returned', '599201187ca682b14c718c1edf1c2e8f8f1d5919', FALSE, 'FfaReadmit · Refusal')
  , ('32d2c8359f1fef07', 'client', 'The secure connection to {0} answered with an error (HTTP {1}). The portal needs it; the game keeps working on the backup connection.', 'd5b117f10ffc8778cabfba8b7aba015e3f60a84e', FALSE, 'SecureRouteText · Failure')
  , ('ed7895202a5064dd', 'client', 'The secure connection to {0} answered, but not as the SCR server. The portal needs it; the game keeps working on the backup connection.', 'e3fc95f79db81ac07a5c0346aea0124f33237a5a', FALSE, 'SecureRouteText · Failure')
  , ('e96e9bdeefbec771', 'client', 'The secure connection to {0} could not be opened. The portal needs it; the game keeps working on the backup connection.', '2562ef774723433b2dd876bc876d1e579fa2c191', FALSE, 'SecureRouteText · Failure')
  , ('3395cdf89969ea91', 'client', 'The secure connection to {0} failed its security check. The portal needs it; the game keeps working on the backup connection.', '8e8d7fc97b00890e397b232c3cb6457b32935de3', FALSE, 'SecureRouteText · Failure')
  , ('c005d7dba26a5b0e', 'client', 'The secure connection to {0} failed: the address could not be looked up. The portal needs it; the game keeps working on the backup connection.', '8bb03cec7b8a5bbb356f4987fa71f260cad6b966', FALSE, 'SecureRouteText · Failure')
  , ('ef36a94f153fa40d', 'client', 'The secure connection to {0} timed out after {1} s. The portal needs it; the game keeps working on the backup connection.', '91882fbef8fdd21f2a873bb77bfedece97050940', FALSE, 'SecureRouteText · Failure')
  , ('420805fb2bf0d520', 'client', 'The secure connection to {0} was refused. The portal needs it; the game keeps working on the backup connection.', 'a0ec6c71c98888b264fb1e52c1ffa86dc30e725f', FALSE, 'SecureRouteText · Failure')
  , ('3f9c471fc9e220dc', 'client', 'The selected cosmetic is still loading.', 'e5701337d8b35a274ac925afbd1394d8ba3e2c4d', FALSE, 'NativeUI · StartCosmeticPlacementAdjustment')
  , ('161970b49a18c03f', 'client', 'The server could not answer about your pack - checking again shortly', '0fd73328ec70e8e04eea4ea66332a9ee086fb80b', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('b40d3df6121fb8d3', 'client', 'The server could not read that trade request - update the mod or try again', '1874f33a0c88ff4e21e14bee93f2979b381af4ce', FALSE, 'PlayerCardsUI · ReasonText')
  , ('69f2dc842f8fdaad', 'client', 'The server is busy with that trade - try again in a moment', '7c49586ebb3a3722ff4aaab3d1086bb23e6a8e82', FALSE, 'PlayerCardsUI · ReasonText')
  , ('c045e838e0d9048d', 'client', 'The server kept asking us to pause - we waited as long as we can; the rest are still in your binder', 'fa0fcaf674f50ff08b2cc9bd67c4b3e520b2c948', FALSE, 'PlayerCardsUI · ReasonText')
  , ('8d2b5e3300bf0cb4', 'client', 'The server refused that - try again in a moment', '335870f68a38779df1fee5b11cfdfc4955a592c3', FALSE, 'PlayerCardsUI · ReasonText')
  , ('493142c8ef702485', 'client', 'The server refused the title change.', '4a70f54519df0f3173869cd674041664c00af5d5', FALSE, 'TitleLaddersUI · OnWearClicked')
  , ('34097f6a51a2eff8', 'client', 'The server refused this request ({0}).', '8bb5dbbad00cb39d4c4de4ce8473abfc6c82a2d7', FALSE, 'MailClient · ErrorDetail')
  , ('c9a5ea03566f65f1', 'client', 'The subject contains characters that are not allowed.', 'eb0ca29fad7ce89cf3bb17409c868be370ee1c79', FALSE, 'MailClient · ErrorDetail')
  , ('91a1e4d8d8097fcc', 'client', 'The subject is too long ({0} characters max).', '9b3afe4da74b7727b11fa0e01d3fbcaeccf17258', FALSE, 'MailClient · ErrorDetail')
  , ('2506a4c323852259', 'client', 'The subject must be a single line.', '0967c16f2f49c7ed6c3f978cad149d2741eaf58d', FALSE, 'MailClient · ErrorDetail')
  , ('dca1b81b5132c44f', 'client', 'The subject repeats one character too many times.', '6f3f20c0701e938f7844a2a2913e49a69f8cd20e', FALSE, 'MailClient · ErrorDetail')
  , ('89132bd80f16b0ea', 'client', 'The two wheels cannot take a modifier key.', '3aeaa26d827619fd5beffeaf78644086fcfac744', FALSE, 'NativeUI.Keybinds · KeybindRefusalText, KeybindRenderPane')
  , ('08e4b089323f0e2d', 'client', 'The white line is your rating; the band is the rating deviation - it shrinks as you play, and your rating moves less once it is narrow.', '4e0b21fb9bea2e824b17f811cb690017e9a9e984', TRUE, 'InfoViz · BuildGlickoRd')
  , ('84521b8589cb5bc1', 'client', 'They already left the lobby.', 'db33e30c2adcc157e72c999486438d03b7b67162', FALSE, 'ApiClient · KickRefusalText')
  , ('288dbb0fdf1491bc', 'client', 'They/them', '2a94b32a35c314d000ef6cd80beca279a0e2067b', FALSE, 'shop catalog · cosmetic name/description')
  , ('44b5fdd557a067f1', 'client', 'They/them I', '58989067415f754d205b51e5b9c20265eb6440c9', FALSE, 'shop catalog · cosmetic name/description')
  , ('5dd14d7bbe0266cb', 'client', 'They/them II', 'a70ebcf353d74d7db85932a7afd0f4376367db64', FALSE, 'shop catalog · cosmetic name/description')
  , ('9ac15f440744cc84', 'client', 'They/them III', 'f87d8bdf7233e4680038ca142d78ca4596ccd025', FALSE, 'shop catalog · cosmetic name/description')
  , ('6979e92369e575d1', 'client', 'They/them IV', '2863d83c550f0a10bf2c0c4f63dd32020c7f10d1', FALSE, 'shop catalog · cosmetic name/description')
  , ('dcbab2eae52cf65f', 'client', 'They/them V', '0cafce6645b8661e55c9df3ec88ead0022536646', FALSE, 'shop catalog · cosmetic name/description')
  , ('f235df555d002514', 'client', 'Thicker menu text. Uses the game''s own font at a heavier weight - not a different typeface.', 'e2c34a89258190d36f1eb34cb0743e6fea492528', FALSE, 'NativeUI · BuildSettingsTab')
  , ('f0607d4b143a64b0', 'client', 'Thicker menu text: <color=#88FF88>ON</color>', '34a21e05c30ded2a040b26c49002ff123c162768', FALSE, 'NativeUI · PaintHeavyFont')
  , ('b4d0bf3130aeccad', 'client', 'Thicker menu text: <color=#FF9966>OFF</color>', '5898784be18a6aba413074e338d99a93783068ef', FALSE, 'NativeUI · PaintHeavyFont')
  , ('b697880762e3dc8a', 'client', 'Third-Place Match', 'b21bd14ee4c5c4af11dc4fa7061ac7be7ea2fc63', FALSE, 'NativeUI · TrRoundLabel')
  , ('7122492c4d94cb89', 'client', 'This account cannot send mail.', '980f8f7a005ea297b36863b4f9dc5af47a107e40', FALSE, 'MailClient · ErrorDetail')
  , ('ca295c7c1131aee2', 'client', 'This account cannot trade cards', '341b18af5e6fdad850d15c00192f44a7781296ab', FALSE, 'PlayerCardsUI · ReasonText')
  , ('c8b8c9f66518f658', 'client', 'This account is not ready for mail yet - try again later.', '0bf3d6b67e43f2f4ab78212f925262b8fec5ba12', FALSE, 'MailClient · ErrorDetail')
  , ('4f2532a4d52ec616', 'client', 'This account isn''t registered as an artist.', '8d3f894fef9a0d6167b3bc9a6cbb1e4536c3656b', FALSE, 'NativeUI · RefreshArtistTab')
  , ('009938a72c78a165', 'client', 'This account was deleted - there is no pack to recover', '04d45c0b9eb0bed3a96c710a468fc36cbd1b469f', TRUE, 'PlayerCardsUI · HandleAnswer')
  , ('5d21bdd01e548ebe', 'client', 'This album requires a newer mod version', '7b7e7647c451370101bd2a1c3d708e4869be52d2', FALSE, 'ServerTextRules · TrRefusalDetail, TrRefusalObject')
  , ('4ce7f5c5cac95c36', 'client', 'This artist has restricted you from buying their items', '9a8fa1b99f5627a9ec83527fcc9c81a2376cd7e5', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('49b956669342a00e', 'client', 'This cosmetic has not shipped in the mod yet and cannot be gifted', 'eed2a5ec4901e2532a834da46e650a436794178c', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('24e16c90be178d0c', 'client', 'This cosmetic has not shipped in the mod yet; stock stays closed until it does', '4ff7d5fcbf5b0a5844b5cdedf0154030a6cb8e77', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1dd732c9889fad99', 'client', 'This cosmetic has not shipped yet; adjust its existing submission instead', 'ab0cb0ac1b37ac2e43c4e09f804e747258216baa', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('3e87e5058c1aa582', 'client', 'This cosmetic is approved but has not shipped in the mod yet', 'f208ca70007f5b0ea151f084479b26f06099d3c7', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('738daca5c3f26df9', 'client', 'This is so sad. Please give this man a break', '439df3824c961ecc56f1fe97caa5ffd60c2a740b', FALSE, 'shop catalog · cosmetic name/description')
  , ('20e3c976ee553dfa', 'client', 'This is your only copy of this card', 'b8e8e823660003eb04c36105633f2c379a4313b2', FALSE, 'PlayerCardsUI · RefreshCompose')
  , ('58eeef8807d9892c', 'client', 'This item requires a newer mod version', '985b07e43a52673229eea39b9d71ce52c933e0e1', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('9587bbf7526fe6c6', 'client', 'This item requires a newer mod version than the recipient has used; they need to update the mod first', '387933644b2eb228747753b5af4ab22c1eb155bf', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5efc804cdbd7b97c', 'client', 'This lobby closed before the match started. Nothing was counted.', '6c017ee044ef4c2b9a89650b1554c3bb61c62259', FALSE, 'FfaAssembly · ExitToast, OnNotice')
  , ('039b85ed360c892c', 'client', 'This lobby is no longer open - the setting was not changed.', '1d11fc4b57f6bc0487c9216ba0e334ff2cc1d31d', FALSE, 'ApiClient · RulesDetailText')
  , ('9910c408b19e9929', 'client', 'This lobby uses settings your mod version can''t play - update the mod.', 'e1b42ad8989065e6a3087c83ce3e497dc835a1e8', FALSE, 'ApiClient · RulesDetailText')
  , ('155c3f658befa4a1', 'client', 'This mod sends data to a private server run by the mod author to power the leaderboard and ranked matchmaking.

What gets recorded if you allow:
  • Your Steam ID and in-game display name
  • Your Discord ID and username, ONLY if you link your Discord via the in-game link code
  • Each match you play: rounds won, points, duration, cards picked, cards offered, opponent
  • Your Glicko-2 rating history

What you can do later:
  • Revoke consent anytime with the Data & Privacy switch (F5 → Settings → Privacy & account). Reporting stops.
  • Delete your data with the Delete My Data button (F5 → Settings → Privacy & account). Steam ID, display name, and Discord link are scrubbed. Matches stay so other players'' ratings and histories aren''t disturbed. Deletion is IRREVERSIBLE — you cannot re-register this Steam ID later.

Choose Allow to use the leaderboard. Choose Decline to run the mod fully offline.', '2df686421487c143005754eeb70aff865ad006dd', TRUE, 'CompetitiveUI · DrawConsentModal')
  , ('e1b3992c0376d935', 'client', 'This node serves reads only; writes are handled by the primary. Seeing this means a request reached the standby that should not have.', '2d670f74574cc5384deb2fe4785628198592ed8b', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5849f232f351cc51', 'client', 'This release only ships a zip — opening the releases page to update manually', '27694ce8fa62968aaec88d052b20071f9e6a3402', FALSE, 'ApiClient · DoAutoUpdate')
  , ('8f174f2aaacd01b6', 'client', 'This report is not available', '50227628c89ba9e09dcc721b8680e92633d9de04', FALSE, 'SessionReportView · ErrorMessage')
  , ('37d0bc7fab06c7ea', 'client', 'This rung has no shop row on the server, so it cannot be worn.', '9f97bda8874100ce083fa21d2d31c96b49f39a8c', FALSE, 'TitleLaddersUI · OnWearClicked')
  , ('e18bda3d30d526af', 'client', 'Thorn Crown', '526a09199b53f93b3d5427114172a2671c6cd74e', FALSE, 'shop catalog · cosmetic name/description')
  , ('e3f60beb4c28d4fc', 'client', 'Those cards cannot be sent in a trade - choose them again', '87ddac4d6d5fa465a13264bfb87e64543cedd409', FALSE, 'PlayerCardsUI · ReasonText')
  , ('12f7c7e33d999282', 'client', 'Three orbiting spheres of raw energy. ANIMATED.', 'cb7c351d80fb7f2eb5d656664b0709b7a3bd0416', FALSE, 'shop catalog · cosmetic name/description')
  , ('f1956f7da9acba2f', 'client', 'Thruster', '1df3e2c454f7a0f7fab70025dc725310c34a68cc', FALSE, 'shop catalog · cosmetic name/description')
  , ('4622a66c4c03af3f', 'client', 'Thunderbird', 'c4780f4837eebde8ca1de31df251ef05e2361eb2', FALSE, 'shop catalog · cosmetic name/description')
  , ('9c3600034286ad0a', 'client', 'Thunderstore', '6bc6c5a526fc83f0257710772097ebe1885b2b2b', FALSE, 'NativeUI · BuildPage')
  , ('3b839398da0a7306', 'client', 'Tidepool', '60c939e8c8b5a9eee31173dadc4d14d0f36d8887', FALSE, 'shop catalog · cosmetic name/description')
  , ('a9b069824b3e0bcd', 'client', 'Tie', '7d075f169d648523eaa03bb2a98984e48aa65769', FALSE, 'ProfileCard · ResultName')
  , ('1271aee114daa4c4', 'client', 'Tier', '5bd44ebe63cd3b9445ca759f970513d78b28a61c', FALSE, 'NativeUI · BuildCardStatsTab, RefreshCardStats')
  , ('2efb0b0998fa1c5b', 'client', 'Tier {0}', '30dcd8cab0b0f64b3a1ddbd4584ab3fdb4f6c31f', FALSE, 'TitleLaddersUI · PaintTierRow')
  , ('46d56eaebc7647ed', 'client', 'Time in lead', 'ef0fc164f793f689f1d23a5e3130e4b3ed01798b', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('8dce4de87ebefc5b', 'client', 'Time to show them who is the coolest dude around! A pair of glasses that takes up the eye slot', 'f54d4c1fe052a1040ab35be570d899d745e18151', FALSE, 'shop catalog · cosmetic name/description')
  , ('a8e7491399151552', 'client', 'Time''s up - {0} picked automatically.', '698e542479926ac30ba7d470149597aaecb9e425', FALSE, 'FfaMode · FfaLocalPickUI')
  , ('f150f5fc47ef1b43', 'client', 'Timeline', '018514a3d58aa08353dd5e387ee29de45981c409', FALSE, 'SessionReportModel · Build')
  , ('7ebcbde6dbe69280', 'client', 'Times Offered', 'eb04a56fc82f93bea4cf4d1b01baf017e892076b', FALSE, 'NativeUI · TrMetric')
  , ('19f025c8862581ab', 'client', 'Times Picked', '3ab26affbf74ac9caaef9e4f7750b9add285ee67', FALSE, 'NativeUI · TrMetric')
  , ('37e257e16a522c12', 'client', 'Times offered', '997855b1a375e259990a47e51491808528f5295d', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('245a527fbb3a61ff', 'client', 'Times picked (all players)', 'e2993d8a67ea3605c1ca0272e53ca9c159870936', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('f1f232b77a6b7397', 'client', 'Times picked (ranked games only)', '55ca1d6fd64c1aa2b8364c095427f5b23e923720', TRUE, 'NativeUI · BuildCompareCardMetric')
  , ('ec056671a7384f77', 'client', 'Timezone:', '777fcbd0b5a6a370b32741af5ca3cdb45c6a347a', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('e571d7422af03bcb', 'client', 'Titan', '0ce8e5dac8f6f61d3eba42d016f55230f093a2c7', FALSE, 'shop catalog · cosmetic name/description')
  , ('625fff326e96d031', 'client', 'Title Ladders', '863066f5445a625003756fb2fafa070af5117a23', FALSE, 'TitleLaddersUI · BuildShopEntries')
  , ('1ea1bb377fdee4ff', 'client', 'Titles', 'a116f7255e19431f1fbf68cdd9f4dce3b66e6b04', FALSE, 'InfoLibrary, InfoViz, NativeUI · (file scope), BuildVisibilitySeats')
  , ('1ee66467a63c926b', 'client', 'Titles are the short labels that render beside your name across the mod - leaderboard rows, Recent Series, Records, Compare, and every T-chat message you send. You can own any number of them, but only one is active at a time: pick it in the Shop tab with <color=#7FD4FF>Set Active</color>.

<color=#FFD94D><b>CURRENT RANK - FREE FOR EVERYONE</b></color>

<color=#7FD4FF>Current Rank</color> costs 0 gold and sits in the shop for every player. It''s dynamic: wherever it renders, it shows your live 1v1 rank name in that rank''s color, resolved fresh at render time. Rank up and the title upgrades itself; rank down and it follows you there too. The ladder behind it runs 25 rungs, from Beginner I at 0 rating to Grand Master V at 2610.

<color=#FFD94D><b>PODIUM TITLES</b></color>

There are three podium titles, one per ranked ladder: 1v1, 2v2 and FFA. Each is granted the moment you enter that board''s visible top 3, and taken back the moment you fall out of it <color=#8A8A93>(the position check runs on a cached board, so both directions can trail the actual standings by a minute or two)</color>. A board only lists players who have at least one counted series - or, for FFA, one recorded game - so a fresh account can''t hold a podium.

The rendering is the interesting part:

- While you hold a podium spot, the title renders live as <color=#FFD700>1st Place</color>, <color=#C0C0C0>2nd Place</color> or <color=#CD7F32>3rd Place</color> in gold, silver or bronze - always your CURRENT position, with a 1v1, 2v2 or FFA prefix everywhere except that ladder''s own board.
- <color=#FF6666>Off the podium, the title leaves your inventory entirely</color> until you climb back into the top 3. You hold it exactly as long as you hold the spot.

Podium titles never rotate on a schedule and can never be bought. The only way in is the top 3.

<color=#FFD94D><b>SLAYER TITLES</b></color>

Two legendary trophies for beating the names on the door:

<color=#7FD4FF>Sid Slayer</color> - win a completed ranked 1v1 series where Sid is the loser. Renders <color=#FF4655>red</color>.
<color=#7FD4FF>Stan Slayer</color> - win a completed ranked 1v1 series where Stan is the loser. Renders <color=#00E5FF>cyan</color>.

Each arrives attached to its achievement, which also pays <color=#7FE87F>1000 gold</color> (see <color=#7FD4FF>Achievement guide</color>). Taking a single game off them isn''t enough - the series has to complete with you as the winner.

<color=#FFD94D><b>TRANSLATOR TITLES</b></color>

Verified translation work through the translation portal earns three tiers. The unit is a live string: an approved translation where you were the proposer or the reviewer - doing both jobs on the same string still counts once.

<color=#7FD4FF>Rosetta</color> (rare) - 10 live strings. Pays 100 gold.
<color=#7FD4FF>Dragoman</color> (epic) - 100 live strings. Pays 300 gold.
<color=#7FD4FF>Babel</color> (legendary) - 1000 live strings. Pays 1000 gold.

<color=#FFD94D><b>PURCHASED TITLES</b></color>

Regular titles sit in the shop with a gold price and work like any other cosmetic: buy once, own forever, wear it whenever you feel like it.

<color=#FFD94D><b>EQUIPPING AND WHERE TITLES SHOW</b></color>

- Earned titles (podium, slayer, translator) are hidden from the public shop listing, but every one YOU own appears in your own shop view with its Set Active button. <color=#FF6666>Buying them is always refused</color> - earning the moment is the only currency they accept.
- Equipping a new title replaces the old one; titles never stack.
- Titles show on the mod''s own surfaces: the leaderboard, Recent Series, Records, Compare, the stats panels, your T-chat messages (in the title''s color), and the Discord chat bridge.
- Titles do NOT appear on the overhead in-game nametag, and players without the mod never see them - every title surface lives in the mod''s UI or on Discord.', '2d45294cfb5df3152b549d461df19d0ddc8c8414', TRUE, 'InfoLibrary · (file scope)')
  , ('f67bfdc298763ef1', 'client', 'To make a preset an unmodded opponent can see: open the character menu, choose an empty preset, and build the face from base-game eyes, mouths and details only.', '05e759d3a5611e8a350d623c24c145b2c13f3fcc', TRUE, 'AvatarDefaults · RecoveryInstruction')
  , ('beb9cf4cb1f60b03', 'client', 'To pick the best server region for a match, the mod measures your ping to each Photon region and sends the result to the server, where it is kept for at most one hour.', '56506086c6aef29104a57951862e1c8cad6d6759', FALSE, 'CompetitiveUI · DrawConsentModal')
  , ('1bfb571a1da5c088', 'client', 'To {0}', 'a201e92f6e7c9226193bf36b254b541ae72c43fe', FALSE, 'PlayerCardsUI · FillTradeRow, RecentLine, RefreshCompose')
  , ('bf44afebebb3f83a', 'client', 'To: {0}', 'a88aedfc4f2bb81fcbc57c4cf66c266d7fad07c6', FALSE, 'MailUI · PaintComposer')
  , ('6e08c396abf6b6c7', 'client', 'To: {0} and {1} others', '1b4230aae70d4644132b63d836debb79cdaeb608', FALSE, 'MailUI · PaintComposer')
  , ('358e5dcea7fb1153', 'client', 'Today''s free pack is already claimed', '07a7384e5943f8b3ce0ef928ff2d3fe81e58b022', FALSE, 'PlayerCardsUI · ReasonText')
  , ('7f715f49771a9e45', 'client', 'Too Good', 'd8790d3f5d3204300191d3871bab8e4e03d050fc', FALSE, 'shop catalog · cosmetic name/description')
  , ('74ac860db9ea1834', 'client', 'Too many cosmetic changes are already awaiting review', 'c192f783513bf133bd3b17d3029ea9b44511bf4f', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b23a6d6dc64dde43', 'client', 'Too many messages - try again in {0} hours.', 'fd7a242888698ca0f0bcbf366fe4bc6c18f34e71', FALSE, 'MailClient · RateLimitText')
  , ('1a4a2a0320860132', 'client', 'Too many messages - try again in {0} minutes.', 'b4add5d9c65f50ace2999c72928bd14e6613fb85', FALSE, 'MailClient · RateLimitText')
  , ('4eabfc99622a78b2', 'client', 'Too many messages - try again in {0} seconds.', 'f7bc8ed90c03af9250594c0be5bc2443a08fdf5e', FALSE, 'MailClient · RateLimitText')
  , ('a3166b9081b8142a', 'client', 'Too many messages - wait a minute and try again.', '3a10c33de5c861b4c12ad993ccc3038a6c158a64', FALSE, 'MailClient · RateLimitText')
  , ('bb83c24df96aeb64', 'client', 'Too many recipients for one message.', '6f9591653d343912dc73f0b8b4ad276449b5ee51', FALSE, 'MailClient · ErrorDetail')
  , ('e224785f648cafd4', 'client', 'Too many requests at once - wait a few seconds and try again', '27c832cb50f6c0ab3338996d8ebb7bd1bf16fc73', FALSE, 'PlayerCardsUI · ReasonText')
  , ('a231b1ca932802e7', 'client', 'Top Dog', 'a77ff322dbbf723c4f640ec5c0003cf2e528f798', FALSE, 'shop catalog · cosmetic name/description')
  , ('a864fb68e6c542dd', 'client', 'Top Pickers', 'ae6dae198291b6d03a3f1f168f1e35ac35551a54', FALSE, 'NativeUI · TrMetric')
  , ('7c40182849a2b50d', 'client', 'Top Streaks', '2bcded4477fbc29b2189244d26662a863ff2e0e2', FALSE, 'NativeUI · TrMetric')
  , ('027931eb075e1aa4', 'client', 'Top Winners', '6462a1a2c3dc92512ae5dce25012908d66eaea5d', FALSE, 'NativeUI · TrMetric')
  , ('9513c0c659b79924', 'client', 'Top card: {0}', '495b347d5f86ced5aa9fb53e411ee15bbc393293', FALSE, 'PlayerCardsUI · FillTile, ShowCardText')
  , ('0d08c15acf64fc37', 'client', 'Top cards (all modes)', '618c86600676077552bc3fcb0201a11317e768d5', FALSE, 'PostSessionReport · ComposePlayerPanel1v1, ComposePlayerPanelCompact')
  , ('190526c2629dbea2', 'client', 'Top of the food chain', 'e5f48c13ee118dc3dacd8e536d53a9d26f5301df', FALSE, 'shop catalog · cosmetic name/description')
  , ('3c02865780f65b62', 'client', 'Top of the ladder.', 'd7b21694b0fa2964b2ff0945e77b228a3cd15fa4', FALSE, 'TitleLaddersUI · PaintEntry')
  , ('e77878efbc01c8b8', 'client', 'Total Mayhem', '584febf2226943cce895111f9b1ff34d68fa3a3a', FALSE, 'ApiClient · AchievementDefs')
  , ('4829edfbd8946d0c', 'client', 'Total XP', 'de22faa36e05c70dc66d022852845a823e484fe8', FALSE, 'NativeUI · BuildCompareBarChart, TrMetric')
  , ('d72b1daf8080b698', 'client', 'Total time', 'd7da73164c888a7d30e67a3a8c05fbd266ea9fad', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('4602ccfcb6641ef3', 'client', 'Total: {0} ({1}W / {2}L)  <color=#FFD94D>Gold: {3}</color>', '21d10582916e120d4c8320df023f92494b61642c', TRUE, 'NativeUI · RefreshMyStats')
  , ('65459268621110a8', 'client', 'Touch Grass', 'a2c06f13201a8b0dd13595ac4dd0d24a7c4670c6', FALSE, 'ApiClient · AchievementDefs')
  , ('b4587fda5129ecfa', 'client', 'Tournament Bets', '03545bd7eb151a8d59b9ea0fd5a685517c287f12', FALSE, 'NativeUI · ShowTournamentBetsPopup')
  , ('4254217c1c4f7bf9', 'client', 'Tournament in progress - your next match will connect automatically. Keep ROUNDS open.', 'fb10fa9913c39f956d36b21c5e77b85f398b20f2', FALSE, 'CompetitiveUI · DrawTournamentBanner')
  , ('8b0f70cb42c1cda3', 'client', 'Tournament info is refreshing - try again in a moment', 'e3303e8feef02cd0711fbca17db104b380e423c2', FALSE, 'NativeUI · TFencedTournament')
  , ('96c507e94207749f', 'client', 'Tournament match can''t auto-connect: the server has not set a region. Open the Tournaments tab.', '5fe5279bd7d72bd60bd03f4a88338b5faf185e42', FALSE, 'Plugin · GateTournamentRegion')
  , ('ccc921208d9d8ddc', 'client', 'Tournament match found - waiting for the server to pick a region...', '32879284bdafa598c63187724f5bad1b9e124248', FALSE, 'Plugin · GateTournamentRegion')
  , ('b155c9c4df2a3afc', 'client', 'Tournament match starting vs {0}', '88c2dc058427a98557779a76694b97b2196fd0fc', FALSE, 'NativeUI · RefreshTournaments')
  , ('455b205f737f7f07', 'client', 'Tournaments', 'fee20df1963ec9531d0a42884334083687be1d13', FALSE, 'InfoLibrary, NativeUI · (file scope)')
  , ('f76648a14f012b93', 'client', 'Tournaments are 8-16 player double-elimination brackets of best-of-3 series, run end to end by the mod and the bot. There are two kinds: <color=#7FD4FF>Sync</color> (the whole bracket plays out in one sitting) and <color=#7FD4FF>Async</color> (each match has a week to happen). Both are ranked - every game moves your normal 1v1 rating.

<color=#FFD94D><b>THE TWO KINDS</b></color>

<color=#7FD4FF>Sync</color> - weekly. The default start is Saturday at noon Pacific time, but the field votes on the real time: signing up includes marking which start times you can make, from 8 slots at 6-hour steps around the default. The tournament locks 48 hours before the DEFAULT start - the voted time can sit up to a day to either side of it.

<color=#7FD4FF>Async</color> - a new one opens 2 days after the previous one finishes. Signups run for 7 days, then it locks and starts immediately. Every match has a 7-day deadline (check-ins can add a day), so a full bracket takes roughly 6-9 weeks depending on how fast people play.

<color=#FFD94D><b>SIGNING UP</b></color>

- Sign up on the F5 Tournaments tab. A linked Discord account is required - the bot runs everything by DM (see <color=#7FD4FF>The bot & check-ins</color>).

- Sync signups must mark at least one start time. Signing up again replaces your time votes.

- You can un-sign freely during voting. After lock the in-game button closes - withdrawing then happens by answering <b>No</b> on the bot''s availability-check DM. <color=#FF6666>Once the tournament is running you can''t un-sign at all</color> - from there, not showing up is a forfeit and counts on your no-show %.

- The field caps at 16. Signups past the cap become <color=#7FD4FF>speculative</color>: they don''t play, but they are the backfill pool - if a confirmed player leaves before the start, the most reliable speculative inherits their seat. Ordering into the 16 (and out of the pool) goes by no-show % first, then signup time.

- Your <color=#7FD4FF>no-show %</color> is a rolling 90-day measure of tournaments you signed up for and then missed. Old misses fade out over the 90 days.

<color=#FFD94D><b>HOW THE LOCK WORKS</b></color>

- Sync locks 48 hours before the default start. It needs at least 8 confirmed players AND one time slot at least 8 signups (speculatives included) can make; otherwise the whole tournament pushes back one week and your votes carry forward.

- The winning slot becomes the start time. <color=#FF6666>If you didn''t mark the winning slot, your signup is removed</color> - no penalty, and the bot DMs you why. Speculatives promote into the freed seats.

- Sync can also start early: once at least 8 players are in, every confirmed player pressing <color=#7FD4FF>Force Start</color> on the tab within 10 minutes of each other starts the tournament 10 minutes later.

- Async has no time vote - after the 7-day signup window it locks on player count alone and starts right away.

- Locking snapshots the prize pool at the confirmed player count and clears any ranked blocks between participants - signing up opts you in to playing whoever else signed up.

<color=#FFD94D><b>SEEDING AND THE BRACKET</b></color>

- Your seed is your 1v1 rating snapshotted at lock; the highest rating is seed 1. Pairing is standard bracket placement, with seeds 1 and 2 starting in opposite halves. Seed numbers stay hidden until the tournament starts, so nobody can work out their round-1 opponent in advance.

- With 9 to 15 players the bracket is built for 16 and the top seeds get round-1 byes to fill the gap.

- Double elimination in plain terms: lose a winners-bracket match and you drop into the losers bracket; lose there and you''re out. The losers-bracket champion meets the winners-bracket champion in the grand final - and if the losers-bracket champion wins it, one extra deciding match is played, because the winners-bracket champion hadn''t lost a series yet.

- Every match is a best-of-3, played as a normal ranked series.

<color=#FFD94D><b>SYNC PLAY DAY</b></color>

The whole contract is: <color=#7FE87F>have ROUNDS open at the start time - sitting at the main menu is fine.</color> The mod does everything else.

- While ROUNDS runs, the mod pings the server every 20 seconds; you count as present while your last ping is under 2 minutes old. The F5 menu never needs to be open.

- From 15 minutes out you get a reminder DM and an in-game countdown banner; every match-ready moment gets its own DM too (see <color=#7FD4FF>The bot & check-ins</color>).

- When your match is ready and both players are present, the mod connects you automatically - green banner, match-found sound, taskbar flash. If you''re mid-casual-game you get a red banner instead, and the mod pulls you out of that room with no disconnect penalty.

- Matches give a 10-minute show-up grace. If your opponent never joins your room, the mod warns you at 90 seconds and returns you to the menu after 6 minutes - you stay ready, and the server forfeits the match to you if they don''t show.

- Between your matches there''s a 7-minute breather with the next room already prepared. Both players pressing <color=#7FD4FF>Play Now</color> on the Tournaments tab starts it early.

- The server picks each match''s connection region for both players, so you always land in the same room whatever your menu region is set to.

<color=#FFD94D><b>PLAYING AN ASYNC MATCH</b></color>

- When your match goes live the bot DMs both of you with the deadline. There''s no start instant, no auto-connect, and no room code from the bracket.

- Agree a time with your opponent (use /dm-opponent in Discord, or just message them), then play a normal private lobby: main menu, Online, Host Room, and one of you sends the other the 6-character code.

- The result records automatically as long as you both have the mod running with <color=#7FD4FF>Ranked enabled</color> - the server binds the series to your bracket pairing from any room. The mod turns Ranked on for you when a tournament match is live (see <color=#7FD4FF>Deadlines & forfeits</color>).

- In the final 24 hours before the deadline the bot sends a check-in DM; answering that you plan to play today extends the deadline 24 hours, once per opponent.', 'dde2afe15d21de6b5ce4e0a459c84f911313a441', TRUE, 'InfoLibrary · (file scope)')
  , ('64969edef9932b86', 'client', 'Toxic Cloud', 'a667fae512b63902faee00b07f06f45b68f99092', FALSE, 'InfoViz, shop catalog · BuildDotTimeline, cosmetic name/description')
  , ('a056950ff82a33c6', 'client', 'Toxic Spill', '1660bad3f82d6d49f38461bde6cfddfe9830caae', FALSE, 'shop catalog · cosmetic name/description')
  , ('f734b208caa4f204', 'client', 'Tracker', 'c15771fc77a45dae33911c04bb171e6f49fa33cb', FALSE, 'shop catalog · cosmetic name/description')
  , ('127ceae105cad5ec', 'client', 'Tracking & Fair Play', 'c42e9abf5a38ab33401c8bf8760d6a1a2d460ddd', FALSE, 'InfoLibrary · (file scope)')
  , ('4d8297a54d44c901', 'client', 'Trade cancelled', 'ab2bd89b5042ab4cad17df53e8eaa575e7d0b89f', FALSE, 'PlayerCardsUI · RecentLine, TradeAct')
  , ('c224f93cdb5f93fd', 'client', 'Trade completed', 'ff1234bf462e063b944e5d9c3e6d331009f8f0b0', FALSE, 'PlayerCardsUI · RecentLine, TradeAct')
  , ('9e3595f297b7d212', 'client', 'Trade declined', '5c493c829514b1b9ed6f13a3fded429dff89f2e0', FALSE, 'PlayerCardsUI · RecentLine, TradeAct')
  , ('e51799e869e3da1c', 'client', 'Trade expired', '2f37b494d8e9944afd4fb016e81062309606faf8', FALSE, 'PlayerCardsUI · RecentLine')
  , ('7eb36375fb075969', 'client', 'Traded', 'b2d01ab7156cf5a550bd458447ff3bb90b0e72f5', FALSE, 'PlayerCardsUI · PaintTileBadge')
  , ('fc131db5e8ad2624', 'client', 'Trades', '597b1092b35773a3b65fbcb4e6424c2bcc006dd1', FALSE, 'PlayerCardsUI · BuildInto, PaintTradesLabel')
  , ('c355b4603adac37a', 'client', 'Trades today: {0}/{1}', '9b6b7c90f1db518a38962df23d3f9793f2aa2af4', FALSE, 'PlayerCardsUI · RefreshTrades')
  , ('8763d154f95763e2', 'client', 'Trading is not available yet', '90b00c9e64f4d1c7ec577f5c87605e4c49839be1', FALSE, 'PlayerCardsUI · ReasonText, TradeState')
  , ('6aba9a1c34fa3b38', 'client', 'Trading is paused', 'd38068595e1360b938b5afe52e4b647c98abd957', FALSE, 'PlayerCardsUI · ReasonText, TradeState')
  , ('1c5a31cb31fb37f3', 'client', 'Trails', 'abe7e366ae1c1eacb6ef6af9bb1d6c200b03a458', FALSE, 'InfoViz, NativeUI · (file scope), BuildVisibilitySeats')
  , ('9c494c7f25abb2c3', 'client', 'Trans pride colors with particle sparkles.', '502598c638643dedcad27c187b7569ebb08e4615', FALSE, 'shop catalog · cosmetic name/description')
  , ('3836763834fbb27e', 'client', 'Translate SCR (web portal)', 'f5b022a24101fc5adb935f8dd1359ad661f7ea15', FALSE, 'NativeUI · PaintActionRows')
  , ('b5e4bc86afedf812', 'client', 'Translation role revoked.', '68708e68355c1424ba1010b04a7d02bbf94ac448', TRUE, 'NativeUI · BuildAdminTab')
  , ('d55e6921fd41f77c', 'client', 'Trick Shot', '4a4402e6434a346c14dfdf94605528fda018c26d', FALSE, 'shop catalog · cosmetic name/description')
  , ('6f4efddd4bda07b6', 'client', 'Tride', '1599ddb3455a45ccc59a3fac422049947650292b', FALSE, 'shop catalog · cosmetic name/description')
  , ('76c6d1804fba8e34', 'client', 'Trigger Refresh', '073d3d4eea1bed0f0b419a090e46c35cfc72e826', FALSE, 'InfoViz · BuildRefreshFlow, BuildRefreshGate, TextFallback')
  , ('13e7a1792e8abd1e', 'client', 'Tropical teal sinking into deep blue. Two-color gradient.', '35f58c657c654b247ae5592e9450f5a69c96ebff', FALSE, 'shop catalog · cosmetic name/description')
  , ('570c2cdd778837a4', 'client', 'True', '88b33e4e12f75ac8bf792aebde41f1a090f3a612', FALSE, 'InfoViz · SeqTable, SeqText')
  , ('0cab6cacbbc851b9', 'client', 'Tryhard', '0c06f367e6f129656bdd8dd841192a6f4d2dcb57', FALSE, 'shop catalog · cosmetic name/description')
  , ('b35fb4ad612dfe48', 'client', 'Trying, hard.', '05622e2e52c968bbde79af9c43a01a69c348ffd0', FALSE, 'shop catalog · cosmetic name/description')
  , ('98f47de8aadcb4b9', 'client', 'Turtle', '7039da614328dbb74b73091f274ceec249a388f5', FALSE, 'shop catalog · cosmetic name/description')
  , ('6cc40699e7654bdd', 'client', 'Turtle Sage', 'e436d0cdffa15d9704cf39ed30d738d97adb89d1', FALSE, 'shop catalog · cosmetic name/description')
  , ('cd5edd2dfb625384', 'client', 'Twilight', '6caad4cda78d3c6ad47660162f70accf6748494f', FALSE, 'shop catalog · cosmetic name/description')
  , ('2d379480e63e50b0', 'client', 'Twilight Gradient', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', FALSE, 'shop catalog · cosmetic name/description')
  , ('426d72c497d1fb76', 'client', 'Twins!', 'd16e8b753f78e3ec681fc4f9b2778ef39c3809cc', FALSE, 'ApiClient · AchievementDefs')
  , ('a915f28966712ddc', 'client', 'Twisted Topper', 'fe369661beab47e8efc5972a9b686463867affe5', FALSE, 'shop catalog · cosmetic name/description')
  , ('89e56876664535f9', 'client', 'Twitch', 'e8ea5fe2a6a5083495e58e7939264d6fc4a08efe', FALSE, 'NativeUI · BuildPage')
  , ('61bb06cc51843ce1', 'client', 'Two crossed battle standards. For the cause!', 'a9b6b056b13b501af43880063da2ed0de4059f24', FALSE, 'shop catalog · cosmetic name/description')
  , ('fbbce02111ccebf0', 'client', 'Two glowing green feelers. Take me to your leader.', 'fc31465be9e079dfb54cb2d55d591edc83fd4ceb', FALSE, 'shop catalog · cosmetic name/description')
  , ('5e99bccde500db1a', 'client', 'Two teams of two play a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- Random queue uses an Elo band that widens as you wait.
  The server auto-balances the teams.
- Custom lobbies have no Elo band.
  Joining the lobby is consent to play.
- All 4 players have 120 seconds to ready up.
  If time expires, auto-queue players go back to
  searching; a custom lobby is simply released.
- Designed but not live yet: after an auto-queue game
  with a point margin of 3 or more, the weakest winner
  will trade places with the strongest loser. Until
  that ships, teams stay locked all series.

<color=#FFD94D><b>SCORING</b></color>

- The first team to win 2 games wins the series.
- 2v2 uses its own Glicko rating.
  It does not change your 1v1 rating.
- Rating updates after the completed series.
- W-L and WR count completed series, not individual games.

<color=#FFD94D><b>REWARDS</b></color>

- Each game gives 600 base XP.
  A game win gets x1.5, for 900 base XP.
- A series win gives 50 base Gold.
  A series loss gives 25 base Gold.
- The opposing team''s rating tier can multiply base rewards.
- Game XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player''s display name.
<color=#7FD4FF>Rating</color> - The player''s separate 2v2 Glicko rating.
<color=#7FD4FF>W-L</color> - Completed series won and lost.
<color=#7FD4FF>WR</color> - Series wins divided by completed series.
<color=#7FD4FF>Avg Mate Elo</color> - Average rating of past teammates.
  A teammate uses 2v2 rating after 5 completed series.
  Before that, their 1v1 rating is used, or 1500 if absent.
<color=#7FD4FF>Gold</color> - Lifetime Gold earned from 2v2 only.
<color=#7FD4FF>XP</color> - Lifetime XP earned from 2v2 only.
  Gold and XP do not affect your rating-based rank.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.', '9c58c47f379b8af787fea4b478aac44660dcf37a', TRUE, 'ModeInfoText · (file scope)')
  , ('fd3aee43a259e1ee', 'client', 'Tycoon', '1379a85c7654f115f20e9d48fca85582637605d7', FALSE, 'shop catalog · cosmetic name/description')
  , ('a13da205cf3e6b93', 'client', 'Type !link CODE in Discord', 'de6c0edd74bd11469c959c7269b1894c011895fc', FALSE, 'NativeUI · BuildHomeTab')
  , ('248b6c3c08e4d317', 'client', 'Typing channel', '6f038cc9011f8772486e3ecf9af8265a33c6594a', FALSE, 'NativeUI · BuildHomeTab, OpenChatTypingPicker')
  , ('85f536bb36b8ecd0', 'client', 'Typing: {0}  ({1} to change)', 'be2aacc29e7b8ad4f4fe8fbdf09ca250a75e78f3', FALSE, 'NativeUI · RefreshChatLog')
  , ('5e9556fd03d2183f', 'client', 'UNC', '7a9e4183785b69904cb7ed8e647ccd549224f5a4', FALSE, 'PcLabels · Tr')
  , ('f154da60d126569f', 'client', 'UNC' || chr(4) || 'pc.band_short.uncommon', '6eea2b31574ae66e786c908b5c78b6f31a6a05b7', FALSE, 'PcLabels · Tr · pc.band_short.uncommon')
  , ('098f12da49c845cd', 'client', 'UNCOMMON', '3b33f16111a355d3651aaca8bff79ec31e0d054c', FALSE, 'PcLabels · Tr')
  , ('e6bea932bd6381bc', 'client', 'UNCOMMON' || chr(4) || 'pc.band.uncommon', '68dd5059e44ffc61efc6a70955e4317cb973d0b5', FALSE, 'PcLabels · Tr · pc.band.uncommon')
  , ('315bee3c4ca62189', 'client', 'UP', '11a66854c0ed7fd7fbaf5a561663c5dc867c9f19', FALSE, 'NativeUI.Keybinds · KeybindOverlayCap')
  , ('66b1bfa0c7da43ad', 'client', 'Umber', '1255b7d12b59020bccf9dffde6b463bb84d3eedb', FALSE, 'shop catalog · cosmetic name/description')
  , ('ee1a59a01ad44392', 'client', 'Unavailable', '2c9c1f79142df1b66d7a9ed0086592e49c8cf16e', FALSE, 'ApiClient · SpectateReason')
  , ('b72853819816a32d', 'client', 'Unavailable until the game restarts', '7e5925410b95b8d08940c6d0bc28ddc1fa89e808', FALSE, 'MusicEngine · MusicStatusLine')
  , ('5e52fd220fd26006', 'client', 'Unban', 'd2671bfbfdd28d9143047f6a5239296f8a690156', TRUE, 'NativeUI · BuildAdminBanRow')
  , ('7567c90e85adfb18', 'client', 'Unblock', '12aabd251c4213f1cebfe4cb83e6547df55552c3', FALSE, 'NativeUI · GetOrCreateArtistBlockRow')
  , ('4a045cc8b4541843', 'client', 'Unblocked {0}.', '8ee98a7371967a4625215adb4dec48b751251f76', FALSE, 'MailUI · Unblock')
  , ('cb79d154949e23bd', 'client', 'Unbound', '8fbf9c7d0bf57a289957eead4b31d561dfdcd807', FALSE, 'NativeUI.Keybinds · KeybindFace, KeybindKeyName')
  , ('701947c757af5fa3', 'client', 'Unclosed quote — usage: /report "Multi Word Name" [reason]', '6df7395e6a96187a22b6cfc54a7672e0323a6d78', FALSE, 'NativeUI · HandleReportCommand')
  , ('55d6340624531595', 'client', 'Uncommon', '630e0b25835dd27620dc4ef0c6b4d0300696b62f', FALSE, 'NativeUI, PlayerCardsUI, SessionReportModel · Build, RarityLabel, RefreshCardStats')
  , ('277adba289bdb3bc', 'client', 'Uncommon' || chr(4) || 'card rarity', '1b25b1def15facfdbd36fe3ebb0382030e196693', FALSE, 'NativeUI · RefreshCardStats · card rarity')
  , ('09d008b24cde86fb', 'client', 'Undefeated', 'f238736d2617f168f736046f029d91b34c25464c', FALSE, 'shop catalog · cosmetic name/description')
  , ('ef8b357138a3ef69', 'client', 'Underline', '39773aa3efa19090c918baedac1fe737dea25b92', FALSE, 'shop catalog · cosmetic name/description')
  , ('b61b00ae9924cd72', 'client', 'Underworld', '68c5aaeaec955f166f73912d182f66e281c95d95', FALSE, 'shop catalog · cosmetic name/description')
  , ('73b8b301941b6d68', 'client', 'Undying', 'c15be439c086bc750413938337c9d1290d048f20', FALSE, 'shop catalog · cosmetic name/description')
  , ('8130edc9d99316e3', 'client', 'Unequip', '11442128172c9afd9632fadcdf0aa392e5083094', FALSE, 'NativeUI · ApplyShopRow')
  , ('115669d00bdf96b0', 'client', 'Unfocused 120 FPS cap: <color=#88FF88>ON</color>', 'c71884961136003db03094525edbbee7e5da42dc', FALSE, 'NativeUI · PaintCapFps')
  , ('c4e26bdf43287f07', 'client', 'Unfocused 120 FPS cap: <color=#FF9966>OFF</color>', 'c2d1908e08f8d3629bf1f765acdb632a6ddf7b34', FALSE, 'NativeUI · PaintCapFps')
  , ('0db9c0aeaf61a440', 'client', 'Unfocused deep idle (60s): <color=#88FF88>ON</color>', '93f9e18a8aa5cabddfdddc88fec3c5342da056fa', FALSE, 'NativeUI · PaintDeepIdle')
  , ('58fbea629e3fa26a', 'client', 'Unfocused deep idle (60s): <color=#FF9966>OFF</color>', '2f22b1bc82be022594e05b9ce2b5a2246c921b6a', FALSE, 'NativeUI · PaintDeepIdle')
  , ('0d18b8f43d73161e', 'client', 'Unique Players', '874a0591fc04611262fdd744ebec93993dacecc5', FALSE, 'NativeUI · TrMetric')
  , ('3c3c5f6eac20881b', 'client', 'Unity / Game', '1b1d817f13affedf2bc1117a61c3b4ca949b2e62', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('dae179ea3b8774a4', 'client', 'Unknown', 'bc7819b34ff87570745fbe461e36a16f80e562ce', FALSE, 'NativeUI · RefreshCardStats, ShowCardPreview')
  , ('acd99861498c86bc', 'client', 'Unknown' || chr(4) || 'card rarity', 'cba56bc5bb2f58f1481c22801b7fe24b52339b1f', FALSE, 'NativeUI · RefreshCardStats · card rarity')
  , ('cd2c0619969e467e', 'client', 'Unknown player', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', FALSE, 'H2HSummary, ProfileCard · BuildLine, Render')
  , ('cb26de5eb6b8bae9', 'client', 'Unlock chat everywhere', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', FALSE, 'NativeUI · StartChatLockdownFlow')
  , ('292c4b2933ce8fed', 'client', 'Unlocked by achievement, not purchasable', 'cb2751b310d1c126368ac261156c0b15cde9edb2', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('f840a0d158c1b1f7', 'client', 'Unnamed player', '206f671f32f526fd6db1657341434252f2974197', FALSE, 'PcLabels, PlayerCardsUI · FillTradeRow, RecentLine, RefreshCompose +2')
  , ('d53f4a6494e52fc0', 'client', 'Unnamed player' || chr(4) || 'pc.unnamed', 'ed80cf7cf86e1366f48ab88e50ed1ade75ba29f9', FALSE, 'PcLabels · Tr · pc.unnamed')
  , ('1048f83aab6b00f4', 'client', 'Unranked', 'af211a25fedbe2dfeba2058203be09d7de5acda9', TRUE, 'PcLabels · Tr')
  , ('229b71f8adf8e843', 'client', 'Unranked' || chr(4) || 'pc.unranked', '725b885ea6b4ce430456fd6f03e559031f3a1482', TRUE, 'PcLabels · Tr · pc.unranked')
  , ('78624af8fab45ef5', 'client', 'Unranked | {0}W {1}L', '0e9eae5f2e06ce8ede043bbe4a00b514173ab336', TRUE, 'PlayerCardsUI · RankLine')
  , ('5593dbe5ca8039d3', 'client', 'Unstoppable', '39e6741f25d3f45d31f8790ca0b6174dca928597', FALSE, 'ApiClient · AchievementDefs')
  , ('c3ba5409519731c4', 'client', 'Unsupported signature version', '0090cb71340db319cb341ed1ddad35f835f250d4', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('44a291e8d72f6864', 'client', 'Untouchable', '32363366360c0121e17ca2a47b773d8e15bd3bc0', FALSE, 'ApiClient, shop catalog · AchievementDefs, cosmetic name/description')
  , ('9861939095b4ee24', 'client', 'Up Arrow', '5264803fe5fc61032925bb3bf0dab9aa8363939a', FALSE, 'NativeUI.Keybinds · KeybindKeyName')
  , ('ade79993560f1bf0', 'client', 'Update', 'fb91e24fa52d8d2b32937bf04d843f730319a902', FALSE, 'NativeUI · BuildPage')
  , ('fafe22194f8ed4aa', 'client', 'Update available — update through your mod manager', '89716467dcde7378aa43d06eef69031d0d9df6e8', FALSE, 'ApiClient · DoAutoUpdate')
  , ('8c7e9c3d3b46e123', 'client', 'Update downloaded! Close ROUNDS to apply.', '3be557abee2dda3ad206f2e43fd11ca7e1ad1986', FALSE, 'ApiClient · DoAutoUpdate')
  , ('bf1f2179915227a5', 'client', 'Update failed — couldn''t find your installed mod file. Update manually from GitHub.', '99bec94bc84f0b7bfa76f4cf90729acdc10c32aa', FALSE, 'ApiClient · DoAutoUpdate')
  , ('a8d697bbf97db263', 'client', 'Update failed — couldn''t reach GitHub. Check your connection and try again.', '17fa6818aea10b37cf9fbfdd4a24e3f33f9526cb', FALSE, 'ApiClient · DoAutoUpdate')
  , ('87a67ab6de450391', 'client', 'Update failed — couldn''t save the updater. Update manually from GitHub.', '551a4339d7ce4a648c8047eff421de9e2b83d944', FALSE, 'ApiClient · DoAutoUpdate')
  , ('f1a7d88d4ab987b7', 'client', 'Update failed — couldn''t start the updater. Update manually from GitHub.', 'ba7ee6a74491308d3b2c4ef062a67a3f46c8805c', FALSE, 'ApiClient · DoAutoUpdate')
  , ('504938ea1a6af0af', 'client', 'Update failed — that release has no download attached. Update manually from GitHub.', '80045841ca2a8c433297c3f4ba3fa635e6a807db', FALSE, 'ApiClient · DoAutoUpdate')
  , ('464d409e47ac187e', 'client', 'Update failed — the download didn''t finish. Try again.', '0895fbf0cb0205381394acf72281d4c28b6f17d9', FALSE, 'ApiClient · DoAutoUpdate')
  , ('2b15656d65d9b82b', 'client', 'Update required', 'f440d8803b105e07c6b61d2a4e92402a86929b73', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('dcd14e4c10fc12cb', 'client', 'Update the mod first', '48a4d199e3576dd1c613586c028ef6e9b52e94ea', FALSE, 'PlayerCardsUI · ReasonText')
  , ('b7adc58cf20616e9', 'client', 'Update the mod to use mail.', '0b4257d9a89e14f4f46f5f3b21ee5fb370ec1473', FALSE, 'MailClient · ErrorDetail')
  , ('679714879d01cc42', 'client', 'Update the mod to watch this game.', '456115cee506f55cc804f67bb38392aaf846a9e2', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('4998b15922fb8ea2', 'client', 'Updates', 'c76d18079a076ee34ffc62b5b9bd0909da356dce', FALSE, 'RatingGraphAxis · Label')
  , ('7e422ba5e7c33075', 'client', 'Upgrade', 'a6f47e00e036c5589eb12e237894b37fb015d365', FALSE, 'TitleLaddersUI · ActionLabel')
  , ('f21486a74e18c3bb', 'client', 'Upload a Cosmetic...', '7b0543786aca645a0c22d2b047ede094e3ca42c4', FALSE, 'NativeUI · BuildArtistTab')
  , ('f1708fd00756de32', 'client', 'Ursa Major', '94ada68ccf9a1a524b11f12b2a2c7e8011734acd', FALSE, 'shop catalog · cosmetic name/description')
  , ('fa1183ae7a5066c9', 'client', 'Usage: /report [name] [reason]', '22696fce4a6f219c2d5ddd1ee161c0b74cf82250', FALSE, 'NativeUI · HandleReportCommand')
  , ('bf2537cfc9a000af', 'client', 'Usage: /report [name] [reason]  (quote multi-word names: /report "Bad Actor" reason)', '6e902bbd6abba18b61d96350cc916b45c58bf725', FALSE, 'NativeUI · HandleReportCommand')
  , ('b8726a2e1acd9dfe', 'client', 'Use', '1d4d43cc6f3a833e0340a0d1794b6d7b9958657e', FALSE, 'NativeUI, NativeUI.Settings · OpenChatTypingPicker, OpenChatViewPicker, SettingsOpenDropdown')
  , ('23312ec72122ea17', 'client', 'Use vanilla music', 'fc8aa74b208bf96597dfceec0adc76284bd94eab', FALSE, 'NativeUI · BuildMusicTab')
  , ('2862bc6be01046aa', 'client', 'Utility unlocks (e.g. hide your gold total on the leaderboard).', '1b613ddf1549425f05d9b31e4bdd762382c123ec', TRUE, 'NativeUI · SHOP_TAB_DESCS')
  , ('689a1b913ca5b95f', 'client', 'VANILLA GROW: FRAME RATE CHANGES DAMAGE', 'e3b2c4d88bb44675b4d10d5aa3f7a001254164b9', FALSE, 'InfoViz · BuildGrowCurve')
  , ('dbcea9ac17806e03', 'client', 'VOTING / SIGNUPS OPEN', '67e7a92881ae1200be8d73f68942f37d8b841edd', FALSE, 'NativeUI · RefreshTournaments')
  , ('5751014d4ce89a9e', 'client', 'Valid upload_request_id is required', '745d33e62f2847bc0d7fc3102c5df51d7b73900c', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('90a61f96fc8b293a', 'client', 'Vanilla avatar', '5cf3af41da08fc167b42fb2094079570b4d9086b', FALSE, 'NativeUI · BuildSettingsTab')
  , ('e51f835ccadd0f25', 'client', 'Vanilla avatar: <color=#88CCFF>{0}</color>', 'e3274ead58dddc8312649cdc58ed043d9d91ea76', FALSE, 'NativeUI · PaintAvatarVanilla')
  , ('5e7990ce511a1502', 'client', 'Vanilla stays vanilla', '722b8253ed5d9130b7ce842a66865d6780fa4b64', FALSE, 'InfoLibrary · (file scope)')
  , ('e222892ca8d0f4f1', 'client', 'Velvet', '50c8e9195e5ecd5791a33f4dc54310bbea98a77f', FALSE, 'shop catalog · cosmetic name/description')
  , ('496ab005cd8a3b4f', 'client', 'Verified movement tech: the shield edge bounce, wall jumps, and the flying bounce. Every rule on this page comes straight from the game''s code.

<color=#FFD94D><b>THE SHIELD EDGE BOUNCE</b></color>

The arena has a hard kill boundary just off-screen. While you are past it, the game checks you every 0.1 seconds:

- <color=#FF6666>Not blocking:</color> you take a 51-damage lethal hit and an impulse back toward the arena. At 100 HP, two unshielded edge hits kill you.
- <color=#7FE87F>Blocking:</color> no damage at all, and the return impulse is twice as strong. Your old velocity is zeroed first, so the bounce is clean and predictable no matter how fast you were flying out.

The block window is 0.3 seconds and the edge check ticks every 0.1 seconds, so the press can slightly TRAIL your exit and still count. Getting launched off-screen is survivable on demand: block as you cross the edge and you come back harder, for free. In a knockback war this is the difference between a lost point and a return volley.

<color=#FFD94D><b>WALL JUMPS AND JUMP REFRESH</b></color>

- Touching a wall in the air while holding movement INTO it counts as a wall grab. Unless you jumped within the last 0.15 seconds, <color=#7FE87F>a wall touch refreshes ALL of your jumps</color>.
- Pressing jump within 0.1 seconds of a wall touch performs a wall jump: up and away from the wall instead of straight up.
- Ground jumps add extra horizontal push proportional to how fast you were already moving sideways; wall jumps skip that bonus.
- Holding jump keeps adding upward force for a short moment after takeoff - tap for a short hop, hold for full height.
- While hanging close to a wall, your time-in-air counts more slowly for game systems that care about air time.

<color=#FFD94D><b>THE FLYING BOUNCE</b></color>

A hit big enough to set you ''flying'' changes how walls treat you: while flying, hitting map geometry reflects your velocity off the surface, stuns you for 0.2 seconds, and deals a 5-damage self-hit. The reflected launch comes out after a quarter-second hold.

That self-hit is an ordinary blockable hit: <color=#7FE87F>blocking at the moment of wall impact negates the 5 damage</color>.

<color=#FFD94D><b>MYTHS THE CODE SAYS NO TO</b></color>

- <color=#8A8A93>Wall sliding is real, but not where you''d think: pressing into a wall damps your speed a little and keeps resetting the gravity ramp, so you do fall slower - while the stat actually named ''wall grab drag'' does nothing at all.</color>
- <color=#8A8A93>Cards that advertise a self-push on block do nothing on a normal block press - the game''s own block window suppresses the push before it can apply. Do not draft them for movement.</color>

<color=#FFD94D><b>SHIELD CHARGE IS THE REAL BLOCK MOVEMENT</b></color>

Shield Charge launches you along your AIM direction on any block press, and the launch works during your own block window. Hitting a player cancels the launch, damages and knocks them back, and grants a bonus block. It also combos with the wall rules above: charge into a wall, get your jumps refreshed, wall-jump out.', 'ed706f2149025b474c9a6e245bf4a9e6908ecbe6', TRUE, 'InfoLibrary · (file scope)')
  , ('9566e3ebe6920019', 'client', 'View channel', '3cf575503d0141f8791e89998e508076168963e3', FALSE, 'NativeUI · OpenChatViewPicker')
  , ('ce82d9971527a1ab', 'client', 'Viewing: {0}  <color=#888>(press {1} to chat)</color>', '148886cba3727dbad089ca461ee5b43908c03351', FALSE, 'NativeUI · RefreshChatLog')
  , ('bcee8cac3b07a692', 'client', 'Village Idiot', '6bae2b3c94856afdfb389124ba2eef473df23cdf', FALSE, 'shop catalog · cosmetic name/description')
  , ('a7886b3e8ebf0753', 'client', 'Visuals', '0f48a4ccae951aebb1354bd8b48c57bf48dc6a70', FALSE, 'SettingsDescriptors.g · SubTabLabelTr')
  , ('3950da75a154598a', 'client', 'Vivid orange neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', '9a39b423a562fe4943decb524e92851ad0c94a4f', FALSE, 'shop catalog · cosmetic name/description')
  , ('2dca86b596943f57', 'client', 'Void', '207c7c00630b836d3afb46848bdb24a92023331d', FALSE, 'shop catalog · cosmetic name/description')
  , ('4e8fc7c0e6288df8', 'client', 'Void Ripple', 'ec5f447f3fa0edd8c92f7101ef7f729f6466b96d', FALSE, 'shop catalog · cosmetic name/description')
  , ('6023f2dc69b9be58', 'client', 'Voidshot', 'd44941df851133e25121f54f10ddffbc79ed5ed4', FALSE, 'shop catalog · cosmetic name/description')
  , ('0c88e1a2a371e57d', 'client', 'W-L and WR count completed series. XP and Gold accrue per player slot; 1v1 rating never moves.', '9413f2a8d079b061160c6cce7968b08bb38bf16b', TRUE, 'InfoViz · BuildTeamFormat')
  , ('1318e9afd85da213', 'client', 'WALL JUMP', 'f81fae96e119e012ff27043537c33c26f0545e75', FALSE, 'InfoViz · BuildMovementWindow')
  , ('a6d88b76ef5d1086', 'client', 'WATCH', 'f187dbf97ca89e5c15383b3fa7d810b24a33323e', FALSE, 'NativeUI · AddSpectateButton, ApplySpectateLiveRow, CreateFfaBetLobbyRow +1')
  , ('133de46463d0e3ed', 'client', 'WB R{0}', '7bc3e74f332c7c66058d8c0c6f128dffd68b02a1', FALSE, 'NativeUI · TrBracketProgress')
  , ('3c0d5358f8d4d5bf', 'client', 'WHAT EACH SEAT ACTUALLY SEES', 'f0db6799b034ff866597cee74eff4ea14f74175d', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('8242f437f1ba7af8', 'client', 'WHEN A GAME IS RECORDED AND RATED', 'f723884c1a8f207248e9f8bb98e7019a979c9d0f', FALSE, 'InfoViz · BuildWhenCounts')
  , ('d4b6c2192ee2be64', 'client', 'WHERE GOLD COMES FROM', '07a76104d37f51b66843ad75694bac1918b012b0', TRUE, 'InfoViz · BuildGoldSourcesLegend')
  , ('2768f7fef66286bb', 'client', 'WHERE YOUR GOLD HAS COME FROM', 'b1656ecb60391d107bea3e96f0db721368eaba93', TRUE, 'InfoViz · BuildGoldSourcesChart')
  , ('6d56f30dd3dd50f7', 'client', 'WINNERS CHAMP', 'a1f04d4d1e7f99b9139640cf2e9b7fa3a6154903', FALSE, 'InfoViz · BuildBracketFlow')
  , ('b2b856cabfe69155', 'client', 'WINNERS FINAL', 'e466f5b100a24b17e640948976a1fef4fe86681f', FALSE, 'InfoViz · BuildBracketFlow')
  , ('e59b71033ad70521', 'client', 'Waiting for all 3 players to connect — hang tight...', 'f7585ab975d96d0a37f8cb0b66d945ba600cafd2', FALSE, 'GameStateWatcher · PollRoomState')
  , ('30f54024c484dfa7', 'client', 'Waiting for opponent...', 'e9ec8b04b776b9c340c2b12d163577e69c861c8f', FALSE, 'NativeUI · BuildRankedRow, RefreshQueueUI')
  , ('8e2c60cb97779937', 'client', 'Waiting for their answer', '330252c827a516f7381bade01b7ebc95decda50b', FALSE, 'PlayerCardsUI · FillTradeRow')
  , ('b9f70b17a07ec48f', 'client', 'Waiting for your Steam sign-in - Player Cards need it', 'a0a017c5a0cbec55e351653d991c71345a85785c', FALSE, 'PlayerCardsUI · Refresh')
  , ('c2e6d9d121cad78b', 'client', 'Waiting for {0} ({1:F0})...', 'a5213556d4c72afdc8eb34d8c9c1b6854bc20ddd', FALSE, 'NativeUI · RefreshQueueUI')
  , ('a3a01b87cd946688', 'client', 'Waiting for {0} player(s) to connect: {1} s', 'b8890c8a0a9735b3efa2c02ae9c282fba2e4d551', FALSE, 'FfaAssembly · Banner')
  , ('e027d99d19464948', 'client', 'Warlord', '545009b3d84c91b9bd8f30fd2a8efd38bdbc92a9', FALSE, 'shop catalog · cosmetic name/description')
  , ('1a75ea9cccafc189', 'client', 'Warm coral-orange body color.', 'dbe4d86fb51352879c5bc4e9cb3c5823c4ee486c', FALSE, 'shop catalog · cosmetic name/description')
  , ('dd76e64b87e0aa28', 'client', 'Warm cream + tan palette.', '4700ad8692d08573598fbb4950115440b6c1c7ac', FALSE, 'shop catalog · cosmetic name/description')
  , ('c198ec18f335a171', 'client', 'Warm desert sand tones.', '427a3cd1255e088f822589a37ac6636241598de9', FALSE, 'shop catalog · cosmetic name/description')
  , ('05a9b2435b114fb5', 'client', 'Warm honey-gold body color.', 'c148920398c05ff36e4fcbd84d182dc5c3cc1650', TRUE, 'shop catalog · cosmetic name/description')
  , ('e5e3095c005a72cc', 'client', 'Warm orange blocks on a sunset-toned backdrop.', '8b99503fef5328110821262702556cf11f1dc23b', FALSE, 'shop catalog · cosmetic name/description')
  , ('a3c3ed36d90a8308', 'client', 'Warp Speed', '11760707cc84ef3be3f1817190a90ed8b1bda66b', FALSE, 'shop catalog · cosmetic name/description')
  , ('06f3389b4a2b3301', 'client', 'Wear it and earn gold from ranked play', '34a9f062f66c695d3ea74a20d51efef594a52e82', TRUE, 'shop catalog · cosmetic name/description')
  , ('af9bb90b577b28ba', 'client', 'Wear it and finish ranked series', '906ffa46751cdd074664f5106e10545ac1ce1831', TRUE, 'TitleLaddersUI · PaintDrop')
  , ('4be4de2911e669b8', 'client', 'Wear it and lose ranked games', 'd3474293eab66f24dd9733f065826c426bef25c1', TRUE, 'shop catalog · cosmetic name/description')
  , ('5b3214685473fb8f', 'client', 'Wear it and play ranked 1v1 with Bouncy, Ricochet, Mayhem or Trickster', '611fd5e167ab313470c89408908438c2dab73431', TRUE, 'shop catalog · cosmetic name/description')
  , ('206707df42f22d81', 'client', 'Wear it and play ranked 1v1 with Echo, Empower, Shockwave or Supernova', 'f8a2d31ff2e7f21f21241fe24a275327d92c701e', TRUE, 'shop catalog · cosmetic name/description')
  , ('bee886b3b06c07b1', 'client', 'Wear it and play ranked 1v1 with Fast Forward, Chase, Sneaky or Thruster', '67fcf421f563d9335c27975b1f43fb481e12d882', TRUE, 'shop catalog · cosmetic name/description')
  , ('c75eb01b4b2f1ebe', 'client', 'Wear it and play ranked 1v1 with Healing Field, Leech, Lifestealer or Parasite', 'a32aa8b5611d891bdb130bdfc2b617b8833e5fc3', TRUE, 'shop catalog · cosmetic name/description')
  , ('6e9e5f0cdbfa01fa', 'client', 'Wear it and play ranked 1v1 with Homing, Target Bounce or Remote', 'ac557d1f660480d49078da582aecc57138f8cfea', TRUE, 'shop catalog · cosmetic name/description')
  , ('304d5f1451c81e32', 'client', 'Wear it and play ranked 1v1 with Huge, Brawler, Tank, Pristine Perseverance or Defender', '3b63a81cf75dcb25d148459d4b1df47871f8bf1b', TRUE, 'shop catalog · cosmetic name/description')
  , ('043fbd2b8cfcf5b1', 'client', 'Wear it and play ranked 1v1 with Poison, Toxic Cloud or Decay', '1001e4e5123bf942371c914af86c9c213d56d887', TRUE, 'shop catalog · cosmetic name/description')
  , ('71b0f6ef6e866ea1', 'client', 'Wear it and play ranked 1v1 with Quick Reload, Refresh, Scavenger or Tactical Reload', 'e6ecad1c8b403d3683be2e6dc20b2e85f4d68792', TRUE, 'shop catalog · cosmetic name/description')
  , ('7ef64cc96e54fac2', 'client', 'Wear it and play ranked 1v1 with Wind Up, Quick Shot, Fastball or Steady Shot', '5dd208e2ede4194201e1f10553cfb66190aaa068', TRUE, 'shop catalog · cosmetic name/description')
  , ('99ce3a415607b415', 'client', 'Wear it and play ranked games', 'e9391c8c052a7d0cd43ced92c803f91b25fb3e4b', TRUE, 'shop catalog · cosmetic name/description')
  , ('709962aa8394214d', 'client', 'Wear it and win ranked 1v1 after trailing by 5 points', '10fe8c641efb705d4caff27129f31fb1d79ecebb', TRUE, 'shop catalog · cosmetic name/description')
  , ('debf1c1a2471c145', 'client', 'Wear it and win ranked 1v1 conceding 2 points or fewer', '10ee5409611ac9f49f9c73a751479fa129d32324', TRUE, 'shop catalog · cosmetic name/description')
  , ('26ff4a007832b08b', 'client', 'Wear it and win ranked 1v1 games 5-0', '20c72ff0a77089a3fe7be54ee5cacb7ef05d6645', TRUE, 'shop catalog · cosmetic name/description')
  , ('40a897e756b88b3f', 'client', 'Wear it and win ranked 1v1 games in 3:30 or less', '660a836c9cd7c7393cdc256bb3724c51298e7633', TRUE, 'shop catalog · cosmetic name/description')
  , ('df23d5331723a7c6', 'client', 'Wear it and win ranked 1v1 games in a row', '066d85682249ada6e597dea8a36812fcf6df3c53', TRUE, 'shop catalog · cosmetic name/description')
  , ('41aeba0210f6841f', 'client', 'Wear it and win ranked 1v1 with 30% accuracy over 40+ shots', 'b9d6ba3e4316f7e20c9863b847cb9653ff43ca5a', TRUE, 'shop catalog · cosmetic name/description')
  , ('69a15a467a654bc8', 'client', 'Wear it and win ranked games', '4989276cd6983fe206fcd17e925fa59f652ee97c', TRUE, 'shop catalog · cosmetic name/description')
  , ('e05f733dc555566c', 'client', 'Well Wraped Hat', 'eb2d72144a8eb56074736534e4fda9d819d267c0', FALSE, 'shop catalog · cosmetic name/description')
  , ('920dfd8aa0a16e2e', 'client', 'Well played!', '58361b407af345d54448bd228158566a1d188ca7', FALSE, 'QuickChat · Phrases')
  , ('34b4e4fcb0da7041', 'client', 'Wet teal-grey stone walls under an overcast slate sky, rain streaking down the backdrop.', 'dbfa8132673eda37733efbad711f380ae714de0a', FALSE, 'shop catalog · cosmetic name/description')
  , ('5dd73a36dbbf1de3', 'client', 'What each vanilla bug fix does and where it applies. Gating rules are in <color=#7FD4FF>Vanilla stays vanilla</color>: crash guards run everywhere, gameplay changes only where everyone is modded and agreed.

<color=#FFD94D><b>ALWAYS ON - CRASH AND STATE GUARDS</b></color>

These run in every game, quickplay included. None changes a rule: each replaces a crash or a broken state with what the game intended.

<color=#7FD4FF>Frozen inputs, dead Escape</color> - vanilla''s input toggle crashes on a half-spawned player, freezing your keys at match found or permanently killing Escape. The mod skips the half-wired player and carries on.

<color=#7FD4FF>Can''t ready up</color> - vanilla can try to spawn you before the connection has joined a room and leave you with no ready ring. The mod holds the spawn until the room is real; after 30 seconds it returns you to the menu.

<color=#7FD4FF>Dead blocks, silent Shield Charge, invisible Empower</color> - between games, vanilla can tear cards down in the wrong order and leave dead handlers on your block and gun: a block that does nothing, a Shield Charge that never triggers again, an invisible double-damage Empower. The mod scrubs them before every block and at every game and rematch start.

<color=#7FD4FF>Phoenix revive crash</color> - after an FFA leaver, vanilla''s Phoenix looks its revive target up by list position, crashes, and leaves them invisible and unhittable on every screen, forever. The revive now resolves by player ID.

<color=#7FD4FF>One-screen health desync</color> - a sound-engine crash during lifesteal could abort your client''s ENTIRE incoming hit, and ROUNDS never re-syncs health - the two screens then disagreed about your HP forever. The sound failure is swallowed so the damage still lands.

<color=#7FD4FF>Display and audio repairs</color> - a leaver emptying a team no longer freezes everyone on the victory screen; a failed Steam name lookup is retried (15 tries over half a minute) instead of naming you ''PlayerName'' all room; Chase''s card text drops its Health line (vanilla never applies that stat - the card itself is unchanged); leaked sound voices no longer muffle the session; looping sounds (map saws, Abyssal Countdown''s charge) stop when their round ends; plus expiring a leaking radar visual, quieting crown errors, and silencing pure log-noise crashes.

<color=#FFD94D><b>ANY GAME - LOCAL REPAIRS</b></color>

These run in every online room too. Each repairs your screen''s bookkeeping toward what the bullet''s owner already decided - no rule changes, no new disagreements.

<color=#7FD4FF>Spray loses auto-fire</color> - one Demonic Pact poisons every later game in the room: vanilla copies its no-auto-fire flag onto the gun and never clears it, turning Spray click-per-shot. Cleared between games.

<color=#7FD4FF>Invisible Drill bullets</color> - a point-blank Drill bullet could go invisible on the other screen (its effect registered before the bullet finished initializing). The mod snaps it to its true position and re-registers the missing pieces.

<color=#7FD4FF>Poison that lands but does nothing</color> - the same race hit poison: the bullet visibly hits on your screen but no damage follows, because the poison never registered on the remote copy. Re-registered, with a dedupe so it can never register twice for double damage.

<color=#7FD4FF>Round-end phantom kills</color> - poison and burn ticks during the round-won animation could kill mid-transition and award a phantom round. Modded clients ignore damage-over-time and deaths during the transition window; full room-wide protection needs the room''s (usually modded) host seat too.

<color=#7FD4FF>Leftover bullets after the point</color> - vanilla never clears mid-air bullets at a point boundary, so an end-of-round poison bullet could hit you AFTER respawn. Each client now despawns its own bullets at the boundary, via vanilla''s own despawn call.', '0dfd2c2a42475a101ace09e8af90e5a56cf53e0c', FALSE, 'InfoLibrary · (file scope)')
  , ('fc5b6244bdd13c72', 'client', 'What happens when someone doesn''t show up, quits, or leaves a tournament - and exactly how prizes are computed. Short version: <color=#7FE87F>a finished series always stands</color>, absence is what gets punished, and forfeit wins never pay podium prizes.

<color=#FFD94D><b>DEADLINES</b></color>

- Sync: matches give a 10-minute show-up grace from the moment they go ready. A match that follows a PLAYED match sits in a 7-minute breather first (a bye-fed match can go ready immediately), and a match still in its breather can never forfeit anyone. While both players are present the server waits - a sync match can run past its deadline.

- Async: every match, the grand-final reset included, has a 7-day deadline from the moment it goes live. The deadline check-in DM can extend it 24 hours, once per opponent. Presence doesn''t spare an async match - only playing does.

<color=#FFD94D><b>WHEN THE DEADLINE HITS</b></color>

The server resolves an overdue match in this exact order - the first rule that applies decides it:

- 1. <color=#7FE87F>A finished series always stands</color> - nothing overrides a played result.
- 2. If exactly one seat is banned, the other player advances immediately.
- 3. A game reported in the last 45 minutes means a live series - the match is left alone.
- 4. Sync only: both players present - the server keeps waiting.
- 5. Exactly one player present - <color=#FF6666>the absent player forfeits</color> and the present one advances.
- 6. Otherwise: if the series was started and the score is uneven, the score leader advances. Failing that, if exactly one of you answered the async deadline check-in - any answer - that player advances over the silent one. Failing that too, the lower no-show % advances, and a dead tie falls to a fixed arbitrary tiebreak.

Only absent seats get the no-show mark (a banned seat forfeits regardless of presence, and a silent seat can lose the async tiebreaks while present). Your <color=#7FD4FF>no-show %</color> is a rolling 90-day rate that decides your priority into future tournaments, backfill order, and these tiebreaks.

<color=#FFD94D><b>WHAT A FORFEIT DOES - AND DOESN''T</b></color>

- The bracket advances exactly as if the match completed - the winner moves on, the loser drops or is out.

- <color=#FF6666>A forfeit mints nothing.</color> Podium placements only exist for played, completed series - a forfeit-decided podium spot pays no prize.

- No rating moves. Rating only changes when a series completes; a forfeited match''s series is simply never completed or scored.

- Betting closes: a forfeited match''s series can''t be bet on.

<color=#FFD94D><b>LEAVING, AND WHO REPLACES YOU</b></color>

- During voting: un-sign freely.

- After lock, before the start: answering <b>No</b> on the bot''s availability-check DM withdraws you and runs the backfill flow - the most reliable speculative signup takes your exact bracket slot (with their own rating); no speculative available means your would-be opponents get byes. Leaving this way carries no penalty. If you have no answerable DM left, you''re expected to show - a no-show forfeits and counts on your no-show %.

- Once running: you can''t un-sign. Not showing up forfeits your matches and counts on your no-show %.

- Quitting mid-game follows normal 1v1 disconnect rules: the DC lands on your leave %, and unless your opponent was at match point (then they take the game, which can finish the series) the series stays open at its score. The deadline sweep resolves an abandoned series: after the 45-minute grace a still-present opponent wins; if both walked away, the score leader advances.

<color=#FFD94D><b>THE RANKED OVERRIDE</b></color>

- When one of your tournament matches is live and your Ranked toggle is off, the mod flips it ON and tells you. Async matches happen in private lobbies, which only record as ranked when both players have Ranked enabled - the override guarantees your result records.

- <color=#FF6666>It stays ON after the match.</color> There is no auto-revert: turn it off in Settings if you don''t want later games rated. Turning it off between tournament matches gets it flipped back on when your next match goes live.

<color=#FFD94D><b>PRIZES, TROPHIES AND BETTING</b></color>

- The pool scales with the player count snapshotted at lock. At 8 players: 1000 / 600 / 120 Gold and 5000 / 3000 / 150 XP for 1st / 2nd / 3rd. It grows linearly with the field, doubling at 16 players: 2000 / 1200 / 240 Gold and 10000 / 6000 / 300 XP.

- <color=#7FE87F>Prizes pay when the whole bracket completes</color>, not when your final match ends. A forfeit-decided rank is skipped rather than passed down.

- <color=#8A8A93>Prize XP behaves like any other XP: it converts to Gold at the usual 100 XP = 1 Gold, and a level boundary it crosses pays the normal level reward.</color>

- Trophies are Discord roles: SCR Tournament Winner, Runner Up, and 3rd Place; a second same placement upgrades the role to its (x2) version. Every confirmed participant gets the Participant role. Roles only go out for brackets of 16 or more players. Winning or taking 2nd in a tournament also unlocks a paying achievement (separate ones for sync and async), and playing a bracket through without ever forfeiting unlocks Iron Bracket.

- Every tournament game is a normal ranked best-of-3: it moves your regular 1v1 rating whether or not you reach the podium.

- Tournament matches are bettable on the same terms as any live ranked series: betting locks at 2 live points in game 1 or once any game is decided. An async pairing that waits days stays bettable the whole wait at 0-0.', '3960e8a1336364cf16f4a14fde90e1b691431c08', TRUE, 'InfoLibrary · (file scope)')
  , ('9d452a3cc7e4d696', 'client', 'What other players can and cannot see of your mod. The short version is a guarantee: <color=#7FE87F>the only things a non-modded opponent can ever see of the mod are your nametag styling and the quick-chat phrases you choose to send.</color> Quick chat is chat, not a cosmetic - it goes out through the game''s own chat bubble, exactly like a typed message. Everything else either needs the mod on the viewer''s side or never leaves your machine.

<color=#FFD94D><b>WHAT A NON-MODDED OPPONENT SEES</b></color>

<color=#7FD4FF>Nametag styling - visible, with two exceptions below.</color> Formatting (bold, italic, underline, strikethrough, float), solid and neon colors, sizes, caps and spacing transforms, rainbow and the gradients all render on a completely unmodded client. The mechanism: the mod writes the style into your Photon nickname as rich text, and vanilla''s own name labels already render rich text - players were putting raw style tags in their Steam names long before this mod existed. That''s why this one class is allowed to cross.

Two nametag styles are the exception and render mod-side only:

- <color=#7FD4FF>Glows</color> - applied locally on modded screens. A vanilla opponent sees your name without the glow (any other styling you stacked still shows), and no leftover artifact.
- <color=#7FD4FF>Typefaces</color> - a local font swap. A vanilla opponent sees your name in the default font.

Everything else shows a non-modded player nothing:

- <color=#7FD4FF>Face cosmetics</color> - the item ID travels over vanilla''s own face channel, but a vanilla client doesn''t know the ID and renders an EMPTY slot instead. No crash, no fallback item - that slot is bare on their screen, and any vanilla face parts you wear still show normally.
- <color=#7FD4FF>Trails</color> - nothing.
- <color=#7FD4FF>Body colors</color> - they see the default team orange/blue.
- <color=#7FD4FF>Auras</color> - nothing.
- <color=#7FD4FF>Titles, chat styling, Hide Gold</color> - these only exist on mod surfaces (the F5 overlay, T-chat, Discord). Vanilla has no place to show them.

<color=#FFD94D><b>WHAT A MODDED OPPONENT SEES</b></color>

The whole catalog: your face cosmetics render fully (the art ships inside the mod), plus your trail, body color, aura, nametag glow and typeface, and your title on the boards and in chat.

Three caveats:

- Modded viewers can individually opt out of trails, body colors, and animated cosmetics in Settings - your cosmetic renders only for viewers who left those on.
- A body color also becomes your team identity on modded screens: point announcements, the round-counter dots, and the FFA score strip use it. A viewer with that setting off sees plain vanilla teams.
- Titles never appear over your head in-match, for anyone. They render on the F5 boards, in T-chat, and on Discord only.

<color=#FFD94D><b>WHAT NEVER LEAVES YOUR MACHINE</b></color>

- <color=#7FD4FF>Map skins</color> - never networked at all. Nobody sees your map skin, modded or not: every player sees their own equipped skin, or vanilla. Equipping one changes exactly one screen - yours.
- <color=#7FD4FF>Cursor color and shape</color> - your own cursor, on your own screen.

<color=#7FE87F>Your cosmetics never produce a broken visual, an empty rectangle, or a crash on a non-modded screen.</color> <color=#8A8A93>One early glow implementation did leak a visible rectangle to vanilla clients - it was removed for exactly that reason, and glows have rendered mod-side only ever since.</color>', '667404cccb112645b3632eca1c8ed8b4a0c12407', TRUE, 'InfoLibrary · (file scope)')
  , ('1bd91200b53d69fb', 'client', 'What unmodded players see', 'bdc8edc8e6f87a7432574daa3dfd55564ef74fdd', FALSE, 'InfoLibrary · (file scope)')
  , ('9e4688ee7855897b', 'client', 'When a game counts', '82787788a58b2381733c8d8cd22405f47bf7231b', FALSE, 'InfoLibrary · (file scope)')
  , ('a280c4d0e2ff3006', 'client', 'When to press this: {0}', 'c9b599b1367f8a4a2dffa61dc87ab595491b51af', FALSE, 'NativeUI.Settings · SettingsRenderDestructivePane, SettingsRenderPane')
  , ('b0af469852baf260', 'client', 'Where their gold came from', 'b7333d5b1bdacbc317e77f570a617109fb32f3da', TRUE, 'NativeUI · BuildCompareGenericPie')
  , ('411f4757ae88db90', 'client', 'Which channel for {0}?', '6c7e2155b7b8c086656478fb6bd75fa3eb755085', FALSE, 'NativeUI · StartChatMuteFlow')
  , ('b68d2ef723bd1fc8', 'client', 'Which character your picture shows: Follow uses the one you have selected in the character menu, or pin a saved preset. The preview below is what your card will show.', '1e3593aa9e3efe1e5974ee95149a40ae4e03fa07', TRUE, 'PlayerCardsUI · BuildSettingsRows')
  , ('48ab37a3b4f0c7b3', 'client', 'Which language for {0}?', '8f6f68e46a3e45f48d74027000b9b28312ed6fe1', FALSE, 'NativeUI · BuildAdminTab')
  , ('b25a2fb5ec8a68e0', 'client', 'White Cursor', '7afa3cb197e2dfdfb6813dd41d7d5de2c47e7c19', FALSE, 'shop catalog · cosmetic name/description')
  , ('e5988ac9e0383fc1', 'client', 'Who can mail me: <color=#88FF88>Everyone</color>', '1f64f5776b09e9278851caffb89e4f96db612e27', FALSE, 'MailUI · PaintMailFrom')
  , ('bd06028e66d68a8b', 'client', 'Who can mail me: <color=#FF9966>Nobody</color>', '8d0da7eaad5c45b2f590870091cc37062c052a1a', FALSE, 'MailUI · PaintMailFrom')
  , ('4c5dddf9072c1d87', 'client', 'Who can mail me: <color=#FFD94D>People I have played</color>', '4c26a5fb4569b0f70bf12735e201ac8ff2f124e2', FALSE, 'MailUI · PaintMailFrom')
  , ('c855be95c9b870e4', 'client', 'Who may send you in-game mail. Blocked senders never reach you.', '4efa38c1176679a155455493a3340eb9ad0f8b1f', FALSE, 'MailUI · BuildSettingsRow')
  , ('0a2e75ad695d3112', 'client', 'Who picks these cards the most', '7845471d1f67cb530d5de522f234514781b8b9b2', FALSE, 'NativeUI · BuildCompareCardPickers')
  , ('9caebef13ee3df25', 'client', 'Why are they being muted?', 'f7684920539e981571f6a088e2ab56e1cadbf00f', FALSE, 'NativeUI · ChatMuteMsgDuration')
  , ('9afbb108fc3616ee', 'client', 'Why is {0} being muted?', '8f838a7b9a41c37488c3198ef9d9bb91e2882c3e', FALSE, 'NativeUI · StartChatMuteFlow')
  , ('6e56266160067f83', 'client', 'Win', '4973f4c599d5f42cf7bde52d66c3ed8ef77accb1', FALSE, 'ProfileCard · ResultName')
  , ('819c9c1c3c9acf27', 'client', 'Win %', 'a7c9d3c0a5e39ccbb537414aa21bf930c5134232', FALSE, 'NativeUI · BuildCompareNemesisPanel')
  , ('b11e9b8eb932f992', 'client', 'Win 100 casual games in a row', 'a62db852b1d4fd67229d8c1db9abc212214d14f9', FALSE, 'ApiClient · AchievementDefs')
  , ('7878af0d6218e40f', 'client', 'Win 100 ranked series in a row', '2b7036dfd10c1a088708a60f75f3ca0d3c38080c', TRUE, 'ApiClient · AchievementDefs')
  , ('c2080414dc4ad407', 'client', 'Win 200 casual games in a row', '6a83a7c5726697f6747faae9710baf615f3c39fd', FALSE, 'ApiClient · AchievementDefs')
  , ('340a5f64fddafe56', 'client', 'Win 25 ranked series in a row', '2a82cc109e90813127d860437aafeeb22673804e', TRUE, 'ApiClient · AchievementDefs')
  , ('dcea6ed7a205f942', 'client', 'Win 5-0 with Phoenix without losing a life', 'c35aa7a4bc5418558d8050151209b86ec073635d', FALSE, 'ApiClient · AchievementDefs')
  , ('88e636ffe6099863', 'client', 'Win 50 ranked series in a row', '7f8c92d2df2ed7b9d2de661abde38c650a78b757', TRUE, 'ApiClient · AchievementDefs')
  , ('0a1304bbfc6f8b68', 'client', 'Win 500 casual games in a row', '4d2a378dce953a8292d517344fabdca770c713d7', FALSE, 'ApiClient · AchievementDefs')
  , ('498e2111639dc482', 'client', 'Win a 2v2 game 5-0', '52c738eb71779ebebb572ab7101e3ba0c99a061f', FALSE, 'ApiClient · AchievementDefs')
  , ('0a7f9dcfb7f7b30d', 'client', 'Win a game 5-0 with Barrage in your build', '0dc10933da1d6d92074a29c880208de24ac1736a', FALSE, 'ApiClient · AchievementDefs')
  , ('e86c99634581b48f', 'client', 'Win a game 5-0 with Burst in your build', 'a00c23aea46eb757db62174a1007698f8d5679b6', FALSE, 'ApiClient · AchievementDefs')
  , ('3d216c23dff44220', 'client', 'Win a game 5-0 with Explosive Bullet in your build', '0ef4874f3aef9de833424d6a9cef72c32e0f0291', FALSE, 'ApiClient · AchievementDefs')
  , ('7f68781b5d95c2be', 'client', 'Win a game 5-0 with Healing Field in your build', '51684c861757561dafef3e283514ebf103cd7b8f', FALSE, 'ApiClient · AchievementDefs')
  , ('3370f43648b2c0c3', 'client', 'Win a game 5-0 with Spray in your build', '6adaa65a59b1108cebdbaa309fc74aa603c266c8', FALSE, 'ApiClient · AchievementDefs')
  , ('0ab780cd5bee16fd', 'client', 'Win a game after being down 0-3', 'cc461b976cfa54f3f4fc80d112c44227fd752691', FALSE, 'ApiClient · AchievementDefs')
  , ('372406d1b8cd9ace', 'client', 'Win a game without ever jumping', '895f9f6d66f8bad245cd5e1e05e38d7705ea3470', FALSE, 'ApiClient · AchievementDefs')
  , ('7ff5a7c44329fddf', 'client', 'Win a game without firing a single shot', '0d164072c1c67cc0f40de17a0e756df812a9f276', FALSE, 'ApiClient · AchievementDefs')
  , ('903bd2d1530486a8', 'client', 'Win a game without moving or jumping', '7ff9c6a9ec21ae6eee1aa022097cc772d6981aa5', FALSE, 'ApiClient · AchievementDefs')
  , ('154bb996c84705ea', 'client', 'Win a game without taking any damage', '25d565c70ac31cc9a4e68446aefbca42024c1db2', FALSE, 'ApiClient · AchievementDefs')
  , ('530f79859164bfc5', 'client', 'Win a live (sync) tournament', 'b6930ee4436274d073a3d615ae030956e78e7e28', FALSE, 'ApiClient · AchievementDefs')
  , ('81599270ec80413d', 'client', 'Win a ranked FFA 5-0 with 3 or more players who finished the game (nobody else takes a point)', '2208321d2e32a6ef70e8ca6768a862add05eb5f3', TRUE, 'ApiClient · AchievementDefs')
  , ('f3b58e64da9b75e5', 'client', 'Win a ranked FFA 5-0 with 4 or more players who finished the game (nobody else takes a point)', '4a48f06b22127f5f05a5b45cd3da2456c9b0fe3d', TRUE, 'ApiClient · AchievementDefs')
  , ('c8daded48a4c4144', 'client', 'Win a ranked FFA 5-0 with 5 or more players who finished the game (nobody else takes a point)', 'f7a6f23b98545e7cd98d7588148f400981489b85', TRUE, 'ApiClient · AchievementDefs')
  , ('b0bbeabb2c6af5f3', 'client', 'Win after being down 0-4', '098f5df305727f005ed1895b5994020e1cc19406', FALSE, 'ApiClient · AchievementDefs')
  , ('bce06d48a403b9a4', 'client', 'Win against Sid in a ranked series', '1792eca0039ac2d3327c9bf01f4dbca43e48e063', TRUE, 'ApiClient · AchievementDefs')
  , ('23a58ca68c16b593', 'client', 'Win against Stan in a ranked series', '68d423046930d4adf98766d56162de081943e7f8', TRUE, 'ApiClient · AchievementDefs')
  , ('8cd713a42dc28b19', 'client', 'Win an async tournament', '28f7fc6c7106e01bbdbd4bdcdff80262b106c5cc', FALSE, 'ApiClient · AchievementDefs')
  , ('8385611059aa9da2', 'client', 'Win five games 5-0 in a row', '7f852990398165dad77d4ed415dac0e63d4a1149', FALSE, 'ApiClient · AchievementDefs')
  , ('a82a78bd04c6f072', 'client', 'Win rate holding this card', '85c14bca8ee898db2c83eccfda879d9e0447a251', FALSE, 'NativeUI · BuildCompareCardMetric')
  , ('cee62f37b4113baf', 'client', 'Win rate holding this card (ranked games only)', '78c5fbf3c125733d57b79e440509b7494ac71551', TRUE, 'NativeUI · BuildCompareCardMetric')
  , ('feb59a76f97cc1b2', 'client', 'Win taking only the left-most card on every pick, without ever looking at the others', '82e21ae0bb23c7bf1a5dadd5a70daa9e562ab824', FALSE, 'ApiClient · AchievementDefs')
  , ('ac570864590c58d5', 'client', 'Win with Abyssal Countdown as your FIRST pick, activating it every round', '35fce3934da3c301073ba9a0ba73e8eba28a197a', FALSE, 'ApiClient · AchievementDefs')
  , ('ba292685c6b16f5e', 'client', 'Win with Empower and Healing Field together', '061542f4315766fa49452c133d2445cf3c714521', FALSE, 'ApiClient · AchievementDefs')
  , ('beb56c01fc312e7e', 'client', 'Win with Shields Up, exactly 1 ammo, and a lightning-fast reload', '9cc4287e6d1f7c078c8ac963e9cd8f292f0f1f02', FALSE, 'ApiClient · AchievementDefs')
  , ('b0818db3177b092e', 'client', 'Win with Sneaky and Drill together', '1c1206ecc70c025967719deee7ea420f8a770c9d', FALSE, 'ApiClient · AchievementDefs')
  , ('4d87829d1cd53cb7', 'client', 'Win with four copies of the same card', '2c1c7702a7580ec61b8151a66d8ca50c49965c34', FALSE, 'ApiClient · AchievementDefs')
  , ('3a644e4611722c81', 'client', 'Win with two Glass Cannons in your build', '6411369e12cb04569d5e4f57f3eab0cad4248a7f', FALSE, 'ApiClient · AchievementDefs')
  , ('b1bbe5774b2b4dfd', 'client', 'Win with two or more Pristines', 'c53e157e2a81efdacfd391f05f42b4dc1b608a64', FALSE, 'ApiClient · AchievementDefs')
  , ('6066a6cb536f4b96', 'client', 'Win with two or more Saws', '809eb193730a6e60b092ac15cb906006e2d0c47d', FALSE, 'ApiClient · AchievementDefs')
  , ('44817929693030e4', 'client', 'Win with two or more Supernovas', '6309e3b549f2e05f7a832b5a3ceee711e45eb469', FALSE, 'ApiClient · AchievementDefs')
  , ('f8465990452e8309', 'client', 'Win/Loss Record', '297f06ad75081de5ae834632a5e00a251ff00202', FALSE, 'NativeUI · BuildMyStatsTab')
  , ('34d3eb642e9c3172', 'client', 'Wind Up', 'b91321d5ef0293b38ccb6d6bcedb0a1403a64e76', FALSE, 'shop catalog · cosmetic name/description')
  , ('2657ecf2564002d6', 'client', 'Wind up the right arm and take off. Dancing locks your controls for the duration.', 'c3ed4e612af7644a8c04b0bb56878797d9751c8d', FALSE, 'shop catalog · cosmetic name/description')
  , ('d3932de27d2daea3', 'client', 'Windup', 'c0365b235944850932d02480035816faa8e51970', FALSE, 'shop catalog · cosmetic name/description')
  , ('403c28519696a825', 'client', 'Windup main', '7bef0c61f63c0bafbdd397fcdb4fd5388041c31f', FALSE, 'shop catalog · cosmetic name/description')
  , ('8f7d96d5e823b55f', 'client', 'Winners', '1d50bf1d8b44e075c6690ac4d150713976be836d', FALSE, 'NativeUI · RefreshTournaments')
  , ('0ae4685afc299c35', 'client', 'Winners R{0}', '27c75d311287f1efeac29f898a8bed563731cd11', FALSE, 'NativeUI · TrRoundLabel')
  , ('0da8c2b28b8377a5', 'client', 'Wins', 'b6c015d12e1b59bd78fb246985e37730e38521f8', FALSE, 'NativeUI · BuildCardStatsTab, BuildFfaTab, RefreshCardStats +1')
  , ('be9560e3832c8bb9', 'client', 'Wins without firing', '1b48a60b0d625b75c26ce2cf730ff892e74f4114', FALSE, 'shop catalog · cosmetic name/description')
  , ('8c0133547ab53ad0', 'client', 'Wise beyond your years.', '05cb4b22604d22cab8e2fae50a1050c33fa3521a', FALSE, 'shop catalog · cosmetic name/description')
  , ('c7c6e4fba9dcb3c6', 'client', 'Wisps of grey smoke drift off your body.', '6f3c2cb5e1f2e4a068c8389405e3e496e4f9ef97', FALSE, 'shop catalog · cosmetic name/description')
  , ('28f008bfef758548', 'client', 'Wisps of living shadow crown your head. ANIMATED.', '504f4643d13463af8dc37482c5cbe0acc4a75d6b', FALSE, 'shop catalog · cosmetic name/description')
  , ('f9a6b826fb4fcf48', 'client', 'With a linked Discord account, mail also reaches you there while the game is closed, and a reply written from Discord lands back in this inbox.', '9f4886eed410ac6195a103272a6b7794c0bc69c3', FALSE, 'SettingsDescriptors.g · HelpBodyTr')
  , ('96479f1fb8b6533f', 'client', 'Without data consent the mod will not work properly: the leaderboard, ranked matchmaking, chat, player cards and bug reports with logs all stop working.', 'a762f270b7420721b1c971945bf107c5cb370198', TRUE, 'CompetitiveUI · DrawConsentModal')
  , ('2a302e5baecea9de', 'client', 'Won', 'b273fb28770817940a8c1ea6a33b69274996a898', FALSE, 'NativeUI · BuildCompareBarChart')
  , ('be075293da95a629', 'client', 'World Turtle', '1380373170e606619f8309d152aea3408ab593b0', FALSE, 'shop catalog · cosmetic name/description')
  , ('e1dbf69f1828cbc7', 'client', 'Worn by those who climbed the mountain.', 'bca16e3079936dcb4198b1cfc3ffba6610a7e47d', FALSE, 'shop catalog · cosmetic name/description')
  , ('3a86a25f6f851f48', 'client', 'Worst Cards', '7f1deb6a2004a9be435217ff05ec93fbbbabd6e8', FALSE, 'NativeUI · TrMetric')
  , ('4864f47fce10af17', 'client', 'Wraith', '96433896e4e854f2b7b6dd20cbd7f3c2f5164edf', FALSE, 'shop catalog · cosmetic name/description')
  , ('695949eccf2a3eb4', 'client', 'Wrap your name in <b>bold</b>. Stackable with other name styles.', 'c99d12a2a8f36120e482c0fc40e974443dba78bb', FALSE, 'shop catalog · cosmetic name/description')
  , ('ada862d6c0f469e7', 'client', 'Wrap your name in <i>italic</i>. Stackable with other name styles.', '609dfb565c93a98b2b30104355b3a4232da847f4', FALSE, 'shop catalog · cosmetic name/description')
  , ('4635963f683e47cd', 'client', 'Write a message first.', '89da64f4fb77bd76ddec45e4ea6ccb27e52dd8a7', FALSE, 'MailClient, MailUI · ErrorDetail, SendCurrent')
  , ('2ae422d5d897c4cd', 'client', 'Wrong password - try again', 'd46cc0b91a618d588b82c99aabd80674a0044423', FALSE, 'ApiClient · EnrollResult, FfaEnrollResult')
  , ('e0b4ad50d4d4d3b6', 'client', 'Wrong password — try again.', '6703be73dbca5860e567df343a6ee94a965a7cee', FALSE, 'ApiClient · EnrollResult, FfaEnrollResult')
  , ('37343c87c3b2e4f5', 'client', 'XL Name', 'b8c7196ddeefdf59f5ef6da9406d00a866271c3a', FALSE, 'shop catalog · cosmetic name/description')
  , ('eaaf09a6858baeb7', 'client', 'XP per game', '99944bb47be6f4331e20c75e1c4dacbf1e1b900e', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('1e8065936ec534f9', 'client', 'XP this set', 'c8b2140e3bc75cadd867e2b566487e1eb7ed3f38', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('b58acd5e29be1ec7', 'client', 'XP, Gold & levels', '13adb395aafe582e56beeb4950df2212c37ed5c3', TRUE, 'InfoLibrary · (file scope)')
  , ('83036a2c18f9f131', 'client', 'YES', '8fff039853f5c2bbb8a28d056b579c7dcb7d137f', FALSE, 'NativeUI · BuildCompareAchievementGrid')
  , ('e128123d770ddbe2', 'client', 'YOUR CLIENT', '83788d4175517bd358cfab6754397adc8ccb40c5', FALSE, 'InfoViz · BuildReportPipeline')
  , ('93242dc563a40eaa', 'client', 'Yeah', '5bf308cf1d016503a4a74b2849cc00b563192617', FALSE, 'QuickChat · Phrases')
  , ('1256b14cad0e0458', 'client', 'Year/Month/Day', '4eb88001f59d0dff9c3b238ba04dce6e865ae9c1', FALSE, 'NativeUI · PaintDateFormat')
  , ('dcc9b37fdb87b814', 'client', 'Yellow Cursor', 'ee87adceb5e62cb4131c19198f5051250f0d91c2', FALSE, 'shop catalog · cosmetic name/description')
  , ('2c0e445629c0ccdc', 'client', 'Yes', '5397e0583f14f6c88de06b1ef28f460a1fb5b0ae', FALSE, 'FfaReadmit, InfoViz · BuildDamageMatrix, BuildRefreshFlow, BuildRefreshGate +2')
  , ('5ef0b9cf34f0aff2', 'client', 'Yin & Yang', '89ffbc49c5cd513fb7f444af55b747d977cda309', FALSE, 'shop catalog · cosmetic name/description')
  , ('822d0a2200219e04', 'client', 'You', '905cb326c779f0123e079bf8ccb223176a3cf32d', FALSE, 'MailUI · PaintReader')
  , ('1b440804c5f58293', 'client', 'You already have an open trade with that player', '6dedde4e05ca9340f3dfd569fe9233b25728caab', FALSE, 'PlayerCardsUI · ReasonText')
  , ('bd57f21b2e779ae1', 'client', 'You are back in the match', '812fabb8632244503f103b70e66d722740ae855b', FALSE, 'FfaLateEntry, TeamHoldReturn · Finish, OnSelfKept')
  , ('29bd0b648d3d1e87', 'client', 'You are in another queue', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', FALSE, 'FfaReadmit · Refusal')
  , ('050a5b01e285120b', 'client', 'You are muted - mail is unavailable while the mute lasts.', '3116b2c0ca286eb2b0b8f489d30f590d39889ec9', FALSE, 'MailClient · ErrorDetail')
  , ('fd5231aec2abe9c3', 'client', 'You are not in the card pool yet, so there is no card to show - this is your picture.', '61e42e3be6e519b6adc72e9100103d915126c0a3', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('33ce1c7ad84fd592', 'client', 'You can shard up to {0} cards at once', '086119d1f4355c9d7f55053217766af908d7d8da', FALSE, 'PlayerCardsUI · FailShard, OnShardDupesClick, OnShardPackClick +2')
  , ('56cb480415159ed5', 'client', 'You can''t kick yourself.', '721206543a1129dbde968828564469c8dc9920bd', FALSE, 'ApiClient · KickRefusalText')
  , ('d0098e42bc70b57c', 'client', 'You cannot block yourself.', 'bd408e8d9fe13b04edf6829e4dc5f1f9ceba08b4', FALSE, 'MailClient · ErrorDetail')
  , ('d7767f82ff53e075', 'client', 'You cannot trade with yourself', '50f0c8b6609a1de157a2fa66867d91eeee1c3a4d', FALSE, 'PlayerCardsUI · ReasonText')
  , ('204b1b6ea3748c33', 'client', 'You cannot trade yet', '747b31b708dee4a305988f373f830ba3f6601eb6', FALSE, 'PlayerCardsUI · ReasonText')
  , ('86bef07ffd1d0db8', 'client', 'You cannot trade yet - trading needs {0} days with the mod and {1} completed ranked series', 'abe52c128c352093fd3e227044a112ef18b7464b', TRUE, 'PlayerCardsUI · ReasonText')
  , ('ecd655e60930807a', 'client', 'You could not connect in time. No penalty. Queue again when ready.', 'c523be92a13346387596ff6f91bbec6eb94d3d77', TRUE, 'FfaAssembly, Plugin · ExitToast, OnNotice, Update')
  , ('ca67f6bba15bf734', 'client', 'You don''t own any dances yet - check the Shop''s DANCES section!', 'f3dbe5f67e8948cd7dab46f833832ddc3020a155', FALSE, 'CompetitiveUI · DrawDanceWheel')
  , ('ef7d36f6f1419a85', 'client', 'You get', '53eb1352da0ffb51c0ec047f0ef125c909ddaefa', FALSE, 'PlayerCardsUI · BuildCompose, CreateTradeRow, RecentLine')
  , ('6808f5109ab018c8', 'client', 'You give', '0f0c1f054257fa71284ba2949d0b89519086461e', FALSE, 'PlayerCardsUI · BuildCompose, CreateTradeRow, RecentLine')
  , ('c20dcd7b75b273ca', 'client', 'You have made all the trades allowed today - try again after midnight UTC', '4501a63a0939339906230bd509335ec3c7d4bbca', FALSE, 'PlayerCardsUI · ReasonText')
  , ('17781d070b85181e', 'client', 'You have sent all the proposals allowed today - try again after midnight UTC', '2c03ffc19cad63fd29bca0cbc00b01970df05b37', FALSE, 'PlayerCardsUI · ReasonText')
  , ('99e6d1114ba0ad43', 'client', 'You have too many proposals waiting - cancel one first', '3744760206c9232c13785cfc79195ab28de5e25f', FALSE, 'PlayerCardsUI · ReasonText')
  , ('46c115670d7841bd', 'client', 'You joined the match in progress. This game is unrated for you.', '628d45b2a5677a7dbe44d8fa1f6987de0bc8236d', FALSE, 'FfaLateEntry · OnSelfKept')
  , ('98cb664fca411c1c', 'client', 'You left that match', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', FALSE, 'FfaReadmit · Refusal')
  , ('16f2e4dd38463d7b', 'client', 'You should join Competitive Rounds, it''s a discord community', '908c526215debbd4ee1363e3666282a9b9c82697', FALSE, 'QuickChat · Phrases')
  , ('a8064a9ac9627e7d', 'client', 'You show up.', 'bfcb6f0bdfeaee7d87fac66f8d55ddb559b17ec6', FALSE, 'shop catalog · cosmetic name/description')
  , ('6473799d8b6629d5', 'client', 'You two have made all the trades allowed today - try again after midnight UTC', 'a3c31f7b1830ce22f77089520881e878da0a5863', FALSE, 'PlayerCardsUI · ReasonText')
  , ('54b9610f5c99d951', 'client', 'You''re in a game', 'c0c8bdf0b6fe537303ba396b719ae5cf118a35db', FALSE, 'ApiClient · SpectateReason, SpectateReasonExact')
  , ('8491027df4c0bf40', 'client', 'You''re in a live {0} game — finish or leave it first.', '0c37cdb67a8d79b797a1543e2a928ce02dc0c279', FALSE, 'ApiClient · ActionPreflight')
  , ('569b4265e5397abd', 'client', 'YouTube', '558865a16feb9f751b8bcebf46a954afbeba0b24', FALSE, 'NativeUI · BuildPage')
  , ('302286c7bebce02f', 'client', 'Your 2v2 lobby is starting — Ready Up in the 2v2 tab (F5)!', 'ed3eef7baa9af81e1bcad9ad0c5e50e73461bc01', FALSE, 'ApiClient · HandleResolveProbe')
  , ('a6a7046f4bb0c262', 'client', 'Your Block Rate', 'e03e13e5bb0bbe771dbd3eb0a4c64c1e041c0aae', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('8cc6d8d3d47ce7f7', 'client', 'Your Blocks', '0276f6c79774a509341d5391c2d18d92221b2cd4', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('e1430b629fdd11db', 'client', 'Your FFA is already starting — leave it first if you meant to switch.', '474d42f7f1bc7ec4fb3361d3ab3259f46e3e8969', FALSE, 'ApiClient · FfaLobbyActionPreflight')
  , ('c543f55c8141978b', 'client', 'Your FFA lobby closed.', '340d94cdc21e867be6acbc8abc8ef344e8b19f6c', FALSE, 'ApiClient · FfaEnrollResult, UpdateFfaQueuePoll')
  , ('6ecfb3dab02b8467', 'client', 'Your FFA match continued without you - you''ve been removed from it.', '28271452910576a33933fb47d894f1e4d8a6eb87', FALSE, 'ApiClient · UpdateFfaQueuePoll')
  , ('01c1ced9ae420dcb', 'client', 'Your FFA match is still running. Rejoin? {0}', 'a09387a2e372ec9a480465c4d160e094e93a97a9', FALSE, 'FfaReadmit · DrawBar')
  , ('b85e68945bf5ad76', 'client', 'Your Hit Rate', '068fd40efe11d831b1df4bcbec07d05060b33675', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('7ab44213445cb2aa', 'client', 'Your Player Cards settings changed elsewhere - refreshed, try again', 'fafa7a2e2b4157b61a99e0487242b96ddeb7849a', FALSE, 'PlayerCardsUI · ReasonText')
  , ('16540f87011c669f', 'client', 'Your block list is full - unblock someone first.', 'ef6344b64f4741812805f017ac356d6ef622e9f4', FALSE, 'MailClient · ErrorDetail')
  , ('32483a0dfb1f067d', 'client', 'Your card as other players see it.', '5aeaf96140298b59f0239b4647e8270001d22dcc', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('464dc008a1416f5b', 'client', 'Your card could not be loaded right now - it is tried again shortly.', '6e1b2cec7ca0d70ca1d728390444da7c073ecc80', FALSE, 'PlayerCardsUI · SettingsCardView')
  , ('a927cab608d66bbd', 'client', 'Your card trading is off - turn it on in Settings', 'b94232afdb4a102efd75eb9b58b576ef10101454', FALSE, 'PlayerCardsUI · ReasonText')
  , ('0d1b0b03bae1833c', 'client', 'Your controls changed: {0}', '1fe5b3e9abf3ace9ea248656b194e41e3d06ec38', FALSE, 'NativeUI.Keybinds · KeybindChangedToast')
  , ('285d7e4d5c39d2b2', 'client', 'Your game is dropping frames (worst {0} ms)', '586d2a346956f0f867bcd4d3f641fe92cf790371', FALSE, 'LagNotices · LineFor')
  , ('bdef3eab309b6d4f', 'client', 'Your last pack ({0}) - {1}', 'a2e51f8d50cb3129b85e049045e2a25cba2700b0', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('b09ec1965c867d6b', 'client', 'Your match (R{0}{1}): vs <color=#FFDE88>{2}</color>', 'c2c4b1271a540c47e1d7b74f8be6384b8cdc27d6', FALSE, 'NativeUI · RefreshTournaments')
  , ('5ff81c1cbcb1bc7b', 'client', 'Your match is still running. Rejoin? {0}', '3bddba2aa07f0439693aac97861343544b2aa635', FALSE, 'TeamHoldReturn · DrawOffer')
  , ('42457c2a96aab1c1', 'client', 'Your message was removed and you are muted for {0} minutes (auto-moderation).', '71214d59685431088efe8e890fe68b9123c092b3', FALSE, 'NativeUI · OnChatMessage')
  , ('64e8a47541007536', 'client', 'Your name fades from warm amber into deep pink.', '2bbe77e5794acb118c3f9cadfd5a8b5130e9a46d', FALSE, 'shop catalog · cosmetic name/description')
  , ('bd97142ff2899914', 'client', 'Your no-show penalty: <color=#FFCC44>{0}%</color>', '932d39ba6afffe50ecdb9d96f8e9953fc8738c51', TRUE, 'NativeUI · RefreshTournaments')
  , ('9da49dab4e160e9e', 'client', 'Your opponent is banned from the mod - leaving match.', '9928a61ba2ff67208eefea21eb021f851ef71662', TRUE, 'ApiClient · CheckOpponentRanked')
  , ('a6b6ef816a86dfbd', 'client', 'Your opponent never joined. Returning to menu - you stay ready, and the server forfeits the match to you if they don''t show.', '57d3eb1060253f9b1b0ac4f595b7ca7fc35b74f7', TRUE, 'GameStateWatcher · PollRoomState')
  , ('df4b15513b35bf9f', 'client', 'Your pack was opened but its answer could not be read - check your binder', '822b3a2ce6729514ac19e9c6684d928128e11ff8', FALSE, 'PlayerCardsUI · HandleAnswer')
  , ('3d3f357c73935320', 'client', 'Your packs', '8da4806ae9fda2e1398ea936d55ccfba37c2b98e', FALSE, 'PlayerCardsUI · BuildOpenView')
  , ('1d3095cabdbc923a', 'client', 'Your personal breakdown appears here once gold data loads.', '7c8dc31180d2f22bff91272414ca074254e9957e', TRUE, 'InfoViz · BuildGoldSourcesLegend')
  , ('f66df2fe117a9ae1', 'client', 'Your pick missed the cutoff - no card this round.', '81aad0f1de7edc9038fb058738030cd6cadfd48a', FALSE, 'FfaMode · FfaPickPhase')
  , ('9c9228360f345cff', 'client', 'Your picks', 'f8acd4ea8b53c8e63f98ea885d48befcc946b1e1', FALSE, 'CompetitiveUI · DrawCardHoverTooltip')
  , ('458e4de1c2f8d9ab', 'client', 'Your ping to the relay is high ({0} ms)', '4c19162ad3fa67a9827c74dad8dbf9162e282948', FALSE, 'LagNotices · LineFor')
  , ('698827c82f5162bc', 'client', 'Your placements:  <color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(played {3})</color>', '07165fcd109bbf9198d1f39c2f4d6149df178a3c', FALSE, 'NativeUI · RefreshRecentTournamentPlacements')
  , ('633dc1e39f94d3a0', 'client', 'Your placements: <color=#888>no completed tournaments yet</color>', 'a1a912243dc59524cca780830160df18bf83b01c', FALSE, 'NativeUI · RefreshRecentTournamentPlacements')
  , ('0f58f10cbab027e1', 'client', 'Your shield absorbs for exactly 0.3 seconds per press, the absorb decision is made on the SHOOTER''s machine, and a pile of cards ride the block event. This page covers all of it.

<color=#FFD94D><b>WHAT PRESSING BLOCK DOES</b></color>

An off-cooldown block press does three things at once, bullet or no bullet:

- Runs every card effect that rides your block. Shield Charge fires before everything else, then the main chain - Empower charges here, block-heal cards heal here, and block-spawn cards (Frost Slam, Supernova, Teleport) place their effects here.
- Starts the cooldown.
- Arms the absorb window: <color=#7FE87F>your shield absorbs for exactly 0.3 seconds after the press</color>.

Activating and absorbing are separate events. The press always happens; absorption only happens if a bullet reaches you inside the window.

<color=#FFD94D><b>WHAT AN ABSORBED BULLET DOES</b></color>

- It deals no damage, no knockback, no slow, and spawns none of its on-hit effects.
- Its velocity is reversed - it flies straight back the way it came.
- The shooter loses their immunity to it: <color=#7FE87F>a reflected bullet can hit its own shooter</color>.
- Your ''on successful block'' card effects fire - unless the bullet you blocked was one of your own.
- A few special bullets are destroyed on block instead of reflected.

The same window negates almost everything else that can touch you: direct damage, knockback, bullet slow, explosion slow and silence, stun, and poison or burn ticks (see <color=#7FD4FF>Poison & damage over time</color>). A crate or saw that hits your shield is bounced away harder than it would be off your body. Even the arena edge respects it: flying off-screen while blocking costs no damage and launches you back in twice as hard (see <color=#7FD4FF>Movement & shield tech</color>).

<color=#FFD94D><b>COOLDOWN</b></color>

- Base cooldown is 4 seconds. Cards modify it by adding to it or multiplying it.
- The timer runs on game time, so slow-motion moments stretch it in real time.
- The recharge is announced: a reload particle and a sound play the moment your shield is ready again.
- <color=#FF6666>Presses during cooldown do nothing at all</color> - no window, no card effects.

<color=#FFD94D><b>ECHO BLOCKS</b></color>

Cards that grant additional blocks turn one press into a burst: the first block schedules the extras in quick succession, and each echo re-runs the full card chain and re-arms the 0.3 second absorb window <color=#7FE87F>without restarting the cooldown</color>. One press buys a longer stretch of near-continuous cover.

Two wrinkles: card effects can ignore specific block types, and Empower is the one that matters - it charges only from a real press, never from echoes or Shield Charge dashes, and the charge is spent on your next fired shot.

<color=#FFD94D><b>I BLOCKED ON TIME AND STILL GOT HIT</b></color>

The absorb decision is not made on your machine. Every bullet is simulated separately on every player''s PC, and the copy that counts is the shooter''s. When their copy of the bullet reaches you, their game checks their copy of YOUR shield - and that copy only turns on once your press has crossed the network, about half your ping plus half theirs after you pressed. A bullet that reached you on their screen inside that gap is ruled unblocked, the damage is sent as a final number, and nothing on your machine can refuse it. Your shield being visibly up on your screen never enters the decision.

The flip side is symmetric: your bullets are judged on YOUR screen. If your shot connected on your machine, it connects. The full mechanism and the numbers live one article over (see <color=#7FD4FF>Netcode & Photon</color>).

<color=#FFD94D><b>WHAT THE MOD REPAIRS</b></color>

Vanilla ROUNDS has a family of bugs where block dies silently between games: the rematch teardown can destroy card objects half-way, leaving dead ''zombie'' hooks attached to your block. The next game your shield animates and starts its cooldown but absorbs nothing - or basic blocking works while a card effect like Shield Charge never fires again.

The mod sweeps those dead hooks out at every game start, on every rematch, and right before every block executes, and one broken card hook no longer cancels the rest of your block. These repairs run everywhere because they only remove provably dead leftovers - restoring the block vanilla meant you to have, never inventing a new rule. <color=#7FE87F>A non-modded player always gets pure vanilla gameplay</color> (see <color=#7FD4FF>Vanilla stays vanilla</color>). The complete repair list lives in <color=#7FD4FF>Bug fixes the mod ships</color>.', 'f1a69beeabd980c74bf3e17ddd9ae4aeb0a0a681', FALSE, 'InfoLibrary · (file scope)')
  , ('f7e236d85e98d55c', 'client', 'Your vanilla avatar preset has items an unmodded player cannot see, so your avatar was not switched.', '307824db5a062f3c19de1e0ac6c57754439361b6', TRUE, 'AvatarDefaults · UnusableMessage')
  , ('58e458bc36b5ce5d', 'client', 'Your view starts at the next round - that is the first moment the score, cards and health can be shown correctly.', '7762d72ce7bf49fc4b449858f0e7cda036a17301', FALSE, 'SpectatorHud · DrawBlackout')
  , ('37545b9a9e7d68d5', 'client', 'Your {0} lobby closed.', 'a579e85fe77434bad2e5c6b95c5d6f7f3e165040', FALSE, 'ApiClient · EnrollResult, HandleResolveProbe')
  , ('48c9d127e51bbf72', 'client', 'Your {0} lobby seat expired — join or create a new one.', 'bcece8c6a3f5cadce3449b5db2ac668778dcaf13', FALSE, 'ApiClient · HandleSeatExpired')
  , ('66971b4f85c68794', 'client', 'a dance is your own choice; None keeps the card still', '8a2d5a6b289df05a8217712007b5b9678a9844ff', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('caa69845c819c00e', 'client', 'a debugging overlay, not a HUD', '52f43e28df0c1fea90c01c2a7c161fc6f3fe6f08', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('64dc51615fc974c9', 'client', 'a person makes the call', 'f8dfbbe866f95cc4ec4b4480ee1ecaf3956c6a33', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('1f04befd14871e1b', 'client', 'a picture choice has no right answer', 'ad8cd1ecad408c191de6727c9f2f2f776b1abae6', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('85ef80364c159655', 'client', 'a pot scaled by lobby size, battles and opponent tier, split by placement', 'fc051e48bec64b6c5b9f5f7a8795c8c9e4f9c7eb', FALSE, 'InfoViz · BuildGoldSourcesLegend')
  , ('bf4ae830222e69d8', 'client', 'a year ago', '2e8849fcb4982de44770ca02f39c8751143b02c2', FALSE, 'H2HSummary · Ago')
  , ('ecee43db04e473cc', 'client', 'absorbs everything', '984d0e19218e75b60f1a78f14bcdd2f6ce92af7d', FALSE, 'InfoViz · BuildBlockWindow')
  , ('0bd87dd08a40ab2c', 'client', 'advanced', 'e62854369199d65b6a66cd90fe8203ac4d5be26c', FALSE, 'NativeUI · TrBracketProgress')
  , ('6ea3113de6680882', 'client', 'after a handful of series', '47899b0bf8c2b9dd3fd5ee49700c77ed0d8f56a2', FALSE, 'InfoViz · BuildGlickoRd')
  , ('f96d89a65de6bc21', 'client', 'also locks when any game is decided', 'd8010d74929ce9a0815f1768239e5630c11eea1e', FALSE, 'InfoViz · BuildBetWindow')
  , ('6743a3837d3b1790', 'client', 'always earns x1.5 pay', 'ca0de51d37da52488bbe822980c08e8f4b54ea66', FALSE, 'InfoViz · BuildOvtFormat')
  , ('f8911a22f310a60e', 'client', 'an empty slot - no crash, no fallback', '9c22dec522b1a7430c72799f83d17ab2283012af', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('1e2ea23b5080c65d', 'client', 'anim_fps must be 0.5-15', '593f9a1d86c1818cf98d78d072a134cae66ff1a7', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('58ee2b908906df35', 'client', 'any moment now', 'c148b7d5a3359c89b5accd4d542783d6e39a0cc7', FALSE, 'NativeUI · RefreshTeamTab')
  , ('0f65b4dfb83ff4a3', 'client', 'any preset; this is the one you wear everywhere else', 'db480f6051fd1c85fae2c92d8c0ace34ea6c3251', TRUE, 'SettingsDescriptors.g · ReasonTr')
  , ('4dc02aabf266cbc2', 'client', 'applies only when everyone in the room agrees', '7b1d45a11485f18f38049d31aed0611afa427cc8', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('cf2430fb314a3447', 'client', 'applying a language rebuilds the page, so it cannot be part of one atomic bulk write; press this row to apply the detected id', '34e037d5352a3cd0e5fc03a4c297b48ff40f6a6d', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('d6b2086f3537ac5a', 'client', 'art submitted in-game', '51965c0404a0449c99b8e16f493f6b7c5bd1ec18', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('1931b64f5776ffe6', 'client', 'artist sets price + stock', 'ec27f4e8a660e892b1e898de326c873c402f9da8', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('149bf365c330d13c', 'client', 'as DUO (w/ {0}) vs {1}', '8833ad12d379ff3fa61c32bb9e943d7b06b5856d', FALSE, 'NativeUI · BuildPlayerModeHistoryText')
  , ('0aa6a16a1673de73', 'client', 'as SOLO vs {0} + {1}', '1bd88366f34ba7f14fb904e5ed1646c4644328cc', FALSE, 'NativeUI · BuildPlayerModeHistoryText')
  , ('87fcd616bdd6fcd8', 'client', 'assigned by the server', '8b665bae87464c9df3296fae2077214efc5ab31a', FALSE, 'InfoViz · BuildOvtFormat')
  , ('897cd9f9f0988cbc', 'client', 'bad frame PNG: {0}', 'b1fae58e612a85748a0f50ca56ef757201ad0b26', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('f95da11526f422b8', 'client', 'base game', 'd4935ba458a53152ac538277ca378c07b264d9f2', FALSE, 'InfoViz · BuildKeyboard')
  , ('3632263954867005', 'client', 'before asking in Discord', '30cb48da002c0263d1db7bc890437137a9bade3e', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('15f05013486c4b64', 'client', 'blocked senders never reach you anyway', '0d3dc2fcafd63a4cae2dce400c8c7b3096ba9e8c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('a9260e7026739931', 'client', 'blocking: 0 damage + 2x return impulse', '83e43e66b11a38d83ba77abdfad13d330f58e224', FALSE, 'InfoViz · BuildMovementWindow')
  , ('0fee8e919c17a19d', 'client', 'both', 'fc39b18f287d8bbfaceae020f4a4eb32ac5c1e70', FALSE, 'InfoViz · BuildKeyboard')
  , ('a662402c35b6f0bf', 'client', 'both Ranked', '58632221da3c855ed9e898cb8e3496ec9c4a261e', TRUE, 'InfoViz · BuildWhenCounts')
  , ('fde13d6dfeb98727', 'client', 'bought with gold', '9e28e613531564839fab0948ad65be8240edde78', TRUE, 'PlayerCardsUI · PackSourceLabel')
  , ('f6a1adbc04a6cdf5', 'client', 'bought with shards', '576eab9ec531aff8936743e561e09e9f24322eb2', FALSE, 'PlayerCardsUI · PackSourceLabel')
  , ('dbfcf5cb5e976351', 'client', 'brand new (+/- 350)', '81dc80bb5cad62384352a74489b0ad8f36a90d30', FALSE, 'InfoViz · BuildGlickoRd')
  , ('1928b19204130de1', 'client', 'bundled into the mod', 'b0b19f7da5a641c8cd96fdb91d53b19ae2d2e36b', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('a7fcf02867fbd4d7', 'client', 'by hit %, block %, ranked DPS, keys/sec and build-type mix', '651f6d70cd3ed3c066cebcf7be52166bbfa8091d', TRUE, 'NativeUI · BuildCompareSimilarPanel')
  , ('a952b80387530503', 'client', 'can''t be altered in transit', '02947f4f39f84289021e16e1b6436a5e33a0b16c', FALSE, 'InfoViz · BuildReportPipeline')
  , ('d2fd8dbf24d79c16', 'client', 'cancelling costs nothing and re-arms cleanly', '6432091ddfc1dabd32ea56353cbebbfc5d00137e', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('78e9e5d12627a6b8', 'client', 'card cap {0}', 'c9cdc8df661d6d05e10abb81d1e2474b641699f1', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('fe4a63da748dfc1e', 'client', 'casual', '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', FALSE, 'PostSessionReport · ComposeFfa, GameLine1')
  , ('c952a39f8d2c92f3', 'client', 'casual FFA and 1v2 = recorded, not rated', 'd4e4e53c827126fca1c39f8ee242bc7e1857b9a7', FALSE, 'InfoViz · BuildWhenCounts')
  , ('5b5576e89a0dc32c', 'client', 'chat muted: {0}', 'f2d2f8cbf273a81020233acc930b363dd373e5c9', FALSE, 'CompetitiveUI · MutedPlayersLine')
  , ('7d87487feb28d27d', 'client', 'chat muted: {0} and {1} more', '8ab345f9f512c744baa145d36832807d535fa0a8', FALSE, 'CompetitiveUI · MutedPlayersLine')
  , ('dbf4faef919486db', 'client', 'cleared - flags alone never punish', '85b95acdb74387a141ac27ee0aa79640ecfdfb13', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('5e2f844126994bca', 'client', 'click Preview again to stop', '16f5853cbde985dccf1dea304da084cc7b21813c', FALSE, 'CompetitiveUI · DrawDancePreview')
  , ('ec58935c8e62aad7', 'client', 'click a phrase - Esc closes', '1a2420720ae16deb2834e7dcc92b8fa67fdf8c8f', FALSE, 'CompetitiveUI · DrawQuickChat')
  , ('0f5f1b1f46107a34', 'client', 'click to close', '91960f92069cca3cfe3fa8c85263b2d73280c7d9', FALSE, 'TitleLaddersUI · PaintEntry')
  , ('1f906dd204f11211', 'client', 'color', '6dd0fe8001145bec4a12d0e22da711c4970d000b', FALSE, 'NativeUI · TrKindWord')
  , ('e1057c640d9c18b6', 'client', 'common', '94c8c21d08740f5da9eaa38d1f175c592692f0d1', FALSE, 'NativeUI · TrRarity')
  , ('f81f26ce4b5af021', 'client', 'competitive clock: 120 FPS', 'f89dbad40ddd7997cc2643ea0dd31f5156b2c380', FALSE, 'InfoViz · BuildGrowCurve')
  , ('99c7f1983a568f7e', 'client', 'confirmed - admin tools: ban, reversal', '05599a662494b836496c17e39d7810966b42c27b', TRUE, 'InfoViz · BuildAnticheatPipeline')
  , ('9b4017b6bd758b09', 'client', 'consent is the player''s own decision, never bulk-written', 'eae8fb4905da9f4423de1a11eede2917d134b484', TRUE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('ecc58e271f42be14', 'client', 'converted frame {0} is {1} KB — the per-image limit is {2} KB. Simplify the art or reduce its colour count.', 'fe6276c7974d4b520ef5345d8b21e91602f37eeb', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('655530026039087e', 'client', 'cosmetic only', 'e6661c75c7cd3bbc2c4969714ebe9f1ab521f2b0', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('608d364ad4b7b31d', 'client', 'could not process GIF: {0}', 'f250a0eee4006971e164d25b14c5dbae3a149972', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b21c41222533d93c', 'client', 'cursor color', '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', FALSE, 'NativeUI · TrKindWord')
  , ('0cd2498ace5eb5b1', 'client', 'custom 2v2 lobby', 'd317f861f54f6c4a8fd4dac6ff0efcea37ec2e1d', FALSE, 'NativeUI · RefreshTeamTab')
  , ('cc72dae7e378ae92', 'client', 'date ->', 'bbe8e50ce0d4d8b4bd3623810d2f59ade4778727', FALSE, 'RatingGraphAxis · Caption')
  , ('0c9d1a4a99b9465b', 'client', 'days since first rating update ->', '141d8664db867feb557c919b90eac6b3dc23ab84', FALSE, 'RatingGraphAxis · Caption')
  , ('2432c9ac4a936b82', 'client', 'default', '7505d64a54e061b7acd54ccd58b49dc43500b635', FALSE, 'NativeUI · BuildTournamentsTab')
  , ('13b5e24f84f0ed66', 'client', 'default orange / blue', 'a7eaf6bc6f5bfd2e69d581a14dda0fd9d27bbc20', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('827f844cab215227', 'client', 'dimmed: rolled out of the build', '38238831b07e80bca8d80f8e86ae0aed5ef368f4', FALSE, 'SessionReportModel · Build')
  , ('2b4173329e12fc5c', 'client', 'discarding...', 'c25b5ae851ef94a712e1e959666badc32ebcc288', FALSE, 'PlayerCardsUI · RefreshBinder')
  , ('1bd56f0d3fbd9153', 'client', 'discord.gg/comp-rounds', '2452413e142aae220bf50fbfa426f638b7816ce4', FALSE, 'QuickChat · Phrases')
  , ('622d1aecdaadf508', 'client', 'dmg', '7ff9ab96af63157f5eb7ba53993ddb4cb0fe8079', FALSE, 'SessionReportModel · Build, BuildTotalsPages')
  , ('e84b62487348bc8f', 'client', 'dmg/s', '28ac0476b5890ad8e1cab72ee2faf0155c4799cb', FALSE, 'SessionReportModel · Build')
  , ('6b44e02890ead855', 'client', 'does not trigger', 'fdeeaaea73befff1c3f2418cccbbd1dc09d4f6e3', FALSE, 'InfoViz · BuildDamageMatrix')
  , ('57d6cc8fbd1ceb65', 'client', 'double forfeit', 'eb73bf2d20362f847999941af75cd7d0392e5e9c', TRUE, 'NativeUI · RefreshTournaments')
  , ('567d2c353e31dfc1', 'client', 'draft restored', 'ee58b8dc38927dddce94c7e953b5dcb41a5e559b', FALSE, 'CompetitiveUI · DrawChatInput')
  , ('6600871667ff3f3f', 'client', 'drafts are machine-translated until reviewed, and English is always complete', '29799778c71699702f0505db5af247ded3d14d31', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('bd6d31d0b058348d', 'client', 'duo', '16ef1d431149d2a08902873a443dbbe54c85cddb', FALSE, 'NativeUI · RefreshOneVTwoTab')
  , ('db1c0f8507f229d7', 'client', 'duo: the whole right half', 'b8daf3245d0bb316337366d100c95c7e657c362f', FALSE, 'InfoViz · BuildOvtFormat')
  , ('dd2445017b5ffa41', 'client', 'earn gold by playing', 'f1fbdca78de260855c81cbd171d9379eb4c1394a', TRUE, 'InfoViz · BuildCosmeticsFlow')
  , ('0eeafe13444eadc0', 'client', 'earned - ranked win', '437ad83a07a9f0651adfcc04bac69d0f72e170d2', TRUE, 'PlayerCardsUI · PackSourceLabel')
  , ('1c965c61e0820139', 'client', 'earned - sweep', '0dc378086ca9226f24fff6a581a3a8c7b9cef334', FALSE, 'PlayerCardsUI · PackSourceLabel')
  , ('49365749c7b1c2de', 'client', 'edge check: 0.1s; block window: 0.3s', '60c988b15337b0f7139c96ec178e4dc424949c85', FALSE, 'InfoViz · BuildMovementWindow')
  , ('a9a22f4ebe81cc18', 'client', 'eliminated GF Reset R{0}', '35c786c8d69dc9b6e1b0585dab12a3a935b6eec1', TRUE, 'NativeUI · TrBracketProgress')
  , ('611bd0298e4bd918', 'client', 'eliminated GF R{0}', '3e939ba84b1ce4f469134097a48f00df1970ec2d', FALSE, 'NativeUI · TrBracketProgress')
  , ('1ddaf4e2acd1df55', 'client', 'eliminated LB R{0}', '6051781ea72ce471137b5e9d4120f00d97dc0200', FALSE, 'NativeUI · TrBracketProgress')
  , ('ec348a5400155f57', 'client', 'eliminated TP R{0}', 'f237708222f0d8732b127e02086bd73c13a3c25a', FALSE, 'NativeUI · TrBracketProgress')
  , ('d1a39a168846c694', 'client', 'eliminated WB R{0}', '5c423ae5079ae44d36cdb0b173848cf53a4dcf35', FALSE, 'NativeUI · TrBracketProgress')
  , ('87c6e8bf8e7ae780', 'client', 'enabled?', 'b896146b87f9453da24ac71dee61c5e301b13a6a', FALSE, 'InfoViz · BuildWhenCounts')
  , ('73384d8d31140e09', 'client', 'epic', '31fe23de06e7a9e05684f021f52cfc0e2832c19d', FALSE, 'NativeUI · TrRarity')
  , ('c372037f23bf8282', 'client', 'events and streamed state', '95a3328110c7692a26084ccda18cf878c13df0d3', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('3a0f1f521d0087b1', 'client', 'every 5 levels: 100g, then 500g past level 50', 'a360cd1a4517c555248721ed7c005b0978680c08', FALSE, 'InfoViz · BuildGoldSourcesLegend')
  , ('fe155ed1d897c0ce', 'client', 'everything, glow and typeface included', 'ac7d200fa1ec6ce18c2d700dbaef2f32e2a9efa4', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('066f351f496a5f39', 'client', 'expected_price_required', 'fce2cc01c372646609e04c94cbeadba3e2e61277', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b1106ea1ec6e7b1e', 'client', 'expired', '45a6f9adb1df3a78aafc71391c7d3bfa7680229b', FALSE, 'ApiClient · UpdateQueuePoll')
  , ('65b696f2c39bd5da', 'client', 'face', '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', FALSE, 'NativeUI · TrKindWord')
  , ('73fdcc5f35928195', 'client', 'final 24h check-in', '9a9f207e68bab4a7126b9ec05121eecc23a57a4b', FALSE, 'InfoViz · BuildForfeitClock')
  , ('53c4654c16ccc2d1', 'client', 'finished series: result stands', '538071b476b87fe12f052546400549b2e321210c', FALSE, 'InfoViz · BuildForfeitClock')
  , ('af192920f8bd310e', 'client', 'first team to 2 games', 'f48902bd433ae6ef4d653cc3eff2ed4d03a50591', FALSE, 'InfoViz · BuildTeamFormat')
  , ('9240c6f8bf4ffaf7', 'client', 'first to {0}', '3a47aeacaf0654f2611e9a1ccdd01ff81afb6aeb', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('2d9ea9902f3f8cbc', 'client', 'follows the character you actually play', '2f085869430294653d0373bce3e46b3658594a55', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('6c9656a1c0649133', 'client', 'for streams and for spotting missed inputs', '16f5a1fcc18ac38828de9ab5beeed832a3395480', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('74de101558f02d2f', 'client', 'forbidden', '5854a82bc4373373f08e11b4ba52e373bc3ccdc7', FALSE, 'ServerTextRules · TrMiddleware')
  , ('9df9f251777c0b73', 'client', 'forfeit', 'db2c164b2807ad45e39f6681f4bcd30e8a151225', TRUE, 'NativeUI · RefreshTournaments')
  , ('a8a84cc00a76ea0f', 'client', 'fps', 'ee4c907f5db26515b9abd64046331b63a0d445e5', FALSE, 'SessionReportModel · Build')
  , ('f7ebce26adf69e67', 'client', 'frame PNG missing or too large', '8b0cfbfdc18dac66e604333c28f0beae13c77b44', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1a0298c36dd4cfda', 'client', 'frame png_base64 is not valid base64', 'bec46b5a0ff2f331254565430e511e56ce08aedf', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('9afe7f5321da1d99', 'client', 'frame_count must be 2-{0}', '0e6e6b2f0ef22e24c0d6f8cbf98b2041ece6dd92', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b3d306dfe7756ace', 'client', 'frame_no must be 2-{0}', '742459d71ad2b37cdb16842717b8fbaaadb51147', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('d0ef691cec78bdbb', 'client', 'frames_hash must be sha256 hex', '317e60f21d8470f1afb1ce93aea0739f62775bd9', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('f1a40a0e8692e70f', 'client', 'free daily pack', '8ad878e07d7aa5a970e57a5a43f01783d151ac88', FALSE, 'PlayerCardsUI · PackSourceLabel')
  , ('c0a0607f3e2d6394', 'client', 'game 1 starts', '3eaf750e8d8107db4ca83f8176b53e0e3a3e30e4', FALSE, 'InfoViz · BuildBetWindow')
  , ('8e55c28baa95c60c', 'client', 'game in last 45 min: wait', '94658d7c8c878f44e18d73f9c8affbfa3f8aa94f', FALSE, 'InfoViz · BuildForfeitClock')
  , ('f3d6ba57b5fb6eaf', 'client', 'game server relay', '9752a30de8b8b560ac88841e9d20469390e55604', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('db229afb121a7c98', 'client', 'game {0}', 'ea40b74c910ba3a15a95232156618a2f3a6c06d9', FALSE, 'ServerTextRules, SessionReportModel · BetScore, BuildTotalsPages')
  , ('ead52802db829ad0', 'client', 'gif_base64 is not valid base64', 'b0e0a71904e5fd4d257940a56253637b9af6dd70', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8245ac00aeeb8a39', 'client', 'gif_processing_unavailable', '34ed5a04ff0fd5466210dc9da3e22ce0d8c4757a', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('a7275d92b5c01840', 'client', 'gold', '09feb137fd5e58ac9131bff6c66ba2e70260bf8c', TRUE, 'SessionReportModel · BuildTotalsPages')
  , ('d64fd3c88730b97b', 'client', 'host-only, and it despawns real bullets', '1aa265d6c1851afb488f7414987830794f095ded', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('2cb03ccea2e7dfe3', 'client', 'image_processing_unavailable', '411d20fc899fa4c8988b74cc2cfcdb37a154987b', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b652886c9f750c58', 'client', 'impossibly fast series', '8358d9cff2953c92267bb21092fff91232279340', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('1c5fa6b4e8f76ca5', 'client', 'internal_key_required', 'a2e76ec54573988be95f60db82c0427738b4bf88', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('66f0a10fe77a4874', 'client', 'invalidated outright, gold and XP reversed', 'd90a22c31ec7bdaf4e9f528f58c63a30ac020e29', TRUE, 'InfoViz · BuildAnticheatPipeline')
  , ('8156d646ed5d3762', 'client', 'is elected reporter', 'bc85baafd8bb80ab1dbe6764cb0d771feba2fe72', FALSE, 'InfoViz · BuildReportPipeline')
  , ('233438f6ae9913b7', 'client', 'it combines with an equipped cursor colour', '93b691fd04feffee114831988cedfd9da7a17351', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('ea21a88fede55bdf', 'client', 'it costs nothing while you are playing', '6501a591452de86dd2c5cf1efed8c799efd7c2fb', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('0eb7c9c59f49f8d5', 'client', 'it deletes your rating, history and collection, and there is no undo', 'd746ddc283a3e674b62c0c5efd663abf4d40a0c7', TRUE, 'SettingsDescriptors.g · ReasonTr')
  , ('6ad35b1b8f71c2c7', 'client', 'it is the instrument you judge the rest of this tab with', 'a36fc9fd73667c42a1563584c1b205218f12a634', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('0a1f36c837a11dfd', 'client', 'it is the only place a block can be lifted', '5863dcb7443dac013f265e3b4eb5eaf7122f42c1', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('34464da33ce17504', 'client', 'it is the only place the individual patches can be seen', '5c62bc0c4d6ec1ed0d365f6c161378e2e3c93bd5', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('a00d1ffe51d6b211', 'client', 'it leaves every queue at once and costs nothing if you are not in one', 'c2d61ad42ca4acdaa2a9d607e4f705fc864ea5a5', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('eb605eb5f534eb6f', 'client', 'it only hides you from Home lists; it does not hide matches', 'ab28e89d2a9fc74e593dc672e9e1b16ddf9ded46', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('06f495e2b4472851', 'client', 'it opens a browser; nothing in game changes', '8db28acc19b6e7d3022aaafa35d11bc7e0eec48c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('e66cb18f68b63ea3', 'client', 'jump within 0.1s: up and away', 'e076f29122f30e52c0c072566963e93522d67fd6', FALSE, 'InfoViz · BuildMovementWindow')
  , ('253b8816f895e0e3', 'client', 'just now', 'a7f8e7cc0d43d21e5d1a4d0a3b0d5ff66a5da1ed', FALSE, 'ProfileCard · Ago')
  , ('cf5cb9ff40d507e3', 'client', 'keeps a modded avatar out of games where it renders with holes', '0dd3a6f354eb8bd666a33b1fc29e753bc2fd211c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('32e1c10c1d2398a5', 'client', 'keeps boards to players you can actually meet', '8736ade781bb7e933fcb92f55f23d0101a7db6fb', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('ce0e1f95541897c6', 'client', 'kill boundary', '4cbe09f6351f1f3546faeafe30805718ab64e2a4', FALSE, 'InfoViz · BuildMovementWindow')
  , ('fb958bd172565785', 'client', 'kills', '4b11e02d76ac718fc586685475785a677180fb4c', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('020d4a91d7f73c41', 'client', 'largest visible win in heavy firefights', '6758adebb032283893ab5c5b5784a9c9b31e879a', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('7a881118486c1995', 'client', 'leafy mushroom', 'd7c3ca35dc2b8189ab0b9f4451740d1ec6ed59f0', FALSE, 'shop catalog · cosmetic name/description')
  , ('a1a070bd7dc66637', 'client', 'legendary', '4c87891558ebeb3be19116efc8e9037e43f0ad1e', FALSE, 'NativeUI · TrRarity')
  , ('31b5af2a37cfe36c', 'client', 'length {0}', 'd4ba8333c2ff32a5932fd443b9d171d11fae9dad', FALSE, 'SessionReportModel · Build')
  , ('3cc0e9f1d938d32c', 'client', 'lets trades find your binder', '86e8ad488933c8a5ca8fd72ba75fe5d7a47c9daf', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('ff097547403cfb2a', 'client', 'level', 'ad60c535ff88e85bf0254452fe3934f24e9668d5', FALSE, 'InfoViz · BuildXpCurve')
  , ('4557861be9fd2f0d', 'client', 'local display only; decimals help only when a card leaves max health on a fraction', '4f7dc5db0ca56a15d9614ea9e2a087cde9f3b746', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('93ad7abdc83e80b3', 'client', 'local fight simulation', '478712e443993e3d89008450795a14a38a876383', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('64fb4772b536bd46', 'client', 'longest', '1118aa5e083aac060f34ef110ca131dcc08a4e49', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('c13921814b798a44', 'client', 'lost {0} of {1}', 'e0b4578475d11bc2affdf781c63bf10d756ba3b8', FALSE, 'NativeUI · BuildComparePlayerNemesisPanel')
  , ('757475070fae24d1', 'client', 'macro-pace input windows', '9c40e6c83966edf6af71bfd2f2102c7b0d01024a', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('62db12584044bf19', 'client', 'maintenance', '5b30e2c5ecb965cd571ebe6fa56b9b1db7e21ae4', FALSE, 'ServerTextRules · TrMiddleware')
  , ('adc07fa5126b4b49', 'client', 'malformed PNG (IHDR is not the first chunk)', 'd9fb83b92be5e2d5b3fa328b0b506b0919bbc0f9', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('4c2c45ac7305a4d9', 'client', 'malformed PNG (bad CRC on {0} chunk)', 'be1c18d64e7c57e483a5fa3356d92778b3ae5cdf', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8232c24b94f97d0d', 'client', 'malformed PNG (chunk length runs past end of file)', 'e9afe5cf2f721f7fdd7599b84ae502b53d01841a', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('a08c9778f1c42739', 'client', 'malformed PNG (invalid chunk type)', '9f32a0dbbd3039c6bff7076ad36ed44ea6b4d5d6', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('1a6564421fdf22c7', 'client', 'malformed PNG (no IEND chunk)', '5ed888ca9078c711953730f88671ed4b530b51a7', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('074226830f67f56e', 'client', 'master gate; off disables all seven', '7b4647df095f31f302396978941b26eb19f2759c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('918e61d0f4abde33', 'client', 'match data unavailable', 'b51992409edca91e5f36b8af904c5f333dff1f5c', FALSE, 'PostSessionReport · Compose2v2, ComposeFfa, ComposeGameRows1v1')
  , ('a4255a4114972113', 'client', 'match goes live', '861be15995b350b7675a1c2783e64e1d6d1e2414', FALSE, 'InfoViz · BuildForfeitClock')
  , ('8ec80c0992c52337', 'client', 'matches always use your picks regardless', 'ae3f48c37cab3c6b85acb35e5e371734368fbb3f', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('b2e72677b57733d8', 'client', 'menu code cannot matter mid-match', 'd095d2d4194c396b65bfca02112304027a6fb74b', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('e708ab538100605b', 'client', 'missing frames: have {0} of {1}', '95e6d93bf41f6cdc0dde3ba59cbdba3ac449e455', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('7e318ed8676d0e52', 'client', 'mod', '7dd30f0a95d522bfc058be4e75847f8b6df9f76b', FALSE, 'InfoViz · BuildKeyboard')
  , ('abe8e5a9fd37471a', 'client', 'mod-issued', 'aa50bfd83ec8c8109f2b439405fd8292fadace98', FALSE, 'InfoViz · BuildWhenCounts')
  , ('f1ae60f8bed4f5b8', 'client', 'mod-issued: queue / 2v2 / tournament / ranked FFA = ranked', '4bf611ca20f506ef1cfbbe3c15e669598075a558', TRUE, 'InfoViz · BuildWhenCounts')
  , ('64fbafa71c64ea5b', 'client', 'music album', '1d4c4223850b4c5a79983792395382208c8f79c8', FALSE, 'NativeUI · TrKindWord')
  , ('57b76a495ff1b2ba', 'client', 'must be exactly 512x512 (got {0}x{1})', '19a3ae6e5d002af98fb948344f6db9dbb05a3642', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('7a6d628940a29076', 'client', 'mutual forfeit', '4448b532f041bf034129ac3c8023aea565d60eef', TRUE, 'NativeUI · TrBracketProgress')
  , ('55ac00362d911aae', 'client', 'name too short (letters/numbers/spaces only)', 'f517659313aa5eacbf57f6f19a375141369ae034', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('c92a9fa248bfbe4e', 'client', 'nametag', '4a16571080b2d5ec503066ad09664991bc0338bb', FALSE, 'NativeUI · TrKindWord')
  , ('5f35571c528c719d', 'client', 'never active in a room or on match-found', '0ff072dfdf511903576f7674dfb83ba01674d4df', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('cb93e4d862f0d5d8', 'client', 'no - casual', 'b385fed762cbac170a73be10adb8a477f1761794', FALSE, 'InfoViz · BuildWhenCounts')
  , ('01a4b599f350abae', 'client', 'no - stop', '0297fb1e6c176b4d67ea304108c33235fbb5d723', FALSE, 'InfoViz · BuildWhenCounts')
  , ('1d57224fd1a0098c', 'client', 'no build recorded for these games', 'a1ab96766fdd1c8827af3c5700e41d3acd7a8c6b', FALSE, 'SessionReportModel · Build')
  , ('568bed8b059b93ef', 'client', 'no card data', '3865e6152a8c60511725d508e1493e63c71e47c3', FALSE, 'NativeUI · BuildCompareCardGrid')
  , ('5a6a862a3fe38072', 'client', 'no cards recorded', 'ea42e0f58f16d642275677edc0ba3dc66ee8b595', FALSE, 'SessionReportModel · Build')
  , ('eba3826ea7d1aee5', 'client', 'no data', '4d968a30a022f41e9826f0cf09d36c2b6a22bfa4', FALSE, 'NativeUI, PostSessionReport · BuildCompareCardPickers, BuildCompareGenericPie, BuildComparePieChart +4')
  , ('5dbdcd2c139f60eb', 'client', 'no data yet', '5721ec14c55e6b84fcb1167530b5e59891bc4d54', FALSE, 'NativeUI · BuildCompareRecordsPanel')
  , ('2ca28458c1bba16f', 'client', 'no debt, no double buys', '3041bad1187c20fb9675fb2ee260fb4efa4a8055', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('20f0dec1c5491a83', 'client', 'no direct PC link', '60e7dc38d58fa8d4dd69f14b8056f4fa75478377', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('d71cb0cd1bf730ff', 'client', 'no opponent has taken 3+ series from them', '2ecd6485173e509e08f96a4f140ca72a57dfb91b', FALSE, 'NativeUI · BuildComparePlayerNemesisPanel')
  , ('cc7fc9633cd6dc97', 'client', 'no profit at these odds', '2220d7c0a8777ada584d790974e9a04202b70c3c', FALSE, 'NativeUI · ApplyBetRow, ApplyTeamBetRow')
  , ('2bb5ba7c61b812cd', 'client', 'no rating, gold or XP recorded for this set', '3b51171733348d8dd5029bda44128b80eb3f76fd', TRUE, 'SessionReportView · DrawProgressPage')
  , ('efa2db577712bf34', 'client', 'nobody - your screen only, never networked', '0462fea2f9874e1ca9333be1562c930ed280d248', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('7ae14936a4754653', 'client', 'nobody yet', '35bcd8643f8ac67f525e911a2088afb8d31d4e78', FALSE, 'NativeUI · BuildCompareCardLeaders')
  , ('b24bfe85b7dcec93', 'client', 'none yet', '02942cecd86ee6b2511efea71d4e9b2e944fb42a', FALSE, 'NativeUI · RefreshRecentTournamentsPopup')
  , ('0da1581804ff3c96', 'client', 'not a GIF file', '21f2ec9fe54cde671fbbe57fd4d83a935451fae6', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8bd6981e400fe461', 'client', 'not a PNG file', '1cd6ee2b12356b96054253790d3073acad9bb47c', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('84560648012ce2e1', 'client', 'not blocking: 51 damage + return impulse', '5ecbe3fc814b3bedd3ae2f8e48735110c17a7e27', FALSE, 'InfoViz · BuildMovementWindow')
  , ('6e609efa1850f406', 'client', 'not enough data (4+ picks)', 'b812a48694a85178a169e0758e8e3d81298192fc', FALSE, 'NativeUI · BuildCompareCardGrid')
  , ('9baea7ac09c3203f', 'client', 'not recorded (older block format)', 'ab72048da17149f931cb904c904a44a9367463ab', FALSE, 'SessionReportModel · Build')
  , ('a69613aa44b5d523', 'client', 'not recorded for this set', '7f29bc27e0084c8072431aaeb444fb961369d2d3', FALSE, 'SessionReportModel · MissingText')
  , ('98dbdb058acc75ef', 'client', 'not supported for this mode', '6dd42b86329428d04bfef42cbc19b06bac62e734', FALSE, 'SessionReportModel · MissingText')
  , ('0195071f9f835b41', 'client', 'nothing', '0feca720e2c29dafb2c900713ba560e03b758711', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('34e94342172ccc16', 'client', 'nothing - vanilla has no surface for them', '7c6b93acbc4088c277552ad8ef6ab2f2dd378d59', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('2cc63cfa491890ed', 'client', 'nothing moves until you accept a proposal', '2d3ec7acb5b76ef12260ba2194ba3f42a580a50b', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('6c3530c8c280b3ff', 'client', 'now: <b>{0}</b>', '11ef3b2ae60a4251cd73fef09e480569d29ecdfd', FALSE, 'NativeUI · RefreshTournaments')
  , ('c611c863fac6939b', 'client', 'off falls everyone back to orange/blue', '387705e610ae9aa60250f9acdc7958e32868f8fd', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('101d75933f2149ce', 'client', 'off is crisper and slightly faster', '0f6398a20a4a0c7b8d5639332b031fec87cfa08c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('13c07d021068e14a', 'client', 'off is flat but faster', '6de678ac69b4a5859d01714d7bca92796d57b6df', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('245df8e62a3e4889', 'client', 'off keeps lighting and drops the beams', 'd0b889affc17a0df2d198e87db1919f48e7fa2ec', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('99ff6d9d5d869554', 'client', 'on the boards and in chat', 'c3f2d0282552ceccb72ae077467142fd8eb4b486', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('b68c518beaf82114', 'client', 'once Discord is linked, mail reaches you when the game is closed and you can reply from there', '4e03cf1546b316d493277d9e08a2ff114a05a922', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('6db3bbf4f54c0cb1', 'client', 'one +24h extension', '0782adb78e6c9b99ee3bcd1ef5f675a1b8147757', FALSE, 'InfoViz · BuildForfeitClock')
  , ('62696896c58079eb', 'client', 'one 0.3s block window', '286e61e5c91f29635f56fae46d6fa62ff77b3552', FALSE, 'InfoViz · BuildDotTimeline')
  , ('bea16a781a4dd7d5', 'client', 'one 2v2 rating outcome', 'e5398f883daa5f89eb09ddf30c9d5b97f7ec8978', FALSE, 'InfoViz · BuildTeamFormat')
  , ('4867ccd0ab09b4b7', 'client', 'one active, or multi-equip', '5015bc8802ef6f39234ea8b46bd73b2a9ca5ec1f', FALSE, 'InfoViz · BuildCosmeticsFlow')
  , ('1e0ef297c1e3d8b3', 'client', 'one color at a time', 'f9c0c29d091d50a9086354e063e47954c59e1b90', FALSE, 'NativeUI · ApplyShopRow')
  , ('8cad63c636cdcf6f', 'client', 'one font at a time', 'ff83a9a220be04b92113dda6c44401123dc40b01', FALSE, 'NativeUI · ApplyShopRow')
  , ('3bd7fbbab2fca8f1', 'client', 'one glow at a time - modded players only', '35a7375e3bb813dfde5e763661731fac75a6e0d2', FALSE, 'NativeUI · ApplyShopRow')
  , ('64bf847d283de5e3', 'client', 'one line, bottom-left, and only on custom tracks', '5d79658b553b0ad3a51942772e58939d3cb3be89', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('cb214dd8fdcdef80', 'client', 'one present: absent player forfeits', '5bfb30cdbd1b6e637c5e3fdd9b7cc5cbc4498c7b', TRUE, 'InfoViz · BuildForfeitClock')
  , ('e165e5ae840a62fb', 'client', 'one size at a time', '7ab9c8362a5abfb2e9bfcbaa02d5a3f8fc771179', FALSE, 'NativeUI · ApplyShopRow')
  , ('8e4bd5a8e9eec6ae', 'client', 'one typeface at a time - modded players only', '0570f3e02cc6e225a109dc75f565ed8681b8252e', FALSE, 'NativeUI · ApplyShopRow')
  , ('7ce772413df76f97', 'client', 'online, data on, fighter', '99bc7c117c72c2123f3c96eb3dd62d003748821e', FALSE, 'InfoViz · BuildWhenCounts')
  , ('95939f53b57e809f', 'client', 'only after reading the armed warning', '65775754146f98c398dfa2e5fd6ee210d27e1229', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('cbb0440aa5052d96', 'client', 'only if it is 1-1', 'effa17fb09544b590f3e2505d9d125d726ed1f86', FALSE, 'InfoViz · BuildSeriesFormat')
  , ('03eef5b5ee6d4c1b', 'client', 'only presets an unmodded opponent''s own loader can resolve are visible to them', '2e642b708572d9d15775c9c781875a9afdd1d1b5', TRUE, 'SettingsDescriptors.g · ReasonTr')
  , ('9b5fd8306d932300', 'client', 'only rare pulls, and only in one channel', '25d1391b89ec64436ee05d2338510e5755c6204d', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('b8010c785cd567b8', 'client', 'only to leave for good', '841cc10c82ddae233dccb94fad97d6f38afac2b6', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('823d02b9c23306f3', 'client', 'operator_key_invalid', '0de78c988a927f0fdb6f0af793bef37b66fa60e1', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8509b908ebcf9771', 'client', 'opp n/a', 'a964374df27d3749238d57fd9b59327ce6ca8e34', FALSE, 'CompetitiveUI · DrawFPS')
  , ('35da6249eafff7ec', 'client', 'opponent', '5fdeae599e43279dabc19756a63e0bf037b96fb2', FALSE, 'CompetitiveUI, NativeUI · DrawTournamentBanner, FillRow, RefreshTournamentGameIndicator')
  , ('25b56b01dc34efe4', 'client', 'opponent has run', 'dea9d1370e983ae7e4bed0df6cf3b161e81228f4', FALSE, 'InfoViz · BuildWhenCounts')
  , ('8674f3a4352c42f5', 'client', 'opt-in, and it needs a linked Discord to do anything', 'd398d26e816cfae8d97f8886176d45ae7237e035', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('bb0cbec539928a34', 'client', 'optional extra opening pick', 'c60f08db0bad1ed802b2acf74f4b6d03af15d01c', FALSE, 'InfoViz · BuildOvtFormat')
  , ('3ef6e666a4087849', 'client', 'otherwise: score / check-in / no-show tiebreak', '8044c2aa3964a194eff018e055d8259fe024ad05', FALSE, 'InfoViz · BuildForfeitClock')
  , ('0da56f0ef6ca392b', 'client', 'own bullets judge hits', '9d84d798f14ca14192b5a722f8deba3488997934', FALSE, 'InfoViz · BuildNetcodeMap')
  , ('b4bfb963848f5ab0', 'client', 'painted-in glow stays whatever you pick', '37e9f30f3364142870477118c8bedd19d9ed3210', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('5e3938bdf04b7f3d', 'client', 'payload_too_large', 'cd3a039cedf66c52a09dbfc9c8c71ce82c188b13', FALSE, 'ServerTextRules · TrMiddleware')
  , ('a04ec76206e3effa', 'client', 'placement is outside the character editor limit', 'f1144d6fa29a934a26f8f12f47de5633bffc3540', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('3581c4eb186d0477', 'client', 'player color', '871899515bc960165cb986ba61c6b0e2fdfc4483', FALSE, 'NativeUI · TrKindWord')
  , ('d55388f40533f056', 'client', 'player effect', '2b5305a40a645b84a38ed158244a3dde340433b5', FALSE, 'NativeUI · TrKindWord')
  , ('59adbbf05041eea4', 'client', 'player_session_required', 'd6200f4aaee803b4904e8ea6c1be9b2136185fd4', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b94190ef9b2b7350', 'client', 'png_base64 is not valid base64', 'a0dbb0e848a16186d2b26b838a7f09074d9f3984', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('5e67478d8215cb4d', 'client', 'point + release {0} to dance', '2f993c703c59434d8af192f7b6fd96dffd7811b1', FALSE, 'CompetitiveUI · DrawDanceWheel')
  , ('fa783eeb076651e3', 'client', 'point + release {0} to send', '0545b092d2bb9b6517f741b61518de1160f3f2a2', FALSE, 'CompetitiveUI · DrawQuickChat')
  , ('b1e7b0efa8b13273', 'client', 'point lost', 'edc079e759d1a31c643e22a7b51cad76aad0a5b9', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('38cc6e054ab4d13c', 'client', 'point won', '84042146ce1d2bd8175899ff7ce91ec8e89f4032', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('5150a5bb7cbaf0bf', 'client', 'press', 'cd09e18a9bd74edaca7d487211db598da4416565', FALSE, 'InfoViz · BuildBlockWindow')
  , ('f7a262877a996f15', 'client', 'private', 'e80721793c24ae14edfca9b26ad406a9815cd3ff', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('9a3384adc1e2bf15', 'client', 'race target not recorded for {0} of {1} games', 'dab08e27cd07eac73d61a8c28bfdf5246c5acd88', FALSE, 'SessionReportModel · FinishRace')
  , ('5810b68cc636e4f5', 'client', 'race target not recorded: the axis ends at the top score', 'b8a70e3dfdde28eb7ba2fc3c8b5e1110fcd14706', FALSE, 'SessionReportModel · FinishRace')
  , ('2c24e474e0752c0f', 'client', 'ranked 1v1 series vs anyone in the selection, minimum 5 series', '8573726b84feacf62a9d1bb6345a0386a66ff840', TRUE, 'NativeUI · BuildCompareNemesisPanel')
  , ('a95824928e650499', 'client', 'ranked is disabled until you grant it; revoking it again turns ranked back off', '4a91518828948e857061c551c9b96c7e7ff27ca4', TRUE, 'SettingsDescriptors.g · ReasonTr')
  , ('828f105fce189c49', 'client', 'ranked or casual', '251a6cbf14c3adbb715cea7913f49fac0b956c85', TRUE, 'InfoViz · BuildReportPipeline')
  , ('33189667ce7b6ff8', 'client', 'rare', 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', FALSE, 'NativeUI · TrRarity')
  , ('62950a190108a608', 'client', 'rate_limited', 'c27ecc872980bf8fbda2b1364f6894c9e0a3b75d', FALSE, 'ServerTextRules · TrMiddleware, TrRefusalDetail')
  , ('f6db22d3c2bc80be', 'client', 'rating updates ->', '95b76d40aaa4f50c07c2e2235514f88dafcb74cb', FALSE, 'RatingGraphAxis · Caption')
  , ('3f31f55ddbefc45e', 'client', 'read_credential_required', '4e3034d2f68a8b25e816d2ff0638ce4f2ba6fcb3', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('e9811070aa59c9ff', 'client', 'read_gate_unavailable', '303267699ebc318fcdb268ba98910f9f5df57a12', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('7892abd1235fd20e', 'client', 'recent: worst frame {0} ms  resends {1}  discards {2}', '740920adaadc3217938c2e81699d3c4c0e24b1da', FALSE, 'CompetitiveUI · DrawFPS')
  , ('545cded3a4c7556c', 'client', 'recently online', '9480ffe6b949b61541654d37159b5729522647c9', FALSE, 'NativeUI · FmtAgo')
  , ('d84edc438cf970b4', 'client', 'recordable setting?', '758f79de372b7abe0da36f7a47150319187a120b', FALSE, 'InfoViz · BuildWhenCounts')
  , ('78c89c8ea5a01801', 'client', 'recorded once', '75c4d27c742d1f6e7f36095b70192842a6fb0217', FALSE, 'InfoViz · BuildReportPipeline')
  , ('d3dc6e977ef36a1f', 'client', 'regular (converged)', 'b1a78dcbad0d2834c3cf2f89267746a475b04459', FALSE, 'InfoViz · BuildGlickoRd')
  , ('78c0027d4e974379', 'client', 'removes allocation stutter', '691b4f4f5291b737207222a9d013a9f8cccb2244', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('7eee4ef390e42b2e', 'client', 'render_scale must be between 0.50 and 2.25', '51214840171380f7a0e94eb91da8053291dfb98f', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('96c5ee2343e8fc4e', 'client', 'replica age est. n/a', 'b44615b80638caec6d833652c893406c8cbe5c0f', FALSE, 'CompetitiveUI · DrawFPS')
  , ('b6b5460f14b428cd', 'client', 'replica age est. {0} ms one-way (peer-reported input)', '8629cbea57d01e40915bde78c4729afbd6e559fe', FALSE, 'CompetitiveUI · DrawFPS')
  , ('99db5e6326bcafea', 'client', 'report version {0} - some panels may be missing', 'b9c9cc53149d9fbd53f10c4e00a4aa4d3e672822', FALSE, 'SessionReportModel · Build')
  , ('435a4b2bbc8034c8', 'client', 'reset if LB wins', '4f3db459147e54b55553a20c115fcf8572173c35', TRUE, 'InfoViz · BuildBracketFlow')
  , ('caff242c617e9b2c', 'client', 'room code', '9b2aab6b06a8501fc157f91e020a7376de7c5078', FALSE, 'InfoViz · BuildWhenCounts')
  , ('ab3f5cd6e8d0692c', 'client', 'room type?', 'b6d58313c976fea70b5d632b3f1250c39de2282c', FALSE, 'InfoViz · BuildWhenCounts')
  , ('19a8a3a52d540e05', 'client', 'rounds', '75a7b3952462474f6b7d5d061bbfabf02042cead', FALSE, 'SessionReportModel · Build')
  , ('65643a73af1222dd', 'client', 'same-card', '289751437f860828c589bd3ecdcf0c5d29fe8c9d', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('242bfcfe3f1d1135', 'client', 'scale and offsets must be finite', '2ea01dbe70f92d145d8baa2fc74351ff1d3f058d', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('07a44aa1da6ea9d0', 'client', 'scale and offsets must be numbers', 'f42a27847c824c95356ad5e2077ba698f1aaa4fa', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('4c0cc2649d32d885', 'client', 'scrmod.com', 'd685959a21b1062cebf71473cca54c8abdaeafe4', FALSE, 'NativeUI · BuildPage')
  , ('3079dc37a5aeff56', 'client', 'sending your logs automatically is your own decision, never bulk-written', 'c5175ab15ded9f42c53c0b66f7827dae9485c714', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('55b409d36bfa6468', 'client', 'sends the same logs the report form sends without you filing one; worth turning on if you have ever filed a report', 'a5cce8d4e8100d7382a2245dc537de5d20c010c1', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('7a80d7e68ec2f588', 'client', 'series created', 'ba803cb03686e743d6e9702d329b5bfe5c5e2a94', FALSE, 'InfoViz · BuildBetWindow')
  , ('974671d54b95adb3', 'client', 'series ends', 'bad9bfbb27bf708a96616e3cb17bf14ecb178567', FALSE, 'InfoViz · BuildBetWindow')
  , ('e9dde5e52bcb8a2a', 'client', 'service_account_forbidden', '4977aa3ee32cb29843a9082ceabdedca3f41c622', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('8ab7a9d527dae982', 'client', 'service_policy_unavailable', '48a5efcb2c9eda5ee799290d09646fca8cbfb951', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('37224aac59708350', 'client', 'session_check_unavailable', '9fb59b324c591e29786803a763d9b5c579563b67', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('af1e843b1ac03278', 'client', 'session_replication_pending', '0a15c1db8cc927ea25e3957269281fe129b46520', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('ebdc55fd69e037a2', 'client', 'session_required', 'ba1ef721fff2848ec3f0b1c2e43f59e4d1df8691', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('0e7ac4518a710622', 'client', 'sharding...', 'b3c59914fd28d4bac07eeed2425f5096322fbe93', FALSE, 'PlayerCardsUI · FillTile, RefreshBinder, RefreshSelectRow +2')
  , ('74b15a6e53f51a1e', 'client', 'short-match farming pattern', '20bdbf8143b5d78b30c7701b6fd05c824e7f6d93', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('315c2a0244220176', 'client', 'shortest', '5ccd4275b3008ff41aac2030f0352b8f71cd83e2', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('9dd953313fc75502', 'client', 'showing the newest {0} games of this sitting', '3dfd2e885692b06244c1ab4a2f5815cff81aed53', FALSE, 'SessionReportModel · Build')
  , ('d6b721431ce9f5db', 'client', 'showing the newest {0} games of this sitting ({1} not shown)', '6d2b7548ed0a229c3022f463d6ecfc1c074ed549', FALSE, 'SessionReportModel · Build')
  , ('11746e605482ad0f', 'client', 'showing {0} of {1}', '46ec2f98b00b79b27fba942b4baae134d4ddfacd', FALSE, 'PostSessionReport · BuildGraphPages, Compose2v2, ComposeFfa +3')
  , ('7e28c54c9288e1f2', 'client', 'signed up', '6d9703a3413d93d6c98f735422c6f9d6d87d4aa5', FALSE, 'NativeUI · TrBracketProgress')
  , ('82ea29a5fd82d269', 'client', 'slot must be eyes, mouth or detail', '9d2b2048aa49b564e9c0c48cd70ade6237660496', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('194ab49ff9cb5a32', 'client', 'solo {0}-{1} duo', '2129f0c7ad5dbb9c4ebef23f29bc48bea9478978', FALSE, 'SessionReportModel · FinalScore')
  , ('6ec8b00fdee94097', 'client', 'solo: the outer-left point', 'c78fc60f816f6151cfedc59e75bc5099d887665f', FALSE, 'InfoViz · BuildOvtFormat')
  , ('b8adf2986f373097', 'client', 'stackable', 'bea1572501beca2ebef3a391a800868da0c570a0', FALSE, 'NativeUI · ApplyShopRow')
  , ('85590d927883dba0', 'client', 'stops null-reference spam and changes nothing visible', '1f1d4bcb3f24405de15dddb979ccda10edd043a1', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('99a8bcc2b2f76b2e', 'client', 'submission is not accepting frames', '53112242eda1e7c7681093829780366262a353e0', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('af87839fe5c1c66f', 'client', 'submission is not finalizable', 'bf10e07cafcd71dab40919dd459013e0073333fc', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('ecea1c33bb3e1124', 'client', 'submission not found', '77f3ac8ca283417423edcee4d34ae5fa26857b21', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('2b7b86af90eaee32', 'client', 'submission_id and frame_no are required', 'a93191a69804a4cc741d7481c46693fcb0668f5b', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b64f0db498ba5379', 'client', 'submission_id is required', '930b0ca9b941436c091f1c0aaf4527662c73a91f', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('e9f082ac6d69f0fa', 'client', 'sudden death', '59567f73ed8c4e9cfe4dc31ccbc0a82eb0ff30fa', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('75a548880244891a', 'client', 'swallows the one null reference a destroyed bullet raises at a screen edge', '0acc4f3fc2963bfc85ab4f5815112b7e137ef045', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('5f29530b34795185', 'client', 'swallows the one null reference the hit sound raises when its parent is gone', 'd397949e66cc7fa8b3528ddfecea5277ad21963a', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('b0595633f9173320', 'client', 'team 1 {0}-{1} team 2', '9c84c6a903d31152de1b8d3b1f408cfba58b0eab', FALSE, 'SessionReportModel · FinalScore')
  , ('02e7fed14bc8dd22', 'client', 'tells you which region you are on', 'e0ceea83304b3811eaf1d74fb68a57006ccbf1f9', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('64c2f3ce909e1f3b', 'client', 'the Chat overlay mode control cycles the same state in game; Muted also tells the room you cannot read chat', 'b7cc486b61767945e6b26102cd36a3e4cbae81f8', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('1056c66be142583a', 'client', 'the Home chat log updates either way; this is the pop-up', '09112c22a004bb1a95c7dd1d726f9bd5c00b8b5c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('8ca1c23facb2c763', 'client', 'the Info library answers most rules questions', '24b4e73ebdefb7842049e8fa279df7cd6f192c7c', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('6dd409c29663c8ce', 'client', 'the SDF face drops thin glyphs when light', '02df184b8a889aa61429f98a69071463e0af88e7', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('563586da39b3814b', 'client', 'the base award scales with your opponent''s tier; podium and sweep bonuses can add more', '4f07327b6b2ffcb74a720b247fdf065d8ebb7891', FALSE, 'InfoViz · BuildGoldSourcesLegend')
  , ('4ad250fa964a3477', 'client', 'the full art', '745c907a5bceb3e19de222759912533d47907064', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('85322f19a78eccdd', 'client', 'the host', 'd1788f386fb5e576b73f0c14aa294dd1c2977898', FALSE, 'NativeUI · RefreshFfaTab')
  , ('44dbc703f6f12cb1', 'client', 'the menu stays audible either way', '2ae3c576b064f9ab143a6c4ba1a36c4c6c813200', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('4a16145380f98364', 'client', 'the mod?', 'dead726bfa96a471da1ee009d3a1b131af1380c3', FALSE, 'InfoViz · BuildWhenCounts')
  , ('d89af6b095fa7a6e', 'client', 'the one automatic penalty', 'a9a4378b07fb2a7eb676e4d7a5babcd48893621a', TRUE, 'InfoViz · BuildAnticheatPipeline')
  , ('8b1c7dcee4011d4f', 'client', 'the shipped default; 0 is a mode rather than a short timer, because chat then never appears in game', '887359911078669e801804bd492b0eb618e8a6bf', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('347c59bb0d93dd05', 'client', 'the shipped default; menus only, never match data, so switch to the order you read fastest', '8b3d14a4b909afa0e4cc74effedf95a16bdc9812', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('d94f5b08f27af934', 'client', 'the styled name - minus glow and typeface', '77ca2284c1b7b0157881d45cb033ce75ddf1aab4', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('d0f78e8bc9e61df5', 'client', 'there is no region detection to reset TO, and a deliberate regional choice should not revert to the shipped US default', '8ddaf6fcd4890bd9db787f97565a854ed5c1b751', TRUE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('0424598d53212fa1', 'client', 'this is the press that performs the deletion', '9660a2d683a3e47c4686cffdb657c139ca8207e3', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('4b213397a673b237', 'client', 'this is your only copy of {0}', 'c6e03a3b0739dd0ed13a41b0fa51bec8841ad9ee', FALSE, 'PlayerCardsUI · OnDiscardClick, OnlyCopyNote')
  , ('0c49023f677c728c', 'client', 'this row only opens and closes a list; it stores no value', '994029f6d10bb0dc993f3b93ba62712055515559', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('ec19e45ee4b8da76', 'client', 'this row performs an action and stores no value, so there is nothing for a reset to write', '4eeeb6c35c154e00fffaecd1c0051f21da376c72', TRUE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('9058aa60dd0d6780', 'client', 'this row stores no value, and nothing bulk may ever arm or confirm a deletion', 'f6f1a342e0c368f0a22d7b944c73fb388720c362', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('e6a36b479b8265ce', 'client', 'this value lives on the server: a bulk privacy write is one round trip per value, each able to fail on its own, and a half-failed bulk change leaves the page claiming a state the server never stored', '90bbccaf7b8741a220dfca0dc64b12e09ff4ff5b', FALSE, 'SettingsDescriptors.g · ExclusionReasonTr')
  , ('167c8c2ffec8b6e8', 'client', 'title', '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', FALSE, 'NativeUI · TrKindWord')
  , ('c748f274fd740798', 'client', 'touch wall while holding into it', '661e06440fb85ef6750ea1fa15b10d3d1d12096c', FALSE, 'InfoViz · BuildMovementWindow')
  , ('acf6218467f33f12', 'client', 'tracks the whole game', '6f2c72bec243a655d2179316134a66cc9d19533e', FALSE, 'InfoViz · BuildReportPipeline')
  , ('a8aa6f63a0e7347f', 'client', 'trail', '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', FALSE, 'NativeUI · TrKindWord')
  , ('fdf90a6e35fd8343', 'client', 'triggers', '0d850d1fb8c4564a96bca7874d3015c0176cbdd0', FALSE, 'InfoViz · BuildDamageMatrix')
  , ('e00fd16be6205299', 'client', 'truncated PNG (chunk header runs past end of file)', '22b0fde72281a62f91dff0e804ee28fe73721222', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('cac3062641cbd50c', 'client', 'turn it off on a weak GPU; nothing is hidden', '015e0e54d41cabacf00102bd93e36b89bf6488e7', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('1852e794161187f3', 'client', 'turning it off also removes spectators already watching', 'dfeee7a9c36246c774c88e3567ba09d68b62e90a', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('68ae3ba5bde0a1c6', 'client', 'two players, one side', 'c19286c4efd42e3a0809eb95f62008936dc218fb', FALSE, 'InfoViz · BuildOvtFormat')
  , ('538ea7a3863c3322', 'client', 'two teams of two', '320ea28ff8cf9fb1c048c77e5311c2c2ccbda228', FALSE, 'InfoViz · BuildTeamFormat')
  , ('fe8425e82c256c70', 'client', 'uncommon', '8d13318ea523c584ca30b15fad027045157b076b', FALSE, 'NativeUI · TrRarity')
  , ('e6066223b0b305c1', 'client', 'unknown', '50d8b4a941c26b89482c94ab324b5a274f9ced66', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('c4abfe07405d45b5', 'client', 'unknown path', '4902794a18b07e5f86e7f33d4029788b2034de4f', FALSE, 'CompetitiveUI · DrawLogViewerModal')
  , ('eb897bb9be7c79b8', 'client', 'unlimited', 'e1a6f0b6f73a57a8b3ee30419e28f6cb95143908', FALSE, 'NativeUI · RefreshArtistTab')
  , ('a9c6838ab6dd70a6', 'client', 'unreadable PNG: {0}', '0470b3bfc083fe0caff6c37701f574418a7c21d2', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('12788a3b5f878f99', 'client', 'update mod', '5b4aa6fedb5fe06a5f4726d0464394192862ffd1', FALSE, 'NativeUI · RenderHostLobbySection')
  , ('878c2724efc99f6c', 'client', 'utility', '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', FALSE, 'NativeUI · TrKindWord')
  , ('4c729674439fff07', 'client', 'via Discord', '673413af4b73dbbd25f6acdaae7f37d5f001bec6', FALSE, 'MailUI · PaintReader')
  , ('ec3284a5904bb9a1', 'client', 'vs {0}', '8941784e7b51bc9575c6ad7277d273019630104a', FALSE, 'CompetitiveUI, H2HSummary, NativeUI · BuildLine, FillRow, RefreshMatchStatusCache +1')
  , ('cbc1f7ce7819d980', 'client', 'vs {0}: first game this session', 'e944ac9b80a010f18e34cd58514c85d670852aca', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('6e6dc7f3133d7aed', 'client', 'vs {0}: {1}-{2} this session', 'a3917c0620dd986c7fd0b4339f378788e8a55cff', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('d20bb0a584961c1a', 'client', 'w/ {0}', '4b6ebac7f834ce8bb4f4d9fb1155b902d4dac0ce', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('b51b794698a1cd64', 'client', 'w/ {0}   vs {1}', '96d510eecdc8dec60e5e9065d67fb5b7cfb4f49c', FALSE, 'CompetitiveUI · RefreshMatchStatusCache')
  , ('c18900dcc62a1e2c', 'client', 'waiting {0}s', '4f286c6173a7b0795cf964e5d23a676e35a7da86', FALSE, 'SpectatorHud · ConnectStatusLine')
  , ('b1d1da9612c4011d', 'client', 'wall touch refreshes all jumps unless you jumped within the last 0.15s', '6dde9dc4ea9619bfcd9b8dcbc48605479fb1cbf9', FALSE, 'InfoViz · BuildMovementWindow')
  , ('9f872c3b36543248', 'client', 'watching', '874e70e6ab4d774bd2950cff37e0f6d516a63a5d', FALSE, 'NativeUI · RenderOvtLiveGames')
  , ('1cfb1bcbca9e7fa5', 'client', 'when the count beside it is not 7/7', '64eb4efe4fe6d3f874c2531ec65c59c2cf5b1209', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('7baa5c9d697a074c', 'client', 'when the game thinks you are still queued', 'af3ae9834ca632d716ffc2e2443afc8cd316ab01', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('9dd1688278d41b8d', 'client', 'when you want to help translate the mod', '01a5f1d6974c2617b84eb460631e1ccba45ea3e9', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('74d0411862b12522', 'client', 'when you want to unblock someone', '1746cb0de7b4b1239b66006943d9ec19256ce8f0', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('84c17b96c91dc43d', 'client', 'whenever you armed it by accident', 'ddb9d641eca3225ac920e15c27fc2fb06a912212', FALSE, 'SettingsDescriptors.g · WhenToPressTr')
  , ('86b037a625d0b9b4', 'client', 'window over - cooldown keeps counting from the press', '8bb57a9623bacb4a696286be7447896412172cb2', FALSE, 'InfoViz · BuildBlockWindow')
  , ('84603418a58395c8', 'client', 'with exact evidence', '380985fee96b8861416b2c6ba8f200ba045c59e0', FALSE, 'InfoViz · BuildAnticheatPipeline')
  , ('ba5b1bda254c9b96', 'client', 'won by forfeit', '7bdb949aa5e49969fc45277751121088bae773f6', TRUE, 'NativeUI · TrBracketProgress')
  , ('5f66136e50a33724', 'client', 'worth it while investigating one match; it is noisy, so turn it back off afterwards', 'ad2db4d17676b54f81b1f4de74d5aae414066495', FALSE, 'SettingsDescriptors.g · ReasonTr')
  , ('c61fa7034ff70a0e', 'client', 'yes', 'fb360f9c09ac8c5edb2f18be5de4e80ea4c430d0', FALSE, 'InfoViz · BuildWhenCounts')
  , ('658c8881ff4b6496', 'client', 'yesterday', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', FALSE, 'H2HSummary · Ago')
  , ('237b52a3029ad67f', 'client', 'you', '8af56de68279cb6f5ed022f31af18b9fcdcc2e92', FALSE, 'NativeUI · FillRow')
  , ('3878e9a06f200884', 'client', 'your aura', 'eeb8efa38b04f77978c1af0170aa5d063ac81369', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('33bfac719482404c', 'client', 'your color', '0e2aa9db2a51762cc7ef7e2472f33a421dc2776e', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('b4d316822b96ba26', 'client', 'your stake plus profit by the odds - short-odds wins are lightly taxed', '0cb58f388e3dde80555698a33dd62ee6f8cd6af5', FALSE, 'InfoViz · BuildGoldSourcesLegend')
  , ('a3825c2ab956ca64', 'client', 'your trail', '6287c791cf7634cffd62a205b30593f7bc398ca0', FALSE, 'InfoViz · BuildVisibilitySeats')
  , ('3b0db3500eaa50f3', 'client', '{0:N0} XP', '8fa729e9316bef96c0d4cd7ce5decbcde8605aef', FALSE, 'NativeUI · RefreshMyStats')
  , ('e2dccdf13c763727', 'client', '{0}  {1}%  ({2} picks)', 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', FALSE, 'PostSessionReport · FavCardLine')
  , ('5be7e933e570652e', 'client', '{0} (away) got {1}', '0afb928a9a1a63e43a466df8800e5bf2db693dab', FALSE, 'FfaMode · ApplyManifestPick')
  , ('a424ebab1dfeeb56', 'client', '{0} (hold) - dance wheel; dancing locks your controls', 'a6bf4f2389295dfdb7ad63d86eb9a2078c0b76a3', FALSE, 'InfoViz · BuildKeyboard')
  , ('5a68dd9788702e67', 'client', '{0} (hold) - quick-chat wheel, release to send', 'affafc49cfe489453832758dc3471f3f98c3a373', FALSE, 'InfoViz · BuildKeyboard')
  , ('c995fa627e62204a', 'client', '{0} (hold, in a lobby) - ready up / join', '383be83bbc34d04da5dcb28a11d9451db164dab6', FALSE, 'InfoViz · BuildKeyboard')
  , ('99d8c7aa699316e8', 'client', '{0} (hold, in a match) - live scoreboard', 'acf6ba0a98909fa0bbe504945c483dc81c00d3b8', FALSE, 'InfoViz · BuildKeyboard')
  , ('5238386c4c01c3a0', 'client', '{0} (tap, while typing in chat) - switch the chat language channel', 'c19aa76eb50f3ad712b8592b03ff1713af02da7f', FALSE, 'InfoViz · BuildKeyboard')
  , ('107f9e44420b6a70', 'client', '{0} ({1} ratings, {2} listeners)', '2e5c88d9dff1ac89fe4c65eb5841e1a969463c87', FALSE, 'NativeUI · RefreshMusicTab')
  , ('8d1eb7f439d936f8', 'client', '{0} + {1} more', '01af2476cdb74ff6297b08f331bcd2a1c276cf52', FALSE, 'SpectatorHud · BuildTerminalLine')
  , ('d1501eb2dc50e743', 'client', '{0} - cycle the chat overlay mode', '4b712bd125fc9151a491733e970010e51ae5043b', FALSE, 'InfoViz · BuildKeyboard')
  , ('6c4ece2fb0649ec6', 'client', '{0} - cycle your equipped map skins', '1e395c4e58f633994e5d9304798b4ca585184589', FALSE, 'InfoViz · BuildKeyboard')
  , ('babb81673aae1d99', 'client', '{0} - move.  {1} - jump', '3f4742e68725ca402e345ba00429035f605f15fd', FALSE, 'InfoViz · BuildKeyboard')
  , ('5771a3dbf4a6ebb7', 'client', '{0} - open / close the competitive menu', '2939ef85f045ee7cc7cb9c691ebe7eea11900bc5', FALSE, 'InfoViz · BuildKeyboard')
  , ('d0d2d4c91816b1f8', 'client', '{0} - open in-game chat', '69a358031d6d4c5fd8572da5548566516c3ced5b', FALSE, 'InfoViz · BuildKeyboard')
  , ('1dd31e8f2f17452e', 'client', '{0} - shoot.  {1} - block', '741476a9c960d40f9ade50e5391fe61e1eb461ab', FALSE, 'InfoViz · BuildKeyboard')
  , ('6058766975fa9cce', 'client', '{0} - top of the ladder.', '5946098a7e35ec22cf7d63c12bc08d878da90c8a', FALSE, 'TitleLaddersUI · ProgressText')
  , ('0500528ae3344450', 'client', '{0} - {1} games - {2} played', '4d002c2ce0b90e49202eaef503544ce33e4ced50', FALSE, 'SessionReportModel · Build')
  , ('560a32b0d16aa441', 'client', '{0} / {1} unlocked', 'f44e9fd85b7ae7b1813d58f357d0ec3c223627aa', FALSE, 'NativeUI · GetAchievementText, RefreshAchievements')
  , ('dc6588862dd02f39', 'client', '{0} <b>won</b> {1}-{2}', '6aefdf8cf3774a76db4f21466926eaa31e1bf15c', FALSE, 'NativeUI, PostSessionReport · Compose2v2, RefreshTeamTab')
  , ('3441b08a2609bf6c', 'client', '{0} Block Rate', '66eabd902fbdcda13ee03b9cb6457cb45d8178b3', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('5bb89ae8f8fe797b', 'client', '{0} Blocks', 'bf913700cbab41212cf3ad715dd81da699639b50', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('a4036f830a92a60a', 'client', '{0} GOT A POINT', 'eb511260e4db899255c5755b6c52fadda28a8606', FALSE, 'TeamColorIdentity · AfterDoShowPoints')
  , ('3a9e2a2db7d4115e', 'client', '{0} GOT HALF A POINT', '0628f47a69f660375da687357d797c395f669618', FALSE, 'TeamColorIdentity · AfterDoShowPoints')
  , ('54f6a34eb41233e6', 'client', '{0} Hit Rate', 'fbea93183790813787fd128dedfee3c20e02181f', FALSE, 'CompetitiveUI · PaintPairGraph')
  , ('5e7130826042033e', 'client', '{0} active players', '7b291b43e0c48457d2f8d4727faff725dec5828c', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('1bfb29d0610f08e5', 'client', '{0} active players ({1}d)', '1ab2f62477596e5ae4eefd59c1604a8713707dbc', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('5db13011ad111262', 'client', '{0} and {1} more', '616f33b46c1533c1418ef7509c1e8dfd23521644', FALSE, 'CompetitiveUI · RefreshFfaMatchPointBanner')
  , ('aba91628ab0e4069', 'client', '{0} can now translate {1}.', '352e94ec0f7361050981402124252d03ad906990', FALSE, 'NativeUI · BuildAdminTab')
  , ('5f8050bf63a306fa', 'client', '{0} cards', '4b2e608f2980000efc58b108cd4a6fffdc13b4b1', FALSE, 'PlayerCardsUI · RefreshBinder')
  , ('572c49153567a8b1', 'client', '{0} d ago', '4a93a5aeeee725aff10b0cf88441c452e85cb806', FALSE, 'ProfileCard · Ago')
  , ('d00d1cf6fc532cd8', 'client', '{0} days ago', '9344533c4118c35c73e68a704ed70271514f9211', FALSE, 'H2HSummary · Ago')
  , ('dff040f0708dc38d', 'client', '{0} did not return. The match ends as a disconnect.', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', FALSE, 'TeamHoldBanner · Line')
  , ('6f660f7ab40c9fb1', 'client', '{0} did not return; seat released', 'dde36fb32699b8f418e4ddd09014d5b814a911d4', FALSE, 'FfaReadmit · OnHoldsAnswer')
  , ('667904796cde2009', 'client', '{0} dps', 'f274e414cfaafd05ff3a007da9a995bc7723be59', FALSE, 'NativeUI, PostSessionReport · BuildFfaRecentRowText, FillRow, SideStats')
  , ('23f3e8961d9a6d6d', 'client', '{0} elo', '5519c24b363f6799a1bfaab8e067c25e0eca51e3', FALSE, 'NativeUI, PostSessionReport · FfaPlayerLine, RefreshHistory, SeriesHeaderText +1')
  , ('a6591208353e8c19', 'client', '{0} games', '2e77263bcf3946e67a96ad9f1138da667d0f0255', FALSE, 'TitleLaddersUI · UnitCount')
  , ('f175d5d9643750aa', 'client', '{0} games    {1}W - {2}L    {3}', 'cceed712efad9af4f4ef2b04ce0b8d5a66f086ce', FALSE, 'NativeUI · RefreshSession')
  , ('ea5a4baa04c86c8d', 'client', '{0} games  {1} wins  Top3 {2}%  Avg place {3}', '74461284c35ce3294a098d44ec320782994dba20', FALSE, 'PostSessionReport · ComposeFfaMiniPanel')
  , ('39d3224cdc75aaf1', 'client', '{0} gold', '2b008282f83e9225ab40ddf0bb29d39540824671', TRUE, 'PlayerCardsUI, TitleLaddersUI · Refresh, UnitCount')
  , ('d896225c4b934865', 'client', '{0} h ago', 'f29997e604005ce5aa841d40a0fe3a77ae4c6980', FALSE, 'ProfileCard · Ago')
  , ('563f328fb4d4aa1d', 'client', '{0} half-point events', '60af1d144ac434a965bf13bb977aa7aadb4bb8d3', FALSE, 'NativeUI · ParseFfaTimeline')
  , ('b933f3c706c40e83', 'client', '{0} is back', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', FALSE, 'FfaLateEntry, TeamHoldBanner · AfterPair, Line')
  , ('197f283ed051ad83', 'client', '{0} is now your title.', '793854d7e383649b1aa1c4dd9454a8479437b9f9', FALSE, 'TitleLaddersUI · OnWearClicked')
  , ('690eba24c1191a59', 'client', '{0} is rejoining', '37a2e787a323c769817b4d2446d54a8b45a264f3', FALSE, 'TeamHoldBanner · Line')
  , ('256d2b14212ba5d4', 'client', '{0} item(s), {1} cop(ies) out there.', '1ab5b75b0bfcc6c62c111b526749c2b8fdbd47ed', FALSE, 'NativeUI · RefreshArtistTab')
  , ('580d15e9663872e6', 'client', '{0} keys/s', 'a2df9cb008e9644c6620b3985803262c7bd369d3', FALSE, 'NativeUI, PostSessionReport · FillRow, SideStats')
  , ('8d2f51bb322a407c', 'client', '{0} kills   {1} dmg', 'b752606308eb98d088cea0df5ed83d968850cc18', FALSE, 'PostSessionReport · FfaPlayerLine')
  , ('1befb6e99aff9cb6', 'client', '{0} losses', 'c10f2aad3e4773224d91f7013462e27fd1dea962', FALSE, 'TitleLaddersUI · UnitCount')
  , ('bc555d5b081fc988', 'client', '{0} lost {1}', '1c04abac777e7a98a7bb9a840ed12f7780cedf82', FALSE, 'FfaMode · ApplyManifestPick')
  , ('2aa987f867bde0fc', 'client', '{0} matches ({1}W / {2}L)  WR: {3}%', 'da5d5190f132c40421541404bfbc922fa7b4115e', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('7b96b5a23f982716', 'client', '{0} min ago', 'b9e7312c9f0f882c9d389eabbd62129e6fefa8c4', FALSE, 'ProfileCard · Ago')
  , ('3b76eb04250b37e5', 'client', '{0} months ago', '3c784acc314dd9a21178a33cfb55e12ab4f6711a', FALSE, 'H2HSummary · Ago')
  , ('65f941ceb85bcf25', 'client', '{0} not shown', '85a9a4bcdeb72a56f9fcebae4f8968432141bd56', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('139aed472ae35511', 'client', '{0} of {1} - {2} to go.', 'af84949b68ff2cacdc96b6bca93220098200889a', FALSE, 'TitleLaddersUI · ProgressText')
  , ('f685742f5ba61184', 'client', '{0} of {1} games timed', 'f485646d5daaedec904038521981948c2f233e0d', FALSE, 'SessionReportModel · BuildTotalsPages')
  , ('c9cc67272a1c866f', 'client', '{0} of {1} left', 'ce9deb48ef00eef45a5b3b38a2161430725ea158', FALSE, 'NativeUI · RefreshArtistTab')
  , ('a91f68125d236ee4', 'client', '{0} of {1} paid packs today - {2} cards each', 'ca4b0d3f9aa54ac39cc997f0b8c76c5f9dd97829', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('3f3e4849188126ca', 'client', '{0} of {1} players', '1b349c2c85da7aa6f6fce0e2315fe90c1db905ef', FALSE, 'NativeUI · RefreshLeaderboard')
  , ('b87ca2f52e5ce09b', 'client', '{0} of {1} to {2} - {3} to go.', '2231f56cad45b5466a4fd7f5eff7935e06bcd17b', FALSE, 'TitleLaddersUI · ProgressText')
  , ('2ef8c7b3a201cae0', 'client', '{0} opening picks', 'a24642bb9528015ac471a91a10e938a1cbe5d461', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('399ed0d6343742dd', 'client', '{0} paid packs today - no daily limit on this account - {1} cards each', 'e46a6351a2a17383127d33142062257b0b527adb', FALSE, 'PlayerCardsUI · RefreshOpen')
  , ('d483410df0912195', 'client', '{0} picked {1}', 'c5da09baee730a66b62342fdae0743b9f8ddcd00', FALSE, 'FfaMode · ApplyManifestPick')
  , ('78b3d4e42121719e', 'client', '{0} player online now', '52a835c16e77c4e0732602eddc7d23596d83990b', FALSE, 'NativeUI · RefreshHomeTab')
  , ('515b68d89b1340f5', 'client', '{0} players', '152c34217212e77f1f0a331aeb6b60286b866830', FALSE, 'SpectatorHud · ComposeTerminalBarLine')
  , ('944fb6c6b97b06d6', 'client', '{0} players could not connect. Re-forming the lobby with everyone still here.', 'd77462714935d5043fdd85b3b8146dc5994723da', FALSE, 'ApiClient · ArmFfaLock')
  , ('8805516634c1f20a', 'client', '{0} players could not connect. The match continues; they may join later.', '6779c644a28a6463c6fd47e5665dffd2d98a24a1', FALSE, 'FfaAssembly · ShortStart')
  , ('7124fad98f05cda2', 'client', '{0} players online now', '18b717861013be8d79565ed16af73c668bcacd51', FALSE, 'NativeUI · RefreshHomeTab')
  , ('2eb242866aaaf376', 'client', '{0} players ranked', '65d4768dbb287c5c86628ac8189b2366ee6700ab', TRUE, 'NativeUI · RefreshLeaderboard')
  , ('e3bb623ce7ca2b09', 'client', '{0} ready! Joining...', '62abf774b7f12a0871590e49783f1c035359ecda', FALSE, 'NativeUI · RefreshQueueUI')
  , ('9065d0a94556a6f9', 'client', '{0} searching', 'e515dbabaae121a13462690c0904e09c4db7d0ed', FALSE, 'NativeUI · RefreshQueueUI')
  , ('79b8c540a97eb0f5', 'client', '{0} series', '222835a0e60f0877394563d301aa723289df5eeb', FALSE, 'TitleLaddersUI · UnitCount')
  , ('108905e2123ecbc7', 'client', '{0} series played', 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', FALSE, 'PostSessionReport · ComposePlayerPanelCompact')
  , ('de07a6a162a4f5f4', 'client', '{0} shards', '6c462948b80bf66d1c4f457418fa25033f3f5ef2', FALSE, 'PlayerCardsUI · Refresh')
  , ('32164f94c093337e', 'client', '{0} submissions already awaiting review — wait for those first', '37f80fabf67d32cde3802de90f9fcb8a621a73aa', FALSE, 'ServerTextRules · TrRefusalDetail')
  , ('b2d9015872c16efa', 'client', '{0} tiers - click to see them all', '2a700ab30dddcc9d663ba259923f36e5ec1294b0', FALSE, 'TitleLaddersUI · PaintEntry')
  , ('577b16be2ddd5908', 'client', '{0} total', '3a0bdc132cd5be4ced44219ee0d007f2880b21d5', FALSE, 'NativeUI · BuildCompareCardLeaders')
  , ('0322c42f001ed4a7', 'client', '{0} tracks', '5e337b6470b963b592464ec5c40d56150f192cf7', FALSE, 'NativeUI · RefreshMusicTab')
  , ('631a133c537677af', 'client', '{0} tracks - {1} - {2}', '9c2e955e1da510a3a7ac7128096bed12c608b737', FALSE, 'NativeUI · ApplyShopRow')
  , ('4b44c291102565eb', 'client', '{0} unread', '28724d54e1d94f4f2e39c4dbe273e5ff00477c44', FALSE, 'MailUI · PaintNav')
  , ('bb67c219422bc077', 'client', '{0} weeks ago', '93a527feb58430dacc2462c4e3aec2f6dfc49791', FALSE, 'H2HSummary · Ago')
  , ('e181752d3a2abb1c', 'client', '{0} winning picks', '16c142f517d5cd3cc3b465b392c9ea438374786d', FALSE, 'NativeUI · BuildCompareCardLeaders')
  , ('c8e44d6c1eed650a', 'client', '{0} wins', '3edc41c3216dce4c68017cea78823127a817031e', FALSE, 'TitleLaddersUI · UnitCount')
  , ('6310f1ba042977c5', 'client', '{0} wins in a row', '1fc94955b2afecaebfb0e7162240448b0564a09f', FALSE, 'TitleLaddersUI · UnitCount')
  , ('59fac74fb0f824fa', 'client', '{0} wins the game!', '9639517ce2b7fbbf135e23f54c237619f3f318d6', FALSE, 'FfaMode · SpectatorCheckGameOver')
  , ('5366e6d1aa97a268', 'client', '{0} years ago', '9a3274443563edf3bd9c07afa970a039ce5ea98f', FALSE, 'H2HSummary · Ago')
  , ('c704367c7945a6b6', 'client', '{0}''s binder is private - they can still propose a trade to you', 'b4be910bc862aeca0f3df350d8488a6f1a8774b2', FALSE, 'PlayerCardsUI · RefreshCompose')
  , ('ef5de162affbd1c3', 'client', '{0}-card draw', '33279a7d64b9594ed34377d1a28a94f4855fb062', FALSE, 'NativeUI · FfaSettingsSummaryBits')
  , ('c26fbd3a29e275e7', 'client', '{0}-player FFA', '3794e1ee399ff58720490640f0a77e3f2b1af14c', FALSE, 'ServerTextRules · SeriesRightLabel')
  , ('b8037a9a2a6f7770', 'client', '{0}-player FFA starting in 5 seconds!', '06869a27250bbb2bd445d71839cd9317c2551ab4', FALSE, 'ApiClient · ArmFfaLock')
  , ('8652c96055f60c8c', 'client', '{0}: <color=#888>(not bound)</color>', '2968d53cd798cf7fb980789d461ea11b3a0d2aa4', FALSE, 'NativeUI · PaintPerfRow')
  , ('b3e2957858fb3018', 'client', '{0}: <color=#FF9966>OFF</color>', '22d79b7411b323a43df61650426791552bdec4ae', FALSE, 'NativeUI · PaintPerfRow')
  , ('c81155b0fa7eca7b', 'client', '{0}h ago', 'f7ce37d55c66b97cbd23a453b13f007c5a09ac19', FALSE, 'NativeUI · FmtAgo')
  , ('a7d29267d8478a44', 'client', '{0}ms opp (peer-reported)', '90cee0472af31ee422a8e8c8e0b8659d1a4d26d5', FALSE, 'CompetitiveUI · DrawFPS')
  , ('a4d81bd7fbd09eff', 'game', 'A huge amount of', 'cce292ce06a96fe2893d663fb2e7510e849218c8', FALSE, 'StringTableCards/AMOUNT_AHUGEAMOUNTOF')
  , ('78d960de3938c3aa', 'game', 'Slightly more', '39ffa12afa64c78190e0d3e9c9d534b3f120fd76', FALSE, 'StringTableCards/AMOUNT_ALITTLEBITOF')
  , ('069eb166aa855aba', 'game', 'A lot lower', 'df1c20b44dc5a005ca96222f69051e6f45fc24d1', FALSE, 'StringTableCards/AMOUNT_ALOTLOWER')
  , ('ae45d23094ff342e', 'game', 'A bunch more', 'bd05371fad5d297d48e01fcca5e59f55c92a5388', FALSE, 'StringTableCards/AMOUNT_ALOTOF')
  , ('203a31ab7377e279', 'game', 'Lower', 'b91eed4b7a80cd9572a27e65ebdff9caa4b3b9a4', FALSE, 'StringTableCards/AMOUNT_LOWER')
  , ('a7fd3731ab075f9e', 'game', 'Slightly lower', 'ab87fc42ed5f4607ee3eedaaed654d8c65be9890', FALSE, 'StringTableCards/AMOUNT_SLIGHTLYLOWER')
  , ('88a3763ecd68c926', 'game', 'Slightly smaller', 'd2ae97a6f9a1028baa25b15030d29e626167e46f', FALSE, 'StringTableCards/AMOUNT_SLIGHTLYSMALLER')
  , ('2bf6225670195b64', 'game', 'Smaller', '30219022865242c8c328da5ba178d41684da1403', FALSE, 'StringTableCards/AMOUNT_SMALLER')
  , ('6828d481f25f271e', 'game', 'More', '4bab2d8fe13fa6ab57f80098b414f0f734c5dd25', FALSE, 'StringTableCards/AMOUNT_SOME')
  , ('320035d28bb925e1', 'game', 'ABYSSAL COUNTDOWN', '386edac8a5be7c743569bb67a4f28c59f145c8ec', FALSE, 'StringTableCards/CARD_ABYSSAL_COUNTDOWN')
  , ('0c24e5696ff0c465', 'game', 'Stand still to summon dark powers', '4711a33663d9b1cb6f9b4ff2946306f909bb44ac', FALSE, 'StringTableCards/CARD_ABYSSAL_COUNTDOWN_DESC')
  , ('e089833a65a32244', 'game', 'BARRAGE', '36458d1195b5500723ec845ebe1335f5377c2109', FALSE, 'StringTableCards/CARD_BARRAGE')
  , ('984d68e9a86f1e92', 'game', 'Fire many bullets at the same time', '6da9fab9c4bc66166d0ad99277842237b8a79d37', FALSE, 'StringTableCards/CARD_BARRAGE_DESC')
  , ('f05fce1b70186512', 'game', 'BIG BULLET', '0a24e48b811ae17a79b0b12e291acb7fc7642df0', FALSE, 'StringTableCards/CARD_BIG_BULLET')
  , ('7188ba9ad803f323', 'game', 'Bigger bullets', '739e1d923303bddc618583ae50a45b0cdaf6f22c', FALSE, 'StringTableCards/CARD_BIG_BULLET_DESC')
  , ('605658c249cc8630', 'game', 'BOMBS AWAY', '0ee58998762310019739faa1cbaf6bae20cb8d63', FALSE, 'StringTableCards/CARD_BOMBS_AWAY')
  , ('c9a51e0e1ea11854', 'game', 'Spawn a bunch of small bombs around you when you block', '742b8f036853bf5ee788a595cfb952653c588b27', FALSE, 'StringTableCards/CARD_BOMBS_AWAY_DESC')
  , ('23047503aa37b788', 'game', 'BOUNCY', '0a6258c9f6ab3046dadd92968ae4c4d0e99ad04f', FALSE, 'StringTableCards/CARD_BOUNCY')
  , ('1343d05a1b0993f0', 'game', 'BRAWLER', '6dd77966414893447ed2b450a83c6fd263a13490', FALSE, 'StringTableCards/CARD_BRAWLER')
  , ('96bbbba49c28ed43', 'game', '+200% HP 3s after dealing DMG', '4cf72f0360afeabe6839c60a545d8afa8f8c8b64', FALSE, 'StringTableCards/CARD_BRAWLER_DESC — Health Points, Damage')
  , ('233be27e4f15d639', 'game', 'BUCKSHOT', '405deae30af72d5bc7285c4710f940268ad14dc6', FALSE, 'StringTableCards/CARD_BUCKSHOT')
  , ('da1b72d2fb954b57', 'game', 'Adds a shotgun vibe to your attack', 'faa00a67e6ef39a491f7eb2cbde4edb5d12c1f06', FALSE, 'StringTableCards/CARD_BUCKSHOT_DESC')
  , ('df78316425dc18c5', 'game', 'BURST', '9ce5d0f6a1f87b8df6a22465f8b3ef966431e2d9', FALSE, 'StringTableCards/CARD_BURST')
  , ('b7a35a4da059181f', 'game', 'Multiple bullets are fired in a sequence', '8e163db9f28e935dc30bf475a4c62ecd23d6c95e', FALSE, 'StringTableCards/CARD_BURST_DESC')
  , ('56fa9eaf1e7fd735', 'game', 'CAREFUL PLANNING', 'cc11eaa53476ff46ab4c677bd5023765dc9263a9', FALSE, 'StringTableCards/CARD_CAREFUL_PLANNING')
  , ('b9fbea5d65e6e66e', 'game', 'CHASE', 'd65eb6205af9b7f4e475e3f6fc087a34422883c6', FALSE, 'StringTableCards/CARD_CHASE')
  , ('cf5d29191379b896', 'game', '+60% movement when moving towards the opponent', 'dd12999157ae0b9a1e421a24ae72f53a7e3b5572', FALSE, 'StringTableCards/CARD_CHASE_DESC')
  , ('51a65b45048ed861', 'game', 'CHILLING PRESENCE', '69f0c1d7433aeaaed0da797fa67ff46cf4c1f997', FALSE, 'StringTableCards/CARD_CHILLING_PRESENCE')
  , ('6dbbe5597bf64f50', 'game', 'Slightly slow nearby enemies', '7be668a4fe8a476e93552a44baa7e48df4ec24fc', FALSE, 'StringTableCards/CARD_CHILLING_PRESENCE_DESC')
  , ('3a5238859631d3ae', 'game', 'COLD BULLETS', '54b8053dda16aad844f4de22eb0c06b14d0ac05c', FALSE, 'StringTableCards/CARD_COLD_BULLETS')
  , ('13ae50b4514bb95f', 'game', 'COMBINE', '1665da04efb16a2aec6e302e358745cc7ad78c35', FALSE, 'StringTableCards/CARD_COMBINE')
  , ('d72fb22fa6163e81', 'game', 'DAZZLE', '9387b0cb1f5e6881cdf630c309fdd4572750c3c1', FALSE, 'StringTableCards/CARD_DAZZLE')
  , ('3f6f9cd86c97db07', 'game', 'Bullets stun the oponent multiple times', 'ce910a4320ada733c71205e850ff8259839ef1f8', FALSE, 'StringTableCards/CARD_DAZZLE_DESC')
  , ('6cb131cbfe9994a0', 'game', 'DECAY', 'eb866db5850f7f76706cc98aa681c751d787ec10', FALSE, 'StringTableCards/CARD_DECAY')
  , ('f8ced7340afd321a', 'game', 'Damage done to you is dealt over 4 seconds', 'e9e58f05b790744b31ac42de18725afe12a06459', FALSE, 'StringTableCards/CARD_DECAY_DESC')
  , ('4b1650a5cc411411', 'game', 'DEFENDER', '885fdc9aa0ab665c2dcc9e35a8c3078398b9ae73', FALSE, 'StringTableCards/CARD_DEFENDER')
  , ('86c12d3915d8a3fe', 'game', 'Demonic pact', '493f137ec26e3c4890c0428655f2eb36f1e390fd', FALSE, 'StringTableCards/CARD_DEMONIC_PACT')
  , ('f9af58f6147262d9', 'game', 'Shooting costs 10HP
Removes shooting cooldown', '7eb1d0ef257bb78989f40d9f8e434bd56fddf5e7', FALSE, 'StringTableCards/CARD_DEMONIC_PACT_DESC — Health Points')
  , ('95521f0cd0fac665', 'game', 'DRILL AMMO', '981988b465f43590b3f024711420ab51ba303b0a', FALSE, 'StringTableCards/CARD_DRILL_AMMO')
  , ('ee360168cd7b0d3e', 'game', 'ECHO', '6781cfc8284296eb70ba05270579b9deac096a80', FALSE, 'StringTableCards/CARD_ECHO')
  , ('dec78d4fd2107f1e', 'game', 'Blocking triggers another, delayed block', 'bf738ce6ebe2c2bbaa10a74cccfbcda05b0ec0d4', FALSE, 'StringTableCards/CARD_ECHO_DESC')
  , ('f58abfbaabcef3be', 'game', 'EMP', '316f7985b2196ffa3985a411b212a6da8a548709', FALSE, 'StringTableCards/CARD_EMP — Electromagnetic pulse')
  , ('1c1b39aab2fc963b', 'game', 'EMPOWER', 'c8d117e77eecb8f2e481fcaa326807dec2779527', FALSE, 'StringTableCards/CARD_EMPOWER')
  , ('e136defac1fab317', 'game', 'Blocking increases the damage and speed of your next shot.
The shot also triggers any on block abilities where it lands.', '92ba9cabfe72adbfba042e4ed214cf98c61f66aa', FALSE, 'StringTableCards/CARD_EMPOWER_DESC')
  , ('468bc45e2ba8d698', 'game', 'Blocking spawns a ring of slowing projectiles', 'a0195c0cf38236ac5eb965e5e8ca13816c32e316', FALSE, 'StringTableCards/CARD_EMP_DESC')
  , ('6bf7254f8bd481e1', 'game', 'EXPLOSIVE BULLET', 'ff849afde5ff08801cd474e6a1996a75ae87f195', FALSE, 'StringTableCards/CARD_EXPLOSIVE_BULLET')
  , ('eaa378854b4ff2f1', 'game', 'Bullet explodes on impact', 'c18d7d533a5f061b72ed65db5e75de2cb0bc4b4d', FALSE, 'StringTableCards/CARD_EXPLOSIVE_BULLET_DESC')
  , ('bc5ef555d953bee2', 'game', 'FASTBALL', '289df29919cf2bb172118b41fe4e024750ac144c', FALSE, 'StringTableCards/CARD_FASTBALL')
  , ('0a6fd7b5a8bfc260', 'game', 'Fast forward', '7966f705b3d65923629592dd35195fb7a36bebdc', FALSE, 'StringTableCards/CARD_FAST_FORWARD')
  , ('f3522d9082eb1df1', 'game', 'Bullets keep the default trajectory', '9349c2e2cdd88afa6330264145134e6b1ce0e088', FALSE, 'StringTableCards/CARD_FAST_FORWARD_DESC')
  , ('9725a834b50f6946', 'game', 'FROST SLAM', '82ff102374c8ed60f1e51721cc6396e8c3ef3512', FALSE, 'StringTableCards/CARD_FROST_SLAM')
  , ('955f576bcd5935c1', 'game', 'Slows enemies around you when you block', '958cf206bee03fc02e32bd57e886f30feb15b182', FALSE, 'StringTableCards/CARD_FROST_SLAM_DESC')
  , ('de85918db7d321c6', 'game', 'GLASS CANNON', '4bc00f32ce4492bacd5886b88fbe94204aca6313', FALSE, 'StringTableCards/CARD_GLASS_CANNON')
  , ('3df86d4f495fbeb2', 'game', 'GROW', '5e7dbabf8c70be19b6c8be0167a746f206f57969', FALSE, 'StringTableCards/CARD_GROW')
  , ('6466039f078b9b29', 'game', 'Bullets gets more damage over time when travelling', 'fae8fc513192afe1f5a8bd331194881fb86df3c2', FALSE, 'StringTableCards/CARD_GROW_DESC')
  , ('65d78156773abdb8', 'game', 'Healing field', '541a369258ece062bf593b14ce24004e457be136', FALSE, 'StringTableCards/CARD_HEALING_FIELD')
  , ('63ca8f483529510b', 'game', 'Blocking creates a healing field', 'c18a33d7d3ef2b00ae81989322977ae3e326e1ac', FALSE, 'StringTableCards/CARD_HEALING_FIELD_DESC')
  , ('842765e862019d78', 'game', 'HOMING', '98f028708d8bf5eb14f0722193dc31b2ebc0fc9b', FALSE, 'StringTableCards/CARD_HOMING')
  , ('180256f3c81a984e', 'game', 'Bullets home towards visible targets', '9d05fcdf7bcecc1ec4a38df4db8ecb2f7557f92c', FALSE, 'StringTableCards/CARD_HOMING_DESC')
  , ('3547320195741e93', 'game', 'HUGE', 'f972c365fd5f66835adf3e756e996923b2340fdb', FALSE, 'StringTableCards/CARD_HUGE')
  , ('b43af19169139958', 'game', 'Implode', 'cab8414810031a7944ef39bef893c146fc126bdf', FALSE, 'StringTableCards/CARD_IMPLODE')
  , ('e5473f59c2cad614', 'game', 'Blocking pulls enemies towards you', '91bbac2d58276906897f7c86f4e6ce9799b15ae9', FALSE, 'StringTableCards/CARD_IMPLODE_DESC')
  , ('ee0f83d5227f6a52', 'game', 'LEECH', 'dd70321d7b240369f6a0ad5758908c5b1d76d121', FALSE, 'StringTableCards/CARD_LEECH')
  , ('9b1e4c75087fb1f8', 'game', 'LIFESTEALER', 'c52dbdd11a2ef54e34f56252333f2573f2a08c95', FALSE, 'StringTableCards/CARD_LIFESTEALER')
  , ('0f3442d66b69918d', 'game', 'Steal HP from your opponent when near', 'f1d408316447410202b4d9caf659de8d93742fcb', FALSE, 'StringTableCards/CARD_LIFESTEALER_DESC — Health Points
2023-10-17: Added missing capitalization of "HP" to keep consistency')
  , ('88bde4fad5c5ecd8', 'game', 'MAYHEM', '0f04a4b49adbb4532514eaae422ea58bac4112a9', FALSE, 'StringTableCards/CARD_MAYHEM')
  , ('7df16c97f1097a3f', 'game', 'OVERPOWER', 'ef9d45a08107a968c244afdc6d05ebc19d9004b8', FALSE, 'StringTableCards/CARD_OVERPOWER')
  , ('ba96fca51968f524', 'game', 'Deal 15% of your max HP to enemies around you when you block', '8504325bff4c363ff45f4d70c743aa1a1c314a00', FALSE, 'StringTableCards/CARD_OVERPOWER_DESC — Health Points')
  , ('c0ba4e9ce075ba67', 'game', 'PARASITE', '78b869238b083d9f178baf9d1617edeecae134cc', FALSE, 'StringTableCards/CARD_PARASITE')
  , ('cc1575ac7ddebd3f', 'game', 'Bullets deal damage over 5 seconds', '87afc1bd217963a2c1ea4fdf261ad830297d0f4c', FALSE, 'StringTableCards/CARD_PARASITE_DESC')
  , ('81463339a0cf951c', 'game', 'PHOENIX', 'c6fbb606ae021f2cfa297f136b2b7c9e4ac0e21a', FALSE, 'StringTableCards/CARD_PHOENIX')
  , ('d7128fcb45c3d75f', 'game', 'Respawn once on death', '75cfd015a64587260d6a87421c3abab5a18ea801', FALSE, 'StringTableCards/CARD_PHOENIX_DESC')
  , ('432fb528f53d3c97', 'game', 'POISON', 'b8eaf34112191ee93d21c9795faa3ea2e2095694', FALSE, 'StringTableCards/CARD_POISON')
  , ('979f21663871da12', 'game', 'Bullets deal damage over 3 seconds', '7c50b022cbbe130e1acaa569843fb7c6fea512d6', FALSE, 'StringTableCards/CARD_POISON_DESC')
  , ('fee8d8d629009cb5', 'game', 'PRISTINE PERSEVERENCE', '35492c772884120ab86449b6a74bd87231823230', FALSE, 'StringTableCards/CARD_PRISITNE_PERSEVERENCE — 2023-10-20: ENG: Fixed a typo in "PRISTINE" ("PRISITNE")')
  , ('7ccc1a98abe848cc', 'game', '+400% HP when above 90% HP', '15e14617a6182f0dcb9af8bdeeab14110bb680e0', FALSE, 'StringTableCards/CARD_PRISITNE_PERSEVERENCE_DESC — Health Points')
  , ('3a3b109343e207d9', 'game', 'QUICK RELOAD', 'a836984427e52623bb34564ac49ad4a73e397bc4', FALSE, 'StringTableCards/CARD_QUICK_RELOAD')
  , ('d69ecbdd58e9a4e3', 'game', 'QUICK SHOT', '470cb98a2d91b7adc7ff74ad3896f437d4593c85', FALSE, 'StringTableCards/CARD_QUICK_SHOT')
  , ('cc1b40e3619a5039', 'game', 'RADAR SHOT', 'e869e9148290b94902ca3a0cfd22a7d1b74e5306', FALSE, 'StringTableCards/CARD_RADAR_SHOT')
  , ('dc0301976907f1c2', 'game', 'Blocking scans the area for enemies. You automatically shoot any enemy found.', 'd8e25405f0eeb973e84b4db5dc0781c1378f1773', FALSE, 'StringTableCards/CARD_RADAR_SHOT_DESC')
  , ('7ba2d9bab03e78cb', 'game', 'RADIANCE', '5167d60b8ae929cbbb30e35c7fb111fd5b32ca5a', FALSE, 'StringTableCards/CARD_RADIANCE')
  , ('126074c573f27c2f', 'game', 'Spawn damaging sun waves when reloading.
The rate increases during the reload sequence.', 'a770314528bc1518e218a7a4d7cdaa88021cf428', FALSE, 'StringTableCards/CARD_RADIANCE_DESC')
  , ('e08afd75068a4ec9', 'game', 'Refresh', '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', FALSE, 'StringTableCards/CARD_REFRESH')
  , ('34e9b914537df923', 'game', 'You get block back when deal damage', 'a5fa658c2c8c40f9ebfe56175f43426d1209cebd', FALSE, 'StringTableCards/CARD_REFRESH_DESC')
  , ('d5d0b8093f2eeaaa', 'game', 'REMOTE', '56ddbcf248ccde5c85f33b60acf834452cc75e80', FALSE, 'StringTableCards/CARD_REMOTE')
  , ('954e55728c5ebdb5', 'game', 'Steer bullet with right stick / mouse', '75753bf610345ff4b4900107c07fa3eef681f7cc', FALSE, 'StringTableCards/CARD_REMOTE_DESC — Xbox Terminology: right stick')
  , ('7b16a85fbc14efad', 'game', 'Steer bullet with right stick', 'd5e636522abecde6fa4b84788a1858739a98936e', FALSE, 'StringTableCards/CARD_REMOTE_DESC_PS — PS Terminology: right stick')
  , ('3eacc35f9d7b18aa', 'game', 'Steer bullet with right stick', 'd5e636522abecde6fa4b84788a1858739a98936e', FALSE, 'StringTableCards/CARD_REMOTE_DESC_XBOX — Xbox Terminology: right stick')
  , ('5fbaf7ccbe5a45d2', 'game', 'RICCOCHET', '1b39d9c3d5a0f2c828b58a4be84d7aa0c9443993', FALSE, 'StringTableCards/CARD_RICCOCHET')
  , ('ae1b61d68f6be632', 'game', 'Bullets lose half of their speed when they bounce', 'eeb2b4041d5a2b1404a7b053ef143cbb21cd597e', FALSE, 'StringTableCards/CARD_RICCOCHET_DESC')
  , ('5f848b3eb8cb35f5', 'game', 'SAW', 'e2d1b2b887c37d8de2e52efcd6756c609ae4930a', FALSE, 'StringTableCards/CARD_SAW')
  , ('699eebe6e98c8a83', 'game', 'Blocking spawns a saw around you for a short while', '3fb749ccb42970013bf69b55ad8c2fc03c57753c', FALSE, 'StringTableCards/CARD_SAW_DESC')
  , ('42836d81ac36a09a', 'game', 'SCAVENGER', 'cf6a5c76ea7c05b4a42a43c86b8d66a0c51435d2', FALSE, 'StringTableCards/CARD_SCAVENGER')
  , ('6104d7afb98b0f0f', 'game', 'Dealing damage reloads your weapon', '53bea03dbb1bf46302373ebc4248c5be987848fb', FALSE, 'StringTableCards/CARD_SCAVENGER_DESC')
  , ('9041d79180a7885a', 'game', 'SHIELDS UP', 'e01575b4fb24b245a5ea4b8c4c2f488477cb0e60', FALSE, 'StringTableCards/CARD_SHIELDS_UP')
  , ('71c7cc75d6b8beb2', 'game', 'Firing your last bullet triggers a block.
Disabled continuous reloading.', 'ce53c9742edad3d2129a95c55cb2ad881e5fb7af', FALSE, 'StringTableCards/CARD_SHIELDS_UP_DESC')
  , ('99fe63301300574c', 'game', 'SHIELD CHARGE', 'fd39ea1533bf5cbae0a8f95fef32b3dd3fcff7eb', FALSE, 'StringTableCards/CARD_SHIELD_CHARGE')
  , ('3ccac216ea7253bf', 'game', 'Blocking launches you forward and gives you a second automatic block upon ending the charge', '3e0066058eff1eb3572f51d4dcd7ad63e596e2fc', FALSE, 'StringTableCards/CARD_SHIELD_CHARGE_DESC')
  , ('4e05f277a8a868e9', 'game', 'Shockwave', 'f9cf560f7be04bf83ae4c79a06b27119a6f9fb24', FALSE, 'StringTableCards/CARD_SHOCKWAVE')
  , ('b882dfc5e49a8b27', 'game', 'Blocking pushes enemies away', 'be2dcc180690ac2b28b36f3bc5b2de4e86cedbc8', FALSE, 'StringTableCards/CARD_SHOCKWAVE_DESC')
  , ('3bdf1f73a2397b9a', 'game', 'SILENCE', '18773d628381f0718a9bdcd419e80bd93cedfaef', FALSE, 'StringTableCards/CARD_SILENCE')
  , ('9acd5548c4af6f72', 'game', 'Blocking silences enemies nearby', '601a761df2846692cecc9620f5b5b51386fba28d', FALSE, 'StringTableCards/CARD_SILENCE_DESC')
  , ('aa4e258db8b6ccf9', 'game', 'SNEAKY', 'e766fbb63609c13053ed95c2861eb92b6c3a1c9b', FALSE, 'StringTableCards/CARD_SNEAKY')
  , ('3b79a005c95703c1', 'game', 'Bullets avoid the ground', '041fd1d4160a5658ae47bca05f21a00978b748da', FALSE, 'StringTableCards/CARD_SNEAKY_DESC')
  , ('d13261664319d348', 'game', 'SPRAY', 'c075dbc1d193b8693966c4419c37347c4b26c0e8', FALSE, 'StringTableCards/CARD_SPRAY')
  , ('b391ace447463335', 'game', 'STATIC FIELD', 'ab988966c77076dd620838a48f1bb75c8925b7d8', FALSE, 'StringTableCards/CARD_STATIC_FIELD')
  , ('d6e8bd0bdac54aca', 'game', 'Blocking creates a field that slows and deals damage', '8dbd56da69dd06aaf006e5832ae4057cee231335', FALSE, 'StringTableCards/CARD_STATIC_FIELD_DESC')
  , ('7044fcd18b0d4eee', 'game', 'STEADY SHOT', '12a79b9c26ef6e3d05a9b0c0de56f9caa740313f', FALSE, 'StringTableCards/CARD_STEADY_SHOT')
  , ('02d0a1f9b84af9cd', 'game', 'SUPERNOVA', 'd032c1d22752988e0185ad5e057b0e8bfc6775f1', FALSE, 'StringTableCards/CARD_SUPERNOVA')
  , ('272352f5117c660e', 'game', 'Spawns a field that pulls enemies in and stuns after a while', '6225ec18d5b84d94bcde33e55c1b3adc2562fd0a', FALSE, 'StringTableCards/CARD_SUPERNOVA_DESC')
  , ('23ee26b036ad3ca1', 'game', 'TACTICAL RELOAD', '655aa405686724cd398ca2779accf853b80fd3e0', FALSE, 'StringTableCards/CARD_TACTICAL_RELOAD')
  , ('569d888f5c7acfb1', 'game', 'Blocking reloads your weapon
', '86c53fb59b278b65b63de1b597b229c080cc44d3', FALSE, 'StringTableCards/CARD_TACTICAL_RELOAD_DESC')
  , ('7e4aa27012d8b519', 'game', 'TANK', 'db5987d0f64d0eaf17d2eb3dade36af46a56c522', FALSE, 'StringTableCards/CARD_TANK')
  , ('a8cde029eaa51955', 'game', 'Target BOUNCE', '2c43fb7e5e1cf0a6af307b0e14f36aed31de5420', FALSE, 'StringTableCards/CARD_TARGET_BOUNCE')
  , ('277d3dae33f6df39', 'game', 'Bullets aim for visible targets when bouncing', '7cb0894b38a9d409abcc0bd91c7fbe2bdae69678', FALSE, 'StringTableCards/CARD_TARGET_BOUNCE_DESC')
  , ('964287e89050ad74', 'game', 'TASTE OF BLOOD', '66436cc2f7f9253f178561921da7ebd06d6cad25', FALSE, 'StringTableCards/CARD_TASTE_OF_BLOOD')
  , ('e1c6a7b3b01a5ea3', 'game', '+50% movement speed 3s after dealing DMG', 'c54531dc5619aa09aa7340a024d95f61b7343a33', FALSE, 'StringTableCards/CARD_TASTE_OF_BLOOD_DESC — Damage')
  , ('063fa1974155ab7a', 'game', 'TELEPORT', '0c952f6370ea34faf764b28b990b2dc9fea61c2d', FALSE, 'StringTableCards/CARD_TELEPORT')
  , ('c8c1cc84c8764b32', 'game', 'Blocking teleports you forward', '6187fec97811787020169fb281a6d49e70351094', FALSE, 'StringTableCards/CARD_TELEPORT_DESC')
  , ('3e45786ce06b8b01', 'game', 'THRUSTER', '0c544e0e51697d2d58d88172c038c2fa8f6fab61', FALSE, 'StringTableCards/CARD_THRUSTER')
  , ('a21309559a923a8c', 'game', 'Bullets have thrusters that push targets', '8b76d9f6d1734fe097d6b5b82addc77bfcbca8db', FALSE, 'StringTableCards/CARD_THRUSTER_DESC')
  , ('e49544b02de62bd7', 'game', 'TIMED DETONATION', 'ae11dfcd56c2fca956df64ec5938f7deed89ba27', FALSE, 'StringTableCards/CARD_TIMED_DETONATION')
  , ('8ac709afc941fd09', 'game', 'Bullets spawn bombs that explode after half a second', 'b66487b42373c8811e76677f9220c0611923c4c5', FALSE, 'StringTableCards/CARD_TIMED_DETONATION_DESC')
  , ('d714153f5c99e2a3', 'game', 'TOXIC CLOUD', '6c7af6f071afda6157b0ea5fff370b11d5c1dcc3', FALSE, 'StringTableCards/CARD_TOXIC_CLOUD')
  , ('e438c01d296a47e9', 'game', 'Bullets spawn a poison cloud on impact. 
Clouds deal damage and slow.', '63c22c07f95b9c77b5278d3b10a80e002f857070', FALSE, 'StringTableCards/CARD_TOXIC_CLOUD_DESC')
  , ('a8834cee75e9ea18', 'game', 'TRICKSTER', '90c4b8a73c7bb53ccfced47868e1d46a633e3629', FALSE, 'StringTableCards/CARD_TRICKSTER')
  , ('f559411bd6b00928', 'game', 'Bullets deal 80% more DMG per bounce', 'b5b743ca14140d1f46ee0d54f4ad9cd52eac6b4f', FALSE, 'StringTableCards/CARD_TRICKSTER_DESC — Damage')
  , ('c07af5ea08c763b7', 'game', 'WIND UP', '4254bda1022380ff63c6b4df5489fe82ac2bdbb2', FALSE, 'StringTableCards/CARD_WIND_UP')
  , ('c750bf9316216979', 'game', 'Ammo', '407c60401b79318f2877683ed6df36f0bda6cfee', FALSE, 'StringTableCards/STAT_AMMO')
  , ('e3ab55dbf190f7a0', 'game', 'ATKSPD', '500b368d2548c54ca3b29a3fff6ec8f61e959fed', FALSE, 'StringTableCards/STAT_ATKSPD — Attack Speed')
  , ('7a2f8bfdc21c1700', 'game', 'Attack Speed', 'f33d401006f73851c505f11dbbcdbc71a877088c', FALSE, 'StringTableCards/STAT_ATTACK_SPEED')
  , ('8c64a22bde49bfff', 'game', 'Block cooldown', 'c07d9b19ee315214241c27deef929d12e1be0e65', FALSE, 'StringTableCards/STAT_BLOCK_COOLDOWN')
  , ('c2145c8238c29395', 'game', 'Bullet', 'b98da0ccc81f4f734434572f19ccc66972aae344', FALSE, 'StringTableCards/STAT_BULLET')
  , ('1c025368bd76b722', 'game', 'Bullets', '7509c5747e5db3dfa3373afc42eca9f5b27a8599', FALSE, 'StringTableCards/STAT_BULLETS')
  , ('756f628a3b169a47', 'game', 'Bullets drill through walls', '54c75b16453513030f98e6cc097b0158d92e2edd', FALSE, 'StringTableCards/STAT_BULLETS_DRILL_THROUGH_WALLS')
  , ('4012cf85c5136b08', 'game', 'Bullet bounce', '12b4854c1fe7f858dba582f76f0630a3db01a6cf', FALSE, 'StringTableCards/STAT_BULLET_BOUNCE')
  , ('28753fa2516fa9a7', 'game', 'Bullet bounces', '62014f1a9ff0c5190b3b038653b4b8b0ce5a9f3c', FALSE, 'StringTableCards/STAT_BULLET_BOUNCES')
  , ('279b058cb2249f39', 'game', 'Bullet slow', '1982b45375c2d30f60024c602fa49444a089bddb', FALSE, 'StringTableCards/STAT_BULLET_SLOW')
  , ('7bd54751dd308e5e', 'game', 'Bullet speed', 'b3ffdc1b829c231e7a4594def624fcbe0e95fa1b', FALSE, 'StringTableCards/STAT_BULLET_SPEED')
  , ('304f8c3468fc9885', 'game', 'DMG', 'f9f8e0e1ab62d56507241796e4d58bf672523306', FALSE, 'StringTableCards/STAT_DMG — Damage')
  , ('644852b751fe9f28', 'game', 'Health', '3703cd216881d3303a10a898fe54439bf05685b6', FALSE, 'StringTableCards/STAT_HEALTH')
  , ('834d2735f544cc7a', 'game', 'HP', '5200bdfc01a139a753c6eb52ee1911cadd069dd9', FALSE, 'StringTableCards/STAT_HP — Health Points')
  , ('4b213ee4dd01cc14', 'game', 'Life steal', '417f106adb9eb8a88f7f754dff056d4ad92f62fa', FALSE, 'StringTableCards/STAT_LIFE_STEAL')
  , ('d24503f7cd674e50', 'game', 'Projectile speed', '4136b3ae32a2e2c8926110d85348d158497cb1aa', FALSE, 'StringTableCards/STAT_PROJECTILE_SPEED')
  , ('6bfdd85f5ded36f0', 'game', 'Reload speed', '634b59c88dd54e7bc5e5537d65050cf556efec66', FALSE, 'StringTableCards/STAT_RELOAD_SPEED')
  , ('0eea28ade399f3c3', 'game', 'Reload time', '5e26878441512323613f2225e1881f25812714aa', FALSE, 'StringTableCards/STAT_RELOAD_TIME')
  , ('e5e8c7a46ed4b12e', 'game', 'Splash DMG', 'f83bdc9ec4bdd67182052b7358c6b54b4a49b185', FALSE, 'StringTableCards/STAT_SPLASH_DMG — Damage')
  , ('25efa481b1fb6700', 'game', 'Back', 'b52b36b7269fbfc58ec24bb724691951a3decbe8', FALSE, 'StringTableDefault/BUTTON_BACK — Action to go back to previous menu')
  , ('b14cb9f81053d278', 'game', 'Block and mute opponent', '0335d5dbbe4561d4eeda25021a567c465906ce25', FALSE, 'StringTableDefault/BUTTON_BLOCK — Block as in blacklisting the player')
  , ('e06dcf032f5a37d2', 'game', 'Manage blocklist', '4c1894bd6aa5379146515a928925ad1ff8c88735', FALSE, 'StringTableDefault/BUTTON_BLOCKLIST')
  , ('58978992916fe6a0', 'game', 'Continue', '2e02623966f9391facf6eaefc8b079ed5b630bee', FALSE, 'StringTableDefault/BUTTON_CONTINUE')
  , ('72ffea5fd21a2465', 'game', 'Get OAUTH', '8db5fed15ee21019f29337511a4422c2b3bf1ce0', FALSE, 'StringTableDefault/BUTTON_GETOAUTH')
  , ('a5213a20493acf09', 'game', 'Host', '3960ec4ca5fb5e5d8cdb2cc1c5121c003e426517', FALSE, 'StringTableDefault/BUTTON_HOST — Verb')
  , ('22de6be221508bd8', 'game', 'Host room', 'e0bf717ef48a6002f8b798ea1e13f80279d0a579', FALSE, 'StringTableDefault/BUTTON_HOSTROOM')
  , ('5aecb28115473fc1', 'game', 'Invite friend', '18d228b022c63aa8346d7ece8fc455f05f14c051', FALSE, 'StringTableDefault/BUTTON_INVITEFRIEND')
  , ('b386ce912e7da2db', 'game', 'Local', 'dc99d54d9990e3c134420be3918e88f28531e630', FALSE, 'StringTableDefault/BUTTON_LOCAL')
  , ('1770758391fafe0f', 'game', 'Main menu', '37646650602612502263cd071e26789b69a70d88', FALSE, 'StringTableDefault/BUTTON_MAINMENU')
  , ('88f039c46bf3aef2', 'game', 'Online', 'c3e839df608469149df1ef34a1c9bb26b62b5452', FALSE, 'StringTableDefault/BUTTON_ONLINE')
  , ('614fa528bd87d77f', 'game', 'Options', '6bf5da9c080bee3a8142586c412aa39971137eee', FALSE, 'StringTableDefault/BUTTON_OPTIONS')
  , ('75b1089a156c0abe', 'game', 'Quick match', 'a370fa498a53d254ea33c4d045026b32ed7b70cc', FALSE, 'StringTableDefault/BUTTON_QUICKMATCH')
  , ('a3e748141eea4dda', 'game', 'Quit', '1a2285d8881f226e13430515a9dd2b9fb6294200', FALSE, 'StringTableDefault/BUTTON_QUIT — Close the game')
  , ('22bca019fe79ef9e', 'game', 'Report opponent', '0ee07ba377d37ab0accfe1f82226824e83b15812', FALSE, 'StringTableDefault/BUTTON_REPORT')
  , ('170c3fd168ea0be6', 'game', 'Resume', 'b3bd0b5a70497bec4a02b7eb1cb0d4f37eb71a2a', FALSE, 'StringTableDefault/BUTTON_RESUME')
  , ('3bdfb7d09a20f37b', 'game', 'Sandbox', '0a771c36be05d64f376a7d57849bb33ee0c53884', FALSE, 'StringTableDefault/BUTTON_SANDBOX')
  , ('29ca0ad33866e932', 'game', 'Save', 'efc007a393f66cdb14d57d385822a3d9e36ef873', FALSE, 'StringTableDefault/BUTTON_SAVE')
  , ('5f8bd23a48bfb8ae', 'game', 'Twitch matchmaking', 'cfe8c15588f8ba75d26a5b2fabe5e381f05f1004', FALSE, 'StringTableDefault/BUTTON_TWITCH — Do no translate "Twitch"')
  , ('7e0a40783617fcb7', 'game', 'Unblock opponent', 'c20a70fb6d864af3710aac16a3e8859972d1ef97', FALSE, 'StringTableDefault/BUTTON_UNBLOCK — Opposite action from above')
  , ('86ab357492065501', 'game', 'Versus', '6c2a9ad9d5afa593beebde44fdababc7ff75a34e', FALSE, 'StringTableDefault/BUTTON_VERSUS')
  , ('773e6de3fed90eab', 'game', 'Detail 1', 'ba3736eeae70ec057418be4390a2bdb189db2b00', FALSE, 'StringTableDefault/CATEGORY_DETAIL1')
  , ('8de9bc69b1fa7a20', 'game', 'Detail 2', '8d8e49016abeb10257cc8a87b2cdb720de04044f', FALSE, 'StringTableDefault/CATEGORY_DETAIL2')
  , ('86a17d42b414bd16', 'game', 'Eyes', '62be7f51429e4e104e01fe3131805c3195ede1d0', FALSE, 'StringTableDefault/CATEGORY_EYES')
  , ('ad08ff14df37c264', 'game', 'Mouths', '8ddd5fb683bbb8507b7a2af05877758767701743', FALSE, 'StringTableDefault/CATEGORY_MOUTHS — Plural')
  , ('3b78230aff37b0bf', 'game', 'Other player left', '3d32564b9b9cc7a7c8b6c71b28839862d67aa664', FALSE, 'StringTableDefault/ERROR_PLAYER_LEFT')
  , ('898597131b854727', 'game', '简体中文', '93659150d0e56377fc3a57cb9bb7d958fd637a74', FALSE, 'StringTableDefault/LANG_CHINESE — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('4500828df2e65566', 'game', 'English', '649df08a448ee3fa90f3746baaf6b0907df42c91', FALSE, 'StringTableDefault/LANG_ENGLISH')
  , ('f472e0b120dc8c99', 'game', 'Français', '2ca514ebd7c3a61fe53823a0785c326287c4ede8', FALSE, 'StringTableDefault/LANG_FRENCH — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('f21a648d0ad01def', 'game', 'Deutsch', 'a6a7709266d3a74cd8c4657eb32a56d5727b91eb', FALSE, 'StringTableDefault/LANG_GERMAN — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('6b7ead97a78496f6', 'game', 'Italiano', '21df73947a06d77d2ad5fe166c8ddfcdc53a6fdb', FALSE, 'StringTableDefault/LANG_ITALIAN — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('ef93fe294836d086', 'game', '日本語', 'c12140a0ffb4e56481b4fe0a7a25040c2eafa9ca', FALSE, 'StringTableDefault/LANG_JAPANESE — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('24f88664dcd4a628', 'game', 'Português (Brasil)', 'd53cc7ed60de7a3d7011da44b3d0e6c11cb1b68d', FALSE, 'StringTableDefault/LANG_PORTUGUESE_BR — 2023-10-23: Replaced the unlocalized name with its translated version
2023-10-17: Added missing "t" in "Portuguese"')
  , ('9b151c658a5ec994', 'game', 'Русский', '5537fc8e69d7e9830f739eb94071c2212b4027ad', FALSE, 'StringTableDefault/LANG_RUSSIAN — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('ad342332ae4f797c', 'game', 'Español', '2001ca082b2d2742765d8ac9182678bfe0374fbf', FALSE, 'StringTableDefault/LANG_SPANISH — 2023-10-23: Replaced the unlocalized name with its translated version')
  , ('cb766e20e27fc2fc', 'game', 'Svenska', 'f344580ac42f760d329f42fd603592846f6ea50b', FALSE, 'StringTableDefault/LANG_SWEDISH — Not used, for testing purposes
2023-10-23: Replaced the unlocalized name with its translated version')
  , ('34aa06074e3d8576', 'game', 'Lock aiming to 8 directions (Controller)', '12f565353f4c5f3481dc7e91cba078f2af9f9a8d', FALSE, 'StringTableDefault/OPTION_CONTROLLER_AIM8DIR — Xbox Terminology: Controller (to take from "Xbox Wireless Controller")')
  , ('58deaa5e3f8e5168', 'game', 'Lock aiming to 8 directions (Controller)', '12f565353f4c5f3481dc7e91cba078f2af9f9a8d', FALSE, 'StringTableDefault/OPTION_CONTROLLER_AIM8DIR_PS — PS Terminology: Controller (to take from "wireless controller")')
  , ('6f6f3c7c31dcf277', 'game', 'Allow cross platform multiplayer', 'a7c388a0ede2c4f26f4295589ab2b13c395d2d34', FALSE, 'StringTableDefault/OPTION_CROSSPLAY')
  , ('7337988d9c68d788', 'game', 'Exclusive Fullscreen', 'de1e144ae13f8076061282171ad9a317ccbdd141', FALSE, 'StringTableDefault/OPTION_EXCLUSIVEFULLSCREEN')
  , ('7e65b027a3e3fb77', 'game', 'Fullscreen Mode', '55d050edae26d24cc822c7a7b3d9b4f00cc44f8f', FALSE, 'StringTableDefault/OPTION_FULLSCREEN')
  , ('6269332e5e9b9dcb', 'game', 'Fullscreen Window', 'd6590b268a500fed2f76419209b48b42acbec865', FALSE, 'StringTableDefault/OPTION_FULLSCREENWINDOW')
  , ('52d71cf9cc89962c', 'game', 'Language', '89b86ab0e66f527166d98df92ddbcf5416ed58f6', FALSE, 'StringTableDefault/OPTION_LANGUAGE')
  , ('2792e878bdb98dbe', 'game', 'Left stick aiming', 'cb308c1c33d95a03cccaadca89fc64592851331f', FALSE, 'StringTableDefault/OPTION_LEFTSTICKAIMING — Xbox Terminology: Left Stick')
  , ('a91acddb9c66607f', 'game', 'Left stick aiming', 'cb308c1c33d95a03cccaadca89fc64592851331f', FALSE, 'StringTableDefault/OPTION_LEFTSTICKAIMING_PS — PS Terminology: Left Stick')
  , ('9acf80614042428d', 'game', 'Maximize Window', '202a9d0d5201007a969ade291e676a04ac106223', FALSE, 'StringTableDefault/OPTION_MAXIMIZEWINDOW')
  , ('0b1f4d1ce7905901', 'game', 'Lock aiming to 8 directions (Mouse)', '002acc9334a6a85859be46cb3c3bb7c47c8613cf', FALSE, 'StringTableDefault/OPTION_MOUSE_AIM8DIR')
  , ('65702329da800b20', 'game', 'Mute Chat', '4fc9b771f03771106b19f552f29437db4e82e5d4', FALSE, 'StringTableDefault/OPTION_MUTE')
  , ('64f83a9de1531aa1', 'game', 'No', '816c52fd2bdd94a63cd0944823a6c0aa9384c103', FALSE, 'StringTableDefault/OPTION_NO')
  , ('f7269abe66c04b31', 'game', 'Resolution', '516aae52959dcf5398a9985414a78b8c24a4f0e5', FALSE, 'StringTableDefault/OPTION_RESOLUTION')
  , ('c9bf79f4e691db5d', 'game', 'Show card stat numbers', 'ca9663eaa2390d8afe9dd01f6980661c2dc8af30', FALSE, 'StringTableDefault/OPTION_SHOWSTATNUMBERS')
  , ('675638018d7fbb3d', 'game', 'Master volume', 'a444d635bd13bba529ac69d96957db504df25517', FALSE, 'StringTableDefault/OPTION_VOLUME_MASTER — Main audio volume')
  , ('52237a4b42e100b7', 'game', 'Music volume', '0d49fceb8d4a4c2a1998a342c9e3bbca56602384', FALSE, 'StringTableDefault/OPTION_VOLUME_MUSIC — 2023-10-17: Fixed a typo in "Music" ("Mucis")')
  , ('a095bbad6cb4b1cd', 'game', 'SFX volume', '7418091711590856caa989340bb1dac687a9f70f', FALSE, 'StringTableDefault/OPTION_VOLUME_SFX — Sound effects volume')
  , ('4c7655180a482cad', 'game', 'V-SYNC', '0babceedb41c6bc469bc9a859dcab6b82a8411e3', FALSE, 'StringTableDefault/OPTION_VSYNC')
  , ('b12c7a7c8d1efcb9', 'game', 'Windowed', '7d22ecce0385c959845f551d5a3b5ab183398dfa', FALSE, 'StringTableDefault/OPTION_WINDOWED')
  , ('138e18857cac5a72', 'game', 'Yes', '5397e0583f14f6c88de06b1ef28f460a1fb5b0ae', FALSE, 'StringTableDefault/OPTION_YES')
  , ('e16b3887c2129190', 'game', 'Being 
Edited', '94d0af801156cf4c3f4cca8b7efaecf25aeaaf0d', FALSE, 'StringTableDefault/PROMPT_BEINGEDITED')
  , ('2841f494f6f6cdd3', 'game', 'You have not blocked any users from other platforms', '3b665f98f5099560a4083a2a787f297c699a51a5', FALSE, 'StringTableDefault/PROMPT_BLOCKLIST_EMPTY — Shown when managing blocklist but the list is empty')
  , ('c032272018bc8288', 'game', '<sprite name=BUTTON_EAST> Cancel', '33fce666d786872962f01375310f69ada281385f', FALSE, 'StringTableDefault/PROMPT_CANCEL_CONTROLLER')
  , ('3f5362876ef8816d', 'game', '[ESC] Cancel', 'd8b97299b3dbc1213b24cc7d3a3d0a220452f6b8', FALSE, 'StringTableDefault/PROMPT_CANCEL_MOUSE')
  , ('ac777af161d15bde', 'game', 'Continue?', '4e6302ed03494c9085e960acbd0bb635e148ed80', FALSE, 'StringTableDefault/PROMPT_CONTINUE')
  , ('172d14a4aa6b80e1', 'game', 'Disconnected', '771e05f27b99fd59f638f41a7a4e977b1d4691fe', FALSE, 'StringTableDefault/PROMPT_DISCONNECT')
  , ('4b4e998d002aa314', 'game', 'Enter card name', 'dcfdf8113edb226febe26c5bbd29e7ffce9b6075', FALSE, 'StringTableDefault/PROMPT_ENTER_CARD_NAME')
  , ('5be23ab4dd2dbd3a', 'game', 'Enter chat message', 'fa99bae9c84a05cb3c9d2b65df0abd496e728db9', FALSE, 'StringTableDefault/PROMPT_ENTER_CHAT_MESSAGE')
  , ('930d340d5de3eafd', 'game', 'Half Blue', '40b746d43e17c67de98407d8d7f0a76a389bca04', FALSE, 'StringTableDefault/PROMPT_HALF_BLUE')
  , ('37d2b1b1c8b23a69', 'game', 'Half Orange', '70df01119382511ae43afdafff14d67d7a16f7c8', FALSE, 'StringTableDefault/PROMPT_HALF_ORANGE')
  , ('db241e1d44efebf0', 'game', 'Waiting for', '20e0b197969178eebc409975c732488b57d52839', FALSE, 'StringTableDefault/PROMPT_HOSTING')
  , ('147271f0b1b11c48', 'game', '<sprite name=BUTTON_WEST> To join room', 'cbe55da30bff13c4cb08fa7139870c0fc260385e', FALSE, 'StringTableDefault/PROMPT_JOINROOM')
  , ('54fcd59ad6dea5f5', 'game', 'Press enter key to join with roomcode', 'be54c03cac3d35478d0776ba7fd7440b95bb5937', FALSE, 'StringTableDefault/PROMPT_JOINROOM_ENTER')
  , ('400e7c9ceac83d8a', 'game', 'Press jump
to join', '48beb18d1e3cd72aaa6740af8058b1a545be0aa3', FALSE, 'StringTableDefault/PROMPT_JUMP_TO_JOIN')
  , ('206cc9338e586cf5', 'game', 'LET''S GOO!', '99a01cdc098e5a37f53c20fb706c096e097e09ef', FALSE, 'StringTableDefault/PROMPT_LETSGO — 2023-10-17: Added missing apostrophe in "LET''S".')
  , ('50ddb14a1a0ebbbe', 'game', 'Match found', '14846ed7d50293587e98be171845ca9900f7e207', FALSE, 'StringTableDefault/PROMPT_MATCHFOUND')
  , ('fcd7c1e7500aa9d6', 'game', 'To move items', 'ac9bca845b7b754ba930e7a133eeb8fc5946d006', FALSE, 'StringTableDefault/PROMPT_MOVE_ITEMS')
  , ('83d97e35f6f9a3e4', 'game', '[RIGHT STICK]
To move items', '1df8742b04067aaa6bb9f9630983534f7e52c794', FALSE, 'StringTableDefault/PROMPT_MOVE_ITEMS_CONTROLLER')
  , ('3d78d0a5bb742b0b', 'game', '[RIGHT STICK]
To move items', '1df8742b04067aaa6bb9f9630983534f7e52c794', FALSE, 'StringTableDefault/PROMPT_MOVE_ITEMS_CONTROLLER_PS — PS Terminology')
  , ('20a3c59e0a2ebcf4', 'game', 'Pick one', '490fd462becfdea6fe54ee4160229f09ae5f4178', FALSE, 'StringTableDefault/PROMPT_PICKONE')
  , ('8f6303a38f0e3f52', 'game', 'Ready', '20c7c5522fc28c5817550dd82bc3272eb6a991c7', FALSE, 'StringTableDefault/PROMPT_READY')
  , ('14ac400eb74d19bd', 'game', 'Rematch?', '2b8ca1c6f332d7ac6f7dc56c8abc7aceaae03d75', FALSE, 'StringTableDefault/PROMPT_REMATCH')
  , ('5390ad8a16180923', 'game', 'Roomcode: {ROOMCODE}', 'ab2966c3678546323d365369fae08e7a4eda6ce8', FALSE, 'StringTableDefault/PROMPT_ROOMCODE')
  , ('f8f0279d2c6f32dd', 'game', 'Round Blue', 'aa66f9301cd5132398ccebb906809c284e321c08', FALSE, 'StringTableDefault/PROMPT_ROUND_BLUE')
  , ('59f9beed30cbc149', 'game', 'Round Orange', '56a03cc77d4a6b636621118f0e0e4af7ee180cca', FALSE, 'StringTableDefault/PROMPT_ROUND_ORANGE')
  , ('6ff4816bd7be86fa', 'game', 'Press <sprite name=BUTTON_NORTH> to open text input
Type names of the cards to spawn them
Shoot the cards to pick them', '8881d7e62e56565f8dea1d988f38d923617623ad', FALSE, 'StringTableDefault/PROMPT_SANDBOX_CONTROLLER')
  , ('468d3f428f3909bf', 'game', 'Press enter to chat
Type names of the cards to spawn them
Shoot the cards to pick them', '7dc68189b96ecec024485a3328c4a307f5f160c9', FALSE, 'StringTableDefault/PROMPT_SANDBOX_MOUSE')
  , ('0725d81ee01070b9', 'game', 'Searching', '98cc363c0119e35d1c8070755fc4d4c2387aad71', FALSE, 'StringTableDefault/PROMPT_SEARCHING')
  , ('1754376f6be23625', 'game', 'Press
[<sprite name=BUTTON_SOUTH>]
to join', '819fd6c09f58c6d18d248de0a4100cc6a42567fd', FALSE, 'StringTableDefault/PROMPT_SOUTH_TO_JOIN')
  , ('3b26d48525873580', 'game', 'Press
[SPACE]
to join', '165c7d6cfbeef2876075725c4166be0c612ebb20', FALSE, 'StringTableDefault/PROMPT_SPACE_TO_JOIN')
  , ('d2f82d54461dd992', 'game', 'Press
[<sprite name=BUTTON_START>]
to save', '8aeb98f766a942b626836ca0bb0556dce68a8593', FALSE, 'StringTableDefault/PROMPT_START_TO_SAVE')
  , ('65c15ec0c162c4b3', 'game', 'Press [<sprite name=BUTTON_START>] when ready', 'd759a34e84df44091ff5dfc06ca78d66c960a21f', FALSE, 'StringTableDefault/PROMPT_START_WHEN_READY')
  , ('ad65a56975f3e7b4', 'game', 'To edit', '1b83a841db1d77b3da9721da75ae6856edbcda21', FALSE, 'StringTableDefault/PROMPT_TOEDIT')
  , ('9d8c564216c4fca8', 'game', 'Victory!', '25296a531b53ddf34c2ed0da107c44afa1167d07', FALSE, 'StringTableDefault/PROMPT_VICTORY')
  , ('5b92f3c6a6bc9bba', 'game', 'VS', 'b8a1e1dc56dfb4912a6dd518664883f8000965ae', FALSE, 'StringTableDefault/PROMPT_VS — Versus')
  , ('9a146c1abc14a051', 'game', 'Waiting', '33d30632848d3fd0ed2340adbd7be3e3e8e61010', FALSE, 'StringTableDefault/PROMPT_WAITING')
  , ('9b6756e2e3392101', 'game', 'Waiting for friend', 'd0481d10e87426be70e916ceb26124fd75be3f9e', FALSE, 'StringTableDefault/PROMPT_WAITING_FOR_FRIEND')
  , ('0f2503e67bb0f23f', 'game', 'Press [SPACE] when ready', 'c5a34c2887680c7eaf3082c6984bf4aa4f56160a', FALSE, 'StringTableDefault/PROMT_SPACE_WHEN_READY')
;

DO $sync410$
DECLARE
  n_client INT; n_game INT; n_ids INT;
  live_client INT; live_game INT;
  n_seen INT; n_retire INT; n_retired INT; n_sup INT; n_sup_ret INT;
  n_bad INT;
BEGIN
  SELECT count(*) INTO n_client FROM _sync410 WHERE namespace = 'client';
  SELECT count(*) INTO n_game FROM _sync410 WHERE namespace = 'game';
  SELECT count(DISTINCT key_id) INTO n_ids FROM _sync410;
  IF n_client <> 3779 OR n_game <> 242 OR n_ids <> 4021 THEN
    RAISE EXCEPTION 'migration 410: the manifest holds % client and % game keys (% ids), expected 3779, 242 and 4021',
      n_client, n_game, n_ids;
  END IF;
  SELECT count(*) INTO live_client FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  SELECT count(*) INTO live_game FROM i18n_keys WHERE namespace = 'game' AND retired_at IS NULL;
  IF (live_client > 0 AND n_client < live_client * 0.9) OR (live_game > 0 AND n_game < live_game * 0.9) THEN
    RAISE EXCEPTION 'migration 410: the manifest would retire more than 10%% of a namespace (% client and % game keys live)',
      live_client, live_game;
  END IF;

  INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
  SELECT m.key_id, m.namespace, m.msgctxt, m.source_hash, m.sensitive, NULL, m.context, NOW()
    FROM _sync410 m
  ON CONFLICT (key_id) DO UPDATE SET namespace = EXCLUDED.namespace,
    msgctxt = EXCLUDED.msgctxt, source_hash = EXCLUDED.source_hash,
    sensitive = EXCLUDED.sensitive, max_px = EXCLUDED.max_px,
    context = EXCLUDED.context,
    retired_at = NULL, updated_at = NOW();
  GET DIAGNOSTICS n_seen = ROW_COUNT;

  INSERT INTO _retired410 (key_id)
  SELECT k.key_id FROM i18n_keys k
   WHERE k.retired_at IS NULL AND k.namespace IN ('client', 'game')
     AND NOT EXISTS (SELECT 1 FROM _sync410 m WHERE m.key_id = k.key_id);
  GET DIAGNOSTICS n_retire = ROW_COUNT;
  UPDATE i18n_keys k SET retired_at = NOW()
   WHERE k.retired_at IS NULL
     AND EXISTS (SELECT 1 FROM _retired410 r WHERE r.key_id = k.key_id);
  GET DIAGNOSTICS n_retired = ROW_COUNT;
  IF n_retired <> n_retire THEN
    RAISE EXCEPTION 'migration 410: % keys selected to retire, % retired', n_retire, n_retired;
  END IF;

  UPDATE i18n_proposals p SET status = 'superseded',
         review_note = 'source changed at key sync', reviewed_at = NOW()
    FROM i18n_keys k
   WHERE p.key_id = k.key_id AND p.status = 'pending'
     AND EXISTS (SELECT 1 FROM _sync410 m WHERE m.key_id = k.key_id)
     AND p.source_hash <> k.source_hash;
  GET DIAGNOSTICS n_sup = ROW_COUNT;
  UPDATE i18n_proposals p SET status = 'superseded',
         review_note = 'key retired at key sync', reviewed_at = NOW()
   WHERE p.status = 'pending'
     AND EXISTS (SELECT 1 FROM _retired410 r WHERE r.key_id = p.key_id);
  GET DIAGNOSTICS n_sup_ret = ROW_COUNT;

  INSERT INTO i18n_review_events (actor_steam_id, actor_role, language_code, key_id, action, detail)
  VALUES ('76561198040410653', 'admin', 'all', NULL, 'sync_keys',
          n_seen::text || ' keys, ' || n_retired::text || ' retired, ' || n_sup::text || ' superseded, '
          || n_sup_ret::text || ' superseded (retired); migration 410');

  SELECT count(*) INTO n_bad FROM _sync410 m
   WHERE NOT EXISTS (
           SELECT 1 FROM i18n_keys k
            WHERE k.key_id = m.key_id AND k.retired_at IS NULL
              AND k.namespace = m.namespace AND k.msgctxt = m.msgctxt
              AND k.source_hash = m.source_hash AND k.sensitive = m.sensitive
              AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM m.context);
  IF n_bad <> 0 THEN
    RAISE EXCEPTION 'post-check FAILED: % manifest keys are not live with the manifest''s values', n_bad;
  END IF;
  SELECT count(*) INTO n_bad FROM i18n_keys k
   WHERE k.retired_at IS NULL AND k.namespace IN ('client', 'game')
     AND NOT EXISTS (SELECT 1 FROM _sync410 m WHERE m.key_id = k.key_id);
  IF n_bad <> 0 THEN
    RAISE EXCEPTION 'post-check FAILED: % live keys are outside the manifest', n_bad;
  END IF;
  SELECT count(*) INTO n_bad FROM i18n_proposals p
   WHERE p.status = 'pending'
     AND EXISTS (SELECT 1 FROM _retired410 r WHERE r.key_id = p.key_id);
  IF n_bad <> 0 THEN
    RAISE EXCEPTION 'post-check FAILED: % pending proposals remain on keys this run retired', n_bad;
  END IF;
  RAISE NOTICE 'migration 410: % keys synced, % retired, % superseded, % superseded (retired); live before % client and % game',
    n_seen, n_retired, n_sup, n_sup_ret, live_client, live_game;
END $sync410$;

COMMIT;

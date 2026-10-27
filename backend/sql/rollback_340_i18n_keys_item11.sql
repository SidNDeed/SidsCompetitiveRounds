-- rollback_340_i18n_keys_item11.sql
-- Reverses the item-11 re-key of migration 340 and retires the proposal seeds
-- 341 attached to the successor keys. Data only: no code reads these keys by
-- name, so this file is independent of the api deploy order. NOT a
-- release-train migration. Explicit transaction (learning #340).
--
-- What it does: the three predecessor keys go live again, the three successor
-- keys are retired, and every pending proposal on a successor key (the twelve
-- machine seeds of 341, plus anything proposed on them since) is marked
-- superseded. What it leaves: the proposals 340 marked superseded on the
-- predecessor keys stay superseded (a translator re-proposes through the
-- portal if that text is wanted again), and approved entries on either side
-- are never written; an approved entry on a retired key is hidden with its
-- key and reappears if the key is ever un-retired.

BEGIN;

UPDATE i18n_keys
   SET retired_at = NULL, updated_at = NOW()
 WHERE key_id IN ('c4facebcda2e750a', 'c14135018e41f6f6', 'c84c43c265080ec2')
   AND retired_at IS NOT NULL;

UPDATE i18n_keys
   SET retired_at = NOW(), updated_at = NOW()
 WHERE key_id IN ('fc07ba40fe031c27', 'd89523ad6cb44ac1', '7d2c24d463786026')
   AND retired_at IS NULL;

UPDATE i18n_proposals
   SET status = 'superseded'
 WHERE key_id IN ('fc07ba40fe031c27', 'd89523ad6cb44ac1', '7d2c24d463786026')
   AND status = 'pending';

COMMIT;

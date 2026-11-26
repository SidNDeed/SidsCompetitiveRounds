"""MODLOG-1 ruling 4: the class of every route of main.app (the census
test_modlog_census.py walks). Each row: (method, path) -> (class, family
or reason, writers). MOD = a moderator action on a player or on a
player's result: every function in `writers` holds a _modlog_write call
and the endpoint reaches it. NOT = not such an action, with a reason word
of REASONS; a NOT row that names writers records anyway (an action on no
player, or a system action on the way) and is in the reach check too.
"""

MOD = "MOD"
NOT = "NOT"

FAMILIES = ("bans", "chat", "mail_case", "results", "cards", "grants")
# read: a GET (it changes no moderator state); own: the caller's own
# account, settings, mail, cards or submissions; gameplay: queues, lobbies,
# matches, series, bets, spectating, tournaments and the evidence a game
# sends; service: the bot's and the deploy tools' plumbing (acks, outbox,
# leases, posts, name sync); config: an admin's or a moderator's change to
# the server or its content, not to a player; automatic: a grant the server
# makes from an outside event; read_upkeep: a GET that answers a read and
# also keeps the server's own state on the way (a cache, a heartbeat or a
# poll's step, a delivery attempt, a session's refresh, a read audit),
# changing no moderator state on a player (fix A6: 'read' is checked).
REASONS = ("read", "read_upkeep", "own", "gameplay", "service", "config", "automatic")

CENSUS = {
    ('POST', '/api/v1/admin/artists/set'): (MOD, 'grants', (('main', 'admin_set_artist'), )),  # main.admin_set_artist
    ('POST', '/api/v1/admin/ban'): (MOD, 'bans', (('main', '_apply_ban_core'), ('main', '_ban_set_length_core'), ('main', '_ban_rate_gate_or_raise'), )),  # main.admin_ban
    ('POST', '/api/v1/admin/ban/details'): (MOD, 'bans', (('main', 'admin_ban_details'), )),  # main.admin_ban_details (BAN-RECORD-1)
    ('POST', '/api/v1/admin/cosmetic-review'): (MOD, 'grants', (('main', '_admin_cosmetic_review_impl'), )),  # main.admin_cosmetic_review
    ('POST', '/api/v1/admin/ffa-g3-seats'): (MOD, 'grants', (('main', 'admin_ffa_g3_seat'), )),  # main.admin_ffa_g3_seat
    ('POST', '/api/v1/admin/grant-achievement'): (MOD, 'grants', (('main', 'admin_grant_achievement'), )),  # main.admin_grant_achievement
    ('POST', '/api/v1/admin/i18n/grants'): (MOD, 'grants', (('main', 'admin_i18n_grant'), )),  # main.admin_i18n_grant
    ('POST', '/api/v1/admin/mail/bulk-grants'): (MOD, 'grants', (('main', 'admin_mail_bulk_grant'), )),  # main.admin_mail_bulk_grant
    ('DELETE', '/api/v1/admin/mail/bulk-grants/{steam_id}'): (MOD, 'grants', (('main', 'admin_mail_bulk_grant_revoke'), )),  # main.admin_mail_bulk_grant_revoke
    ('POST', '/api/v1/admin/moderation-cases/{case_id}/act'): (MOD, 'mail_case', (('main', '_moderation_case_act'), ('main', '_apply_ban_core'), )),  # main.admin_moderation_case_act
    ('POST', '/api/v1/admin/pc/portrait/clear'): (MOD, 'cards', (('main', 'admin_pc_portrait_clear'), )),  # main.admin_pc_portrait_clear
    ('POST', '/api/v1/admin/pc/trades/reverse'): (MOD, 'cards', (('main', '_admin_pc_trade_reverse_tx'), )),  # main.admin_pc_trade_reverse
    ('POST', '/api/v1/admin/quarantine/{qid}/accept'): (MOD, 'results', (('main', '_qapply_finish'), )),  # main.admin_accept_quarantine
    ('POST', '/api/v1/admin/quarantine/{qid}/credit'): (MOD, 'results', (('main', '_qapply_credit'), )),  # main.admin_credit_quarantine
    ('POST', '/api/v1/admin/quarantine/{qid}/discard'): (MOD, 'results', (('main', 'admin_discard_quarantine'), )),  # main.admin_discard_quarantine
    ('POST', '/api/v1/admin/records/exclude'): (MOD, 'results', (('main', 'admin_record_exclude'), )),  # main.admin_record_exclude
    ('POST', '/api/v1/admin/resolve-flag-restoration'): (MOD, 'results', (('main', 'admin_resolve_flag_restoration'), )),  # main.admin_resolve_flag_restoration
    ('POST', '/api/v1/admin/reverse-series'): (MOD, 'results', (('main', 'admin_reverse_series'), )),  # main.admin_reverse_series
    ('POST', '/api/v1/admin/review-flag'): (MOD, 'results', (('main', 'admin_review_flag'), )),  # main.admin_review_flag
    ('POST', '/api/v1/admin/team/rebuild-glicko'): (MOD, 'results', (('main', 'admin_rebuild_team_glicko'), ('main', '_modlog_rebuild_start'), )),  # main.admin_rebuild_team_glicko
    ('POST', '/api/v1/admin/team/reverse-series'): (MOD, 'results', (('main', 'admin_reverse_team_series'), )),  # main.admin_reverse_team_series
    ('POST', '/api/v1/admin/team/series/{series_id}/resolve'): (MOD, 'results', (('main', 'admin_resolve_team_series'), )),  # main.admin_resolve_team_series
    ('POST', '/api/v1/admin/unban'): (MOD, 'bans', (('main', 'admin_unban'), )),  # main.admin_unban
    ('POST', '/api/v1/chat/moderate/bridge-unmute'): (MOD, 'chat', (('main', 'chat_moderate_bridge_unmute'), )),  # main.chat_moderate_bridge_unmute
    ('POST', '/api/v1/chat/moderate/delete'): (MOD, 'chat', (('main', 'chat_moderate_delete'), )),  # main.chat_moderate_delete
    ('POST', '/api/v1/chat/moderate/mute'): (MOD, 'chat', (('main', 'chat_moderate_mute'), )),  # main.chat_moderate_mute
    ('POST', '/api/v1/chat/moderate/mute-by-message'): (MOD, 'chat', (('main', 'chat_moderate_mute_by_message'), )),  # main.chat_moderate_mute_by_message
    ('POST', '/api/v1/chat/moderate/unmute'): (MOD, 'chat', (('main', 'chat_moderate_unmute'), )),  # main.chat_moderate_unmute
    ('POST', '/api/v1/internal/chat/bridge-moderation'): (MOD, 'chat', (('main', 'internal_chat_bridge_moderation'), )),  # main.internal_chat_bridge_moderation
    ('POST', '/api/v1/internal/chat/discord-deleted'): (MOD, 'chat', (('main', 'internal_chat_discord_deleted'), )),  # main.internal_chat_discord_deleted
    ('POST', '/api/v1/internal/chat/discord-mute'): (MOD, 'chat', (('main', 'internal_chat_discord_mute'), )),  # main.internal_chat_discord_mute
    ('POST', '/api/v1/internal/moderation-cases/{case_id}/act'): (MOD, 'mail_case', (('main', '_moderation_case_act'), ('main', '_apply_ban_core'), )),  # main.internal_moderation_case_act
    ('GET', '/api/v1/achievements/definitions'): (NOT, 'read', ()),  # main.get_achievement_definitions
    ('POST', '/api/v1/achievements/unlock'): (NOT, 'gameplay', ()),  # main.unlock_achievement
    ('GET', '/api/v1/achievements/{key}/earners'): (NOT, 'read_upkeep', ()),  # main.get_achievement_earners
    ('GET', '/api/v1/achievements/{steam_id}'): (NOT, 'read', ()),  # main.get_player_achievements
    ('GET', '/api/v1/admin/actions'): (NOT, 'read', ()),  # main.admin_list_actions
    ('GET', '/api/v1/admin/admins'): (NOT, 'read', ()),  # main.admin_list_admins
    ('POST', '/api/v1/admin/alerts'): (NOT, 'config', (('main', 'admin_alert_create'), )),  # main.admin_alert_create
    ('GET', '/api/v1/admin/alerts/list'): (NOT, 'read', ()),  # main.admin_alerts_list
    ('POST', '/api/v1/admin/alerts/revoke'): (NOT, 'config', (('main', 'admin_alert_revoke'), )),  # main.admin_alert_revoke
    ('GET', '/api/v1/admin/banned-users'): (NOT, 'read', ()),  # main.admin_list_bans
    ('GET', '/api/v1/admin/bans/links'): (NOT, 'read', ()),  # main.admin_ban_links (ALT-BAN-1: a read, no log row)
    ('GET', '/api/v1/admin/card-evidence'): (NOT, 'read', ()),  # main.admin_card_evidence
    ('POST', '/api/v1/admin/card-pool-census'): (NOT, 'config', ()),  # main.admin_register_card_census
    ('GET', '/api/v1/admin/check-status'): (NOT, 'read', ()),  # main.admin_check_status
    ('GET', '/api/v1/admin/combat-evidence'): (NOT, 'read', ()),  # main.admin_combat_evidence
    ('GET', '/api/v1/admin/cosmetic-frames'): (NOT, 'read', ()),  # main.admin_cosmetic_frames
    ('GET', '/api/v1/admin/cosmetic-release-candidates'): (NOT, 'read', ()),  # main.admin_cosmetic_release_candidates
    ('GET', '/api/v1/admin/cosmetic-submissions'): (NOT, 'read', ()),  # main.admin_cosmetic_submissions
    ('GET', '/api/v1/admin/flagged-matches'): (NOT, 'read', ()),  # main.admin_list_flagged
    ('POST', '/api/v1/admin/game-file-digests'): (NOT, 'config', ()),  # main.admin_register_game_file_digest
    ('GET', '/api/v1/admin/i18n/grants/list'): (NOT, 'read', ()),  # main.admin_i18n_grants_list
    ('POST', '/api/v1/admin/i18n/sync-keys'): (NOT, 'config', ()),  # main.admin_i18n_sync_keys
    ('GET', '/api/v1/admin/identity-clock-evidence'): (NOT, 'read', ()),  # main.admin_identity_clock_evidence
    ('POST', '/api/v1/admin/mail/broadcast'): (NOT, 'config', (('main', 'admin_mail_broadcast'), )),  # main.admin_mail_broadcast
    ('POST', '/api/v1/admin/maintenance/start'): (NOT, 'config', ()),  # main.maintenance_start
    ('GET', '/api/v1/admin/maintenance/status'): (NOT, 'read', ()),  # main.maintenance_status
    ('POST', '/api/v1/admin/maintenance/stop'): (NOT, 'config', ()),  # main.maintenance_stop
    ('GET', '/api/v1/admin/missing-discord-usernames'): (NOT, 'read', ()),  # main.missing_discord_usernames
    ('GET', '/api/v1/admin/moderation-cases'): (NOT, 'read', ()),  # main.admin_moderation_cases
    ('POST', '/api/v1/admin/moderation-cases/{case_id}/notified'): (NOT, 'config', ()),  # main.admin_moderation_case_notified
    ('GET', '/api/v1/admin/modlog'): (NOT, 'read', ()),  # main.admin_modlog
    ('GET', '/api/v1/admin/operators'): (NOT, 'read', ()),  # main.admin_operator_list
    ('POST', '/api/v1/admin/operators/keys'): (NOT, 'config', (('main', 'admin_operator_key_issue'), )),  # main.admin_operator_key_issue
    ('POST', '/api/v1/admin/operators/keys/revoke'): (NOT, 'config', (('main', 'admin_operator_key_revoke'), )),  # main.admin_operator_key_revoke
    ('POST', '/api/v1/admin/pc/snapshot'): (NOT, 'config', (('main', 'admin_pc_snapshot'), )),  # main.admin_pc_snapshot
    ('GET', '/api/v1/admin/pc/trades'): (NOT, 'read', ()),  # main.admin_pc_trades
    ('GET', '/api/v1/admin/quarantine'): (NOT, 'read', ()),  # main.admin_list_quarantine
    ('GET', '/api/v1/admin/quarantine/triage'): (NOT, 'read_upkeep', ()),  # main.admin_quarantine_triage
    ('GET', '/api/v1/admin/quarantine/triage/{mode}/{group_id}'): (NOT, 'read_upkeep', ()),  # main.admin_quarantine_triage_group
    ('GET', '/api/v1/admin/read-census'): (NOT, 'read', ()),  # main.admin_read_census
    ('POST', '/api/v1/admin/read-gate/mode'): (NOT, 'config', (('main', 'admin_read_gate_mode'), )),  # main.admin_read_gate_mode
    ('GET', '/api/v1/admin/recent-series'): (NOT, 'read', ()),  # main.admin_recent_series
    ('POST', '/api/v1/admin/release-digests'): (NOT, 'config', ()),  # main.admin_register_release_digest
    ('POST', '/api/v1/admin/release-notes'): (NOT, 'config', ()),  # main.admin_set_release_notes
    ('GET', '/api/v1/admin/seat-evidence'): (NOT, 'read', ()),  # main.admin_seat_evidence
    ('POST', '/api/v1/admin/set-discord-username'): (NOT, 'service', ()),  # main.set_discord_username
    ('POST', '/api/v1/admin/shop/set-artist'): (NOT, 'config', (('main', 'admin_set_item_artist'), )),  # main.admin_set_item_artist
    ('GET', '/api/v1/alerts/active'): (NOT, 'read', ()),  # main.alerts_active
    ('POST', '/api/v1/artist/block'): (NOT, 'own', ()),  # main.artist_block
    ('POST', '/api/v1/artist/catalog-cosmetic-placement'): (NOT, 'own', ()),  # main.artist_catalog_cosmetic_placement
    ('POST', '/api/v1/artist/cosmetic-placement'): (NOT, 'own', ()),  # main.artist_cosmetic_placement
    ('GET', '/api/v1/artist/cosmetic-preview'): (NOT, 'read', ()),  # main.artist_cosmetic_preview
    ('POST', '/api/v1/artist/gift'): (NOT, 'own', ()),  # main.artist_gift
    ('GET', '/api/v1/artist/my-submissions'): (NOT, 'read', ()),  # main.artist_my_submissions
    ('POST', '/api/v1/artist/set-desc'): (NOT, 'own', ()),  # main.artist_set_desc
    ('POST', '/api/v1/artist/set-name'): (NOT, 'own', ()),  # main.artist_set_name
    ('POST', '/api/v1/artist/set-price'): (NOT, 'own', ()),  # main.artist_set_price
    ('POST', '/api/v1/artist/set-stock'): (NOT, 'own', ()),  # main.artist_set_stock
    ('GET', '/api/v1/artist/status/{steam_id}'): (NOT, 'read', ()),  # main.artist_status
    ('POST', '/api/v1/artist/submit-cosmetic'): (NOT, 'own', ()),  # main.artist_submit_cosmetic
    ('POST', '/api/v1/artist/submit-cosmetic-finalize'): (NOT, 'own', ()),  # main.artist_submit_cosmetic_finalize
    ('POST', '/api/v1/artist/submit-cosmetic-frame'): (NOT, 'own', ()),  # main.artist_submit_cosmetic_frame
    ('POST', '/api/v1/artist/submit-cosmetic-gif'): (NOT, 'own', ()),  # main.artist_submit_cosmetic_gif
    ('GET', '/api/v1/artist/{steam_id}/items'): (NOT, 'read', ()),  # main.artist_items
    ('GET', '/api/v1/artist/{steam_id}/sales'): (NOT, 'read', ()),  # main.artist_sales
    ('GET', '/api/v1/artists'): (NOT, 'read', ()),  # main.list_artists
    ('POST', '/api/v1/auth/steam'): (NOT, 'own', ()),  # main.steam_auth
    ('POST', '/api/v1/bets'): (NOT, 'gameplay', ()),  # main.place_bet
    ('GET', '/api/v1/broadcast/report-status'): (NOT, 'read', ()),  # main.broadcast_report_status
    ('GET', '/api/v1/broadcast/target'): (NOT, 'read_upkeep', ()),  # main.broadcast_target
    ('GET', '/api/v1/bug-reports'): (NOT, 'read', ()),  # main.list_bug_reports
    ('POST', '/api/v1/bug-reports'): (NOT, 'own', ()),  # main.submit_bug_report
    ('GET', '/api/v1/bug-reports/events/recent'): (NOT, 'read', ()),  # main.recent_bug_report_events
    ('GET', '/api/v1/bug-reports/recent'): (NOT, 'read', ()),  # main.recent_bug_reports
    ('GET', '/api/v1/bug-reports/{report_id}'): (NOT, 'read', ()),  # main.get_bug_report
    ('POST', '/api/v1/bug-reports/{report_id}/comment'): (NOT, 'config', ()),  # main.admin_comment_on_bug_report
    ('GET', '/api/v1/bug-reports/{report_id}/log'): (NOT, 'read', ()),  # main.download_bug_report_log
    ('POST', '/api/v1/bug-reports/{report_id}/status'): (NOT, 'config', ()),  # main.admin_change_bug_report_status
    ('GET', '/api/v1/cards'): (NOT, 'read', ()),  # main.get_card_stats
    ('GET', '/api/v1/cards/leaders-summary'): (NOT, 'read', ()),  # main.get_card_leaders_summary
    ('GET', '/api/v1/cards/pickers-summary'): (NOT, 'read', ()),  # main.get_card_pickers_summary
    ('GET', '/api/v1/cards/top-pickers'): (NOT, 'read', ()),  # main.get_card_top_pickers
    ('POST', '/api/v1/chat/moderate/lockdown'): (NOT, 'config', (('main', '_set_chat_lockdown'), )),  # main.chat_moderate_lockdown
    ('GET', '/api/v1/chat/moderate/mutes'): (NOT, 'read_upkeep', ()),  # main.chat_moderate_list_mutes
    ('GET', '/api/v1/chat/moderate/spam-patterns'): (NOT, 'read', ()),  # main.chat_moderate_spam_patterns
    ('POST', '/api/v1/chat/moderate/spam-patterns/add'): (NOT, 'config', (('main', 'chat_moderate_spam_pattern_add'), )),  # main.chat_moderate_spam_pattern_add
    ('POST', '/api/v1/chat/moderate/spam-patterns/revoke'): (NOT, 'config', (('main', 'chat_moderate_spam_pattern_revoke'), )),  # main.chat_moderate_spam_pattern_revoke
    ('POST', '/api/v1/chat/post'): (NOT, 'own', (('main', '_chat_censor_strike'), )),  # main.post_chat_from_discord
    ('GET', '/api/v1/chat/recent'): (NOT, 'read_upkeep', ()),  # main.get_recent_chat
    ('POST', '/api/v1/client/compat-outcome'): (NOT, 'own', ()),  # main.submit_compat_outcome
    ('GET', '/api/v1/compare/nemesis'): (NOT, 'read', ()),  # main.get_compare_nemesis
    ('GET', '/api/v1/compare/player-nemesis'): (NOT, 'read', ()),  # main.get_compare_player_nemesis
    ('POST', '/api/v1/discord-bets'): (NOT, 'gameplay', ()),  # main.place_discord_bet
    ('POST', '/api/v1/discord-ffa-bets'): (NOT, 'gameplay', ()),  # main.place_discord_ffa_bet
    ('POST', '/api/v1/discord-lobby-bets'): (NOT, 'gameplay', ()),  # main.place_discord_lobby_bet
    ('POST', '/api/v1/discord-team-bets'): (NOT, 'gameplay', ()),  # main.place_discord_team_bet
    ('POST', '/api/v1/ffa/bets'): (NOT, 'gameplay', ()),  # main.place_ffa_bet
    ('GET', '/api/v1/ffa/bettable'): (NOT, 'read', ()),  # main.ffa_bettable
    ('GET', '/api/v1/ffa/leaderboard'): (NOT, 'read_upkeep', ()),  # main.ffa_leaderboard
    ('GET', '/api/v1/ffa/lobbies'): (NOT, 'read_upkeep', ()),  # main.ffa_lobby_browser
    ('POST', '/api/v1/ffa/lobbies/{lobby_id}/live-points'): (NOT, 'gameplay', ()),  # main.update_ffa_live_points
    ('POST', '/api/v1/ffa/lobby/create'): (NOT, 'gameplay', ()),  # main.ffa_lobby_create
    ('POST', '/api/v1/ffa/lobby/join'): (NOT, 'gameplay', ()),  # main.ffa_lobby_join
    ('POST', '/api/v1/ffa/lobby/kick'): (NOT, 'gameplay', ()),  # main.ffa_lobby_kick
    ('POST', '/api/v1/ffa/lobby/settings'): (NOT, 'gameplay', ()),  # main.ffa_lobby_settings
    ('POST', '/api/v1/ffa/lobby/start'): (NOT, 'gameplay', ()),  # main.ffa_lobby_start
    ('POST', '/api/v1/ffa/lobby/{lobby_id}/assembly'): (NOT, 'gameplay', ()),  # main.ffa_lobby_assembly
    ('POST', '/api/v1/ffa/lobby/{lobby_id}/connect'): (NOT, 'gameplay', ()),  # main.ffa_lobby_connect
    ('POST', '/api/v1/ffa/lobby/{lobby_id}/readmit'): (NOT, 'gameplay', ()),  # main.ffa_lobby_readmit
    ('POST', '/api/v1/ffa/lobby/{lobby_id}/release'): (NOT, 'gameplay', ()),  # main.ffa_lobby_release
    ('POST', '/api/v1/ffa/matches'): (NOT, 'gameplay', ()),  # main.submit_ffa_match
    ('POST', '/api/v1/ffa/queue/join'): (NOT, 'gameplay', ()),  # main.ffa_queue_join
    ('POST', '/api/v1/ffa/queue/leave'): (NOT, 'gameplay', ()),  # main.ffa_queue_leave
    ('GET', '/api/v1/ffa/queue/list'): (NOT, 'read', ()),  # main.ffa_queue_list
    ('GET', '/api/v1/ffa/queue/poll/{steam_id}'): (NOT, 'read_upkeep', ()),  # main.ffa_queue_poll
    ('GET', '/api/v1/ffa/queue/recent-joins'): (NOT, 'read', ()),  # main.ffa_queue_recent_joins
    ('GET', '/api/v1/ffa/readmit/offer'): (NOT, 'read_upkeep', ()),  # main.ffa_readmit_offer
    ('GET', '/api/v1/ffa/recent'): (NOT, 'read_upkeep', ()),  # main.ffa_recent
    ('GET', '/api/v1/h2h/{steam_id}/{opponent_steam_id}'): (NOT, 'read', ()),  # main.h2h_summary
    ('GET', '/api/v1/health'): (NOT, 'read', ()),  # main.health_check
    ('GET', '/api/v1/i18n/approved'): (NOT, 'read_upkeep', ()),  # main.i18n_approved_list
    ('GET', '/api/v1/i18n/contributors'): (NOT, 'read_upkeep', ()),  # main.i18n_contributors
    ('GET', '/api/v1/i18n/grants/mine'): (NOT, 'read_upkeep', ()),  # main.i18n_my_grants
    ('GET', '/api/v1/i18n/history'): (NOT, 'read_upkeep', ()),  # main.i18n_key_history
    ('GET', '/api/v1/i18n/keys'): (NOT, 'read_upkeep', ()),  # main.i18n_keys
    ('GET', '/api/v1/i18n/pack/{locale}'): (NOT, 'read', ()),  # main.i18n_pack
    ('POST', '/api/v1/i18n/portal-session'): (NOT, 'own', ()),  # main.i18n_portal_session
    ('POST', '/api/v1/i18n/portal-session/refresh'): (NOT, 'own', ()),  # main.i18n_portal_session_refresh
    ('GET', '/api/v1/i18n/progress'): (NOT, 'read_upkeep', ()),  # main.i18n_progress
    ('GET', '/api/v1/i18n/proposals'): (NOT, 'read_upkeep', ()),  # main.i18n_proposal_queue
    ('POST', '/api/v1/i18n/proposals'): (NOT, 'own', ()),  # main.i18n_propose
    ('POST', '/api/v1/i18n/revert'): (NOT, 'config', ()),  # main.i18n_revert
    ('POST', '/api/v1/i18n/review'): (NOT, 'config', ()),  # main.i18n_review
    ('POST', '/api/v1/internal/booster-grant'): (NOT, 'automatic', ()),  # main.booster_grant
    ('POST', '/api/v1/internal/bug-reports/by-number/{bug_number}/user-comment'): (NOT, 'service', ()),  # main.user_comment_on_bug_report
    ('POST', '/api/v1/internal/bug-reports/events/ack'): (NOT, 'service', ()),  # main.ack_bug_report_events
    ('POST', '/api/v1/internal/bug-reports/{report_id}/channel-posted'): (NOT, 'service', ()),  # main.ack_bug_report_posted
    ('POST', '/api/v1/internal/bug-reports/{report_id}/comment'): (NOT, 'service', ()),  # main.internal_comment_on_bug_report
    ('POST', '/api/v1/internal/channel-posts/ack'): (NOT, 'service', ()),  # main.ack_channel_post
    ('GET', '/api/v1/internal/channel-posts/pending'): (NOT, 'read_upkeep', ()),  # main.pending_channel_posts
    ('POST', '/api/v1/internal/chat/bridge'): (NOT, 'service', ()),  # main.bridge_stream_chat
    ('POST', '/api/v1/internal/chat/lockdown'): (NOT, 'config', (('main', '_set_chat_lockdown'), )),  # main.internal_chat_lockdown
    ('GET', '/api/v1/internal/chat/lockdown-state'): (NOT, 'read', ()),  # main.internal_chat_lockdown_state
    ('POST', '/api/v1/internal/chat/mirrors'): (NOT, 'service', ()),  # main.internal_chat_mirrors
    ('GET', '/api/v1/internal/chat/mod-actions'): (NOT, 'read_upkeep', ()),  # main.internal_chat_mod_actions
    ('POST', '/api/v1/internal/chat/mod-actions/ack'): (NOT, 'service', ()),  # main.internal_chat_mod_actions_ack
    ('GET', '/api/v1/internal/chat/since'): (NOT, 'read_upkeep', ()),  # main.internal_chat_since
    ('GET', '/api/v1/internal/evidence-report/game/{code}'): (NOT, 'read_upkeep', ()),  # admin_evidence.evidence_report_game
    ('GET', '/api/v1/internal/evidence-report/pair'): (NOT, 'read_upkeep', ()),  # admin_evidence.evidence_report_pair
    ('GET', '/api/v1/internal/evidence-report/player/{steam_id}'): (NOT, 'read_upkeep', ()),  # admin_evidence.evidence_report_player
    ('GET', '/api/v1/internal/evidence-report/series/{code}'): (NOT, 'read_upkeep', ()),  # admin_evidence.evidence_report_series
    ('GET', '/api/v1/internal/janitor-selftest'): (NOT, 'read', ()),  # main.get_janitor_selftest
    ('GET', '/api/v1/internal/lfp-pings'): (NOT, 'read', ()),  # main.internal_lfp_pings
    ('POST', '/api/v1/internal/lfp-pings/ack'): (NOT, 'service', ()),  # main.ack_lfp_pings
    ('GET', '/api/v1/internal/linked-players'): (NOT, 'read', ()),  # main.internal_linked_players
    ('POST', '/api/v1/internal/logs/auto/prune'): (NOT, 'service', ()),  # auto_logs.run_auto_log_prune
    ('POST', '/api/v1/internal/mail/relay-pref'): (NOT, 'service', ()),  # mail_discord.mail_relay_pref
    ('POST', '/api/v1/internal/mail/relay-threads'): (NOT, 'service', ()),  # mail_discord.mail_relay_threads
    ('POST', '/api/v1/internal/mail/reply-from-discord'): (NOT, 'service', ()),  # mail_discord.mail_reply_from_discord
    ('POST', '/api/v1/internal/moderation-cases/{case_id}/notified'): (NOT, 'config', ()),  # main.internal_moderation_case_notified
    ('GET', '/api/v1/internal/modlog'): (NOT, 'read', ()),  # main.internal_modlog
    ('GET', '/api/v1/internal/pc/binder'): (NOT, 'read', ()),  # main.internal_pc_binder
    ('GET', '/api/v1/internal/pc/binder/{owner_ref}/page/{page}/{locale}.png'): (NOT, 'read', ()),  # main.internal_pc_binder_page
    ('GET', '/api/v1/internal/pc/card'): (NOT, 'read', ()),  # main.internal_pc_card
    ('GET', '/api/v1/internal/pc/collection'): (NOT, 'read', ()),  # main.internal_pc_collection
    ('POST', '/api/v1/internal/pc/daily'): (NOT, 'service', ()),  # main.internal_pc_daily
    ('POST', '/api/v1/internal/pc/events/ack'): (NOT, 'service', ()),  # main.internal_pc_events_ack
    ('GET', '/api/v1/internal/pc/events/pending'): (NOT, 'read_upkeep', ()),  # main.internal_pc_events_pending
    ('GET', '/api/v1/internal/pc/face/back'): (NOT, 'read', ()),  # main.internal_pc_face_back
    ('GET', '/api/v1/internal/pc/face/preview/{player_ref}/{locale}'): (NOT, 'read_upkeep', ()),  # main.internal_pc_face_preview
    ('GET', '/api/v1/internal/pc/face/print/{print_id}/{locale}'): (NOT, 'read', ()),  # main.internal_pc_face_print
    ('POST', '/api/v1/internal/pc/lease'): (NOT, 'service', ()),  # main.internal_pc_lease
    ('DELETE', '/api/v1/internal/pc/lease/{lease_id}'): (NOT, 'service', ()),  # main.internal_pc_lease_release
    ('GET', '/api/v1/internal/pc/lease/{lease_id}'): (NOT, 'read', ()),  # main.internal_pc_lease_check
    ('GET', '/api/v1/internal/pc/motion/preview/{player_ref}/{locale}.gif'): (NOT, 'read', ()),  # main.internal_pc_motion_preview
    ('GET', '/api/v1/internal/pc/packs'): (NOT, 'read', ()),  # main.internal_pc_packs
    ('POST', '/api/v1/internal/pc/packs/open'): (NOT, 'service', ()),  # main.internal_pc_open_pack
    ('GET', '/api/v1/internal/pc/packs/{pack_id}/strip/{locale}.png'): (NOT, 'read', ()),  # main.internal_pc_pack_strip
    ('GET', '/api/v1/internal/pending-dms'): (NOT, 'read_upkeep', ()),  # main.internal_pending_dms
    ('POST', '/api/v1/internal/pending-dms/ack'): (NOT, 'service', ()),  # main.ack_pending_dms
    ('GET', '/api/v1/internal/pending-dms/{dm_id}/cancelled'): (NOT, 'read', ()),  # main.internal_pending_dm_cancelled
    ('GET', '/api/v1/internal/quarantine/digest'): (NOT, 'read_upkeep', ()),  # main.internal_quarantine_digest
    ('POST', '/api/v1/internal/quarantine/digest/posted'): (NOT, 'service', ()),  # main.internal_quarantine_digest_posted
    ('POST', '/api/v1/internal/rank-role-colors'): (NOT, 'service', ()),  # main.push_rank_role_colors
    ('GET', '/api/v1/internal/recent-bans'): (NOT, 'read', ()),  # main.get_recent_bans
    ('GET', '/api/v1/internal/recent-flags'): (NOT, 'read', ()),  # main.get_recent_flags
    ('POST', '/api/v1/internal/recent-flags/ack'): (NOT, 'service', ()),  # main.acknowledge_recent_flag
    ('POST', '/api/v1/internal/release-posts'): (NOT, 'service', ()),  # main.push_release_posts
    ('POST', '/api/v1/internal/stream-posts/ack'): (NOT, 'service', ()),  # main.internal_stream_posts_ack
    ('GET', '/api/v1/internal/stream-posts/pending'): (NOT, 'read_upkeep', ()),  # main.internal_stream_posts_pending
    ('GET', '/api/v1/internal/tournament-notices'): (NOT, 'read', ()),  # main.internal_tournament_notices
    ('POST', '/api/v1/internal/tournament-notices/ack'): (NOT, 'service', ()),  # main.ack_tournament_notices
    ('POST', '/api/v1/internal/tournaments/checkin-response'): (NOT, 'service', ()),  # main.internal_tournament_checkin_response
    ('POST', '/api/v1/invites'): (NOT, 'gameplay', ()),  # main.invite_send
    ('GET', '/api/v1/invites/pending'): (NOT, 'read', ()),  # main.invite_pending
    ('POST', '/api/v1/invites/{invite_id}/accept'): (NOT, 'gameplay', ()),  # main.invite_accept
    ('POST', '/api/v1/invites/{invite_id}/cancel'): (NOT, 'gameplay', ()),  # main.invite_cancel
    ('POST', '/api/v1/invites/{invite_id}/decline'): (NOT, 'gameplay', ()),  # main.invite_decline
    ('GET', '/api/v1/leaderboard'): (NOT, 'read_upkeep', ()),  # main.get_leaderboard
    ('POST', '/api/v1/lfp-ping'): (NOT, 'gameplay', ()),  # main.lfp_ping
    ('POST', '/api/v1/lobby-bets'): (NOT, 'gameplay', ()),  # main.place_lobby_bet
    ('POST', '/api/v1/lobby-bets/cancel'): (NOT, 'gameplay', ()),  # main.cancel_lobby_bet
    ('POST', '/api/v1/logs/auto'): (NOT, 'own', ()),  # auto_logs.upload_auto_log
    ('POST', '/api/v1/mail'): (NOT, 'own', ()),  # main.mail_send
    ('GET', '/api/v1/mail/blocks'): (NOT, 'read', ()),  # main.mail_blocks_list
    ('POST', '/api/v1/mail/blocks'): (NOT, 'own', ()),  # main.mail_block_add
    ('DELETE', '/api/v1/mail/blocks/{steam_id}'): (NOT, 'own', ()),  # main.mail_block_remove
    ('GET', '/api/v1/mail/inbox'): (NOT, 'read_upkeep', ()),  # main.mail_inbox
    ('GET', '/api/v1/mail/sent'): (NOT, 'read', ()),  # main.mail_sent
    ('GET', '/api/v1/mail/settings'): (NOT, 'read', ()),  # main.mail_settings_get
    ('PUT', '/api/v1/mail/settings'): (NOT, 'own', ()),  # main.mail_settings_put
    ('GET', '/api/v1/mail/status'): (NOT, 'read', ()),  # main.mail_status
    ('DELETE', '/api/v1/mail/{message_id}'): (NOT, 'own', ()),  # main.mail_delete
    ('GET', '/api/v1/mail/{message_id}'): (NOT, 'read_upkeep', ()),  # main.mail_detail
    ('POST', '/api/v1/mail/{message_id}/read'): (NOT, 'own', ()),  # main.mail_read
    ('POST', '/api/v1/mail/{message_id}/reply'): (NOT, 'own', ()),  # main.mail_reply
    ('POST', '/api/v1/mail/{message_id}/report'): (NOT, 'own', ()),  # main.mail_report
    ('POST', '/api/v1/match/game/start'): (NOT, 'gameplay', ()),  # match_hold.match_game_start
    ('POST', '/api/v1/match/hold/beat'): (NOT, 'gameplay', ()),  # match_hold.match_hold_beat
    ('GET', '/api/v1/match/hold/by-room'): (NOT, 'read', ()),  # match_hold.match_hold_by_room
    ('GET', '/api/v1/match/hold/mine'): (NOT, 'read_upkeep', ()),  # match_hold.match_hold_mine
    ('POST', '/api/v1/match/hold/open'): (NOT, 'gameplay', ()),  # match_hold.match_hold_open
    ('POST', '/api/v1/match/hold/{hold_id}/bind'): (NOT, 'gameplay', ()),  # match_hold.match_hold_bind
    ('POST', '/api/v1/match/hold/{hold_id}/claim'): (NOT, 'gameplay', ()),  # match_hold.match_hold_claim
    ('POST', '/api/v1/match/hold/{hold_id}/end'): (NOT, 'gameplay', ()),  # match_hold.match_hold_end
    ('POST', '/api/v1/match/hold/{hold_id}/entered'): (NOT, 'gameplay', ()),  # match_hold.match_hold_entered
    ('GET', '/api/v1/match/hold/{hold_id}/state'): (NOT, 'read', ()),  # match_hold.match_hold_state
    ('POST', '/api/v1/matches'): (NOT, 'gameplay', ()),  # main.submit_match
    ('GET', '/api/v1/matches/by-code/{code}'): (NOT, 'read', ()),  # main.get_match_by_code
    ('POST', '/api/v1/matches/card-evidence'): (NOT, 'gameplay', ()),  # main.submit_card_evidence
    ('POST', '/api/v1/matches/casual-dc'): (NOT, 'gameplay', ()),  # main.report_casual_dc
    ('POST', '/api/v1/matches/combat-evidence'): (NOT, 'gameplay', ()),  # main.submit_combat_evidence
    ('POST', '/api/v1/matches/identity-clock-evidence'): (NOT, 'gameplay', ()),  # main.submit_identity_clock_evidence
    ('POST', '/api/v1/matches/macro-evidence'): (NOT, 'gameplay', ()),  # main.submit_macro_evidence
    ('POST', '/api/v1/matches/seat-evidence'): (NOT, 'gameplay', ()),  # main.submit_seat_evidence
    ('GET', '/api/v1/mod-version'): (NOT, 'read', ()),  # main.get_mod_version
    ('GET', '/api/v1/mod/check/{steam_id}'): (NOT, 'read', ()),  # main.check_player_registered
    ('POST', '/api/v1/mod/toggle-ranked/{steam_id}'): (NOT, 'own', ()),  # main.toggle_ranked
    ('POST', '/api/v1/music/rate'): (NOT, 'own', ()),  # main.music_rate
    ('GET', '/api/v1/music/ratings'): (NOT, 'read_upkeep', ()),  # main.music_ratings_public
    ('GET', '/api/v1/music/ratings/mine'): (NOT, 'read_upkeep', ()),  # main.music_ratings_mine
    ('GET', '/api/v1/ovt/leaderboard'): (NOT, 'read_upkeep', ()),  # main.ovt_leaderboard
    ('GET', '/api/v1/ovt/lobbies'): (NOT, 'read_upkeep', ()),  # main.ovt_lobby_browser
    ('POST', '/api/v1/ovt/lobby/create'): (NOT, 'gameplay', ()),  # main.ovt_lobby_create
    ('POST', '/api/v1/ovt/lobby/join'): (NOT, 'gameplay', ()),  # main.ovt_lobby_join
    ('POST', '/api/v1/ovt/lobby/kick'): (NOT, 'gameplay', ()),  # main.ovt_lobby_kick
    ('POST', '/api/v1/ovt/lobby/leave'): (NOT, 'gameplay', ()),  # main.ovt_lobby_leave
    ('POST', '/api/v1/ovt/lobby/prefs'): (NOT, 'gameplay', ()),  # main.ovt_lobby_prefs
    ('GET', '/api/v1/ovt/lobby/resolve'): (NOT, 'read_upkeep', ()),  # main.ovt_lobby_resolve
    ('POST', '/api/v1/ovt/lobby/settings'): (NOT, 'gameplay', ()),  # main.ovt_lobby_settings
    ('POST', '/api/v1/ovt/lobby/start'): (NOT, 'gameplay', ()),  # main.ovt_lobby_start
    ('GET', '/api/v1/ovt/lobby/state'): (NOT, 'read_upkeep', ()),  # main.ovt_lobby_state
    ('POST', '/api/v1/ovt/matches'): (NOT, 'gameplay', ()),  # main.submit_ovt_match
    ('POST', '/api/v1/ovt/queue/join'): (NOT, 'gameplay', ()),  # main.ovt_queue_join
    ('POST', '/api/v1/ovt/queue/leave'): (NOT, 'gameplay', ()),  # main.ovt_queue_leave
    ('GET', '/api/v1/ovt/queue/list'): (NOT, 'read', ()),  # main.ovt_queue_list
    ('GET', '/api/v1/ovt/queue/poll/{steam_id}'): (NOT, 'read_upkeep', ()),  # main.ovt_queue_poll
    ('GET', '/api/v1/ovt/queue/recent-joins'): (NOT, 'read', ()),  # main.ovt_queue_recent_joins
    ('GET', '/api/v1/ovt/recent'): (NOT, 'read', ()),  # main.ovt_recent
    ('GET', '/api/v1/ovt/series/active'): (NOT, 'read', ()),  # main.ovt_series_active
    ('POST', '/api/v1/ovt/series/continuation'): (NOT, 'gameplay', ()),  # main.ovt_series_continuation
    ('GET', '/api/v1/pc-face/motion'): (NOT, 'read', ()),  # main.pc_face_motion_read
    ('GET', '/api/v1/pc-face/motion/{print_id}/{motion_rev}/{locale}/{size}.png'): (NOT, 'read', ()),  # main.pc_face_motion_atlas
    ('GET', '/api/v1/pc-face/{print_id}/{rev}/{locale}/{size}.png'): (NOT, 'read', ()),  # main.pc_face_png
    ('GET', '/api/v1/pc/card'): (NOT, 'read', ()),  # main.pc_card_face
    ('GET', '/api/v1/pc/collection'): (NOT, 'read', ()),  # main.pc_collection
    ('POST', '/api/v1/pc/daily'): (NOT, 'own', ()),  # main.pc_daily_claim
    ('POST', '/api/v1/pc/dance'): (NOT, 'own', ()),  # main.pc_dance_select
    ('GET', '/api/v1/pc/face/preview'): (NOT, 'read_upkeep', ()),  # main.pc_face_preview
    ('GET', '/api/v1/pc/me'): (NOT, 'read', ()),  # main.pc_me
    ('GET', '/api/v1/pc/packs'): (NOT, 'read', ()),  # main.pc_packs_history
    ('POST', '/api/v1/pc/packs/open'): (NOT, 'own', ()),  # main.pc_open_pack
    ('GET', '/api/v1/pc/packs/result'): (NOT, 'read_upkeep', ()),  # main.pc_pack_result
    ('GET', '/api/v1/pc/pool'): (NOT, 'read', ()),  # main.pc_pool_summary
    ('POST', '/api/v1/pc/portrait'): (NOT, 'own', ()),  # main.pc_portrait_upload
    ('POST', '/api/v1/pc/portrait/motion'): (NOT, 'own', ()),  # main.pc_motion_upload
    ('POST', '/api/v1/pc/prints/discard'): (NOT, 'own', ()),  # main.pc_discard_print
    ('POST', '/api/v1/pc/prints/discard-batch'): (NOT, 'own', ()),  # main.pc_discard_batch
    ('POST', '/api/v1/pc/settings'): (NOT, 'own', ()),  # main.pc_set_setting
    ('GET', '/api/v1/pc/trades'): (NOT, 'read', ()),  # main.pc_trades
    ('POST', '/api/v1/pc/trades/accept'): (NOT, 'own', ()),  # main.pc_trade_accept
    ('POST', '/api/v1/pc/trades/cancel'): (NOT, 'own', ()),  # main.pc_trade_cancel
    ('POST', '/api/v1/pc/trades/decline'): (NOT, 'own', ()),  # main.pc_trade_decline
    ('POST', '/api/v1/pc/trades/propose'): (NOT, 'own', ()),  # main.pc_trade_propose
    ('POST', '/api/v1/players/block'): (NOT, 'own', ()),  # main.block_player
    ('GET', '/api/v1/players/blocks/{steam_id}'): (NOT, 'read', ()),  # main.get_player_blocks
    ('GET', '/api/v1/players/by-discord/{discord_id}'): (NOT, 'read', ()),  # main.get_player_by_discord
    ('POST', '/api/v1/players/link-code'): (NOT, 'own', ()),  # main.generate_link_code
    ('POST', '/api/v1/players/link-discord'): (NOT, 'own', ()),  # main.link_discord
    ('GET', '/api/v1/players/search'): (NOT, 'read', ()),  # main.search_players
    ('POST', '/api/v1/players/unblock'): (NOT, 'own', ()),  # main.unblock_player
    ('GET', '/api/v1/players/{steam_id}'): (NOT, 'read_upkeep', ()),  # main.get_player_stats
    ('POST', '/api/v1/players/{steam_id}/active-color'): (NOT, 'own', ()),  # main.set_active_color
    ('POST', '/api/v1/players/{steam_id}/active-cursor-color'): (NOT, 'own', ()),  # main.set_active_cursor_color
    ('POST', '/api/v1/players/{steam_id}/active-player-color'): (NOT, 'own', ()),  # main.set_active_player_color
    ('POST', '/api/v1/players/{steam_id}/active-player-effect'): (NOT, 'own', ()),  # main.set_active_player_effect
    ('POST', '/api/v1/players/{steam_id}/active-title'): (NOT, 'own', ()),  # main.set_active_title
    ('POST', '/api/v1/players/{steam_id}/active-trail'): (NOT, 'own', ()),  # main.set_active_trail
    ('POST', '/api/v1/players/{steam_id}/appear-offline'): (NOT, 'own', ()),  # main.set_appear_offline
    ('GET', '/api/v1/players/{steam_id}/bets'): (NOT, 'read', ()),  # main.get_player_bets
    ('GET', '/api/v1/players/{steam_id}/build-type'): (NOT, 'read', ()),  # main.get_player_build_type
    ('GET', '/api/v1/players/{steam_id}/card-tiers'): (NOT, 'read', ()),  # main.get_player_card_tiers
    ('POST', '/api/v1/players/{steam_id}/card-tiers'): (NOT, 'own', ()),  # main.set_player_card_tier
    ('POST', '/api/v1/players/{steam_id}/color-toggle'): (NOT, 'own', ()),  # main.toggle_color
    ('DELETE', '/api/v1/players/{steam_id}/data'): (NOT, 'own', ()),  # main.delete_player_data
    ('GET', '/api/v1/players/{steam_id}/ffa-history'): (NOT, 'read', ()),  # main.player_ffa_history
    ('GET', '/api/v1/players/{steam_id}/gold-sources'): (NOT, 'read', ()),  # main.get_gold_sources
    ('POST', '/api/v1/players/{steam_id}/hide-gold'): (NOT, 'own', ()),  # main.set_hide_gold
    ('GET', '/api/v1/players/{steam_id}/inventory'): (NOT, 'read', ()),  # main.get_inventory
    ('GET', '/api/v1/players/{steam_id}/matches'): (NOT, 'read_upkeep', ()),  # main.get_player_matches
    ('GET', '/api/v1/players/{steam_id}/matches/summary'): (NOT, 'read', ()),  # main.get_player_matches_summary
    ('POST', '/api/v1/players/{steam_id}/nametag-toggle'): (NOT, 'own', ()),  # main.toggle_nametag_style
    ('GET', '/api/v1/players/{steam_id}/ovt-history'): (NOT, 'read', ()),  # main.player_ovt_history
    ('POST', '/api/v1/players/{steam_id}/pref-same-cards'): (NOT, 'own', ()),  # main.set_pref_same_cards
    ('GET', '/api/v1/players/{steam_id}/ranked-friends'): (NOT, 'read', ()),  # main.get_ranked_friends
    ('GET', '/api/v1/players/{steam_id}/rating-history'): (NOT, 'read', ()),  # main.get_player_rating_history
    ('GET', '/api/v1/players/{steam_id}/rating-preview'): (NOT, 'read', ()),  # main.get_rating_preview
    ('POST', '/api/v1/players/{steam_id}/show-discord'): (NOT, 'own', ()),  # main.set_show_discord
    ('GET', '/api/v1/players/{steam_id}/similar'): (NOT, 'read', ()),  # main.get_similar_players
    ('GET', '/api/v1/players/{steam_id}/team-bets'): (NOT, 'read', ()),  # main.get_player_team_bets
    ('GET', '/api/v1/players/{steam_id}/team-history'): (NOT, 'read', ()),  # main.player_team_history
    ('GET', '/api/v1/players/{steam_id}/title-ladders'): (NOT, 'read', ()),  # title_ladders.get_title_ladders
    ('GET', '/api/v1/players/{steam_id}/vs/{opponent_steam_id}/top-cards'): (NOT, 'read', ()),  # main.get_h2h_top_cards
    ('GET', '/api/v1/presence/online'): (NOT, 'read_upkeep', ()),  # main.presence_online
    ('GET', '/api/v1/presence/ping'): (NOT, 'read_upkeep', ()),  # main.presence_ping
    ('GET', '/api/v1/queue/count'): (NOT, 'read', ()),  # main.queue_count
    ('POST', '/api/v1/queue/decline'): (NOT, 'gameplay', ()),  # main.queue_decline
    ('POST', '/api/v1/queue/join'): (NOT, 'gameplay', ()),  # main.queue_join
    ('POST', '/api/v1/queue/leave'): (NOT, 'gameplay', ()),  # main.queue_leave
    ('GET', '/api/v1/queue/poll/{steam_id}'): (NOT, 'read_upkeep', ()),  # main.queue_poll
    ('POST', '/api/v1/queue/ready'): (NOT, 'gameplay', ()),  # main.queue_ready
    ('GET', '/api/v1/queue/recent-joins'): (NOT, 'read', ()),  # main.queue_recent_joins
    ('POST', '/api/v1/queues/escape'): (NOT, 'gameplay', ()),  # main.queues_escape
    ('GET', '/api/v1/rank-tiers'): (NOT, 'read', ()),  # main.get_rank_tiers
    ('GET', '/api/v1/rating-preview/2v2'): (NOT, 'read', ()),  # main.get_rating_preview_2v2
    ('GET', '/api/v1/rating-preview/ffa'): (NOT, 'read', ()),  # main.get_rating_preview_ffa
    ('GET', '/api/v1/read-gate/probe'): (NOT, 'read', ()),  # main.read_gate_probe
    ('GET', '/api/v1/records'): (NOT, 'read_upkeep', ()),  # main.get_records_board
    ('GET', '/api/v1/release-notes/full/{locale}'): (NOT, 'read', ()),  # main.release_notes_full
    ('GET', '/api/v1/release-notes/{locale}'): (NOT, 'read', ()),  # main.release_notes_localized
    ('GET', '/api/v1/releases/recent'): (NOT, 'read', ()),  # main.get_recent_releases
    ('GET', '/api/v1/report'): (NOT, 'read', ()),  # main.get_set_report
    ('POST', '/api/v1/report-disconnect'): (NOT, 'gameplay', ()),  # main.report_disconnect
    ('GET', '/api/v1/series/active'): (NOT, 'read_upkeep', ()),  # main.get_active_series
    ('POST', '/api/v1/series/preflight'): (NOT, 'gameplay', ()),  # main.series_preflight
    ('GET', '/api/v1/series/recent'): (NOT, 'read', ()),  # main.get_recent_series
    ('GET', '/api/v1/series/recent-multimode'): (NOT, 'read', ()),  # main.get_recent_multimode_series
    ('POST', '/api/v1/series/{series_id}/live-points'): (NOT, 'gameplay', ()),  # main.update_live_points
    ('POST', '/api/v1/settings/allow-spectators'): (NOT, 'own', ()),  # main.set_allow_spectators
    ('GET', '/api/v1/shop/items'): (NOT, 'read', ()),  # main.list_shop_items
    ('GET', '/api/v1/shop/newest'): (NOT, 'read', ()),  # main.newest_shop_items
    ('POST', '/api/v1/shop/purchase'): (NOT, 'own', ()),  # main.purchase_item
    ('GET', '/api/v1/shop/sales-board'): (NOT, 'read', ()),  # main.shop_sales_board
    ('POST', '/api/v1/spectate/close'): (NOT, 'gameplay', ()),  # main.spectate_close
    ('GET', '/api/v1/spectate/games'): (NOT, 'read_upkeep', ()),  # main.spectate_games
    ('POST', '/api/v1/spectate/grant'): (NOT, 'gameplay', ()),  # main.spectate_grant
    ('POST', '/api/v1/spectate/heartbeat'): (NOT, 'gameplay', ()),  # main.spectate_heartbeat
    ('POST', '/api/v1/spectate/leave'): (NOT, 'gameplay', ()),  # main.spectate_leave
    ('POST', '/api/v1/spectate/participant-attest'): (NOT, 'gameplay', ()),  # main.spectate_participant_attest
    ('POST', '/api/v1/spectate/validate'): (NOT, 'gameplay', ()),  # main.spectate_validate
    ('POST', '/api/v1/team-bets'): (NOT, 'gameplay', ()),  # main.place_team_bet
    ('GET', '/api/v1/team/all-series-paged'): (NOT, 'read_upkeep', ()),  # main.team_all_series_paged
    ('GET', '/api/v1/team/leaderboard'): (NOT, 'read_upkeep', ()),  # main.team_leaderboard
    ('GET', '/api/v1/team/lobbies'): (NOT, 'read_upkeep', ()),  # main.team_lobby_browser
    ('POST', '/api/v1/team/lobby/create'): (NOT, 'gameplay', ()),  # main.team_lobby_create
    ('POST', '/api/v1/team/lobby/join'): (NOT, 'gameplay', ()),  # main.team_lobby_join
    ('POST', '/api/v1/team/lobby/kick'): (NOT, 'gameplay', ()),  # main.team_lobby_kick
    ('POST', '/api/v1/team/lobby/leave'): (NOT, 'gameplay', ()),  # main.team_lobby_leave
    ('POST', '/api/v1/team/lobby/prefs'): (NOT, 'gameplay', ()),  # main.team_lobby_prefs
    ('GET', '/api/v1/team/lobby/resolve'): (NOT, 'read_upkeep', ()),  # main.team_lobby_resolve
    ('POST', '/api/v1/team/lobby/settings'): (NOT, 'gameplay', ()),  # main.team_lobby_settings
    ('POST', '/api/v1/team/lobby/start'): (NOT, 'gameplay', ()),  # main.team_lobby_start
    ('GET', '/api/v1/team/lobby/state'): (NOT, 'read_upkeep', ()),  # main.team_lobby_state
    ('POST', '/api/v1/team/matches'): (NOT, 'gameplay', ()),  # main.submit_team_match
    ('GET', '/api/v1/team/players/{steam_id}/team-matches'): (NOT, 'read', ()),  # main.get_player_team_matches
    ('GET', '/api/v1/team/players/{steam_id}/team-stats'): (NOT, 'read', ()),  # main.get_player_team_stats
    ('GET', '/api/v1/team/queue/count'): (NOT, 'read', ()),  # main.team_queue_count
    ('POST', '/api/v1/team/queue/join'): (NOT, 'gameplay', ()),  # main.team_queue_join
    ('POST', '/api/v1/team/queue/leave'): (NOT, 'gameplay', ()),  # main.team_queue_leave
    ('GET', '/api/v1/team/queue/list'): (NOT, 'read', ()),  # main.team_queue_list
    ('POST', '/api/v1/team/queue/manual-pick-toggle'): (NOT, 'gameplay', ()),  # main.team_queue_manual_pick_toggle
    ('GET', '/api/v1/team/queue/poll/{steam_id}'): (NOT, 'read_upkeep', ()),  # main.team_queue_poll
    ('POST', '/api/v1/team/queue/preferred-team'): (NOT, 'gameplay', ()),  # main.team_queue_preferred_team
    ('POST', '/api/v1/team/queue/ready'): (NOT, 'gameplay', ()),  # main.team_queue_ready
    ('GET', '/api/v1/team/queue/recent-joins'): (NOT, 'read', ()),  # main.team_queue_recent_joins
    ('GET', '/api/v1/team/series/active'): (NOT, 'read', ()),  # main.get_active_team_series
    ('POST', '/api/v1/team/series/continuation'): (NOT, 'gameplay', ()),  # main.team_series_continuation
    ('GET', '/api/v1/team/series/recent'): (NOT, 'read', ()),  # main.team_series_recent
    ('POST', '/api/v1/team/series/{series_id}/live-points'): (NOT, 'gameplay', ()),  # main.update_team_live_points
    ('POST', '/api/v1/team/series/{series_id}/report-dc'): (NOT, 'gameplay', ()),  # main.team_series_report_dc
    ('POST', '/api/v1/team/series/{series_id}/spawn-confirm'): (NOT, 'gameplay', ()),  # main.team_series_spawn_confirm
    ('GET', '/api/v1/team/series/{series_id}/state'): (NOT, 'read_upkeep', ()),  # main.team_series_state
    ('GET', '/api/v1/team/series/{series_id}/status'): (NOT, 'read', ()),  # main.team_series_status_readonly
    ('GET', '/api/v1/tournaments/current'): (NOT, 'read', ()),  # tournaments.get_current
    ('GET', '/api/v1/tournaments/history'): (NOT, 'read', ()),  # tournaments.history
    ('GET', '/api/v1/tournaments/history-detail'): (NOT, 'read', ()),  # tournaments.history_detail
    ('GET', '/api/v1/tournaments/internal/watch'): (NOT, 'read', ()),  # tournaments.internal_watch
    ('GET', '/api/v1/tournaments/my-active-matches'): (NOT, 'read', ()),  # tournaments.my_active_matches
    ('GET', '/api/v1/tournaments/players/{steam_id}/penalty'): (NOT, 'read_upkeep', ()),  # tournaments.player_penalty
    ('GET', '/api/v1/tournaments/players/{steam_id}/tournaments'): (NOT, 'read', ()),  # tournaments.player_tournaments
    ('GET', '/api/v1/tournaments/{tournament_id}/bracket-detail'): (NOT, 'read', ()),  # tournaments.bracket_detail
    ('POST', '/api/v1/tournaments/{tournament_id}/force-start-vote'): (NOT, 'gameplay', ()),  # tournaments.force_vote
    ('POST', '/api/v1/tournaments/{tournament_id}/matches/{match_id}/forfeit'): (NOT, 'gameplay', ()),  # tournaments.forfeit_match
    ('POST', '/api/v1/tournaments/{tournament_id}/matches/{match_id}/play-now'): (NOT, 'gameplay', ()),  # tournaments.play_now
    ('POST', '/api/v1/tournaments/{tournament_id}/ready'): (NOT, 'gameplay', ()),  # tournaments.ready
    ('POST', '/api/v1/tournaments/{tournament_id}/signup'): (NOT, 'gameplay', ()),  # tournaments.signup
    ('POST', '/api/v1/tournaments/{tournament_id}/time-vote'): (NOT, 'gameplay', ()),  # tournaments.time_vote
    ('POST', '/api/v1/tournaments/{tournament_id}/unsignup'): (NOT, 'gameplay', ()),  # tournaments.unsignup
    ('WS', '/api/v1/ws/chat'): (NOT, 'own', (('main', '_chat_censor_strike'), )),  # main.ws_chat
    ('GET', '/translate'): (NOT, 'read', ()),  # main.i18n_portal_page
}

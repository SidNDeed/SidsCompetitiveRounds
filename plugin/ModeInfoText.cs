namespace CompetitiveRounds
{
    internal static class ModeInfoText
    {
        // i18n: every member here is a PROPERTY whose literal sits directly
        // inside I18n.Tr/TrF — the extractor only harvests literals at Tr/TrF
        // call sites, and a const can't call Tr. Property access happens at
        // Info-click time, long after I18nCatalogues.Install(), so the lookup
        // always sees the catalogues. Consumers (ShowInfoPopup call sites)
        // compile unchanged.
        public static string TeamTitle => I18n.Tr("2v2 - How It Works");
        public static string Team => I18n.Tr(@"Two teams of two play a best-of-3 series.

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
- The opposing team's rating tier can multiply base rewards.
- Game XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate 2v2 Glicko rating.
<color=#7FD4FF>W-L</color> - Completed series won and lost.
<color=#7FD4FF>WR</color> - Series wins divided by completed series.
<color=#7FD4FF>Avg Mate Elo</color> - Average rating of past teammates.
  A teammate uses 2v2 rating after 5 completed series.
  Before that, their 1v1 rating is used, or 1500 if absent.
<color=#7FD4FF>Gold</color> - Lifetime Gold earned from 2v2 only.
<color=#7FD4FF>XP</color> - Lifetime XP earned from 2v2 only.
  Gold and XP do not affect your rating-based rank.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.");

        public static string OvtTitle => I18n.Tr("1v2 - How It Works");
        public static string Ovt => I18n.Tr(@"One solo player faces a duo in a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- This is a consent queue with no Elo band and no ready-up.
- The server assigns one solo and two duo players.
- Solo Extra Initial Pick is optional: the solo draws
  2 cards on the opening pick. In the random queue any
  player's opt-in turns it on; in a hosted lobby the
  host's setting decides.

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
  and the opponents' rating tier multiplies up to x3.
  Facing a top-3 1v2 player adds x1.35, win or lose.
- Series end: 40 base Gold per winner, 20 per loser,
  scaled by the opponents' rating tier.
- Game XP converts to Gold at 100 XP = 1 Gold, and
  level-ups pay their usual bonus Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

- The tab has separate Solo and Duo boards.
- You appear only on boards for roles you have played.
<color=#7FD4FF>Rank</color> - Activity order: wins, then WR, then games.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>W-L</color> - Games won and lost in that role only.
<color=#7FD4FF>WR</color> - Win rate for games in that role.
- These are activity boards. They are not sorted by Gold.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving while locked with no games played cancels the
  series; a leave mid-game leaves the result to the
  normal match report. The beta has no leave counter.");

        public static string FfaTitle => I18n.Tr("FFA - How It Works");
        // Config source for the prose (Codex v1.36 client find 13): while
        // sitting in an OPEN lobby, FfaMode's engine statics are not yet
        // latched (that happens at ready_join / the room prop) — the live
        // values are ApiClient's lobby-poll mirrors, which is exactly the
        // reading-window the Info button exists for. In-room / locked, the
        // engine statics ARE the truth. Display-only: the poll never mutates
        // engine state.
        private static int FfaTargetNow =>
            ApiClient.OpenFfaLobbyId != null ? ApiClient.FfaLobbyCfgTarget : FfaMode.RoundsToWin;
        private static int FfaCapNow =>
            ApiClient.OpenFfaLobbyId != null ? ApiClient.FfaLobbyCfgCap : FfaMode.CardCap;
        // A PROPERTY, not a const (v1.36 configurable lobbies, §7a): the
        // score target and card cap are per-lobby now, and a const would bake
        // "5" into prose forever. Evaluated at Info-click time, so it renders
        // the CURRENT lobby's numbers when the player is in one and the
        // defaults otherwise. The whole body is ONE TrF template with {0} =
        // score target and {1} = card cap, so translators see the entire doc
        // as a single unit with the live numbers as holes.
        public static string Ffa => I18n.TrF(@"Free-for-all for 3-10 players. Every player is their own team.
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

- Same Cards rule: everyone's Nth card draw offers the
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
  nearest to you (up to 4 of them), so one game can't
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
  five times last place's cut. Part pays as XP, part as
  Placement Gold, and a stronger opposing field
  multiplies the pot (the usual tier bonus).

- XP converts to Gold at 100 XP = 1 Gold, and level-ups
  pay their usual bonus Gold. A level-up landing during
  a game shows up inside that game's +g number - that is
  how a last place can occasionally out-earn the winner.

- Spectators can bet Gold on FFA lobbies from this tab.

<color=#FFD94D><b>READING THE RECENT FFAS LIST</b></color>

<color=#7FD4FF>Dots + N(P)</color> - Full points won.
<color=#7FD4FF>Half dots + N(H)</color> - Round wins that
  did not become one of that player's full points.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - That game's XP and Gold
  (including any level-up bonus).
<color=#7FD4FF>Green/red number</color> - FFA rating change.
<color=#7FD4FF>Cards</color> - The hand held at game end.
  <color=#FF6666>+N replaced</color> counts picks that were
  pushed out by the card cap - hover the line to see
  every pick in order.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate FFA Glicko rating.
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
  2 half points while their own tally was still zero,
  in which case that game does not rate them.", FfaTargetNow, FfaCapNow);
    }
}

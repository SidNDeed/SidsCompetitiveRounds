namespace CompetitiveRounds
{
    internal static class ModeInfoText
    {
        public const string TeamTitle = "2v2 - How It Works";
        public const string Team = @"Two teams of two play a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- Random queue uses an Elo band that widens as you wait.
  The server auto-balances the teams.
- Custom lobbies have no Elo band.
  Joining the lobby is consent to play.
- All 4 players have 120 seconds to ready up.
  If time expires, everyone returns to searching.
- After an auto-queue game with a point margin of 3 or more,
  the weakest winner may swap with the strongest loser.

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

- Leaving mid-game is recorded.";

        public const string OvtTitle = "1v2 - How It Works";
        public const string Ovt = @"One solo player faces a duo in a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- This is a consent queue with no Elo band and no ready-up.
- The server assigns one solo and two duo players.
- Solo Extra Initial Pick is optional.
  If anyone enables it, the solo draws 2 cards on the
  opening pick.

<color=#FFD94D><b>SCORING</b></color>

- The first side to win 2 games wins the series.
- 1v2 is an UNRANKED beta. No rating is applied yet.
- Games are recorded and will count when ranked play launches.

<color=#FFD94D><b>REWARDS</b></color>

- Each game gives 500 XP.
  A game win gets x1.5, for 750 XP.
- A series win gives each winner 40 Gold.
  A series loss gives each loser 20 Gold.
- Game XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

- The tab has separate Solo and Duo boards.
- You appear only on boards for roles you have played.
<color=#7FD4FF>Rank</color> - Activity order: wins, then WR, then games.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>W-L</color> - Games won and lost in that role only.
<color=#7FD4FF>WR</color> - Win rate for games in that role.
- These are activity boards. They are not sorted by Gold.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.";

        public const string FfaTitle = "FFA - How It Works";
        public const string Ffa = @"Free-for-all for 3-10 players. Every player is a team.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- The queue has no Elo band. Joining is consent to play.
- At 3 players, a 25-second gather window begins.
  Up to 10 players can join. A full lobby starts at once.
- The last player alive wins a half point.
  2 half points make a point. The first to 5 points wins.
- After each point, everyone except the point winner
  picks a card at the same time.
- Nothing is ever picked for you. The pick window stays
  open at least 45 seconds and extends while picks come
  in (90 seconds max). Miss it and you get no card.
- You can hold 5 cards.
  Picking a 6th removes your oldest card.

<color=#FFD94D><b>SCORING</b></color>

- FFA is ranked with its own Glicko rating.
- Placement uses points, then all half points earned
  (spent ones included), then total kills.
- Ties share a place using competition order: 1, 2, 2, 4.
- Rating compares you with up to 4 placement-adjacent players.
  A tied placement counts as a draw.

<color=#FFD94D><b>REWARDS</b></color>

- XP starts at 300, plus 60 per player placed below you.
- First place multiplies that total by x1.5.
- XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate FFA Glicko rating.
<color=#7FD4FF>Games</color> - Recorded FFA games played.
<color=#7FD4FF>Wins</color> - Games finished in 1st place.
<color=#7FD4FF>Top3</color> - Games finished in 1st, 2nd, or 3rd.
<color=#7FD4FF>AvgPl</color> - Average finishing place over all games.
  Lower is better. 1.0 means winning every game.
<color=#7FD4FF>WR</color> - Share of games won outright.
  It is shown as a percent: 50% means half were wins.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.
- A leaver keeps their tallies for placement.";
    }
}

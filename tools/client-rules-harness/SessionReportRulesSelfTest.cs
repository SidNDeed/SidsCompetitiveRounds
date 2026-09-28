using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of SessionReportRules (board row 30a). It lives
    /// HERE, under tools/, and not in plugin/SessionReportRules.cs, so the
    /// shipped DLL carries no fixture: the plugin build compiles only the
    /// rules half of this partial class, the harness compiles both.
    ///
    /// The five envelope fixtures are what GET /api/v1/report returned for
    /// backend/tests/test_session_report_pg.py's seeded world, one per kind -
    /// a ranked 1v1 series, a casual 1v1 session, a 2v2 series, a 1v2 series
    /// and a three-game FFA lobby sitting - captured with that module's
    /// SESSION_REPORT_ENVELOPE_DUMP hook; the run's random steam ids are
    /// replaced by fixed synthetic ones (Alpha ...0001 to Echo ...0005). A
    /// case names the field it reads and prints what the parser returned, so
    /// a failure says which part of the wire shape moved.
    /// </summary>
    internal static partial class SessionReportRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const string A = "76561190000000001", B = "76561190000000002", C = "76561190000000003",
                             D = "76561190000000004", E = "76561190000000005";

        private const string RANKED_SERIES =
            @"{""v"":1,""kind"":""ranked"",""players"":[{""id"":""76561190000000002"",""name"":""Bravo"",""color"":""#99B3E6"",""team"":null},{""id"":""76561190000000001"",""name"":""Alpha"",""color"":""#E69988"",""team"":null}],""games"":[{""match_id"":""a1693ccb-51b7-4ccb-b4f6-c57802a207a3"",""started_at"":""2026-09-01T12:00:00+00:00"",""duration_s"":124,""scores"":{""76561190000000001"":5,""76561190000000002"":3},""points"":{""76561190000000001"":12,""76561190000000002"":8},""timelines"":{""76561190000000001"":{""damage"":[[31.0,0],[62.0,150],[93.0,300],[124.0,420]],""shots"":[[41.3,10],[82.7,20],[124.0,30]],""hits"":[[41.3,4],[82.7,9],[124.0,15]],""blocks"":[[41.3,2],[82.7,4],[124.0,6]],""blocks_ok"":[[41.3,1],[82.7,3],[124.0,4]],""score"":[[6.0,1],[12.0,2],[18.0,3],[24.0,3],[30.0,2],[36.0,2],[42.0,3],[48.0,4],[54.0,5],[60.0,6],[66.0,6],[72.0,6],[78.0,7],[84.0,7],[90.0,6],[96.0,7],[102.0,8],[108.0,8],[114.0,9],[120.0,10]]},""76561190000000002"":{""damage"":[[31.0,0],[62.0,90],[93.0,200],[124.0,260]],""shots"":[[41.3,12],[82.7,24],[124.0,36]],""hits"":[[41.3,3],[82.7,8],[124.0,10]],""blocks"":[[41.3,1],[82.7,2],[124.0,3]],""blocks_ok"":[[41.3,0],[82.7,1],[124.0,1]],""score"":[[6.0,0],[12.0,0],[18.0,0],[24.0,1],[30.0,2],[36.0,3],[42.0,3],[48.0,2],[54.0,2],[60.0,2],[66.0,3],[72.0,4],[78.0,4],[84.0,5],[90.0,6],[96.0,6],[102.0,6],[108.0,7],[114.0,7],[120.0,6]]}},""available"":[""blocks"",""blocks_ok"",""damage"",""hits"",""score"",""shots""],""picks"":[{""t"":null,""id"":""76561190000000001"",""card"":""BombsAway""},{""t"":null,""id"":""76561190000000002"",""card"":""Leach""}],""deaths"":[{""t"":6.0,""id"":""76561190000000002""},{""t"":12.0,""id"":""76561190000000002""},{""t"":18.0,""id"":""76561190000000002""},{""t"":24.0,""id"":""76561190000000001""},{""t"":30.0,""id"":""76561190000000001""},{""t"":36.0,""id"":""76561190000000001""},{""t"":42.0,""id"":""76561190000000002""},{""t"":48.0,""id"":""76561190000000002""},{""t"":54.0,""id"":""76561190000000002""},{""t"":60.0,""id"":""76561190000000002""},{""t"":66.0,""id"":""76561190000000001""},{""t"":72.0,""id"":""76561190000000001""},{""t"":78.0,""id"":""76561190000000002""},{""t"":84.0,""id"":""76561190000000001""},{""t"":90.0,""id"":""76561190000000001""},{""t"":96.0,""id"":""76561190000000002""},{""t"":102.0,""id"":""76561190000000002""},{""t"":108.0,""id"":""76561190000000001""},{""t"":114.0,""id"":""76561190000000002""},{""t"":120.0,""id"":""76561190000000002""}],""end_build"":{""76561190000000001"":[""BombsAway""],""76561190000000002"":[""Leach""]},""end_stats"":{},""totals"":{""76561190000000001"":{""shots"":30,""hits"":15,""blocks"":6,""blocks_ok"":4,""damage"":420,""deaths"":6},""76561190000000002"":{""shots"":36,""hits"":10,""blocks"":3,""blocks_ok"":1,""damage"":260,""deaths"":10}},""rules"":null},{""match_id"":""850dd972-bb5e-47f2-811a-d5c463791e7a"",""started_at"":""2026-09-01T12:12:00+00:00"",""duration_s"":106,""scores"":{""76561190000000002"":5,""76561190000000001"":2},""points"":{""76561190000000002"":11,""76561190000000001"":6},""timelines"":{""76561190000000002"":{""damage"":[[26.5,0],[53.0,150],[79.5,300],[106.0,420]],""shots"":[[35.3,10],[70.7,20],[106.0,30]],""hits"":[[35.3,4],[70.7,9],[106.0,15]],""blocks"":[[35.3,2],[70.7,4],[106.0,6]],""blocks_ok"":[[35.3,1],[70.7,3],[106.0,4]],""score"":[[6.0,1],[12.0,2],[18.0,2],[24.0,3],[30.0,4],[36.0,4],[42.0,4],[48.0,5],[54.0,6],[60.0,6],[66.0,7],[72.0,8],[78.0,9],[84.0,9],[90.0,8],[96.0,9],[102.0,10]]},""76561190000000001"":{""damage"":[[26.5,0],[53.0,90],[79.5,200],[106.0,260]],""shots"":[[35.3,12],[70.7,24],[106.0,36]],""hits"":[[35.3,3],[70.7,8],[106.0,10]],""blocks"":[[35.3,1],[70.7,2],[106.0,3]],""blocks_ok"":[[35.3,0],[70.7,1],[106.0,1]],""score"":[[6.0,0],[12.0,0],[18.0,1],[24.0,1],[30.0,0],[36.0,1],[42.0,2],[48.0,2],[54.0,2],[60.0,3],[66.0,3],[72.0,2],[78.0,2],[84.0,3],[90.0,4],[96.0,4],[102.0,4]]}},""available"":[""blocks"",""blocks_ok"",""damage"",""hits"",""score"",""shots""],""picks"":[],""deaths"":[{""t"":6.0,""id"":""76561190000000001""},{""t"":12.0,""id"":""76561190000000001""},{""t"":18.0,""id"":""76561190000000002""},{""t"":24.0,""id"":""76561190000000001""},{""t"":30.0,""id"":""76561190000000001""},{""t"":36.0,""id"":""76561190000000002""},{""t"":42.0,""id"":""76561190000000002""},{""t"":48.0,""id"":""76561190000000001""},{""t"":54.0,""id"":""76561190000000001""},{""t"":60.0,""id"":""76561190000000002""},{""t"":66.0,""id"":""76561190000000001""},{""t"":72.0,""id"":""76561190000000001""},{""t"":78.0,""id"":""76561190000000001""},{""t"":84.0,""id"":""76561190000000002""},{""t"":90.0,""id"":""76561190000000002""},{""t"":96.0,""id"":""76561190000000001""},{""t"":102.0,""id"":""76561190000000001""}],""end_build"":{""76561190000000002"":[],""76561190000000001"":[]},""end_stats"":{},""totals"":{""76561190000000002"":{""shots"":30,""hits"":15,""blocks"":6,""blocks_ok"":4,""damage"":420,""deaths"":4},""76561190000000001"":{""shots"":36,""hits"":10,""blocks"":3,""blocks_ok"":1,""damage"":260,""deaths"":10}},""rules"":null},{""match_id"":""56e59bff-f93e-49e0-83ea-75b216ffd3f9"",""started_at"":""2026-09-01T12:24:00+00:00"",""duration_s"":130,""scores"":{""76561190000000001"":5,""76561190000000002"":4},""points"":{""76561190000000001"":11,""76561190000000002"":10},""timelines"":{""76561190000000001"":{""damage"":[[32.5,0],[65.0,150],[97.5,300],[130.0,420]],""shots"":[[43.3,10],[86.7,20],[130.0,30]],""hits"":[[43.3,4],[86.7,9],[130.0,15]],""blocks"":[[43.3,2],[86.7,4],[130.0,6]],""blocks_ok"":[[43.3,1],[86.7,3],[130.0,4]],""score"":[[6.0,0],[12.0,0],[18.0,0],[24.0,1],[30.0,2],[36.0,2],[42.0,2],[48.0,3],[54.0,4],[60.0,5],[66.0,5],[72.0,4],[78.0,5],[84.0,6],[90.0,6],[96.0,6],[102.0,6],[108.0,7],[114.0,8],[120.0,9],[126.0,10]]},""76561190000000002"":{""damage"":[[32.5,0],[65.0,90],[97.5,200],[130.0,260]],""shots"":[[43.3,12],[86.7,24],[130.0,36]],""hits"":[[43.3,3],[86.7,8],[130.0,10]],""blocks"":[[43.3,1],[86.7,2],[130.0,3]],""blocks_ok"":[[43.3,0],[86.7,1],[130.0,1]],""score"":[[6.0,1],[12.0,2],[18.0,3],[24.0,3],[30.0,2],[36.0,3],[42.0,4],[48.0,4],[54.0,4],[60.0,4],[66.0,5],[72.0,6],[78.0,6],[84.0,6],[90.0,7],[96.0,8],[102.0,9],[108.0,9],[114.0,8],[120.0,8],[126.0,8]]}},""available"":[""blocks"",""blocks_ok"",""damage"",""hits"",""score"",""shots""],""picks"":[],""deaths"":[{""t"":6.0,""id"":""76561190000000001""},{""t"":12.0,""id"":""76561190000000001""},{""t"":18.0,""id"":""76561190000000001""},{""t"":24.0,""id"":""76561190000000002""},{""t"":30.0,""id"":""76561190000000002""},{""t"":36.0,""id"":""76561190000000001""},{""t"":42.0,""id"":""76561190000000001""},{""t"":48.0,""id"":""76561190000000002""},{""t"":54.0,""id"":""76561190000000002""},{""t"":60.0,""id"":""76561190000000002""},{""t"":66.0,""id"":""76561190000000001""},{""t"":72.0,""id"":""76561190000000001""},{""t"":78.0,""id"":""76561190000000002""},{""t"":84.0,""id"":""76561190000000002""},{""t"":90.0,""id"":""76561190000000001""},{""t"":96.0,""id"":""76561190000000001""},{""t"":102.0,""id"":""76561190000000001""},{""t"":108.0,""id"":""76561190000000002""},{""t"":114.0,""id"":""76561190000000002""},{""t"":120.0,""id"":""76561190000000002""},{""t"":126.0,""id"":""76561190000000002""}],""end_build"":{""76561190000000001"":[],""76561190000000002"":[]},""end_stats"":{},""totals"":{""76561190000000001"":{""shots"":30,""hits"":15,""blocks"":6,""blocks_ok"":4,""damage"":420,""deaths"":8},""76561190000000002"":{""shots"":36,""hits"":10,""blocks"":3,""blocks_ok"":1,""damage"":260,""deaths"":10}},""rules"":null}],""set_summary"":{""rating"":{""76561190000000002"":{""before"":1500.0,""after"":1488.5,""delta"":-11.5},""76561190000000001"":{""before"":1600.0,""after"":1611.5,""delta"":11.5}},""gold"":{""76561190000000001"":25,""76561190000000002"":5}},""truncated"":false,""games_omitted"":0}";

        private const string CASUAL_SESSION =
            @"{""v"":1,""kind"":""casual"",""players"":[{""id"":""76561190000000002"",""name"":""Bravo"",""color"":""#99B3E6"",""team"":null},{""id"":""76561190000000001"",""name"":""Alpha"",""color"":""#E69988"",""team"":null}],""games"":[{""match_id"":""bc16fac5-0486-42c5-a870-f051d82f2e0f"",""started_at"":""2026-09-01T12:40:00+00:00"",""duration_s"":64,""scores"":{""76561190000000001"":5,""76561190000000002"":0},""points"":{""76561190000000001"":10,""76561190000000002"":0},""timelines"":{""76561190000000001"":{""damage"":[[16.0,0],[32.0,150],[48.0,300],[64.0,420]],""shots"":[[21.3,10],[42.7,20],[64.0,30]],""hits"":[[21.3,4],[42.7,9],[64.0,15]],""blocks"":[[21.3,2],[42.7,4],[64.0,6]],""blocks_ok"":[[21.3,1],[42.7,3],[64.0,4]],""score"":[[6.0,1],[12.0,2],[18.0,3],[24.0,4],[30.0,5],[36.0,6],[42.0,7],[48.0,8],[54.0,9],[60.0,10]]},""76561190000000002"":{""damage"":[[16.0,0],[32.0,90],[48.0,200],[64.0,260]],""shots"":[[21.3,12],[42.7,24],[64.0,36]],""hits"":[[21.3,3],[42.7,8],[64.0,10]],""blocks"":[[21.3,1],[42.7,2],[64.0,3]],""blocks_ok"":[[21.3,0],[42.7,1],[64.0,1]],""score"":[[6.0,0],[12.0,0],[18.0,0],[24.0,0],[30.0,0],[36.0,0],[42.0,0],[48.0,0],[54.0,0],[60.0,0]]}},""available"":[""blocks"",""blocks_ok"",""damage"",""hits"",""score"",""shots""],""picks"":[],""deaths"":[{""t"":6.0,""id"":""76561190000000002""},{""t"":12.0,""id"":""76561190000000002""},{""t"":18.0,""id"":""76561190000000002""},{""t"":24.0,""id"":""76561190000000002""},{""t"":30.0,""id"":""76561190000000002""},{""t"":36.0,""id"":""76561190000000002""},{""t"":42.0,""id"":""76561190000000002""},{""t"":48.0,""id"":""76561190000000002""},{""t"":54.0,""id"":""76561190000000002""},{""t"":60.0,""id"":""76561190000000002""}],""end_build"":{""76561190000000001"":[],""76561190000000002"":[]},""end_stats"":{},""totals"":{""76561190000000001"":{""shots"":30,""hits"":15,""blocks"":6,""blocks_ok"":4,""damage"":420,""deaths"":0},""76561190000000002"":{""shots"":36,""hits"":10,""blocks"":3,""blocks_ok"":1,""damage"":260,""deaths"":10}},""rules"":null},{""match_id"":""8188db7c-0c49-47d7-985e-b6f215b9bc76"",""started_at"":""2026-09-01T12:50:00+00:00"",""duration_s"":100,""scores"":{""76561190000000002"":5,""76561190000000001"":3},""points"":{""76561190000000002"":10,""76561190000000001"":6},""timelines"":{""76561190000000002"":{""damage"":[[25.0,0],[50.0,150],[75.0,300],[100.0,420]],""shots"":[[33.3,10],[66.7,20],[100.0,30]],""hits"":[[33.3,4],[66.7,9],[100.0,15]],""blocks"":[[33.3,2],[66.7,4],[100.0,6]],""blocks_ok"":[[33.3,1],[66.7,3],[100.0,4]],""score"":[[6.0,0],[12.0,0],[18.0,0],[24.0,0],[30.0,0],[36.0,0],[42.0,1],[48.0,2],[54.0,3],[60.0,4],[66.0,5],[72.0,6],[78.0,7],[84.0,8],[90.0,9],[96.0,10]]},""76561190000000001"":{""damage"":[[25.0,0],[50.0,90],[75.0,200],[100.0,260]],""shots"":[[33.3,12],[66.7,24],[100.0,36]],""hits"":[[33.3,3],[66.7,8],[100.0,10]],""blocks"":[[33.3,1],[66.7,2],[100.0,3]],""blocks_ok"":[[33.3,0],[66.7,1],[100.0,1]],""score"":[[6.0,1],[12.0,2],[18.0,3],[24.0,4],[30.0,5],[36.0,6],[42.0,6],[48.0,6],[54.0,6],[60.0,6],[66.0,6],[72.0,6],[78.0,6],[84.0,6],[90.0,6],[96.0,6]]}},""available"":[""blocks"",""blocks_ok"",""damage"",""hits"",""score"",""shots""],""picks"":[],""deaths"":[{""t"":6.0,""id"":""76561190000000002""},{""t"":12.0,""id"":""76561190000000002""},{""t"":18.0,""id"":""76561190000000002""},{""t"":24.0,""id"":""76561190000000002""},{""t"":30.0,""id"":""76561190000000002""},{""t"":36.0,""id"":""76561190000000002""},{""t"":42.0,""id"":""76561190000000001""},{""t"":48.0,""id"":""76561190000000001""},{""t"":54.0,""id"":""76561190000000001""},{""t"":60.0,""id"":""76561190000000001""},{""t"":66.0,""id"":""76561190000000001""},{""t"":72.0,""id"":""76561190000000001""},{""t"":78.0,""id"":""76561190000000001""},{""t"":84.0,""id"":""76561190000000001""},{""t"":90.0,""id"":""76561190000000001""},{""t"":96.0,""id"":""76561190000000001""}],""end_build"":{""76561190000000002"":[],""76561190000000001"":[]},""end_stats"":{},""totals"":{""76561190000000002"":{""shots"":30,""hits"":15,""blocks"":6,""blocks_ok"":4,""damage"":420,""deaths"":6},""76561190000000001"":{""shots"":36,""hits"":10,""blocks"":3,""blocks_ok"":1,""damage"":260,""deaths"":10}},""rules"":null}],""set_summary"":{""rating"":{},""gold"":{""76561190000000001"":2,""76561190000000002"":2}},""truncated"":true,""games_omitted"":1}";

        private const string TEAM_SERIES =
            @"{""v"":1,""kind"":""team"",""players"":[{""id"":""76561190000000001"",""name"":""Alpha"",""color"":""#99B3E6"",""team"":1},{""id"":""76561190000000003"",""name"":""Charlie"",""color"":""#E69988"",""team"":1},{""id"":""76561190000000002"",""name"":""Bravo"",""color"":""#8FD18F"",""team"":2},{""id"":""76561190000000004"",""name"":""Delta"",""color"":""#E6C866"",""team"":2}],""games"":[{""match_id"":""2adb6508-ac1d-4245-80d8-105214044564"",""started_at"":""2026-09-01T13:06:00+00:00"",""duration_s"":300,""scores"":{""76561190000000001"":5,""76561190000000003"":5,""76561190000000002"":3,""76561190000000004"":3},""points"":{""76561190000000001"":10,""76561190000000003"":10,""76561190000000002"":6,""76561190000000004"":6},""timelines"":{""76561190000000001"":{""damage"":[[150.0,0],[300.0,300]],""shots"":[[150.0,5],[300.0,10]],""hits"":[[150.0,2],[300.0,6]],""fps"":[[150.0,60],[300.0,61]]},""76561190000000003"":{},""76561190000000002"":{},""76561190000000004"":{}},""available"":[""damage"",""fps"",""hits"",""shots""],""picks"":[],""deaths"":[],""end_build"":{""76561190000000001"":[],""76561190000000003"":[],""76561190000000002"":[],""76561190000000004"":[]},""end_stats"":{},""totals"":{""76561190000000001"":{""shots"":10,""hits"":6,""keys"":80,""active_s"":200.0}},""rules"":null},{""match_id"":""d1d4fef4-9d31-4a04-abb2-9ab4b5dd6f17"",""started_at"":""2026-09-01T13:13:00+00:00"",""duration_s"":300,""scores"":{""76561190000000001"":5,""76561190000000003"":5,""76561190000000002"":2,""76561190000000004"":2},""points"":{""76561190000000001"":10,""76561190000000003"":10,""76561190000000002"":4,""76561190000000004"":4},""timelines"":{""76561190000000001"":{""damage"":[[150.0,0],[300.0,300]],""shots"":[[150.0,5],[300.0,10]],""hits"":[[150.0,2],[300.0,6]],""fps"":[[150.0,60],[300.0,61]]},""76561190000000003"":{},""76561190000000002"":{},""76561190000000004"":{}},""available"":[""damage"",""fps"",""hits"",""shots""],""picks"":[],""deaths"":[],""end_build"":{""76561190000000001"":[],""76561190000000003"":[],""76561190000000002"":[],""76561190000000004"":[]},""end_stats"":{},""totals"":{""76561190000000001"":{""shots"":10,""hits"":6,""keys"":80,""active_s"":200.0}},""rules"":null}],""set_summary"":{""rating"":{""76561190000000001"":{""before"":null,""after"":null,""delta"":9.0},""76561190000000003"":{""before"":null,""after"":null,""delta"":9.0},""76561190000000002"":{""before"":null,""after"":null,""delta"":-9.0},""76561190000000004"":{""before"":null,""after"":null,""delta"":-9.0}},""gold"":{}},""truncated"":false,""games_omitted"":0}";

        private const string OVT_SERIES =
            @"{""v"":1,""kind"":""ovt"",""players"":[{""id"":""76561190000000001"",""name"":""Alpha"",""color"":""#99B3E6"",""team"":1},{""id"":""76561190000000002"",""name"":""Bravo"",""color"":""#E69988"",""team"":2},{""id"":""76561190000000003"",""name"":""Charlie"",""color"":""#8FD18F"",""team"":2}],""games"":[{""match_id"":""6492eeda-2cd4-4e71-953b-b6dbdb5fd29a"",""started_at"":""2026-09-01T13:22:00+00:00"",""duration_s"":240,""scores"":{""76561190000000001"":5,""76561190000000002"":4,""76561190000000003"":4},""points"":{""76561190000000001"":10,""76561190000000002"":8,""76561190000000003"":8},""timelines"":{""76561190000000001"":{""damage"":[[80.0,0],[160.0,200],[240.0,380]]},""76561190000000002"":{},""76561190000000003"":{}},""available"":[""damage""],""picks"":[],""deaths"":[],""end_build"":{""76561190000000001"":[],""76561190000000002"":[],""76561190000000003"":[]},""end_stats"":{},""totals"":{},""rules"":null},{""match_id"":""3b69d41b-dd45-4570-b471-18e32f976013"",""started_at"":""2026-09-01T13:28:00+00:00"",""duration_s"":240,""scores"":{""76561190000000001"":3,""76561190000000002"":5,""76561190000000003"":5},""points"":{""76561190000000001"":6,""76561190000000002"":10,""76561190000000003"":10},""timelines"":{""76561190000000001"":{""damage"":[[80.0,0],[160.0,200],[240.0,380]]},""76561190000000002"":{},""76561190000000003"":{}},""available"":[""damage""],""picks"":[],""deaths"":[],""end_build"":{""76561190000000001"":[],""76561190000000002"":[],""76561190000000003"":[]},""end_stats"":{},""totals"":{},""rules"":null}],""set_summary"":{""rating"":{""76561190000000001"":{""before"":null,""after"":null,""delta"":6.0},""76561190000000002"":{""before"":null,""after"":null,""delta"":-3.0},""76561190000000003"":{""before"":null,""after"":null,""delta"":-3.0}},""gold"":{""76561190000000001"":3,""76561190000000002"":1,""76561190000000003"":1}},""truncated"":false,""games_omitted"":0}";

        private const string FFA_LOBBY =
            @"{""v"":1,""kind"":""ffa"",""players"":[{""id"":""76561190000000001"",""name"":""Alpha"",""color"":""#99B3E6"",""team"":null},{""id"":""76561190000000002"",""name"":""Bravo"",""color"":""#E69988"",""team"":null},{""id"":""76561190000000004"",""name"":""Delta"",""color"":""#8FD18F"",""team"":null},{""id"":""76561190000000005"",""name"":""Echo"",""color"":""#E6C866"",""team"":null},{""id"":""76561190000000003"",""name"":""Charlie"",""color"":""#C48CFF"",""team"":null}],""games"":[{""match_id"":""f4b88d40-46e7-4575-94a6-f16508cea21a"",""started_at"":""2026-09-01T13:40:00+00:00"",""duration_s"":200,""scores"":{""76561190000000001"":3,""76561190000000002"":1,""76561190000000003"":0},""points"":{""76561190000000001"":6,""76561190000000002"":2,""76561190000000003"":0},""timelines"":{""76561190000000001"":{""kills"":[[100.0,0],[200.0,3]],""score"":[[22.2,0.5],[44.4,1.0],[66.7,1.0],[88.9,1.0],[111.1,1.5],[133.3,1.5],[155.6,2.0],[177.8,2.5],[200.0,3.0]]},""76561190000000002"":{""kills"":[[100.0,0],[200.0,1]],""score"":[[22.2,0.0],[44.4,0.0],[66.7,0.5],[88.9,1.0],[111.1,1.0],[133.3,1.0],[155.6,1.0],[177.8,1.0],[200.0,1.0]]},""76561190000000003"":{""kills"":[[100.0,0],[200.0,0]],""score"":[[22.2,0.0],[44.4,0.0],[66.7,0.0],[88.9,0.0],[111.1,0.0],[133.3,0.5],[155.6,0.0],[177.8,0.0],[200.0,0.0]]}},""available"":[""kills"",""score""],""picks"":[{""t"":null,""id"":""76561190000000001"",""card"":""CardA0""},{""t"":null,""id"":""76561190000000003"",""card"":""CardC2""},{""t"":null,""id"":""76561190000000002"",""card"":""CardB1""}],""deaths"":[],""end_build"":{""76561190000000001"":[""CardA0""],""76561190000000002"":[""CardB1""],""76561190000000003"":[""CardC2""]},""end_stats"":{},""totals"":{""76561190000000001"":{""damage"":400,""kills"":3},""76561190000000002"":{""damage"":200,""kills"":1},""76561190000000003"":{""damage"":100,""kills"":0}},""settings"":{""score_target"":3,""card_cap"":5,""initial_picks"":1,""card_candidates"":5,""same_card_rule"":false,""sudden_death"":false}},{""match_id"":""f3c9967a-6777-4d26-9c76-eb68d3c65e5a"",""started_at"":""2026-09-01T13:50:00+00:00"",""duration_s"":200,""scores"":{""76561190000000002"":3,""76561190000000001"":1,""76561190000000004"":0},""points"":{""76561190000000002"":6,""76561190000000001"":2,""76561190000000004"":0},""timelines"":{""76561190000000002"":{""kills"":[[100.0,0],[200.0,3]],""score"":[[22.2,0.5],[44.4,1.0],[66.7,1.0],[88.9,1.0],[111.1,1.5],[133.3,2.0],[155.6,2.0],[177.8,2.5],[200.0,3.0]]},""76561190000000001"":{""kills"":[[100.0,0],[200.0,1]],""score"":[[22.2,0.0],[44.4,0.0],[66.7,0.5],[88.9,1.0],[111.1,1.0],[133.3,1.0],[155.6,1.0],[177.8,1.0],[200.0,1.0]]},""76561190000000004"":{""kills"":[[100.0,0],[200.0,0]],""score"":[[22.2,0.0],[44.4,0.0],[66.7,0.0],[88.9,0.0],[111.1,0.0],[133.3,0.0],[155.6,0.5],[177.8,0.5],[200.0,0.0]]}},""available"":[""kills"",""score""],""picks"":[{""t"":null,""id"":""76561190000000004"",""card"":""CardD3""},{""t"":null,""id"":""76561190000000002"",""card"":""CardB1""},{""t"":null,""id"":""76561190000000001"",""card"":""CardA0""}],""deaths"":[],""end_build"":{""76561190000000002"":[""CardB1""],""76561190000000001"":[""CardA0""],""76561190000000004"":[""CardD3""]},""end_stats"":{},""totals"":{""76561190000000002"":{""damage"":400,""kills"":3},""76561190000000001"":{""damage"":200,""kills"":1},""76561190000000004"":{""damage"":100,""kills"":0}},""settings"":{""score_target"":3,""card_cap"":5,""initial_picks"":1,""card_candidates"":5,""same_card_rule"":false,""sudden_death"":false}},{""match_id"":""d9a3800e-e586-4cd6-bf94-4d5b8e02fcb0"",""started_at"":""2026-09-01T14:00:00+00:00"",""duration_s"":200,""scores"":{""76561190000000001"":3,""76561190000000002"":1,""76561190000000004"":0,""76561190000000005"":0},""points"":{""76561190000000001"":6,""76561190000000002"":2,""76561190000000004"":0,""76561190000000005"":0},""timelines"":{""76561190000000001"":{""kills"":[[100.0,0],[200.0,3]],""score"":[[18.2,0.0],[36.4,0.5],[54.5,1.0],[72.7,1.0],[90.9,1.0],[109.1,1.0],[127.3,1.5],[145.5,2.0],[163.6,2.5],[181.8,2.5],[200.0,3.0]]},""76561190000000002"":{""kills"":[[100.0,0],[200.0,1]],""score"":[[18.2,0.0],[36.4,0.0],[54.5,0.0],[72.7,0.5],[90.9,0.5],[109.1,1.0],[127.3,1.0],[145.5,1.0],[163.6,1.0],[181.8,1.5],[200.0,1.0]]},""76561190000000004"":{""kills"":[[100.0,0],[200.0,0]],""score"":[[18.2,0.0],[36.4,0.0],[54.5,0.0],[72.7,0.0],[90.9,0.0],[109.1,0.0],[127.3,0.0],[145.5,0.0],[163.6,0.0],[181.8,0.0],[200.0,0.0]]},""76561190000000005"":{""kills"":[[100.0,0],[200.0,0]],""score"":[[18.2,0.5],[36.4,0.5],[54.5,0.0],[72.7,0.0],[90.9,0.5],[109.1,0.0],[127.3,0.0],[145.5,0.0],[163.6,0.0],[181.8,0.0],[200.0,0.0]]}},""available"":[""kills"",""score""],""picks"":[{""t"":null,""id"":""76561190000000004"",""card"":""CardD3""},{""t"":null,""id"":""76561190000000002"",""card"":""CardB1""},{""t"":null,""id"":""76561190000000001"",""card"":""CardA0""},{""t"":null,""id"":""76561190000000005"",""card"":""CardE4""}],""deaths"":[],""end_build"":{""76561190000000001"":[""CardA0""],""76561190000000002"":[""CardB1""],""76561190000000004"":[""CardD3""],""76561190000000005"":[""CardE4""]},""end_stats"":{},""totals"":{""76561190000000001"":{""damage"":400,""kills"":3},""76561190000000002"":{""damage"":200,""kills"":1},""76561190000000004"":{""damage"":100,""kills"":0},""76561190000000005"":{""damage"":100,""kills"":0}},""settings"":{""score_target"":3,""card_cap"":5,""initial_picks"":1,""card_candidates"":5,""same_card_rule"":false,""sudden_death"":false}}],""set_summary"":{""rating"":{""76561190000000001"":{""before"":1500.0,""after"":1519.5,""delta"":19.5},""76561190000000002"":{""before"":1500.0,""after"":1503.0,""delta"":3.0},""76561190000000003"":{""before"":1500.0,""after"":1490.0,""delta"":-10.0},""76561190000000004"":{""before"":1500.0,""after"":1486.0,""delta"":-14.0},""76561190000000005"":{""before"":1500.0,""after"":1492.0,""delta"":-8.0}},""gold"":{""76561190000000001"":7,""76561190000000002"":5,""76561190000000003"":1,""76561190000000004"":2,""76561190000000005"":1}},""truncated"":false,""games_omitted"":0}";

        // A display name and a card name carrying every character a string-blind
        // slicer would take for structure.
        private const string HOSTILE =
            @"{""v"":1,""kind"":""casual"",""players"":[{""id"":""1"",""name"":""Br\""}],{[ace"",""color"":""#fff""},{""id"":""2"",""name"":""x""}],""games"":[{""match_id"":""m1"",""scores"":{""1"":2,""2"":1},""picks"":[{""id"":""1"",""card"":""x]}\""{""},{""id"":""2"",""card"":""""}]}]}";

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            RankedCases(r);
            CasualCases(r);
            TeamCases(r);
            OvtCases(r);
            FfaCases(r);
            RobustnessCases(r);
            return r;
        }

        private static void RankedCases(SelfTestResult r)
        {
            var e = Parse(RANKED_SERIES);
            if (e == null) { Check(r, "ranked: the envelope parses", false, "null"); return; }
            Check(r, "ranked: kind, version and roster order", e.V == 1 && e.Kind == "ranked" && Ids(e) == B + "," + A,
                  e.V + " " + e.Kind + " " + Ids(e));
            bool three = e.Games.Count == 3;
            Check(r, "ranked: three games in order with their scores", three
                  && Sc(e.Games[0], A) == 5 && Sc(e.Games[0], B) == 3 && Sc(e.Games[1], B) == 5 && Sc(e.Games[1], A) == 2
                  && Sc(e.Games[2], A) == 5 && Sc(e.Games[2], B) == 4, Scores(e));
            var g0 = three ? e.Games[0] : new Game();
            Check(r, "ranked: game 1 picks in pick order with their pickers", g0.Picks.Count == 2
                  && g0.Picks[0].Id == A && g0.Picks[0].Card == "BombsAway" && g0.Picks[1].Id == B && g0.Picks[1].Card == "Leach",
                  PickText(g0));
            List<Pt> score = Stream(g0, A, "score");
            Check(r, "ranked: the score timeline keeps every sample", score != null && score.Count == 20 && score[0].X >= 0f,
                  score == null ? "no stream" : score.Count + " samples, first t=" + score[0].X.ToString(INV));
            bool deathsOk = g0.Deaths.Count > 0;
            foreach (var d in g0.Deaths) deathsOk &= d.T >= 0f && (d.Id == A || d.Id == B);
            Check(r, "ranked: deaths carry a time and a roster id", deathsOk, g0.Deaths.Count + " deaths");
            Check(r, "ranked: set rating before, after and delta", Rt(e, A, 1600f, 1611.5f, 11.5f) && Rt(e, B, 1500f, 1488.5f, -11.5f),
                  RatingText(e, A) + " / " + RatingText(e, B));
            Check(r, "ranked: set gold per player", Gold(e, A) == 25 && Gold(e, B) == 5 && e.Gold.Count == 2,
                  Gold(e, A) + "/" + Gold(e, B));
            Check(r, "ranked: the available streams are the recorded ones", g0.Available.Contains("score")
                  && g0.Available.Contains("damage") && !g0.Available.Contains("ping"), string.Join(",", Sorted(g0.Available)));
        }

        private static void CasualCases(SelfTestResult r)
        {
            var e = Parse(CASUAL_SESSION);
            if (e == null) { Check(r, "casual: the envelope parses", false, "null"); return; }
            Check(r, "casual: a truncated set counts the game it left out", e.Kind == "casual" && e.Truncated
                  && e.GamesOmitted == 1 && e.Games.Count == 2, e.Kind + " truncated=" + e.Truncated + " omitted="
                  + e.GamesOmitted + " games=" + e.Games.Count);
            Dictionary<string, float> tb = null;
            if (e.Games.Count > 0) e.Games[0].Totals.TryGetValue(B, out tb);
            Check(r, "casual: totals are sparse - an unrecorded counter has no key, never a zero",
                  tb != null && tb.ContainsKey("deaths") && tb["deaths"] == 10f && !tb.ContainsKey("kills"),
                  tb == null ? "no totals" : string.Join(",", Sorted(tb.Keys)));
            Check(r, "casual: no rating, the set gold per player", e.Rating.Count == 0 && Gold(e, A) == 2 && Gold(e, B) == 2,
                  "rating=" + e.Rating.Count + " gold=" + Gold(e, A) + "/" + Gold(e, B));
        }

        private static void TeamCases(SelfTestResult r)
        {
            var e = Parse(TEAM_SERIES);
            if (e == null) { Check(r, "team: the envelope parses", false, "null"); return; }
            Check(r, "team: kind and two sides of two", e.Kind == "team" && Ids(e) == A + "," + C + "," + B + "," + D
                  && Teams(e) == "1,1,2,2", e.Kind + " " + Ids(e) + " teams " + Teams(e));
            var g0 = e.Games.Count == 2 ? e.Games[0] : new Game();
            Check(r, "team: every seat carries its side's rounds", Sc(g0, A) == 5 && Sc(g0, C) == 5 && Sc(g0, B) == 3 && Sc(g0, D) == 3,
                  Scores(e));
            Dictionary<string, List<Pt>> cs;
            bool empty = g0.Timelines.TryGetValue(C, out cs) && cs != null && cs.Count == 0;
            Check(r, "team: a seat with no telemetry has an empty stream map", empty && Stream(g0, A, "damage") != null,
                  empty ? "C empty, A damage " + (Stream(g0, A, "damage") != null) : "C missing or non-empty");
            RatingEntry rc;
            bool deltaOnly = e.Rating.TryGetValue(C, out rc) && rc != null && !rc.Before.HasValue && !rc.After.HasValue
                             && Math.Abs(rc.Delta - 9f) < 1e-3f;
            Check(r, "team: a rating delta without before and after", deltaOnly, RatingText(e, C));
            Check(r, "team: no set gold is an empty map", e.Gold.Count == 0, "gold entries " + e.Gold.Count);
        }

        private static void OvtCases(SelfTestResult r)
        {
            var e = Parse(OVT_SERIES);
            if (e == null) { Check(r, "1v2: the envelope parses", false, "null"); return; }
            Check(r, "1v2: the solo is side 1 and the duo side 2", e.Kind == "ovt" && Ids(e) == A + "," + B + "," + C
                  && Teams(e) == "1,2,2", e.Kind + " " + Ids(e) + " teams " + Teams(e));
            var g1 = e.Games.Count == 2 ? e.Games[1] : new Game();
            Check(r, "1v2: game 2 scores and its one recorded stream", Sc(g1, A) == 3 && Sc(g1, B) == 5 && Sc(g1, C) == 5
                  && g1.Available.Count == 1 && g1.Available.Contains("damage"), Scores(e) + " available "
                  + string.Join(",", Sorted(g1.Available)));
            Check(r, "1v2: rating deltas per seat", Rt(e, A, null, null, 6f) && Rt(e, B, null, null, -3f),
                  RatingText(e, A) + " / " + RatingText(e, B));
        }

        private static void FfaCases(SelfTestResult r)
        {
            var e = Parse(FFA_LOBBY);
            if (e == null) { Check(r, "ffa: the envelope parses", false, "null"); return; }
            Check(r, "ffa: kind, three games and the union roster in order", e.Kind == "ffa" && e.Games.Count == 3
                  && Ids(e) == A + "," + B + "," + D + "," + E + "," + C, e.Kind + " games=" + e.Games.Count + " " + Ids(e));
            if (e.Games.Count != 3) return;
            Game g0 = e.Games[0], g1 = e.Games[1], g2 = e.Games[2];
            Check(r, "ffa: a player who sat a game out has no score key in it", g0.Scores.Count == 3 && g0.Scores.ContainsKey(C)
                  && !g0.Scores.ContainsKey(D) && g1.Scores.ContainsKey(D) && !g1.Scores.ContainsKey(C),
                  "g1 " + string.Join(",", Sorted(g0.Scores.Keys)) + " g2 " + string.Join(",", Sorted(g1.Scores.Keys)));
            List<string> ab;
            bool built = g2.EndBuild.TryGetValue(A, out ab) && ab != null && ab.Count == 1 && ab[0] == "CardA0";
            bool picked = g2.Picks.Count == 4 && g2.Picks.Exists(p => p.Id == E && p.Card == "CardE4");
            Check(r, "ffa: game 3 picks and end builds", built && picked, PickText(g2));
            Check(r, "ffa: the set rating and gold over the sitting", Rt(e, C, 1500f, 1490f, -10f) && Gold(e, A) == 7,
                  RatingText(e, C) + " gold A " + Gold(e, A));
            List<Pt> kills = Stream(g0, A, "kills");
            Check(r, "ffa: the kills stream parses", kills != null && kills.Count == 2,
                  kills == null ? "no stream" : kills.Count + " samples");
        }

        private static void RobustnessCases(SelfTestResult r)
        {
            var e = Parse(HOSTILE);
            bool whole = e != null && e.Players.Count == 2 && e.Players[0].Name == "Br\"}],{[ace" && e.Players[1].Id == "2"
                         && e.Games.Count == 1 && e.Games[0].Picks.Count == 1 && e.Games[0].Picks[0].Card == "x]}\"{";
            Check(r, "hostile strings: braces and quotes inside a name or card do not split members", whole,
                  e == null ? "null" : e.Players.Count + " players, first=" + (e.Players.Count > 0 ? e.Players[0].Name : "-")
                  + " games=" + e.Games.Count + " picks=" + (e.Games.Count > 0 ? e.Games[0].Picks.Count : -1));
            int p0 = HOSTILE.IndexOf(@"{""id"":""1""", StringComparison.Ordinal);
            int aware = MatchBrace(HOSTILE, p0), blind = BlindMatch(HOSTILE, p0, '{', '}');
            Check(r, "hostile strings (control): a string-blind matcher cuts the first player short", p0 > 0 && blind >= 0
                  && blind < aware && HOSTILE.Substring(p0, aware - p0 + 1).EndsWith(@"""color"":""#fff""}", StringComparison.Ordinal),
                  "player object at " + p0 + ": aware end " + aware + ", blind end " + blind);
            Check(r, "a pick with an empty card is dropped", e != null && e.Games.Count == 1 && e.Games[0].Picks.Count == 1,
                  e == null || e.Games.Count == 0 ? "-" : e.Games[0].Picks.Count + " picks");
            var v2 = Parse(@"{""v"":2,""kind"":""ranked"",""players"":[],""games"":[]}");
            Check(r, "a later version still parses and says so", v2 != null && v2.V == 2, v2 == null ? "null" : "v=" + v2.V);
            bool none = Parse("") == null && Parse("[1,2]") == null && Parse(@"{""v"":1") == null && Parse(null) == null;
            Check(r, "not an envelope: empty, an array, unterminated, null", none, none ? "all null" : "one parsed");
            string s = Str(@"""a\""b\\cA""");
            Check(r, "string escapes decode: quote, backslash, unicode", s == "a\"b\\cA", s);
            bool num = Num("null", -1f) == -1f && Num(@"""5""", -1f) == -1f && Num("2.5", 0f) == 2.5f && Num("true", 0f) == 1f;
            Check(r, "a null or quoted scalar falls back, a number parses", num,
                  Num("null", -1f).ToString(INV) + "," + Num(@"""5""", -1f).ToString(INV) + "," + Num("2.5", 0f).ToString(INV));
        }

        // -- helpers -------------------------------------------------------------

        /// <summary>The matcher as it would be without string awareness: the
        /// control that proves HOSTILE is hostile.</summary>
        private static int BlindMatch(string s, int open, char o, char c)
        {
            int depth = 0;
            for (int i = open; i < s.Length; i++)
            {
                if (s[i] == o) depth++;
                else if (s[i] == c) { depth--; if (depth == 0) return i; }
            }
            return -1;
        }

        private static string Ids(Envelope e)
        {
            var l = new List<string>();
            foreach (var p in e.Players) l.Add(p.Id);
            return string.Join(",", l.ToArray());
        }

        private static string Teams(Envelope e)
        {
            var l = new List<string>();
            foreach (var p in e.Players) l.Add(p.Team.ToString(INV));
            return string.Join(",", l.ToArray());
        }

        private static int Sc(Game g, string id) { int v; return g.Scores.TryGetValue(id, out v) ? v : -999; }

        private static int Gold(Envelope e, string id) { int v; return e.Gold.TryGetValue(id, out v) ? v : -999; }

        private static List<Pt> Stream(Game g, string id, string name)
        {
            Dictionary<string, List<Pt>> st;
            List<Pt> s;
            return g.Timelines.TryGetValue(id, out st) && st != null && st.TryGetValue(name, out s) ? s : null;
        }

        private static bool Rt(Envelope e, string id, float? before, float? after, float delta)
        {
            RatingEntry x;
            if (!e.Rating.TryGetValue(id, out x) || x == null) return false;
            return Same(x.Before, before) && Same(x.After, after) && Math.Abs(x.Delta - delta) < 1e-3f;
        }

        private static bool Same(float? a, float? b)
            => a.HasValue == b.HasValue && (!a.HasValue || Math.Abs(a.Value - b.Value) < 1e-3f);

        private static string RatingText(Envelope e, string id)
        {
            RatingEntry x;
            if (!e.Rating.TryGetValue(id, out x) || x == null) return "none";
            return (x.Before.HasValue ? x.Before.Value.ToString(INV) : "null") + "->"
                   + (x.After.HasValue ? x.After.Value.ToString(INV) : "null") + " (" + x.Delta.ToString(INV) + ")";
        }

        private static string Scores(Envelope e)
        {
            var sb = new StringBuilder();
            foreach (var g in e.Games)
            {
                if (sb.Length > 0) sb.Append(" | ");
                foreach (var id in Sorted(g.Scores.Keys)) sb.Append(id.Substring(id.Length - 1)).Append('=').Append(g.Scores[id]).Append(' ');
            }
            return sb.ToString().Trim();
        }

        private static string PickText(Game g)
        {
            var l = new List<string>();
            foreach (var p in g.Picks) l.Add(p.Id.Substring(p.Id.Length - 1) + ":" + p.Card);
            return string.Join(",", l.ToArray());
        }

        private static List<string> Sorted(IEnumerable<string> xs)
        {
            var l = new List<string>(xs);
            l.Sort(StringComparer.Ordinal);
            return l;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}

"""The frozen default-deny grammar of the a1 walks (rehearsal-four
round 7, child ga1; ruling REHEARSAL-FOUR-R6 (1)(b)).

GENERATED ONCE by RF/r7/ga1/gen_shapes.py from the REAL spans the a1
walks visit at a30d37f6 (backend/api unchanged since), then frozen and
PRUNED by hand: no shape a prior finding's program needs and the real
spans do not use. Never regenerated to fit a file: a span that needs a
shape outside these sets is conformed, or the question goes to the
integrator. Each shape carries the first real file:line using it.

Round 8 (ruling REHEARSAL-FOUR-R7-A1): A1_BINDINGS anchors every
meaningful store and every transaction end at its frozen position (M3),
A1_CALLEES is the only route to a callee outside a module's own
namespace (M4), A1_NAMEDTUPLES is the complete definition scope of
region_pick.py (M5), and the census block below is ga1's round-7 freeze
restored, minus three removed shapes (M4, M7, M8).
"""


# (file, def line, name, nodes) of every span the a1 walks admit
A1_SPANS = (
    ('main.py', 4295, '_team_clear_dc_fallback_marker', 34),
    ('main.py', 6449, '_parse_version', 44),
    ('main.py', 16342, '_lock_queue_rows_ordered', 168),
    ('main.py', 16795, '_admission_key', 36),
    ('main.py', 16799, '_lease_admission_gate', 624),
    ('main.py', 16938, '_lease_acquire', 115),
    ('main.py', 16988, '_lease_acquire_many', 108),
    ('main.py', 17374, '_lock_snapshot_rows', 143),
    ('main.py', 17413, '_lease_live_claim_strict', 29),
    ('main.py', 17439, '_formation_lease_conflict', 113),
    ('main.py', 18552, '_region_pings_newer', 63),
    ('main.py', 18630, '_region_mode_of', 96),
    ('main.py', 18649, '_region_current', 33),
    ('main.py', 18661, '_region_volumes', 113),
    ('main.py', 18683, '_group_region', 706),
    ('main.py', 19899, 'queue_poll', 2650),
    ('main.py', 28308, '_bet_fighter_tax', 88),
    ('main.py', 28327, '_credit_bet_fighter_tax', 113),
    ('main.py', 28352, '_credit_team_bet_fighter_tax', 115),
    ('main.py', 37777, '_return_stake_exactly', 96),
    ('main.py', 48796, '_balance_teams', 230),
    ('main.py', 48816, '_team_balance_rating', 49),
    ('main.py', 49167, 'team_queue_poll', 4249),
    ('main.py', 51053, '_reconcile_team_series_bets', 606),
    ('main.py', 51683, '_team_quartet_key', 26),
    ('main.py', 51691, '_team_quartet_lock', 27),
    ('main.py', 51708, '_team_series_resumable', 139),
    ('main.py', 51736, '_team_lock_family_pick', 441),
    ('main.py', 51835, '_team_resolve_live_family', 214),
    ('main.py', 51875, '_team_relock_existing_series', 271),
    ('main.py', 53486, 'ovt_queue_poll', 2152),
    ('main.py', 54211, '_mrw_mod', 9),
    ('main.py', 55772, '_ffa_gather_decide', 92),
    ('main.py', 56222, '_rules_normalize', 114),
    ('main.py', 56244, '_rules_json', 64),
    ('main.py', 56277, '_mod_version_at_least', 39),
    ('main.py', 56289, '_ffa_roster_clears_proximity_floor', 59),
    ('main.py', 56305, '_request_mod_version', 28),
    ('main.py', 56329, '_rules_for_queue_match', 78),
    ('main.py', 56352, '_rules_members', 136),
    ('main.py', 56374, '_rules_for_members', 118),
    ('main.py', 56839, '_ffa_sort_key', 25),
    ('main.py', 57187, '_player_body_color', 88),
    ('main.py', 57207, '_team_color_holders', 51),
    ('main.py', 57227, '_stamp_team_series_colors', 249),
    ('main.py', 62065, '_asm_sqlstate', 119),
    ('main.py', 64662, '_ffa_queue_poll_inner', 2939),
    ('main.py', 73439, '_assert_no_service_subject', 96),
    ('main.py', 73487, '_service_player_uuids', 183),
    ('match_hold.py', 212, 'caps_token_sql', 16),
    ('match_hold.py', 235, '_mode_or_400', 23),
    ('match_hold.py', 351, '_latch_sql', 78),
    ('match_hold.py', 364, '_hold_latch', 108),
    ('match_report_window.py', 47, '_get', 25),
    ('match_report_window.py', 51, 'held_overlap', 115),
    ('match_report_window.py', 68, 'anchor_fresh', 42),
    ('match_report_window.py', 77, 'series_fresh', 40),
    ('match_report_window.py', 85, 'series_holds', 30),
    ('region_pick.py', 39, '_is_number', 26),
    ('region_pick.py', 43, '_clean_map', 98),
    ('region_pick.py', 62, '_baseline', 171),
    ('region_pick.py', 89, 'home_of', 40),
    ('region_pick.py', 101, 'pick_region_for_group', 54),
    ('region_pick.py', 186, '_pick', 892),
    ('tournaments.py', 279, '_region_candidate_volumes', 47),
)


A1_NODES = 20183


A1_SHAPES = frozenset({
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Global|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:64662
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:16342
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Import|Return|While],decorator_list=[Call],returns=-,type_comment=-,type_params=[])',  # main.py:19899
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[Call],returns=-,type_comment=-,type_params=[])',  # main.py:53486
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:16988
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:56352
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:51875
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return|Try],decorator_list=[],returns=Subscript,type_comment=-,type_params=[])',  # main.py:16799
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:57207
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:56374
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|FunctionDef|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:18683
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|Global|If|Return],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:73487
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:28352
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:16938
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # match_hold.py:364
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:18661
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # tournaments.py:279
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|Try],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:57227
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[AsyncWith|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:57187
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:51691
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|For|If],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:17374
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|If],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:28327
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:17413
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:51053
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Try],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',  # main.py:4295
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Assign|Expr|FunctionDef|Return],decorator_list=[],returns=Subscript,type_comment=-,type_params=[])',  # main.py:48796
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Assign|Expr|If|Return],decorator_list=[],returns=Subscript,type_comment=-,type_params=[])',  # main.py:28308
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|FunctionDef|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick.py:186
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:18630
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # match_report_window.py:51
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:55772
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:51708
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:56329
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return|While],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:62065
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # match_hold.py:351
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:18552
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:48816
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If|Try],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:56277
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:54211
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # main.py:51683
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:56305
    '<root>>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',  # match_hold.py:235
    '<root>>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # match_report_window.py:47
    '<root>>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=Subscript,type_comment=-,type_params=[])',  # main.py:16795
    '<root>>FunctionDef(name=str,args=arguments,body=[Try],decorator_list=[],returns=Subscript,type_comment=-,type_params=[])',  # main.py:6449
    'Assert.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # main.py:48801
    'Assert.test>Compare(left=Name,ops=[Gt],comparators=[Name])',  # main.py:28323
    'Assign.targets>Name(id=str,ctx=Store)',  # main.py:16377
    'Assign.targets>Subscript(value=Call,slice=Constant,ctx=Store)',  # main.py:65119
    'Assign.targets>Subscript(value=Name,slice=Call,ctx=Store)',  # main.py:56370
    'Assign.targets>Subscript(value=Name,slice=Constant,ctx=Store)',  # main.py:18772
    'Assign.targets>Subscript(value=Name,slice=Name,ctx=Store)',  # main.py:18642
    'Assign.targets>Subscript(value=Name,slice=Subscript,ctx=Store)',  # main.py:18724
    'Assign.targets>Tuple(elts=[Name],ctx=Store)',  # main.py:16950
    'Assign.targets>Tuple(elts=[Subscript],ctx=Store)',  # main.py:18677
    'Assign.value>Await(value=Call)',  # main.py:16950
    'Assign.value>BinOp(left=BinOp,op=Add,right=BinOp)',  # main.py:28364
    'Assign.value>BinOp(left=Call,op=Add,right=Constant)',  # main.py:18642
    'Assign.value>BinOp(left=Name,op=Add,right=List)',  # main.py:49363
    'Assign.value>BinOp(left=Name,op=FloorDiv,right=Constant)',  # main.py:28365
    'Assign.value>BinOp(left=Name,op=Sub,right=Call)',  # main.py:20092
    'Assign.value>BinOp(left=Name,op=Sub,right=Name)',  # main.py:28318
    'Assign.value>BoolOp(op=And,values=[Call])',  # main.py:56336
    'Assign.value>BoolOp(op=And,values=[Call|Compare])',  # main.py:65269
    'Assign.value>BoolOp(op=And,values=[Compare])',  # main.py:49388
    'Assign.value>BoolOp(op=Or,values=[BoolOp|Compare])',  # main.py:53651
    'Assign.value>BoolOp(op=Or,values=[Call|Constant])',  # main.py:18758
    'Assign.value>BoolOp(op=Or,values=[Call|List])',  # main.py:18757
    'Assign.value>BoolOp(op=Or,values=[Call|Subscript])',  # main.py:18740
    'Assign.value>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:20188
    'Assign.value>Call(func=Attribute,args=[Attribute],keywords=[])',  # main.py:20062
    'Assign.value>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:16918
    'Assign.value>Call(func=Attribute,args=[Constant],keywords=[])',  # region_pick.py:201
    'Assign.value>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # region_pick.py:193
    'Assign.value>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # match_hold.py:352
    'Assign.value>Call(func=Attribute,args=[Name],keywords=[])',  # main.py:18727
    'Assign.value>Call(func=Attribute,args=[Name],keywords=[keyword])',  # main.py:51725
    'Assign.value>Call(func=Attribute,args=[Subscript|Tuple],keywords=[])',  # main.py:18732
    'Assign.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:16828
    'Assign.value>Call(func=Attribute,args=[],keywords=[keyword])',  # main.py:18739
    'Assign.value>Call(func=Name,args=[Attribute],keywords=[])',  # main.py:20241
    'Assign.value>Call(func=Name,args=[BinOp],keywords=[])',  # main.py:28321
    'Assign.value>Call(func=Name,args=[BinOp|Call],keywords=[])',  # main.py:65146
    'Assign.value>Call(func=Name,args=[BinOp|Constant],keywords=[])',  # main.py:64819
    'Assign.value>Call(func=Name,args=[BinOp|Name],keywords=[])',  # main.py:55793
    'Assign.value>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:49386
    'Assign.value>Call(func=Name,args=[Call],keywords=[])',  # main.py:18645
    'Assign.value>Call(func=Name,args=[Call|Name],keywords=[])',  # main.py:65266
    'Assign.value>Call(func=Name,args=[Constant],keywords=[])',  # match_report_window.py:54
    'Assign.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # main.py:49897
    'Assign.value>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:48809
    'Assign.value>Call(func=Name,args=[GeneratorExp],keywords=[keyword])',  # main.py:64816
    'Assign.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:17471
    'Assign.value>Call(func=Name,args=[Name],keywords=[keyword])',  # main.py:18748
    'Assign.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:64807
    'Assign.value>Call(func=Name,args=[Name|Subscript],keywords=[keyword])',  # main.py:20220
    'Assign.value>Call(func=Name,args=[SetComp],keywords=[keyword])',  # main.py:16826
    'Assign.value>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:16912
    'Assign.value>Call(func=Name,args=[],keywords=[])',  # main.py:18743
    'Assign.value>Call(func=Name,args=[],keywords=[keyword])',  # main.py:20276
    'Assign.value>Compare(left=Name,ops=[LtE],comparators=[Name])',  # region_pick.py:249
    'Assign.value>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # main.py:51125
    'Assign.value>Constant(value=NoneType)',  # main.py:18737
    'Assign.value>Constant(value=bool)',  # main.py:16837
    'Assign.value>Constant(value=float)',  # main.py:64817
    'Assign.value>Constant(value=int)',  # main.py:19981
    'Assign.value>Constant(value=str)',  # main.py:51134
    'Assign.value>Dict(keys=[Constant],values=[Call])',  # main.py:53738
    'Assign.value>Dict(keys=[Constant],values=[Call|Constant|List|Name])',  # region_pick.py:227
    'Assign.value>Dict(keys=[Constant],values=[Call|Name])',  # main.py:20456
    'Assign.value>Dict(keys=[Constant],values=[Call|Name|Subscript])',  # main.py:49697
    'Assign.value>Dict(keys=[Constant],values=[Name|Subscript])',  # main.py:49760
    'Assign.value>Dict(keys=[Constant],values=[Subscript])',  # main.py:56248
    'Assign.value>Dict(keys=[Name],values=[Call])',  # main.py:49853
    'Assign.value>Dict(keys=[],values=[])',  # main.py:18638
    'Assign.value>DictComp(key=Attribute,value=Name,generators=[comprehension])',  # main.py:28363
    'Assign.value>DictComp(key=Call,value=Name,generators=[comprehension])',  # main.py:16892
    'Assign.value>DictComp(key=Call,value=Tuple,generators=[comprehension])',  # main.py:56360
    'Assign.value>DictComp(key=Subscript,value=Subscript,generators=[comprehension])',  # main.py:50068
    'Assign.value>IfExp(test=BoolOp,body=Name,orelse=Constant)',  # region_pick.py:204
    'Assign.value>IfExp(test=BoolOp,body=Subscript,orelse=Constant)',  # main.py:51096
    'Assign.value>IfExp(test=Call,body=Name,orelse=Dict)',  # region_pick.py:190
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Constant)',  # main.py:20365
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Set)',  # main.py:16875
    'Assign.value>IfExp(test=Compare,body=Constant,orelse=Constant)',  # main.py:51910
    'Assign.value>IfExp(test=Compare,body=Name,orelse=Name)',  # match_report_window.py:61
    'Assign.value>IfExp(test=Compare,body=Subscript,orelse=Constant)',  # main.py:18640
    'Assign.value>IfExp(test=Compare,body=Tuple,orelse=Constant)',  # main.py:18723
    'Assign.value>IfExp(test=Compare,body=Tuple,orelse=IfExp)',  # main.py:51105
    'Assign.value>IfExp(test=Name,body=Call,orelse=Call)',  # main.py:49390
    'Assign.value>IfExp(test=Name,body=Call,orelse=Constant)',  # main.py:51126
    'Assign.value>IfExp(test=Name,body=Call,orelse=Subscript)',  # main.py:53752
    'Assign.value>IfExp(test=Name,body=Call,orelse=Tuple)',  # main.py:51127
    'Assign.value>IfExp(test=Name,body=Compare,orelse=Compare)',  # region_pick.py:248
    'Assign.value>IfExp(test=Name,body=Constant,orelse=Constant)',  # main.py:51130
    'Assign.value>IfExp(test=Name,body=Name,orelse=BinOp)',  # main.py:73536
    'Assign.value>IfExp(test=Name,body=Name,orelse=IfExp)',  # region_pick.py:250
    'Assign.value>JoinedStr(values=[Constant|FormattedValue])',  # main.py:20217
    'Assign.value>List(elts=[Dict],ctx=Load)',  # main.py:50021
    'Assign.value>List(elts=[Name],ctx=Load)',  # main.py:62069
    'Assign.value>List(elts=[Subscript],ctx=Load)',  # main.py:49759
    'Assign.value>List(elts=[Tuple],ctx=Load)',  # main.py:20197
    'Assign.value>List(elts=[],ctx=Load)',  # main.py:16377
    'Assign.value>ListComp(elt=Attribute,generators=[comprehension])',  # region_pick.py:74
    'Assign.value>ListComp(elt=Call,generators=[comprehension])',  # main.py:16830
    'Assign.value>ListComp(elt=Name,generators=[comprehension])',  # main.py:20198
    'Assign.value>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:18715
    'Assign.value>ListComp(elt=Tuple,generators=[comprehension])',  # main.py:57243
    'Assign.value>Name(id=str,ctx=Load)',  # main.py:18669
    'Assign.value>Set(elts=[Subscript])',  # main.py:51799
    'Assign.value>SetComp(elt=Call,generators=[comprehension])',  # main.py:16884
    'Assign.value>SetComp(elt=Name,generators=[comprehension])',  # region_pick.py:189
    'Assign.value>Subscript(value=Call,slice=Constant,ctx=Load)',  # main.py:16839
    'Assign.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20066
    'Assign.value>Tuple(elts=[Attribute],ctx=Load)',  # region_pick.py:265
    'Assign.value>Tuple(elts=[Call],ctx=Load)',  # region_pick.py:241
    'Assign.value>Tuple(elts=[Call|Name],ctx=Load)',  # main.py:18677
    'Assign.value>Tuple(elts=[Call|Subscript],ctx=Load)',  # main.py:56370
    'Assign.value>Tuple(elts=[Constant|Dict|Name],ctx=Load)',  # main.py:18713
    'Assign.value>Tuple(elts=[Constant|Name],ctx=Load)',  # region_pick.py:269
    'Assign.value>Tuple(elts=[List],ctx=Load)',  # main.py:50044
    'Assign.value>Tuple(elts=[Name],ctx=Load)',  # main.py:18729
    'Assign.value>Tuple(elts=[Name|Subscript],ctx=Load)',  # main.py:18724
    'Assign.value>Tuple(elts=[Subscript],ctx=Load)',  # main.py:17482
    'Assign.value>UnaryOp(op=Not,operand=Name)',  # main.py:20177
    'Assign.value>UnaryOp(op=Not,operand=Subscript)',  # main.py:49407
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Call])',  # main.py:19899
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant])',  # main.py:28327
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Name])',  # main.py:51053
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Tuple])',  # main.py:28352
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # main.py:4295
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant],kwarg=-,defaults=[])',  # main.py:16342
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant|Tuple],kwarg=-,defaults=[Constant])',  # main.py:16799
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant|Tuple],kwarg=-,defaults=[Constant|Name])',  # main.py:16938
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant|Tuple],kwarg=-,defaults=[])',  # main.py:17439
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[NoneType],kwarg=-,defaults=[])',  # main.py:37777
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Tuple],kwarg=-,defaults=[Constant|Name])',  # main.py:16988
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:19987
    'AsyncFunctionDef.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # main.py:28364
    'AsyncFunctionDef.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # main.py:18757
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:16826
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:16837
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # main.py:49697
    'AsyncFunctionDef.body>Assign(targets=[Name],value=DictComp,type_comment=-)',  # main.py:16892
    'AsyncFunctionDef.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:16875
    'AsyncFunctionDef.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',  # main.py:53821
    'AsyncFunctionDef.body>Assign(targets=[Name],value=List,type_comment=-)',  # main.py:16377
    'AsyncFunctionDef.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # main.py:16830
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:18669
    'AsyncFunctionDef.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # main.py:16884
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:16910
    'AsyncFunctionDef.body>Assign(targets=[Subscript],value=Constant,type_comment=-)',  # main.py:65309
    'AsyncFunctionDef.body>Assign(targets=[Tuple],value=Await,type_comment=-)',  # main.py:17001
    'AsyncFunctionDef.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # main.py:19933
    'AsyncFunctionDef.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # main.py:18713
    'AsyncFunctionDef.body>AsyncWith(items=[withitem],body=[Assign],type_comment=-)',  # main.py:57194
    'AsyncFunctionDef.body>Expr(value=Await)',  # main.py:16958
    'AsyncFunctionDef.body>Expr(value=Call)',  # main.py:16876
    'AsyncFunctionDef.body>Expr(value=Constant)',  # main.py:4296
    'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',  # main.py:53741
    'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',  # main.py:20429
    'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[If],orelse=[],type_comment=-)',  # main.py:16381
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Assign],orelse=[],type_comment=-)',  # main.py:56369
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Assign|Expr],orelse=[],type_comment=-)',  # main.py:51909
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # main.py:51767
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:16911
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # main.py:17008
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Expr|If],orelse=[],type_comment=-)',  # main.py:51794
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # main.py:16378
    'AsyncFunctionDef.body>For(target=Name,iter=Tuple,body=[Expr],orelse=[],type_comment=-)',  # main.py:50129
    'AsyncFunctionDef.body>For(target=Tuple,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # main.py:65289
    'AsyncFunctionDef.body>For(target=Tuple,iter=Call,body=[Expr|If],orelse=[],type_comment=-)',  # main.py:17400
    'AsyncFunctionDef.body>For(target=Tuple,iter=Name,body=[Assign|If|Return],orelse=[],type_comment=-)',  # main.py:17474
    'AsyncFunctionDef.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:18755
    'AsyncFunctionDef.body>Global(names=[str])',  # main.py:65135
    'AsyncFunctionDef.body>If(test=Await,body=[Expr|Return],orelse=[])',  # main.py:49681
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign],orelse=[])',  # main.py:65140
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',  # main.py:49321
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',  # main.py:20121
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return|Try],orelse=[])',  # main.py:49254
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # main.py:53556
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Expr],orelse=[])',  # main.py:28344
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',  # main.py:20112
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Return],orelse=[])',  # main.py:18671
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Try],orelse=[])',  # main.py:73507
    'AsyncFunctionDef.body>If(test=Call,body=[Raise],orelse=[])',  # main.py:73452
    'AsyncFunctionDef.body>If(test=Call,body=[Return],orelse=[])',  # main.py:16893
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign],orelse=[])',  # main.py:18768
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr],orelse=[Expr])',  # main.py:20076
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|For],orelse=[Assign])',  # main.py:50043
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|If|Return],orelse=[])',  # main.py:49997
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',  # main.py:65237
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',  # main.py:49758
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr],orelse=[])',  # main.py:17472
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Raise],orelse=[])',  # main.py:20054
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # main.py:20414
    'AsyncFunctionDef.body>If(test=Compare,body=[Raise],orelse=[])',  # main.py:16375
    'AsyncFunctionDef.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:28336
    'AsyncFunctionDef.body>If(test=Name,body=[Assign|Expr],orelse=[])',  # main.py:51806
    'AsyncFunctionDef.body>If(test=Name,body=[Assign|Return],orelse=[])',  # main.py:16867
    'AsyncFunctionDef.body>If(test=Name,body=[Expr],orelse=[])',  # main.py:50131
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Assign|Expr|Return],orelse=[])',  # main.py:53805
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Assign|If],orelse=[])',  # main.py:16949
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Assign|Return],orelse=[])',  # main.py:16827
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',  # main.py:19967
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Raise],orelse=[])',  # main.py:19924
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',  # main.py:17006
    "AsyncFunctionDef.body>Import(names=['uuid'])",  # main.py:19922
    'AsyncFunctionDef.body>Return(value=Await)',  # main.py:53868
    'AsyncFunctionDef.body>Return(value=BoolOp)',  # main.py:18774
    'AsyncFunctionDef.body>Return(value=Call)',  # main.py:17433
    'AsyncFunctionDef.body>Return(value=Constant)',  # main.py:17011
    'AsyncFunctionDef.body>Return(value=DictComp)',  # tournaments.py:308
    'AsyncFunctionDef.body>Return(value=Name)',  # main.py:16979
    'AsyncFunctionDef.body>Return(value=Subscript)',  # main.py:18680
    'AsyncFunctionDef.body>Return(value=Tuple)',  # main.py:16935
    'AsyncFunctionDef.body>Try(body=[Assign|AsyncWith|For|If],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:18714
    'AsyncFunctionDef.body>Try(body=[Assign|AsyncWith|ImportFrom],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:18673
    'AsyncFunctionDef.body>Try(body=[Assign|Expr|For],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:16838
    'AsyncFunctionDef.body>Try(body=[Assign|If],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:57233
    'AsyncFunctionDef.body>Try(body=[AsyncWith],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:4340
    'AsyncFunctionDef.body>While(test=BoolOp,body=[Assign|AugAssign|Expr|If],orelse=[])',  # main.py:20015
    'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',  # main.py:49898
    'AsyncFunctionDef.decorator_list>Call(func=Attribute,args=[Constant],keywords=[keyword])',  # main.py:19898
    'AsyncFunctionDef.returns>Constant(value=NoneType)',  # main.py:4295
    'AsyncFunctionDef.returns>Constant(value=str)',  # main.py:73487
    'AsyncFunctionDef.returns>Name(id=str,ctx=Load)',  # main.py:56352
    'AsyncFunctionDef.returns>Subscript(value=Name,slice=Tuple,ctx=Load)',  # main.py:16810
    'AsyncWith.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:18676
    'AsyncWith.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:51089
    'AsyncWith.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:51122
    'AsyncWith.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:51096
    'AsyncWith.body>Expr(value=Await)',  # main.py:4342
    'AsyncWith.body>For(target=Name,iter=Call,body=[Assign],orelse=[],type_comment=-)',  # main.py:18722
    'AsyncWith.body>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # main.py:51111
    'AsyncWith.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # main.py:51123
    'AsyncWith.body>If(test=BoolOp,body=[Expr],orelse=[])',  # main.py:51169
    'AsyncWith.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',  # main.py:51101
    'AsyncWith.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:51094
    'AsyncWith.items>withitem(context_expr=Call,optional_vars=-)',  # main.py:4341
    'Attribute.ctx>Load()',  # main.py:4341
    "Attribute.value>Attribute(value=Name,attr='headers',ctx=Load)",  # main.py:19933
    "Attribute.value>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:223
    'Attribute.value>Await(value=Call)',  # main.py:16828
    'Attribute.value>BinOp(left=Call,op=Sub,right=BoolOp)',  # main.py:20449
    'Attribute.value>BinOp(left=Call,op=Sub,right=Name)',  # main.py:53682
    'Attribute.value>BinOp(left=Call,op=Sub,right=Subscript)',  # main.py:53557
    'Attribute.value>BinOp(left=Name,op=Sub,right=BoolOp)',  # main.py:20065
    'Attribute.value>BinOp(left=Name,op=Sub,right=Name)',  # main.py:64819
    'Attribute.value>BinOp(left=Name,op=Sub,right=Subscript)',  # main.py:20162
    'Attribute.value>BoolOp(op=Or,values=[Call|Constant])',  # main.py:49656
    'Attribute.value>BoolOp(op=Or,values=[Constant|Name])',  # main.py:57244
    'Attribute.value>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:49954
    'Attribute.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:6451
    'Attribute.value>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:56300
    'Attribute.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:18679
    'Attribute.value>Call(func=Name,args=[],keywords=[])',  # main.py:51725
    'Attribute.value>Constant(value=str)',  # main.py:18758
    'Attribute.value>Name(id=str,ctx=Load)',  # main.py:4341
    'Attribute.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:53751
    'AugAssign.op>Add()',  # main.py:20016
    'AugAssign.op>BitAnd()',  # region_pick.py:239
    'AugAssign.op>BitOr()',  # main.py:18746
    'AugAssign.op>Sub()',  # main.py:49762
    'AugAssign.target>Name(id=str,ctx=Store)',  # main.py:18746
    'AugAssign.value>BinOp(left=Name,op=Sub,right=Name)',  # match_report_window.py:64
    'AugAssign.value>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick.py:239
    'AugAssign.value>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:18746
    'AugAssign.value>Constant(value=int)',  # main.py:20016
    'Await.value>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:16828
    'Await.value>Call(func=Attribute,args=[Call|Dict],keywords=[])',  # main.py:4342
    'Await.value>Call(func=Attribute,args=[Call|Name],keywords=[])',  # match_hold.py:380
    'Await.value>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # main.py:53849
    'Await.value>Call(func=Attribute,args=[Constant|Name|Subscript],keywords=[])',  # main.py:49515
    'Await.value>Call(func=Attribute,args=[Name|Subscript],keywords=[])',  # main.py:51796
    'Await.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:16863
    'Await.value>Call(func=Name,args=[Attribute|Constant|List|Name],keywords=[keyword])',  # main.py:20311
    'Await.value>Call(func=Name,args=[BinOp|Constant|Name],keywords=[])',  # main.py:50173
    'Await.value>Call(func=Name,args=[BinOp|Constant|Name],keywords=[keyword])',  # main.py:50101
    'Await.value>Call(func=Name,args=[BinOp|Name],keywords=[])',  # main.py:49784
    'Await.value>Call(func=Name,args=[BinOp|Name],keywords=[keyword])',  # main.py:49825
    'Await.value>Call(func=Name,args=[BinOp|Name|Subscript],keywords=[])',  # main.py:50083
    'Await.value>Call(func=Name,args=[Call|Constant|Name],keywords=[])',  # main.py:28366
    'Await.value>Call(func=Name,args=[Call|Constant|Name],keywords=[keyword])',  # main.py:49481
    'Await.value>Call(func=Name,args=[Call|Constant|Name|Subscript],keywords=[])',  # main.py:51923
    'Await.value>Call(func=Name,args=[Call|Name],keywords=[])',  # main.py:17410
    'Await.value>Call(func=Name,args=[Call|Name|Subscript],keywords=[])',  # main.py:51158
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name],keywords=[])',  # main.py:49611
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name],keywords=[keyword])',  # main.py:53836
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name|Subscript],keywords=[])',  # main.py:49573
    'Await.value>Call(func=Name,args=[Constant|List|Name],keywords=[])',  # main.py:19979
    'Await.value>Call(func=Name,args=[Constant|List|Name],keywords=[keyword])',  # main.py:20243
    'Await.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # main.py:49198
    'Await.value>Call(func=Name,args=[Constant|Name],keywords=[keyword])',  # main.py:20472
    'Await.value>Call(func=Name,args=[Constant|Name|Subscript],keywords=[])',  # main.py:49334
    'Await.value>Call(func=Name,args=[Constant|Name|Subscript],keywords=[keyword])',  # main.py:49290
    'Await.value>Call(func=Name,args=[ListComp|Name],keywords=[])',  # main.py:53760
    'Await.value>Call(func=Name,args=[ListComp|Name],keywords=[keyword])',  # main.py:49457
    'Await.value>Call(func=Name,args=[List|Name],keywords=[])',  # main.py:20471
    'Await.value>Call(func=Name,args=[List|Name],keywords=[keyword])',  # main.py:16950
    'Await.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:17477
    'Await.value>Call(func=Name,args=[Name],keywords=[keyword])',  # main.py:17001
    'Await.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:19977
    'Await.value>Call(func=Name,args=[Name|Subscript],keywords=[keyword])',  # main.py:20238
    'Await.value>Call(func=Name,args=[],keywords=[])',  # main.py:16383
    'BinOp.left>BinOp(left=BoolOp,op=Add,right=BoolOp)',  # main.py:51808
    'BinOp.left>BinOp(left=Constant,op=Add,right=Name)',  # main.py:65026
    'BinOp.left>BinOp(left=Name,op=BitAnd,right=Name)',  # region_pick.py:244
    'BinOp.left>BinOp(left=Name,op=FloorDiv,right=Constant)',  # main.py:28364
    'BinOp.left>BinOp(left=Name,op=Sub,right=Name)',  # match_report_window.py:74
    'BinOp.left>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:51808
    'BinOp.left>Call(func=Attribute,args=[Attribute],keywords=[])',  # main.py:20449
    'BinOp.left>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # main.py:18642
    'BinOp.left>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick.py:257
    'BinOp.left>Constant(value=float)',  # main.py:64819
    'BinOp.left>Constant(value=int)',  # main.py:53558
    'BinOp.left>Constant(value=str)',  # main.py:65026
    'BinOp.left>JoinedStr(values=[Constant|FormattedValue])',  # main.py:18761
    'BinOp.left>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:49785
    'BinOp.left>ListComp(elt=Tuple,generators=[comprehension])',  # main.py:49826
    'BinOp.left>Name(id=str,ctx=Load)',  # main.py:16795
    'BinOp.left>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:51126
    'BinOp.op>Add()',  # main.py:18642
    'BinOp.op>BitAnd()',  # region_pick.py:244
    'BinOp.op>BitOr()',  # main.py:16795
    'BinOp.op>FloorDiv()',  # main.py:28364
    'BinOp.op>Mod()',  # main.py:28364
    'BinOp.op>Mult()',  # main.py:20112
    'BinOp.op>Sub()',  # main.py:18671
    'BinOp.right>BinOp(left=Name,op=Mod,right=Constant)',  # main.py:28364
    'BinOp.right>BinOp(left=Name,op=Sub,right=Constant)',  # main.py:73538
    'BinOp.right>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:51808
    'BinOp.right>BoolOp(op=Or,values=[Subscript])',  # main.py:20065
    'BinOp.right>Call(func=Attribute,args=[],keywords=[])',  # main.py:64819
    'BinOp.right>Call(func=Name,args=[Name],keywords=[])',  # main.py:51121
    'BinOp.right>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:51126
    'BinOp.right>Call(func=Name,args=[],keywords=[keyword])',  # main.py:20092
    'BinOp.right>Constant(value=NoneType)',  # main.py:16795
    'BinOp.right>Constant(value=float)',  # main.py:73538
    'BinOp.right>Constant(value=int)',  # main.py:18642
    'BinOp.right>Constant(value=str)',  # main.py:65028
    'BinOp.right>IfExp(test=Compare,body=JoinedStr,orelse=Constant)',  # main.py:18767
    'BinOp.right>List(elts=[Name],ctx=Load)',  # main.py:49363
    'BinOp.right>List(elts=[Tuple],ctx=Load)',  # main.py:49827
    'BinOp.right>Name(id=str,ctx=Load)',  # main.py:28318
    'BinOp.right>Set(elts=[Name])',  # region_pick.py:244
    'BinOp.right>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18671
    'BinOp.right>Tuple(elts=[Attribute|UnaryOp],ctx=Load)',  # region_pick.py:257
    'BoolOp.op>And()',  # main.py:16379
    'BoolOp.op>Or()',  # main.py:17401
    "BoolOp.values>Attribute(value=Name,attr='admitted_by',ctx=Load)",  # region_pick.py:261
    "BoolOp.values>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:83
    'BoolOp.values>BoolOp(op=And,values=[Call|UnaryOp])',  # region_pick.py:232
    'BoolOp.values>BoolOp(op=And,values=[Compare])',  # main.py:51801
    'BoolOp.values>BoolOp(op=And,values=[Name|UnaryOp])',  # main.py:53652
    'BoolOp.values>BoolOp(op=Or,values=[Compare])',  # main.py:64978
    'BoolOp.values>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:18757
    'BoolOp.values>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # main.py:18758
    'BoolOp.values>Call(func=Attribute,args=[],keywords=[])',  # main.py:20579
    'BoolOp.values>Call(func=Name,args=[Constant|GeneratorExp],keywords=[])',  # main.py:53815
    'BoolOp.values>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:56336
    'BoolOp.values>Call(func=Name,args=[Name],keywords=[])',  # main.py:18740
    'BoolOp.values>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:18728
    'BoolOp.values>Call(func=Name,args=[Name|Tuple],keywords=[])',  # region_pick.py:40
    'BoolOp.values>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:64888
    'BoolOp.values>Call(func=Name,args=[],keywords=[])',  # main.py:53692
    'BoolOp.values>Compare(left=Attribute,ops=[Eq],comparators=[Name])',  # main.py:28344
    'BoolOp.values>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # main.py:18738
    'BoolOp.values>Compare(left=Attribute,ops=[NotEq],comparators=[Name])',  # region_pick.py:83
    'BoolOp.values>Compare(left=Await,ops=[Is],comparators=[Constant])',  # main.py:64948
    'BoolOp.values>Compare(left=BinOp,ops=[Gt],comparators=[Constant])',  # main.py:65140
    'BoolOp.values>Compare(left=BinOp,ops=[Gt],comparators=[Name])',  # main.py:73508
    'BoolOp.values>Compare(left=BinOp,ops=[LtE],comparators=[Name])',  # region_pick.py:202
    'BoolOp.values>Compare(left=BinOp,ops=[Lt],comparators=[Name])',  # main.py:18671
    'BoolOp.values>Compare(left=BoolOp,ops=[Gt],comparators=[Constant])',  # main.py:51814
    'BoolOp.values>Compare(left=BoolOp,ops=[LtE],comparators=[Constant])',  # main.py:51721
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Call])',  # main.py:53666
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # main.py:53638
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Name])',  # main.py:16920
    'BoolOp.values>Compare(left=Call,ops=[GtE],comparators=[Call])',  # main.py:65017
    'BoolOp.values>Compare(left=Call,ops=[GtE],comparators=[Constant])',  # main.py:53689
    'BoolOp.values>Compare(left=Call,ops=[GtE],comparators=[Name])',  # main.py:64828
    'BoolOp.values>Compare(left=Call,ops=[Gt],comparators=[Constant])',  # main.py:53665
    'BoolOp.values>Compare(left=Call,ops=[Gt],comparators=[Name])',  # main.py:28319
    'BoolOp.values>Compare(left=Call,ops=[In],comparators=[Name])',  # main.py:62072
    'BoolOp.values>Compare(left=Call,ops=[Lt],comparators=[Call])',  # region_pick.py:261
    'BoolOp.values>Compare(left=Call,ops=[Lt],comparators=[Constant])',  # main.py:50047
    'BoolOp.values>Compare(left=Call,ops=[Lt],comparators=[Name])',  # main.py:65220
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Call])',  # main.py:49955
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Constant])',  # main.py:49859
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Name])',  # main.py:49954
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Call])',  # main.py:51801
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # main.py:50047
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Subscript])',  # main.py:64828
    'BoolOp.values>Compare(left=Name,ops=[GtE],comparators=[Name])',  # main.py:55786
    'BoolOp.values>Compare(left=Name,ops=[Gt],comparators=[BinOp])',  # main.py:20112
    'BoolOp.values>Compare(left=Name,ops=[Gt],comparators=[Constant])',  # main.py:53638
    'BoolOp.values>Compare(left=Name,ops=[Gt],comparators=[Name])',  # main.py:20163
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Attribute])',  # region_pick.py:83
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # main.py:16379
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Constant])',  # main.py:18563
    'BoolOp.values>Compare(left=Name,ops=[LtE],comparators=[Constant])',  # main.py:28319
    'BoolOp.values>Compare(left=Name,ops=[LtE],comparators=[Name])',  # main.py:48824
    'BoolOp.values>Compare(left=Name,ops=[Lt],comparators=[Constant])',  # main.py:20015
    'BoolOp.values>Compare(left=Name,ops=[Lt],comparators=[Name])',  # main.py:18566
    'BoolOp.values>Compare(left=Name,ops=[NotEq],comparators=[Call])',  # main.py:65221
    'BoolOp.values>Compare(left=Name,ops=[NotIn],comparators=[Name])',  # main.py:16379
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # main.py:20112
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # main.py:49603
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Subscript])',  # main.py:51812
    'BoolOp.values>Compare(left=Subscript,ops=[Gt],comparators=[Call])',  # main.py:64947
    'BoolOp.values>Compare(left=Subscript,ops=[Gt],comparators=[Name])',  # main.py:51730
    'BoolOp.values>Compare(left=Subscript,ops=[In],comparators=[Tuple])',  # main.py:16913
    'BoolOp.values>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',  # main.py:49254
    'BoolOp.values>Compare(left=Subscript,ops=[Is],comparators=[Constant])',  # main.py:51099
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',  # main.py:20485
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # main.py:16914
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Subscript])',  # main.py:18563
    'BoolOp.values>Compare(left=Subscript,ops=[NotIn],comparators=[Name])',  # main.py:51101
    'BoolOp.values>Constant(value=NoneType)',  # main.py:57204
    'BoolOp.values>Constant(value=bool)',  # main.py:49400
    'BoolOp.values>Constant(value=float)',  # main.py:49387
    'BoolOp.values>Constant(value=int)',  # main.py:20579
    'BoolOp.values>Constant(value=str)',  # main.py:18760
    'BoolOp.values>List(elts=[],ctx=Load)',  # main.py:18757
    'BoolOp.values>Name(id=str,ctx=Load)',  # main.py:16913
    'BoolOp.values>Subscript(value=BoolOp,slice=Slice,ctx=Load)',  # main.py:57204
    'BoolOp.values>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18671
    'BoolOp.values>Tuple(elts=[],ctx=Load)',  # main.py:17401
    'BoolOp.values>UnaryOp(op=Not,operand=BoolOp)',  # main.py:20163
    'BoolOp.values>UnaryOp(op=Not,operand=Call)',  # main.py:53640
    'BoolOp.values>UnaryOp(op=Not,operand=Name)',  # main.py:49369
    'BoolOp.values>UnaryOp(op=Not,operand=Subscript)',  # main.py:57202
    "Call.args>Attribute(value=Name,attr='id',ctx=Load)",  # main.py:20313
    "Call.args>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:239
    "Call.args>Attribute(value=Name,attr='n',ctx=Load)",  # tournaments.py:308
    "Call.args>Attribute(value=Name,attr='region',ctx=Load)",  # region_pick.py:257
    "Call.args>Attribute(value=Name,attr='rules',ctx=Load)",  # main.py:20241
    "Call.args>Attribute(value=Name,attr='state',ctx=Load)",  # main.py:56309
    "Call.args>Attribute(value=Name,attr='sum',ctx=Load)",  # region_pick.py:257
    "Call.args>Attribute(value=Name,attr='utc',ctx=Load)",  # main.py:20062
    "Call.args>Attribute(value=Name,attr='worst',ctx=Load)",  # region_pick.py:257
    "Call.args>Attribute(value=Subscript,attr='map',ctx=Load)",  # region_pick.py:237
    'Call.args>Await(value=Call)',  # main.py:51796
    'Call.args>BinOp(left=BinOp,op=Add,right=Constant)',  # main.py:65026
    'Call.args>BinOp(left=BinOp,op=Sub,right=Set)',  # region_pick.py:244
    'Call.args>BinOp(left=Constant,op=Sub,right=Call)',  # main.py:64819
    'Call.args>BinOp(left=JoinedStr,op=Add,right=IfExp)',  # main.py:18761
    'Call.args>BinOp(left=ListComp,op=Add,right=List)',  # main.py:49785
    'Call.args>BinOp(left=Name,op=Add,right=Constant)',  # main.py:20429
    'Call.args>BinOp(left=Name,op=Add,right=Name)',  # main.py:50084
    'Call.args>BinOp(left=Name,op=Mult,right=Name)',  # main.py:28321
    'Call.args>BinOp(left=Name,op=Sub,right=Name)',  # main.py:48811
    'Call.args>BinOp(left=Subscript,op=Mult,right=Call)',  # main.py:51126
    'Call.args>BoolOp(op=And,values=[Compare|Name|Subscript])',  # main.py:49602
    'Call.args>BoolOp(op=And,values=[Compare|Subscript])',  # main.py:49604
    'Call.args>BoolOp(op=Or,values=[Call|Constant])',  # main.py:49386
    'Call.args>BoolOp(op=Or,values=[Call|Name])',  # main.py:56384
    'Call.args>BoolOp(op=Or,values=[Constant|Name])',  # main.py:56300
    'Call.args>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:53638
    'Call.args>BoolOp(op=Or,values=[List|Subscript])',  # main.py:64862
    'Call.args>BoolOp(op=Or,values=[Name|Tuple])',  # main.py:17410
    'Call.args>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:18759
    'Call.args>Call(func=Attribute,args=[Name],keywords=[])',  # main.py:28368
    'Call.args>Call(func=Attribute,args=[],keywords=[])',  # main.py:18645
    'Call.args>Call(func=Name,args=[BinOp],keywords=[])',  # main.py:51126
    'Call.args>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:17410
    'Call.args>Call(func=Name,args=[Call],keywords=[])',  # match_hold.py:380
    'Call.args>Call(func=Name,args=[Call|Name],keywords=[])',  # main.py:64823
    'Call.args>Call(func=Name,args=[Constant],keywords=[])',  # main.py:4342
    'Call.args>Call(func=Name,args=[Constant|Name],keywords=[])',  # main.py:62079
    'Call.args>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:51688
    'Call.args>Call(func=Name,args=[JoinedStr],keywords=[])',  # main.py:17407
    'Call.args>Call(func=Name,args=[Name],keywords=[])',  # main.py:20464
    'Call.args>Call(func=Name,args=[Name],keywords=[keyword])',  # main.py:20465
    'Call.args>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:16918
    'Call.args>Call(func=Name,args=[],keywords=[keyword])',  # main.py:28346
    'Call.args>Constant(value=NoneType)',  # main.py:20551
    'Call.args>Constant(value=float)',  # main.py:64819
    'Call.args>Constant(value=int)',  # main.py:18642
    'Call.args>Constant(value=str)',  # main.py:4343
    'Call.args>Dict(keys=[Constant],values=[Attribute|Name|Subscript])',  # main.py:49600
    'Call.args>Dict(keys=[Constant],values=[BinOp|Call|Name])',  # main.py:50160
    'Call.args>Dict(keys=[Constant],values=[BoolOp|Name])',  # main.py:57273
    'Call.args>Dict(keys=[Constant],values=[Call])',  # main.py:51705
    'Call.args>Dict(keys=[Constant],values=[Call|Compare|Name|Subscript])',  # main.py:49508
    'Call.args>Dict(keys=[Constant],values=[Call|IfExp|Name])',  # main.py:18741
    'Call.args>Dict(keys=[Constant],values=[Call|ListComp|Name])',  # region_pick.py:271
    'Call.args>Dict(keys=[Constant],values=[Call|ListComp|Name|Subscript])',  # main.py:65286
    'Call.args>Dict(keys=[Constant],values=[Call|Name])',  # main.py:16933
    'Call.args>Dict(keys=[Constant],values=[Call|Name|Subscript])',  # main.py:50111
    'Call.args>Dict(keys=[Constant],values=[Call|Subscript])',  # main.py:50029
    'Call.args>Dict(keys=[Constant],values=[Constant|IfExp|Name|Subscript])',  # main.py:65049
    'Call.args>Dict(keys=[Constant],values=[Constant|Subscript])',  # main.py:65029
    'Call.args>Dict(keys=[Constant],values=[ListComp])',  # main.py:50144
    'Call.args>Dict(keys=[Constant],values=[Name])',  # main.py:4346
    'Call.args>Dict(keys=[Constant],values=[Name|Subscript])',  # main.py:49281
    'Call.args>Dict(keys=[Constant],values=[Subscript])',  # main.py:20134
    'Call.args>GeneratorExp(elt=BinOp,generators=[comprehension])',  # match_hold.py:352
    'Call.args>GeneratorExp(elt=BoolOp,generators=[comprehension])',  # region_pick.py:83
    'Call.args>GeneratorExp(elt=Call,generators=[comprehension])',  # main.py:6451
    'Call.args>GeneratorExp(elt=Compare,generators=[comprehension])',  # main.py:16893
    'Call.args>GeneratorExp(elt=Constant,generators=[comprehension])',  # region_pick.py:246
    'Call.args>GeneratorExp(elt=JoinedStr,generators=[comprehension])',  # main.py:18758
    'Call.args>GeneratorExp(elt=Name,generators=[comprehension])',  # main.py:18646
    'Call.args>GeneratorExp(elt=Subscript,generators=[comprehension])',  # main.py:48809
    'Call.args>JoinedStr(values=[Constant|FormattedValue])',  # main.py:16376
    'Call.args>List(elts=[Constant],ctx=Load)',  # main.py:28345
    'Call.args>List(elts=[Name],ctx=Load)',  # main.py:16951
    'Call.args>List(elts=[Name|Subscript],ctx=Load)',  # main.py:20244
    'Call.args>List(elts=[Subscript],ctx=Load)',  # main.py:19980
    'Call.args>List(elts=[Tuple],ctx=Load)',  # main.py:20297
    'Call.args>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:49574
    'Call.args>ListComp(elt=Tuple,generators=[comprehension])',  # main.py:49458
    'Call.args>Name(id=str,ctx=Load)',  # main.py:6451
    'Call.args>SetComp(elt=Name,generators=[comprehension])',  # main.py:16826
    'Call.args>SetComp(elt=Tuple,generators=[comprehension])',  # main.py:17401
    'Call.args>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:16892
    'Call.args>Subscript(value=Name,slice=Name,ctx=Load)',  # match_hold.py:353
    'Call.args>Subscript(value=Name,slice=Slice,ctx=Load)',  # main.py:53750
    'Call.args>Tuple(elts=[Constant],ctx=Load)',  # main.py:18732
    'Call.args>Tuple(elts=[Name],ctx=Load)',  # main.py:18733
    "Call.func>Attribute(value=Attribute,attr='get',ctx=Load)",  # main.py:19933
    "Call.func>Attribute(value=Await,attr='all',ctx=Load)",  # main.py:51859
    "Call.func>Attribute(value=Await,attr='first',ctx=Load)",  # main.py:57195
    "Call.func>Attribute(value=Await,attr='mappings',ctx=Load)",  # main.py:16839
    "Call.func>Attribute(value=Await,attr='scalar',ctx=Load)",  # main.py:16851
    "Call.func>Attribute(value=Await,attr='scalar_one',ctx=Load)",  # main.py:16828
    "Call.func>Attribute(value=Await,attr='scalar_one_or_none',ctx=Load)",  # main.py:49327
    "Call.func>Attribute(value=Await,attr='scalars',ctx=Load)",  # main.py:16924
    "Call.func>Attribute(value=BinOp,attr='total_seconds',ctx=Load)",  # main.py:20065
    "Call.func>Attribute(value=BoolOp,attr='lower',ctx=Load)",  # main.py:49656
    "Call.func>Attribute(value=BoolOp,attr='lstrip',ctx=Load)",  # main.py:65270
    "Call.func>Attribute(value=BoolOp,attr='strip',ctx=Load)",  # match_hold.py:376
    "Call.func>Attribute(value=Call,attr='all',ctx=Load)",  # main.py:16886
    "Call.func>Attribute(value=Call,attr='fetchall',ctx=Load)",  # main.py:56363
    "Call.func>Attribute(value=Call,attr='first',ctx=Load)",  # main.py:17433
    "Call.func>Attribute(value=Call,attr='lstrip',ctx=Load)",  # main.py:56300
    "Call.func>Attribute(value=Call,attr='one',ctx=Load)",  # main.py:16839
    "Call.func>Attribute(value=Call,attr='series_fresh',ctx=Load)",  # main.py:51725
    "Call.func>Attribute(value=Call,attr='series_holds',ctx=Load)",  # main.py:51796
    "Call.func>Attribute(value=Call,attr='split',ctx=Load)",  # main.py:6451
    "Call.func>Attribute(value=Constant,attr='join',ctx=Load)",  # main.py:18758
    "Call.func>Attribute(value=Name,attr='UUID',ctx=Load)",  # main.py:56359
    "Call.func>Attribute(value=Name,attr='_asdict',ctx=Load)",  # region_pick.py:274
    "Call.func>Attribute(value=Name,attr='_hold_latch',ctx=Load)",  # main.py:49515
    "Call.func>Attribute(value=Name,attr='add',ctx=Load)",  # main.py:17473
    "Call.func>Attribute(value=Name,attr='append',ctx=Load)",  # main.py:16380
    "Call.func>Attribute(value=Name,attr='begin_nested',ctx=Load)",  # main.py:4341
    "Call.func>Attribute(value=Name,attr='caps_token_sql',ctx=Load)",  # main.py:49597
    "Call.func>Attribute(value=Name,attr='ceil',ctx=Load)",  # main.py:64823
    "Call.func>Attribute(value=Name,attr='choice',ctx=Load)",  # main.py:57236
    "Call.func>Attribute(value=Name,attr='commit',ctx=Load)",  # main.py:19950
    "Call.func>Attribute(value=Name,attr='dumps',ctx=Load)",  # main.py:56251
    "Call.func>Attribute(value=Name,attr='execute',ctx=Load)",  # main.py:4342
    "Call.func>Attribute(value=Name,attr='expire',ctx=Load)",  # main.py:28345
    "Call.func>Attribute(value=Name,attr='extend',ctx=Load)",  # main.py:50130
    "Call.func>Attribute(value=Name,attr='flush',ctx=Load)",  # main.py:20284
    "Call.func>Attribute(value=Name,attr='format',ctx=Load)",  # main.py:49695
    "Call.func>Attribute(value=Name,attr='get',ctx=Load)",  # main.py:16918
    "Call.func>Attribute(value=Name,attr='intersection',ctx=Load)",  # main.py:73452
    "Call.func>Attribute(value=Name,attr='items',ctx=Load)",  # main.py:18646
    "Call.func>Attribute(value=Name,attr='loads',ctx=Load)",  # main.py:18735
    "Call.func>Attribute(value=Name,attr='lower',ctx=Load)",  # main.py:57238
    "Call.func>Attribute(value=Name,attr='mappings',ctx=Load)",  # main.py:18722
    "Call.func>Attribute(value=Name,attr='monotonic',ctx=Load)",  # main.py:18670
    "Call.func>Attribute(value=Name,attr='now',ctx=Load)",  # main.py:20062
    "Call.func>Attribute(value=Name,attr='pop',ctx=Load)",  # main.py:62071
    "Call.func>Attribute(value=Name,attr='replace',ctx=Load)",  # main.py:18739
    "Call.func>Attribute(value=Name,attr='rollback',ctx=Load)",  # main.py:16863
    "Call.func>Attribute(value=Name,attr='scalar',ctx=Load)",  # main.py:20579
    "Call.func>Attribute(value=Name,attr='sort',ctx=Load)",  # main.py:51807
    "Call.func>Attribute(value=Name,attr='strip',ctx=Load)",  # main.py:6451
    "Call.func>Attribute(value=Name,attr='time',ctx=Load)",  # main.py:18751
    "Call.func>Attribute(value=Name,attr='timestamp',ctx=Load)",  # main.py:18742
    "Call.func>Attribute(value=Name,attr='update',ctx=Load)",  # main.py:16876
    "Call.func>Attribute(value=Name,attr='uuid4',ctx=Load)",  # main.py:16957
    "Call.func>Attribute(value=Name,attr='values',ctx=Load)",  # main.py:18645
    "Call.func>Attribute(value=Subscript,attr='isdigit',ctx=Load)",  # main.py:53751
    'Call.func>Name(id=str,ctx=Load)',  # main.py:4342
    "Call.keywords>keyword(arg='_gate_held',value=Constant)",  # main.py:17010
    "Call.keywords>keyword(arg='affected_player_ids',value=BinOp)",  # main.py:50096
    "Call.keywords>keyword(arg='affected_player_ids',value=Call)",  # main.py:51847
    "Call.keywords>keyword(arg='affected_player_ids',value=List)",  # main.py:20006
    "Call.keywords>keyword(arg='affected_player_ids',value=ListComp)",  # main.py:53831
    "Call.keywords>keyword(arg='affected_steam_ids',value=List)",  # main.py:20006
    "Call.keywords>keyword(arg='allow',value=Tuple)",  # main.py:49459
    "Call.keywords>keyword(arg='allow_any',value=ListComp)",  # main.py:49828
    "Call.keywords>keyword(arg='allow_any',value=Tuple)",  # main.py:20298
    "Call.keywords>keyword(arg='allowed_group_ids',value=Name)",  # main.py:16952
    "Call.keywords>keyword(arg='allowed_hold_ids',value=Name)",  # main.py:16953
    "Call.keywords>keyword(arg='allowed_keys',value=Name)",  # main.py:17005
    "Call.keywords>keyword(arg='allowed_keys',value=Tuple)",  # main.py:20314
    "Call.keywords>keyword(arg='amount',value=Call)",  # main.py:37861
    "Call.keywords>keyword(arg='amount',value=Name)",  # main.py:28347
    "Call.keywords>keyword(arg='balance_rating',value=Name)",  # main.py:49398
    "Call.keywords>keyword(arg='bilateral',value=IfExp)",  # main.py:49696
    "Call.keywords>keyword(arg='completed_series',value=Name)",  # main.py:49399
    "Call.keywords>keyword(arg='content',value=Name)",  # main.py:49195
    "Call.keywords>keyword(arg='current',value=Call)",  # main.py:49483
    "Call.keywords>keyword(arg='default',value=Constant)",  # main.py:64816
    "Call.keywords>keyword(arg='detail',value=Constant)",  # main.py:16865
    "Call.keywords>keyword(arg='display_name',value=Subscript)",  # main.py:49393
    "Call.keywords>keyword(arg='elo_range',value=IfExp)",  # main.py:20590
    "Call.keywords>keyword(arg='elo_range',value=Name)",  # main.py:49683
    "Call.keywords>keyword(arg='elo_unbounded',value=Compare)",  # main.py:20591
    "Call.keywords>keyword(arg='ge',value=Constant)",  # main.py:49169
    "Call.keywords>keyword(arg='hold',value=IfExp)",  # main.py:49631
    "Call.keywords>keyword(arg='key',value=Lambda)",  # main.py:17402
    "Call.keywords>keyword(arg='key',value=Name)",  # main.py:16381
    "Call.keywords>keyword(arg='le',value=Constant)",  # main.py:49169
    "Call.keywords>keyword(arg='live_p1_points',value=Constant)",  # main.py:20279
    "Call.keywords>keyword(arg='live_p2_points',value=Constant)",  # main.py:20279
    "Call.keywords>keyword(arg='margin_ms',value=Name)",  # main.py:18750
    "Call.keywords>keyword(arg='match_age_seconds',value=Constant)",  # main.py:50212
    "Call.keywords>keyword(arg='match_age_seconds',value=IfExp)",  # main.py:49624
    "Call.keywords>keyword(arg='max_age_s',value=Name)",  # main.py:18751
    "Call.keywords>keyword(arg='max_total_seconds',value=Name)",  # main.py:49292
    "Call.keywords>keyword(arg='minutes',value=Name)",  # main.py:51724
    "Call.keywords>keyword(arg='my_pid',value=Name)",  # main.py:20245
    "Call.keywords>keyword(arg='my_pid',value=Subscript)",  # main.py:53838
    "Call.keywords>keyword(arg='my_ready',value=Call)",  # main.py:49625
    "Call.keywords>keyword(arg='now',value=Call)",  # main.py:18751
    "Call.keywords>keyword(arg='now',value=Name)",  # main.py:51725
    "Call.keywords>keyword(arg='only',value=Constant)",  # main.py:20465
    "Call.keywords>keyword(arg='only',value=ListComp)",  # main.py:49794
    "Call.keywords>keyword(arg='only',value=Name)",  # main.py:49952
    "Call.keywords>keyword(arg='only',value=Subscript)",  # main.py:20484
    "Call.keywords>keyword(arg='opponent_name',value=Subscript)",  # main.py:20348
    "Call.keywords>keyword(arg='opponent_rating',value=Subscript)",  # main.py:20349
    "Call.keywords>keyword(arg='opponent_ready',value=Constant)",  # main.py:20350
    "Call.keywords>keyword(arg='opponent_ready',value=Name)",  # main.py:20383
    "Call.keywords>keyword(arg='opponent_steam_id',value=Subscript)",  # main.py:20347
    "Call.keywords>keyword(arg='opponents',value=List)",  # main.py:51981
    "Call.keywords>keyword(arg='opponents',value=Name)",  # main.py:49621
    "Call.keywords>keyword(arg='p1_pings',value=Subscript)",  # main.py:20223
    "Call.keywords>keyword(arg='p1_pings_at',value=Subscript)",  # main.py:20224
    "Call.keywords>keyword(arg='p1_series_wins',value=Constant)",  # main.py:20278
    "Call.keywords>keyword(arg='p1_steam_id',value=IfExp)",  # main.py:20354
    "Call.keywords>keyword(arg='p1_wins',value=Attribute)",  # main.py:20356
    "Call.keywords>keyword(arg='p1_wins',value=IfExp)",  # main.py:20391
    "Call.keywords>keyword(arg='p2_pings',value=Subscript)",  # main.py:20223
    "Call.keywords>keyword(arg='p2_pings_at',value=Subscript)",  # main.py:20224
    "Call.keywords>keyword(arg='p2_series_wins',value=Constant)",  # main.py:20278
    "Call.keywords>keyword(arg='p2_steam_id',value=IfExp)",  # main.py:20355
    "Call.keywords>keyword(arg='p2_wins',value=Attribute)",  # main.py:20357
    "Call.keywords>keyword(arg='p2_wins',value=IfExp)",  # main.py:20392
    "Call.keywords>keyword(arg='parents',value=List)",  # main.py:49787
    "Call.keywords>keyword(arg='photon_region',value=BoolOp)",  # main.py:20385
    "Call.keywords>keyword(arg='photon_region',value=Name)",  # main.py:20352
    "Call.keywords>keyword(arg='player1_id',value=Name)",  # main.py:20277
    "Call.keywords>keyword(arg='player2_id',value=Subscript)",  # main.py:20277
    "Call.keywords>keyword(arg='player_id',value=Name)",  # main.py:28347
    "Call.keywords>keyword(arg='player_id',value=Subscript)",  # main.py:51156
    "Call.keywords>keyword(arg='player_ids',value=BinOp)",  # main.py:49915
    "Call.keywords>keyword(arg='player_ids',value=List)",  # main.py:20473
    "Call.keywords>keyword(arg='player_ids',value=ListComp)",  # main.py:49467
    "Call.keywords>keyword(arg='player_ids',value=Name)",  # main.py:49374
    "Call.keywords>keyword(arg='queue_count',value=Call)",  # main.py:49317
    "Call.keywords>keyword(arg='queue_count',value=Constant)",  # main.py:49683
    "Call.keywords>keyword(arg='queue_count',value=Name)",  # main.py:50013
    "Call.keywords>keyword(arg='queue_size',value=Name)",  # main.py:20585
    "Call.keywords>keyword(arg='rating',value=Call)",  # main.py:49394
    "Call.keywords>keyword(arg='ready',value=Call)",  # main.py:49400
    "Call.keywords>keyword(arg='reason',value=Constant)",  # main.py:51157
    "Call.keywords>keyword(arg='reason',value=Name)",  # main.py:28348
    "Call.keywords>keyword(arg='reference_id',value=Call)",  # main.py:28348
    "Call.keywords>keyword(arg='region',value=Subscript)",  # main.py:49395
    "Call.keywords>keyword(arg='regret_ms',value=Name)",  # main.py:18750
    "Call.keywords>keyword(arg='request',value=Name)",  # main.py:20245
    "Call.keywords>keyword(arg='require',value=Constant)",  # main.py:49459
    "Call.keywords>keyword(arg='response_model',value=Name)",  # main.py:19898
    "Call.keywords>keyword(arg='reverse',value=Constant)",  # main.py:51809
    "Call.keywords>keyword(arg='room',value=Name)",  # main.py:49483
    "Call.keywords>keyword(arg='room_id',value=Name)",  # main.py:20238
    "Call.keywords>keyword(arg='room_name',value=Name)",  # main.py:20351
    "Call.keywords>keyword(arg='room_region',value=Name)",  # main.py:49623
    "Call.keywords>keyword(arg='rules',value=Call)",  # main.py:20358
    "Call.keywords>keyword(arg='rules',value=Name)",  # main.py:20251
    "Call.keywords>keyword(arg='rules_prop',value=Call)",  # main.py:20359
    "Call.keywords>keyword(arg='seconds',value=Name)",  # main.py:20092
    "Call.keywords>keyword(arg='separators',value=Tuple)",  # main.py:56251
    "Call.keywords>keyword(arg='series_id',value=Call)",  # main.py:20353
    "Call.keywords>keyword(arg='series_id',value=Name)",  # main.py:20386
    "Call.keywords>keyword(arg='sort_keys',value=Constant)",  # main.py:56251
    "Call.keywords>keyword(arg='status',value=Constant)",  # main.py:19969
    "Call.keywords>keyword(arg='status',value=IfExp)",  # main.py:20215
    "Call.keywords>keyword(arg='status_code',value=Constant)",  # main.py:16865
    "Call.keywords>keyword(arg='steam_id',value=Subscript)",  # main.py:49392
    "Call.keywords>keyword(arg='strict_team_ovt_queue',value=Name)",  # main.py:16954
    "Call.keywords>keyword(arg='tags',value=List)",  # main.py:19898
    "Call.keywords>keyword(arg='team_assigned',value=Name)",  # main.py:49619
    "Call.keywords>keyword(arg='team_assigned',value=Subscript)",  # main.py:49396
    "Call.keywords>keyword(arg='teammates',value=List)",  # main.py:51980
    "Call.keywords>keyword(arg='teammates',value=Name)",  # main.py:49620
    "Call.keywords>keyword(arg='tzinfo',value=Attribute)",  # main.py:18739
    "Call.keywords>keyword(arg='using_fallback_rating',value=Name)",  # main.py:49397
    "Call.keywords>keyword(arg='wait_time',value=Constant)",  # main.py:20418
    "Call.keywords>keyword(arg='wait_time',value=Name)",  # main.py:20118
    "Call.keywords>keyword(arg='window',value=Name)",  # main.py:51725
    "Compare.comparators>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:83
    'Compare.comparators>BinOp(left=Constant,op=Mult,right=Constant)',  # main.py:53558
    'Compare.comparators>BinOp(left=Name,op=Mult,right=Constant)',  # main.py:20112
    'Compare.comparators>Call(func=Attribute,args=[Attribute],keywords=[])',  # main.py:64947
    'Compare.comparators>Call(func=Attribute,args=[],keywords=[])',  # main.py:57238
    'Compare.comparators>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:65017
    'Compare.comparators>Call(func=Name,args=[GeneratorExp],keywords=[keyword])',  # main.py:65221
    'Compare.comparators>Call(func=Name,args=[Name],keywords=[])',  # main.py:49795
    'Compare.comparators>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:49955
    'Compare.comparators>Constant(value=NoneType)',  # main.py:16379
    'Compare.comparators>Constant(value=bool)',  # main.py:20314
    'Compare.comparators>Constant(value=float)',  # main.py:65140
    'Compare.comparators>Constant(value=int)',  # main.py:20015
    'Compare.comparators>Constant(value=str)',  # main.py:16389
    'Compare.comparators>Name(id=str,ctx=Load)',  # main.py:16375
    'Compare.comparators>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18563
    'Compare.comparators>Tuple(elts=[Constant],ctx=Load)',  # main.py:16864
    'Compare.comparators>Tuple(elts=[Name],ctx=Load)',  # main.py:51910
    "Compare.left>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick.py:83
    "Compare.left>Attribute(value=Name,attr='id',ctx=Load)",  # main.py:28344
    "Compare.left>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:211
    "Compare.left>Attribute(value=Name,attr='player1_id',ctx=Load)",  # main.py:20354
    "Compare.left>Attribute(value=Name,attr='tzinfo',ctx=Load)",  # main.py:18738
    'Compare.left>Await(value=Call)',  # main.py:20199
    'Compare.left>BinOp(left=BinOp,op=Sub,right=Call)',  # match_report_window.py:74
    'Compare.left>BinOp(left=Constant,op=Mult,right=Name)',  # region_pick.py:248
    'Compare.left>BinOp(left=Name,op=Sub,right=Name)',  # main.py:65140
    'Compare.left>BinOp(left=Name,op=Sub,right=Subscript)',  # main.py:18671
    'Compare.left>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:51721
    'Compare.left>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:56239
    'Compare.left>Call(func=Attribute,args=[],keywords=[])',  # main.py:49656
    'Compare.left>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick.py:261
    'Compare.left>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:53638
    'Compare.left>Call(func=Name,args=[Call],keywords=[])',  # main.py:56284
    'Compare.left>Call(func=Name,args=[Name],keywords=[])',  # main.py:16864
    'Compare.left>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:16893
    'Compare.left>Constant(value=str)',  # main.py:18640
    'Compare.left>Name(id=str,ctx=Load)',  # main.py:16375
    'Compare.left>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:16913
    'Compare.ops>Eq()',  # main.py:16389
    'Compare.ops>Gt()',  # main.py:20112
    'Compare.ops>GtE()',  # main.py:48822
    'Compare.ops>In()',  # main.py:16864
    'Compare.ops>Is()',  # main.py:16796
    'Compare.ops>IsNot()',  # main.py:16379
    'Compare.ops>Lt()',  # main.py:18565
    'Compare.ops>LtE()',  # main.py:28319
    'Compare.ops>NotEq()',  # main.py:16914
    'Compare.ops>NotIn()',  # main.py:16375
    'Dict.keys>Constant(value=str)',  # main.py:4346
    'Dict.keys>Name(id=str,ctx=Load)',  # main.py:49853
    "Dict.values>Attribute(value=Name,attr='HOLD_CAPS_TOKEN',ctx=Load)",  # main.py:49601
    "Dict.values>Attribute(value=Name,attr='id',ctx=Load)",  # region_pick.py:222
    'Dict.values>BinOp(left=Name,op=Add,right=Name)',  # main.py:50164
    'Dict.values>BoolOp(op=And,values=[Compare])',  # main.py:64828
    'Dict.values>BoolOp(op=Or,values=[Constant|Name])',  # main.py:57273
    'Dict.values>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:49853
    'Dict.values>Call(func=Name,args=[Call],keywords=[])',  # main.py:50025
    'Dict.values>Call(func=Name,args=[Name],keywords=[])',  # main.py:16934
    'Dict.values>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:18741
    'Dict.values>Compare(left=Name,ops=[Eq],comparators=[Subscript])',  # main.py:64827
    'Dict.values>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # main.py:64847
    'Dict.values>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',  # main.py:49509
    'Dict.values>Constant(value=NoneType)',  # region_pick.py:227
    'Dict.values>Constant(value=bool)',  # main.py:56339
    'Dict.values>Constant(value=int)',  # main.py:53511
    'Dict.values>Constant(value=str)',  # main.py:53511
    'Dict.values>IfExp(test=Attribute,body=Call,orelse=Constant)',  # region_pick.py:223
    'Dict.values>IfExp(test=Compare,body=Call,orelse=Constant)',  # main.py:18742
    'Dict.values>IfExp(test=Name,body=Constant,orelse=Constant)',  # main.py:65050
    'Dict.values>IfExp(test=Subscript,body=Call,orelse=Constant)',  # main.py:64848
    'Dict.values>JoinedStr(values=[Constant|FormattedValue])',  # main.py:18753
    'Dict.values>List(elts=[],ctx=Load)',  # region_pick.py:229
    'Dict.values>ListComp(elt=Call,generators=[comprehension])',  # main.py:51861
    'Dict.values>ListComp(elt=Dict,generators=[comprehension])',  # main.py:64843
    'Dict.values>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:50144
    'Dict.values>Name(id=str,ctx=Load)',  # main.py:4346
    'Dict.values>Subscript(value=BoolOp,slice=Slice,ctx=Load)',  # main.py:53845
    'Dict.values>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20134
    'Dict.values>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # main.py:53844
    'Dict.values>UnaryOp(op=USub,operand=Constant)',  # main.py:65123
    'DictComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # main.py:16892
    'DictComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # main.py:51859
    "DictComp.key>Attribute(value=Name,attr='id',ctx=Load)",  # main.py:28363
    "DictComp.key>Attribute(value=Name,attr='region',ctx=Load)",  # tournaments.py:308
    'DictComp.key>Call(func=Name,args=[Name],keywords=[])',  # main.py:51859
    'DictComp.key>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:16892
    'DictComp.key>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:50068
    'DictComp.value>Call(func=Name,args=[Attribute],keywords=[])',  # tournaments.py:308
    'DictComp.value>Name(id=str,ctx=Load)',  # main.py:16892
    'DictComp.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:50068
    'DictComp.value>Tuple(elts=[Constant],ctx=Load)',  # main.py:56360
    'ExceptHandler.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:18737
    'ExceptHandler.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:73579
    'ExceptHandler.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # main.py:18753
    'ExceptHandler.body>Expr(value=Await)',  # main.py:16863
    'ExceptHandler.body>Expr(value=Call)',  # main.py:18679
    'ExceptHandler.body>If(test=BoolOp,body=[Expr|Raise],orelse=[])',  # main.py:73580
    'ExceptHandler.body>If(test=Compare,body=[Raise],orelse=[])',  # main.py:16864
    'ExceptHandler.body>If(test=UnaryOp,body=[Expr|Raise],orelse=[])',  # main.py:73565
    'ExceptHandler.body>Pass()',  # main.py:4348
    'ExceptHandler.body>Raise(exc=-,cause=-)',  # main.py:16866
    'ExceptHandler.body>Return(value=Constant)',  # main.py:56286
    'ExceptHandler.body>Return(value=Tuple)',  # main.py:6453
    'ExceptHandler.type>Name(id=str,ctx=Load)',  # main.py:4347
    'Expr.value>Await(value=Call)',  # main.py:4342
    'Expr.value>Call(func=Attribute,args=[BoolOp],keywords=[])',  # main.py:56384
    'Expr.value>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:28346
    'Expr.value>Call(func=Attribute,args=[Dict],keywords=[])',  # main.py:18741
    'Expr.value>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # main.py:16876
    'Expr.value>Call(func=Attribute,args=[List],keywords=[])',  # main.py:50130
    'Expr.value>Call(func=Attribute,args=[List|Name],keywords=[])',  # main.py:28345
    'Expr.value>Call(func=Attribute,args=[Name],keywords=[])',  # main.py:16380
    'Expr.value>Call(func=Attribute,args=[Subscript],keywords=[])',  # main.py:49417
    'Expr.value>Call(func=Attribute,args=[Tuple],keywords=[])',  # main.py:57214
    'Expr.value>Call(func=Attribute,args=[],keywords=[keyword])',  # main.py:51807
    'Expr.value>Call(func=Name,args=[BinOp],keywords=[])',  # main.py:18761
    'Expr.value>Call(func=Name,args=[JoinedStr],keywords=[])',  # main.py:18679
    'Expr.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:19926
    'Expr.value>Constant(value=str)',  # main.py:4296
    'For.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:17477
    'For.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # main.py:18740
    'For.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:16851
    'For.body>Assign(targets=[Name],value=Compare,type_comment=-)',  # region_pick.py:249
    'For.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:53794
    'For.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # main.py:20456
    'For.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:18640
    'For.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # main.py:53751
    'For.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:20452
    'For.body>Assign(targets=[Name],value=Tuple,type_comment=-)',  # main.py:17482
    'For.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # region_pick.py:58
    'For.body>Assign(targets=[Subscript],value=Subscript,type_comment=-)',  # main.py:49855
    'For.body>Assign(targets=[Subscript],value=Tuple,type_comment=-)',  # main.py:18724
    'For.body>Assign(targets=[Tuple],value=Await,type_comment=-)',  # main.py:57212
    'For.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # main.py:18732
    'For.body>AugAssign(target=Name,op=BitAnd,value=Call)',  # region_pick.py:239
    'For.body>Break()',  # main.py:53795
    'For.body>Expr(value=Await)',  # main.py:17009
    'For.body>Expr(value=Call)',  # main.py:18741
    'For.body>For(target=Tuple,iter=List,body=[Expr],orelse=[],type_comment=-)',  # main.py:20524
    'For.body>If(test=BoolOp,body=[Assign],orelse=[])',  # main.py:18738
    'For.body>If(test=BoolOp,body=[Assign|Continue|Expr],orelse=[])',  # main.py:20485
    'For.body>If(test=BoolOp,body=[Assign|Continue|Expr|If],orelse=[])',  # main.py:65191
    'For.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # main.py:51798
    'For.body>If(test=BoolOp,body=[Continue],orelse=[])',  # main.py:51812
    'For.body>If(test=BoolOp,body=[Expr],orelse=[Expr])',  # main.py:56383
    'For.body>If(test=BoolOp,body=[Expr],orelse=[If])',  # main.py:50047
    'For.body>If(test=BoolOp,body=[Expr],orelse=[])',  # main.py:16379
    'For.body>If(test=BoolOp,body=[Return],orelse=[])',  # main.py:16913
    'For.body>If(test=Call,body=[Assign],orelse=[])',  # main.py:56235
    'For.body>If(test=Call,body=[AugAssign],orelse=[])',  # main.py:18745
    'For.body>If(test=Call,body=[Try],orelse=[])',  # main.py:18733
    'For.body>If(test=Compare,body=[Assign],orelse=[Assign])',  # main.py:51124
    'For.body>If(test=Compare,body=[Assign],orelse=[])',  # main.py:65188
    'For.body>If(test=Compare,body=[Assign|Break],orelse=[])',  # main.py:16854
    'For.body>If(test=Compare,body=[Assign|Continue|Expr],orelse=[])',  # main.py:53771
    'For.body>If(test=Compare,body=[Assign|Continue|Expr|If],orelse=[])',  # main.py:20506
    'For.body>If(test=Compare,body=[AugAssign],orelse=[])',  # match_report_window.py:63
    'For.body>If(test=Compare,body=[AugAssign|If],orelse=[AugAssign|Expr])',  # main.py:51150
    'For.body>If(test=Compare,body=[Break],orelse=[])',  # main.py:20466
    'For.body>If(test=Compare,body=[Continue],orelse=[])',  # main.py:16916
    'For.body>If(test=Compare,body=[Continue|If],orelse=[])',  # main.py:17478
    'For.body>If(test=Compare,body=[Expr],orelse=[If])',  # main.py:16389
    'For.body>If(test=Compare,body=[Expr],orelse=[])',  # main.py:16382
    'For.body>If(test=Compare,body=[Expr|Raise],orelse=[])',  # main.py:20440
    'For.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # main.py:20437
    'For.body>If(test=Compare,body=[Raise],orelse=[])',  # main.py:17404
    'For.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:51784
    'For.body>If(test=Name,body=[Assign],orelse=[])',  # main.py:18641
    'For.body>If(test=Name,body=[Expr],orelse=[])',  # main.py:57213
    'For.body>If(test=UnaryOp,body=[Assign],orelse=[])',  # region_pick.py:198
    'For.body>If(test=UnaryOp,body=[Continue],orelse=[])',  # main.py:51795
    'For.body>Return(value=Call)',  # main.py:20556
    'For.body>Return(value=Tuple)',  # main.py:17485
    'For.iter>BoolOp(op=Or,values=[Name|Tuple])',  # region_pick.py:197
    'For.iter>Call(func=Attribute,args=[],keywords=[])',  # main.py:18722
    'For.iter>Call(func=Name,args=[BinOp],keywords=[])',  # region_pick.py:244
    'For.iter>Call(func=Name,args=[BinOp|Constant],keywords=[])',  # main.py:20429
    'For.iter>Call(func=Name,args=[Name],keywords=[])',  # main.py:65289
    'For.iter>Call(func=Name,args=[Name],keywords=[keyword])',  # main.py:16381
    'For.iter>Call(func=Name,args=[SetComp],keywords=[keyword])',  # main.py:17400
    'For.iter>List(elts=[Tuple],ctx=Load)',  # main.py:20524
    'For.iter>Name(id=str,ctx=Load)',  # main.py:16378
    'For.iter>Subscript(value=Name,slice=Slice,ctx=Load)',  # region_pick.py:238
    'For.iter>Tuple(elts=[Constant],ctx=Load)',  # main.py:56233
    'For.iter>Tuple(elts=[Name],ctx=Load)',  # main.py:50129
    'For.orelse>Expr(value=Await)',  # main.py:20570
    'For.orelse>Expr(value=Call)',  # main.py:20571
    'For.orelse>Raise(exc=Call,cause=-)',  # main.py:20573
    'For.target>Name(id=str,ctx=Store)',  # main.py:16378
    'For.target>Tuple(elts=[Name],ctx=Store)',  # main.py:17400
    'For.target>Tuple(elts=[Name|Tuple],ctx=Store)',  # main.py:56381
    'FormattedValue.format_spec>JoinedStr(values=[Constant])',  # main.py:50011
    "FormattedValue.value>Attribute(value=Call,attr='__name__',ctx=Load)",  # main.py:18679
    'FormattedValue.value>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:18759
    'FormattedValue.value>Call(func=Name,args=[Call],keywords=[])',  # main.py:18759
    'FormattedValue.value>Call(func=Name,args=[Constant],keywords=[])',  # match_hold.py:359
    'FormattedValue.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:37858
    'FormattedValue.value>IfExp(test=Name,body=Constant,orelse=Constant)',  # main.py:49337
    'FormattedValue.value>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:50016
    'FormattedValue.value>Name(id=str,ctx=Load)',  # main.py:16376
    'FormattedValue.value>Subscript(value=Attribute,slice=Slice,ctx=Load)',  # main.py:20217
    'FormattedValue.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20148
    'FormattedValue.value>Subscript(value=Name,slice=Name,ctx=Load)',  # match_hold.py:355
    'FunctionDef.args>arguments(posonlyargs=[],args=[],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # main.py:54211
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant])',  # main.py:18630
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # main.py:6449
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant],kwarg=-,defaults=[])',  # region_pick.py:101
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[NoneType],kwarg=-,defaults=[])',  # match_report_window.py:68
    'FunctionDef.body>Assert(test=Compare,msg=-)',  # main.py:28323
    'FunctionDef.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # main.py:28318
    'FunctionDef.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # main.py:49388
    'FunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:18645
    'FunctionDef.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # main.py:18638
    'FunctionDef.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:49390
    'FunctionDef.body>Assign(targets=[Name],value=List,type_comment=-)',  # main.py:48803
    'FunctionDef.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # region_pick.py:74
    'FunctionDef.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:48802
    'FunctionDef.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # region_pick.py:189
    'FunctionDef.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:51726
    'FunctionDef.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # region_pick.py:208
    'FunctionDef.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # region_pick.py:241
    'FunctionDef.body>Expr(value=Call)',  # region_pick.py:259
    'FunctionDef.body>Expr(value=Constant)',  # main.py:18553
    'FunctionDef.body>For(target=Name,iter=BoolOp,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # region_pick.py:197
    'FunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr],orelse=[],type_comment=-)',  # region_pick.py:244
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:18639
    'FunctionDef.body>For(target=Name,iter=Subscript,body=[AugAssign],orelse=[],type_comment=-)',  # region_pick.py:238
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|If],orelse=[],type_comment=-)',  # region_pick.py:51
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:48808
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick.py:210
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick.py:221
    'FunctionDef.body>If(test=BoolOp,body=[Return],orelse=[])',  # main.py:28319
    'FunctionDef.body>If(test=Call,body=[Assign],orelse=[])',  # main.py:56249
    'FunctionDef.body>If(test=Call,body=[For|If],orelse=[])',  # main.py:56232
    'FunctionDef.body>If(test=Call,body=[Try],orelse=[])',  # main.py:56227
    'FunctionDef.body>If(test=Compare,body=[Assign],orelse=[])',  # region_pick.py:187
    'FunctionDef.body>If(test=Compare,body=[If|Return],orelse=[])',  # main.py:18562
    'FunctionDef.body>If(test=Compare,body=[Raise],orelse=[])',  # match_hold.py:236
    'FunctionDef.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:48822
    'FunctionDef.body>If(test=Name,body=[Assign],orelse=[Assign])',  # region_pick.py:263
    'FunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',  # main.py:18643
    "FunctionDef.body>Import(names=['match_report_window'])",  # main.py:54213
    'FunctionDef.body>Return(value=BinOp)',  # region_pick.py:257
    'FunctionDef.body>Return(value=BoolOp)',  # main.py:18566
    'FunctionDef.body>Return(value=Call)',  # main.py:18646
    'FunctionDef.body>Return(value=Compare)',  # match_report_window.py:74
    'FunctionDef.body>Return(value=Constant)',  # main.py:51733
    'FunctionDef.body>Return(value=Dict)',  # main.py:56339
    'FunctionDef.body>Return(value=IfExp)',  # main.py:18756
    'FunctionDef.body>Return(value=JoinedStr)',  # match_hold.py:220
    'FunctionDef.body>Return(value=ListComp)',  # region_pick.py:222
    'FunctionDef.body>Return(value=Name)',  # main.py:48826
    'FunctionDef.body>Return(value=Tuple)',  # main.py:16796
    'FunctionDef.body>Try(body=[Return],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:6450
    'FunctionDef.body>While(test=Name,body=[Assign|Expr|For|If],orelse=[])',  # main.py:62070
    'FunctionDef.returns>Name(id=str,ctx=Load)',  # main.py:48816
    'FunctionDef.returns>Subscript(value=Name,slice=Tuple,ctx=Load)',  # main.py:6449
    'GeneratorExp.elt>BinOp(left=Constant,op=Add,right=Name)',  # match_hold.py:352
    'GeneratorExp.elt>BinOp(left=Name,op=Sub,right=Name)',  # region_pick.py:247
    'GeneratorExp.elt>BoolOp(op=And,values=[Attribute|Compare])',  # region_pick.py:83
    'GeneratorExp.elt>Call(func=Name,args=[Call|Name],keywords=[keyword])',  # match_report_window.py:81
    'GeneratorExp.elt>Call(func=Name,args=[Name],keywords=[])',  # main.py:6451
    'GeneratorExp.elt>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:53820
    'GeneratorExp.elt>Compare(left=Call,ops=[GtE],comparators=[Name])',  # main.py:56300
    'GeneratorExp.elt>Compare(left=Call,ops=[In],comparators=[Name])',  # main.py:16935
    'GeneratorExp.elt>Compare(left=Call,ops=[NotIn],comparators=[Name])',  # main.py:16893
    'GeneratorExp.elt>Compare(left=Name,ops=[In],comparators=[Tuple])',  # main.py:49856
    'GeneratorExp.elt>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # region_pick.py:232
    'GeneratorExp.elt>Constant(value=int)',  # region_pick.py:246
    'GeneratorExp.elt>JoinedStr(values=[Constant|FormattedValue])',  # main.py:18759
    'GeneratorExp.elt>Name(id=str,ctx=Load)',  # main.py:18646
    'GeneratorExp.elt>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:48809
    'GeneratorExp.generators>comprehension(target=Name,iter=Call,ifs=[],is_async=0)',  # main.py:6451
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # main.py:16876
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[Subscript],is_async=0)',  # main.py:64816
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # main.py:16893
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # main.py:18646
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # region_pick.py:247
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Name,ifs=[],is_async=0)',  # main.py:16883
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Subscript,ifs=[],is_async=0)',  # match_hold.py:352
    'If.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:20127
    'If.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # main.py:20092
    'If.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # main.py:20188
    'If.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:16828
    'If.body>Assign(targets=[Name],value=Compare,type_comment=-)',  # main.py:51125
    'If.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:16855
    'If.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # main.py:49760
    'If.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:20365
    'If.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',  # main.py:20217
    'If.body>Assign(targets=[Name],value=List,type_comment=-)',  # main.py:20197
    'If.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # main.py:20198
    'If.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:20225
    'If.body>Assign(targets=[Name],value=Set,type_comment=-)',  # main.py:51799
    'If.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:20156
    'If.body>Assign(targets=[Name],value=UnaryOp,type_comment=-)',  # main.py:20177
    'If.body>Assign(targets=[Subscript],value=BinOp,type_comment=-)',  # main.py:18642
    'If.body>Assign(targets=[Subscript],value=Constant,type_comment=-)',  # main.py:65119
    'If.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # main.py:18772
    'If.body>Assign(targets=[Subscript],value=Subscript,type_comment=-)',  # main.py:56240
    'If.body>Assign(targets=[Subscript],value=Tuple,type_comment=-)',  # main.py:18729
    'If.body>Assign(targets=[Tuple],value=Await,type_comment=-)',  # main.py:16950
    'If.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # main.py:65216
    'If.body>Assign(targets=[Tuple],value=IfExp,type_comment=-)',  # main.py:51127
    'If.body>Assign(targets=[Tuple],value=Name,type_comment=-)',  # main.py:18726
    'If.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # main.py:50044
    'If.body>AugAssign(target=Name,op=Add,value=BinOp)',  # match_report_window.py:64
    'If.body>AugAssign(target=Name,op=Add,value=Constant)',  # main.py:51151
    'If.body>AugAssign(target=Name,op=BitOr,value=Call)',  # main.py:18746
    'If.body>Break()',  # main.py:16856
    'If.body>Continue()',  # main.py:16917
    'If.body>Expr(value=Await)',  # main.py:16383
    'If.body>Expr(value=Call)',  # main.py:16380
    'If.body>For(target=Name,iter=Name,body=[Assign],orelse=[],type_comment=-)',  # main.py:49854
    'If.body>For(target=Name,iter=Name,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:50045
    'If.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # main.py:49415
    'If.body>For(target=Name,iter=Tuple,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:56233
    'If.body>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # main.py:49385
    'If.body>If(test=BoolOp,body=[Assign],orelse=[If])',  # main.py:53640
    'If.body>If(test=BoolOp,body=[Assign],orelse=[])',  # main.py:18728
    'If.body>If(test=BoolOp,body=[Assign|Break],orelse=[])',  # main.py:65219
    'If.body>If(test=BoolOp,body=[Assign|Expr],orelse=[])',  # main.py:53706
    'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',  # main.py:20176
    'If.body>If(test=BoolOp,body=[Assign|Expr|Return],orelse=[])',  # main.py:49369
    'If.body>If(test=BoolOp,body=[Assign|If],orelse=[If])',  # main.py:53667
    'If.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # main.py:53659
    'If.body>If(test=BoolOp,body=[Expr],orelse=[])',  # main.py:64755
    'If.body>If(test=BoolOp,body=[Expr|If|Return],orelse=[])',  # main.py:64748
    'If.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',  # main.py:20163
    'If.body>If(test=BoolOp,body=[Return],orelse=[])',  # main.py:18563
    'If.body>If(test=Call,body=[Assign|If],orelse=[])',  # main.py:49856
    'If.body>If(test=Compare,body=[Assign],orelse=[Assign])',  # main.py:20240
    'If.body>If(test=Compare,body=[Assign],orelse=[])',  # main.py:56239
    'If.body>If(test=Compare,body=[Assign|Break],orelse=[])',  # main.py:49981
    'If.body>If(test=Compare,body=[Assign|Expr],orelse=[])',  # main.py:20275
    'If.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',  # main.py:49331
    'If.body>If(test=Compare,body=[Assign|If],orelse=[])',  # main.py:64815
    'If.body>If(test=Compare,body=[Break],orelse=[])',  # main.py:20512
    'If.body>If(test=Compare,body=[Expr],orelse=[Expr])',  # main.py:20204
    'If.body>If(test=Compare,body=[Expr],orelse=[])',  # main.py:50010
    'If.body>If(test=Compare,body=[Expr|If],orelse=[])',  # main.py:65193
    'If.body>If(test=Compare,body=[Expr|Raise],orelse=[])',  # main.py:20311
    'If.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # main.py:20300
    'If.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:65079
    'If.body>If(test=Name,body=[Assign],orelse=[])',  # main.py:49422
    'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',  # main.py:49405
    'If.body>If(test=Name,body=[Assign|Expr|Return],orelse=[])',  # main.py:20363
    'If.body>If(test=Name,body=[Expr],orelse=[])',  # main.py:20333
    'If.body>If(test=Name,body=[Expr|If|Return],orelse=[])',  # main.py:20200
    'If.body>If(test=Name,body=[Expr|Return],orelse=[])',  # main.py:53695
    'If.body>If(test=Name,body=[Return],orelse=[])',  # main.py:17479
    'If.body>If(test=Subscript,body=[Assign|If],orelse=[])',  # main.py:20161
    'If.body>If(test=UnaryOp,body=[Assign],orelse=[])',  # main.py:20273
    'If.body>If(test=UnaryOp,body=[Assign|Expr|For|If],orelse=[Assign])',  # main.py:49408
    'If.body>If(test=UnaryOp,body=[Assign|If],orelse=[If])',  # main.py:20189
    'If.body>If(test=UnaryOp,body=[Continue],orelse=[])',  # main.py:51801
    'If.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',  # main.py:20138
    'If.body>If(test=UnaryOp,body=[Return],orelse=[])',  # main.py:16955
    'If.body>Raise(exc=Call,cause=-)',  # main.py:16376
    'If.body>Raise(exc=Call,cause=Constant)',  # main.py:16865
    'If.body>Return(value=-)',  # main.py:28337
    'If.body>Return(value=Await)',  # main.py:53722
    'If.body>Return(value=BoolOp)',  # main.py:51730
    'If.body>Return(value=Call)',  # main.py:19969
    'If.body>Return(value=Compare)',  # main.py:18565
    'If.body>Return(value=Constant)',  # main.py:16956
    'If.body>Return(value=Dict)',  # main.py:53511
    'If.body>Return(value=Name)',  # main.py:18644
    'If.body>Return(value=Subscript)',  # main.py:18672
    'If.body>Return(value=Tuple)',  # main.py:16829
    'If.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:18734
    'If.body>Try(body=[Assign|AsyncWith],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:73520
    'If.body>Try(body=[AsyncWith],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # main.py:49288
    'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',  # main.py:49761
    'If.orelse>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:20243
    'If.orelse>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:20267
    'If.orelse>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:51133
    'If.orelse>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:49587
    'If.orelse>Assign(targets=[Tuple],value=Call,type_comment=-)',  # main.py:50061
    'If.orelse>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # region_pick.py:268
    'If.orelse>AugAssign(target=Name,op=Add,value=Constant)',  # main.py:51162
    'If.orelse>Expr(value=Await)',  # main.py:20106
    'If.orelse>Expr(value=Call)',  # main.py:50052
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[If])',  # main.py:64888
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[])',  # main.py:53685
    'If.orelse>If(test=BoolOp,body=[Expr],orelse=[Expr])',  # main.py:50049
    'If.orelse>If(test=Compare,body=[Expr],orelse=[If])',  # main.py:16392
    'If.orelse>If(test=Compare,body=[Expr],orelse=[])',  # main.py:16398
    'If.orelse>If(test=Compare,body=[Expr|Return],orelse=[Assign])',  # main.py:20256
    'If.orelse>If(test=Name,body=[Assign],orelse=[])',  # main.py:53646
    'If.test>Await(value=Call)',  # main.py:49681
    'If.test>BoolOp(op=And,values=[BoolOp|Name])',  # main.py:64978
    'If.test>BoolOp(op=And,values=[Call|Compare|Name|UnaryOp])',  # main.py:53685
    'If.test>BoolOp(op=And,values=[Call|Name])',  # main.py:62077
    'If.test>BoolOp(op=And,values=[Compare])',  # main.py:16379
    'If.test>BoolOp(op=And,values=[Compare|Name])',  # main.py:16913
    'If.test>BoolOp(op=And,values=[Compare|Subscript])',  # main.py:18671
    'If.test>BoolOp(op=And,values=[Compare|UnaryOp])',  # main.py:20163
    'If.test>BoolOp(op=And,values=[Name])',  # main.py:20176
    'If.test>BoolOp(op=And,values=[Name|UnaryOp])',  # main.py:53640
    'If.test>BoolOp(op=Or,values=[BoolOp|Compare])',  # main.py:55786
    'If.test>BoolOp(op=Or,values=[Call|Compare])',  # main.py:18728
    'If.test>BoolOp(op=Or,values=[Call|UnaryOp])',  # region_pick.py:54
    'If.test>BoolOp(op=Or,values=[Compare])',  # main.py:18563
    'If.test>BoolOp(op=Or,values=[Compare|UnaryOp])',  # main.py:57202
    'If.test>BoolOp(op=Or,values=[Name])',  # main.py:51169
    'If.test>BoolOp(op=Or,values=[UnaryOp])',  # region_pick.py:52
    'If.test>Call(func=Attribute,args=[Await],keywords=[])',  # main.py:73464
    'If.test>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:56249
    'If.test>Call(func=Attribute,args=[Name],keywords=[])',  # main.py:73452
    'If.test>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:16893
    'If.test>Call(func=Name,args=[Name],keywords=[])',  # main.py:56232
    'If.test>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:18745
    'If.test>Call(func=Name,args=[Name|Tuple],keywords=[])',  # main.py:18733
    'If.test>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # region_pick.py:211
    'If.test>Compare(left=Await,ops=[IsNot],comparators=[Constant])',  # main.py:20414
    'If.test>Compare(left=Await,ops=[Is],comparators=[Constant])',  # main.py:20311
    'If.test>Compare(left=Call,ops=[Eq],comparators=[Call])',  # main.py:65188
    'If.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # main.py:49656
    'If.test>Compare(left=Call,ops=[In],comparators=[Tuple])',  # main.py:16864
    'If.test>Compare(left=Call,ops=[Lt],comparators=[Constant])',  # main.py:49350
    'If.test>Compare(left=Call,ops=[Lt],comparators=[Name])',  # main.py:65120
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Call])',  # main.py:49795
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Constant])',  # main.py:49961
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Name])',  # main.py:56296
    'If.test>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # main.py:16389
    'If.test>Compare(left=Name,ops=[GtE],comparators=[Constant])',  # main.py:50010
    'If.test>Compare(left=Name,ops=[GtE],comparators=[Name])',  # main.py:48822
    'If.test>Compare(left=Name,ops=[Gt],comparators=[BinOp])',  # main.py:53558
    'If.test>Compare(left=Name,ops=[Gt],comparators=[Constant])',  # main.py:51152
    'If.test>Compare(left=Name,ops=[Gt],comparators=[Name])',  # match_report_window.py:63
    'If.test>Compare(left=Name,ops=[In],comparators=[Name])',  # main.py:17483
    'If.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # main.py:16382
    'If.test>Compare(left=Name,ops=[Is],comparators=[Constant])',  # main.py:16854
    'If.test>Compare(left=Name,ops=[LtE],comparators=[Constant])',  # main.py:28336
    'If.test>Compare(left=Name,ops=[Lt],comparators=[Name])',  # main.py:65116
    'If.test>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # main.py:49268
    'If.test>Compare(left=Name,ops=[NotEq],comparators=[Name])',  # main.py:53753
    'If.test>Compare(left=Name,ops=[NotIn],comparators=[Attribute])',  # region_pick.py:215
    'If.test>Compare(left=Name,ops=[NotIn],comparators=[Name])',  # main.py:16375
    'If.test>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # main.py:16916
    'If.test>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # main.py:20512
    'If.test>Compare(left=Subscript,ops=[In],comparators=[Name])',  # main.py:20209
    'If.test>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',  # main.py:64815
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',  # main.py:20440
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # main.py:20256
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Subscript])',  # main.py:20054
    'If.test>Name(id=str,ctx=Load)',  # main.py:16867
    'If.test>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20161
    'If.test>UnaryOp(op=Not,operand=Attribute)',  # region_pick.py:213
    'If.test>UnaryOp(op=Not,operand=Await)',  # main.py:19924
    'If.test>UnaryOp(op=Not,operand=BoolOp)',  # main.py:51801
    'If.test>UnaryOp(op=Not,operand=Call)',  # main.py:20147
    'If.test>UnaryOp(op=Not,operand=Compare)',  # region_pick.py:56
    'If.test>UnaryOp(op=Not,operand=Name)',  # main.py:16827
    'If.test>UnaryOp(op=Not,operand=Subscript)',  # main.py:49408
    'IfExp.body>Call(func=Attribute,args=[Name],keywords=[])',  # main.py:57236
    'IfExp.body>Call(func=Attribute,args=[],keywords=[])',  # main.py:18742
    'IfExp.body>Call(func=Name,args=[Attribute],keywords=[])',  # main.py:20365
    'IfExp.body>Call(func=Name,args=[Attribute|Constant],keywords=[])',  # main.py:56309
    'IfExp.body>Call(func=Name,args=[Call],keywords=[])',  # main.py:49390
    'IfExp.body>Call(func=Name,args=[Name],keywords=[])',  # main.py:50081
    'IfExp.body>Call(func=Name,args=[Name],keywords=[keyword])',  # main.py:53752
    'IfExp.body>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:51127
    'IfExp.body>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:51908
    'IfExp.body>Call(func=Name,args=[],keywords=[])',  # main.py:16875
    'IfExp.body>Compare(left=BinOp,ops=[Gt],comparators=[Name])',  # region_pick.py:248
    'IfExp.body>Constant(value=NoneType)',  # main.py:16796
    'IfExp.body>Constant(value=int)',  # main.py:20391
    'IfExp.body>Constant(value=str)',  # main.py:18756
    'IfExp.body>JoinedStr(values=[Constant|FormattedValue])',  # main.py:18767
    'IfExp.body>Name(id=str,ctx=Load)',  # main.py:20354
    'IfExp.body>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18640
    'IfExp.body>Tuple(elts=[Name],ctx=Load)',  # region_pick.py:254
    'IfExp.body>Tuple(elts=[Subscript],ctx=Load)',  # main.py:18723
    "IfExp.orelse>Attribute(value=Name,attr='p1_series_wins',ctx=Load)",  # main.py:20391
    "IfExp.orelse>Attribute(value=Name,attr='p2_series_wins',ctx=Load)",  # main.py:20392
    'IfExp.orelse>BinOp(left=Name,op=Sub,right=BinOp)',  # main.py:73538
    'IfExp.orelse>Call(func=Name,args=[Call],keywords=[])',  # main.py:49390
    'IfExp.orelse>Call(func=Name,args=[Name],keywords=[])',  # main.py:16796
    'IfExp.orelse>Compare(left=BinOp,ops=[GtE],comparators=[Name])',  # region_pick.py:248
    'IfExp.orelse>Constant(value=NoneType)',  # main.py:18640
    'IfExp.orelse>Constant(value=bool)',  # main.py:64841
    'IfExp.orelse>Constant(value=int)',  # main.py:49624
    'IfExp.orelse>Constant(value=str)',  # main.py:18767
    'IfExp.orelse>Dict(keys=[],values=[])',  # region_pick.py:190
    'IfExp.orelse>IfExp(test=Compare,body=Name,orelse=Subscript)',  # main.py:20388
    'IfExp.orelse>IfExp(test=Compare,body=Subscript,orelse=Name)',  # main.py:20390
    'IfExp.orelse>IfExp(test=Compare,body=Tuple,orelse=Tuple)',  # main.py:51107
    'IfExp.orelse>IfExp(test=Name,body=Name,orelse=Constant)',  # region_pick.py:250
    'IfExp.orelse>Name(id=str,ctx=Load)',  # main.py:18756
    'IfExp.orelse>Set(elts=[Call])',  # main.py:16875
    'IfExp.orelse>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20354
    'IfExp.orelse>Subscript(value=Name,slice=Name,ctx=Load)',  # match_report_window.py:48
    'IfExp.orelse>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # main.py:53752
    'IfExp.orelse>Tuple(elts=[Constant],ctx=Load)',  # main.py:51129
    'IfExp.orelse>Tuple(elts=[Name],ctx=Load)',  # region_pick.py:254
    'IfExp.orelse>Tuple(elts=[],ctx=Load)',  # main.py:51108
    "IfExp.test>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:223
    'IfExp.test>BoolOp(op=And,values=[Call|Name])',  # region_pick.py:204
    'IfExp.test>BoolOp(op=And,values=[Compare])',  # main.py:51097
    'IfExp.test>Call(func=Name,args=[Constant|Name],keywords=[])',  # match_report_window.py:48
    'IfExp.test>Call(func=Name,args=[Name],keywords=[])',  # region_pick.py:190
    'IfExp.test>Compare(left=Attribute,ops=[Eq],comparators=[Name])',  # main.py:20354
    'IfExp.test>Compare(left=BoolOp,ops=[Gt],comparators=[Constant])',  # main.py:64845
    'IfExp.test>Compare(left=Constant,ops=[In],comparators=[Name])',  # main.py:18640
    'IfExp.test>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # main.py:16875
    'IfExp.test>Compare(left=Name,ops=[Gt],comparators=[Name])',  # match_report_window.py:61
    'IfExp.test>Compare(left=Name,ops=[In],comparators=[Name])',  # main.py:20215
    'IfExp.test>Compare(left=Name,ops=[In],comparators=[Tuple])',  # main.py:51910
    'IfExp.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # main.py:18742
    'IfExp.test>Compare(left=Name,ops=[Is],comparators=[Constant])',  # main.py:16796
    'IfExp.test>Compare(left=Name,ops=[Lt],comparators=[Name])',  # match_report_window.py:62
    'IfExp.test>Compare(left=Subscript,ops=[Eq],comparators=[Subscript])',  # main.py:53851
    'IfExp.test>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',  # main.py:18723
    'IfExp.test>Name(id=str,ctx=Load)',  # main.py:49337
    'IfExp.test>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:49624
    "Import.names>alias(name='match_report_window',asname=None)",  # main.py:54213
    "Import.names>alias(name='uuid',asname='uuid_mod')",  # main.py:19922
    "ImportFrom.names>alias(name='_region_candidate_volumes',asname=None)",  # main.py:18674
    'JoinedStr.values>Constant(value=str)',  # main.py:16376
    'JoinedStr.values>FormattedValue(value=Attribute,conversion=-1,format_spec=-)',  # main.py:18679
    'JoinedStr.values>FormattedValue(value=Call,conversion=-1,format_spec=-)',  # main.py:18759
    'JoinedStr.values>FormattedValue(value=IfExp,conversion=-1,format_spec=-)',  # main.py:49337
    'JoinedStr.values>FormattedValue(value=ListComp,conversion=-1,format_spec=-)',  # main.py:50016
    'JoinedStr.values>FormattedValue(value=Name,conversion=-1,format_spec=-)',  # main.py:17407
    'JoinedStr.values>FormattedValue(value=Name,conversion=114,format_spec=-)',  # main.py:16376
    'JoinedStr.values>FormattedValue(value=Subscript,conversion=-1,format_spec=-)',  # main.py:20148
    'JoinedStr.values>FormattedValue(value=Subscript,conversion=-1,format_spec=JoinedStr)',  # main.py:50011
    'Lambda.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # main.py:17402
    'Lambda.body>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:48812
    'Lambda.body>Subscript(value=Name,slice=Name,ctx=Load)',  # main.py:50069
    'Lambda.body>Tuple(elts=[BinOp|Subscript],ctx=Load)',  # main.py:51807
    'Lambda.body>Tuple(elts=[Call|Subscript],ctx=Load)',  # main.py:17402
    'Lambda.body>Tuple(elts=[Name|Subscript],ctx=Load)',  # region_pick.py:98
    'List.ctx>Load()',  # main.py:16377
    'List.elts>Constant(value=str)',  # main.py:19898
    'List.elts>Dict(keys=[Constant],values=[Call|Name|Subscript])',  # main.py:50022
    'List.elts>Name(id=str,ctx=Load)',  # main.py:16951
    'List.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:19980
    'List.elts>Tuple(elts=[Constant|Subscript],ctx=Load)',  # main.py:49787
    'List.elts>Tuple(elts=[List],ctx=Load)',  # main.py:48804
    'List.elts>Tuple(elts=[Name],ctx=Load)',  # main.py:20197
    'List.elts>Tuple(elts=[Name|Subscript],ctx=Load)',  # main.py:20524
    'List.elts>Tuple(elts=[Subscript],ctx=Load)',  # main.py:20197
    "ListComp.elt>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick.py:74
    'ListComp.elt>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:56359
    'ListComp.elt>Call(func=Attribute,args=[],keywords=[])',  # region_pick.py:274
    'ListComp.elt>Call(func=Name,args=[Name],keywords=[])',  # main.py:16830
    'ListComp.elt>Call(func=Name,args=[],keywords=[keyword])',  # main.py:50196
    'ListComp.elt>Dict(keys=[Constant],values=[Attribute|IfExp|Name])',  # region_pick.py:222
    'ListComp.elt>Dict(keys=[Constant],values=[Call|Compare|IfExp|Subscript])',  # main.py:64844
    'ListComp.elt>Name(id=str,ctx=Load)',  # main.py:20198
    'ListComp.elt>Subscript(value=Attribute,slice=Name,ctx=Load)',  # region_pick.py:240
    'ListComp.elt>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18715
    'ListComp.elt>Tuple(elts=[Call|Name],ctx=Load)',  # main.py:51863
    'ListComp.elt>Tuple(elts=[Constant|Name],ctx=Load)',  # main.py:49828
    'ListComp.elt>Tuple(elts=[Name],ctx=Load)',  # main.py:57243
    'ListComp.elt>Tuple(elts=[Subscript],ctx=Load)',  # main.py:49458
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Attribute],is_async=0)',  # region_pick.py:74
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[BoolOp],is_async=0)',  # region_pick.py:260
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Call],is_async=0)',  # main.py:53751
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # main.py:49361
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # main.py:16830
    'ListComp.generators>comprehension(target=Name,iter=Subscript,ifs=[],is_async=0)',  # main.py:48813
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # main.py:49857
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # region_pick.py:222
    'ListComp.generators>comprehension(target=Tuple,iter=Name,ifs=[Compare],is_async=0)',  # main.py:20198
    'Name.ctx>Load()',  # main.py:4341
    'Name.ctx>Store()',  # main.py:6451
    'Raise.cause>Constant(value=NoneType)',  # main.py:16865
    'Raise.exc>Call(func=Name,args=[Constant],keywords=[])',  # match_hold.py:237
    'Raise.exc>Call(func=Name,args=[JoinedStr],keywords=[])',  # main.py:16376
    'Raise.exc>Call(func=Name,args=[],keywords=[keyword])',  # main.py:16865
    'Return.value>Await(value=Call)',  # main.py:53722
    'Return.value>BinOp(left=Call,op=Add,right=Tuple)',  # region_pick.py:257
    'Return.value>BoolOp(op=And,values=[Call|UnaryOp])',  # region_pick.py:40
    'Return.value>BoolOp(op=And,values=[Compare])',  # main.py:51730
    'Return.value>BoolOp(op=And,values=[Compare|Name])',  # main.py:51732
    'Return.value>BoolOp(op=Or,values=[Compare])',  # main.py:18566
    'Return.value>BoolOp(op=Or,values=[Constant|Name])',  # main.py:18774
    'Return.value>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:51688
    'Return.value>Call(func=Attribute,args=[Name],keywords=[keyword])',  # main.py:56251
    'Return.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:17433
    'Return.value>Call(func=Name,args=[BinOp],keywords=[])',  # main.py:48811
    'Return.value>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:6451
    'Return.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:56387
    'Return.value>Call(func=Name,args=[Name],keywords=[keyword])',  # region_pick.py:98
    'Return.value>Call(func=Name,args=[],keywords=[keyword])',  # main.py:19969
    'Return.value>Compare(left=BinOp,ops=[Lt],comparators=[Name])',  # match_report_window.py:74
    'Return.value>Compare(left=Call,ops=[GtE],comparators=[Call])',  # main.py:56284
    'Return.value>Compare(left=Subscript,ops=[Lt],comparators=[Subscript])',  # main.py:18565
    'Return.value>Constant(value=NoneType)',  # main.py:17486
    'Return.value>Constant(value=bool)',  # main.py:16956
    'Return.value>Constant(value=str)',  # region_pick.py:212
    'Return.value>Dict(keys=[Constant],values=[BoolOp|Call|Compare|Constant|IfExp|ListComp|Name|Subscript])',  # main.py:64824
    'Return.value>Dict(keys=[Constant],values=[Call|Constant])',  # main.py:53608
    'Return.value>Dict(keys=[Constant],values=[Call|Constant|Name])',  # main.py:65151
    'Return.value>Dict(keys=[Constant],values=[Call|Constant|Name|UnaryOp])',  # main.py:65122
    'Return.value>Dict(keys=[Constant],values=[Constant])',  # main.py:53511
    'Return.value>Dict(keys=[Constant],values=[Constant|Name])',  # main.py:56339
    'Return.value>DictComp(key=Attribute,value=Call,generators=[comprehension])',  # tournaments.py:308
    'Return.value>IfExp(test=Call,body=Call,orelse=Subscript)',  # match_report_window.py:48
    'Return.value>IfExp(test=Call,body=Name,orelse=Constant)',  # region_pick.py:194
    'Return.value>IfExp(test=Compare,body=Call,orelse=Constant)',  # main.py:56309
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Name)',  # main.py:18756
    'Return.value>IfExp(test=Name,body=Tuple,orelse=Tuple)',  # region_pick.py:254
    'Return.value>JoinedStr(values=[Constant|FormattedValue])',  # match_hold.py:220
    'Return.value>ListComp(elt=Dict,generators=[comprehension])',  # region_pick.py:222
    'Return.value>Name(id=str,ctx=Load)',  # main.py:16979
    'Return.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18672
    'Return.value>Tuple(elts=[BoolOp],ctx=Load)',  # main.py:57204
    'Return.value>Tuple(elts=[BoolOp|Call],ctx=Load)',  # main.py:56844
    'Return.value>Tuple(elts=[Call|Constant],ctx=Load)',  # main.py:55794
    'Return.value>Tuple(elts=[Call|Name],ctx=Load)',  # main.py:16935
    'Return.value>Tuple(elts=[Constant],ctx=Load)',  # main.py:6453
    'Return.value>Tuple(elts=[Constant|Name],ctx=Load)',  # main.py:16829
    'Return.value>Tuple(elts=[Constant|Subscript],ctx=Load)',  # region_pick.py:81
    'Return.value>Tuple(elts=[Dict|Name],ctx=Load)',  # region_pick.py:183
    'Return.value>Tuple(elts=[IfExp|Name],ctx=Load)',  # main.py:16796
    'Return.value>Tuple(elts=[ListComp],ctx=Load)',  # main.py:48813
    'Return.value>Tuple(elts=[Name],ctx=Load)',  # main.py:28324
    'Return.value>Tuple(elts=[Name|Subscript],ctx=Load)',  # main.py:18654
    'Set.elts>Call(func=Name,args=[Name],keywords=[])',  # main.py:16875
    'Set.elts>Name(id=str,ctx=Load)',  # region_pick.py:244
    'Set.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:51799
    'SetComp.elt>Call(func=Name,args=[Name],keywords=[])',  # main.py:16884
    'SetComp.elt>Name(id=str,ctx=Load)',  # main.py:16826
    'SetComp.elt>Tuple(elts=[Name],ctx=Load)',  # main.py:17401
    'SetComp.generators>comprehension(target=Name,iter=BoolOp,ifs=[BoolOp],is_async=0)',  # region_pick.py:189
    'SetComp.generators>comprehension(target=Name,iter=BoolOp,ifs=[Name],is_async=0)',  # main.py:73451
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # main.py:16826
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # main.py:73526
    'SetComp.generators>comprehension(target=Tuple,iter=BoolOp,ifs=[BoolOp],is_async=0)',  # main.py:17401
    'Slice.lower>Constant(value=int)',  # region_pick.py:238
    'Slice.upper>Constant(value=int)',  # main.py:20217
    'Subscript.ctx>Load()',  # main.py:6449
    'Subscript.ctx>Store()',  # main.py:18642
    'Subscript.slice>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:56370
    'Subscript.slice>Constant(value=int)',  # main.py:16910
    'Subscript.slice>Constant(value=str)',  # main.py:16849
    'Subscript.slice>Name(id=str,ctx=Load)',  # main.py:18642
    'Subscript.slice>Slice(lower=-,upper=Constant,step=-)',  # main.py:20217
    'Subscript.slice>Slice(lower=Constant,upper=-,step=-)',  # region_pick.py:238
    'Subscript.slice>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:18724
    'Subscript.slice>Tuple(elts=[BinOp|Name],ctx=Load)',  # main.py:16795
    'Subscript.slice>Tuple(elts=[Constant|Name],ctx=Load)',  # main.py:6449
    'Subscript.slice>Tuple(elts=[Name],ctx=Load)',  # main.py:16810
    'Subscript.slice>Tuple(elts=[Subscript],ctx=Load)',  # main.py:48796
    "Subscript.value>Attribute(value=Call,attr='hex',ctx=Load)",  # main.py:20217
    "Subscript.value>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick.py:240
    'Subscript.value>BoolOp(op=Or,values=[Constant|Name])',  # main.py:53845
    'Subscript.value>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:57204
    'Subscript.value>BoolOp(op=Or,values=[Name])',  # region_pick.py:86
    'Subscript.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:16839
    'Subscript.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:16910
    'Subscript.value>Call(func=Name,args=[],keywords=[])',  # main.py:65119
    'Subscript.value>Name(id=str,ctx=Load)',  # main.py:6449
    'Subscript.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:53752
    'Try.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:18747
    'Try.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:18743
    'Try.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # main.py:18716
    'Try.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # main.py:73535
    'Try.body>Assign(targets=[Name],value=List,type_comment=-)',  # main.py:18730
    'Try.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # main.py:18715
    'Try.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:73544
    'Try.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # main.py:73526
    'Try.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # main.py:16839
    'Try.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # main.py:18748
    'Try.body>Assign(targets=[Tuple],value=IfExp,type_comment=-)',  # main.py:57236
    'Try.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # main.py:18677
    'Try.body>AsyncWith(items=[withitem],body=[Assign],type_comment=-)',  # main.py:18675
    'Try.body>AsyncWith(items=[withitem],body=[Assign|Expr|For|If],type_comment=-)',  # main.py:51088
    'Try.body>AsyncWith(items=[withitem],body=[Assign|For],type_comment=-)',  # main.py:18717
    'Try.body>AsyncWith(items=[withitem],body=[Expr],type_comment=-)',  # main.py:4341
    'Try.body>Expr(value=Await)',  # main.py:16857
    'Try.body>For(target=Name,iter=Name,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # main.py:18731
    'Try.body>For(target=Name,iter=Name,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:16850
    'Try.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # main.py:18744
    'Try.body>If(test=BoolOp,body=[Assign],orelse=[])',  # main.py:57238
    'Try.body>If(test=Compare,body=[Assign|If],orelse=[])',  # main.py:18725
    "Try.body>ImportFrom(module='tournaments',names=[alias],level=0)",  # main.py:18674
    'Try.body>Return(value=Call)',  # main.py:6451
    'Try.body>Return(value=Compare)',  # main.py:56284
    'Try.body>Return(value=IfExp)',  # main.py:56309
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Assign])',  # main.py:18736
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Pass])',  # main.py:4347
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Return])',  # main.py:6452
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign])',  # main.py:18752
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign|Expr])',  # main.py:57246
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign|Expr|If])',  # main.py:73545
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr])',  # main.py:18678
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr|If|Raise])',  # main.py:16860
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Return])',  # region_pick.py:182
    'Tuple.ctx>Load()',  # main.py:6453
    'Tuple.ctx>Store()',  # main.py:16883
    "Tuple.elts>Attribute(value=Name,attr='admitted_by',ctx=Load)",  # region_pick.py:265
    "Tuple.elts>Attribute(value=Name,attr='gain',ctx=Load)",  # region_pick.py:266
    "Tuple.elts>Attribute(value=Name,attr='id',ctx=Load)",  # main.py:20299
    "Tuple.elts>Attribute(value=Name,attr='max_regret',ctx=Load)",  # region_pick.py:266
    "Tuple.elts>Attribute(value=Name,attr='region',ctx=Load)",  # region_pick.py:257
    "Tuple.elts>Attribute(value=Name,attr='sum',ctx=Load)",  # region_pick.py:266
    "Tuple.elts>Attribute(value=Name,attr='worst',ctx=Load)",  # region_pick.py:266
    'Tuple.elts>BinOp(left=BinOp,op=Add,right=BoolOp)',  # main.py:51808
    'Tuple.elts>BinOp(left=Name,op=BitOr,right=Constant)',  # main.py:16795
    'Tuple.elts>BoolOp(op=Or,values=[Constant|Name])',  # main.py:56844
    'Tuple.elts>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:57204
    'Tuple.elts>Call(func=Attribute,args=[Call],keywords=[])',  # main.py:51863
    'Tuple.elts>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:56844
    'Tuple.elts>Call(func=Name,args=[Call|Constant],keywords=[])',  # main.py:55794
    'Tuple.elts>Call(func=Name,args=[GeneratorExp],keywords=[])',  # main.py:16935
    'Tuple.elts>Call(func=Name,args=[Name],keywords=[])',  # main.py:18677
    'Tuple.elts>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:17402
    'Tuple.elts>Constant(value=NoneType)',  # main.py:18732
    'Tuple.elts>Constant(value=bool)',  # main.py:16829
    'Tuple.elts>Constant(value=ellipsis)',  # main.py:6449
    'Tuple.elts>Constant(value=int)',  # main.py:6453
    'Tuple.elts>Constant(value=str)',  # main.py:16864
    'Tuple.elts>Dict(keys=[Constant],values=[Call])',  # region_pick.py:183
    'Tuple.elts>Dict(keys=[Constant],values=[JoinedStr])',  # main.py:18753
    'Tuple.elts>Dict(keys=[],values=[])',  # main.py:18713
    'Tuple.elts>IfExp(test=Compare,body=Constant,orelse=Call)',  # main.py:16796
    'Tuple.elts>List(elts=[Subscript],ctx=Load)',  # main.py:48804
    'Tuple.elts>List(elts=[],ctx=Load)',  # main.py:50044
    'Tuple.elts>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:48813
    'Tuple.elts>Name(id=str,ctx=Load)',  # main.py:6449
    'Tuple.elts>Name(id=str,ctx=Store)',  # main.py:16883
    'Tuple.elts>Subscript(value=BoolOp,slice=Constant,ctx=Load)',  # region_pick.py:86
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:17402
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Store)',  # main.py:18677
    'Tuple.elts>Subscript(value=Name,slice=Name,ctx=Load)',  # main.py:48796
    'Tuple.elts>Tuple(elts=[Attribute|Constant],ctx=Load)',  # main.py:20299
    'Tuple.elts>Tuple(elts=[Constant],ctx=Load)',  # main.py:20298
    'Tuple.elts>Tuple(elts=[Name],ctx=Store)',  # main.py:56381
    'Tuple.elts>UnaryOp(op=USub,operand=Call)',  # region_pick.py:257
    'UnaryOp.op>Not()',  # main.py:16827
    'UnaryOp.op>USub()',  # main.py:65123
    "UnaryOp.operand>Attribute(value=Name,attr='fresh',ctx=Load)",  # region_pick.py:213
    'UnaryOp.operand>Await(value=Call)',  # main.py:19924
    'UnaryOp.operand>BoolOp(op=And,values=[Name])',  # main.py:20163
    'UnaryOp.operand>BoolOp(op=Or,values=[BoolOp])',  # main.py:51801
    'UnaryOp.operand>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick.py:257
    'UnaryOp.operand>Call(func=Name,args=[Await|Name],keywords=[])',  # main.py:51795
    'UnaryOp.operand>Call(func=Name,args=[Name],keywords=[])',  # main.py:20147
    'UnaryOp.operand>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:53683
    'UnaryOp.operand>Call(func=Name,args=[],keywords=[])',  # main.py:53640
    'UnaryOp.operand>Compare(left=Name,ops=[LtE],comparators=[Name])',  # region_pick.py:56
    'UnaryOp.operand>Constant(value=int)',  # main.py:65123
    'UnaryOp.operand>Name(id=str,ctx=Load)',  # main.py:16827
    'UnaryOp.operand>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:49407
    'While.body>Assign(targets=[Name],value=Await,type_comment=-)',  # main.py:49825
    'While.body>Assign(targets=[Name],value=Call,type_comment=-)',  # main.py:20018
    'While.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # main.py:49851
    'While.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # main.py:49913
    'While.body>Assign(targets=[Name],value=Name,type_comment=-)',  # main.py:49798
    'While.body>Assign(targets=[Tuple],value=Await,type_comment=-)',  # main.py:49868
    'While.body>AugAssign(target=Name,op=Add,value=Constant)',  # main.py:20016
    'While.body>AugAssign(target=Name,op=Sub,value=Constant)',  # main.py:49762
    'While.body>Break()',  # main.py:49876
    'While.body>Expr(value=Await)',  # main.py:20017
    'While.body>Expr(value=Call)',  # main.py:62074
    'While.body>For(target=Name,iter=Tuple,body=[Assign|If],orelse=[],type_comment=-)',  # main.py:62075
    'While.body>If(test=BoolOp,body=[Assign|Break|Expr],orelse=[])',  # main.py:49953
    'While.body>If(test=BoolOp,body=[Continue],orelse=[])',  # main.py:62072
    'While.body>If(test=Compare,body=[Assign|Break],orelse=[])',  # main.py:49905
    'While.body>If(test=Compare,body=[Assign|For|If],orelse=[])',  # main.py:49852
    'While.body>If(test=Compare,body=[Break],orelse=[])',  # main.py:49777
    'While.body>If(test=Compare,body=[Break|Expr],orelse=[])',  # main.py:49829
    'While.body>If(test=Compare,body=[Continue|Expr],orelse=[])',  # main.py:49795
    'While.body>If(test=Compare,body=[Continue|Expr|If],orelse=[])',  # main.py:49976
    'While.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # main.py:49872
    'While.body>If(test=Compare,body=[Return],orelse=[])',  # main.py:49870
    'While.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',  # main.py:20027
    'While.orelse>Expr(value=Await)',  # main.py:49878
    'While.orelse>Expr(value=Call)',  # main.py:49879
    'While.orelse>Raise(exc=Call,cause=-)',  # main.py:49881
    'While.test>BoolOp(op=And,values=[Compare])',  # main.py:20015
    'While.test>Compare(left=Name,ops=[Gt],comparators=[Constant])',  # main.py:49761
    'While.test>Name(id=str,ctx=Load)',  # main.py:62070
    'arg.annotation>BinOp(left=Name,op=BitOr,right=Constant)',  # main.py:28333
    'arg.annotation>Name(id=str,ctx=Load)',  # main.py:6449
    'arg.annotation>Subscript(value=Name,slice=Name,ctx=Load)',  # main.py:48796
    'arg.annotation>Subscript(value=Name,slice=Tuple,ctx=Load)',  # main.py:28358
    'arguments.args>arg(arg=str,annotation=-,type_comment=-)',  # main.py:4295
    'arguments.args>arg(arg=str,annotation=BinOp,type_comment=-)',  # main.py:28333
    'arguments.args>arg(arg=str,annotation=Name,type_comment=-)',  # main.py:6449
    'arguments.args>arg(arg=str,annotation=Subscript,type_comment=-)',  # main.py:28358
    'arguments.defaults>Call(func=Name,args=[Constant],keywords=[keyword])',  # main.py:49169
    'arguments.defaults>Call(func=Name,args=[Name],keywords=[])',  # main.py:19899
    'arguments.defaults>Constant(value=NoneType)',  # main.py:16803
    'arguments.defaults>Constant(value=float)',  # main.py:48816
    'arguments.defaults>Constant(value=str)',  # main.py:18630
    'arguments.defaults>Name(id=str,ctx=Load)',  # main.py:16939
    'arguments.defaults>Tuple(elts=[],ctx=Load)',  # main.py:28358
    'arguments.kw_defaults>Constant(value=NoneType)',  # main.py:16343
    'arguments.kw_defaults>Constant(value=bool)',  # main.py:16809
    'arguments.kw_defaults>Constant(value=int)',  # main.py:16808
    'arguments.kw_defaults>Constant(value=str)',  # main.py:18683
    'arguments.kw_defaults>Tuple(elts=[],ctx=Load)',  # main.py:16805
    'arguments.kwonlyargs>arg(arg=str,annotation=-,type_comment=-)',  # main.py:16343
    'arguments.kwonlyargs>arg(arg=str,annotation=Name,type_comment=-)',  # main.py:16808
    "comprehension.ifs>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick.py:74
    'comprehension.ifs>BoolOp(op=And,values=[Attribute|Compare])',  # region_pick.py:261
    'comprehension.ifs>BoolOp(op=And,values=[Call|Name])',  # region_pick.py:189
    'comprehension.ifs>BoolOp(op=And,values=[Compare|Name])',  # main.py:17401
    'comprehension.ifs>Call(func=Attribute,args=[],keywords=[])',  # main.py:53751
    'comprehension.ifs>Call(func=Name,args=[GeneratorExp],keywords=[])',  # region_pick.py:83
    'comprehension.ifs>Compare(left=Await,ops=[IsNot],comparators=[Constant])',  # main.py:20199
    'comprehension.ifs>Compare(left=BinOp,ops=[GtE],comparators=[Name])',  # region_pick.py:246
    'comprehension.ifs>Compare(left=Call,ops=[NotEq],comparators=[Call])',  # main.py:57244
    'comprehension.ifs>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # main.py:49857
    'comprehension.ifs>Compare(left=Name,ops=[Eq],comparators=[Name])',  # main.py:18646
    'comprehension.ifs>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # main.py:16826
    'comprehension.ifs>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # main.py:53815
    'comprehension.ifs>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # main.py:49361
    'comprehension.ifs>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # main.py:49362
    'comprehension.ifs>Compare(left=Subscript,ops=[NotEq],comparators=[Subscript])',  # main.py:53816
    'comprehension.ifs>Compare(left=Subscript,ops=[NotIn],comparators=[Name])',  # main.py:49420
    'comprehension.ifs>Name(id=str,ctx=Load)',  # main.py:73451
    'comprehension.ifs>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:64816
    'comprehension.iter>BoolOp(op=Or,values=[Name|Tuple])',  # main.py:17401
    'comprehension.iter>Call(func=Attribute,args=[Constant],keywords=[])',  # main.py:6451
    'comprehension.iter>Call(func=Attribute,args=[],keywords=[])',  # main.py:18646
    'comprehension.iter>Call(func=Name,args=[Name],keywords=[])',  # region_pick.py:225
    'comprehension.iter>Name(id=str,ctx=Load)',  # main.py:16826
    'comprehension.iter>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:48813
    'comprehension.iter>Subscript(value=Name,slice=Name,ctx=Load)',  # match_hold.py:352
    'comprehension.target>Name(id=str,ctx=Store)',  # main.py:6451
    'comprehension.target>Tuple(elts=[Name],ctx=Store)',  # main.py:16883
    "keyword.value>Attribute(value=Name,attr='p1_series_wins',ctx=Load)",  # main.py:20356
    "keyword.value>Attribute(value=Name,attr='p2_series_wins',ctx=Load)",  # main.py:20357
    "keyword.value>Attribute(value=Name,attr='utc',ctx=Load)",  # main.py:18739
    'keyword.value>BinOp(left=ListComp,op=Add,right=Call)',  # main.py:51121
    'keyword.value>BinOp(left=Name,op=Add,right=List)',  # main.py:49915
    'keyword.value>BinOp(left=Name,op=Add,right=Name)',  # main.py:50096
    'keyword.value>BoolOp(op=Or,values=[Constant|Subscript])',  # main.py:20385
    'keyword.value>Call(func=Attribute,args=[],keywords=[])',  # main.py:18751
    'keyword.value>Call(func=Name,args=[Attribute],keywords=[])',  # main.py:20353
    'keyword.value>Call(func=Name,args=[BoolOp],keywords=[])',  # main.py:49400
    'keyword.value>Call(func=Name,args=[Call],keywords=[])',  # main.py:49394
    'keyword.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # main.py:20358
    'keyword.value>Call(func=Name,args=[Name],keywords=[])',  # main.py:20359
    'keyword.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # main.py:53828
    'keyword.value>Call(func=Name,args=[Subscript],keywords=[])',  # main.py:49318
    'keyword.value>Compare(left=Name,ops=[Is],comparators=[Constant])',  # main.py:20591
    'keyword.value>Constant(value=NoneType)',  # main.py:20465
    'keyword.value>Constant(value=bool)',  # main.py:17010
    'keyword.value>Constant(value=int)',  # main.py:16865
    'keyword.value>Constant(value=str)',  # main.py:16865
    'keyword.value>IfExp(test=Compare,body=Constant,orelse=Attribute)',  # main.py:20391
    'keyword.value>IfExp(test=Compare,body=Constant,orelse=Constant)',  # main.py:20215
    'keyword.value>IfExp(test=Compare,body=Constant,orelse=IfExp)',  # main.py:20387
    'keyword.value>IfExp(test=Compare,body=Constant,orelse=Name)',  # main.py:49696
    'keyword.value>IfExp(test=Compare,body=Name,orelse=Name)',  # main.py:20590
    'keyword.value>IfExp(test=Compare,body=Name,orelse=Subscript)',  # main.py:20354
    'keyword.value>IfExp(test=Compare,body=Subscript,orelse=Name)',  # main.py:20355
    'keyword.value>IfExp(test=Name,body=Constant,orelse=Constant)',  # main.py:49339
    'keyword.value>IfExp(test=Name,body=Name,orelse=Constant)',  # main.py:49631
    'keyword.value>IfExp(test=Subscript,body=Call,orelse=Constant)',  # main.py:49624
    'keyword.value>Lambda(args=arguments,body=Call)',  # main.py:48812
    'keyword.value>Lambda(args=arguments,body=Subscript)',  # main.py:50069
    'keyword.value>Lambda(args=arguments,body=Tuple)',  # main.py:17402
    'keyword.value>List(elts=[Constant],ctx=Load)',  # main.py:19898
    'keyword.value>List(elts=[Name],ctx=Load)',  # main.py:20006
    'keyword.value>List(elts=[Name|Subscript],ctx=Load)',  # main.py:20473
    'keyword.value>List(elts=[Subscript],ctx=Load)',  # main.py:20006
    'keyword.value>List(elts=[Tuple],ctx=Load)',  # main.py:49787
    'keyword.value>List(elts=[],ctx=Load)',  # main.py:51980
    'keyword.value>ListComp(elt=Subscript,generators=[comprehension])',  # main.py:49467
    'keyword.value>ListComp(elt=Tuple,generators=[comprehension])',  # main.py:49828
    'keyword.value>Name(id=str,ctx=Load)',  # main.py:16381
    'keyword.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # main.py:20223
    'keyword.value>Tuple(elts=[Constant],ctx=Load)',  # main.py:56251
    'keyword.value>Tuple(elts=[Constant|Subscript],ctx=Load)',  # main.py:49459
    'keyword.value>Tuple(elts=[Tuple],ctx=Load)',  # main.py:20298
    'withitem.context_expr>Call(func=Attribute,args=[],keywords=[])',  # main.py:4341
})


A1_MEANINGFUL = frozenset({
    'AsyncSession',
    'BET_TAX_ODDS_MAX',
    'BET_TAX_RATE',
    'Counter',
    'DBAPIError',
    'Depends',
    'Exception',
    'FFA_GATHER_CAP_SECONDS',
    'FFA_GATHER_EXTEND_SECONDS',
    'FFA_GATHER_SECONDS',
    'FFA_KILLS_TIEBREAK_MIN_VERSION',
    'FFA_MAX_PLAYERS',
    'FFA_MIN_PLAYERS',
    'FFA_PROXIMITY_VICTIM_MIN_VERSION',
    'FORMATION_MAX_ATTEMPTS',
    'FRESH_ANCHORS',
    'GoldTransaction',
    'HOLD_CAPS_TOKEN',
    'HTTPException',
    'IntegrityError',
    'JSONResponse',
    'LEASE_MAX_LOBBY_SEAT',
    'LEASE_TTL_ASSEMBLY',
    'LEASE_TTL_INGAME',
    'LEASE_TTL_POLLING',
    'LOBBY_MEMBER_FRESH_SQL',
    'MODES',
    'OperationalError',
    'PING_MAX_MS',
    'PING_MIN_MS',
    'Player',
    'QUEUE_EXPIRE_MINUTES',
    'Query',
    'QueuePollResponse',
    'RANKED_WINDOW_LEGACY_CAP',
    'READY_TIMEOUT_SECONDS',
    'REGION_GROUP_REGRET_MS',
    'REGION_LIVE_WINDOW_DAYS',
    'REGION_PINGS_ISSUANCE_MAX_AGE_S',
    'REGION_PINGS_MARGIN_MS',
    'REGION_VOLUMES_CACHE_S',
    'ROOM_RULES_DEFAULT',
    'ROOM_RULES_MIN_VERSION',
    'RankedSeries',
    'Request',
    'SPECTATE_BROADCAST_STEAM_IDS',
    'StakeRefundRefused',
    'TEAM_QUEUE_EXPIRE_MINUTES',
    'TEAM_READY_TIMEOUT_SECONDS',
    'TEAM_TRUST_2V2_RATING_AFTER',
    'TEAM_TRUST_2V2_RD_BELOW',
    'TeamQueueMember',
    'TeamQueuePollResponse',
    'ValueError',
    'WHY_BASELINE',
    'WHY_BOUNDED',
    'WHY_ERROR',
    'WHY_MAJORITY',
    'WHY_QUORUM',
    '_Cand',
    '_FFA_CANDIDATE_SQL',
    '_FFA_CLOSE_RECORD_SET',
    '_MAJORITY_STRICT',
    '_MEMBER_COLS',
    '_OVT_CANDIDATE_SQL',
    '_QUEUE_LOCK_TABLES',
    '_QUEUE_PARENT_LOCK_TABLES',
    '_QUEUE_TABLE',
    '_RANKED_CANDIDATE_SQL',
    '_REGION_VOLUMES_CACHE',
    '_ROOM_RULES_QUEUE_TABLES',
    '_SELECT_BY_WORST',
    '_SERIES_TABLE',
    '_SERVICE_UUID_MAX_AGE_SECONDS',
    '_SERVICE_UUID_REFRESH_SECONDS',
    '_SKIP_QUORUM',
    '_Seat',
    '_TEAM_BET_REFUND_STATUSES',
    '_TEAM_BILATERAL_SQL',
    '_TEAM_CALLER_ROW_COLS',
    '_TEAM_CANDIDATE_SQL_TMPL',
    '_TEAM_LIVE_FAMILY_IDS_SQL',
    '_TEAM_RESUME_CONSENT_SQL',
    '_TEAM_RESUME_WINDOW_MINUTES',
    '_admission_key',
    '_asm_poll_step',
    '_asm_sqlstate',
    '_assert_no_service_subject',
    '_balance_teams',
    '_baseline',
    '_bet_fighter_tax',
    '_check_steam_session',
    '_clean_map',
    '_credit_bet_fighter_tax',
    '_credit_team_bet_fighter_tax',
    '_dissolve_group_rows',
    '_evict_other_queue_searching',
    '_ffa_effective_host',
    '_ffa_gather_decide',
    '_ffa_gather_last_join_mono',
    '_ffa_live_lobby_members',
    '_ffa_lobby_config',
    '_ffa_poll_locked_payload',
    '_ffa_roster_clears_proximity_floor',
    '_ffa_sort_key',
    '_find_current_active_series',
    '_form_attempt',
    '_form_left',
    '_formation_lease_conflict',
    '_get',
    '_group_game_in_progress',
    '_group_game_positively_live',
    '_group_region',
    '_identity_lock_many',
    '_in_match_evidence_trustworthy',
    '_is_banned',
    '_is_number',
    '_json',
    '_latch_sql',
    '_lease_acquire',
    '_lease_acquire_many',
    '_lease_admission_gate',
    '_lease_live_claim_strict',
    '_lease_live_mode',
    '_lease_renew',
    '_lock_group_snapshot',
    '_lock_queue_rows_ordered',
    '_lock_snapshot_rows',
    '_match_hold',
    '_mod_version_at_least',
    '_mode_or_400',
    '_mrw_mod',
    '_ovt_poll_locked_payload',
    '_parse_version',
    '_pick',
    '_pick_region_for_group',
    '_pick_room_region',
    '_player_body_color',
    '_presence_is_online',
    '_presence_touch',
    '_publish_pair_sitting',
    '_queue_delete_partner_if_reciprocal',
    '_queue_pair_reciprocal',
    '_queue_reset_partner_if_reciprocal',
    '_queue_reset_to_searching',
    '_queue_stamp_room_reciprocal',
    '_ranked_identity_phase',
    '_ranked_window_binds',
    '_rdm_claim',
    '_reconcile_ffa_lobby_bets',
    '_reconcile_team_series_bets',
    '_region_current',
    '_region_home_of',
    '_region_mode_of',
    '_region_pings_from_header',
    '_region_pings_newer',
    '_region_pings_store',
    '_region_volumes',
    '_request_mod_version',
    '_return_stake_exactly',
    '_rules_admit',
    '_rules_for_members',
    '_rules_for_queue_match',
    '_rules_json',
    '_rules_members',
    '_rules_normalize',
    '_rules_payload',
    '_rules_prop',
    '_s2_player_live_hold',
    '_s2_poll_readmissible',
    '_service_player_uuids',
    '_stamp_team_series_colors',
    '_strict_steam_session_ok',
    '_team_balance_rating',
    '_team_clear_dc_fallback_marker',
    '_team_color_holders',
    '_team_lock_family_pick',
    '_team_quartet_key',
    '_team_quartet_lock',
    '_team_relock_existing_series',
    '_team_resolve_live_family',
    '_team_series_resumable',
    'abs',
    'all',
    'anchor_fresh',
    'any',
    'app',
    'asyncio',
    'bool',
    'bytes',
    'caps_token_sql',
    'collections',
    'compute_elo_range',
    'compute_ranked_window',
    'ctx',
    'datetime',
    'db',
    'dict',
    'enumerate',
    'float',
    'get_db',
    'getattr',
    'globals',
    'hasattr',
    'held_overlap',
    'id',
    'int',
    'isinstance',
    'len',
    'list',
    'math',
    'max',
    'min',
    'namedtuple',
    'next',
    'print',
    'random',
    'range',
    'repr',
    'round',
    'session',
    'set',
    'sorted',
    'str',
    'sum',
    'text',
    'time',
    'timedelta',
    'timezone',
    'tuple',
    'type',
    'uuid',
    'uuid_mod',
    'zip',
    # round 8 (M3): the team formation's roster, so its stores are anchored
    'others',
})


# The anchored rule (round 8, ruling REHEARSAL-FOUR-R7-A1, M3;
# closed_walk.anchored_refusals). GENERATED ONCE from the real spans at
# 3130bb9d by RF/r8/ga1/gen_r8_frozen.py and frozen; never regenerated.
# A pair (spelling, how) admits a binding that is not a store: a
# parameter, an import. A triple admits ONE position: a store of a
# meaningful spelling, (spelling, 'store', anchor), or a transaction end,
# (attr, 'end', anchor); the anchor is every node shape from the span
# root's child down to the Name or the call. Round 7's pairs
# ('_form_attempt', 'store') and ('_form_left', 'store'), which admitted
# such a store anywhere, are gone, and the commit and rollback calls are
# no longer admitted anywhere their shape is: each real one is listed at
# its own position (the first real file:line it stands at).
A1_BINDINGS = frozenset({
    ('db', 'parameter'),
    ('uuid_mod', 'import'),
    ('rollback', 'end', (  # main.py:16863
        'AsyncFunctionDef.body>Try(body=[Assign|Expr|For],handlers=[ExceptHandler],orelse=[],finalbody=[])',
        'Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr|If|Raise])',
        'ExceptHandler.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:19950
        'AsyncFunctionDef.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:19968
        'AsyncFunctionDef.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20017
        'AsyncFunctionDef.body>While(test=BoolOp,body=[Assign|AugAssign|Expr|If],orelse=[])',
        'While.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20028
        'AsyncFunctionDef.body>While(test=BoolOp,body=[Assign|AugAssign|Expr|If],orelse=[])',
        'While.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20117
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20141
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20172
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=Subscript,body=[Assign|If],orelse=[])',
        'If.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20213
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|If],orelse=[If])',
        'If.body>If(test=Name,body=[Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20254
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|If],orelse=[If])',
        'If.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20261
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|If],orelse=[If])',
        'If.orelse>If(test=Compare,body=[Expr|Return],orelse=[Assign])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20304
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:20315
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=Compare,body=[Expr|Raise],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20328
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20366
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20398
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20417
        'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('_form_attempt', 'store', (  # main.py:20429
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.target>Name(id=str,ctx=Store)',
    )),
    ('commit', 'end', (  # main.py:20438
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:20486
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=BoolOp,body=[Assign|Continue|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:20510
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=Compare,body=[Assign|Continue|Expr|If],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:20552
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=Compare,body=[Expr|Raise],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:20554
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:20570
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|For|If|Return],orelse=[Expr|Raise],type_comment=-)',
        'For.orelse>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49282
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return|Try],orelse=[])',
        'If.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49309
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return|Try],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49316
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return|Try],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49335
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49380
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Subscript,body=[Assign|If],orelse=[])',
        'If.body>If(test=BoolOp,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49437
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|Expr|For|If],orelse=[Assign])',
        'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49474
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|Expr|For|If],orelse=[Assign])',
        'If.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:49576
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=UnaryOp,body=[Assign|Expr|For|If],orelse=[Assign])',
        'If.body>If(test=Compare,body=[Expr|Raise],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49606
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49635
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|FunctionDef|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49682
        'AsyncFunctionDef.body>If(test=Await,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('_form_left', 'store', (  # main.py:49757
        'AsyncFunctionDef.body>Assign(targets=[Name],value=Name,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('_form_left', 'store', (  # main.py:49762
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>AugAssign(target=Name,op=Sub,value=Constant)',
        'AugAssign.target>Name(id=str,ctx=Store)',
    )),
    ('rollback', 'end', (  # main.py:49796
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Continue|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:49844
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Break|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49873
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:49878
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.orelse>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:49887
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|While],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('others', 'store', (  # main.py:49890
        'AsyncFunctionDef.body>Assign(targets=[Name],value=Constant,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('_form_left', 'store', (  # main.py:49897
        'AsyncFunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('_form_left', 'store', (  # main.py:49899
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>AugAssign(target=Name,op=Sub,value=Constant)',
        'AugAssign.target>Name(id=str,ctx=Store)',
    )),
    ('others', 'store', (  # main.py:49906
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Assign|Break],orelse=[])',
        'If.body>Assign(targets=[Name],value=Name,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('rollback', 'end', (  # main.py:49958
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=BoolOp,body=[Assign|Break|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('others', 'store', (  # main.py:49959
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=BoolOp,body=[Assign|Break|Expr],orelse=[])',
        'If.body>Assign(targets=[Name],value=List,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('rollback', 'end', (  # main.py:49962
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Continue|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:49980
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Continue|Expr|If],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('others', 'store', (  # main.py:49984
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>If(test=Compare,body=[Continue|Expr|If],orelse=[])',
        'If.body>If(test=Compare,body=[Assign|Break],orelse=[])',
        'If.body>Assign(targets=[Name],value=List,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('others', 'store', (  # main.py:49987
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.body>Assign(targets=[Name],value=Name,type_comment=-)',
        'Assign.targets>Name(id=str,ctx=Store)',
    )),
    ('rollback', 'end', (  # main.py:49992
        'AsyncFunctionDef.body>While(test=Compare,body=[Assign|AugAssign|Break|Expr|If],orelse=[Expr|Raise])',
        'While.orelse>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:50012
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:50176
        'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Raise],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:53561
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|If],orelse=[])',
        'If.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:53702
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=Name,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('_form_attempt', 'store', (  # main.py:53741
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',
        'For.target>Name(id=str,ctx=Store)',
    )),
    ('rollback', 'end', (  # main.py:53772
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=Compare,body=[Assign|Continue|Expr],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:53787
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=Compare,body=[Assign|Continue|Expr|If],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:53800
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',
        'For.orelse>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:53807
        'AsyncFunctionDef.body>If(test=UnaryOp,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:53818
        'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:64760
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return|Try],orelse=[])',
        'If.body>If(test=BoolOp,body=[Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('commit', 'end', (  # main.py:64951
        'AsyncFunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:65192
        'AsyncFunctionDef.body>For(target=Name,iter=Call,body=[Assign|Break|Expr|If],orelse=[Expr|Raise],type_comment=-)',
        'For.body>If(test=BoolOp,body=[Assign|Continue|Expr|If],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
    ('rollback', 'end', (  # main.py:65248
        'AsyncFunctionDef.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',
        'If.body>Expr(value=Await)',
        'Expr.value>Await(value=Call)',
        'Await.value>Call(func=Attribute,args=[],keywords=[])',
    )),
})


# Round 9 (ruling REHEARSAL-R8-A1, G2; finding grammar_shapes_a1:2106): the
# anchors above are NARROWED by two, never added to: the committing
# refusals of queue_poll (main.py:20059 and :20446, `await db.commit()`
# then `raise HTTPException(503, "queue_contended")`) were conformed to
# `await db.rollback()` (their transactions hold only reads and locks
# since the last commit or rollback, so the end is the same; production
# edits recorded in RF/r9/gr/NOTES-r9-gr.md), and their two
# ('commit', 'end', ...) anchors, whose chains equal the rollback anchors
# at :50176 and :20552, are removed: a commit at a refusal that raises
# now refuses by its anchor.
#
# The POSITION rule (closed_walk.positions, G2 and G3): an anchor binds a
# chain of shapes, not which of several equal chains a node stands at nor
# its place among its siblings, and a constant's shape binds its type,
# not its value. A1_POSITIONS holds, for every span of A1_SPANS, the
# position of every anchored node and every constant: (spelling or method
# or the constant's repr, 'store' | 'end' | 'const', the span's name, the
# path of `<field>[<index>]` places from the span root down to the node).
# GENERATED ONCE from the conformed spans by RF/r9/gr/gen_a1_r9.py (2322
# positions) and frozen; never regenerated. A1_BINDINGS carries the
# marker ('<positions>',) that switches the rule on, and every position.
A1_POSITIONS = frozenset({
    ("'          FROM team_queue q WHERE q.player_id = :pid) AS me_s2  FROM team_series s WHERE s.id = :sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("' ('", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' ('", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' ('", 'const', '_reconcile_team_series_bets', ('body[1]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' ('", 'const', '_return_stake_exactly', ('body[2]', 'body[0]', 'exc', 'args[0]', 'values[4]')),
    ("' ('", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' ('", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[2]')),
    ("' (family resolve, caller='", 'const', '_team_lock_family_pick', ('body[10]', 'body[4]', 'value', 'args[0]', 'values[2]')),
    ("' (lease expired; lobby left untouched)'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[2]', 'value', 'args[0]', 'values[4]')),
    ("' (lobby '", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[2]')),
    ("' (lobby '", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[2]')),
    ("' (lobby '", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[3]', 'value', 'args[0]', 'values[2]')),
    ("' (player '", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' (series '", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[2]')),
    ("' FROM '", 'const', '_latch_sql', ('body[2]', 'value', 'values[4]')),
    ("' WHERE id = :pid FOR UPDATE'", 'const', '_lock_snapshot_rows', ('body[2]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("' WHERE id = CAST(:sid AS uuid) AND hold_room = CAST(:room AS varchar)'", 'const', '_hold_latch', ('body[6]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("' attempts left)'", 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("' attempts'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'orelse[1]', 'value', 'args[0]', 'values[4]')),
    ("' attempts'", 'const', 'ovt_queue_poll', ('body[21]', 'orelse[1]', 'value', 'args[0]', 'values[4]')),
    ("' attempts'", 'const', 'queue_poll', ('body[28]', 'orelse[1]', 'value', 'args[0]', 'values[4]')),
    ("' baseline='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[8]')),
    ("' caller='", 'const', '_team_relock_existing_series', ('body[9]', 'value', 'args[0]', 'values[2]')),
    ("' closed, members freed'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[4]', 'value', 'args[0]', 'values[2]')),
    ("' closed, members freed'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[3]', 'value', 'args[0]', 'values[2]')),
    ("' decider='", 'const', '_ffa_queue_poll_inner', ('body[47]', 'value', 'args[0]', 'values[6]')),
    ("' drifted under the barrier; the next poll re-reads its own predicate'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' elo_range='", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("' error='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'right', 'body', 'values[0]')),
    ("' extra_pick='", 'const', 'ovt_queue_poll', ('body[37]', 'value', 'args[0]', 'values[6]')),
    ("' formation contended out after '", 'const', '_ffa_queue_poll_inner', ('body[33]', 'orelse[1]', 'value', 'args[0]', 'values[2]')),
    ("' formation contended out after '", 'const', 'ovt_queue_poll', ('body[21]', 'orelse[1]', 'value', 'args[0]', 'values[2]')),
    ("' formation contended out after '", 'const', 'queue_poll', ('body[28]', 'orelse[1]', 'value', 'args[0]', 'values[2]')),
    ("' found_others='", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' from lobby '", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[2]', 'value', 'args[0]', 'values[2]')),
    ("' gain='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[22]')),
    ("' gold to player '", 'const', '_return_stake_exactly', ('body[2]', 'body[0]', 'exc', 'args[0]', 'values[2]')),
    ("' is already committed ('", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' is already committed ('", 'const', '_team_resolve_live_family', ('body[7]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' is already committed ('", 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' is already committed ('", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' is already committed ('", 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' is already committed ('", 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' is committed elsewhere ('", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' legacy='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[10]')),
    ("' locking 4-player series with '", 'const', 'team_queue_poll', ('body[36]', 'value', 'args[0]', 'values[2]')),
    ("' matched_with='", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' members='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[28]')),
    ("' my_rating='", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[8]')),
    ("' n='", 'const', '_ffa_queue_poll_inner', ('body[47]', 'value', 'args[0]', 'values[4]')),
    ("' n='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[12]')),
    ("' opp_ready='", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[8]')),
    ("' pair kept changing under lock acquisition; asking for a retry'", 'const', 'queue_poll', ('body[17]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' pair not reciprocal (opp status='", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' pick='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[4]')),
    ("' q                   WHERE q.player_id IN ('", 'const', '_latch_sql', ('body[2]', 'value', 'values[6]')),
    ("' q\\n          JOIN players p ON p.id = q.player_id\\n         WHERE q.player_id = ANY(CAST(:ids AS uuid[]))\\n    '", 'const', '_rules_members', ('body[5]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("' q_size='", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' reason='", 'const', '_team_relock_existing_series', ('body[9]', 'value', 'args[0]', 'values[4]')),
    ("' refunded'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[8]')),
    ("' regret='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[24]')),
    ("' replay room mismatch (ours='", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' room '", 'const', '_ffa_queue_poll_inner', ('body[47]', 'value', 'args[0]', 'values[2]')),
    ("' room '", 'const', 'ovt_queue_poll', ('body[37]', 'value', 'args[0]', 'values[2]')),
    ("' room issue refused: '", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' room stamp not reciprocal \u2014 dissolving own row'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' room='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[2]')),
    ("' s   SET hold_room = CAST(:room AS varchar),       hold_v2 = (SELECT count(*) = '", 'const', '_latch_sql', ('body[2]', 'value', 'values[2]')),
    ("' seat '", 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' settled, '", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("' solo='", 'const', 'ovt_queue_poll', ('body[37]', 'value', 'args[0]', 'values[4]')),
    ("' sum_b='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[14]')),
    ("' sum_pick='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[16]')),
    ("' t2='", 'const', 'team_queue_poll', ('body[40]', 'body[4]', 'value', 'args[0]', 'values[2]')),
    ("' theirs='", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' tie='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[26]')),
    ("' timed out at match_age='", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("' vs opp='", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("' why='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[6]')),
    ("' worst_b='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[18]')),
    ("' worst_pick='", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[20]')),
    ("''", 'const', '_ffa_sort_key', ('body[1]', 'value', 'elts[0]', 'args[0]', 'values[1]')),
    ("''", 'const', '_ffa_sort_key', ('body[1]', 'value', 'elts[1]', 'values[1]')),
    ("''", 'const', '_group_region', ('args', 'kw_defaults[1]')),
    ("''", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'right', 'orelse')),
    ("''", 'const', '_hold_latch', ('body[2]', 'value', 'func', 'value', 'values[1]')),
    ("''", 'const', '_player_body_color', ('body[3]', 'value', 'elts[0]', 'values[0]', 'value', 'values[1]')),
    ("''", 'const', '_player_body_color', ('body[3]', 'value', 'elts[1]', 'values[0]', 'value', 'values[1]')),
    ("''", 'const', '_stamp_team_series_colors', ('body[2]', 'body[4]', 'body[0]', 'value', 'generators[0]', 'ifs[0]', 'left', 'func', 'value', 'values[1]')),
    ("''", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'values[1]', 'values[1]')),
    ("''", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'values[2]', 'values[1]')),
    ("''", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'values[3]', 'values[1]')),
    ("''", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'values[4]', 'values[1]')),
    ("''", 'const', '_team_lock_family_pick', ('args', 'defaults[2]')),
    ("''", 'const', 'team_queue_poll', ('body[27]', 'value', 'keywords[0]', 'value', 'body')),
    ("'(release the gather?, seconds left) for a roster of `seats` seats.\\n\\n    A function rather than a run of locals because the decision is taken\\n    TWICE: once on the discovered roster, and again on the REDISCOVERED one\\n    after a contended attempt. A roster released only because it was FULL\\n    \u2014 the one release that waits for nothing \u2014 and which then shrank under\\n    the identity barrier must not still be released: what the players would\\n    get is a three-seat game the window had not yet opened for, after being\\n    told the lobby was full.\\n\\n    Reads no module state and writes none. The started/last-join stamps\\n    belong to the poll above and to the join endpoint, and a second\\n    evaluation must not restart the window it is evaluating.'", 'const', '_ffa_gather_decide', ('body[0]', 'value')),
    ("')                     AND '", 'const', '_latch_sql', ('body[2]', 'value', 'values[8]')),
    ("') WHERE s.id = CAST(:sid AS uuid)   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)'", 'const', '_latch_sql', ('body[2]', 'value', 'values[10]')),
    ("') was refused: the balance does not cover the stake the wager records, so no gold and no ledger row were written'", 'const', '_return_stake_exactly', ('body[2]', 'body[0]', 'exc', 'args[0]', 'values[6]')),
    ("') \u2014 dissolving own row'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("') \u2014 dissolving own row'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("') \u2014 group '", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[4]')),
    ("') \u2014 healing'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("') \u2014 janitor retries: '", 'const', '_reconcile_team_series_bets', ('body[1]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("') \u2014 resetting own row'", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("')'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[4]')),
    ("')'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]', 'value', 'args[0]', 'values[6]')),
    ("')'", 'const', '_team_lock_family_pick', ('body[10]', 'body[4]', 'value', 'args[0]', 'values[4]')),
    ("')'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[4]')),
    ("')'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[8]')),
    ("')'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[3]', 'value', 'args[0]', 'values[4]')),
    ("')'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("'): '", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("'); deferring'", 'const', '_team_resolve_live_family', ('body[7]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("'); falling through to fresh formation'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("'); rediscovering '", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("'); rediscovering '", 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("'); rediscovering '", 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("'); rediscovering ('", 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ("', '", 'const', '_latch_sql', ('body[0]', 'value', 'func', 'value')),
    ("', age '", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]', 'value', 'args[0]', 'values[2]')),
    ("', age '", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[4]')),
    ("', stamping vanilla: '", 'const', '_stamp_team_series_colors', ('body[2]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("','", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'func', 'value')),
    ("','", 'const', '_rules_json', ('body[4]', 'value', 'keywords[0]', 'value', 'elts[0]')),
    ("','", 'const', '_team_quartet_key', ('body[1]', 'value', 'func', 'value')),
    ("'-'", 'const', '_group_region', ('body[3]', 'body[0]', 'value', 'body')),
    ("'-'", 'const', '_group_region', ('body[5]', 'value', 'values[1]')),
    ("'-attempt budget is spent'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[1]', 'value', 'args[0]', 'values[4]')),
    ("'-attempt budget is spent'", 'const', 'team_queue_poll', ('body[34]', 'orelse[1]', 'value', 'args[0]', 'values[4]')),
    ("'.'", 'const', '_parse_version', ('body[0]', 'body[0]', 'value', 'args[0]', 'generators[0]', 'iter', 'args[0]')),
    ("'.0f'", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[9]', 'format_spec', 'values[0]')),
    ("'/'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("'/'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[5]')),
    ("'/'", 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("'/'", 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[8]')),
    ("'/api/v1/ovt/queue/poll/{steam_id}'", 'const', 'ovt_queue_poll', ('decorator_list[0]', 'args[0]')),
    ("'/api/v1/queue/poll/{steam_id}'", 'const', 'queue_poll', ('decorator_list[0]', 'args[0]')),
    ("'/api/v1/team/queue/poll/{steam_id}'", 'const', 'team_queue_poll', ('decorator_list[0]', 'args[0]')),
    ("'0'", 'const', '_ffa_queue_poll_inner', ('body[38]', 'value', 'values[1]', 'args[0]', 'elt', 'left', 'args[0]', 'func', 'value', 'values[1]')),
    ("'0'", 'const', '_ffa_roster_clears_proximity_floor', ('body[3]', 'value', 'args[0]', 'elt', 'left', 'args[0]', 'func', 'value', 'args[0]', 'values[1]')),
    ("'1v2 Queue'", 'const', 'ovt_queue_poll', ('decorator_list[0]', 'keywords[0]', 'value', 'elts[0]')),
    ("'55P03'", 'const', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'test', 'comparators[0]', 'elts[0]')),
    ("'57014'", 'const', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'test', 'comparators[0]', 'elts[1]')),
    ("': '", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("': '", 'const', '_group_region', ('body[2]', 'handlers[0]', 'body[0]', 'value', 'elts[2]', 'values[0]', 'values[1]')),
    ("': '", 'const', '_region_volumes', ('body[4]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("': '", 'const', '_stamp_team_series_colors', ('body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("': '", 'const', 'ovt_queue_poll', ('body[15]', 'body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("': '", 'const', 'team_queue_poll', ('body[18]', 'body[4]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("': '", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[2]')),
    ("':'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[1]')),
    ("':'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[3]')),
    ("':'", 'const', '_rules_json', ('body[4]', 'value', 'keywords[0]', 'value', 'elts[1]')),
    ("'Acquire for a whole group in ONE deterministic global order.\\n\\n    Ordering is mandatory, not tidiness. Two match formations that overlap on\\n    two players (A and B) and acquire in opposite orders deadlock on the\\n    queue_leases tuples \u2014 and `_lock_queue_rows_ordered` cannot help, because\\n    it orders rows in the mode-specific queue table, a different relation.\\n    Sorting by str(player_id) matches the canonical ordering this codebase\\n    already uses for its other cross-row lock passes (#197/#202).'", 'const', '_lease_acquire_many', ('body[0]', 'value')),
    ("'CAST(:tok AS text) = ANY(string_to_array('", 'const', 'caps_token_sql', ('body[1]', 'value', 'values[0]')),
    ("'Canonical JSON text for a CAST(:rules AS JSONB) bind (#275/#448 \u2014\\n    bind parameters are typed at the SQL side, never inferred).'", 'const', '_rules_json', ('body[0]', 'value')),
    ("'Canonical identity of a four-player group for advisory locking \u2014\\n    sorted str(uuid) join, the same canonical ordering every other lock pass\\n    uses (#197). Value-keyed because the rows being serialized (a same-four\\n    team_series) may not exist yet (#207).'", 'const', '_team_quartet_key', ('body[0]', 'value')),
    ("'Credit one fighter tax as an atomic balance delta plus ledger row.'", 'const', '_credit_bet_fighter_tax', ('body[0]', 'value')),
    ("'DELETE FROM ffa_queue WHERE player_id = :pid'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ffa_queue WHERE player_id = :pid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ffa_queue WHERE player_id = :pid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ffa_queue WHERE player_id = :pid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ffa_queue WHERE series_id = :lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ovt_queue WHERE player_id = :pid'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ovt_queue WHERE player_id = :pid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ovt_queue WHERE series_id = :sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ranked_queue WHERE player_id = :pid'", 'const', 'queue_poll', ('body[23]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ranked_queue WHERE player_id = :pid'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM ranked_queue WHERE player_id = :pid'", 'const', 'queue_poll', ('body[25]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM team_queue WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[17]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM team_queue WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM team_queue WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[23]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'DELETE FROM team_queue WHERE player_id = ANY(:ids)'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[3]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'Deterministic cross-language ordering for steam ids: (length, ordinal)\\n    equals numeric order for canonical non-padded numeric ids, and the C#\\n    reporter implements the identical comparison \u2014 the HMAC canonical and\\n    slot assignment must byte-match without either side parsing int64.'", 'const', '_ffa_sort_key', ('body[0]', 'value')),
    ("'Every hold of a series, with the three stamps the window reads.'", 'const', 'series_holds', ('body[0]', 'value')),
    ("'Member-scoped floor test. None / garbage \u2192 False: the unhandled case\\n    fails toward the DEFAULT rules, never toward revealing a non-default room\\n    to a client that cannot honour it (#276).'", 'const', '_mod_version_at_least', ('body[0]', 'value')),
    ("'Pick the partition (AB-CD / AC-BD / AD-BC) with the smallest |\u0394-Elo|.\\n    `players` is a list of 4 dicts with keys: player_id, balance_rating.\\n    Returns (team1_ids, team2_ids) in original order \u2014 the caller assigns\\n    team_assigned=1/2 by membership.'", 'const', '_balance_teams', ('body[0]', 'value')),
    ("'Player-UUID mirror of SPECTATE_BROADCAST_STEAM_IDS, cached hourly.\\n\\n    Staleness bound, ENFORCED rather than described: a fill is served for at\\n    most _SERVICE_UUID_MAX_AGE_SECONDS. Past that, a failing refresh refuses\\n    with 503 instead of serving the old set. The bound matters because these\\n    UUIDs identify the accounts a ~90-site policy guard REFUSES: if a service\\n    players row is replaced, the cached UUID no longer names that account, and\\n    an unbounded reuse would let every UUID-only guard pass the replacement \u2014\\n    including ones that credit gold. A refusal costs a retry; passing costs a\\n    payment that stands.\\n\\n    A row created after a fill is likewise invisible until the bound expires,\\n    which stays acceptable for the same reason as before: the set is a\\n    hand-edited constant (SHOP_OWNER pattern) and extending it is a deploy,\\n    which restarts the process and empties the cache anyway.\\n    '", 'const', '_service_player_uuids', ('body[0]', 'value')),
    ("'Polled by all 4 participants. Drives the searching \u2192 matched \u2192 ready_join state machine.\\n    At lock time, runs the balancer to assign teams. Identical safety pattern to 1v1:\\n    SELECT FOR UPDATE SKIP LOCKED on the candidate set, atomic update of all 4 rows.\\n\\n    Session-bound, same reasoning as the 1v2 and FFA polls (#233 find 1). This\\n    poll refreshes last_polled for the CLAIMED steam_id, and queue liveness\\n    inferences treat that freshness as evidence a client is alive \u2014 a\\n    destructive input, since the sweeps act on its absence. Unauthenticated,\\n    anyone could forge freshness for a whole locked group of four.\\n\\n    This was the LAST of the three multi-player polls left ungated: ovt and ffa\\n    were session-bound when that lesson was written and team was missed, so the\\n    fix existed beside the hole for a full release. Found by the Aug-7\\n    post-deploy sweep, which flagged it precisely because the sibling routes\\n    disagreed. `request` is now REQUIRED (it was `Request = None`, which would\\n    have made the check silently unenforceable). Enforcement inherits the\\n    steam-auth arming rollout; unarmed accounts remain soft.'", 'const', 'team_queue_poll', ('body[0]', 'value')),
    ("'Queue'", 'const', 'queue_poll', ('decorator_list[0]', 'keywords[1]', 'value', 'elts[0]')),
    ("'Refuse a competitive/economy mutation involving a service account.\\n\\n    Settlement callers pass DB-row-resolved player UUIDs.  Creation funnels\\n    may additionally pass the claimed Steam ids before get-or-create can dirty\\n    a Player row.  Keeping both inputs in one helper makes the DB identity\\n    resolution authoritative while still closing first-write creation holes.\\n    '", 'const', '_assert_no_service_subject', ('body[0]', 'value')),
    ("'SELECT * FROM ffa_queue WHERE steam_id = :sid'", 'const', '_ffa_queue_poll_inner', ('body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT 1 FROM '", 'const', '_lock_snapshot_rows', ('body[2]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'SELECT 1 FROM ffa_queue WHERE player_id = :pid FOR UPDATE'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT 1 FROM ovt_queue WHERE player_id = :pid FOR UPDATE'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT 1 FROM players WHERE id = :pid FOR NO KEY UPDATE'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[5]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT 1 FROM ranked_queue WHERE player_id = :pid FOR UPDATE'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT 1 FROM team_queue WHERE player_id = :pid FOR UPDATE'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT COALESCE(MAX(m.ended_at),                (SELECT l.start_granted_at FROM ffa_lobbies l                  WHERE l.id = :lid))  FROM ffa_matches m WHERE m.lobby_id = :lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT MAX(ended_at) FROM ovt_matches WHERE series_id = :sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT clock_timestamp()'", 'const', '_lease_admission_gate', ('body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT clock_timestamp()'", 'const', '_lease_admission_gate', ('body[6]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT clock_timestamp()'", 'const', '_lease_admission_gate', ('body[7]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT clock_timestamp()'", 'const', '_team_lock_family_pick', ('body[6]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT held_anchor_at, held_until, closed_at FROM match_seat_holds WHERE series_id = CAST(:sid AS uuid)'", 'const', 'series_holds', ('body[1]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT hold_v2 FROM '", 'const', '_hold_latch', ('body[6]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'SELECT id FROM players WHERE id = CAST(:pid AS uuid) FOR NO KEY UPDATE'", 'const', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT id, player_id, amount, odds_multiplier, bet_on_team  FROM team_bets WHERE team_series_id = :sid AND settled_at IS NULL ORDER BY player_id::text, id LIMIT 200'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT id, steam_id FROM players WHERE id = ANY(CAST(:ids AS uuid[]))'", 'const', '_team_resolve_live_family', ('body[5]', 'value', 'generators[0]', 'iter', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT l.*,       GREATEST(0.0, 60.0 - EXTRACT(EPOCH FROM (clock_timestamp() - l.settings_changed_at)))           AS settings_lock_remaining  FROM ffa_lobbies l WHERE l.id = :lid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT l.status, l.games_played, l.player_count, l.member_ids,       l.start_granted_at  FROM ffa_lobbies l WHERE l.id = :lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT mod_version FROM ffa_queue WHERE player_id = ANY(:ids)'", 'const', '_ffa_queue_poll_inner', ('body[35]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT mode, group_id FROM queue_leases WHERE player_id = :pid AND expires_at > clock_timestamp()'", 'const', '_lease_live_claim_strict', ('body[1]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT p.steam_id FROM ffa_lobbies l  JOIN players p ON p.id = ANY(l.member_ids) WHERE l.id = :lid AND p.steam_id <> :me'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))'", 'const', '_team_quartet_lock', ('body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT player_id, pings, measured_at, gen_nonce, gen_seq  FROM player_region_pings WHERE player_id = ANY(:ids)'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT player_id, rating, status, joined_at, wait_since FROM ranked_queue WHERE player_id = :pid'", 'const', 'queue_poll', ('body[28]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT player_id, steam_id, display_name, rating, region, team_assigned\\n               FROM team_queue WHERE series_id = :sid AND player_id != :pid'", 'const', 'team_queue_poll', ('body[66]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT q.*, p.id AS pid FROM ovt_queue q JOIN players p ON p.id = q.player_id WHERE q.steam_id = :sid'", 'const', 'ovt_queue_poll', ('body[8]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT room_name, room_region FROM team_queue WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[13]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT s.hold_v2, s.hold_room,       (SELECT '", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'SELECT s.status, s.created_at, s.solo_id, s.duo_a_id, s.duo_b_id,       (SELECT COUNT(*) FROM ovt_matches m WHERE m.series_id = s.id) AS games  FROM ovt_series s WHERE s.id = :sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT status FROM ovt_lobbies WHERE id = :lid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT status FROM ranked_queue WHERE player_id = :pid'", 'const', 'queue_poll', ('body[28]', 'body[12]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT status FROM team_lobbies WHERE id = :lid'", 'const', 'team_queue_poll', ('body[18]', 'body[1]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT status FROM team_series WHERE id = :sid'", 'const', 'team_queue_poll', ('body[19]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT status, winner_team, invalidated_at, t1a_id, t1b_id, t2a_id, t2b_id FROM team_series WHERE id = :sid FOR NO KEY UPDATE'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT steam_id FROM ovt_queue WHERE series_id = :sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'SELECT team_assigned, matched_at FROM team_queue WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[63]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'Split tax equally, with an odd-gold remainder going to slot A.'", 'const', '_credit_team_bet_fighter_tax', ('body[0]', 'value')),
    ("'Team Queue'", 'const', 'team_queue_poll', ('decorator_list[0]', 'keywords[1]', 'value', 'elts[0]')),
    ("'The X-Mod-Version the version_gate middleware parsed for THIS request\\n    (request.state.mod_version); None when absent.'", 'const', '_request_mod_version', ('body[0]', 'value')),
    ("'The hold time inside [v, now]: for each hold the overlap of\\n    [held_anchor_at, least(closed_at, held_until)) with [v, now].'", 'const', 'held_overlap', ('body[0]', 'value')),
    ("'The map as {code: ms} with every garbage ENTRY dropped (non-str or\\n    empty key, non-int or bool value, value outside 1..5000). Not a dict, or\\n    nothing left after dropping, is absent (None): an empty map carries no\\n    information and cannot prove anything about a seat.'", 'const', '_clean_map', ('body[0]', 'value')),
    ("'UPDATE '", 'const', '_latch_sql', ('body[2]', 'value', 'values[0]')),
    ("'UPDATE ffa_queue SET last_polled = NOW() WHERE player_id = :pid'", 'const', '_ffa_queue_poll_inner', ('body[9]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE ovt_queue SET last_polled = NOW(), mod_version = :mv WHERE player_id = :pid'", 'const', 'ovt_queue_poll', ('body[11]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE players SET gold_earned = COALESCE(gold_earned,0) + :p WHERE id = :pid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE players SET gold_earned = COALESCE(gold_earned,0) + :tax WHERE id = :pid'", 'const', '_credit_bet_fighter_tax', ('body[3]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE players SET gold_spent = COALESCE(gold_spent, 0) - CAST(:amt AS integer) WHERE id = :pid AND COALESCE(gold_spent, 0) >= CAST(:amt AS integer) RETURNING gold_spent'", 'const', '_return_stake_exactly', ('body[1]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE ranked_queue SET last_polled = NOW(), mod_version = :mv WHERE player_id = :pid'", 'const', 'queue_poll', ('body[22]', 'orelse[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE ranked_queue\\n                       SET last_polled = NOW(),\\n                           mod_version = :mv,\\n                           region_pings = CAST(:region_pings AS JSONB),\\n                           region_pings_at = CAST(:region_pings_at AS TIMESTAMPTZ)\\n                     WHERE player_id = :pid'", 'const', 'queue_poll', ('body[22]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_bets SET payout = :p, settled_at = NOW(), settlement_kind = :k WHERE id = :bid AND settled_at IS NULL RETURNING id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_bets SET payout = :p, settled_at = NOW(), settlement_kind = :k, fighter_tax = NULLIF(:tax, 0) WHERE id = :bid AND settled_at IS NULL RETURNING id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_queue SET last_polled = NOW(), mod_version = :mv WHERE player_id = :pid'", 'const', 'team_queue_poll', ('body[16]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_queue\\n                           SET room_name = :rn, room_region = :rr\\n                           WHERE series_id = :sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_series   SET dc_fallback_at = NULL, dc_fallback_player_id = NULL WHERE id = :sid'", 'const', '_team_clear_dc_fallback_marker', ('body[1]', 'body[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_series SET photon_room_id = :rn, region = :rr, room_issued_at = NOW(), rules = CASE WHEN CAST(:has_rules AS BOOLEAN)              THEN CAST(:rules AS JSONB) ELSE rules END WHERE id = :sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'UPDATE team_series SET relocked_at = clock_timestamp() WHERE id = :sid'", 'const', '_team_relock_existing_series', ('body[6]', 'body[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'Use 2v2 rating once a player has either:\\n       - enough completed series (TEAM_TRUST_2V2_RATING_AFTER), OR\\n       - converged RD (rd <= TEAM_TRUST_2V2_RD_BELOW)\\n    Otherwise fall back to their 1v1 rating. RD path catches active players\\n    whose 2v2 rating is meaningful even before they hit the series threshold.'", 'const', '_team_balance_rating', ('body[0]', 'value')),
    ("'[FFA-LOCK] '", 'const', '_ffa_queue_poll_inner', ('body[33]', 'orelse[1]', 'value', 'args[0]', 'values[0]')),
    ("'[FFA-LOCK] dead lock reset (lobby '", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]', 'value', 'args[0]', 'values[0]')),
    ("'[FFA-LOCK] lobby '", 'const', '_ffa_queue_poll_inner', ('body[47]', 'value', 'args[0]', 'values[0]')),
    ("'[FFA-LOCK] seat '", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[FFA-LOCK] sitting over \u2014 lobby '", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[4]', 'value', 'args[0]', 'values[0]')),
    ("'[GROUP-REGION] '", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[0]')),
    ("'[GROUP-REGION] volumes unavailable: '", 'const', '_region_volumes', ('body[4]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] ffa lobby renew failed for '", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] freed '", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[2]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] open 1v2 lobby seat expired for '", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] open 2v2 lobby seat expired for '", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] open-lobby seat expired for '", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] ovt lobby renew failed for '", 'const', 'ovt_queue_poll', ('body[15]', 'body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[LEASE] team lobby renew failed for '", 'const', 'team_queue_poll', ('body[18]', 'body[4]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[OVT-LOCK] '", 'const', 'ovt_queue_poll', ('body[21]', 'orelse[1]', 'value', 'args[0]', 'values[0]')),
    ("'[OVT-LOCK] dead lock '", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[OVT-LOCK] seat '", 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[OVT-LOCK] series '", 'const', 'ovt_queue_poll', ('body[37]', 'value', 'args[0]', 'values[0]')),
    ("'[OVT-LOCK] sitting over \u2014 series '", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-CANCEL] '", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[17]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[QUEUE-POLL] '", 'const', 'queue_poll', ('body[28]', 'orelse[1]', 'value', 'args[0]', 'values[0]')),
    ("'[SERVICE-POLICY] uuid cache could not be filled: '", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[SERVICE-POLICY] uuid cache refresh failed and the previous set is past its age bound: '", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[SERVICE-POLICY] uuid cache refresh failed, keeping the previous set within its age bound: '", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[3]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-BETS] reconcile failed for '", 'const', '_reconcile_team_series_bets', ('body[1]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-BETS] reconcile skipped for '", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-BETS] reconciled series '", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-FAMILY] relock refused: '", 'const', '_team_resolve_live_family', ('body[7]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] '", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[1]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] '", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] '", 'const', 'team_queue_poll', ('body[34]', 'orelse[1]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] caller='", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] caller='", 'const', 'team_queue_poll', ('body[36]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] manual-pick honored: t1='", 'const', 'team_queue_poll', ('body[40]', 'body[4]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] relock onto existing series='", 'const', '_team_relock_existing_series', ('body[9]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] resume unavailable: '", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] seat '", 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE-LOCK] superseded zero-game husk '", 'const', '_team_lock_family_pick', ('body[10]', 'body[4]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE] activation refused for series '", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAM-QUEUE] non-active series '", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAMCOLOR] holder lookup failed for series '", 'const', '_stamp_team_series_colors', ('body[2]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'[TEAMCOLOR] stamp failed for series '", 'const', '_stamp_team_series_colors', ('body[3]', 'handlers[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ("'\\n                    SELECT id::text FROM players\\n                     WHERE steam_id = ANY(CAST(:sids AS text[]))\\n                '", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'body[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                DELETE FROM player_blocks\\n                WHERE (blocker_id, blocked_id) IN (\\n                    SELECT UNNEST(CAST(:b1 AS uuid[])), UNNEST(CAST(:b2 AS uuid[]))\\n                )\\n            '", 'const', 'team_queue_poll', ('body[58]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                SELECT player_id, steam_id, display_name, rating, ready, room_name,\\n                       region, home_region, region_pings, region_pings_at,\\n                       status, matched_with\\n                FROM ranked_queue WHERE player_id = :oid\\n            '", 'const', 'queue_poll', ('body[24]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                SELECT player_id, steam_id, display_name, rating, region, ready, team_assigned\\n                FROM team_queue\\n                WHERE series_id = :sid AND player_id != :pid\\n            '", 'const', 'team_queue_poll', ('body[19]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                SELECT rq.player_id, rq.matched_with\\n                FROM ranked_queue rq\\n                JOIN players p ON rq.player_id = p.id\\n                WHERE p.steam_id = :sid\\n            '", 'const', 'queue_poll', ('body[16]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                SELECT rq.player_id, rq.steam_id, rq.display_name, rq.rating,\\n                       rq.rating_deviation, rq.status, rq.matched_with,\\n                       rq.room_name, rq.room_region, rq.region, rq.home_region,\\n                       rq.ready, rq.joined_at, rq.wait_since, rq.matched_at,\\n                       rq.region_pings, rq.region_pings_at, rq.rules\\n                FROM ranked_queue rq\\n                JOIN players p ON rq.player_id = p.id\\n                WHERE p.steam_id = :sid\\n            '", 'const', 'queue_poll', ('body[16]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n                UPDATE team_series\\n                   SET t1_color_name=:t1n, t1_color_hex=:t1h,\\n                       t2_color_name=:t2n, t2_color_hex=:t2h\\n                 WHERE id = :sid\\n            '", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n              FROM team_queue tq\\n             WHERE tq.player_id = :pid\\n        '", 'const', 'team_queue_poll', ('body[34]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("'\\n            FROM team_queue tq\\n            JOIN players p ON tq.player_id = p.id\\n            WHERE p.steam_id = :sid\\n        '", 'const', 'team_queue_poll', ('body[9]', 'value', 'value', 'args[0]', 'args[0]', 'values[2]')),
    ("'\\n            SELECT '", 'const', 'team_queue_poll', ('body[34]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'\\n            SELECT '", 'const', 'team_queue_poll', ('body[9]', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'\\n            SELECT rq.player_id, rq.matched_with\\n            FROM ranked_queue rq\\n            JOIN players p ON rq.player_id = p.id\\n            WHERE p.steam_id = :sid\\n        '", 'const', 'queue_poll', ('body[7]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n            SELECT rq.player_id, rq.steam_id, rq.display_name, rq.rating,\\n                   rq.rating_deviation, rq.status, rq.matched_with,\\n                   rq.room_name, rq.room_region, rq.region, rq.home_region,\\n                   rq.ready, rq.joined_at, rq.wait_since, rq.matched_at,\\n                   rq.region_pings, rq.region_pings_at, rq.rules\\n            FROM ranked_queue rq\\n            JOIN players p ON rq.player_id = p.id\\n            WHERE p.steam_id = :sid\\n        '", 'const', 'queue_poll', ('body[12]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n        DELETE FROM queue_blocks\\n        WHERE ctid IN (\\n            SELECT ctid FROM queue_blocks\\n            WHERE expires_at < NOW()\\n            FOR UPDATE SKIP LOCKED\\n        )\\n    '", 'const', 'queue_poll', ('body[5]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n        INSERT INTO queue_leases (player_id, mode, group_id, generation,\\n                                  acquired_at, renewed_at, expires_at)\\n        VALUES (:pid, :mode, :gid, :gen, clock_timestamp(), clock_timestamp(),\\n                clock_timestamp() + make_interval(secs => :ttl))\\n        ON CONFLICT (player_id) DO UPDATE\\n           SET mode = EXCLUDED.mode, group_id = EXCLUDED.group_id,\\n               generation = EXCLUDED.generation,\\n               acquired_at = clock_timestamp(),\\n               renewed_at = clock_timestamp(),\\n               -- Recomputed from the CURRENT clock, NOT EXCLUDED.expires_at.\\n               -- The VALUES list is evaluated BEFORE this statement waits on\\n               -- the conflicting lease tuple, while acquired_at/renewed_at\\n               -- above are evaluated after \u2014 so reusing EXCLUDED.expires_at\\n               -- silently shortens the lease by however long the wait was,\\n               -- and once the wait exceeds the TTL it makes\\n               -- expires_at <= renewed_at, which violates the CHECK in\\n               -- migration 174 and aborts the ENTIRE match formation.\\n               expires_at = clock_timestamp() + make_interval(secs => :ttl)\\n    '", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n        SELECT id\\n          FROM match_seat_holds\\n         WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n           AND closed_at IS NULL\\n           AND held_until > CAST(:now AS timestamptz)\\n           AND (bound_at IS NULL OR entered_at IS NOT NULL\\n                OR bound_at + make_interval(secs => CAST(:entry_s AS integer))\\n                    > CAST(:now AS timestamptz))\\n    '", 'const', '_lease_admission_gate', ('body[18]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n        SELECT player_id, mode, group_id\\n          FROM queue_leases\\n         WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n           AND expires_at > CAST(:now AS timestamptz)\\n    '", 'const', '_lease_admission_gate', ('body[12]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ("'\\n        SELECT q.player_id, p.pref_same_cards AS pref, q.mod_version AS mv\\n          FROM '", 'const', '_rules_members', ('body[5]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ("'__cause__'", 'const', '_asm_sqlstate', ('body[3]', 'body[5]', 'value', 'args[0]', 'args[1]')),
    ("'_ffa_gather_started_mono'", 'const', '_ffa_queue_poll_inner', ('body[20]', 'body[0]', 'targets[0]', 'slice')),
    ("'_ffa_gather_started_mono'", 'const', '_ffa_queue_poll_inner', ('body[48]', 'targets[0]', 'slice')),
    ("'a 1v1 match'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[12]', 'body[0]', 'value', 'value', 'args[3]')),
    ("'a 1v2 lobby'", 'const', 'ovt_queue_poll', ('body[38]', 'value', 'value', 'args[3]')),
    ("'a 2v2 match'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[6]', 'body[0]', 'value', 'value', 'args[3]')),
    ("'absent'", 'const', '_pick', ('body[8]', 'body[0]', 'body[0]', 'value')),
    ("'active'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'test', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'test', 'values[2]', 'comparators[0]')),
    ("'active'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'test', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[6]', 'value', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', '_team_series_resumable', ('body[5]', 'test', 'comparators[0]')),
    ("'active'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'test', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', 'ovt_queue_poll', ('body[16]', 'body[6]', 'value', 'values[1]', 'comparators[0]')),
    ("'active'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'test', 'values[2]', 'comparators[0]')),
    ("'active'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[6]', 'value')),
    ("'active'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'test', 'comparators[0]')),
    ("'admission_contended'", 'const', '_ffa_queue_poll_inner', ('body[45]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'body[0]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', '_team_relock_existing_series', ('body[4]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', 'ovt_queue_poll', ('body[35]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', 'queue_poll', ('body[28]', 'body[19]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'admission_contended'", 'const', 'team_queue_poll', ('body[61]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'all4'", 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'amount'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[1]', 'value', 'body', 'args[0]', 'args[0]', 'left', 'slice')),
    ("'amount'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[2]', 'value', 'body', 'args[0]', 'slice')),
    ("'amount'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[0]', 'value', 'slice')),
    ("'amount'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[1]', 'value', 'value', 'args[2]', 'slice')),
    ("'amt'", 'const', '_return_stake_exactly', ('body[1]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'an FFA lobby'", 'const', '_ffa_queue_poll_inner', ('body[49]', 'value', 'value', 'args[3]')),
    ("'assembly_failed'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[0]', 'value', 'body')),
    ("'assembly_failed'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[0]', 'value', 'body')),
    ("'assembly_timeout'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[0]', 'value', 'orelse')),
    ("'assembly_timeout'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[0]', 'value', 'orelse')),
    ("'at'", 'const', '_region_volumes', ('body[3]', 'test', 'values[0]', 'slice')),
    ("'at'", 'const', '_region_volumes', ('body[3]', 'test', 'values[1]', 'left', 'right', 'slice')),
    ("'at'", 'const', '_region_volumes', ('body[4]', 'body[2]', 'targets[0]', 'elts[0]', 'slice')),
    ("'auto'", 'const', 'team_queue_poll', ('body[22]', 'test', 'left', 'func', 'value', 'values[1]')),
    ("'auto'", 'const', 'team_queue_poll', ('body[26]', 'value', 'func', 'value', 'values[1]')),
    ("'auto'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[2]', 'left', 'func', 'value', 'values[1]')),
    ("'b1'", 'const', 'team_queue_poll', ('body[58]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'b2'", 'const', 'team_queue_poll', ('body[58]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'balance_rating'", 'const', '_balance_teams', ('body[4]', 'body[0]', 'value', 'args[0]', 'elt', 'slice')),
    ("'balance_rating'", 'const', '_balance_teams', ('body[4]', 'body[1]', 'value', 'args[0]', 'elt', 'slice')),
    ("'balance_rating'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[1]')),
    ("'balance_rating'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[1]')),
    ("'baseline'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[9]', 'value', 'args[0]', 'args[0]')),
    ("'baseline'", 'const', '_pick', ('body[11]', 'value', 'keys[0]')),
    ("'bet_on_team'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[0]', 'value', 'left', 'slice')),
    ("'bid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'bid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'can_start'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[3]')),
    ("'candidates'", 'const', '_pick', ('body[11]', 'value', 'keys[8]')),
    ("'candidates'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[6]')),
    ("'card_candidates'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[9]')),
    ("'card_candidates'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[9]', 'slice')),
    ("'card_cap'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[11]')),
    ("'card_cap'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[11]', 'slice')),
    ("'closed_at'", 'const', 'held_overlap', ('body[2]', 'body[2]', 'value', 'args[1]')),
    ("'completed'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[0]', 'comparators[0]')),
    ("'completed_series'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[0]', 'args[0]')),
    ("'completed_series'", 'const', 'team_queue_poll', ('body[21]', 'value', 'args[1]', 'slice')),
    ("'completed_series'", 'const', 'team_queue_poll', ('body[34]', 'body[11]', 'value', 'args[1]', 'slice')),
    ("'completed_series'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[1]', 'args[1]', 'slice')),
    ("'cost_b'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[4]', 'value', 'args[0]', 'args[0]')),
    ("'cost_b'", 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'keys[2]')),
    ("'cost_pick'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[6]', 'value', 'args[0]', 'args[0]')),
    ("'cost_pick'", 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'keys[3]')),
    ("'created_at'", 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[1]', 'slice')),
    ("'da'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'db'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'dc_grace_until'", 'const', '_team_series_resumable', ('body[6]', 'body[0]', 'value', 'values[0]', 'left', 'slice')),
    ("'dc_grace_until'", 'const', '_team_series_resumable', ('body[6]', 'body[0]', 'value', 'values[1]', 'left', 'slice')),
    ("'dc_incomplete'", 'const', '_team_series_resumable', ('body[7]', 'test', 'comparators[0]')),
    ("'dc_manual_pending'", 'const', '_team_series_resumable', ('body[7]', 'body[0]', 'value', 'values[0]', 'comparators[0]')),
    ("'dc_paused'", 'const', '_team_series_resumable', ('body[6]', 'test', 'comparators[0]')),
    ("'dead lock reset'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[2]', 'value', 'value', 'args[2]')),
    ("'defer'", 'const', '_team_lock_family_pick', ('body[4]', 'body[1]', 'body[0]', 'value', 'elts[0]')),
    ("'defer'", 'const', '_team_resolve_live_family', ('body[7]', 'body[1]', 'value', 'elts[0]')),
    ("'defer'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'test', 'comparators[0]')),
    ("'defer'", 'const', 'team_queue_poll', ('body[48]', 'test', 'comparators[0]')),
    ("'display_name'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[1]')),
    ("'display_name'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[1]', 'slice')),
    ("'display_name'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'display_name'", 'const', 'queue_poll', ('body[24]', 'body[12]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'display_name'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'display_name'", 'const', 'queue_poll', ('body[28]', 'body[21]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'display_name'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[1]', 'value', 'slice')),
    ("'display_name'", 'const', 'team_queue_poll', ('body[68]', 'value', 'elt', 'keywords[1]', 'value', 'slice')),
    ("'display_name'", 'const', 'team_queue_poll', ('body[69]', 'value', 'elt', 'keywords[1]', 'value', 'slice')),
    ("'duo_a_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[1]', 'body[0]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'slice')),
    ("'duo_b_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[1]', 'body[0]', 'value', 'value', 'keywords[0]', 'value', 'elts[2]', 'slice')),
    ("'entry_s'", 'const', '_lease_admission_gate', ('body[18]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'error'", 'const', '_group_region', ('body[1]', 'value', 'elts[1]')),
    ("'error'", 'const', '_group_region', ('body[2]', 'handlers[0]', 'body[0]', 'value', 'elts[1]')),
    ("'error'", 'const', '_group_region', ('body[2]', 'handlers[0]', 'body[0]', 'value', 'elts[2]', 'keys[0]')),
    ("'error'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'right', 'body', 'values[1]', 'value', 'args[0]')),
    ("'error'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'right', 'test', 'comparators[0]')),
    ("'error'", 'const', 'pick_region_for_group', ('body[1]', 'handlers[0]', 'body[0]', 'value', 'elts[2]', 'keys[0]')),
    ("'expired'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[2]', 'value', 'values[0]')),
    ("'expired'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[2]', 'value', 'values[0]')),
    ("'expired'", 'const', 'queue_poll', ('body[23]', 'body[2]', 'value', 'keywords[0]', 'value')),
    ("'expired'", 'const', 'team_queue_poll', ('body[17]', 'body[2]', 'value', 'keywords[0]', 'value')),
    ("'fallback_rating'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[3]', 'args[0]', 'args[0]', 'values[0]', 'slice')),
    ("'fallback_rating'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[0]', 'args[0]')),
    ("'fallback_rating'", 'const', 'team_queue_poll', ('body[21]', 'value', 'args[2]', 'slice')),
    ("'fallback_rating'", 'const', 'team_queue_poll', ('body[34]', 'body[11]', 'value', 'args[2]', 'slice')),
    ("'fallback_rating'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[1]', 'args[2]', 'slice')),
    ("'family_resolve'", 'const', '_team_resolve_live_family', ('body[8]', 'value', 'value', 'args[5]')),
    ("'ff'", 'const', '_rules_for_queue_match', ('body[4]', 'value', 'keys[0]')),
    ("'ff'", 'const', '_rules_json', ('body[2]', 'value', 'keys[0]')),
    ("'ff'", 'const', '_rules_json', ('body[2]', 'value', 'values[0]', 'slice')),
    ("'ff'", 'const', '_rules_normalize', ('body[3]', 'body[0]', 'iter', 'elts[0]')),
    ("'ffa'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[2]')),
    ("'ffa'", 'const', '_ffa_queue_poll_inner', ('body[3]', 'value', 'value', 'args[2]')),
    ("'ffa'", 'const', '_ffa_queue_poll_inner', ('body[40]', 'value', 'value', 'args[3]')),
    ("'ffa'", 'const', '_ffa_queue_poll_inner', ('body[45]', 'test', 'left', 'value', 'args[2]')),
    ("'ffa_'", 'const', '_ffa_queue_poll_inner', ('body[39]', 'value', 'values[0]')),
    ("'ffa_queue'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[2]', 'value', 'value', 'args[1]')),
    ("'ffa_queue'", 'const', '_ffa_queue_poll_inner', ('body[49]', 'value', 'value', 'args[2]')),
    ("'ffa_queue'", 'const', '_ffa_queue_poll_inner', ('body[4]', 'value', 'value', 'args[1]')),
    ("'ffa_queue'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'orelse[0]', 'test', 'comparators[0]')),
    ("'fresh'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[2]', 'comparators[0]', 'args[0]', 'slice')),
    ("'fresh'", 'const', '_pick', ('body[12]', 'test', 'values[1]', 'values[1]', 'args[0]', 'elt', 'comparators[0]')),
    ("'fresh'", 'const', '_pick', ('body[8]', 'body[3]', 'value')),
    ("'fresh'", 'const', '_team_lock_family_pick', ('body[11]', 'body[0]', 'value', 'elts[0]')),
    ("'fresh'", 'const', '_team_lock_family_pick', ('body[2]', 'body[0]', 'value', 'elts[0]')),
    ("'fresh'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[2]', 'comparators[0]', 'args[0]', 'slice')),
    ("'gain'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[23]', 'value', 'args[0]', 'args[0]')),
    ("'gain'", 'const', '_pick', ('body[11]', 'value', 'keys[6]')),
    ("'gain'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[4]')),
    ("'games'", 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[0]', 'left', 'values[0]', 'slice')),
    ("'games'", 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'left', 'left', 'values[0]', 'slice')),
    ("'games'", 'const', '_team_series_resumable', ('body[1]', 'test', 'values[0]', 'left', 'values[0]', 'slice')),
    ("'games'", 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[2]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'games'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'games'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'test', 'values[1]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'games_played'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[2]', 'test', 'left', 'values[0]', 'slice')),
    ("'games_played'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'games_played'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'test', 'values[1]', 'values[0]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'games_played'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[2]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'gather_seconds_left'", 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'keys[3]')),
    ("'gather_seconds_left'", 'const', '_ffa_queue_poll_inner', ('body[28]', 'body[1]', 'value', 'keys[3]')),
    ("'gather_seconds_left'", 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'keys[3]')),
    ("'gather_seconds_left'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[2]', 'value', 'keys[3]')),
    ("'gen'", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'gen_nonce'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]', 'value', 'body', 'elts[0]', 'slice')),
    ("'gen_nonce'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]', 'value', 'test', 'left', 'slice')),
    ("'gen_seq'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]', 'value', 'body', 'elts[1]', 'slice')),
    ("'get'", 'const', '_get', ('body[0]', 'value', 'test', 'args[1]')),
    ("'gid'", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'gold_earned'", 'const', '_credit_bet_fighter_tax', ('body[4]', 'body[0]', 'value', 'args[1]', 'elts[0]')),
    ("'group_id'", 'const', '_formation_lease_conflict', ('body[3]', 'body[3]', 'value', 'elts[1]', 'slice')),
    ("'group_id'", 'const', '_lease_admission_gate', ('body[14]', 'test', 'args[0]', 'elt', 'left', 'args[1]', 'slice')),
    ("'group_id'", 'const', '_lease_admission_gate', ('body[17]', 'body[0]', 'value', 'args[1]', 'slice')),
    ("'group_id'", 'const', '_lease_admission_gate', ('body[17]', 'body[4]', 'test', 'values[1]', 'left', 'args[1]', 'slice')),
    ("'has_rules'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'held_anchor_at'", 'const', 'held_overlap', ('body[2]', 'body[0]', 'value', 'args[1]')),
    ("'held_lobby'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[7]', 'value', 'values[1]', 'left', 'slice')),
    ("'held_until'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[7]', 'value', 'values[0]', 'left', 'slice')),
    ("'held_until'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[7]', 'value', 'values[2]', 'left', 'slice')),
    ("'held_until'", 'const', 'held_overlap', ('body[2]', 'body[1]', 'value', 'args[1]')),
    ("'hold_room'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[3]', 'value', 'args[0]', 'values[3]', 'left', 'slice')),
    ("'hold_v2'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[3]', 'value', 'args[0]', 'values[1]', 'slice')),
    ("'home'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'keys[1]')),
    ("'home'", 'const', '_pick', ('body[5]', 'body[4]', 'value', 'args[0]')),
    ("'home_region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'args[1]', 'slice')),
    ("'home_region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'args[3]', 'slice')),
    ("'host_player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[6]', 'value', 'args[0]', 'slice')),
    ("'id'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'keys[0]')),
    ("'id'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[0]', 'value', 'args[0]')),
    ("'id'", 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'keys[0]')),
    ("'id'", 'const', '_pick', ('body[5]', 'body[6]', 'value', 'args[0]', 'args[0]', 'args[0]')),
    ("'id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[3]', 'slice')),
    ("'id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[2]', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[10]', 'body[0]', 'test', 'values[1]', 'comparators[0]', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[10]', 'body[0]', 'test', 'values[1]', 'left', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[10]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[10]', 'body[3]', 'value', 'value', 'args[1]', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[10]', 'body[4]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'id'", 'const', '_team_lock_family_pick', ('body[7]', 'body[0]', 'test', 'operand', 'args[1]', 'value', 'args[1]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[11]', 'value', 'keywords[1]', 'value', 'args[0]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[4]', 'test', 'left', 'value', 'args[3]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[5]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[6]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[7]', 'value', 'value', 'args[1]', 'slice')),
    ("'id'", 'const', '_team_relock_existing_series', ('body[9]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'id'", 'const', '_team_resolve_live_family', ('body[6]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'slice')),
    ("'id'", 'const', 'team_queue_poll', ('body[31]', 'body[1]', 'value', 'values[2]', 'slice')),
    ("'id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[4]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[1]', 'slice')),
    ("'ids'", 'const', '_ffa_queue_poll_inner', ('body[35]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', '_rules_members', ('body[5]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', '_team_lock_family_pick', ('body[1]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', '_team_resolve_live_family', ('body[5]', 'value', 'generators[0]', 'iter', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[3]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'ids'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[8]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'initial_picks'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[10]')),
    ("'initial_picks'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[10]', 'slice')),
    ("'invalidated_at'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[2]', 'left', 'slice')),
    ("'invalidation_reason'", 'const', '_team_series_resumable', ('body[7]', 'body[0]', 'value', 'values[0]', 'left', 'slice')),
    ("'is_host'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[2]')),
    ("'is_host'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[4]')),
    ("'is_ranked'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[14]', 'body', 'args[0]', 'slice')),
    ("'is_ranked'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[14]', 'test', 'left', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[0]', 'value', 'func', 'value', 'right', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'test', 'values[1]', 'left', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[0]', 'value', 'args[0]', 'elt', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[0]', 'value', 'args[0]', 'generators[0]', 'ifs[0]', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[5]', 'body', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'joined_at'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[5]', 'test', 'slice')),
    ("'joined_at'", 'const', 'ovt_queue_poll', ('body[14]', 'body[0]', 'value', 'func', 'value', 'right', 'slice')),
    ("'joined_at'", 'const', 'ovt_queue_poll', ('body[14]', 'test', 'values[1]', 'left', 'slice')),
    ("'joined_at'", 'const', 'queue_poll', ('body[19]', 'value', 'args[0]', 'func', 'value', 'right', 'values[1]', 'slice')),
    ("'joined_at'", 'const', 'queue_poll', ('body[28]', 'body[3]', 'value', 'args[0]', 'func', 'value', 'right', 'values[1]', 'slice')),
    ("'joined_at'", 'const', 'team_queue_poll', ('body[14]', 'value', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'k'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'k'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'k'", 'const', '_team_quartet_lock', ('body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'kt'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[5]')),
    ("'lease_expired'", 'const', '_formation_lease_conflict', ('body[3]', 'body[2]', 'body[0]', 'body[0]', 'value', 'elts[1]')),
    ("'lease_held_elsewhere'", 'const', '_formation_lease_conflict', ('body[3]', 'body[5]', 'value', 'elts[1]')),
    ("'lease_lapsed'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[3]', 'value', 'value', 'args[2]')),
    ("'lexical'", 'const', '_baseline', ('body[9]', 'value', 'elts[1]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'lid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'lid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[5]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', 'team_queue_poll', ('body[18]', 'body[1]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lid'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'lid'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'lid'", 'const', 'team_queue_poll', ('body[18]', 'body[6]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'live'", 'const', '_region_candidate_volumes', ('body[1]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'lobby'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[0]')),
    ("'lobby'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'test', 'values[0]', 'comparators[0]')),
    ("'lobby'", 'const', '_rules_normalize', ('body[3]', 'body[1]', 'test', 'comparators[0]', 'elts[0]')),
    ("'lobby'", 'const', 'ovt_queue_poll', ('body[15]', 'body[7]', 'value', 'values[0]')),
    ("'lobby'", 'const', 'ovt_queue_poll', ('body[15]', 'test', 'values[0]', 'comparators[0]')),
    ("'lobby'", 'const', 'team_queue_poll', ('body[18]', 'body[8]', 'value', 'keywords[0]', 'value')),
    ("'lobby'", 'const', 'team_queue_poll', ('body[18]', 'test', 'values[0]', 'comparators[0]')),
    ("'lobby_closed'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[3]', 'value', 'values[0]')),
    ("'lobby_closed'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[4]', 'value', 'values[0]')),
    ("'lobby_closed'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[3]', 'value', 'values[0]')),
    ("'lobby_closed'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[4]', 'value', 'values[0]')),
    ("'lobby_closed'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[4]', 'value', 'keywords[0]', 'value')),
    ("'lobby_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[1]')),
    ("'lobby_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[7]', 'value', 'keys[2]')),
    ("'lobby_ranked'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[14]')),
    ("'lost'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[3]', 'value', 'orelse')),
    ("'manual'", 'const', 'team_queue_poll', ('body[22]', 'test', 'comparators[0]')),
    ("'manual'", 'const', 'team_queue_poll', ('body[27]', 'value', 'keywords[0]', 'value', 'test', 'comparators[0]')),
    ("'manual'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'test', 'comparators[0]')),
    ("'manual'", 'const', 'team_queue_poll', ('body[40]', 'test', 'comparators[0]')),
    ("'manual'", 'const', 'team_queue_poll', ('body[44]', 'value', 'test', 'comparators[0]')),
    ("'manual'", 'const', 'team_queue_poll', ('body[45]', 'value', 'test', 'comparators[0]')),
    ("'manual_pick_enabled'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[5]')),
    ("'manual_pick_enabled'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[5]', 'args[0]', 'args[0]')),
    ("'manual_pick_enabled'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[5]')),
    ("'manual_pick_enabled'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[5]', 'args[0]', 'args[0]')),
    ("'map'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'keys[2]')),
    ("'map'", 'const', '_group_region', ('body[2]', 'body[7]', 'body[0]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'map'", 'const', '_group_region', ('body[2]', 'body[7]', 'body[0]', 'test', 'args[0]', 'slice')),
    ("'map'", 'const', '_pick', ('body[5]', 'body[1]', 'value', 'args[0]', 'args[0]')),
    ("'mat'", 'const', 'queue_poll', ('body[28]', 'body[18]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'mat'", 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'match_report_window as loaded now (a test may load a copy of it).'", 'const', '_mrw_mod', ('body[0]', 'value')),
    ("'matched'", 'const', '_team_relock_existing_series', ('body[11]', 'value', 'keywords[0]', 'value')),
    ("'matched'", 'const', 'ovt_queue_poll', ('body[16]', 'test', 'values[0]', 'comparators[0]', 'elts[1]')),
    ("'matched'", 'const', 'queue_poll', ('body[24]', 'body[12]', 'value', 'keywords[0]', 'value')),
    ("'matched'", 'const', 'queue_poll', ('body[24]', 'test', 'values[0]', 'comparators[0]')),
    ("'matched'", 'const', 'queue_poll', ('body[28]', 'body[21]', 'value', 'keywords[0]', 'value')),
    ("'matched'", 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[0]', 'value')),
    ("'matched'", 'const', 'team_queue_poll', ('body[19]', 'test', 'values[0]', 'comparators[0]', 'elts[0]')),
    ("'matched'", 'const', 'team_queue_poll', ('body[70]', 'value', 'keywords[0]', 'value')),
    ("'matched_at'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[2]', 'value', 'body', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[2]', 'value', 'test', 'left', 'slice')),
    ("'matched_at'", 'const', 'ovt_queue_poll', ('body[16]', 'body[2]', 'value', 'body', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', 'ovt_queue_poll', ('body[16]', 'body[2]', 'value', 'test', 'left', 'slice')),
    ("'matched_at'", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[0]', 'value', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', 'queue_poll', ('body[24]', 'body[8]', 'test', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[0]', 'value', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'test', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[7]', 'value', 'body', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[7]', 'value', 'test', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[5]', 'value', 'body', 'args[0]', 'func', 'value', 'right', 'slice')),
    ("'matched_at'", 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[5]', 'value', 'test', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[10]', 'value', 'value', 'args[2]', 'elts[1]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[16]', 'body[4]', 'value', 'value', 'args[2]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[16]', 'body[5]', 'value', 'value', 'args[2]', 'elts[1]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[16]', 'test', 'values[0]', 'comparators[0]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[16]', 'test', 'values[0]', 'left', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[17]', 'test', 'comparators[0]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[17]', 'test', 'left', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[24]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[24]', 'test', 'values[1]', 'slice')),
    ("'matched_with'", 'const', 'queue_poll', ('body[9]', 'value', 'value', 'args[2]', 'slice')),
    ("'max_players'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[5]')),
    ("'max_regret'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[25]', 'value', 'args[0]', 'args[0]')),
    ("'max_regret'", 'const', '_pick', ('body[11]', 'value', 'keys[7]')),
    ("'max_regret'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[5]')),
    ("'maxp'", 'const', '_ffa_queue_poll_inner', ('body[16]', 'value', 'keys[0]')),
    ("'me'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'me'", 'const', 'team_queue_poll', ('body[31]', 'body[1]', 'value', 'keys[1]')),
    ("'me_s2'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[4]', 'value', 'args[0]', 'values[1]', 'slice')),
    ("'measured'", 'const', '_baseline', ('body[8]', 'body[0]', 'value', 'elts[1]')),
    ("'measured_at'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[1]', 'value', 'elts[1]', 'slice')),
    ("'measured_at'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'keys[3]')),
    ("'measured_at'", 'const', '_pick', ('body[5]', 'body[2]', 'value', 'args[0]')),
    ("'member_banned'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[5]', 'value', 'value', 'args[2]')),
    ("'member_ids'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[1]', 'body[0]', 'value', 'value', 'keywords[0]', 'value', 'args[0]', 'values[0]', 'slice')),
    ("'members'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[16]')),
    ("'members'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'min_players'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[6]')),
    ("'missing_baseline'", 'const', '_pick', ('body[8]', 'body[2]', 'body[0]', 'value')),
    ("'mod_version'", 'const', '_request_mod_version', ('body[1]', 'body[0]', 'value', 'body', 'args[1]')),
    ("'mode must be team or ovt'", 'const', '_mode_or_400', ('body[0]', 'body[0]', 'exc', 'args[1]')),
    ("'mode'", 'const', '_formation_lease_conflict', ('body[3]', 'body[3]', 'value', 'elts[0]', 'slice')),
    ("'mode'", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'mode'", 'const', '_lease_admission_gate', ('body[14]', 'test', 'args[0]', 'elt', 'left', 'args[0]', 'slice')),
    ("'mode'", 'const', '_lease_admission_gate', ('body[17]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'mode'", 'const', '_lease_admission_gate', ('body[17]', 'body[1]', 'test', 'values[1]', 'left', 'slice')),
    ("'mode'", 'const', '_lease_admission_gate', ('body[17]', 'body[4]', 'test', 'values[1]', 'left', 'args[0]', 'slice')),
    ("'mv'", 'const', '_rules_members', ('body[6]', 'body[0]', 'value', 'elts[1]', 'slice')),
    ("'mv'", 'const', 'ovt_queue_poll', ('body[11]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'mv'", 'const', 'queue_poll', ('body[22]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'mv'", 'const', 'queue_poll', ('body[22]', 'orelse[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'mv'", 'const', 'team_queue_poll', ('body[16]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'my_r'", 'const', 'team_queue_poll', ('body[28]', 'value', 'keys[1]')),
    ("'my_r'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[3]', 'comparators[0]', 'args[0]', 'slice')),
    ("'my_rating'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[4]')),
    ("'my_series'", 'const', '_ffa_queue_poll_inner', ('body[11]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'my_series'", 'const', 'ovt_queue_poll', ('body[13]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'my_uncapped'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[3]')),
    ("'n'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'n'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[13]', 'value', 'args[0]', 'args[0]')),
    ("'n'", 'const', '_pick', ('body[11]', 'value', 'keys[1]')),
    ("'not_in_queue'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[5]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[3]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', '_ffa_queue_poll_inner', ('body[5]', 'body[0]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', '_ffa_queue_poll_inner', ('body[7]', 'body[1]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[4]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]', 'body[0]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', 'ovt_queue_poll', ('body[7]', 'body[0]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', 'ovt_queue_poll', ('body[9]', 'body[1]', 'value', 'values[0]')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[14]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[16]', 'body[3]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[16]', 'body[7]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[3]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[25]', 'body[2]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[28]', 'body[1]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'queue_poll', ('body[8]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[11]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[3]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[5]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[7]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[5]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[3]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[4]', 'body[2]', 'value', 'keywords[0]', 'value', 'body')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[23]', 'body[2]', 'value', 'keywords[0]', 'value')),
    ("'not_in_queue'", 'const', 'team_queue_poll', ('body[8]', 'body[0]', 'value', 'keywords[0]', 'value')),
    ("'now'", 'const', '_lease_admission_gate', ('body[12]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'now'", 'const', '_lease_admission_gate', ('body[18]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'odds_multiplier'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[1]', 'value', 'body', 'args[0]', 'args[0]', 'right', 'args[0]', 'slice')),
    ("'odds_multiplier'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[2]', 'value', 'body', 'args[1]', 'slice')),
    ("'oid'", 'const', 'queue_poll', ('body[24]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'open'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ("'open'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'test', 'comparators[0]')),
    ("'open'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'test', 'comparators[0]')),
    ("'opp_id'", 'const', 'queue_poll', ('body[28]', 'body[18]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'orig'", 'const', '_asm_sqlstate', ('body[3]', 'body[4]', 'value', 'args[0]', 'args[1]')),
    ("'ovt'", 'const', '_lease_admission_gate', ('body[17]', 'body[1]', 'test', 'values[1]', 'comparators[0]', 'elts[1]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[15]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[2]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[1]', 'value', 'value', 'args[1]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[28]', 'value', 'value', 'args[3]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[33]', 'value', 'value', 'args[1]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[35]', 'test', 'left', 'value', 'args[2]')),
    ("'ovt'", 'const', 'ovt_queue_poll', ('body[5]', 'value', 'value', 'args[2]')),
    ("'ovt_'", 'const', 'ovt_queue_poll', ('body[27]', 'value', 'values[0]')),
    ("'ovt_queue'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'test', 'comparators[0]')),
    ("'ovt_queue'", 'const', 'ovt_queue_poll', ('body[21]', 'body[8]', 'value', 'value', 'args[1]')),
    ("'ovt_queue'", 'const', 'ovt_queue_poll', ('body[31]', 'value', 'value', 'args[2]')),
    ("'ovt_queue'", 'const', 'ovt_queue_poll', ('body[38]', 'value', 'value', 'args[2]')),
    ("'ovt_queue'", 'const', 'ovt_queue_poll', ('body[6]', 'value', 'value', 'args[1]')),
    ("'p'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'p'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'p'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pgcode'", 'const', '_asm_sqlstate', ('body[3]', 'body[3]', 'iter', 'elts[1]')),
    ("'picked'", 'const', '_team_lock_family_pick', ('body[12]', 'value', 'elts[0]')),
    ("'picked'", 'const', '_team_resolve_live_family', ('body[3]', 'test', 'comparators[0]')),
    ("'pid'", 'const', '_credit_bet_fighter_tax', ('body[3]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'pid'", 'const', '_ffa_queue_poll_inner', ('body[9]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lease_live_claim_strict', ('body[1]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_lock_snapshot_rows', ('body[2]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_player_body_color', ('body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[5]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pid'", 'const', '_return_stake_exactly', ('body[1]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pid'", 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[11]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'pid'", 'const', 'queue_poll', ('body[22]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[22]', 'orelse[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[23]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[25]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[28]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[28]', 'body[12]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'queue_poll', ('body[28]', 'body[18]', 'body[0]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'pid'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[16]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[17]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[13]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[19]', 'body[2]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[23]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[28]', 'value', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[29]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[34]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[63]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pid'", 'const', 'team_queue_poll', ('body[66]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'pids'", 'const', '_lease_admission_gate', ('body[12]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pids'", 'const', '_lease_admission_gate', ('body[15]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pids'", 'const', '_lease_admission_gate', ('body[18]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'pids'", 'const', 'team_queue_poll', ('body[31]', 'body[1]', 'value', 'keys[0]')),
    ("'pings'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[1]', 'value', 'elts[0]', 'slice')),
    ("'player_count'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[4]')),
    ("'player_count'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[4]', 'comparators[0]', 'args[0]', 'values[0]', 'slice')),
    ("'player_count'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[5]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_balance_teams', ('body[6]', 'value', 'elts[0]', 'elt', 'slice')),
    ("'player_id'", 'const', '_balance_teams', ('body[6]', 'value', 'elts[1]', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[4]', 'left', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[2]', 'comparators[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[3]', 'values[0]', 'comparators[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'test', 'values[2]', 'left', 'value', 'args[1]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[1]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[5]', 'body[0]', 'value', 'value', 'args[1]', 'elt', 'elts[1]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[35]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[40]', 'value', 'value', 'keywords[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[42]', 'value', 'value', 'keywords[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'values[4]', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'values[4]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[45]', 'test', 'left', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[49]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[8]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'player_id'", 'const', '_ffa_queue_poll_inner', ('body[9]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', '_group_region', ('body[2]', 'body[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[1]', 'targets[0]', 'slice', 'slice')),
    ("'player_id'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'values[0]', 'args[0]', 'slice')),
    ("'player_id'", 'const', '_lease_admission_gate', ('body[13]', 'value', 'key', 'args[0]', 'slice')),
    ("'player_id'", 'const', '_lease_admission_gate', ('body[17]', 'body[3]', 'value', 'args[0]', 'args[0]', 'slice')),
    ("'player_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[7]', 'value', 'value', 'keywords[0]', 'value', 'left', 'elt', 'slice')),
    ("'player_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'player_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[1]', 'value', 'args[0]', 'keywords[0]', 'value', 'slice')),
    ("'player_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[1]', 'value', 'value', 'args[1]', 'slice')),
    ("'player_id'", 'const', '_rules_members', ('body[6]', 'body[0]', 'targets[0]', 'slice', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[10]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[11]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[12]', 'value', 'value', 'args[1]', 'elt', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[7]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[24]', 'value', 'generators[0]', 'ifs[0]', 'comparators[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[24]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[28]', 'value', 'value', 'keywords[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[30]', 'value', 'value', 'keywords[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[31]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[31]', 'value', 'value', 'keywords[1]', 'value', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[2]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[3]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[34]', 'body[0]', 'value', 'test', 'comparators[0]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[34]', 'body[0]', 'value', 'test', 'left', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'values[4]', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[35]', 'test', 'left', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', 'ovt_queue_poll', ('body[38]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[10]', 'value', 'value', 'args[2]', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[15]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[16]', 'body[5]', 'value', 'value', 'args[2]', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[20]', 'value', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[4]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[4]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[2]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[0]', 'value', 'elts[1]', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]', 'orelse[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]', 'test', 'left', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[6]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]', 'orelse[0]', 'value', 'value', 'args[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'test', 'operand', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[5]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[1]', 'value', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[7]', 'value', 'value', 'args[1]', 'elts[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'left', 'value', 'args[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[11]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[13]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[15]', 'value', 'value', 'args[1]', 'elts[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[18]', 'iter', 'elts[0]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[18]', 'iter', 'elts[1]', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'queue_poll', ('body[28]', 'body[19]', 'test', 'left', 'value', 'args[1]', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[12]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[15]', 'value', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'test', 'left', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]', 'body[0]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[0]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]', 'value', 'value', 'args[1]', 'elt', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[1]', 'value', 'value', 'keywords[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[6]', 'body[0]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[1]', 'body[0]', 'targets[0]', 'slice', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[5]', 'value', 'args[0]', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[9]', 'value', 'value', 'args[1]', 'left', 'elt', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[34]', 'body[12]', 'value', 'value', 'args[1]', 'left', 'elt', 'elts[1]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[34]', 'body[4]', 'value', 'elt', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[0]')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[0]')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'orelse[0]', 'value', 'args[0]', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[41]', 'value', 'key', 'slice')),
    ("'player_id'", 'const', 'team_queue_poll', ('body[46]', 'value', 'value', 'args[2]', 'slice')),
    ("'players_needed'", 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'keys[2]')),
    ("'players_needed'", 'const', '_ffa_queue_poll_inner', ('body[28]', 'body[1]', 'value', 'keys[2]')),
    ("'players_needed'", 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'keys[2]')),
    ("'players_needed'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[2]', 'value', 'keys[2]')),
    ("'poll'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'values[2]')),
    ("'poll'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'values[3]')),
    ("'poll_assembly_failed'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'values[2]', 'body')),
    ("'poll_dead_lock'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'values[2]', 'orelse')),
    ("'pref'", 'const', '_rules_members', ('body[6]', 'body[0]', 'value', 'elts[0]', 'args[0]', 'slice')),
    ("'preferred_side'", 'const', 'ovt_queue_poll', ('body[23]', 'value', 'values[0]', 'args[0]', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[0]', 'value', 'values[0]', 'args[0]')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[1]', 'body[0]', 'value', 'slice')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[6]')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[6]', 'args[0]')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[6]')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[6]', 'args[0]')),
    ("'preferred_team'", 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[0]', 'value', 'slice')),
    ("'previous'", 'const', '_lease_admission_gate', ('body[5]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'proximity_capable'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[6]')),
    ("'q.caps'", 'const', '_latch_sql', ('body[2]', 'value', 'values[9]', 'value', 'args[0]')),
    ("'q.caps'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[1]', 'value', 'args[0]')),
    ("'qt'", 'const', 'team_queue_poll', ('body[28]', 'value', 'keys[3]')),
    ("'queue'", 'const', '_rules_for_queue_match', ('body[4]', 'value', 'values[2]')),
    ("'queue'", 'const', '_rules_normalize', ('body[3]', 'body[1]', 'test', 'comparators[0]', 'elts[1]')),
    ("'queue'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[13]', 'value', 'args[1]')),
    ("'queue'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[13]', 'value', 'args[1]')),
    ("'queue_contended'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'orelse[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'ovt_queue_poll', ('body[21]', 'orelse[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'queue_poll', ('body[17]', 'body[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'queue_poll', ('body[28]', 'body[2]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'queue_poll', ('body[28]', 'orelse[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_contended'", 'const', 'team_queue_poll', ('body[34]', 'orelse[2]', 'exc', 'keywords[1]', 'value')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[2]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[7]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[3]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[4]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[5]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[6]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[3]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[28]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[2]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[5]', 'body[0]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', '_ffa_queue_poll_inner', ('body[7]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[2]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[3]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[4]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[15]', 'body[7]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[4]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]', 'body[0]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[6]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[22]', 'body[2]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[25]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[7]', 'body[0]', 'value', 'keys[1]')),
    ("'queue_count'", 'const', 'ovt_queue_poll', ('body[9]', 'body[1]', 'value', 'keys[1]')),
    ("'queue_type'", 'const', 'team_queue_poll', ('body[22]', 'test', 'left', 'func', 'value', 'values[0]', 'args[0]')),
    ("'queue_type'", 'const', 'team_queue_poll', ('body[26]', 'value', 'func', 'value', 'values[0]', 'args[0]')),
    ("'queue_type'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[2]', 'left', 'func', 'value', 'values[0]', 'slice')),
    ("'range'", 'const', 'team_queue_poll', ('body[28]', 'value', 'keys[2]')),
    ("'ranked'", 'const', '_lease_admission_gate', ('body[8]', 'value', 'test', 'comparators[0]')),
    ("'ranked'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[7]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[0]')),
    ("'ranked'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[7]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'elts[0]')),
    ("'ranked'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'left', 'value', 'args[2]')),
    ("'ranked'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'left', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[0]')),
    ("'ranked'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'left', 'value', 'keywords[0]', 'value', 'elts[1]', 'elts[0]')),
    ("'ranked'", 'const', 'queue_poll', ('body[28]', 'body[19]', 'test', 'left', 'value', 'args[2]')),
    ("'ranked_'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[3]', 'value', 'values[0]')),
    ("'ranked_queue'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'test', 'comparators[0]')),
    ("'ranked_queue'", 'const', 'queue_poll', ('body[10]', 'value', 'value', 'args[1]')),
    ("'ranked_queue'", 'const', 'queue_poll', ('body[16]', 'body[5]', 'value', 'value', 'args[1]')),
    ("'ranked_queue'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[12]', 'body[0]', 'value', 'value', 'args[2]')),
    ("'ranked_queue'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]', 'orelse[0]', 'value', 'value', 'args[2]')),
    ("'ranked_queue'", 'const', 'queue_poll', ('body[28]', 'body[11]', 'value', 'value', 'args[1]')),
    ("'rating'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[2]')),
    ("'rating'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[2]', 'body', 'args[0]', 'args[0]', 'slice')),
    ("'rating'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[4]', 'value', 'slice')),
    ("'rating'", 'const', 'queue_poll', ('body[24]', 'body[12]', 'value', 'keywords[4]', 'value', 'slice')),
    ("'rating'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[4]', 'value', 'slice')),
    ("'rating'", 'const', 'queue_poll', ('body[28]', 'body[21]', 'value', 'keywords[4]', 'value', 'slice')),
    ("'rating'", 'const', 'queue_poll', ('body[28]', 'body[5]', 'value', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[4]', 'value', 'orelse', 'args[0]', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[2]', 'value', 'args[0]', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[21]', 'value', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[28]', 'value', 'values[1]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[34]', 'body[11]', 'value', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[3]', 'left', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]', 'value', 'args[0]', 'values[9]', 'value', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[2]')),
    ("'rating'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[2]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[2]')),
    ("'rating'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[1]', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[2]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[68]', 'value', 'elt', 'keywords[2]', 'value', 'args[0]', 'args[0]', 'slice')),
    ("'rating'", 'const', 'team_queue_poll', ('body[69]', 'value', 'elt', 'keywords[2]', 'value', 'args[0]', 'args[0]', 'slice')),
    ("'rating_1v1'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[3]')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[1]', 'value', 'args[0]', 'values[0]', 'args[0]')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[21]', 'value', 'args[3]', 'slice')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[34]', 'body[11]', 'value', 'args[3]', 'slice')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[3]', 'slice')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[1]', 'args[3]', 'slice')),
    ("'rating_deviation'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[3]', 'slice')),
    ("'raw'", 'const', '_group_region', ('body[7]', 'body[1]', 'targets[0]', 'slice')),
    ("'rd'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[3]')),
    ("'rd'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[3]')),
    ("'ready'", 'const', 'queue_poll', ('body[24]', 'body[5]', 'value', 'slice')),
    ("'ready'", 'const', 'queue_poll', ('body[24]', 'body[6]', 'value', 'slice')),
    ("'ready'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[8]', 'value', 'args[0]', 'values[0]', 'args[0]')),
    ("'ready'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[8]', 'value', 'args[0]', 'slice')),
    ("'ready'", 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[6]', 'value', 'args[0]', 'slice')),
    ("'ready'", 'const', 'team_queue_poll', ('body[19]', 'body[9]', 'value', 'args[0]', 'elt', 'slice')),
    ("'ready'", 'const', 'team_queue_poll', ('body[19]', 'test', 'values[0]', 'comparators[0]', 'elts[1]')),
    ("'ready_join'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'test', 'values[0]', 'comparators[0]')),
    ("'ready_join'", 'const', 'ovt_queue_poll', ('body[16]', 'test', 'values[0]', 'comparators[0]', 'elts[0]')),
    ("'ready_join'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[0]', 'value')),
    ("'ready_join'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[0]', 'value')),
    ("'ready_join'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[0]', 'value')),
    ("'ready_timeout'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[3]', 'value', 'value', 'args[2]')),
    ("'rec_path'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'rec_path'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'rec_trigger'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'rec_trigger'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'refund of '", 'const', '_return_stake_exactly', ('body[2]', 'body[0]', 'exc', 'args[0]', 'values[0]')),
    ("'refunded'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[2]', 'value')),
    ("'refusing rules read for unknown table '", 'const', '_rules_members', ('body[1]', 'body[0]', 'exc', 'args[0]', 'values[0]')),
    ("'refusing to lock unknown parent table '", 'const', '_lock_snapshot_rows', ('body[2]', 'body[0]', 'body[0]', 'exc', 'args[0]', 'values[0]')),
    ("'refusing to lock unknown table '", 'const', '_lock_queue_rows_ordered', ('body[1]', 'body[0]', 'exc', 'args[0]', 'values[0]')),
    ("'refusing to lock unknown table '", 'const', '_lock_snapshot_rows', ('body[1]', 'body[0]', 'exc', 'args[0]', 'values[0]')),
    ("'reg'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'reg'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'reg'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[6]')),
    ("'reg'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'region'", 'const', '_group_region', ('body[2]', 'body[5]', 'body[3]', 'value', 'values[1]', 'slice')),
    ("'region'", 'const', '_region_mode_of', ('body[2]', 'body[0]', 'value', 'body', 'slice')),
    ("'region'", 'const', '_region_mode_of', ('body[2]', 'body[0]', 'value', 'test', 'left')),
    ("'region'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[7]', 'value', 'values[1]', 'slice')),
    ("'region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[3]', 'value', 'values[1]', 'slice')),
    ("'region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'args[0]', 'slice')),
    ("'region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'args[2]', 'slice')),
    ("'region'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'region'", 'const', 'team_queue_poll', ('body[68]', 'value', 'elt', 'keywords[3]', 'value', 'slice')),
    ("'region'", 'const', 'team_queue_poll', ('body[69]', 'value', 'elt', 'keywords[3]', 'value', 'slice')),
    ("'region_pings'", 'const', 'queue_poll', ('body[22]', 'body[1]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'region_pings'", 'const', 'queue_poll', ('body[22]', 'body[3]', 'targets[0]', 'slice')),
    ("'region_pings'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'keywords[0]', 'value', 'slice')),
    ("'region_pings'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'keywords[1]', 'value', 'slice')),
    ("'region_pings_at'", 'const', 'queue_poll', ('body[22]', 'body[1]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'region_pings_at'", 'const', 'queue_poll', ('body[22]', 'body[4]', 'targets[0]', 'slice')),
    ("'region_pings_at'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'keywords[2]', 'value', 'slice')),
    ("'region_pings_at'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]', 'value', 'keywords[3]', 'value', 'slice')),
    ("'released (hosted)'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[1]', 'value', 'body')),
    ("'released (hosted)'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[5]', 'value', 'body')),
    ("'relocked'", 'const', '_team_resolve_live_family', ('body[9]', 'value', 'elts[0]')),
    ("'relocked'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[14]', 'test', 'comparators[0]')),
    ("'relocked'", 'const', 'team_queue_poll', ('body[47]', 'test', 'comparators[0]')),
    ("'reset to searching'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[5]', 'value', 'orelse')),
    ("'reset'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[1]', 'value', 'orelse')),
    ("'rmax'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[2]')),
    ("'rmin'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[1]')),
    ("'rn'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'rn'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'room'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'room'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'room'", 'const', '_hold_latch', ('body[4]', 'value', 'keys[1]')),
    ("'room'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[5]')),
    ("'room'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'room_name'", 'const', 'queue_poll', ('body[24]', 'body[7]', 'value', 'slice')),
    ("'room_name'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ("'room_name'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'test', 'left', 'slice')),
    ("'room_name'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[0]', 'value', 'operand', 'slice')),
    ("'room_name'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[15]', 'value', 'slice')),
    ("'room_name'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[0]', 'value', 'slice')),
    ("'room_name'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'test', 'operand', 'slice')),
    ("'room_region'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[7]', 'value', 'values[0]', 'slice')),
    ("'room_region'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[3]', 'value', 'values[0]', 'slice')),
    ("'room_region'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[16]', 'value', 'slice')),
    ("'room_region'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[1]', 'value', 'slice')),
    ("'rr'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'rr'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'rsn'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'rsn'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'rules'", 'const', '_team_relock_existing_series', ('body[2]', 'value', 'body', 'args[0]', 'slice')),
    ("'rules'", 'const', '_team_relock_existing_series', ('body[2]', 'value', 'test', 'left', 'slice')),
    ("'rules'", 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'rules'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[7]')),
    ("'rules'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[3]', 'value', 'args[0]', 'slice')),
    ("'rules'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'orelse[0]', 'value', 'args[0]', 'slice')),
    ("'rules'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[8]', 'value', 'args[0]', 'slice')),
    ("'rules'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'rules'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'values[3]', 'left', 'slice')),
    ("'rules'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[2]', 'value', 'args[0]', 'slice')),
    ("'rules'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[6]')),
    ("'rules'", 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'s my_ready='", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ("'s, assembly_failed='", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]', 'value', 'args[0]', 'values[4]')),
    ("'s, assembly_failed='", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[6]')),
    ("'s.'", 'const', '_latch_sql', ('body[0]', 'value', 'args[0]', 'elt', 'left')),
    ("'same_card_rule'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[12]')),
    ("'same_card_rule'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[12]', 'slice')),
    ("'sc'", 'const', '_rules_for_queue_match', ('body[4]', 'value', 'keys[1]')),
    ("'sc'", 'const', '_rules_json', ('body[2]', 'value', 'keys[1]')),
    ("'sc'", 'const', '_rules_json', ('body[2]', 'value', 'values[1]', 'slice')),
    ("'sc'", 'const', '_rules_normalize', ('body[3]', 'body[0]', 'iter', 'elts[1]')),
    ("'score_target'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[8]')),
    ("'score_target'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[8]', 'slice')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'test', 'values[0]', 'comparators[0]')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[6]', 'value', 'values[0]')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'values[0]')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[28]', 'body[1]', 'value', 'values[0]')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'values[0]')),
    ("'searching'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[2]', 'value', 'values[0]')),
    ("'searching'", 'const', '_lease_admission_gate', ('body[17]', 'body[2]', 'test', 'comparators[0]')),
    ("'searching'", 'const', 'ovt_queue_poll', ('body[14]', 'test', 'values[0]', 'comparators[0]')),
    ("'searching'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[6]', 'value', 'values[0]')),
    ("'searching'", 'const', 'ovt_queue_poll', ('body[22]', 'body[2]', 'value', 'values[0]')),
    ("'searching'", 'const', 'ovt_queue_poll', ('body[25]', 'body[1]', 'value', 'values[0]')),
    ("'searching'", 'const', 'queue_poll', ('body[23]', 'test', 'values[0]', 'comparators[0]')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[2]', 'body[2]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[3]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[4]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[3]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[3]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[3]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[3]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'queue_poll', ('body[28]', 'body[14]', 'test', 'values[1]', 'comparators[0]')),
    ("'searching'", 'const', 'queue_poll', ('body[28]', 'body[2]', 'test', 'comparators[0]')),
    ("'searching'", 'const', 'queue_poll', ('body[32]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'team_queue_poll', ('body[17]', 'test', 'values[0]', 'comparators[0]')),
    ("'searching'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[5]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[7]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[5]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[3]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'team_queue_poll', ('body[19]', 'body[4]', 'body[2]', 'value', 'keywords[0]', 'value', 'orelse')),
    ("'searching'", 'const', 'team_queue_poll', ('body[25]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[1]', 'comparators[0]')),
    ("'searching'", 'const', 'team_queue_poll', ('body[35]', 'body[4]', 'value', 'keywords[0]', 'value')),
    ("'searching'", 'const', 'team_queue_poll', ('body[48]', 'body[1]', 'value', 'keywords[0]', 'value')),
    ("'seats'", 'const', '_group_region', ('body[4]', 'value', 'values[0]', 'args[0]')),
    ("'seats'", 'const', '_pick', ('body[11]', 'value', 'keys[9]')),
    ("'seats'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[7]')),
    ("'sep'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[11]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[1]', 'args[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[3]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[5]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'test', 'values[1]', 'left', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]', 'test', 'values[2]', 'operand', 'args[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[7]', 'operand', 'args[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[1]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[4]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[2]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[17]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'test', 'values[1]', 'args[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[7]', 'value', 'values[1]', 'comparators[0]', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[2]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'series_id'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'test', 'values[1]', 'left', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[13]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[3]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[3]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[5]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'body[7]', 'value', 'values[2]', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[15]', 'test', 'values[1]', 'left', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[3]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[1]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[13]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]', 'test', 'values[2]', 'operand', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[5]', 'operand', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'ovt_queue_poll', ('body[16]', 'test', 'values[1]', 'left', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[1]', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[1]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[4]', 'body[0]', 'body[0]', 'value', 'value', 'args[3]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[1]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[3]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[6]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'body[8]', 'value', 'keywords[2]', 'value', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[18]', 'test', 'values[1]', 'left', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[1]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[3]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[10]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[11]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'test', 'left', 'value', 'args[3]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[2]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[4]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[5]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]', 'value', 'value', 'keywords[0]', 'value', 'elts[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[1]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[3]', 'value', 'value', 'args[1]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]', 'value', 'value', 'args[1]', 'values[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'values[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[1]', 'value', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[1]', 'value', 'args[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[2]', 'value', 'value', 'args[1]', 'values[0]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'body[4]', 'body[0]', 'value', 'value', 'args[2]', 'slice')),
    ("'series_id'", 'const', 'team_queue_poll', ('body[19]', 'test', 'values[1]', 'slice')),
    ("'service_account_forbidden'", 'const', '_assert_no_service_subject', ('body[2]', 'body[0]', 'exc', 'keywords[1]', 'value')),
    ("'service_account_forbidden'", 'const', '_assert_no_service_subject', ('body[5]', 'body[0]', 'exc', 'keywords[1]', 'value')),
    ("'service_ids'", 'const', '_ffa_queue_poll_inner', ('body[16]', 'value', 'keys[1]')),
    ("'service_ids'", 'const', '_ffa_queue_poll_inner', ('body[18]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'service_ids'", 'const', '_ffa_queue_poll_inner', ('body[19]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'service_ids'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[1]', 'value', 'values[0]', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'service_ids'", 'const', 'ovt_queue_poll', ('body[18]', 'value', 'keys[0]')),
    ("'service_ids'", 'const', 'queue_poll', ('body[28]', 'body[7]', 'value', 'keys[5]')),
    ("'service_ids'", 'const', 'team_queue_poll', ('body[28]', 'value', 'keys[4]')),
    ("'service_policy_unavailable'", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'service_policy_unavailable'", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'body[1]', 'exc', 'keywords[1]', 'value')),
    ("'session_required'", 'const', 'queue_poll', ('body[2]', 'body[0]', 'exc', 'keywords[1]', 'value')),
    ("'set[str]'", 'const', '_service_player_uuids', ('returns',)),
    ("'settings_changed_at'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'test', 'left', 'slice')),
    ("'settings_lock_remaining'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[3]', 'value', 'args[0]', 'args[0]', 'args[0]', 'values[0]', 'slice')),
    ("'settings_lock_seconds'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[15]')),
    ("'sid'", 'const', '_ffa_queue_poll_inner', ('body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_hold_latch', ('body[4]', 'value', 'keys[0]')),
    ("'sid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_clear_dc_fallback_marker', ('body[1]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_lock_family_pick', ('body[10]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_lock_family_pick', ('body[4]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_relock_existing_series', ('body[5]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', '_team_relock_existing_series', ('body[6]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[0]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'ovt_queue_poll', ('body[8]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'queue_poll', ('body[12]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'queue_poll', ('body[16]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'queue_poll', ('body[16]', 'body[6]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'queue_poll', ('body[7]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'series_holds', ('body[1]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[4]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[19]', 'body[2]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[31]', 'body[1]', 'value', 'keys[2]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[66]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sid'", 'const', 'team_queue_poll', ('body[9]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'side'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'sids'", 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'body[0]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'sitting over (all members back at menu)'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[1]', 'value', 'value', 'args[2]')),
    ("'sitting_over'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[1]', 'values[1]')),
    ("'slot'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'solo'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'solo_extra_pick'", 'const', 'ovt_queue_poll', ('body[26]', 'value', 'args[0]', 'elt', 'args[0]', 'slice')),
    ("'solo_id'", 'const', 'ovt_queue_poll', ('body[16]', 'body[1]', 'body[0]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'slice')),
    ("'sqlstate'", 'const', '_asm_sqlstate', ('body[3]', 'body[3]', 'iter', 'elts[0]')),
    ("'src'", 'const', '_rules_for_queue_match', ('body[4]', 'value', 'keys[2]')),
    ("'src'", 'const', '_rules_json', ('body[3]', 'body[0]', 'targets[0]', 'slice')),
    ("'src'", 'const', '_rules_json', ('body[3]', 'body[0]', 'value', 'slice')),
    ("'src'", 'const', '_rules_json', ('body[3]', 'test', 'args[0]')),
    ("'src'", 'const', '_rules_normalize', ('body[3]', 'body[1]', 'body[0]', 'targets[0]', 'slice')),
    ("'src'", 'const', '_rules_normalize', ('body[3]', 'body[1]', 'body[0]', 'value', 'slice')),
    ("'src'", 'const', '_rules_normalize', ('body[3]', 'body[1]', 'test', 'left', 'args[0]')),
    ("'stale'", 'const', '_pick', ('body[8]', 'body[1]', 'body[0]', 'value')),
    ("'start_granted_at'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[3]', 'left', 'slice')),
    ("'start_granted_at'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'test', 'values[1]', 'values[1]', 'left', 'slice')),
    ("'start_granted_at'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[4]', 'left', 'slice')),
    ("'state'", 'const', '_group_region', ('body[5]', 'value', 'values[0]', 'args[0]', 'elt', 'values[2]', 'value', 'args[0]')),
    ("'state'", 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'keys[1]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[2]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[12]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[3]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[4]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'test', 'values[2]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[5]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[6]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[6]', 'value', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[3]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[28]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[2]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[5]', 'body[0]', 'value', 'keys[0]')),
    ("'status'", 'const', '_ffa_queue_poll_inner', ('body[7]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', '_lease_admission_gate', ('body[17]', 'body[2]', 'test', 'left', 'slice')),
    ("'status'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ("'status'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', '_team_series_resumable', ('body[4]', 'value', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[2]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[14]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[3]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[4]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[15]', 'body[7]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[15]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[4]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]', 'body[0]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[6]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[6]', 'value', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'test', 'values[2]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[16]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[22]', 'body[2]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[25]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[7]', 'body[0]', 'value', 'keys[0]')),
    ("'status'", 'const', 'ovt_queue_poll', ('body[9]', 'body[1]', 'value', 'keys[0]')),
    ("'status'", 'const', 'queue_poll', ('body[23]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'queue_poll', ('body[24]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'status'", 'const', 'queue_poll', ('body[24]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'queue_poll', ('body[28]', 'body[14]', 'test', 'values[1]', 'left', 'slice')),
    ("'status'", 'const', 'queue_poll', ('body[28]', 'body[2]', 'test', 'left', 'slice')),
    ("'status'", 'const', 'team_queue_poll', ('body[17]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'team_queue_poll', ('body[18]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'team_queue_poll', ('body[19]', 'test', 'values[0]', 'left', 'slice')),
    ("'status'", 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[1]', 'left', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[0]')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[0]', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[30]', 'value', 'args[0]', 'elt', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[0]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[5]', 'body[0]', 'value', 'value', 'args[1]', 'elt', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[5]', 'test', 'values[2]', 'comparators[0]', 'args[0]', 'elt', 'slice')),
    ("'steam_id'", 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[7]', 'value', 'keywords[0]', 'value', 'body', 'args[0]', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[12]', 'value', 'value', 'args[1]', 'elt', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[3]', 'value', 'elt', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[3]', 'value', 'generators[0]', 'ifs[0]', 'func', 'value', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[4]', 'value', 'orelse', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[21]', 'body[6]', 'value', 'value', 'args[1]', 'elt', 'slice')),
    ("'steam_id'", 'const', 'ovt_queue_poll', ('body[37]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[10]', 'value', 'orelse', 'body', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[2]', 'value', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[9]', 'value', 'orelse', 'orelse', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[12]', 'value', 'keywords[2]', 'value', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[10]', 'value', 'body', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[2]', 'value', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[9]', 'value', 'orelse', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[0]', 'value', 'elts[1]', 'elts[1]', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[7]', 'value', 'value', 'args[1]', 'elts[1]', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[28]', 'body[10]', 'value', 'value', 'args[1]', 'elts[1]', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[28]', 'body[15]', 'value', 'value', 'args[1]', 'elts[1]', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'queue_poll', ('body[28]', 'body[21]', 'value', 'keywords[2]', 'value', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[0]', 'value', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]', 'body[0]', 'test', 'left', 'value', 'args[1]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]', 'value', 'value', 'args[1]', 'elt', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[3]', 'value', 'value', 'args[1]', 'left', 'elt', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[9]', 'value', 'value', 'args[1]', 'left', 'elt', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[34]', 'body[12]', 'value', 'value', 'args[1]', 'left', 'elt', 'elts[0]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[34]', 'body[3]', 'value', 'value', 'args[1]', 'left', 'elt', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[36]', 'value', 'args[0]', 'values[3]', 'value', 'elt', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'keys[4]')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[37]', 'value', 'elts[0]', 'values[4]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'keys[4]')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[38]', 'body[0]', 'value', 'args[0]', 'values[4]', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[41]', 'value', 'value', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[68]', 'value', 'elt', 'keywords[0]', 'value', 'slice')),
    ("'steam_id'", 'const', 'team_queue_poll', ('body[69]', 'value', 'elt', 'keywords[0]', 'value', 'slice')),
    ("'sudden_death'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'keys[13]')),
    ("'sudden_death'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[13]', 'slice')),
    ("'sum_b'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[15]', 'value', 'args[0]', 'args[0]')),
    ("'sum_b'", 'const', '_pick', ('body[11]', 'value', 'keys[2]')),
    ("'sum_b'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[0]')),
    ("'sum_pick'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[17]', 'value', 'args[0]', 'args[0]')),
    ("'sum_pick'", 'const', '_pick', ('body[11]', 'value', 'keys[3]')),
    ("'sum_pick'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[1]')),
    ("'superseded_requeue'", 'const', '_team_lock_family_pick', ('body[10]', 'body[3]', 'value', 'value', 'args[2]')),
    ("'t'", 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'t1'", 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'t1_series_wins'", 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[1]', 'left', 'values[0]', 'slice')),
    ("'t1_series_wins'", 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'left', 'right', 'values[0]', 'slice')),
    ("'t1_series_wins'", 'const', '_team_series_resumable', ('body[1]', 'test', 'values[1]', 'left', 'values[0]', 'slice')),
    ("'t1a'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'t1a_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'body', 'elts[0]', 'slice')),
    ("'t1a_id'", 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[0]', 'value', 'elts[0]', 'slice')),
    ("'t1a_id'", 'const', '_team_relock_existing_series', ('body[1]', 'value', 'elts[0]', 'slice')),
    ("'t1a_id'", 'const', 'team_queue_poll', ('body[31]', 'body[0]', 'value', 'elts[0]', 'slice')),
    ("'t1b'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'t1b_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'body', 'elts[1]', 'slice')),
    ("'t1b_id'", 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[0]', 'value', 'elts[1]', 'slice')),
    ("'t1b_id'", 'const', '_team_relock_existing_series', ('body[1]', 'value', 'elts[1]', 'slice')),
    ("'t1b_id'", 'const', 'team_queue_poll', ('body[31]', 'body[0]', 'value', 'elts[1]', 'slice')),
    ("'t1h'", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'t1n'", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[1]')),
    ("'t2_series_wins'", 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[2]', 'left', 'values[0]', 'slice')),
    ("'t2_series_wins'", 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'right', 'values[0]', 'slice')),
    ("'t2_series_wins'", 'const', '_team_series_resumable', ('body[1]', 'test', 'values[2]', 'left', 'values[0]', 'slice')),
    ("'t2a'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'t2a_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'orelse', 'body', 'elts[0]', 'slice')),
    ("'t2a_id'", 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[1]', 'value', 'elts[0]', 'slice')),
    ("'t2a_id'", 'const', 'team_queue_poll', ('body[31]', 'body[0]', 'value', 'elts[2]', 'slice')),
    ("'t2b'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'t2b_id'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'orelse', 'body', 'elts[1]', 'slice')),
    ("'t2b_id'", 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[1]', 'value', 'elts[1]', 'slice')),
    ("'t2b_id'", 'const', 'team_queue_poll', ('body[31]', 'body[0]', 'value', 'elts[3]', 'slice')),
    ("'t2h'", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'t2n'", 'const', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]', 'value', 'value', 'args[1]', 'keys[3]')),
    ("'tax'", 'const', '_credit_bet_fighter_tax', ('body[3]', 'value', 'value', 'args[1]', 'keys[0]')),
    ("'tax'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'team'", 'const', '_lease_admission_gate', ('body[17]', 'body[1]', 'test', 'values[1]', 'comparators[0]', 'elts[0]')),
    ("'team'", 'const', '_team_relock_existing_series', ('body[4]', 'test', 'left', 'value', 'args[2]')),
    ("'team'", 'const', '_team_resolve_live_family', ('body[6]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]')),
    ("'team'", 'const', 'team_queue_poll', ('body[18]', 'body[4]', 'body[0]', 'body[0]', 'value', 'value', 'args[2]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[1]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[10]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'test', 'left', 'value', 'args[2]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[2]', 'body[0]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[1]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[6]', 'value', 'value', 'args[3]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[1]', 'body[0]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[19]', 'body[4]', 'body[0]', 'value', 'value', 'args[1]')),
    ("'team'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[9]', 'value', 'value', 'keywords[0]', 'value', 'elt', 'elts[0]')),
    ("'team'", 'const', 'team_queue_poll', ('body[61]', 'test', 'left', 'value', 'args[2]')),
    ("'team'", 'const', 'team_queue_poll', ('body[6]', 'value', 'value', 'args[2]')),
    ("'team_'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[5]', 'value', 'values[0]')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[4]', 'value', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[19]', 'body[5]', 'value', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[19]', 'body[6]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[19]', 'body[7]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[65]', 'value', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[68]', 'value', 'elt', 'keywords[4]', 'value', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[68]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[69]', 'value', 'elt', 'keywords[4]', 'value', 'slice')),
    ("'team_assigned'", 'const', 'team_queue_poll', ('body[69]', 'value', 'generators[0]', 'ifs[0]', 'left', 'slice')),
    ("'team_bet_payout'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[1]', 'value', 'args[0]', 'keywords[2]', 'value')),
    ("'team_bet_refund'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[1]', 'value', 'value', 'keywords[0]', 'value')),
    ("'team_bet_tax'", 'const', '_credit_team_bet_fighter_tax', ('body[5]', 'value', 'value', 'args[3]')),
    ("'team_bet_tax'", 'const', '_credit_team_bet_fighter_tax', ('body[6]', 'value', 'value', 'args[3]')),
    ("'team_queue'", 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'test', 'comparators[0]')),
    ("'team_queue'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[6]', 'body[0]', 'value', 'value', 'args[2]')),
    ("'team_queue'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[4]', 'value', 'value', 'args[1]')),
    ("'team_queue'", 'const', 'team_queue_poll', ('body[34]', 'body[5]', 'value', 'value', 'args[1]')),
    ("'team_queue'", 'const', 'team_queue_poll', ('body[51]', 'value', 'value', 'args[2]')),
    ("'team_queue'", 'const', 'team_queue_poll', ('body[7]', 'value', 'value', 'args[1]')),
    ("'team_series'", 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[4]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[0]')),
    ("'tie'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[27]', 'value', 'args[0]', 'args[0]')),
    ("'tie'", 'const', '_pick', ('body[11]', 'value', 'keys[10]')),
    ("'tok'", 'const', '_hold_latch', ('body[4]', 'value', 'keys[2]')),
    ("'tok'", 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keys[2]')),
    ("'total'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[1]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'total'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[2]', 'left', 'args[0]', 'slice')),
    ("'total'", 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[4]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'total'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[1]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'total'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[2]', 'left', 'args[0]', 'slice')),
    ("'total'", 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[3]', 'left', 'args[0]', 'values[0]', 'slice')),
    ("'ttl'", 'const', '_lease_acquire', ('body[3]', 'value', 'value', 'args[1]', 'keys[4]')),
    ("'us'", 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'values[2]', 'value', 'values[1]')),
    ("'us'", 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'values[3]', 'value', 'values[1]')),
    ("'us'", 'const', '_group_region', ('body[8]', 'value', 'values[2]')),
    ("'us'", 'const', '_region_mode_of', ('args', 'defaults[0]')),
    ("'us'", 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[6]', 'value', 'values[1]')),
    ("'us'", 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'values[3]', 'value', 'values[1]')),
    ("'us'", 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[7]', 'value', 'values[2]')),
    ("'us'", 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[3]', 'value', 'values[2]')),
    ("'vV'", 'const', '_ffa_queue_poll_inner', ('body[38]', 'value', 'values[1]', 'args[0]', 'elt', 'left', 'args[0]', 'args[0]')),
    ("'vV'", 'const', '_ffa_roster_clears_proximity_floor', ('body[3]', 'value', 'args[0]', 'elt', 'left', 'args[0]', 'args[0]')),
    ("'value'", 'const', '_lease_admission_gate', ('body[5]', 'body[0]', 'value', 'slice')),
    ("'volumes'", 'const', '_region_volumes', ('body[3]', 'body[0]', 'value', 'slice')),
    ("'volumes'", 'const', '_region_volumes', ('body[4]', 'body[2]', 'targets[0]', 'elts[1]', 'slice')),
    ("'volumes'", 'const', '_region_volumes', ('body[5]', 'value', 'slice')),
    ("'wab'", 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'keys[5]')),
    ("'wait_seconds'", 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'keys[5]')),
    ("'wait_since'", 'const', 'queue_poll', ('body[19]', 'value', 'args[0]', 'func', 'value', 'right', 'values[0]', 'slice')),
    ("'wait_since'", 'const', 'queue_poll', ('body[28]', 'body[3]', 'value', 'args[0]', 'func', 'value', 'right', 'values[0]', 'slice')),
    ("'why'", 'const', '_group_region', ('body[7]', 'body[0]', 'targets[0]', 'slice')),
    ("'winner_team'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'body', 'slice')),
    ("'winner_team'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[1]', 'left', 'slice')),
    ("'won'", 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[3]', 'value', 'body')),
    ("'worst_b'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[19]', 'value', 'args[0]', 'args[0]')),
    ("'worst_b'", 'const', '_pick', ('body[11]', 'value', 'keys[4]')),
    ("'worst_b'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[2]')),
    ("'worst_pick'", 'const', '_group_region', ('body[6]', 'value', 'args[0]', 'left', 'values[21]', 'value', 'args[0]', 'args[0]')),
    ("'worst_pick'", 'const', '_pick', ('body[11]', 'value', 'keys[5]')),
    ("'worst_pick'", 'const', '_pick', ('body[24]', 'value', 'args[0]', 'keys[3]')),
    ("'x-region-pings'", 'const', 'queue_poll', ('body[4]', 'value', 'args[0]', 'args[0]')),
    ("'{ff, sc} from a JSONB value / dict / JSON text / None. Missing or\\n    malformed keys fall to the defaults \u2014 the conservative direction for both\\n    (FF ON is vanilla; SC OFF is a private roll).'", 'const', '_rules_normalize', ('body[0]', 'value')),
    ('" WHERE id=:lid AND status=\'active\'"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]', 'right')),
    ('" WHERE id=:lid AND status=\'active\'"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]', 'right')),
    ('" formation contended out; the poll\'s "', 'const', 'team_queue_poll', ('body[34]', 'orelse[1]', 'value', 'args[0]', 'values[2]')),
    ('" resume contended out; the poll\'s "', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[1]', 'value', 'args[0]', 'values[2]')),
    ('"(name, hex) of the player\'s equipped body colour, or (None, None).\\n    kind=\'player_color\' \u2014 NOT kind=\'color\', which is the map-colour system."', 'const', '_player_body_color', ('body[0]', 'value')),
    ('"): status \'"', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[4]')),
    ('", \',\'))"', 'const', 'caps_token_sql', ('body[1]', 'value', 'values[2]')),
    ('"A seat\'s measured home: the lowest-ping code of its own map after\\n    cleaning (ties lexical), or None without a usable map. The data path\\n    (main._group_region) prefers this to the queue row\'s join-time\\n    connection region, which after a room in another region is THAT room\'s\\n    region, not where the player is (c2 H3)."', 'const', 'home_of', ('body[0]', 'value')),
    ('"All (name, hex) body colours held by a team\'s members, in member\\n    order. Empty list = nobody holds one = vanilla team."', 'const', '_team_color_holders', ('body[0]', 'value')),
    ('"Bug 245: re-lock four queued players onto an EXISTING live series\\n    instead of minting a duplicate. Shared by the sticky DC-resume path and\\n    the same-four dedupe backstop in the 2v2 queue matcher.\\n\\n    Contract: the CALLER holds FOR UPDATE (obtained via SKIP LOCKED) on the\\n    series row `srow` and has verified all four members are present + fresh\\n    in team_queue (searching, or already bound to THIS series), eligible per\\n    _team_series_resumable, and not service subjects. Team assignment keeps\\n    the series\' ORIGINAL partition \u2014 scores only make sense under it, and\\n    the balancer-time slot order stays canonical for HMAC matching.\\n\\n    Review r1 findings, each load-bearing:\\n      * live_t1/t2_points are PRESERVED (finding 1): they are the bet\\n        cutoff\'s monotonic latch \u2014 resetting them reopened a betting window\\n        that game 1\'s progress had already closed. The next game\'s live\\n        POSTs overwrite them.\\n      * photon_room_id / room_issued_at are CLEARED (finding 3): the old\\n        room is dead, and a deferred DC report naming it must not match the\\n        resumed series (report-dc ignores a room-carrying report against a\\n        room-less row). Re-issuance stores the new room before play.\\n      * spawn_confirmations / spawn_confirmed_by RESET (finding 6): stale\\n        4/4 evidence from the dead room disabled the 180s assembly cancel\\n        and the stale-series janitor for the new room.\\n    The dc_manual_pending flag clears because play resumed \u2014 nothing is\\n    pending an admin call any more."', 'const', '_team_relock_existing_series', ('body[0]', 'value')),
    ('"Clear the deferral marker on a series an adoption funnel just revived.\\n\\n    THE OPERATION, NOT THE LINE (#432, #330). Every funnel that flips a\\n    team_series row back to \'active\' and clears dc_player_id has to call this: a\\n    marker that survives a resume comes due like any other: on the first\\n    tick after it passes the bound, the sweep settles the FRESHLY RESUMED\\n    series to dc_incomplete and attributes it to the previous sitting\'s\\n    disconnect.\\n\\n    THE CLEAR IS UNCONDITIONAL, AND THE MARKER\'S AGE IS NOT SOMETHING ANY\\n    CALLER MAY REASON FROM. A revival says nothing about how old the marker\\n    is. A settlement inside the bound followed by an immediate revival leaves\\n    a marker YOUNGER than the bound; a post-bound sweep followed by a later\\n    revival leaves one OLDER. This comment and the header of migration 356\\n    each used to assert one of those as if it were the only case, in opposite\\n    directions, and neither followed from the revival. Both cases need the\\n    same clear, so the clear is age-independent. WHAT THIS CALL GUARANTEES,\\n    precisely, because a guarantee in a comment is a claim about the whole\\n    state space (#351): it ATTEMPTS the clear inside its own savepoint and\\n    swallows every exception the attempt raises. On a clean return the row\\n    carries no marker ONLY when that UPDATE actually ran; a swallowed database\\n    error -- the pre-356 missing column, a lock timeout, a connection the\\n    driver has already given up on -- leaves the revived row still carrying\\n    its marker, and a later tick past the bound can settle a series that has\\n    resumed. That is a recorded residual of this design and not a case a\\n    caller may reason away. That is also why the clear belongs\\n    in the funnel and not in a freshness test in the sweep -- a freshness test\\n    would have to pick one of those two cases to be right about.\\n\\n    There are exactly two such funnels, the queue/sticky resume\\n    (_team_relock_existing_series) and the hosted-lobby Start adoption\\n    (team_lobby_start), and the first cut of this change cleared the marker in\\n    only one of them. test_sept16_dc_fallback_shape.py counts the revival\\n    OPERATION across the WHOLE file -- matched on the columns the operation\\n    writes, insensitive to how the SQL is spaced -- and requires this call\\n    inside every function that performs one, so a third funnel cannot be added\\n    without either calling it or reddening.\\n\\n    Its own savepoint rather than a clause in the callers\' own UPDATE (#235):\\n    pre-migration-356 the columns do not exist and a caught SQL error poisons\\n    the whole enclosing transaction under asyncpg -- neither resume may start\\n    failing because a deploy ran out of order. Skipping it then is harmless,\\n    because with no column there are no markers.\\n    "', 'const', '_team_clear_dc_fallback_marker', ('body[0]', 'value')),
    ('"Compute + persist both teams\' colour identity on a just-created\\n    team_series row. Best-effort: a cosmetic lookup failure must never take\\n    a lock/Start/continuation down with it."', 'const', '_stamp_team_series_colors', ('body[0]', 'value')),
    ('"Core of the same-four family resolution (r1 finding 5; r2 HIGH 2/3\\n    made it a SHARED primitive \u2014 the queue matcher, the hosted-lobby Start\\n    and the continuation endpoint are all same-four creation funnels and\\n    each must resolve the WHOLE family, never a newest-row probe).\\n\\n    CONTRACT: the caller already holds _team_quartet_lock for these four.\\n    Enumerates every live same-four row, locks each (SKIP LOCKED),\\n    supersedes zero-game husks (cancel + bet reconcile), and picks the\\n    authoritative resumable row per _team_series_resumable.\\n\\n    Returns (\'picked\', row) with the authoritative row LOCKED; (\'fresh\',\\n    None) when nothing is resumable and an insert may proceed; (\'defer\',\\n    None) when a family row is visible but locked elsewhere (admin resolve,\\n    DC report, janitor) \u2014 never mint a duplicate while the authoritative\\n    row is in motion.\\n\\n    Partition intent (r1 finding 11): when req_t1/req_t2 are given, a\\n    played series whose stored split differs from the REQUESTED split (side\\n    swap tolerated) is not resumable \u2014 a deliberate re-split starts a fresh\\n    series; the old row is left for the janitor/admin rather than cancelled\\n    (it has real results and bets). Zero-game husks are superseded\\n    regardless of partition."', 'const', '_team_lock_family_pick', ('body[0]', 'value')),
    ('"DELETE FROM ovt_queue WHERE player_id = :pid AND status = \'lobby\'"', 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE mode = \'ffa\' AND group_id = :lid"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE player_id = :pid   AND mode = \'ffa\' AND group_id = :lid"', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE player_id = :pid   AND mode = \'ovt\' AND group_id = :lid"', 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE player_id = :pid   AND mode = \'ovt\' AND group_id = :lid"', 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE player_id = :pid   AND mode = \'team\' AND group_id = :lid"', 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM queue_leases WHERE player_id = :pid   AND mode = \'team\' AND group_id = :lid"', 'const', 'team_queue_poll', ('body[18]', 'body[5]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"DELETE FROM team_queue WHERE player_id = :pid AND status = \'lobby\'"', 'const', 'team_queue_poll', ('body[18]', 'body[2]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"Grant (or supersede) this player\'s single queue commitment.\\n\\n    Always overwrites: acquiring a new commitment necessarily ends the old one,\\n    and a fresh `generation` means any heartbeat still in flight for the\\n    previous commitment can no longer renew it. Callers must run this in the\\n    SAME transaction as the status write that locks the row, so a rolled-back\\n    lock cannot leave a lease behind."', 'const', '_lease_acquire', ('body[0]', 'value')),
    ('"Latch the hold flag of one room issue, inside the caller\'s transaction\\n    (the statement that issues the room; NX1 calls it at every issue site).\\n\\n    hold_room becomes `room`; hold_v2 becomes TRUE only when EVERY member of\\n    the series has a queue row of this mode carrying HOLD_CAPS_TOKEN (a\\n    missing row or token gives FALSE, the direction of today). A flag already\\n    written for this room never changes: the UPDATE matches only a row whose\\n    hold_room differs, so a second call for the same room is inert and a\\n    relock to a new room re-judges. Returns the flag the row holds for `room`\\n    afterwards (FALSE for an empty room, which latches nothing)."', 'const', '_hold_latch', ('body[0]', 'value')),
    ('"Lock an already-DISCOVERED snapshot: named parents, then named queue rows.\\n\\n    The counterpart to _lock_queue_group_for_player for callers that have\\n    already crossed the identity barrier. It differs in the three ways that\\n    matter, and each difference is load-bearing:\\n\\n      * NO COMMIT. The group helper commits when the row is missing and when\\n        its membership re-check fails. Committing here would release every\\n        transaction-scoped advisory lock the caller took in phase 3 and hand\\n        the formation straight back to the race it just closed.\\n      * NO RETRY. Drift is the CALLER\'s to handle, because only the caller can\\n        roll back and rediscover -- and rediscovery may turn up an identity we\\n        do not yet hold, which must never be acquired while rows are held.\\n      * NO DISCOVERY. Parents and rows are passed in. An open-ended scan after\\n        the barrier can select a player outside the gated set, which is exactly\\n        the hole the barrier exists to close.\\n\\n    Parent rows come first (series/lobby before queue), matching match\\n    completion, which already locks the series before touching its queue rows.\\n    Both passes are deterministically ordered so two callers holding different\\n    identity subsets still agree on row order.\\n    "', 'const', '_lock_snapshot_rows', ('body[0]', 'value')),
    ('"ONE resume-eligibility predicate for every path (r1 finding 8 \u2014 the\\n    dedupe backstop bypassing the sticky path\'s age/reason/grace rules is\\n    how a two-hour-old husk got reactivated with a stale score). `row` must\\n    carry status, dc_grace_until, invalidation_reason, created_at,\\n    room_issued_at, last_game_at (newest valid team_matches.ended_at, may\\n    be None), games, t1/t2_series_wins.\\n\\n    Stage 2 (V3 S5, RJS-H6, RJS-M7): `holds` are the series\' holds and\\n    `now` is REQUIRED, the DB clock the caller read once in its\\n    transaction; each anchor is fresh when its age less the hold time\\n    after it is under the window (match_report_window.series_fresh). With\\n    no holds it is the predicate of today."', 'const', '_team_series_resumable', ('body[0]', 'value')),
    ('"One anchor of the same-four window: fresh when its age less the hold\\n    time after it is under the window. `now` is required (the DB clock of\\n    the caller\'s transaction)."', 'const', 'anchor_fresh', ('body[0]', 'value')),
    ('"Poll the 1v2 queue. When 3 searching players are present, the lowest\\n    Steam ID locks the match: assigns 1 solo + 2 duo (honoring preferences,\\n    else join order), creates the series + room, and flips all three to\\n    \'ready_join\'. SELECT FOR UPDATE SKIP LOCKED (#34) prevents duplicate rooms.\\n\\n    Session-bound (Codex sitting-over review find 1, FFA-poll parity): this\\n    poll refreshes last_polled for the CLAIMED steam_id, and the new\\n    all-members-polling inference makes that a destructive input \u2014 an\\n    unauthenticated caller could forge freshness for a whole locked trio and\\n    cancel their live series. Enforcement inherits the steam-auth arming\\n    rollout; unarmed accounts remain soft (documented residual until\\n    STEAM_AUTH_ENFORCE fully arms)."', 'const', 'ovt_queue_poll', ('body[0]', 'value')),
    ('"Poll the FFA queue. Lock rule: with >= FFA_MIN_PLAYERS fresh searching\\n    rows, the lowest Steam ID AMONG THE LOCKED SET (ovt lesson \u2014 the decider\\n    must be a member) locks up to FFA_MAX_PLAYERS earliest joiners once the\\n    gather window has run (or instantly when full). Session-bound (Codex\\n    design find 8): an unauthenticated poll would let anyone keep a victim\'s\\n    row eternally fresh and repeatedly elect it into doomed lobbies."', 'const', '_ffa_queue_poll_inner', ('body[0]', 'value')),
    ('"Queue-matched rooms (no host): Same Cards is ON only when EVERY member\\n    has players.pref_same_cards on AND every member\'s OWN last request was at\\n    or above the floor. Friendly fire is fixed ON (Sid, answer C). An empty\\n    roster can never vote yes."', 'const', '_rules_for_queue_match', ('body[0]', 'value')),
    ('"Queue-matched rules for a roster: the calling seat is judged by THIS\\n    request\'s header (its row may lag one poll); every other seat by its own\\n    row. Returns the {ff, sc} record to freeze."', 'const', '_rules_for_members', ('body[0]', 'value')),
    ('"Queue-matcher wrapper over _team_lock_family_pick: takes the quartet\\n    lock, resolves the family, and re-locks the four QUEUE rows onto the\\n    authoritative series. Returns (\'relocked\', TeamQueuePollResponse) /\\n    (\'fresh\', None) / (\'defer\', None)."', 'const', '_team_resolve_live_family', ('body[0]', 'value')),
    ('"Return ``(net_payout, tax)`` for a winning bet\'s stored odds.\\n\\n    Tax is floor(profit * BET_TAX_RATE) when the stored odds are at or below\\n    BET_TAX_ODDS_MAX. Tax is on PROFIT only, never stake. Because the rate is\\n    below 1, net stays above stake whenever gross was above stake; zero-rounded\\n    profit wins remain identified by settlement_kind=\'won\' (learning #244).\\n    Persist NET as payout; every read surface renders that stored value and\\n    must never recompute the tax for display.\\n    "', 'const', '_bet_fighter_tax', ('body[0]', 'value')),
    ('"SELECT COUNT(*) AS total,       COUNT(*) FILTER (WHERE last_polled > NOW() - INTERVAL \'90 seconds\') AS fresh  FROM ffa_queue WHERE series_id = :lid"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) AS total,       COUNT(*) FILTER (WHERE last_polled > NOW() - INTERVAL \'90 seconds\') AS fresh  FROM ovt_queue WHERE series_id = :sid"', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ffa_queue WHERE status = \'searching\'   AND last_polled > NOW() - INTERVAL \'10 seconds\'   AND NOT (steam_id = ANY(CAST(:service_ids AS text[])))"', 'const', '_ffa_queue_poll_inner', ('body[19]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ffa_queue WHERE status = \'searching\'   AND last_polled > NOW() - INTERVAL \'75 seconds\'   AND NOT (steam_id = ANY(CAST(:service_ids AS text[])))"', 'const', '_ffa_queue_poll_inner', ('body[18]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ffa_queue WHERE status = \'searching\'   AND last_polled > NOW() - INTERVAL \'75 seconds\'   AND NOT (steam_id = ANY(CAST(:service_ids AS text[])))"', 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[1]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ffa_queue WHERE status = \'searching\'   AND last_polled > NOW() - INTERVAL \'75 seconds\'"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[5]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ovt_queue WHERE series_id = :lid   AND status = \'lobby\' AND "', 'const', 'ovt_queue_poll', ('body[15]', 'body[5]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ('"SELECT COUNT(*) FROM ovt_queue WHERE status = \'searching\'   AND last_polled > NOW() - INTERVAL \'75 seconds\'"', 'const', 'ovt_queue_poll', ('body[22]', 'body[1]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ovt_queue WHERE status = \'searching\'"', 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[5]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM ranked_queue WHERE status = \'searching\'"', 'const', 'queue_poll', ('body[29]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT COUNT(*) FROM team_queue WHERE series_id = :lid   AND status = \'lobby\' AND "', 'const', 'team_queue_poll', ('body[18]', 'body[6]', 'value', 'values[0]', 'func', 'value', 'value', 'args[0]', 'args[0]', 'values[0]')),
    ('"SELECT COUNT(*) FROM team_queue WHERE status=\'searching\' AND last_polled > NOW() - INTERVAL \'90 seconds\'"', 'const', 'team_queue_poll', ('body[35]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"SELECT set_config(\'lock_timeout\', :previous, true)"', 'const', '_lease_admission_gate', ('body[5]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"Serialize commitment writers, then re-check the live database truth.\\n\\n    The durable players rows are the common lock relation for all four queue\\n    families and match-seat holds. They are locked in UUID-text order after\\n    each path\'s existing parent/group locks, so overlapping rosters serialize\\n    without serializing unrelated players or reversing the group lock order.\\n    The predicates run only after that wait, making a second writer observe the\\n    first writer\'s committed hold, queue and lease state.\\n\\n    Queue rows remain lease-authoritative (migration 174): a non-searching\\n    husk without its matching live lease is not a commitment. Claim alone asks\\n    for the stricter historical team/ovt rule, where even an out-of-series\\n    search row is a refusal. Allowed groups carry a hosted lobby into its new\\n    series; allowed holds carry the exact hold that open repeats or claim uses.\\n    "', 'const', '_lease_admission_gate', ('body[0]', 'value')),
    ('"Terminal bet resolution for a 2v2 series that is being cancelled/voided\\n    (or is discovered already closed with unsettled bets \u2014 the janitor sweep).\\n    A completed, non-invalidated series with a recorded winner SETTLES its\\n    unsettled bets against that result (#241 \u2014 the settle savepoint can roll\\n    back while the completion commits, leaving chargeable-but-unpaid winners);\\n    a series in an allowed terminal-cancel status refunds the stake; ANY other\\n    status (active, dc_incomplete, dc_paused, ...) is skipped \u2014 its lifecycle\\n    isn\'t decided yet. The stalled-active janitor arm opts \'active\' into the\\n    refund set explicitly (the husk policy, mirroring the 1v1 stalled prune).\\n\\n    The series row is locked FOR NO KEY UPDATE first (#202: the weakest mode\\n    that conflicts with everything we must serialize against): it conflicts\\n    with the FOR UPDATE every completion path holds AND with the plain status\\n    UPDATEs (report-dc\'s flip to dc_incomplete takes NO KEY UPDATE, which\\n    KEY SHARE would have sailed past \u2014 Codex round-2 find 2), while staying\\n    compatible with the FK KEY SHARE that team_bets/team_matches INSERTs take.\\n    So an in-flight completion or DC transition commits before we classify,\\n    and we then settle/skip against the real state instead of refunding it.\\n    Accepted residual (round-2 find 1 / round-3 find 1): a series writer that\\n    has not yet taken its series lock when the stalled sweep claims a refund\\n    can still finish afterwards \u2014 report-dc between its synthetic-match\\n    INSERT (FK KEY SHARE only) and the completion helper\'s FOR UPDATE, or the\\n    non-forfeit DC path whose dc_incomplete flip was read-then-write. Both\\n    need a game-less HOUR plus a ~ms interleaving, and the outcome is always\\n    the documented refund-sticky policy (#107): stakes returned, never a\\n    double-pay (every write is claimed), with the skip/settle decision made\\n    against whatever state committed first.\\n    Claim-first per bet (settled_at gate inside the UPDATE) so a concurrent\\n    settle can never double-pay; gold direction mirrors the live paths (win:\\n    bettor gold_earned += net payout and fighters receive the tax; refund:\\n    gold_spent -= stake). Bounded per pass (leftovers picked up by the\\n    janitor\'s next tick). Savepoint-contained, never raises."', 'const', '_reconcile_team_series_bets', ('body[0]', 'value')),
    ('"The SQLSTATE an exception carries: its own, its DBAPI original\'s (the\\n    SQLAlchemy wrapper\'s .orig) or its cause\'s (asyncpg\'s error)."', 'const', '_asm_sqlstate', ('body[0]', 'value')),
    ('"The `current` overlay for _group_region from a writer\'s own store\\n    result: (player_id, map, measured_at, gen), or None."', 'const', '_region_current', ('body[0]', 'value')),
    ('"The room-region pick for a multiplayer issuance (region_pick.py holds\\n    the rule; the block comment above, the data path). `db` is the issuing\\n    request\'s own session \u2014 the members\' rows are read on it under a\\n    savepoint (c2 H2: no second pool connection while the caller holds its\\n    first, and its locks). `rows` are the members\' queue rows in seat order;\\n    `legacy_pick` is the mode\'s answer before this rule and the fallback on\\n    any error; `current` = (player_id, map, measured_at, gen) is the calling\\n    seat\'s validated header from THIS request, overlaid when it would have\\n    replaced the stored row.\\n\\n    A seat\'s HOME is the lowest-ping code of its own map (region_pick.home_of;\\n    stale or fresh \u2014 where a player is does not go stale within the hour the\\n    rows live), and only without any map the queue row\'s region, which is\\n    the join-time CONNECTION: after a room in another region, that room\'s\\n    region, not a home (c2 H3).\\n\\n    Liveness: a candidate must be in EVERY member\'s map (the rule\'s\\n    intersection). There is no server-side region allowlist BY DECISION (the\\n    corroboration comment above _note_region_seen: Photon serves regions\\n    ROUNDS\' own selector does not list \u2014 hk and uae are in this project\'s\\n    match history \u2014 and a list would refuse a room that was connecting\\n    fine), so the members\' own measured codes are the live set, and a home\\n    no other member has measured never wins a baseline tie\\n    (region_pick._baseline). Volumes for the last tie-break are the 45-day\\n    match counts (_region_volumes). Never raises; one [GROUP-REGION] line\\n    per issuance on EVERY branch, refusals included \u2014 the maps outlive the\\n    queue rows by an hour at most, so the line is the record of what the\\n    rule saw."', 'const', '_group_region', ('body[0]', 'value')),
    ('"The rule\'s LAST tie-break: matches played per region over the last 45\\n    days \u2014 tournaments._region_candidate_volumes, the count the tournament\\n    region pick already uses (c2 M2; the process\'s 7-day sighting counts\\n    stood in for it before). One query per process per\\n    REGION_VOLUMES_CACHE_S, on the caller\'s session under a savepoint;\\n    unavailable -> the last cached answer, or nothing (a tie-break only,\\n    never liveness)."', 'const', '_region_volumes', ('body[0]', 'value')),
    ('"Today\'s freshness test of `_team_series_resumable` (any of\\n    created_at, room_issued_at, last_game_at under the window) with every\\n    anchor measured by `anchor_fresh`."', 'const', 'series_fresh', ('body[0]', 'value')),
    ('"Today\'s multiplayer pick made deterministic: the most common non-empty\\n    home region among the rows, ties to the lexically first code (the old\\n    `max(set(...), key=count)` broke ties by set order, i.e. by the process\'s\\n    hash seed; 1v2\'s first-non-empty seat-order bias is retired with it \u2014\\n    recorded deviation, R1-22), `default` when nobody has one. The v4 rule\\n    recomputes its own baseline from the same homes with the R3 tie policy;\\n    this value is the fallback the rule returns on any error."', 'const', '_region_mode_of', ('body[0]', 'value')),
    ('"UPDATE ffa_lobbies SET status=\'canceled\', invalidation_reason=:rsn,       invalidated_at=NOW(),"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]', 'left', 'left')),
    ('"UPDATE ffa_lobbies SET status=\'completed\', completed_at=NOW(),"', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]', 'left', 'left')),
    ('"UPDATE ovt_series SET status=\'canceled\', invalidation_reason=:rsn,       invalidated_at=NOW() WHERE id=:sid AND status=\'active\'"', 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"UPDATE ovt_series SET status=\'canceled\', invalidation_reason=\'sitting_abandoned\',       invalidated_at=NOW() WHERE id=:sid AND status=\'active\'"', 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"UPDATE team_series SET status=\'cancelled\', invalidated_at=NOW(), invalidation_reason=\'lease_lapsed\' WHERE id = :sid"', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"UPDATE team_series SET status=\'cancelled\', invalidated_at=NOW(), invalidation_reason=\'member_banned\' WHERE id = :sid"', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[4]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"UPDATE team_series SET status=\'cancelled\', invalidated_at=NOW(), invalidation_reason=\'ready_timeout\' WHERE id = :sid"', 'const', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"Whether a map (gen, measured_at) REPLACES a stored one \u2014 the Python\\n    twin of the upsert\'s WHERE in _REGION_PINGS_UPSERT_SQL; the issuance\\n    overlay applies the caller\'s header only when this says the store would\\n    have kept it. A new nonce always wins, the same nonce needs a greater seq,\\n    and a map without a generation falls back to a strictly newer\\n    measured_at. measured_at is derived from the header\'s age at RECEIPT, so\\n    a request delayed in transit can look newer than the sweep that followed\\n    it; the generation exists so the order of sweeps, not of arrivals,\\n    decides (design r2, R1-20)."', 'const', '_region_pings_newer', ('body[0]', 'value')),
    ('"Whether one complete queue-stamped FFA roster clears cr_prox1.\\n\\n    The floor is read on every call so a rolling API deploy can tighten it\\n    between a parent\'s lock and REFORM.  Missing, NULL and malformed stamps\\n    fail toward an unrated room.\\n    "', 'const', '_ffa_roster_clears_proximity_floor', ('body[0]', 'value')),
    ('"[FFA-LOBBY] INVARIANT: \'lobby\' row survived Start on active lobby "', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'body[0]', 'value', 'args[0]', 'values[0]')),
    ('"\' is not terminal here"', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]', 'value', 'args[0]', 'values[6]')),
    ('"\\n                    UPDATE ranked_queue\\n                    SET status = \'matched\', matched_with = :opp_id,\\n                        room_name = NULL, room_region = NULL, ready = false, matched_at = :mat\\n                    WHERE player_id = :pid\\n                "', 'const', 'queue_poll', ('body[28]', 'body[18]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n                UPDATE ffa_queue SET status=\'searching\', series_id=NULL, slot=NULL,\\n                       room_name=NULL, room_region=NULL, matched_at=NULL, joined_at=NOW(),\\n                       held_until=NULL, held_lobby=NULL\\n                 WHERE series_id = :lid\\n            "', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n                UPDATE team_queue\\n                   SET status = \'matched\',\\n                       series_id = :sid,\\n                       team_assigned = :t,\\n                       matched_at = NOW(),\\n                       rules = CAST(:rules AS JSONB)\\n                 WHERE player_id = :pid\\n            "', 'const', '_team_relock_existing_series', ('body[3]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id,\\n                                     status, was_auto_balanced, created_at, rules)\\n            VALUES (:sid, :t1a, :t1b, :t2a, :t2b, \'active\', :wab, NOW(),\\n                    CAST(:rules AS JSONB))\\n        "', 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            SELECT id, t1a_id, t1b_id, t2a_id, t2b_id\\n              FROM team_series ts\\n             WHERE :pid IN (t1a_id, t1b_id, t2a_id, t2b_id)\\n               AND ((status = \'dc_paused\' AND dc_grace_until > NOW())\\n                 OR (status = \'dc_incomplete\'\\n                     AND invalidation_reason = \'dc_manual_pending\'\\n                     AND (created_at > NOW() - INTERVAL \'30 minutes\'\\n                          OR EXISTS (SELECT 1 FROM team_matches tm\\n                                      WHERE tm.series_id = ts.id\\n                                        AND tm.ended_at > NOW() - INTERVAL \'30 minutes\'))))\\n             ORDER BY created_at DESC\\n             LIMIT 1\\n        "', 'const', 'team_queue_poll', ('body[29]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            SELECT si.name, si.preview_color\\n              FROM players p\\n              JOIN shop_items si ON si.id = p.active_player_color_id\\n                                AND si.kind = \'player_color\'\\n             WHERE p.id = :pid\\n        "', 'const', '_player_body_color', ('body[1]', 'body[0]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            SELECT ts.id, ts.status, ts.t1a_id, ts.t1b_id, ts.t2a_id, ts.t2b_id,\\n                   ts.t1_series_wins, ts.t2_series_wins, ts.dc_grace_until,\\n                   ts.invalidation_reason, ts.created_at, ts.room_issued_at,\\n                   ts.rules,\\n                   (SELECT COUNT(*) FROM team_matches tm\\n                     WHERE tm.series_id = ts.id\\n                       AND tm.invalidated_at IS NULL) AS games,\\n                   (SELECT MAX(tm.ended_at) FROM team_matches tm\\n                     WHERE tm.series_id = ts.id\\n                       AND tm.invalidated_at IS NULL) AS last_game_at\\n              FROM team_series ts\\n             WHERE ts.id = :sid\\n               AND ts.status IN (\'active\', \'dc_paused\', \'dc_incomplete\')\\n             FOR UPDATE OF ts SKIP LOCKED\\n        "', 'const', '_team_lock_family_pick', ('body[4]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            UPDATE ffa_queue SET status=\'ready_join\', series_id=:lid, slot=:slot,\\n                   room_name=:room, room_region=:reg, matched_at=NOW(),\\n                   held_until=NULL, held_lobby=NULL\\n             WHERE player_id=:pid\\n        "', 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            UPDATE ovt_queue SET status=\'ready_join\', series_id=:sid, side_assigned=:side,\\n                   room_name=:room, room_region=:reg, matched_at=NOW()\\n             WHERE player_id=:pid\\n        "', 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            UPDATE team_queue\\n            SET status=\'matched\',\\n                series_id=:sid,\\n                team_assigned = CASE WHEN player_id = ANY(:t1) THEN 1 ELSE 2 END,\\n                matched_at = :mat,\\n                ready = false,\\n                room_name = NULL, room_region = NULL,\\n                rules = CAST(:rules AS JSONB)\\n            WHERE player_id = ANY(:all4)\\n        "', 'const', 'team_queue_poll', ('body[60]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            UPDATE team_series\\n               SET status = \'active\',\\n                   dc_grace_until = NULL,\\n                   dc_team_remaining = NULL,\\n                   dc_player_id = NULL,\\n                   photon_room_id = NULL,\\n                   room_issued_at = NULL,\\n                   -- Stage 2 (V3 S1 step 2) - the hold flag goes with the room\\n                   -- it was latched for; the next room issue re-judges it.\\n                   hold_v2 = FALSE,\\n                   hold_room = NULL,\\n                   spawn_confirmations = 0,\\n                   spawn_confirmed_by = \'[]\'::jsonb,\\n                   invalidation_reason = CASE\\n                       WHEN invalidation_reason = \'dc_manual_pending\' THEN NULL\\n                       ELSE invalidation_reason END\\n             WHERE id = :sid\\n               AND status IN (\'active\', \'dc_paused\', \'dc_incomplete\')\\n        "', 'const', '_team_relock_existing_series', ('body[5]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            UPDATE team_series\\n               SET status = \'cancelled\', completed_at = NOW(),\\n                   invalidation_reason = \'superseded_requeue\'\\n             WHERE id = :sid\\n        "', 'const', '_team_lock_family_pick', ('body[10]', 'body[2]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n            WITH previous AS MATERIALIZED (\\n                SELECT current_setting(\'lock_timeout\') AS value,\\n                       setting::bigint AS milliseconds\\n                  FROM pg_settings WHERE name = \'lock_timeout\' AND unit = \'ms\'\\n            )\\n            SELECT value, set_config(\'lock_timeout\',\\n                LEAST(COALESCE(NULLIF(milliseconds, 0), 1000), 1000)::text || \'ms\',\\n                true)\\n              FROM previous\\n        "', 'const', '_lease_admission_gate', ('body[5]', 'body[0]', 'value', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        DELETE FROM ffa_queue WHERE player_id IN (\\n            SELECT player_id FROM ffa_queue\\n             WHERE status != \'searching\' AND matched_at IS NOT NULL\\n               AND matched_at < NOW() - INTERVAL \'3 hours\'\\n               AND series_id IS DISTINCT FROM :my_series\\n               AND NOT (held_until IS NOT NULL\\n                        AND held_lobby IS NOT DISTINCT FROM series_id\\n                        AND held_until > clock_timestamp())\\n             FOR UPDATE SKIP LOCKED)\\n    "', 'const', '_ffa_queue_poll_inner', ('body[11]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        DELETE FROM ffa_queue WHERE player_id IN (\\n            SELECT player_id FROM ffa_queue\\n             WHERE status = \'searching\' AND last_polled < NOW() - INTERVAL \'75 seconds\'\\n             FOR UPDATE SKIP LOCKED)\\n    "', 'const', '_ffa_queue_poll_inner', ('body[10]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        DELETE FROM ovt_queue WHERE player_id IN (\\n            SELECT player_id FROM ovt_queue\\n             WHERE status != \'searching\' AND matched_at IS NOT NULL\\n               AND matched_at < NOW() - INTERVAL \'3 hours\'\\n               AND series_id IS DISTINCT FROM :my_series\\n             FOR UPDATE SKIP LOCKED)\\n    "', 'const', 'ovt_queue_poll', ('body[13]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        DELETE FROM ovt_queue WHERE player_id IN (\\n            SELECT player_id FROM ovt_queue\\n             WHERE status = \'searching\' AND last_polled < NOW() - INTERVAL \'75 seconds\'\\n             FOR UPDATE SKIP LOCKED)\\n    "', 'const', 'ovt_queue_poll', ('body[12]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        INSERT INTO ffa_lobbies (id, status, photon_room_id, region, player_count, member_ids,\\n                                 created_at, kills_tiebreak, is_ranked,\\n                                 assembly_v1, admission_v1)\\n        VALUES (:lid, \'active\', :room, :reg, :n, :members, NOW(), :kt,\\n                :proximity_capable, FALSE, FALSE)\\n    "', 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        INSERT INTO ovt_series (id, solo_id, duo_a_id, duo_b_id, status, is_ranked,\\n                                solo_extra_pick, photon_room_id, region, created_at, rules)\\n        VALUES (:sid, :solo, :da, :db, \'active\', false, :sep, :room, :reg, NOW(),\\n                CAST(:rules AS JSONB))\\n    "', 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        SELECT player_id, \'ranked\'::varchar AS mode, NULL::uuid AS group_id, status\\n          FROM ranked_queue WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n        UNION ALL\\n        SELECT player_id, \'team\'::varchar, series_id, status\\n          FROM team_queue WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n        UNION ALL\\n        SELECT player_id, \'ovt\'::varchar, series_id, status\\n          FROM ovt_queue WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n        UNION ALL\\n        SELECT player_id, \'ffa\'::varchar, series_id, status\\n          FROM ffa_queue WHERE player_id = ANY(CAST(:pids AS uuid[]))\\n    "', 'const', '_lease_admission_gate', ('body[15]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"\\n        SELECT region, COUNT(*) AS n\\n          FROM matches\\n         WHERE created_at > NOW() - make_interval(days => :live)\\n           AND region IS NOT NULL AND region <> \'\'\\n         GROUP BY region\\n    "', 'const', '_region_candidate_volumes', ('body[1]', 'value', 'func', 'value', 'value', 'args[0]', 'args[0]')),
    ('"player_id -> (pref_same_cards, that row\'s own mod_version) for a set of\\n    queue rows. Reads the ROW\'s version (the seat\'s own last poll), never\\n    players.mod_version (a global last-write-wins value). A member without a\\n    row is reported as (False, None) \u2014 it can never vote yes."', 'const', '_rules_members', ('body[0]', 'value')),
    ('0', 'const', '_balance_teams', ('body[3]', 'value', 'elts[0]', 'elts[0]', 'elts[0]', 'slice')),
    ('0', 'const', '_balance_teams', ('body[3]', 'value', 'elts[1]', 'elts[0]', 'elts[0]', 'slice')),
    ('0', 'const', '_balance_teams', ('body[3]', 'value', 'elts[2]', 'elts[0]', 'elts[0]', 'slice')),
    ('0', 'const', '_balance_teams', ('body[5]', 'value', 'keywords[0]', 'value', 'body', 'args[0]', 'slice')),
    ('0', 'const', '_balance_teams', ('body[6]', 'value', 'elts[0]', 'generators[0]', 'iter', 'slice')),
    ('0', 'const', '_baseline', ('body[6]', 'body[0]', 'value', 'elts[0]', 'slice')),
    ('0', 'const', '_baseline', ('body[8]', 'body[0]', 'value', 'elts[0]', 'slice')),
    ('0', 'const', '_baseline', ('body[9]', 'value', 'elts[0]', 'slice')),
    ('0', 'const', '_bet_fighter_tax', ('body[2]', 'body[0]', 'value', 'elts[1]')),
    ('0', 'const', '_bet_fighter_tax', ('body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('0', 'const', '_credit_bet_fighter_tax', ('body[1]', 'test', 'comparators[0]')),
    ('0', 'const', '_credit_team_bet_fighter_tax', ('body[1]', 'test', 'comparators[0]')),
    ('0', 'const', '_ffa_gather_decide', ('body[1]', 'body[0]', 'value', 'elts[1]')),
    ('0', 'const', '_ffa_gather_decide', ('body[4]', 'value', 'elts[1]', 'args[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[2]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[10]', 'value')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[2]', 'orelse')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[2]', 'test', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[2]', 'test', 'left', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[5]', 'orelse')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[3]', 'values[2]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[3]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[4]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[1]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[1]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[4]', 'comparators[0]', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[4]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[5]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[5]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'test', 'values[1]', 'values[0]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'test', 'values[1]', 'values[0]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[5]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[5]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[2]', 'value', 'orelse')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[2]', 'comparators[0]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[2]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[3]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[18]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[19]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[31]', 'body[1]', 'value', 'values[3]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[1]', 'test', 'left', 'slice')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[34]', 'body[1]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[5]', 'body[0]', 'value', 'values[1]')),
    ('0', 'const', '_ffa_queue_poll_inner', ('body[7]', 'body[1]', 'value', 'values[1]')),
    ('0', 'const', '_lock_snapshot_rows', ('body[2]', 'iter', 'keywords[0]', 'value', 'body', 'elts[0]', 'slice')),
    ('0', 'const', '_parse_version', ('body[0]', 'handlers[0]', 'body[0]', 'value', 'elts[0]')),
    ('0', 'const', '_pick', ('body[12]', 'test', 'values[0]', 'comparators[0]')),
    ('0', 'const', '_pick', ('body[13]', 'value', 'args[0]', 'value', 'slice')),
    ('0', 'const', '_pick', ('body[23]', 'body[0]', 'value', 'slice')),
    ('0', 'const', '_pick', ('body[23]', 'orelse[1]', 'value', 'elts[2]')),
    ('0', 'const', '_pick', ('body[23]', 'orelse[1]', 'value', 'elts[3]')),
    ('0', 'const', '_pick', ('body[3]', 'body[0]', 'value', 'args[1]')),
    ('0', 'const', '_pick', ('body[3]', 'body[1]', 'value', 'orelse')),
    ('0', 'const', '_player_body_color', ('body[3]', 'value', 'elts[0]', 'values[0]', 'value', 'values[0]', 'slice')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[8]', 'value')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[1]', 'value', 'orelse')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[2]', 'value', 'orelse', 'elts[0]')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[2]', 'value', 'orelse', 'elts[1]')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[1]', 'value')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[2]', 'value', 'value', 'args[1]', 'slice')),
    ('0', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'test', 'comparators[0]')),
    ('0', 'const', '_region_current', ('body[2]', 'value', 'elts[1]', 'slice')),
    ('0', 'const', '_region_mode_of', ('body[2]', 'body[1]', 'body[0]', 'value', 'left', 'args[1]')),
    ('0', 'const', '_region_pings_newer', ('body[1]', 'body[0]', 'test', 'values[1]', 'comparators[0]', 'slice')),
    ('0', 'const', '_region_pings_newer', ('body[1]', 'body[0]', 'test', 'values[1]', 'left', 'slice')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[0]', 'left', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[1]', 'left', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[2]', 'comparators[0]')),
    ('0', 'const', '_team_lock_family_pick', ('body[10]', 'body[1]', 'test', 'values[2]', 'left', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'left', 'left', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'left', 'right', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[0]', 'value', 'body', 'elts[0]', 'right', 'values[1]')),
    ('0', 'const', '_team_lock_family_pick', ('body[9]', 'body[1]', 'value', 'slice')),
    ('0', 'const', '_team_relock_existing_series', ('body[11]', 'value', 'keywords[5]', 'value')),
    ('0', 'const', '_team_resolve_live_family', ('body[7]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[0]', 'left', 'values[1]')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[1]', 'left', 'values[1]')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[2]', 'comparators[0]')),
    ('0', 'const', '_team_series_resumable', ('body[1]', 'test', 'values[2]', 'left', 'values[1]')),
    ('0', 'const', 'held_overlap', ('body[1]', 'value', 'args[0]')),
    ('0', 'const', 'ovt_queue_poll', ('args', 'defaults[1]', 'args[0]')),
    ('0', 'const', 'ovt_queue_poll', ('args', 'defaults[1]', 'keywords[0]', 'value')),
    ('0', 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[2]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[3]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[4]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[15]', 'body[5]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[4]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]', 'body[0]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[5]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[2]', 'value', 'orelse')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[2]', 'comparators[0]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[2]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[1]', 'comparators[0]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[1]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'comparators[0]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[1]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[3]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'test', 'values[1]', 'comparators[0]')),
    ('0', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'test', 'values[1]', 'left', 'args[0]', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ('0', 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[3]', 'test', 'left', 'slice')),
    ('0', 'const', 'ovt_queue_poll', ('body[21]', 'body[4]', 'value', 'orelse', 'value', 'slice')),
    ('0', 'const', 'ovt_queue_poll', ('body[22]', 'body[1]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[23]', 'value', 'values[1]', 'slice')),
    ('0', 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[2]', 'value', 'slice')),
    ('0', 'const', 'ovt_queue_poll', ('body[7]', 'body[0]', 'value', 'values[1]')),
    ('0', 'const', 'ovt_queue_poll', ('body[9]', 'body[1]', 'value', 'values[1]')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[11]', 'value', 'body')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[12]', 'value', 'body')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[2]', 'value')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[3]', 'value')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[4]', 'value')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]', 'value', 'keywords[5]', 'value')),
    ('0', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('0', 'const', 'queue_poll', ('body[25]', 'body[2]', 'value', 'keywords[1]', 'value')),
    ('0', 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('0', 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[3]', 'test', 'left', 'slice')),
    ('0', 'const', 'queue_poll', ('body[30]', 'value', 'values[1]')),
    ('0', 'const', 'team_queue_poll', ('args', 'defaults[1]', 'args[0]')),
    ('0', 'const', 'team_queue_poll', ('args', 'defaults[1]', 'keywords[0]', 'value')),
    ('0', 'const', 'team_queue_poll', ('body[18]', 'body[6]', 'value', 'values[1]')),
    ('0', 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[0]', 'value', 'args[0]', 'values[1]')),
    ('0', 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[3]', 'value', 'args[0]', 'values[1]')),
    ('0', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[7]', 'value', 'orelse')),
    ('0', 'const', 'team_queue_poll', ('body[19]', 'body[16]', 'value', 'keywords[5]', 'value', 'orelse')),
    ('0', 'const', 'team_queue_poll', ('body[25]', 'body[1]', 'value', 'keywords[1]', 'value')),
    ('0', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'test', 'comparators[0]')),
    ('0', 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[1]', 'value', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[2]', 'test', 'left', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[34]', 'test', 'comparators[0]')),
    ('0', 'const', 'team_queue_poll', ('body[35]', 'body[1]', 'value', 'values[1]')),
    ('0', 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'values[1]', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'values[3]', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[57]', 'body[0]', 'value', 'args[0]', 'elts[0]', 'elts[0]', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[57]', 'body[0]', 'value', 'args[0]', 'elts[1]', 'elts[1]', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[58]', 'body[0]', 'value', 'value', 'args[1]', 'values[0]', 'elt', 'slice')),
    ('0', 'const', 'team_queue_poll', ('body[70]', 'value', 'keywords[5]', 'value')),
    ('0.0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[1]', 'value')),
    ('0.0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[2]', 'body[0]', 'value', 'args[0]')),
    ('0.0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[3]', 'value', 'args[0]', 'args[0]', 'args[0]', 'values[1]')),
    ('1', 'const', '_balance_teams', ('body[3]', 'value', 'elts[0]', 'elts[0]', 'elts[1]', 'slice')),
    ('1', 'const', '_balance_teams', ('body[3]', 'value', 'elts[1]', 'elts[1]', 'elts[0]', 'slice')),
    ('1', 'const', '_balance_teams', ('body[3]', 'value', 'elts[2]', 'elts[1]', 'elts[0]', 'slice')),
    ('1', 'const', '_balance_teams', ('body[5]', 'value', 'keywords[0]', 'value', 'body', 'args[1]', 'slice')),
    ('1', 'const', '_balance_teams', ('body[6]', 'value', 'elts[1]', 'generators[0]', 'iter', 'slice')),
    ('1', 'const', '_baseline', ('body[6]', 'test', 'comparators[0]')),
    ('1', 'const', '_baseline', ('body[8]', 'test', 'comparators[0]')),
    ('1', 'const', '_ffa_queue_poll_inner', ('body[21]', 'body[1]', 'value', 'values[3]', 'operand')),
    ('1', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('1', 'const', '_ffa_queue_poll_inner', ('body[33]', 'iter', 'args[0]')),
    ('1', 'const', '_ffa_queue_poll_inner', ('body[33]', 'iter', 'args[1]', 'right')),
    ('1', 'const', '_group_region', ('body[2]', 'body[3]', 'body[2]', 'test', 'values[1]', 'args[3]', 'slice')),
    ('1', 'const', '_lease_admission_gate', ('body[16]', 'value', 'slice')),
    ('1', 'const', '_lease_admission_gate', ('body[17]', 'body[1]', 'test', 'values[2]', 'left', 'slice')),
    ('1', 'const', '_lock_snapshot_rows', ('body[2]', 'iter', 'keywords[0]', 'value', 'body', 'elts[1]', 'args[0]', 'slice')),
    ('1', 'const', '_pick', ('body[14]', 'iter', 'slice', 'lower')),
    ('1', 'const', '_pick', ('body[18]', 'body[1]', 'value', 'args[0]', 'elt')),
    ('1', 'const', '_player_body_color', ('body[2]', 'test', 'values[1]', 'operand', 'slice')),
    ('1', 'const', '_player_body_color', ('body[3]', 'value', 'elts[1]', 'values[0]', 'value', 'values[0]', 'slice')),
    ('1', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[1]', 'comparators[0]', 'elts[0]')),
    ('1', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'test', 'comparators[0]')),
    ('1', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[0]', 'value')),
    ('1', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[2]', 'value', 'value', 'args[2]', 'slice')),
    ('1', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[0]', 'value')),
    ('1', 'const', '_region_current', ('body[2]', 'value', 'elts[2]', 'slice')),
    ('1', 'const', '_region_mode_of', ('body[2]', 'body[1]', 'body[0]', 'value', 'right')),
    ('1', 'const', '_region_pings_newer', ('body[1]', 'body[1]', 'value', 'comparators[0]', 'slice')),
    ('1', 'const', '_region_pings_newer', ('body[1]', 'body[1]', 'value', 'left', 'slice')),
    ('1', 'const', '_team_relock_existing_series', ('body[10]', 'value', 'body')),
    ('1', 'const', '_team_relock_existing_series', ('body[3]', 'body[0]', 'value', 'body')),
    ('1', 'const', '_team_resolve_live_family', ('body[7]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('1', 'const', 'ovt_queue_poll', ('args', 'defaults[1]', 'keywords[1]', 'value')),
    ('1', 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('1', 'const', 'ovt_queue_poll', ('body[21]', 'iter', 'args[0]')),
    ('1', 'const', 'ovt_queue_poll', ('body[21]', 'iter', 'args[1]', 'right')),
    ('1', 'const', 'ovt_queue_poll', ('body[23]', 'value', 'values[0]', 'args[0]', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('1', 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[3]', 'value', 'slice')),
    ('1', 'const', 'ovt_queue_poll', ('body[34]', 'body[0]', 'value', 'body')),
    ('1', 'const', 'queue_poll', ('body[11]', 'value')),
    ('1', 'const', 'queue_poll', ('body[16]', 'body[0]', 'value')),
    ('1', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ('1', 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ('1', 'const', 'queue_poll', ('body[28]', 'iter', 'args[0]')),
    ('1', 'const', 'queue_poll', ('body[28]', 'iter', 'args[1]', 'right')),
    ('1', 'const', 'team_queue_poll', ('args', 'defaults[1]', 'keywords[1]', 'value')),
    ('1', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]', 'value', 'args[0]', 'values[5]', 'value', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[0]', 'value')),
    ('1', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[0]', 'value', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('1', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'test', 'args[0]', 'elt', 'comparators[0]', 'elts[0]')),
    ('1', 'const', 'team_queue_poll', ('body[33]', 'value', 'args[1]')),
    ('1', 'const', 'team_queue_poll', ('body[34]', 'body[0]', 'value')),
    ('1', 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]', 'value', 'args[0]', 'values[3]', 'value', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('1', 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'values[2]', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[52]', 'value', 'value', 'args[1]', 'values[4]', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[57]', 'body[0]', 'value', 'args[0]', 'elts[0]', 'elts[1]', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[57]', 'body[0]', 'value', 'args[0]', 'elts[1]', 'elts[0]', 'slice')),
    ('1', 'const', 'team_queue_poll', ('body[58]', 'body[0]', 'value', 'value', 'args[1]', 'values[1]', 'elt', 'slice')),
    ('1000000', 'const', 'team_queue_poll', ('body[22]', 'body[0]', 'value')),
    ('12', 'const', '_ffa_queue_poll_inner', ('body[39]', 'value', 'values[1]', 'value', 'slice', 'upper')),
    ('12', 'const', 'ovt_queue_poll', ('body[27]', 'value', 'values[1]', 'value', 'slice', 'upper')),
    ('12', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[3]', 'value', 'values[1]', 'value', 'slice', 'upper')),
    ('12', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[5]', 'value', 'values[1]', 'value', 'slice', 'upper')),
    ('15.0', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[2]', 'body[0]', 'value', 'args[1]', 'left')),
    ('15.0', 'const', '_ffa_queue_poll_inner', ('body[24]', 'test', 'values[1]', 'comparators[0]')),
    ('1500', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[16]', 'elt', 'values[3]', 'args[0]', 'args[0]', 'values[1]')),
    ('180', 'const', 'pick_region_for_group', ('args', 'kw_defaults[2]')),
    ('2', 'const', '_balance_teams', ('body[3]', 'value', 'elts[0]', 'elts[1]', 'elts[0]', 'slice')),
    ('2', 'const', '_balance_teams', ('body[3]', 'value', 'elts[1]', 'elts[0]', 'elts[1]', 'slice')),
    ('2', 'const', '_balance_teams', ('body[3]', 'value', 'elts[2]', 'elts[1]', 'elts[1]', 'slice')),
    ('2', 'const', '_credit_team_bet_fighter_tax', ('body[3]', 'value', 'left', 'right')),
    ('2', 'const', '_credit_team_bet_fighter_tax', ('body[3]', 'value', 'right', 'right')),
    ('2', 'const', '_credit_team_bet_fighter_tax', ('body[4]', 'value', 'right')),
    ('2', 'const', '_group_region', ('body[2]', 'body[3]', 'body[2]', 'test', 'values[1]', 'args[2]', 'slice')),
    ('2', 'const', '_pick', ('body[18]', 'body[3]', 'value', 'body', 'left', 'left')),
    ('2', 'const', '_pick', ('body[18]', 'body[3]', 'value', 'orelse', 'left', 'left')),
    ('2', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[1]', 'comparators[0]', 'elts[1]')),
    ('2', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]', 'value', 'orelse', 'test', 'comparators[0]')),
    ('2', 'const', '_region_current', ('body[2]', 'value', 'elts[3]', 'slice')),
    ('2', 'const', '_team_relock_existing_series', ('body[10]', 'value', 'orelse')),
    ('2', 'const', '_team_relock_existing_series', ('body[3]', 'body[0]', 'value', 'orelse')),
    ('2', 'const', 'ovt_queue_poll', ('body[25]', 'test', 'comparators[0]')),
    ('2', 'const', 'ovt_queue_poll', ('body[34]', 'body[0]', 'value', 'orelse')),
    ('2', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[1]', 'value', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[2]', 'test', 'values[1]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'test', 'args[0]', 'elt', 'comparators[0]', 'elts[1]')),
    ('2', 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'test', 'values[0]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'test', 'values[1]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]', 'orelse[0]', 'test', 'comparators[0]')),
    ('2', 'const', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]', 'test', 'comparators[0]')),
    ('20', 'const', 'pick_region_for_group', ('args', 'kw_defaults[0]')),
    ('3', 'const', '_balance_teams', ('body[3]', 'value', 'elts[0]', 'elts[1]', 'elts[1]', 'slice')),
    ('3', 'const', '_balance_teams', ('body[3]', 'value', 'elts[1]', 'elts[1]', 'elts[1]', 'slice')),
    ('3', 'const', '_balance_teams', ('body[3]', 'value', 'elts[2]', 'elts[0]', 'elts[1]', 'slice')),
    ('3', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[3]', 'comparators[0]')),
    ('3', 'const', 'ovt_queue_poll', ('body[21]', 'body[10]', 'test', 'comparators[0]')),
    ('3', 'const', 'ovt_queue_poll', ('body[21]', 'body[1]', 'test', 'comparators[0]')),
    ('3', 'const', 'ovt_queue_poll', ('body[21]', 'body[2]', 'value', 'args[0]', 'slice', 'upper')),
    ('3', 'const', 'queue_poll', ('body[16]', 'test', 'values[1]', 'comparators[0]')),
    ('3', 'const', 'team_queue_poll', ('body[19]', 'body[4]', 'test', 'comparators[0]')),
    ('3', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[2]', 'test', 'comparators[0]')),
    ('3', 'const', 'team_queue_poll', ('body[34]', 'body[2]', 'test', 'comparators[0]')),
    ('3', 'const', 'team_queue_poll', ('body[34]', 'body[9]', 'test', 'comparators[0]')),
    ('3', 'const', 'team_queue_poll', ('body[35]', 'test', 'comparators[0]')),
    ('30', 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'test', 'comparators[0]', 'left')),
    ('30', 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'test', 'comparators[0]', 'left')),
    ('30', 'const', 'pick_region_for_group', ('args', 'kw_defaults[1]')),
    ('300', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[2]', 'comparators[0]')),
    ('300', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'test', 'values[2]', 'comparators[0]')),
    ('350.0', 'const', '_team_balance_rating', ('args', 'defaults[0]')),
    ('350.0', 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[1]', 'value', 'args[0]', 'values[1]')),
    ('4', 'const', '_balance_teams', ('body[1]', 'test', 'comparators[0]')),
    ('4', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'body[1]', 'value', 'keywords[1]', 'value')),
    ('4', 'const', 'team_queue_poll', ('body[35]', 'body[2]', 'test', 'comparators[0]')),
    ('4', 'const', 'team_queue_poll', ('body[48]', 'body[1]', 'value', 'keywords[1]', 'value')),
    ('40', 'const', '_player_body_color', ('body[3]', 'value', 'elts[0]', 'values[0]', 'slice', 'upper')),
    ('400', 'const', '_mode_or_400', ('body[0]', 'body[0]', 'exc', 'args[0]')),
    ('401', 'const', 'queue_poll', ('body[2]', 'body[0]', 'exc', 'keywords[0]', 'value')),
    ('403', 'const', '_assert_no_service_subject', ('body[2]', 'body[0]', 'exc', 'keywords[0]', 'value')),
    ('403', 'const', '_assert_no_service_subject', ('body[5]', 'body[0]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_ffa_queue_poll_inner', ('body[33]', 'orelse[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_ffa_queue_poll_inner', ('body[45]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'body[0]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', '_team_relock_existing_series', ('body[4]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'ovt_queue_poll', ('body[21]', 'orelse[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'ovt_queue_poll', ('body[35]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'queue_poll', ('body[17]', 'body[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'queue_poll', ('body[28]', 'body[19]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'queue_poll', ('body[28]', 'body[2]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'queue_poll', ('body[28]', 'orelse[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'team_queue_poll', ('body[34]', 'orelse[2]', 'exc', 'keywords[0]', 'value')),
    ('503', 'const', 'team_queue_poll', ('body[61]', 'body[1]', 'exc', 'keywords[0]', 'value')),
    ('60', 'const', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'test', 'comparators[0]', 'right')),
    ('60', 'const', '_lease_admission_gate', ('args', 'kw_defaults[3]')),
    ('60', 'const', 'ovt_queue_poll', ('body[14]', 'body[1]', 'test', 'comparators[0]', 'right')),
    ('60', 'const', 'queue_poll', ('body[23]', 'test', 'values[1]', 'comparators[0]', 'right')),
    ('60', 'const', 'team_queue_poll', ('body[17]', 'test', 'values[1]', 'comparators[0]', 'right')),
    ('60.0', 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'body[2]', 'value', 'orelse', 'right', 'right')),
    ('600', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[3]', 'comparators[0]')),
    ('600', 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[3]', 'comparators[0]')),
    ('8', 'const', '_ffa_queue_poll_inner', ('body[43]', 'value', 'value', 'args[1]', 'values[2]', 'slice', 'upper')),
    ('8', 'const', '_ffa_queue_poll_inner', ('body[44]', 'body[0]', 'value', 'value', 'args[1]', 'values[3]', 'slice', 'upper')),
    ('8', 'const', 'ovt_queue_poll', ('body[32]', 'value', 'value', 'args[1]', 'values[6]', 'slice', 'upper')),
    ('8', 'const', 'ovt_queue_poll', ('body[34]', 'body[1]', 'value', 'value', 'args[1]', 'values[3]', 'slice', 'upper')),
    ('9', 'const', '_player_body_color', ('body[3]', 'value', 'elts[1]', 'values[0]', 'slice', 'upper')),
    ('900', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('900', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('Ellipsis', 'const', '_credit_team_bet_fighter_tax', ('args', 'args[5]', 'annotation', 'slice', 'elts[1]')),
    ('Ellipsis', 'const', '_parse_version', ('returns', 'slice', 'elts[1]')),
    ('False', 'const', '_ffa_gather_decide', ('body[4]', 'value', 'elts[0]')),
    ('False', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[10]', 'value')),
    ('False', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[4]', 'value')),
    ('False', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[9]', 'value')),
    ('False', 'const', '_ffa_queue_poll_inner', ('body[45]', 'test', 'comparators[0]')),
    ('False', 'const', '_ffa_roster_clears_proximity_floor', ('body[1]', 'body[0]', 'value')),
    ('False', 'const', '_formation_lease_conflict', ('args', 'kw_defaults[2]')),
    ('False', 'const', '_hold_latch', ('body[3]', 'body[0]', 'value')),
    ('False', 'const', '_lease_acquire', ('args', 'kw_defaults[0]')),
    ('False', 'const', '_lease_acquire', ('args', 'kw_defaults[3]')),
    ('False', 'const', '_lease_acquire', ('body[1]', 'body[1]', 'body[0]', 'value')),
    ('False', 'const', '_lease_acquire_many', ('body[3]', 'body[0]', 'value')),
    ('False', 'const', '_lease_admission_gate', ('args', 'kw_defaults[4]')),
    ('False', 'const', '_lease_admission_gate', ('body[14]', 'body[0]', 'value', 'elts[0]')),
    ('False', 'const', '_lease_admission_gate', ('body[17]', 'body[1]', 'body[0]', 'value', 'elts[0]')),
    ('False', 'const', '_lease_admission_gate', ('body[17]', 'body[4]', 'body[0]', 'value', 'elts[0]')),
    ('False', 'const', '_lease_admission_gate', ('body[4]', 'value')),
    ('False', 'const', '_lease_admission_gate', ('body[6]', 'body[1]', 'value', 'elts[0]')),
    ('False', 'const', '_mod_version_at_least', ('body[1]', 'body[0]', 'value')),
    ('False', 'const', '_mod_version_at_least', ('body[2]', 'handlers[0]', 'body[0]', 'value')),
    ('False', 'const', '_rules_members', ('body[3]', 'value', 'value', 'elts[0]')),
    ('False', 'const', '_team_relock_existing_series', ('body[4]', 'test', 'comparators[0]')),
    ('False', 'const', '_team_series_resumable', ('body[1]', 'body[0]', 'value')),
    ('False', 'const', '_team_series_resumable', ('body[8]', 'value')),
    ('False', 'const', 'anchor_fresh', ('body[1]', 'body[0]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[15]', 'body[2]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[16]', 'body[4]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[16]', 'body[7]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[16]', 'body[8]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[20]', 'value')),
    ('False', 'const', 'ovt_queue_poll', ('body[35]', 'test', 'comparators[0]')),
    ('False', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[2]', 'value')),
    ('False', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'comparators[0]')),
    ('False', 'const', 'queue_poll', ('body[28]', 'body[19]', 'test', 'comparators[0]')),
    ('False', 'const', 'queue_poll', ('body[28]', 'body[21]', 'value', 'keywords[5]', 'value')),
    ('False', 'const', 'team_queue_poll', ('body[18]', 'body[3]', 'value')),
    ('False', 'const', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]', 'value', 'keywords[8]', 'value', 'args[0]', 'values[1]')),
    ('False', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'test', 'comparators[0]')),
    ('False', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[1]', 'value')),
    ('False', 'const', 'team_queue_poll', ('body[40]', 'body[3]', 'value')),
    ('False', 'const', 'team_queue_poll', ('body[61]', 'test', 'comparators[0]')),
    ('None', 'const', '_admission_key', ('body[0]', 'value', 'elts[1]', 'body')),
    ('None', 'const', '_admission_key', ('body[0]', 'value', 'elts[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_admission_key', ('returns', 'slice', 'elts[1]', 'right')),
    ('None', 'const', '_asm_sqlstate', ('body[3]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_asm_sqlstate', ('body[3]', 'body[3]', 'body[0]', 'value', 'args[2]')),
    ('None', 'const', '_asm_sqlstate', ('body[3]', 'body[4]', 'value', 'args[0]', 'args[2]')),
    ('None', 'const', '_asm_sqlstate', ('body[3]', 'body[5]', 'value', 'args[0]', 'args[2]')),
    ('None', 'const', '_asm_sqlstate', ('body[4]', 'value')),
    ('None', 'const', '_assert_no_service_subject', ('returns',)),
    ('None', 'const', '_baseline', ('body[2]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_baseline', ('body[6]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_clean_map', ('body[1]', 'body[0]', 'value')),
    ('None', 'const', '_clean_map', ('body[4]', 'value', 'values[1]')),
    ('None', 'const', '_credit_bet_fighter_tax', ('args', 'args[5]', 'annotation', 'right')),
    ('None', 'const', '_credit_bet_fighter_tax', ('args', 'defaults[0]')),
    ('None', 'const', '_credit_bet_fighter_tax', ('body[4]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_credit_bet_fighter_tax', ('returns',)),
    ('None', 'const', '_credit_team_bet_fighter_tax', ('returns',)),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[12]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[0]', 'value', 'keywords[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[2]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[14]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[13]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'test', 'values[3]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'test', 'values[1]', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[15]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[2]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[3]', 'value', 'values[4]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[6]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[7]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'test', 'values[2]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[14]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[17]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[20]', 'body[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[24]', 'body[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[24]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[26]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[32]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[4]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[2]', 'value', 'args[0]', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[5]', 'body[0]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[34]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[48]', 'value')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[5]', 'test', 'comparators[0]')),
    ('None', 'const', '_ffa_queue_poll_inner', ('body[7]', 'test', 'comparators[0]')),
    ('None', 'const', '_formation_lease_conflict', ('args', 'kw_defaults[0]')),
    ('None', 'const', '_formation_lease_conflict', ('body[2]', 'test', 'comparators[0]')),
    ('None', 'const', '_formation_lease_conflict', ('body[3]', 'body[0]', 'test', 'comparators[0]')),
    ('None', 'const', '_formation_lease_conflict', ('body[3]', 'body[2]', 'test', 'comparators[0]')),
    ('None', 'const', '_formation_lease_conflict', ('body[4]', 'value')),
    ('None', 'const', '_group_region', ('args', 'kw_defaults[0]')),
    ('None', 'const', '_group_region', ('args', 'kw_defaults[2]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]', 'value', 'orelse')),
    ('None', 'const', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[3]', 'body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[3]', 'test', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[0]', 'value', 'args[1]', 'elts[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[0]', 'value', 'args[1]', 'elts[1]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[0]', 'value', 'args[1]', 'elts[2]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[1]', 'body[0]', 'handlers[0]', 'body[0]', 'value')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[2]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'values[3]', 'orelse')),
    ('None', 'const', '_group_region', ('body[2]', 'body[5]', 'body[4]', 'value', 'args[0]', 'values[3]', 'test', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[3]', 'body[0]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', '_group_region', ('body[7]', 'test', 'comparators[0]')),
    ('None', 'const', '_lease_acquire', ('args', 'defaults[0]')),
    ('None', 'const', '_lease_acquire_many', ('args', 'defaults[0]')),
    ('None', 'const', '_lease_acquire_many', ('body[1]', 'value', 'args[0]', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('None', 'const', '_lease_admission_gate', ('args', 'defaults[0]')),
    ('None', 'const', '_lease_admission_gate', ('body[11]', 'value', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('None', 'const', '_lease_admission_gate', ('body[17]', 'body[4]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_lease_admission_gate', ('body[1]', 'value', 'args[0]', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('None', 'const', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'body[0]', 'cause')),
    ('None', 'const', '_lease_admission_gate', ('body[9]', 'value', 'args[0]', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('None', 'const', '_lock_queue_rows_ordered', ('args', 'kw_defaults[0]')),
    ('None', 'const', '_lock_queue_rows_ordered', ('body[3]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_lock_queue_rows_ordered', ('body[4]', 'body[0]', 'test', 'comparators[0]')),
    ('None', 'const', '_lock_queue_rows_ordered', ('returns',)),
    ('None', 'const', '_lock_snapshot_rows', ('args', 'kw_defaults[0]')),
    ('None', 'const', '_lock_snapshot_rows', ('args', 'kw_defaults[1]')),
    ('None', 'const', '_lock_snapshot_rows', ('body[2]', 'iter', 'args[0]', 'generators[0]', 'ifs[0]', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_lock_snapshot_rows', ('returns',)),
    ('None', 'const', '_pick', ('body[0]', 'test', 'comparators[0]')),
    ('None', 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'values[2]', 'orelse')),
    ('None', 'const', '_pick', ('body[10]', 'body[0]', 'value', 'elt', 'values[3]', 'orelse')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[2]')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[3]')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[4]')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[5]')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[6]')),
    ('None', 'const', '_pick', ('body[11]', 'value', 'values[7]')),
    ('None', 'const', '_pick', ('body[18]', 'body[5]', 'value', 'orelse', 'orelse')),
    ('None', 'const', '_pick', ('body[5]', 'body[3]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_pick', ('body[5]', 'body[5]', 'value', 'orelse')),
    ('None', 'const', '_pick', ('body[8]', 'body[0]', 'test', 'comparators[0]')),
    ('None', 'const', '_player_body_color', ('body[2]', 'body[0]', 'value', 'elts[0]')),
    ('None', 'const', '_player_body_color', ('body[2]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_player_body_color', ('body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_player_body_color', ('body[3]', 'value', 'elts[0]', 'values[1]')),
    ('None', 'const', '_player_body_color', ('body[3]', 'value', 'elts[1]', 'values[1]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'orelse')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]', 'value', 'test', 'values[2]', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'test', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[2]', 'test', 'comparators[0]')),
    ('None', 'const', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'test', 'comparators[0]')),
    ('None', 'const', '_region_current', ('body[1]', 'body[0]', 'value')),
    ('None', 'const', '_region_mode_of', ('body[2]', 'body[0]', 'value', 'orelse')),
    ('None', 'const', '_region_pings_newer', ('body[1]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_region_pings_newer', ('body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_region_pings_newer', ('body[2]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_request_mod_version', ('body[1]', 'body[0]', 'value', 'body', 'args[2]')),
    ('None', 'const', '_request_mod_version', ('body[1]', 'body[0]', 'value', 'orelse')),
    ('None', 'const', '_request_mod_version', ('body[1]', 'body[0]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', '_request_mod_version', ('body[1]', 'handlers[0]', 'body[0]', 'value')),
    ('None', 'const', '_return_stake_exactly', ('body[2]', 'test', 'comparators[0]')),
    ('None', 'const', '_return_stake_exactly', ('returns',)),
    ('None', 'const', '_rules_for_members', ('args', 'defaults[0]')),
    ('None', 'const', '_rules_for_members', ('args', 'defaults[1]')),
    ('None', 'const', '_rules_for_members', ('body[3]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_rules_for_members', ('body[3]', 'body[1]', 'test', 'values[2]', 'comparators[0]')),
    ('None', 'const', '_rules_members', ('body[3]', 'value', 'value', 'elts[1]')),
    ('None', 'const', '_rules_normalize', ('body[2]', 'body[0]', 'handlers[0]', 'body[0]', 'value')),
    ('None', 'const', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_service_player_uuids', ('body[4]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[1]', 'value')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[2]', 'value', 'orelse', 'elts[0]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[2]', 'value', 'orelse', 'elts[1]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[3]', 'value', 'orelse', 'elts[0]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[3]', 'value', 'orelse', 'elts[1]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[4]', 'body[1]', 'value', 'orelse', 'elts[0]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'body[4]', 'body[1]', 'value', 'orelse', 'elts[1]')),
    ('None', 'const', '_stamp_team_series_colors', ('body[2]', 'handlers[0]', 'body[1]', 'value')),
    ('None', 'const', '_stamp_team_series_colors', ('returns',)),
    ('None', 'const', '_team_balance_rating', ('body[2]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_team_clear_dc_fallback_marker', ('returns',)),
    ('None', 'const', '_team_lock_family_pick', ('args', 'defaults[0]')),
    ('None', 'const', '_team_lock_family_pick', ('args', 'defaults[1]')),
    ('None', 'const', '_team_lock_family_pick', ('body[10]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_team_lock_family_pick', ('body[11]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_team_lock_family_pick', ('body[11]', 'test', 'comparators[0]')),
    ('None', 'const', '_team_lock_family_pick', ('body[2]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_team_lock_family_pick', ('body[4]', 'body[1]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_team_lock_family_pick', ('body[4]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', '_team_lock_family_pick', ('body[7]', 'body[1]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', '_team_lock_family_pick', ('body[8]', 'value')),
    ('None', 'const', '_team_quartet_lock', ('returns',)),
    ('None', 'const', '_team_relock_existing_series', ('body[2]', 'value', 'orelse')),
    ('None', 'const', '_team_relock_existing_series', ('body[2]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', '_team_resolve_live_family', ('args', 'defaults[0]')),
    ('None', 'const', '_team_resolve_live_family', ('args', 'defaults[1]')),
    ('None', 'const', '_team_resolve_live_family', ('body[3]', 'body[0]', 'value', 'elts[1]')),
    ('None', 'const', '_team_resolve_live_family', ('body[7]', 'body[1]', 'value', 'elts[1]')),
    ('None', 'const', '_team_resolve_live_family', ('body[7]', 'test', 'comparators[0]')),
    ('None', 'const', '_team_series_resumable', ('body[6]', 'body[0]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'anchor_fresh', ('body[1]', 'test', 'comparators[0]')),
    ('None', 'const', 'held_overlap', ('body[2]', 'body[3]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'home_of', ('body[2]', 'body[0]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[14]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[15]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[2]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[3]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[6]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]', 'value', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[16]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[19]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[0]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[10]', 'body[1]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[2]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[13]', 'test', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[1]', 'body[0]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[21]', 'body[5]', 'body[0]', 'value')),
    ('None', 'const', 'ovt_queue_poll', ('body[23]', 'value', 'values[0]', 'args[1]')),
    ('None', 'const', 'ovt_queue_poll', ('body[4]', 'test', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[7]', 'test', 'comparators[0]')),
    ('None', 'const', 'ovt_queue_poll', ('body[9]', 'test', 'comparators[0]')),
    ('None', 'const', 'pick_region_for_group', ('args', 'kw_defaults[3]')),
    ('None', 'const', 'queue_poll', ('body[22]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[1]', 'value', 'orelse')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[1]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[10]', 'value', 'body')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[10]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[11]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[12]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[9]', 'value', 'body')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[10]', 'body[5]', 'value', 'keywords[9]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[1]', 'value')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[1]', 'value', 'generators[0]', 'ifs[0]', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[7]', 'value', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[1]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'test', 'left', 'value', 'keywords[0]', 'value', 'elts[0]', 'elts[1]')),
    ('None', 'const', 'queue_poll', ('body[25]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[27]', 'value')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[14]', 'body[1]', 'value')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[14]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[14]', 'test', 'values[2]', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[16]', 'body[2]', 'value')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[16]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[19]', 'test', 'left', 'value', 'args[3]')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[1]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[8]', 'value', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', 'queue_poll', ('body[28]', 'body[9]', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[32]', 'value', 'keywords[3]', 'value', 'test', 'comparators[0]')),
    ('None', 'const', 'queue_poll', ('body[32]', 'value', 'keywords[4]', 'value', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[18]', 'test', 'values[1]', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]', 'body[0]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]', 'value', 'value', 'args[1]', 'values[3]', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[3]', 'value', 'args[0]', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[4]', 'value', 'args[0]', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]', 'value', 'keywords[11]', 'value', 'orelse')),
    ('None', 'const', 'team_queue_poll', ('body[23]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[11]', 'value')),
    ('None', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[2]', 'body[0]', 'value')),
    ('None', 'const', 'team_queue_poll', ('body[31]', 'body[2]', 'body[1]', 'value', 'args[0]', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', 'team_queue_poll', ('body[31]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[32]', 'value')),
    ('None', 'const', 'team_queue_poll', ('body[34]', 'body[13]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[34]', 'body[1]', 'value', 'args[0]', 'func', 'value', 'func', 'value', 'value', 'args[1]', 'keywords[0]', 'value')),
    ('None', 'const', 'team_queue_poll', ('body[34]', 'body[8]', 'test', 'values[0]', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[44]', 'value', 'orelse')),
    ('None', 'const', 'team_queue_poll', ('body[45]', 'value', 'orelse')),
    ('None', 'const', 'team_queue_poll', ('body[5]', 'test', 'comparators[0]')),
    ('None', 'const', 'team_queue_poll', ('body[8]', 'test', 'comparators[0]')),
    ('True', 'const', '_ffa_gather_decide', ('body[1]', 'body[0]', 'value', 'elts[0]')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[12]', 'value', 'values[14]', 'orelse')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[13]', 'body[2]', 'value')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]', 'body[0]', 'value')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'body[0]', 'value')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'body[0]', 'value')),
    ('True', 'const', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'body[0]', 'value')),
    ('True', 'const', '_lease_acquire_many', ('body[4]', 'body[0]', 'value', 'value', 'keywords[0]', 'value')),
    ('True', 'const', '_lease_acquire_many', ('body[5]', 'value')),
    ('True', 'const', '_lease_admission_gate', ('body[2]', 'body[1]', 'value', 'elts[0]')),
    ('True', 'const', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[1]', 'body[0]', 'value')),
    ('True', 'const', '_region_pings_newer', ('body[1]', 'body[0]', 'body[0]', 'value')),
    ('True', 'const', '_rules_for_queue_match', ('body[4]', 'value', 'values[0]')),
    ('True', 'const', '_rules_json', ('body[4]', 'value', 'keywords[1]', 'value')),
    ('True', 'const', '_team_lock_family_pick', ('body[9]', 'body[0]', 'value', 'keywords[1]', 'value')),
    ('True', 'const', 'ovt_queue_poll', ('body[16]', 'body[5]', 'body[0]', 'value')),
    ('True', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]', 'body[0]', 'value')),
    ('True', 'const', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'body[0]', 'value')),
    ('True', 'const', 'ovt_queue_poll', ('body[21]', 'body[14]', 'value')),
    ('True', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[14]', 'value', 'keywords[5]', 'value')),
    ('True', 'const', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[7]', 'value')),
    ('True', 'const', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]', 'value', 'value', 'keywords[1]', 'value')),
    ('True', 'const', 'team_queue_poll', ('body[39]', 'value')),
    ('\'(mode, group_id) of this player\\\'s LIVE lease, or None. Errors PROPAGATE.\\n\\n    A sibling of _lease_live_mode, NOT a strictening of it. That helper turns a\\n    read failure into "free", and its callers -- ranked/team/OVT/FFA join, team\\n    and OVT and FFA lobby create and join, same-mode husk reclamation, FFA\\n    poll\\\'s own expired-lease self-release -- are all built on that polarity;\\n    making it strict globally would newly abort every one of them on a lease\\n    read fault. A fail-soft helper becomes a bug the moment a caller with the\\n    opposite polarity reuses it (#412), so formation gets its own reader.\\n\\n    Here the polarity is inverted deliberately: a formation that cannot READ\\n    the leases must not conclude the players are free. Failing to form is an\\n    availability cost; forming twice is the defect this change exists to\\n    remove.\\n\\n    Note the consequence for deploy order -- this has no savepoint and no\\n    catch, so queue_leases must EXIST before this code is live. Surviving that\\n    window is precisely what _lease_live_mode\\\'s savepoint was written for.\\n    \'', 'const', '_lease_live_claim_strict', ('body[0]', 'value')),
    ('\'B = the mode of the members\\\' non-empty homes; legacy_pick when nobody\\n    has one. Tie policy (R3 as revised by c2 H1): among tied modal homes,\\n    first the ones at least one OTHER member\\\'s map contains (a home nobody\\n    else can even reach is never the room\\\'s default), then the lexically\\n    first code \u2014 never the numbers. A tied home that won on the members\\\'\\n    ping totals became the baseline WITHOUT passing the admission gate, and\\n    the gate is what bounds what the rest of the room pays; from a\\n    map-independent anchor every departure, the numerically best tied home\\n    included, is judged by the same arithmetic. Returns (B, tie) with tie\\n    None (no tie), "measured" (peer measurement alone decided) or\\n    "lexical".\'', 'const', '_baseline', ('body[0]', 'value')),
    ('\'First member whose live lease forbids this formation, else None.\\n\\n    members   iterable of (steam_id, player_id) for the WHOLE roster -- every\\n              identity this transaction will write, not merely the fresh ones.\\n    allow     (mode, group_id) this formation is entitled to supersede, i.e.\\n              its OWN exact predecessor. Hosted Start\\\'s seats already hold a\\n              same-mode lobby lease BY DESIGN, so a blanket "reject any live\\n              lease" would refuse every healthy Start -- fail-closed in the\\n              most operationally severe way available, and a guard is judged by\\n              what its refusal costs (#430).\\n    allow_any several such predecessors, for a formation whose own history is\\n              not single-valued. 1v1 room issuance is the case: the pass that\\n              ISSUES the room holds (ranked, NULL) from discovery, and every\\n              replay of that same branch already holds (ranked, series.id)\\n              from the issuing pass. Both are that pair\\\'s own predecessor.\\n    require   every member must hold one of the admissible pairs; absent is\\n              NOT admissible.\\n              This is queue_ready and delayed activation, which refresh a\\n              possibly stale pair: an expired lease there means the pair is\\n              already gone, and proceeding would resurrect it and make it\\n              cross-mode eligible again.\\n\\n    Returns (steam_id, reason) for the first offender, or None when the whole\\n    roster is admissible. Reasons are stable strings so a test can tell the\\n    three policies apart rather than merely observing that something refused.\\n    \'', 'const', '_formation_lease_conflict', ('body[0]', 'value')),
    ('\'Return one refunded stake by the EXACT amount, or refuse and move nothing.\\n\\n    ONE definition for every refund in this file, because every one of them\\n    used to write `gold_spent = GREATEST(0, COALESCE(gold_spent,0) - :amt)`\\n    beside a ledger row for the WHOLE stake. The clamp is silent, and what it\\n    produces is not a smaller refund: with `gold_spent = 5` and a 10-gold\\n    stake the ledger records 10 returned while the balance moves 5, so the\\n    ledger\\\'s sum and `gold_earned - gold_spent` stop agreeing and the player is\\n    5 gold short with nothing in the record that says so.\\n\\n    #326 is the rule this restores: a money mutation is a DB delta, and a\\n    delta is the amount or it is wrong. The cover predicate lives IN the\\n    statement, so the check and the write are one operation no concurrent\\n    debit can get between, and the RETURNING is what says whether it applied\\n    -- `0` is a real balance, so the ABSENCE of a row is the only signal read\\n    here.\\n\\n    A balance that cannot cover the exact delta is a corrupt state, so this\\n    RAISES `StakeRefundRefused` rather than paying part of it. Every caller\\n    CLAIMS the stake with a conditional `UPDATE ... RETURNING` in THIS\\n    transaction, so the raise takes the claim down with it and the wager goes\\n    back to unsettled for the next pass to find.\\n\\n    WHAT A REFUSAL COSTS IS THE THING TO JUDGE IT BY (#430), and it is not the\\n    same at the four kinds of call site. Each is named from a resolved caller\\n    rather than covered by one sentence, because the first draft of this list\\n    was written from the shape it expected and got two of them wrong:\\n\\n      * AN UNGUARDED REQUEST HANDLER -- `admin_reverse_series` through\\n        `_refund_series_bets`, and `cancel_lobby_bet` through\\n        `_lobby_bet_pay_refund` -- surfaces it as a 500 over a transaction\\n        that rolled back. Nothing moved, the operator or the bettor retries,\\n        and that is the conservative direction.\\n      * THE CONFIG-SKEW SETTLEMENT does better and deliberately: it catches\\n        the refusal and re-raises it as a 503 `FfaReportRefusal` carrying the\\n        lobby\\\'s progress, so the client\\\'s outbox RETRIES a report that\\n        changed nothing instead of spending it on a 4xx. The settlement does\\n        not commit either way.\\n      * A SAVEPOINTED BATCH (`_refund_lobby_bets`, `_refund_ffa_lobby_bets`,\\n        `_reconcile_team_series_bets`, and so the team reversal that calls the\\n        last of them) loses its own batch and nothing outside it; the caller\\\'s\\n        disband, leave or reversal still commits and the janitor retries.\\n      * A BATCH SWEEP over rows belonging to DIFFERENT players\\n        (`_flush_lobby_bet_refunds`, `_prune_stale_series`) must SKIP the\\n        refused item and keep going. This is why the refusal has its own\\n        class: those two select their work ordered and unfiltered, so a single\\n        uncoverable row at the head of the order is a permanent block on every\\n        other player\\\'s refund if the sweep stops at it. Both now record the\\n        item, log it and take the next one, which is the per-item degradation\\n        #204 asks for -- and neither treats a DBAPI failure that way, because\\n        there is no next row to take when the transaction itself is gone.\\n\\n    The per-bettor loop inside `_refund_series_bets` is not a fifth shape: its\\n    claim covers every bettor of one series in one statement, so a refusal\\n    there is that series, atomically, and it is the caller above it that\\n    decides what the series costs.\\n\\n    The ledger row is added AFTER the balance has moved, so neither half of\\n    the record can be committed without the other, whichever path called.\\n\\n    It writes the ledger row itself, so no caller can keep one half of the\\n    record without the other.\\n\\n    `:amt` is CAST and `:pid` deliberately is NOT, which is the one place this\\n    file departs from "type every bind" (#448) and it departs for a reason the\\n    live control proves rather than asserts. Compared against `id`, the\\n    parameter is typed by that column, and the driver then accepts both shapes\\n    callers arrive with -- a `UUID` off an ORM row and a `str` off a mappings\\n    row. Wrapping it as `CAST(:pid AS uuid)` retypes the parameter itself to\\n    text, and every `UUID`-passing caller becomes a driver type error at the\\n    moment a refund is due. Whichever way it is written, the column is never\\n    the thing cast: casting `id` is what turns this into a sequential scan.\'', 'const', '_return_stake_exactly', ('body[0]', 'value')),
    ('\'SQL for "this caps column carries HOLD_CAPS_TOKEN" (a comma list, the\\n    exact token; bind :tok = HOLD_CAPS_TOKEN): the one test the latch applies\\n    per member. A gate deciding who reads the flag evaluates it inside the\\n    statement that reads the flag, so the flag and the caller\\\'s token state\\n    come from one snapshot; for a caller without the token the key is absent,\\n    not false, and a released client reads byte for byte what trunk answers\\n    (bar BV-A, the trunk oracle).\'', 'const', 'caps_token_sql', ('body[0]', 'value')),
    ('\'Serialize every same-four series CREATION/RESUME funnel (r1 finding\\n    4): the queue matcher and the signed continuation endpoint could both\\n    read "no live same-four series" and insert disjoint rows. Both funnels\\n    take this xact-scoped advisory lock BEFORE their live recheck.\\n    Ordering note (A1, 2026-09-17): BOTH funnels now take the four per-steam\\n    identity locks FIRST -- the continuation always did, and the queue poll\\n    acquires them at its phase barrier before it touches a queue row. So two\\n    callers over one quartet contend on identities, and the one that loses is\\n    holding nothing at all. The poll additionally holds its four team_queue\\n    tuples when it takes this lock, which cannot close a cycle: reaching those\\n    tuples requires the same four identities the other caller would need.\'', 'const', '_team_quartet_lock', ('body[0]', 'value')),
    ('\'Take FOR UPDATE locks on the given queue rows in a deterministic GLOBAL\\n    order (ascending player_id), one statement per row.\\n\\n    `before_each`, when given, is awaited before each row\\\'s statement: a caller\\n    under one deadline re-arms its lock_timeout and statement_timeout there\\n    from what is left of that deadline, so the row waits together spend one\\n    budget (merge pass 6, R2-C-L1; _asm_reform_formation). The order and the\\n    statements are the same with or without it.\\n\\n    Why this exists: queue_poll and queue_ready both used to lock the CALLER\\\'s\\n    row first and then the opponent\\\'s. Two players polling at the same instant\\n    therefore grabbed the same two rows in opposite orders \u2014 textbook ABBA.\\n    Postgres logged it twice on 2026-07-26 07:02 ("deadlock detected ... while\\n    locking tuple in relation ranked_queue"), and the loser\\\'s request 500s; the\\n    client silently retries its poll 3s later, so it reads as a stutter in\\n    matchmaking rather than an error anyone reports.\\n\\n    Why one statement per row instead of a single\\n    `WHERE player_id = ANY(...) ORDER BY player_id FOR UPDATE`: that form relies\\n    on the planner putting LockRows above the Sort so rows lock in sorted order.\\n    It normally does, but it is a plan-shape assumption, and this is the one\\n    place where being wrong reintroduces exactly the bug we are fixing. Separate\\n    ordered statements are unambiguous and each is a single indexed lookup.\\n\\n    CRITICAL: the caller must NOT already hold a lock on any of these rows.\\n    Discover the peer ids with an UNLOCKED read, call this, then re-read the\\n    authoritative state under the locks \u2014 a lock acquired before this runs puts\\n    us right back into an inconsistent order.\\n\\n    Missing rows are simply not locked; callers revalidate after the re-read.\\n    \'', 'const', '_lock_queue_rows_ordered', ('body[0]', 'value')),
    ('\'The room\\\'s region for a group issuance: (pick, why, detail).\\n\\n    Disclosure (both sentences travel together \u2014 docstring, log, changelog;\\n    stated at the production constants, margin 20 / regret 30): A move needs\\n    either half the room to gain 20 ms or nobody to lose more than 30 ms, and\\n    then happens only if it lowers the room\\\'s total ping, or keeps the total\\n    and lowers its worst ping \u2014 so a majority can move a minority, but never\\n    by more than the majority gains. The room may be a region no member\\n    calls home.\\n\\n    Inputs. ``members``: seat-ordered dicts ``{"id", "home", "map",\\n    "measured_at"}`` \u2014 ``home`` is what the caller says the seat\\\'s home is\\n    (main derives it from the seat\\\'s own map through ``home_of`` and only\\n    without a map uses the queue row\\\'s region), ``map`` is ``{code: ms}`` or\\n    None, ``measured_at`` an epoch float or None. ``live_regions``: the codes the server considers real\\n    (candidates must be in it; the baseline need not be). ``volumes``: code ->\\n    45-day volume, a tie-break only. ``legacy_pick``: the mode\\\'s existing pick,\\n    used only when no member has a home, or when this function fails.\\n\\n    The rule.\\n      1. B (baseline) = the mode of the members\\\' non-empty homes; the region\\n         every member would get today. Tie among modal homes: the ones at\\n         least one other member\\\'s map contains, then the lexically first\\n         code \u2014 never the members\\\' ping totals (c2 H1: a tied home must not\\n         become the baseline on a ping advantage the gate never judged).\\n         ``detail["tie"]`` records ``measured``, ``lexical`` or None.\\n      2. Quorum: every member has a FRESH map (``now - measured_at <=\\n         max_age_s``) that contains B. Otherwise the verdict is B,\\n         ``why="quorum"``, and ``detail["seats"]`` says per seat why\\n         (``fresh|stale|absent|missing_baseline``). A seat whose cost at B is\\n         unknown can never be moved by the others\\\' numbers.\\n      3. Choosable = live_regions \u2229 (\u2229 over members of the map\\\'s codes). B is\\n         in every map by quorum and is admitted unconditionally.\\n      4. Admission of r \u2260 B: gain = members whose ping drops by at least\\n         ``margin_ms`` (``map[B] - map[r] >= margin_ms``); max_regret = the\\n         largest ``map[r] - map[B]`` over members. Admitted iff\\n         ``2*gain >= N`` (majority arm) OR ``max_regret <= regret_ms``\\n         (bounded arm). Pairs and solos go through the same arithmetic.\\n      5. Selection among the admitted: the lowest total ping, then the lowest\\n         worst, then the HIGHER volume, then the lexically first code. The\\n         room leaves B only for a strictly lower total, or an equal total\\n         with a strictly lower worst (R1: volume and code order only\\n         candidates that already beat B). ``why`` is "baseline" when the pick\\n         is B, "majority" when the majority arm admitted the winner (whether\\n         or not the bounded arm did too), "bounded" when only the regret arm\\n         admitted it.\\n\\n    Outcomes the rule can never reach (sum selection):\\n      * A lone far player never moves a 3+ room unless every other member\\n        pays at most ``regret_ms`` AND the room\\\'s total still falls \u2014 its own\\n        gain must exceed what the others pay, added up.\\n      * A non-majority move requires that nobody pays more than the bound;\\n        with the bound at 0 nobody pays anything \u2014 and a move that costs no\\n        one still happens when it lowers the total (R4).\\n      * A majority move never costs the minority more, in total, than the\\n        majority gains in total: the total must strictly fall. There is no\\n        separate cap; the majority\\\'s own gain is the cap.\\n      * A room with ANY seat lacking a fresh map that contains B never moves\\n        off B.\\n      * The room never leaves B for an equal total unless the worst seat\\n        strictly improves, and never on volume or code alone (R1).\\n      * The host\\\'s home has no role anywhere (H); a tie among modal homes\\n        falls to peer measurement, then to the documented lexical bias \u2014\\n        never to the members\\\' ping totals, so no tied home is ever the\\n        baseline on numbers the gate did not judge.\\n\\n    Never raises and never returns None: any exception inside the body yields\\n    ``(legacy_pick, "error", {"error": repr(exc)})``. Garbage map entries are\\n    dropped before use (see ``_clean_map``); a garbage ``measured_at`` makes\\n    the seat stale; a non-dict member is an absent seat; an empty room has no\\n    quorum. ``detail`` carries ``baseline, n, sum_b, sum_pick, worst_b,\\n    worst_pick, gain, max_regret, candidates`` (selection-ordered\\n    ``{region, sum, worst, gain, max_regret, admitted_by}``), ``seats``\\n    (seat-ordered ``{id, state, cost_b, cost_pick}``) and ``tie`` \u2014 enough to\\n    reconstruct the pick line after the queue rows are gone. The verdict\\n    (pick, why) is invariant under member order.\'', 'const', 'pick_region_for_group', ('body[0]', 'value')),
    ('\'\\n    Poll queue status. Handles searching, matching, mutual ready-up, and timeouts.\\n    Uses SELECT FOR UPDATE SKIP LOCKED for race-safe matching.\\n    Elo range: \xb1100 / \xb1200@30s / \xb1400@60s / \xb1800@120s.\\n    Ready timeout: READY_TIMEOUT_SECONDS (90 s) \u2014 if both players don\\\'t ready\\n    up, the match is canceled.\\n\\n    v1.40.1: requires the caller\\\'s OWN valid Steam session (fail-closed \u2014\\n    _strict_steam_session_ok, the same gate the link-code and artist\\n    endpoints use; _check_steam_session is a compatibility gate keyed on the\\n    client-supplied X-Mod-Version and is not a boundary). The poll answers with\\n    this seat\\\'s own pairing and, at ready-up, the issued room name and region,\\n    so it is served only to the seat that owns the row. The 401 detail literal\\n    is LOAD-BEARING: ApiClient.HandleSessionReject matches "session_required"\\n    to re-mint; the client leaves the queue once its polls have been refused\\n    for 30 s straight (at least three, spanning a session re-mint cycle;\\n    refusals of a superseded credential do not count). Every live client\\n    (>= 1.40.0) stamps its token on every request WHILE IT HOLDS ONE \u2014 a seat\\n    before its first mint, or whose session was refused, is refused here until\\n    the heartbeat re-mints (impl note 65). Presence is touched only AFTER the\\n    gate \u2014 an unaccepted request must not count as an online seat.\\n    \'', 'const', 'queue_poll', ('body[0]', 'value')),
    ('\'{region: matches played there in the last REGION_LIVE_WINDOW_DAYS}.\\n\\n    Two jobs in one query. (a) LIVENESS: a region nobody has played in recently\\n    is not offered, because pinning a region Photon has retired makes both\\n    clients fail to connect identically and both forfeit. (b) The last\\n    numeric tie-break, standing in for "which region is Photon actually\\n    serving well".\\n\\n    The VERDICT specified a 90-day volume for (b); this uses the 45-day\\n    liveness count instead so both jobs come from one query. Stated precisely\\n    rather than hand-waved: the two windows do NOT produce the same ordering\\n    everywhere (measured Aug 13, `au` sits 7th over 120d and 10th over 45d),\\n    but the top six by volume \u2014 ussc, us, eu, usw, ru, cae, i.e. every region\\n    this community actually plays in \u2014 are identically ordered in both, and\\n    this tie-break is only reached when two regions have the SAME minimax cost\\n    AND the same total, which needs identical medians. The window cannot\\n    plausibly decide a pairing on its own.\\n\\n    Deliberately NOT filtered on invalidated_at: an invalidated match still\\n    proves Photon served that region.\\n    \'', 'const', '_region_candidate_volumes', ('body[0]', 'value')),
    ('_form_attempt', 'store', '_ffa_queue_poll_inner', ('body[33]', 'target')),
    ('_form_attempt', 'store', 'ovt_queue_poll', ('body[21]', 'target')),
    ('_form_attempt', 'store', 'queue_poll', ('body[28]', 'target')),
    ('_form_left', 'store', 'team_queue_poll', ('body[30]', 'targets[0]')),
    ('_form_left', 'store', 'team_queue_poll', ('body[31]', 'body[2]', 'body[0]', 'target')),
    ('_form_left', 'store', 'team_queue_poll', ('body[33]', 'targets[0]')),
    ('_form_left', 'store', 'team_queue_poll', ('body[34]', 'body[0]', 'target')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[1]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[2]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[2]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[13]', 'body[8]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[3]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[3]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[14]', 'body[16]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[1]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[15]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[21]', 'body[0]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[28]', 'body[0]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[31]', 'body[0]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[46]', 'value', 'value')),
    ('commit', 'end', '_ffa_queue_poll_inner', ('body[7]', 'body[0]', 'value', 'value')),
    ('commit', 'end', '_team_relock_existing_series', ('body[8]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[15]', 'body[6]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[16]', 'body[12]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[17]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[36]', 'value', 'value')),
    ('commit', 'end', 'ovt_queue_poll', ('body[9]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[14]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[16]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[16]', 'body[3]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[16]', 'body[7]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[23]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[10]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[11]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[2]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[3]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[3]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[11]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[25]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[26]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[28]', 'body[1]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[28]', 'body[20]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[31]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[6]', 'value', 'value')),
    ('commit', 'end', 'queue_poll', ('body[8]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[11]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[17]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[18]', 'body[2]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[18]', 'body[5]', 'body[2]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[18]', 'body[7]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[4]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[6]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[4]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[14]', 'body[5]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[15]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[1]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[19]', 'body[4]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[23]', 'body[1]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[24]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[25]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[31]', 'body[3]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[48]', 'body[0]', 'value', 'value')),
    ('commit', 'end', 'team_queue_poll', ('body[62]', 'value', 'value')),
    ('others', 'store', 'team_queue_poll', ('body[32]', 'targets[0]')),
    ('others', 'store', 'team_queue_poll', ('body[34]', 'body[13]', 'body[2]', 'body[0]', 'targets[0]')),
    ('others', 'store', 'team_queue_poll', ('body[34]', 'body[14]', 'targets[0]')),
    ('others', 'store', 'team_queue_poll', ('body[34]', 'body[2]', 'body[0]', 'targets[0]')),
    ('others', 'store', 'team_queue_poll', ('body[34]', 'body[8]', 'body[2]', 'targets[0]')),
    ('rollback', 'end', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', '_ffa_queue_poll_inner', ('body[33]', 'orelse[0]', 'value', 'value')),
    ('rollback', 'end', '_ffa_queue_poll_inner', ('body[34]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', '_ffa_queue_poll_inner', ('body[45]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', '_team_relock_existing_series', ('body[4]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[21]', 'body[10]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[21]', 'orelse[0]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[22]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[25]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'ovt_queue_poll', ('body[35]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[17]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[28]', 'body[14]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[28]', 'body[16]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[28]', 'body[19]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[28]', 'body[2]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'queue_poll', ('body[28]', 'orelse[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[31]', 'body[2]', 'body[6]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[34]', 'body[13]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[34]', 'body[8]', 'body[1]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[34]', 'body[9]', 'body[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[34]', 'orelse[0]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[35]', 'body[3]', 'value', 'value')),
    ('rollback', 'end', 'team_queue_poll', ('body[61]', 'body[0]', 'value', 'value')),
})
A1_BINDINGS = A1_BINDINGS | A1_POSITIONS | frozenset({("<positions>",)})

# The ORDER rule (closed_walk.orders; W30b at the round-9 merge, the gr
# child's question 2): the position rule left free the order of
# consecutive statements none of which holds a position (39 such runs,
# RF/r9/tip/order_runs.py). A1_ORDERS holds, for every span of A1_SPANS,
# every statement's order key: (shape_grammar.header_digest of the
# statement, 'order', the span's name, the index path; the root at ()).
# TAKEN ONCE from the real spans at the merge by RF/r9/tip/order_rule_a1.py
# (1537 keys) and frozen; never regenerated. A1_BINDINGS carries the marker
# ('<orders>',) that switches the rule on, and every key.
A1_ORDERS = frozenset({
    ('000d082e6f558169', 'order', 'team_queue_poll', ('body[17]', 'body[0]')),
    ('000d082e6f558169', 'order', 'team_queue_poll', ('body[18]', 'body[5]', 'body[0]')),
    ('000d082e6f558169', 'order', 'team_queue_poll', ('body[23]', 'body[0]')),
    ('00348c3d2ab0e55e', 'order', '_team_balance_rating', ('body[3]',)),
    ('0034cf60722e366a', 'order', '_region_candidate_volumes', ()),
    ('005081a6fd2f842f', 'order', '_pick', ('body[8]', 'body[2]')),
    ('0066e18887b779a8', 'order', 'queue_poll', ('body[14]',)),
    ('0066e18887b779a8', 'order', 'queue_poll', ('body[16]', 'body[7]')),
    ('0074193dd42d7b75', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]')),
    ('00f4dfea0bcf1696', 'order', '_group_region', ('body[2]', 'body[1]')),
    ('01298b9b3dc14cc3', 'order', '_ffa_queue_poll_inner', ('body[33]',)),
    ('013ffe0d6a1959a6', 'order', '_balance_teams', ('body[4]', 'body[1]')),
    ('015bd9c5eebf2f8a', 'order', '_group_region', ('body[2]', 'body[7]', 'body[0]')),
    ('01cec40bd15021c0', 'order', '_rules_members', ('body[5]',)),
    ('01e5a12c99bba52a', 'order', '_rules_members', ('body[4]',)),
    ('021a26160cb9a7e7', 'order', 'team_queue_poll', ('body[34]', 'body[1]')),
    ('02d7a747921a329a', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[11]')),
    ('02d7a747921a329a', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[2]', 'body[0]')),
    ('02e1378a2b621f2a', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[5]')),
    ('02e78a62449d41d3', 'order', '_lease_acquire_many', ('body[2]',)),
    ('0300e88d40f621b0', 'order', 'queue_poll', ('body[22]', 'body[4]')),
    ('03d23007d36dedf8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[0]')),
    ('04f747a6a6230c7c', 'order', '_lease_live_claim_strict', ('body[1]',)),
    ('055cc680d3a98c49', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[0]')),
    ('0563c09f9c73a997', 'order', 'ovt_queue_poll', ('body[8]',)),
    ('05735a02d59b177e', 'order', '_clean_map', ('body[4]',)),
    ('05e98e1c0a0bb96a', 'order', '_reconcile_team_series_bets', ()),
    ('05eed66686a6e56e', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[0]')),
    ('0632018cdfaee96a', 'order', 'team_queue_poll', ('body[34]', 'body[2]', 'body[0]')),
    ('063b8b246d7cbca0', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]')),
    ('0662c662e4e9fa89', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[7]')),
    ('06a4e967b4af653e', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[5]')),
    ('06a4e967b4af653e', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[7]')),
    ('06a4e967b4af653e', 'order', 'team_queue_poll', ('body[19]', 'body[1]', 'body[3]')),
    ('06a4e967b4af653e', 'order', 'team_queue_poll', ('body[19]', 'body[4]', 'body[2]')),
    ('06c4254f023b74a7', 'order', 'team_queue_poll', ('body[17]',)),
    ('06c7b2f15e2db744', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[9]')),
    ('06cb43782306437c', 'order', '_asm_sqlstate', ('body[3]', 'body[2]')),
    ('06e1ae1629cfacac', 'order', '_team_resolve_live_family', ('body[3]', 'body[0]')),
    ('073c60e955e4ee16', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[9]')),
    ('0755e4cd2872008f', 'order', '_region_current', ()),
    ('07eba966d2173891', 'order', '_lock_snapshot_rows', ('body[3]',)),
    ('08108cc2109bd2b0', 'order', '_group_region', ('body[2]', 'body[5]')),
    ('08751af5595973b0', 'order', '_lease_admission_gate', ('body[17]', 'body[3]')),
    ('0927c1ec7d5bac08', 'order', '_assert_no_service_subject', ('body[3]',)),
    ('0a0ab79abcf92671', 'order', 'ovt_queue_poll', ('body[15]', 'body[7]')),
    ('0a3a861406e8db16', 'order', 'ovt_queue_poll', ('body[0]',)),
    ('0acd1d17beae68b5', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[1]')),
    ('0adbc64fad7f6f6d', 'order', 'team_queue_poll', ('body[19]', 'body[0]')),
    ('0b871e3ca7c7dd9d', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[15]')),
    ('0b98a87520e3d18f', 'order', '_pick', ('body[8]', 'body[2]', 'body[0]')),
    ('0bbe7380a5437170', 'order', 'queue_poll', ('body[28]', 'body[18]', 'body[0]')),
    ('0bddff088c2ccd23', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[1]')),
    ('0beb9475458075b3', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[15]')),
    ('0c302968e4f32907', 'order', '_pick', ('body[23]',)),
    ('0c3cce4b7c21fa38', 'order', '_service_player_uuids', ()),
    ('0c726c09c5011d52', 'order', '_region_pings_newer', ()),
    ('0cba3d4504635607', 'order', '_ffa_queue_poll_inner', ('body[24]',)),
    ('0cbdb2fb757783af', 'order', '_formation_lease_conflict', ('body[3]', 'body[3]')),
    ('0ccf023667b22f34', 'order', '_lease_acquire_many', ('body[4]',)),
    ('0cd717dffe903b9f', 'order', '_lock_queue_rows_ordered', ('body[3]', 'body[0]')),
    ('0db29e11722c64df', 'order', '_team_lock_family_pick', ('body[3]',)),
    ('0dc3aa4473be378d', 'order', '_ffa_queue_poll_inner', ('body[8]',)),
    ('0dc3aa4473be378d', 'order', 'ovt_queue_poll', ('body[10]',)),
    ('0dc3aa4473be378d', 'order', 'team_queue_poll', ('body[12]',)),
    ('0dd78fa326f6f2c3', 'order', '_rules_normalize', ('body[3]', 'body[0]', 'body[1]', 'body[0]')),
    ('0de1379122435e55', 'order', 'team_queue_poll', ('body[65]',)),
    ('0e4575bf12b26b27', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[3]')),
    ('0e6045c9397b042a', 'order', '_pick', ()),
    ('0f973ab494822839', 'order', '_pick', ('body[18]', 'body[6]')),
    ('0fc78572804568f3', 'order', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[0]')),
    ('100fd23a58053702', 'order', '_formation_lease_conflict', ('body[3]', 'body[2]')),
    ('105903d2ebbd9f98', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'body[2]')),
    ('10788b85f538e91a', 'order', 'held_overlap', ('body[2]', 'body[0]')),
    ('10c48682fe9fc609', 'order', '_lock_queue_rows_ordered', ('body[3]',)),
    ('10c524dc845ffd04', 'order', '_rules_for_members', ('body[4]',)),
    ('10e644c124acbd50', 'order', '_team_color_holders', ()),
    ('110b2d320cdd23e9', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[0]')),
    ('111abc31953933ca', 'order', 'queue_poll', ('body[28]', 'body[17]')),
    ('111abc31953933ca', 'order', 'team_queue_poll', ('body[59]',)),
    ('111b532fef5a680a', 'order', '_assert_no_service_subject', ('body[0]',)),
    ('111f2c5b6b99af9f', 'order', '_region_candidate_volumes', ('body[2]',)),
    ('112ea8b15e8f6d01', 'order', '_team_relock_existing_series', ('body[3]', 'body[0]')),
    ('1132926c289f0efe', 'order', '_assert_no_service_subject', ('body[1]',)),
    ('113d6c2c780c2b51', 'order', 'queue_poll', ('body[19]',)),
    ('1144e727d2313dd7', 'order', 'home_of', ()),
    ('1232db70e1c9e2e3', 'order', '_ffa_queue_poll_inner', ('body[12]', 'body[0]')),
    ('1232db70e1c9e2e3', 'order', 'ovt_queue_poll', ('body[14]', 'body[0]')),
    ('12377bf827c91375', 'order', 'team_queue_poll', ('body[34]', 'body[9]')),
    ('128b0458681d678f', 'order', '_ffa_queue_poll_inner', ('body[26]',)),
    ('12a01a477ab6dc96', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[2]')),
    ('12b75c43c79d8961', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]')),
    ('12d30d471631d42e', 'order', 'ovt_queue_poll', ('body[21]', 'body[14]')),
    ('12e967afa0ba7ebd', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[2]')),
    ('132c804f1a9eca4e', 'order', 'queue_poll', ('body[13]',)),
    ('136703a89a5dbeed', 'order', '_ffa_queue_poll_inner', ('body[7]',)),
    ('136703a89a5dbeed', 'order', 'ovt_queue_poll', ('body[9]',)),
    ('136703a89a5dbeed', 'order', 'queue_poll', ('body[28]', 'body[1]')),
    ('137061416a6ec21b', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[15]', 'body[0]')),
    ('1373814b290ac8c9', 'order', 'held_overlap', ('body[0]',)),
    ('137d12d251b19e1e', 'order', '_stamp_team_series_colors', ('body[0]',)),
    ('13be0c646d1bc12f', 'order', '_request_mod_version', ('body[1]', 'body[0]')),
    ('13d729b6da0ec0c2', 'order', '_group_region', ('body[5]',)),
    ('13ea567d04188626', 'order', 'queue_poll', ('body[28]', 'body[10]')),
    ('141201e4eff7dbec', 'order', '_ffa_queue_poll_inner', ('body[2]',)),
    ('141201e4eff7dbec', 'order', 'ovt_queue_poll', ('body[2]',)),
    ('141201e4eff7dbec', 'order', 'queue_poll', ('body[3]',)),
    ('141201e4eff7dbec', 'order', 'team_queue_poll', ('body[3]',)),
    ('14332dd3e2b5329f', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[0]')),
    ('143abdc0bdd04ee2', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]')),
    ('146aaca05b77eb36', 'order', '_team_series_resumable', ('body[5]',)),
    ('149b70a756c9fb62', 'order', '_ffa_queue_poll_inner', ('body[45]',)),
    ('14c73db9c40d66ba', 'order', 'queue_poll', ('body[28]', 'body[15]')),
    ('14ddac345e8eab66', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]')),
    ('14e7bd848b7d6c7c', 'order', '_baseline', ('body[8]', 'body[0]')),
    ('14f8e204f9d48ca4', 'order', 'team_queue_poll', ('body[49]',)),
    ('14fa293eeda8c5bb', 'order', 'team_queue_poll', ('body[58]', 'body[0]')),
    ('1516fc6a5f2bcdcd', 'order', '_credit_bet_fighter_tax', ('body[2]',)),
    ('1592348c4cbcdb5a', 'order', '_lease_admission_gate', ('body[5]', 'body[2]')),
    ('15bdd46b1f2b3c51', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]')),
    ('16237feb29ebbbee', 'order', '_region_mode_of', ('body[3]', 'body[0]')),
    ('163d55c7c7f9fc8b', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[2]')),
    ('167b6fb2352678e6', 'order', 'ovt_queue_poll', ('body[21]', 'body[1]')),
    ('1680faf32a6b7e16', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[2]')),
    ('16a040a2e71c9007', 'order', '_mode_or_400', ('body[0]',)),
    ('16a75d244fea5140', 'order', '_ffa_queue_poll_inner', ('body[11]',)),
    ('16cdb106c7c6f6ef', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[17]')),
    ('16d1275c56d88c98', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[0]')),
    ('17cc47620b2d931e', 'order', '_group_region', ('body[2]', 'body[3]', 'body[0]')),
    ('1800e85e25aee6a7', 'order', '_team_series_resumable', ('body[6]', 'body[0]')),
    ('181a82cbb89f9300', 'order', '_assert_no_service_subject', ('body[5]',)),
    ('18e33075dbb21360', 'order', 'held_overlap', ('body[2]', 'body[6]', 'body[0]')),
    ('1907d9e4b51cb12b', 'order', 'ovt_queue_poll', ('body[34]',)),
    ('195614fd4ae82a1f', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[3]')),
    ('198ac3752502aeab', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[5]')),
    ('19aae2773db05100', 'order', 'queue_poll', ('body[24]', 'body[1]')),
    ('1a6ec789595a8f82', 'order', '_player_body_color', ()),
    ('1ac7827c6b91f846', 'order', 'queue_poll', ('body[5]',)),
    ('1ac98c491b4450d2', 'order', '_hold_latch', ('body[1]',)),
    ('1afa2fcfdef98d7b', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]')),
    ('1b959eaff4cdaacc', 'order', 'queue_poll', ('body[28]', 'body[4]')),
    ('1bd7f031d31805c5', 'order', '_lock_queue_rows_ordered', ('body[0]',)),
    ('1bed68c6fbbaee89', 'order', '_region_mode_of', ('body[2]', 'body[0]')),
    ('1c5c3ade1aba7b59', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[3]')),
    ('1cc185948d2057cf', 'order', '_ffa_queue_poll_inner', ('body[35]',)),
    ('1ccd7148e6bddea9', 'order', 'team_queue_poll', ('body[18]', 'body[6]')),
    ('1ce4c3fb4e7ba039', 'order', '_team_relock_existing_series', ('body[6]', 'body[0]', 'body[0]')),
    ('1d0423c38e68ff6b', 'order', '_ffa_queue_poll_inner', ('body[4]',)),
    ('1d07387b9d200fa6', 'order', '_credit_bet_fighter_tax', ('body[0]',)),
    ('1d276f4ffce1dd0f', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]')),
    ('1d2efe4309f754b6', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[4]')),
    ('1dc437e3a07eb36f', 'order', 'queue_poll', ('body[28]', 'body[0]')),
    ('1e2537e73b22ad9d', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[1]', 'body[0]')),
    ('1e2f37cec0a57556', 'order', '_pick', ('body[8]', 'body[1]')),
    ('1e98137f7188db89', 'order', '_team_lock_family_pick', ('body[10]',)),
    ('1ee088a4c431a822', 'order', 'anchor_fresh', ('body[0]',)),
    ('1f83700e727e0ebf', 'order', '_credit_team_bet_fighter_tax', ('body[5]',)),
    ('1fb88552705757ed', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[2]')),
    ('1fd2ee6b8399077f', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'orelse[0]')),
    ('203b7dfb4dfebd9c', 'order', '_team_lock_family_pick', ('body[4]', 'body[2]')),
    ('20878edc499ea243', 'order', '_stamp_team_series_colors', ('body[2]', 'handlers[0]', 'body[0]')),
    ('20cdfe6fc8716a29', 'order', '_baseline', ('body[2]',)),
    ('20d8e51c012dc6d7', 'order', '_pick', ('body[23]', 'orelse[1]')),
    ('20e6c18e87e4e743', 'order', '_get', ()),
    ('210595528c06a7d0', 'order', '_parse_version', ()),
    ('2117e83b92a4930e', 'order', 'team_queue_poll', ('body[34]', 'body[8]', 'body[0]')),
    ('2127581411c5d9ad', 'order', '_formation_lease_conflict', ('body[0]',)),
    ('216451290ff6235c', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'body[0]')),
    ('216451290ff6235c', 'order', '_player_body_color', ('body[1]',)),
    ('216451290ff6235c', 'order', '_region_volumes', ('body[4]', 'body[1]')),
    ('216451290ff6235c', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'body[0]')),
    ('216451290ff6235c', 'order', '_stamp_team_series_colors', ('body[3]', 'body[0]')),
    ('216451290ff6235c', 'order', '_team_clear_dc_fallback_marker', ('body[1]', 'body[0]')),
    ('216451290ff6235c', 'order', '_team_relock_existing_series', ('body[6]', 'body[0]')),
    ('216451290ff6235c', 'order', 'ovt_queue_poll', ('body[15]', 'body[3]', 'body[0]')),
    ('216451290ff6235c', 'order', 'team_queue_poll', ('body[18]', 'body[4]', 'body[0]')),
    ('217ac9034119d116', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]')),
    ('217ddce911e2c8f6', 'order', '_region_volumes', ('body[4]', 'body[2]')),
    ('219d196c60052b3f', 'order', '_pick', ('body[5]',)),
    ('21a28279dc05788a', 'order', '_balance_teams', ('body[4]',)),
    ('21b34bb156dd9666', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[7]')),
    ('22078d3215bb7ac6', 'order', 'ovt_queue_poll', ('body[21]', 'body[0]')),
    ('22a8ccd0c0045106', 'order', '_baseline', ('body[2]', 'body[0]')),
    ('22decd1254ee198c', 'order', '_hold_latch', ('body[5]',)),
    ('22f2d69dc096700e', 'order', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[1]')),
    ('22fe74e107e07678', 'order', 'team_queue_poll', ('body[55]',)),
    ('2311a3a7430dea80', 'order', '_lease_acquire_many', ('body[0]',)),
    ('233e0775cfca7a0b', 'order', 'ovt_queue_poll', ('body[28]',)),
    ('23797c2e0e7c21e1', 'order', 'team_queue_poll', ('body[40]', 'orelse[0]')),
    ('23831fd76cd8706c', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[3]')),
    ('2396cdcc3a663c57', 'order', 'caps_token_sql', ('body[0]',)),
    ('23ab6aa24dbd1235', 'order', '_lock_snapshot_rows', ('body[2]', 'body[0]')),
    ('23c08eecca75993b', 'order', '_team_balance_rating', ()),
    ('23c49a84e5244b7d', 'order', '_rules_for_members', ()),
    ('23fa07374b98262c', 'order', '_pick', ('body[0]',)),
    ('244c817a04bfb0a4', 'order', 'queue_poll', ('body[16]', 'body[0]')),
    ('24671f350e6e6c8c', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[0]')),
    ('249fb8accf1dbd94', 'order', 'queue_poll', ('body[28]', 'body[19]')),
    ('24a958e60b398fe1', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'orelse[0]')),
    ('24af868715aa10f9', 'order', '_lease_admission_gate', ('body[17]', 'body[0]')),
    ('24b6844cf1112e76', 'order', 'team_queue_poll', ('body[20]',)),
    ('24ef26729339a88a', 'order', 'team_queue_poll', ('body[58]',)),
    ('2574c5aeb299a142', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]')),
    ('25b816d82e9c8f68', 'order', 'team_queue_poll', ('body[47]',)),
    ('26631f3ea493c1ac', 'order', '_hold_latch', ('body[6]',)),
    ('269139153980c1bd', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]')),
    ('269139153980c1bd', 'order', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]')),
    ('26c7d1c38b771a24', 'order', '_pick', ('body[23]', 'body[0]')),
    ('280683749bde5bda', 'order', '_get', ('body[0]',)),
    ('2845c283c7ac0b33', 'order', 'queue_poll', ('body[24]', 'body[10]')),
    ('28602f4049405c9c', 'order', 'queue_poll', ('body[4]',)),
    ('289c0a7fd66edef2', 'order', '_asm_sqlstate', ('body[3]',)),
    ('28a4b15118dc078d', 'order', '_asm_sqlstate', ('body[3]', 'body[3]')),
    ('28ba0eb09b72de71', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[5]')),
    ('28d1558c1a9f7638', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[2]')),
    ('28e026db02287871', 'order', 'team_queue_poll', ('body[18]', 'body[4]', 'body[0]', 'body[0]')),
    ('292f866828e518bf', 'order', 'team_queue_poll', ('body[34]', 'body[4]')),
    ('2942b22d4b923bc5', 'order', '_ffa_queue_poll_inner', ('body[13]',)),
    ('299ab986695829dd', 'order', '_credit_team_bet_fighter_tax', ()),
    ('2a0223875e20b561', 'order', '_bet_fighter_tax', ('body[0]',)),
    ('2a122c7662aba3b5', 'order', 'ovt_queue_poll', ('body[39]',)),
    ('2a378f92acb9a31b', 'order', '_pick', ('body[24]',)),
    ('2a8cdade3c8c7fae', 'order', 'ovt_queue_poll', ('body[16]', 'body[13]')),
    ('2a8ddff9fc76eb44', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]')),
    ('2abe10cb71dffd66', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[3]')),
    ('2c0228f09182318b', 'order', '_rules_for_queue_match', ('body[1]',)),
    ('2c031254eb8c69dd', 'order', 'ovt_queue_poll', ('body[16]', 'body[0]')),
    ('2c330794998aea1a', 'order', 'team_queue_poll', ('body[18]', 'body[1]')),
    ('2c4ee4176682aa66', 'order', 'queue_poll', ('body[28]', 'body[8]')),
    ('2c510929024fcb68', 'order', 'team_queue_poll', ('body[18]', 'body[4]', 'handlers[0]', 'body[0]')),
    ('2c880acd2238e75e', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[14]')),
    ('2ca0473464676d53', 'order', '_lock_snapshot_rows', ('body[2]', 'body[1]')),
    ('2d1b61cf3f4dd896', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[1]')),
    ('2d335311ec27b50c', 'order', '_mrw_mod', ('body[1]',)),
    ('2d4e1003c221bbac', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[0]')),
    ('2d895f62e55b64c3', 'order', '_pick', ('body[5]', 'body[5]')),
    ('2da604b10df0947e', 'order', 'ovt_queue_poll', ('body[26]',)),
    ('2ecb99d8738ab69c', 'order', '_formation_lease_conflict', ('body[3]', 'body[4]')),
    ('2f13921be2a5470f', 'order', '_balance_teams', ()),
    ('2f30888531296275', 'order', '_lease_admission_gate', ('body[2]', 'body[0]')),
    ('2f30888531296275', 'order', '_lease_admission_gate', ('body[6]', 'body[0]')),
    ('2f30888531296275', 'order', '_lease_admission_gate', ('body[7]',)),
    ('2f472d83d0b12251', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[8]')),
    ('2f472d83d0b12251', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[2]')),
    ('2f7f5e80c5514bf9', 'order', '_lock_snapshot_rows', ()),
    ('2f953b66d55c1b2e', 'order', '_team_balance_rating', ('body[1]',)),
    ('3024d6cb07d36781', 'order', '_rules_for_queue_match', ('body[4]',)),
    ('30332cb061347a3f', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[0]')),
    ('305aa0c1d122f953', 'order', 'ovt_queue_poll', ('body[32]',)),
    ('305e7ed84db123f9', 'order', 'team_queue_poll', ('body[5]', 'body[0]')),
    ('306112243766fbb6', 'order', '_team_relock_existing_series', ('body[3]', 'body[1]')),
    ('30725e8f9da02908', 'order', '_lease_acquire_many', ()),
    ('30c554d41b5202d5', 'order', '_rules_for_queue_match', ()),
    ('310b513c426f8c03', 'order', 'queue_poll', ('body[16]', 'body[6]')),
    ('310f250a98a30b23', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]')),
    ('311ffe6710c79514', 'order', '_latch_sql', ()),
    ('3151e112834d20c8', 'order', 'team_queue_poll', ('body[19]', 'body[6]')),
    ('31670479b09e6dd2', 'order', 'team_queue_poll', ('body[11]', 'body[1]')),
    ('31670479b09e6dd2', 'order', 'team_queue_poll', ('body[18]', 'body[2]', 'body[3]')),
    ('31670479b09e6dd2', 'order', 'team_queue_poll', ('body[23]', 'body[2]')),
    ('31670479b09e6dd2', 'order', 'team_queue_poll', ('body[8]', 'body[0]')),
    ('316ca025940ca19f', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[0]')),
    ('3173a71642c13d8c', 'order', '_lease_admission_gate', ('body[19]',)),
    ('3181f8f68e9daf05', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[5]')),
    ('31aab3c6894b8db5', 'order', '_group_region', ('body[2]', 'body[2]', 'body[1]')),
    ('31ea0f85ab371dac', 'order', 'team_queue_poll', ('body[21]',)),
    ('31ea0f85ab371dac', 'order', 'team_queue_poll', ('body[34]', 'body[11]')),
    ('32331de9944f2cab', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[4]')),
    ('32f0209e5a272d36', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[0]')),
    ('32f0209e5a272d36', 'order', '_ffa_queue_poll_inner', ('body[33]', 'orelse[0]')),
    ('32f0209e5a272d36', 'order', '_ffa_queue_poll_inner', ('body[34]', 'body[0]')),
    ('32f0209e5a272d36', 'order', '_ffa_queue_poll_inner', ('body[45]', 'body[0]')),
    ('32f0209e5a272d36', 'order', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[0]')),
    ('32f0209e5a272d36', 'order', '_team_relock_existing_series', ('body[4]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[21]', 'body[10]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[21]', 'orelse[0]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[22]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[25]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'ovt_queue_poll', ('body[35]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[17]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[28]', 'body[14]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[28]', 'body[19]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[28]', 'body[2]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'queue_poll', ('body[28]', 'orelse[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[6]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[34]', 'body[8]', 'body[1]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[34]', 'body[9]', 'body[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[34]', 'orelse[0]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[35]', 'body[3]')),
    ('32f0209e5a272d36', 'order', 'team_queue_poll', ('body[61]', 'body[0]')),
    ('330e089bfb5f7345', 'order', '_rules_normalize', ('body[3]', 'body[0]', 'body[1]')),
    ('33ad028538234c70', 'order', 'held_overlap', ('body[2]', 'body[2]')),
    ('34174fb569afc944', 'order', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[1]')),
    ('34174fb569afc944', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[1]')),
    ('347ef31f91f2158e', 'order', '_lease_admission_gate', ('body[12]',)),
    ('35036f494d54cf5c', 'order', '_lock_snapshot_rows', ('body[2]', 'body[0]', 'body[0]')),
    ('3550fb2a0264b33d', 'order', '_mod_version_at_least', ()),
    ('356ac133e8f7ec99', 'order', '_team_relock_existing_series', ('body[11]',)),
    ('3591c38b54c27871', 'order', 'team_queue_poll', ('body[39]',)),
    ('359c61508ba19da3', 'order', 'ovt_queue_poll', ('body[29]',)),
    ('35ee0dcb5ec2ff2f', 'order', 'held_overlap', ('body[2]', 'body[3]')),
    ('360435008c736b8c', 'order', 'queue_poll', ('body[22]', 'body[2]')),
    ('369d33de6fd61794', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[3]')),
    ('3738921dba44d8e5', 'order', '_team_resolve_live_family', ('body[2]',)),
    ('374215698cea8629', 'order', 'team_queue_poll', ('body[56]',)),
    ('37ad51c1473bd089', 'order', '_team_series_resumable', ('body[2]',)),
    ('37b75372b5fd81d7', 'order', 'team_queue_poll', ('body[18]', 'body[8]')),
    ('37d0b709d9a4594a', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]')),
    ('37e392abc8863f45', 'order', '_rules_json', ('body[0]',)),
    ('37f51911869e3ffa', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'orelse[0]', 'body[0]')),
    ('38880c13979f706d', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[5]')),
    ('38b453c2d166d112', 'order', '_region_mode_of', ('body[2]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', '_ffa_queue_poll_inner', ('body[45]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', '_team_relock_existing_series', ('body[4]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', 'ovt_queue_poll', ('body[35]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[9]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', 'queue_poll', ('body[28]', 'body[19]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]', 'body[1]')),
    ('38bdc57d3c7f2b95', 'order', 'team_queue_poll', ('body[61]', 'body[1]')),
    ('38ccd9ef815ef12c', 'order', 'ovt_queue_poll', ('body[11]',)),
    ('38dd9587e21323bd', 'order', 'team_queue_poll', ('body[34]', 'body[6]')),
    ('38ebd1ccc958afcf', 'order', '_team_color_holders', ('body[2]', 'body[0]')),
    ('394c00cc374caed3', 'order', '_clean_map', ('body[0]',)),
    ('3983ea7a1b915899', 'order', 'team_queue_poll', ('body[53]',)),
    ('39853a12e3eb8984', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[4]')),
    ('399ea27f0a77b839', 'order', '_team_lock_family_pick', ('body[10]', 'body[0]')),
    ('39c7c7e3bbc140f2', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[3]')),
    ('3a2a52272324145b', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'body[1]')),
    ('3a2a52272324145b', 'order', 'team_queue_poll', ('body[48]', 'body[1]')),
    ('3a3f2d77a1a2e417', 'order', '_pick', ('body[4]',)),
    ('3a8595c0d32ffca4', 'order', '_team_series_resumable', ('body[5]', 'body[0]')),
    ('3a8c5837ecf6e51b', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[16]')),
    ('3aa49409f2a4d13d', 'order', '_region_pings_newer', ('body[0]',)),
    ('3ad6ffca5ef982d6', 'order', '_baseline', ('body[3]',)),
    ('3b455aeefb9e8f4a', 'order', '_ffa_gather_decide', ('body[2]',)),
    ('3b4b951de8bbd96d', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[5]', 'body[0]')),
    ('3b59c0bac6b3983c', 'order', '_region_current', ('body[2]',)),
    ('3b672175c1c2bbc3', 'order', '_baseline', ('body[9]',)),
    ('3b8f9e668e124fbe', 'order', '_region_pings_newer', ('body[1]', 'body[0]')),
    ('3bac23f4576d0ba1', 'order', 'team_queue_poll', ('body[7]',)),
    ('3bc1eab78344398c', 'order', '_rules_for_members', ('body[3]', 'body[1]', 'body[0]')),
    ('3c36332945655d28', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[5]')),
    ('3c46a416603ba1ed', 'order', '_balance_teams', ('body[0]',)),
    ('3c4ee8a4cce7c082', 'order', '_credit_team_bet_fighter_tax', ('body[4]',)),
    ('3c5bd7359f8273cc', 'order', '_ffa_sort_key', ()),
    ('3c5ebba85fd99079', 'order', '_parse_version', ('body[0]', 'handlers[0]', 'body[0]')),
    ('3c77bf2c0db4a582', 'order', 'ovt_queue_poll', ('body[13]',)),
    ('3ca485c913aa3682', 'order', '_team_quartet_key', ('body[0]',)),
    ('3cc1aa1c9abac663', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]')),
    ('3cf7b0aeca36bb0d', 'order', '_ffa_queue_poll_inner', ('body[42]',)),
    ('3d0a085c815faf02', 'order', '_bet_fighter_tax', ('body[2]', 'body[0]')),
    ('3d0cfe8a6cd0cae1', 'order', '_ffa_queue_poll_inner', ('body[33]', 'orelse[2]')),
    ('3d0cfe8a6cd0cae1', 'order', 'ovt_queue_poll', ('body[21]', 'orelse[2]')),
    ('3d0cfe8a6cd0cae1', 'order', 'queue_poll', ('body[17]', 'body[2]')),
    ('3d0cfe8a6cd0cae1', 'order', 'queue_poll', ('body[28]', 'body[2]', 'body[1]')),
    ('3d0cfe8a6cd0cae1', 'order', 'queue_poll', ('body[28]', 'orelse[2]')),
    ('3d0cfe8a6cd0cae1', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'orelse[2]')),
    ('3d0cfe8a6cd0cae1', 'order', 'team_queue_poll', ('body[34]', 'orelse[2]')),
    ('3d1e0aaa463df3ee', 'order', '_asm_sqlstate', ('body[3]', 'body[1]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_clean_map', ('body[3]', 'body[0]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_clean_map', ('body[3]', 'body[1]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_clean_map', ('body[3]', 'body[2]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[6]')),
    ('3d1e0aaa463df3ee', 'order', '_formation_lease_conflict', ('body[3]', 'body[0]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_formation_lease_conflict', ('body[3]', 'body[2]', 'body[1]')),
    ('3d1e0aaa463df3ee', 'order', '_formation_lease_conflict', ('body[3]', 'body[4]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_lease_admission_gate', ('body[17]', 'body[2]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[2]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_team_lock_family_pick', ('body[10]', 'body[0]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_team_lock_family_pick', ('body[10]', 'body[1]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_team_lock_family_pick', ('body[7]', 'body[0]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[2]', 'body[0]')),
    ('3d1e0aaa463df3ee', 'order', 'ovt_queue_poll', ('body[21]', 'body[10]', 'body[2]')),
    ('3d1e0aaa463df3ee', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[4]')),
    ('3d1e0aaa463df3ee', 'order', 'queue_poll', ('body[28]', 'body[14]', 'body[2]')),
    ('3d1e0aaa463df3ee', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[4]')),
    ('3d1e0aaa463df3ee', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[6]', 'body[1]')),
    ('3d1e0aaa463df3ee', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[3]')),
    ('3d1e0aaa463df3ee', 'order', 'team_queue_poll', ('body[34]', 'body[9]', 'body[1]')),
    ('3d68bd53fc06910d', 'order', '_hold_latch', ()),
    ('3db6a0232c0e501a', 'order', '_rules_for_members', ('body[2]',)),
    ('3dc1bf420a3f26eb', 'order', 'queue_poll', ('body[28]', 'body[5]')),
    ('3ddee4b84fe4d96e', 'order', '_ffa_gather_decide', ('body[3]',)),
    ('3e05c90127a2c8db', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[0]')),
    ('3e23bf76c40264f6', 'order', '_rules_members', ('body[0]',)),
    ('3e5ac81cf96e50c7', 'order', '_ffa_queue_poll_inner', ('body[27]',)),
    ('3e6dec4011a215c0', 'order', 'team_queue_poll', ('body[54]',)),
    ('3e74604f97269948', 'order', '_ffa_queue_poll_inner', ('body[29]',)),
    ('3ea4aaddd169b175', 'order', 'team_queue_poll', ('body[19]', 'body[1]', 'body[0]')),
    ('3eb07c33e5fe2b17', 'order', 'team_queue_poll', ('body[19]', 'body[9]')),
    ('3f5db7f8c8c7802c', 'order', '_ffa_queue_poll_inner', ('body[44]', 'body[0]')),
    ('3f8a052d61a85a3f', 'order', 'ovt_queue_poll', ('body[3]',)),
    ('3f8a052d61a85a3f', 'order', 'team_queue_poll', ('body[4]',)),
    ('3fb8b3a24de29e68', 'order', 'anchor_fresh', ('body[1]',)),
    ('3fd5387fce21e361', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]', 'body[0]')),
    ('3ff8c553d0466a2e', 'order', '_region_mode_of', ('body[2]', 'body[1]', 'body[0]')),
    ('4026eb0d17fc3917', 'order', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[0]')),
    ('4026eb0d17fc3917', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[0]')),
    ('4039be3297c5b062', 'order', '_assert_no_service_subject', ('body[4]',)),
    ('40a3a759431f1504', 'order', '_pick', ('body[18]', 'body[3]')),
    ('40c4f1f9f3fd858f', 'order', 'queue_poll', ('body[28]', 'body[11]')),
    ('40ce129fe2227b7a', 'order', 'series_holds', ()),
    ('40ce5b68754ecde6', 'order', '_player_body_color', ('body[2]',)),
    ('40ef8704145aa525', 'order', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]', 'body[0]')),
    ('41160a1184d4c681', 'order', 'team_queue_poll', ('body[41]',)),
    ('4153e2e9d38eee07', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[12]')),
    ('41622fc3a49af6c6', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[1]')),
    ('416c33d71216a91f', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[5]', 'body[0]')),
    ('41fa13565cd0ecd6', 'order', '_group_region', ('body[2]', 'body[4]')),
    ('42040de90f99567a', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[2]')),
    ('427087ad474205d0', 'order', 'queue_poll', ('body[16]', 'body[2]')),
    ('42c7723533d1bea0', 'order', '_pick', ('body[18]', 'body[0]')),
    ('42cb689e618eef54', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[5]', 'body[0]')),
    ('433f5d775174df92', 'order', '_rules_json', ('body[4]',)),
    ('434af6f9b735ae0a', 'order', '_ffa_roster_clears_proximity_floor', ('body[3]',)),
    ('438ba6c6006ecb9f', 'order', 'pick_region_for_group', ('body[0]',)),
    ('43cd379936dff239', 'order', '_player_body_color', ('body[2]', 'body[0]')),
    ('43f0bb1bad92655e', 'order', 'queue_poll', ('body[22]', 'orelse[0]')),
    ('442805385064e7db', 'order', '_reconcile_team_series_bets', ('body[1]', 'handlers[0]', 'body[0]')),
    ('444c4b56f817f6ff', 'order', '_group_region', ('body[6]',)),
    ('4477242f2ebac6d6', 'order', 'team_queue_poll', ('body[11]',)),
    ('448c7a24c3c6e6b4', 'order', 'ovt_queue_poll', ('body[4]',)),
    ('448c7a24c3c6e6b4', 'order', 'team_queue_poll', ('body[5]',)),
    ('44f5a178cc27e9bf', 'order', '_ffa_queue_poll_inner', ('body[22]',)),
    ('451c4471dc67b023', 'order', '_team_color_holders', ('body[1]',)),
    ('451decd6c00aa812', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[2]')),
    ('452acfc06fb81f03', 'order', '_group_region', ('body[2]', 'body[7]', 'body[0]', 'body[0]')),
    ('453b8dbb9eff14bd', 'order', '_lease_admission_gate', ('body[3]',)),
    ('4546faea57c31bb0', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[1]')),
    ('45ac92d82476df4f', 'order', '_region_volumes', ('body[0]',)),
    ('4633837fcacd3989', 'order', '_player_body_color', ('body[0]',)),
    ('46410ac88c993cc8', 'order', '_ffa_queue_poll_inner', ('body[31]',)),
    ('46410ac88c993cc8', 'order', 'ovt_queue_poll', ('body[21]', 'body[5]')),
    ('464276c09d5d4cb6', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]', 'body[1]')),
    ('464276c09d5d4cb6', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'body[1]')),
    ('465001913bd87f37', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[12]')),
    ('4651add04453b8b8', 'order', '_team_lock_family_pick', ('body[0]',)),
    ('467feacab8b3e98f', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]', 'body[0]')),
    ('469b02a71af40588', 'order', '_rules_normalize', ('body[2]',)),
    ('46b8af5bbe2009ac', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[1]')),
    ('47a88b3404264750', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[0]')),
    ('47a88b3404264750', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[6]')),
    ('47a88b3404264750', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[5]', 'body[0]')),
    ('47a9723b5b589c5c', 'order', '_pick', ('body[11]',)),
    ('47d6375caa37921d', 'order', 'team_queue_poll', ('body[19]', 'body[4]')),
    ('4862ab5cfa463ae3', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]', 'body[0]')),
    ('488bb120551097e7', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'body[0]')),
    ('488bb120551097e7', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'body[0]')),
    ('488bb120551097e7', 'order', 'ovt_queue_poll', ('body[16]', 'body[5]', 'body[0]')),
    ('4895e41fe9839b79', 'order', '_team_color_holders', ('body[0]',)),
    ('495412fe8e185d60', 'order', '_lock_queue_rows_ordered', ('body[2]',)),
    ('4a10d5c44bc8e87b', 'order', '_team_lock_family_pick', ('body[1]',)),
    ('4a1a8f6c0fb1f593', 'order', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[0]')),
    ('4a21e85040ab2f49', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'body[0]', 'body[0]')),
    ('4a622c434394875a', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[1]')),
    ('4a6e89450c96f0c0', 'order', 'team_queue_poll', ('body[61]',)),
    ('4ac4814e0d677c4f', 'order', '_group_region', ('body[2]', 'body[5]', 'body[4]')),
    ('4b02a9a40aef791d', 'order', '_baseline', ('body[0]',)),
    ('4b0615fcf1db854b', 'order', 'queue_poll', ('body[12]',)),
    ('4b09563dba5d7158', 'order', '_pick', ('body[8]', 'body[1]', 'body[0]')),
    ('4b1063cf66e410c9', 'order', '_lease_acquire', ('body[0]',)),
    ('4b28ab54b3673e40', 'order', '_pick', ('body[20]',)),
    ('4b952050a201b6f9', 'order', 'queue_poll', ('body[24]', 'body[9]')),
    ('4bc1f38b981cfe0f', 'order', '_mod_version_at_least', ('body[1]',)),
    ('4bcea58eed8af306', 'order', '_ffa_queue_poll_inner', ('body[6]',)),
    ('4bda036aa0321e6c', 'order', '_team_quartet_key', ('body[1]',)),
    ('4c1e67ce12da21c8', 'order', '_stamp_team_series_colors', ('body[2]', 'body[0]')),
    ('4c74303c09efccf7', 'order', '_ffa_queue_poll_inner', ('body[38]',)),
    ('4cd4053f7c957c43', 'order', '_region_mode_of', ('body[1]',)),
    ('4cd9d71981a9a1e8', 'order', '_ffa_queue_poll_inner', ()),
    ('4cdf47e977588866', 'order', 'team_queue_poll', ('body[28]',)),
    ('4ceb3fd2b6d48b3d', 'order', 'ovt_queue_poll', ('body[21]', 'body[11]')),
    ('4d090c36cbf3997e', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[10]')),
    ('4d65313bf46f29b3', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[5]')),
    ('4d691d468a53fa9e', 'order', 'team_queue_poll', ('body[19]', 'body[14]')),
    ('4de438302f50a119', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[7]')),
    ('4ded7843c0b90ffc', 'order', '_ffa_queue_poll_inner', ('body[26]', 'body[0]')),
    ('4df5737c58af042d', 'order', '_group_region', ('body[2]', 'body[7]')),
    ('4e1ccda110c91fdb', 'order', '_team_relock_existing_series', ('body[10]',)),
    ('4e3f7258c3ac94d3', 'order', '_stamp_team_series_colors', ('body[2]', 'body[4]', 'body[1]')),
    ('4e99c972d9263bc2', 'order', '_team_resolve_live_family', ()),
    ('4edb2dc8fc72a46b', 'order', 'team_queue_poll', ('body[36]',)),
    ('4ee364da5483b782', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[7]')),
    ('4eea83856361419c', 'order', '_team_lock_family_pick', ('body[4]', 'body[1]', 'body[0]')),
    ('4eea83856361419c', 'order', '_team_resolve_live_family', ('body[7]', 'body[1]')),
    ('4f0b24524d96da6b', 'order', 'held_overlap', ('body[2]', 'body[5]')),
    ('4f9316d813ac54ad', 'order', '_clean_map', ('body[3]',)),
    ('5181a3eb85fa847d', 'order', '_credit_bet_fighter_tax', ('body[3]',)),
    ('51829adafdc1607a', 'order', '_clean_map', ('body[3]', 'body[3]')),
    ('51c46058e33e22ba', 'order', '_region_volumes', ()),
    ('51f735bdca72ce81', 'order', '_rules_normalize', ('body[3]', 'body[1]')),
    ('52100c5adb062db5', 'order', 'team_queue_poll', ('body[18]', 'body[2]', 'body[0]')),
    ('521cd1061441eb25', 'order', '_balance_teams', ('body[6]',)),
    ('526ea85040012ce8', 'order', '_ffa_queue_poll_inner', ('body[1]',)),
    ('526ea85040012ce8', 'order', 'ovt_queue_poll', ('body[1]',)),
    ('526ea85040012ce8', 'order', 'team_queue_poll', ('body[18]', 'body[0]')),
    ('526ea85040012ce8', 'order', 'team_queue_poll', ('body[2]',)),
    ('52996f018f788f72', 'order', '_region_mode_of', ('body[0]',)),
    ('529a1cc6ef559f92', 'order', 'held_overlap', ('body[3]',)),
    ('52baddb361ae3e22', 'order', 'ovt_queue_poll', ('body[21]', 'body[8]')),
    ('52c22f44bb79f7c8', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]')),
    ('52c6b8f21a995dc6', 'order', '_asm_sqlstate', ('body[3]', 'body[4]')),
    ('52d43ffd47eb2d35', 'order', '_rules_json', ('body[3]', 'body[0]')),
    ('5315e16135dd2a64', 'order', 'queue_poll', ('body[22]', 'body[0]')),
    ('53685fb4075fdc19', 'order', '_mode_or_400', ('body[0]', 'body[0]')),
    ('536bc772529fe04d', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[0]')),
    ('538221135f8979b8', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[0]')),
    ('53dd1d58940c340e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[3]')),
    ('543855677614f2e6', 'order', 'series_holds', ('body[0]',)),
    ('547dfaeaefd61edc', 'order', 'team_queue_poll', ('body[38]', 'body[0]')),
    ('548d95a734383b3d', 'order', '_asm_sqlstate', ('body[0]',)),
    ('54bf297a68808c8a', 'order', 'ovt_queue_poll', ('body[21]', 'body[7]')),
    ('54c2faf5c00b0ecd', 'order', 'held_overlap', ('body[2]', 'body[3]', 'body[0]')),
    ('553aba640ac90dba', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[6]')),
    ('559e8abf6c6804c2', 'order', '_return_stake_exactly', ('body[1]',)),
    ('55e71264a9e7bfb0', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[1]')),
    ('55ff0bed8ab0c98a', 'order', '_team_relock_existing_series', ()),
    ('562c0a71b940d04b', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[3]')),
    ('562fcc3a3a100e52', 'order', '_return_stake_exactly', ('body[2]',)),
    ('5638332df2804b31', 'order', 'queue_poll', ('body[28]',)),
    ('565a38c81b445a5e', 'order', 'queue_poll', ('body[32]',)),
    ('5674d02dfcc83266', 'order', '_is_number', ()),
    ('567768940d96c506', 'order', 'team_queue_poll', ('body[66]',)),
    ('56ab9ad5845cb9e3', 'order', '_group_region', ('body[2]', 'body[5]', 'body[0]')),
    ('57089cc388ebcbb3', 'order', '_region_volumes', ('body[4]',)),
    ('5745ff906e90bc7d', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[0]')),
    ('57b78557eaebbb41', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[1]')),
    ('5831b5ecb7c378c5', 'order', 'queue_poll', ('body[24]', 'body[6]')),
    ('58627fa6638f3293', 'order', '_ffa_queue_poll_inner', ('body[21]', 'body[1]')),
    ('589e6710267542d7', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[0]')),
    ('58b8b803e687f9ed', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[2]')),
    ('58db6a77091be314', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]')),
    ('59355d4c0b3fbbdc', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[0]')),
    ('596f637609effab0', 'order', 'team_queue_poll', ('body[19]', 'body[3]')),
    ('596f637609effab0', 'order', 'team_queue_poll', ('body[67]',)),
    ('59abc74f60241de3', 'order', '_formation_lease_conflict', ('body[2]',)),
    ('59ba0640170bea0a', 'order', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]')),
    ('59ea2bd51857a6f8', 'order', '_ffa_sort_key', ('body[0]',)),
    ('5a08ec868a3154db', 'order', 'team_queue_poll', ('body[19]', 'body[13]')),
    ('5a38c692b92c23ac', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]')),
    ('5a4caf86e0bffd91', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]')),
    ('5aa52facad180274', 'order', '_mod_version_at_least', ('body[2]', 'body[0]')),
    ('5aaf5eb6b2b74919', 'order', 'ovt_queue_poll', ('body[16]', 'body[1]', 'body[0]')),
    ('5b506c80d9d77a56', 'order', '_lease_admission_gate', ('body[14]',)),
    ('5b7bd4df8c70d269', 'order', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[2]')),
    ('5b9f883ea38d5278', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[1]')),
    ('5ba003048c5a89ed', 'order', '_formation_lease_conflict', ('body[1]',)),
    ('5bd963800f79090e', 'order', '_group_region', ('body[2]', 'body[2]', 'body[1]', 'body[0]')),
    ('5bfa4b7eeaeb2eca', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[3]')),
    ('5c01fcb94463c508', 'order', 'team_queue_poll', ('body[38]',)),
    ('5d12f473e4297f76', 'order', '_team_lock_family_pick', ('body[10]', 'body[1]')),
    ('5d367b02ebcc8d69', 'order', '_ffa_queue_poll_inner', ('body[49]',)),
    ('5d75af3175f25de2', 'order', '_team_lock_family_pick', ('body[7]',)),
    ('5db38001ebd1c35b', 'order', '_group_region', ('body[3]',)),
    ('5dc1b903f832f393', 'order', '_baseline', ('body[8]',)),
    ('5de15d5f4be6d78d', 'order', 'ovt_queue_poll', ('body[34]', 'body[0]')),
    ('5e59c7c99f50c3a1', 'order', '_bet_fighter_tax', ('body[4]',)),
    ('5e7ff301f03f64fe', 'order', 'queue_poll', ('body[23]', 'body[0]')),
    ('5e7ff301f03f64fe', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[0]', 'body[0]')),
    ('5e7ff301f03f64fe', 'order', 'queue_poll', ('body[25]', 'body[0]')),
    ('5ed79e33a61a18d4', 'order', 'queue_poll', ('body[28]', 'body[16]')),
    ('5f0166354e286f40', 'order', 'ovt_queue_poll', ('body[21]',)),
    ('5f274f2609b03037', 'order', '_baseline', ('body[6]', 'body[0]')),
    ('5f4b9c5d9444ea99', 'order', 'queue_poll', ('body[24]', 'body[5]')),
    ('5fcb2cf05e4f46e4', 'order', 'team_queue_poll', ('body[34]', 'body[3]')),
    ('5fee4c669904d898', 'order', '_assert_no_service_subject', ('body[2]', 'body[0]')),
    ('5fee4c669904d898', 'order', '_assert_no_service_subject', ('body[5]', 'body[0]')),
    ('6026bf00092baa37', 'order', 'ovt_queue_poll', ('body[22]',)),
    ('60451d271cc5d922', 'order', 'team_queue_poll', ('body[22]',)),
    ('6085c2cf8319ee97', 'order', '_team_clear_dc_fallback_marker', ()),
    ('609eba482508b175', 'order', '_rules_normalize', ('body[2]', 'body[0]', 'handlers[0]', 'body[0]')),
    ('60a0860f9afec76c', 'order', 'team_queue_poll', ('body[35]', 'body[0]')),
    ('618251e42d6753a9', 'order', '_parse_version', ('body[0]', 'body[0]')),
    ('61ab73080a17379a', 'order', '_service_player_uuids', ('body[1]',)),
    ('61ce7716615655b9', 'order', '_baseline', ('body[1]',)),
    ('6208078225ccac6b', 'order', '_pick', ('body[0]', 'body[0]')),
    ('627544784f58afca', 'order', '_asm_sqlstate', ('body[3]', 'body[3]', 'body[1]', 'body[0]')),
    ('628105d07b3aeffd', 'order', '_lease_admission_gate', ()),
    ('62d26edaa253c242', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[4]')),
    ('630010d46fe808a7', 'order', '_region_candidate_volumes', ('body[1]',)),
    ('6301fa7b458037e1', 'order', 'anchor_fresh', ()),
    ('63668e1beaf7d013', 'order', 'queue_poll', ('body[28]', 'body[9]')),
    ('6370a1aa311ac6d8', 'order', '_rules_for_queue_match', ('body[2]',)),
    ('6379e1a5786a05b9', 'order', '_team_resolve_live_family', ('body[8]',)),
    ('637f5f6b11b92711', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[3]')),
    ('639334b4bb1bb8f3', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]')),
    ('63b3468e0e932972', 'order', '_team_relock_existing_series', ('body[7]',)),
    ('63d118cf8c1889a6', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[5]')),
    ('63e2390d50e6aa40', 'order', '_latch_sql', ('body[0]',)),
    ('63fafd90bb41b7a5', 'order', 'ovt_queue_poll', ('body[16]', 'body[1]')),
    ('644dfb44f5c651c8', 'order', '_group_region', ('body[2]', 'body[5]', 'body[1]', 'body[0]', 'handlers[0]', 'body[0]')),
    ('644e9e3203a409d6', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[1]')),
    ('645531a381d6da9d', 'order', '_rules_normalize', ('body[2]', 'body[0]', 'body[0]')),
    ('64aacefa95b5a3ef', 'order', 'team_queue_poll', ('body[44]',)),
    ('64f2e5ed0e55bb64', 'order', 'pick_region_for_group', ()),
    ('6526014f8b0943c7', 'order', 'team_queue_poll', ('body[57]',)),
    ('6565281c829e57f8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[0]')),
    ('658b4c84d9409ec2', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[5]')),
    ('65b26c990d1da506', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[6]')),
    ('65bf04b59115732c', 'order', '_region_mode_of', ('body[3]',)),
    ('65c986ffc4ece6bc', 'order', '_ffa_queue_poll_inner', ('body[12]', 'body[1]')),
    ('65c986ffc4ece6bc', 'order', 'ovt_queue_poll', ('body[14]', 'body[1]')),
    ('6601a3e2f89b083f', 'order', 'ovt_queue_poll', ('body[25]',)),
    ('6608adbfa0ca0699', 'order', 'team_queue_poll', ('body[34]', 'body[13]')),
    ('665903532c733ea6', 'order', 'team_queue_poll', ('body[14]',)),
    ('66600a00843c2236', 'order', 'team_queue_poll', ('body[10]',)),
    ('6675fae7dff4146a', 'order', '_team_lock_family_pick', ('body[5]',)),
    ('6698a7ba6af64291', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[5]')),
    ('66f409f3560f993b', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'body[0]')),
    ('675db70a4ac087ce', 'order', '_ffa_queue_poll_inner', ('body[18]',)),
    ('676c6bfbd6dd6b29', 'order', 'queue_poll', ('body[24]', 'body[3]')),
    ('67c4dd46082b545e', 'order', 'team_queue_poll', ('body[40]', 'body[1]')),
    ('67d29f73a01dd2e7', 'order', '_group_region', ('body[0]',)),
    ('67d3bbbba47365f7', 'order', '_rules_normalize', ('body[0]',)),
    ('68239fdd0ff54aeb', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[9]')),
    ('68239fdd0ff54aeb', 'order', 'ovt_queue_poll', ('body[16]', 'body[7]')),
    ('6828cb0709d1ec92', 'order', '_player_body_color', ('body[1]', 'body[0]')),
    ('68696058c0054fe6', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[6]')),
    ('68725c9a70f87f65', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]', 'orelse[0]')),
    ('6874d5fd99dd9bd4', 'order', 'caps_token_sql', ('body[1]',)),
    ('68ab79190267ef20', 'order', '_lease_admission_gate', ('body[5]',)),
    ('68b32706fea85202', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[0]')),
    ('694934aacf93dfa9', 'order', '_ffa_queue_poll_inner', ('body[12]',)),
    ('694934aacf93dfa9', 'order', 'ovt_queue_poll', ('body[14]',)),
    ('694df24b2f739276', 'order', 'team_queue_poll', ('body[42]',)),
    ('697e6ecb057d0eee', 'order', '_balance_teams', ('body[3]',)),
    ('69c229485c98680f', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[1]')),
    ('69c662b24927bf16', 'order', 'team_queue_poll', ('body[31]', 'body[1]')),
    ('69da9047e37c4c9a', 'order', 'queue_poll', ('body[2]',)),
    ('6a00fef6e2dfada3', 'order', 'team_queue_poll', ('body[19]', 'body[1]')),
    ('6a4551393715763f', 'order', '_rules_json', ()),
    ('6a5fac30ded6d85e', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[4]')),
    ('6aa04dfa29dc17e4', 'order', '_asm_sqlstate', ('body[2]',)),
    ('6abb3365123ee9ac', 'order', '_ffa_gather_decide', ('body[1]', 'body[0]')),
    ('6b073e5542d33068', 'order', 'team_queue_poll', ('body[40]', 'body[4]')),
    ('6b5c11984ebb9088', 'order', 'held_overlap', ('body[2]', 'body[4]')),
    ('6c622a98f1d97d38', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[1]')),
    ('6c6cdadc3bcf5437', 'order', '_team_series_resumable', ('body[7]',)),
    ('6da71a5b2acafbc5', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[7]')),
    ('6da7a79281db8949', 'order', '_ffa_queue_poll_inner', ('body[37]',)),
    ('6dd826efc04383ad', 'order', '_pick', ('body[6]',)),
    ('6e9561f22c3f395e', 'order', '_ffa_gather_decide', ('body[1]',)),
    ('6ea87e258e23f1db', 'order', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]')),
    ('6ebeaf4b24251b13', 'order', '_return_stake_exactly', ()),
    ('6eca8ceeaa8f3e30', 'order', '_team_resolve_live_family', ('body[6]',)),
    ('6ed2dc0617354e91', 'order', '_stamp_team_series_colors', ('body[3]',)),
    ('6efc8df8621048b2', 'order', '_pick', ('body[19]', 'body[0]')),
    ('6f9f0c0de8b30be8', 'order', '_lock_snapshot_rows', ('body[0]',)),
    ('6fa79ea6bb64bf63', 'order', 'ovt_queue_poll', ('body[35]',)),
    ('6ffc0afa9220cd89', 'order', '_hold_latch', ('body[0]',)),
    ('700a9c994517fc89', 'order', '_lease_admission_gate', ('body[0]',)),
    ('7010117f5679e27c', 'order', 'home_of', ('body[3]',)),
    ('707e33823583618d', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'orelse[1]')),
    ('7083a85ce44089c9', 'order', '_group_region', ('body[8]',)),
    ('70994e5635df9760', 'order', '_is_number', ('body[0]',)),
    ('70be4cd962492b09', 'order', 'queue_poll', ('body[16]',)),
    ('70e8fbe588d8f6ce', 'order', '_pick', ('body[3]', 'body[0]')),
    ('71244d36a310fede', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]')),
    ('717bfa41bf406893', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[0]')),
    ('7189c773ecbffc52', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[2]')),
    ('71a8a6162e948306', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[8]')),
    ('71b1ce6a1252b35a', 'order', '_rules_for_members', ('body[3]', 'body[0]')),
    ('71f83ab327156eaa', 'order', 'queue_poll', ('body[17]',)),
    ('722ee9c6122fef08', 'order', 'team_queue_poll', ('body[69]',)),
    ('725b6c6111c6f604', 'order', '_mod_version_at_least', ('body[0]',)),
    ('726ce7a9c9c5b498', 'order', 'held_overlap', ('body[2]', 'body[6]')),
    ('731deca4c15ebd2c', 'order', 'team_queue_poll', ('body[19]', 'body[8]')),
    ('7371473bf1b554ee', 'order', '_team_resolve_live_family', ('body[5]',)),
    ('7416cdf545a336d5', 'order', 'team_queue_poll', ('body[45]',)),
    ('744a1ae56b598887', 'order', '_team_color_holders', ('body[2]', 'body[1]')),
    ('749ad1396ae8066a', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[1]')),
    ('74a2740c76cf9145', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[4]')),
    ('74a2740c76cf9145', 'order', 'ovt_queue_poll', ('body[16]', 'body[4]')),
    ('74db11fe8d6e3a77', 'order', '_service_player_uuids', ('body[0]',)),
    ('74efe3441888011f', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]')),
    ('7513339a677ff5d2', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[0]')),
    ('756cbbaa067c973b', 'order', '_pick', ('body[12]', 'body[0]')),
    ('75b806d466b3d30e', 'order', 'ovt_queue_poll', ('body[21]', 'orelse[1]')),
    ('761bad314a193cc7', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[13]')),
    ('7669ef06c3e58b64', 'order', '_pick', ('body[18]',)),
    ('76ca177529f281c8', 'order', '_pick', ('body[23]', 'orelse[0]')),
    ('776fb45834bc40be', 'order', 'pick_region_for_group', ('body[1]', 'body[0]')),
    ('778a8e2fc91df28b', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[2]')),
    ('778a8e2fc91df28b', 'order', 'ovt_queue_poll', ('body[16]', 'body[2]')),
    ('77b78acd1ac5598e', 'order', 'ovt_queue_poll', ('body[21]', 'body[10]')),
    ('77dfb7fbad7f56d3', 'order', '_group_region', ('body[2]',)),
    ('78273cc2fc8eca1e', 'order', '_ffa_queue_poll_inner', ('body[44]',)),
    ('783a70cca38098d2', 'order', '_formation_lease_conflict', ('body[2]', 'body[0]')),
    ('784d24b6a9c45971', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]', 'body[0]')),
    ('78879736c930a195', 'order', '_region_volumes', ('body[4]', 'body[0]')),
    ('78ab5b93b4d2e6e3', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]')),
    ('78ccd9018fa62161', 'order', '_pick', ('body[10]',)),
    ('7921c169aa3c62d1', 'order', '_lease_admission_gate', ('body[5]', 'body[1]')),
    ('79a0aac443e74598', 'order', 'team_queue_poll', ('body[34]',)),
    ('79a689950c09efbc', 'order', '_team_resolve_live_family', ('body[7]', 'body[0]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[2]', 'body[0]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[3]', 'body[1]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[1]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[0]', 'orelse[0]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[1]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[1]')),
    ('7a34d51b7817572e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[1]')),
    ('7a4a4d30ff55c6a3', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'body[0]')),
    ('7a5f58a95996bb50', 'order', '_ffa_queue_poll_inner', ('body[40]',)),
    ('7a926139eafcd32d', 'order', 'queue_poll', ('body[29]',)),
    ('7ad43a7b35ec85ad', 'order', '_ffa_sort_key', ('body[1]',)),
    ('7aed6fe66e4e03ca', 'order', 'team_queue_poll', ('body[70]',)),
    ('7aeffd373fa865dc', 'order', '_service_player_uuids', ('body[4]',)),
    ('7b3aa46973d8acf7', 'order', '_group_region', ('body[2]', 'body[2]')),
    ('7bc5ef069a9d05e8', 'order', 'series_fresh', ()),
    ('7bcf594cabaeefff', 'order', 'team_queue_poll', ('body[33]',)),
    ('7bff5c871b17df2d', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]', 'body[0]')),
    ('7bff5c871b17df2d', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]', 'body[0]')),
    ('7c22d85ef18df88c', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[1]')),
    ('7c4f2b739751f105', 'order', '_lease_acquire_many', ('body[5]',)),
    ('7c4f2b739751f105', 'order', '_region_pings_newer', ('body[1]', 'body[0]', 'body[0]')),
    ('7c7f2cbefe8bda44', 'order', '_ffa_queue_poll_inner', ('body[20]', 'body[0]')),
    ('7c7f2cbefe8bda44', 'order', '_ffa_queue_poll_inner', ('body[48]',)),
    ('7cbd0bc5d6b321c8', 'order', '_mode_or_400', ()),
    ('7d2563963c8001c1', 'order', '_hold_latch', ('body[4]',)),
    ('7d43dad34c59ca0d', 'order', '_pick', ('body[8]',)),
    ('7d676ffaccb066b8', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[3]')),
    ('7d676ffaccb066b8', 'order', 'ovt_queue_poll', ('body[15]', 'body[3]')),
    ('7d676ffaccb066b8', 'order', 'team_queue_poll', ('body[18]', 'body[4]')),
    ('7d73eceb5a0d5d15', 'order', '_ffa_queue_poll_inner', ('body[31]', 'body[1]')),
    ('7d8f596267ee1ab7', 'order', 'pick_region_for_group', ('body[1]',)),
    ('7e4d7c064e37605e', 'order', '_team_quartet_lock', ()),
    ('7e6193fe6acdb350', 'order', '_rules_for_members', ('body[0]',)),
    ('7e9d4f8d46b19498', 'order', 'ovt_queue_poll', ('body[21]', 'body[12]')),
    ('7f07198a70937738', 'order', '_team_resolve_live_family', ('body[3]',)),
    ('7f18ebd704edfb25', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[14]')),
    ('7f90493f76fe4c87', 'order', '_asm_sqlstate', ('body[3]', 'body[3]', 'body[0]')),
    ('8036d16d98649b98', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]')),
    ('8041ecda31276bec', 'order', '_rules_for_queue_match', ('body[3]',)),
    ('8079878614c822d8', 'order', '_group_region', ('body[2]', 'body[3]', 'body[2]')),
    ('80b96236d696c06a', 'order', 'queue_poll', ('body[24]', 'body[12]')),
    ('810d8e72f1a15705', 'order', '_ffa_queue_poll_inner', ('body[34]', 'body[1]')),
    ('8162f92d0239df4b', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[6]')),
    ('8168a16f5b649dac', 'order', 'queue_poll', ('body[24]', 'body[3]', 'body[0]')),
    ('81ba4e6673252b86', 'order', 'queue_poll', ('body[16]', 'body[4]')),
    ('81ba4e6673252b86', 'order', 'queue_poll', ('body[9]',)),
    ('81d7c84256319dc0', 'order', '_bet_fighter_tax', ('body[2]',)),
    ('8201df9b6d1a0bbf', 'order', '_bet_fighter_tax', ()),
    ('8210ab5737ba68ea', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]')),
    ('8210ab5737ba68ea', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]')),
    ('8254c1b70929699c', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]')),
    ('8256b8dca387f8a6', 'order', '_assert_no_service_subject', ()),
    ('82ae9ea21786bba9', 'order', '_rules_members', ('body[6]', 'body[0]')),
    ('82bc794298e90705', 'order', '_rules_normalize', ('body[1]',)),
    ('82cc27c4e9805992', 'order', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[1]')),
    ('831aeac4475d643d', 'order', '_rules_for_members', ('body[3]',)),
    ('838dfa0963508a8e', 'order', 'team_queue_poll', ('body[51]',)),
    ('8392571201c300cf', 'order', '_team_series_resumable', ('body[4]',)),
    ('83c8160aad8ce688', 'order', 'pick_region_for_group', ('body[1]', 'handlers[0]', 'body[0]')),
    ('8410f25edc33c598', 'order', 'queue_poll', ()),
    ('8432aefe33f764d9', 'order', '_lease_acquire', ('body[2]',)),
    ('845b49da1b125812', 'order', 'queue_poll', ('body[24]',)),
    ('84688fdeb59e7ac8', 'order', '_ffa_queue_poll_inner', ('body[16]',)),
    ('847d0967ed6b9afa', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]', 'body[0]')),
    ('84a09977321036dd', 'order', '_team_lock_family_pick', ('body[10]', 'body[3]')),
    ('85b2817d6608ead9', 'order', '_ffa_queue_poll_inner', ('body[9]',)),
    ('85cd7be03eaa62a5', 'order', '_asm_sqlstate', ('body[3]', 'body[3]', 'body[1]')),
    ('861db95dbb1bcc2d', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[3]')),
    ('8633039857b55272', 'order', 'ovt_queue_poll', ('body[15]', 'body[0]')),
    ('864d633d767e0d42', 'order', '_ffa_queue_poll_inner', ('body[47]',)),
    ('86b1296cb6b5ad85', 'order', '_pick', ('body[14]',)),
    ('86c7cbb763068132', 'order', '_team_relock_existing_series', ('body[2]',)),
    ('870ec7431bbdcec2', 'order', 'ovt_queue_poll', ('body[20]',)),
    ('874d52bd1317d17b', 'order', '_lease_admission_gate', ('body[4]',)),
    ('87c4edab35692981', 'order', '_lease_acquire', ('body[1]', 'body[0]')),
    ('87fd8011e087b012', 'order', '_pick', ('body[15]',)),
    ('8801122cec65db88', 'order', '_group_region', ('body[2]', 'body[5]', 'body[1]', 'body[0]')),
    ('88187bd93e1d1ad7', 'order', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]', 'orelse[0]')),
    ('8833719411c49b0d', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[13]')),
    ('8896febdcb1f88f6', 'order', 'team_queue_poll', ('body[0]',)),
    ('88b9b9af031c31bc', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[10]')),
    ('88b9b9af031c31bc', 'order', 'ovt_queue_poll', ('body[16]', 'body[8]')),
    ('8994ed72ef16f71a', 'order', 'team_queue_poll', ('body[34]', 'body[12]')),
    ('89ab09ef1b0580d4', 'order', '_pick', ('body[9]',)),
    ('8a11724e9603a2a3', 'order', '_balance_teams', ('body[5]',)),
    ('8a12f213fe248513', 'order', 'team_queue_poll', ('body[9]',)),
    ('8a34c57f59b35b48', 'order', '_pick', ('body[8]', 'body[0]')),
    ('8a5781016b19ae9a', 'order', '_assert_no_service_subject', ('body[4]', 'body[0]')),
    ('8a5781016b19ae9a', 'order', '_credit_bet_fighter_tax', ('body[1]', 'body[0]')),
    ('8a5781016b19ae9a', 'order', '_credit_team_bet_fighter_tax', ('body[1]', 'body[0]')),
    ('8a5781016b19ae9a', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[1]', 'body[0]')),
    ('8a5781016b19ae9a', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[1]')),
    ('8a5c69a6ddc8a837', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]')),
    ('8a9fb75ce44dc6ef', 'order', '_pick', ('body[5]', 'body[6]')),
    ('8accd76a90c8f3d0', 'order', 'ovt_queue_poll', ('body[16]', 'body[3]')),
    ('8b02e5a43bd498e8', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'body[3]')),
    ('8b7054c2a8d26481', 'order', '_ffa_queue_poll_inner', ('body[19]',)),
    ('8b8e159bb71b281f', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[8]')),
    ('8bd7a015854c93e0', 'order', 'team_queue_poll', ('body[17]', 'body[2]')),
    ('8c130372080b8541', 'order', '_region_candidate_volumes', ('body[0]',)),
    ('8c5c3f6efebc83a3', 'order', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[0]')),
    ('8c778e88688ca571', 'order', '_team_lock_family_pick', ('body[9]',)),
    ('8d86ba32cd642a12', 'order', '_baseline', ('body[7]',)),
    ('8d9d92d8f674cc19', 'order', '_request_mod_version', ('body[0]',)),
    ('8dd1533bc3c6b9e1', 'order', '_lease_admission_gate', ('body[14]', 'body[0]')),
    ('8dd1533bc3c6b9e1', 'order', '_lease_admission_gate', ('body[17]', 'body[1]', 'body[0]')),
    ('8dd1533bc3c6b9e1', 'order', '_lease_admission_gate', ('body[17]', 'body[4]', 'body[0]')),
    ('8dd1533bc3c6b9e1', 'order', '_lease_admission_gate', ('body[6]', 'body[1]')),
    ('8de3351b3ccc032d', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]')),
    ('8ef4d578bb730a83', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[2]')),
    ('8ef4d578bb730a83', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[1]', 'orelse[0]')),
    ('8f04561f22a5b573', 'order', 'team_queue_poll', ('body[40]', 'body[2]')),
    ('8f5cf9135b382e62', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]')),
    ('8f7b98ed963f6b50', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[2]')),
    ('8fe73594226f6da6', 'order', '_team_lock_family_pick', ('body[12]',)),
    ('9001ca031d1e6c59', 'order', '_team_lock_family_pick', ('body[8]',)),
    ('9021f459f0ee4d3a', 'order', '_rules_normalize', ('body[3]', 'body[0]', 'body[0]')),
    ('90249c44b0c73557', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[14]', 'body[0]')),
    ('906f510d4ce6030f', 'order', 'team_queue_poll', ('body[48]',)),
    ('907910bf71d310b2', 'order', '_lock_queue_rows_ordered', ()),
    ('908a5e01aea1b864', 'order', '_team_resolve_live_family', ('body[4]',)),
    ('90ae75984348b2ff', 'order', 'queue_poll', ('body[21]',)),
    ('90d15854407cb8df', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[4]')),
    ('91278ac4ec125171', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[0]')),
    ('91304b383c8fe2c9', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[1]')),
    ('91304b383c8fe2c9', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[1]')),
    ('92561f3c890b5fa1', 'order', '_team_resolve_live_family', ('body[7]',)),
    ('926543293f7163d5', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[3]')),
    ('928e612937074baf', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]', 'body[0]')),
    ('92a5789302f8924b', 'order', '_team_lock_family_pick', ('body[4]',)),
    ('92ac1a5bc8761da5', 'order', '_team_series_resumable', ('body[7]', 'body[0]')),
    ('92da1267ece979b1', 'order', '_team_lock_family_pick', ('body[10]', 'body[2]')),
    ('92e1589a7e0bf72b', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]', 'orelse[0]', 'orelse[0]', 'body[1]')),
    ('92e1589a7e0bf72b', 'order', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]', 'body[1]')),
    ('932f265b3d7e4b83', 'order', '_team_lock_family_pick', ()),
    ('933540a27faac847', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[4]')),
    ('933540a27faac847', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[13]')),
    ('933540a27faac847', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[7]')),
    ('93c3d9716d6c7f29', 'order', '_team_quartet_key', ()),
    ('943b3b7ec8b13cd6', 'order', 'queue_poll', ('body[28]', 'body[3]')),
    ('943de9fb7def16d2', 'order', 'queue_poll', ('body[28]', 'body[12]')),
    ('946ad944d2daf1ce', 'order', '_return_stake_exactly', ('body[3]',)),
    ('9564eed769b83850', 'order', '_pick', ('body[18]', 'body[5]')),
    ('95a7a0f20d004b2d', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[0]')),
    ('95b8267bf888ec5b', 'order', '_ffa_queue_poll_inner', ('body[3]',)),
    ('95bc091dac5b4b04', 'order', '_pick', ('body[23]', 'body[1]')),
    ('95bc72bd0208b8ab', 'order', 'team_queue_poll', ('body[26]',)),
    ('95beca30d41bcd68', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[3]')),
    ('95fae7ec0a5ce16b', 'order', '_team_lock_family_pick', ('body[7]', 'body[1]')),
    ('95fcb15309ea1a06', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[2]')),
    ('96b1a78d06a40241', 'order', '_ffa_queue_poll_inner', ('body[21]',)),
    ('96bb3a520e7f7e57', 'order', '_ffa_roster_clears_proximity_floor', ('body[1]',)),
    ('975a27cc6eca7ea8', 'order', '_ffa_queue_poll_inner', ('body[30]',)),
    ('97d424f4b4e3c6ce', 'order', 'queue_poll', ('body[28]', 'body[21]')),
    ('97ea4c26d2ae1062', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[0]')),
    ('9812fffd17b6165d', 'order', '_group_region', ('body[2]', 'body[8]')),
    ('981e34c1f1f869ed', 'order', '_team_series_resumable', ('body[3]',)),
    ('98453e3ee1425696', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[2]', 'body[2]')),
    ('986ff8e10d36075a', 'order', '_lease_admission_gate', ('body[2]',)),
    ('9883c3cb82700e6c', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]')),
    ('9892787742d3490d', 'order', '_lease_admission_gate', ('body[8]',)),
    ('98c23dae5010bfb2', 'order', '_team_relock_existing_series', ('body[5]',)),
    ('991e20fc97a5a568', 'order', 'team_queue_poll', ('body[46]',)),
    ('99571cf4cfcbb4fd', 'order', '_region_pings_newer', ('body[1]',)),
    ('996ebdfc08dc8a3b', 'order', '_latch_sql', ('body[1]',)),
    ('99ac3b5f7906b052', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[0]')),
    ('99fb332ea9597af1', 'order', '_team_relock_existing_series', ('body[4]',)),
    ('9a21a4adf3b3bea4', 'order', '_team_resolve_live_family', ('body[1]',)),
    ('9acfee56f4f6d8ed', 'order', '_baseline', ('body[4]',)),
    ('9acfee56f4f6d8ed', 'order', '_region_mode_of', ('body[4]',)),
    ('9b0bf59b1e39660e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[0]')),
    ('9bac8536804f0bd2', 'order', 'team_queue_poll', ('body[34]', 'body[14]')),
    ('9bc1a421c61211c9', 'order', 'team_queue_poll', ('body[19]', 'body[11]')),
    ('9be8d8314819b851', 'order', 'ovt_queue_poll', ('body[5]',)),
    ('9bfd68bbac05f8c1', 'order', '_ffa_gather_decide', ('body[4]',)),
    ('9c5bb828be6c7ab2', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]')),
    ('9c5bb828be6c7ab2', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]')),
    ('9c5bb828be6c7ab2', 'order', 'team_queue_poll', ('body[18]', 'body[5]')),
    ('9d0fb3a6380fe848', 'order', '_pick', ('body[8]', 'body[3]')),
    ('9d1a43bba17f98cf', 'order', 'team_queue_poll', ('body[50]',)),
    ('9d5bb1ece11143b8', 'order', 'queue_poll', ('body[23]',)),
    ('9da2dd160723efc1', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[3]')),
    ('9dab07ea32f8273e', 'order', '_clean_map', ()),
    ('9de56f351c13893f', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[14]')),
    ('9df6827a93cfaabd', 'order', '_group_region', ('body[2]', 'handlers[0]', 'body[0]')),
    ('9dfdc15a38a6e26c', 'order', '_stamp_team_series_colors', ()),
    ('9e11a85977e0c12d', 'order', '_asm_sqlstate', ('body[4]',)),
    ('9e11a85977e0c12d', 'order', '_clean_map', ('body[1]', 'body[0]')),
    ('9e11a85977e0c12d', 'order', '_formation_lease_conflict', ('body[4]',)),
    ('9e11a85977e0c12d', 'order', '_region_current', ('body[1]', 'body[0]')),
    ('9e11a85977e0c12d', 'order', '_request_mod_version', ('body[1]', 'handlers[0]', 'body[0]')),
    ('9e11a85977e0c12d', 'order', 'home_of', ('body[2]', 'body[0]')),
    ('9e1398fda07cc031', 'order', '_group_region', ('body[2]', 'body[5]', 'body[1]')),
    ('9e3eda57e336777e', 'order', '_service_player_uuids', ('body[2]',)),
    ('9e77dd339a544491', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[5]')),
    ('9e77dd339a544491', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[3]')),
    ('9e77dd339a544491', 'order', '_ffa_queue_poll_inner', ('body[5]', 'body[0]')),
    ('9e77dd339a544491', 'order', '_ffa_queue_poll_inner', ('body[7]', 'body[1]')),
    ('9e77dd339a544491', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[4]')),
    ('9e77dd339a544491', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[4]', 'body[0]')),
    ('9e77dd339a544491', 'order', 'ovt_queue_poll', ('body[7]', 'body[0]')),
    ('9e77dd339a544491', 'order', 'ovt_queue_poll', ('body[9]', 'body[1]')),
    ('9e81b3b264f37560', 'order', '_asm_sqlstate', ('body[3]', 'body[5]')),
    ('9e89d52672ee7e54', 'order', 'queue_poll', ('body[24]', 'body[2]')),
    ('9e92b32aee79c800', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[1]')),
    ('9e98ef0525285ac3', 'order', 'team_queue_poll', ('body[25]', 'body[1]')),
    ('9f44d4b9fca3e081', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[1]')),
    ('9f5833e9bf2213dc', 'order', '_team_relock_existing_series', ('body[3]',)),
    ('a015b2de32ddd5d6', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[7]')),
    ('a04fee63f37a2c2a', 'order', 'team_queue_poll', ('body[18]', 'body[5]', 'body[4]')),
    ('a0b14761239c8c84', 'order', 'ovt_queue_poll', ('body[19]',)),
    ('a0b14761239c8c84', 'order', 'ovt_queue_poll', ('body[21]', 'body[10]', 'body[1]')),
    ('a0b14761239c8c84', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[2]')),
    ('a0b14761239c8c84', 'order', 'ovt_queue_poll', ('body[21]', 'body[1]', 'body[0]')),
    ('a0b14761239c8c84', 'order', 'ovt_queue_poll', ('body[21]', 'body[5]', 'body[0]')),
    ('a0c685a77195edb8', 'order', '_team_resolve_live_family', ('body[0]',)),
    ('a0f67f62780aa700', 'order', 'team_queue_poll', ('body[18]', 'body[2]', 'body[1]')),
    ('a0f67f62780aa700', 'order', 'team_queue_poll', ('body[18]', 'body[5]', 'body[1]')),
    ('a12575c4c15e57ed', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'body[0]')),
    ('a129c2540a7086bf', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[0]', 'body[0]')),
    ('a1a3f90bf85e4367', 'order', '_lock_queue_rows_ordered', ('body[4]',)),
    ('a1c920f9f552b74f', 'order', 'team_queue_poll', ('body[63]',)),
    ('a1f05eaccd39cfcf', 'order', '_lease_admission_gate', ('body[16]',)),
    ('a225d9e331f79bd0', 'order', '_group_region', ('body[2]', 'body[9]')),
    ('a24aac3abbecc79f', 'order', '_ffa_queue_poll_inner', ('body[20]',)),
    ('a3bb0ae810815258', 'order', '_pick', ('body[10]', 'body[0]')),
    ('a3c744cb74e82a63', 'order', 'ovt_queue_poll', ('body[23]',)),
    ('a4226db78f3ce26e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[1]')),
    ('a4307684a3f1b804', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[0]')),
    ('a45698f909669e8b', 'order', '_credit_bet_fighter_tax', ('body[4]', 'body[0]')),
    ('a47de389bc4b22ae', 'order', 'team_queue_poll', ('body[34]', 'body[7]')),
    ('a48c99b2a3ab88c4', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[3]', 'body[0]')),
    ('a48d1642891bff80', 'order', '_group_region', ()),
    ('a508141b730091ee', 'order', 'team_queue_poll', ('body[52]',)),
    ('a53cb2447575fa5a', 'order', '_clean_map', ('body[3]', 'body[1]')),
    ('a53f148b3c490c05', 'order', 'ovt_queue_poll', ('body[38]',)),
    ('a59ceeb4e156ee64', 'order', '_ffa_queue_poll_inner', ('body[24]', 'body[0]')),
    ('a5af48018e73ffb5', 'order', 'team_queue_poll', ('body[60]',)),
    ('a5f8baaeb01e33cc', 'order', '_team_clear_dc_fallback_marker', ('body[0]',)),
    ('a60a8b7859ef4877', 'order', 'team_queue_poll', ('body[34]', 'body[8]')),
    ('a6531f506c07516f', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]')),
    ('a6548908c1c0a043', 'order', '_asm_sqlstate', ()),
    ('a6663107079a0b03', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[4]')),
    ('a68c520be2676d12', 'order', '_clean_map', ('body[3]', 'body[2]')),
    ('a71ae103158cbf7a', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[0]')),
    ('a766826b16f508a3', 'order', 'team_queue_poll', ('body[19]', 'body[16]')),
    ('a792576c260fec62', 'order', 'queue_poll', ('body[2]', 'body[0]')),
    ('a7b6cea2cb04f986', 'order', '_pick', ('body[5]', 'body[0]', 'body[0]')),
    ('a7dfe6962b9a7584', 'order', 'team_queue_poll', ('body[34]', 'body[2]')),
    ('a7eb04e2399c90a7', 'order', 'queue_poll', ('body[24]', 'body[4]')),
    ('a864581e5eca689d', 'order', 'team_queue_poll', ('body[19]', 'body[10]')),
    ('a8b74cefae01e00a', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'body[0]')),
    ('a8ed73358b0e379e', 'order', '_team_balance_rating', ('body[1]', 'body[0]')),
    ('a8ed73358b0e379e', 'order', '_team_balance_rating', ('body[2]', 'body[0]')),
    ('a934eab738c8df43', 'order', 'held_overlap', ('body[2]',)),
    ('a947a4b31fd59ffb', 'order', '_group_region', ('body[7]', 'body[0]')),
    ('a9a9123dff5b8c4e', 'order', '_player_body_color', ('body[3]',)),
    ('a9bbf02d08443fd6', 'order', '_pick', ('body[7]',)),
    ('a9e0fdeedba27003', 'order', '_credit_team_bet_fighter_tax', ('body[3]',)),
    ('a9e8d5fc73cbf91c', 'order', '_pick', ('body[22]',)),
    ('a9f94e6c1a82fe92', 'order', '_rules_json', ('body[2]',)),
    ('aa091f19b9a3e90e', 'order', '_return_stake_exactly', ('body[2]', 'body[0]')),
    ('aa3279ea5b05c8b7', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[2]')),
    ('aa35888fa5d41911', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[8]')),
    ('aa87790582aec52f', 'order', 'team_queue_poll', ('body[31]', 'body[2]')),
    ('aac5eb62b6398518', 'order', 'queue_poll', ('body[10]',)),
    ('aac5eb62b6398518', 'order', 'queue_poll', ('body[16]', 'body[5]')),
    ('ab748b31904bdcf9', 'order', '_mrw_mod', ('body[2]',)),
    ('ab8ed3617e9efbdd', 'order', '_baseline', ('body[6]',)),
    ('ab9eae1bde45a018', 'order', '_bet_fighter_tax', ('body[5]',)),
    ('abc6965c0c9a72d5', 'order', '_service_player_uuids', ('body[5]',)),
    ('ac3150380a164621', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[2]')),
    ('ac36b241dd5311d3', 'order', '_region_pings_newer', ('body[1]', 'body[1]')),
    ('ac3e64f544fd668d', 'order', '_formation_lease_conflict', ('body[3]', 'body[0]')),
    ('aca40187e57b098b', 'order', '_team_lock_family_pick', ('body[9]', 'body[0]')),
    ('acad70209ef35387', 'order', 'ovt_queue_poll', ('body[24]',)),
    ('acbd4eeb1a9da701', 'order', 'queue_poll', ('body[25]', 'body[2]')),
    ('ad15c0fa9394cdb4', 'order', '_lease_acquire', ('body[4]',)),
    ('ad39babe09aa0d5e', 'order', '_lease_acquire', ('body[1]',)),
    ('adcd7a688120c3a5', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[1]')),
    ('add5cec51a603e05', 'order', 'ovt_queue_poll', ('body[4]', 'body[0]')),
    ('add81cff679436d2', 'order', '_team_lock_family_pick', ('body[10]', 'body[4]')),
    ('ae2a15d5b30d83b9', 'order', '_latch_sql', ('body[2]',)),
    ('ae878b3cc23fda66', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[6]', 'body[0]')),
    ('aeae8ffc7201e4fe', 'order', '_ffa_queue_poll_inner', ('body[5]',)),
    ('aeae8ffc7201e4fe', 'order', 'ovt_queue_poll', ('body[7]',)),
    ('aeae8ffc7201e4fe', 'order', 'team_queue_poll', ('body[8]',)),
    ('af650e5c76cd2684', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]')),
    ('af98d9f68ee6bf32', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[8]')),
    ('aff1c84e24e8f697', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[2]')),
    ('b00fca1a2f00c1af', 'order', '_stamp_team_series_colors', ('body[2]', 'body[2]')),
    ('b0440285a54354b2', 'order', '_bet_fighter_tax', ('body[3]',)),
    ('b049f7e58e491fa0', 'order', '_ffa_queue_poll_inner', ('body[14]',)),
    ('b05f57b51d20c45f', 'order', '_team_quartet_lock', ('body[0]',)),
    ('b0a92292ad1029b6', 'order', 'ovt_queue_poll', ('body[15]', 'body[2]')),
    ('b0a92292ad1029b6', 'order', 'team_queue_poll', ('body[18]', 'body[3]')),
    ('b0d188af7e75bd18', 'order', '_lock_queue_rows_ordered', ('body[1]',)),
    ('b0d188af7e75bd18', 'order', '_lock_snapshot_rows', ('body[1]',)),
    ('b0e631c122efd6e9', 'order', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[2]')),
    ('b0e631c122efd6e9', 'order', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[2]')),
    ('b0ff999378d6d344', 'order', '_team_lock_family_pick', ('body[7]', 'body[0]')),
    ('b129b42d4f53e5d3', 'order', '_lease_admission_gate', ('body[2]', 'body[1]')),
    ('b14e1e6cddb99ad8', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[1]')),
    ('b14e1e6cddb99ad8', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[3]')),
    ('b199029912e92552', 'order', '_pick', ('body[19]',)),
    ('b1c234c306c6c46e', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[0]')),
    ('b1cd02bd5b634ee6', 'order', '_lease_admission_gate', ('body[10]',)),
    ('b21144b790874ca7', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[9]')),
    ('b2326d7e085bc2f2', 'order', 'ovt_queue_poll', ('body[15]',)),
    ('b286fd7ba7b78cfa', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[2]')),
    ('b2978bb33e6add82', 'order', '_lock_queue_rows_ordered', ('body[3]', 'body[0]', 'body[0]')),
    ('b2db8feac9a9a697', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[1]')),
    ('b2e4ab2737c3d0df', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[1]')),
    ('b2e6ec2f094ef0bb', 'order', '_lease_admission_gate', ('body[17]', 'body[1]')),
    ('b365047f445b8047', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[11]', 'body[0]')),
    ('b3984f8f692dff28', 'order', '_ffa_roster_clears_proximity_floor', ('body[0]',)),
    ('b3bb2a82e6888551', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]')),
    ('b3c96eb36bbbd5f9', 'order', '_clean_map', ('body[1]',)),
    ('b3d84832c913422d', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[12]')),
    ('b3e21b03d1d6e524', 'order', 'queue_poll', ('body[28]', 'orelse[1]')),
    ('b3f6a21646deebf2', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[6]')),
    ('b3f6a21646deebf2', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[6]')),
    ('b3f6a21646deebf2', 'order', 'ovt_queue_poll', ('body[22]', 'body[2]')),
    ('b41b756143e0ec82', 'order', '_rules_for_members', ('body[1]',)),
    ('b42bf9b8c7fefc69', 'order', '_ffa_queue_poll_inner', ('body[25]', 'body[0]')),
    ('b441a23488e37bbb', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]')),
    ('b462bd9fff9a1334', 'order', '_rules_for_members', ('body[3]', 'body[1]', 'orelse[0]')),
    ('b471783b183de19a', 'order', '_mrw_mod', ()),
    ('b5322730545a49f7', 'order', '_group_region', ('body[2]', 'body[0]')),
    ('b573f2875418eeac', 'order', '_service_player_uuids', ('body[3]',)),
    ('b5a66fa170bb8336', 'order', '_mrw_mod', ('body[0]',)),
    ('b5c150b681feaac9', 'order', '_formation_lease_conflict', ('body[3]',)),
    ('b5c75a7a70b2a6ae', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'orelse[0]', 'body[0]')),
    ('b5c75a7a70b2a6ae', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'orelse[0]', 'body[0]')),
    ('b5c944e9563b3c18', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[14]')),
    ('b5d3bca81644a506', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[3]', 'body[1]')),
    ('b6259a7360f0390c', 'order', '_region_volumes', ('body[3]',)),
    ('b6739fb175292af8', 'order', '_rules_for_queue_match', ('body[0]',)),
    ('b68c39b95a20d7bf', 'order', 'queue_poll', ('body[28]', 'body[2]')),
    ('b6962c41f3a87399', 'order', '_rules_members', ('body[4]', 'body[0]')),
    ('b6962c41f3a87399', 'order', '_rules_members', ('body[7]',)),
    ('b6962c41f3a87399', 'order', '_rules_normalize', ('body[4]',)),
    ('b69a3c0008a1eb8c', 'order', 'team_queue_poll', ('body[40]', 'body[3]')),
    ('b6ac457fc892357a', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[2]')),
    ('b707198148a42b4e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[6]')),
    ('b82b89572e4a3d5f', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[0]')),
    ('b855bf14ea490671', 'order', '_ffa_queue_poll_inner', ('body[10]',)),
    ('b8853d7f6855bde3', 'order', 'team_queue_poll', ('body[40]', 'body[0]')),
    ('b889e533489adefb', 'order', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[0]')),
    ('b889e533489adefb', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[1]')),
    ('b889e533489adefb', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[0]')),
    ('b889e533489adefb', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[0]')),
    ('b8949636a0f5a1ce', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[3]')),
    ('b8949636a0f5a1ce', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[4]')),
    ('b8949636a0f5a1ce', 'order', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[3]')),
    ('b8949636a0f5a1ce', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[4]')),
    ('b8de3b862c1481f3', 'order', '_team_quartet_lock', ('body[1]',)),
    ('b91e00e5c2e52232', 'order', 'ovt_queue_poll', ('body[12]',)),
    ('b93ef147eb454eac', 'order', 'team_queue_poll', ('body[40]', 'body[2]', 'body[0]', 'orelse[0]', 'body[0]')),
    ('b93f0d94c07efcfc', 'order', '_credit_team_bet_fighter_tax', ('body[0]',)),
    ('b9cda53d5f7240d7', 'order', '_balance_teams', ('body[4]', 'body[0]')),
    ('ba02670a8dfb49ce', 'order', '_asm_sqlstate', ('body[1]',)),
    ('ba2bf0fdf636cdcd', 'order', 'home_of', ('body[2]',)),
    ('ba5976a198b1c048', 'order', '_return_stake_exactly', ('body[0]',)),
    ('ba70bec38cfe98fd', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[0]')),
    ('ba9f75e8e54e2873', 'order', 'ovt_queue_poll', ('body[18]',)),
    ('bb197c6333ed70c9', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]', 'orelse[0]', 'orelse[0]')),
    ('bb3c1ed92b32d3ad', 'order', '_region_pings_newer', ('body[2]',)),
    ('bbe5faa22a7b74c6', 'order', 'team_queue_poll', ('body[47]', 'body[0]')),
    ('bc0819bbfe03e732', 'order', '_group_region', ('body[2]', 'body[5]', 'body[2]')),
    ('bc3c1f281bcaaa15', 'order', '_reconcile_team_series_bets', ('body[1]',)),
    ('bc5110a91d058a9a', 'order', 'anchor_fresh', ('body[2]',)),
    ('bc793d5e05a132f3', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[0]')),
    ('bc87be51ef20c447', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[11]')),
    ('bcd492d58926afd7', 'order', '_asm_sqlstate', ('body[3]', 'body[1]')),
    ('bcdee9b936ddc3c7', 'order', 'held_overlap', ('body[2]', 'body[1]')),
    ('bd6fc7d57b48d289', 'order', 'queue_poll', ('body[28]', 'body[14]')),
    ('bd79323f4f05d2c6', 'order', '_pick', ('body[20]', 'body[0]')),
    ('bd96805a4bfee9d2', 'order', '_ffa_queue_poll_inner', ('body[39]',)),
    ('be383063930bf189', 'order', 'series_holds', ('body[1]',)),
    ('be8d0dcbf54c260b', 'order', '_formation_lease_conflict', ('body[3]', 'body[2]', 'body[0]', 'body[0]')),
    ('be9fda909a5ed081', 'order', '_pick', ('body[21]',)),
    ('beace8ca2173031a', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'body[1]')),
    ('bf612ed83fd7ca0f', 'order', 'team_queue_poll', ('body[18]',)),
    ('bf8bc48d0bdaea65', 'order', 'team_queue_poll', ('body[68]',)),
    ('bfa25b5c65c75f64', 'order', '_region_volumes', ('body[2]',)),
    ('bfb83b5694dec317', 'order', 'queue_poll', ('body[22]',)),
    ('bfbeb718e6481598', 'order', 'queue_poll', ('body[28]', 'body[6]')),
    ('c042a4d18bc53dce', 'order', 'series_fresh', ('body[1]',)),
    ('c0978600f72101ff', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]')),
    ('c0a85f21b33ae24a', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[1]')),
    ('c0c38b273fa5ef92', 'order', '_team_lock_family_pick', ('body[6]',)),
    ('c0d25d96e6146e7b', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[1]', 'body[1]', 'body[0]')),
    ('c0d25d96e6146e7b', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]', 'body[5]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[8]')),
    ('c0d25d96e6146e7b', 'order', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[1]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', 'ovt_queue_poll', ('body[21]', 'body[13]', 'body[3]', 'body[0]')),
    ('c0d25d96e6146e7b', 'order', 'ovt_queue_poll', ('body[21]', 'body[15]')),
    ('c0d25d96e6146e7b', 'order', 'ovt_queue_poll', ('body[21]', 'body[1]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', 'ovt_queue_poll', ('body[21]', 'body[5]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[3]', 'body[0]')),
    ('c0d25d96e6146e7b', 'order', 'queue_poll', ('body[28]', 'body[9]', 'body[0]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[10]', 'body[2]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[16]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[2]', 'body[0]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[2]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[34]', 'body[15]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[34]', 'body[2]', 'body[1]')),
    ('c0d25d96e6146e7b', 'order', 'team_queue_poll', ('body[34]', 'body[8]', 'body[3]')),
    ('c0e34aba599a18bd', 'order', 'held_overlap', ()),
    ('c144653e7a8cbb82', 'order', '_rules_members', ('body[2]',)),
    ('c1a65cbf5a61f9a5', 'order', '_pick', ('body[17]',)),
    ('c220c48581ee55d4', 'order', 'team_queue_poll', ('body[6]',)),
    ('c267b2d0af877bae', 'order', 'queue_poll', ('body[20]',)),
    ('c321f2f247ef1502', 'order', '_lease_admission_gate', ('body[11]',)),
    ('c339addcaf2ae647', 'order', 'series_fresh', ('body[0]',)),
    ('c3405f79ec826379', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[8]', 'orelse[0]')),
    ('c3cdd50b59c7d0e5', 'order', '_rules_normalize', ('body[3]',)),
    ('c3d2eb3ec5e4fe0d', 'order', '_team_resolve_live_family', ('body[9]',)),
    ('c3f6a8583ccfc153', 'order', '_admission_key', ('body[0]',)),
    ('c4253834317a9ff4', 'order', '_assert_no_service_subject', ('body[2]',)),
    ('c49a5210be1d4a16', 'order', 'ovt_queue_poll', ('body[16]',)),
    ('c4a9c6373b5cf07f', 'order', '_team_lock_family_pick', ('body[11]', 'body[0]')),
    ('c4a9c6373b5cf07f', 'order', '_team_lock_family_pick', ('body[2]', 'body[0]')),
    ('c4de3ed15e57b879', 'order', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[2]')),
    ('c4ed5e2cf59c6d5b', 'order', 'queue_poll', ('body[28]', 'body[13]')),
    ('c4f5b1e674541cf4', 'order', 'team_queue_poll', ()),
    ('c506c4f69ce538e5', 'order', 'team_queue_poll', ('body[29]',)),
    ('c52d7c727d601c11', 'order', '_bet_fighter_tax', ('body[1]',)),
    ('c5526b4885abe23d', 'order', 'queue_poll', ('body[15]',)),
    ('c559a2b0bd33c384', 'order', '_ffa_queue_poll_inner', ('body[41]',)),
    ('c578e47b3cdc796c', 'order', '_lease_admission_gate', ('body[17]', 'body[4]')),
    ('c5c029bbab0a00a0', 'order', 'queue_poll', ('body[0]',)),
    ('c6023c05282fb9b2', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[4]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[2]', 'body[2]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[3]', 'body[3]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[4]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[3]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[3]')),
    ('c6470ee79dce1058', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[3]')),
    ('c652e6bc3f936696', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[0]')),
    ('c652e6bc3f936696', 'order', 'team_queue_poll', ('body[34]', 'body[0]')),
    ('c68c802a6bd67d2b', 'order', '_team_lock_family_pick', ('body[7]', 'body[2]')),
    ('c695097504d14410', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]')),
    ('c6b9f7c20b1d10c0', 'order', '_rules_members', ('body[6]',)),
    ('c706ed47a64880c0', 'order', '_pick', ('body[1]',)),
    ('c790f305eb592372', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]')),
    ('c7a112dd0dd7f6d5', 'order', '_region_volumes', ('body[3]', 'body[0]')),
    ('c7a112dd0dd7f6d5', 'order', '_region_volumes', ('body[5]',)),
    ('c7fcaf1af7954687', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[3]')),
    ('c842ca07ebe64745', 'order', '_bet_fighter_tax', ('body[6]',)),
    ('c871fcffce54a55a', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]')),
    ('c8eedf950fb919b6', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[2]')),
    ('c8f9496314e2b704', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]')),
    ('c8fe5cc1c56f4ec5', 'order', '_ffa_gather_decide', ('body[0]',)),
    ('c900deaed225e541', 'order', 'ovt_queue_poll', ('body[15]', 'body[3]', 'body[0]', 'body[0]')),
    ('c958f1f7645ab938', 'order', '_pick', ('body[8]', 'body[0]', 'body[0]')),
    ('ca0a257c8d62732e', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[0]')),
    ('ca0aaf621fb70c97', 'order', '_team_balance_rating', ('body[0]',)),
    ('ca4eb05f53f4b93b', 'order', 'team_queue_poll', ('body[64]',)),
    ('caba37469d9f6026', 'order', '_ffa_queue_poll_inner', ('body[28]', 'body[1]')),
    ('cadd992c794f8c9b', 'order', '_group_region', ('body[1]',)),
    ('cb2b72f9f5820ff5', 'order', '_lock_queue_rows_ordered', ('body[4]', 'body[1]', 'orelse[0]')),
    ('cbd218790f4f78b6', 'order', '_pick', ('body[5]', 'body[4]')),
    ('cbe667876a3168f5', 'order', '_mode_or_400', ('body[1]',)),
    ('cbe85f94a97e727c', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[7]')),
    ('cc50d0e77b787c69', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[0]')),
    ('cc50d0e77b787c69', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[0]', 'body[0]')),
    ('cc551327b6213b53', 'order', '_stamp_team_series_colors', ('body[3]', 'handlers[0]', 'body[0]')),
    ('cc8ad5504f321ac9', 'order', 'queue_poll', ('body[1]',)),
    ('cc8ad5504f321ac9', 'order', 'team_queue_poll', ('body[1]',)),
    ('ccb35f8a95acc7f9', 'order', '_team_balance_rating', ('body[2]',)),
    ('ccd476c5f41078b5', 'order', '_balance_teams', ('body[1]',)),
    ('ccd553588f728777', 'order', '_lease_admission_gate', ('body[5]', 'body[1]', 'body[1]', 'body[0]')),
    ('ccef94ee2cf4c34a', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'orelse[1]')),
    ('cd016b5dc525bc16', 'order', 'team_queue_poll', ('body[15]',)),
    ('cd6a995546a3cb36', 'order', '_stamp_team_series_colors', ('body[2]', 'body[3]')),
    ('cdb04c15b34c048b', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[5]')),
    ('cdb0b75f8767110c', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]', 'body[0]')),
    ('cdd0bf6daada030c', 'order', 'team_queue_poll', ('body[37]',)),
    ('cdda3fc48a4874f0', 'order', 'team_queue_poll', ('body[19]', 'body[12]')),
    ('cde5ae6c01a8d4b7', 'order', 'ovt_queue_poll', ('body[15]', 'body[1]')),
    ('cde5ae6c01a8d4b7', 'order', 'team_queue_poll', ('body[18]', 'body[2]')),
    ('cdf0070a2be70611', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[0]')),
    ('ce26ad2162851e81', 'order', '_team_lock_family_pick', ('body[4]', 'body[0]')),
    ('ce6d9bf65f6f3728', 'order', '_pick', ('body[18]', 'body[4]')),
    ('ce7ea7ac275ff11c', 'order', '_lease_admission_gate', ('body[5]', 'handlers[0]', 'body[1]', 'body[0]')),
    ('ceaf6133eb5b0558', 'order', '_ffa_queue_poll_inner', ('body[32]',)),
    ('cec75bd47f04b451', 'order', '_ffa_gather_decide', ()),
    ('cf5bec6ca446b14b', 'order', '_lease_live_claim_strict', ()),
    ('cf853744717cb633', 'order', '_lease_admission_gate', ('body[18]',)),
    ('cfa6bc4957779e21', 'order', '_lease_live_claim_strict', ('body[0]',)),
    ('cfae5076060f06b4', 'order', '_service_player_uuids', ('body[4]', 'body[0]')),
    ('cfd7b006b00bfdc1', 'order', '_pick', ('body[5]', 'body[1]')),
    ('cffcf026086bce0c', 'order', '_hold_latch', ('body[7]',)),
    ('d0ef3c353d7be5eb', 'order', 'team_queue_poll', ('body[19]', 'body[2]')),
    ('d108f6069529946f', 'order', 'queue_poll', ('body[28]', 'body[7]')),
    ('d141e9285c783ff1', 'order', '_formation_lease_conflict', ()),
    ('d14f3911012dd220', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[1]')),
    ('d1b8fb1001ff4106', 'order', 'ovt_queue_poll', ('body[21]', 'body[3]')),
    ('d1be5fb6f87f317c', 'order', 'ovt_queue_poll', ('body[34]', 'body[1]')),
    ('d1dd0ff775d0122f', 'order', 'team_queue_poll', ('body[35]',)),
    ('d1eeaf48ac23cbe7', 'order', 'ovt_queue_poll', ('body[6]',)),
    ('d27369df5507322e', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[0]', 'body[1]')),
    ('d2a079338e364f79', 'order', 'team_queue_poll', ('body[19]', 'body[5]')),
    ('d2e7ec1f27d20668', 'order', '_stamp_team_series_colors', ('body[3]', 'body[0]', 'body[0]')),
    ('d30cbfe942814a6a', 'order', 'ovt_queue_poll', ('body[15]', 'body[3]', 'handlers[0]', 'body[0]')),
    ('d351d55b85a4e0de', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[0]')),
    ('d3530fa2b2b248b8', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[6]')),
    ('d36ce02535ecd0aa', 'order', 'team_queue_poll', ('body[19]', 'body[11]', 'body[5]')),
    ('d3871732c0178e43', 'order', 'queue_poll', ('body[23]', 'body[2]')),
    ('d3c1483e859403d2', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[0]')),
    ('d3db659f10f0df2f', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[0]')),
    ('d4b944725a10e590', 'order', 'caps_token_sql', ()),
    ('d4e52491291fd9fd', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[5]')),
    ('d4f031c6cd9b6977', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[0]')),
    ('d51ce59a6d7fd463', 'order', '_lease_acquire_many', ('body[1]',)),
    ('d51ce59a6d7fd463', 'order', '_lease_admission_gate', ('body[1]',)),
    ('d56e160f7ff771b5', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[2]')),
    ('d5aeba0af8ffe7fc', 'order', 'queue_poll', ('body[22]', 'body[3]')),
    ('d5d09099618d07f1', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[5]')),
    ('d5d09099618d07f1', 'order', 'ovt_queue_poll', ('body[16]', 'body[5]')),
    ('d604b0a150bc2e73', 'order', '_rules_members', ('body[3]',)),
    ('d60d15c61b8f1c87', 'order', '_ffa_roster_clears_proximity_floor', ()),
    ('d631a0d3f3b52f49', 'order', 'queue_poll', ('body[27]',)),
    ('d631a0d3f3b52f49', 'order', 'queue_poll', ('body[28]', 'body[14]', 'body[1]')),
    ('d631a0d3f3b52f49', 'order', 'queue_poll', ('body[28]', 'body[16]', 'body[2]')),
    ('d651f3a6d0c3ef30', 'order', 'team_queue_poll', ('body[34]', 'body[10]')),
    ('d681e5c46ee41f43', 'order', '_clean_map', ('body[2]',)),
    ('d685d1d924e74e0d', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]')),
    ('d69fb730c9ea0896', 'order', 'queue_poll', ('body[14]', 'body[1]')),
    ('d69fb730c9ea0896', 'order', 'queue_poll', ('body[16]', 'body[3]', 'body[1]')),
    ('d69fb730c9ea0896', 'order', 'queue_poll', ('body[16]', 'body[7]', 'body[1]')),
    ('d69fb730c9ea0896', 'order', 'queue_poll', ('body[28]', 'body[1]', 'body[1]')),
    ('d69fb730c9ea0896', 'order', 'queue_poll', ('body[8]', 'body[1]')),
    ('d6eee2729256533c', 'order', '_region_mode_of', ()),
    ('d74546f905d0a073', 'order', '_ffa_queue_poll_inner', ('body[43]',)),
    ('d79be245cd72aa97', 'order', '_rules_normalize', ('body[3]', 'body[0]')),
    ('d7cc90ecbfb13fce', 'order', '_group_region', ('body[2]', 'body[3]', 'body[2]', 'body[0]')),
    ('d84adc9d19f25f6c', 'order', '_group_region', ('body[2]', 'body[2]', 'body[0]')),
    ('d8567dd278de7e83', 'order', 'team_queue_poll', ('body[31]', 'body[0]')),
    ('d88d8aed3677a1c4', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[10]')),
    ('d88d8aed3677a1c4', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[6]', 'body[2]')),
    ('d88e2abd41e54bd6', 'order', '_team_lock_family_pick', ('body[7]', 'body[1]', 'body[1]')),
    ('d8faa1153b03a407', 'order', '_pick', ('body[12]',)),
    ('d920308fc896730e', 'order', 'team_queue_poll', ('body[34]', 'body[5]')),
    ('d968786bbb94381a', 'order', '_ffa_queue_poll_inner', ('body[23]',)),
    ('d978fa8776fb912f', 'order', '_lease_acquire', ('body[3]',)),
    ('d9b240623d9e1e38', 'order', '_stamp_team_series_colors', ('body[1]',)),
    ('d9b240623d9e1e38', 'order', '_stamp_team_series_colors', ('body[2]', 'handlers[0]', 'body[1]')),
    ('d9c8d66b0d9284a5', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]')),
    ('d9db29a7081d630d', 'order', '_lease_admission_gate', ('body[5]', 'body[0]')),
    ('d9ddcbdcc48b3ae3', 'order', '_pick', ('body[13]',)),
    ('d9fe54326d9b3f55', 'order', '_credit_bet_fighter_tax', ('body[1]',)),
    ('d9fe54326d9b3f55', 'order', '_credit_team_bet_fighter_tax', ('body[1]',)),
    ('da0ed57a812204f6', 'order', '_region_volumes', ('body[1]',)),
    ('da4e5aebece216ab', 'order', '_stamp_team_series_colors', ('body[2]', 'body[4]')),
    ('dac7c13e268071fe', 'order', 'ovt_queue_poll', ('body[21]', 'body[2]')),
    ('dad1084dd290f580', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[3]')),
    ('dae27ee99941a112', 'order', '_lock_snapshot_rows', ('body[2]',)),
    ('daf6c50253406aac', 'order', '_team_lock_family_pick', ('body[2]',)),
    ('db8c5a9a112e0326', 'order', 'queue_poll', ('body[30]',)),
    ('dbc2356364a88c53', 'order', 'team_queue_poll', ('body[31]',)),
    ('dbd5683deab8f751', 'order', '_request_mod_version', ()),
    ('dbd8268543269617', 'order', 'ovt_queue_poll', ('body[21]', 'body[4]')),
    ('dcb3c5c4ab20bca5', 'order', 'team_queue_poll', ('body[19]', 'body[7]')),
    ('dcded1a5c4bddf05', 'order', 'team_queue_poll', ('body[35]', 'body[4]')),
    ('dd143835c8104de7', 'order', '_ffa_queue_poll_inner', ('body[25]',)),
    ('dd2cb7cf20001a1a', 'order', '_clean_map', ('body[3]', 'body[0]')),
    ('dd95de12a497e921', 'order', '_region_mode_of', ('body[5]',)),
    ('ddced25b8cc68549', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[3]')),
    ('ddcf3c4dd0d7ec43', 'order', '_lease_admission_gate', ('body[9]',)),
    ('de692986dd5c0baf', 'order', 'ovt_queue_poll', ('body[16]', 'body[5]', 'orelse[0]', 'body[0]')),
    ('decc6c5b9442a0d5', 'order', '_ffa_queue_poll_inner', ('body[0]',)),
    ('df4502448579b00a', 'order', 'queue_poll', ('body[28]', 'body[18]')),
    ('df5126f32df7d233', 'order', 'queue_poll', ('body[25]',)),
    ('df5126f32df7d233', 'order', 'team_queue_poll', ('body[23]',)),
    ('dfa4156ed21b62a2', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[3]')),
    ('dfd1399743b68e65', 'order', '_team_lock_family_pick', ('body[4]', 'body[1]')),
    ('dfebb196219cb821', 'order', '_team_color_holders', ('body[3]',)),
    ('e02b63bf7de08643', 'order', '_credit_team_bet_fighter_tax', ('body[2]',)),
    ('e06139294816ffa2', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[7]')),
    ('e0c24981212b326d', 'order', '_group_region', ('body[2]', 'body[5]', 'body[3]')),
    ('e0c2d28bca8db582', 'order', '_lease_admission_gate', ('body[17]', 'body[2]')),
    ('e0e2b5de76d7d626', 'order', 'team_queue_poll', ('body[30]',)),
    ('e0f37a3ea4460269', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[2]')),
    ('e131a5af92209b23', 'order', '_stamp_team_series_colors', ('body[2]', 'body[4]', 'body[0]')),
    ('e15d9400d272a5d3', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'orelse[0]')),
    ('e18c4b5295e9fc5b', 'order', '_pick', ('body[5]', 'body[0]')),
    ('e1b2fbf66d857764', 'order', '_asm_sqlstate', ('body[3]', 'body[0]')),
    ('e1ce90da939ff14e', 'order', '_team_color_holders', ('body[2]',)),
    ('e21e187f142fdd81', 'order', '_ffa_queue_poll_inner', ('body[36]',)),
    ('e2480eee2d18e929', 'order', '_formation_lease_conflict', ('body[3]', 'body[1]')),
    ('e292cd54b0a21ff6', 'order', '_group_region', ('body[7]', 'body[1]')),
    ('e2a88af984e8f130', 'order', '_region_current', ('body[1]',)),
    ('e2fbae762f88298b', 'order', '_ffa_queue_poll_inner', ('body[17]',)),
    ('e35e92fa2c816357', 'order', '_team_clear_dc_fallback_marker', ('body[1]', 'body[0]', 'body[0]')),
    ('e396348f6d90d246', 'order', 'ovt_queue_poll', ('body[21]', 'body[9]')),
    ('e46559e82c76a471', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[0]')),
    ('e478e352c6155837', 'order', '_lease_admission_gate', ('body[6]',)),
    ('e4aa8d41004cda79', 'order', 'ovt_queue_poll', ('body[16]', 'body[6]')),
    ('e4b451d2769272ec', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[1]', 'body[0]', 'body[0]')),
    ('e51b3e616dab0f8c', 'order', '_ffa_queue_poll_inner', ('body[33]', 'orelse[1]')),
    ('e5283b5432ee83f9', 'order', 'team_queue_poll', ('body[19]', 'body[4]', 'body[0]')),
    ('e54e169a0b52dc51', 'order', 'ovt_queue_poll', ('body[31]',)),
    ('e554f9fd77ec0be9', 'order', '_team_series_resumable', ('body[6]',)),
    ('e56832c810b55078', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[3]')),
    ('e57c273e32ab16bf', 'order', 'ovt_queue_poll', ('body[37]',)),
    ('e5def64f01c6b60c', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]', 'body[0]')),
    ('e6178f36562814ba', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[0]')),
    ('e64372489354c07e', 'order', '_hold_latch', ('body[2]',)),
    ('e6e7835b58fc40d0', 'order', '_pick', ('body[18]', 'body[1]')),
    ('e76cd15b07ef3e4a', 'order', 'held_overlap', ('body[1]',)),
    ('e7aa134c256165a5', 'order', 'team_queue_poll', ('body[40]', 'body[1]', 'body[1]')),
    ('e832f6bb100c1b3d', 'order', 'ovt_queue_poll', ('body[15]', 'body[5]')),
    ('e85a2a9c3eccf58d', 'order', 'queue_poll', ('body[18]',)),
    ('e85a2a9c3eccf58d', 'order', 'team_queue_poll', ('body[13]',)),
    ('e89d421a09a8d286', 'order', '_region_current', ('body[0]',)),
    ('e8eaa2c9756e95ec', 'order', '_pick', ('body[16]',)),
    ('e8edcf448cc1682f', 'order', '_pick', ('body[14]', 'body[0]')),
    ('e8f439e78326a29d', 'order', 'team_queue_poll', ('body[19]', 'body[1]', 'body[2]')),
    ('e8f4ceee252ef9a8', 'order', '_team_series_resumable', ()),
    ('e96bfae4d0bb39e6', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[1]')),
    ('e981f68a91c593f3', 'order', 'team_queue_poll', ('body[40]',)),
    ('e9a73f56c17166b1', 'order', 'ovt_queue_poll', ('body[25]', 'body[1]')),
    ('e9b6ddf2b4fb791b', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[0]', 'body[0]')),
    ('ea37fd81c3c6acc3', 'order', '_team_relock_existing_series', ('body[0]',)),
    ('ea3a86f949ed84b7', 'order', '_region_volumes', ('body[4]', 'body[1]', 'body[0]')),
    ('ea642f0352f5bc8f', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[4]')),
    ('eb4cb428904c4725', 'order', '_lease_acquire', ('body[1]', 'body[1]')),
    ('eb4cb428904c4725', 'order', '_lease_acquire_many', ('body[3]',)),
    ('eb4f0cbd788beb19', 'order', 'ovt_queue_poll', ('body[30]',)),
    ('eb5725ff3216e67d', 'order', '_pick', ('body[5]', 'body[2]')),
    ('eb6b67701dc8812e', 'order', 'home_of', ('body[1]',)),
    ('eb8cb351c1f6ce8d', 'order', 'team_queue_poll', ('body[35]', 'body[1]')),
    ('eb906396e8ac32cb', 'order', '_pick', ('body[5]', 'body[3]')),
    ('ebb4bb6ce26e36b6', 'order', '_group_region', ('body[2]', 'body[5]', 'body[2]', 'body[0]')),
    ('ec22986b00bde7af', 'order', '_lease_admission_gate', ('body[17]',)),
    ('ec2a57341d5c2fc4', 'order', '_rules_members', ('body[1]',)),
    ('ec44a0b958a11113', 'order', 'team_queue_poll', ('body[32]',)),
    ('ec5277aab8d3db7d', 'order', '_formation_lease_conflict', ('body[3]', 'body[5]')),
    ('ec66bcbca1eda449', 'order', '_pick', ('body[23]', 'body[2]')),
    ('ec7de7137b39164d', 'order', '_team_color_holders', ('body[2]', 'body[1]', 'body[0]')),
    ('ecffaaeab4d140c2', 'order', '_lease_acquire', ()),
    ('ed062257d61e5dce', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]')),
    ('ed22b4c37341facb', 'order', 'queue_poll', ('body[24]', 'body[7]')),
    ('ed60529e51e1ecbd', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'body[0]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_ffa_roster_clears_proximity_floor', ('body[1]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_hold_latch', ('body[3]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_lease_acquire', ('body[1]', 'body[1]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_lease_acquire_many', ('body[3]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_mod_version_at_least', ('body[1]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_mod_version_at_least', ('body[2]', 'handlers[0]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_team_series_resumable', ('body[1]', 'body[0]')),
    ('ede5d2543428e070', 'order', '_team_series_resumable', ('body[8]',)),
    ('ede5d2543428e070', 'order', 'anchor_fresh', ('body[1]', 'body[0]')),
    ('ee05333e43b89e4a', 'order', 'team_queue_poll', ('body[18]', 'body[5]', 'body[3]')),
    ('ee99c8251c46d375', 'order', '_pick', ('body[2]',)),
    ('eec28254c9962bb3', 'order', '_team_lock_family_pick', ('body[9]', 'body[1]')),
    ('eee20f7c50ecda99', 'order', '_team_lock_family_pick', ('body[11]',)),
    ('ef4a6c076940912f', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[1]')),
    ('ef6934f6f5ee2279', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[2]', 'body[0]')),
    ('ef6b678abd8e5e10', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]')),
    ('ef942c771176feab', 'order', '_stamp_team_series_colors', ('body[2]', 'body[1]')),
    ('efac647e5cc7c722', 'order', '_ffa_queue_poll_inner', ('body[33]', 'body[5]')),
    ('eff4c03dff2d8973', 'order', '_baseline', ()),
    ('f01e2674057472e9', 'order', '_ffa_queue_poll_inner', ('body[34]',)),
    ('f0493fb74d46bd30', 'order', 'team_queue_poll', ('body[22]', 'body[0]')),
    ('f04bf1e858b90f08', 'order', '_team_relock_existing_series', ('body[1]',)),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[12]', 'body[1]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[1]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[4]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[8]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[12]', 'body[3]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[3]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[16]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[8]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[15]',)),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[21]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[28]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[31]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[46]',)),
    ('f08dddfb3fb221e8', 'order', '_ffa_queue_poll_inner', ('body[7]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', '_team_relock_existing_series', ('body[8]',)),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[14]', 'body[1]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[15]', 'body[1]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[15]', 'body[4]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[15]', 'body[6]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[16]', 'body[10]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[16]', 'body[11]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[16]', 'body[12]')),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[17]',)),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[36]',)),
    ('f08dddfb3fb221e8', 'order', 'ovt_queue_poll', ('body[9]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[14]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[16]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[16]', 'body[3]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[16]', 'body[7]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[23]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[11]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[2]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[3]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[8]', 'body[1]', 'body[3]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[11]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[9]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[8]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[25]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[26]',)),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[28]', 'body[1]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[28]', 'body[20]')),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[31]',)),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[6]',)),
    ('f08dddfb3fb221e8', 'order', 'queue_poll', ('body[8]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[11]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[17]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[18]', 'body[2]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[18]', 'body[5]', 'body[2]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[18]', 'body[7]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[4]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[2]', 'body[6]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[4]', 'body[4]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[5]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[15]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[1]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[19]', 'body[4]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[23]', 'body[1]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[24]',)),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[25]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[15]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[31]', 'body[3]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[48]', 'body[0]')),
    ('f08dddfb3fb221e8', 'order', 'team_queue_poll', ('body[62]',)),
    ('f0afe992ecf36d47', 'order', 'team_queue_poll', ('body[57]', 'body[0]')),
    ('f0ba102001410016', 'order', 'ovt_queue_poll', ('body[21]', 'body[6]')),
    ('f0ccc524f8c14d08', 'order', '_team_series_resumable', ('body[1]',)),
    ('f0d65e07fa83c6b1', 'order', 'team_queue_poll', ('body[34]', 'orelse[1]')),
    ('f0e66b73b4b5f9a1', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[10]')),
    ('f10b79eea2e90802', 'order', 'queue_poll', ('body[7]',)),
    ('f179f00c924122c3', 'order', '_baseline', ('body[5]',)),
    ('f18724d8a844f45d', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[1]')),
    ('f1bb645e6e888f54', 'order', '_lease_admission_gate', ('body[13]',)),
    ('f1cbe755223e74ff', 'order', 'ovt_queue_poll', ('body[27]',)),
    ('f1db8b0266703a55', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[11]', 'body[2]', 'body[0]')),
    ('f212850dcdbc17f9', 'order', '_lock_queue_rows_ordered', ('body[1]', 'body[0]')),
    ('f212850dcdbc17f9', 'order', '_lock_snapshot_rows', ('body[1]', 'body[0]')),
    ('f28603d1d3c00bc4', 'order', 'ovt_queue_poll', ()),
    ('f2e0d99b40d35953', 'order', '_team_relock_existing_series', ('body[9]',)),
    ('f2ee5cee43686a82', 'order', '_lease_acquire_many', ('body[4]', 'body[0]')),
    ('f38a97faa7adc0c1', 'order', 'queue_poll', ('body[16]', 'body[3]')),
    ('f38a97faa7adc0c1', 'order', 'queue_poll', ('body[8]',)),
    ('f3bae33f454da3b7', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[3]')),
    ('f4247d166fc15aec', 'order', '_formation_lease_conflict', ('body[3]', 'body[2]', 'body[0]')),
    ('f4429dd80499f6cf', 'order', '_pick', ('body[18]', 'body[2]')),
    ('f4523040de1336cb', 'order', '_group_region', ('body[4]',)),
    ('f45c22a4a83fa434', 'order', '_group_region', ('body[2]', 'body[3]', 'body[1]')),
    ('f45dbf31738551d5', 'order', 'queue_poll', ('body[22]', 'body[1]')),
    ('f485f6b975d7e98f', 'order', 'ovt_queue_poll', ('body[22]', 'body[1]')),
    ('f4d45f0ca516a7f7', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[13]', 'body[2]')),
    ('f4dbccb0eb6ad866', 'order', '_reconcile_team_series_bets', ('body[1]', 'body[0]', 'body[9]', 'body[0]')),
    ('f4e3be19dd808e0c', 'order', '_admission_key', ()),
    ('f50793634ad881e4', 'order', '_region_mode_of', ('body[2]',)),
    ('f56c1613654be179', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[1]', 'body[0]')),
    ('f57c215ba3452da1', 'order', '_ffa_queue_poll_inner', ('body[13]', 'body[3]', 'handlers[0]', 'body[0]')),
    ('f57e552bba75a3a0', 'order', '_team_series_resumable', ('body[0]',)),
    ('f5a5ef258f23924b', 'order', 'team_queue_poll', ('body[43]',)),
    ('f5a90bd238bf9bca', 'order', '_ffa_roster_clears_proximity_floor', ('body[2]',)),
    ('f5e956da7a26b8e3', 'order', 'team_queue_poll', ('body[35]', 'body[2]')),
    ('f62a9db56db24f81', 'order', '_stamp_team_series_colors', ('body[2]',)),
    ('f64385852ca0f6a0', 'order', '_rules_members', ('body[1]', 'body[0]')),
    ('f6507fb48dbd0ecd', 'order', 'team_queue_poll', ('body[19]',)),
    ('f686d9e38ce9def3', 'order', 'team_queue_poll', ('body[34]', 'body[13]', 'body[2]', 'body[0]')),
    ('f686d9e38ce9def3', 'order', 'team_queue_poll', ('body[34]', 'body[8]', 'body[2]')),
    ('f6d0135decc0aff5', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[4]')),
    ('f6e1072f9df70a52', 'order', '_rules_json', ('body[1]',)),
    ('f7718f44a94e31cc', 'order', '_group_region', ('body[2]', 'body[6]')),
    ('f7734d30a2043c01', 'order', '_pick', ('body[25]',)),
    ('f79d5b24345eb51f', 'order', '_rules_members', ()),
    ('f7a6932a9c9be5c6', 'order', 'queue_poll', ('body[24]', 'body[0]')),
    ('f7f20a0ca9ae26c0', 'order', '_balance_teams', ('body[2]',)),
    ('f89af2aa8fe6e09e', 'order', 'team_queue_poll', ('body[25]',)),
    ('f8abc98c023ce61b', 'order', '_credit_team_bet_fighter_tax', ('body[6]',)),
    ('f8e211bd496e62be', 'order', '_team_clear_dc_fallback_marker', ('body[1]', 'handlers[0]', 'body[0]')),
    ('f8e211bd496e62be', 'order', '_team_relock_existing_series', ('body[6]', 'handlers[0]', 'body[0]')),
    ('f952fbfbb1944777', 'order', 'team_queue_poll', ('body[16]',)),
    ('f98b6ce8842d31f8', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[6]')),
    ('f991420c836ad273', 'order', '_rules_normalize', ('body[3]', 'body[1]', 'body[0]')),
    ('f9a8051a6acfa0f3', 'order', '_reconcile_team_series_bets', ('body[0]',)),
    ('f9b27877803946fb', 'order', '_group_region', ('body[2]', 'body[3]')),
    ('f9e50501484ddce6', 'order', 'team_queue_poll', ('body[19]', 'body[10]', 'body[1]', 'body[0]')),
    ('f9f163dc92777560', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[9]')),
    ('fa6cd6d9edec8cec', 'order', '_region_volumes', ('body[4]', 'handlers[0]', 'body[0]')),
    ('fad7c408e96a3258', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[6]')),
    ('faf9d3eb36972efb', 'order', 'team_queue_poll', ('body[19]', 'body[14]', 'body[1]', 'body[10]')),
    ('fb2d411bb07eec21', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[12]', 'body[0]')),
    ('fb524bbfb28586ba', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'body[2]', 'body[0]')),
    ('fb9590efe868386c', 'order', '_ffa_queue_poll_inner', ('body[28]',)),
    ('fc19b4801c801499', 'order', '_group_region', ('body[7]',)),
    ('fc209b80f7552cb6', 'order', '_rules_json', ('body[3]',)),
    ('fc487e62deb9f3c4', 'order', 'team_queue_poll', ('body[31]', 'body[2]', 'body[12]', 'body[1]')),
    ('fca8da89bd1bec36', 'order', '_service_player_uuids', ('body[4]', 'body[0]', 'handlers[0]', 'body[2]', 'body[0]')),
    ('fcd523d6dd605216', 'order', '_rules_normalize', ()),
    ('fceecc00006692a1', 'order', '_pick', ('body[3]', 'body[1]')),
    ('fcefc0b345a3e845', 'order', '_hold_latch', ('body[3]',)),
    ('fcfbba6ad74511c8', 'order', '_group_region', ('body[2]', 'body[5]', 'body[1]', 'body[0]', 'body[0]')),
    ('fd9f553644442f19', 'order', '_lease_admission_gate', ('body[15]',)),
    ('fd9f96060cb6817a', 'order', 'team_queue_poll', ('body[35]', 'body[2]', 'body[0]')),
    ('fde140b1e79f2e3e', 'order', 'team_queue_poll', ('body[27]',)),
    ('fdf848c7bac25202', 'order', 'queue_poll', ('body[24]', 'body[8]')),
    ('fe1fbad014dfcc6a', 'order', '_ffa_queue_poll_inner', ('body[50]',)),
    ('fe35be7d7f401cbd', 'order', 'home_of', ('body[0]',)),
    ('fe5bdbed4fede82c', 'order', '_group_region', ('body[3]', 'body[0]')),
    ('fe5c3378168e98b0', 'order', '_balance_teams', ('body[4]', 'body[2]')),
    ('fe6ef4a5fa6289c2', 'order', '_credit_bet_fighter_tax', ('body[4]',)),
    ('fe8a67c1f5f1e48d', 'order', 'ovt_queue_poll', ('body[33]',)),
    ('feecdb32460870c3', 'order', '_credit_bet_fighter_tax', ('body[5]',)),
    ('feee23206e3d5dd9', 'order', '_rules_for_members', ('body[3]', 'body[1]')),
    ('ff0d372f51ce8cfa', 'order', 'queue_poll', ('body[24]', 'body[10]', 'body[3]')),
    ('ff0d372f51ce8cfa', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[4]', 'orelse[0]', 'orelse[0]')),
    ('ff30e8df2d5ddb2c', 'order', 'queue_poll', ('body[17]', 'body[0]')),
    ('ff392cdc7d3ffa7d', 'order', '_ffa_queue_poll_inner', ('body[14]', 'body[11]', 'body[2]', 'body[1]')),
    ('ff392cdc7d3ffa7d', 'order', 'ovt_queue_poll', ('body[16]', 'body[9]', 'body[2]', 'body[1]')),
    ('ff541e9591afb190', 'order', '_pick', ('body[3]',)),
    ('ff977917d47ee26d', 'order', '_credit_bet_fighter_tax', ()),
    ('ff9d0a6e8fee8525', 'order', 'queue_poll', ('body[11]',)),
    ('ffca8955471f4d73', 'order', 'queue_poll', ('body[24]', 'body[9]', 'body[8]')),
    ('ffe28aadcd8089ad', 'order', '_ffa_queue_poll_inner', ('body[34]', 'body[2]')),
    ('fff646cfc0aab315', 'order', '_mod_version_at_least', ('body[2]',)),
    ('fff646cfc0aab315', 'order', '_parse_version', ('body[0]',)),
    ('fff646cfc0aab315', 'order', '_request_mod_version', ('body[1]',)),
    ('fff646cfc0aab315', 'order', '_rules_normalize', ('body[2]', 'body[0]')),
    ('fff646cfc0aab315', 'order', '_team_clear_dc_fallback_marker', ('body[1]',)),
    ('fff646cfc0aab315', 'order', '_team_relock_existing_series', ('body[6]',)),
})
A1_BINDINGS = A1_BINDINGS | A1_ORDERS | frozenset({("<orders>",)})

A1_IMPORTS = frozenset({
    ('tournaments', '_region_candidate_volumes', None),
    (None, 'match_report_window', None),
    (None, 'uuid', 'uuid_mod'),
})


# The frozen callee table (round 8, ruling REHEARSAL-FOUR-R7-A1, M4; rule
# (1)(c); closed_walk.Bindings.callee): every callee the real walks reach
# outside the walked function's own module namespace, as (form, file,
# line, name) - the form is the callee's spelling, or a local import's
# statement text, and (file, line, name) its frozen span in A1_SPANS. The
# test binds each form to its function by its own static imports
# (test_a1_identity_formation._A1_CALLEES) and asserts the two agree; no
# other callee outside a module's namespace resolves.
A1_CALLEES = frozenset({
    ('from tournaments import _region_candidate_volumes', 'tournaments.py',
     279, '_region_candidate_volumes'),
    ('_match_hold._hold_latch', 'match_hold.py', 364, '_hold_latch'),
    ('_mrw_mod().series_fresh', 'match_report_window.py', 77, 'series_fresh'),
    ('_mrw_mod().series_holds', 'match_report_window.py', 85, 'series_holds'),
})


# The definition scope (round 8, ruling REHEARSAL-FOUR-R7-A1, M5;
# closed_walk.Bindings.namedtuple_class): the spelled shape
# (shape_grammar.shape, plus '#<spelling>' for a Name) of EVERY node of
# region_pick.py, the one module whose classes (_Seat, _Cand) the real
# walks construct, GENERATED ONCE at 3130bb9d by RF/r8/ga1/gen_r8_frozen.py
# and frozen. Round 7's ten statement shapes admitted the class's own
# statement only; now a node region_pick.py gains anywhere (a store to a
# class or its attributes, a setattr call, a class statement) refuses the
# constructor call by shape.
A1_NAMEDTUPLES = frozenset({
    '<root>>Module(body=[Assign|Expr|FunctionDef|Import|ImportFrom],type_ignores=[])',  # region_pick:0
    'Expr.value>Constant(value=str)',  # region_pick:1
    'Module.body>Expr(value=Constant)',  # region_pick:1
    "Import.names>alias(name='time',asname=None)",  # region_pick:18
    "Module.body>Import(names=['time'])",  # region_pick:18
    "ImportFrom.names>alias(name='Counter',asname=None)",  # region_pick:19
    "ImportFrom.names>alias(name='namedtuple',asname=None)",  # region_pick:19
    "Module.body>ImportFrom(module='collections',names=[alias],level=0)",  # region_pick:19
    'Assign.targets>Name(id=str,ctx=Store)#PING_MIN_MS',  # region_pick:21
    'Assign.value>Constant(value=int)',  # region_pick:21
    'Module.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # region_pick:21
    'Name.ctx>Store()',  # region_pick:21
    'Assign.targets>Name(id=str,ctx=Store)#PING_MAX_MS',  # region_pick:22
    'Assign.targets>Name(id=str,ctx=Store)#WHY_BASELINE',  # region_pick:24
    'Assign.value>Constant(value=str)',  # region_pick:24
    'Assign.targets>Name(id=str,ctx=Store)#WHY_MAJORITY',  # region_pick:25
    'Assign.targets>Name(id=str,ctx=Store)#WHY_BOUNDED',  # region_pick:26
    'Assign.targets>Name(id=str,ctx=Store)#WHY_QUORUM',  # region_pick:27
    'Assign.targets>Name(id=str,ctx=Store)#WHY_ERROR',  # region_pick:28
    'Assign.targets>Name(id=str,ctx=Store)#_MAJORITY_STRICT',  # region_pick:31
    'Assign.value>Constant(value=bool)',  # region_pick:31
    'Assign.targets>Name(id=str,ctx=Store)#_SKIP_QUORUM',  # region_pick:32
    'Assign.targets>Name(id=str,ctx=Store)#_SELECT_BY_WORST',  # region_pick:33
    'Assign.targets>Name(id=str,ctx=Store)#_Seat',  # region_pick:35
    'Assign.value>Call(func=Name,args=[Constant],keywords=[])',  # region_pick:35
    'Call.args>Constant(value=str)',  # region_pick:35
    'Call.func>Name(id=str,ctx=Load)#namedtuple',  # region_pick:35
    'Module.body>Assign(targets=[Name],value=Call,type_comment=-)',  # region_pick:35
    'Name.ctx>Load()',  # region_pick:35
    'Assign.targets>Name(id=str,ctx=Store)#_Cand',  # region_pick:36
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # region_pick:39
    'Module.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:39
    'arguments.args>arg(arg=str,annotation=-,type_comment=-)',  # region_pick:39
    'BoolOp.op>And()',  # region_pick:40
    'BoolOp.values>Call(func=Name,args=[Name|Tuple],keywords=[])',  # region_pick:40
    'BoolOp.values>UnaryOp(op=Not,operand=Call)',  # region_pick:40
    'Call.args>Name(id=str,ctx=Load)#bool',  # region_pick:40
    'Call.args>Name(id=str,ctx=Load)#value',  # region_pick:40
    'Call.args>Tuple(elts=[Name],ctx=Load)',  # region_pick:40
    'Call.func>Name(id=str,ctx=Load)#isinstance',  # region_pick:40
    'FunctionDef.body>Return(value=BoolOp)',  # region_pick:40
    'Return.value>BoolOp(op=And,values=[Call|UnaryOp])',  # region_pick:40
    'Tuple.ctx>Load()',  # region_pick:40
    'Tuple.elts>Name(id=str,ctx=Load)#float',  # region_pick:40
    'Tuple.elts>Name(id=str,ctx=Load)#int',  # region_pick:40
    'UnaryOp.op>Not()',  # region_pick:40
    'UnaryOp.operand>Call(func=Name,args=[Name],keywords=[])',  # region_pick:40
    'Module.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:43
    'FunctionDef.body>Expr(value=Constant)',  # region_pick:44
    'Call.args>Name(id=str,ctx=Load)#dict',  # region_pick:48
    'Call.args>Name(id=str,ctx=Load)#raw',  # region_pick:48
    'FunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',  # region_pick:48
    'If.test>UnaryOp(op=Not,operand=Call)',  # region_pick:48
    'If.body>Return(value=Constant)',  # region_pick:49
    'Return.value>Constant(value=NoneType)',  # region_pick:49
    'Assign.targets>Name(id=str,ctx=Store)#clean',  # region_pick:50
    'Assign.value>Dict(keys=[],values=[])',  # region_pick:50
    'FunctionDef.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # region_pick:50
    'Attribute.ctx>Load()',  # region_pick:51
    'Attribute.value>Name(id=str,ctx=Load)#raw',  # region_pick:51
    "Call.func>Attribute(value=Name,attr='items',ctx=Load)",  # region_pick:51
    'For.iter>Call(func=Attribute,args=[],keywords=[])',  # region_pick:51
    'For.target>Tuple(elts=[Name],ctx=Store)',  # region_pick:51
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|If],orelse=[],type_comment=-)',  # region_pick:51
    'Tuple.ctx>Store()',  # region_pick:51
    'Tuple.elts>Name(id=str,ctx=Store)#key',  # region_pick:51
    'Tuple.elts>Name(id=str,ctx=Store)#ms',  # region_pick:51
    'BoolOp.op>Or()',  # region_pick:52
    'BoolOp.values>UnaryOp(op=Not,operand=Name)',  # region_pick:52
    'Call.args>Name(id=str,ctx=Load)#key',  # region_pick:52
    'Call.args>Name(id=str,ctx=Load)#str',  # region_pick:52
    'For.body>If(test=BoolOp,body=[Continue],orelse=[])',  # region_pick:52
    'If.test>BoolOp(op=Or,values=[UnaryOp])',  # region_pick:52
    'UnaryOp.operand>Name(id=str,ctx=Load)#key',  # region_pick:52
    'If.body>Continue()',  # region_pick:53
    'BoolOp.values>Call(func=Name,args=[Name],keywords=[])',  # region_pick:54
    'Call.args>Name(id=str,ctx=Load)#int',  # region_pick:54
    'Call.args>Name(id=str,ctx=Load)#ms',  # region_pick:54
    'If.test>BoolOp(op=Or,values=[Call|UnaryOp])',  # region_pick:54
    'Compare.comparators>Name(id=str,ctx=Load)#PING_MAX_MS',  # region_pick:56
    'Compare.comparators>Name(id=str,ctx=Load)#ms',  # region_pick:56
    'Compare.left>Name(id=str,ctx=Load)#PING_MIN_MS',  # region_pick:56
    'Compare.ops>LtE()',  # region_pick:56
    'For.body>If(test=UnaryOp,body=[Continue],orelse=[])',  # region_pick:56
    'If.test>UnaryOp(op=Not,operand=Compare)',  # region_pick:56
    'UnaryOp.operand>Compare(left=Name,ops=[LtE],comparators=[Name])',  # region_pick:56
    'Assign.targets>Subscript(value=Name,slice=Name,ctx=Store)',  # region_pick:58
    'Assign.value>Name(id=str,ctx=Load)#ms',  # region_pick:58
    'For.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # region_pick:58
    'Subscript.ctx>Store()',  # region_pick:58
    'Subscript.slice>Name(id=str,ctx=Load)#key',  # region_pick:58
    'Subscript.value>Name(id=str,ctx=Load)#clean',  # region_pick:58
    'BoolOp.values>Constant(value=NoneType)',  # region_pick:59
    'BoolOp.values>Name(id=str,ctx=Load)#clean',  # region_pick:59
    'Return.value>BoolOp(op=Or,values=[Constant|Name])',  # region_pick:59
    'Module.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:62
    'Assign.targets>Name(id=str,ctx=Store)#homes',  # region_pick:74
    'Assign.value>ListComp(elt=Attribute,generators=[comprehension])',  # region_pick:74
    'Attribute.value>Name(id=str,ctx=Load)#s',  # region_pick:74
    'FunctionDef.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # region_pick:74
    "ListComp.elt>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick:74
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Attribute],is_async=0)',  # region_pick:74
    "comprehension.ifs>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick:74
    'comprehension.iter>Name(id=str,ctx=Load)#seats',  # region_pick:74
    'comprehension.target>Name(id=str,ctx=Store)#s',  # region_pick:74
    'If.test>UnaryOp(op=Not,operand=Name)',  # region_pick:75
    'UnaryOp.operand>Name(id=str,ctx=Load)#homes',  # region_pick:75
    'If.body>Return(value=Tuple)',  # region_pick:76
    'Return.value>Tuple(elts=[Constant|Name],ctx=Load)',  # region_pick:76
    'Tuple.elts>Constant(value=NoneType)',  # region_pick:76
    'Tuple.elts>Name(id=str,ctx=Load)#legacy_pick',  # region_pick:76
    'Assign.targets>Name(id=str,ctx=Store)#counts',  # region_pick:77
    'Assign.value>Call(func=Name,args=[Name],keywords=[])',  # region_pick:77
    'Call.args>Name(id=str,ctx=Load)#homes',  # region_pick:77
    'Call.func>Name(id=str,ctx=Load)#Counter',  # region_pick:77
    'FunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',  # region_pick:77
    'Assign.targets>Name(id=str,ctx=Store)#top',  # region_pick:78
    'Assign.value>Call(func=Name,args=[Call],keywords=[])',  # region_pick:78
    'Attribute.value>Name(id=str,ctx=Load)#counts',  # region_pick:78
    'Call.args>Call(func=Attribute,args=[],keywords=[])',  # region_pick:78
    "Call.func>Attribute(value=Name,attr='values',ctx=Load)",  # region_pick:78
    'Call.func>Name(id=str,ctx=Load)#max',  # region_pick:78
    'Assign.targets>Name(id=str,ctx=Store)#tied',  # region_pick:79
    'Assign.value>Call(func=Name,args=[GeneratorExp],keywords=[])',  # region_pick:79
    'Call.args>GeneratorExp(elt=Name,generators=[comprehension])',  # region_pick:79
    'Call.func>Name(id=str,ctx=Load)#sorted',  # region_pick:79
    'Compare.comparators>Name(id=str,ctx=Load)#top',  # region_pick:79
    'Compare.left>Name(id=str,ctx=Load)#n',  # region_pick:79
    'Compare.ops>Eq()',  # region_pick:79
    'GeneratorExp.elt>Name(id=str,ctx=Load)#code',  # region_pick:79
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # region_pick:79
    'Tuple.elts>Name(id=str,ctx=Store)#code',  # region_pick:79
    'Tuple.elts>Name(id=str,ctx=Store)#n',  # region_pick:79
    'comprehension.ifs>Compare(left=Name,ops=[Eq],comparators=[Name])',  # region_pick:79
    'comprehension.iter>Call(func=Attribute,args=[],keywords=[])',  # region_pick:79
    'comprehension.target>Tuple(elts=[Name],ctx=Store)',  # region_pick:79
    'Call.args>Name(id=str,ctx=Load)#tied',  # region_pick:80
    'Call.func>Name(id=str,ctx=Load)#len',  # region_pick:80
    'Compare.comparators>Constant(value=int)',  # region_pick:80
    'Compare.left>Call(func=Name,args=[Name],keywords=[])',  # region_pick:80
    'FunctionDef.body>If(test=Compare,body=[Return],orelse=[])',  # region_pick:80
    'If.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # region_pick:80
    'Return.value>Tuple(elts=[Constant|Subscript],ctx=Load)',  # region_pick:81
    'Subscript.ctx>Load()',  # region_pick:81
    'Subscript.slice>Constant(value=int)',  # region_pick:81
    'Subscript.value>Name(id=str,ctx=Load)#tied',  # region_pick:81
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # region_pick:81
    'Assign.targets>Name(id=str,ctx=Store)#measured',  # region_pick:82
    'Assign.value>ListComp(elt=Name,generators=[comprehension])',  # region_pick:82
    'ListComp.elt>Name(id=str,ctx=Load)#code',  # region_pick:82
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Call],is_async=0)',  # region_pick:82
    'comprehension.iter>Name(id=str,ctx=Load)#tied',  # region_pick:82
    'comprehension.target>Name(id=str,ctx=Store)#code',  # region_pick:82
    "BoolOp.values>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:83
    'BoolOp.values>Compare(left=Attribute,ops=[NotEq],comparators=[Name])',  # region_pick:83
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Attribute])',  # region_pick:83
    'Call.args>GeneratorExp(elt=BoolOp,generators=[comprehension])',  # region_pick:83
    'Call.func>Name(id=str,ctx=Load)#any',  # region_pick:83
    "Compare.comparators>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:83
    'Compare.comparators>Name(id=str,ctx=Load)#code',  # region_pick:83
    "Compare.left>Attribute(value=Name,attr='home',ctx=Load)",  # region_pick:83
    'Compare.left>Name(id=str,ctx=Load)#code',  # region_pick:83
    'Compare.ops>In()',  # region_pick:83
    'Compare.ops>NotEq()',  # region_pick:83
    'GeneratorExp.elt>BoolOp(op=And,values=[Attribute|Compare])',  # region_pick:83
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # region_pick:83
    'comprehension.ifs>Call(func=Name,args=[GeneratorExp],keywords=[])',  # region_pick:83
    'Call.args>Name(id=str,ctx=Load)#measured',  # region_pick:84
    'Subscript.value>Name(id=str,ctx=Load)#measured',  # region_pick:85
    'Tuple.elts>Constant(value=str)',  # region_pick:85
    'BoolOp.values>Name(id=str,ctx=Load)#measured',  # region_pick:86
    'BoolOp.values>Name(id=str,ctx=Load)#tied',  # region_pick:86
    'FunctionDef.body>Return(value=Tuple)',  # region_pick:86
    'Subscript.value>BoolOp(op=Or,values=[Name])',  # region_pick:86
    'Tuple.elts>Subscript(value=BoolOp,slice=Constant,ctx=Load)',  # region_pick:86
    'Call.args>Name(id=str,ctx=Load)#raw_map',  # region_pick:95
    'Call.func>Name(id=str,ctx=Load)#_clean_map',  # region_pick:95
    'UnaryOp.operand>Name(id=str,ctx=Load)#clean',  # region_pick:96
    'Call.args>Name(id=str,ctx=Load)#clean',  # region_pick:98
    'Call.func>Name(id=str,ctx=Load)#min',  # region_pick:98
    "Call.keywords>keyword(arg='key',value=Lambda)",  # region_pick:98
    'FunctionDef.body>Return(value=Call)',  # region_pick:98
    'Lambda.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # region_pick:98
    'Lambda.body>Tuple(elts=[Name|Subscript],ctx=Load)',  # region_pick:98
    'Return.value>Call(func=Name,args=[Name],keywords=[keyword])',  # region_pick:98
    'Subscript.slice>Name(id=str,ctx=Load)#code',  # region_pick:98
    'Tuple.elts>Name(id=str,ctx=Load)#code',  # region_pick:98
    'Tuple.elts>Subscript(value=Name,slice=Name,ctx=Load)',  # region_pick:98
    'keyword.value>Lambda(args=arguments,body=Tuple)',  # region_pick:98
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[Constant],kwarg=-,defaults=[])',  # region_pick:101
    'Module.body>FunctionDef(name=str,args=arguments,body=[Expr|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:101
    'arguments.kw_defaults>Constant(value=NoneType)',  # region_pick:102
    'arguments.kw_defaults>Constant(value=int)',  # region_pick:102
    'arguments.kwonlyargs>arg(arg=str,annotation=-,type_comment=-)',  # region_pick:102
    'FunctionDef.body>Try(body=[Return],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # region_pick:179
    'Call.args>Name(id=str,ctx=Load)#legacy_pick',  # region_pick:180
    'Call.args>Name(id=str,ctx=Load)#live_regions',  # region_pick:180
    'Call.args>Name(id=str,ctx=Load)#members',  # region_pick:180
    'Call.args>Name(id=str,ctx=Load)#volumes',  # region_pick:180
    'Call.func>Name(id=str,ctx=Load)#_pick',  # region_pick:180
    'Return.value>Call(func=Name,args=[Name],keywords=[])',  # region_pick:180
    'Try.body>Return(value=Call)',  # region_pick:180
    'Call.args>Name(id=str,ctx=Load)#margin_ms',  # region_pick:181
    'Call.args>Name(id=str,ctx=Load)#max_age_s',  # region_pick:181
    'Call.args>Name(id=str,ctx=Load)#now',  # region_pick:181
    'Call.args>Name(id=str,ctx=Load)#regret_ms',  # region_pick:181
    'ExceptHandler.type>Name(id=str,ctx=Load)#Exception',  # region_pick:182
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Return])',  # region_pick:182
    'Call.args>Name(id=str,ctx=Load)#exc',  # region_pick:183
    'Call.func>Name(id=str,ctx=Load)#repr',  # region_pick:183
    'Dict.keys>Constant(value=str)',  # region_pick:183
    'Dict.values>Call(func=Name,args=[Name],keywords=[])',  # region_pick:183
    'ExceptHandler.body>Return(value=Tuple)',  # region_pick:183
    'Return.value>Tuple(elts=[Dict|Name],ctx=Load)',  # region_pick:183
    'Tuple.elts>Dict(keys=[Constant],values=[Call])',  # region_pick:183
    'Tuple.elts>Name(id=str,ctx=Load)#WHY_ERROR',  # region_pick:183
    'Module.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|FunctionDef|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:186
    'Compare.comparators>Constant(value=NoneType)',  # region_pick:187
    'Compare.left>Name(id=str,ctx=Load)#now',  # region_pick:187
    'Compare.ops>Is()',  # region_pick:187
    'FunctionDef.body>If(test=Compare,body=[Assign],orelse=[])',  # region_pick:187
    'If.test>Compare(left=Name,ops=[Is],comparators=[Constant])',  # region_pick:187
    'Assign.targets>Name(id=str,ctx=Store)#now',  # region_pick:188
    'Assign.value>Call(func=Attribute,args=[],keywords=[])',  # region_pick:188
    'Attribute.value>Name(id=str,ctx=Load)#time',  # region_pick:188
    "Call.func>Attribute(value=Name,attr='time',ctx=Load)",  # region_pick:188
    'If.body>Assign(targets=[Name],value=Call,type_comment=-)',  # region_pick:188
    'Assign.targets>Name(id=str,ctx=Store)#live',  # region_pick:189
    'Assign.value>SetComp(elt=Name,generators=[comprehension])',  # region_pick:189
    'BoolOp.values>Name(id=str,ctx=Load)#code',  # region_pick:189
    'BoolOp.values>Name(id=str,ctx=Load)#live_regions',  # region_pick:189
    'BoolOp.values>Tuple(elts=[],ctx=Load)',  # region_pick:189
    'Call.args>Name(id=str,ctx=Load)#code',  # region_pick:189
    'FunctionDef.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # region_pick:189
    'SetComp.elt>Name(id=str,ctx=Load)#code',  # region_pick:189
    'SetComp.generators>comprehension(target=Name,iter=BoolOp,ifs=[BoolOp],is_async=0)',  # region_pick:189
    'comprehension.ifs>BoolOp(op=And,values=[Call|Name])',  # region_pick:189
    'comprehension.iter>BoolOp(op=Or,values=[Name|Tuple])',  # region_pick:189
    'Assign.targets>Name(id=str,ctx=Store)#vols',  # region_pick:190
    'Assign.value>IfExp(test=Call,body=Name,orelse=Dict)',  # region_pick:190
    'FunctionDef.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # region_pick:190
    'IfExp.body>Name(id=str,ctx=Load)#volumes',  # region_pick:190
    'IfExp.orelse>Dict(keys=[],values=[])',  # region_pick:190
    'IfExp.test>Call(func=Name,args=[Name],keywords=[])',  # region_pick:190
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:192
    'Assign.targets>Name(id=str,ctx=Store)#v',  # region_pick:193
    'Assign.value>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # region_pick:193
    'Attribute.value>Name(id=str,ctx=Load)#vols',  # region_pick:193
    'Call.args>Constant(value=int)',  # region_pick:193
    "Call.func>Attribute(value=Name,attr='get',ctx=Load)",  # region_pick:193
    'Call.args>Name(id=str,ctx=Load)#v',  # region_pick:194
    'Call.func>Name(id=str,ctx=Load)#_is_number',  # region_pick:194
    'FunctionDef.body>Return(value=IfExp)',  # region_pick:194
    'IfExp.body>Name(id=str,ctx=Load)#v',  # region_pick:194
    'IfExp.orelse>Constant(value=int)',  # region_pick:194
    'Return.value>IfExp(test=Call,body=Name,orelse=Constant)',  # region_pick:194
    'Assign.targets>Name(id=str,ctx=Store)#seats',  # region_pick:196
    'Assign.value>List(elts=[],ctx=Load)',  # region_pick:196
    'FunctionDef.body>Assign(targets=[Name],value=List,type_comment=-)',  # region_pick:196
    'List.ctx>Load()',  # region_pick:196
    'BoolOp.values>Name(id=str,ctx=Load)#members',  # region_pick:197
    'For.iter>BoolOp(op=Or,values=[Name|Tuple])',  # region_pick:197
    'For.target>Name(id=str,ctx=Store)#member',  # region_pick:197
    'FunctionDef.body>For(target=Name,iter=BoolOp,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # region_pick:197
    'Call.args>Name(id=str,ctx=Load)#member',  # region_pick:198
    'For.body>If(test=UnaryOp,body=[Assign],orelse=[])',  # region_pick:198
    'Assign.targets>Name(id=str,ctx=Store)#member',  # region_pick:199
    'If.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # region_pick:199
    'Attribute.value>Name(id=str,ctx=Load)#member',  # region_pick:200
    'Call.args>Call(func=Attribute,args=[Constant],keywords=[])',  # region_pick:200
    'For.body>Assign(targets=[Name],value=Call,type_comment=-)',  # region_pick:200
    'Assign.targets>Name(id=str,ctx=Store)#at',  # region_pick:201
    'Assign.value>Call(func=Attribute,args=[Constant],keywords=[])',  # region_pick:201
    'Assign.targets>Name(id=str,ctx=Store)#fresh',  # region_pick:202
    'Assign.value>BoolOp(op=And,values=[Call|Compare])',  # region_pick:202
    'BinOp.left>Name(id=str,ctx=Load)#now',  # region_pick:202
    'BinOp.op>Sub()',  # region_pick:202
    'BinOp.right>Name(id=str,ctx=Load)#at',  # region_pick:202
    'BoolOp.values>Compare(left=BinOp,ops=[LtE],comparators=[Name])',  # region_pick:202
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # region_pick:202
    'Call.args>Name(id=str,ctx=Load)#at',  # region_pick:202
    'Compare.comparators>Name(id=str,ctx=Load)#max_age_s',  # region_pick:202
    'Compare.left>BinOp(left=Name,op=Sub,right=Name)',  # region_pick:202
    'Compare.left>Name(id=str,ctx=Load)#clean',  # region_pick:202
    'Compare.ops>IsNot()',  # region_pick:202
    'For.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # region_pick:202
    'Assign.targets>Name(id=str,ctx=Store)#home',  # region_pick:203
    'Assign.value>IfExp(test=BoolOp,body=Name,orelse=Constant)',  # region_pick:204
    'BoolOp.values>Name(id=str,ctx=Load)#home',  # region_pick:204
    'Call.args>Name(id=str,ctx=Load)#home',  # region_pick:204
    'For.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # region_pick:204
    'IfExp.body>Name(id=str,ctx=Load)#home',  # region_pick:204
    'IfExp.orelse>Constant(value=NoneType)',  # region_pick:204
    'IfExp.test>BoolOp(op=And,values=[Call|Name])',  # region_pick:204
    'Attribute.value>Name(id=str,ctx=Load)#seats',  # region_pick:205
    'Call.args>Call(func=Name,args=[Call|Name],keywords=[])',  # region_pick:205
    'Call.args>Name(id=str,ctx=Load)#fresh',  # region_pick:205
    "Call.func>Attribute(value=Name,attr='append',ctx=Load)",  # region_pick:205
    'Call.func>Name(id=str,ctx=Load)#_Seat',  # region_pick:205
    'Expr.value>Call(func=Attribute,args=[Call],keywords=[])',  # region_pick:205
    'For.body>Expr(value=Call)',  # region_pick:205
    'Assign.targets>Name(id=str,ctx=Store)#n',  # region_pick:206
    'Call.args>Name(id=str,ctx=Load)#seats',  # region_pick:206
    'Assign.targets>Tuple(elts=[Name],ctx=Store)',  # region_pick:208
    'Call.func>Name(id=str,ctx=Load)#_baseline',  # region_pick:208
    'FunctionDef.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # region_pick:208
    'Tuple.elts>Name(id=str,ctx=Store)#baseline',  # region_pick:208
    'Tuple.elts>Name(id=str,ctx=Store)#tie',  # region_pick:208
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:210
    'Attribute.value>Name(id=str,ctx=Load)#seat',  # region_pick:211
    "Compare.left>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:211
    'If.test>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # region_pick:211
    'Return.value>Constant(value=str)',  # region_pick:212
    'If.test>UnaryOp(op=Not,operand=Attribute)',  # region_pick:213
    "UnaryOp.operand>Attribute(value=Name,attr='fresh',ctx=Load)",  # region_pick:213
    'Compare.left>Name(id=str,ctx=Load)#baseline',  # region_pick:215
    'Compare.ops>NotIn()',  # region_pick:215
    'If.test>Compare(left=Name,ops=[NotIn],comparators=[Attribute])',  # region_pick:215
    'FunctionDef.body>Return(value=Constant)',  # region_pick:217
    'Assign.targets>Name(id=str,ctx=Store)#states',  # region_pick:219
    'Assign.value>ListComp(elt=Call,generators=[comprehension])',  # region_pick:219
    'Call.args>Name(id=str,ctx=Load)#s',  # region_pick:219
    'Call.func>Name(id=str,ctx=Load)#state',  # region_pick:219
    'ListComp.elt>Call(func=Name,args=[Name],keywords=[])',  # region_pick:219
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # region_pick:219
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # region_pick:221
    "Dict.values>Attribute(value=Name,attr='id',ctx=Load)",  # region_pick:222
    'Dict.values>Name(id=str,ctx=Load)#st',  # region_pick:222
    'FunctionDef.body>Return(value=ListComp)',  # region_pick:222
    'ListComp.elt>Dict(keys=[Constant],values=[Attribute|IfExp|Name])',  # region_pick:222
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # region_pick:222
    'Return.value>ListComp(elt=Dict,generators=[comprehension])',  # region_pick:222
    "Attribute.value>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:223
    'Call.args>Name(id=str,ctx=Load)#baseline',  # region_pick:223
    "Call.func>Attribute(value=Attribute,attr='get',ctx=Load)",  # region_pick:223
    'Dict.values>IfExp(test=Attribute,body=Call,orelse=Constant)',  # region_pick:223
    'IfExp.body>Call(func=Attribute,args=[Name],keywords=[])',  # region_pick:223
    "IfExp.test>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:223
    'Call.args>Name(id=str,ctx=Load)#pick',  # region_pick:224
    'Call.args>Name(id=str,ctx=Load)#states',  # region_pick:225
    'Call.func>Name(id=str,ctx=Load)#zip',  # region_pick:225
    'Tuple.elts>Name(id=str,ctx=Store)#s',  # region_pick:225
    'Tuple.elts>Name(id=str,ctx=Store)#st',  # region_pick:225
    'comprehension.iter>Call(func=Name,args=[Name],keywords=[])',  # region_pick:225
    'Assign.targets>Name(id=str,ctx=Store)#detail',  # region_pick:227
    'Assign.value>Dict(keys=[Constant],values=[Call|Constant|List|Name])',  # region_pick:227
    'Dict.values>Constant(value=NoneType)',  # region_pick:227
    'Dict.values>Name(id=str,ctx=Load)#baseline',  # region_pick:227
    'Dict.values>Name(id=str,ctx=Load)#n',  # region_pick:227
    'Call.func>Name(id=str,ctx=Load)#seat_rows',  # region_pick:229
    'Dict.values>List(elts=[],ctx=Load)',  # region_pick:229
    'Dict.values>Name(id=str,ctx=Load)#tie',  # region_pick:229
    'BoolOp.values>BoolOp(op=And,values=[Call|UnaryOp])',  # region_pick:232
    'BoolOp.values>Call(func=Name,args=[GeneratorExp],keywords=[])',  # region_pick:232
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # region_pick:232
    'Call.args>GeneratorExp(elt=Compare,generators=[comprehension])',  # region_pick:232
    'Compare.comparators>Constant(value=str)',  # region_pick:232
    'Compare.left>Name(id=str,ctx=Load)#st',  # region_pick:232
    'FunctionDef.body>If(test=BoolOp,body=[Return],orelse=[])',  # region_pick:232
    'GeneratorExp.elt>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # region_pick:232
    'If.test>BoolOp(op=Or,values=[BoolOp|Compare])',  # region_pick:232
    'UnaryOp.operand>Name(id=str,ctx=Load)#_SKIP_QUORUM',  # region_pick:232
    'comprehension.iter>Name(id=str,ctx=Load)#states',  # region_pick:232
    'comprehension.target>Name(id=str,ctx=Store)#st',  # region_pick:232
    'Return.value>Tuple(elts=[Name],ctx=Load)',  # region_pick:233
    'Tuple.elts>Name(id=str,ctx=Load)#WHY_QUORUM',  # region_pick:233
    'Tuple.elts>Name(id=str,ctx=Load)#baseline',  # region_pick:233
    'Tuple.elts>Name(id=str,ctx=Load)#detail',  # region_pick:233
    'Assign.targets>Name(id=str,ctx=Store)#common',  # region_pick:237
    'Assign.value>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick:237
    'Attribute.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # region_pick:237
    "Call.args>Attribute(value=Subscript,attr='map',ctx=Load)",  # region_pick:237
    'Call.func>Name(id=str,ctx=Load)#set',  # region_pick:237
    'Subscript.value>Name(id=str,ctx=Load)#seats',  # region_pick:237
    'For.iter>Subscript(value=Name,slice=Slice,ctx=Load)',  # region_pick:238
    'For.target>Name(id=str,ctx=Store)#seat',  # region_pick:238
    'FunctionDef.body>For(target=Name,iter=Subscript,body=[AugAssign],orelse=[],type_comment=-)',  # region_pick:238
    'Slice.lower>Constant(value=int)',  # region_pick:238
    'Subscript.slice>Slice(lower=Constant,upper=-,step=-)',  # region_pick:238
    'AugAssign.op>BitAnd()',  # region_pick:239
    'AugAssign.target>Name(id=str,ctx=Store)#common',  # region_pick:239
    'AugAssign.value>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick:239
    "Call.args>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:239
    'For.body>AugAssign(target=Name,op=BitAnd,value=Call)',  # region_pick:239
    'Assign.targets>Name(id=str,ctx=Store)#costs_b',  # region_pick:240
    'Assign.value>ListComp(elt=Subscript,generators=[comprehension])',  # region_pick:240
    'ListComp.elt>Subscript(value=Attribute,slice=Name,ctx=Load)',  # region_pick:240
    'Subscript.slice>Name(id=str,ctx=Load)#baseline',  # region_pick:240
    "Subscript.value>Attribute(value=Name,attr='map',ctx=Load)",  # region_pick:240
    'Assign.value>Tuple(elts=[Call],ctx=Load)',  # region_pick:241
    'Call.args>Name(id=str,ctx=Load)#costs_b',  # region_pick:241
    'Call.func>Name(id=str,ctx=Load)#sum',  # region_pick:241
    'FunctionDef.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # region_pick:241
    'Tuple.elts>Call(func=Name,args=[Name],keywords=[])',  # region_pick:241
    'Tuple.elts>Name(id=str,ctx=Store)#sum_b',  # region_pick:241
    'Tuple.elts>Name(id=str,ctx=Store)#worst_b',  # region_pick:241
    'Assign.targets>Name(id=str,ctx=Store)#cands',  # region_pick:243
    'BinOp.left>BinOp(left=Name,op=BitAnd,right=Name)',  # region_pick:244
    'BinOp.left>Name(id=str,ctx=Load)#live',  # region_pick:244
    'BinOp.op>BitAnd()',  # region_pick:244
    'BinOp.right>Name(id=str,ctx=Load)#common',  # region_pick:244
    'BinOp.right>Set(elts=[Name])',  # region_pick:244
    'Call.args>BinOp(left=BinOp,op=Sub,right=Set)',  # region_pick:244
    'For.iter>Call(func=Name,args=[BinOp],keywords=[])',  # region_pick:244
    'For.target>Name(id=str,ctx=Store)#code',  # region_pick:244
    'FunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr],orelse=[],type_comment=-)',  # region_pick:244
    'Set.elts>Name(id=str,ctx=Load)#baseline',  # region_pick:244
    'Assign.targets>Name(id=str,ctx=Store)#costs',  # region_pick:245
    'For.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # region_pick:245
    'Assign.targets>Name(id=str,ctx=Store)#gain',  # region_pick:246
    'BinOp.left>Name(id=str,ctx=Load)#cb',  # region_pick:246
    'BinOp.right>Name(id=str,ctx=Load)#c',  # region_pick:246
    'Call.args>GeneratorExp(elt=Constant,generators=[comprehension])',  # region_pick:246
    'Call.args>Name(id=str,ctx=Load)#costs',  # region_pick:246
    'Compare.comparators>Name(id=str,ctx=Load)#margin_ms',  # region_pick:246
    'Compare.ops>GtE()',  # region_pick:246
    'GeneratorExp.elt>Constant(value=int)',  # region_pick:246
    'Tuple.elts>Name(id=str,ctx=Store)#c',  # region_pick:246
    'Tuple.elts>Name(id=str,ctx=Store)#cb',  # region_pick:246
    'comprehension.ifs>Compare(left=BinOp,ops=[GtE],comparators=[Name])',  # region_pick:246
    'Assign.targets>Name(id=str,ctx=Store)#max_regret',  # region_pick:247
    'BinOp.left>Name(id=str,ctx=Load)#c',  # region_pick:247
    'BinOp.right>Name(id=str,ctx=Load)#cb',  # region_pick:247
    'Call.args>GeneratorExp(elt=BinOp,generators=[comprehension])',  # region_pick:247
    'GeneratorExp.elt>BinOp(left=Name,op=Sub,right=Name)',  # region_pick:247
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # region_pick:247
    'Assign.targets>Name(id=str,ctx=Store)#majority',  # region_pick:248
    'Assign.value>IfExp(test=Name,body=Compare,orelse=Compare)',  # region_pick:248
    'BinOp.left>Constant(value=int)',  # region_pick:248
    'BinOp.op>Mult()',  # region_pick:248
    'BinOp.right>Name(id=str,ctx=Load)#gain',  # region_pick:248
    'Compare.comparators>Name(id=str,ctx=Load)#n',  # region_pick:248
    'Compare.left>BinOp(left=Constant,op=Mult,right=Name)',  # region_pick:248
    'Compare.ops>Gt()',  # region_pick:248
    'IfExp.body>Compare(left=BinOp,ops=[Gt],comparators=[Name])',  # region_pick:248
    'IfExp.orelse>Compare(left=BinOp,ops=[GtE],comparators=[Name])',  # region_pick:248
    'IfExp.test>Name(id=str,ctx=Load)#_MAJORITY_STRICT',  # region_pick:248
    'Assign.targets>Name(id=str,ctx=Store)#bounded',  # region_pick:249
    'Assign.value>Compare(left=Name,ops=[LtE],comparators=[Name])',  # region_pick:249
    'Compare.comparators>Name(id=str,ctx=Load)#regret_ms',  # region_pick:249
    'Compare.left>Name(id=str,ctx=Load)#max_regret',  # region_pick:249
    'For.body>Assign(targets=[Name],value=Compare,type_comment=-)',  # region_pick:249
    'Assign.targets>Name(id=str,ctx=Store)#admitted_by',  # region_pick:250
    'Assign.value>IfExp(test=Name,body=Name,orelse=IfExp)',  # region_pick:250
    'IfExp.body>Name(id=str,ctx=Load)#WHY_BOUNDED',  # region_pick:250
    'IfExp.body>Name(id=str,ctx=Load)#WHY_MAJORITY',  # region_pick:250
    'IfExp.orelse>IfExp(test=Name,body=Name,orelse=Constant)',  # region_pick:250
    'IfExp.test>Name(id=str,ctx=Load)#bounded',  # region_pick:250
    'IfExp.test>Name(id=str,ctx=Load)#majority',  # region_pick:250
    'Attribute.value>Name(id=str,ctx=Load)#cands',  # region_pick:251
    'Call.args>Call(func=Name,args=[Name],keywords=[])',  # region_pick:251
    'Call.args>Name(id=str,ctx=Load)#admitted_by',  # region_pick:251
    'Call.args>Name(id=str,ctx=Load)#gain',  # region_pick:251
    'Call.args>Name(id=str,ctx=Load)#max_regret',  # region_pick:251
    'Call.func>Name(id=str,ctx=Load)#_Cand',  # region_pick:251
    'IfExp.body>Tuple(elts=[Name],ctx=Load)',  # region_pick:254
    'IfExp.orelse>Tuple(elts=[Name],ctx=Load)',  # region_pick:254
    'IfExp.test>Name(id=str,ctx=Load)#_SELECT_BY_WORST',  # region_pick:254
    'Return.value>IfExp(test=Name,body=Tuple,orelse=Tuple)',  # region_pick:254
    'Tuple.elts>Name(id=str,ctx=Load)#total',  # region_pick:254
    'Tuple.elts>Name(id=str,ctx=Load)#worst',  # region_pick:254
    'Attribute.value>Name(id=str,ctx=Load)#cand',  # region_pick:257
    'BinOp.left>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick:257
    'BinOp.op>Add()',  # region_pick:257
    'BinOp.right>Tuple(elts=[Attribute|UnaryOp],ctx=Load)',  # region_pick:257
    "Call.args>Attribute(value=Name,attr='region',ctx=Load)",  # region_pick:257
    "Call.args>Attribute(value=Name,attr='sum',ctx=Load)",  # region_pick:257
    "Call.args>Attribute(value=Name,attr='worst',ctx=Load)",  # region_pick:257
    'Call.func>Name(id=str,ctx=Load)#primary',  # region_pick:257
    'Call.func>Name(id=str,ctx=Load)#volume',  # region_pick:257
    'FunctionDef.body>Return(value=BinOp)',  # region_pick:257
    'Return.value>BinOp(left=Call,op=Add,right=Tuple)',  # region_pick:257
    "Tuple.elts>Attribute(value=Name,attr='region',ctx=Load)",  # region_pick:257
    'Tuple.elts>UnaryOp(op=USub,operand=Call)',  # region_pick:257
    'UnaryOp.op>USub()',  # region_pick:257
    'UnaryOp.operand>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick:257
    "Call.func>Attribute(value=Name,attr='sort',ctx=Load)",  # region_pick:259
    "Call.keywords>keyword(arg='key',value=Name)",  # region_pick:259
    'Expr.value>Call(func=Attribute,args=[],keywords=[keyword])',  # region_pick:259
    'FunctionDef.body>Expr(value=Call)',  # region_pick:259
    'keyword.value>Name(id=str,ctx=Load)#order',  # region_pick:259
    'Assign.targets>Name(id=str,ctx=Store)#better',  # region_pick:260
    'ListComp.elt>Name(id=str,ctx=Load)#c',  # region_pick:260
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[BoolOp],is_async=0)',  # region_pick:260
    'comprehension.iter>Name(id=str,ctx=Load)#cands',  # region_pick:260
    'comprehension.target>Name(id=str,ctx=Store)#c',  # region_pick:260
    'Attribute.value>Name(id=str,ctx=Load)#c',  # region_pick:261
    "BoolOp.values>Attribute(value=Name,attr='admitted_by',ctx=Load)",  # region_pick:261
    'BoolOp.values>Compare(left=Call,ops=[Lt],comparators=[Call])',  # region_pick:261
    'Call.args>Name(id=str,ctx=Load)#sum_b',  # region_pick:261
    'Call.args>Name(id=str,ctx=Load)#worst_b',  # region_pick:261
    'Compare.comparators>Call(func=Name,args=[Name],keywords=[])',  # region_pick:261
    'Compare.left>Call(func=Name,args=[Attribute],keywords=[])',  # region_pick:261
    'Compare.ops>Lt()',  # region_pick:261
    'comprehension.ifs>BoolOp(op=And,values=[Attribute|Compare])',  # region_pick:261
    'FunctionDef.body>If(test=Name,body=[Assign],orelse=[Assign])',  # region_pick:263
    'If.test>Name(id=str,ctx=Load)#better',  # region_pick:263
    'Assign.targets>Name(id=str,ctx=Store)#winner',  # region_pick:264
    'Assign.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # region_pick:264
    'If.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # region_pick:264
    'Subscript.value>Name(id=str,ctx=Load)#better',  # region_pick:264
    'Assign.value>Tuple(elts=[Attribute],ctx=Load)',  # region_pick:265
    'Attribute.value>Name(id=str,ctx=Load)#winner',  # region_pick:265
    'If.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # region_pick:265
    "Tuple.elts>Attribute(value=Name,attr='admitted_by',ctx=Load)",  # region_pick:265
    'Tuple.elts>Name(id=str,ctx=Store)#pick',  # region_pick:265
    'Tuple.elts>Name(id=str,ctx=Store)#why',  # region_pick:265
    "Tuple.elts>Attribute(value=Name,attr='gain',ctx=Load)",  # region_pick:266
    "Tuple.elts>Attribute(value=Name,attr='max_regret',ctx=Load)",  # region_pick:266
    "Tuple.elts>Attribute(value=Name,attr='sum',ctx=Load)",  # region_pick:266
    "Tuple.elts>Attribute(value=Name,attr='worst',ctx=Load)",  # region_pick:266
    'Tuple.elts>Name(id=str,ctx=Store)#gain',  # region_pick:266
    'Tuple.elts>Name(id=str,ctx=Store)#max_regret',  # region_pick:266
    'Tuple.elts>Name(id=str,ctx=Store)#sum_pick',  # region_pick:266
    'Tuple.elts>Name(id=str,ctx=Store)#worst_pick',  # region_pick:266
    'Assign.value>Tuple(elts=[Name],ctx=Load)',  # region_pick:268
    'If.orelse>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # region_pick:268
    'Tuple.elts>Name(id=str,ctx=Load)#WHY_BASELINE',  # region_pick:268
    'Assign.value>Tuple(elts=[Constant|Name],ctx=Load)',  # region_pick:269
    'Tuple.elts>Constant(value=int)',  # region_pick:269
    'Tuple.elts>Name(id=str,ctx=Load)#sum_b',  # region_pick:269
    'Tuple.elts>Name(id=str,ctx=Load)#worst_b',  # region_pick:269
    'Attribute.value>Name(id=str,ctx=Load)#detail',  # region_pick:271
    'Call.args>Dict(keys=[Constant],values=[Call|ListComp|Name])',  # region_pick:271
    "Call.func>Attribute(value=Name,attr='update',ctx=Load)",  # region_pick:271
    'Expr.value>Call(func=Attribute,args=[Dict],keywords=[])',  # region_pick:271
    'Dict.values>Name(id=str,ctx=Load)#sum_b',  # region_pick:272
    'Dict.values>Name(id=str,ctx=Load)#sum_pick',  # region_pick:272
    'Dict.values>Name(id=str,ctx=Load)#worst_b',  # region_pick:272
    'Dict.values>Name(id=str,ctx=Load)#worst_pick',  # region_pick:272
    'Dict.values>Name(id=str,ctx=Load)#gain',  # region_pick:273
    'Dict.values>Name(id=str,ctx=Load)#max_regret',  # region_pick:273
    "Call.func>Attribute(value=Name,attr='_asdict',ctx=Load)",  # region_pick:274
    'Dict.values>ListComp(elt=Call,generators=[comprehension])',  # region_pick:274
    'ListComp.elt>Call(func=Attribute,args=[],keywords=[])',  # region_pick:274
    'Tuple.elts>Name(id=str,ctx=Load)#pick',  # region_pick:277
    'Tuple.elts>Name(id=str,ctx=Load)#why',  # region_pick:277
})

# --- the census grammar ------------------------------------------
# Every node shape of every walker span the census reads
# (resolution_sites.walker_spans): closed_walk and the a1 file at this
# child's commit, the gate file at a30d37f6 (child gg owns it and will
# change it; W30b re-checks at merge). No AnnAssign: the walker code
# holds none, so one refuses.
#
# Round 8 (ruling REHEARSAL-FOUR-R7-A1, M8): this block is ga1's round-7
# freeze restored exactly (51d4faf2); the re-freeze at the merge
# (3130bb9d: 75 shapes added, 20 removed, regenerated from the merged
# code) is undone. Shapes are never added back: code outside this set is
# conformed to it. Three shapes are REMOVED, never replaced: the
# importlib route (M4, closed_walk:755), the module-accessor route of
# Bindings.callee (M4, closed_walk:765) and the generic resolver form on
# a plain name (M7, `<name>.named(...)`; the census's one resolver form is
# `<name>.b.<method>(...)`, resolution_sites._resolver_call). WALKER_NODES
# is the round-7 total, kept as the freeze's record; the census test
# compares, per file, the nodes the grammar checked with an independent
# count of the same spans.
WALKER_NODES = 37286

WALKER_SHAPES = frozenset({
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:87
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3448
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[AugAssign],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:81
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[AugAssign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:59
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1565
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1559
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:63
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Assign|Expr|For|FunctionDef|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3681
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Assign|Expr|If|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:4409
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:133
    '<root>>FunctionDef(name=str,args=arguments,body=[Assert|Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:4482
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:106
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|AugAssign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1484
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|AugAssign|Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1542
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|AugAssign|Expr|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1037
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|ClassDef|Expr|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3661
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|ClassDef|Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2793
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3442
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|FunctionDef|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1896
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|FunctionDef|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:922
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:714
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:4713
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Raise|While],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1195
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:990
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):280
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3858
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return],decorator_list=[Call],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2929
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:66
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:4377
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|Return|While],decorator_list=[Call],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2945
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|FunctionDef|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:814
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|FunctionDef|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:938
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|FunctionDef|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1136
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:129
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Raise],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:532
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:120
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return|Try],decorator_list=[Name],returns=-,type_comment=-,type_params=[])',  # closed_walk:772
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:185
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Import],decorator_list=[Attribute],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:711
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Import|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3982
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:513
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):544
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return|While],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:265
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|For|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:421
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1027
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|FunctionDef|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1905
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:284
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1451
    '<root>>FunctionDef(name=str,args=arguments,body=[AugAssign],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):238
    '<root>>FunctionDef(name=str,args=arguments,body=[AugAssign|Expr|For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1602
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:444
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1526
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|For|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1174
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:557
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1362
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:615
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|If|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:759
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:279
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:161
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Return|While],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:363
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1512
    '<root>>FunctionDef(name=str,args=arguments,body=[For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1609
    '<root>>FunctionDef(name=str,args=arguments,body=[For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg (a30d37f6):374
    '<root>>FunctionDef(name=str,args=arguments,body=[If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:447
    '<root>>FunctionDef(name=str,args=arguments,body=[If|Raise],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1506
    '<root>>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:863
    '<root>>FunctionDef(name=str,args=arguments,body=[Raise],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1368
    '<root>>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[Call],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2923
    '<root>>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:377
    'Assert.msg>Constant(value=str)',  # test_a1_identity_formation:95
    'Assert.msg>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:136
    'Assert.msg>Tuple(elts=[Call|Name],ctx=Load)',  # test_a1_identity_formation:4420
    'Assert.test>BoolOp(op=And,values=[Compare])',  # test_a1_identity_formation:3690
    'Assert.test>Compare(left=Call,ops=[Eq],comparators=[Call])',  # test_a1_identity_formation:139
    'Assert.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:3696
    'Assert.test>Compare(left=Constant,ops=[In],comparators=[Name])',  # test_a1_identity_formation:94
    'Assert.test>Compare(left=Name,ops=[Eq],comparators=[Call])',  # test_a1_identity_formation:135
    "Assign.targets>Attribute(value=Name,attr='__file__',ctx=Store)",  # test_a1_identity_formation:3666
    "Assign.targets>Attribute(value=Name,attr='_done',ctx=Store)",  # closed_walk:118
    "Assign.targets>Attribute(value=Name,attr='_enumerated',ctx=Store)",  # closed_walk:431
    "Assign.targets>Attribute(value=Name,attr='_lock_calls',ctx=Store)",  # test_a1_identity_formation:3446
    "Assign.targets>Attribute(value=Name,attr='_plain_sub',ctx=Store)",  # closed_walk:1425
    "Assign.targets>Attribute(value=Name,attr='_refuse_attempt',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):1053
    "Assign.targets>Attribute(value=Name,attr='_refused',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):1052
    "Assign.targets>Attribute(value=Name,attr='_rows',ctx=Store)",  # test_a1_identity_formation:37
    "Assign.targets>Attribute(value=Name,attr='_walked_nodes',ctx=Store)",  # closed_walk:1476
    "Assign.targets>Attribute(value=Name,attr='admitted',ctx=Store)",  # closed_walk:114
    "Assign.targets>Attribute(value=Name,attr='allowed',ctx=Store)",  # closed_walk:110
    "Assign.targets>Attribute(value=Name,attr='b',ctx=Store)",  # closed_walk:1456
    "Assign.targets>Attribute(value=Name,attr='caught',ctx=Store)",  # closed_walk:1473
    "Assign.targets>Attribute(value=Name,attr='commits',ctx=Store)",  # test_a1_identity_formation:71
    "Assign.targets>Attribute(value=Name,attr='depth',ctx=Store)",  # test_a1_identity_formation:2806
    "Assign.targets>Attribute(value=Name,attr='effects',ctx=Store)",  # closed_walk:1469
    "Assign.targets>Attribute(value=Name,attr='fail_lease_read',ctx=Store)",  # test_a1_identity_formation:76
    "Assign.targets>Attribute(value=Name,attr='fail_on',ctx=Store)",  # test_a1_identity_formation:3444
    "Assign.targets>Attribute(value=Name,attr='gate_kinds',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):200
    "Assign.targets>Attribute(value=Name,attr='grammar',ctx=Store)",  # closed_walk:428
    "Assign.targets>Attribute(value=Name,attr='guarded',ctx=Store)",  # closed_walk:1460
    "Assign.targets>Attribute(value=Name,attr='has_fn',ctx=Store)",  # closed_walk:430
    "Assign.targets>Attribute(value=Name,attr='helper',ctx=Store)",  # closed_walk:1463
    "Assign.targets>Attribute(value=Name,attr='helper_hook',ctx=Store)",  # closed_walk:1390
    "Assign.targets>Attribute(value=Name,attr='helpers',ctx=Store)",  # closed_walk:1395
    "Assign.targets>Attribute(value=Name,attr='imports',ctx=Store)",  # closed_walk:111
    "Assign.targets>Attribute(value=Name,attr='leases',ctx=Store)",  # test_a1_identity_formation:75
    "Assign.targets>Attribute(value=Name,attr='local',ctx=Store)",  # closed_walk:1459
    "Assign.targets>Attribute(value=Name,attr='meaningful',ctx=Store)",  # closed_walk:109
    "Assign.targets>Attribute(value=Name,attr='met',ctx=Store)",  # closed_walk:1397
    "Assign.targets>Attribute(value=Name,attr='namedtuples',ctx=Store)",  # closed_walk:112
    "Assign.targets>Attribute(value=Name,attr='nt_seen',ctx=Store)",  # closed_walk:117
    "Assign.targets>Attribute(value=Name,attr='opaque',ctx=Store)",  # closed_walk:1466
    "Assign.targets>Attribute(value=Name,attr='p',ctx=Store)",  # closed_walk:1455
    "Assign.targets>Attribute(value=Name,attr='params',ctx=Store)",  # closed_walk:1461
    "Assign.targets>Attribute(value=Name,attr='permitted',ctx=Store)",  # closed_walk:1462
    "Assign.targets>Attribute(value=Name,attr='policy',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):227
    "Assign.targets>Attribute(value=Name,attr='pure_awaits',ctx=Store)",  # closed_walk:1383
    "Assign.targets>Attribute(value=Name,attr='pure_calls',ctx=Store)",  # closed_walk:1381
    "Assign.targets>Attribute(value=Name,attr='pure_methods',ctx=Store)",  # closed_walk:1382
    "Assign.targets>Attribute(value=Name,attr='record',ctx=Store)",  # closed_walk:113
    "Assign.targets>Attribute(value=Name,attr='rollbacks',ctx=Store)",  # test_a1_identity_formation:72
    "Assign.targets>Attribute(value=Name,attr='savepoints',ctx=Store)",  # test_a1_identity_formation:73
    "Assign.targets>Attribute(value=Name,attr='scope',ctx=Store)",  # closed_walk:423
    "Assign.targets>Attribute(value=Name,attr='seen',ctx=Store)",  # closed_walk:116
    "Assign.targets>Attribute(value=Name,attr='session',ctx=Store)",  # closed_walk:424
    "Assign.targets>Attribute(value=Name,attr='shapes',ctx=Store)",  # closed_walk:108
    "Assign.targets>Attribute(value=Name,attr='sites',ctx=Store)",  # closed_walk:429
    "Assign.targets>Attribute(value=Name,attr='sql',ctx=Store)",  # closed_walk:1384
    "Assign.targets>Attribute(value=Name,attr='sqlstate',ctx=Store)",  # test_a1_identity_formation:3445
    "Assign.targets>Attribute(value=Name,attr='statements',ctx=Store)",  # test_a1_identity_formation:69
    "Assign.targets>Attribute(value=Name,attr='sync_state',ctx=Store)",  # test_a1_identity_formation:3672
    "Assign.targets>Attribute(value=Name,attr='trees',ctx=Store)",  # closed_walk:115
    "Assign.targets>Attribute(value=Name,attr='walked_defs',ctx=Store)",  # closed_walk:1468
    "Assign.targets>Attribute(value=Name,attr='walking',ctx=Store)",  # closed_walk:1396
    "Assign.targets>Attribute(value=Name,attr='where',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):235
    "Assign.targets>Attribute(value=Subscript,attr='grammar',ctx=Store)",  # test_a1_identity_formation:703
    'Assign.targets>Name(id=str,ctx=Store)',  # closed_walk:70
    'Assign.targets>Subscript(value=Attribute,slice=Attribute,ctx=Store)',  # test_a1_identity_formation:3667
    'Assign.targets>Subscript(value=Attribute,slice=Call,ctx=Store)',  # closed_walk:156
    'Assign.targets>Subscript(value=Attribute,slice=Name,ctx=Store)',  # closed_walk:140
    'Assign.targets>Subscript(value=Name,slice=Attribute,ctx=Store)',  # closed_walk:1054
    'Assign.targets>Subscript(value=Name,slice=BoolOp,ctx=Store)',  # test_a1_identity_formation:3820
    'Assign.targets>Subscript(value=Name,slice=Call,ctx=Store)',  # closed_walk:1040
    'Assign.targets>Subscript(value=Name,slice=Constant,ctx=Store)',  # test_a1_identity_formation:1436
    'Assign.targets>Subscript(value=Name,slice=Name,ctx=Store)',  # closed_walk:194
    'Assign.targets>Tuple(elts=[Attribute],ctx=Store)',  # test_match_hold_admission_gate_pg (a30d37f6):236
    'Assign.targets>Tuple(elts=[Name],ctx=Store)',  # closed_walk:146
    'Assign.targets>Tuple(elts=[Name|Subscript],ctx=Store)',  # test_a1_identity_formation:1439
    'Assign.targets>Tuple(elts=[Name|Tuple],ctx=Store)',  # test_a1_identity_formation:1485
    'Assign.targets>Tuple(elts=[Subscript],ctx=Store)',  # test_match_hold_admission_gate_pg (a30d37f6):65
    "Assign.value>Attribute(value=Attribute,attr='id',ctx=Load)",  # closed_walk:905
    "Assign.value>Attribute(value=Attribute,attr='session',ctx=Load)",  # closed_walk:1739
    "Assign.value>Attribute(value=Attribute,attr='value',ctx=Load)",  # closed_walk:315
    "Assign.value>Attribute(value=Call,attr='__name__',ctx=Load)",  # closed_walk:2009
    "Assign.value>Attribute(value=Call,attr='grammar',ctx=Load)",  # test_a1_identity_formation:2175
    "Assign.value>Attribute(value=Call,attr='parameters',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):696
    "Assign.value>Attribute(value=Call,attr='parent',ctx=Load)",  # test_a1_identity_formation:3861
    "Assign.value>Attribute(value=Name,attr='_refuse_attempt',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1053
    "Assign.value>Attribute(value=Name,attr='_refused',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1052
    "Assign.value>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:731
    "Assign.value>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:1028
    "Assign.value>Attribute(value=Name,attr='attr',ctx=Load)",  # test_a1_identity_formation:3844
    "Assign.value>Attribute(value=Name,attr='body',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):781
    "Assign.value>Attribute(value=Name,attr='elts',ctx=Load)",  # test_a1_identity_formation:845
    "Assign.value>Attribute(value=Name,attr='exc',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):677
    "Assign.value>Attribute(value=Name,attr='grammar',ctx=Load)",  # closed_walk:811
    "Assign.value>Attribute(value=Name,attr='helpers',ctx=Load)",  # closed_walk:1919
    "Assign.value>Attribute(value=Name,attr='items',ctx=Load)",  # closed_walk:2059
    "Assign.value>Attribute(value=Name,attr='met',ctx=Load)",  # closed_walk:1423
    "Assign.value>Attribute(value=Name,attr='name',ctx=Load)",  # test_a1_identity_formation:3820
    "Assign.value>Attribute(value=Name,attr='session',ctx=Load)",  # closed_walk:1934
    "Assign.value>Attribute(value=Name,attr='target',ctx=Load)",  # closed_walk:321
    "Assign.value>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:317
    "Assign.value>Attribute(value=Name,attr='walking',ctx=Load)",  # closed_walk:1920
    'Assign.value>BinOp(left=Attribute,op=Add,right=Attribute)',  # closed_walk:1966
    'Assign.value>BinOp(left=BinOp,op=Add,right=BoolOp)',  # closed_walk:75
    'Assign.value>BinOp(left=BinOp,op=Add,right=Constant)',  # test_a1_identity_formation:3699
    'Assign.value>BinOp(left=BinOp,op=Add,right=ListComp)',  # closed_walk:436
    'Assign.value>BinOp(left=BinOp,op=Div,right=Name)',  # test_a1_identity_formation:4413
    'Assign.value>BinOp(left=BinOp,op=Sub,right=Attribute)',  # closed_walk:1247
    'Assign.value>BinOp(left=Call,op=Add,right=Call)',  # test_match_hold_admission_gate_pg (a30d37f6):1046
    'Assign.value>BinOp(left=Call,op=Add,right=Constant)',  # closed_walk:946
    'Assign.value>BinOp(left=Call,op=Add,right=ListComp)',  # closed_walk:1620
    'Assign.value>BinOp(left=Constant,op=Add,right=Subscript)',  # test_a1_identity_formation:2430
    'Assign.value>BinOp(left=List,op=Add,right=ListComp)',  # test_a1_identity_formation:2445
    'Assign.value>BinOp(left=List,op=Add,right=Name)',  # test_a1_identity_formation:2437
    'Assign.value>BinOp(left=ListComp,op=Add,right=ListComp)',  # test_a1_identity_formation:2180
    'Assign.value>BinOp(left=Name,op=Add,right=Call)',  # test_a1_identity_formation:1793
    'Assign.value>BinOp(left=Name,op=Add,right=Constant)',  # test_a1_identity_formation:3206
    'Assign.value>BinOp(left=Name,op=Add,right=ListComp)',  # closed_walk:985
    'Assign.value>BinOp(left=Name,op=Add,right=Name)',  # test_a1_identity_formation:1376
    'Assign.value>BinOp(left=Name,op=Add,right=Tuple)',  # test_a1_identity_formation:1283
    'Assign.value>BinOp(left=Name,op=BitAnd,right=Set)',  # closed_walk:1821
    'Assign.value>BinOp(left=Subscript,op=Add,right=Attribute)',  # test_a1_identity_formation:1368
    'Assign.value>BoolOp(op=And,values=[Call|Compare])',  # test_a1_identity_formation:2251
    'Assign.value>BoolOp(op=And,values=[Call|Compare|Subscript])',  # test_a1_identity_formation:1278
    'Assign.value>BoolOp(op=And,values=[Compare])',  # closed_walk:1773
    'Assign.value>BoolOp(op=Or,values=[Call])',  # test_a1_identity_formation:2823
    'Assign.value>BoolOp(op=Or,values=[Call|Constant])',  # closed_walk:164
    'Assign.value>BoolOp(op=Or,values=[Call|Name])',  # closed_walk:525
    'Assign.value>BoolOp(op=Or,values=[Dict|Name])',  # closed_walk:836
    'Assign.value>BoolOp(op=Or,values=[Name|Subscript])',  # test_match_hold_admission_gate_pg (a30d37f6):379
    'Assign.value>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:285
    'Assign.value>Call(func=Attribute,args=[Attribute],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):290
    'Assign.value>Call(func=Attribute,args=[Attribute|BoolOp],keywords=[])',  # closed_walk:810
    'Assign.value>Call(func=Attribute,args=[Attribute|Call],keywords=[])',  # closed_walk:765
    'Assign.value>Call(func=Attribute,args=[Attribute|Call],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):549
    'Assign.value>Call(func=Attribute,args=[Attribute|Call|IfExp|Name],keywords=[keyword])',  # test_a1_identity_formation:2194
    'Assign.value>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:144
    'Assign.value>Call(func=Attribute,args=[Attribute|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):232
    'Assign.value>Call(func=Attribute,args=[BinOp],keywords=[])',  # test_a1_identity_formation:3035
    'Assign.value>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:191
    'Assign.value>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:2959
    'Assign.value>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # test_a1_identity_formation:117
    'Assign.value>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # test_a1_identity_formation:2975
    'Assign.value>Call(func=Attribute,args=[IfExp|Name],keywords=[keyword])',  # test_a1_identity_formation:2176
    'Assign.value>Call(func=Attribute,args=[JoinedStr],keywords=[])',  # test_a1_identity_formation:4470
    'Assign.value>Call(func=Attribute,args=[List|Name],keywords=[])',  # closed_walk:980
    'Assign.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:123
    'Assign.value>Call(func=Attribute,args=[Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):198
    'Assign.value>Call(func=Attribute,args=[Name|Tuple],keywords=[])',  # closed_walk:506
    'Assign.value>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:98
    'Assign.value>Call(func=Attribute,args=[Tuple],keywords=[])',  # test_a1_identity_formation:4335
    'Assign.value>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:270
    'Assign.value>Call(func=Attribute,args=[],keywords=[keyword])',  # closed_walk:1909
    'Assign.value>Call(func=Call,args=[],keywords=[])',  # test_a1_identity_formation:3453
    'Assign.value>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:473
    'Assign.value>Call(func=Name,args=[Attribute|BinOp],keywords=[])',  # closed_walk:1420
    'Assign.value>Call(func=Name,args=[Attribute|BinOp|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):596
    'Assign.value>Call(func=Name,args=[Attribute|Call|Constant],keywords=[])',  # closed_walk:755
    'Assign.value>Call(func=Name,args=[Attribute|Call|Name],keywords=[])',  # closed_walk:1820
    'Assign.value>Call(func=Name,args=[Attribute|Call|Name],keywords=[keyword])',  # closed_walk:1888
    'Assign.value>Call(func=Name,args=[Attribute|Constant|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):360
    'Assign.value>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:815
    'Assign.value>Call(func=Name,args=[Attribute|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):358
    'Assign.value>Call(func=Name,args=[Attribute|Name|Tuple],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):539
    'Assign.value>Call(func=Name,args=[BinOp],keywords=[])',  # test_a1_identity_formation:2297
    'Assign.value>Call(func=Name,args=[BinOp|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1907
    'Assign.value>Call(func=Name,args=[BoolOp],keywords=[])',  # test_a1_identity_formation:75
    'Assign.value>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:141
    'Assign.value>Call(func=Name,args=[Call|Constant],keywords=[])',  # test_a1_identity_formation:838
    'Assign.value>Call(func=Name,args=[Call|Constant|Name],keywords=[])',  # test_a1_identity_formation:630
    'Assign.value>Call(func=Name,args=[Call|JoinedStr],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):591
    'Assign.value>Call(func=Name,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:4514
    'Assign.value>Call(func=Name,args=[Call|Name],keywords=[keyword])',  # closed_walk:1014
    'Assign.value>Call(func=Name,args=[Constant],keywords=[])',  # test_a1_identity_formation:2366
    'Assign.value>Call(func=Name,args=[Constant|GeneratorExp],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):449
    'Assign.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:187
    'Assign.value>Call(func=Name,args=[Dict|Name],keywords=[])',  # test_a1_identity_formation:1438
    'Assign.value>Call(func=Name,args=[Dict|Name|Tuple],keywords=[])',  # test_a1_identity_formation:1349
    'Assign.value>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:1935
    'Assign.value>Call(func=Name,args=[GeneratorExp],keywords=[keyword])',  # test_a1_identity_formation:896
    'Assign.value>Call(func=Name,args=[JoinedStr|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):764
    'Assign.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:108
    'Assign.value>Call(func=Name,args=[Name],keywords=[keyword])',  # closed_walk:1927
    'Assign.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # test_a1_identity_formation:2278
    'Assign.value>Call(func=Name,args=[SetComp],keywords=[])',  # test_a1_identity_formation:1108
    'Assign.value>Call(func=Name,args=[Starred],keywords=[])',  # closed_walk:1064
    'Assign.value>Call(func=Name,args=[Subscript],keywords=[])',  # test_a1_identity_formation:1352
    'Assign.value>Call(func=Name,args=[],keywords=[])',  # closed_walk:309
    'Assign.value>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1029
    'Assign.value>Compare(left=Name,ops=[In],comparators=[Tuple])',  # test_a1_identity_formation:998
    'Assign.value>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # closed_walk:430
    'Assign.value>Constant(value=NoneType)',  # closed_walk:193
    'Assign.value>Constant(value=bool)',  # closed_walk:1219
    'Assign.value>Constant(value=int)',  # test_a1_identity_formation:71
    'Assign.value>Constant(value=str)',  # closed_walk:166
    'Assign.value>Dict(keys=[Constant],values=[Constant])',  # test_a1_identity_formation:1035
    'Assign.value>Dict(keys=[],values=[])',  # closed_walk:114
    'Assign.value>DictComp(key=Name,value=Call,generators=[comprehension])',  # test_a1_identity_formation:4382
    'Assign.value>DictComp(key=Name,value=Constant,generators=[comprehension])',  # closed_walk:1035
    'Assign.value>DictComp(key=Name,value=Name,generators=[comprehension])',  # closed_walk:1086
    'Assign.value>GeneratorExp(elt=Subscript,generators=[comprehension])',  # test_a1_identity_formation:2165
    'Assign.value>IfExp(test=Attribute,body=Call,orelse=Compare)',  # closed_walk:700
    'Assign.value>IfExp(test=Attribute,body=Subscript,orelse=Constant)',  # closed_walk:1076
    'Assign.value>IfExp(test=BoolOp,body=Attribute,orelse=Constant)',  # test_a1_identity_formation:518
    'Assign.value>IfExp(test=BoolOp,body=Call,orelse=Constant)',  # closed_walk:947
    'Assign.value>IfExp(test=BoolOp,body=Subscript,orelse=Constant)',  # test_a1_identity_formation:836
    'Assign.value>IfExp(test=BoolOp,body=Subscript,orelse=Name)',  # closed_walk:1296
    'Assign.value>IfExp(test=Call,body=Attribute,orelse=Attribute)',  # test_match_hold_admission_gate_pg (a30d37f6):1251
    'Assign.value>IfExp(test=Call,body=Attribute,orelse=Constant)',  # closed_walk:1944
    'Assign.value>IfExp(test=Call,body=Attribute,orelse=List)',  # closed_walk:480
    'Assign.value>IfExp(test=Call,body=Attribute,orelse=Name)',  # test_match_hold_admission_gate_pg (a30d37f6):664
    'Assign.value>IfExp(test=Call,body=Call,orelse=Constant)',  # closed_walk:768
    'Assign.value>IfExp(test=Call,body=Name,orelse=Call)',  # closed_walk:1466
    'Assign.value>IfExp(test=Call,body=Subscript,orelse=Constant)',  # test_a1_identity_formation:858
    'Assign.value>IfExp(test=Compare,body=Attribute,orelse=Constant)',  # closed_walk:2060
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Call)',  # closed_walk:1657
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Constant)',  # closed_walk:761
    'Assign.value>IfExp(test=Compare,body=Call,orelse=List)',  # closed_walk:723
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Name)',  # test_a1_identity_formation:1031
    'Assign.value>IfExp(test=Compare,body=Constant,orelse=ListComp)',  # closed_walk:961
    'Assign.value>IfExp(test=Compare,body=Name,orelse=BinOp)',  # closed_walk:1054
    'Assign.value>IfExp(test=Compare,body=Name,orelse=Call)',  # closed_walk:1456
    'Assign.value>IfExp(test=Compare,body=Name,orelse=Name)',  # test_a1_identity_formation:629
    'Assign.value>IfExp(test=Compare,body=Name,orelse=Tuple)',  # closed_walk:1913
    'Assign.value>IfExp(test=Compare,body=Subscript,orelse=Constant)',  # closed_walk:1772
    'Assign.value>IfExp(test=Compare,body=Subscript,orelse=Subscript)',  # test_a1_identity_formation:1014
    'Assign.value>IfExp(test=Name,body=Attribute,orelse=Name)',  # test_match_hold_admission_gate_pg (a30d37f6):519
    'Assign.value>IfExp(test=Name,body=Call,orelse=Constant)',  # closed_walk:821
    'Assign.value>IfExp(test=Name,body=Call,orelse=List)',  # test_a1_identity_formation:1290
    'Assign.value>IfExp(test=Name,body=Dict,orelse=Dict)',  # test_a1_identity_formation:3814
    'Assign.value>IfExp(test=Name,body=JoinedStr,orelse=Attribute)',  # test_a1_identity_formation:3831
    'Assign.value>IfExp(test=Name,body=JoinedStr,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):409
    'Assign.value>IfExp(test=Name,body=Subscript,orelse=Constant)',  # closed_walk:1230
    'Assign.value>IfExp(test=UnaryOp,body=Call,orelse=Attribute)',  # closed_walk:699
    'Assign.value>JoinedStr(values=[Constant|FormattedValue])',  # closed_walk:1508
    'Assign.value>Lambda(args=arguments,body=Call)',  # test_match_hold_admission_gate_pg (a30d37f6):201
    'Assign.value>List(elts=[Constant],ctx=Load)',  # closed_walk:1111
    'Assign.value>List(elts=[Dict],ctx=Load)',  # closed_walk:954
    'Assign.value>List(elts=[List],ctx=Load)',  # closed_walk:1057
    'Assign.value>List(elts=[Name],ctx=Load)',  # closed_walk:1493
    'Assign.value>List(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:2449
    'Assign.value>List(elts=[],ctx=Load)',  # closed_walk:70
    'Assign.value>ListComp(elt=Attribute,generators=[comprehension])',  # closed_walk:721
    'Assign.value>ListComp(elt=BinOp,generators=[comprehension])',  # closed_walk:1059
    'Assign.value>ListComp(elt=Call,generators=[comprehension])',  # closed_walk:960
    'Assign.value>ListComp(elt=IfExp,generators=[comprehension])',  # closed_walk:1207
    'Assign.value>ListComp(elt=JoinedStr,generators=[comprehension])',  # test_a1_identity_formation:1487
    'Assign.value>ListComp(elt=Name,generators=[comprehension])',  # closed_walk:177
    'Assign.value>Name(id=str,ctx=Load)',  # closed_walk:113
    'Assign.value>SetComp(elt=Attribute,generators=[comprehension])',  # test_a1_identity_formation:1207
    'Assign.value>SetComp(elt=Call,generators=[comprehension])',  # closed_walk:932
    'Assign.value>SetComp(elt=Name,generators=[comprehension])',  # closed_walk:1238
    'Assign.value>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:146
    'Assign.value>Subscript(value=Attribute,slice=Name,ctx=Load)',  # test_a1_identity_formation:722
    'Assign.value>Subscript(value=Attribute,slice=Subscript,ctx=Load)',  # test_a1_identity_formation:1041
    'Assign.value>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:1858
    'Assign.value>Subscript(value=Call,slice=UnaryOp,ctx=Load)',  # closed_walk:719
    'Assign.value>Subscript(value=Name,slice=Attribute,ctx=Load)',  # test_a1_identity_formation:3841
    'Assign.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:1208
    'Assign.value>Subscript(value=Name,slice=Name,ctx=Load)',  # closed_walk:728
    'Assign.value>Subscript(value=Name,slice=Slice,ctx=Load)',  # closed_walk:1202
    'Assign.value>Subscript(value=Name,slice=UnaryOp,ctx=Load)',  # closed_walk:1286
    'Assign.value>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1320
    'Assign.value>Tuple(elts=[Attribute],ctx=Load)',  # closed_walk:945
    'Assign.value>Tuple(elts=[Attribute|Call|Constant],ctx=Load)',  # test_a1_identity_formation:3667
    'Assign.value>Tuple(elts=[BinOp|Call],ctx=Load)',  # test_a1_identity_formation:3203
    'Assign.value>Tuple(elts=[BinOp|Call|Name],ctx=Load)',  # closed_walk:135
    'Assign.value>Tuple(elts=[BinOp|Constant],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):366
    'Assign.value>Tuple(elts=[Call],ctx=Load)',  # closed_walk:938
    'Assign.value>Tuple(elts=[Call|Constant],ctx=Load)',  # closed_walk:1213
    'Assign.value>Tuple(elts=[Call|Dict],ctx=Load)',  # test_a1_identity_formation:2961
    'Assign.value>Tuple(elts=[Call|JoinedStr],ctx=Load)',  # closed_walk:149
    'Assign.value>Tuple(elts=[Call|List],ctx=Load)',  # closed_walk:268
    'Assign.value>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:631
    'Assign.value>Tuple(elts=[Constant|IfExp],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):355
    'Assign.value>Tuple(elts=[Constant|JoinedStr],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):344
    'Assign.value>Tuple(elts=[Constant|List],ctx=Load)',  # test_a1_identity_formation:1141
    'Assign.value>Tuple(elts=[Dict],ctx=Load)',  # closed_walk:931
    'Assign.value>Tuple(elts=[List],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):236
    'Assign.value>Tuple(elts=[Name],ctx=Load)',  # closed_walk:194
    'Assign.value>Tuple(elts=[Name|Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):1317
    'Assign.value>Tuple(elts=[Subscript],ctx=Load)',  # test_a1_identity_formation:1439
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant])',  # test_a1_identity_formation:87
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # test_a1_identity_formation:59
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',  # test_a1_identity_formation:88
    'AsyncFunctionDef.body>AugAssign(target=Attribute,op=Add,value=Constant)',  # test_a1_identity_formation:60
    'AsyncFunctionDef.body>Expr(value=Await)',  # test_a1_identity_formation:1567
    'AsyncFunctionDef.body>Expr(value=Call)',  # test_a1_identity_formation:89
    'AsyncFunctionDef.body>Expr(value=Constant)',  # test_a1_identity_formation:1560
    'AsyncFunctionDef.body>If(test=Compare,body=[Assert|Assign|If|Return],orelse=[])',  # test_a1_identity_formation:91
    'AsyncFunctionDef.body>If(test=Compare,body=[AugAssign|If],orelse=[])',  # test_a1_identity_formation:3450
    'AsyncFunctionDef.body>Return(value=Await)',  # test_a1_identity_formation:3457
    'AsyncFunctionDef.body>Return(value=Call)',  # test_a1_identity_formation:100
    'AsyncFunctionDef.body>Return(value=Constant)',  # test_a1_identity_formation:64
    'AsyncFunctionDef.body>Return(value=Name)',  # test_a1_identity_formation:61
    'Attribute.ctx>Load()',  # closed_walk:71
    'Attribute.ctx>Store()',  # closed_walk:108
    "Attribute.value>Attribute(value=Attribute,attr='func',ctx=Load)",  # closed_walk:765
    "Attribute.value>Attribute(value=Attribute,attr='value',ctx=Load)",  # closed_walk:947
    "Attribute.value>Attribute(value=Call,attr='__name__',ctx=Load)",  # closed_walk:2049
    "Attribute.value>Attribute(value=Call,attr='grammar',ctx=Load)",  # test_a1_identity_formation:638
    "Attribute.value>Attribute(value=Call,attr='parent',ctx=Load)",  # test_a1_identity_formation:4413
    "Attribute.value>Attribute(value=Name,attr='__code__',ctx=Load)",  # closed_walk:167
    "Attribute.value>Attribute(value=Name,attr='__dict__',ctx=Load)",  # test_a1_identity_formation:4475
    "Attribute.value>Attribute(value=Name,attr='_done',ctx=Load)",  # closed_walk:133
    "Attribute.value>Attribute(value=Name,attr='_enumerated',ctx=Load)",  # closed_walk:635
    "Attribute.value>Attribute(value=Name,attr='_walked_nodes',ctx=Load)",  # closed_walk:1482
    "Attribute.value>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:436
    "Attribute.value>Attribute(value=Name,attr='b',ctx=Load)",  # closed_walk:1515
    "Attribute.value>Attribute(value=Name,attr='effects',ctx=Load)",  # closed_walk:1607
    "Attribute.value>Attribute(value=Name,attr='func',ctx=Load)",  # closed_walk:314
    "Attribute.value>Attribute(value=Name,attr='grammar',ctx=Load)",  # closed_walk:1013
    "Attribute.value>Attribute(value=Name,attr='helper',ctx=Load)",  # closed_walk:1507
    "Attribute.value>Attribute(value=Name,attr='leases',ctx=Load)",  # test_a1_identity_formation:98
    "Attribute.value>Attribute(value=Name,attr='left',ctx=Load)",  # closed_walk:905
    "Attribute.value>Attribute(value=Name,attr='nt_seen',ctx=Load)",  # closed_walk:125
    "Attribute.value>Attribute(value=Name,attr='p',ctx=Load)",  # closed_walk:1503
    "Attribute.value>Attribute(value=Name,attr='params',ctx=Load)",  # test_a1_identity_formation:90
    "Attribute.value>Attribute(value=Name,attr='path',ctx=Load)",  # closed_walk:167
    "Attribute.value>Attribute(value=Name,attr='policy',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):234
    "Attribute.value>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):245
    "Attribute.value>Attribute(value=Name,attr='seen',ctx=Load)",  # closed_walk:139
    "Attribute.value>Attribute(value=Name,attr='session',ctx=Load)",  # test_a1_identity_formation:60
    "Attribute.value>Attribute(value=Name,attr='sites',ctx=Load)",  # closed_walk:445
    "Attribute.value>Attribute(value=Name,attr='slice',ctx=Load)",  # closed_walk:1039
    "Attribute.value>Attribute(value=Name,attr='statements',ctx=Load)",  # test_a1_identity_formation:89
    "Attribute.value>Attribute(value=Name,attr='target',ctx=Load)",  # closed_walk:968
    "Attribute.value>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:760
    "Attribute.value>Attribute(value=Name,attr='walked_defs',ctx=Load)",  # closed_walk:2096
    "Attribute.value>Attribute(value=Name,attr='walking',ctx=Load)",  # closed_walk:1886
    "Attribute.value>Attribute(value=Subscript,attr='body',ctx=Load)",  # test_a1_identity_formation:4534
    "Attribute.value>Attribute(value=Subscript,attr='value',ctx=Load)",  # closed_walk:791
    'Attribute.value>Await(value=Call)',  # test_a1_identity_formation:1562
    'Attribute.value>BoolOp(op=Or,values=[Attribute])',  # closed_walk:461
    'Attribute.value>BoolOp(op=Or,values=[Call|Name])',  # closed_walk:1328
    'Attribute.value>Call(func=Attribute,args=[Call],keywords=[])',  # test_a1_identity_formation:4534
    'Attribute.value>Call(func=Attribute,args=[Call],keywords=[keyword])',  # test_a1_identity_formation:2924
    'Attribute.value>Call(func=Attribute,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:4333
    'Attribute.value>Call(func=Attribute,args=[List|Name],keywords=[])',  # closed_walk:445
    'Attribute.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:138
    'Attribute.value>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:128
    'Attribute.value>Call(func=Name,args=[Constant],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1046
    'Attribute.value>Call(func=Name,args=[Constant],keywords=[keyword])',  # closed_walk:360
    'Attribute.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:355
    'Attribute.value>Call(func=Name,args=[IfExp|Name],keywords=[])',  # closed_walk:1298
    'Attribute.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:136
    'Attribute.value>Call(func=Name,args=[Name],keywords=[keyword])',  # closed_walk:1309
    'Attribute.value>Call(func=Name,args=[],keywords=[])',  # test_a1_identity_formation:1166
    'Attribute.value>Constant(value=str)',  # closed_walk:575
    'Attribute.value>Name(id=str,ctx=Load)',  # closed_walk:71
    'Attribute.value>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:788
    'Attribute.value>Subscript(value=Attribute,slice=UnaryOp,ctx=Load)',  # test_a1_identity_formation:1355
    'Attribute.value>Subscript(value=Name,slice=BinOp,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):617
    'Attribute.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:788
    'Attribute.value>Subscript(value=Name,slice=Name,ctx=Load)',  # closed_walk:1989
    'Attribute.value>Subscript(value=Name,slice=Slice,ctx=Load)',  # test_a1_identity_formation:486
    'Attribute.value>Subscript(value=Name,slice=Subscript,ctx=Load)',  # test_a1_identity_formation:2292
    'Attribute.value>Subscript(value=Name,slice=UnaryOp,ctx=Load)',  # test_a1_identity_formation:1398
    'Attribute.value>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1321
    'AugAssign.op>Add()',  # closed_walk:1503
    'AugAssign.op>BitOr()',  # test_a1_identity_formation:4727
    'AugAssign.op>Sub()',  # test_a1_identity_formation:1231
    "AugAssign.target>Attribute(value=Attribute,attr='savepoints',ctx=Store)",  # test_a1_identity_formation:60
    "AugAssign.target>Attribute(value=Name,attr='_lock_calls',ctx=Store)",  # test_a1_identity_formation:3451
    "AugAssign.target>Attribute(value=Name,attr='commits',ctx=Store)",  # test_a1_identity_formation:82
    "AugAssign.target>Attribute(value=Name,attr='depth',ctx=Store)",  # test_a1_identity_formation:2809
    "AugAssign.target>Attribute(value=Name,attr='rollbacks',ctx=Store)",  # test_a1_identity_formation:85
    'AugAssign.target>Name(id=str,ctx=Store)',  # test_a1_identity_formation:1134
    'AugAssign.target>Subscript(value=Attribute,slice=BinOp,ctx=Store)',  # closed_walk:1545
    'AugAssign.target>Subscript(value=Attribute,slice=Constant,ctx=Store)',  # closed_walk:1503
    'AugAssign.target>Subscript(value=Name,slice=BinOp,ctx=Store)',  # test_a1_identity_formation:1109
    'AugAssign.target>Subscript(value=Name,slice=Constant,ctx=Store)',  # test_a1_identity_formation:1070
    'AugAssign.target>Subscript(value=Name,slice=JoinedStr,ctx=Store)',  # test_a1_identity_formation:1282
    'AugAssign.target>Subscript(value=Name,slice=Tuple,ctx=Store)',  # test_match_hold_admission_gate_pg (a30d37f6):239
    'AugAssign.value>Call(func=Name,args=[Attribute|Name],keywords=[])',  # test_a1_identity_formation:1134
    'AugAssign.value>Constant(value=int)',  # closed_walk:1503
    'AugAssign.value>SetComp(elt=Name,generators=[comprehension])',  # test_a1_identity_formation:4727
    'Await.value>Call(func=Attribute,args=[Call],keywords=[])',  # test_a1_identity_formation:1562
    'Await.value>Call(func=Attribute,args=[Name],keywords=[])',  # test_a1_identity_formation:3457
    'Await.value>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:1574
    "BinOp.left>Attribute(value=Attribute,attr='co_firstlineno',ctx=Load)",  # closed_walk:167
    "BinOp.left>Attribute(value=Attribute,attr='defaults',ctx=Load)",  # closed_walk:1576
    "BinOp.left>Attribute(value=Attribute,attr='parent',ctx=Load)",  # test_a1_identity_formation:4413
    "BinOp.left>Attribute(value=Attribute,attr='posonlyargs',ctx=Load)",  # closed_walk:721
    "BinOp.left>Attribute(value=Name,attr='body',ctx=Load)",  # test_a1_identity_formation:1429
    "BinOp.left>Attribute(value=Name,attr='end_lineno',ctx=Load)",  # test_a1_identity_formation:3232
    "BinOp.left>Attribute(value=Name,attr='parent',ctx=Load)",  # test_a1_identity_formation:3863
    "BinOp.left>Attribute(value=Name,attr='posonlyargs',ctx=Load)",  # closed_walk:378
    "BinOp.left>Attribute(value=Name,attr='pure_calls',ctx=Load)",  # closed_walk:1420
    "BinOp.left>Attribute(value=Name,attr='pure_methods',ctx=Load)",  # closed_walk:1421
    'BinOp.left>BinOp(left=Attribute,op=Add,right=Attribute)',  # closed_walk:378
    'BinOp.left>BinOp(left=Attribute,op=Div,right=Constant)',  # test_a1_identity_formation:4413
    'BinOp.left>BinOp(left=BinOp,op=Add,right=Attribute)',  # closed_walk:378
    'BinOp.left>BinOp(left=BinOp,op=Add,right=Constant)',  # test_a1_identity_formation:3751
    'BinOp.left>BinOp(left=BinOp,op=Add,right=JoinedStr)',  # test_a1_identity_formation:3755
    'BinOp.left>BinOp(left=BinOp,op=Add,right=List)',  # test_a1_identity_formation:2372
    'BinOp.left>BinOp(left=BinOp,op=Add,right=ListComp)',  # test_a1_identity_formation:2372
    'BinOp.left>BinOp(left=BinOp,op=Add,right=Name)',  # test_a1_identity_formation:2452
    'BinOp.left>BinOp(left=Call,op=Add,right=Call)',  # closed_walk:436
    'BinOp.left>BinOp(left=Constant,op=Add,right=Call)',  # test_a1_identity_formation:3035
    'BinOp.left>BinOp(left=Constant,op=Add,right=Name)',  # test_a1_identity_formation:3693
    'BinOp.left>BinOp(left=Constant,op=Mult,right=BoolOp)',  # closed_walk:75
    'BinOp.left>BinOp(left=List,op=Add,right=ListComp)',  # test_a1_identity_formation:2372
    'BinOp.left>BinOp(left=List,op=Add,right=Name)',  # test_a1_identity_formation:2466
    'BinOp.left>BinOp(left=Name,op=Add,right=Constant)',  # closed_walk:1218
    'BinOp.left>BinOp(left=Name,op=Add,right=List)',  # test_a1_identity_formation:2472
    'BinOp.left>BinOp(left=Name,op=Add,right=Name)',  # test_a1_identity_formation:2450
    'BinOp.left>BinOp(left=Name,op=Sub,right=Attribute)',  # closed_walk:1247
    'BinOp.left>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:486
    'BinOp.left>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # closed_walk:946
    'BinOp.left>Call(func=Attribute,args=[Name],keywords=[])',  # test_a1_identity_formation:4472
    'BinOp.left>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:436
    'BinOp.left>Call(func=Name,args=[Constant|Name],keywords=[])',  # test_a1_identity_formation:1483
    'BinOp.left>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:977
    'BinOp.left>Call(func=Name,args=[],keywords=[])',  # closed_walk:281
    'BinOp.left>Constant(value=str)',  # closed_walk:75
    'BinOp.left>IfExp(test=Name,body=Constant,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):1832
    'BinOp.left>JoinedStr(values=[Constant|FormattedValue])',  # test_match_hold_admission_gate_pg (a30d37f6):366
    'BinOp.left>List(elts=[BinOp],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):1832
    'BinOp.left>List(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:2372
    'BinOp.left>ListComp(elt=JoinedStr,generators=[comprehension])',  # test_a1_identity_formation:2180
    'BinOp.left>Name(id=str,ctx=Load)',  # closed_walk:135
    'BinOp.left>Subscript(value=Attribute,slice=Slice,ctx=Load)',  # test_a1_identity_formation:1368
    'BinOp.left>Subscript(value=Name,slice=Attribute,ctx=Load)',  # closed_walk:1054
    'BinOp.left>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1352
    'BinOp.left>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:4382
    'BinOp.op>Add()',  # closed_walk:75
    'BinOp.op>BitAnd()',  # closed_walk:1054
    'BinOp.op>BitOr()',  # closed_walk:977
    'BinOp.op>Div()',  # test_a1_identity_formation:3863
    'BinOp.op>Mult()',  # closed_walk:75
    'BinOp.op>Sub()',  # closed_walk:167
    "BinOp.right>Attribute(value=Attribute,attr='args',ctx=Load)",  # closed_walk:721
    "BinOp.right>Attribute(value=Attribute,attr='attr',ctx=Load)",  # closed_walk:1685
    "BinOp.right>Attribute(value=Attribute,attr='kwonlyargs',ctx=Load)",  # closed_walk:1928
    "BinOp.right>Attribute(value=Call,attr='__name__',ctx=Load)",  # closed_walk:1545
    "BinOp.right>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:378
    "BinOp.right>Attribute(value=Name,attr='kwonlyargs',ctx=Load)",  # closed_walk:378
    "BinOp.right>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_a1_identity_formation:1368
    "BinOp.right>Attribute(value=Name,attr='read',ctx=Load)",  # closed_walk:1247
    "BinOp.right>Attribute(value=Name,attr='setting',ctx=Load)",  # closed_walk:1254
    "BinOp.right>Attribute(value=Name,attr='write',ctx=Load)",  # closed_walk:1247
    'BinOp.right>BoolOp(op=Or,values=[Attribute|Constant])',  # closed_walk:75
    'BinOp.right>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:1242
    'BinOp.right>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:4554
    'BinOp.right>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # test_a1_identity_formation:1109
    'BinOp.right>Call(func=Attribute,args=[Name],keywords=[])',  # test_a1_identity_formation:1155
    'BinOp.right>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:436
    'BinOp.right>Call(func=Name,args=[Constant],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1046
    'BinOp.right>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:135
    'BinOp.right>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:281
    'BinOp.right>Constant(value=int)',  # closed_walk:167
    'BinOp.right>Constant(value=str)',  # test_a1_identity_formation:3035
    'BinOp.right>IfExp(test=Attribute,body=Subscript,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):367
    'BinOp.right>IfExp(test=Name,body=BinOp,orelse=Constant)',  # test_a1_identity_formation:1109
    'BinOp.right>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:3755
    'BinOp.right>List(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:2377
    'BinOp.right>List(elts=[JoinedStr],ctx=Load)',  # test_a1_identity_formation:2220
    'BinOp.right>List(elts=[Name],ctx=Load)',  # closed_walk:1059
    'BinOp.right>ListComp(elt=Attribute,generators=[comprehension])',  # closed_walk:1620
    'BinOp.right>ListComp(elt=BinOp,generators=[comprehension])',  # closed_walk:985
    'BinOp.right>ListComp(elt=Call,generators=[comprehension])',  # test_a1_identity_formation:2448
    'BinOp.right>ListComp(elt=JoinedStr,generators=[comprehension])',  # test_a1_identity_formation:2182
    'BinOp.right>ListComp(elt=Name,generators=[comprehension])',  # closed_walk:379
    'BinOp.right>Name(id=str,ctx=Load)',  # closed_walk:139
    'BinOp.right>Set(elts=[Constant])',  # closed_walk:1821
    'BinOp.right>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:2430
    'BinOp.right>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:4517
    'BinOp.right>Tuple(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:1262
    'BoolOp.op>And()',  # closed_walk:188
    'BoolOp.op>Or()',  # closed_walk:75
    "BoolOp.values>Attribute(value=Attribute,attr='kwarg',ctx=Load)",  # closed_walk:1929
    "BoolOp.values>Attribute(value=Attribute,attr='vararg',ctx=Load)",  # closed_walk:1929
    "BoolOp.values>Attribute(value=Call,attr='parameters',ctx=Load)",  # closed_walk:777
    "BoolOp.values>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:1749
    "BoolOp.values>Attribute(value=Name,attr='asname',ctx=Load)",  # closed_walk:461
    "BoolOp.values>Attribute(value=Name,attr='body',ctx=Load)",  # closed_walk:1939
    "BoolOp.values>Attribute(value=Name,attr='decorator_list',ctx=Load)",  # closed_walk:2080
    "BoolOp.values>Attribute(value=Name,attr='defaults',ctx=Load)",  # closed_walk:1031
    "BoolOp.values>Attribute(value=Name,attr='depth',ctx=Load)",  # test_a1_identity_formation:2824
    "BoolOp.values>Attribute(value=Name,attr='handlers',ctx=Load)",  # closed_walk:1936
    "BoolOp.values>Attribute(value=Name,attr='keywords',ctx=Load)",  # closed_walk:1031
    "BoolOp.values>Attribute(value=Name,attr='kwarg',ctx=Load)",  # closed_walk:1030
    "BoolOp.values>Attribute(value=Name,attr='kwonlyargs',ctx=Load)",  # closed_walk:1031
    "BoolOp.values>Attribute(value=Name,attr='level',ctx=Load)",  # closed_walk:75
    "BoolOp.values>Attribute(value=Name,attr='lineno',ctx=Load)",  # test_a1_identity_formation:1069
    "BoolOp.values>Attribute(value=Name,attr='module',ctx=Load)",  # closed_walk:75
    "BoolOp.values>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:461
    "BoolOp.values>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_a1_identity_formation:1329
    "BoolOp.values>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):365
    "BoolOp.values>Attribute(value=Name,attr='rest',ctx=Load)",  # closed_walk:469
    "BoolOp.values>Attribute(value=Name,attr='vararg',ctx=Load)",  # closed_walk:1030
    'BoolOp.values>BinOp(left=Name,op=BitAnd,right=Attribute)',  # closed_walk:1258
    'BoolOp.values>BinOp(left=Name,op=BitAnd,right=Name)',  # test_a1_identity_formation:2982
    'BoolOp.values>BoolOp(op=And,values=[Call])',  # test_match_hold_admission_gate_pg (a30d37f6):1259
    'BoolOp.values>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:693
    'BoolOp.values>BoolOp(op=And,values=[Compare])',  # closed_walk:1232
    'BoolOp.values>BoolOp(op=And,values=[Compare|Name])',  # test_a1_identity_formation:1100
    'BoolOp.values>BoolOp(op=Or,values=[Attribute|UnaryOp])',  # closed_walk:1923
    'BoolOp.values>BoolOp(op=Or,values=[BoolOp|Subscript])',  # test_a1_identity_formation:1100
    'BoolOp.values>BoolOp(op=Or,values=[Call])',  # closed_walk:1956
    'BoolOp.values>BoolOp(op=Or,values=[Compare])',  # test_a1_identity_formation:3193
    'BoolOp.values>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:1560
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Constant],keywords=[])',  # closed_walk:1078
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Constant|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):288
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Constant|Tuple],keywords=[])',  # test_a1_identity_formation:522
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # test_a1_identity_formation:800
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Name|Tuple],keywords=[])',  # test_a1_identity_formation:852
    'BoolOp.values>Call(func=Attribute,args=[Attribute|Subscript|Tuple],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):816
    'BoolOp.values>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:3245
    'BoolOp.values>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # closed_walk:872
    'BoolOp.values>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # test_a1_identity_formation:1073
    'BoolOp.values>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:164
    'BoolOp.values>Call(func=Attribute,args=[Name|Subscript|Tuple],keywords=[])',  # test_a1_identity_formation:2252
    'BoolOp.values>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:3251
    'BoolOp.values>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:313
    'BoolOp.values>Call(func=Name,args=[Attribute|Constant],keywords=[])',  # test_a1_identity_formation:2823
    'BoolOp.values>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',  # closed_walk:1945
    'BoolOp.values>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:311
    'BoolOp.values>Call(func=Name,args=[Attribute|Subscript],keywords=[])',  # closed_walk:787
    'BoolOp.values>Call(func=Name,args=[Attribute|Tuple],keywords=[])',  # closed_walk:311
    'BoolOp.values>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:525
    'BoolOp.values>Call(func=Name,args=[Constant|Name|Subscript],keywords=[])',  # test_a1_identity_formation:863
    'BoolOp.values>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:871
    'BoolOp.values>Call(func=Name,args=[IfExp|Name],keywords=[])',  # test_a1_identity_formation:1233
    'BoolOp.values>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:710
    'BoolOp.values>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:467
    'BoolOp.values>Call(func=Name,args=[Subscript],keywords=[])',  # closed_walk:1946
    'BoolOp.values>Call(func=Name,args=[Subscript|Tuple],keywords=[])',  # test_a1_identity_formation:533
    'BoolOp.values>Compare(left=Attribute,ops=[Eq],comparators=[Attribute])',  # closed_walk:549
    'BoolOp.values>Compare(left=Attribute,ops=[Eq],comparators=[Constant])',  # closed_walk:950
    'BoolOp.values>Compare(left=Attribute,ops=[Eq],comparators=[Name])',  # closed_walk:523
    'BoolOp.values>Compare(left=Attribute,ops=[In],comparators=[Call])',  # closed_walk:667
    'BoolOp.values>Compare(left=Attribute,ops=[In],comparators=[Name])',  # closed_walk:314
    'BoolOp.values>Compare(left=Attribute,ops=[In],comparators=[Tuple])',  # test_a1_identity_formation:523
    'BoolOp.values>Compare(left=Attribute,ops=[IsNot],comparators=[Constant])',  # closed_walk:604
    'BoolOp.values>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # closed_walk:788
    'BoolOp.values>Compare(left=Attribute,ops=[Is],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):776
    'BoolOp.values>Compare(left=Attribute,ops=[NotEq],comparators=[Constant])',  # closed_walk:1759
    'BoolOp.values>Compare(left=Attribute,ops=[NotEq],comparators=[UnaryOp])',  # closed_walk:855
    'BoolOp.values>Compare(left=BinOp,ops=[Lt],comparators=[Call])',  # closed_walk:1225
    'BoolOp.values>Compare(left=BinOp,ops=[NotIn],comparators=[Name])',  # test_a1_identity_formation:3253
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # closed_walk:672
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[JoinedStr])',  # test_a1_identity_formation:904
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Name])',  # test_a1_identity_formation:850
    'BoolOp.values>Compare(left=Call,ops=[GtE],comparators=[Call])',  # test_match_hold_admission_gate_pg (a30d37f6):703
    'BoolOp.values>Compare(left=Call,ops=[Gt],comparators=[Call])',  # test_match_hold_admission_gate_pg (a30d37f6):702
    'BoolOp.values>Compare(left=Call,ops=[Gt],comparators=[Name])',  # closed_walk:1860
    'BoolOp.values>Compare(left=Call,ops=[In],comparators=[Attribute])',  # closed_walk:1623
    'BoolOp.values>Compare(left=Call,ops=[In],comparators=[Name])',  # closed_walk:971
    'BoolOp.values>Compare(left=Call,ops=[In],comparators=[Tuple])',  # test_a1_identity_formation:920
    'BoolOp.values>Compare(left=Call,ops=[IsNot],comparators=[Constant])',  # closed_walk:1637
    'BoolOp.values>Compare(left=Call,ops=[Is],comparators=[Constant])',  # test_a1_identity_formation:1383
    'BoolOp.values>Compare(left=Call,ops=[Is],comparators=[Name])',  # closed_walk:1051
    'BoolOp.values>Compare(left=Call,ops=[LtE],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):583
    'BoolOp.values>Compare(left=Call,ops=[Lt],comparators=[Constant])',  # test_match_hold_admission_gate_pg (a30d37f6):784
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Call])',  # closed_walk:1032
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Constant])',  # closed_walk:174
    'BoolOp.values>Compare(left=Call,ops=[NotIn],comparators=[Attribute])',  # closed_walk:1500
    'BoolOp.values>Compare(left=Call,ops=[NotIn],comparators=[Name])',  # test_a1_identity_formation:924
    'BoolOp.values>Compare(left=Constant,ops=[In],comparators=[Name])',  # closed_walk:1097
    'BoolOp.values>Compare(left=Constant,ops=[NotIn],comparators=[Name])',  # closed_walk:1253
    'BoolOp.values>Compare(left=ListComp,ops=[NotEq],comparators=[List])',  # test_a1_identity_formation:1378
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # closed_walk:517
    'BoolOp.values>Compare(left=Name,ops=[Gt],comparators=[Constant])',  # closed_walk:1223
    'BoolOp.values>Compare(left=Name,ops=[Gt],comparators=[Subscript])',  # test_a1_identity_formation:3193
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Attribute])',  # closed_walk:1235
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Name])',  # closed_walk:188
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Subscript])',  # test_a1_identity_formation:1322
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Tuple])',  # closed_walk:1231
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # closed_walk:474
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Name])',  # closed_walk:517
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Constant])',  # closed_walk:174
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Name])',  # closed_walk:727
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Subscript])',  # test_a1_identity_formation:1504
    'BoolOp.values>Compare(left=Name,ops=[LtE],comparators=[Name])',  # test_a1_identity_formation:3193
    'BoolOp.values>Compare(left=Name,ops=[Lt],comparators=[Call])',  # closed_walk:727
    'BoolOp.values>Compare(left=Name,ops=[NotEq],comparators=[Name])',  # closed_walk:732
    'BoolOp.values>Compare(left=Name,ops=[NotIn],comparators=[Call])',  # closed_walk:474
    'BoolOp.values>Compare(left=Name,ops=[NotIn],comparators=[Name])',  # closed_walk:1239
    'BoolOp.values>Compare(left=Name,ops=[NotIn],comparators=[Tuple])',  # closed_walk:1776
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # closed_walk:672
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Name])',  # test_a1_identity_formation:1322
    'BoolOp.values>Compare(left=Subscript,ops=[Eq],comparators=[Subscript])',  # closed_walk:1187
    'BoolOp.values>Compare(left=Subscript,ops=[In],comparators=[Tuple])',  # closed_walk:1187
    'BoolOp.values>Compare(left=Subscript,ops=[Is],comparators=[Name])',  # closed_walk:188
    'BoolOp.values>Compare(left=Subscript,ops=[Is],comparators=[Subscript])',  # test_a1_identity_formation:2273
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',  # closed_walk:1205
    'BoolOp.values>Compare(left=Subscript,ops=[NotIn],comparators=[Tuple])',  # closed_walk:906
    'BoolOp.values>Compare(left=Tuple,ops=[Eq],comparators=[Tuple])',  # test_a1_identity_formation:1101
    'BoolOp.values>Constant(value=NoneType)',  # test_a1_identity_formation:1073
    'BoolOp.values>Constant(value=int)',  # closed_walk:75
    'BoolOp.values>Constant(value=str)',  # closed_walk:75
    'BoolOp.values>Dict(keys=[],values=[])',  # closed_walk:836
    'BoolOp.values>List(elts=[Constant],ctx=Load)',  # closed_walk:1025
    'BoolOp.values>List(elts=[],ctx=Load)',  # closed_walk:1157
    'BoolOp.values>Name(id=str,ctx=Load)',  # closed_walk:525
    'BoolOp.values>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1100
    'BoolOp.values>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1069
    'BoolOp.values>UnaryOp(op=Not,operand=Attribute)',  # closed_walk:552
    'BoolOp.values>UnaryOp(op=Not,operand=BinOp)',  # closed_walk:1253
    'BoolOp.values>UnaryOp(op=Not,operand=BoolOp)',  # closed_walk:732
    'BoolOp.values>UnaryOp(op=Not,operand=Call)',  # closed_walk:448
    'BoolOp.values>UnaryOp(op=Not,operand=Compare)',  # test_a1_identity_formation:1209
    'BoolOp.values>UnaryOp(op=Not,operand=Name)',  # closed_walk:981
    'BoolOp.values>UnaryOp(op=Not,operand=Subscript)',  # test_match_hold_admission_gate_pg (a30d37f6):365
    "Call.args>Attribute(value=Attribute,attr='__name__',ctx=Load)",  # closed_walk:1507
    "Call.args>Attribute(value=Attribute,attr='callee',ctx=Load)",  # closed_walk:1648
    "Call.args>Attribute(value=Attribute,attr='defaults',ctx=Load)",  # closed_walk:436
    "Call.args>Attribute(value=Attribute,attr='execute_kind',ctx=Load)",  # closed_walk:1766
    "Call.args>Attribute(value=Attribute,attr='func',ctx=Load)",  # closed_walk:763
    "Call.args>Attribute(value=Attribute,attr='grammar',ctx=Load)",  # closed_walk:1657
    "Call.args>Attribute(value=Attribute,attr='id',ctx=Load)",  # closed_walk:760
    "Call.args>Attribute(value=Attribute,attr='kw_defaults',ctx=Load)",  # closed_walk:1969
    "Call.args>Attribute(value=Attribute,attr='kwonlyargs',ctx=Load)",  # closed_walk:1969
    "Call.args>Attribute(value=Attribute,attr='listed',ctx=Load)",  # closed_walk:1638
    "Call.args>Attribute(value=Attribute,attr='namedtuple_class',ctx=Load)",  # closed_walk:1642
    "Call.args>Attribute(value=Attribute,attr='opaque_callee',ctx=Load)",  # closed_walk:1809
    "Call.args>Attribute(value=Attribute,attr='pure_awaits',ctx=Load)",  # closed_walk:1781
    "Call.args>Attribute(value=Attribute,attr='pure_calls',ctx=Load)",  # closed_walk:1638
    "Call.args>Attribute(value=Attribute,attr='session',ctx=Load)",  # closed_walk:2061
    "Call.args>Attribute(value=Attribute,attr='session_argument',ctx=Load)",  # closed_walk:1537
    "Call.args>Attribute(value=Attribute,attr='session_root_ok',ctx=Load)",  # closed_walk:1536
    "Call.args>Attribute(value=Attribute,attr='spelled_in',ctx=Load)",  # closed_walk:1774
    "Call.args>Attribute(value=Attribute,attr='sql',ctx=Load)",  # closed_walk:1766
    "Call.args>Attribute(value=Attribute,attr='value',ctx=Load)",  # closed_walk:473
    "Call.args>Attribute(value=Call,attr='__name__',ctx=Load)",  # closed_walk:136
    "Call.args>Attribute(value=Call,attr='body',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):360
    "Call.args>Attribute(value=Call,attr='effects',ctx=Load)",  # closed_walk:1842
    "Call.args>Attribute(value=Call,attr='parameters',ctx=Load)",  # closed_walk:723
    "Call.args>Attribute(value=Name,attr='A1_BINDINGS',ctx=Load)",  # test_a1_identity_formation:617
    "Call.args>Attribute(value=Name,attr='A1_IMPORTS',ctx=Load)",  # test_a1_identity_formation:618
    "Call.args>Attribute(value=Name,attr='A1_MEANINGFUL',ctx=Load)",  # test_a1_identity_formation:617
    "Call.args>Attribute(value=Name,attr='A1_NAMEDTUPLES',ctx=Load)",  # test_a1_identity_formation:618
    "Call.args>Attribute(value=Name,attr='A1_SHAPES',ctx=Load)",  # test_a1_identity_formation:617
    "Call.args>Attribute(value=Name,attr='Add',ctx=Load)",  # closed_walk:846
    "Call.args>Attribute(value=Name,attr='Assert',ctx=Load)",  # closed_walk:2028
    "Call.args>Attribute(value=Name,attr='Assign',ctx=Load)",  # closed_walk:327
    "Call.args>Attribute(value=Name,attr='AsyncWith',ctx=Load)",  # closed_walk:2058
    "Call.args>Attribute(value=Name,attr='Attribute',ctx=Load)",  # closed_walk:313
    "Call.args>Attribute(value=Name,attr='AugAssign',ctx=Load)",  # closed_walk:966
    "Call.args>Attribute(value=Name,attr='Await',ctx=Load)",  # closed_walk:1945
    "Call.args>Attribute(value=Name,attr='BinOp',ctx=Load)",  # closed_walk:846
    "Call.args>Attribute(value=Name,attr='Break',ctx=Load)",  # test_a1_identity_formation:1298
    "Call.args>Attribute(value=Name,attr='Call',ctx=Load)",  # closed_walk:313
    "Call.args>Attribute(value=Name,attr='ClassDef',ctx=Load)",  # closed_walk:454
    "Call.args>Attribute(value=Name,attr='Compare',ctx=Load)",  # closed_walk:899
    "Call.args>Attribute(value=Name,attr='Constant',ctx=Load)",  # closed_walk:786
    "Call.args>Attribute(value=Name,attr='Delete',ctx=Load)",  # closed_walk:2025
    "Call.args>Attribute(value=Name,attr='Dict',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):650
    "Call.args>Attribute(value=Name,attr='DictComp',ctx=Load)",  # closed_walk:1591
    "Call.args>Attribute(value=Name,attr='Eq',ctx=Load)",  # test_a1_identity_formation:854
    "Call.args>Attribute(value=Name,attr='ExceptHandler',ctx=Load)",  # closed_walk:462
    "Call.args>Attribute(value=Name,attr='Expr',ctx=Load)",  # closed_walk:785
    "Call.args>Attribute(value=Name,attr='For',ctx=Load)",  # closed_walk:2037
    "Call.args>Attribute(value=Name,attr='FormattedValue',ctx=Load)",  # closed_walk:854
    "Call.args>Attribute(value=Name,attr='FunctionDef',ctx=Load)",  # closed_walk:2076
    "Call.args>Attribute(value=Name,attr='Global',ctx=Load)",  # closed_walk:2097
    "Call.args>Attribute(value=Name,attr='If',ctx=Load)",  # closed_walk:899
    "Call.args>Attribute(value=Name,attr='IfExp',ctx=Load)",  # closed_walk:937
    "Call.args>Attribute(value=Name,attr='Import',ctx=Load)",  # closed_walk:72
    "Call.args>Attribute(value=Name,attr='ImportFrom',ctx=Load)",  # closed_walk:74
    "Call.args>Attribute(value=Name,attr='Is',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):777
    "Call.args>Attribute(value=Name,attr='IsNot',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1291
    "Call.args>Attribute(value=Name,attr='JoinedStr',ctx=Load)",  # closed_walk:849
    "Call.args>Attribute(value=Name,attr='Lambda',ctx=Load)",  # closed_walk:456
    "Call.args>Attribute(value=Name,attr='Load',ctx=Load)",  # closed_walk:448
    "Call.args>Attribute(value=Name,attr='MatchMapping',ctx=Load)",  # closed_walk:469
    "Call.args>Attribute(value=Name,attr='Module',ctx=Load)",  # closed_walk:1296
    "Call.args>Attribute(value=Name,attr='Name',ctx=Load)",  # closed_walk:311
    "Call.args>Attribute(value=Name,attr='Not',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):815
    "Call.args>Attribute(value=Name,attr='NotIn',ctx=Load)",  # closed_walk:901
    "Call.args>Attribute(value=Name,attr='Pass',ctx=Load)",  # test_a1_identity_formation:1140
    "Call.args>Attribute(value=Name,attr='Raise',ctx=Load)",  # closed_walk:1287
    "Call.args>Attribute(value=Name,attr='Return',ctx=Load)",  # closed_walk:789
    "Call.args>Attribute(value=Name,attr='Starred',ctx=Load)",  # closed_walk:1033
    "Call.args>Attribute(value=Name,attr='Store',ctx=Load)",  # test_a1_identity_formation:3838
    "Call.args>Attribute(value=Name,attr='Subscript',ctx=Load)",  # closed_walk:869
    "Call.args>Attribute(value=Name,attr='Try',ctx=Load)",  # closed_walk:1936
    "Call.args>Attribute(value=Name,attr='Tuple',ctx=Load)",  # test_a1_identity_formation:839
    "Call.args>Attribute(value=Name,attr='UnaryOp',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):814
    "Call.args>Attribute(value=Name,attr='While',ctx=Load)",  # test_a1_identity_formation:896
    "Call.args>Attribute(value=Name,attr='__dict__',ctx=Load)",  # test_a1_identity_formation:3671
    "Call.args>Attribute(value=Name,attr='__file__',ctx=Load)",  # test_a1_identity_formation:3671
    "Call.args>Attribute(value=Name,attr='__name__',ctx=Load)",  # closed_walk:275
    "Call.args>Attribute(value=Name,attr='_ffa_gather_decide',ctx=Load)",  # test_a1_identity_formation:4402
    "Call.args>Attribute(value=Name,attr='allowed',ctx=Load)",  # closed_walk:151
    "Call.args>Attribute(value=Name,attr='annotation',ctx=Load)",  # closed_walk:2087
    "Call.args>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:434
    "Call.args>Attribute(value=Name,attr='attr',ctx=Load)",  # closed_walk:761
    "Call.args>Attribute(value=Name,attr='b',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):425
    "Call.args>Attribute(value=Name,attr='body',ctx=Load)",  # closed_walk:436
    "Call.args>Attribute(value=Name,attr='cause',ctx=Load)",  # closed_walk:2073
    "Call.args>Attribute(value=Name,attr='comprehension',ctx=Load)",  # closed_walk:1581
    "Call.args>Attribute(value=Name,attr='ctx',ctx=Load)",  # closed_walk:311
    "Call.args>Attribute(value=Name,attr='effects',ctx=Load)",  # closed_walk:1490
    "Call.args>Attribute(value=Name,attr='elts',ctx=Load)",  # test_a1_identity_formation:839
    "Call.args>Attribute(value=Name,attr='end_lineno',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):62
    "Call.args>Attribute(value=Name,attr='exc',ctx=Load)",  # closed_walk:2071
    "Call.args>Attribute(value=Name,attr='expr',ctx=Load)",  # closed_walk:1500
    "Call.args>Attribute(value=Name,attr='finalbody',ctx=Load)",  # closed_walk:2048
    "Call.args>Attribute(value=Name,attr='func',ctx=Load)",  # closed_walk:313
    "Call.args>Attribute(value=Name,attr='grammar',ctx=Load)",  # closed_walk:766
    "Call.args>Attribute(value=Name,attr='guarded',ctx=Load)",  # closed_walk:1767
    "Call.args>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:312
    "Call.args>Attribute(value=Name,attr='iter',ctx=Load)",  # closed_walk:1583
    "Call.args>Attribute(value=Name,attr='keys',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):654
    "Call.args>Attribute(value=Name,attr='left',ctx=Load)",  # closed_walk:847
    "Call.args>Attribute(value=Name,attr='lineno',ctx=Load)",  # closed_walk:844
    "Call.args>Attribute(value=Name,attr='local',ctx=Load)",  # closed_walk:1766
    "Call.args>Attribute(value=Name,attr='meaningful',ctx=Load)",  # closed_walk:150
    "Call.args>Attribute(value=Name,attr='module',ctx=Load)",  # closed_walk:755
    "Call.args>Attribute(value=Name,attr='msg',ctx=Load)",  # closed_walk:2031
    "Call.args>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:451
    "Call.args>Attribute(value=Name,attr='op',ctx=Load)",  # closed_walk:846
    "Call.args>Attribute(value=Name,attr='opaque',ctx=Load)",  # closed_walk:1804
    "Call.args>Attribute(value=Name,attr='operand',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):816
    "Call.args>Attribute(value=Name,attr='ops',ctx=Load)",  # closed_walk:900
    "Call.args>Attribute(value=Name,attr='orelse',ctx=Load)",  # closed_walk:938
    "Call.args>Attribute(value=Name,attr='p',ctx=Load)",  # closed_walk:1659
    "Call.args>Attribute(value=Name,attr='params',ctx=Load)",  # closed_walk:1774
    "Call.args>Attribute(value=Name,attr='policy',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):290
    "Call.args>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1224
    "Call.args>Attribute(value=Name,attr='pure_awaits',ctx=Load)",  # closed_walk:1422
    "Call.args>Attribute(value=Name,attr='pure_calls',ctx=Load)",  # closed_walk:1916
    "Call.args>Attribute(value=Name,attr='pure_methods',ctx=Load)",  # closed_walk:1916
    "Call.args>Attribute(value=Name,attr='rest',ctx=Load)",  # closed_walk:470
    "Call.args>Attribute(value=Name,attr='returns',ctx=Load)",  # closed_walk:2089
    "Call.args>Attribute(value=Name,attr='right',ctx=Load)",  # closed_walk:848
    "Call.args>Attribute(value=Name,attr='scope',ctx=Load)",  # closed_walk:511
    "Call.args>Attribute(value=Name,attr='session',ctx=Load)",  # closed_walk:677
    "Call.args>Attribute(value=Name,attr='shapes',ctx=Load)",  # closed_walk:144
    "Call.args>Attribute(value=Name,attr='slice',ctx=Load)",  # closed_walk:1038
    "Call.args>Attribute(value=Name,attr='sql',ctx=Load)",  # closed_walk:1422
    "Call.args>Attribute(value=Name,attr='statements',ctx=Load)",  # test_a1_identity_formation:108
    "Call.args>Attribute(value=Name,attr='stmt',ctx=Load)",  # closed_walk:894
    "Call.args>Attribute(value=Name,attr='target',ctx=Load)",  # closed_walk:967
    "Call.args>Attribute(value=Name,attr='targets',ctx=Load)",  # closed_walk:943
    "Call.args>Attribute(value=Name,attr='test',ctx=Load)",  # closed_walk:2029
    "Call.args>Attribute(value=Name,attr='type',ctx=Load)",  # closed_walk:2054
    "Call.args>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:759
    "Call.args>Attribute(value=Name,attr='values',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):653
    "Call.args>Attribute(value=Subscript,attr='id',ctx=Load)",  # closed_walk:909
    "Call.args>Attribute(value=Subscript,attr='lineno',ctx=Load)",  # test_a1_identity_formation:1266
    "Call.args>Attribute(value=Subscript,attr='name',ctx=Load)",  # closed_walk:793
    "Call.args>Attribute(value=Subscript,attr='names',ctx=Load)",  # closed_walk:788
    "Call.args>Attribute(value=Subscript,attr='target',ctx=Load)",  # test_a1_identity_formation:908
    "Call.args>Attribute(value=Subscript,attr='value',ctx=Load)",  # closed_walk:790
    'Call.args>BinOp(left=Attribute,op=Add,right=Constant)',  # test_a1_identity_formation:3232
    'Call.args>BinOp(left=Attribute,op=BitOr,right=Name)',  # closed_walk:1420
    'Call.args>BinOp(left=BinOp,op=Add,right=Call)',  # closed_walk:1220
    'Call.args>BinOp(left=BinOp,op=Add,right=Constant)',  # test_a1_identity_formation:3035
    'Call.args>BinOp(left=BinOp,op=Add,right=List)',  # test_a1_identity_formation:2452
    'Call.args>BinOp(left=BinOp,op=Add,right=ListComp)',  # test_a1_identity_formation:2372
    'Call.args>BinOp(left=BinOp,op=Add,right=Name)',  # test_a1_identity_formation:2450
    'Call.args>BinOp(left=Call,op=Add,right=Constant)',  # test_a1_identity_formation:486
    'Call.args>BinOp(left=Call,op=Add,right=Name)',  # test_match_hold_admission_gate_pg (a30d37f6):1061
    'Call.args>BinOp(left=Call,op=Add,right=Tuple)',  # test_a1_identity_formation:4517
    'Call.args>BinOp(left=Call,op=Sub,right=Call)',  # closed_walk:281
    'Call.args>BinOp(left=Constant,op=Add,right=Subscript)',  # test_match_hold_admission_gate_pg (a30d37f6):381
    'Call.args>BinOp(left=List,op=Add,right=ListComp)',  # test_match_hold_admission_gate_pg (a30d37f6):1912
    'Call.args>BinOp(left=List,op=Add,right=Name)',  # test_a1_identity_formation:2469
    'Call.args>BinOp(left=Name,op=Add,right=Constant)',  # closed_walk:1226
    'Call.args>BinOp(left=Name,op=Add,right=Name)',  # test_a1_identity_formation:2451
    'Call.args>BinOp(left=Name,op=Add,right=Tuple)',  # test_a1_identity_formation:1262
    'Call.args>BinOp(left=Name,op=BitAnd,right=Name)',  # closed_walk:1242
    'Call.args>BinOp(left=Name,op=Sub,right=Constant)',  # test_a1_identity_formation:3204
    'Call.args>BinOp(left=Name,op=Sub,right=Name)',  # test_a1_identity_formation:1511
    'Call.args>BinOp(left=Name,op=Sub,right=Set)',  # test_a1_identity_formation:2297
    'Call.args>BoolOp(op=Or,values=[Attribute])',  # test_a1_identity_formation:3824
    'Call.args>BoolOp(op=Or,values=[Call|List])',  # closed_walk:1157
    'Call.args>BoolOp(op=Or,values=[Call|Name])',  # closed_walk:662
    'Call.args>BoolOp(op=Or,values=[Call|Subscript])',  # test_match_hold_admission_gate_pg (a30d37f6):255
    'Call.args>BoolOp(op=Or,values=[Dict|Name])',  # test_a1_identity_formation:75
    'Call.args>BoolOp(op=Or,values=[Name|Subscript])',  # test_match_hold_admission_gate_pg (a30d37f6):275
    'Call.args>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:755
    'Call.args>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:765
    'Call.args>Call(func=Attribute,args=[BinOp],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1912
    'Call.args>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:1869
    'Call.args>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:3864
    'Call.args>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # test_a1_identity_formation:4515
    'Call.args>Call(func=Attribute,args=[List|Name],keywords=[])',  # closed_walk:984
    'Call.args>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:141
    'Call.args>Call(func=Attribute,args=[Name|Tuple],keywords=[])',  # closed_walk:494
    'Call.args>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:4330
    'Call.args>Call(func=Attribute,args=[Tuple],keywords=[keyword])',  # test_a1_identity_formation:724
    'Call.args>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:874
    'Call.args>Call(func=Attribute,args=[],keywords=[keyword])',  # test_a1_identity_formation:1290
    'Call.args>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1570
    'Call.args>Call(func=Name,args=[Attribute|BinOp],keywords=[])',  # test_a1_identity_formation:3232
    'Call.args>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',  # test_a1_identity_formation:3671
    'Call.args>Call(func=Name,args=[Attribute|GeneratorExp],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):653
    'Call.args>Call(func=Name,args=[Attribute|ListComp],keywords=[])',  # closed_walk:1967
    'Call.args>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1820
    'Call.args>Call(func=Name,args=[Attribute|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):1249
    'Call.args>Call(func=Name,args=[BinOp],keywords=[])',  # closed_walk:1242
    'Call.args>Call(func=Name,args=[BinOp|Name],keywords=[])',  # closed_walk:1220
    'Call.args>Call(func=Name,args=[BoolOp],keywords=[])',  # test_a1_identity_formation:90
    'Call.args>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:874
    'Call.args>Call(func=Name,args=[Call|Constant],keywords=[])',  # test_a1_identity_formation:1218
    'Call.args>Call(func=Name,args=[Call|Dict],keywords=[])',  # test_a1_identity_formation:1218
    'Call.args>Call(func=Name,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:2940
    'Call.args>Call(func=Name,args=[Constant],keywords=[])',  # test_a1_identity_formation:1562
    'Call.args>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:1515
    'Call.args>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:133
    'Call.args>Call(func=Name,args=[Set],keywords=[])',  # test_a1_identity_formation:1256
    'Call.args>Call(func=Name,args=[Subscript],keywords=[])',  # test_a1_identity_formation:922
    'Call.args>Call(func=Name,args=[],keywords=[])',  # test_a1_identity_formation:2932
    'Call.args>Constant(value=NoneType)',  # closed_walk:187
    'Call.args>Constant(value=bool)',  # closed_walk:1153
    'Call.args>Constant(value=int)',  # closed_walk:135
    'Call.args>Constant(value=str)',  # closed_walk:135
    'Call.args>Dict(keys=[Constant],values=[Attribute])',  # test_a1_identity_formation:3454
    'Call.args>Dict(keys=[Constant],values=[Dict|Name])',  # test_a1_identity_formation:1219
    'Call.args>Dict(keys=[NoneType],values=[Name])',  # test_a1_identity_formation:1438
    'Call.args>Dict(keys=[],values=[])',  # test_a1_identity_formation:725
    'Call.args>DictComp(key=Attribute,value=Name,generators=[comprehension])',  # closed_walk:1969
    'Call.args>DictComp(key=Name,value=Name,generators=[comprehension])',  # test_a1_identity_formation:4475
    'Call.args>GeneratorExp(elt=Attribute,generators=[comprehension])',  # closed_walk:952
    'Call.args>GeneratorExp(elt=BinOp,generators=[comprehension])',  # test_a1_identity_formation:4515
    'Call.args>GeneratorExp(elt=BoolOp,generators=[comprehension])',  # closed_walk:871
    'Call.args>GeneratorExp(elt=Call,generators=[comprehension])',  # closed_walk:919
    'Call.args>GeneratorExp(elt=Compare,generators=[comprehension])',  # closed_walk:127
    'Call.args>GeneratorExp(elt=Constant,generators=[comprehension])',  # closed_walk:174
    'Call.args>GeneratorExp(elt=JoinedStr,generators=[comprehension])',  # test_a1_identity_formation:1109
    'Call.args>GeneratorExp(elt=Name,generators=[comprehension])',  # closed_walk:498
    'Call.args>GeneratorExp(elt=Subscript,generators=[comprehension])',  # closed_walk:683
    'Call.args>GeneratorExp(elt=Tuple,generators=[comprehension])',  # closed_walk:73
    'Call.args>GeneratorExp(elt=UnaryOp,generators=[comprehension])',  # test_a1_identity_formation:1209
    'Call.args>IfExp(test=Call,body=Attribute,orelse=Name)',  # test_a1_identity_formation:1233
    'Call.args>IfExp(test=Call,body=Name,orelse=Constant)',  # closed_walk:1298
    'Call.args>IfExp(test=Call,body=Tuple,orelse=Tuple)',  # closed_walk:1434
    'Call.args>IfExp(test=Compare,body=JoinedStr,orelse=Constant)',  # closed_walk:1745
    'Call.args>IfExp(test=Compare,body=Name,orelse=Name)',  # test_a1_identity_formation:1498
    'Call.args>IfExp(test=Compare,body=Tuple,orelse=Tuple)',  # closed_walk:1437
    'Call.args>IfExp(test=Name,body=Constant,orelse=Constant)',  # closed_walk:1995
    'Call.args>IfExp(test=Name,body=List,orelse=List)',  # test_a1_identity_formation:99
    'Call.args>IfExp(test=Name,body=Name,orelse=BinOp)',  # test_a1_identity_formation:4486
    'Call.args>JoinedStr(values=[Constant|FormattedValue])',  # closed_walk:139
    'Call.args>Lambda(args=arguments,body=Call)',  # closed_walk:1767
    'Call.args>List(elts=[Attribute],ctx=Load)',  # closed_walk:853
    'Call.args>List(elts=[BinOp|Constant],ctx=Load)',  # test_a1_identity_formation:4584
    'Call.args>List(elts=[Call],ctx=Load)',  # closed_walk:847
    'Call.args>List(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:4568
    'Call.args>List(elts=[Name],ctx=Load)',  # closed_walk:917
    'Call.args>List(elts=[],ctx=Load)',  # closed_walk:445
    'Call.args>ListComp(elt=Attribute,generators=[comprehension])',  # closed_walk:1967
    'Call.args>Name(id=str,ctx=Load)',  # closed_walk:71
    'Call.args>Set(elts=[Call])',  # test_a1_identity_formation:2292
    'Call.args>Set(elts=[Name])',  # test_a1_identity_formation:1256
    'Call.args>SetComp(elt=Tuple,generators=[comprehension])',  # test_a1_identity_formation:1108
    'Call.args>Starred(value=Call,ctx=Load)',  # closed_walk:784
    'Call.args>Starred(value=GeneratorExp,ctx=Load)',  # test_a1_identity_formation:4399
    'Call.args>Starred(value=ListComp,ctx=Load)',  # test_a1_identity_formation:1166
    'Call.args>Starred(value=Name,ctx=Load)',  # closed_walk:1064
    'Call.args>Subscript(value=Attribute,slice=BinOp,ctx=Load)',  # test_a1_identity_formation:1428
    'Call.args>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:901
    'Call.args>Subscript(value=Attribute,slice=Name,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):586
    'Call.args>Subscript(value=Attribute,slice=Slice,ctx=Load)',  # closed_walk:1504
    'Call.args>Subscript(value=Attribute,slice=UnaryOp,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):822
    'Call.args>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:461
    'Call.args>Subscript(value=Name,slice=Attribute,ctx=Load)',  # closed_walk:865
    'Call.args>Subscript(value=Name,slice=BinOp,ctx=Load)',  # test_a1_identity_formation:2280
    'Call.args>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:787
    'Call.args>Subscript(value=Name,slice=Name,ctx=Load)',  # closed_walk:1059
    'Call.args>Subscript(value=Name,slice=Slice,ctx=Load)',  # closed_walk:1186
    'Call.args>Subscript(value=Name,slice=UnaryOp,ctx=Load)',  # test_a1_identity_formation:2274
    'Call.args>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:1517
    'Call.args>Subscript(value=Tuple,slice=Name,ctx=Load)',  # test_a1_identity_formation:4535
    'Call.args>Tuple(elts=[Attribute],ctx=Load)',  # closed_walk:311
    'Call.args>Tuple(elts=[Attribute|Call|Constant|Name],ctx=Load)',  # test_a1_identity_formation:1261
    'Call.args>Tuple(elts=[Attribute|Call|Constant|Subscript],ctx=Load)',  # test_a1_identity_formation:1269
    'Call.args>Tuple(elts=[Attribute|Call|Name],ctx=Load)',  # test_a1_identity_formation:1297
    'Call.args>Tuple(elts=[Attribute|Constant],ctx=Load)',  # closed_walk:1079
    'Call.args>Tuple(elts=[Attribute|JoinedStr],ctx=Load)',  # test_a1_identity_formation:1143
    'Call.args>Tuple(elts=[Attribute|Name],ctx=Load)',  # test_a1_identity_formation:1299
    'Call.args>Tuple(elts=[Attribute|Subscript],ctx=Load)',  # closed_walk:975
    'Call.args>Tuple(elts=[BinOp|Constant],ctx=Load)',  # closed_walk:1241
    'Call.args>Tuple(elts=[BinOp|Name],ctx=Load)',  # test_a1_identity_formation:3255
    'Call.args>Tuple(elts=[BoolOp|Subscript],ctx=Load)',  # test_a1_identity_formation:1069
    'Call.args>Tuple(elts=[Call],ctx=Load)',  # closed_walk:915
    'Call.args>Tuple(elts=[Call|Constant],ctx=Load)',  # closed_walk:1765
    'Call.args>Tuple(elts=[Call|Constant|Subscript],ctx=Load)',  # test_a1_identity_formation:119
    'Call.args>Tuple(elts=[Call|JoinedStr],ctx=Load)',  # closed_walk:287
    'Call.args>Tuple(elts=[Call|Name],ctx=Load)',  # closed_walk:1510
    'Call.args>Tuple(elts=[Compare|Name],ctx=Load)',  # closed_walk:1237
    'Call.args>Tuple(elts=[Constant],ctx=Load)',  # closed_walk:1185
    'Call.args>Tuple(elts=[Constant|JoinedStr],ctx=Load)',  # closed_walk:1183
    'Call.args>Tuple(elts=[Constant|JoinedStr|Name],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):313
    'Call.args>Tuple(elts=[Constant|List],ctx=Load)',  # test_a1_identity_formation:4405
    'Call.args>Tuple(elts=[Constant|Name],ctx=Load)',  # closed_walk:1509
    'Call.args>Tuple(elts=[Constant|Name|Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):317
    'Call.args>Tuple(elts=[IfExp|JoinedStr],ctx=Load)',  # closed_walk:1831
    'Call.args>Tuple(elts=[JoinedStr|List],ctx=Load)',  # test_a1_identity_formation:4395
    'Call.args>Tuple(elts=[JoinedStr|Name],ctx=Load)',  # closed_walk:147
    'Call.args>Tuple(elts=[JoinedStr|Subscript],ctx=Load)',  # closed_walk:1828
    'Call.args>Tuple(elts=[Name],ctx=Load)',  # closed_walk:445
    'Call.args>Tuple(elts=[Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):1210
    'Call.args>Tuple(elts=[],ctx=Load)',  # closed_walk:494
    'Call.args>UnaryOp(op=USub,operand=Constant)',  # test_a1_identity_formation:3204
    "Call.func>Attribute(value=Attribute,attr='add',ctx=Load)",  # closed_walk:635
    "Call.func>Attribute(value=Attribute,attr='admit',ctx=Load)",  # closed_walk:1013
    "Call.func>Attribute(value=Attribute,attr='append',ctx=Load)",  # closed_walk:1607
    "Call.func>Attribute(value=Attribute,attr='basename',ctx=Load)",  # closed_walk:167
    "Call.func>Attribute(value=Attribute,attr='callee',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):253
    "Call.func>Attribute(value=Attribute,attr='discard',ctx=Load)",  # closed_walk:1891
    "Call.func>Attribute(value=Attribute,attr='get',ctx=Load)",  # closed_walk:133
    "Call.func>Attribute(value=Attribute,attr='helper_hook',ctx=Load)",  # closed_walk:1818
    "Call.func>Attribute(value=Attribute,attr='insert',ctx=Load)",  # test_a1_identity_formation:4534
    "Call.func>Attribute(value=Attribute,attr='is_param',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):592
    "Call.func>Attribute(value=Attribute,attr='is_root',ctx=Load)",  # closed_walk:1565
    "Call.func>Attribute(value=Attribute,attr='is_session',ctx=Load)",  # closed_walk:1560
    "Call.func>Attribute(value=Attribute,attr='items',ctx=Load)",  # closed_walk:498
    "Call.func>Attribute(value=Attribute,attr='lower',ctx=Load)",  # closed_walk:2049
    "Call.func>Attribute(value=Attribute,attr='module_accessor',ctx=Load)",  # closed_walk:1657
    "Call.func>Attribute(value=Attribute,attr='named',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):533
    "Call.func>Attribute(value=Attribute,attr='resolve',ctx=Load)",  # closed_walk:1515
    "Call.func>Attribute(value=Attribute,attr='same',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):816
    "Call.func>Attribute(value=Attribute,attr='session_argument',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):273
    "Call.func>Attribute(value=Attribute,attr='session_root_ok',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):272
    "Call.func>Attribute(value=Attribute,attr='session_value',ctx=Load)",  # closed_walk:1535
    "Call.func>Attribute(value=Attribute,attr='setdefault',ctx=Load)",  # closed_walk:139
    "Call.func>Attribute(value=Attribute,attr='spelled_once',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):658
    "Call.func>Attribute(value=Attribute,attr='update',ctx=Load)",  # closed_walk:125
    "Call.func>Attribute(value=Await,attr='scalar',ctx=Load)",  # test_a1_identity_formation:1562
    "Call.func>Attribute(value=BoolOp,attr='callee',ctx=Load)",  # closed_walk:1337
    "Call.func>Attribute(value=BoolOp,attr='execute_kind',ctx=Load)",  # closed_walk:1328
    "Call.func>Attribute(value=BoolOp,attr='split',ctx=Load)",  # closed_walk:461
    "Call.func>Attribute(value=Call,attr='__init__',ctx=Load)",  # test_a1_identity_formation:3443
    "Call.func>Attribute(value=Call,attr='accept',ctx=Load)",  # closed_walk:1842
    "Call.func>Attribute(value=Call,attr='append',ctx=Load)",  # closed_walk:445
    "Call.func>Attribute(value=Call,attr='bound',ctx=Load)",  # closed_walk:355
    "Call.func>Attribute(value=Call,attr='execute',ctx=Load)",  # test_a1_identity_formation:3457
    "Call.func>Attribute(value=Call,attr='guards',ctx=Load)",  # closed_walk:1298
    "Call.func>Attribute(value=Call,attr='is_session',ctx=Load)",  # closed_walk:1315
    "Call.func>Attribute(value=Call,attr='items',ctx=Load)",  # closed_walk:138
    "Call.func>Attribute(value=Call,attr='join',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1046
    "Call.func>Attribute(value=Call,attr='local_sql',ctx=Load)",  # closed_walk:1308
    "Call.func>Attribute(value=Call,attr='new_event_loop',ctx=Load)",  # test_a1_identity_formation:128
    "Call.func>Attribute(value=Call,attr='read',ctx=Load)",  # test_a1_identity_formation:2924
    "Call.func>Attribute(value=Call,attr='resolve',ctx=Load)",  # test_a1_identity_formation:3861
    "Call.func>Attribute(value=Call,attr='run_until_complete',ctx=Load)",  # test_a1_identity_formation:128
    "Call.func>Attribute(value=Call,attr='split',ctx=Load)",  # closed_walk:719
    "Call.func>Attribute(value=Call,attr='sql_texts',ctx=Load)",  # closed_walk:1275
    "Call.func>Attribute(value=Call,attr='startswith',ctx=Load)",  # test_a1_identity_formation:2941
    "Call.func>Attribute(value=Call,attr='union',ctx=Load)",  # test_a1_identity_formation:1166
    "Call.func>Attribute(value=Call,attr='visit',ctx=Load)",  # test_a1_identity_formation:2828
    "Call.func>Attribute(value=Constant,attr='join',ctx=Load)",  # closed_walk:575
    "Call.func>Attribute(value=Name,attr='Bindings',ctx=Load)",  # test_a1_identity_formation:536
    "Call.func>Attribute(value=Name,attr='Counter',ctx=Load)",  # closed_walk:1397
    "Call.func>Attribute(value=Name,attr='Expression',ctx=Load)",  # test_a1_identity_formation:1218
    "Call.func>Attribute(value=Name,attr='Grammar',ctx=Load)",  # test_a1_identity_formation:617
    "Call.func>Attribute(value=Name,attr='Load',ctx=Load)",  # test_a1_identity_formation:1290
    "Call.func>Attribute(value=Name,attr='ModuleType',ctx=Load)",  # test_a1_identity_formation:3665
    "Call.func>Attribute(value=Name,attr='Name',ctx=Load)",  # test_a1_identity_formation:2218
    "Call.func>Attribute(value=Name,attr='Path',ctx=Load)",  # test_a1_identity_formation:3861
    "Call.func>Attribute(value=Name,attr='Policy',ctx=Load)",  # test_a1_identity_formation:701
    "Call.func>Attribute(value=Name,attr='SimpleNamespace',ctx=Load)",  # closed_walk:1909
    "Call.func>Attribute(value=Name,attr='Tuple',ctx=Load)",  # test_a1_identity_formation:1290
    "Call.func>Attribute(value=Name,attr='Visitor',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):290
    "Call.func>Attribute(value=Name,attr='__setattr__',ctx=Load)",  # closed_walk:1365
    "Call.func>Attribute(value=Name,attr='__subclasses__',ctx=Load)",  # closed_walk:271
    "Call.func>Attribute(value=Name,attr='_add',ctx=Load)",  # closed_walk:435
    "Call.func>Attribute(value=Name,attr='_builder_domain_texts',ctx=Load)",  # closed_walk:1025
    "Call.func>Attribute(value=Name,attr='_check',ctx=Load)",  # closed_walk:1536
    "Call.func>Attribute(value=Name,attr='_collect',ctx=Load)",  # closed_walk:442
    "Call.func>Attribute(value=Name,attr='_formatted',ctx=Load)",  # closed_walk:857
    "Call.func>Attribute(value=Name,attr='_guarded',ctx=Load)",  # test_a1_identity_formation:2814
    "Call.func>Attribute(value=Name,attr='_helper_args',ctx=Load)",  # closed_walk:1652
    "Call.func>Attribute(value=Name,attr='_helper_tree',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):358
    "Call.func>Attribute(value=Name,attr='_module_object',ctx=Load)",  # closed_walk:588
    "Call.func>Attribute(value=Name,attr='_module_or_enumerated',ctx=Load)",  # closed_walk:653
    "Call.func>Attribute(value=Name,attr='_plain_args',ctx=Load)",  # closed_walk:1628
    "Call.func>Attribute(value=Name,attr='_pure',ctx=Load)",  # closed_walk:1639
    "Call.func>Attribute(value=Name,attr='_resolve',ctx=Load)",  # closed_walk:1622
    "Call.func>Attribute(value=Name,attr='_sessions',ctx=Load)",  # closed_walk:683
    "Call.func>Attribute(value=Name,attr='_spelled',ctx=Load)",  # closed_walk:1538
    "Call.func>Attribute(value=Name,attr='accept',ctx=Load)",  # closed_walk:1979
    "Call.func>Attribute(value=Name,attr='add',ctx=Load)",  # closed_walk:275
    "Call.func>Attribute(value=Name,attr='admit',ctx=Load)",  # closed_walk:784
    "Call.func>Attribute(value=Name,attr='append',ctx=Load)",  # closed_walk:853
    "Call.func>Attribute(value=Name,attr='awaited',ctx=Load)",  # closed_walk:1598
    "Call.func>Attribute(value=Name,attr='binding_refusals',ctx=Load)",  # closed_walk:150
    "Call.func>Attribute(value=Name,attr='bindings',ctx=Load)",  # closed_walk:174
    "Call.func>Attribute(value=Name,attr='builder_texts',ctx=Load)",  # closed_walk:1096
    "Call.func>Attribute(value=Name,attr='call',ctx=Load)",  # closed_walk:1595
    "Call.func>Attribute(value=Name,attr='call_arguments',ctx=Load)",  # test_a1_identity_formation:1054
    "Call.func>Attribute(value=Name,attr='callee',ctx=Load)",  # closed_walk:709
    "Call.func>Attribute(value=Name,attr='census',ctx=Load)",  # test_a1_identity_formation:4333
    "Call.func>Attribute(value=Name,attr='check',ctx=Load)",  # closed_walk:144
    "Call.func>Attribute(value=Name,attr='clear',ctx=Load)",  # test_a1_identity_formation:1440
    "Call.func>Attribute(value=Name,attr='commit',ctx=Load)",  # test_a1_identity_formation:1574
    "Call.func>Attribute(value=Name,attr='compile',ctx=Load)",  # test_a1_identity_formation:3035
    "Call.func>Attribute(value=Name,attr='count',ctx=Load)",  # closed_walk:700
    "Call.func>Attribute(value=Name,attr='dedent',ctx=Load)",  # closed_walk:1869
    "Call.func>Attribute(value=Name,attr='def_effects',ctx=Load)",  # test_a1_identity_formation:2194
    "Call.func>Attribute(value=Name,attr='dump',ctx=Load)",  # test_a1_identity_formation:2817
    "Call.func>Attribute(value=Name,attr='escape',ctx=Load)",  # test_a1_identity_formation:3035
    "Call.func>Attribute(value=Name,attr='every_binding',ctx=Load)",  # test_a1_identity_formation:895
    "Call.func>Attribute(value=Name,attr='execute',ctx=Load)",  # test_a1_identity_formation:1562
    "Call.func>Attribute(value=Name,attr='execute_kind',ctx=Load)",  # test_a1_identity_formation:742
    "Call.func>Attribute(value=Name,attr='expr_effects',ctx=Load)",  # test_a1_identity_formation:755
    "Call.func>Attribute(value=Name,attr='extend',ctx=Load)",  # closed_walk:73
    "Call.func>Attribute(value=Name,attr='fail',ctx=Load)",  # closed_walk:1501
    "Call.func>Attribute(value=Name,attr='fail_at',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):242
    "Call.func>Attribute(value=Name,attr='find',ctx=Load)",  # test_a1_identity_formation:1791
    "Call.func>Attribute(value=Name,attr='findall',ctx=Load)",  # test_a1_identity_formation:2976
    "Call.func>Attribute(value=Name,attr='finditer',ctx=Load)",  # test_a1_identity_formation:470
    "Call.func>Attribute(value=Name,attr='format',ctx=Load)",  # closed_walk:962
    "Call.func>Attribute(value=Name,attr='fullmatch',ctx=Load)",  # closed_walk:872
    "Call.func>Attribute(value=Name,attr='generic_visit',ctx=Load)",  # test_a1_identity_formation:2810
    "Call.func>Attribute(value=Name,attr='get',ctx=Load)",  # closed_walk:285
    "Call.func>Attribute(value=Name,attr='get_event_loop_policy',ctx=Load)",  # test_a1_identity_formation:128
    "Call.func>Attribute(value=Name,attr='getmodule',ctx=Load)",  # closed_walk:1014
    "Call.func>Attribute(value=Name,attr='getsource',ctx=Load)",  # closed_walk:191
    "Call.func>Attribute(value=Name,attr='getsourcefile',ctx=Load)",  # closed_walk:164
    "Call.func>Attribute(value=Name,attr='glob',ctx=Load)",  # test_a1_identity_formation:3864
    "Call.func>Attribute(value=Name,attr='group',ctx=Load)",  # test_a1_identity_formation:119
    "Call.func>Attribute(value=Name,attr='guards',ctx=Load)",  # closed_walk:1931
    "Call.func>Attribute(value=Name,attr='helper_effects',ctx=Load)",  # test_a1_identity_formation:747
    "Call.func>Attribute(value=Name,attr='index',ctx=Load)",  # closed_walk:1859
    "Call.func>Attribute(value=Name,attr='is_db_call',ctx=Load)",  # test_a1_identity_formation:738
    "Call.func>Attribute(value=Name,attr='is_param',ctx=Load)",  # closed_walk:700
    "Call.func>Attribute(value=Name,attr='is_session',ctx=Load)",  # closed_walk:692
    "Call.func>Attribute(value=Name,attr='iscoroutinefunction',ctx=Load)",  # closed_walk:1009
    "Call.func>Attribute(value=Name,attr='isfunction',ctx=Load)",  # closed_walk:769
    "Call.func>Attribute(value=Name,attr='items',ctx=Load)",  # closed_walk:920
    "Call.func>Attribute(value=Name,attr='iter_child_nodes',ctx=Load)",  # closed_walk:1132
    "Call.func>Attribute(value=Name,attr='join',ctx=Load)",  # test_a1_identity_formation:2371
    "Call.func>Attribute(value=Name,attr='literal_eval',ctx=Load)",  # test_a1_identity_formation:1160
    "Call.func>Attribute(value=Name,attr='local_sql',ctx=Load)",  # closed_walk:1932
    "Call.func>Attribute(value=Name,attr='lru_cache',ctx=Load)",  # test_a1_identity_formation:2922
    "Call.func>Attribute(value=Name,attr='lstrip',ctx=Load)",  # test_a1_identity_formation:3245
    "Call.func>Attribute(value=Name,attr='match',ctx=Load)",  # test_a1_identity_formation:117
    "Call.func>Attribute(value=Name,attr='module',ctx=Load)",  # closed_walk:760
    "Call.func>Attribute(value=Name,attr='open',ctx=Load)",  # test_a1_identity_formation:2924
    "Call.func>Attribute(value=Name,attr='parse',ctx=Load)",  # closed_walk:191
    "Call.func>Attribute(value=Name,attr='plain_effects',ctx=Load)",  # test_a1_identity_formation:4402
    "Call.func>Attribute(value=Name,attr='pop',ctx=Load)",  # closed_walk:270
    "Call.func>Attribute(value=Name,attr='read_text',ctx=Load)",  # test_a1_identity_formation:3865
    "Call.func>Attribute(value=Name,attr='reads',ctx=Load)",  # test_a1_identity_formation:897
    "Call.func>Attribute(value=Name,attr='refusals',ctx=Load)",  # test_a1_identity_formation:4727
    "Call.func>Attribute(value=Name,attr='replace',ctx=Load)",  # test_a1_identity_formation:2448
    "Call.func>Attribute(value=Name,attr='resolve',ctx=Load)",  # closed_walk:516
    "Call.func>Attribute(value=Name,attr='resolver_methods',ctx=Load)",  # test_a1_identity_formation:4330
    "Call.func>Attribute(value=Name,attr='roots',ctx=Load)",  # closed_walk:474
    "Call.func>Attribute(value=Name,attr='same',ctx=Load)",  # test_a1_identity_formation:852
    "Call.func>Attribute(value=Name,attr='search',ctx=Load)",  # test_a1_identity_formation:2965
    "Call.func>Attribute(value=Name,attr='session_argument',ctx=Load)",  # test_a1_identity_formation:1062
    "Call.func>Attribute(value=Name,attr='session_root_ok',ctx=Load)",  # test_a1_identity_formation:1061
    "Call.func>Attribute(value=Name,attr='session_value',ctx=Load)",  # test_a1_identity_formation:1058
    "Call.func>Attribute(value=Name,attr='setattr',ctx=Load)",  # test_a1_identity_formation:723
    "Call.func>Attribute(value=Name,attr='setdefault',ctx=Load)",  # closed_walk:915
    "Call.func>Attribute(value=Name,attr='shape',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):309
    "Call.func>Attribute(value=Name,attr='shapes',ctx=Load)",  # closed_walk:123
    "Call.func>Attribute(value=Name,attr='signature',ctx=Load)",  # closed_walk:723
    "Call.func>Attribute(value=Name,attr='sort',ctx=Load)",  # test_a1_identity_formation:476
    "Call.func>Attribute(value=Name,attr='source_of',ctx=Load)",  # test_a1_identity_formation:635
    "Call.func>Attribute(value=Name,attr='spelled',ctx=Load)",  # closed_walk:561
    "Call.func>Attribute(value=Name,attr='spelled_in',ctx=Load)",  # test_a1_identity_formation:2232
    "Call.func>Attribute(value=Name,attr='spelled_once',ctx=Load)",  # closed_walk:611
    "Call.func>Attribute(value=Name,attr='split',ctx=Load)",  # closed_walk:683
    "Call.func>Attribute(value=Name,attr='splitlines',ctx=Load)",  # test_a1_identity_formation:3668
    "Call.func>Attribute(value=Name,attr='sql_kind',ctx=Load)",  # test_a1_identity_formation:730
    "Call.func>Attribute(value=Name,attr='sql_texts',ctx=Load)",  # closed_walk:847
    "Call.func>Attribute(value=Name,attr='start',ctx=Load)",  # test_a1_identity_formation:471
    "Call.func>Attribute(value=Name,attr='startswith',ctx=Load)",  # closed_walk:1507
    "Call.func>Attribute(value=Name,attr='statement_ok',ctx=Load)",  # closed_walk:818
    "Call.func>Attribute(value=Name,attr='stores',ctx=Load)",  # test_a1_identity_formation:1155
    "Call.func>Attribute(value=Name,attr='text',ctx=Load)",  # test_a1_identity_formation:904
    "Call.func>Attribute(value=Name,attr='unparse',ctx=Load)",  # closed_walk:583
    "Call.func>Attribute(value=Name,attr='unwrap',ctx=Load)",  # closed_walk:768
    "Call.func>Attribute(value=Name,attr='update',ctx=Load)",  # closed_walk:919
    "Call.func>Attribute(value=Name,attr='upper',ctx=Load)",  # closed_walk:1210
    "Call.func>Attribute(value=Name,attr='values',ctx=Load)",  # closed_walk:873
    "Call.func>Attribute(value=Name,attr='visit',ctx=Load)",  # closed_walk:141
    "Call.func>Attribute(value=Name,attr='walk',ctx=Load)",  # closed_walk:71
    "Call.func>Attribute(value=Subscript,attr='count',ctx=Load)",  # test_a1_identity_formation:486
    "Call.func>Attribute(value=Subscript,attr='items',ctx=Load)",  # test_a1_identity_formation:1321
    "Call.func>Attribute(value=Subscript,attr='lstrip',ctx=Load)",  # test_a1_identity_formation:2941
    "Call.func>Attribute(value=Subscript,attr='upper',ctx=Load)",  # closed_walk:1189
    "Call.func>Attribute(value=Subscript,attr='values',ctx=Load)",  # test_a1_identity_formation:48
    'Call.func>Call(func=Name,args=[Constant|Dict|Tuple],keywords=[])',  # test_a1_identity_formation:3453
    'Call.func>Name(id=str,ctx=Load)',  # closed_walk:72
    "Call.keywords>keyword(arg='__name__',value=Name)",  # closed_walk:1909
    "Call.keywords>keyword(arg='barrier',value=Tuple)",  # test_a1_identity_formation:2457
    "Call.keywords>keyword(arg='bindings',value=Attribute)",  # test_match_hold_admission_gate_pg (a30d37f6):290
    "Call.keywords>keyword(arg='bindings',value=Name)",  # closed_walk:1843
    "Call.keywords>keyword(arg='classes',value=Tuple)",  # test_a1_identity_formation:4602
    "Call.keywords>keyword(arg='ctx',value=Call)",  # test_a1_identity_formation:1290
    "Call.keywords>keyword(arg='elts',value=Name)",  # test_a1_identity_formation:1290
    "Call.keywords>keyword(arg='encoding',value=Constant)",  # test_a1_identity_formation:2925
    "Call.keywords>keyword(arg='ends',value=Call)",  # test_a1_identity_formation:2292
    "Call.keywords>keyword(arg='fn',value=Call)",  # test_match_hold_admission_gate_pg (a30d37f6):358
    "Call.keywords>keyword(arg='fn',value=Name)",  # test_match_hold_admission_gate_pg (a30d37f6):591
    "Call.keywords>keyword(arg='grammar',value=Attribute)",  # closed_walk:1015
    "Call.keywords>keyword(arg='grammar',value=Call)",  # closed_walk:1458
    "Call.keywords>keyword(arg='grammar',value=Name)",  # test_a1_identity_formation:2177
    "Call.keywords>keyword(arg='id',value=Name)",  # test_a1_identity_formation:2218
    "Call.keywords>keyword(arg='key',value=Attribute)",  # test_a1_identity_formation:135
    "Call.keywords>keyword(arg='key',value=Lambda)",  # test_a1_identity_formation:898
    "Call.keywords>keyword(arg='key',value=Name)",  # closed_walk:1059
    "Call.keywords>keyword(arg='maxsize',value=Constant)",  # test_a1_identity_formation:2922
    "Call.keywords>keyword(arg='newline',value=Constant)",  # test_a1_identity_formation:2925
    "Call.keywords>keyword(arg='opaque',value=Dict)",  # test_a1_identity_formation:2196
    "Call.keywords>keyword(arg='opaque',value=Name)",  # closed_walk:1842
    "Call.keywords>keyword(arg='permitted',value=Name)",  # test_match_hold_admission_gate_pg (a30d37f6):290
    "Call.keywords>keyword(arg='plain_only',value=Constant)",  # test_match_hold_admission_gate_pg (a30d37f6):277
    "Call.keywords>keyword(arg='record',value=Constant)",  # test_a1_identity_formation:724
    "Call.keywords>keyword(arg='replace',value=Constant)",  # test_a1_identity_formation:4546
    "Call.keywords>keyword(arg='rollbacks',value=Constant)",  # test_match_hold_admission_gate_pg (a30d37f6):550
    "Call.keywords>keyword(arg='scope',value=Name)",  # test_a1_identity_formation:1486
    "Call.keywords>keyword(arg='session',value=Attribute)",  # closed_walk:1014
    "Call.keywords>keyword(arg='session',value=Name)",  # closed_walk:1315
    "Call.keywords>keyword(arg='source',value=Call)",  # closed_walk:1889
    "Call.keywords>keyword(arg='spend',value=Tuple)",  # test_a1_identity_formation:2483
    "Call.keywords>keyword(arg='stmts',value=Call)",  # closed_walk:1309
    "Call.keywords>keyword(arg='stmts',value=IfExp)",  # test_match_hold_admission_gate_pg (a30d37f6):233
    "Call.keywords>keyword(arg='stmts',value=Name)",  # closed_walk:360
    "Call.keywords>keyword(arg='top',value=Constant)",  # test_match_hold_admission_gate_pg (a30d37f6):361
    "Call.keywords>keyword(arg='what',value=Constant)",  # test_match_hold_admission_gate_pg (a30d37f6):490
    "Call.keywords>keyword(arg='what',value=Name)",  # test_match_hold_admission_gate_pg (a30d37f6):277
    'Call.keywords>keyword(arg=None,value=Dict)',  # closed_walk:960
    'Call.keywords>keyword(arg=None,value=Name)',  # closed_walk:962
    "ClassDef.bases>Attribute(value=Name,attr='NodeVisitor',ctx=Load)",  # test_a1_identity_formation:2804
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[Assign],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2805
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2822
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[AugAssign|Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2808
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[Expr],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2813
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:2816
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3675
    "Compare.comparators>Attribute(value=Attribute,attr='pure_methods',ctx=Load)",  # closed_walk:1708
    "Compare.comparators>Attribute(value=Name,attr='AST',ctx=Load)",  # closed_walk:274
    "Compare.comparators>Attribute(value=Name,attr='_enumerated',ctx=Load)",  # closed_walk:639
    "Compare.comparators>Attribute(value=Name,attr='_reads',ctx=Load)",  # test_a1_identity_formation:1590
    "Compare.comparators>Attribute(value=Name,attr='_walked_nodes',ctx=Load)",  # closed_walk:1500
    "Compare.comparators>Attribute(value=Name,attr='caught',ctx=Load)",  # closed_walk:1822
    "Compare.comparators>Attribute(value=Name,attr='fail_on',ctx=Load)",  # test_a1_identity_formation:3452
    "Compare.comparators>Attribute(value=Name,attr='gate_kinds',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):342
    "Compare.comparators>Attribute(value=Name,attr='helpers',ctx=Load)",  # closed_walk:1880
    "Compare.comparators>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:549
    "Compare.comparators>Attribute(value=Name,attr='namedtuples',ctx=Load)",  # closed_walk:127
    "Compare.comparators>Attribute(value=Name,attr='permitted',ctx=Load)",  # closed_walk:1744
    "Compare.comparators>Attribute(value=Name,attr='syntax',ctx=Load)",  # closed_walk:1235
    "Compare.comparators>Attribute(value=Name,attr='walked_defs',ctx=Load)",  # closed_walk:1623
    "Compare.comparators>Attribute(value=Name,attr='walking',ctx=Load)",  # closed_walk:1882
    "Compare.comparators>Attribute(value=Subscript,attr='empty',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):704
    "Compare.comparators>Attribute(value=Subscript,attr='name',ctx=Load)",  # closed_walk:791
    'Compare.comparators>BinOp(left=Call,op=BitOr,right=Set)',  # test_a1_identity_formation:1209
    'Compare.comparators>BoolOp(op=Or,values=[Constant|Name])',  # test_a1_identity_formation:4336
    'Compare.comparators>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:978
    'Compare.comparators>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:474
    'Compare.comparators>Call(func=Name,args=[Attribute],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):654
    'Compare.comparators>Call(func=Name,args=[Attribute|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):667
    'Compare.comparators>Call(func=Name,args=[Call],keywords=[])',  # test_a1_identity_formation:139
    'Compare.comparators>Call(func=Name,args=[Call],keywords=[keyword])',  # test_a1_identity_formation:135
    'Compare.comparators>Call(func=Name,args=[List],keywords=[])',  # closed_walk:917
    'Compare.comparators>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:727
    'Compare.comparators>Constant(value=NoneType)',  # closed_walk:174
    'Compare.comparators>Constant(value=bool)',  # test_a1_identity_formation:1311
    'Compare.comparators>Constant(value=int)',  # closed_walk:175
    'Compare.comparators>Constant(value=str)',  # closed_walk:499
    'Compare.comparators>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:904
    'Compare.comparators>List(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:1378
    'Compare.comparators>Name(id=str,ctx=Load)',  # closed_walk:133
    'Compare.comparators>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:1187
    'Compare.comparators>Subscript(value=Name,slice=UnaryOp,ctx=Load)',  # test_a1_identity_formation:2273
    'Compare.comparators>Tuple(elts=[Attribute],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):700
    'Compare.comparators>Tuple(elts=[Constant],ctx=Load)',  # closed_walk:906
    'Compare.comparators>Tuple(elts=[Constant|JoinedStr],ctx=Load)',  # test_a1_identity_formation:920
    'Compare.comparators>Tuple(elts=[Constant|Name],ctx=Load)',  # test_a1_identity_formation:3819
    'Compare.comparators>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:3842
    'Compare.comparators>Tuple(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:1506
    'Compare.comparators>UnaryOp(op=USub,operand=Constant)',  # closed_walk:855
    "Compare.left>Attribute(value=Attribute,attr='attr',ctx=Load)",  # closed_walk:314
    "Compare.left>Attribute(value=Attribute,attr='helper_hook',ctx=Load)",  # closed_walk:1816
    "Compare.left>Attribute(value=Attribute,attr='id',ctx=Load)",  # closed_walk:791
    "Compare.left>Attribute(value=Attribute,attr='value',ctx=Load)",  # test_a1_identity_formation:811
    "Compare.left>Attribute(value=Name,attr='_lock_calls',ctx=Load)",  # test_a1_identity_formation:3452
    "Compare.left>Attribute(value=Name,attr='annotation',ctx=Load)",  # closed_walk:2086
    "Compare.left>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:1082
    "Compare.left>Attribute(value=Name,attr='attr',ctx=Load)",  # closed_walk:1557
    "Compare.left>Attribute(value=Name,attr='callee',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):75
    "Compare.left>Attribute(value=Name,attr='cause',ctx=Load)",  # closed_walk:2072
    "Compare.left>Attribute(value=Name,attr='conversion',ctx=Load)",  # closed_walk:855
    "Compare.left>Attribute(value=Name,attr='exc',ctx=Load)",  # closed_walk:2070
    "Compare.left>Attribute(value=Name,attr='format_spec',ctx=Load)",  # closed_walk:855
    "Compare.left>Attribute(value=Name,attr='grammar',ctx=Load)",  # closed_walk:547
    "Compare.left>Attribute(value=Name,attr='helper',ctx=Load)",  # closed_walk:1507
    "Compare.left>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:523
    "Compare.left>Attribute(value=Name,attr='kind',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):700
    "Compare.left>Attribute(value=Name,attr='lineno',ctx=Load)",  # test_a1_identity_formation:4419
    "Compare.left>Attribute(value=Name,attr='module',ctx=Load)",  # test_a1_identity_formation:3817
    "Compare.left>Attribute(value=Name,attr='msg',ctx=Load)",  # closed_walk:2030
    "Compare.left>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:549
    "Compare.left>Attribute(value=Name,attr='returns',ctx=Load)",  # closed_walk:2088
    "Compare.left>Attribute(value=Name,attr='type',ctx=Load)",  # closed_walk:2053
    "Compare.left>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:730
    "Compare.left>Attribute(value=Subscript,attr='asname',ctx=Load)",  # closed_walk:788
    "Compare.left>Attribute(value=Subscript,attr='default',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):704
    "Compare.left>Attribute(value=Subscript,attr='optional_vars',ctx=Load)",  # closed_walk:2062
    "Compare.left>Attribute(value=Subscript,attr='value',ctx=Load)",  # closed_walk:1989
    'Compare.left>BinOp(left=Name,op=Add,right=Constant)',  # closed_walk:1225
    'Compare.left>BinOp(left=Name,op=Sub,right=Name)',  # test_a1_identity_formation:4336
    'Compare.left>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:1044
    'Compare.left>Call(func=Attribute,args=[Attribute|BinOp],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):58
    'Compare.left>Call(func=Attribute,args=[Attribute|Call],keywords=[])',  # closed_walk:1692
    'Compare.left>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:1637
    'Compare.left>Call(func=Attribute,args=[Attribute|Name|Tuple],keywords=[])',  # closed_walk:1773
    'Compare.left>Call(func=Attribute,args=[Attribute|Tuple],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):216
    'Compare.left>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:133
    'Compare.left>Call(func=Attribute,args=[Constant],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):703
    'Compare.left>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:687
    'Compare.left>Call(func=Attribute,args=[Name|Tuple],keywords=[])',  # test_a1_identity_formation:2232
    'Compare.left>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:905
    'Compare.left>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:788
    'Compare.left>Call(func=Name,args=[Attribute|Constant],keywords=[])',  # test_a1_identity_formation:3514
    'Compare.left>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:174
    'Compare.left>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:179
    'Compare.left>Call(func=Name,args=[Name|Subscript],keywords=[])',  # test_a1_identity_formation:862
    'Compare.left>Call(func=Name,args=[Subscript],keywords=[])',  # closed_walk:1218
    'Compare.left>Constant(value=NoneType)',  # closed_walk:1097
    'Compare.left>Constant(value=str)',  # closed_walk:1104
    'Compare.left>ListComp(elt=Name,generators=[comprehension])',  # test_a1_identity_formation:1378
    'Compare.left>Name(id=str,ctx=Load)',  # closed_walk:127
    'Compare.left>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:641
    'Compare.left>Subscript(value=Name,slice=Attribute,ctx=Load)',  # closed_walk:1054
    'Compare.left>Subscript(value=Name,slice=BinOp,ctx=Load)',  # closed_walk:1225
    'Compare.left>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:1184
    'Compare.left>Subscript(value=Name,slice=Name,ctx=Load)',  # test_a1_identity_formation:1796
    'Compare.left>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:188
    'Compare.left>Subscript(value=Subscript,slice=Name,ctx=Load)',  # test_a1_identity_formation:1322
    'Compare.left>Tuple(elts=[Name],ctx=Load)',  # closed_walk:152
    'Compare.ops>Eq()',  # closed_walk:152
    'Compare.ops>Gt()',  # closed_walk:507
    'Compare.ops>GtE()',  # test_match_hold_admission_gate_pg (a30d37f6):703
    'Compare.ops>In()',  # closed_walk:127
    'Compare.ops>Is()',  # closed_walk:133
    'Compare.ops>IsNot()',  # closed_walk:274
    'Compare.ops>Lt()',  # closed_walk:727
    'Compare.ops>LtE()',  # closed_walk:986
    'Compare.ops>NotEq()',  # closed_walk:174
    'Compare.ops>NotIn()',  # closed_walk:474
    "Dict.keys>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:960
    "Dict.keys>Attribute(value=Name,attr='name',ctx=Load)",  # test_a1_identity_formation:2196
    'Dict.keys>Constant(value=str)',  # test_a1_identity_formation:1035
    'Dict.keys>Name(id=str,ctx=Load)',  # test_a1_identity_formation:3814
    "Dict.values>Attribute(value=Name,attr='sqlstate',ctx=Load)",  # test_a1_identity_formation:3454
    'Dict.values>Constant(value=bool)',  # test_a1_identity_formation:1035
    'Dict.values>Constant(value=int)',  # test_match_hold_admission_gate_pg (a30d37f6):359
    'Dict.values>Dict(keys=[],values=[])',  # test_a1_identity_formation:1219
    'Dict.values>Name(id=str,ctx=Load)',  # closed_walk:960
    'DictComp.generators>comprehension(target=Name,iter=BinOp,ifs=[],is_async=0)',  # test_a1_identity_formation:4382
    'DictComp.generators>comprehension(target=Name,iter=Call,ifs=[],is_async=0)',  # test_match_hold_admission_gate_pg (a30d37f6):108
    'DictComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # closed_walk:1035
    'DictComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Call],is_async=0)',  # test_a1_identity_formation:1321
    'DictComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # closed_walk:1086
    'DictComp.generators>comprehension(target=Tuple,iter=Call,ifs=[UnaryOp],is_async=0)',  # test_a1_identity_formation:4475
    'DictComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # closed_walk:920
    "DictComp.key>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:1969
    'DictComp.key>Name(id=str,ctx=Load)',  # closed_walk:920
    'DictComp.value>Call(func=Attribute,args=[Call],keywords=[])',  # test_a1_identity_formation:4382
    'DictComp.value>Constant(value=NoneType)',  # closed_walk:1035
    'DictComp.value>Name(id=str,ctx=Load)',  # closed_walk:1086
    'DictComp.value>Tuple(elts=[Call|Name],ctx=Load)',  # closed_walk:920
    'ExceptHandler.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # closed_walk:166
    'ExceptHandler.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):598
    'ExceptHandler.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):411
    'ExceptHandler.body>Assign(targets=[Name],value=Tuple,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):348
    'ExceptHandler.body>Assign(targets=[Tuple],value=Subscript,type_comment=-)',  # closed_walk:146
    'ExceptHandler.body>Continue()',  # test_a1_identity_formation:1239
    'ExceptHandler.body>Expr(value=Call)',  # closed_walk:1517
    'ExceptHandler.body>Pass()',  # test_a1_identity_formation:637
    'ExceptHandler.body>Raise(exc=Call,cause=-)',  # closed_walk:147
    'ExceptHandler.body>Raise(exc=Call,cause=Constant)',  # closed_walk:1103
    'ExceptHandler.body>Return(value=BinOp)',  # test_a1_identity_formation:2220
    'ExceptHandler.body>Return(value=Constant)',  # closed_walk:782
    'ExceptHandler.body>Return(value=IfExp)',  # test_a1_identity_formation:1089
    'ExceptHandler.body>Return(value=JoinedStr)',  # test_match_hold_admission_gate_pg (a30d37f6):589
    'ExceptHandler.body>Return(value=List)',  # test_a1_identity_formation:2172
    'ExceptHandler.body>Return(value=Subscript)',  # test_match_hold_admission_gate_pg (a30d37f6):552
    'ExceptHandler.body>Return(value=Tuple)',  # test_a1_identity_formation:886
    "ExceptHandler.type>Attribute(value=Name,attr='Refused',ctx=Load)",  # closed_walk:145
    'ExceptHandler.type>Name(id=str,ctx=Load)',  # closed_walk:165
    'ExceptHandler.type>Tuple(elts=[Name],ctx=Load)',  # closed_walk:192
    'Expr.value>Await(value=Call)',  # test_a1_identity_formation:1567
    'Expr.value>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:275
    'Expr.value>Call(func=Attribute,args=[Attribute|Call|Name],keywords=[])',  # test_a1_identity_formation:1062
    'Expr.value>Call(func=Attribute,args=[Attribute|Constant],keywords=[])',  # closed_walk:1583
    'Expr.value>Call(func=Attribute,args=[Attribute|Constant|Name],keywords=[])',  # closed_walk:449
    'Expr.value>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:1536
    'Expr.value>Call(func=Attribute,args=[Attribute|Tuple],keywords=[])',  # test_a1_identity_formation:2934
    'Expr.value>Call(func=Attribute,args=[BinOp],keywords=[])',  # closed_walk:1226
    'Expr.value>Call(func=Attribute,args=[BinOp|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):381
    'Expr.value>Call(func=Attribute,args=[BoolOp],keywords=[])',  # test_a1_identity_formation:3824
    'Expr.value>Call(func=Attribute,args=[BoolOp|JoinedStr],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):275
    'Expr.value>Call(func=Attribute,args=[BoolOp|Name],keywords=[])',  # closed_walk:662
    'Expr.value>Call(func=Attribute,args=[BoolOp|Subscript],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):255
    'Expr.value>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:857
    'Expr.value>Call(func=Attribute,args=[Call|Constant|Name],keywords=[])',  # closed_walk:1366
    'Expr.value>Call(func=Attribute,args=[Call|Name],keywords=[])',  # closed_walk:1808
    'Expr.value>Call(func=Attribute,args=[Call|Name|Tuple],keywords=[])',  # test_a1_identity_formation:2218
    'Expr.value>Call(func=Attribute,args=[Constant],keywords=[])',  # closed_walk:972
    'Expr.value>Call(func=Attribute,args=[Constant|Dict|Name],keywords=[])',  # test_a1_identity_formation:725
    'Expr.value>Call(func=Attribute,args=[Constant|JoinedStr],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):363
    'Expr.value>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # closed_walk:435
    'Expr.value>Call(func=Attribute,args=[Constant|Subscript],keywords=[])',  # test_a1_identity_formation:4534
    'Expr.value>Call(func=Attribute,args=[Constant|Subscript|Tuple],keywords=[])',  # closed_walk:461
    'Expr.value>Call(func=Attribute,args=[DictComp],keywords=[])',  # closed_walk:1969
    'Expr.value>Call(func=Attribute,args=[GeneratorExp],keywords=[])',  # closed_walk:73
    'Expr.value>Call(func=Attribute,args=[IfExp],keywords=[])',  # closed_walk:1434
    'Expr.value>Call(func=Attribute,args=[IfExp|Name],keywords=[])',  # closed_walk:1745
    'Expr.value>Call(func=Attribute,args=[JoinedStr],keywords=[])',  # test_a1_identity_formation:1492
    'Expr.value>Call(func=Attribute,args=[JoinedStr|Name],keywords=[])',  # closed_walk:139
    'Expr.value>Call(func=Attribute,args=[JoinedStr|Subscript],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1328
    'Expr.value>Call(func=Attribute,args=[List],keywords=[])',  # closed_walk:853
    'Expr.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:125
    'Expr.value>Call(func=Attribute,args=[Name|Starred],keywords=[])',  # closed_walk:784
    'Expr.value>Call(func=Attribute,args=[Name|Subscript],keywords=[])',  # closed_walk:1517
    'Expr.value>Call(func=Attribute,args=[Name|Subscript|Tuple],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):811
    'Expr.value>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:110
    'Expr.value>Call(func=Attribute,args=[Tuple],keywords=[])',  # closed_walk:445
    'Expr.value>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:476
    'Expr.value>Call(func=Name,args=[Attribute],keywords=[])',  # test_a1_identity_formation:1194
    'Expr.value>Call(func=Name,args=[Attribute|Call],keywords=[])',  # test_a1_identity_formation:3671
    'Expr.value>Call(func=Name,args=[Attribute|Constant],keywords=[])',  # closed_walk:1153
    'Expr.value>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1154
    'Expr.value>Call(func=Name,args=[Attribute|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):612
    'Expr.value>Call(func=Name,args=[BoolOp|Name],keywords=[])',  # closed_walk:1157
    'Expr.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:1163
    'Expr.value>Call(func=Name,args=[Dict|Name],keywords=[])',  # test_a1_identity_formation:1191
    'Expr.value>Call(func=Name,args=[JoinedStr|Name],keywords=[])',  # test_a1_identity_formation:1293
    'Expr.value>Call(func=Name,args=[Name],keywords=[])',  # test_a1_identity_formation:582
    'Expr.value>Call(func=Name,args=[Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):277
    'Expr.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # test_a1_identity_formation:647
    'Expr.value>Call(func=Name,args=[],keywords=[])',  # closed_walk:1495
    'Expr.value>Constant(value=str)',  # closed_walk:67
    'For.body>Assign(targets=[Name],value=Attribute,type_comment=-)',  # closed_walk:905
    'For.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # closed_walk:985
    'For.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:893
    'For.body>Assign(targets=[Name],value=Compare,type_comment=-)',  # test_a1_identity_formation:3813
    'For.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # test_a1_identity_formation:3836
    'For.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # closed_walk:1018
    'For.body>Assign(targets=[Name],value=List,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):55
    'For.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # closed_walk:960
    'For.body>Assign(targets=[Name],value=Name,type_comment=-)',  # closed_walk:328
    'For.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # closed_walk:1858
    'For.body>Assign(targets=[Name],value=Tuple,type_comment=-)',  # test_a1_identity_formation:1437
    'For.body>Assign(targets=[Subscript],value=Call,type_comment=-)',  # test_a1_identity_formation:3865
    'For.body>Assign(targets=[Subscript],value=Constant,type_comment=-)',  # test_a1_identity_formation:1436
    'For.body>Assign(targets=[Subscript],value=IfExp,type_comment=-)',  # closed_walk:1054
    'For.body>Assign(targets=[Subscript],value=SetComp,type_comment=-)',  # test_a1_identity_formation:2976
    'For.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # closed_walk:915
    'For.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # test_a1_identity_formation:1439
    'For.body>AugAssign(target=Name,op=Add,value=Call)',  # test_a1_identity_formation:1134
    'For.body>AugAssign(target=Subscript,op=Add,value=Constant)',  # closed_walk:2010
    'For.body>Expr(value=Call)',  # closed_walk:139
    'For.body>For(target=Name,iter=Attribute,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:4725
    'For.body>For(target=Name,iter=Call,body=[Assign],orelse=[],type_comment=-)',  # test_a1_identity_formation:3864
    'For.body>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:441
    'For.body>For(target=Name,iter=Call,body=[If],orelse=[],type_comment=-)',  # closed_walk:483
    'For.body>For(target=Name,iter=Subscript,body=[Expr|If],orelse=[],type_comment=-)',  # closed_walk:916
    'For.body>For(target=Name,iter=Tuple,body=[Assign|If],orelse=[],type_comment=-)',  # closed_walk:892
    'For.body>For(target=Tuple,iter=Call,body=[Assign],orelse=[],type_comment=-)',  # closed_walk:984
    'For.body>For(target=Tuple,iter=Call,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:897
    'For.body>For(target=Tuple,iter=Call,body=[Assign|If],orelse=[],type_comment=-)',  # test_a1_identity_formation:4333
    'For.body>For(target=Tuple,iter=Name,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:2964
    'For.body>FunctionDef(name=str,args=arguments,body=[For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3826
    'For.body>If(test=BinOp,body=[Expr],orelse=[])',  # test_a1_identity_formation:2200
    'For.body>If(test=BoolOp,body=[Assign],orelse=[])',  # closed_walk:727
    'For.body>If(test=BoolOp,body=[Assign|AugAssign|Continue|Expr|If|Try],orelse=[])',  # test_a1_identity_formation:1233
    'For.body>If(test=BoolOp,body=[Assign|Continue|Expr],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):451
    'For.body>If(test=BoolOp,body=[Assign|Continue|Expr|If],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):628
    'For.body>If(test=BoolOp,body=[Assign|Expr],orelse=[])',  # test_a1_identity_formation:2982
    'For.body>If(test=BoolOp,body=[Assign|Expr|If],orelse=[If])',  # closed_walk:943
    'For.body>If(test=BoolOp,body=[Assign|Expr|If],orelse=[])',  # closed_walk:1229
    'For.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # closed_walk:1942
    'For.body>If(test=BoolOp,body=[Continue],orelse=[])',  # closed_walk:906
    'For.body>If(test=BoolOp,body=[Continue|Expr],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):421
    'For.body>If(test=BoolOp,body=[Expr],orelse=[If])',  # closed_walk:311
    'For.body>If(test=BoolOp,body=[Expr],orelse=[])',  # closed_walk:894
    'For.body>If(test=BoolOp,body=[Expr|If],orelse=[])',  # closed_walk:1223
    'For.body>If(test=BoolOp,body=[For],orelse=[If])',  # test_a1_identity_formation:3817
    'For.body>If(test=BoolOp,body=[Pass],orelse=[If])',  # test_a1_identity_formation:3837
    'For.body>If(test=BoolOp,body=[Raise],orelse=[])',  # closed_walk:1187
    'For.body>If(test=BoolOp,body=[Return],orelse=[])',  # closed_walk:1044
    'For.body>If(test=Call,body=[Assign|Break],orelse=[])',  # test_a1_identity_formation:3205
    'For.body>If(test=Call,body=[Assign|Continue],orelse=[])',  # test_a1_identity_formation:1337
    'For.body>If(test=Call,body=[Assign|Continue|Expr|If],orelse=[])',  # test_a1_identity_formation:1324
    'For.body>If(test=Call,body=[Assign|Continue|If],orelse=[])',  # test_a1_identity_formation:1303
    'For.body>If(test=Call,body=[Assign|Continue|Try],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):269
    'For.body>If(test=Call,body=[Assign|Expr|If|Return],orelse=[])',  # test_a1_identity_formation:1285
    'For.body>If(test=Call,body=[Assign|For|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):424
    'For.body>If(test=Call,body=[Assign|If],orelse=[])',  # closed_walk:484
    'For.body>If(test=Call,body=[Assign|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):621
    'For.body>If(test=Call,body=[AugAssign],orelse=[If])',  # test_a1_identity_formation:1173
    'For.body>If(test=Call,body=[AugAssign],orelse=[])',  # test_a1_identity_formation:4726
    'For.body>If(test=Call,body=[Continue],orelse=[])',  # closed_walk:1145
    'For.body>If(test=Call,body=[Continue|Expr],orelse=[])',  # test_a1_identity_formation:1058
    'For.body>If(test=Call,body=[Continue|Expr|If],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1302
    'For.body>If(test=Call,body=[Expr],orelse=[Expr])',  # closed_walk:1535
    'For.body>If(test=Call,body=[Expr],orelse=[If])',  # closed_walk:72
    'For.body>If(test=Call,body=[Expr],orelse=[])',  # closed_walk:331
    'For.body>If(test=Call,body=[Expr|If|Return],orelse=[])',  # closed_walk:1743
    'For.body>If(test=Call,body=[For],orelse=[])',  # test_a1_identity_formation:787
    'For.body>If(test=Call,body=[For|If],orelse=[For])',  # test_a1_identity_formation:1415
    'For.body>If(test=Call,body=[For|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):505
    'For.body>If(test=Call,body=[If],orelse=[If])',  # closed_walk:2014
    'For.body>If(test=Call,body=[Return],orelse=[])',  # closed_walk:561
    'For.body>If(test=Compare,body=[Assign],orelse=[If])',  # test_a1_identity_formation:481
    'For.body>If(test=Compare,body=[Assign],orelse=[])',  # closed_walk:730
    'For.body>If(test=Compare,body=[Assign|AugAssign|Continue|If],orelse=[])',  # test_a1_identity_formation:1277
    'For.body>If(test=Compare,body=[Assign|Break],orelse=[])',  # closed_walk:957
    'For.body>If(test=Compare,body=[Assign|Continue|If],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1284
    'For.body>If(test=Compare,body=[Assign|Expr],orelse=[])',  # closed_walk:1218
    'For.body>If(test=Compare,body=[Break],orelse=[])',  # closed_walk:917
    'For.body>If(test=Compare,body=[Continue],orelse=[If])',  # test_match_hold_admission_gate_pg (a30d37f6):376
    'For.body>If(test=Compare,body=[Continue],orelse=[])',  # closed_walk:152
    'For.body>If(test=Compare,body=[Continue|Expr],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):266
    'For.body>If(test=Compare,body=[Expr],orelse=[If])',  # closed_walk:1980
    'For.body>If(test=Compare,body=[Expr],orelse=[])',  # closed_walk:1532
    'For.body>If(test=Compare,body=[For],orelse=[])',  # closed_walk:1215
    'For.body>If(test=Compare,body=[Raise],orelse=[])',  # closed_walk:631
    'For.body>If(test=Compare,body=[Return],orelse=[])',  # closed_walk:1060
    'For.body>If(test=Name,body=[Assign],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):63
    'For.body>If(test=Name,body=[AugAssign|Continue],orelse=[])',  # test_a1_identity_formation:1230
    'For.body>If(test=Name,body=[Continue|Expr],orelse=[])',  # test_a1_identity_formation:118
    'For.body>If(test=Name,body=[Expr],orelse=[])',  # test_a1_identity_formation:122
    'For.body>If(test=UnaryOp,body=[Continue],orelse=[])',  # closed_walk:899
    'For.body>If(test=UnaryOp,body=[Continue|Expr],orelse=[])',  # closed_walk:1855
    'For.body>If(test=UnaryOp,body=[Return],orelse=[])',  # closed_walk:1051
    'For.body>Raise(exc=Call,cause=-)',  # closed_walk:154
    'For.body>Return(value=JoinedStr)',  # test_match_hold_admission_gate_pg (a30d37f6):642
    'For.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:2193
    'For.body>Try(body=[Assign|Expr],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:4390
    'For.body>Try(body=[Expr],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:2169
    'For.body>While(test=Call,body=[Assign],orelse=[])',  # closed_walk:329
    "For.iter>Attribute(value=Call,attr='body',ctx=Load)",  # test_a1_identity_formation:4725
    "For.iter>Attribute(value=Call,attr='effects',ctx=Load)",  # closed_walk:1979
    "For.iter>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:1433
    "For.iter>Attribute(value=Name,attr='body',ctx=Load)",  # test_a1_identity_formation:579
    "For.iter>Attribute(value=Name,attr='effects',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):307
    "For.iter>Attribute(value=Name,attr='generators',ctx=Load)",  # closed_walk:1589
    "For.iter>Attribute(value=Name,attr='handlers',ctx=Load)",  # closed_walk:2052
    "For.iter>Attribute(value=Name,attr='ifs',ctx=Load)",  # closed_walk:1586
    "For.iter>Attribute(value=Name,attr='keywords',ctx=Load)",  # closed_walk:729
    "For.iter>Attribute(value=Name,attr='names',ctx=Load)",  # closed_walk:460
    "For.iter>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_a1_identity_formation:581
    "For.iter>Attribute(value=Name,attr='targets',ctx=Load)",  # closed_walk:2018
    "For.iter>Attribute(value=Name,attr='values',ctx=Load)",  # closed_walk:851
    'For.iter>BinOp(left=Attribute,op=Add,right=Attribute)',  # test_a1_identity_formation:1429
    'For.iter>BinOp(left=Attribute,op=Add,right=ListComp)',  # closed_walk:1576
    'For.iter>BinOp(left=BinOp,op=Add,right=Attribute)',  # closed_walk:2085
    'For.iter>BinOp(left=Call,op=BitOr,right=Call)',  # closed_walk:977
    'For.iter>BoolOp(op=Or,values=[Call|List])',  # closed_walk:1158
    'For.iter>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:150
    'For.iter>Call(func=Attribute,args=[Call],keywords=[])',  # test_a1_identity_formation:2932
    'For.iter>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:71
    'For.iter>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:138
    'For.iter>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:434
    'For.iter>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1017
    'For.iter>Call(func=Name,args=[Attribute|Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):490
    'For.iter>Call(func=Name,args=[BinOp|Name],keywords=[])',  # test_a1_identity_formation:3208
    'For.iter>Call(func=Name,args=[BinOp|UnaryOp],keywords=[])',  # test_a1_identity_formation:3204
    'For.iter>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:984
    'For.iter>Call(func=Name,args=[List],keywords=[])',  # test_a1_identity_formation:1416
    'For.iter>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:897
    'For.iter>Call(func=Name,args=[Name|Subscript],keywords=[])',  # closed_walk:1186
    'For.iter>Call(func=Name,args=[Subscript],keywords=[])',  # closed_walk:1228
    'For.iter>Call(func=Name,args=[Tuple],keywords=[])',  # test_a1_identity_formation:2167
    'For.iter>IfExp(test=Call,body=Attribute,orelse=List)',  # closed_walk:327
    'For.iter>IfExp(test=Call,body=List,orelse=List)',  # closed_walk:1591
    'For.iter>Name(id=str,ctx=Load)',  # closed_walk:440
    'For.iter>Subscript(value=Attribute,slice=Slice,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):850
    'For.iter>Subscript(value=Name,slice=Slice,ctx=Load)',  # closed_walk:916
    'For.iter>Tuple(elts=[BinOp|Name],ctx=Load)',  # test_a1_identity_formation:3863
    'For.iter>Tuple(elts=[Constant],ctx=Load)',  # closed_walk:892
    'For.iter>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:2192
    'For.iter>Tuple(elts=[Tuple],ctx=Load)',  # closed_walk:1216
    'For.target>Name(id=str,ctx=Store)',  # closed_walk:71
    'For.target>Tuple(elts=[Name],ctx=Store)',  # closed_walk:138
    'For.target>Tuple(elts=[Tuple],ctx=Store)',  # test_a1_identity_formation:4333
    "FormattedValue.value>Attribute(value=Attribute,attr='__name__',ctx=Load)",  # closed_walk:1508
    "FormattedValue.value>Attribute(value=Attribute,attr='id',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):479
    "FormattedValue.value>Attribute(value=Call,attr='__name__',ctx=Load)",  # closed_walk:289
    "FormattedValue.value>Attribute(value=Name,attr='__name__',ctx=Load)",  # closed_walk:1818
    "FormattedValue.value>Attribute(value=Name,attr='attr',ctx=Load)",  # closed_walk:1559
    "FormattedValue.value>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:554
    "FormattedValue.value>Attribute(value=Name,attr='lineno',ctx=Load)",  # test_a1_identity_formation:2208
    "FormattedValue.value>Attribute(value=Name,attr='name',ctx=Load)",  # test_a1_identity_formation:2172
    "FormattedValue.value>Attribute(value=Name,attr='value',ctx=Load)",  # test_a1_identity_formation:3849
    "FormattedValue.value>Attribute(value=Subscript,attr='lineno',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):617
    'FormattedValue.value>BinOp(left=Name,op=Add,right=Name)',  # closed_walk:139
    'FormattedValue.value>BoolOp(op=Or,values=[Call|Constant])',  # test_a1_identity_formation:1359
    'FormattedValue.value>BoolOp(op=Or,values=[Constant|Name])',  # test_a1_identity_formation:1508
    'FormattedValue.value>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:1732
    'FormattedValue.value>Call(func=Attribute,args=[Call],keywords=[])',  # closed_walk:1662
    'FormattedValue.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:575
    'FormattedValue.value>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:1189
    'FormattedValue.value>Call(func=Name,args=[BinOp],keywords=[])',  # test_a1_identity_formation:1511
    'FormattedValue.value>Call(func=Name,args=[Call],keywords=[keyword])',  # test_a1_identity_formation:137
    'FormattedValue.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:149
    'FormattedValue.value>Call(func=Name,args=[Name],keywords=[])',  # test_a1_identity_formation:892
    'FormattedValue.value>IfExp(test=Compare,body=Constant,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):642
    'FormattedValue.value>IfExp(test=Name,body=Attribute,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):644
    'FormattedValue.value>IfExp(test=Name,body=Constant,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):531
    'FormattedValue.value>Name(id=str,ctx=Load)',  # closed_walk:139
    'FormattedValue.value>Subscript(value=Call,slice=Slice,ctx=Load)',  # closed_walk:1502
    'FormattedValue.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):387
    'FormattedValue.value>Subscript(value=Name,slice=Slice,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):312
    'FormattedValue.value>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # test_a1_identity_formation:2172
    'FunctionDef.args>arguments(posonlyargs=[],args=[],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # closed_walk:265
    'FunctionDef.args>arguments(posonlyargs=[],args=[],vararg=arg,kwonlyargs=[arg],kw_defaults=[Constant],kwarg=-,defaults=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1830
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Call])',  # closed_walk:1272
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Call|Constant])',  # closed_walk:106
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Call|Constant|Tuple])',  # closed_walk:1452
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant])',  # closed_walk:129
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant|Tuple])',  # closed_walk:565
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Tuple])',  # closed_walk:1877
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # closed_walk:66
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=arg,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # closed_walk:1519
    'FunctionDef.body>Assert(test=BoolOp,msg=-)',  # test_a1_identity_formation:3690
    'FunctionDef.body>Assert(test=Compare,msg=-)',  # test_a1_identity_formation:3696
    'FunctionDef.body>Assert(test=Compare,msg=JoinedStr)',  # test_a1_identity_formation:135
    'FunctionDef.body>Assert(test=Compare,msg=Tuple)',  # test_a1_identity_formation:4420
    'FunctionDef.body>Assign(targets=[Attribute],value=Attribute,type_comment=-)',  # closed_walk:1918
    'FunctionDef.body>Assign(targets=[Attribute],value=Call,type_comment=-)',  # closed_walk:108
    'FunctionDef.body>Assign(targets=[Attribute],value=Compare,type_comment=-)',  # closed_walk:430
    'FunctionDef.body>Assign(targets=[Attribute],value=Constant,type_comment=-)',  # closed_walk:1390
    'FunctionDef.body>Assign(targets=[Attribute],value=Dict,type_comment=-)',  # closed_walk:114
    'FunctionDef.body>Assign(targets=[Attribute],value=IfExp,type_comment=-)',  # closed_walk:1456
    'FunctionDef.body>Assign(targets=[Attribute],value=JoinedStr,type_comment=-)',  # test_a1_identity_formation:4471
    'FunctionDef.body>Assign(targets=[Attribute],value=List,type_comment=-)',  # closed_walk:1469
    'FunctionDef.body>Assign(targets=[Attribute],value=ListComp,type_comment=-)',  # test_a1_identity_formation:37
    'FunctionDef.body>Assign(targets=[Attribute],value=Name,type_comment=-)',  # closed_walk:113
    'FunctionDef.body>Assign(targets=[Name],value=Attribute,type_comment=-)',  # closed_walk:811
    'FunctionDef.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # closed_walk:1620
    'FunctionDef.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # closed_walk:525
    'FunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:123
    'FunctionDef.body>Assign(targets=[Name],value=Compare,type_comment=-)',  # test_a1_identity_formation:998
    'FunctionDef.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # closed_walk:725
    'FunctionDef.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # closed_walk:889
    'FunctionDef.body>Assign(targets=[Name],value=DictComp,type_comment=-)',  # closed_walk:1035
    'FunctionDef.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # closed_walk:699
    'FunctionDef.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):1045
    'FunctionDef.body>Assign(targets=[Name],value=List,type_comment=-)',  # closed_walk:70
    'FunctionDef.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # closed_walk:177
    'FunctionDef.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # closed_walk:932
    'FunctionDef.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # closed_walk:719
    'FunctionDef.body>Assign(targets=[Name],value=Tuple,type_comment=-)',  # closed_walk:135
    'FunctionDef.body>Assign(targets=[Subscript],value=BinOp,type_comment=-)',  # test_a1_identity_formation:2430
    'FunctionDef.body>Assign(targets=[Subscript],value=Call,type_comment=-)',  # test_a1_identity_formation:4537
    'FunctionDef.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # closed_walk:156
    'FunctionDef.body>Assign(targets=[Subscript],value=Tuple,type_comment=-)',  # closed_walk:194
    'FunctionDef.body>Assign(targets=[Tuple],value=Attribute,type_comment=-)',  # test_a1_identity_formation:845
    'FunctionDef.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # closed_walk:516
    'FunctionDef.body>Assign(targets=[Tuple],value=GeneratorExp,type_comment=-)',  # test_a1_identity_formation:2165
    'FunctionDef.body>Assign(targets=[Tuple],value=Name,type_comment=-)',  # test_a1_identity_formation:894
    'FunctionDef.body>Assign(targets=[Tuple],value=Subscript,type_comment=-)',  # test_a1_identity_formation:835
    'FunctionDef.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # closed_walk:268
    'FunctionDef.body>AugAssign(target=Attribute,op=Add,value=Constant)',  # test_a1_identity_formation:2809
    'FunctionDef.body>AugAssign(target=Attribute,op=Sub,value=Constant)',  # test_a1_identity_formation:2811
    'FunctionDef.body>AugAssign(target=Subscript,op=Add,value=Constant)',  # closed_walk:1503
    'FunctionDef.body>ClassDef(name=str,bases=[Attribute],keywords=[],body=[FunctionDef],decorator_list=[],type_params=[])',  # test_a1_identity_formation:2804
    'FunctionDef.body>ClassDef(name=str,bases=[],keywords=[],body=[FunctionDef],decorator_list=[],type_params=[])',  # test_a1_identity_formation:3674
    'FunctionDef.body>Expr(value=Call)',  # closed_walk:445
    'FunctionDef.body>Expr(value=Constant)',  # closed_walk:67
    'FunctionDef.body>For(target=Name,iter=Attribute,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1433
    'FunctionDef.body>For(target=Name,iter=Attribute,body=[If],orelse=[],type_comment=-)',  # closed_walk:729
    'FunctionDef.body>For(target=Name,iter=BinOp,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:977
    'FunctionDef.body>For(target=Name,iter=BinOp,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1975
    'FunctionDef.body>For(target=Name,iter=Call,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # closed_walk:1017
    'FunctionDef.body>For(target=Name,iter=Call,body=[Assign|If],orelse=[],type_comment=-)',  # closed_walk:1041
    'FunctionDef.body>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # test_a1_identity_formation:470
    'FunctionDef.body>For(target=Name,iter=Call,body=[For],orelse=[],type_comment=-)',  # closed_walk:891
    'FunctionDef.body>For(target=Name,iter=Call,body=[If],orelse=[],type_comment=-)',  # closed_walk:71
    'FunctionDef.body>For(target=Name,iter=Call,body=[Try],orelse=[],type_comment=-)',  # test_a1_identity_formation:2216
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|AugAssign|If],orelse=[],type_comment=-)',  # closed_walk:2007
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # closed_walk:1063
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|For],orelse=[],type_comment=-)',  # test_a1_identity_formation:2962
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|If],orelse=[],type_comment=-)',  # closed_walk:1058
    'FunctionDef.body>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:661
    'FunctionDef.body>For(target=Name,iter=Name,body=[Expr|If],orelse=[],type_comment=-)',  # test_a1_identity_formation:903
    'FunctionDef.body>For(target=Name,iter=Name,body=[For],orelse=[],type_comment=-)',  # closed_walk:440
    'FunctionDef.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # closed_walk:560
    'FunctionDef.body>For(target=Name,iter=Subscript,body=[Return],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):850
    'FunctionDef.body>For(target=Name,iter=Tuple,body=[Expr],orelse=[],type_comment=-)',  # test_a1_identity_formation:3748
    'FunctionDef.body>For(target=Name,iter=Tuple,body=[For],orelse=[],type_comment=-)',  # test_a1_identity_formation:3863
    'FunctionDef.body>For(target=Name,iter=Tuple,body=[If],orelse=[],type_comment=-)',  # closed_walk:1742
    'FunctionDef.body>For(target=Name,iter=Tuple,body=[If|Try],orelse=[],type_comment=-)',  # test_a1_identity_formation:2192
    'FunctionDef.body>For(target=Name,iter=Tuple,body=[Try],orelse=[],type_comment=-)',  # test_a1_identity_formation:4389
    'FunctionDef.body>For(target=Tuple,iter=Attribute,body=[If],orelse=[],type_comment=-)',  # closed_walk:1979
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|Expr|For|FunctionDef],orelse=[],type_comment=-)',  # test_a1_identity_formation:3811
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # test_a1_identity_formation:1229
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|If],orelse=[],type_comment=-)',  # test_a1_identity_formation:116
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|If|Return],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):608
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Expr|If],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):265
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[For],orelse=[],type_comment=-)',  # test_a1_identity_formation:4332
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[If],orelse=[],type_comment=-)',  # closed_walk:726
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Try],orelse=[],type_comment=-)',  # test_a1_identity_formation:2167
    'FunctionDef.body>For(target=Tuple,iter=Name,body=[Expr|If],orelse=[],type_comment=-)',  # closed_walk:1610
    'FunctionDef.body>For(target=Tuple,iter=Name,body=[If],orelse=[],type_comment=-)',  # closed_walk:630
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|AugAssign|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1105
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1127
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1193
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1201
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:4532
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1223
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:847
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Expr|For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1972
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1091
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[For],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1143
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[If],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:574
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:936
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1072
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:1080
    'FunctionDef.body>If(test=Attribute,body=[Assign|For],orelse=[Assign|For|Try])',  # closed_walk:137
    'FunctionDef.body>If(test=Attribute,body=[Expr|Return],orelse=[])',  # closed_walk:124
    'FunctionDef.body>If(test=Attribute,body=[Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):670
    'FunctionDef.body>If(test=BinOp,body=[Raise],orelse=[])',  # closed_walk:1240
    'FunctionDef.body>If(test=BoolOp,body=[Assign],orelse=[If])',  # closed_walk:1091
    'FunctionDef.body>If(test=BoolOp,body=[Assign],orelse=[Try])',  # test_match_hold_admission_gate_pg (a30d37f6):403
    'FunctionDef.body>If(test=BoolOp,body=[Assign],orelse=[])',  # closed_walk:710
    'FunctionDef.body>If(test=BoolOp,body=[Assign|Expr|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1247
    'FunctionDef.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # closed_walk:869
    'FunctionDef.body>If(test=BoolOp,body=[Assign|If|Return],orelse=[])',  # closed_walk:1253
    'FunctionDef.body>If(test=BoolOp,body=[Assign|Raise],orelse=[])',  # closed_walk:1507
    'FunctionDef.body>If(test=BoolOp,body=[AugAssign|Expr|Return],orelse=[])',  # closed_walk:1753
    'FunctionDef.body>If(test=BoolOp,body=[Expr],orelse=[Assign|If|Try])',  # test_a1_identity_formation:2268
    'FunctionDef.body>If(test=BoolOp,body=[Expr],orelse=[If])',  # closed_walk:448
    'FunctionDef.body>If(test=BoolOp,body=[Expr],orelse=[])',  # closed_walk:1546
    'FunctionDef.body>If(test=BoolOp,body=[Expr|For|Return],orelse=[])',  # closed_walk:1780
    'FunctionDef.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',  # closed_walk:1803
    'FunctionDef.body>If(test=BoolOp,body=[Raise],orelse=[])',  # closed_walk:588
    'FunctionDef.body>If(test=BoolOp,body=[Return],orelse=[])',  # closed_walk:174
    'FunctionDef.body>If(test=BoolOp,body=[Try],orelse=[])',  # test_a1_identity_formation:1157
    'FunctionDef.body>If(test=Call,body=[Assign],orelse=[Assign])',  # closed_walk:720
    'FunctionDef.body>If(test=Call,body=[Assign],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):721
    'FunctionDef.body>If(test=Call,body=[Assign|AugAssign|Expr|For|If|Return],orelse=[])',  # closed_walk:1667
    'FunctionDef.body>If(test=Call,body=[Assign|AugAssign|Expr|If|Return],orelse=[])',  # closed_walk:1621
    'FunctionDef.body>If(test=Call,body=[Assign|Expr|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1255
    'FunctionDef.body>If(test=Call,body=[Assign|For],orelse=[If])',  # test_a1_identity_formation:1131
    'FunctionDef.body>If(test=Call,body=[Assign|For],orelse=[])',  # closed_walk:478
    'FunctionDef.body>If(test=Call,body=[Assign|For|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):650
    'FunctionDef.body>If(test=Call,body=[Assign|For|Return],orelse=[])',  # closed_walk:849
    'FunctionDef.body>If(test=Call,body=[Assign|If],orelse=[If])',  # closed_walk:748
    'FunctionDef.body>If(test=Call,body=[Assign|If|Return],orelse=[])',  # closed_walk:839
    'FunctionDef.body>If(test=Call,body=[Assign|Return],orelse=[])',  # closed_walk:866
    'FunctionDef.body>If(test=Call,body=[AugAssign|Expr|For|Return],orelse=[])',  # closed_walk:1762
    'FunctionDef.body>If(test=Call,body=[Expr|Import],orelse=[])',  # test_a1_identity_formation:4720
    'FunctionDef.body>If(test=Call,body=[If],orelse=[If])',  # test_a1_identity_formation:575
    'FunctionDef.body>If(test=Call,body=[Raise],orelse=[])',  # closed_walk:1203
    'FunctionDef.body>If(test=Call,body=[Return],orelse=[])',  # closed_walk:1287
    'FunctionDef.body>If(test=Call,body=[Try],orelse=[])',  # test_a1_identity_formation:632
    'FunctionDef.body>If(test=Compare,body=[Assign],orelse=[])',  # closed_walk:438
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr],orelse=[Assign|Expr])',  # closed_walk:1491
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr],orelse=[])',  # closed_walk:1910
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr|For|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):773
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr|If],orelse=[])',  # test_a1_identity_formation:1369
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):533
    'FunctionDef.body>If(test=Compare,body=[Assign|For],orelse=[])',  # closed_walk:433
    'FunctionDef.body>If(test=Compare,body=[Assign|If],orelse=[Assign|If])',  # test_a1_identity_formation:1488
    'FunctionDef.body>If(test=Compare,body=[Assign|If],orelse=[])',  # closed_walk:545
    'FunctionDef.body>If(test=Compare,body=[Assign|If|Raise],orelse=[])',  # closed_walk:1243
    'FunctionDef.body>If(test=Compare,body=[Assign|If|Return],orelse=[])',  # closed_walk:1259
    'FunctionDef.body>If(test=Compare,body=[Expr],orelse=[Assign|If|Try])',  # test_a1_identity_formation:2241
    'FunctionDef.body>If(test=Compare,body=[Expr],orelse=[Expr])',  # test_a1_identity_formation:2817
    'FunctionDef.body>If(test=Compare,body=[Expr],orelse=[])',  # closed_walk:783
    'FunctionDef.body>If(test=Compare,body=[Expr|For|Return],orelse=[])',  # closed_walk:1575
    'FunctionDef.body>If(test=Compare,body=[Expr|If],orelse=[])',  # test_a1_identity_formation:1196
    'FunctionDef.body>If(test=Compare,body=[Expr|If|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):819
    'FunctionDef.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # closed_walk:1594
    'FunctionDef.body>If(test=Compare,body=[For|If|Return],orelse=[])',  # closed_walk:1556
    'FunctionDef.body>If(test=Compare,body=[If],orelse=[])',  # test_a1_identity_formation:1353
    'FunctionDef.body>If(test=Compare,body=[Raise],orelse=[])',  # closed_walk:286
    'FunctionDef.body>If(test=Compare,body=[Return],orelse=[])',  # closed_walk:133
    'FunctionDef.body>If(test=Name,body=[Assign|If],orelse=[Assign|If|Try])',  # test_a1_identity_formation:1010
    'FunctionDef.body>If(test=Name,body=[Expr],orelse=[])',  # closed_walk:1825
    'FunctionDef.body>If(test=Name,body=[Expr|For|Return],orelse=[])',  # closed_walk:1786
    'FunctionDef.body>If(test=Name,body=[Return],orelse=[])',  # closed_walk:509
    'FunctionDef.body>If(test=UnaryOp,body=[Expr],orelse=[AugAssign|Try])',  # test_a1_identity_formation:1044
    'FunctionDef.body>If(test=UnaryOp,body=[Expr],orelse=[If])',  # test_a1_identity_formation:1362
    'FunctionDef.body>If(test=UnaryOp,body=[Expr],orelse=[])',  # closed_walk:1728
    'FunctionDef.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):520
    'FunctionDef.body>If(test=UnaryOp,body=[Raise],orelse=[])',  # closed_walk:701
    'FunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',  # closed_walk:523
    "FunctionDef.body>Import(names=['linecache'])",  # test_a1_identity_formation:3663
    "FunctionDef.body>Import(names=['pathlib'])",  # test_a1_identity_formation:3860
    "FunctionDef.body>Import(names=['resolution_sites'])",  # test_a1_identity_formation:4329
    "FunctionDef.body>Import(names=['shape_grammar'])",  # test_a1_identity_formation:4717
    "FunctionDef.body>Import(names=['sys'])",  # test_a1_identity_formation:721
    "FunctionDef.body>Import(names=['types'])",  # test_a1_identity_formation:3664
    'FunctionDef.body>Raise(exc=Call,cause=-)',  # closed_walk:554
    'FunctionDef.body>Return(value=BinOp)',  # test_match_hold_admission_gate_pg (a30d37f6):1832
    'FunctionDef.body>Return(value=BoolOp)',  # closed_walk:604
    'FunctionDef.body>Return(value=Call)',  # closed_walk:127
    'FunctionDef.body>Return(value=Compare)',  # closed_walk:687
    'FunctionDef.body>Return(value=Constant)',  # closed_walk:530
    'FunctionDef.body>Return(value=DictComp)',  # closed_walk:920
    'FunctionDef.body>Return(value=IfExp)',  # closed_walk:179
    'FunctionDef.body>Return(value=JoinedStr)',  # test_match_hold_admission_gate_pg (a30d37f6):644
    'FunctionDef.body>Return(value=List)',  # test_a1_identity_formation:1125
    'FunctionDef.body>Return(value=ListComp)',  # closed_walk:378
    'FunctionDef.body>Return(value=Name)',  # closed_walk:77
    'FunctionDef.body>Return(value=Subscript)',  # closed_walk:1874
    'FunctionDef.body>Return(value=Tuple)',  # closed_walk:167
    'FunctionDef.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[Assign|If],finalbody=[])',  # test_match_hold_admission_gate_pg (a30d37f6):345
    'FunctionDef.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # closed_walk:163
    'FunctionDef.body>Try(body=[Assign],handlers=[],orelse=[],finalbody=[Expr])',  # closed_walk:1887
    'FunctionDef.body>Try(body=[Assign|Expr],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:1002
    'FunctionDef.body>Try(body=[If],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_match_hold_admission_gate_pg (a30d37f6):585
    'FunctionDef.body>Try(body=[Return],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # closed_walk:1514
    'FunctionDef.body>While(test=BoolOp,body=[Assign],orelse=[])',  # closed_walk:1201
    'FunctionDef.body>While(test=Call,body=[Assign],orelse=[])',  # closed_walk:366
    'FunctionDef.body>While(test=Compare,body=[Assign|Expr|While],orelse=[])',  # test_a1_identity_formation:1792
    'FunctionDef.body>While(test=Name,body=[Assign|Expr|If],orelse=[])',  # closed_walk:1125
    'FunctionDef.body>While(test=Name,body=[Assign|For],orelse=[])',  # test_a1_identity_formation:2979
    'FunctionDef.body>While(test=Name,body=[Assign|If],orelse=[])',  # closed_walk:269
    'FunctionDef.body>While(test=UnaryOp,body=[Assign],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):109
    "FunctionDef.decorator_list>Attribute(value=Name,attr='fixture',ctx=Load)",  # test_a1_identity_formation:710
    'FunctionDef.decorator_list>Call(func=Attribute,args=[],keywords=[keyword])',  # test_a1_identity_formation:2922
    'FunctionDef.decorator_list>Name(id=str,ctx=Load)',  # closed_walk:771
    "GeneratorExp.elt>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:953
    "GeneratorExp.elt>Attribute(value=Name,attr='value',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):653
    'GeneratorExp.elt>BinOp(left=BinOp,op=Add,right=Constant)',  # test_a1_identity_formation:4515
    'GeneratorExp.elt>BoolOp(op=And,values=[Call])',  # closed_walk:872
    'GeneratorExp.elt>BoolOp(op=And,values=[Call|Compare])',  # test_a1_identity_formation:562
    'GeneratorExp.elt>BoolOp(op=And,values=[Call|Compare|UnaryOp])',  # test_a1_identity_formation:3251
    'GeneratorExp.elt>BoolOp(op=And,values=[Compare])',  # closed_walk:1203
    'GeneratorExp.elt>BoolOp(op=Or,values=[BoolOp|Call])',  # test_match_hold_admission_gate_pg (a30d37f6):788
    'GeneratorExp.elt>BoolOp(op=Or,values=[Compare])',  # closed_walk:1860
    'GeneratorExp.elt>Call(func=Attribute,args=[Name],keywords=[])',  # test_a1_identity_formation:3040
    'GeneratorExp.elt>Call(func=Name,args=[Attribute],keywords=[])',  # test_a1_identity_formation:778
    'GeneratorExp.elt>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1033
    'GeneratorExp.elt>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:919
    'GeneratorExp.elt>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:1282
    'GeneratorExp.elt>Compare(left=Attribute,ops=[Is],comparators=[Attribute])',  # test_match_hold_admission_gate_pg (a30d37f6):704
    'GeneratorExp.elt>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # closed_walk:1082
    'GeneratorExp.elt>Compare(left=Attribute,ops=[NotIn],comparators=[Tuple])',  # test_match_hold_admission_gate_pg (a30d37f6):700
    'GeneratorExp.elt>Compare(left=Call,ops=[NotEq],comparators=[Constant])',  # test_a1_identity_formation:932
    'GeneratorExp.elt>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1099
    'GeneratorExp.elt>Compare(left=Name,ops=[Eq],comparators=[Name])',  # closed_walk:178
    'GeneratorExp.elt>Compare(left=Name,ops=[In],comparators=[Attribute])',  # closed_walk:127
    'GeneratorExp.elt>Compare(left=Name,ops=[In],comparators=[Name])',  # test_a1_identity_formation:932
    'GeneratorExp.elt>Compare(left=Name,ops=[Is],comparators=[Constant])',  # closed_walk:981
    'GeneratorExp.elt>Compare(left=Name,ops=[Is],comparators=[Name])',  # test_a1_identity_formation:930
    'GeneratorExp.elt>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # closed_walk:499
    'GeneratorExp.elt>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # closed_walk:1184
    'GeneratorExp.elt>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # test_a1_identity_formation:1317
    'GeneratorExp.elt>Constant(value=int)',  # closed_walk:174
    'GeneratorExp.elt>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:1109
    'GeneratorExp.elt>Name(id=str,ctx=Load)',  # closed_walk:498
    'GeneratorExp.elt>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # test_a1_identity_formation:2165
    'GeneratorExp.elt>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:683
    'GeneratorExp.elt>Subscript(value=Name,slice=Name,ctx=Load)',  # test_a1_identity_formation:4399
    'GeneratorExp.elt>Tuple(elts=[Attribute|Constant],ctx=Load)',  # test_a1_identity_formation:1381
    'GeneratorExp.elt>Tuple(elts=[Attribute|Tuple],ctx=Load)',  # closed_walk:73
    'GeneratorExp.elt>Tuple(elts=[Name],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):72
    'GeneratorExp.elt>UnaryOp(op=Not,operand=Call)',  # test_a1_identity_formation:1210
    'GeneratorExp.generators>comprehension(target=Name,iter=Attribute,ifs=[],is_async=0)',  # closed_walk:73
    'GeneratorExp.generators>comprehension(target=Name,iter=Call,ifs=[BoolOp],is_async=0)',  # closed_walk:1935
    'GeneratorExp.generators>comprehension(target=Name,iter=Call,ifs=[Call],is_async=0)',  # test_a1_identity_formation:778
    'GeneratorExp.generators>comprehension(target=Name,iter=Call,ifs=[],is_async=0)',  # closed_walk:683
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[BoolOp],is_async=0)',  # test_a1_identity_formation:1381
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # test_match_hold_admission_gate_pg (a30d37f6):350
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # closed_walk:127
    'GeneratorExp.generators>comprehension(target=Name,iter=Subscript,ifs=[],is_async=0)',  # test_match_hold_admission_gate_pg (a30d37f6):704
    'GeneratorExp.generators>comprehension(target=Name,iter=Tuple,ifs=[],is_async=0)',  # test_a1_identity_formation:2165
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Attribute,ifs=[],is_async=0)',  # test_match_hold_admission_gate_pg (a30d37f6):302
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[BoolOp],is_async=0)',  # test_match_hold_admission_gate_pg (a30d37f6):72
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[Call],is_async=0)',  # closed_walk:498
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # closed_walk:174
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # closed_walk:178
    'GeneratorExp.generators>comprehension(target=Tuple,iter=Name,ifs=[],is_async=0)',  # closed_walk:499
    'If.body>Assert(test=Compare,msg=Constant)',  # test_a1_identity_formation:94
    'If.body>Assign(targets=[Attribute],value=Attribute,type_comment=-)',  # closed_walk:1423
    'If.body>Assign(targets=[Attribute],value=Dict,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):200
    'If.body>Assign(targets=[Attribute],value=Lambda,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):201
    'If.body>Assign(targets=[Attribute],value=Name,type_comment=-)',  # closed_walk:1425
    'If.body>Assign(targets=[Name],value=Attribute,type_comment=-)',  # closed_walk:315
    'If.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # closed_walk:75
    'If.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # test_a1_identity_formation:1278
    'If.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:141
    'If.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # closed_walk:958
    'If.body>Assign(targets=[Name],value=Dict,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):51
    'If.body>Assign(targets=[Name],value=DictComp,type_comment=-)',  # closed_walk:1086
    'If.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # closed_walk:480
    'If.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',  # closed_walk:1508
    'If.body>Assign(targets=[Name],value=List,type_comment=-)',  # closed_walk:850
    'If.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # closed_walk:721
    'If.body>Assign(targets=[Name],value=Name,type_comment=-)',  # closed_walk:758
    'If.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # closed_walk:728
    'If.body>Assign(targets=[Name],value=Tuple,type_comment=-)',  # test_a1_identity_formation:3194
    'If.body>Assign(targets=[Name|Subscript],value=Call,type_comment=-)',  # test_a1_identity_formation:4416
    'If.body>Assign(targets=[Subscript],value=Attribute,type_comment=-)',  # test_a1_identity_formation:3820
    'If.body>Assign(targets=[Subscript],value=BinOp,type_comment=-)',  # closed_walk:946
    'If.body>Assign(targets=[Subscript],value=Call,type_comment=-)',  # test_a1_identity_formation:701
    'If.body>Assign(targets=[Subscript],value=IfExp,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):1359
    'If.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # closed_walk:140
    'If.body>Assign(targets=[Subscript],value=Tuple,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):202
    'If.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # closed_walk:749
    'If.body>Assign(targets=[Tuple],value=IfExp,type_comment=-)',  # closed_walk:1913
    'If.body>Assign(targets=[Tuple],value=Name,type_comment=-)',  # closed_walk:546
    'If.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # closed_walk:938
    'If.body>AugAssign(target=Attribute,op=Add,value=Constant)',  # test_a1_identity_formation:3451
    'If.body>AugAssign(target=Name,op=Add,value=Constant)',  # test_a1_identity_formation:1797
    'If.body>AugAssign(target=Name,op=BitOr,value=SetComp)',  # test_a1_identity_formation:4727
    'If.body>AugAssign(target=Name,op=Sub,value=Constant)',  # test_a1_identity_formation:1231
    'If.body>AugAssign(target=Subscript,op=Add,value=Constant)',  # closed_walk:1664
    'If.body>Break()',  # closed_walk:488
    'If.body>Continue()',  # closed_walk:153
    'If.body>Expr(value=Call)',  # closed_walk:73
    'If.body>For(target=Name,iter=Attribute,body=[Assign|For|If],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):52
    'If.body>For(target=Name,iter=Attribute,body=[Assign|If],orelse=[],type_comment=-)',  # closed_walk:955
    'If.body>For(target=Name,iter=Attribute,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:460
    'If.body>For(target=Name,iter=Attribute,body=[Expr|If],orelse=[],type_comment=-)',  # closed_walk:2052
    'If.body>For(target=Name,iter=Attribute,body=[If],orelse=[],type_comment=-)',  # closed_walk:851
    'If.body>For(target=Name,iter=BinOp,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1576
    'If.body>For(target=Name,iter=BinOp,body=[If],orelse=[],type_comment=-)',  # closed_walk:2085
    'If.body>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:434
    'If.body>For(target=Name,iter=Call,body=[If],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):490
    'If.body>For(target=Name,iter=IfExp,body=[Assign|If|While],orelse=[],type_comment=-)',  # closed_walk:327
    'If.body>For(target=Name,iter=IfExp,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1591
    'If.body>For(target=Name,iter=Name,body=[AugAssign],orelse=[],type_comment=-)',  # test_a1_identity_formation:1133
    'If.body>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1720
    'If.body>For(target=Name,iter=Name,body=[For],orelse=[],type_comment=-)',  # closed_walk:482
    'If.body>For(target=Name,iter=Subscript,body=[Expr],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):436
    'If.body>For(target=Name,iter=Subscript,body=[If|Return],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):787
    'If.body>For(target=Name,iter=Tuple,body=[If],orelse=[],type_comment=-)',  # closed_walk:1216
    'If.body>For(target=Tuple,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:138
    'If.body>For(target=Tuple,iter=Call,body=[If],orelse=[],type_comment=-)',  # closed_walk:1792
    'If.body>If(test=Attribute,body=[Expr],orelse=[])',  # closed_walk:1582
    'If.body>If(test=Attribute,body=[Raise],orelse=[])',  # test_a1_identity_formation:92
    'If.body>If(test=Attribute,body=[Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):839
    'If.body>If(test=BoolOp,body=[Assign|AugAssign|Expr|If|Return],orelse=[])',  # closed_walk:1690
    'If.body>If(test=BoolOp,body=[Assign|For],orelse=[Assign])',  # closed_walk:952
    'If.body>If(test=BoolOp,body=[Assign|If],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):614
    'If.body>If(test=BoolOp,body=[Assign|If|Return],orelse=[])',  # closed_walk:1246
    'If.body>If(test=BoolOp,body=[AugAssign|Expr|Return],orelse=[])',  # closed_walk:1623
    'If.body>If(test=BoolOp,body=[Break|Expr],orelse=[])',  # closed_walk:486
    'If.body>If(test=BoolOp,body=[Continue],orelse=[])',  # closed_walk:1235
    'If.body>If(test=BoolOp,body=[Continue|Expr],orelse=[])',  # test_a1_identity_formation:3832
    'If.body>If(test=BoolOp,body=[Expr],orelse=[Expr])',  # closed_walk:971
    'If.body>If(test=BoolOp,body=[Expr],orelse=[])',  # closed_walk:474
    'If.body>If(test=BoolOp,body=[Expr|Return],orelse=[])',  # closed_walk:1565
    'If.body>If(test=BoolOp,body=[If],orelse=[])',  # closed_walk:1231
    'If.body>If(test=BoolOp,body=[Pass],orelse=[])',  # closed_walk:1260
    'If.body>If(test=BoolOp,body=[Raise],orelse=[])',  # closed_walk:1988
    'If.body>If(test=BoolOp,body=[Return],orelse=[])',  # closed_walk:549
    'If.body>If(test=BoolOp,body=[Try],orelse=[])',  # test_a1_identity_formation:1418
    'If.body>If(test=Call,body=[Expr],orelse=[Expr])',  # closed_walk:1712
    'If.body>If(test=Call,body=[Expr],orelse=[])',  # closed_walk:318
    'If.body>If(test=Call,body=[Expr|For|If|Return],orelse=[])',  # closed_walk:1581
    'If.body>If(test=Call,body=[Expr|If],orelse=[])',  # closed_walk:1673
    'If.body>If(test=Call,body=[Return],orelse=[])',  # closed_walk:840
    'If.body>If(test=Compare,body=[Assign],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1211
    'If.body>If(test=Compare,body=[Assign|Expr],orelse=[])',  # test_a1_identity_formation:1491
    'If.body>If(test=Compare,body=[Assign|If],orelse=[If])',  # closed_walk:750
    'If.body>If(test=Compare,body=[Assign|Raise],orelse=[])',  # test_a1_identity_formation:3452
    'If.body>If(test=Compare,body=[AugAssign|Expr],orelse=[Assign|Expr|If])',  # test_match_hold_admission_gate_pg (a30d37f6):426
    'If.body>If(test=Compare,body=[AugAssign|Expr|Return],orelse=[])',  # closed_walk:1676
    'If.body>If(test=Compare,body=[Continue|Expr],orelse=[])',  # test_a1_identity_formation:1240
    'If.body>If(test=Compare,body=[Expr],orelse=[Expr])',  # test_a1_identity_formation:1354
    'If.body>If(test=Compare,body=[Expr],orelse=[])',  # closed_walk:1633
    'If.body>If(test=Compare,body=[Expr|If],orelse=[])',  # test_a1_identity_formation:1177
    'If.body>If(test=Compare,body=[Expr|Return],orelse=[])',  # closed_walk:1669
    'If.body>If(test=Compare,body=[If],orelse=[If])',  # closed_walk:547
    'If.body>If(test=Compare,body=[Return],orelse=[])',  # test_a1_identity_formation:1012
    'If.body>If(test=Name,body=[Expr],orelse=[])',  # closed_walk:1660
    'If.body>If(test=Name,body=[Raise],orelse=[])',  # closed_walk:1248
    'If.body>If(test=UnaryOp,body=[Expr],orelse=[Assign|For|If])',  # test_a1_identity_formation:1390
    'If.body>If(test=UnaryOp,body=[Expr],orelse=[Expr])',  # test_match_hold_admission_gate_pg (a30d37f6):1287
    'If.body>If(test=UnaryOp,body=[Expr],orelse=[])',  # closed_walk:2061
    'If.body>If(test=UnaryOp,body=[For|Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):445
    'If.body>If(test=UnaryOp,body=[Return],orelse=[])',  # closed_walk:752
    "If.body>Import(names=['linecache'])",  # test_a1_identity_formation:4721
    'If.body>Pass()',  # closed_walk:1261
    'If.body>Raise(exc=Call,cause=-)',  # closed_walk:287
    'If.body>Return(value=-)',  # closed_walk:134
    'If.body>Return(value=Attribute)',  # closed_walk:544
    'If.body>Return(value=BinOp)',  # test_a1_identity_formation:1483
    'If.body>Return(value=Call)',  # closed_walk:847
    'If.body>Return(value=Constant)',  # closed_walk:126
    'If.body>Return(value=Dict)',  # test_a1_identity_formation:1147
    'If.body>Return(value=IfExp)',  # closed_walk:845
    'If.body>Return(value=JoinedStr)',  # test_match_hold_admission_gate_pg (a30d37f6):577
    'If.body>Return(value=List)',  # closed_walk:838
    'If.body>Return(value=ListComp)',  # test_a1_identity_formation:1117
    'If.body>Return(value=Name)',  # closed_walk:562
    'If.body>Return(value=Subscript)',  # closed_walk:189
    'If.body>Return(value=Tuple)',  # test_a1_identity_formation:790
    'If.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:1159
    'If.body>Try(body=[Expr],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_match_hold_admission_gate_pg (a30d37f6):271
    'If.body>Try(body=[If],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:633
    'If.body>While(test=Call,body=[Assign],orelse=[])',  # closed_walk:316
    'If.orelse>Assign(targets=[Name],value=BinOp,type_comment=-)',  # closed_walk:1496
    'If.orelse>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:964
    'If.orelse>Assign(targets=[Name],value=Dict,type_comment=-)',  # closed_walk:1089
    'If.orelse>Assign(targets=[Name],value=IfExp,type_comment=-)',  # closed_walk:723
    'If.orelse>Assign(targets=[Name],value=ListComp,type_comment=-)',  # test_a1_identity_formation:1496
    'If.orelse>Assign(targets=[Name],value=SetComp,type_comment=-)',  # test_a1_identity_formation:1427
    'If.orelse>Assign(targets=[Name],value=Subscript,type_comment=-)',  # test_a1_identity_formation:1023
    'If.orelse>Assign(targets=[Name],value=Tuple,type_comment=-)',  # closed_walk:149
    'If.orelse>Assign(targets=[Tuple],value=Call,type_comment=-)',  # test_a1_identity_formation:2246
    'If.orelse>AugAssign(target=Subscript,op=Add,value=Constant)',  # test_a1_identity_formation:1070
    'If.orelse>Continue()',  # test_match_hold_admission_gate_pg (a30d37f6):504
    'If.orelse>Expr(value=Call)',  # closed_walk:974
    'If.orelse>For(target=Name,iter=BinOp,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:1429
    'If.orelse>For(target=Name,iter=BoolOp,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1158
    'If.orelse>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # test_a1_identity_formation:1425
    'If.orelse>For(target=Name,iter=Subscript,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:1414
    'If.orelse>For(target=Name,iter=Tuple,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1156
    'If.orelse>For(target=Tuple,iter=Call,body=[If|Raise],orelse=[],type_comment=-)',  # closed_walk:150
    'If.orelse>For(target=Tuple,iter=Name,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # test_a1_identity_formation:1433
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[Assign])',  # test_match_hold_admission_gate_pg (a30d37f6):365
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[If])',  # closed_walk:759
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[])',  # closed_walk:757
    'If.orelse>If(test=BoolOp,body=[Assign|If],orelse=[])',  # closed_walk:471
    'If.orelse>If(test=BoolOp,body=[Assign|If|While],orelse=[If])',  # closed_walk:313
    'If.orelse>If(test=BoolOp,body=[Expr],orelse=[Expr])',  # test_a1_identity_formation:1186
    'If.orelse>If(test=BoolOp,body=[Expr],orelse=[If])',  # closed_walk:462
    'If.orelse>If(test=BoolOp,body=[Expr],orelse=[])',  # test_a1_identity_formation:485
    'If.orelse>If(test=BoolOp,body=[For],orelse=[If])',  # test_a1_identity_formation:2059
    'If.orelse>If(test=BoolOp,body=[Return],orelse=[])',  # closed_walk:551
    'If.orelse>If(test=Call,body=[Assign],orelse=[Expr|Return])',  # test_a1_identity_formation:1140
    'If.orelse>If(test=Call,body=[Assign],orelse=[If])',  # test_a1_identity_formation:1137
    'If.orelse>If(test=Call,body=[Assign|AugAssign|Expr|If],orelse=[If])',  # closed_walk:2058
    'If.orelse>If(test=Call,body=[Assign|Expr],orelse=[])',  # closed_walk:74
    'If.orelse>If(test=Call,body=[Assign|Expr|If],orelse=[If])',  # closed_walk:1986
    'If.orelse>If(test=Call,body=[Assign|If|While],orelse=[If])',  # closed_walk:320
    'If.orelse>If(test=Call,body=[AugAssign|Expr|For|If],orelse=[If])',  # closed_walk:2076
    'If.orelse>If(test=Call,body=[Expr],orelse=[Continue|Expr])',  # test_match_hold_admission_gate_pg (a30d37f6):498
    'If.orelse>If(test=Call,body=[Expr],orelse=[For])',  # closed_walk:1152
    'If.orelse>If(test=Call,body=[Expr],orelse=[If])',  # closed_walk:454
    'If.orelse>If(test=Call,body=[Expr],orelse=[])',  # test_a1_identity_formation:2065
    'If.orelse>If(test=Call,body=[Expr|For],orelse=[If])',  # closed_walk:450
    'If.orelse>If(test=Call,body=[Expr|If],orelse=[If])',  # closed_walk:1982
    'If.orelse>If(test=Call,body=[Expr|If],orelse=[Return])',  # closed_walk:854
    'If.orelse>If(test=Call,body=[For],orelse=[If])',  # closed_walk:456
    'If.orelse>If(test=Call,body=[For],orelse=[])',  # closed_walk:326
    'If.orelse>If(test=Call,body=[If],orelse=[If])',  # closed_walk:2069
    'If.orelse>If(test=Call,body=[Pass],orelse=[Expr])',  # closed_walk:2097
    'If.orelse>If(test=Call,body=[Pass],orelse=[If])',  # closed_walk:2074
    'If.orelse>If(test=Compare,body=[Assign],orelse=[Assign|If])',  # test_match_hold_admission_gate_pg (a30d37f6):354
    'If.orelse>If(test=Compare,body=[Assign],orelse=[Expr])',  # test_match_hold_admission_gate_pg (a30d37f6):384
    'If.orelse>If(test=Compare,body=[Assign],orelse=[If])',  # test_a1_identity_formation:483
    'If.orelse>If(test=Compare,body=[Assign],orelse=[])',  # test_a1_identity_formation:1501
    'If.orelse>If(test=Compare,body=[AugAssign],orelse=[])',  # test_a1_identity_formation:1798
    'If.orelse>If(test=Compare,body=[Continue],orelse=[If])',  # test_match_hold_admission_gate_pg (a30d37f6):382
    'If.orelse>If(test=Compare,body=[Expr],orelse=[If])',  # closed_walk:1994
    'If.orelse>If(test=Compare,body=[Expr],orelse=[])',  # closed_walk:274
    'If.orelse>If(test=Compare,body=[Expr|If],orelse=[Expr])',  # test_match_hold_admission_gate_pg (a30d37f6):1209
    'If.orelse>If(test=Compare,body=[Return],orelse=[])',  # test_a1_identity_formation:1021
    'If.orelse>If(test=Name,body=[Expr],orelse=[])',  # test_a1_identity_formation:1400
    'If.orelse>If(test=UnaryOp,body=[Expr],orelse=[])',  # test_a1_identity_formation:2230
    'If.orelse>If(test=UnaryOp,body=[For],orelse=[])',  # test_a1_identity_formation:583
    'If.orelse>Return(value=Constant)',  # closed_walk:859
    'If.orelse>Return(value=Dict)',  # test_a1_identity_formation:1145
    'If.orelse>Try(body=[Assign],handlers=[ExceptHandler],orelse=[Assign|If],finalbody=[])',  # test_a1_identity_formation:2289
    'If.orelse>Try(body=[Assign],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # closed_walk:143
    'If.orelse>Try(body=[For],handlers=[ExceptHandler],orelse=[],finalbody=[])',  # test_a1_identity_formation:1053
    "If.test>Attribute(value=Name,attr='fail_lease_read',ctx=Load)",  # test_a1_identity_formation:92
    "If.test>Attribute(value=Name,attr='is_async',ctx=Load)",  # closed_walk:1582
    "If.test>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):670
    "If.test>Attribute(value=Name,attr='record',ctx=Load)",  # closed_walk:124
    'If.test>BinOp(left=Name,op=BitAnd,right=Name)',  # closed_walk:1240
    'If.test>BinOp(left=Name,op=BitAnd,right=Set)',  # test_a1_identity_formation:2200
    'If.test>BoolOp(op=And,values=[Attribute|Call])',  # closed_walk:462
    'If.test>BoolOp(op=And,values=[Attribute|Call|Compare])',  # closed_walk:1939
    'If.test>BoolOp(op=And,values=[Attribute|Call|Compare|UnaryOp])',  # closed_walk:551
    'If.test>BoolOp(op=And,values=[Attribute|Compare])',  # test_a1_identity_formation:2824
    'If.test>BoolOp(op=And,values=[BinOp|Compare])',  # test_a1_identity_formation:2982
    'If.test>BoolOp(op=And,values=[BoolOp|Call])',  # closed_walk:1923
    'If.test>BoolOp(op=And,values=[BoolOp|Compare])',  # test_a1_identity_formation:3193
    'If.test>BoolOp(op=And,values=[Call])',  # closed_walk:311
    'If.test>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:313
    'If.test>BoolOp(op=And,values=[Call|Compare|Name])',  # test_a1_identity_formation:3832
    'If.test>BoolOp(op=And,values=[Call|Compare|Name|UnaryOp])',  # test_a1_identity_formation:3837
    'If.test>BoolOp(op=And,values=[Call|Compare|UnaryOp])',  # closed_walk:1093
    'If.test>BoolOp(op=And,values=[Call|Name])',  # closed_walk:871
    'If.test>BoolOp(op=And,values=[Call|UnaryOp])',  # closed_walk:448
    'If.test>BoolOp(op=And,values=[Compare])',  # closed_walk:188
    'If.test>BoolOp(op=And,values=[Compare|Name])',  # closed_walk:1822
    'If.test>BoolOp(op=And,values=[Compare|UnaryOp])',  # closed_walk:1253
    'If.test>BoolOp(op=And,values=[Name|UnaryOp])',  # test_a1_identity_formation:1280
    'If.test>BoolOp(op=Or,values=[Attribute])',  # closed_walk:1749
    'If.test>BoolOp(op=Or,values=[Attribute|Call])',  # test_a1_identity_formation:1329
    'If.test>BoolOp(op=Or,values=[Attribute|Call|Compare])',  # closed_walk:1030
    'If.test>BoolOp(op=Or,values=[Attribute|UnaryOp])',  # closed_walk:777
    'If.test>BoolOp(op=Or,values=[BoolOp|Compare])',  # closed_walk:1232
    'If.test>BoolOp(op=Or,values=[Call])',  # closed_walk:1055
    'If.test>BoolOp(op=Or,values=[Call|Compare])',  # closed_walk:1009
    'If.test>BoolOp(op=Or,values=[Call|Name])',  # closed_walk:1184
    'If.test>BoolOp(op=Or,values=[Call|UnaryOp])',  # closed_walk:981
    'If.test>BoolOp(op=Or,values=[Compare])',  # closed_walk:174
    'If.test>BoolOp(op=Or,values=[Compare|Name])',  # test_a1_identity_formation:1384
    'If.test>BoolOp(op=Or,values=[Compare|UnaryOp])',  # closed_walk:588
    'If.test>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:840
    'If.test>Call(func=Attribute,args=[Constant],keywords=[])',  # closed_walk:1982
    'If.test>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:561
    'If.test>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_a1_identity_formation:3205
    'If.test>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1621
    'If.test>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:72
    'If.test>Call(func=Name,args=[Call|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1249
    'If.test>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:1762
    'If.test>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:1203
    'If.test>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1085
    'If.test>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:320
    'If.test>Compare(left=Attribute,ops=[Eq],comparators=[Attribute])',  # test_a1_identity_formation:3452
    'If.test>Compare(left=Attribute,ops=[Eq],comparators=[Constant])',  # closed_walk:1676
    'If.test>Compare(left=Attribute,ops=[In],comparators=[Attribute])',  # closed_walk:639
    'If.test>Compare(left=Attribute,ops=[In],comparators=[Tuple])',  # closed_walk:1682
    'If.test>Compare(left=Attribute,ops=[IsNot],comparators=[Constant])',  # closed_walk:547
    'If.test>Compare(left=Attribute,ops=[Is],comparators=[Name])',  # closed_walk:730
    'If.test>Compare(left=Attribute,ops=[NotIn],comparators=[Attribute])',  # closed_walk:1708
    'If.test>Compare(left=BinOp,ops=[Gt],comparators=[Call])',  # test_a1_identity_formation:833
    'If.test>Compare(left=BinOp,ops=[In],comparators=[Name])',  # test_a1_identity_formation:3247
    'If.test>Compare(left=BinOp,ops=[NotEq],comparators=[BoolOp])',  # test_a1_identity_formation:4336
    'If.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1354
    'If.test>Compare(left=Call,ops=[Eq],comparators=[Name])',  # closed_walk:1218
    'If.test>Compare(left=Call,ops=[Gt],comparators=[Constant])',  # closed_walk:507
    'If.test>Compare(left=Call,ops=[Gt],comparators=[Name])',  # closed_walk:1060
    'If.test>Compare(left=Call,ops=[In],comparators=[Name])',  # test_a1_identity_formation:916
    'If.test>Compare(left=Call,ops=[IsNot],comparators=[Constant])',  # closed_walk:1669
    'If.test>Compare(left=Call,ops=[Is],comparators=[Constant])',  # test_match_hold_admission_gate_pg (a30d37f6):767
    'If.test>Compare(left=Call,ops=[Is],comparators=[Name])',  # closed_walk:133
    'If.test>Compare(left=Call,ops=[LtE],comparators=[Name])',  # closed_walk:986
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Call])',  # closed_walk:978
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Constant])',  # closed_walk:1872
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):529
    'If.test>Compare(left=Call,ops=[NotIn],comparators=[Attribute])',  # closed_walk:1744
    'If.test>Compare(left=Call,ops=[NotIn],comparators=[Name])',  # test_a1_identity_formation:1430
    'If.test>Compare(left=Constant,ops=[In],comparators=[Call])',  # test_a1_identity_formation:2817
    'If.test>Compare(left=Constant,ops=[In],comparators=[Name])',  # test_a1_identity_formation:91
    'If.test>Compare(left=Constant,ops=[NotIn],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):49
    'If.test>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # closed_walk:543
    'If.test>Compare(left=Name,ops=[Eq],comparators=[Name])',  # test_a1_identity_formation:3038
    'If.test>Compare(left=Name,ops=[In],comparators=[Attribute])',  # closed_walk:1880
    'If.test>Compare(left=Name,ops=[In],comparators=[Call])',  # closed_walk:917
    'If.test>Compare(left=Name,ops=[In],comparators=[Name])',  # closed_walk:1209
    'If.test>Compare(left=Name,ops=[In],comparators=[Tuple])',  # closed_walk:1259
    'If.test>Compare(left=Name,ops=[IsNot],comparators=[Attribute])',  # closed_walk:274
    'If.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # closed_walk:433
    'If.test>Compare(left=Name,ops=[IsNot],comparators=[Name])',  # closed_walk:1363
    'If.test>Compare(left=Name,ops=[Is],comparators=[Constant])',  # closed_walk:286
    'If.test>Compare(left=Name,ops=[Is],comparators=[Name])',  # test_a1_identity_formation:789
    'If.test>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # closed_walk:527
    'If.test>Compare(left=Name,ops=[NotEq],comparators=[Name])',  # test_a1_identity_formation:1509
    'If.test>Compare(left=Name,ops=[NotIn],comparators=[Name])',  # closed_walk:573
    'If.test>Compare(left=Name,ops=[NotIn],comparators=[Tuple])',  # closed_walk:1633
    'If.test>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1796
    'If.test>Compare(left=Subscript,ops=[In],comparators=[Tuple])',  # test_match_hold_admission_gate_pg (a30d37f6):376
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',  # closed_walk:641
    'If.test>Compare(left=Tuple,ops=[Eq],comparators=[Name])',  # closed_walk:152
    'If.test>Compare(left=Tuple,ops=[In],comparators=[Tuple])',  # test_a1_identity_formation:1506
    'If.test>Name(id=str,ctx=Load)',  # closed_walk:272
    'If.test>UnaryOp(op=Not,operand=Attribute)',  # test_a1_identity_formation:46
    'If.test>UnaryOp(op=Not,operand=BoolOp)',  # closed_walk:523
    'If.test>UnaryOp(op=Not,operand=Call)',  # closed_walk:808
    'If.test>UnaryOp(op=Not,operand=Name)',  # closed_walk:701
    'If.test>UnaryOp(op=Not,operand=Subscript)',  # test_a1_identity_formation:1205
    "IfExp.body>Attribute(value=Attribute,attr='value',ctx=Load)",  # test_a1_identity_formation:518
    "IfExp.body>Attribute(value=Name,attr='body',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1251
    "IfExp.body>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:368
    "IfExp.body>Attribute(value=Name,attr='targets',ctx=Load)",  # closed_walk:327
    "IfExp.body>Attribute(value=Name,attr='test',ctx=Load)",  # test_a1_identity_formation:1233
    "IfExp.body>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:1944
    "IfExp.body>Attribute(value=Subscript,attr='context_expr',ctx=Load)",  # closed_walk:2060
    "IfExp.body>Attribute(value=Subscript,attr='lineno',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):644
    'IfExp.body>BinOp(left=Constant,op=Add,right=Call)',  # test_a1_identity_formation:1109
    'IfExp.body>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:947
    'IfExp.body>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:700
    'IfExp.body>Call(func=Attribute,args=[Starred],keywords=[])',  # test_a1_identity_formation:1166
    'IfExp.body>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:1031
    'IfExp.body>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:723
    'IfExp.body>Call(func=Name,args=[Attribute|Call],keywords=[])',  # test_a1_identity_formation:1290
    'IfExp.body>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',  # closed_walk:761
    'IfExp.body>Call(func=Name,args=[Attribute|Name],keywords=[])',  # test_a1_identity_formation:1310
    'IfExp.body>Call(func=Name,args=[Call|IfExp],keywords=[])',  # test_a1_identity_formation:1497
    'IfExp.body>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:699
    'IfExp.body>Call(func=Name,args=[],keywords=[])',  # closed_walk:1657
    'IfExp.body>Constant(value=NoneType)',  # closed_walk:939
    'IfExp.body>Constant(value=str)',  # closed_walk:1104
    'IfExp.body>Dict(keys=[Name],values=[Name])',  # test_a1_identity_formation:3814
    'IfExp.body>JoinedStr(values=[Constant|FormattedValue])',  # closed_walk:1745
    'IfExp.body>List(elts=[Attribute],ctx=Load)',  # closed_walk:1591
    'IfExp.body>List(elts=[Name],ctx=Load)',  # closed_walk:845
    'IfExp.body>List(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:1089
    'IfExp.body>List(elts=[],ctx=Load)',  # test_a1_identity_formation:4392
    'IfExp.body>Name(id=str,ctx=Load)',  # closed_walk:517
    'IfExp.body>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:1076
    'IfExp.body>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:1772
    'IfExp.body>Subscript(value=Name,slice=BinOp,ctx=Load)',  # closed_walk:1230
    'IfExp.body>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:179
    'IfExp.body>Tuple(elts=[Attribute],ctx=Load)',  # closed_walk:677
    'IfExp.body>Tuple(elts=[Attribute|Constant],ctx=Load)',  # closed_walk:1434
    'IfExp.body>Tuple(elts=[Subscript],ctx=Load)',  # test_a1_identity_formation:3195
    "IfExp.orelse>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:699
    "IfExp.orelse>Attribute(value=Name,attr='name',ctx=Load)",  # test_a1_identity_formation:3831
    "IfExp.orelse>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1252
    "IfExp.orelse>Attribute(value=Name,attr='value',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1256
    'IfExp.orelse>BinOp(left=Name,op=Add,right=Name)',  # closed_walk:939
    'IfExp.orelse>BinOp(left=Subscript,op=BitAnd,right=Name)',  # closed_walk:1054
    'IfExp.orelse>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:678
    'IfExp.orelse>Call(func=Name,args=[Attribute],keywords=[keyword])',  # closed_walk:1457
    'IfExp.orelse>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1659
    'IfExp.orelse>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1466
    'IfExp.orelse>Call(func=Name,args=[],keywords=[])',  # test_a1_identity_formation:1166
    'IfExp.orelse>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # closed_walk:700
    'IfExp.orelse>Constant(value=NoneType)',  # closed_walk:179
    'IfExp.orelse>Constant(value=str)',  # closed_walk:1105
    'IfExp.orelse>Dict(keys=[],values=[])',  # test_a1_identity_formation:3814
    'IfExp.orelse>IfExp(test=Compare,body=Constant,orelse=Constant)',  # closed_walk:1104
    'IfExp.orelse>IfExp(test=Compare,body=Constant,orelse=IfExp)',  # closed_walk:1832
    'IfExp.orelse>JoinedStr(values=[Constant|FormattedValue])',  # test_match_hold_admission_gate_pg (a30d37f6):601
    'IfExp.orelse>List(elts=[Attribute],ctx=Load)',  # closed_walk:327
    'IfExp.orelse>List(elts=[JoinedStr],ctx=Load)',  # test_a1_identity_formation:4393
    'IfExp.orelse>List(elts=[Name],ctx=Load)',  # test_a1_identity_formation:4718
    'IfExp.orelse>List(elts=[],ctx=Load)',  # closed_walk:724
    'IfExp.orelse>ListComp(elt=Call,generators=[comprehension])',  # closed_walk:962
    'IfExp.orelse>Name(id=str,ctx=Load)',  # closed_walk:1297
    'IfExp.orelse>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1014
    'IfExp.orelse>Tuple(elts=[Attribute|Constant],ctx=Load)',  # closed_walk:1437
    'IfExp.orelse>Tuple(elts=[Call|Constant],ctx=Load)',  # closed_walk:1914
    'IfExp.orelse>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:3195
    'IfExp.orelse>Tuple(elts=[Constant|Name],ctx=Load)',  # closed_walk:1435
    "IfExp.test>Attribute(value=Name,attr='_rows',ctx=Load)",  # test_a1_identity_formation:43
    "IfExp.test>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:1076
    "IfExp.test>Attribute(value=Name,attr='has_fn',ctx=Load)",  # closed_walk:700
    "IfExp.test>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):367
    'IfExp.test>BinOp(left=Name,op=BitAnd,right=Set)',  # test_match_hold_admission_gate_pg (a30d37f6):355
    'IfExp.test>BoolOp(op=And,values=[Call])',  # test_a1_identity_formation:518
    'IfExp.test>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:948
    'IfExp.test>BoolOp(op=And,values=[Compare])',  # closed_walk:517
    'IfExp.test>BoolOp(op=And,values=[Compare|Name])',  # closed_walk:1276
    'IfExp.test>BoolOp(op=And,values=[Name])',  # test_a1_identity_formation:2247
    'IfExp.test>BoolOp(op=Or,values=[BinOp|Name])',  # closed_walk:1258
    'IfExp.test>BoolOp(op=Or,values=[Compare])',  # closed_walk:939
    'IfExp.test>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:1092
    'IfExp.test>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:769
    'IfExp.test>Call(func=Name,args=[Attribute],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):633
    'IfExp.test>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:327
    'IfExp.test>Call(func=Name,args=[Constant|Name],keywords=[])',  # test_a1_identity_formation:858
    'IfExp.test>Call(func=Name,args=[GeneratorExp],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1251
    'IfExp.test>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:768
    'IfExp.test>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:480
    'IfExp.test>Compare(left=Attribute,ops=[IsNot],comparators=[Constant])',  # closed_walk:1018
    'IfExp.test>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # closed_walk:1437
    'IfExp.test>Compare(left=BinOp,ops=[Lt],comparators=[Call])',  # test_match_hold_admission_gate_pg (a30d37f6):123
    'IfExp.test>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # closed_walk:179
    'IfExp.test>Compare(left=Call,ops=[IsNot],comparators=[Constant])',  # closed_walk:1657
    'IfExp.test>Compare(left=Constant,ops=[In],comparators=[Name])',  # closed_walk:1104
    'IfExp.test>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1014
    'IfExp.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # closed_walk:724
    'IfExp.test>Compare(left=Name,ops=[Is],comparators=[Constant])',  # closed_walk:961
    'IfExp.test>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # closed_walk:1207
    'IfExp.test>Compare(left=Subscript,ops=[In],comparators=[Constant])',  # test_match_hold_admission_gate_pg (a30d37f6):642
    'IfExp.test>Compare(left=Subscript,ops=[Is],comparators=[Constant])',  # closed_walk:1054
    'IfExp.test>Name(id=str,ctx=Load)',  # closed_walk:821
    'IfExp.test>UnaryOp(op=Not,operand=Call)',  # closed_walk:699
    "Import.names>alias(name='linecache',asname='_linecache')",  # test_a1_identity_formation:3663
    "Import.names>alias(name='linecache',asname=None)",  # test_a1_identity_formation:4467
    "Import.names>alias(name='pathlib',asname=None)",  # test_a1_identity_formation:3860
    "Import.names>alias(name='resolution_sites',asname='_rs')",  # test_a1_identity_formation:4329
    "Import.names>alias(name='shape_grammar',asname='_sg')",  # test_a1_identity_formation:4717
    "Import.names>alias(name='sys',asname='_sys')",  # test_a1_identity_formation:721
    "Import.names>alias(name='types',asname='_types')",  # test_a1_identity_formation:3664
    "Import.names>alias(name='types',asname=None)",  # test_match_hold_admission_gate_pg (a30d37f6):1043
    'JoinedStr.values>Constant(value=str)',  # closed_walk:139
    'JoinedStr.values>FormattedValue(value=Attribute,conversion=-1,format_spec=-)',  # closed_walk:289
    'JoinedStr.values>FormattedValue(value=Attribute,conversion=114,format_spec=-)',  # test_a1_identity_formation:3849
    'JoinedStr.values>FormattedValue(value=BinOp,conversion=-1,format_spec=-)',  # closed_walk:139
    'JoinedStr.values>FormattedValue(value=BoolOp,conversion=-1,format_spec=-)',  # test_a1_identity_formation:1359
    'JoinedStr.values>FormattedValue(value=Call,conversion=-1,format_spec=-)',  # closed_walk:149
    'JoinedStr.values>FormattedValue(value=Call,conversion=114,format_spec=-)',  # test_a1_identity_formation:137
    'JoinedStr.values>FormattedValue(value=IfExp,conversion=-1,format_spec=-)',  # test_match_hold_admission_gate_pg (a30d37f6):531
    'JoinedStr.values>FormattedValue(value=Name,conversion=-1,format_spec=-)',  # closed_walk:139
    'JoinedStr.values>FormattedValue(value=Name,conversion=114,format_spec=-)',  # closed_walk:1267
    'JoinedStr.values>FormattedValue(value=Subscript,conversion=-1,format_spec=-)',  # closed_walk:1502
    'JoinedStr.values>FormattedValue(value=Subscript,conversion=114,format_spec=-)',  # test_match_hold_admission_gate_pg (a30d37f6):461
    'Lambda.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):201
    'Lambda.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',  # closed_walk:1767
    "Lambda.body>Attribute(value=Name,attr='lineno',ctx=Load)",  # test_a1_identity_formation:898
    'Lambda.body>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1767
    'Lambda.body>Call(func=Name,args=[Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):201
    'List.ctx>Load()',  # closed_walk:70
    "List.elts>Attribute(value=Name,attr='AST',ctx=Load)",  # closed_walk:268
    "List.elts>Attribute(value=Name,attr='elt',ctx=Load)",  # closed_walk:1591
    "List.elts>Attribute(value=Name,attr='id',ctx=Load)",  # test_a1_identity_formation:1114
    "List.elts>Attribute(value=Name,attr='key',ctx=Load)",  # closed_walk:1591
    "List.elts>Attribute(value=Name,attr='target',ctx=Load)",  # closed_walk:327
    "List.elts>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:838
    'List.elts>BinOp(left=Constant,op=Add,right=Call)',  # test_a1_identity_formation:4584
    'List.elts>BinOp(left=IfExp,op=Add,right=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):1832
    'List.elts>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:847
    'List.elts>Constant(value=NoneType)',  # closed_walk:1010
    'List.elts>Constant(value=str)',  # closed_walk:1111
    'List.elts>Dict(keys=[],values=[])',  # closed_walk:954
    'List.elts>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:2172
    'List.elts>List(elts=[],ctx=Load)',  # closed_walk:1057
    'List.elts>Name(id=str,ctx=Load)',  # closed_walk:845
    'List.elts>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1006
    'List.elts>Tuple(elts=[Attribute|Constant],ctx=Load)',  # test_a1_identity_formation:1028
    'List.elts>Tuple(elts=[Call|Constant],ctx=Load)',  # test_a1_identity_formation:2450
    'List.elts>Tuple(elts=[Call|Constant|Name],ctx=Load)',  # test_a1_identity_formation:4541
    'List.elts>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:1089
    'List.elts>Tuple(elts=[Constant|JoinedStr],ctx=Load)',  # test_a1_identity_formation:1022
    'List.elts>Tuple(elts=[Constant|Starred],ctx=Load)',  # test_a1_identity_formation:4567
    "ListComp.elt>Attribute(value=Name,attr='arg',ctx=Load)",  # closed_walk:378
    "ListComp.elt>Attribute(value=Name,attr='id',ctx=Load)",  # test_a1_identity_formation:1117
    "ListComp.elt>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:1620
    'ListComp.elt>BinOp(left=Constant,op=Add,right=Name)',  # test_a1_identity_formation:2375
    'ListComp.elt>BinOp(left=Name,op=Add,right=List)',  # closed_walk:1059
    'ListComp.elt>BinOp(left=Name,op=Add,right=Name)',  # closed_walk:985
    'ListComp.elt>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:2448
    'ListComp.elt>Call(func=Attribute,args=[Name],keywords=[])',  # test_a1_identity_formation:1166
    'ListComp.elt>Call(func=Attribute,args=[],keywords=[keyword])',  # closed_walk:962
    'ListComp.elt>Call(func=Name,args=[Name],keywords=[])',  # test_a1_identity_formation:37
    'ListComp.elt>Call(func=Name,args=[Name],keywords=[keyword])',  # closed_walk:960
    'ListComp.elt>IfExp(test=Compare,body=Subscript,orelse=Constant)',  # closed_walk:1207
    'ListComp.elt>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:1487
    'ListComp.elt>Name(id=str,ctx=Load)',  # closed_walk:177
    'ListComp.elt>Tuple(elts=[BinOp|Subscript],ctx=Load)',  # test_a1_identity_formation:2940
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[Call],is_async=0)',  # closed_walk:177
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[Compare],is_async=0)',  # closed_walk:436
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[Name],is_async=0)',  # closed_walk:1576
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[UnaryOp],is_async=0)',  # closed_walk:785
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[],is_async=0)',  # closed_walk:1620
    'ListComp.generators>comprehension(target=Name,iter=BinOp,ifs=[],is_async=0)',  # closed_walk:378
    'ListComp.generators>comprehension(target=Name,iter=Call,ifs=[BoolOp],is_async=0)',  # closed_walk:659
    'ListComp.generators>comprehension(target=Name,iter=Call,ifs=[Call],is_async=0)',  # test_a1_identity_formation:1208
    'ListComp.generators>comprehension(target=Name,iter=Call,ifs=[Compare],is_async=0)',  # test_a1_identity_formation:1255
    'ListComp.generators>comprehension(target=Name,iter=Call,ifs=[UnaryOp],is_async=0)',  # test_a1_identity_formation:2940
    'ListComp.generators>comprehension(target=Name,iter=Call,ifs=[],is_async=0)',  # closed_walk:1059
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Call],is_async=0)',  # test_a1_identity_formation:1500
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # closed_walk:960
    'ListComp.generators>comprehension(target=Name,iter=Subscript,ifs=[Name],is_async=0)',  # closed_walk:1245
    'ListComp.generators>comprehension(target=Name,iter=Subscript,ifs=[],is_async=0)',  # closed_walk:1967
    'ListComp.generators>comprehension(target=Name,iter=Tuple,ifs=[Call],is_async=0)',  # test_a1_identity_formation:2186
    'ListComp.generators>comprehension(target=Name,iter=Tuple,ifs=[Compare],is_async=0)',  # closed_walk:379
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Call],is_async=0)',  # test_a1_identity_formation:1024
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Compare],is_async=0)',  # test_a1_identity_formation:2265
    'ListComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # test_a1_identity_formation:2180
    'ListComp.generators>comprehension(target=Tuple,iter=Name,ifs=[Compare],is_async=0)',  # test_a1_identity_formation:1496
    'ListComp.generators>comprehension(target=Tuple,iter=Name,ifs=[],is_async=0)',  # closed_walk:636
    'ListComp.generators>comprehension(target=Tuple,iter=Subscript,ifs=[BoolOp],is_async=0)',  # test_a1_identity_formation:1489
    'Name.ctx>Load()',  # closed_walk:71
    'Name.ctx>Store()',  # closed_walk:70
    'Raise.cause>Constant(value=NoneType)',  # closed_walk:1103
    'Raise.exc>Call(func=Name,args=[Constant],keywords=[])',  # closed_walk:1364
    'Raise.exc>Call(func=Name,args=[Constant|Dict|Name],keywords=[])',  # test_a1_identity_formation:3455
    'Raise.exc>Call(func=Name,args=[Tuple],keywords=[])',  # closed_walk:147
    "Return.value>Attribute(value=Attribute,attr='attr',ctx=Load)",  # test_a1_identity_formation:524
    "Return.value>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:544
    'Return.value>Await(value=Call)',  # test_a1_identity_formation:3457
    'Return.value>BinOp(left=BinOp,op=Add,right=List)',  # test_match_hold_admission_gate_pg (a30d37f6):1832
    'Return.value>BinOp(left=Call,op=Add,right=Call)',  # test_a1_identity_formation:1483
    'Return.value>BinOp(left=Name,op=Add,right=List)',  # test_a1_identity_formation:2220
    'Return.value>BoolOp(op=And,values=[Call])',  # closed_walk:1289
    'Return.value>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:667
    'Return.value>BoolOp(op=And,values=[Call|Compare|UnaryOp])',  # test_a1_identity_formation:849
    'Return.value>BoolOp(op=And,values=[Compare])',  # closed_walk:604
    'Return.value>BoolOp(op=Or,values=[BoolOp|Call])',  # closed_walk:692
    'Return.value>BoolOp(op=Or,values=[Call|Constant])',  # test_a1_identity_formation:1073
    'Return.value>BoolOp(op=Or,values=[Call|List])',  # closed_walk:1025
    'Return.value>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:793
    'Return.value>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:622
    'Return.value>Call(func=Attribute,args=[BinOp],keywords=[])',  # test_a1_identity_formation:2371
    'Return.value>Call(func=Attribute,args=[BinOp|Name],keywords=[])',  # test_a1_identity_formation:3693
    'Return.value>Call(func=Attribute,args=[Call],keywords=[])',  # test_a1_identity_formation:2924
    'Return.value>Call(func=Attribute,args=[Call|Name],keywords=[])',  # closed_walk:1515
    'Return.value>Call(func=Attribute,args=[Call|Name],keywords=[keyword])',  # test_a1_identity_formation:755
    'Return.value>Call(func=Attribute,args=[IfExp|Name],keywords=[])',  # test_a1_identity_formation:4486
    'Return.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:654
    'Return.value>Call(func=Attribute,args=[Name|Subscript],keywords=[keyword])',  # test_a1_identity_formation:536
    'Return.value>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:355
    'Return.value>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1842
    'Return.value>Call(func=Name,args=[Attribute|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):672
    'Return.value>Call(func=Name,args=[BinOp],keywords=[])',  # closed_walk:281
    'Return.value>Call(func=Name,args=[BinOp|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1061
    'Return.value>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:494
    'Return.value>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:127
    'Return.value>Call(func=Name,args=[IfExp],keywords=[])',  # test_a1_identity_formation:99
    'Return.value>Call(func=Name,args=[List],keywords=[])',  # closed_walk:847
    'Return.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:663
    'Return.value>Call(func=Name,args=[Name],keywords=[keyword])',  # test_a1_identity_formation:1086
    'Return.value>Call(func=Name,args=[Name|Subscript],keywords=[])',  # closed_walk:1504
    'Return.value>Call(func=Name,args=[Starred],keywords=[])',  # closed_walk:1522
    'Return.value>Call(func=Name,args=[Starred],keywords=[keyword])',  # test_a1_identity_formation:4625
    'Return.value>Call(func=Name,args=[Subscript],keywords=[])',  # closed_walk:865
    'Return.value>Call(func=Name,args=[],keywords=[])',  # closed_walk:1885
    'Return.value>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:766
    'Return.value>Compare(left=Call,ops=[In],comparators=[Call])',  # closed_walk:687
    'Return.value>Compare(left=Name,ops=[Is],comparators=[Constant])',  # test_a1_identity_formation:1579
    'Return.value>Constant(value=NoneType)',  # closed_walk:176
    'Return.value>Constant(value=bool)',  # closed_walk:126
    'Return.value>Constant(value=str)',  # closed_walk:1251
    'Return.value>Dict(keys=[],values=[])',  # test_a1_identity_formation:1145
    'Return.value>DictComp(key=Name,value=Tuple,generators=[comprehension])',  # closed_walk:920
    'Return.value>IfExp(test=Attribute,body=Subscript,orelse=Constant)',  # test_a1_identity_formation:43
    'Return.value>IfExp(test=BoolOp,body=Constant,orelse=BinOp)',  # closed_walk:939
    'Return.value>IfExp(test=BoolOp,body=Constant,orelse=Constant)',  # closed_walk:1258
    'Return.value>IfExp(test=BoolOp,body=Name,orelse=Constant)',  # closed_walk:517
    'Return.value>IfExp(test=BoolOp,body=Subscript,orelse=Constant)',  # closed_walk:1276
    'Return.value>IfExp(test=Call,body=Attribute,orelse=Constant)',  # closed_walk:368
    'Return.value>IfExp(test=Call,body=Call,orelse=Call)',  # test_a1_identity_formation:3676
    'Return.value>IfExp(test=Call,body=Call,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):394
    'Return.value>IfExp(test=Call,body=List,orelse=Constant)',  # closed_walk:845
    'Return.value>IfExp(test=Call,body=List,orelse=List)',  # test_a1_identity_formation:1089
    'Return.value>IfExp(test=Call,body=Name,orelse=Constant)',  # closed_walk:769
    'Return.value>IfExp(test=Call,body=Tuple,orelse=Call)',  # closed_walk:677
    'Return.value>IfExp(test=Compare,body=Constant,orelse=IfExp)',  # closed_walk:1104
    'Return.value>IfExp(test=Compare,body=Constant,orelse=JoinedStr)',  # test_match_hold_admission_gate_pg (a30d37f6):601
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Subscript)',  # test_a1_identity_formation:1350
    'Return.value>IfExp(test=Compare,body=Subscript,orelse=Constant)',  # closed_walk:179
    'Return.value>IfExp(test=Name,body=Call,orelse=Call)',  # test_a1_identity_formation:1166
    'Return.value>IfExp(test=Name,body=JoinedStr,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):554
    'Return.value>IfExp(test=Name,body=Tuple,orelse=Tuple)',  # test_a1_identity_formation:3195
    'Return.value>JoinedStr(values=[Constant|FormattedValue])',  # test_match_hold_admission_gate_pg (a30d37f6):577
    'Return.value>List(elts=[Attribute],ctx=Load)',  # closed_walk:838
    'Return.value>List(elts=[Constant],ctx=Load)',  # closed_walk:1010
    'Return.value>List(elts=[JoinedStr],ctx=Load)',  # test_a1_identity_formation:2172
    'Return.value>List(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:4540
    'Return.value>List(elts=[],ctx=Load)',  # test_a1_identity_formation:1122
    'Return.value>ListComp(elt=Attribute,generators=[comprehension])',  # closed_walk:378
    'Return.value>ListComp(elt=Name,generators=[comprehension])',  # closed_walk:636
    'Return.value>ListComp(elt=Tuple,generators=[comprehension])',  # test_a1_identity_formation:2940
    'Return.value>Name(id=str,ctx=Load)',  # closed_walk:77
    'Return.value>Subscript(value=Attribute,slice=Call,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):707
    'Return.value>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):671
    'Return.value>Subscript(value=Attribute,slice=Name,ctx=Load)',  # closed_walk:1881
    'Return.value>Subscript(value=Call,slice=Constant,ctx=Load)',  # test_a1_identity_formation:48
    'Return.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:510
    'Return.value>Subscript(value=Name,slice=Name,ctx=Load)',  # test_a1_identity_formation:704
    'Return.value>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:189
    'Return.value>Tuple(elts=[Attribute],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):1350
    'Return.value>Tuple(elts=[BinOp|Call],ctx=Load)',  # closed_walk:167
    'Return.value>Tuple(elts=[Call|Constant],ctx=Load)',  # closed_walk:511
    'Return.value>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:791
    'Return.value>Tuple(elts=[Constant|List|Name|Tuple],ctx=Load)',  # test_a1_identity_formation:1009
    'Return.value>Tuple(elts=[Constant|List|Tuple],ctx=Load)',  # test_a1_identity_formation:1006
    'Return.value>Tuple(elts=[Constant|Name],ctx=Load)',  # test_a1_identity_formation:935
    'Return.value>Tuple(elts=[List|Subscript],ctx=Load)',  # test_a1_identity_formation:886
    'Return.value>Tuple(elts=[List|Tuple],ctx=Load)',  # test_a1_identity_formation:892
    'Return.value>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:790
    'Return.value>Tuple(elts=[Name|Tuple],ctx=Load)',  # test_a1_identity_formation:1448
    'Set.elts>Call(func=Name,args=[Attribute],keywords=[])',  # test_a1_identity_formation:2292
    'Set.elts>Constant(value=str)',  # closed_walk:1821
    'Set.elts>Name(id=str,ctx=Load)',  # test_a1_identity_formation:1256
    "SetComp.elt>Attribute(value=Name,attr='id',ctx=Load)",  # test_a1_identity_formation:1207
    "SetComp.elt>Attribute(value=Name,attr='lineno',ctx=Load)",  # test_a1_identity_formation:1446
    "SetComp.elt>Attribute(value=Subscript,attr='id',ctx=Load)",  # test_a1_identity_formation:2210
    'SetComp.elt>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:932
    'SetComp.elt>Name(id=str,ctx=Load)',  # closed_walk:1238
    'SetComp.elt>Tuple(elts=[Name|Subscript],ctx=Load)',  # test_a1_identity_formation:1108
    'SetComp.generators>comprehension(target=Name,iter=Call,ifs=[BoolOp],is_async=0)',  # test_a1_identity_formation:2210
    'SetComp.generators>comprehension(target=Name,iter=Call,ifs=[Call],is_async=0)',  # closed_walk:932
    'SetComp.generators>comprehension(target=Name,iter=Call,ifs=[Compare],is_async=0)',  # test_a1_identity_formation:1446
    'SetComp.generators>comprehension(target=Name,iter=Call,ifs=[],is_async=0)',  # closed_walk:932
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',  # closed_walk:1101
    'SetComp.generators>comprehension(target=Tuple,iter=Call,ifs=[BoolOp],is_async=0)',  # closed_walk:1239
    'SetComp.generators>comprehension(target=Tuple,iter=Call,ifs=[Call],is_async=0)',  # test_a1_identity_formation:1427
    'SetComp.generators>comprehension(target=Tuple,iter=Call,ifs=[],is_async=0)',  # test_a1_identity_formation:4727
    'SetComp.generators>comprehension(target=Tuple,iter=Name,ifs=[Compare],is_async=0)',  # test_a1_identity_formation:1108
    'SetComp.generators>comprehension(target=Tuple,iter=Name,ifs=[],is_async=0)',  # closed_walk:1238
    'Slice.lower>BinOp(left=Call,op=Sub,right=Call)',  # closed_walk:1967
    'Slice.lower>BinOp(left=Name,op=Add,right=Constant)',  # closed_walk:916
    'Slice.lower>BinOp(left=Subscript,op=Add,right=Constant)',  # test_a1_identity_formation:1352
    'Slice.lower>Call(func=Name,args=[Attribute],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):705
    'Slice.lower>Constant(value=int)',  # closed_walk:1186
    'Slice.lower>Name(id=str,ctx=Load)',  # closed_walk:1504
    'Slice.upper>BinOp(left=BinOp,op=Add,right=Call)',  # closed_walk:1218
    'Slice.upper>BinOp(left=Name,op=Add,right=Constant)',  # test_a1_identity_formation:835
    'Slice.upper>BinOp(left=Subscript,op=Add,right=Constant)',  # test_a1_identity_formation:1394
    'Slice.upper>Constant(value=int)',  # closed_walk:1245
    'Slice.upper>Name(id=str,ctx=Load)',  # test_a1_identity_formation:486
    'Slice.upper>UnaryOp(op=USub,operand=Constant)',  # closed_walk:1202
    'Starred.ctx>Load()',  # closed_walk:784
    'Starred.value>Call(func=Name,args=[Constant|List],keywords=[])',  # test_a1_identity_formation:4568
    'Starred.value>Call(func=Name,args=[Constant|List],keywords=[keyword])',  # test_a1_identity_formation:4602
    'Starred.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:784
    'Starred.value>GeneratorExp(elt=Subscript,generators=[comprehension])',  # test_a1_identity_formation:4399
    'Starred.value>ListComp(elt=Call,generators=[comprehension])',  # test_a1_identity_formation:1166
    'Starred.value>Name(id=str,ctx=Load)',  # closed_walk:1064
    'Subscript.ctx>Load()',  # closed_walk:146
    'Subscript.ctx>Store()',  # closed_walk:140
    "Subscript.slice>Attribute(value=Name,attr='__file__',ctx=Load)",  # test_a1_identity_formation:3667
    "Subscript.slice>Attribute(value=Name,attr='__name__',ctx=Load)",  # test_a1_identity_formation:3670
    "Subscript.slice>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:865
    "Subscript.slice>Attribute(value=Name,attr='name',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):64
    "Subscript.slice>Attribute(value=Name,attr='stem',ctx=Load)",  # test_a1_identity_formation:3865
    "Subscript.slice>Attribute(value=Subscript,attr='id',ctx=Load)",  # test_a1_identity_formation:1160
    'Subscript.slice>BinOp(left=Constant,op=Add,right=Attribute)',  # closed_walk:1545
    'Subscript.slice>BinOp(left=Constant,op=Add,right=Name)',  # closed_walk:1603
    'Subscript.slice>BinOp(left=Name,op=Add,right=Constant)',  # closed_walk:1225
    'Subscript.slice>BinOp(left=Name,op=Add,right=IfExp)',  # test_a1_identity_formation:1109
    'Subscript.slice>BinOp(left=Name,op=Sub,right=Constant)',  # closed_walk:1230
    'Subscript.slice>BoolOp(op=Or,values=[Attribute])',  # test_a1_identity_formation:3820
    'Subscript.slice>Call(func=Attribute,args=[Constant],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):707
    'Subscript.slice>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1040
    'Subscript.slice>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:156
    'Subscript.slice>Constant(value=int)',  # closed_walk:146
    'Subscript.slice>Constant(value=str)',  # closed_walk:1503
    'Subscript.slice>JoinedStr(values=[Constant|FormattedValue])',  # test_a1_identity_formation:1282
    'Subscript.slice>Name(id=str,ctx=Load)',  # closed_walk:140
    'Subscript.slice>Slice(lower=-,upper=-,step=-)',  # test_a1_identity_formation:1439
    'Subscript.slice>Slice(lower=-,upper=BinOp,step=-)',  # test_a1_identity_formation:1394
    'Subscript.slice>Slice(lower=-,upper=Constant,step=-)',  # closed_walk:1502
    'Subscript.slice>Slice(lower=-,upper=Name,step=-)',  # test_a1_identity_formation:486
    'Subscript.slice>Slice(lower=-,upper=UnaryOp,step=-)',  # closed_walk:1202
    'Subscript.slice>Slice(lower=BinOp,upper=-,step=-)',  # closed_walk:916
    'Subscript.slice>Slice(lower=BinOp,upper=BinOp,step=-)',  # closed_walk:1218
    'Subscript.slice>Slice(lower=Call,upper=-,step=-)',  # test_match_hold_admission_gate_pg (a30d37f6):705
    'Subscript.slice>Slice(lower=Constant,upper=-,step=-)',  # closed_walk:1186
    'Subscript.slice>Slice(lower=Constant,upper=Constant,step=-)',  # closed_walk:1245
    'Subscript.slice>Slice(lower=Constant,upper=UnaryOp,step=-)',  # test_match_hold_admission_gate_pg (a30d37f6):787
    'Subscript.slice>Slice(lower=Name,upper=-,step=-)',  # closed_walk:1504
    'Subscript.slice>Slice(lower=Name,upper=BinOp,step=-)',  # test_a1_identity_formation:835
    'Subscript.slice>Slice(lower=Name,upper=Name,step=-)',  # test_a1_identity_formation:1801
    'Subscript.slice>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1041
    'Subscript.slice>Tuple(elts=[Attribute|Name],ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):239
    'Subscript.slice>UnaryOp(op=USub,operand=Constant)',  # closed_walk:719
    "Subscript.value>Attribute(value=Attribute,attr='elts',ctx=Load)",  # test_a1_identity_formation:2248
    "Subscript.value>Attribute(value=Attribute,attr='met',ctx=Load)",  # closed_walk:1503
    "Subscript.value>Attribute(value=Call,attr='body',ctx=Load)",  # test_a1_identity_formation:2165
    "Subscript.value>Attribute(value=Name,attr='_done',ctx=Load)",  # closed_walk:156
    "Subscript.value>Attribute(value=Name,attr='_rows',ctx=Load)",  # test_a1_identity_formation:43
    "Subscript.value>Attribute(value=Name,attr='admitted',ctx=Load)",  # closed_walk:157
    "Subscript.value>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:146
    "Subscript.value>Attribute(value=Name,attr='body',ctx=Load)",  # closed_walk:1296
    "Subscript.value>Attribute(value=Name,attr='cache',ctx=Load)",  # test_a1_identity_formation:3667
    "Subscript.value>Attribute(value=Name,attr='comparators',ctx=Load)",  # closed_walk:902
    "Subscript.value>Attribute(value=Name,attr='effects',ctx=Load)",  # closed_walk:1504
    "Subscript.value>Attribute(value=Name,attr='elts',ctx=Load)",  # test_a1_identity_formation:2206
    "Subscript.value>Attribute(value=Name,attr='gate_kinds',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):343
    "Subscript.value>Attribute(value=Name,attr='helpers',ctx=Load)",  # closed_walk:1881
    "Subscript.value>Attribute(value=Name,attr='modules',ctx=Load)",  # test_a1_identity_formation:722
    "Subscript.value>Attribute(value=Name,attr='ops',ctx=Load)",  # closed_walk:901
    "Subscript.value>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_a1_identity_formation:1365
    "Subscript.value>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):367
    "Subscript.value>Attribute(value=Name,attr='sites',ctx=Load)",  # closed_walk:906
    "Subscript.value>Attribute(value=Name,attr='targets',ctx=Load)",  # closed_walk:944
    "Subscript.value>Attribute(value=Name,attr='trees',ctx=Load)",  # closed_walk:140
    "Subscript.value>Attribute(value=Subscript,attr='elts',ctx=Load)",  # test_a1_identity_formation:2210
    "Subscript.value>Attribute(value=Subscript,attr='names',ctx=Load)",  # closed_walk:788
    'Subscript.value>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:641
    'Subscript.value>Call(func=Attribute,args=[Constant],keywords=[])',  # closed_walk:461
    'Subscript.value>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:1502
    'Subscript.value>Call(func=Name,args=[Call],keywords=[])',  # test_a1_identity_formation:48
    'Subscript.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1829
    'Subscript.value>Name(id=str,ctx=Load)',  # closed_walk:179
    'Subscript.value>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:1103
    'Subscript.value>Subscript(value=Attribute,slice=Name,ctx=Load)',  # closed_walk:906
    'Subscript.value>Subscript(value=Name,slice=BinOp,ctx=Load)',  # closed_walk:1229
    'Subscript.value>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:672
    'Subscript.value>Subscript(value=Name,slice=Name,ctx=Load)',  # closed_walk:188
    'Subscript.value>Subscript(value=Name,slice=UnaryOp,ctx=Load)',  # closed_walk:1201
    'Subscript.value>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:906
    'Subscript.value>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:4535
    'Try.body>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # closed_walk:164
    'Try.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:144
    'Try.body>Assign(targets=[Name],value=IfExp,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):409
    'Try.body>Assign(targets=[Name],value=ListComp,type_comment=-)',  # test_a1_identity_formation:1017
    'Try.body>Assign(targets=[Name],value=SetComp,type_comment=-)',  # closed_walk:1101
    'Try.body>Assign(targets=[Subscript],value=Call,type_comment=-)',  # test_a1_identity_formation:1160
    'Try.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # closed_walk:1180
    'Try.body>Expr(value=Call)',  # test_a1_identity_formation:1003
    'Try.body>For(target=Tuple,iter=Call,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:1054
    'Try.body>If(test=BoolOp,body=[Return],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):586
    'Try.body>If(test=Compare,body=[Assign],orelse=[])',  # test_a1_identity_formation:634
    'Try.body>If(test=UnaryOp,body=[Expr],orelse=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1346
    'Try.body>Return(value=Call)',  # closed_walk:1515
    'Try.body>Return(value=Compare)',  # test_a1_identity_formation:766
    'Try.finalbody>Expr(value=Call)',  # closed_walk:1891
    'Try.handlers>ExceptHandler(type=Attribute,name=str,body=[Assign|Raise])',  # closed_walk:145
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Assign])',  # closed_walk:165
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Return])',  # test_a1_identity_formation:767
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign])',  # test_match_hold_admission_gate_pg (a30d37f6):347
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign|Expr])',  # test_a1_identity_formation:2253
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Assign|Expr|Return])',  # test_match_hold_admission_gate_pg (a30d37f6):293
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Continue|Expr])',  # test_a1_identity_formation:1237
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr])',  # closed_walk:1516
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr|Return])',  # test_a1_identity_formation:1087
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Raise])',  # closed_walk:1102
    'Try.handlers>ExceptHandler(type=Name,name=str,body=[Return])',  # test_a1_identity_formation:885
    'Try.handlers>ExceptHandler(type=Tuple,name=-,body=[Assign])',  # closed_walk:192
    'Try.handlers>ExceptHandler(type=Tuple,name=-,body=[Pass])',  # test_a1_identity_formation:636
    'Try.handlers>ExceptHandler(type=Tuple,name=-,body=[Return])',  # closed_walk:781
    'Try.orelse>Assign(targets=[Name],value=Call,type_comment=-)',  # test_a1_identity_formation:2297
    'Try.orelse>If(test=Name,body=[Assign],orelse=[If])',  # test_match_hold_admission_gate_pg (a30d37f6):351
    'Try.orelse>If(test=Name,body=[Expr],orelse=[])',  # test_a1_identity_formation:2299
    'Tuple.ctx>Load()',  # closed_walk:73
    'Tuple.ctx>Store()',  # closed_walk:138
    "Tuple.elts>Attribute(value=Name,attr='AnnAssign',ctx=Load)",  # closed_walk:326
    "Tuple.elts>Attribute(value=Name,attr='Assign',ctx=Load)",  # closed_walk:326
    "Tuple.elts>Attribute(value=Name,attr='AsyncFor',ctx=Load)",  # closed_walk:933
    "Tuple.elts>Attribute(value=Name,attr='AsyncFunctionDef',ctx=Load)",  # closed_walk:450
    "Tuple.elts>Attribute(value=Name,attr='Attribute',ctx=Load)",  # closed_walk:316
    "Tuple.elts>Attribute(value=Name,attr='AugAssign',ctx=Load)",  # closed_walk:320
    "Tuple.elts>Attribute(value=Name,attr='Await',ctx=Load)",  # closed_walk:1282
    "Tuple.elts>Attribute(value=Name,attr='BoolOp',ctx=Load)",  # test_a1_identity_formation:1212
    "Tuple.elts>Attribute(value=Name,attr='Break',ctx=Load)",  # closed_walk:1150
    "Tuple.elts>Attribute(value=Name,attr='Call',ctx=Load)",  # test_a1_identity_formation:1213
    "Tuple.elts>Attribute(value=Name,attr='ClassDef',ctx=Load)",  # closed_walk:1128
    "Tuple.elts>Attribute(value=Name,attr='Compare',ctx=Load)",  # test_a1_identity_formation:1212
    "Tuple.elts>Attribute(value=Name,attr='Constant',ctx=Load)",  # test_a1_identity_formation:1213
    "Tuple.elts>Attribute(value=Name,attr='Continue',ctx=Load)",  # closed_walk:1150
    "Tuple.elts>Attribute(value=Name,attr='Del',ctx=Load)",  # closed_walk:311
    "Tuple.elts>Attribute(value=Name,attr='Delete',ctx=Load)",  # closed_walk:479
    "Tuple.elts>Attribute(value=Name,attr='Expr',ctx=Load)",  # closed_walk:2014
    "Tuple.elts>Attribute(value=Name,attr='For',ctx=Load)",  # closed_walk:933
    "Tuple.elts>Attribute(value=Name,attr='FunctionDef',ctx=Load)",  # closed_walk:450
    "Tuple.elts>Attribute(value=Name,attr='Global',ctx=Load)",  # closed_walk:464
    "Tuple.elts>Attribute(value=Name,attr='Import',ctx=Load)",  # closed_walk:459
    "Tuple.elts>Attribute(value=Name,attr='ImportFrom',ctx=Load)",  # closed_walk:459
    "Tuple.elts>Attribute(value=Name,attr='Lambda',ctx=Load)",  # closed_walk:1128
    "Tuple.elts>Attribute(value=Name,attr='List',ctx=Load)",  # test_a1_identity_formation:1115
    "Tuple.elts>Attribute(value=Name,attr='Load',ctx=Load)",  # test_a1_identity_formation:1214
    "Tuple.elts>Attribute(value=Name,attr='MatchAs',ctx=Load)",  # closed_walk:467
    "Tuple.elts>Attribute(value=Name,attr='MatchStar',ctx=Load)",  # closed_walk:467
    "Tuple.elts>Attribute(value=Name,attr='Name',ctx=Load)",  # closed_walk:1546
    "Tuple.elts>Attribute(value=Name,attr='Nonlocal',ctx=Load)",  # closed_walk:464
    "Tuple.elts>Attribute(value=Name,attr='POSITIONAL_ONLY',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):700
    "Tuple.elts>Attribute(value=Name,attr='POSITIONAL_OR_KEYWORD',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):700
    "Tuple.elts>Attribute(value=Name,attr='Pass',ctx=Load)",  # closed_walk:2074
    "Tuple.elts>Attribute(value=Name,attr='Raise',ctx=Load)",  # test_a1_identity_formation:1187
    "Tuple.elts>Attribute(value=Name,attr='Return',ctx=Load)",  # closed_walk:1282
    "Tuple.elts>Attribute(value=Name,attr='Store',ctx=Load)",  # closed_walk:311
    "Tuple.elts>Attribute(value=Name,attr='Subscript',ctx=Load)",  # closed_walk:316
    "Tuple.elts>Attribute(value=Name,attr='Tuple',ctx=Load)",  # test_a1_identity_formation:1115
    "Tuple.elts>Attribute(value=Name,attr='UnaryOp',ctx=Load)",  # test_a1_identity_formation:1212
    "Tuple.elts>Attribute(value=Name,attr='While',ctx=Load)",  # closed_walk:933
    "Tuple.elts>Attribute(value=Name,attr='Yield',ctx=Load)",  # closed_walk:2090
    "Tuple.elts>Attribute(value=Name,attr='YieldFrom',ctx=Load)",  # closed_walk:2090
    "Tuple.elts>Attribute(value=Name,attr='__file__',ctx=Load)",  # test_a1_identity_formation:3668
    "Tuple.elts>Attribute(value=Name,attr='__module__',ctx=Load)",  # closed_walk:1879
    "Tuple.elts>Attribute(value=Name,attr='__qualname__',ctx=Load)",  # closed_walk:1879
    "Tuple.elts>Attribute(value=Name,attr='asname',ctx=Load)",  # closed_walk:73
    "Tuple.elts>Attribute(value=Name,attr='boolop',ctx=Load)",  # test_a1_identity_formation:1214
    "Tuple.elts>Attribute(value=Name,attr='cmpop',ctx=Load)",  # test_a1_identity_formation:1214
    "Tuple.elts>Attribute(value=Name,attr='col_offset',ctx=Load)",  # closed_walk:975
    "Tuple.elts>Attribute(value=Name,attr='end_lineno',ctx=Load)",  # test_a1_identity_formation:2934
    "Tuple.elts>Attribute(value=Name,attr='kwarg',ctx=Load)",  # closed_walk:379
    "Tuple.elts>Attribute(value=Name,attr='lineno',ctx=Load)",  # closed_walk:73
    "Tuple.elts>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:73
    "Tuple.elts>Attribute(value=Name,attr='problems',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1350
    "Tuple.elts>Attribute(value=Name,attr='problems',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):236
    "Tuple.elts>Attribute(value=Name,attr='seen',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):1350
    "Tuple.elts>Attribute(value=Name,attr='seen',ctx=Store)",  # test_match_hold_admission_gate_pg (a30d37f6):236
    "Tuple.elts>Attribute(value=Name,attr='session',ctx=Load)",  # closed_walk:677
    "Tuple.elts>Attribute(value=Name,attr='unaryop',ctx=Load)",  # test_a1_identity_formation:1215
    "Tuple.elts>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:945
    "Tuple.elts>Attribute(value=Name,attr='vararg',ctx=Load)",  # closed_walk:379
    "Tuple.elts>Attribute(value=Name,attr='where',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):239
    "Tuple.elts>Attribute(value=Subscript,attr='id',ctx=Load)",  # closed_walk:945
    "Tuple.elts>Attribute(value=Subscript,attr='lineno',ctx=Load)",  # test_a1_identity_formation:1264
    'Tuple.elts>BinOp(left=Attribute,op=Div,right=Constant)',  # test_a1_identity_formation:3863
    'Tuple.elts>BinOp(left=Attribute,op=Sub,right=Constant)',  # closed_walk:167
    'Tuple.elts>BinOp(left=Constant,op=Add,right=Call)',  # closed_walk:1241
    'Tuple.elts>BinOp(left=JoinedStr,op=Add,right=IfExp)',  # test_match_hold_admission_gate_pg (a30d37f6):366
    'Tuple.elts>BinOp(left=Name,op=Add,right=Call)',  # closed_walk:135
    'Tuple.elts>BinOp(left=Name,op=Add,right=Constant)',  # test_a1_identity_formation:2940
    'Tuple.elts>BinOp(left=Name,op=Sub,right=Constant)',  # test_a1_identity_formation:3203
    'Tuple.elts>BoolOp(op=Or,values=[Attribute|Subscript])',  # test_a1_identity_formation:1069
    'Tuple.elts>BoolOp(op=Or,values=[Name|Subscript])',  # test_a1_identity_formation:1088
    'Tuple.elts>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:938
    'Tuple.elts>Call(func=Attribute,args=[Attribute|Lambda|Name],keywords=[])',  # closed_walk:1765
    'Tuple.elts>Call(func=Attribute,args=[BinOp|Name],keywords=[])',  # test_a1_identity_formation:3750
    'Tuple.elts>Call(func=Attribute,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:3739
    'Tuple.elts>Call(func=Attribute,args=[Constant],keywords=[])',  # test_a1_identity_formation:119
    'Tuple.elts>Call(func=Attribute,args=[Constant|Name],keywords=[])',  # test_a1_identity_formation:3703
    'Tuple.elts>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:167
    'Tuple.elts>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:471
    'Tuple.elts>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1124
    'Tuple.elts>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',  # closed_walk:136
    'Tuple.elts>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:511
    'Tuple.elts>Call(func=Name,args=[BinOp],keywords=[])',  # test_a1_identity_formation:1262
    'Tuple.elts>Call(func=Name,args=[BinOp],keywords=[keyword])',  # test_a1_identity_formation:2457
    'Tuple.elts>Call(func=Name,args=[BinOp|Name],keywords=[])',  # test_a1_identity_formation:2451
    'Tuple.elts>Call(func=Name,args=[BinOp|Name],keywords=[keyword])',  # test_a1_identity_formation:2461
    'Tuple.elts>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:915
    'Tuple.elts>Call(func=Name,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:3203
    'Tuple.elts>Call(func=Name,args=[Call|Name],keywords=[keyword])',  # test_a1_identity_formation:4557
    'Tuple.elts>Call(func=Name,args=[Constant],keywords=[])',  # test_a1_identity_formation:4516
    'Tuple.elts>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:149
    'Tuple.elts>Call(func=Name,args=[Constant|Name],keywords=[keyword])',  # test_a1_identity_formation:4544
    'Tuple.elts>Call(func=Name,args=[Constant|Subscript],keywords=[])',  # test_a1_identity_formation:4388
    'Tuple.elts>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:920
    'Tuple.elts>Call(func=Name,args=[Starred],keywords=[])',  # test_a1_identity_formation:4398
    'Tuple.elts>Call(func=Name,args=[Subscript],keywords=[])',  # test_a1_identity_formation:4385
    'Tuple.elts>Call(func=Name,args=[],keywords=[])',  # closed_walk:268
    'Tuple.elts>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',  # closed_walk:1237
    'Tuple.elts>Constant(value=NoneType)',  # closed_walk:73
    'Tuple.elts>Constant(value=bool)',  # closed_walk:1213
    'Tuple.elts>Constant(value=int)',  # closed_walk:1183
    'Tuple.elts>Constant(value=str)',  # closed_walk:511
    'Tuple.elts>Dict(keys=[],values=[])',  # closed_walk:931
    'Tuple.elts>IfExp(test=BinOp,body=Constant,orelse=Constant)',  # test_match_hold_admission_gate_pg (a30d37f6):355
    'Tuple.elts>IfExp(test=Compare,body=Call,orelse=Constant)',  # test_a1_identity_formation:1310
    'Tuple.elts>IfExp(test=Compare,body=Constant,orelse=IfExp)',  # closed_walk:1832
    'Tuple.elts>IfExp(test=Compare,body=List,orelse=List)',  # test_a1_identity_formation:4392
    'Tuple.elts>JoinedStr(values=[Constant|FormattedValue])',  # closed_walk:147
    'Tuple.elts>List(elts=[Attribute],ctx=Load)',  # closed_walk:268
    'Tuple.elts>List(elts=[Name],ctx=Load)',  # test_a1_identity_formation:1013
    'Tuple.elts>List(elts=[Subscript],ctx=Load)',  # test_a1_identity_formation:1006
    'Tuple.elts>List(elts=[Tuple],ctx=Load)',  # test_a1_identity_formation:1022
    'Tuple.elts>List(elts=[],ctx=Load)',  # closed_walk:1124
    'Tuple.elts>Name(id=str,ctx=Load)',  # closed_walk:76
    'Tuple.elts>Name(id=str,ctx=Store)',  # closed_walk:138
    'Tuple.elts>Starred(value=Call,ctx=Load)',  # test_a1_identity_formation:4568
    'Tuple.elts>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # test_a1_identity_formation:886
    'Tuple.elts>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:1829
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:975
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Store)',  # test_match_hold_admission_gate_pg (a30d37f6):65
    'Tuple.elts>Subscript(value=Name,slice=Name,ctx=Load)',  # test_a1_identity_formation:2940
    'Tuple.elts>Subscript(value=Name,slice=Slice,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):317
    'Tuple.elts>Subscript(value=Name,slice=Slice,ctx=Store)',  # test_a1_identity_formation:1439
    'Tuple.elts>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:1103
    'Tuple.elts>Tuple(elts=[Attribute|Constant],ctx=Load)',  # closed_walk:73
    'Tuple.elts>Tuple(elts=[Attribute|JoinedStr],ctx=Load)',  # test_a1_identity_formation:906
    'Tuple.elts>Tuple(elts=[Attribute|Name],ctx=Load)',  # closed_walk:76
    'Tuple.elts>Tuple(elts=[Call],ctx=Load)',  # test_a1_identity_formation:1006
    'Tuple.elts>Tuple(elts=[Constant],ctx=Load)',  # closed_walk:1216
    'Tuple.elts>Tuple(elts=[Constant|JoinedStr],ctx=Load)',  # test_a1_identity_formation:892
    'Tuple.elts>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:1448
    'Tuple.elts>Tuple(elts=[Name],ctx=Store)',  # closed_walk:920
    'UnaryOp.op>Not()',  # closed_walk:448
    'UnaryOp.op>USub()',  # closed_walk:719
    "UnaryOp.operand>Attribute(value=Attribute,attr='args',ctx=Load)",  # closed_walk:763
    "UnaryOp.operand>Attribute(value=Attribute,attr='keywords',ctx=Load)",  # closed_walk:764
    "UnaryOp.operand>Attribute(value=Name,attr='_rows',ctx=Load)",  # test_a1_identity_formation:46
    "UnaryOp.operand>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:952
    "UnaryOp.operand>Attribute(value=Name,attr='held',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):75
    "UnaryOp.operand>Attribute(value=Name,attr='keywords',ctx=Load)",  # closed_walk:1078
    "UnaryOp.operand>Attribute(value=Name,attr='level',ctx=Load)",  # closed_walk:552
    "UnaryOp.operand>Attribute(value=Name,attr='module',ctx=Load)",  # closed_walk:1923
    "UnaryOp.operand>Attribute(value=Name,attr='orelse',ctx=Load)",  # test_a1_identity_formation:849
    'UnaryOp.operand>BinOp(left=Name,op=BitAnd,right=Name)',  # closed_walk:1253
    'UnaryOp.operand>BoolOp(op=And,values=[Attribute|Call|UnaryOp])',  # closed_walk:752
    'UnaryOp.operand>BoolOp(op=And,values=[Call])',  # closed_walk:785
    'UnaryOp.operand>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:523
    'UnaryOp.operand>BoolOp(op=And,values=[Call|Compare|Name])',  # test_a1_identity_formation:2279
    'UnaryOp.operand>BoolOp(op=And,values=[Call|Compare|Name|UnaryOp])',  # test_a1_identity_formation:2273
    'UnaryOp.operand>BoolOp(op=And,values=[Call|Compare|UnaryOp])',  # closed_walk:1077
    'UnaryOp.operand>BoolOp(op=And,values=[Call|Name])',  # closed_walk:910
    'UnaryOp.operand>BoolOp(op=And,values=[Compare])',  # test_a1_identity_formation:904
    'UnaryOp.operand>BoolOp(op=Or,values=[BoolOp|Compare])',  # test_a1_identity_formation:2230
    'UnaryOp.operand>BoolOp(op=Or,values=[Call])',  # closed_walk:732
    'UnaryOp.operand>Call(func=Attribute,args=[Attribute],keywords=[])',  # closed_walk:1044
    'UnaryOp.operand>Call(func=Attribute,args=[Attribute|Constant],keywords=[])',  # test_a1_identity_formation:1210
    'UnaryOp.operand>Call(func=Attribute,args=[Constant],keywords=[])',  # closed_walk:1855
    'UnaryOp.operand>Call(func=Attribute,args=[Constant|Subscript|Tuple],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):586
    'UnaryOp.operand>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:588
    'UnaryOp.operand>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:448
    'UnaryOp.operand>Call(func=Name,args=[Attribute|Call],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):655
    'UnaryOp.operand>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:699
    'UnaryOp.operand>Call(func=Name,args=[Attribute|Subscript],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):782
    'UnaryOp.operand>Call(func=Name,args=[Attribute|Tuple],keywords=[])',  # closed_walk:1730
    'UnaryOp.operand>Call(func=Name,args=[Constant|Name],keywords=[])',  # test_a1_identity_formation:763
    'UnaryOp.operand>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:1095
    'UnaryOp.operand>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:812
    'UnaryOp.operand>Call(func=Name,args=[Name],keywords=[keyword])',  # test_match_hold_admission_gate_pg (a30d37f6):1346
    'UnaryOp.operand>Call(func=Name,args=[Name|Tuple],keywords=[])',  # test_a1_identity_formation:583
    'UnaryOp.operand>Compare(left=Name,ops=[LtE],comparators=[BinOp])',  # test_a1_identity_formation:1209
    'UnaryOp.operand>Constant(value=int)',  # closed_walk:719
    'UnaryOp.operand>Name(id=str,ctx=Load)',  # closed_walk:701
    'UnaryOp.operand>Subscript(value=Name,slice=Constant,ctx=Load)',  # test_a1_identity_formation:1205
    'While.body>Assign(targets=[Name],value=Attribute,type_comment=-)',  # closed_walk:317
    'While.body>Assign(targets=[Name],value=BinOp,type_comment=-)',  # test_a1_identity_formation:1793
    'While.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:270
    'While.body>Assign(targets=[Name],value=Constant,type_comment=-)',  # test_a1_identity_formation:1794
    'While.body>Assign(targets=[Name],value=Subscript,type_comment=-)',  # closed_walk:1202
    'While.body>AugAssign(target=Name,op=Add,value=Constant)',  # test_a1_identity_formation:1800
    'While.body>Expr(value=Call)',  # closed_walk:1132
    'While.body>For(target=Tuple,iter=Call,body=[If],orelse=[],type_comment=-)',  # test_a1_identity_formation:2981
    'While.body>If(test=Call,body=[Continue],orelse=[])',  # closed_walk:1127
    'While.body>If(test=Call,body=[Expr],orelse=[])',  # closed_walk:1130
    'While.body>If(test=Compare,body=[AugAssign],orelse=[If])',  # test_a1_identity_formation:1796
    'While.body>If(test=Name,body=[Expr],orelse=[If])',  # closed_walk:272
    'While.body>While(test=Name,body=[AugAssign|If],orelse=[])',  # test_a1_identity_formation:1795
    'While.test>BoolOp(op=And,values=[Compare|Name])',  # closed_walk:1201
    'While.test>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:1169
    'While.test>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:316
    'While.test>Compare(left=Name,ops=[NotEq],comparators=[UnaryOp])',  # test_a1_identity_formation:1792
    'While.test>Name(id=str,ctx=Load)',  # closed_walk:269
    'While.test>UnaryOp(op=Not,operand=Call)',  # test_match_hold_admission_gate_pg (a30d37f6):109
    'arguments.args>arg(arg=str,annotation=-,type_comment=-)',  # closed_walk:66
    'arguments.defaults>Call(func=Name,args=[],keywords=[])',  # closed_walk:107
    'arguments.defaults>Constant(value=NoneType)',  # closed_walk:421
    'arguments.defaults>Constant(value=bool)',  # closed_walk:107
    'arguments.defaults>Constant(value=int)',  # closed_walk:129
    'arguments.defaults>Constant(value=str)',  # closed_walk:421
    'arguments.defaults>Name(id=str,ctx=Load)',  # test_match_hold_admission_gate_pg (a30d37f6):201
    'arguments.defaults>Tuple(elts=[Constant],ctx=Load)',  # closed_walk:565
    'arguments.defaults>Tuple(elts=[],ctx=Load)',  # closed_walk:1452
    'arguments.kw_defaults>Constant(value=bool)',  # test_match_hold_admission_gate_pg (a30d37f6):1830
    'arguments.kwonlyargs>arg(arg=str,annotation=-,type_comment=-)',  # test_match_hold_admission_gate_pg (a30d37f6):1830
    'arguments.vararg>arg(arg=str,annotation=-,type_comment=-)',  # closed_walk:1519
    'comprehension.ifs>BoolOp(op=And,values=[Attribute|Call])',  # closed_walk:1936
    'comprehension.ifs>BoolOp(op=And,values=[BoolOp|Call])',  # test_match_hold_admission_gate_pg (a30d37f6):287
    'comprehension.ifs>BoolOp(op=And,values=[BoolOp|Call|Compare])',  # closed_walk:1954
    'comprehension.ifs>BoolOp(op=And,values=[Call])',  # closed_walk:1949
    'comprehension.ifs>BoolOp(op=And,values=[Call|Compare])',  # closed_walk:659
    'comprehension.ifs>BoolOp(op=And,values=[Compare])',  # test_a1_identity_formation:1490
    'comprehension.ifs>BoolOp(op=And,values=[Compare|Name])',  # closed_walk:1239
    'comprehension.ifs>BoolOp(op=And,values=[Compare|UnaryOp])',  # test_match_hold_admission_gate_pg (a30d37f6):75
    'comprehension.ifs>Call(func=Name,args=[Attribute|Name],keywords=[])',  # test_a1_identity_formation:779
    'comprehension.ifs>Call(func=Name,args=[Attribute|Subscript],keywords=[])',  # test_a1_identity_formation:1428
    'comprehension.ifs>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:178
    'comprehension.ifs>Call(func=Name,args=[Name],keywords=[])',  # test_a1_identity_formation:1500
    'comprehension.ifs>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:933
    'comprehension.ifs>Compare(left=Call,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1447
    'comprehension.ifs>Compare(left=Call,ops=[In],comparators=[Name])',  # closed_walk:1087
    'comprehension.ifs>Compare(left=Name,ops=[Eq],comparators=[Constant])',  # test_a1_identity_formation:1496
    'comprehension.ifs>Compare(left=Name,ops=[Eq],comparators=[Name])',  # closed_walk:175
    'comprehension.ifs>Compare(left=Name,ops=[IsNot],comparators=[Constant])',  # closed_walk:379
    'comprehension.ifs>Compare(left=Name,ops=[IsNot],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):444
    'comprehension.ifs>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # test_a1_identity_formation:1108
    'comprehension.ifs>Compare(left=Name,ops=[NotEq],comparators=[Tuple])',  # test_a1_identity_formation:1257
    'comprehension.ifs>Compare(left=Name,ops=[NotIn],comparators=[Call])',  # test_a1_identity_formation:1273
    'comprehension.ifs>Compare(left=Name,ops=[NotIn],comparators=[Name])',  # test_match_hold_admission_gate_pg (a30d37f6):73
    'comprehension.ifs>Compare(left=Name,ops=[NotIn],comparators=[Tuple])',  # test_match_hold_admission_gate_pg (a30d37f6):553
    'comprehension.ifs>Name(id=str,ctx=Load)',  # closed_walk:1245
    'comprehension.ifs>UnaryOp(op=Not,operand=BoolOp)',  # closed_walk:785
    'comprehension.ifs>UnaryOp(op=Not,operand=Call)',  # test_a1_identity_formation:2941
    "comprehension.iter>Attribute(value=Attribute,attr='kw_defaults',ctx=Load)",  # closed_walk:437
    "comprehension.iter>Attribute(value=Name,attr='args',ctx=Load)",  # closed_walk:1033
    "comprehension.iter>Attribute(value=Name,attr='body',ctx=Load)",  # closed_walk:177
    "comprehension.iter>Attribute(value=Name,attr='effects',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):302
    "comprehension.iter>Attribute(value=Name,attr='elts',ctx=Load)",  # test_a1_identity_formation:840
    "comprehension.iter>Attribute(value=Name,attr='keys',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):651
    "comprehension.iter>Attribute(value=Name,attr='keywords',ctx=Load)",  # closed_walk:953
    "comprehension.iter>Attribute(value=Name,attr='names',ctx=Load)",  # closed_walk:73
    'comprehension.iter>BinOp(left=Attribute,op=Add,right=Attribute)',  # closed_walk:721
    'comprehension.iter>BinOp(left=BinOp,op=Add,right=Attribute)',  # closed_walk:1928
    'comprehension.iter>BinOp(left=BinOp,op=Add,right=ListComp)',  # closed_walk:378
    'comprehension.iter>BinOp(left=Tuple,op=Add,right=Name)',  # test_a1_identity_formation:4382
    'comprehension.iter>Call(func=Attribute,args=[Attribute],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):1231
    'comprehension.iter>Call(func=Attribute,args=[Attribute|Constant|Name],keywords=[])',  # test_a1_identity_formation:4727
    'comprehension.iter>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:174
    'comprehension.iter>Call(func=Attribute,args=[Name|Tuple],keywords=[])',  # test_a1_identity_formation:895
    'comprehension.iter>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:498
    'comprehension.iter>Call(func=Name,args=[Attribute],keywords=[])',  # closed_walk:1969
    'comprehension.iter>Call(func=Name,args=[Attribute|Call],keywords=[])',  # test_a1_identity_formation:1255
    'comprehension.iter>Call(func=Name,args=[Call|Name],keywords=[])',  # test_a1_identity_formation:2940
    'comprehension.iter>Call(func=Name,args=[Constant|Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):74
    'comprehension.iter>Call(func=Name,args=[Constant|Name|Tuple],keywords=[])',  # test_a1_identity_formation:1464
    'comprehension.iter>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1239
    'comprehension.iter>Call(func=Name,args=[Name],keywords=[keyword])',  # test_a1_identity_formation:1065
    'comprehension.iter>Call(func=Name,args=[Subscript],keywords=[])',  # test_a1_identity_formation:1427
    'comprehension.iter>Call(func=Name,args=[Subscript],keywords=[keyword])',  # closed_walk:1059
    'comprehension.iter>Name(id=str,ctx=Load)',  # closed_walk:127
    'comprehension.iter>Subscript(value=Name,slice=Slice,ctx=Load)',  # closed_walk:1245
    'comprehension.iter>Tuple(elts=[Attribute],ctx=Load)',  # closed_walk:379
    'comprehension.iter>Tuple(elts=[Call],ctx=Load)',  # test_a1_identity_formation:1287
    'comprehension.iter>Tuple(elts=[IfExp],ctx=Load)',  # test_a1_identity_formation:1310
    'comprehension.iter>Tuple(elts=[Name],ctx=Load)',  # test_a1_identity_formation:2166
    'comprehension.target>Name(id=str,ctx=Store)',  # closed_walk:73
    'comprehension.target>Tuple(elts=[Name],ctx=Store)',  # closed_walk:174
    'comprehension.target>Tuple(elts=[Name|Tuple],ctx=Store)',  # closed_walk:920
    "keyword.value>Attribute(value=Attribute,attr='session',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):234
    "keyword.value>Attribute(value=Call,attr='grammar',ctx=Load)",  # test_a1_identity_formation:537
    "keyword.value>Attribute(value=Name,attr='_ffa_sort_key',ctx=Load)",  # test_a1_identity_formation:135
    "keyword.value>Attribute(value=Name,attr='b',ctx=Load)",  # test_match_hold_admission_gate_pg (a30d37f6):290
    "keyword.value>Attribute(value=Name,attr='grammar',ctx=Load)",  # closed_walk:1015
    "keyword.value>Attribute(value=Name,attr='session',ctx=Load)",  # closed_walk:1014
    'keyword.value>Call(func=Attribute,args=[Name],keywords=[])',  # test_match_hold_admission_gate_pg (a30d37f6):358
    'keyword.value>Call(func=Attribute,args=[],keywords=[])',  # test_a1_identity_formation:1290
    'keyword.value>Call(func=Name,args=[Constant|List|Name],keywords=[])',  # closed_walk:1309
    'keyword.value>Call(func=Name,args=[Constant|Name],keywords=[])',  # closed_walk:1458
    'keyword.value>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1889
    'keyword.value>Call(func=Name,args=[Set],keywords=[])',  # test_a1_identity_formation:2292
    'keyword.value>Constant(value=NoneType)',  # test_a1_identity_formation:2922
    'keyword.value>Constant(value=bool)',  # test_a1_identity_formation:724
    'keyword.value>Constant(value=str)',  # test_a1_identity_formation:2925
    'keyword.value>Dict(keys=[Attribute],values=[Name])',  # closed_walk:960
    'keyword.value>IfExp(test=BoolOp,body=List,orelse=Name)',  # test_match_hold_admission_gate_pg (a30d37f6):233
    'keyword.value>Lambda(args=arguments,body=Attribute)',  # test_a1_identity_formation:898
    'keyword.value>Name(id=str,ctx=Load)',  # closed_walk:360
    'keyword.value>Tuple(elts=[Constant],ctx=Load)',  # test_a1_identity_formation:2457
})

# Round 11 (ruling FOUR-R11-A1 (2), GROUP 2; again for rules W, P and K of FOUR-R11-A4): the hand re-freeze for
# FIX-R11-ID (the identity binder's reads, the registered sources, the
# receiver provenance of F10). Every shape below is new walker code of
# round 11; the comment names the first line that needs it. The round-7
# freeze above is unchanged; the boundary test pins this block by its
# own size and digest.
R7_LESS_THREE_WALKER_SHAPES = WALKER_SHAPES
R11_ID_WALKER_SHAPES = frozenset({
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|AugAssign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:2624
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|For|FunctionDef|If|Return|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg:2772
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return|While],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:1764
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Try],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:2598
    '<root>>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[Name],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:621
    "Assign.targets>Attribute(value=Attribute,attr='span_def',ctx=Store)",  # test_match_hold_admission_gate_pg:1411
    "Assign.targets>Attribute(value=Name,attr='_plain_owner',ctx=Store)",  # closed_walk:2233
    "Assign.targets>Attribute(value=Name,attr='_ret_joins',ctx=Store)",  # closed_walk:3827
    "Assign.targets>Attribute(value=Name,attr='opaque_receivers',ctx=Store)",  # closed_walk:3828
    "Assign.targets>Attribute(value=Name,attr='param_values',ctx=Store)",  # closed_walk:741
    "Assign.targets>Attribute(value=Name,attr='parent',ctx=Store)",  # closed_walk:737
    "Assign.targets>Attribute(value=Name,attr='span_def',ctx=Store)",  # closed_walk:744
    'Assign.targets>Subscript(value=Name,slice=Slice,ctx=Store)',  # closed_walk:2886
    'Assign.targets>Subscript(value=Subscript,slice=Call,ctx=Store)',  # closed_walk:1776
    'Assign.targets>Tuple(elts=[Name|Starred],ctx=Store)',  # closed_walk:3081
    "Assign.value>Attribute(value=Name,attr='__name__',ctx=Load)",  # closed_walk:1550
    "Assign.value>Attribute(value=Name,attr='func',ctx=Load)",  # closed_walk:1860
    "Assign.value>Attribute(value=Name,attr='id',ctx=Load)",  # closed_walk:1406
    "Assign.value>Attribute(value=Name,attr='monitoring',ctx=Load)",  # test_match_hold_admission_gate_pg:2779
    "Assign.value>Attribute(value=Name,attr='scope',ctx=Load)",  # closed_walk:1365
    "Assign.value>Attribute(value=Subscript,attr='id',ctx=Load)",  # closed_walk:1599
    'Assign.value>BinOp(left=Constant,op=Add,right=Attribute)',  # closed_walk:3209
    'Assign.value>BinOp(left=ListComp,op=Add,right=IfExp)',  # closed_walk:2839
    'Assign.value>BinOp(left=SetComp,op=BitOr,right=IfExp)',  # closed_walk:2437
    'Assign.value>BinOp(left=Subscript,op=Add,right=Name)',  # closed_walk:3241
    'Assign.value>BoolOp(op=Or,values=[List|ListComp])',  # closed_walk:2639
    'Assign.value>Call(func=Attribute,args=[Attribute|Call|Name],keywords=[])',  # test_match_hold_admission_gate_pg:596
    'Assign.value>Call(func=Attribute,args=[Attribute|IfExp|Name],keywords=[keyword])',  # test_a1_identity_formation:2271
    'Assign.value>Call(func=Attribute,args=[Call|Constant],keywords=[])',  # closed_walk:2604
    'Assign.value>Call(func=Attribute,args=[Constant|Dict],keywords=[])',  # closed_walk:2856
    'Assign.value>Call(func=Attribute,args=[Constant|List],keywords=[])',  # closed_walk:2861
    'Assign.value>Call(func=Attribute,args=[IfExp|Name],keywords=[])',  # test_a1_identity_formation:5807
    'Assign.value>Call(func=Attribute,args=[Name|Subscript],keywords=[])',  # closed_walk:854
    'Assign.value>Call(func=Name,args=[Attribute|Call],keywords=[])',  # closed_walk:1668
    'Assign.value>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',  # closed_walk:846
    'Assign.value>Call(func=Name,args=[GeneratorExp|Name],keywords=[])',  # closed_walk:1742
    'Assign.value>Call(func=Name,args=[Name|Tuple],keywords=[])',  # closed_walk:1781
    'Assign.value>Dict(keys=[Constant],values=[Call|Name])',  # closed_walk:1880
    'Assign.value>Dict(keys=[Constant],values=[Dict])',  # closed_walk:1770
    'Assign.value>IfExp(test=Attribute,body=Attribute,orelse=Attribute)',  # closed_walk:1361
    'Assign.value>IfExp(test=Attribute,body=Compare,orelse=BoolOp)',  # closed_walk:1439
    'Assign.value>IfExp(test=BoolOp,body=Constant,orelse=Name)',  # closed_walk:2372
    'Assign.value>IfExp(test=BoolOp,body=Name,orelse=Call)',  # test_match_hold_admission_gate_pg:2827
    'Assign.value>IfExp(test=Call,body=List,orelse=IfExp)',  # closed_walk:2518
    'Assign.value>IfExp(test=Call,body=Name,orelse=Constant)',  # closed_walk:1845
    'Assign.value>IfExp(test=Compare,body=Call,orelse=Dict)',  # closed_walk:2793
    'Assign.value>IfExp(test=Compare,body=Constant,orelse=Tuple)',  # test_match_hold_admission_gate_pg:525
    'Assign.value>IfExp(test=Compare,body=Subscript,orelse=Call)',  # closed_walk:1504
    'Assign.value>IfExp(test=Name,body=Constant,orelse=Call)',  # closed_walk:3540
    'Assign.value>IfExp(test=Name,body=Constant,orelse=Name)',  # closed_walk:3237
    'Assign.value>IfExp(test=Name,body=List,orelse=Call)',  # closed_walk:3543
    'Assign.value>IfExp(test=Name,body=Name,orelse=Constant)',  # test_a1_identity_formation:5809
    'Assign.value>IfExp(test=Subscript,body=Constant,orelse=Name)',  # closed_walk:3561
    'Assign.value>ListComp(elt=Subscript,generators=[comprehension])',  # closed_walk:2446
    'Assign.value>ListComp(elt=Tuple,generators=[comprehension])',  # closed_walk:1407
    'Assign.value>Tuple(elts=[Attribute|Name],ctx=Load)',  # closed_walk:2824
    'Assign.value>Tuple(elts=[Call|Constant|List],ctx=Load)',  # closed_walk:2830
    'Assign.value>Tuple(elts=[Call|Name],ctx=Load)',  # closed_walk:1469
    'Assign.value>Tuple(elts=[Constant|List|Name],ctx=Load)',  # closed_walk:2902
    'Assign.value>Tuple(elts=[Constant|Name|Tuple],ctx=Load)',  # test_match_hold_admission_gate_pg:512
    'Assign.value>Tuple(elts=[Dict|List],ctx=Load)',  # closed_walk:1841
    "Attribute.value>Attribute(value=Attribute,attr='__dict__',ctx=Load)",  # closed_walk:3676
    "Attribute.value>Attribute(value=Call,attr='parameters',ctx=Load)",  # closed_walk:3057
    "Attribute.value>Attribute(value=Name,attr='PROVIDERS',ctx=Load)",  # closed_walk:852
    "Attribute.value>Attribute(value=Name,attr='Parameter',ctx=Load)",  # closed_walk:3050
    "Attribute.value>Attribute(value=Name,attr='_cw_datetime',ctx=Load)",  # test_match_hold_admission_gate_pg:2763
    "Attribute.value>Attribute(value=Name,attr='elts',ctx=Load)",  # closed_walk:3001
    "Attribute.value>Attribute(value=Name,attr='events',ctx=Load)",  # test_match_hold_admission_gate_pg:2848
    "Attribute.value>Attribute(value=Name,attr='f_locals',ctx=Load)",  # test_match_hold_admission_gate_pg:2822
    "Attribute.value>Attribute(value=Name,attr='gate_kinds',ctx=Load)",  # test_match_hold_admission_gate_pg:504
    "Attribute.value>Attribute(value=Name,attr='helpers',ctx=Load)",  # closed_walk:3766
    "Attribute.value>Attribute(value=Name,attr='parent',ctx=Load)",  # closed_walk:1414
    "Attribute.value>Attribute(value=Name,attr='scope',ctx=Load)",  # closed_walk:856
    "Attribute.value>Attribute(value=Name,attr='types',ctx=Load)",  # test_a1_identity_formation:622
    'Attribute.value>Call(func=Attribute,args=[Attribute|List],keywords=[])',  # closed_walk:1775
    'Attribute.value>Call(func=Attribute,args=[Constant|Dict],keywords=[])',  # closed_walk:3676
    'Attribute.value>Call(func=Attribute,args=[Dict|Name],keywords=[])',  # closed_walk:1524
    'Attribute.value>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:861
    'Attribute.value>Subscript(value=Attribute,slice=Name,ctx=Load)',  # closed_walk:1610
    'Attribute.value>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:1717
    'Attribute.value>Subscript(value=Name,slice=Attribute,ctx=Load)',  # test_match_hold_admission_gate_pg:2785
    'AugAssign.value>ListComp(elt=Call,generators=[comprehension])',  # closed_walk:2966
    'AugAssign.value>ListComp(elt=Tuple,generators=[comprehension])',  # closed_walk:2652
    'AugAssign.value>Name(id=str,ctx=Load)',  # closed_walk:1818
    "BinOp.left>Attribute(value=Attribute,attr='co_flags',ctx=Load)",  # closed_walk:1373
    'BinOp.left>BinOp(left=List,op=Mult,right=BinOp)',  # closed_walk:3050
    'BinOp.left>List(elts=[Attribute],ctx=Load)',  # closed_walk:2520
    'BinOp.left>List(elts=[IfExp],ctx=Load)',  # closed_walk:2881
    'BinOp.left>ListComp(elt=IfExp,generators=[comprehension])',  # closed_walk:2618
    'BinOp.left>ListComp(elt=Subscript,generators=[comprehension])',  # closed_walk:2645
    'BinOp.left>SetComp(elt=Name,generators=[comprehension])',  # closed_walk:2437
    'BinOp.left>Tuple(elts=[Subscript],ctx=Load)',  # closed_walk:2373
    'BinOp.op>FloorDiv()',  # closed_walk:2734
    "BinOp.right>Attribute(value=Name,attr='lineno',ctx=Load)",  # closed_walk:3208
    'BinOp.right>BinOp(left=Call,op=Sub,right=Call)',  # closed_walk:3050
    'BinOp.right>Call(func=Attribute,args=[BinOp],keywords=[])',  # closed_walk:2373
    'BinOp.right>IfExp(test=Compare,body=List,orelse=List)',  # closed_walk:2448
    'BinOp.right>IfExp(test=Name,body=Call,orelse=Call)',  # closed_walk:2437
    'BinOp.right>IfExp(test=Name,body=List,orelse=List)',  # closed_walk:2840
    'BinOp.right>ListComp(elt=IfExp,generators=[comprehension])',  # closed_walk:3050
    'BinOp.right>Subscript(value=Subscript,slice=Constant,ctx=Load)',  # closed_walk:3220
    'BoolOp.values>BinOp(left=Attribute,op=BitAnd,right=Constant)',  # closed_walk:1373
    'BoolOp.values>BoolOp(op=Or,values=[BoolOp])',  # closed_walk:1865
    'BoolOp.values>BoolOp(op=Or,values=[Call|Compare])',  # test_match_hold_admission_gate_pg:507
    'BoolOp.values>Call(func=Attribute,args=[Name|Subscript],keywords=[])',  # closed_walk:863
    'BoolOp.values>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:1471
    'BoolOp.values>Call(func=Name,args=[Constant|Subscript],keywords=[])',  # closed_walk:3036
    'BoolOp.values>Compare(left=Attribute,ops=[NotEq],comparators=[Attribute])',  # closed_walk:1371
    'BoolOp.values>Compare(left=Call,ops=[Eq],comparators=[Call])',  # closed_walk:2999
    'BoolOp.values>Compare(left=Call,ops=[Gt],comparators=[Constant])',  # closed_walk:2683
    'BoolOp.values>Compare(left=Call,ops=[IsNot],comparators=[Attribute])',  # closed_walk:1743
    'BoolOp.values>Compare(left=Call,ops=[IsNot],comparators=[Name])',  # closed_walk:1711
    'BoolOp.values>Compare(left=Call,ops=[IsNot],comparators=[Subscript])',  # test_match_hold_admission_gate_pg:2827
    'BoolOp.values>Compare(left=Call,ops=[Is],comparators=[Call])',  # closed_walk:1026
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Subscript])',  # test_match_hold_admission_gate_pg:2813
    'BoolOp.values>Compare(left=Call,ops=[NotIn],comparators=[Tuple])',  # closed_walk:3097
    'BoolOp.values>Compare(left=Name,ops=[Eq],comparators=[Name])',  # closed_walk:1008
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Attribute])',  # closed_walk:1197
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Subscript])',  # closed_walk:1618
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Attribute])',  # closed_walk:2905
    'BoolOp.values>Compare(left=Name,ops=[Lt],comparators=[Name])',  # test_match_hold_admission_gate_pg:2790
    'BoolOp.values>Compare(left=Name,ops=[NotEq],comparators=[Constant])',  # closed_walk:2433
    'BoolOp.values>Compare(left=Subscript,ops=[IsNot],comparators=[Attribute])',  # closed_walk:2819
    'BoolOp.values>Compare(left=Subscript,ops=[IsNot],comparators=[Name])',  # closed_walk:1712
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # closed_walk:1526
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Subscript])',  # closed_walk:1374
    'BoolOp.values>IfExp(test=Attribute,body=Compare,orelse=UnaryOp)',  # closed_walk:1409
    'BoolOp.values>ListComp(elt=Name,generators=[comprehension])',  # closed_walk:2639
    "Call.args>Attribute(value=Attribute,attr='CALL',ctx=Load)",  # test_match_hold_admission_gate_pg:2848
    "Call.args>Attribute(value=Attribute,attr='FunctionType',ctx=Load)",  # test_a1_identity_formation:622
    "Call.args>Attribute(value=Attribute,attr='attr',ctx=Load)",  # closed_walk:1460
    "Call.args>Attribute(value=Attribute,attr='elts',ctx=Load)",  # closed_walk:1607
    "Call.args>Attribute(value=Attribute,attr='opaque_def',ctx=Load)",  # closed_walk:3675
    "Call.args>Attribute(value=Name,attr='AnnAssign',ctx=Load)",  # closed_walk:3004
    "Call.args>Attribute(value=Name,attr='BoolOp',ctx=Load)",  # closed_walk:2519
    "Call.args>Attribute(value=Name,attr='FunctionType',ctx=Load)",  # closed_walk:3158
    "Call.args>Attribute(value=Name,attr='NamedExpr',ctx=Load)",  # closed_walk:2930
    "Call.args>Attribute(value=Name,attr='Slice',ctx=Load)",  # closed_walk:2539
    "Call.args>Attribute(value=Name,attr='__code__',ctx=Load)",  # closed_walk:2818
    "Call.args>Attribute(value=Name,attr='comparators',ctx=Load)",  # closed_walk:2520
    "Call.args>Attribute(value=Name,attr='defaults',ctx=Load)",  # closed_walk:3050
    "Call.args>Attribute(value=Name,attr='elt',ctx=Load)",  # closed_walk:2492
    "Call.args>Attribute(value=Name,attr='generators',ctx=Load)",  # closed_walk:1615
    "Call.args>Attribute(value=Name,attr='key',ctx=Load)",  # closed_walk:2490
    "Call.args>Attribute(value=Subscript,attr='elts',ctx=Load)",  # closed_walk:1598
    "Call.args>Attribute(value=Subscript,attr='targets',ctx=Load)",  # closed_walk:1826
    'Call.args>BinOp(left=ListComp,op=Add,right=List)',  # closed_walk:2618
    'Call.args>BinOp(left=Name,op=Add,right=IfExp)',  # closed_walk:2448
    'Call.args>BinOp(left=Tuple,op=Add,right=Subscript)',  # closed_walk:2373
    'Call.args>Call(func=Name,args=[Attribute|Call|Name],keywords=[])',  # closed_walk:3694
    'Call.args>Dict(keys=[Attribute],values=[Name])',  # closed_walk:1170
    'Call.args>IfExp(test=Subscript,body=Call,orelse=Name)',  # closed_walk:2782
    'Call.args>Lambda(args=arguments,body=IfExp)',  # closed_walk:2359
    'Call.args>List(elts=[Call|Subscript],ctx=Load)',  # closed_walk:2684
    'Call.args>List(elts=[Constant|Subscript],ctx=Load)',  # closed_walk:2687
    'Call.args>ListComp(elt=Call,generators=[comprehension])',  # closed_walk:2378
    'Call.args>SetComp(elt=Name,generators=[comprehension])',  # closed_walk:2449
    'Call.args>Subscript(value=Attribute,slice=Call,ctx=Load)',  # closed_walk:3001
    'Call.args>Tuple(elts=[Attribute|Constant|Name],ctx=Load)',  # closed_walk:1537
    'Call.args>Tuple(elts=[Attribute|Constant|Name|Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg:2840
    'Call.args>Tuple(elts=[Attribute|Constant|Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg:2808
    'Call.args>Tuple(elts=[BinOp|Constant|Name],ctx=Load)',  # closed_walk:3220
    'Call.args>Tuple(elts=[Constant|Subscript],ctx=Load)',  # test_match_hold_admission_gate_pg:2819
    "Call.func>Attribute(value=Attribute,attr='bound_value',ctx=Load)",  # closed_walk:3204
    "Call.func>Attribute(value=Attribute,attr='index',ctx=Load)",  # closed_walk:3001
    "Call.func>Attribute(value=Attribute,attr='k_attr',ctx=Load)",  # closed_walk:3219
    "Call.func>Attribute(value=Attribute,attr='values',ctx=Load)",  # closed_walk:3057
    "Call.func>Attribute(value=Call,attr='count',ctx=Load)",  # closed_walk:1568
    "Call.func>Attribute(value=Call,attr='get',ctx=Load)",  # closed_walk:861
    "Call.func>Attribute(value=Name,attr='__binder_address__',ctx=Load)",  # test_a1_identity_formation:3799
    "Call.func>Attribute(value=Name,attr='_call_sites',ctx=Load)",  # closed_walk:1492
    "Call.func>Attribute(value=Name,attr='_const_names',ctx=Load)",  # closed_walk:1802
    "Call.func>Attribute(value=Name,attr='_getframe',ctx=Load)",  # test_match_hold_admission_gate_pg:2817
    "Call.func>Attribute(value=Name,attr='_handed',ctx=Load)",  # closed_walk:1575
    "Call.func>Attribute(value=Name,attr='_inert_string',ctx=Load)",  # closed_walk:1556
    "Call.func>Attribute(value=Name,attr='_k_census',ctx=Load)",  # closed_walk:1736
    "Call.func>Attribute(value=Name,attr='_local_root',ctx=Load)",  # closed_walk:1388
    "Call.func>Attribute(value=Name,attr='_module',ctx=Load)",  # closed_walk:1008
    "Call.func>Attribute(value=Name,attr='_module_function',ctx=Load)",  # closed_walk:1567
    "Call.func>Attribute(value=Name,attr='_name_index',ctx=Load)",  # closed_walk:1554
    "Call.func>Attribute(value=Name,attr='_own',ctx=Load)",  # test_a1_identity_formation:631
    "Call.func>Attribute(value=Name,attr='_owner_module',ctx=Load)",  # closed_walk:1490
    "Call.func>Attribute(value=Name,attr='_param_calls',ctx=Load)",  # closed_walk:1651
    "Call.func>Attribute(value=Name,attr='_root_over_sites',ctx=Load)",  # closed_walk:1483
    "Call.func>Attribute(value=Name,attr='_rooted',ctx=Load)",  # closed_walk:1391
    "Call.func>Attribute(value=Name,attr='_store_census',ctx=Load)",  # closed_walk:1757
    "Call.func>Attribute(value=Name,attr='_w_root',ctx=Load)",  # closed_walk:1494
    "Call.func>Attribute(value=Name,attr='bound_identity',ctx=Load)",  # closed_walk:887
    "Call.func>Attribute(value=Name,attr='bound_root',ctx=Load)",  # closed_walk:1442
    "Call.func>Attribute(value=Name,attr='carry',ctx=Load)",  # closed_walk:1472
    "Call.func>Attribute(value=Name,attr='co_lines',ctx=Load)",  # test_match_hold_admission_gate_pg:2789
    "Call.func>Attribute(value=Name,attr='defaultdict',ctx=Load)",  # test_match_hold_admission_gate_pg:2783
    "Call.func>Attribute(value=Name,attr='discard',ctx=Load)",  # closed_walk:1485
    "Call.func>Attribute(value=Name,attr='discharge_receivers',ctx=Load)",  # test_match_hold_admission_gate_pg:596
    "Call.func>Attribute(value=Name,attr='free_tool_id',ctx=Load)",  # test_match_hold_admission_gate_pg:2857
    "Call.func>Attribute(value=Name,attr='get_tool',ctx=Load)",  # test_match_hold_admission_gate_pg:2780
    "Call.func>Attribute(value=Name,attr='getsourcelines',ctx=Load)",  # test_a1_identity_formation:634
    "Call.func>Attribute(value=Name,attr='k_class',ctx=Load)",  # closed_walk:1531
    "Call.func>Attribute(value=Name,attr='k_method',ctx=Load)",  # closed_walk:1460
    "Call.func>Attribute(value=Name,attr='listed',ctx=Load)",  # closed_walk:2718
    "Call.func>Attribute(value=Name,attr='namedtuple_class',ctx=Load)",  # closed_walk:2564
    "Call.func>Attribute(value=Name,attr='nested_def',ctx=Load)",  # closed_walk:2575
    "Call.func>Attribute(value=Name,attr='observe',ctx=Load)",  # closed_walk:830
    "Call.func>Attribute(value=Name,attr='observe_chain',ctx=Load)",  # closed_walk:1269
    "Call.func>Attribute(value=Name,attr='opaque_def',ctx=Load)",  # closed_walk:1170
    "Call.func>Attribute(value=Name,attr='recording',ctx=Load)",  # closed_walk:1482
    "Call.func>Attribute(value=Name,attr='register_callback',ctx=Load)",  # test_match_hold_admission_gate_pg:2848
    "Call.func>Attribute(value=Name,attr='register_source',ctx=Load)",  # test_a1_identity_formation:3785
    "Call.func>Attribute(value=Name,attr='set_local_events',ctx=Load)",  # test_match_hold_admission_gate_pg:2850
    "Call.func>Attribute(value=Name,attr='span_function',ctx=Load)",  # closed_walk:1390
    "Call.func>Attribute(value=Name,attr='supplied',ctx=Load)",  # test_a1_identity_formation:857
    "Call.func>Attribute(value=Name,attr='trusted',ctx=Load)",  # closed_walk:854
    "Call.func>Attribute(value=Name,attr='trusted_class',ctx=Load)",  # closed_walk:913
    "Call.func>Attribute(value=Name,attr='trusted_constant',ctx=Load)",  # closed_walk:2850
    "Call.func>Attribute(value=Name,attr='trusted_function',ctx=Load)",  # closed_walk:912
    "Call.func>Attribute(value=Name,attr='use_tool_id',ctx=Load)",  # test_match_hold_admission_gate_pg:2846
    "Call.func>Attribute(value=Name,attr='valid',ctx=Load)",  # test_match_hold_admission_gate_pg:507
    "Call.func>Attribute(value=Subscript,attr='append',ctx=Load)",  # test_match_hold_admission_gate_pg:2785
    "Call.func>Attribute(value=Subscript,attr='get',ctx=Load)",  # closed_walk:1555
    "Call.func>Attribute(value=Subscript,attr='setdefault',ctx=Load)",  # closed_walk:1775
    "Call.func>Attribute(value=Subscript,attr='split',ctx=Load)",  # test_match_hold_admission_gate_pg:2821
    "Call.func>Attribute(value=Subscript,attr='valid',ctx=Load)",  # closed_walk:1471
    "Call.keywords>keyword(arg='awaited',value=Constant)",  # closed_walk:2536
    "Call.keywords>keyword(arg='b',value=Attribute)",  # test_match_hold_admission_gate_pg:598
    "Call.keywords>keyword(arg='effects',value=List)",  # test_match_hold_admission_gate_pg:599
    "Call.keywords>keyword(arg='helper',value=Constant)",  # test_match_hold_admission_gate_pg:598
    "Call.keywords>keyword(arg='outward',value=Name)",  # closed_walk:2934
    "Call.keywords>keyword(arg='p',value=Attribute)",  # test_match_hold_admission_gate_pg:598
    "Call.keywords>keyword(arg='param_values',value=Dict)",  # closed_walk:3183
    "Call.keywords>keyword(arg='receivers',value=Compare)",  # test_a1_identity_formation:2283
    "Call.keywords>keyword(arg='receivers',value=Constant)",  # closed_walk:3182
    'ClassDef.body>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_a1_identity_formation:3793
    "Compare.comparators>Attribute(value=Attribute,attr='datetime',ctx=Load)",  # test_match_hold_admission_gate_pg:2763
    "Compare.comparators>Attribute(value=Attribute,attr='empty',ctx=Load)",  # closed_walk:3097
    "Compare.comparators>Attribute(value=Name,attr='FunctionType',ctx=Load)",  # closed_walk:1743
    "Compare.comparators>Attribute(value=Name,attr='ModuleType',ctx=Load)",  # closed_walk:855
    "Compare.comparators>Attribute(value=Name,attr='__code__',ctx=Load)",  # closed_walk:2819
    "Compare.comparators>Attribute(value=Name,attr='body',ctx=Load)",  # closed_walk:2905
    "Compare.comparators>Attribute(value=Name,attr='iter',ctx=Load)",  # closed_walk:2913
    "Compare.comparators>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:1371
    "Compare.comparators>Attribute(value=Name,attr='param_values',ctx=Load)",  # closed_walk:2981
    "Compare.comparators>Attribute(value=Name,attr='where',ctx=Load)",  # closed_walk:1197
    'Compare.comparators>BinOp(left=Name,op=FloorDiv,right=Constant)',  # closed_walk:2734
    'Compare.comparators>List(elts=[Tuple],ctx=Load)',  # closed_walk:1409
    'Compare.comparators>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:1602
    'Compare.comparators>Subscript(value=Attribute,slice=Name,ctx=Load)',  # closed_walk:1618
    'Compare.comparators>Subscript(value=Call,slice=Constant,ctx=Load)',  # closed_walk:1374
    'Compare.comparators>Subscript(value=Subscript,slice=Slice,ctx=Load)',  # test_match_hold_admission_gate_pg:2813
    'Compare.comparators>Tuple(elts=[Call|Name],ctx=Load)',  # closed_walk:2849
    "Compare.left>Attribute(value=Attribute,attr='co_name',ctx=Load)",  # closed_walk:1371
    "Compare.left>Attribute(value=Name,attr='f_code',ctx=Load)",  # test_match_hold_admission_gate_pg:2818
    "Compare.left>Attribute(value=Name,attr='func',ctx=Load)",  # closed_walk:1571
    "Compare.left>Attribute(value=Name,attr='iter',ctx=Load)",  # closed_walk:1605
    "Compare.left>Attribute(value=Name,attr='left',ctx=Load)",  # closed_walk:1622
    "Compare.left>Attribute(value=Name,attr='target',ctx=Load)",  # closed_walk:2995
    'Compare.left>Call(func=Attribute,args=[Dict|Name],keywords=[])',  # closed_walk:1170
    'Compare.left>Call(func=Name,args=[Attribute|Call],keywords=[])',  # closed_walk:2743
    'Compare.left>Call(func=Name,args=[Constant|Name],keywords=[])',  # test_match_hold_admission_gate_pg:2813
    'Compare.left>Subscript(value=Attribute,slice=Constant,ctx=Load)',  # closed_walk:1448
    'Compare.left>Subscript(value=Attribute,slice=UnaryOp,ctx=Load)',  # closed_walk:1712
    'Delete.targets>Subscript(value=Attribute,slice=Name,ctx=Del)',  # closed_walk:3771
    'Delete.targets>Subscript(value=Name,slice=Call,ctx=Del)',  # closed_walk:2800
    'Dict.values>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:1880
    'Dict.values>Tuple(elts=[Constant|Name|Tuple],ctx=Load)',  # closed_walk:3183
    'Expr.value>Call(func=Attribute,args=[Attribute|Name|Subscript],keywords=[])',  # closed_walk:3219
    'Expr.value>Call(func=Attribute,args=[Name],keywords=[keyword])',  # closed_walk:2134
    'Expr.value>Call(func=Name,args=[Attribute|Call|Name],keywords=[])',  # closed_walk:3688
    'Expr.value>Call(func=Name,args=[Attribute|Name|Subscript],keywords=[])',  # closed_walk:3678
    'For.body>Assign(targets=[Subscript],value=Name,type_comment=-)',  # closed_walk:757
    'For.body>Assign(targets=[Tuple],value=Name,type_comment=-)',  # closed_walk:1496
    'For.body>AugAssign(target=Name,op=BitOr,value=Name)',  # closed_walk:1818
    'For.body>For(target=Name,iter=BinOp,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:3120
    'For.body>For(target=Name,iter=Call,body=[Expr|For],orelse=[],type_comment=-)',  # closed_walk:754
    'For.body>For(target=Name,iter=Name,body=[If],orelse=[],type_comment=-)',  # closed_walk:1621
    'For.body>For(target=Name,iter=Subscript,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:3146
    'For.body>For(target=Tuple,iter=Call,body=[If],orelse=[],type_comment=-)',  # closed_walk:2140
    'For.body>If(test=BoolOp,body=[Continue|For],orelse=[])',  # closed_walk:3125
    'For.body>If(test=Call,body=[Raise],orelse=[])',  # closed_walk:1568
    'For.body>If(test=Compare,body=[Continue|If],orelse=[])',  # test_match_hold_admission_gate_pg:2802
    'For.body>If(test=Compare,body=[Expr],orelse=[Expr])',  # closed_walk:2870
    'For.body>If(test=Name,body=[Assign|If],orelse=[])',  # test_match_hold_admission_gate_pg:2823
    'For.body>If(test=Name,body=[Return],orelse=[])',  # closed_walk:2950
    'For.body>If(test=UnaryOp,body=[Raise],orelse=[])',  # closed_walk:1654
    'For.iter>BinOp(left=Call,op=Add,right=List)',  # closed_walk:2948
    'For.iter>BinOp(left=Name,op=Add,right=Name)',  # closed_walk:3120
    'For.iter>Call(func=Attribute,args=[Name|Tuple],keywords=[])',  # closed_walk:1562
    'For.iter>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2773
    'For.target>Tuple(elts=[Name|Tuple],ctx=Store)',  # closed_walk:2140
    "FormattedValue.value>Attribute(value=Attribute,attr='co_name',ctx=Load)",  # closed_walk:3691
    "FormattedValue.value>Attribute(value=Name,attr='__qualname__',ctx=Load)",  # closed_walk:1533
    "FormattedValue.value>Attribute(value=Subscript,attr='__qualname__',ctx=Load)",  # closed_walk:1717
    'FormattedValue.value>Call(func=Attribute,args=[Subscript],keywords=[])',  # closed_walk:3142
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=arg,defaults=[Tuple])',  # closed_walk:2133
    'FunctionDef.body>Assign(targets=[Name],value=Name,type_comment=-)',  # test_match_hold_admission_gate_pg:255
    'FunctionDef.body>Assign(targets=[Subscript],value=IfExp,type_comment=-)',  # test_match_hold_admission_gate_pg:525
    'FunctionDef.body>Assign(targets=[Subscript],value=ListComp,type_comment=-)',  # closed_walk:2886
    'FunctionDef.body>AugAssign(target=Name,op=Add,value=ListComp)',  # closed_walk:2652
    'FunctionDef.body>For(target=Name,iter=Attribute,body=[For],orelse=[],type_comment=-)',  # closed_walk:1843
    'FunctionDef.body>For(target=Name,iter=BinOp,body=[Assign|If],orelse=[],type_comment=-)',  # closed_walk:2948
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign],orelse=[],type_comment=-)',  # closed_walk:2365
    'FunctionDef.body>For(target=Name,iter=Name,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:3077
    'FunctionDef.body>For(target=Name,iter=Subscript,body=[Assign|Expr|If],orelse=[],type_comment=-)',  # closed_walk:2773
    'FunctionDef.body>For(target=Tuple,iter=Call,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:2135
    'FunctionDef.body>For(target=Tuple,iter=Name,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:1601
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[Assign|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # closed_walk:2754
    'FunctionDef.body>FunctionDef(name=str,args=arguments,body=[For|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',  # test_match_hold_admission_gate_pg:2788
    'FunctionDef.body>If(test=BoolOp,body=[Assign],orelse=[Assign])',  # closed_walk:2644
    'FunctionDef.body>If(test=BoolOp,body=[Assign|Return],orelse=[])',  # closed_walk:1804
    'FunctionDef.body>If(test=BoolOp,body=[Assign|Try],orelse=[])',  # closed_walk:2819
    'FunctionDef.body>If(test=BoolOp,body=[If|Return],orelse=[])',  # closed_walk:2693
    'FunctionDef.body>If(test=Call,body=[Assign|If],orelse=[])',  # closed_walk:2554
    'FunctionDef.body>If(test=Call,body=[If|Return],orelse=[])',  # closed_walk:2509
    'FunctionDef.body>If(test=Compare,body=[Assign],orelse=[Assign])',  # closed_walk:2931
    'FunctionDef.body>If(test=Compare,body=[Assign],orelse=[Assign|If])',  # closed_walk:513
    'FunctionDef.body>If(test=Compare,body=[Assign|Delete|If],orelse=[])',  # test_match_hold_admission_gate_pg:505
    'FunctionDef.body>If(test=Compare,body=[Assign|Expr|Return],orelse=[])',  # closed_walk:3236
    'FunctionDef.body>If(test=Compare,body=[Assign|If|Return|Try],orelse=[])',  # closed_walk:2562
    'FunctionDef.body>If(test=Compare,body=[Delete|If],orelse=[])',  # closed_walk:2796
    'FunctionDef.body>If(test=Compare,body=[If|Return],orelse=[])',  # closed_walk:2581
    'FunctionDef.body>If(test=Name,body=[Assign],orelse=[Assign])',  # closed_walk:3242
    'FunctionDef.body>If(test=Name,body=[If|Return],orelse=[])',  # closed_walk:2463
    'FunctionDef.body>If(test=Name,body=[Raise],orelse=[])',  # closed_walk:1722
    'FunctionDef.body>If(test=Subscript,body=[Assign|Raise],orelse=[])',  # closed_walk:1758
    'FunctionDef.body>If(test=UnaryOp,body=[Assign|If|Return],orelse=[])',  # closed_walk:2846
    'FunctionDef.body>Try(body=[Assign|For],handlers=[],orelse=[],finalbody=[Expr])',  # closed_walk:2867
    'FunctionDef.body>Try(body=[Assign|Return|While],handlers=[],orelse=[],finalbody=[Expr])',  # closed_walk:2608
    'FunctionDef.body>Try(body=[Expr|For],handlers=[],orelse=[],finalbody=[Expr|For])',  # test_match_hold_admission_gate_pg:2847
    'FunctionDef.body>Try(body=[With],handlers=[],orelse=[],finalbody=[Expr])',  # closed_walk:1481
    'FunctionDef.body>While(test=BoolOp,body=[Assign|If],orelse=[])',  # closed_walk:2904
    'FunctionDef.body>While(test=Name,body=[Assign|For|If],orelse=[])',  # closed_walk:1772
    'GeneratorExp.elt>BoolOp(op=And,values=[BoolOp|Compare])',  # test_match_hold_admission_gate_pg:2766
    'GeneratorExp.elt>BoolOp(op=Or,values=[Call])',  # closed_walk:3115
    'GeneratorExp.elt>BoolOp(op=Or,values=[Call|Compare])',  # closed_walk:2443
    'GeneratorExp.elt>Compare(left=Call,ops=[In],comparators=[Name])',  # test_match_hold_admission_gate_pg:2767
    'GeneratorExp.elt>Compare(left=Name,ops=[Eq],comparators=[Subscript])',  # closed_walk:2478
    'GeneratorExp.elt>Compare(left=Name,ops=[In],comparators=[Call])',  # closed_walk:1732
    'GeneratorExp.elt>Compare(left=Name,ops=[In],comparators=[Tuple])',  # closed_walk:2474
    'GeneratorExp.elt>Compare(left=Name,ops=[NotEq],comparators=[Subscript])',  # closed_walk:1514
    'GeneratorExp.elt>Subscript(value=Call,slice=Name,ctx=Load)',  # closed_walk:1742
    'GeneratorExp.elt>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2451
    'GeneratorExp.elt>UnaryOp(op=Not,operand=BoolOp)',  # closed_walk:2452
    'GeneratorExp.generators>comprehension(target=Name,iter=Attribute,ifs=[Compare],is_async=0)',  # closed_walk:1505
    'GeneratorExp.generators>comprehension(target=Name,iter=BinOp,ifs=[UnaryOp],is_async=0)',  # test_a1_identity_formation:2390
    'GeneratorExp.generators>comprehension(target=Name,iter=BinOp,ifs=[],is_async=0)',  # closed_walk:1200
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[Call],is_async=0)',  # closed_walk:2451
    'GeneratorExp.generators>comprehension(target=Name,iter=Name,ifs=[UnaryOp],is_async=0)',  # closed_walk:3148
    'If.body>Assign(targets=[Name|Subscript],value=Tuple,type_comment=-)',  # closed_walk:2824
    'If.body>Assign(targets=[Tuple],value=Subscript,type_comment=-)',  # closed_walk:1759
    'If.body>AugAssign(target=Name,op=Add,value=ListComp)',  # closed_walk:2966
    'If.body>Delete(targets=[Subscript])',  # closed_walk:2800
    'If.body>For(target=Name,iter=Attribute,body=[Assign|AugAssign|If],orelse=[],type_comment=-)',  # closed_walk:1814
    'If.body>For(target=Name,iter=BinOp,body=[Assign|For|If],orelse=[],type_comment=-)',  # closed_walk:3549
    'If.body>If(test=BoolOp,body=[Assign],orelse=[])',  # closed_walk:1008
    'If.body>If(test=BoolOp,body=[If|Return],orelse=[])',  # closed_walk:2997
    'If.body>If(test=Call,body=[Assign],orelse=[Assign])',  # closed_walk:847
    'If.body>If(test=Compare,body=[Assign|AugAssign|Return],orelse=[])',  # closed_walk:2964
    'If.body>If(test=Compare,body=[Assign|Return],orelse=[])',  # closed_walk:2558
    'If.body>If(test=Compare,body=[Expr],orelse=[For])',  # closed_walk:1874
    'If.body>If(test=Compare,body=[If|Return],orelse=[])',  # closed_walk:2980
    'If.body>If(test=UnaryOp,body=[Assign|For|If],orelse=[])',  # closed_walk:3530
    'If.body>If(test=UnaryOp,body=[Expr],orelse=[If])',  # test_match_hold_admission_gate_pg:2803
    'If.body>If(test=UnaryOp,body=[Raise],orelse=[])',  # closed_walk:1694
    'If.body>Return(value=BoolOp)',  # closed_walk:2968
    'If.body>Return(value=Compare)',  # closed_walk:3031
    'If.body>Return(value=Set)',  # closed_walk:1800
    'If.body>Try(body=[Assign],handlers=[ExceptHandler],orelse=[Assign],finalbody=[])',  # test_a1_identity_formation:2270
    'If.orelse>Assign(targets=[Name],value=BoolOp,type_comment=-)',  # closed_walk:863
    'If.orelse>Assign(targets=[Name],value=Constant,type_comment=-)',  # closed_walk:2647
    'If.orelse>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1878
    'If.orelse>If(test=BoolOp,body=[Assign],orelse=[Return])',  # closed_walk:2740
    'If.orelse>If(test=BoolOp,body=[Expr],orelse=[Raise])',  # closed_walk:1573
    'If.orelse>If(test=Call,body=[Expr|If],orelse=[])',  # closed_walk:3909
    'If.orelse>If(test=Compare,body=[Assign],orelse=[Assign])',  # closed_walk:855
    'If.orelse>If(test=Compare,body=[Expr|If],orelse=[])',  # test_match_hold_admission_gate_pg:2806
    'If.orelse>If(test=Name,body=[Assign],orelse=[])',  # closed_walk:1787
    'If.orelse>Raise(exc=Call,cause=-)',  # closed_walk:1577
    'If.test>BoolOp(op=And,values=[BoolOp|Call|Compare])',  # closed_walk:1864
    'If.test>BoolOp(op=And,values=[Compare|IfExp])',  # closed_walk:1409
    'If.test>BoolOp(op=And,values=[Compare|Name|UnaryOp])',  # closed_walk:1784
    'If.test>BoolOp(op=And,values=[Compare|Subscript])',  # closed_walk:3677
    'If.test>BoolOp(op=Or,values=[Attribute|BinOp|Compare|UnaryOp])',  # closed_walk:1371
    'If.test>BoolOp(op=Or,values=[BoolOp])',  # closed_walk:1854
    'If.test>BoolOp(op=Or,values=[Compare|Name|UnaryOp])',  # closed_walk:1563
    'If.test>BoolOp(op=Or,values=[Compare|Subscript])',  # closed_walk:1430
    'If.test>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:1715
    'If.test>Compare(left=Attribute,ops=[Eq],comparators=[Name])',  # closed_walk:3093
    'If.test>Compare(left=Attribute,ops=[IsNot],comparators=[Name])',  # test_match_hold_admission_gate_pg:2818
    'If.test>Compare(left=Attribute,ops=[Is],comparators=[Constant])',  # closed_walk:3138
    'If.test>Compare(left=Call,ops=[IsNot],comparators=[Attribute])',  # closed_walk:1366
    'If.test>Compare(left=Call,ops=[IsNot],comparators=[Name])',  # closed_walk:1170
    'If.test>Compare(left=Call,ops=[IsNot],comparators=[Subscript])',  # test_match_hold_admission_gate_pg:2807
    'If.test>Compare(left=Call,ops=[Is],comparators=[Attribute])',  # closed_walk:855
    'If.test>Compare(left=Call,ops=[NotEq],comparators=[List])',  # closed_walk:1681
    'If.test>Compare(left=Name,ops=[GtE],comparators=[Call])',  # closed_walk:1647
    'If.test>Compare(left=Name,ops=[Gt],comparators=[BinOp])',  # closed_walk:2734
    'If.test>Compare(left=Name,ops=[Gt],comparators=[Name])',  # closed_walk:2499
    'If.test>Compare(left=Name,ops=[Is],comparators=[Attribute])',  # closed_walk:2980
    'If.test>Compare(left=Name,ops=[Is],comparators=[Subscript])',  # closed_walk:1602
    'If.test>Compare(left=Name,ops=[Lt],comparators=[Call])',  # closed_walk:3090
    'If.test>Compare(left=Subscript,ops=[Is],comparators=[Constant])',  # closed_walk:2762
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Name])',  # test_match_hold_admission_gate_pg:2800
    'If.test>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:1758
    "IfExp.body>Attribute(value=Attribute,attr='attr',ctx=Load)",  # closed_walk:2960
    "IfExp.body>Attribute(value=Attribute,attr='empty',ctx=Load)",  # closed_walk:3054
    "IfExp.body>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:3074
    "IfExp.body>Attribute(value=Name,attr='scope',ctx=Load)",  # closed_walk:2847
    "IfExp.body>Attribute(value=Name,attr='where',ctx=Load)",  # closed_walk:1361
    'IfExp.body>BinOp(left=List,op=Add,right=Call)',  # closed_walk:2520
    'IfExp.body>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:1402
    'IfExp.body>Call(func=Attribute,args=[Call|Subscript],keywords=[])',  # closed_walk:1872
    'IfExp.body>Call(func=Attribute,args=[Constant|Dict],keywords=[])',  # closed_walk:2793
    'IfExp.body>Call(func=Name,args=[Call],keywords=[])',  # closed_walk:2437
    'IfExp.body>Call(func=Name,args=[ListComp],keywords=[])',  # closed_walk:2378
    'IfExp.body>Call(func=Name,args=[Name|Subscript],keywords=[])',  # closed_walk:2962
    'IfExp.body>Call(func=Name,args=[Subscript],keywords=[keyword])',  # closed_walk:2345
    'IfExp.body>Compare(left=Name,ops=[Eq],comparators=[List])',  # closed_walk:1409
    'IfExp.body>Constant(value=int)',  # closed_walk:2590
    'IfExp.body>List(elts=[Constant],ctx=Load)',  # closed_walk:2448
    'IfExp.body>Subscript(value=Attribute,slice=Name,ctx=Load)',  # closed_walk:1504
    'IfExp.body>Tuple(elts=[BinOp|Constant|Subscript],ctx=Load)',  # closed_walk:2359
    "IfExp.orelse>Attribute(value=Attribute,attr='co_name',ctx=Load)",  # closed_walk:3075
    "IfExp.orelse>Attribute(value=Name,attr='span_def',ctx=Load)",  # closed_walk:1361
    'IfExp.orelse>BinOp(left=Name,op=BitOr,right=Name)',  # closed_walk:1803
    'IfExp.orelse>BoolOp(op=And,values=[Compare|UnaryOp])',  # closed_walk:1440
    'IfExp.orelse>Call(func=Attribute,args=[Subscript],keywords=[])',  # test_match_hold_admission_gate_pg:2827
    'IfExp.orelse>Call(func=Name,args=[Attribute|Call|Name],keywords=[])',  # closed_walk:3475
    'IfExp.orelse>Call(func=Name,args=[Constant|GeneratorExp],keywords=[])',  # closed_walk:1504
    'IfExp.orelse>Call(func=Name,args=[List],keywords=[])',  # closed_walk:2765
    'IfExp.orelse>IfExp(test=Call,body=BinOp,orelse=List)',  # closed_walk:2520
    'IfExp.orelse>IfExp(test=Call,body=Call,orelse=IfExp)',  # closed_walk:2519
    'IfExp.orelse>IfExp(test=Compare,body=Attribute,orelse=Name)',  # closed_walk:3054
    'IfExp.orelse>Tuple(elts=[Name],ctx=Load)',  # test_match_hold_admission_gate_pg:525
    'IfExp.orelse>UnaryOp(op=Not,operand=Name)',  # closed_walk:1410
    'IfExp.test>BoolOp(op=And,values=[Call|Name])',  # closed_walk:2541
    'IfExp.test>BoolOp(op=And,values=[Call|UnaryOp])',  # closed_walk:2360
    'IfExp.test>BoolOp(op=Or,values=[Compare|Subscript])',  # closed_walk:2372
    'IfExp.test>BoolOp(op=Or,values=[Compare|UnaryOp])',  # test_match_hold_admission_gate_pg:2827
    'IfExp.test>Compare(left=Call,ops=[GtE],comparators=[Constant])',  # closed_walk:1873
    'IfExp.test>Compare(left=Call,ops=[Gt],comparators=[Constant])',  # closed_walk:2653
    'IfExp.test>Compare(left=Call,ops=[Is],comparators=[Attribute])',  # closed_walk:2847
    'IfExp.test>Compare(left=Name,ops=[In],comparators=[Name])',  # closed_walk:2681
    'IfExp.test>Compare(left=Name,ops=[Is],comparators=[Attribute])',  # closed_walk:2927
    'IfExp.test>Compare(left=Name,ops=[Lt],comparators=[Call])',  # closed_walk:1504
    'IfExp.test>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2782
    'Lambda.body>IfExp(test=BoolOp,body=Name,orelse=Call)',  # closed_walk:2541
    'Lambda.body>IfExp(test=BoolOp,body=Tuple,orelse=Call)',  # closed_walk:2359
    "List.elts>Attribute(value=Attribute,attr='empty',ctx=Load)",  # closed_walk:3050
    "List.elts>Attribute(value=Name,attr='left',ctx=Load)",  # closed_walk:2518
    "List.elts>Attribute(value=Name,attr='operand',ctx=Load)",  # closed_walk:2521
    "List.elts>Attribute(value=Name,attr='right',ctx=Load)",  # closed_walk:2518
    'List.elts>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:2490
    'List.elts>Call(func=Name,args=[Name],keywords=[])',  # closed_walk:2515
    'List.elts>Call(func=Name,args=[Name|Subscript],keywords=[])',  # closed_walk:2684
    'List.elts>IfExp(test=Call,body=Subscript,orelse=Constant)',  # closed_walk:2881
    'List.elts>IfExp(test=Compare,body=Call,orelse=Constant)',  # closed_walk:2972
    'List.elts>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2684
    'List.elts>Tuple(elts=[Constant|Name],ctx=Load)',  # closed_walk:1409
    'List.elts>Tuple(elts=[Name],ctx=Load)',  # closed_walk:3243
    "ListComp.elt>Attribute(value=Name,attr='default',ctx=Load)",  # closed_walk:3058
    "ListComp.elt>Attribute(value=Name,attr='name',ctx=Load)",  # closed_walk:3058
    'ListComp.elt>Call(func=Name,args=[Attribute|Name],keywords=[])',  # closed_walk:2966
    'ListComp.elt>IfExp(test=Call,body=Attribute,orelse=IfExp)',  # closed_walk:3053
    'ListComp.elt>IfExp(test=Call,body=Attribute,orelse=Name)',  # closed_walk:3051
    'ListComp.elt>IfExp(test=Compare,body=Call,orelse=Constant)',  # closed_walk:2962
    'ListComp.elt>IfExp(test=Compare,body=Constant,orelse=Call)',  # closed_walk:2618
    'ListComp.elt>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2446
    'ListComp.elt>Tuple(elts=[Call|Tuple],ctx=Load)',  # closed_walk:2946
    'ListComp.elt>Tuple(elts=[Constant|Name],ctx=Load)',  # closed_walk:1771
    'ListComp.elt>Tuple(elts=[Constant|Subscript],ctx=Load)',  # closed_walk:2652
    'ListComp.elt>Tuple(elts=[Name],ctx=Load)',  # closed_walk:1407
    'ListComp.generators>comprehension(target=Name,iter=Attribute,ifs=[BoolOp],is_async=0)',  # closed_walk:1593
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[BoolOp],is_async=0)',  # closed_walk:2433
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # closed_walk:1720
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[UnaryOp],is_async=0)',  # closed_walk:2462
    'ListComp.generators>comprehension(target=Name,iter=Subscript,ifs=[Compare],is_async=0)',  # closed_walk:2886
    "Return.value>Attribute(value=Name,attr='__code__',ctx=Load)",  # test_a1_identity_formation:627
    'Return.value>BinOp(left=BinOp,op=Add,right=Name)',  # closed_walk:2373
    'Return.value>BoolOp(op=Or,values=[BoolOp|Compare])',  # closed_walk:3035
    'Return.value>BoolOp(op=Or,values=[Call|Compare])',  # closed_walk:3033
    'Return.value>BoolOp(op=Or,values=[List|Name])',  # closed_walk:2968
    'Return.value>Call(func=Attribute,args=[Attribute|Constant],keywords=[])',  # closed_walk:1827
    'Return.value>Call(func=Name,args=[Attribute|Call],keywords=[])',  # closed_walk:2543
    'Return.value>Call(func=Name,args=[Call|Name],keywords=[])',  # closed_walk:2219
    'Return.value>Call(func=Name,args=[Lambda|Name],keywords=[])',  # closed_walk:2359
    'Return.value>Call(func=Name,args=[ListComp],keywords=[])',  # closed_walk:2507
    'Return.value>Compare(left=Call,ops=[Is],comparators=[Attribute])',  # test_match_hold_admission_gate_pg:2763
    'Return.value>Compare(left=Call,ops=[Is],comparators=[Name])',  # test_match_hold_admission_gate_pg:2759
    'Return.value>Compare(left=Name,ops=[In],comparators=[Tuple])',  # closed_walk:3031
    'Return.value>IfExp(test=Call,body=Call,orelse=List)',  # closed_walk:2345
    'Return.value>IfExp(test=Call,body=Subscript,orelse=Constant)',  # closed_walk:2478
    'Return.value>IfExp(test=Compare,body=Call,orelse=Name)',  # closed_walk:2653
    'Return.value>IfExp(test=Compare,body=Call,orelse=Tuple)',  # closed_walk:2438
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Call)',  # closed_walk:2765
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Constant)',  # closed_walk:2681
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Name)',  # closed_walk:2927
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Tuple)',  # closed_walk:2485
    'Return.value>IfExp(test=Name,body=Subscript,orelse=Constant)',  # closed_walk:2935
    'Return.value>List(elts=[IfExp],ctx=Load)',  # closed_walk:2972
    'Return.value>ListComp(elt=IfExp,generators=[comprehension])',  # closed_walk:2962
    'Return.value>Set(elts=[Attribute])',  # closed_walk:1800
    'Return.value>Tuple(elts=[Attribute|Name],ctx=Load)',  # test_a1_identity_formation:3798
    'Return.value>Tuple(elts=[BinOp|IfExp],ctx=Load)',  # closed_walk:2951
    'Return.value>Tuple(elts=[BinOp|ListComp],ctx=Load)',  # closed_walk:3056
    'Return.value>Tuple(elts=[Call|Constant|Name],ctx=Load)',  # closed_walk:1673
    'Return.value>Tuple(elts=[Call|Name],ctx=Load)',  # closed_walk:1442
    'Return.value>Tuple(elts=[Constant|Name|Tuple],ctx=Load)',  # closed_walk:1538
    'Return.value>Tuple(elts=[Constant|Subscript],ctx=Load)',  # closed_walk:2392
    'Return.value>Tuple(elts=[Constant|Tuple],ctx=Load)',  # closed_walk:2983
    'Return.value>Tuple(elts=[ListComp],ctx=Load)',  # closed_walk:3058
    'Return.value>Tuple(elts=[Name|Subscript],ctx=Load)',  # closed_walk:1394
    'Return.value>Tuple(elts=[Subscript|Tuple],ctx=Load)',  # closed_walk:1433
    "Set.elts>Attribute(value=Name,attr='value',ctx=Load)",  # closed_walk:1800
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[Call],is_async=0)',  # closed_walk:2437
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',  # closed_walk:2442
    'SetComp.generators>comprehension(target=Name,iter=Subscript,ifs=[],is_async=0)',  # closed_walk:2449
    'Slice.upper>IfExp(test=Compare,body=Constant,orelse=Constant)',  # closed_walk:2590
    'Starred.ctx>Store()',  # closed_walk:3081
    'Starred.value>Name(id=str,ctx=Store)',  # closed_walk:3081
    'Subscript.ctx>Del()',  # closed_walk:2800
    "Subscript.slice>Attribute(value=Subscript,attr='__code__',ctx=Load)",  # test_match_hold_admission_gate_pg:2785
    'Subscript.slice>Call(func=Attribute,args=[Name],keywords=[])',  # closed_walk:3001
    'Subscript.slice>Slice(lower=-,upper=IfExp,step=-)',  # closed_walk:2590
    "Subscript.value>Attribute(value=Name,attr='__mro__',ctx=Load)",  # closed_walk:1712
    "Subscript.value>Attribute(value=Name,attr='generators',ctx=Load)",  # closed_walk:2912
    "Subscript.value>Attribute(value=Name,attr='param_values',ctx=Load)",  # closed_walk:2982
    "Subscript.value>Attribute(value=Name,attr='parent',ctx=Load)",  # closed_walk:757
    'Subscript.value>Call(func=Attribute,args=[Call|Tuple],keywords=[])',  # test_a1_identity_formation:2393
    'Subscript.value>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:1717
    'Subscript.value>Subscript(value=Subscript,slice=Name,ctx=Load)',  # closed_walk:1750
    'Try.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # closed_walk:2609
    'Try.body>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg:2849
    'Try.body>For(target=Tuple,iter=Name,body=[If],orelse=[],type_comment=-)',  # closed_walk:2869
    'Try.body>If(test=Call,body=[Assign],orelse=[If])',  # closed_walk:2738
    'Try.body>If(test=Compare,body=[Return],orelse=[])',  # closed_walk:2718
    'Try.body>While(test=Name,body=[Assign|Expr|If],orelse=[])',  # closed_walk:2610
    'Try.body>With(items=[withitem],body=[Assign],type_comment=-)',  # closed_walk:1482
    'Try.body>With(items=[withitem],body=[Assign|Expr],type_comment=-)',  # closed_walk:2806
    'Try.finalbody>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',  # test_match_hold_admission_gate_pg:2854
    'Try.handlers>ExceptHandler(type=Name,name=-,body=[Pass])',  # test_a1_identity_formation:2275
    'Try.orelse>Assign(targets=[Subscript],value=Tuple,type_comment=-)',  # test_a1_identity_formation:2278
    "Tuple.elts>Attribute(value=Attribute,attr='attr',ctx=Load)",  # closed_walk:1461
    "Tuple.elts>Attribute(value=Call,attr='__name__',ctx=Load)",  # test_match_hold_admission_gate_pg:2809
    "Tuple.elts>Attribute(value=Name,attr='BinOp',ctx=Load)",  # closed_walk:2516
    "Tuple.elts>Attribute(value=Name,attr='DictComp',ctx=Load)",  # closed_walk:2514
    "Tuple.elts>Attribute(value=Name,attr='GeneratorExp',ctx=Load)",  # closed_walk:1613
    "Tuple.elts>Attribute(value=Name,attr='In',ctx=Load)",  # closed_walk:1623
    "Tuple.elts>Attribute(value=Name,attr='Is',ctx=Load)",  # closed_walk:2633
    "Tuple.elts>Attribute(value=Name,attr='IsNot',ctx=Load)",  # closed_walk:2633
    "Tuple.elts>Attribute(value=Name,attr='ListComp',ctx=Load)",  # closed_walk:1613
    "Tuple.elts>Attribute(value=Name,attr='NotIn',ctx=Load)",  # closed_walk:1623
    "Tuple.elts>Attribute(value=Name,attr='SetComp',ctx=Load)",  # closed_walk:1613
    "Tuple.elts>Attribute(value=Name,attr='__code__',ctx=Load)",  # closed_walk:2824
    "Tuple.elts>Attribute(value=Name,attr='__name__',ctx=Load)",  # test_a1_identity_formation:3798
    "Tuple.elts>Attribute(value=Name,attr='attr',ctx=Load)",  # closed_walk:1433
    "Tuple.elts>Attribute(value=Name,attr='comprehension',ctx=Load)",  # closed_walk:2995
    'Tuple.elts>BinOp(left=BinOp,op=Add,right=Subscript)',  # closed_walk:3130
    'Tuple.elts>BinOp(left=Name,op=Add,right=Name)',  # closed_walk:2951
    'Tuple.elts>BinOp(left=Subscript,op=Add,right=Tuple)',  # closed_walk:2359
    'Tuple.elts>Call(func=Attribute,args=[Attribute|Name],keywords=[])',  # closed_walk:1802
    'Tuple.elts>Call(func=Name,args=[GeneratorExp],keywords=[])',  # closed_walk:2451
    'Tuple.elts>IfExp(test=Compare,body=Constant,orelse=Call)',  # closed_walk:2951
    'Tuple.elts>ListComp(elt=Attribute,generators=[comprehension])',  # closed_walk:3056
    'Tuple.elts>Starred(value=Name,ctx=Store)',  # closed_walk:3081
    'Tuple.elts>Tuple(elts=[Attribute],ctx=Load)',  # closed_walk:1433
    'Tuple.elts>Tuple(elts=[Attribute|Constant|Name],ctx=Load)',  # closed_walk:1461
    'Tuple.elts>Tuple(elts=[Constant|Subscript|Tuple],ctx=Load)',  # closed_walk:1433
    'Tuple.elts>Tuple(elts=[],ctx=Load)',  # closed_walk:1538
    'UnaryOp.operand>BoolOp(op=Or,values=[Call|Compare])',  # closed_walk:2452
    'While.body>Assign(targets=[Tuple],value=Call,type_comment=-)',  # closed_walk:1773
    'While.body>Assign(targets=[Tuple],value=Tuple,type_comment=-)',  # closed_walk:1783
    'While.body>For(target=Name,iter=Call,body=[Expr],orelse=[],type_comment=-)',  # closed_walk:1789
    'While.body>If(test=BoolOp,body=[Assign],orelse=[If])',  # closed_walk:1784
    'While.body>If(test=BoolOp,body=[Expr],orelse=[If])',  # closed_walk:2905
    'While.body>If(test=Call,body=[Assign|Expr],orelse=[If])',  # closed_walk:1774
    'While.test>BoolOp(op=And,values=[Compare])',  # closed_walk:2904
    'With.body>Assign(targets=[Name],value=Call,type_comment=-)',  # closed_walk:1483
    'With.body>Expr(value=Call)',  # closed_walk:2807
    'With.items>withitem(context_expr=Call,optional_vars=Name)',  # closed_walk:1482
    'arguments.kwarg>arg(arg=str,annotation=-,type_comment=-)',  # closed_walk:2133
    'comprehension.ifs>BoolOp(op=And,values=[Call|Compare|UnaryOp])',  # closed_walk:1824
    'comprehension.ifs>Call(func=Attribute,args=[Constant],keywords=[])',  # closed_walk:3071
    'comprehension.ifs>Compare(left=Attribute,ops=[Eq],comparators=[Name])',  # closed_walk:1505
    'comprehension.ifs>Compare(left=Name,ops=[In],comparators=[Call])',  # closed_walk:1721
    'comprehension.ifs>Compare(left=Name,ops=[In],comparators=[Tuple])',  # closed_walk:2442
    'comprehension.ifs>Compare(left=Name,ops=[Is],comparators=[Name])',  # closed_walk:1598
    'comprehension.ifs>Compare(left=Name,ops=[NotEq],comparators=[Name])',  # closed_walk:2886
    "comprehension.iter>Attribute(value=Attribute,attr='elts',ctx=Load)",  # closed_walk:1593
    "comprehension.iter>Attribute(value=Name,attr='__mro__',ctx=Load)",  # closed_walk:1732
    "comprehension.iter>Attribute(value=Name,attr='defaults',ctx=Load)",  # closed_walk:3052
    "comprehension.iter>Attribute(value=Name,attr='generators',ctx=Load)",  # closed_walk:1614
    "comprehension.iter>Attribute(value=Name,attr='ifs',ctx=Load)",  # closed_walk:1619
    "comprehension.iter>Attribute(value=Name,attr='kw_defaults',ctx=Load)",  # closed_walk:3055
    "comprehension.iter>Attribute(value=Name,attr='ops',ctx=Load)",  # closed_walk:2633
    "comprehension.iter>Attribute(value=Name,attr='targets',ctx=Load)",  # closed_walk:1823
    'comprehension.iter>BinOp(left=Call,op=Add,right=Call)',  # closed_walk:2513
    'comprehension.iter>BinOp(left=Call,op=Add,right=List)',  # closed_walk:1200
    'comprehension.iter>BinOp(left=Call,op=Add,right=ListComp)',  # closed_walk:2573
    'comprehension.iter>BinOp(left=Name,op=Add,right=Attribute)',  # closed_walk:3056
    'comprehension.iter>BinOp(left=Name,op=Sub,right=Set)',  # test_a1_identity_formation:2390
    'comprehension.iter>Subscript(value=Attribute,slice=Slice,ctx=Load)',  # closed_walk:1720
    'comprehension.iter>Subscript(value=Name,slice=Constant,ctx=Load)',  # closed_walk:2449
    'comprehension.iter>Subscript(value=Name,slice=Name,ctx=Load)',  # closed_walk:2963
    "keyword.value>Attribute(value=Name,attr='policy',ctx=Load)",  # test_match_hold_admission_gate_pg:598
    'keyword.value>Compare(left=Name,ops=[Is],comparators=[Name])',  # test_a1_identity_formation:2283
    'keyword.value>Dict(keys=[Name],values=[Tuple])',  # closed_walk:3183
    'keyword.value>List(elts=[],ctx=Load)',  # test_match_hold_admission_gate_pg:599
    'withitem.context_expr>Call(func=Attribute,args=[],keywords=[])',  # closed_walk:1482
    'withitem.optional_vars>Name(id=str,ctx=Store)',  # closed_walk:1482
})
WALKER_SHAPES = WALKER_SHAPES | R11_ID_WALKER_SHAPES

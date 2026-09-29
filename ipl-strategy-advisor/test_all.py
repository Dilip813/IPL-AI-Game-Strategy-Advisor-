"""
IPL / Cricket regression test suite — IPL AI Game Strategy Advisor
Run from the project root: python test_all.py
"""
import sys, json, urllib.request, urllib.parse, subprocess, time

import os
BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
proc = subprocess.Popen(
    [sys.executable, 'app.py'],
    cwd=BACKEND,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(3)

results = []

def get(path):
    with urllib.request.urlopen('http://127.0.0.1:5000' + path, timeout=8) as r:
        return json.loads(r.read()), r.status

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request('http://127.0.0.1:5000' + path,
        data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

def chk(name, cond):
    results.append((name, bool(cond)))

# ===========================================================
# CRICKET / IPL TESTS
# ===========================================================
print("--- CRICKET / IPL TESTS ---")

# Health check
h, c = get('/api/health')
chk('health: 200 ok', c == 200 and h['status'] == 'ok')
chk('health: sport=cricket', h.get('sport') == 'cricket')
chk('health: league=IPL', h.get('league') == 'IPL')

ct, c = get('/api/cricket/teams')
chk('cricket: teams 200', c == 200)
chk('cricket: 8 IPL teams', len(ct['teams']) >= 8)
chk('cricket: has venues', len(ct['venues']) > 0)
chk('cricket: has seasons', len(ct['seasons']) > 0)
chk('cricket: data notice present', bool(ct['data_notice']))

cm, c = get('/api/cricket/matches')
chk('cricket: matches 200', c == 200)
chk('cricket: 10 IPL matches', cm['count'] >= 10)
chk('cricket: no football keys', 'home_team' not in cm['matches'][0])
chk('cricket: has team1/team2', 'team1' in cm['matches'][0] and 'team2' in cm['matches'][0])

cs, c = get('/api/cricket/team-stats/' + urllib.parse.quote('Chennai Super Kings'))
chk('cricket: team-stats 200', c == 200)
chk('cricket: CSK preferred approach', cs['stats']['preferred_approach'] in ('bat first', 'chase'))

ctp, c = get('/api/cricket/tactical-patterns')
chk('cricket: tactical-patterns 200', c == 200)
chk('cricket: has IPL patterns', len(ctp['patterns']) > 0)

# Full analysis CSK vs MI
ca, c = post('/api/cricket/analyze', {
    'our_team': 'Chennai Super Kings', 'opponent': 'Mumbai Indians'})
chk('cricket: analyze 200', c == 200)
chk('cricket: sport=cricket', ca.get('sport') == 'cricket')
chk('cricket: league=IPL', ca.get('league') == 'IPL')
chk('cricket: has 4 sections', all(k in ca for k in ['match_analysis','opponent_profile','recommendation','insights']))
chk('cricket: agent name has IPL', 'IPL' in ca['match_analysis']['agent'])
chk('cricket: retrieved matches', ca['match_analysis']['retrieved_match_count'] >= 1)
chk('cricket: bowling plan', bool(ca['recommendation']['bowling']['powerplay']))
chk('cricket: batting plan', bool(ca['recommendation']['batting']['powerplay']))
chk('cricket: toss advice', bool(ca['recommendation']['toss_advice']))
chk('cricket: match situation', bool(ca['recommendation']['match_situation_strategy']))
chk('cricket: fielding suggestions', len(ca['recommendation']['fielding_suggestions']) > 0)
chk('cricket: key insights 4+', len(ca['insights']['key_insights']) >= 4)
chk('cricket: phase analysis present', 'phase_analysis' in ca['match_analysis'])
chk('cricket: h2h present', 'h2h_record' in ca['match_analysis'])
chk('cricket: opponent powerplay profile', bool(ca['opponent_profile']['powerplay_profile']))
chk('cricket: opponent strengths', len(ca['opponent_profile']['strengths']) > 0)
chk('cricket: opponent weaknesses', len(ca['opponent_profile']['weaknesses']) > 0)

# Analyze SRH vs Punjab
ca2, c2 = post('/api/cricket/analyze', {
    'our_team': 'Sunrisers Hyderabad', 'opponent': 'Punjab Kings'})
chk('cricket: analyze2 200', c2 == 200)
chk('cricket: analyze2 pp profile', ca2['opponent_profile']['powerplay_profile'] is not None)

# Analyze with venue
ca3, c3 = post('/api/cricket/analyze', {
    'our_team': 'Chennai Super Kings', 'opponent': 'Royal Challengers Bengaluru',
    'venue': 'MA Chidambaram Stadium, Chennai'})
chk('cricket: analyze with venue 200', c3 == 200)
chk('cricket: venue stored', ca3.get('venue') == 'MA Chidambaram Stadium, Chennai')

# What-If scenarios
cw, cw_c = post('/api/cricket/what-if', {
    'scenario': 'We lost 2 wickets in the powerplay',
    'our_team': 'Chennai Super Kings', 'opponent': 'Mumbai Indians'})
chk('cricket: whatif 200', cw_c == 200)
chk('cricket: whatif sport=cricket', cw.get('sport') == 'cricket')
chk('cricket: whatif has advice', bool(cw['tactical_adjustment']))
chk('cricket: whatif 2-wicket type', '2 wickets' in cw['scenario_type'])

cw2, _ = post('/api/cricket/what-if', {
    'scenario': 'We are chasing a high total',
    'our_team': 'Mumbai Indians', 'opponent': 'Sunrisers Hyderabad'})
chk('cricket: whatif high chase', bool(cw2['tactical_adjustment']))
chk('cricket: whatif has evidence', isinstance(cw2['supporting_evidence'], list))

cw3, _ = post('/api/cricket/what-if', {
    'scenario': 'Key bowler is unavailable',
    'our_team': 'Chennai Super Kings', 'opponent': 'Kolkata Knight Riders'})
chk('cricket: whatif bowler unavailable', 'bowler' in cw3['scenario_type'])

cw4, _ = post('/api/cricket/what-if', {
    'scenario': 'We are defending a low total',
    'our_team': 'Mumbai Indians', 'opponent': 'Delhi Capitals'})
chk('cricket: whatif low total', bool(cw4['tactical_adjustment']))

cw5, _ = post('/api/cricket/what-if', {
    'scenario': 'Need 60 runs from 30 balls',
    'our_team': 'Rajasthan Royals', 'opponent': 'Punjab Kings'})
chk('cricket: whatif 60-from-30', bool(cw5['tactical_adjustment']))

# Real-time events
cr, cr_c = post('/api/cricket/realtime', {
    'event': 'Opponent scored 68 in the powerplay',
    'our_team': 'Chennai Super Kings', 'opponent': 'Mumbai Indians'})
chk('cricket: realtime 200', cr_c == 200)
chk('cricket: realtime sport=cricket', cr.get('sport') == 'cricket')
chk('cricket: realtime adjustment', bool(cr['immediate_adjustment']))

cr2, _ = post('/api/cricket/realtime', {
    'event': 'We have lost 3 wickets in 5 overs',
    'our_team': 'Mumbai Indians', 'opponent': 'Royal Challengers Bengaluru'})
chk('cricket: realtime 3 wickets', '3' in cr2['immediate_adjustment'] or 'wicket' in cr2['immediate_adjustment'].lower())

cr3, _ = post('/api/cricket/realtime', {
    'event': 'New batter at the crease for opponent',
    'our_team': 'Chennai Super Kings', 'opponent': 'Kolkata Knight Riders'})
chk('cricket: realtime new batter', bool(cr3['immediate_adjustment']))

# Data isolation — football teams must be rejected
ce, ce_c = post('/api/cricket/analyze', {'our_team': 'FC Atlas', 'opponent': 'Mumbai Indians'})
chk('cricket: football team rejected by cricket endpoint', ce_c == 400)

ce2, ce2_c = post('/api/cricket/analyze', {'our_team': 'Chennai Super Kings', 'opponent': 'Chennai Super Kings'})
chk('cricket: same-team 400', ce2_c == 400)

# Football endpoints must NOT exist
try:
    _, fc = get('/api/teams')
    chk('no football /api/teams endpoint', fc == 404)
except Exception:
    chk('no football /api/teams endpoint', True)

try:
    _, fc = post('/api/analyze', {'our_team': 'FC Atlas', 'opponent': 'Riverside United'})
    chk('no football /api/analyze endpoint', fc == 404)
except Exception:
    chk('no football /api/analyze endpoint', True)

proc.terminate()
proc.wait()

# ===========================================================
# REPORT
# ===========================================================
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print()
print("=" * 56)
print(f"  Test Results: {passed}/{total} passed")
print(f"  IPL / Cricket tests: {passed}/{total}")
print("=" * 56)
for name, ok in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}")
if passed < total:
    sys.exit(1)
else:
    print()
    print("ALL TESTS PASSED")

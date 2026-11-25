"""Parser test against HTML shaped like Wikipedia's 'NBA career statistics' tables (sup footnotes,
† champion / * league-leader markers, a traded season with rowspan, colspan career row)."""
from app.providers.wiki_stats import parse_tables

HTML = """
<h2 id="NBA_career_statistics">NBA career statistics</h2>
<table class="wikitable"><tr><td>Legend</td></tr></table>
<h3>Regular season</h3>
<table class="wikitable sortable" style="text-align:right">
<tr><th>Year</th><th>Team</th><th>GP</th><th>GS</th><th>MPG</th><th>FG%</th><th>3P%</th><th>FT%</th><th>RPG</th><th>APG</th><th>SPG</th><th>BPG</th><th>PPG</th></tr>
<tr><td style="text-align:left;"><a href="#">2014–15</a>†</td><td>Golden State</td><td>80</td><td>80</td><td>32.7</td><td>.487</td><td>.443</td><td>.914</td><td>4.3</td><td>7.7</td><td>2.0</td><td>.2</td><td>23.8</td></tr>
<tr><td>2015–16</td><td>Golden State</td><td>79</td><td>79</td><td>34.2</td><td>.504</td><td>.454</td><td>.908*</td><td>5.4</td><td>6.7</td><td>2.1*</td><td>.2</td><td>30.1*<sup>[a]</sup></td></tr>
<tr><td rowspan="2">2017–18</td><td>Team A</td><td>40</td><td>40</td><td>30.0</td><td>.450</td><td>.350</td><td>.800</td><td>5.0</td><td>4.0</td><td>1.0</td><td>.5</td><td>20.0</td></tr>
<tr><td>Team B</td><td>20</td><td>20</td><td>30.0</td><td>.480</td><td>.380</td><td>.820</td><td>6.0</td><td>5.0</td><td>1.2</td><td>.6</td><td>26.0</td></tr>
<tr><td colspan="2">Career</td><td>1,069</td><td>1,060</td><td>34.3</td><td>.471</td><td>.422</td><td>.911</td><td>4.6</td><td>6.4</td><td>1.5</td><td>.2</td><td>24.8</td></tr>
</table>
<h3>Playoffs</h3>
<table class="wikitable"><tr><th>Year</th><th>Team</th><th>GP</th><th>PPG</th></tr><tr><td>2015</td><td>GS</td><td>21</td><td>28.3</td></tr></table>
"""


def test_parses_regular_season_table():
    d = parse_tables(HTML)
    rows = {r["season"]: r for r in d["rows"]}
    assert rows["2014–15"]["champion"] and rows["2014–15"]["PPG"] == 23.8 and rows["2014–15"]["GP"] == 80
    assert rows["2015–16"]["PPG"] == 30.1 and rows["2015–16"]["led_league"] == {"FT%": True, "SPG": True, "PPG": True}
    t = rows["2017–18"]
    assert t["computed"] and t["GP"] == 60 and t["PPG"] == 22.0 and "Team A / Team B" == t["team"]
    assert d["career"]["GP"] == 1069 and d["career"]["PPG"] == 24.8
    assert len(d["rows"]) == 3


def test_playoffs_section():
    d = parse_tables(HTML, "Playoffs")
    assert d["rows"][0]["PPG"] == 28.3

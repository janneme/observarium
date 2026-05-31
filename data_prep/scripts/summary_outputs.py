#!/usr/bin/env python3
import json
from pathlib import Path

out = Path(__file__).parent.parent / 'output'
stars9 = out / 'stars.m9.json'
dbl = out / 'double_stars.json'
vs = Path(__file__).parent / 'sources' / 'variable_stars_m9.csv'
print('stars exists', stars9.exists())
print('double exists', dbl.exists())
print('variable csv exists', vs.exists())
if stars9.exists():
    data = json.load(stars9.open())
    total = sum(len(v) for v in data.values())
    print('stars total', total, 'constellations', len(data))
if dbl.exists():
    g = json.load(dbl.open())
    print('double systems', len(g))

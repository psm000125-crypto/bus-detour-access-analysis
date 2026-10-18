"""Independently reselect entrance nodes and inspect original wheelchair tags."""
from pathlib import Path
import json,csv,sys,hashlib,collections,math
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.venv_transport/Lib/site-packages'))
import pyproj
pyproj.network.set_network_enabled(False)
raw_path=ROOT/'data_13/raw/osm_medium_windows_response.txt'
query=(ROOT/'data_13/raw/osm_medium_query.txt').read_text(encoding='utf8')
raw=json.loads(raw_path.read_text(encoding='utf8'))
stops=list(csv.DictReader((ROOT/'data_10/selected_stops_20260402.csv').open(encoding='utf-8-sig')))
stop=next(r for r in stops if r['ARS_ID']=='02006')
tr=pyproj.Transformer.from_crs(4326,32652,always_xy=True)
sx,sy=tr.transform(float(stop['X좌표']),float(stop['Y좌표']))
nodes=collections.defaultdict(list)
for e in raw['elements']:
    if e['type']=='node':nodes[e['id']].append(e)
selected=[]
for nid,versions in nodes.items():
    tagged=[e for e in versions if e.get('tags',{}).get('railway')=='subway_entrance']
    if not tagged:continue
    first=tagged[0]
    x,y=tr.transform(first['lon'],first['lat']);distance=math.hypot(x-sx,y-sy)
    if distance<=500+1e-7:
        assert all(e.get('tags')==first['tags'] for e in tagged)
        selected.append({'osm_id':nid,'distance_from_stop_m':distance,'wheelchair_tag_present':'wheelchair' in first['tags'],
                         'wheelchair_tag_value':first['tags'].get('wheelchair'),
                         'tagged_body_records':len(tagged),'skeletal_records':sum(not bool(e.get('tags')) for e in versions),
                         'full_tags':first['tags']})
selected.sort(key=lambda r:r['osm_id'])
csv_rows=list(csv.DictReader((ROOT/'data_29/accessibility.csv').open(encoding='utf-8-sig')))
csv_by_id={int(r['origin'][1:]):r for r in csv_rows}
assert set(csv_by_id)=={r['osm_id'] for r in selected}
for row in selected:assert csv_by_id[row['osm_id']]['wheelchair_tag']==(row['wheelchair_tag_value'] if row['wheelchair_tag_present'] else 'unknown')
result={'selected':len(selected),'counts':dict(collections.Counter(r['wheelchair_tag_value'] if r['wheelchair_tag_present'] else 'missing' for r in selected)),
        'all_csv_ids_and_tags_match':True,'each_selected_node_has_tagged_body_record':all(r['tagged_body_records']>0 for r in selected),
        'query_explicitly_selects_entrance_nodes':'node["railway"="subway_entrance"]' in query,
        'query_body_before_recursion':'out body;>;out skel' in query,
        'query':query.strip(),'raw_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        'interpretation':'missing means no wheelchair key in the selected historical OSM node tags; not absence of all access information or real-world inaccessibility',
        'nodes':selected}
(ROOT/'data_30/peer_access_recheck.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='nodes'},ensure_ascii=False,indent=2))

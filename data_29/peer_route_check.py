"""Diagnostic route reconstruction with mapped linear bus platforms only.

Does not edit model sources or add geometric links.
"""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.venv_transport/Lib/site-packages'),str(ROOT/'data_13')]
import networkx as nx
from recompute_expanded import build,choose_origins,prepare,base
contract,_,_,_,sources,tr=prepare()
_,nodes,ways=base.read_osm(ROOT/'data_13/raw/osm_medium_windows_response.txt')
entries=choose_origins(nodes,tr,sources['S'],500)
g,anchors,engine=build(nodes,ways,sources,contract,entries,0)
original_allowed=base.allowed
def revised_allowed(tags,mode):
    if tags.get('highway')=='platform' and tags.get('public_transport')=='platform' and tags.get('bus')=='yes' and tags.get('area')!='yes':
        return original_allowed({**tags,'highway':'footway'},mode)
    return original_allowed(tags,mode)
base.allowed=revised_allowed
base.EXPLICIT.add('platform')
newg,newanchors,newengine=build(nodes,ways,sources,contract,entries,0)
origin='N3390524793'
to_s=base.shortest(newg,newanchors[origin]['node'],newengine.s)
to_a=base.shortest(newg,newanchors[origin]['node'],newengine.a)
first_nodes=[3390524793,3390512593,3390980836,3390980835,3390980834,3390941198,3390941197]
xy={n:tr.transform(nodes[n]['lon'],nodes[n]['lat']) for n in first_nodes}
first_length=sum(math.dist(xy[u],xy[v]) for u,v in zip(first_nodes,first_nodes[1:]))
result={'interpretation':'diagnostic model-filter repair using existing shared-node platform ways; no field accessibility certification',
        'resolved_before':len(engine.origins),'resolved_after':len(newengine.origins),
        'first_main_connection_length_m':first_length,'platform_bridge_length_m':math.dist(xy[3390941198],xy[3390941197]),
        'original_anchor':anchors[origin],'revised_anchor':newanchors[origin],
        'anchor_S_before':anchors['S'],'anchor_S_after':newanchors['S'],
        'anchor_A_before':anchors['A'],'anchor_A_after':newanchors['A'],
        'to_original_stop':to_s,'to_alternative':to_a,
        'added_platform_way_ids':[w for w in ways if not original_allowed(ways[w].get('tags',{}),'street_assumed') and revised_allowed(ways[w].get('tags',{}),'street_assumed')],
        'new_route_way_records':[{**ways[w]} for w in sorted({newg[u][v]['way_id'] for route in [to_s,to_a] for u,v in zip(route['path'],route['path'][1:])})]}
changes=[]
for name in engine.origins:
    oldrow=engine.row(name,());newrow=newengine.row(name,())
    changes.append({'origin':name,'old_D_known_m':oldrow['D_known_m'],'new_D_known_m':newrow['D_known_m'],
                    'D_known_change_m':newrow['D_known_m']-oldrow['D_known_m'],
                    'old_D_stop_m':oldrow['D_stop_m'],'new_D_stop_m':newrow['D_stop_m'],
                    'D_stop_change_m':newrow['D_stop_m']-oldrow['D_stop_m'],
                    'old_anchor':anchors[name]['node'],'new_anchor':newanchors[name]['node']})
result['old21_changes']=changes
result['old21_anchors_changed']=sum(r['old_anchor']!=r['new_anchor'] for r in changes)
result['old21_D_known_changed']=sum(abs(r['D_known_change_m'])>1e-6 for r in changes)
result['old21_D_stop_changed']=sum(abs(r['D_stop_change_m'])>1e-6 for r in changes)
result['max_abs_known_change_m']=max(abs(r['D_known_change_m']) for r in changes)
result['max_abs_stop_change_m']=max(abs(r['D_stop_change_m']) for r in changes)
(ROOT/'data_29/peer_route_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='new_route_way_records'},ensure_ascii=False,indent=2))

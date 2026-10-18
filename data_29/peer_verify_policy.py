"""Independent enumeration and explicit shortest-path checks for revised policies."""
from pathlib import Path
import sys,json,itertools
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.venv_transport/Lib/site-packages'),str(ROOT/'data_29'),str(ROOT/'data_11')]
import networkx as nx
from reanalyze_platforms import model
from evaluate_policies import evaluate_journey
raw,nodes,ways,entries,graph,anchors,engine=model()
result=json.loads((ROOT/'data_29/results.json').read_text(encoding='utf8'))
tolerance=1e-7
onward=nx.single_source_dijkstra_path_length(graph,engine.a,weight='length_m')
to_stop=nx.single_source_dijkstra_path_length(graph,engine.s,weight='length_m')
origin_paths={e['origin']:nx.shortest_path(graph,anchors[e['origin']]['node'],engine.s,weight='length_m') for e in entries}
candidates=set()
for path in origin_paths.values():
    for node in path[:-1]:
        if (graph.degree(node)>=3 or node==path[0]) and to_stop[node]<=450+tolerance and any(d['highway'] not in {'steps','corridor'} for _,_,d in graph.edges(node,data=True)):
            candidates.add(node)
candidates=sorted(candidates,key=str)
scores=[]
for pair in itertools.combinations(candidates,2):
    distances=[];excesses=[];encountered=0
    for name,path in origin_paths.items():
        first=next((n for n in path[:-1] if n in pair),None)
        if first is None:
            dist=nx.path_weight(graph,path,'length_m')+onward[engine.s]
        else:
            encountered+=1
            dist=nx.path_weight(graph,path[:path.index(first)+1],'length_m')+onward[first]
        distances.append(dist);excesses.append(max(0,dist-onward[path[0]]))
    scores.append({'candidates':list(pair),'covered':encountered,'max_E_m':max(excesses),'sum_E_m':sum(excesses),'max_D_m':max(distances)})
criteria={'coverage_strong':[('covered',-1),('max_E_m',1),('sum_E_m',1)],'efficiency':[('sum_E_m',1),('max_E_m',1)],'equity':[('max_E_m',1),('sum_E_m',1)],'total_distance_equity':[('max_D_m',1),('max_E_m',1),('sum_E_m',1)]}
selected={}
for name,rules in criteria.items():
    pool=scores
    for metric,direction in rules:
        best=min(direction*r[metric] for r in pool)
        pool=[r for r in pool if direction*r[metric]<=best+tolerance]
    selected[name]=min(pool,key=lambda r:tuple(map(str,r['candidates'])))
    assert selected[name]['candidates']==result['policies']['2'][name]['candidates'],name
    for metric in ['covered','max_E_m','sum_E_m','max_D_m']:
        assert abs(selected[name][metric]-result['policies']['2'][name][metric])<tolerance,(name,metric)
max_error=0
for name,policy in selected.items():
    for origin,path in origin_paths.items():
        explicit=evaluate_journey(graph,path[0],engine.s,engine.a,policy['candidates'])
        cached=engine.row(origin,policy['candidates'])
        assert explicit['first_notice']==cached['first_notice']
        for metric in ['D_known_m','D_stop_m','D_policy_m','E_stop_m','E_policy_m','reduction_m']:
            err=abs(explicit[metric]-cached[metric]);max_error=max(max_error,err)
            assert err<tolerance,(name,origin,metric,err)
stairs=graph.copy();stairs.remove_edges_from([(u,v) for u,v,d in graph.edges(data=True) if d['steps']])
disconnected=[name for name,path in origin_paths.items() if not nx.has_path(stairs,path[0],engine.a)]
report={'resolved':len(origin_paths),'candidate_count':len(candidates),'pairs_enumerated':len(scores),'all_4_optima_match':True,'selected':selected,'explicit_evaluator_rows_checked':len(selected)*len(origin_paths),'max_absolute_error_m':max_error,'stairs_only_disconnected_origins':disconnected}
(ROOT/'data_29/peer_policy_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))

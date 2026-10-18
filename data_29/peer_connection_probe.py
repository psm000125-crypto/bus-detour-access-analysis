"""Read-only OSM connectivity diagnostic; writes only diagnostic outputs."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.venv_transport/Lib/site-packages'),str(ROOT/'data_10')]
import networkx as nx
from analyze_walks import read_osm,allowed

results=[]
for rel in ['data_13/raw/osm_medium_windows_response.txt','data_10/raw/osm_20260405.json','data_10/raw/osm_current.json']:
    path=ROOT/rel
    raw,nodes,ways=read_osm(path)
    graphs={}
    for mode in ['street_assumed','pedestrian_only','platform_only_added','all_highway']:
        graph=nx.Graph()
        for wid,w in ways.items():
            tags=w.get('tags',{})
            use=bool(tags.get('highway')) if mode=='all_highway' else allowed(tags,mode)
            if mode=='platform_only_added' and tags.get('highway')=='platform' and tags.get('foot') not in {'no','private'} and tags.get('access') not in {'no','private'}:
                use=True
            if use:
                for u,v in zip(w['nodes'],w['nodes'][1:]):graph.add_edge(u,v,way_id=wid)
        graphs[mode]=graph
    graph=graphs['street_assumed'];origin=3390524793
    component=nx.node_connected_component(graph,origin) if origin in graph else set()
    incidents=[]
    for wid,w in ways.items():
        common=component.intersection(w['nodes'])
        if common:incidents.append({'id':wid,'tags':w.get('tags',{}),'nodes':w['nodes'],'shared_component_nodes':sorted(common),'allowed':allowed(w.get('tags',{}),'street_assumed')})
    result={'source':rel,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'origin':nodes.get(origin),'component_size':len(component),'component_nodes':sorted(component),'incidents':incidents,
            'all_highway_component_size':len(nx.node_connected_component(graphs['all_highway'],origin)) if origin in graphs['all_highway'] else 0,
            'platform_added_component_size':len(nx.node_connected_component(graphs['platform_only_added'],origin)) if origin in graphs['platform_only_added'] else 0,
            'metadata':raw.get('osm3s')}
    platform_graph=graphs['platform_only_added']
    main_component=max(nx.connected_components(graph),key=len)
    if origin in platform_graph:
        component2=nx.node_connected_component(platform_graph,origin)
        main_intersection=component2.intersection(main_component)
        result['platform_added_main_intersection']=len(main_intersection)
        if main_intersection:
            routes=nx.single_source_shortest_path(platform_graph,origin)
            target=min(main_intersection,key=lambda n:len(routes[n]));route=routes[target]
            result['platform_added_first_main_path']={'nodes':route,'ways':[platform_graph[u][v]['way_id'] for u,v in zip(route,route[1:])]}
            used=set(result['platform_added_first_main_path']['ways'])
            result['platform_added_first_main_ways']=[ways[w] for w in used]
    results.append(result)
(ROOT/'data_29/peer_connection_probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))

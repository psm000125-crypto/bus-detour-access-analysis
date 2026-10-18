"""Reproduce source-table agreement and policy checks without AI calls or network."""
from pathlib import Path
import csv, hashlib, json, math
ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,obj):(ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
selection=load(ROOT/'ai_selection.json')
prediction=load(ROOT/'ai_predictions.json')
reference=load(ROOT/'ai_reference_peer.json')
snapshot=load(ROOT/'ai_sources.json')
assert snapshot['original_response_sha256']==reference['source_sha256']
for record in snapshot['records']:
    assert hashlib.sha256(record['text'].encode()).hexdigest()==record['text_sha256']
raw=ROOT/'raw/notice_list.json'
if raw.exists():
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==reference['source_sha256']
assert reference['prediction_outputs_seen'] is False
pred={r['id']:r for r in prediction['rows']}
ref={r['id']:r for r in reference['records']}
assert set(pred)==set(ref)==set(selection['ids'])
comparisons=[]
for id in selection['ids']:
    for field in selection['fields']:
        comparisons.append({'id':id,'field':field,'prediction':pred[id][field],
                            'reference':ref[id][field],'match':pred[id][field]==ref[id][field]})
dates={r['id']:r['createDate'] for r in snapshot['records']}
ai={'notices':len(pred),'fields_per_notice':len(selection['fields']),
    'field_matches':sum(c['match'] for c in comparisons),'field_comparisons':len(comparisons),
    'agreement_percent':100*sum(c['match'] for c in comparisons)/len(comparisons),
    'empty_route_lists':sum(not r['explicit_route_numbers'] for r in pred.values()),
    'per_field':{f:{'matched':sum(c['match'] for c in comparisons if c['field']==f),'n':len(pred)} for f in selection['fields']},
    'source_publication_dates':{id:dates[id] for id in selection['ids']},'comparisons':comparisons,
    'time_conflicts_flagged':['6236: 07:30-09:10 is 100 minutes, but literal source also says 2 hours'],
    'gold_standard':'Separate agent source reading, not independently labeled human ground truth',
    'actual_independent_model_api_calls':0,'human_time_savings_measured':False,
    'scope':'Agreement on archived text and title; no attachment, OCR, stop-coordinate, unseen-population or field-travel performance claim.'}
save('ai_evaluation.json',ai)
res=load(ROOT.parent/'data_29/results.json')
by_policy={r['policy']:r for r in res['summary']}
cov,eff,eq=[by_policy[p] for p in ['coverage_strong','efficiency','equity']]
access=list(csv.DictReader(open(ROOT.parent/'data_29/accessibility.csv',encoding='utf-8-sig')))
priority={r['origin'] for r in access if r['status']!='mapped_route_needs_field_check'}
rows=list(csv.DictReader(open(ROOT.parent/'data_29/journeys.csv',encoding='utf-8-sig')))
lookup={(r['origin'],r['policy']):r for r in rows}
checks=[]
for origin in sorted(priority):
    before,after=lookup[origin,'coverage_strong'],lookup[origin,'efficiency']
    delta=float(after['E_policy_m'])-float(before['E_policy_m'])
    assert delta<=1e-7
    checks.append({'origin':origin,'label':before['label'],'coverage_E_m':float(before['E_policy_m']),
                   'recommended_E_m':float(after['E_policy_m']),'change_m':delta})
factor_g_km=30.4*69300/1000/15
illustration=0.01*5*factor_g_km
assert math.isclose(factor_g_km,140.448) and math.isclose(illustration,7.0224)
out={'default_policy':'efficiency','default_candidates':eff['candidates'],
     'sum_reduction_vs_coverage_m':cov['sum_E_m']-eff['sum_E_m'],
     'sum_reduction_vs_coverage_percent':100*(cov['sum_E_m']-eff['sum_E_m'])/cov['sum_E_m'],
     'maximum_total_distance_is_lowest_among_displayed_criteria':eff['max_D_m']==min(r['max_D_m'] for r in [cov,eff,eq]),
     'late_information_share_of_added_distance_percent':100*(1-eff['location_share_added']),
     'equity_maximum_total_distance_increase_m':eq['max_D_m']-cov['max_D_m'],
     'priority_general_path_checks':checks,'step_free_paths_verified':False,
     'carbon':{'avoidance_fraction_assumption':.01,'car_km_assumption':5,'occupancy_assumption':1,
               'fuel_economy_km_per_litre_assumption':15,'tailpipe_CO2_g_per_vehicle_km':factor_g_km,
               'gross_avoided_CO2_g_per_target_journey':illustration,'actual_net_reduction':False}}
assert out['maximum_total_distance_is_lowest_among_displayed_criteria']
save('policy_and_carbon_checks.json',out)
print(json.dumps({'ai_field_agreement':f"{ai['field_matches']}/{ai['field_comparisons']}",
    'source_dates':ai['source_publication_dates'],'policy_sum_reduction_percent':out['sum_reduction_vs_coverage_percent'],
    'priority_general_paths_checked':len(checks),'carbon_g_per_target_journey':illustration},ensure_ascii=False,indent=2))

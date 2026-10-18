"""Reproduce source-table agreement and policy checks without AI calls or network."""
from pathlib import Path
import csv, hashlib, json, math
DATA=Path(__file__).resolve().parents[1]/"data"
ROOT=DATA/"results"
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,obj):(ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
bundle=load(DATA/'ai_notice_extraction.json')
selection=bundle['selection']
prediction=bundle['predictions']
reference=bundle['reference']
snapshot=bundle['sources']
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
parameters=load(DATA/'carbon_parameters.json')
factor_g_km=parameters['gasoline_net_heat_MJ_per_L']*parameters['CO2_kg_per_TJ']/1000/15
illustration=0.01*5*factor_g_km
assert math.isclose(factor_g_km,140.448) and math.isclose(illustration,7.0224)
save('carbon_example.json', {'avoidance_fraction_assumption':0.01, 'car_km_assumption':5,
    'occupancy_assumption':1, 'fuel_economy_km_per_litre_assumption':15,
    'tailpipe_CO2_g_per_vehicle_km':factor_g_km,
    'gross_avoided_CO2_g_per_target_journey':illustration, 'actual_net_reduction':False})
print(json.dumps({'source_field_matches':ai['field_matches'],
    'field_comparisons':ai['field_comparisons'],
    'carbon_example_g_per_target_journey':illustration}, ensure_ascii=False))

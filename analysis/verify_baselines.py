"""Verify current-model no-harm and keep three policy baselines distinct."""
from pathlib import Path
import csv, hashlib, json, math
ROOT=DATA=Path(__file__).resolve().parents[1]/"data/results"
rows=list(csv.DictReader(open(DATA/'journeys.csv',encoding='utf-8-sig')))
groups={p:{r['origin']:r for r in rows if r['policy']==p} for p in ['equity','coverage_strong','efficiency']}
assert all(len(g)==22 for g in groups.values())
diffs=[]; comparisons={}
for name in ['stop_only','coverage_strong','efficiency']:
    counts={'better':0,'same':0,'worse':0}
    for origin,selected in groups['equity'].items():
        current=float(selected['D_policy_m'])
        baseline=float(selected['D_stop_m']) if name=='stop_only' else float(groups[name][origin]['D_policy_m'])
        change=current-baseline
        status='same' if abs(change)<=1e-7 else ('better' if change<0 else 'worse')
        counts[status]+=1
        diffs.append({'baseline':name,'origin':origin,'label':selected['label'],
                      'baseline_D_m':baseline,'recommended_D_m':current,'change_m':change,
                      'classification':status,'encounters_additional_notice':bool(selected['first_notice'])})
    comparisons[name]=counts
assert comparisons=={'stop_only':{'better':11,'same':11,'worse':0},
                     'coverage_strong':{'better':11,'same':0,'worse':11},
                     'efficiency':{'better':4,'same':8,'worse':10}}
stop=[r for r in diffs if r['baseline']=='stop_only']
reached=[r for r in stop if r['encounters_additional_notice']]
unreached=[r for r in stop if not r['encounters_additional_notice']]
assert len(reached)==len(unreached)==11
assert all(r['classification']=='better' for r in reached)
assert all(r['classification']=='same' for r in unreached)
for r in groups['equity'].values():
    assert math.isclose(float(r['D_policy_m'])-float(r['D_known_m']),float(r['E_policy_m']),abs_tol=1e-7)
    assert math.isclose(float(r['D_stop_m'])-float(r['D_known_m']),float(r['E_stop_m']),abs_tol=1e-7)
result={'recommended_policy':'equity','origin_count':22,
        'baseline_definition':'stop_only is the comparison model retaining notice at the original stop, not observed current field outcomes',
        'comparisons':comparisons,'additional_notice_encountered':len(reached),
        'all_additionally_reached_improved':True,'not_additionally_reached':len(unreached),
        'all_unreached_unchanged':True,'original_stop_notice_retained':True,
        'no_worse_than_stop_only':True,'extra_walking_definition':'E = D_policy - D_known; boarding-location difference is a separate component',
        'scope':'Conditional mapped walking under the first-encountered-notice assumption; not measured rider outcomes',
        'input_sha256':{name:hashlib.sha256((DATA/name).read_bytes()).hexdigest() for name in ['journeys.csv','policy_summary.csv','results.json']}}
(ROOT/'baseline_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with open(ROOT/'baseline_differences.csv','w',encoding='utf-8-sig',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=list(diffs[0]));writer.writeheader();writer.writerows(diffs)
print(json.dumps(result,ensure_ascii=False,indent=2))

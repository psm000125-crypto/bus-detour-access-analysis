"""Recompute policy trade-offs from preserved 22-origin results; no network or AI."""
from pathlib import Path
import csv, hashlib, json, math
BASE=Path(__file__).resolve().parents[1]/"data"
ROOT=DATA=BASE/"results"
summary={r['policy']:r for r in csv.DictReader(open(DATA/'policy_summary.csv',encoding='utf-8-sig'))}
journeys=list(csv.DictReader(open(DATA/'journeys.csv',encoding='utf-8-sig')))
peer=json.loads((BASE/'policy_reference.json').read_text(encoding='utf-8'))
raw_result=json.loads((DATA/'results.json').read_text(encoding='utf-8'))
lookups={p:{r['origin']:r for r in journeys if r['policy']==p} for p in summary}
for key,rows in lookups.items():
    assert len(rows)==22
    for field,calculation in [('max_E_m',lambda:max(float(r['E_policy_m']) for r in rows.values())),
                              ('sum_E_m',lambda:sum(float(r['E_policy_m']) for r in rows.values())),
                              ('max_D_m',lambda:max(float(r['D_policy_m']) for r in rows.values()))]:
        assert math.isclose(calculation(),float(summary[key][field]),abs_tol=1e-7)
comparisons={}; differences=[]
for baseline in ['efficiency','coverage_strong']:
    current={}
    for metric in ['max_E_m','sum_E_m','max_D_m','mean_E_m','mean_D_m']:
        before,after=[float(summary[p][metric]) for p in [baseline,'equity']]
        current[metric]={'baseline':before,'recommended':after,'change_m':after-before,'change_percent':100*(after-before)/before}
        other=peer['equity_vs_baseline'][baseline][metric]
        assert math.isclose(current[metric]['change_m'],other['equity_minus_baseline'],abs_tol=1e-7)
        assert math.isclose(current[metric]['change_percent'],other['change_percent'],abs_tol=1e-7)
    counts={'better':0,'worse':0,'same':0}
    for origin,now in lookups['equity'].items():
        old=lookups[baseline][origin]
        change=float(now['D_policy_m'])-float(old['D_policy_m'])
        status='same' if abs(change)<=1e-7 else ('better' if change<0 else 'worse')
        counts[status]+=1
        differences.append({'baseline':baseline,'origin':origin,'label':now['label'],
            'baseline_E_m':float(old['E_policy_m']),'recommended_E_m':float(now['E_policy_m']),
            'change_m':change,'classification':status})
    assert counts==peer['per_origin_equity_vs_baseline'][baseline]['counts']
    current['route_counts']=counts
    comparisons[baseline]=current
eq=summary['equity']
out={'recommended_policy':'equity',
     'selection_order':['minimize maximum additional walking','minimize sum among equal maximum values'],
     'recommended_candidates':next(r['candidates'] for r in raw_result['summary'] if r['policy']=='equity'),
     'scope':'Equally weighted modeled origin routes; not measured disability, age, income or passenger equity outcomes',
     'comparisons':comparisons,
     'recommended_mean_components_m':{'ordinary_stop_approach':float(eq['mean_B_m']),
        'boarding_location_change':float(eq['mean_L_m']),'late_information':float(eq['mean_E_m']),
        'total':float(eq['mean_D_m'])},
     'rounding':'Distance display nearest 10m, components and total independently rounded; percentages from raw values',
     'late_information_share_of_added_distance_percent':100*(1-float(eq['location_share_added'])),
     'remedies':{'new_routes_recomputed':False,'extra_signs_or_budget_verified':False,
        'condition':'Before adopting extra or moved signs, recompute all routes and costs; reject an option increasing the base maximum additional walking',
        'actual_step_free_route_verified':False},
     'input_sha256':{name:hashlib.sha256((DATA/name).read_bytes()).hexdigest() for name in ['results.json','policy_summary.csv','journeys.csv']}}
assert comparisons['efficiency']['route_counts']=={'better':4,'worse':10,'same':8}
assert comparisons['coverage_strong']['route_counts']=={'better':11,'worse':11,'same':0}
assert 26.7<-comparisons['efficiency']['max_E_m']['change_percent']<26.8
assert .64<comparisons['efficiency']['sum_E_m']['change_percent']<.65
(ROOT/'policy_choice.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with open(ROOT/'policy_differences.csv','w',encoding='utf-8-sig',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=list(differences[0]));writer.writeheader();writer.writerows(differences)
print(json.dumps({'recommended_policy':out['recommended_policy'],'versus_sum_minimum':comparisons['efficiency'],
                  'versus_coverage_route_counts':comparisons['coverage_strong']['route_counts']},ensure_ascii=False,indent=2))

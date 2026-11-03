"""Rebuild figures and tables from seven explicit Yanex run IDs. No model/DB calls."""
import hashlib
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import yanex.results as yr
from bondi.workload import Workload

IDS = ['57d6f1c3','8e4ea30b','6654acdc','d78c69d7','52a02a82','af97d240','9190cd17']
OUT = Path(__file__).resolve().parent
rows, failures, batch_rows = [], [], []
for i, run_id in enumerate(IDS, 1):
    exp = yr.get_experiment(run_id)
    metrics = exp.get_metrics(as_dataframe=False)[-1]
    # Artifact API resolves Yanex's actual filenames; these runs flattened batch paths.
    manifest = exp.load_artifact('manifest.json')
    schema = exp.load_artifact('schema.txt')
    workload = exp.load_artifact('workload.jsonl', loader=Workload.load)
    fingerprints = [entry.query.fingerprint() for entry in workload]
    row = dict(prompt=f'p{i}', run_id=run_id, **metrics)
    row.update(unique_queries=len(set(fingerprints)),
               exact_duplicate_queries=len(fingerprints)-len(set(fingerprints)),
               schema_sha256=hashlib.sha256(schema.encode()).hexdigest(),
               unattempted_batches=4-metrics['batches_attempted'])
    row['minutes'] = metrics.get('model_elapsed_ms', float('nan'))/60000
    accepted = metrics['queries_accepted']
    row['output_tokens_per_accepted'] = metrics.get('output_tokens', float('nan'))/accepted if accepted else None
    for index in range(metrics['batches_attempted']):
        batch = exp.load_artifact(f'{index:06d}.json')
        response = batch.get('response') or {}
        text = response.get('text') or ''
        error = batch.get('parse_error')
        outcome = 'call failure' if batch.get('error_type') else 'batch decode failure' if error else 'decoded'
        batch_rows.append(dict(prompt=f'p{i}', run_id=run_id, batch_index=index, outcome=outcome,
                               finish_reason=response.get('finish_reason'), characters=len(text),
                               elapsed_ms=response.get('elapsed_ms'),
                               output_tokens=(response.get('usage') or {}).get('completion_tokens')))
        if error or batch.get('error_type'):
            message = error['message'] if error else batch['error_type']
            pos_match = re.search(r'char (\d+)', message)
            pos = int(pos_match[1]) if pos_match else None
            failures.append(dict(prompt=f'p{i}', run_id=run_id, batch_index=index, outcome=outcome,
                                 error=message, excerpt=text[max(0,pos-100):pos+150] if pos is not None else ''))
    rows.append(row)
df = pd.DataFrame(rows)
df.to_csv(OUT/'summary.csv', index=False)
pd.DataFrame(batch_rows).to_csv(OUT/'batches.csv', index=False)
(OUT/'failures.json').write_text(json.dumps(failures, indent=2))


qwen=pd.read_csv(OUT.parent/'prompt-sweep-q20-b5-2026-11-03/summary.csv')
comparison=df[['prompt','run_id','queries_accepted','minutes','output_tokens_per_accepted','output_tokens','unique_queries']].merge(qwen[['prompt','queries_accepted','minutes','output_tokens_per_accepted','output_tokens']],on='prompt',suffixes=('_sol','_qwen'))
comparison.to_csv(OUT/'comparison.csv',index=False)
rejected=[]
for run_id in IDS:
 records=yr.get_experiment(run_id).load_artifact('candidates.jsonl')
 if isinstance(records,str):records=[json.loads(line) for line in records.splitlines()]
 rejected.extend(dict(run_id=run_id,**r) for r in records if not r['accepted'])
(OUT/'rejected_candidates.json').write_text(json.dumps(rejected,indent=2))
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
x=list(range(7))
for name,cols in [('comparison',[('queries_accepted','Accepted queries','Queries (20 requested)'),('minutes','Generation time','Minutes')]),('efficiency',[('output_tokens_per_accepted','Output tokens per accepted query','Reported output tokens / accepted'),('output_tokens','Total output tokens','Reported output tokens')])]:
 fig,axes=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
 for ax,(col,title,ylabel) in zip(axes,cols):
  for offset,data,label,color in [(-.19,qwen,'Qwen3.6 · thinking off','#a9b6c6'),(.19,df,'GPT-6.1-Sol · low reasoning','#247a92')]:
   ax.bar([v+offset for v in x],data[col],width=.38,label=label,color=color)
  ax.set(xticks=x,xticklabels=df.prompt,title=title,ylabel=ylabel)
  ax.legend(fontsize=8,frameon=False)
  ax.set_ylim(0,max(df[col].max(),qwen[col].max())*1.25)
 fig.suptitle('Same rendered schema · 20 queries per prompt · batch size 5',fontweight='bold')
 for ext in ['png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=180)
 plt.close(fig)
print(comparison.to_string(index=False))
print('Totals',df.queries_accepted.sum(),df.minutes.sum(),df.output_tokens.sum(),df.input_tokens.sum())
print('Qwen totals',qwen.queries_accepted.sum(),qwen.minutes.sum(),qwen.output_tokens.sum())
print('Duplicates',df.exact_duplicate_queries.tolist())

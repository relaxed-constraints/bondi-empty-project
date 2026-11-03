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

IDS = ['28b9755c','669c89c4','8adf1c41','cf3ae5f7','5f3c7b72','4ef16c01','e8999d55']
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

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
bottom=pd.Series([0]*7)
for values,label,color in [(df.queries_accepted,'Accepted','#247a92'),(df.queries_parse_failed,'Query shape rejected','#bd667b'),(df.queries_target_violations,'Wrong target collection','#9b79b6'),(df.batches_parse_failed*5,'Requested slots in undecodable batches','#df9753')]:
 axes[0].bar(df.prompt,values,bottom=bottom,label=label,color=color);bottom+=values
for j,r in df.iterrows(): axes[0].text(j,r.queries_accepted/2,str(r.queries_accepted),ha='center',color='white',fontweight='bold')
axes[0].set(title='Outcome of 20 requested slots',ylabel='Queries / requested slots',ylim=(0,21))
axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.12),fontsize=8,frameon=False)
old=pd.read_csv(OUT.parent/'prompt-sweep-2026-11-03/summary.csv')
x=list(range(7))
axes[1].bar([v-.18 for v in x],old.queries_accepted,width=.36,label='Earlier: 100 queries, batch 10',color='#afb9c5')
axes[1].bar([v+.18 for v in x],df.queries_accepted*5,width=.36,label='Now: 20 queries, batch 5',color='#247a92')
axes[1].set(xticks=x,xticklabels=df.prompt,ylabel='Accepted / requested (%)',title='Descriptive comparison (not a controlled batch-size test)',ylim=(0,110))
axes[1].text(4,5,'Earlier p5: timeout',ha='center',fontsize=8)
axes[1].legend(loc='upper center',bbox_to_anchor=(.5,-.12),fontsize=8,frameon=False)
fig.suptitle('Qwen3.6 • thinking off • shared schema across current runs',fontweight='bold')
for ext in ['png','svg']: fig.savefig(OUT/f'yield.{ext}',dpi=180)
plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
for ax,col,title,ylabel in [(axes[0],'minutes','Generation time','Minutes (completed calls)'),(axes[1],'output_tokens_per_accepted','Output-token efficiency','Output tokens / accepted query')]:
 ax.bar(df.prompt,df[col],color='#247a92')
 for j,r in df.iterrows(): ax.text(j,r[col],f'{r[col]:.1f}',ha='center',va='bottom')
 ax.set(title=title,ylabel=ylabel,ylim=(0,df[col].max()*1.17))
for ext in ['png','svg']: fig.savefig(OUT/f'efficiency.{ext}',dpi=180)
plt.close(fig)
print(df[['prompt','queries_accepted','unique_queries','exact_duplicate_queries','minutes','output_tokens_per_accepted']].to_string(index=False))

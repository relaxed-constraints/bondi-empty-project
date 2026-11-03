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

IDS = ['77f31e59','072f15a0','c5c119de','0fde4fd3','c1da7a1f','cb4bfa15','f97b3445']
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
               unattempted_batches=10-metrics['batches_attempted'])
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
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
colors=['#8265a7','#247a92','#247a92','#8265a7','#b0b6bf','#247a92','#8265a7']
fig, axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
a=axes[0]
a.bar(df.prompt, df.queries_accepted, color=colors)
for j,row in df.iterrows(): a.text(j,row.queries_accepted+2,str(row.queries_accepted),ha='center',fontweight='bold')
a.axhline(100,color='#8a929c',ls='--',lw=1)
a.set(ylim=(0,114),ylabel='Persistable queries accepted',title='Yield from 100 requested queries per prompt')
a.text(4,13,'Stopped after\nfirst timeout',ha='center',fontsize=9)
a=axes[1]
decoded=df.batches_attempted-df.model_calls_failed-df.batches_parse_failed
bottom=pd.Series([0]*7)
for values,label,color in [(decoded,'Decoded response','#247a92'),(df.batches_parse_failed,'Batch decoding failed','#df9753'),(df.model_calls_failed,'Model call failed','#b45156'),(df.unattempted_batches,'Not attempted','#d8dce2')]:
 a.bar(df.prompt,values,bottom=bottom,label=label,color=color);bottom+=values
 a.set(ylim=(0,10.5),ylabel='Batches (10 planned)',title='Where the generation pipeline stopped')
a.legend(loc='upper center',bbox_to_anchor=(.5,-.12),ncol=2,frameon=False,fontsize=9)
fig.suptitle('Qwen3.6 local • thinking off • batch size 10',fontsize=14,fontweight='bold')
fig.savefig(OUT/'yield.png',dpi=180)
fig.savefig(OUT/'yield.svg')
plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
for a,col,title,ylabel in [(axes[0],'minutes','Recorded generation time','Minutes (completed calls)'),(axes[1],'output_tokens_per_accepted','Output-token efficiency','Output tokens / accepted query')]:
 a.bar(df.prompt,df[col],color=colors)
 for j,row in df.iterrows():
  if pd.notna(row[col]): a.text(j,row[col],f'{row[col]:.1f}',ha='center',va='bottom',fontsize=10)
 a.set(title=title,ylabel=ylabel)
 a.set_ylim(0,df[col].max()*1.16)
 a.text(4,df[col].max()*.08,'No recorded\nusage/time',ha='center',fontsize=9)
fig.suptitle('Complex aggregation prompts generate much longer responses',fontsize=14,fontweight='bold')
fig.savefig(OUT/'efficiency.png',dpi=180)
fig.savefig(OUT/'efficiency.svg')
plt.close(fig)
print(df[['prompt','queries_accepted','unique_queries','exact_duplicate_queries','minutes','output_tokens_per_accepted']].to_string(index=False))

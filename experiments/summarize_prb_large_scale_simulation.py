from __future__ import annotations
import argparse, csv, json, statistics
from pathlib import Path

SCALES=("L10","XL10","XXL10")
SEEDS=tuple(range(20260921,20260931))
METHODS=("pure_benders","aggregate_benders_structured_oracle","prb_benders")

def rj(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def q(xs,p):
    if not xs:return None
    xs=sorted(float(x) for x in xs)
    if len(xs)==1:return xs[0]
    pos=p*(len(xs)-1); lo=int(pos); hi=min(lo+1,len(xs)-1); w=pos-lo
    return xs[lo]*(1-w)+xs[hi]*w

def stats(xs):
    xs=[float(x) for x in xs]
    return (statistics.median(xs),q(xs,.25),q(xs,.75)) if xs else (None,None,None)

def first_at(hist,obj,t):
    if not hist:return None
    lb1=float(hist[0]["lower_bound"]); den=obj-lb1
    if abs(den)<=1e-12:return int(hist[0]["iteration"])
    for row in hist:
        p=(float(row["lower_bound"])-lb1)/den
        if p>=t-1e-12:return int(row["iteration"])
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("root",type=Path); a=ap.parse_args(); root=a.root
    rows=[]
    for p in root.glob("*/*/*/result.json"):
        d = rj(p)

        task = d.get("task")

        if task == "PREPARE":
            continue

        # TIME_LIMIT / RESOURCE_STOP / ERROR 终止记录
        # 可能只有 task，没有单独的 method 字段。
        if not d.get("method") and task:
            d["method"] = task

        # 如果既没有 method，也没有可识别的 task，
        # 说明不是有效算法运行记录，直接忽略。
        if not d.get("method"):
            continue
        d["_dir"] = str(p.parent)
        if d.get("exact_certification") is True and d.get("objective") is not None and (p.parent/"iteration_log.json").exists():
            h=rj(p.parent/"iteration_log.json"); obj=float(d["objective"])
            d["iter90"]=first_at(h,obj,.90); d["iter95"]=first_at(h,obj,.95); d["iter99"]=first_at(h,obj,.99)
        else:d["iter90"]=d["iter95"]=d["iter99"]=None
        rows.append(d)
    if not rows:raise RuntimeError("No algorithm results found")

    idx={(x["scale"],int(x["seed"]),x["method"]):x for x in rows}
    completeness=[]
    for scale in SCALES:
        for seed in SEEDS:
            prepare_path=root/scale/str(seed)/"PREPARE/result.json"
            prepare=rj(prepare_path) if prepare_path.exists() else {}
            records={method:idx.get((scale,seed,method),{}) for method in METHODS}
            objectives=[float(records[m]["objective"]) for m in METHODS
                        if records[m].get("exact_certification") is True and records[m].get("objective") is not None]
            triple=(len(objectives)==3 and max(objectives)-min(objectives)<=1e-4)
            completeness.append({"scale":scale,"seed":seed,"prepare_status":prepare.get("status","MISSING"),
                                 "pure_status":records["pure_benders"].get("status","MISSING"),
                                 "aggregate_status":records["aggregate_benders_structured_oracle"].get("status","MISSING"),
                                 "prb_status":records["prb_benders"].get("status","MISSING"),
                                 "triple_certified":triple})
    with (root/"simulation_completeness_table.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(completeness[0]));w.writeheader();w.writerows(completeness)

    fields=["scale","seed","method","status","exact_certification","objective","iterations","cuts",
            "core_runtime_seconds","master_runtime_seconds","oracle_runtime_seconds","certification_runtime_seconds",
            "peak_process_tree_memory_gib","iter90","iter95","iter99"]
    with (root/"simulation_run_table.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for d in sorted(rows,key=lambda x:(x["scale"],int(x["seed"]),x["method"])):w.writerow({k:d.get(k) for k in fields})

    groups=[]
    for scale in (*SCALES,"pooled"):
        for method in METHODS:
            g=[x for x in rows if (scale=="pooled" or x["scale"]==scale) and x["method"]==method]
            c=[x for x in g if x.get("exact_certification") is True]
            rec={"scale":scale,"method":method,"n_total":len(g),"n_certified":len(c),
                 "certification_rate":len(c)/len(g) if g else None,
                 "n_timeout":sum(x.get("status")=="TIME_LIMIT" for x in g),
                 "n_resource_stop":sum(x.get("status")=="RESOURCE_STOP" for x in g),
                 "n_error":sum(x.get("status")=="ERROR" for x in g)}
            for name,key in [("tcore","core_runtime_seconds"),("iterations","iterations"),("master","master_runtime_seconds"),
                             ("oracle","oracle_runtime_seconds"),("iter90","iter90"),("iter95","iter95"),("iter99","iter99")]:
                vals=[x[key] for x in c if x.get(key) is not None]; med,q1,q3=stats(vals)
                rec[name+"_median"]=med; rec[name+"_q1"]=q1; rec[name+"_q3"]=q3
            groups.append(rec)
    gf=list(groups[0].keys())
    with (root/"simulation_group_summary.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=gf); w.writeheader(); w.writerows(groups)

    pairs=[]
    for scale in sorted({x["scale"] for x in rows}):
        seeds=sorted({int(x["seed"]) for x in rows if x["scale"]==scale})
        for seed in seeds:
            p=idx.get((scale,seed,"pure_benders")); ag=idx.get((scale,seed,"aggregate_benders_structured_oracle")); prb=idx.get((scale,seed,"prb_benders"))
            if not p or not ag or not prb:continue
            if not all(x.get("exact_certification") is True for x in (p,ag,prb)):continue
            objs=[float(x["objective"]) for x in (p,ag,prb)]
            if max(objs)-min(objs)>1e-4:continue
            pairs.append({"scale":scale,"seed":seed,
                          "pure_iterations":p["iterations"],"aggregate_iterations":ag["iterations"],"prb_iterations":prb["iterations"],
                          "prb_over_aggregate_iteration_ratio":float(prb["iterations"])/float(ag["iterations"]),
                          "prb_over_pure_iteration_ratio":float(prb["iterations"])/float(p["iterations"]),
                          "aggregate_over_prb_tcore_ratio":float(ag["core_runtime_seconds"])/float(prb["core_runtime_seconds"]),
                          "pure_over_prb_tcore_ratio":float(p["core_runtime_seconds"])/float(prb["core_runtime_seconds"])})
    if pairs:
        pf=list(pairs[0].keys())
        with (root/"simulation_paired_comparisons.csv").open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=pf); w.writeheader(); w.writerows(pairs)
        ratio_fields=("prb_over_aggregate_iteration_ratio","prb_over_pure_iteration_ratio",
                      "aggregate_over_prb_tcore_ratio","pure_over_prb_tcore_ratio")
        pair_summary=[]
        for scope in (*SCALES,"pooled"):
            selected=[x for x in pairs if scope=="pooled" or x["scale"]==scope]
            for metric in ratio_fields:
                med,q1,q3=stats([x[metric] for x in selected])
                pair_summary.append({"scope":scope,"metric":metric,"n":len(selected),
                                     "median":med,"q1":q1,"q3":q3})
        with (root/"simulation_paired_comparison_summary.csv").open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=list(pair_summary[0]));w.writeheader();w.writerows(pair_summary)
    print("Summary written to",root)

if __name__=="__main__":main()
